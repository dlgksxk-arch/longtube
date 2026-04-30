"""Nano Banana (Google Gemini Flash Image) via fal.ai.

fal.ai 는 Google 의 Gemini 2.5 Flash Image (속칭 "Nano Banana") 모델을 퍼블릭
엔드포인트로 호스팅합니다. 이 서비스는 그 엔드포인트를 직접 호출합니다.

동작:
- `reference_images` 가 비어있으면: `fal-ai/nano-banana` (text-to-image).
- `reference_images` 가 있으면: `fal-ai/nano-banana/edit` (image edit / i2i).
  로컬 파일들을 base64 data URI 로 인코딩해 `image_urls` 로 넘깁니다 —
  multimodal 편집 엔드포인트가 data URI 를 입력 이미지로 받아주므로
  별도의 storage 업로드가 필요 없습니다.

nano-banana / nano-banana-2 / nano-banana-3 모두 같은 기반 모델을 쓰지만,
`nano-banana-3` 는 **레퍼런스 이미지 스타일 유지**를 강하게 유도하는 기본
프롬프트 프리픽스가 추가된 프리셋입니다. nano-banana-pro 는 fal.ai 의
`nano-banana-pro` 엔드포인트(더 무거운 버전)를 사용합니다.

v1.2.20: **폴백 완전 제거**. 사용자 요구 — "API 이용할 때 설정된 모델의 API 연결
안되있을때 알림창 띄우고 풀백으로 처리하지마." FAL_KEY 누락이나 엔드포인트 실패
시 Flux Dev 등 다른 모델로 자동 전환하지 않고 명시적 RuntimeError 를 올린다.
호출 측(파이프라인) 에서 task.error 로 전파되어 UI 알림으로 노출된다.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
from pathlib import Path
from typing import Optional

import httpx

from app.services.image.base import BaseImageService
from app.services.cancel_ctx import raise_if_cancelled  # v1.2.25 cancel 방어
from app import config

FAL_BASE = "https://queue.fal.run"

# 모델 ID → fal.ai endpoint 매핑
_ENDPOINTS = {
    "nano-banana":     "fal-ai/nano-banana",
    "nano-banana-2":   "fal-ai/nano-banana",
    "nano-banana-3":   "fal-ai/nano-banana",
    "nano-banana-pro": "fal-ai/nano-banana-pro",
}

_DISPLAY_NAMES = {
    "nano-banana":     "Nano Banana",
    "nano-banana-2":   "Nano Banana 2",
    "nano-banana-3":   "Nano Banana 3",
    "nano-banana-pro": "Nano Banana Pro",
}

# 레퍼런스 이미지 최대 개수 (payload 크기 방어)
_MAX_REFS = 4


def _safe_json(resp: httpx.Response, where: str) -> dict:
    try:
        return resp.json()
    except (json.JSONDecodeError, ValueError):
        body_preview = (resp.text or "").strip()[:200] or "<empty body>"
        raise RuntimeError(
            f"fal.ai 응답을 JSON 으로 해석할 수 없습니다 ({where}, "
            f"status={resp.status_code}): {body_preview}"
        )


def _file_to_data_uri(path: str) -> Optional[str]:
    """로컬 이미지 파일을 base64 data URI 로 변환. 실패 시 None."""
    try:
        p = Path(path)
        if not p.exists() or p.stat().st_size == 0:
            return None
        ext = p.suffix.lower().lstrip(".")
        mime = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
            "gif": "image/gif",
        }.get(ext, "image/png")
        data = p.read_bytes()
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except (OSError, PermissionError) as e:
        print(f"[nano-banana] 레퍼런스 이미지 읽기 실패 ({path}): {e}")
        return None


class NanoBananaService(BaseImageService):
    """Google Gemini Flash Image (Nano Banana) via fal.ai."""

    MODELS = _DISPLAY_NAMES  # 하위 호환 — 기존 코드가 이 속성을 참조할 수 있음
    supports_reference_images = True

    def __init__(self, model_id: str = "nano-banana-3"):
        self.model_id = model_id
        self.display_name = _DISPLAY_NAMES.get(model_id, model_id)
        self._endpoint = _ENDPOINTS.get(model_id, "fal-ai/nano-banana")
        # "-3" 프리셋: 레퍼런스 이미지 스타일 유지를 강하게 유도
        self._style_lock = model_id == "nano-banana-3"

    async def generate(
        self,
        prompt: str,
        width: int,
        height: int,
        output_path: str,
        reference_images: Optional[list[str]] = None,
    ) -> str:
        # v1.1.63: UI 에서 바꾼 키가 즉시 반영되도록 매 호출마다 config 에서 읽음.
        fal_key = config.FAL_KEY
        if not fal_key:
            raise RuntimeError(
                f"{self.display_name} 은(는) fal.ai 가 호스팅하는 "
                f"Gemini Flash Image 엔드포인트를 사용합니다. FAL_KEY 환경변수가 "
                f"비어 있습니다. .env 에 FAL_KEY 를 넣거나 이미지 모델을 OpenAI "
                f"(openai-image-1) 로 바꿔주세요."
            )

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # 레퍼런스 이미지가 있으면 edit 엔드포인트로 i2i, 없으면 기본 t2i.
        # ★ 과거 버그: 레퍼런스가 주어졌는데 _file_to_data_uri 가 전부 None 이면
        # ref_data_uris 가 비고 조용히 t2i 로 떨어져서 사용자가 등록한 스타일이
        # 완전히 무시됐다. 이제는 "레퍼런스를 넘겼는데 하나도 못 읽으면" 명시적
        # RuntimeError 를 올려서 원인이 드러나게 한다.
        ref_data_uris: list[str] = []
        read_failures: list[str] = []
        if reference_images:
            for p in reference_images[:_MAX_REFS]:
                uri = _file_to_data_uri(p)
                if uri:
                    ref_data_uris.append(uri)
                else:
                    read_failures.append(p)
            if not ref_data_uris:
                raise RuntimeError(
                    f"레퍼런스 이미지를 하나도 읽지 못했습니다 — 순수 t2i 로 "
                    f"폴백하지 않고 중단합니다. 실패 경로: {read_failures[:5]}"
                )

        use_edit = bool(ref_data_uris)
        endpoint = f"{self._endpoint}/edit" if use_edit else self._endpoint

        # v1.1.55: 공통 REFERENCE_STYLE_PREFIX 사용. 모든 nano-banana 변종에서
        # use_edit 이면 예외 없이 스타일 락 프리픽스를 붙인다. 중복 검사는 헬퍼가 수행.
        effective_prompt = prompt
        if use_edit:
            from app.services.image.prompt_builder import apply_reference_style_prefix
            effective_prompt = apply_reference_style_prefix(prompt, has_reference=True)

        payload: dict = {
            "prompt": effective_prompt,
            "num_images": 1,
            # v1.1.30: edit 모드에서도 항상 image_size 를 넘긴다. 과거에는 edit
            # 가 ref 크기를 상속한다고 가정해서 image_size 를 생략했는데, 그러면
            # 사용자의 레퍼런스가 1:1 square 일 때 16:9 요청을 줘도 square 가
            # 나와서 컷 영상이 letterbox/크롭으로 망가진다. fal.ai nano-banana
            # edit 는 image_size 파라미터를 허용하므로 명시적으로 강제한다.
            "image_size": {"width": width, "height": height},
        }
        if use_edit:
            payload["image_urls"] = ref_data_uris

        headers = {"Authorization": f"Key {fal_key}", "Content-Type": "application/json"}

        # v1.2.25: cancel 확인 — 사용자가 이미 중지 눌렀으면 fal.ai 에 제출 금지.
        raise_if_cancelled(f"nano-banana-submit:{self.model_id}")

        try:
            async with httpx.AsyncClient(timeout=240, follow_redirects=True) as client:
                resp = await client.post(
                    f"{FAL_BASE}/{endpoint}",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = _safe_json(resp, "submit")

                if "images" in data and data["images"]:
                    image_url = data["images"][0]["url"]
                elif "request_id" in data:
                    # ★ fal.ai queue API 는 submit 응답이 직접 status_url /
                    # response_url 을 내려준다. 경로를 직접 조립하면
                    # (`fal-ai/nano-banana/edit/requests/...`) 405 가 뜬다 —
                    # 서브경로(`/edit`) 가 status 경로에는 들어가면 안 되기
                    # 때문. 그대로 URL 을 받아 쓴다.
                    status_url = data.get("status_url")
                    response_url = data.get("response_url")
                    if not status_url or not response_url:
                        raise RuntimeError(
                            f"fal.ai 응답에 status_url/response_url 이 없습니다: "
                            f"{str(data)[:200]}"
                        )
                    image_url = await self._poll(
                        client, headers, status_url, response_url
                    )
                else:
                    raise RuntimeError(
                        f"fal.ai 응답에 images/request_id 가 없습니다: {str(data)[:200]}"
                    )

                img_resp = await client.get(image_url)
                img_resp.raise_for_status()
                with open(output_path, "wb") as f:
                    f.write(img_resp.content)
            return output_path
        except Exception as e:
            # v1.2.20: 폴백 제거. Flux Dev 로 갈아치우지 않고 그대로 raise.
            # 호출자(_step_image / _step_thumbnail) 에서 task.error 에 박아서
            # 프런트 알림으로 노출된다.
            raise RuntimeError(
                f"[{self.display_name}] fal.ai 호출 실패 — 폴백 비활성화. "
                f"원인: {e}. FAL_KEY 와 네트워크/계정 잔액을 확인하세요."
            ) from e

    async def _poll(
        self,
        client: httpx.AsyncClient,
        headers: dict,
        status_url: str,
        response_url: str,
    ) -> str:
        for _ in range(80):
            # v1.2.25: polling 루프 안에서 cancel 체크.
            raise_if_cancelled("nano-banana-poll")
            resp = await client.get(status_url, headers=headers)
            resp.raise_for_status()
            data = _safe_json(resp, "poll-status")
            status = data.get("status")
            if status == "COMPLETED":
                result = await client.get(response_url, headers=headers)
                result.raise_for_status()
                rdata = _safe_json(result, "poll-result")
                images = rdata.get("images") or []
                if not images:
                    raise RuntimeError(
                        f"fal.ai 응답에 images 배열이 비어 있습니다: {str(rdata)[:200]}"
                    )
                return images[0]["url"]
            if status in ("FAILED", "ERROR"):
                raise RuntimeError(f"fal.ai 요청 실패: {str(data)[:200]}")
            await asyncio.sleep(3)
        raise TimeoutError(f"{self.display_name} image generation timed out")
