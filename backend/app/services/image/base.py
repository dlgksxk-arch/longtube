"""Base image generation service interface"""
from abc import ABC, abstractmethod
from typing import Optional

ASPECT_SIZES = {
    "16:9": (1280, 720),
    "9:16": (720, 1280),
    "1:1":  (1024, 1024),
    "3:4":  (768, 1024),
}


def get_size(aspect_ratio: str) -> tuple[int, int]:
    return ASPECT_SIZES.get(aspect_ratio, (1280, 720))


class BaseImageService(ABC):
    model_id: str
    display_name: str
    # 레퍼런스 이미지(스타일/캐릭터) 를 실제로 사용하는지 여부.
    # False 인 서비스는 reference_images 를 그냥 드롭한다 — router 에서
    # 프로젝트에 레퍼런스가 있으면 지원 모델로 폴백해야 한다.
    supports_reference_images: bool = False
    # v1.1.59: 사용자 설정 네거티브 프롬프트. ComfyUI 만 실제 사용, 그 외는 무시.
    # 호출부에서 `service.negative_prompt = config.get("image_negative_prompt", "")` 로 세팅.
    negative_prompt: str = ""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        width: int,
        height: int,
        output_path: str,
        reference_images: Optional[list[str]] = None,
    ) -> str:
        """프롬프트 + 참조 이미지 → 이미지 파일 생성. Returns output_path.
        reference_images: list of absolute file paths to reference/character images.
        """
        pass
