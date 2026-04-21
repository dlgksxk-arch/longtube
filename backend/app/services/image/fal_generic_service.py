"""Generic fal.ai image service for Seedream, Z-IMAGE, etc."""
import asyncio
import json
import httpx
from app.services.image.base import BaseImageService
from app import config

FAL_BASE = "https://queue.fal.run"


def _safe_json(resp: httpx.Response, where: str) -> dict:
    try:
        return resp.json()
    except (json.JSONDecodeError, ValueError):
        body_preview = (resp.text or "").strip()[:200] or "<empty body>"
        raise RuntimeError(
            f"fal.ai 응답을 JSON 으로 해석할 수 없습니다 ({where}, "
            f"status={resp.status_code}): {body_preview}"
        )


class FalGenericService(BaseImageService):
    """fal.ai 기반 이미지 모델 통합 서비스 (Seedream, Z-IMAGE 등)"""

    # model_id → fal.ai endpoint mapping
    FAL_ENDPOINTS = {
        "seedream-v4.5": "fal-ai/seedream-v4.5",
        "z-image-turbo": "fal-ai/z-image-turbo",
    }

    def __init__(self, model_id: str):
        self.model_id = model_id
        self.display_name = {
            "seedream-v4.5": "Seedream V4.5",
            "z-image-turbo": "Z-IMAGE Turbo",
        }.get(model_id, model_id)
        self._endpoint = self.FAL_ENDPOINTS.get(model_id, model_id)

    async def generate(self, prompt: str, width: int, height: int, output_path: str, reference_images=None) -> str:
        # v1.1.63: UI 에서 바꾼 키가 즉시 반영되도록 매 호출마다 config 에서 읽음.
        fal_key = config.FAL_KEY
        if not fal_key:
            raise RuntimeError(
                "FAL_KEY 환경변수가 설정돼 있지 않습니다. .env 에 FAL_KEY 를 "
                "넣거나 이미지 모델을 OpenAI / Grok 등으로 바꿔주세요."
            )

        headers = {"Authorization": f"Key {fal_key}", "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=180, follow_redirects=True) as client:
            resp = await client.post(
                f"{FAL_BASE}/{self._endpoint}",
                headers=headers,
                json={
                    "prompt": f"cinematic, high quality, detailed, {prompt}",
                    "image_size": {"width": width, "height": height},
                    "num_images": 1,
                },
            )
            resp.raise_for_status()
            data = _safe_json(resp, "submit")

            if "images" in data:
                image_url = data["images"][0]["url"]
            elif "request_id" in data:
                # ★ submit 응답의 status_url / response_url 을 그대로 사용 —
                # 경로를 직접 조립하면 fal.ai 큐 API 가 405 를 뱉는다.
                status_url = data.get("status_url")
                response_url = data.get("response_url")
                if not status_url or not response_url:
                    raise RuntimeError(
                        f"fal.ai 응답에 status_url/response_url 이 없습니다: "
                        f"{str(data)[:200]}"
                    )
                image_url = await self._poll(client, headers, status_url, response_url)
            else:
                raise RuntimeError(
                    f"fal.ai 응답에 images/request_id 가 없습니다: {str(data)[:200]}"
                )

            img_resp = await client.get(image_url)
            img_resp.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(img_resp.content)

        return output_path

    async def _poll(
        self,
        client: httpx.AsyncClient,
        headers: dict,
        status_url: str,
        response_url: str,
    ) -> str:
        for _ in range(60):
            resp = await client.get(status_url, headers=headers)
            resp.raise_for_status()
            data = _safe_json(resp, "poll-status")
            if data.get("status") == "COMPLETED":
                result = await client.get(response_url, headers=headers)
                result.raise_for_status()
                rdata = _safe_json(result, "poll-result")
                return rdata["images"][0]["url"]
            await asyncio.sleep(3)
        raise TimeoutError(f"{self.display_name} image generation timed out")
