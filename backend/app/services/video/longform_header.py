"""Deterministic top-corner labels for the final long-form render."""
from __future__ import annotations

import os
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


CHANNEL_DISPLAY_NAMES = {
    1: "10분역공",
    2: "Scartography",
    3: "闇解き日本史",
    4: "Empire Errors",
}

# Match the Remotion Shorts hero font stack. The first available face is used.
_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\malgunbd.ttf",
    r"C:\Windows\Fonts\meiryob.ttc",
    r"C:\Windows\Fonts\YuGothB.ttc",
    r"C:\Windows\Fonts\arialbd.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)


def resolve_longform_channel_name(config: dict | None, channel_id: int | None) -> str:
    cfg = config or {}
    configured = (
        cfg.get("longform_channel_name")
        or cfg.get("channel_display_name")
        or cfg.get("youtube_channel_name")
        or cfg.get("brand_name")
        or cfg.get("shorts_channel_name")
    )
    if str(configured or "").strip():
        return str(configured).strip()
    return CHANNEL_DISPLAY_NAMES.get(int(channel_id or 0), "")


def resolve_longform_title(project_title: str | None, script: dict | None) -> str:
    source = script if isinstance(script, dict) else {}
    topic = str(source.get("topic") or "").strip()
    if topic:
        return re.sub(r"\s+", " ", topic)
    title = str(source.get("title") or project_title or "").strip()
    title = re.sub(
        r"^.*?[-–—]?\s*EP(?:ISODE)?\.?\s*\d+\s*[:：\-–—]?\s*",
        "",
        title,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", title)


def _font(size: int) -> ImageFont.ImageFont:
    for candidate in _FONT_CANDIDATES:
        if not os.path.isfile(candidate):
            continue
        try:
            return ImageFont.truetype(candidate, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=0)
    return max(0, bbox[2] - bbox[0]), max(0, bbox[3] - bbox[1])


def _fit_one_line(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    start_size: int,
    min_size: int,
) -> tuple[str, ImageFont.ImageFont, int, int]:
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    for size in range(start_size, min_size - 1, -1):
        font = _font(size)
        width, height = _text_size(draw, clean, font)
        if width <= max_width:
            return clean, font, width, height

    font = _font(min_size)
    ellipsis = "…"
    shortened = clean
    while shortened:
        candidate = shortened.rstrip() + ellipsis
        width, height = _text_size(draw, candidate, font)
        if width <= max_width:
            return candidate, font, width, height
        shortened = shortened[:-1]
    width, height = _text_size(draw, ellipsis, font)
    return ellipsis, font, width, height


def create_longform_header_overlay(
    output_path: str | Path,
    *,
    resolution: str,
    title: str,
    channel_name: str,
) -> Path:
    """Create a transparent full-frame PNG with title left and channel right."""
    try:
        width, height = (int(part) for part in str(resolution).lower().split("x", 1))
    except (TypeError, ValueError):
        raise ValueError(f"Invalid render resolution: {resolution!r}")
    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid render resolution: {resolution!r}")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    scale = max(0.55, min(2.0, width / 1920.0))
    margin_x = max(20, round(48 * scale))
    margin_y = max(16, round(30 * scale))
    gap = max(16, round(32 * scale))
    # Shorts hero text uses a heavy black stroke at roughly 9% of font size.
    # Channel stays at the doubled size; the episode title uses 70% of it.
    channel_stroke = max(4, round(8 * scale))
    channel_start_size = max(48, round(84 * scale))
    channel_min_size = max(36, round(54 * scale))
    title_stroke = max(3, round(8 * scale * 0.70))
    title_start_size = max(34, round(84 * scale * 0.70))
    title_min_size = max(25, round(54 * scale * 0.70))

    usable_width = width - (margin_x * 2) - gap
    channel_limit = max(round(usable_width * 0.20), round(260 * scale))
    title_limit = max(1, usable_width - channel_limit)

    channel_text, channel_font, channel_w, channel_h = _fit_one_line(
        draw, channel_name, channel_limit, channel_start_size, channel_min_size
    )
    title_text, title_font, title_w, title_h = _fit_one_line(
        draw, title, title_limit, title_start_size, title_min_size
    )

    if title_text:
        draw.text(
            (margin_x, margin_y),
            title_text,
            font=title_font,
            fill=(255, 255, 255, 102),
            stroke_width=title_stroke,
            stroke_fill=(0, 0, 0, 102),
        )

    if channel_text:
        draw.text(
            (width - margin_x - channel_w, margin_y),
            channel_text,
            font=channel_font,
            fill=(255, 210, 74, 102),
            stroke_width=channel_stroke,
            stroke_fill=(0, 0, 0, 102),
        )

    image.save(output, format="PNG")
    return output
