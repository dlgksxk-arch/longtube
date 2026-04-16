"""Grok Imagine Image (xAI) service.

NOTE: xAI 의 `grok-imagine-image` 는 현재 고정 해상도만 지원하며 ``size`` 파라미터를
받지 않습니다. ``size`` 를 넘기면 ``400 Bad Request`` 가 납니다. 또한 프롬프트가
긴 경우(1024 자 초과) 역시 400 이 납니다. 실패 시 응답 본문을 함께 던져서
원인을 바로 볼 수 있게 합니다.

v1.1.52: 재시도 로직 추가 — 429/5xx/연결 오류 시 최대 3회 재시도.
v1.1.55: 모델명 grok-2-image → grok-imagine-image 변경 (xAI API 업데이트).
"""
import asyncio
import httpx
from app.services.image.base import BaseImageService
from app.config import XAI_API_KEY

XAI_BASE = "https://api.x.ai/v1"

# xAI 는 프롬프트 길이에 한계가 있어 너무 긴 프롬프트는 400 으로 거절한다.
# 경험적으로 ~1024 자 근처가 상한선.
_PROMPT_CHAR_LIMIT = 1024

MAX_RETRIES = 3


class GrokImageService(BaseImageService):
    def __init__(self):
        self.model_id = "grok-imagine"
        self.display_name = "Grok Imagine Image"

    async def generate(self, prompt: str, width: int, height: int, output_path: str, reference_images=None) -> str:
        if not XAI_API_KEY:
            raise RuntimeError(
                "XAI_API_KEY 환경변수가 설정돼 있지 않습니다. .env 에 XAI_API_KEY "
                "를 넣거나 이미지 모델을 OpenAI (openai-image-1) 로 바꿔주세요."
            )

        headers = {"Authorization": f"Bearer {XAI_API_KEY}", "Content-Type": "application/json"}
        full_prompt = f"cinematic, high quality, {prompt}"
        if len(full_prompt) > _PROMPT_CHAR_LIMIT:
            full_prompt = full_prompt[: _PROMPT_CHAR_LIMIT - 3] + "..."

        last_err = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=120) as client:
                    resp = await client.post(
                        f"{XAI_BASE}/images/generations",
                        headers=headers,
                        json={
                            "model": "grok-imagine-image",
                            "prompt": full_prompt,
                            "n": 1,
                            "response_format": "url",
                        },
                    )

                    # 재시도 가능한 서버 오류
                    if resp.status_code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES:
                        wait = attempt * 5  # 5초, 10초
                        print(f"[Image] xAI HTTP {resp.status_code}, {wait}초 후 재시도 ({attempt}/{MAX_RETRIES})")
                        await asyncio.sleep(wait)
                        continue

                    if resp.status_code >= 400:
                        try:
                            err_body = resp.json()
                            err_msg = (
                                err_body.get("error", {}).get("message")
                                or err_body.get("error")
                                or err_body
                            )
                        except Exception:
                            err_msg = (resp.text or "").strip()[:300] or "<empty body>"
                        raise RuntimeError(
                            f"xAI images API {resp.status_code}: {err_msg}"
                        )

                    try:
                        data = resp.json()
                    except Exception:
                        raise RuntimeError(
                            f"xAI 응답을 JSON 으로 해석 불가 (status={resp.status_code}): "
                            f"{(resp.text or '')[:200]}"
                        )
                    items = data.get("data") or []
                    if not items or not items[0].get("url"):
                        raise RuntimeError(f"xAI 응답에 이미지 URL 이 없습니다: {str(data)[:200]}")
                    image_url = items[0]["url"]

                    img_resp = await client.get(image_url)
                    img_resp.raise_for_status()
                    with open(output_path, "wb") as f:
                        f.write(img_resp.content)

                return output_path

            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                last_err = e
                if attempt < MAX_RETRIES:
                    wait = attempt * 5
                    print(f"[Image] xAI 연결 오류 ({type(e).__name__}), {wait}초 후 재시도 ({attempt}/{MAX_RETRIES})")
                    await asyncio.sleep(wait)
                    continue
                raise RuntimeError(f"xAI 이미지 생성 연결 실패 ({MAX_RETRIES}회 시도): {e}") from e

        # 여기 도달하면 안 되지만 safety net
        raise RuntimeError(f"xAI 이미지 생성 실패 ({MAX_RETRIES}회 시도)")
