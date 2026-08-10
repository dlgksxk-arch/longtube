"""ElevenLabs TTS service
v1.1.52: 재시도 로직 추가.
"""
import asyncio
import base64
import os
from typing import Optional
import httpx
from app.services.tts.base import BaseTTSService, probe_audio_duration
from app.services.tts.alignment import write_alignment_sidecar
from app.services.cancel_ctx import raise_if_cancelled  # v1.2.25 cancel 방어
from app import config

BASE_URL = "https://api.elevenlabs.io/v1"

# ─────────────────────────────────────────────────────────────
# v1.1.57: 화이트리스트 제거 — ElevenLabs 계정의 모든 보이스를 UI에 노출.
# Voice Library 에서 원하는 목소리(무서운, 귀여운 등)를 추가하면
# 자동으로 드롭다운에 표시된다.
# ─────────────────────────────────────────────────────────────


class ElevenLabsService(BaseTTSService):
    engine_model_id = "eleven_v3"

    def __init__(self):
        self.model_id = "elevenlabs"
        self.display_name = "ElevenLabs"

    @property
    def headers(self) -> dict:
        # Read the current .env/env/config value on every call. Long-running
        # workbench jobs must not keep using a stale in-memory key.
        return {"xi-api-key": config.get_runtime_api_key("ELEVENLABS_API_KEY")}

    @staticmethod
    def effective_voice_settings(speed: float, voice_settings: Optional[dict] = None) -> dict:
        settings = dict(voice_settings or {"stability": 0.5, "similarity_boost": 0.75})
        try:
            value = float(speed)
        except (TypeError, ValueError):
            value = 1.0
        settings["speed"] = max(0.7, min(1.2, value))
        return settings

    @classmethod
    def _build_request_payload(
        cls,
        text: str,
        voice_settings: dict,
        request_context: Optional[dict] = None,
    ) -> dict:
        payload = {
            "text": text,
            "model_id": cls.engine_model_id,
            "voice_settings": voice_settings,
        }
        context = request_context or {}
        language_code = str(context.get("language_code") or "").strip().lower()
        if language_code:
            payload["language_code"] = language_code
        # ElevenLabs rejects this option for eleven_v3 with HTTP 400
        # (unsupported_model). Keep it only for models that accept it.
        if (
            cls.engine_model_id != "eleven_v3"
            and context.get("apply_language_text_normalization") is not None
        ):
            payload["apply_language_text_normalization"] = bool(
                context.get("apply_language_text_normalization")
            )
        if cls.engine_model_id != "eleven_v3":
            for key in ("previous_text", "next_text"):
                value = str(context.get(key) or "").strip()
                if value:
                    payload[key] = value
        locators = context.get("pronunciation_dictionary_locators")
        if isinstance(locators, list):
            normalized = []
            for item in locators[:3]:
                if not isinstance(item, dict):
                    continue
                dictionary_id = str(item.get("pronunciation_dictionary_id") or "").strip()
                version_id = str(item.get("version_id") or "").strip()
                if dictionary_id and version_id:
                    normalized.append({
                        "pronunciation_dictionary_id": dictionary_id,
                        "version_id": version_id,
                    })
            if normalized:
                payload["pronunciation_dictionary_locators"] = normalized
        return payload

    async def generate(
        self,
        text: str,
        voice_id: str,
        output_path: str,
        speed: float = 1.0,
        voice_settings: Optional[dict] = None,
        request_context: Optional[dict] = None,
    ) -> dict:
        # ElevenLabs speed range: 0.7 ~ 1.2. Keep marker and request settings identical.
        vs = self.effective_voice_settings(speed, voice_settings)
        MAX_RETRIES = 3
        for attempt in range(1, MAX_RETRIES + 1):
            # v1.2.25: 재시도 루프 안에서 cancel 체크.
            raise_if_cancelled("elevenlabs-tts")
            try:
                async with httpx.AsyncClient(timeout=120) as client:
                    resp = await client.post(
                        f"{BASE_URL}/text-to-speech/{voice_id}/with-timestamps",
                        headers={**self.headers, "Content-Type": "application/json"},
                        json=self._build_request_payload(text, vs, request_context),
                    )
                    if resp.status_code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES:
                        wait = attempt * 3
                        print(f"[TTS] ElevenLabs HTTP {resp.status_code}, {wait}초 후 재시도 ({attempt}/{MAX_RETRIES})")
                        await asyncio.sleep(wait)
                        continue
                    resp.raise_for_status()

                    response_data = resp.json()
                    audio_base64 = response_data.get("audio_base64")
                    if not isinstance(audio_base64, str) or not audio_base64:
                        raise RuntimeError("ElevenLabs timestamp response is missing audio_base64")
                    try:
                        audio_bytes = base64.b64decode(audio_base64, validate=True)
                    except (ValueError, TypeError) as exc:
                        raise RuntimeError("ElevenLabs timestamp response contains invalid audio_base64") from exc
                    if not audio_bytes:
                        raise RuntimeError("ElevenLabs timestamp response decoded to empty audio")

                    with open(output_path, "wb") as f:
                        f.write(audio_bytes)
                    write_alignment_sidecar(
                        output_path,
                        text=text,
                        alignment=response_data.get("alignment"),
                        normalized_alignment=response_data.get("normalized_alignment"),
                        provider="elevenlabs",
                        model_id=self.engine_model_id,
                    )
                    try:
                        from app.services import spend_ledger
                        note = "voice_preview" if os.path.basename(output_path) == "voice_preview.mp3" else os.path.basename(output_path)
                        parts = output_path.replace("\\", "/").split("/")
                        project_id = None
                        if "audio" in parts:
                            audio_idx = parts.index("audio")
                            if audio_idx > 0:
                                project_id = parts[audio_idx - 1]
                        spend_ledger.record_elevenlabs_request(
                            chars=len(text or ""),
                            project_id=project_id,
                            note=note,
                        )
                    except Exception:
                        pass
                break
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                if attempt < MAX_RETRIES:
                    wait = attempt * 3
                    print(f"[TTS] ElevenLabs 연결 오류, {wait}초 후 재시도 ({attempt}/{MAX_RETRIES})")
                    await asyncio.sleep(wait)
                    continue
                raise

        duration = self._get_duration(output_path)

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
            if v.get("category") == "premade":
                continue
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
        return probe_audio_duration(path)
