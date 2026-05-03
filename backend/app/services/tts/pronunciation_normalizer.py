from __future__ import annotations

import re

from app.services.tts.number_normalizer import normalize_year_numbers_for_tts


_KO_PRONUNCIATION_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("법흥왕", "법흥 왕"),
    ("진흥왕", "진흥 왕"),
    ("성왕", "성 왕"),
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
