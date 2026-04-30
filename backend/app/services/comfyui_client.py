"""v1.1.55 — ComfyUI HTTP 클라이언트

같은 네트워크의 ComfyUI 서버에 워크플로 JSON 을 제출하고 결과 파일을 내려
받는 공용 헬퍼. 이미지/영상 서비스 양쪽에서 재사용한다.

설정
----
`COMFYUI_BASE_URL` 환경변수 (예: `http://192.168.0.45:8188`). 비어있으면
`NotConfiguredError` 를 던진다.

핵심 흐름
---------
1) `upload_image(abs_path)` — 필요 시 (영상 I2V 의 start_image) ComfyUI 서버
   에 소스 이미지를 올려 `filename` 을 얻는다.
2) `submit(prompt_graph)` — `/prompt` 에 API 그래프를 POST, `prompt_id`
   반환.
3) `wait_for(prompt_id)` — `/history/{prompt_id}` 를 주기적으로 조회해 완료
   까지 대기. 실패하면 예외.
4) `download_first_output(history, dest_path, kinds=("images","videos"))` —
   결과 노드에서 첫 산출물을 `/view` 로 받아 `dest_path` 에 기록.
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx

from app.config import COMFYUI_BASE_URL


class NotConfiguredError(RuntimeError):
    """COMFYUI_BASE_URL 미설정."""


class ComfyUIError(RuntimeError):
    """ComfyUI 서버가 오류를 반환했거나 타임아웃."""


# v1.2.25: cancel 컨텍스트는 공용 모듈로 이전됨 (`app.services.cancel_ctx`).
# ComfyUI 뿐 아니라 fal.ai / OpenAI / ElevenLabs 등 모든 외부 API 서비스가
# 같은 메커니즘을 공유한다. 아래 심볼은 하위 호환 용 재수출.
from app.services.cancel_ctx import (  # noqa: E402
    OperationCancelled as _OperationCancelled,
    set_cancel_key as _set_cancel_key_shared,
    get_cancel_key as _get_cancel_key_shared,
    is_cancelled as _is_cancelled_shared,
    raise_if_cancelled as _raise_if_cancelled_shared,
)


class ComfyUICancelled(ComfyUIError, _OperationCancelled):
    """파이프라인 cancel 플래그가 세팅되어 ComfyUI 호출을 차단.

    v1.2.24 에서 도입, v1.2.25 에서 공용 `OperationCancelled` 를 같이 상속해
    구버전 `except ComfyUICancelled` 와 신버전 `except OperationCancelled`
    어느 쪽으로 잡아도 동일하게 처리된다.
    """


# 통신 파라미터 — 느린 이미지/영상 워크플로를 견뎌야 하므로 넉넉히.
SUBMIT_TIMEOUT = 30.0       # /prompt, /upload/image 자체는 빠름
POLL_INTERVAL = 1.5         # /history 폴링 주기(초)
DOWNLOAD_TIMEOUT = 120.0    # /view 로 큰 영상 받을 때 대비


def set_cancel_key(key: Optional[str]) -> None:
    """(하위 호환) 공용 cancel_ctx 로 위임.

    기존 pipeline_tasks 에서 `comfyui_client.set_cancel_key(...)` 호출하는
    코드를 그대로 유지하기 위해 남긴 얇은 wrapper. 내부는 전 서비스가 공유하는
    단일 thread-local 을 세팅한다.
    """
    _set_cancel_key_shared(key)


def get_cancel_key() -> Optional[str]:
    return _get_cancel_key_shared()


def _is_cancelled() -> bool:
    return _is_cancelled_shared()


def raise_if_cancelled(where: str = "") -> None:
    """공용 cancel 체크를 돌리고, 걸리면 `ComfyUICancelled` 로 재포장해 raise.

    (공용 `OperationCancelled` 대신 이 서브클래스로 올려야 기존 ComfyUI 서비스
    쪽 `except ComfyUICancelled` 핸들러가 그대로 작동한다.)
    """
    if _is_cancelled_shared():
        key = get_cancel_key()
        raise ComfyUICancelled(
            f"[cancelled] pipeline:cancel:{key} 세팅됨 — {where or 'comfyui'} 차단"
        )


def _require_base_url() -> str:
    if not COMFYUI_BASE_URL:
        raise NotConfiguredError(
            "COMFYUI_BASE_URL 이 설정되지 않았습니다. .env 에 "
            "COMFYUI_BASE_URL=http://<IP>:<PORT> 를 추가하세요."
        )
    return COMFYUI_BASE_URL


def _client_id() -> str:
    """워크플로 제출 시 서버가 클라이언트를 구분하는 데 쓰는 ID."""
    return f"longtube-{uuid.uuid4().hex[:12]}"


def new_client_id() -> str:
    return _client_id()


def _websocket_url(base_url: str, client_id: str) -> str:
    parts = urlsplit(base_url)
    scheme = "wss" if parts.scheme == "https" else "ws"
    query = urlencode({"clientId": client_id})
    return urlunsplit((scheme, parts.netloc, f"{parts.path.rstrip('/')}/ws", query, ""))


def _node_classes(prompt_graph: Optional[dict]) -> dict[str, str]:
    if not isinstance(prompt_graph, dict):
        return {}
    out: dict[str, str] = {}
    for node_id, node in prompt_graph.items():
        if isinstance(node, dict):
            out[str(node_id)] = str(node.get("class_type") or node_id)
    return out


def _emit_progress(cb: Optional[Callable[[dict], None]], event: dict) -> None:
    if not cb:
        return
    try:
        cb(event)
    except Exception:
        pass


async def _watch_prompt_ws(
    *,
    base_url: str,
    client_id: str,
    prompt_id: str,
    prompt_graph: Optional[dict],
    on_progress: Optional[Callable[[dict], None]],
) -> None:
    """Listen to ComfyUI websocket events for live node/progress logs."""
    if not on_progress:
        return
    try:
        import websockets
    except Exception as e:
        _emit_progress(on_progress, {"type": "watch_unavailable", "error": str(e)})
        return

    node_classes = _node_classes(prompt_graph)
    try:
        async with websockets.connect(
            _websocket_url(base_url, client_id),
            ping_interval=None,
            close_timeout=1,
        ) as ws:
            async for raw in ws:
                if isinstance(raw, bytes):
                    continue
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                msg_type = msg.get("type")
                data = msg.get("data") or {}
                event_prompt_id = data.get("prompt_id")
                if event_prompt_id and event_prompt_id != prompt_id:
                    continue

                if msg_type == "progress":
                    node_id = str(data.get("node") or data.get("node_id") or "")
                    _emit_progress(
                        on_progress,
                        {
                            "type": "progress",
                            "value": data.get("value"),
                            "max": data.get("max"),
                            "node_id": node_id,
                            "node_class": node_classes.get(node_id, node_id),
                        },
                    )
                elif msg_type in {
                    "execution_start",
                    "execution_cached",
                    "executing",
                    "executed",
                    "execution_success",
                    "execution_error",
                }:
                    node_id = str(data.get("node") or data.get("node_id") or "")
                    _emit_progress(
                        on_progress,
                        {
                            "type": msg_type,
                            "node_id": node_id,
                            "node_class": node_classes.get(node_id, node_id),
                            "data": data,
                        },
                    )
                    if msg_type in {"execution_success", "execution_error"}:
                        return
    except asyncio.CancelledError:
        raise
    except Exception as e:
        _emit_progress(on_progress, {"type": "watch_error", "error": str(e)})


async def upload_image(src_abs_path: str, *, overwrite: bool = True) -> str:
    """로컬 이미지를 ComfyUI /upload/image 로 올리고, 서버가 알려준 filename
    을 반환. 이 값을 LoadImage 노드의 `image` 필드에 넣는다.

    v1.2.24: 워크플로 제출 전에 cancel 플래그가 걸려 있으면 업로드도 스킵.
    업로드 자체가 GPU 비용을 쓰진 않지만, 이미 중지된 작업이 파일을 서버에
    쌓는 것 자체가 리소스 낭비라 초기에 차단한다.
    """
    raise_if_cancelled("upload_image")
    base = _require_base_url()
    p = Path(src_abs_path)
    if not p.exists():
        raise FileNotFoundError(src_abs_path)

    # 업로드 파일명 충돌을 막기 위해 uuid 프리픽스 추가
    upload_name = f"lt_{uuid.uuid4().hex[:10]}_{p.name}"

    async with httpx.AsyncClient(timeout=SUBMIT_TIMEOUT) as client:
        with open(p, "rb") as fh:
            files = {"image": (upload_name, fh, "application/octet-stream")}
            data = {
                "overwrite": "true" if overwrite else "false",
                "type": "input",
            }
            r = await client.post(f"{base}/upload/image", files=files, data=data)
            if r.status_code != 200:
                raise ComfyUIError(
                    f"/upload/image {r.status_code}: {r.text[:400]}"
                )
            payload = r.json()
            # ComfyUI 는 {"name": "...", "subfolder": "", "type": "input"} 반환
            return payload.get("name") or upload_name


async def submit(prompt_graph: dict, *, client_id: Optional[str] = None) -> str:
    """워크플로 그래프 제출 → prompt_id 반환.

    v1.2.24: 호출 직전에 cancel 플래그를 확인해 이미 중지된 작업이면 `/prompt`
    를 아예 쏘지 않고 `ComfyUICancelled` 로 이탈. `cancel_task` 가 설정한
    redis 플래그를 워커 스레드의 다음 컷 제출 전에 반드시 존중하도록 하는
    마지막 방어선.
    """
    # 🛑 돈줄 차단 최종 방어선 — 한 번 더 cancel 을 확인한 뒤 /prompt 를 쏜다.
    raise_if_cancelled("submit")
    base = _require_base_url()
    body = {"prompt": prompt_graph, "client_id": client_id or _client_id()}
    async with httpx.AsyncClient(timeout=SUBMIT_TIMEOUT) as client:
        r = await client.post(f"{base}/prompt", json=body)
        if r.status_code != 200:
            raise ComfyUIError(f"/prompt {r.status_code}: {r.text[:600]}")
        j = r.json()
        pid = j.get("prompt_id")
        if not pid:
            raise ComfyUIError(f"/prompt: prompt_id 누락 {j}")
        return pid


async def wait_for(
    prompt_id: str,
    *,
    total_timeout: float = 900.0,
    client_id: Optional[str] = None,
    prompt_graph: Optional[dict] = None,
    on_progress: Optional[Callable[[dict], None]] = None,
) -> dict:
    """`/history/{prompt_id}` 폴링. 완료된 엔트리를 반환.

    완료 판정: `status.completed == True` 또는 `outputs` 가 채워져 있음.
    실패 시 `ComfyUIError` (status.messages 에 에러 스택 포함).

    v1.2.24: 폴링 루프 매 반복마다 cancel 플래그를 확인. 세팅돼 있으면 즉시
    ComfyUI `/interrupt` 를 쏘고 `ComfyUICancelled` 로 이탈해서 워커 스레드가
    다음 컷 제출로 흘러가지 못하게 한다.
    """
    base = _require_base_url()
    deadline = asyncio.get_event_loop().time() + total_timeout
    ws_task = None
    if client_id and on_progress:
        ws_task = asyncio.create_task(
            _watch_prompt_ws(
                base_url=base,
                client_id=client_id,
                prompt_id=prompt_id,
                prompt_graph=prompt_graph,
                on_progress=on_progress,
            )
        )
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            while True:
                # 🛑 매 폴링 사이에 cancel 확인 — `/interrupt` 한 번 더 쏘고 이탈.
                if _is_cancelled():
                    try:
                        # 베스트 에포트: 현재 돌고 있는 prompt 도 서버에서 끊는다.
                        await client.post(f"{base}/interrupt")
                    except Exception:
                        pass
                    raise ComfyUICancelled(
                        f"[cancelled] wait_for({prompt_id}) 도중 사용자 중지 감지"
                    )
                if asyncio.get_event_loop().time() >= deadline:
                    raise ComfyUIError(
                        f"prompt {prompt_id} 완료 대기 타임아웃 ({total_timeout:.0f}s)"
                    )
                try:
                    r = await client.get(f"{base}/history/{prompt_id}")
                except httpx.HTTPError:
                    # 일시 오류는 다음 폴링에 재시도
                    await asyncio.sleep(POLL_INTERVAL)
                    continue
                if r.status_code != 200:
                    await asyncio.sleep(POLL_INTERVAL)
                    continue
                data = r.json() or {}
                entry = data.get(prompt_id)
                if not entry:
                    await asyncio.sleep(POLL_INTERVAL)
                    continue
                status = entry.get("status") or {}
                status_str = status.get("status_str")
                if status_str == "error":
                    msgs = status.get("messages") or []
                    raise ComfyUIError(
                        f"ComfyUI 실행 실패 ({prompt_id}): {msgs}"
                    )
                if status.get("completed") or entry.get("outputs"):
                    return entry
                await asyncio.sleep(POLL_INTERVAL)
        finally:
            if ws_task:
                ws_task.cancel()
                try:
                    await ws_task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass


def execution_seconds(history_entry: dict) -> Optional[float]:
    messages = ((history_entry or {}).get("status") or {}).get("messages") or []
    start = None
    success = None
    for item in messages:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        kind, data = item[0], item[1] or {}
        if kind == "execution_start":
            start = data.get("timestamp")
        elif kind == "execution_success":
            success = data.get("timestamp")
    try:
        if start is not None and success is not None:
            return max(0.0, (float(success) - float(start)) / 1000.0)
    except (TypeError, ValueError):
        return None
    return None


def cached_node_count(history_entry: dict) -> int:
    messages = ((history_entry or {}).get("status") or {}).get("messages") or []
    cached: set[str] = set()
    for item in messages:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        kind, data = item[0], item[1] or {}
        if kind == "execution_cached":
            for node_id in data.get("nodes") or []:
                cached.add(str(node_id))
    return len(cached)


async def system_stats() -> dict:
    base = _require_base_url()
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(f"{base}/system_stats")
        if r.status_code != 200:
            raise ComfyUIError(f"/system_stats {r.status_code}: {r.text[:300]}")
        return r.json() or {}


def first_device_vram_text(stats: dict) -> Optional[str]:
    devices = (stats or {}).get("devices") or []
    if not devices:
        return None
    dev = devices[0] or {}
    try:
        total = float(dev.get("vram_total") or 0) / (1024 ** 3)
        free = float(dev.get("vram_free") or 0) / (1024 ** 3)
    except (TypeError, ValueError):
        return None
    name = str(dev.get("name") or "GPU").split(" : ", 1)[0]
    return f"{name}, VRAM {free:.1f}/{total:.1f}GB free"


async def download_first_output(
    history_entry: dict,
    dest_path: str,
    kinds: tuple[str, ...] = ("images", "videos", "gifs"),
) -> str:
    """history 엔트리에서 첫 번째 산출물(이미지 또는 영상) 을 다운로드.

    ComfyUI outputs 스키마:
      outputs[node_id][kind] = [{"filename": "...", "subfolder": "", "type": "output"}, ...]
    `kinds` 순서대로 처음 찾은 것을 내려받는다. `dest_path` 확장자에 맞춰 저장.
    """
    base = _require_base_url()
    outputs = (history_entry or {}).get("outputs") or {}

    target = None
    for node_id, outs in outputs.items():
        if not isinstance(outs, dict):
            continue
        for k in kinds:
            arr = outs.get(k)
            if arr:
                target = arr[0]
                break
        if target:
            break
    if not target:
        raise ComfyUIError(
            f"ComfyUI 출력에서 산출물을 찾지 못함. outputs={list(outputs.keys())}"
        )

    params = {
        "filename": target.get("filename", ""),
        "subfolder": target.get("subfolder", ""),
        "type": target.get("type", "output"),
    }

    async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT) as client:
        r = await client.get(f"{base}/view", params=params)
        if r.status_code != 200:
            raise ComfyUIError(
                f"/view {r.status_code} filename={params['filename']}: {r.text[:300]}"
            )
        os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
        with open(dest_path, "wb") as fh:
            fh.write(r.content)
    return dest_path


async def interrupt() -> bool:
    """ComfyUI 서버의 현재 실행 중 prompt 를 즉시 중단 (`POST /interrupt`).

    v1.1.70: 비상 정지용. 제출된 prompt_id 의 진행 중 실행을 끊는다.
    대기 큐에 있는 prompt 는 건드리지 않으므로 보통 `clear_queue()` 와
    함께 호출한다. 실패해도 예외를 올리지 않는다 (베스트 에포트).

    Returns: True on success, False on failure or not configured.
    """
    if not COMFYUI_BASE_URL:
        return False
    base = COMFYUI_BASE_URL
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{base}/interrupt")
            ok = r.status_code in (200, 204)
            if ok:
                print("[comfyui] /interrupt 호출 성공 — 실행 중 prompt 중단")
            else:
                print(f"[comfyui] /interrupt 실패 {r.status_code}: {r.text[:200]}")
            return ok
    except Exception as e:
        print(f"[comfyui] /interrupt 예외 (무시): {e}")
        return False


async def clear_queue() -> bool:
    """ComfyUI 서버의 대기 큐 전체를 비움 (`POST /queue` with `{"clear": true}`).

    v1.1.70: 비상 정지용. 아직 실행 시작 전 대기열에 쌓인 prompt 를 제거한다.
    현재 실행 중인 prompt 는 영향을 받지 않으므로 `interrupt()` 와 함께 호출.
    실패해도 예외를 올리지 않는다 (베스트 에포트).

    Returns: True on success, False on failure or not configured.
    """
    if not COMFYUI_BASE_URL:
        return False
    base = COMFYUI_BASE_URL
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{base}/queue", json={"clear": True})
            ok = r.status_code in (200, 204)
            if ok:
                print("[comfyui] /queue clear 호출 성공 — 대기 큐 비움")
            else:
                print(f"[comfyui] /queue clear 실패 {r.status_code}: {r.text[:200]}")
            return ok
    except Exception as e:
        print(f"[comfyui] /queue clear 예외 (무시): {e}")
        return False


async def free_memory(*, unload_models: bool = True, free_memory: bool = True) -> bool:
    """ComfyUI /free 엔드포인트 호출 → VRAM 에 올라간 모델/캐시 해제.

    배치 작업(이미지/영상 전체 생성)이 끝난 뒤 호출해 GPU 메모리를 돌려받는다.
    실패해도 예외를 올리지 않는다 (베스트 에포트). COMFYUI_BASE_URL 미설정이면
    False 반환.

    Returns: True on success, False on failure or not configured.
    """
    if not COMFYUI_BASE_URL:
        return False
    base = COMFYUI_BASE_URL
    body = {"unload_models": bool(unload_models), "free_memory": bool(free_memory)}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{base}/free", json=body)
            ok = r.status_code in (200, 204)
            if ok:
                print(f"[comfyui] /free 호출 성공 (unload={unload_models}, free={free_memory})")
            else:
                print(f"[comfyui] /free 실패 {r.status_code}: {r.text[:200]}")
            return ok
    except Exception as e:
        print(f"[comfyui] /free 예외 (무시): {e}")
        return False


def render_workflow(
    template: dict, substitutions: dict
) -> dict:
    """워크플로 JSON 의 `${KEY}` 자리표를 `substitutions[KEY]` 로 치환.

    str 값이면 문자열 format, int 로 "된" 자리표(예: width="${WIDTH}")는
    숫자로 변환. JSON 을 보존하기 위해 재귀 복제.
    """
    import copy
    import re

    ph_re = re.compile(r"^\$\{([A-Z_]+)\}$")

    def _walk(node):
        if isinstance(node, dict):
            # _meta 키는 실행 그래프에 넘기지 않음
            return {k: _walk(v) for k, v in node.items() if k != "_meta"}
        if isinstance(node, list):
            return [_walk(v) for v in node]
        if isinstance(node, str):
            m = ph_re.match(node)
            if m:
                key = m.group(1)
                if key not in substitutions:
                    raise KeyError(f"워크플로 치환 누락: {key}")
                return substitutions[key]
            # 문자열 안에 ${...} 가 섞여 있으면 문자열로 format
            if "${" in node:
                out = node
                for k, v in substitutions.items():
                    out = out.replace(f"${{{k}}}", str(v))
                return out
            return node
        return node

    return _walk(copy.deepcopy(template))
