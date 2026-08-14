"""Provision and persist per-character ElevenLabs Voice Design voices."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlencode

import httpx

from app import config as app_config


ELEVENLABS_BASE_URL = "https://api.elevenlabs.io"
VOICE_DESIGN_MODEL_ID = "eleven_ttv_v3"
VOICE_PREVIEW_TEXT = (
    "오늘 우리는 오래된 기록 속 인물의 선택을 다시 살펴보려 합니다. "
    "말 한마디에는 두려움과 결심이 함께 담겨 있고, 조용한 순간에도 각자의 성격과 삶의 무게가 드러납니다. "
    "과장하지 말고 자연스러운 한국어 발음으로, 상대 인물에게 직접 이야기하듯 이 문장을 들려주십시오."
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _provider_safe_prompt(prompt: str) -> str:
    """Keep the requested voice character while removing explicit minor age terms."""
    safe = re.sub(
        r"Korean adolescent boy around\s+\d+",
        "Korean youthful male",
        prompt,
        flags=re.IGNORECASE,
    )
    safe = re.sub(
        r"Korean adolescent girl around\s+\d+",
        "Korean youthful female",
        safe,
        flags=re.IGNORECASE,
    )
    safe = re.sub(
        r"from being raised as a sacred child",
        "from a formal ritual upbringing",
        safe,
        flags=re.IGNORECASE,
    )
    return safe.strip()


def _design_payload(*, prompt: str, series: str, speaker: str) -> dict[str, Any]:
    provider_prompt = _provider_safe_prompt(prompt)
    payload: dict[str, Any] = {
        "voice_description": provider_prompt,
        "model_id": VOICE_DESIGN_MODEL_ID,
        "text": VOICE_PREVIEW_TEXT,
        "seed": int(_prompt_hash(f"{series}:{speaker}:{prompt}")[:8], 16) & 0x7FFFFFFF,
        "guidance_scale": 3.0,
    }
    # ElevenLabs rejects `quality` for eleven_ttv_v3 even though the generic
    # endpoint schema exposes the field. It is supported only by v2.
    if VOICE_DESIGN_MODEL_ID == "eleven_multilingual_ttv_v2":
        payload["quality"] = 0.9
    return payload


def _dialogue_speakers(script: dict[str, Any]) -> list[str]:
    speakers: list[str] = []
    for cut in script.get("cuts") or []:
        if not isinstance(cut, dict):
            continue
        if _text(cut.get("voice_generation_mode")).upper() != "DIALOGUE":
            continue
        speaker = _text(cut.get("speaker"))
        if speaker and speaker not in speakers:
            speakers.append(speaker)
    return speakers


def _cast_by_name(script: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in script.get("voice_cast") or []:
        if not isinstance(item, dict):
            continue
        name = _text(item.get("인물명"))
        if name:
            out[name.casefold()] = item
    return out


class ElevenLabsVoiceDesignClient:
    def __init__(self, *, timeout: float = 180.0):
        api_key = app_config.get_runtime_api_key("ELEVENLABS_API_KEY")
        if not api_key:
            raise RuntimeError("ElevenLabs Voice Design API 키가 비어 있습니다.")
        self.headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
        self.timeout = timeout

    def _find_existing(self, voice_name: str, prompt: str) -> str:
        query = urlencode({"page_size": 100, "search": voice_name})
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f"{ELEVENLABS_BASE_URL}/v2/voices?{query}",
                headers=self.headers,
            )
            response.raise_for_status()
            for voice in response.json().get("voices") or []:
                if _text(voice.get("name")) != voice_name:
                    continue
                if _text(voice.get("description")) == prompt:
                    return _text(voice.get("voice_id"))
        return ""

    def create_or_reuse(self, *, voice_name: str, prompt: str, series: str, speaker: str) -> str:
        provider_prompt = _provider_safe_prompt(prompt)
        existing = self._find_existing(voice_name, provider_prompt)
        if existing:
            return existing

        with httpx.Client(timeout=self.timeout) as client:
            designed = client.post(
                f"{ELEVENLABS_BASE_URL}/v1/text-to-voice/design",
                headers=self.headers,
                json=_design_payload(prompt=prompt, series=series, speaker=speaker),
            )
            if designed.status_code >= 400:
                raise RuntimeError(
                    f"Voice Design 미리보기 실패 HTTP {designed.status_code}: "
                    f"{designed.text[:500]}"
                )
            previews = designed.json().get("previews") or []
            generated_voice_id = _text(previews[0].get("generated_voice_id")) if previews else ""
            if not generated_voice_id:
                raise RuntimeError(f"Voice Design 미리보기 ID가 없습니다: {speaker}")

            created = client.post(
                f"{ELEVENLABS_BASE_URL}/v1/text-to-voice",
                headers=self.headers,
                json={
                    "voice_name": voice_name,
                    "voice_description": provider_prompt,
                    "generated_voice_id": generated_voice_id,
                    "labels": {
                        "language": "ko",
                        "use_case": "characters",
                        "series": series,
                        "speaker": speaker,
                    },
                },
            )
            if created.status_code >= 400:
                raise RuntimeError(
                    f"Voice Design 저장 실패 HTTP {created.status_code}: "
                    f"{created.text[:500]}"
                )
            voice_id = _text(created.json().get("voice_id"))
            if not voice_id:
                raise RuntimeError(f"Voice Design 생성 결과에 voice_id가 없습니다: {speaker}")
            return voice_id


def ensure_dialogue_voice_cast(
    script: dict[str, Any],
    config: dict[str, Any],
    *,
    create_voice: Callable[..., str] | None = None,
    on_voice_ready: Callable[[str, dict[str, Any]], None] | None = None,
    log: Callable[[str], None] | None = None,
) -> bool:
    """Assign every DIALOGUE speaker a dedicated voice or fail before TTS."""
    speakers = _dialogue_speakers(script)
    if not speakers:
        return False
    if _text(config.get("tts_model")).lower() != "elevenlabs":
        raise RuntimeError("DIALOGUE 컷은 ElevenLabs Voice Design 음성으로만 생성할 수 있습니다.")

    cast = _cast_by_name(script)
    missing_cast = [speaker for speaker in speakers if speaker.casefold() not in cast]
    if missing_cast:
        raise RuntimeError(f"Voice Design 표에 없는 DIALOGUE 화자: {missing_cast}")

    raw_registry = config.get("tts_character_voice_registry")
    registry = dict(raw_registry) if isinstance(raw_registry, dict) else {}
    raw_ids = config.get("tts_character_voice_ids")
    character_ids = dict(raw_ids) if isinstance(raw_ids, dict) else {}
    series = _text(config.get("factory_series") or config.get("series") or script.get("series") or "Factory")
    client: ElevenLabsVoiceDesignClient | None = None
    changed = False

    for speaker in speakers:
        item = cast[speaker.casefold()]
        prompt = _text(item.get("Voice Design Prompt"))
        if len(prompt) < 20:
            raise RuntimeError(f"Voice Design Prompt가 없거나 너무 짧습니다: {speaker}")
        prompt_sha256 = _prompt_hash(prompt)

        voice_id = _text(item.get("voice_id"))
        record = registry.get(speaker)
        if not voice_id and isinstance(record, dict) and _text(record.get("prompt_sha256")) == prompt_sha256:
            voice_id = _text(record.get("voice_id"))
        if not voice_id:
            voice_id = _text(character_ids.get(speaker))

        if not voice_id:
            if create_voice is None:
                client = client or ElevenLabsVoiceDesignClient()
                create_voice = client.create_or_reuse
            voice_name = f"{series} - {speaker}"
            if log:
                log(f"Voice Design 생성: {speaker}")
            voice_id = _text(
                create_voice(
                    voice_name=voice_name,
                    prompt=prompt,
                    series=series,
                    speaker=speaker,
                )
            )
            if not voice_id:
                raise RuntimeError(f"Voice Design voice_id 생성 실패: {speaker}")
            changed = True

        previous_record = registry.get(speaker)
        previous_updated_at = (
            _text(previous_record.get("updated_at"))
            if isinstance(previous_record, dict)
            and _text(previous_record.get("voice_id")) == voice_id
            and _text(previous_record.get("prompt_sha256")) == prompt_sha256
            else ""
        )
        record = {
            "voice_id": voice_id,
            "prompt_sha256": prompt_sha256,
            "policy": _text(item.get("유지정책")),
            "updated_at": previous_updated_at or datetime.now(timezone.utc).isoformat(),
        }
        if _text(item.get("voice_id")) != voice_id:
            item["voice_id"] = voice_id
            changed = True
        if character_ids.get(speaker) != voice_id or registry.get(speaker) != record:
            character_ids[speaker] = voice_id
            registry[speaker] = record
            changed = True
        if on_voice_ready:
            on_voice_ready(speaker, record)

    config["tts_character_voice_ids"] = character_ids
    config["tts_character_voice_registry"] = registry
    return changed
