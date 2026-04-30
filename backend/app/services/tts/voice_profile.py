"""TTS voice pacing profiler.

Script timing must be solved by narration length, not by audio tempo changes.
This module measures the currently selected TTS voice once, caches its real
reading speed, and lets the script generator use that measured rate.
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from typing import Any, Callable

from app import config as app_config
from app.services.tts.factory import get_tts_service


CACHE_PATH = app_config.BASE_DIR / "data" / "tts_voice_profiles.json"
ARTIFACT_ROOT = app_config.BASE_DIR / "data" / "_voice_profiles"
ELEVENLABS_TTS_MODEL_ID = "eleven_multilingual_v2"
DEFAULT_SAMPLE_COUNT = 4

KO_PROFILE_SAMPLES = [
    "오늘 이야기는 작은 회의실에서 조용히 시작됐습니다.",
    "그런데 몇 년 뒤, 모든 예측이 완전히 빗나가게 됩니다.",
    "사람들은 처음엔 이 기술을 대단한 장난감처럼 여겼습니다.",
    "하지만 한 번의 실험이 연구자들의 생각을 완전히 바꿔 놓았습니다.",
    "그리고 지금 우리는 그 결과를 매일 눈앞에서 보고 있습니다.",
]

JA_PROFILE_SAMPLES = [
    "この話は、小さな会議室で静かに始まりました。",
    "しかし数年後、その予測は大きく外れることになります。",
    "人々は最初、この技術を不思議な道具のように見ていました。",
    "ところが一つの実験が、研究者たちの考えを変えていきました。",
]

EN_PROFILE_SAMPLES = [
    "This story began quietly in a small conference room.",
    "A few years later, nearly every prediction would fall apart.",
    "At first, people treated the technology like a strange toy.",
    "Then one experiment changed how researchers understood the future.",
]


def _log(log: Callable[[str], None] | None, message: str) -> None:
    if log:
        log(message)


def _compact(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _count_chars(text: str, language: str) -> int:
    compact = _compact(text)
    if language in ("ko", "ja"):
        return len(compact)
    return len(compact)


def _count_words(text: str) -> int:
    return len(re.findall(r"\b[\w']+\b", text or ""))


def _settings_hash(voice_settings: dict | None) -> str:
    if not voice_settings:
        return "default"
    payload = json.dumps(voice_settings, ensure_ascii=False, sort_keys=True)
    return sha1(payload.encode("utf-8")).hexdigest()[:10]


def _safe_key_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value or "")[:96] or "default"


def resolve_voice_settings(config: dict | None) -> dict | None:
    """Return the same ElevenLabs voice_settings used by voice generation."""
    cfg = config or {}
    tts_model = cfg.get("tts_model", "openai-tts")
    voice_preset = str(cfg.get("tts_voice_preset") or "")
    if tts_model == "elevenlabs" and "child" in voice_preset:
        return {"stability": 0.7, "similarity_boost": 0.85}
    return None


def _coerce_speed(tts_model: str, speed: Any) -> float:
    try:
        value = float(speed if speed is not None else 1.0)
    except (TypeError, ValueError):
        value = 1.0
    if tts_model == "elevenlabs":
        return max(0.7, min(1.2, value))
    return max(0.25, min(4.0, value))


def _cache_key(
    *,
    tts_model: str,
    voice_id: str,
    language: str,
    speed: float,
    voice_settings: dict | None,
) -> str:
    settings = _settings_hash(voice_settings)
    return (
        f"{tts_model}|{ELEVENLABS_TTS_MODEL_ID}|{voice_id}|"
        f"{language}|speed={speed:.2f}|settings={settings}"
    )


def profile_key_from_config(config: dict | None) -> str | None:
    cfg = config or {}
    tts_model = cfg.get("tts_model", "openai-tts")
    voice_id = str(cfg.get("tts_voice_id") or "").strip()
    if not voice_id:
        return None
    language = str(cfg.get("language") or cfg.get("tts_voice_lang") or "ko")
    speed = _coerce_speed(tts_model, cfg.get("tts_speed", 1.0))
    return _cache_key(
        tts_model=tts_model,
        voice_id=voice_id,
        language=language,
        speed=speed,
        voice_settings=resolve_voice_settings(cfg),
    )


def _load_cache() -> dict:
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = CACHE_PATH.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    tmp_path.replace(CACHE_PATH)


def get_cached_voice_profile(key: str | None) -> dict | None:
    if not key:
        return None
    profile = _load_cache().get(key)
    return profile if isinstance(profile, dict) else None


def get_cached_voice_profile_from_config(config: dict | None) -> dict | None:
    return get_cached_voice_profile(profile_key_from_config(config))


def _samples_for_language(language: str) -> list[str]:
    if language == "ja":
        return JA_PROFILE_SAMPLES
    if language == "en":
        return EN_PROFILE_SAMPLES
    return KO_PROFILE_SAMPLES


def _target_range(chars_per_sec: float) -> dict:
    low = max(8, int(math.ceil(app_config.TTS_MIN_DURATION * chars_per_sec)) - 1)
    high = int(math.ceil(app_config.TTS_MAX_DURATION * chars_per_sec))
    return {
        "min_chars": min(low, high),
        "max_chars": high,
        "target_range": f"{min(low, high)}~{high}",
    }


async def ensure_voice_profile_from_config(
    config: dict | None,
    *,
    force: bool = False,
    sample_count: int | None = None,
    log: Callable[[str], None] | None = print,
) -> dict | None:
    """Measure and cache the selected voice speed.

    Returns None for unsupported/non-configured TTS models so script generation
    can continue with conservative defaults instead of blocking the pipeline.
    """
    cfg = config or {}
    tts_model = cfg.get("tts_model", "openai-tts")
    if tts_model != "elevenlabs":
        return None
    if not app_config.ELEVENLABS_API_KEY:
        _log(log, "[voice-profile] skipped: ELEVENLABS_API_KEY is empty")
        return None

    voice_id = str(cfg.get("tts_voice_id") or "").strip()
    if not voice_id:
        _log(log, "[voice-profile] skipped: tts_voice_id is empty")
        return None

    language = str(cfg.get("language") or cfg.get("tts_voice_lang") or "ko")
    speed = _coerce_speed(tts_model, cfg.get("tts_speed", 1.0))
    voice_settings = resolve_voice_settings(cfg)
    key = _cache_key(
        tts_model=tts_model,
        voice_id=voice_id,
        language=language,
        speed=speed,
        voice_settings=voice_settings,
    )

    cache = _load_cache()
    if not force and isinstance(cache.get(key), dict):
        profile = dict(cache[key])
        profile["cached"] = True
        _log(
            log,
            f"[voice-profile] cached {voice_id}: {profile.get('chars_per_sec')} chars/sec",
        )
        return profile

    samples = _samples_for_language(language)
    count = max(1, min(sample_count or DEFAULT_SAMPLE_COUNT, len(samples)))
    samples = samples[:count]
    safe_dir = ARTIFACT_ROOT / _safe_key_part(sha1(key.encode("utf-8")).hexdigest()[:16])
    safe_dir.mkdir(parents=True, exist_ok=True)

    service = get_tts_service(tts_model)
    measurements: list[dict] = []
    total_chars = 0
    total_words = 0
    total_duration = 0.0

    _log(log, f"[voice-profile] measuring {voice_id} with {len(samples)} samples")
    for idx, text in enumerate(samples, start=1):
        output_dir = safe_dir / f"sample_{idx:02d}"
        output_dir.mkdir(parents=True, exist_ok=True)
        # Keep this exact basename so ElevenLabsService skips production timing warnings.
        output_path = str(output_dir / "voice_preview.mp3")
        result = await service.generate(
            text,
            voice_id,
            output_path,
            speed=speed,
            voice_settings=voice_settings,
        )
        duration = float(result.get("duration") or 0.0)
        if duration <= 0:
            continue
        chars = _count_chars(text, language)
        words = _count_words(text)
        total_chars += chars
        total_words += words
        total_duration += duration
        measurements.append({
            "text": text,
            "chars": chars,
            "words": words,
            "duration": round(duration, 3),
            "chars_per_sec": round(chars / duration, 3),
            "words_per_sec": round(words / duration, 3) if words else None,
        })
        _log(log, f"[voice-profile] sample {idx}: {chars} chars / {duration:.2f}s")

    if not measurements or total_duration <= 0:
        raise RuntimeError("Voice profiling failed: no measurable TTS samples")

    chars_per_sec = total_chars / total_duration
    words_per_sec = total_words / total_duration if total_words else None
    timing = _target_range(chars_per_sec)
    profile = {
        "key": key,
        "provider": tts_model,
        "voice_id": voice_id,
        "language": language,
        "speed": speed,
        "tts_model_id": ELEVENLABS_TTS_MODEL_ID,
        "settings_hash": _settings_hash(voice_settings),
        "sample_count": len(measurements),
        "chars_per_sec": round(chars_per_sec, 3),
        "words_per_sec": round(words_per_sec, 3) if words_per_sec else None,
        "target_min_sec": app_config.TTS_MIN_DURATION,
        "target_max_sec": app_config.TTS_MAX_DURATION,
        **timing,
        "samples": measurements,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "artifact_dir": str(safe_dir),
        "cached": False,
    }
    cache[key] = profile
    _save_cache(cache)
    _log(
        log,
        f"[voice-profile] saved {voice_id}: {profile['chars_per_sec']} chars/sec, "
        f"target {profile['target_range']} chars",
    )
    return profile
