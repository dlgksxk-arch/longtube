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
    return f"{prefix} {text}".strip()
