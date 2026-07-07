"""Select the text that should be sent to TTS without changing subtitle text."""
from pathlib import Path
from typing import Any

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


def get_cut_tts_narration(cut_data: dict | None, config: dict | None, fallback: str | None = None) -> str:
    """Use explicit TTS narration only for Japanese projects."""
    cut = cut_data or {}
    base = str(fallback if fallback is not None else cut.get("narration") or "")
    if not is_japanese_language(config or {}):
        return base
    for key in _TTS_NARRATION_KEYS:
        value = str(cut.get(key) or "").strip()
        if value:
            return value
    return base


def uses_cut_tts_narration(cut_data: dict | None, config: dict | None) -> bool:
    if not is_japanese_language(config or {}):
        return False
    cut = cut_data or {}
    return any(str(cut.get(key) or "").strip() for key in _TTS_NARRATION_KEYS)


def tts_input_marker_path(audio_path: str | Path) -> Path:
    return Path(audio_path).with_name(Path(audio_path).name + ".tts.txt")


def tts_input_marker_matches(audio_path: str | Path, expected_tts_narration: str, *, enabled: bool) -> bool:
    if not enabled:
        return True
    marker = tts_input_marker_path(audio_path)
    try:
        return marker.read_text(encoding="utf-8").strip() == str(expected_tts_narration or "").strip()
    except OSError:
        return False


def write_tts_input_marker(audio_path: str | Path, tts_narration: str, *, enabled: bool) -> None:
    if not enabled:
        return
    marker = tts_input_marker_path(audio_path)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(str(tts_narration or "").strip(), encoding="utf-8")
