"""Base TTS service interface"""
import os
from abc import ABC, abstractmethod
from typing import Optional


def _resolve_bins() -> tuple:
    """find_ffmpeg() 로 ffmpeg/ffprobe 절대경로를 구한다.
    Windows 에서 bare 'ffmpeg' 호출이 안 되므로 반드시 필요.
    """
    from app.services.video.subprocess_helper import find_ffmpeg
    ffbin = find_ffmpeg()
    # ffprobe 는 ffmpeg 옆에 같이 있다
    ffprobe = ffbin.replace("ffmpeg.exe", "ffprobe.exe").replace("ffmpeg", "ffprobe")
    if not os.path.exists(ffprobe):
        ffprobe = "ffprobe"  # fallback to PATH
    return ffbin, ffprobe


class BaseTTSService(ABC):
    model_id: str
    display_name: str

    @abstractmethod
    async def generate(self, text: str, voice_id: str, output_path: str, speed: float = 1.0, voice_settings: Optional[dict] = None) -> dict:
        """텍스트 → 음성 파일 생성. Returns {"path": str, "duration": float}"""
        pass

    @abstractmethod
    async def list_voices(self) -> list[dict]:
        """사용 가능한 보이스 목록 반환"""
        pass

    @staticmethod
    def validate_duration_window(
        path: str,
        current_dur: float,
        min_dur: float,
        max_dur: float,
        *,
        tolerance: float = 0.01,
    ) -> float:
        """Check TTS duration without blocking the generated audio file.

        Audio speed/tempo must not be used to force timing. If the result is
        outside the allowed window, keep the file so the problem can be
        inspected and fix the narration text upstream.
        """
        if current_dur <= 0:
            print(f"[TTS] duration warning: could not measure duration for {path}; keeping generated audio")
            return current_dur

        if current_dur < min_dur - tolerance:
            print(
                f"TTS duration {current_dur:.2f}s is too short; "
                f"target is {min_dur:.1f}~{max_dur:.1f}s. "
                "Keeping generated audio; fix by increasing narration text upstream."
            )
            return current_dur

        if current_dur > max_dur + tolerance:
            print(
                f"TTS duration {current_dur:.2f}s is too long; "
                f"target is {min_dur:.1f}~{max_dur:.1f}s. "
                "Keeping generated audio; fix by reducing narration text upstream."
            )
            return current_dur

        return current_dur

    @staticmethod
    def enforce_max_duration(path: str, current_dur: float, max_dur: float) -> float:
        """Deprecated no-op: never speed up or cut narration audio."""
        print(
            f"[TTS] skip max enforce: keeping original {current_dur:.2f}s "
            f"for {path}; adjust narration text instead."
        )
        return current_dur

    @staticmethod
    def enforce_min_duration(path: str, current_dur: float, min_dur: float) -> float:
        """Deprecated no-op: never slow down narration audio."""
        print(
            f"[TTS] skip min enforce: keeping original {current_dur:.2f}s "
            f"for {path}; adjust narration text instead."
        )
        return current_dur
