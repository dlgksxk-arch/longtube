"""Base video generation service interface"""
from abc import ABC, abstractmethod
from typing import Optional


class BaseVideoService(ABC):
    model_id: str
    display_name: str

    @abstractmethod
    async def generate(
        self,
        image_path: str,
        audio_path: Optional[str] = None,
        duration: float = 5.0,
        output_path: str = "",
        aspect_ratio: str = "16:9",
        prompt: str = "",
    ) -> str:
        """이미지 (+ 오디오) → 영상 클립 생성. Returns output_path"""
        pass
