"""Shared helpers for video title formatting."""

from __future__ import annotations

import re
from typing import Any, Optional

_EP_PREFIX_RE = re.compile(r"^\s*EP\.?\s*0*\d+\s*[-:.)]?\s*", re.IGNORECASE)
_EPISODE_PREFIX_RE = re.compile(
    r"^\s*(?:episode|ep)\s*0*\d+\s*[-:.)]\s*",
    re.IGNORECASE,
)
_EP_TAIL_RE = re.compile(
    r"\s*(?:[|/\\\-–—:·]\s*)?"
    r"(?:"
    r"EP\.?\s*0*\d+"
    r"|episode\s*0*\d+"
    r"|episodes?\s*0*\d+"
    r"|에피소드\s*0*\d+"
    r"|第\s*0*\d+\s*[話话集]"
    r"|第\s*[一二三四五六七八九十百千〇零]+\s*[話话集]"
    r"|एपिसोड\s*0*\d+"
    r"|भाग\s*0*\d+"
    r")\s*$",
    re.IGNORECASE,
)
_EP_PIPE_TAIL_RE = re.compile(
    r"\s*[|/\\]\s*"
    r"(?:"
    r".{0,48}?"
    r"(?:EP\.?\s*0*\d+|episode\s*0*\d+|에피소드\s*0*\d+|एपिसोड\s*0*\d+|भाग\s*0*\d+)"
    r")\s*$",
    re.IGNORECASE,
)
_EP_MARKER_RE = re.compile(
    r"\s*(?:[-–—:·]\s*)?"
    r"(?:EP\.?\s*0*\d+|episode\s*0*\d+|에피소드\s*0*\d+|एपिसोड\s*0*\d+|भाग\s*0*\d+)"
    r"\s*(?:[-–—:·]\s*)?",
    re.IGNORECASE,
)
_WHITESPACE_RE = re.compile(r"\s+")
_HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
_JAPANESE_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")
_SHORTS_NUMBER_HASHTAG_RE = re.compile(r"\s+#\d+\b")
_SHORTS_HASHTAG_RE = re.compile(r"\s+#Shorts\b", re.IGNORECASE)


def _first_title_variant(text: str) -> str:
    parts = [p.strip() for p in text.split("|") if p.strip()]
    if not parts:
        return text
    for part in parts:
        cleaned = _EP_MARKER_RE.sub(" ", part).strip(" |/-–—:·")
        if cleaned:
            return part
    return parts[0]


def coerce_episode_number(value: Any) -> Optional[int]:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def episode_label(value: Any) -> str:
    number = coerce_episode_number(value)
    return f"EP.{number:02d}" if number else ""


def with_episode_prefix(title: Any, episode_number: Any) -> str:
    text = str(title or "").strip()
    prefix = episode_label(episode_number)
    if not prefix:
        return text
    text = _EP_PREFIX_RE.sub("", text, count=1).strip()
    text = _EPISODE_PREFIX_RE.sub("", text, count=1).strip()
    text = _first_title_variant(text)
    previous = None
    while previous != text:
        previous = text
        text = _EP_PIPE_TAIL_RE.sub("", text).strip()
        text = _EP_TAIL_RE.sub("", text).strip()
        text = _EP_MARKER_RE.sub(" ", text).strip()
    text = _WHITESPACE_RE.sub(" ", text).strip(" |/-–—:·")
    return f"{text} {prefix}".strip()


def without_episode_prefix(title: Any) -> str:
    """Remove visual episode markers for contexts that must not show EP numbers."""
    text = str(title or "").strip()
    text = _EP_PREFIX_RE.sub("", text, count=1).strip()
    text = _EPISODE_PREFIX_RE.sub("", text, count=1).strip()
    text = _first_title_variant(text)
    previous = None
    while previous != text:
        previous = text
        text = _EP_PIPE_TAIL_RE.sub("", text).strip()
        text = _EP_TAIL_RE.sub("", text).strip()
        text = _EP_MARKER_RE.sub(" ", text).strip()
    return _WHITESPACE_RE.sub(" ", text).strip(" |/-–—:·")


def shorts_upload_title(base_title: Any, *, index: Any = None, total: Any = None, max_len: int = 100) -> str:
    """Build a YouTube Shorts title without numeric hashtags like #1/#2."""
    text = without_episode_prefix(base_title) or "Shorts"
    text = _SHORTS_NUMBER_HASHTAG_RE.sub("", text)
    text = _SHORTS_HASHTAG_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text).strip(" |/-–—:·")
    part = ""
    try:
        idx = int(index)
        count = int(total)
        if count > 1 and idx > 0:
            part = f" · Part {idx}"
    except (TypeError, ValueError):
        part = ""
    suffix = f"{part} #Shorts"
    max_base_len = max(1, int(max_len or 100) - len(suffix))
    return f"{text[:max_base_len].rstrip()}{suffix}".strip()


def script_title_for_language(
    *,
    generated_title: Any,
    project_title: Any,
    topic: Any,
    episode_number: Any,
    language: Any,
    first_narration: Any = None,
) -> str:
    lang = str(language or "ko").strip().lower()
    if lang in {"ko", "kr", "kor", "korean"}:
        base = project_title or topic or generated_title or "Untitled"
    else:
        base = generated_title or project_title or topic or "Untitled"
        if lang in {"ja", "jp", "jpn", "japanese"} and _HANGUL_RE.search(str(base or "")):
            narration = without_episode_prefix(first_narration)
            if narration and _JAPANESE_RE.search(narration) and not _HANGUL_RE.search(narration):
                base = narration
    return with_episode_prefix(base, episode_number)
