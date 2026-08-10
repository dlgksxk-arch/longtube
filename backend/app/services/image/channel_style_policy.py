"""Channel-specific rendering style locks shared by cut and thumbnail paths."""

from __future__ import annotations

import re
from typing import Any, Mapping

from app.services.image.prompt_builder import apply_project_style_to_canonical_prompt


CH3_FIXED_CARTOON_STYLE = (
    "Stylish high-impact historical documentary cartoon illustration, clean thick "
    "outlines, bold graphic shapes, cinematic cel-shaded lighting, vivid but "
    "controlled colors, dramatic rim light, strong silhouettes, dynamic camera "
    "angles, clear foreground action or readable emotion, exciting tension, "
    "polished premium YouTube documentary cartoon look."
)


def is_channel3_context(
    config: Mapping[str, Any] | None = None,
    project_id: object = "",
) -> bool:
    """Return True only for explicit CH3 identifiers."""
    cfg = config or {}
    for key in ("channel", "youtube_channel", "channel_number", "channel_id"):
        value = cfg.get(key)
        if value is None:
            continue
        normalized = str(value).strip().upper()
        if normalized in {"3", "CH3"}:
            return True

    result_dir = str(cfg.get("result_channel_dir") or "").strip().upper()
    if result_dir == "CH3":
        return True

    pid = str(project_id or "").strip().upper()
    return bool(re.search(r"(?:^|[_\\/\-])CH3(?:[_\\/\-]|$)", pid))


def fixed_channel_image_style(
    config: Mapping[str, Any] | None = None,
    project_id: object = "",
    configured_style: object = "",
) -> str:
    """Resolve the immutable rendering style for channels that define one."""
    if is_channel3_context(config, project_id):
        return CH3_FIXED_CARTOON_STYLE
    return re.sub(r"\s+", " ", str(configured_style or "")).strip()


def apply_fixed_channel_image_style(
    prompt: object,
    config: Mapping[str, Any] | None = None,
    project_id: object = "",
) -> str:
    """Apply CH3's style at the final prompt boundary without changing its scene."""
    text = str(prompt or "").strip()
    if not text or not is_channel3_context(config, project_id):
        return text

    styled = apply_project_style_to_canonical_prompt(text, CH3_FIXED_CARTOON_STYLE)
    if styled != text or CH3_FIXED_CARTOON_STYLE in styled:
        return styled

    return (
        f"{text} || CHANNEL 3 RENDERING STYLE LOCK: "
        f"{CH3_FIXED_CARTOON_STYLE}"
    )
