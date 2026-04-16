"""Midjourney image service (via proxy API)
NOTE: Midjourney 공식 API가 없으므로 프록시 서비스(예: goapi.ai, imagineapi.dev) 경유.
프록시 서비스에 따라 엔드포인트/인증 방식 다름. 확인 후 구현 필요.
"""
import httpx
from app.services.image.base import BaseImageService
from app.config import MIDJOURNEY_API_KEY


class MidjourneyService(BaseImageService):
    def __init__(self):
        self.model_id = "midjourney"
        self.display_name = "Midjourney"

    async def generate(self, prompt: str, width: int, height: int, output_path: str, reference_images=None) -> str:
        if not MIDJOURNEY_API_KEY:
            raise ValueError("Midjourney API key not configured. Set MIDJOURNEY_API_KEY in .env")

        # TODO: 프록시 서비스 선택 후 실제 구현
        # 예시 (goapi.ai 기반):
        # async with httpx.AsyncClient(timeout=300) as client:
        #     resp = await client.post(
        #         "https://api.goapi.ai/mj/v2/imagine",
        #         headers={"X-API-KEY": MIDJOURNEY_API_KEY},
        #         json={"prompt": prompt, "aspect_ratio": f"{width}:{height}"},
        #     )
        raise NotImplementedError("Midjourney proxy API 설정 필요. docs/ARCHITECTURE.md 참고.")
