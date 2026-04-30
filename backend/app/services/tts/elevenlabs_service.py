"""ElevenLabs TTS service
v1.1.52: 재시도 로직 추가.
"""
import asyncio
import os
import subprocess
from typing import Optional
import httpx
from app.services.tts.base import BaseTTSService, _resolve_bins
from app.services.cancel_ctx import raise_if_cancelled  # v1.2.25 cancel 방어
from app import config
from app.config import TTS_MAX_DURATION, TTS_MIN_DURATION  # 상수는 고정이라 직접 import OK

BASE_URL = "https://api.elevenlabs.io/v1"

# ─────────────────────────────────────────────────────────────
# v1.1.57: 화이트리스트 제거 — ElevenLabs 계정의 모든 보이스를 UI에 노출.
# Voice Library 에서 원하는 목소리(무서운, 귀여운 등)를 추가하면
# 자동으로 드롭다운에 표시된다.
# ─────────────────────────────────────────────────────────────


class ElevenLabsService(BaseTTSService):
    def __init__(self):
        self.model_id = "elevenlabs"
        self.display_name = "ElevenLabs"

    @property
    def headers(self) -> dict:
        # v1.1.63: UI 에서 바꾼 키가 즉시 반영되도록 매 접근마다 최신 키를 읽음.
        return {"xi-api-key": config.ELEVENLABS_API_KEY}

    async def generate(self, text: str, voice_id: str, output_path: str, speed: float = 1.0, voice_settings: Optional[dict] = None) -> dict:
        vs = dict(voice_settings or {"stability": 0.5, "similarity_boost": 0.75})
        # ElevenLabs speed range: 0.7 ~ 1.2 (공식 문서 기준). 그 밖은 clamp.
        try:
            sp = float(speed)
        except (TypeError, ValueError):
            sp = 1.0
        vs["speed"] = max(0.7, min(1.2, sp))
        MAX_RETRIES = 3
        for attempt in range(1, MAX_RETRIES + 1):
            # v1.2.25: 재시도 루프 안에서 cancel 체크.
            raise_if_cancelled("elevenlabs-tts")
            try:
                async with httpx.AsyncClient(timeout=120) as client:
                    resp = await client.post(
                        f"{BASE_URL}/text-to-speech/{voice_id}",
                        headers={**self.headers, "Content-Type": "application/json"},
                        json={
                            "text": text,
                            "model_id": "eleven_multilingual_v2",
                            "voice_settings": vs,
                        },
                    )
                    if resp.status_code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES:
                        wait = attempt * 3
                        print(f"[TTS] ElevenLabs HTTP {resp.status_code}, {wait}초 후 재시도 ({attempt}/{MAX_RETRIES})")
                        await asyncio.sleep(wait)
                        continue
                    resp.raise_for_status()

                    with open(output_path, "wb") as f:
                        f.write(resp.content)
                break
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                if attempt < MAX_RETRIES:
                    wait = attempt * 3
                    print(f"[TTS] ElevenLabs 연결 오류, {wait}초 후 재시도 ({attempt}/{MAX_RETRIES})")
                    await asyncio.sleep(wait)
                    continue
                raise

        duration = self._get_duration(output_path)

        # Do not tempo-shift or cut narration. Timing must be solved by text length.
        if os.path.basename(output_path) != "voice_preview.mp3":
            try:
                duration = self.validate_duration_window(
                    output_path, duration, TTS_MIN_DURATION, TTS_MAX_DURATION
                )
            except ValueError:
                try:
                    os.remove(output_path)
                except OSError:
                    pass
                raise

        # Return relative path for DB storage (audio/cut_X.wav)
        rel_path = output_path
        # If it's an absolute path, extract relative from project dir
        if os.path.isabs(output_path):
            parts = output_path.replace("\\", "/").split("/")
            try:
                audio_idx = parts.index("audio")
                rel_path = "/".join(parts[audio_idx:])
            except ValueError:
                rel_path = os.path.basename(output_path)
        return {"path": rel_path, "duration": duration}

    async def list_voices(self) -> list[dict]:
        """v1.1.57: 화이트리스트 제거 — 계정의 모든 보이스를 반환."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{BASE_URL}/voices", headers=self.headers)
            resp.raise_for_status()
            data = resp.json()

        all_voices = data.get("voices", [])

        out: list[dict] = []
        for v in all_voices:
            labels = v.get("labels") or {}
            out.append({
                "id": v["voice_id"],
                "name": v["name"],
                "description": v.get("description") or labels.get("description"),
                "preview_url": v.get("preview_url"),
                "category": v.get("category"),
                "gender": labels.get("gender"),
                "accent": labels.get("accent"),
                "age": labels.get("age"),
                "use_case": labels.get("use_case"),
                "language": labels.get("language", "unknown"),
            })
        return out

    @staticmethod
    def _get_duration(path: str) -> float:
        """Get audio duration. Try ffprobe first, fallback to file-size estimate.

        v1.1.54: _resolve_bins() 로 ffprobe 절대경로를 구한다 — Windows 에서
        bare 'ffprobe' 호출이 PATH 에 없으면 실패하여 파일 크기 fallback 이
        부정확한 duration 을 돌려주는 버그 수정.
        """
        try:
            _, ffprobe_bin = _resolve_bins()
            result = subprocess.run(
                [ffprobe_bin, "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
            )
            if result.stdout.strip():
                return float(result.stdout.strip())
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
            pass
        except Exception as e:
            print(f"[TTS] ffprobe duration 측정 실패: {e}")
        # Fallback: estimate from file size (mp3 ~16KB/s at 128kbps)
        try:
            import os
            size = os.path.getsize(path)
            return round(size / 16000, 1)
        except Exception:
            return 0.0
