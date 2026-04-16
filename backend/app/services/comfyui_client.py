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
import os
import uuid
from pathlib import Path
from typing import Optional

import httpx

from app.config import COMFYUI_BASE_URL


class NotConfiguredError(RuntimeError):
    """COMFYUI_BASE_URL 미설정."""


class ComfyUIError(RuntimeError):
    """ComfyUI 서버가 오류를 반환했거나 타임아웃."""


# 통신 파라미터 — 느린 이미지/영상 워크플로를 견뎌야 하므로 넉넉히.
SUBMIT_TIMEOUT = 30.0       # /prompt, /upload/image 자체는 빠름
POLL_INTERVAL = 1.5         # /history 폴링 주기(초)
DOWNLOAD_TIMEOUT = 120.0    # /view 로 큰 영상 받을 때 대비


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


async def upload_image(src_abs_path: str, *, overwrite: bool = True) -> str:
    """로컬 이미지를 ComfyUI /upload/image 로 올리고, 서버가 알려준 filename
    을 반환. 이 값을 LoadImage 노드의 `image` 필드에 넣는다.
    """
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


async def submit(prompt_graph: dict) -> str:
    """워크플로 그래프 제출 → prompt_id 반환."""
    base = _require_base_url()
    body = {"prompt": prompt_graph, "client_id": _client_id()}
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
    prompt_id: str, *, total_timeout: float = 900.0
) -> dict:
    """`/history/{prompt_id}` 폴링. 완료된 엔트리를 반환.

    완료 판정: `status.completed == True` 또는 `outputs` 가 채워져 있음.
    실패 시 `ComfyUIError` (status.messages 에 에러 스택 포함).
    """
    base = _require_base_url()
    deadline = asyncio.get_event_loop().time() + total_timeout
    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            if asyncio.get_event_loop().time() >= deadline:
                raise ComfyUIError(
                    f"prompt {prompt_id} 완료 대기 타임아웃 ({total_timeout:.0f}s)"
                )
            try:
                r = await client.get(f"{base}/history/{prompt_id}")
            except httpx.HTTPError as e:
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
