from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable

from app.services.tts.japanese_reading_dictionary import (
    JAPANESE_TTS_READING_GUARDS,
    katakana_to_hiragana,
    unresolved_japanese_reading_terms,
)
from app.services.tts.narration_source import (
    get_cut_tts_narration,
    is_japanese_language,
    uses_cut_tts_narration,
)
from app.services.tts.pronunciation_normalizer import prepare_spoken_narration_for_tts


_KANJI_RE = re.compile(r"[\u3400-\u9fff]")
_HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
_PARENTHETICAL_RE = re.compile(r"（[^）]*）|\([^)]*\)|【[^】]*】|\[[^]]*]")
_NON_READING_RE = re.compile(r"[^ぁ-んー]")
_MIN_ALIGNMENT_LENGTH = 8
_MIN_ALIGNMENT_RATIO = 0.50
_GUARD_CONTEXT_EXCLUSIONS = {
    "一人": re.compile(r"一人(?:称|前)"),
    "二人": re.compile(r"二人(?:称|三脚)"),
}


@dataclass(frozen=True)
class JapaneseTTSPreflightIssue:
    cut_number: int
    code: str
    message: str

    def format(self) -> str:
        return f"cut {self.cut_number}: {self.message}"


def _reading_key(text: str) -> str:
    return _NON_READING_RE.sub("", katakana_to_hiragana(str(text or "")))


def _normalized_source_reading(text: str) -> str:
    source = _PARENTHETICAL_RE.sub("", str(text or ""))
    return prepare_spoken_narration_for_tts(source, "ja")


def _selected_cut_numbers(cut_numbers: Iterable[int] | None) -> set[int] | None:
    if cut_numbers is None:
        return None
    out: set[int] = set()
    for value in cut_numbers:
        try:
            out.add(int(value))
        except (TypeError, ValueError):
            continue
    return out


def inspect_japanese_tts_script(
    script: dict | None,
    config: dict | None,
    *,
    cut_numbers: Iterable[int] | None = None,
) -> list[JapaneseTTSPreflightIssue]:
    if not is_japanese_language(config or {}):
        return []

    selected = _selected_cut_numbers(cut_numbers)
    issues: list[JapaneseTTSPreflightIssue] = []
    cuts = (script or {}).get("cuts", []) if isinstance(script, dict) else []
    for index, cut in enumerate(cuts, start=1):
        if not isinstance(cut, dict):
            continue
        try:
            cut_number = int(cut.get("cut_number") or index)
        except (TypeError, ValueError):
            cut_number = index
        if selected is not None and cut_number not in selected:
            continue

        source = str(cut.get("narration") or "").strip()
        source_without_parentheticals = _PARENTHETICAL_RE.sub("", source)
        explicit = uses_cut_tts_narration(cut, config or {})
        tts_text = get_cut_tts_narration(cut, config or {}, source).strip()
        if not tts_text:
            issues.append(JapaneseTTSPreflightIssue(cut_number, "empty_tts", "TTS 대사가 비어 있습니다"))
            continue

        if explicit and _KANJI_RE.search(tts_text):
            issues.append(
                JapaneseTTSPreflightIssue(
                    cut_number,
                    "explicit_tts_contains_kanji",
                    "별도 TTS 대사에 한자가 남아 있습니다",
                )
            )
        if explicit and _HANGUL_RE.search(tts_text):
            issues.append(
                JapaneseTTSPreflightIssue(
                    cut_number,
                    "explicit_tts_contains_hangul",
                    "별도 TTS 대사에 한글이 남아 있습니다",
                )
            )

        spoken = prepare_spoken_narration_for_tts(tts_text, "ja")
        unresolved = unresolved_japanese_reading_terms(spoken)
        if unresolved:
            issues.append(
                JapaneseTTSPreflightIssue(
                    cut_number,
                    "unresolved_reading",
                    f"발음 변환 후 미해결 문자가 남았습니다: {', '.join(unresolved[:4])}",
                )
            )

        spoken_key = _reading_key(spoken)
        for surface, accepted_readings in JAPANESE_TTS_READING_GUARDS:
            guard_source = source_without_parentheticals
            exclusion = _GUARD_CONTEXT_EXCLUSIONS.get(surface)
            if exclusion is not None:
                guard_source = exclusion.sub("", guard_source)
            required_count = guard_source.count(surface)
            if required_count <= 0:
                continue
            accepted_keys = tuple(_reading_key(reading) for reading in accepted_readings)
            actual_count = sum(spoken_key.count(reading) for reading in accepted_keys if reading)
            if actual_count >= required_count:
                continue
            accepted_label = " / ".join(accepted_readings)
            issues.append(
                JapaneseTTSPreflightIssue(
                    cut_number,
                    "verified_reading_mismatch",
                    f"{surface} 독음 불일치: 허용 독음 {accepted_label}",
                )
            )

        if explicit:
            source_key = _reading_key(_normalized_source_reading(source))
            if len(source_key) >= _MIN_ALIGNMENT_LENGTH and len(spoken_key) >= _MIN_ALIGNMENT_LENGTH:
                ratio = SequenceMatcher(None, source_key, spoken_key, autojunk=False).ratio()
                if ratio < _MIN_ALIGNMENT_RATIO:
                    issues.append(
                        JapaneseTTSPreflightIssue(
                            cut_number,
                            "source_tts_alignment",
                            f"자막 원문과 TTS 독음의 일치도가 낮습니다 ({ratio:.2f})",
                        )
                    )
    return issues


def assert_japanese_tts_script_ready(
    script: dict | None,
    config: dict | None,
    *,
    cut_numbers: Iterable[int] | None = None,
) -> None:
    issues = inspect_japanese_tts_script(script, config, cut_numbers=cut_numbers)
    if not issues:
        return
    preview = "; ".join(issue.format() for issue in issues[:12])
    extra = f"; 외 {len(issues) - 12}건" if len(issues) > 12 else ""
    raise ValueError(f"일본어 TTS 사전검수 실패 ({len(issues)}건): {preview}{extra}")
