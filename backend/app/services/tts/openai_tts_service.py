"""OpenAI TTS service — httpx 직접 호출 방식.

v1.1.50: AsyncOpenAI SDK 를 걷어내고 httpx.AsyncClient 를 매 호출마다
새로 생성한다. 딸깍 파이프라인은 asyncio.to_thread → run_async (새 이벤트 루프)
경로를 타는데, AsyncOpenAI 의 내부 httpx transport 가 루프 간 공유되면
APIConnectionError 가 발생하기 때문이다. httpx.AsyncClient 를 async with 로
즉석 생성하면 루프 불일치 문제가 원천 차단된다.
"""
import asyncio
import subprocess
from typing import Optional

import httpx

from app.services.tts.base import BaseTTSService, _resolve_bins
from app.config import OPENAI_API_KEY, TTS_MAX_DURATION, TTS_MIN_DURATION

TTS_API_URL = "https://api.openai.com/v1/audio/speech"


class OpenAITTSService(BaseTTSService):
    VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

    def __init__(self):
        self.model_id = "openai-tts"
        self.display_name = "OpenAI TTS"

    async def generate(self, text: str, voice_id: str, output_path: str, speed: float = 1.0, voice_settings: Optional[dict] = None) -> dict:
        voice = voice_id if voice_id in self.VOICES else "alloy"

        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not set")

        body = {
            "model": "tts-1-hd",
            "voice": voice,
            "input": text,
            "response_format": "mp3",
        }
        if speed != 1.0:
            body["speed"] = max(0.25, min(4.0, speed))

        # v1.1.52: 재시도 로직 — 503/429/connection timeout 등 일시적 오류 대응
        MAX_RETRIES = 3
        last_err = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    resp = await client.post(
                        TTS_API_URL,
                        headers={
                            "Authorization": f"Bearer {OPENAI_API_KEY}",
                            "Content-Type": "application/json",
                        },
                        json=body,
                    )
                    if resp.status_code == 200:
                        break
                    # 재시도 가능한 오류: 429, 500, 502, 503, 504
                    if resp.status_code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES:
                        wait = attempt * 3  # 3초, 6초
                        print(f"[TTS] HTTP {resp.status_code}, {wait}초 후 재시도 ({attempt}/{MAX_RETRIES})")
                        await asyncio.sleep(wait)
                        continue
                    detail = resp.text[:300] if resp.text else f"HTTP {resp.status_code}"
                    raise RuntimeError(f"OpenAI TTS API 오류 (HTTP {resp.status_code}): {detail}")
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                last_err = e
                if attempt < MAX_RETRIES:
                    wait = attempt * 3
                    print(f"[TTS] 연결 오류 ({type(e).__name__}), {wait}초 후 재시도 ({attempt}/{MAX_RETRIES})")
                    await asyncio.sleep(wait)
                    continue
                raise RuntimeError(f"OpenAI TTS 연결 실패 ({MAX_RETRIES}회 시도): {e}") from e

        from pathlib import Path
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(resp.content)

        duration = self._get_duration(output_path)

        max_dur = TTS_MAX_DURATION  # 4.5
        if duration > max_dur:
            duration = self.enforce_max_duration(output_path, duration, max_dur)

        # v1.1.53: 음성이 TTS_MIN_DURATION(4.0초) 미만이면 감속으로 늘림
        min_dur = TTS_MIN_DURATION  # 4.0
        if duration < min_dur:
            duration = self.enforce_min_duration(output_path, duration, min_dur)

        import os
        rel_path = output_path
        if os.path.isabs(output_path):
            parts = output_path.replace("\\", "/").split("/")
            try:
                audio_idx = parts.index("audio")
                rel_path = "/".join(parts[audio_idx:])
            except ValueError:
                rel_path = os.path.basename(output_path)
        return {"path": rel_path, "duration": duration}

    async def list_voices(self) -> list[dict]:
        return [{"id": v, "name": v.capitalize(), "language": "multilingual"} for v in self.VOICES]

    @staticmethod
    def _get_duration(path: str) -> float:
        """Get audio duration. Try ffprobe first, fallback to file-size estimate.

        v1.1.54: _resolve_bins() 로 ffprobe 절대경로를 구한다 — Windows 에서
        bare 'ffprobe' 호출이 PATH 에 없으면 실패하여 파일 크기 fallback 이
        부정확한 duration 을 돌려주는 버그를 수정.
        """
        try:
            _, ffprobe_bin = _resolve_bins()
            result = subprocess.run(
                [ffprobe_bin, "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                capture_output=True, text=True, timeout=10,
            )
            if result.stdout.strip():
                return float(result.stdout.strip())
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
            pass
        except Exception as e:
            print(f"[TTS] ffprobe duration 측정 실패: {e}")
        try:
            import os
            size = os.path.getsize(path)
            return round(size / 16000, 1)
        except Exception:
            return 0.0
