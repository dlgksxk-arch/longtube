"""Select the text that should be sent to TTS without changing subtitle text."""
import hashlib
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from app.services.tts.pronunciation_normalizer import (
    prepare_spoken_narration_for_tts,
    pronunciation_normalizer_signature,
)

_JA_LANGUAGE_ALIASES = {
    "jp",
    "jpn",
    "japanese",
    "nihongo",
    "日本語",
    "일본어",
}

_TTS_NARRATION_KEYS = (
    "tts_narration",
    "narration_tts",
    "narration_hiragana",
    "hiragana_narration",
    "대사히라가나",
)
_JA_EXPLICIT_READING_CORRECTIONS: tuple[tuple[str, str, str], ...] = (
    ("喧嘩", "げんか", "けんか"),
    ("死体", "いたい", "したい"),
    ("三種の神器", "みくさのかんどから", "みくさのかむたから"),
)
TTS_INPUT_MARKER_VERSION = 2
_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class PreparedTTSNarration:
    cut_number: int
    original_narration: str
    tts_narration: str
    spoken_narration: str
    previous_text: str = ""
    next_text: str = ""
    uses_explicit_tts: bool = False


def is_japanese_language(config_or_language: Any) -> bool:
    if isinstance(config_or_language, dict):
        raw = (
            config_or_language.get("language")
            or config_or_language.get("lang")
            or config_or_language.get("target_language")
            or ""
        )
    else:
        raw = config_or_language or ""
    language = str(raw).strip().lower().replace("_", "-")
    return language.startswith("ja") or language in _JA_LANGUAGE_ALIASES


def canonical_tts_language(config_or_language: Any) -> str:
    if is_japanese_language(config_or_language):
        return "ja"
    if isinstance(config_or_language, dict):
        raw = (
            config_or_language.get("language")
            or config_or_language.get("lang")
            or config_or_language.get("target_language")
            or "ko"
        )
    else:
        raw = config_or_language or "ko"
    return str(raw).strip().lower().replace("_", "-") or "ko"


def get_cut_tts_narration(cut_data: dict | None, config: dict | None, fallback: str | None = None) -> str:
    """Use explicit TTS narration only for Japanese projects."""
    cut = cut_data or {}
    base = str(fallback if fallback is not None else cut.get("narration") or "")
    if not is_japanese_language(config or {}):
        return base
    for key in _TTS_NARRATION_KEYS:
        value = str(cut.get(key) or "").strip()
        if value:
            corrected = value
            for surface, wrong_reading, verified_reading in _JA_EXPLICIT_READING_CORRECTIONS:
                if surface in base and wrong_reading in corrected:
                    corrected = corrected.replace(wrong_reading, verified_reading, base.count(surface))
            return corrected
    return base


def uses_cut_tts_narration(cut_data: dict | None, config: dict | None) -> bool:
    if not is_japanese_language(config or {}):
        return False
    cut = cut_data or {}
    return any(str(cut.get(key) or "").strip() for key in _TTS_NARRATION_KEYS)


def prepare_script_tts_inputs(script: dict | None, config: dict | None) -> dict[int, PreparedTTSNarration]:
    language = canonical_tts_language(config or {})
    prepared: list[PreparedTTSNarration] = []
    cuts = (script or {}).get("cuts", []) if isinstance(script, dict) else []
    for index, cut in enumerate(cuts, start=1):
        if not isinstance(cut, dict):
            continue
        try:
            cut_number = int(cut.get("cut_number") or index)
        except (TypeError, ValueError):
            cut_number = index
        original = str(cut.get("narration") or "").strip()
        raw_tts = get_cut_tts_narration(cut, config or {}, original).strip()
        prepared.append(
            PreparedTTSNarration(
                cut_number=cut_number,
                original_narration=original,
                tts_narration=raw_tts,
                spoken_narration=prepare_spoken_narration_for_tts(raw_tts, language),
                uses_explicit_tts=uses_cut_tts_narration(cut, config or {}),
            )
        )

    with_context: dict[int, PreparedTTSNarration] = {}
    for index, item in enumerate(prepared):
        previous_text = prepared[index - 1].spoken_narration if index > 0 else ""
        next_text = prepared[index + 1].spoken_narration if index + 1 < len(prepared) else ""
        with_context[item.cut_number] = replace(
            item,
            previous_text=previous_text,
            next_text=next_text,
        )
    return with_context


