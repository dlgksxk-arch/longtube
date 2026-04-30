"""Shared helpers for video title formatting."""

from __future__ import annotations

import re
from typing import Any, Optional

_EP_PREFIX_RE = re.compile(r"^\s*EP\.?\s*\d+", re.IGNORECASE)


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
    if _EP_PREFIX_RE.match(text):
        return text
    return f"{prefix} {text}".strip()
