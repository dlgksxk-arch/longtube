from __future__ import annotations

import re

from app.services.tts.number_normalizer import normalize_year_numbers_for_tts


_KO_PRONUNCIATION_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("문무왕", "문무 왕"),
    ("태종무열왕", "태종 무열 왕"),
    ("무열왕", "무열 왕"),
    ("법흥왕", "법흥 왕"),
    ("진흥왕", "진흥 왕"),
    ("성왕", "성 왕"),
    ("선덕여왕", "선덕 여왕"),
    ("진덕여왕", "진덕 여왕"),
    ("진성여왕", "진성 여왕"),
)
_SPACE_RE = re.compile(r"\s+")


def normalize_korean_pronunciation_for_tts(text: str) -> str:
    result = str(text or "")
    for source, spoken in _KO_PRONUNCIATION_REPLACEMENTS:
        result = result.replace(source, spoken)
    return _SPACE_RE.sub(" ", result).strip()


def prepare_spoken_narration_for_tts(text: str, language: str = "ko") -> str:
    spoken = normalize_year_numbers_for_tts(str(text or ""), language)
    if str(language or "").lower().startswith("ko"):
        spoken = normalize_korean_pronunciation_for_tts(spoken)
    return spoken