def pronunciation_dictionary_locators_from_config(config: dict | None) -> list[dict[str, str]]:
    cfg = config or {}
    options = cfg.get("tts_options") if isinstance(cfg.get("tts_options"), dict) else {}
    raw = (
        cfg.get("elevenlabs_pronunciation_dictionary_locators")
        or cfg.get("tts_pronunciation_dictionary_locators")
        or options.get("pronunciation_dictionary_locators")
        or []
    )
    if isinstance(raw, dict):
        raw = [raw]
    out: list[dict[str, str]] = []
    if isinstance(raw, (list, tuple)):
        for item in raw:
            if not isinstance(item, dict):
                continue
            dictionary_id = str(
                item.get("pronunciation_dictionary_id")
                or item.get("dictionary_id")
                or item.get("id")
                or ""
            ).strip()
            version_id = str(item.get("version_id") or item.get("version") or "").strip()
            if dictionary_id and version_id:
                out.append({
                    "pronunciation_dictionary_id": dictionary_id,
                    "version_id": version_id,
                })
            if len(out) >= 3:
                break
    if not out:
        dictionary_id = str(cfg.get("elevenlabs_pronunciation_dictionary_id") or "").strip()
        version_id = str(cfg.get("elevenlabs_pronunciation_dictionary_version_id") or "").strip()
        if dictionary_id and version_id:
            out.append({
                "pronunciation_dictionary_id": dictionary_id,
                "version_id": version_id,
            })
    return out


def build_tts_request_context(item: PreparedTTSNarration, config: dict | None) -> dict[str, Any]:
    if not is_japanese_language(config or {}):
        return {}
    context: dict[str, Any] = {
        "language_code": "ja",
        "apply_language_text_normalization": True,
    }
    if item.previous_text:
        context["previous_text"] = item.previous_text
    if item.next_text:
        context["next_text"] = item.next_text
    locators = pronunciation_dictionary_locators_from_config(config)
    if locators:
        context["pronunciation_dictionary_locators"] = locators
    return context


def build_tts_input_marker_payload(
    item: PreparedTTSNarration,
    config: dict | None,
    *,
    provider: str,
    engine_model: str,
    voice_id: str,
    speed: float,
    voice_settings: dict | None,
) -> dict[str, Any]:
    language = canonical_tts_language(config or {})
    return {
        "version": TTS_INPUT_MARKER_VERSION,
        "tts_narration": _SPACE_RE.sub(" ", item.tts_narration).strip(),
        "spoken_narration": item.spoken_narration.strip(),
        "language": language,
        "provider": str(provider or ""),
        "engine_model": str(engine_model or ""),
        "voice_id": str(voice_id or ""),
        "speed": round(float(speed or 1.0), 4),
        "voice_settings": dict(voice_settings or {}),
        "request_context": build_tts_request_context(item, config),
        "normalizer_signature": pronunciation_normalizer_signature(language),
    }


def tts_input_marker_path(audio_path: str | Path) -> Path:
    return Path(audio_path).with_name(Path(audio_path).name + ".tts.json")


def legacy_tts_input_marker_path(audio_path: str | Path) -> Path:
    return Path(audio_path).with_name(Path(audio_path).name + ".tts.txt")


def _marker_digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def tts_input_marker_matches(
    audio_path: str | Path,
    expected_tts_narration: str | Mapping[str, Any],
    *,
    enabled: bool,
) -> bool:
    if not enabled:
        return True
    if isinstance(expected_tts_narration, Mapping):
        marker = tts_input_marker_path(audio_path)
        try:
            stored = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return False
        expected = dict(expected_tts_narration)
        return bool(
            stored.get("version") == TTS_INPUT_MARKER_VERSION
            and stored.get("digest") == _marker_digest(expected)
            and stored.get("payload") == expected
        )
    try:
        return legacy_tts_input_marker_path(audio_path).read_text(encoding="utf-8").strip() == str(
            expected_tts_narration or ""
        ).strip()
    except OSError:
        return False


def write_tts_input_marker(
    audio_path: str | Path,
    tts_narration: str | Mapping[str, Any],
    *,
    enabled: bool,
) -> None:
    if not enabled:
        return
    if isinstance(tts_narration, Mapping):
        marker = tts_input_marker_path(audio_path)
        marker.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(tts_narration)
        stored = {
            "version": TTS_INPUT_MARKER_VERSION,
            "digest": _marker_digest(payload),
            "payload": payload,
        }
        temp = marker.with_name(marker.name + ".tmp")
        temp.write_text(json.dumps(stored, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        temp.replace(marker)
        return
    marker = legacy_tts_input_marker_path(audio_path)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(str(tts_narration or "").strip(), encoding="utf-8")
