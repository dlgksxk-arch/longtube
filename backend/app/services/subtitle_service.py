"""Subtitle generation service (ASS format)"""
import hashlib
import json
import re
import shutil
from pathlib import Path

from app.config import CUT_VIDEO_DURATION


CUT_SUBTITLE_START_SEC = 0.2
CUT_SUBTITLE_END_SEC = 4.8
CUT_SUBTITLE_MARKER_VERSION = 9
LEGACY_SUBTITLE_SIZE_MAP = {
    49: 59,
    53: 63,
    58: 68,
    71: 81,
    77: 87,
}


# Global burned-in subtitle look requested for long-form videos:
# large white heavy text, thick black outline, bottom-center placement.
DEFAULT_SUBTITLE_STYLE = {
    "preset": "current",
    "font": "Pretendard Bold",
    "size": 68,
    "color": "#FFFFFF",
    "outline_color": "#000000",
    "position": "bottom",
    "outline_width": 6,
    "shadow": 0,
    "margin_v": 70,
    "bold": True,
    "bg_enabled": False,
}

SUBTITLE_STYLE_PRESETS = {
    "current": {
        "label": "현재",
        "style": dict(DEFAULT_SUBTITLE_STYLE),
    },
    "clean_box": {
        "label": "깔끔 박스",
        "style": {
            **DEFAULT_SUBTITLE_STYLE,
            "size": 63,
            "outline_width": 3,
            "shadow": 0,
            "bg_enabled": True,
            "bg_color": "#000000",
            "bg_opacity": 0.62,
            "margin_v": 76,
        },
    },
    "impact": {
        "label": "임팩트",
        "style": {
            **DEFAULT_SUBTITLE_STYLE,
            "size": 81,
            "color": "#FFE600",
            "outline_color": "#000000",
            "outline_width": 10,
            "shadow": 3,
            "margin_v": 82,
            "bg_enabled": False,
        },
    },
    "shorts_pop": {
        "label": "쇼츠 팝",
        "style": {
            **DEFAULT_SUBTITLE_STYLE,
            "size": 87,
            "color": "#FFFFFF",
            "outline_color": "#111111",
            "outline_width": 9,
            "shadow": 4,
            "margin_v": 110,
            "bg_enabled": True,
            "bg_color": "#8A2BE2",
            "bg_opacity": 0.38,
        },
    },
    "news": {
        "label": "뉴스",
        "style": {
            **DEFAULT_SUBTITLE_STYLE,
            "size": 59,
            "color": "#FFFFFF",
            "outline_width": 2,
            "shadow": 0,
            "bg_enabled": True,
            "bg_color": "#102A43",
            "bg_opacity": 0.78,
            "margin_v": 58,
        },
    },
}


# Korean-variety key-point panels.  These are separate from the full-caption
# style above: the full narration remains an SRT track, while only sparse
# highlights are burned into the video.
VARIETY_HIGHLIGHT_PANELS = {
    "neutral": {
        "label": "담백 정보",
        "tags": ("slowly", "flatly", "thoughtful", "softly"),
        "font": "Malgun Gothic", "size": 76, "bold": -1, "italic": 0,
        "scale_x": 100, "scale_y": 100, "spacing": 0, "angle": 0,
        "color": "#FFFFFF", "keyword_color": "#FFE45B",
        "outline_color": "#142033", "outer_outline_color": "#05080E",
        "back_color": "#172033", "accent_color": "#43D7FF",
        "outline": 3, "outer_outline": 8, "shadow": 2,
        "alignment": 1, "margin_l": 90, "margin_r": 70, "margin_v": 92,
        "x_ratio": 0.07, "y_ratio": 0.86,
        "motion": "soft_pop", "decoration": "info_bracket", "keyword_scale": 112,
    },
    "epic": {
        "label": "웅장 선언",
        "tags": ("dramatic", "booming"),
        "font": "Malgun Gothic", "size": 96, "bold": -1, "italic": 0,
        "scale_x": 106, "scale_y": 100, "spacing": 3, "angle": 0,
        "color": "#FFF1B8", "keyword_color": "#FFD034",
        "outline_color": "#6D3D00", "outer_outline_color": "#1A0B00",
        "back_color": "#3D2100", "accent_color": "#F7B928",
        "outline": 5, "outer_outline": 12, "shadow": 5,
        "alignment": 8, "margin_l": 60, "margin_r": 60, "margin_v": 94,
        "x_ratio": 0.50, "y_ratio": 0.17,
        "motion": "epic_drop", "decoration": "gold_wings", "keyword_scale": 118,
    },
    "anger": {
        "label": "분노 폭발",
        "tags": ("angry", "annoyed", "upset"),
        "font": "Malgun Gothic", "size": 101, "bold": -1, "italic": 0,
        "scale_x": 112, "scale_y": 102, "spacing": 1, "angle": -2,
        "color": "#FFF25B", "keyword_color": "#FFFFFF",
        "outline_color": "#A80000", "outer_outline_color": "#240000",
        "back_color": "#650000", "accent_color": "#FF2A18",
        "outline": 6, "outer_outline": 14, "shadow": 6,
        "alignment": 5, "margin_l": 55, "margin_r": 55, "margin_v": 50,
        "x_ratio": 0.50, "y_ratio": 0.63,
        "motion": "anger_punch", "decoration": "burst_lines", "keyword_scale": 124,
    },
    "shout": {
        "label": "고함 충격",
        "tags": ("shouts",),
        "font": "Malgun Gothic", "size": 108, "bold": -1, "italic": -1,
        "scale_x": 116, "scale_y": 98, "spacing": 4, "angle": -5,
        "color": "#FFFFFF", "keyword_color": "#FFE600",
        "outline_color": "#171717", "outer_outline_color": "#E52B12",
        "back_color": "#111111", "accent_color": "#FF4A22",
        "outline": 7, "outer_outline": 16, "shadow": 4,
        "alignment": 5, "margin_l": 35, "margin_r": 35, "margin_v": 40,
        "x_ratio": 0.50, "y_ratio": 0.51,
        "motion": "shout_slam", "decoration": "speed_lines", "keyword_scale": 126,
    },
    "whisper": {
        "label": "은밀 속삭임",
        "tags": ("quietly", "whispers"),
        "font": "Malgun Gothic", "size": 72, "bold": 0, "italic": -1,
        "scale_x": 98, "scale_y": 94, "spacing": 5, "angle": -1,
        "color": "#F3ECFF", "keyword_color": "#D6B7FF",
        "outline_color": "#39275C", "outer_outline_color": "#120B22",
        "back_color": "#211638", "accent_color": "#A97CFF",
        "outline": 2, "outer_outline": 7, "shadow": 1,
        "alignment": 7, "margin_l": 74, "margin_r": 70, "margin_v": 86,
        "x_ratio": 0.11, "y_ratio": 0.20,
        "motion": "whisper_float", "decoration": "speech_bubble", "keyword_scale": 108,
    },
    "tension": {
        "label": "긴장 초조",
        "tags": ("worried", "rushed", "nervously", "stammers"),
        "font": "Malgun Gothic", "size": 84, "bold": -1, "italic": 0,
        "scale_x": 96, "scale_y": 106, "spacing": 1, "angle": 3,
        "color": "#E6FFF8", "keyword_color": "#FFEB58",
        "outline_color": "#076A5F", "outer_outline_color": "#032521",
        "back_color": "#063F39", "accent_color": "#36E0C1",
        "outline": 4, "outer_outline": 10, "shadow": 3,
        "alignment": 9, "margin_l": 65, "margin_r": 84, "margin_v": 90,
        "x_ratio": 0.89, "y_ratio": 0.22,
        "motion": "tension_jitter", "decoration": "sweat_drops", "keyword_scale": 116,
    },
    "sad": {
        "label": "슬픔 여운",
        "tags": ("sorrowful", "crying", "sighs"),
        "font": "Malgun Gothic", "size": 79, "bold": -1, "italic": 0,
        "scale_x": 95, "scale_y": 104, "spacing": 2, "angle": 0,
        "color": "#E5F1FF", "keyword_color": "#8ED0FF",
        "outline_color": "#1A4D7D", "outer_outline_color": "#06182D",
        "back_color": "#0C2C4A", "accent_color": "#63B8F7",
        "outline": 3, "outer_outline": 9, "shadow": 1,
        "alignment": 1, "margin_l": 112, "margin_r": 62, "margin_v": 106,
        "x_ratio": 0.10, "y_ratio": 0.81,
        "motion": "sad_rise", "decoration": "tear_drops", "keyword_scale": 110,
    },
    "shock": {
        "label": "놀람 의문",
        "tags": ("surprised", "gasps", "curious", "questioning"),
        "font": "Malgun Gothic", "size": 104, "bold": -1, "italic": 0,
        "scale_x": 110, "scale_y": 112, "spacing": 0, "angle": 0,
        "color": "#111111", "keyword_color": "#FF2E63",
        "outline_color": "#FFFFFF", "outer_outline_color": "#00A9D6",
        "back_color": "#DDFBFF", "accent_color": "#55E7FF",
        "outline": 5, "outer_outline": 13, "shadow": 4,
        "alignment": 8, "margin_l": 46, "margin_r": 46, "margin_v": 76,
        "x_ratio": 0.50, "y_ratio": 0.23,
        "motion": "shock_bounce", "decoration": "explosion_star", "keyword_scale": 128,
    },
    "sly": {
        "label": "능청 반전",
        "tags": ("mischievously", "sarcastic"),
        "font": "Malgun Gothic", "size": 87, "bold": -1, "italic": -1,
        "scale_x": 104, "scale_y": 96, "spacing": 3, "angle": -7,
        "color": "#F5FF78", "keyword_color": "#FFFFFF",
        "outline_color": "#6D238D", "outer_outline_color": "#210A30",
        "back_color": "#3A1452", "accent_color": "#D86BFF",
        "outline": 5, "outer_outline": 11, "shadow": 2,
        "alignment": 9, "margin_l": 58, "margin_r": 96, "margin_v": 72,
        "x_ratio": 0.88, "y_ratio": 0.19,
        "motion": "sly_swivel", "decoration": "comic_tail", "keyword_scale": 120,
    },
    "joy": {
        "label": "환호 유쾌",
        "tags": ("happily", "excited", "laughs", "giggle"),
        "font": "Malgun Gothic", "size": 94, "bold": -1, "italic": 0,
        "scale_x": 108, "scale_y": 105, "spacing": 2, "angle": 2,
        "color": "#FFFFFF", "keyword_color": "#FFF45B",
        "outline_color": "#D72F80", "outer_outline_color": "#4C1233",
        "back_color": "#7C1E50", "accent_color": "#FF6DAE",
        "outline": 4, "outer_outline": 11, "shadow": 5,
        "alignment": 2, "margin_l": 50, "margin_r": 50, "margin_v": 88,
        "x_ratio": 0.50, "y_ratio": 0.86,
        "motion": "joy_bounce", "decoration": "hearts", "keyword_scale": 122,
    },
}

VARIETY_HIGHLIGHT_FONT_SCALE = 1.5
VARIETY_HIGHLIGHT_ALIGNMENT = 2
VARIETY_HIGHLIGHT_X_RATIO = 0.50
# Keep the Korean-variety key-point panel close to the lower safe area.
VARIETY_HIGHLIGHT_Y_RATIO = 0.91
VARIETY_HIGHLIGHT_MARGIN_L = 50
VARIETY_HIGHLIGHT_MARGIN_R = 50
VARIETY_HIGHLIGHT_MARGIN_V = 92
VARIETY_HERO_BASE_FONT_SIZE = 104
VARIETY_HERO_FONT = "Malgun Gothic"
VARIETY_HERO_OUTLINE = 9
VARIETY_HERO_OUTER_OUTLINE = 14
VARIETY_HERO_SHADOW = 7
VARIETY_HERO_TAG_COLORS = {
    "neutral": "#FFFFFF",
    "epic": "#FFD24A",
    "anger": "#FF3B30",
    "shout": "#FF6B35",
    "whisper": "#C4A7FF",
    "tension": "#3DE0C5",
    "sad": "#76B7FF",
    "shock": "#55E7FF",
    "sly": "#D86BFF",
    "joy": "#FF6DAE",
}
VARIETY_HERO_KEYWORD_COLORS = {
    "neutral": "#FFD24A",
    "epic": "#FFFFFF",
    "anger": "#FFE45B",
    "shout": "#FFFFFF",
    "whisper": "#FFFFFF",
    "tension": "#FFE45B",
    "sad": "#FFFFFF",
    "shock": "#FFE45B",
    "sly": "#FFE45B",
    "joy": "#FFE45B",
}


def _variety_render_panel(panel_id: str, panel: dict) -> dict:
    """Return one Shorts-hero design; emotion panels only change text colors."""
    return {
        **panel,
        "font": VARIETY_HERO_FONT,
        "size": VARIETY_HERO_BASE_FONT_SIZE,
        "bold": -1,
        "italic": 0,
        "scale_x": 100,
        "scale_y": 100,
        "spacing": 0,
        "angle": 0,
        "color": VARIETY_HERO_TAG_COLORS[panel_id],
        "keyword_color": VARIETY_HERO_KEYWORD_COLORS[panel_id],
        "outline_color": "#000000",
        "outer_outline_color": "#050505",
        "back_color": "#000000",
        "outline": VARIETY_HERO_OUTLINE,
        "outer_outline": VARIETY_HERO_OUTER_OUTLINE,
        "shadow": VARIETY_HERO_SHADOW,
        "keyword_scale": 100,
        "alignment": VARIETY_HIGHLIGHT_ALIGNMENT,
        "margin_l": VARIETY_HIGHLIGHT_MARGIN_L,
        "margin_r": VARIETY_HIGHLIGHT_MARGIN_R,
        "margin_v": VARIETY_HIGHLIGHT_MARGIN_V,
        "x_ratio": VARIETY_HIGHLIGHT_X_RATIO,
        "y_ratio": VARIETY_HIGHLIGHT_Y_RATIO,
    }


def _variety_render_font_size(panel: dict, aspect_ratio: str) -> int:
    size = float(VARIETY_HERO_BASE_FONT_SIZE) * VARIETY_HIGHLIGHT_FONT_SCALE
    if aspect_ratio != "16:9":
        size = float(VARIETY_HERO_BASE_FONT_SIZE)
    return max(1, int(size + 0.5))

VARIETY_TAG_TO_PANEL = {
    tag: panel_id
    for panel_id, panel in VARIETY_HIGHLIGHT_PANELS.items()
    for tag in panel["tags"]
}


def resolve_variety_highlight_panel(
    tts_tags: list[str] | tuple[str, ...] | None,
    *,
    panel_mode: str = "emotion_auto",
    fixed_panel: str = "neutral",
) -> str:
    """Resolve one of the ten visual panels from Eleven v3 audio tags."""
    if panel_mode == "fixed":
        return fixed_panel if fixed_panel in VARIETY_HIGHLIGHT_PANELS else "neutral"
    for raw_tag in tts_tags or ():
        panel_id = VARIETY_TAG_TO_PANEL.get(str(raw_tag or "").strip().lower())
        if panel_id:
            return panel_id
    return "neutral"


def normalize_subtitle_style(style_config: dict | None) -> dict:
    raw = dict(style_config or {})
    raw_had_size = "size" in raw and raw.get("size") is not None
    preset_key = str(raw.get("preset") or raw.get("style_preset") or "current").strip()
    base = dict((SUBTITLE_STYLE_PRESETS.get(preset_key) or SUBTITLE_STYLE_PRESETS["current"])["style"])
    for key in (
        "font",
        "size",
        "color",
        "outline_color",
        "position",
        "outline_width",
        "shadow",
        "margin_v",
        "bold",
        "bg_enabled",
        "bg_color",
        "bg_opacity",
    ):
        if key in raw and raw[key] is not None:
            base[key] = raw[key]
    if raw_had_size:
        try:
            size = max(1, int(base["size"]))
            base["size"] = LEGACY_SUBTITLE_SIZE_MAP.get(size, size)
        except (TypeError, ValueError):
            base["size"] = DEFAULT_SUBTITLE_STYLE["size"]
    base["preset"] = preset_key if preset_key in SUBTITLE_STYLE_PRESETS else "current"
    return base


def format_ass_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def format_srt_time(seconds: float) -> str:
    total_ms = max(0, int(round(float(seconds) * 1000)))
    ms = total_ms % 1000
    total_s = total_ms // 1000
    s = total_s % 60
    total_m = total_s // 60
    m = total_m % 60
    h = total_m // 60
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def split_sentences(text: str) -> list[str]:
    """한국어 문장 분리"""
    parts = re.split(r"(?<=[.!?。])\s+", text.strip())
    return [p for p in parts if p.strip()]


def _ass_escape(text: str) -> str:
    return (text or "").replace("\r", " ").replace("\n", " ").strip()


def _srt_escape(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\r", " ").replace("\n", " ")).strip()


_LEADING_TTS_AUDIO_TAGS_RE = re.compile(
    r"^(?P<prefix>(?:\s*\[[a-z][a-z0-9_ -]{0,31}\])+\s*)",
    re.IGNORECASE,
)


def strip_leading_tts_audio_tags(text: str) -> str:
    """Remove source-authored ElevenLabs audio directions from display text."""
    value = str(text or "")
    return _LEADING_TTS_AUDIO_TAGS_RE.sub("", value, count=1).strip()


def _split_text_for_subtitle(text: str, max_lines: int) -> list[str]:
    max_lines = max(1, int(max_lines or 1))
    if not text:
        return []
    if max_lines == 1:
        return [text]

    target = max(1, round(len(text) / max_lines))
    lines: list[str] = []
    remaining = text
    while remaining and len(lines) < max_lines - 1:
        candidates = [m.start() for m in re.finditer(r"\s+", remaining)]
        if candidates:
            split_at = min(candidates, key=lambda idx: abs(idx - target))
            first = remaining[:split_at].strip()
            rest = remaining[split_at:].strip()
        else:
            split_at = min(max(1, target), max(1, len(remaining) - 1))
            first = remaining[:split_at].strip()
            rest = remaining[split_at:].strip()
        if not first or not rest:
            break
        lines.append(first)
        remaining = rest
        target = max(1, round(len(remaining) / (max_lines - len(lines))))
    if remaining:
        lines.append(remaining.strip())
    return [line for line in lines if line]


def _wrap_two_lines(text: str, aspect_ratio: str = "16:9") -> str:
    text = re.sub(r"\s+", " ", _ass_escape(text))
    if not text:
        return ""
    max_chars = 13 if aspect_ratio == "9:16" else 22
    if len(text) <= max_chars:
        return text

    max_lines = 3 if len(text) > max_chars * 2 else 2
    lines = _split_text_for_subtitle(text, max_lines)
    return "\\N".join(lines)


def _hex_to_ass_color(hex_color: str, alpha: int = 0) -> str:
    """Convert '#RRGGBB' (or 'RRGGBB') → ASS '&HAABBGGRR'.

    ASS colors are stored as ``&HAABBGGRR`` where alpha 00 = fully opaque and
    FF = fully transparent. ``alpha`` is an int 0..255.
    """
    h = (hex_color or "").lstrip("#").rjust(6, "0")[:6]
    try:
        r, g, b = h[0:2], h[2:4], h[4:6]
    except ValueError:
        r, g, b = "FF", "FF", "FF"
    a = max(0, min(255, int(alpha)))
    return f"&H{a:02X}{b}{g}{r}"


# ASS alignment uses numpad layout: 7 8 9 / 4 5 6 / 1 2 3
_POSITION_TO_ALIGNMENT = {
    "bottom": 2,   # bottom-center
    "bottom-left": 1,
    "bottom-right": 3,
    "center": 5,   # middle-center
    "middle": 5,
    "top": 8,      # top-center
    "top-left": 7,
    "top-right": 9,
}


def _play_resolution(aspect_ratio: str) -> tuple[int, int]:
    """PlayResX/Y that match the real output resolution — keeps fontsize
    pixels consistent with what the user sees on screen."""
    if aspect_ratio == "9:16":
        return 1080, 1920
    if aspect_ratio == "1:1":
        return 1080, 1080
    return 1920, 1080  # 16:9 default


def _inserts_intermission_after_cut(
    cut_index: int,
    total_cuts: int,
    *,
    first_intermission_after_cuts: int,
    intermission_every_cuts: int,
    intermission_duration: float,
) -> bool:
    if intermission_duration <= 0 or cut_index >= total_cuts:
        return False
    if first_intermission_after_cuts > 0 and cut_index == first_intermission_after_cuts:
        return True
    return (
        intermission_every_cuts > 0
        and cut_index != first_intermission_after_cuts
        and cut_index % intermission_every_cuts == 0
    )


def generate_ass(
    cuts: list[dict],
    style_config: dict,
    aspect_ratio: str = "16:9",
    *,
    first_intermission_after_cuts: int = 0,
    intermission_every_cuts: int = 0,
    intermission_duration: float = 0.0,
) -> str:
    """Build an ASS subtitle file from cuts and a style config.

    style_config keys (all optional, sensible defaults applied):
        font:           font family name, e.g. "Pretendard Bold"
        size:           font pixel size relative to PlayResY
        color:          primary text color, "#RRGGBB"
        outline_color:  outline (stroke) color, "#RRGGBB"
        position:       "bottom" | "center" | "top" (plus -left/-right variants)
        outline_width:  stroke thickness in px (default 3)
        shadow:         shadow distance in px (default 0)
        margin_v:       vertical margin from edge for bottom/top alignments (default 60)
        bold:           True/False (default True if font name contains "Bold", else False)
        bg_enabled:     True/False — 자막 뒤 배경 박스 사용 여부 (default False)
        bg_color:       background hex color, "#RRGGBB" (default "#000000")
        bg_opacity:     0.0~1.0 — 1.0 이 완전 불투명 (default 0.6)
    """
    style_config = normalize_subtitle_style(style_config)

    font = style_config.get("font", "Pretendard Bold")
    size = int(style_config.get("size", 48) or 48)
    color_hex = style_config.get("color", "#FFFFFF")
    outline_color_hex = style_config.get("outline_color", "#000000")
    position = (style_config.get("position") or "bottom").lower()
    outline_width = int(style_config.get("outline_width", 3) or 3)
    shadow = int(style_config.get("shadow", 0) or 0)
    margin_v = int(style_config.get("margin_v", 60) or 60)

    bg_enabled = bool(style_config.get("bg_enabled", False))
    bg_color_hex = style_config.get("bg_color", "#000000")
    try:
        bg_opacity = float(style_config.get("bg_opacity", 0.6))
    except (TypeError, ValueError):
        bg_opacity = 0.6
    bg_opacity = max(0.0, min(1.0, bg_opacity))
    # ASS 알파: 00=불투명, FF=투명. opacity 1.0 → alpha 0, opacity 0.0 → alpha 255.
    bg_alpha = int(round((1.0 - bg_opacity) * 255))

    # If the font name already includes "Bold", ASS can still use the Bold
    # flag — libass will pick the matching face. Default to bold-on because
    # burned-in subtitles read better that way.
    bold_default = 1 if "bold" in font.lower() else 1
    bold = 1 if style_config.get("bold", bold_default) else 0

    primary = _hex_to_ass_color(color_hex)
    outline = _hex_to_ass_color(outline_color_hex)
    secondary = "&H000000FF"   # unused (karaoke), red-opaque placeholder
    # BackColour 는 BorderStyle=3 일 때 박스 배경색으로 쓰이고,
    # BorderStyle=1 일 때는 그림자색으로만 쓰인다.
    if bg_enabled:
        back_color = _hex_to_ass_color(bg_color_hex, alpha=bg_alpha)
    else:
        back_color = "&H64000000"  # 기본: 반투명 검정 (그림자 플레이스홀더)

    # BorderStyle: 1 = outline only, 3 = opaque box (uses BackColour).
    border_style = 3 if bg_enabled else 1

    alignment = _POSITION_TO_ALIGNMENT.get(position, 2)

    play_w, play_h = _play_resolution(aspect_ratio)

    header = f"""[Script Info]
Title: LongTube Subtitle
ScriptType: v4.00+
PlayResX: {play_w}
PlayResY: {play_h}
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},{primary},{secondary},{outline},{back_color},{bold},0,0,0,100,100,0,0,{border_style},{outline_width},{shadow},{alignment},60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events: list[str] = []
    current_time = 0.0

    # v1.1.45: 각 컷은 CUT_VIDEO_DURATION 초 고정 창(window)을 차지한다.
    # - current_time 은 고정 간격(CUT_VIDEO_DURATION)으로 전진해 컷 경계 싱크를 보장.
    # - 문장들은 해당 창 **앞쪽** 에서 실제 음성 길이(actual_duration)에 맞춰 분포.
    #   음성이 창 길이보다 길면 창 길이로 잘린다 (길어봐야 창 안에서 잘림).
    #   음성이 짧으면 창의 나머지는 무음 + 자막 없음 상태로 남는다.
    for cut_index, cut in enumerate(cuts, start=1):
        cut_window = float(cut.get("cut_video_duration") or CUT_VIDEO_DURATION)
        speech_dur = float(cut.get("actual_duration") or cut.get("duration_estimate") or cut_window)
        if speech_dur <= 0:
            speech_dur = cut_window
        if speech_dur > cut_window:
            speech_dur = cut_window

        narration = strip_leading_tts_audio_tags(cut.get("narration", ""))
        sentences = split_sentences(narration)

        if sentences:
            sentence_dur = speech_dur / len(sentences)

            for i, sentence in enumerate(sentences):
                text = _wrap_two_lines(sentence, aspect_ratio)
                s_start = format_ass_time(current_time + i * sentence_dur)
                s_end = format_ass_time(current_time + (i + 1) * sentence_dur)
                events.append(
                    f"Dialogue: 0,{s_start},{s_end},Default,,0,0,0,,{text}"
                )

        current_time += cut_window
        if _inserts_intermission_after_cut(
            cut_index,
            len(cuts),
            first_intermission_after_cuts=first_intermission_after_cuts,
            intermission_every_cuts=intermission_every_cuts,
            intermission_duration=intermission_duration,
        ):
            current_time += float(intermission_duration)

    return header + "\n".join(events) + "\n"


def generate_srt(
    cuts: list[dict],
    *,
    start_offset: float = 0.0,
    first_intermission_after_cuts: int = 0,
    intermission_every_cuts: int = 0,
    intermission_duration: float = 0.0,
) -> str:
    """Build a timed SRT caption file from cuts.

    This mirrors ``generate_ass`` timing: each cut occupies the fixed
    CUT_VIDEO_DURATION window, and sentence captions are distributed across the
    spoken part of that window. The file is meant for YouTube caption upload,
    not burn-in rendering.
    """
    entries: list[str] = []
    current_time = max(0.0, float(start_offset or 0.0))
    index = 1

    for cut_index, cut in enumerate(cuts, start=1):
        cut_window = float(cut.get("cut_video_duration") or CUT_VIDEO_DURATION)
        speech_dur = float(cut.get("actual_duration") or cut.get("duration_estimate") or cut_window)
        if speech_dur <= 0:
            speech_dur = cut_window
        if speech_dur > cut_window:
            speech_dur = cut_window

        narration = strip_leading_tts_audio_tags(cut.get("narration", ""))
        sentences = split_sentences(narration)
        if sentences:
            sentence_dur = speech_dur / len(sentences)
            for i, sentence in enumerate(sentences):
                text = _srt_escape(sentence)
                if not text:
                    continue
                start = current_time + i * sentence_dur
                end = current_time + (i + 1) * sentence_dur
                entries.append(
                    f"{index}\n{format_srt_time(start)} --> {format_srt_time(end)}\n{text}\n"
                )
                index += 1

        current_time += cut_window
        if _inserts_intermission_after_cut(
            cut_index,
            len(cuts),
            first_intermission_after_cuts=first_intermission_after_cuts,
            intermission_every_cuts=intermission_every_cuts,
            intermission_duration=intermission_duration,
        ):
            current_time += float(intermission_duration)

    return "\n".join(entries)


_VARIETY_KEYWORD_RE = re.compile(r"\*\*(.+?)\*\*")
VARIETY_CAPTION_SOURCE_KEYS = (
    "highlight_caption",
    "한국식 예능 자막 (핵심 포인트)",
    "한국식 예능 자막 (주요 장면용)",
    "한국식 예능 자막 (선택적 하이라이트)",
)


def explicit_variety_highlight_caption(cut: dict) -> str:
    """Return only the caption explicitly authored in the source script."""
    for key in VARIETY_CAPTION_SOURCE_KEYS:
        value = str(cut.get(key) or "").strip()
        if value and value not in {"-", "—"}:
            return value
    return ""


def _variety_inline_color(hex_color: str) -> str:
    """Return a six-digit ASS override colour with a terminating ampersand."""
    raw = str(hex_color or "").lstrip("#").rjust(6, "0")[:6]
    return f"&H{raw[4:6]}{raw[2:4]}{raw[0:2]}&"


def _variety_safe_text(value: str) -> str:
    return (
        re.sub(r"\s+", " ", str(value or "").replace("\r", " ").replace("\n", " "))
        .replace("\\", "／")
        .replace("{", "（")
        .replace("}", "）")
        .strip()
    )


def _variety_caption_and_keyword(cut: dict) -> tuple[str, str]:
    """Extract a short panel caption and optional explicitly marked keyword.

    Editors can mark the important phrase as ``**keyword**`` inside the existing
    ``highlight_caption`` field.  ``highlight_keyword(s)`` is also accepted for
    prepared-script producers, without changing the current API contract.
    """
    source = explicit_variety_highlight_caption(cut)
    if not source:
        return "", ""
    marker = _VARIETY_KEYWORD_RE.search(source)
    marked_keyword = marker.group(1) if marker else ""
    source = _VARIETY_KEYWORD_RE.sub(lambda match: match.group(1), source)
    clean_source = _variety_safe_text(source).rstrip(" ,，")
    text = clean_source

    candidates: list[str] = []
    if marked_keyword:
        candidates.append(marked_keyword)
    raw_keywords = cut.get("highlight_keywords")
    if isinstance(raw_keywords, (list, tuple)):
        candidates.extend(str(item or "") for item in raw_keywords)
    elif raw_keywords:
        candidates.append(str(raw_keywords))
    if cut.get("highlight_keyword"):
        candidates.append(str(cut.get("highlight_keyword")))
    keyword = next(
        (
            clean
            for clean in (_variety_safe_text(item) for item in candidates)
            if clean and clean in text
        ),
        "",
    )
    return text, keyword


def _variety_keyword_text(text: str, keyword: str, panel: dict) -> str:
    if not keyword or keyword not in text:
        return text
    index = text.find(keyword)
    accent = _variety_inline_color(str(panel["keyword_color"]))
    base = _variety_inline_color(str(panel["color"]))
    before = text[:index]
    after = text[index + len(keyword):]
    return (
        before
        + rf"{{\1c{accent}}}"
        + keyword
        + rf"{{\1c{base}}}"
        + after
    )


def _variety_motion_tags(panel_id: str, panel: dict, x: int, y: int) -> str:
    """Match the static Shorts hero title placement for every emotion tag."""
    alignment = int(panel["alignment"])
    return rf"\an{alignment}\pos({x},{y})\fscx100\fscy100"


_VARIETY_DECOR_DRAWINGS = {
    "neutral": "m -42 -72 l 670 -72 l 715 -42 l 670 -12 l -42 -12 m -62 -88 l -42 -88 l -42 4 l -62 4",
    "epic": "m -510 -48 l -392 -96 l -422 -38 l -302 -68 l -340 -14 l 340 -14 l 302 -68 l 422 -38 l 392 -96 l 510 -48 l 428 2 l -428 2",
    "anger": "m -520 -24 l -650 -70 l -548 8 m -470 -106 l -570 -190 l -438 -132 m 520 -24 l 650 -70 l 548 8 m 470 -106 l 570 -190 l 438 -132 m -90 -118 l -22 -236 l 18 -110 m 92 116 l 26 232 l -20 112",
    "shout": "m -690 -92 l -258 -72 l -304 -42 l -730 -58 m -650 -24 l -220 -12 l -276 18 l -704 10 m -612 46 l -176 60 l -252 88 l -674 76",
    "whisper": "m -34 -74 l 650 -74 l 682 -48 l 682 32 l 648 58 l 138 58 l 78 116 l 92 58 l -34 58 l -66 32 l -66 -48",
    "tension": "m 48 -126 b 88 -72 92 -26 52 2 b 12 -26 16 -72 48 -126 m 112 -82 b 142 -42 144 -6 114 14 b 84 -6 86 -42 112 -82 m 178 -50 b 202 -20 204 8 180 24 b 156 8 158 -20 178 -50",
    "sad": "m -56 -116 b -18 -66 -16 -18 -54 8 b -92 -18 -90 -66 -56 -116 m 34 -82 b 64 -42 66 -4 36 16 b 6 -4 8 -42 34 -82 m -80 56 b 40 82 180 42 300 66 b 420 90 550 50 674 70",
    "shock": "m 0 -142 l 62 -74 l 154 -112 l 136 -24 l 250 0 l 146 46 l 202 126 l 96 88 l 34 180 l -20 88 l -122 202 l -62 118 l -154 154 l -136 132 l -250 142 l -146 96 l -202 112 l -96 74 l -34 142 l 20 74 l 122 112 l 62 24",
    "sly": "m -42 -72 l 610 -72 l 650 -32 l 628 48 l 520 68 l 558 124 l 468 66 l -42 66 l -78 24 l -74 -42 m 686 -8 b 742 -24 748 34 704 48 b 674 58 684 88 720 92",
    "joy": "m -360 -22 b -414 -88 -516 -30 -478 52 b -452 104 -394 132 -360 170 b -326 132 -268 104 -242 52 b -204 -30 -306 -88 -360 -22 m 360 -22 b 306 -88 204 -30 242 52 b 268 104 326 132 360 170 b 394 132 452 104 478 52 b 516 -30 414 -88 360 -22",
}


def _variety_decoration_event(
    panel_id: str,
    panel: dict,
    start: str,
    end: str,
    x: int,
    y: int,
) -> str:
    drawing = _VARIETY_DECOR_DRAWINGS[panel_id]
    alpha = {
        "neutral": 92, "epic": 68, "anger": 35, "shout": 18, "whisper": 82,
        "tension": 44, "sad": 70, "shock": 22, "sly": 48, "joy": 34,
    }[panel_id]
    decor_motion = {
        "neutral": "\\fad(120,220)\\fscx88\\fscy100\\t(0,180,\\fscx100)",
        "epic": "\\fad(60,260)\\fscx55\\fscy65\\t(0,240,\\fscx100\\fscy100)",
        "anger": "\\fad(20,150)\\frz-7\\fscx40\\fscy40\\t(0,105,\\fscx100\\fscy100\\frz0)",
        "shout": "\\fad(15,110)\\fscx175\\fscy100\\t(0,130,\\fscx100\\fscy100)",
        "whisper": "\\fade(255,35,35,0,280,980,1400)\\fscx94\\fscy90\\t(0,300,\\fscx100\\fscy100)",
        "tension": "\\fad(40,130)\\fscx80\\fscy70\\t(0,95,\\fscx110\\fscy115)\\t(95,175,\\fscx100\\fscy100)",
        "sad": "\\fad(260,330)\\fscx94\\fscy72\\t(0,420,\\fscx100\\fscy108)",
        "shock": "\\fad(12,120)\\fscx20\\fscy20\\frz18\\t(0,105,\\fscx118\\fscy118\\frz-4)\\t(105,190,\\fscx100\\fscy100\\frz0)",
        "sly": "\\fad(80,190)\\frz12\\fscx72\\fscy110\\t(0,220,\\fscx100\\fscy100\\frz-7)",
        "joy": "\\fad(35,230)\\fscx50\\fscy50\\frz-12\\t(0,130,\\fscx118\\fscy118\\frz6)\\t(130,230,\\fscx100\\fscy100\\frz0)",
    }[panel_id]
    color = _variety_inline_color(str(panel["accent_color"]))
    return (
        f"Dialogue: 1,{start},{end},VarietyDecor,{panel_id},0,0,0,,"
        rf"{{\an5\pos({x},{y})\p1\bord0\shad0\blur0.6\1c{color}\1a&H{alpha:02X}&{decor_motion}}}"
        f"{drawing}"
    )


def generate_variety_highlight_ass(
    cuts: list[dict],
    *,
    aspect_ratio: str = "16:9",
    first_intermission_after_cuts: int = 0,
    intermission_every_cuts: int = 0,
    intermission_duration: float = 0.0,
    panel_mode: str = "emotion_auto",
    fixed_panel: str = "neutral",
) -> str:
    """Render only source-authored Korean-variety captions; narration stays in SRT."""
    play_w, play_h = _play_resolution(aspect_ratio)
    style_lines: list[str] = []
    outline_style_lines: list[str] = []
    for panel_id, source_panel in VARIETY_HIGHLIGHT_PANELS.items():
        panel = _variety_render_panel(panel_id, source_panel)
        size = _variety_render_font_size(source_panel, aspect_ratio)
        common_tail = (
            f"{int(panel['bold'])},{int(panel['italic'])},0,0,"
            f"{int(panel['scale_x'])},{int(panel['scale_y'])},{int(panel['spacing'])},{int(panel['angle'])}"
        )
        margins = (
            f"{int(panel['alignment'])},{int(panel['margin_l'])},"
            f"{int(panel['margin_r'])},{int(panel['margin_v'])},1"
        )
        style_lines.append(
            "Style: "
            f"Variety_{panel_id},{panel['font']},{size},"
            f"{_hex_to_ass_color(str(panel['color']))},&H000000FF,"
            f"{_hex_to_ass_color(str(panel['outline_color']))},"
            f"{_hex_to_ass_color(str(panel['back_color']), alpha=31)},"
            f"{common_tail},1,{int(panel['outline'])},{int(panel['shadow'])},{margins}"
        )
        outline_style_lines.append(
            "Style: "
            f"Outline_{panel_id},{panel['font']},{size},"
            f"{_hex_to_ass_color(str(panel['color']))},&H000000FF,"
            f"{_hex_to_ass_color(str(panel['outer_outline_color']))},"
            f"{_hex_to_ass_color(str(panel['back_color']), alpha=31)},"
            f"{common_tail},1,{int(panel['outer_outline'])},0,{margins}"
        )
    header = f"""[Script Info]
Title: LongTube Korean Variety Highlights
ScriptType: v4.00+
PlayResX: {play_w}
PlayResY: {play_h}
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{chr(10).join(style_lines)}
{chr(10).join(outline_style_lines)}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: list[str] = []
    current_time = 0.0
    for cut_index, cut in enumerate(cuts, start=1):
        window = float(cut.get("cut_video_duration") or CUT_VIDEO_DURATION)
        explicit = explicit_variety_highlight_caption(cut)
        tts_tags = [
            str(tag or "").strip().lower()
            for tag in (cut.get("tts_tags") or [])
            if str(tag or "").strip()
        ]
        text, keyword = _variety_caption_and_keyword(cut)
        if explicit and text and window > 1.0:
            panel_id = resolve_variety_highlight_panel(
                tts_tags,
                panel_mode=panel_mode,
                fixed_panel=fixed_panel,
            )
            panel = _variety_render_panel(panel_id, VARIETY_HIGHLIGHT_PANELS[panel_id])
            x = round(play_w * float(panel["x_ratio"]))
            y = round(play_h * float(panel["y_ratio"]))
            # Keep the panel inside its source cut: 0.5 seconds of lead-in
            # and tail room, with no fixed display-duration cap.
            start = format_ass_time(current_time + 0.5)
            end = format_ass_time(current_time + window - 0.5)
            motion = _variety_motion_tags(panel_id, panel, x, y)
            outer_text = text
            main_text = _variety_keyword_text(text, keyword, panel)
            events.append(
                f"Dialogue: 3,{start},{end},Outline_{panel_id},{panel_id},0,0,0,,"
                f"{{{motion}}}{outer_text}"
            )
            events.append(
                f"Dialogue: 5,{start},{end},Variety_{panel_id},{panel_id},0,0,0,,"
                f"{{{motion}}}{main_text}"
            )
        current_time += window
        if _inserts_intermission_after_cut(
            cut_index,
            len(cuts),
            first_intermission_after_cuts=first_intermission_after_cuts,
            intermission_every_cuts=intermission_every_cuts,
            intermission_duration=intermission_duration,
        ):
            current_time += float(intermission_duration)
    return header + "\n".join(events) + "\n"


def generate_single_cut_ass(
    narration: str,
    duration: float,
    style_config: dict,
    aspect_ratio: str = "16:9",
    start_offset: float = 0.0,
    display_duration: float | None = None,
) -> str:
    """단일 컷용 ASS — 컷 전체 길이에 걸쳐 자막을 표시한다.

    v1.1.55: 컷별 영상 생성 직후 자막을 바로 입히기 위한 헬퍼. 머지 전에
    각 mp4 가 자기 대사를 0~duration 구간에 정확히 표시하므로 이후 concat 에서
    `ensure_min_duration` 등으로 클립 길이가 늘어나도 싱크가 깨지지 않는다.

    `generate_ass` 와 헤더/스타일 규칙은 동일. 이벤트만 0..duration 한 컷에
    대해 문장 단위로 균등 분배.
    """
    # ── 헤더/스타일은 generate_ass 와 동일 로직을 재사용 ──
    style_config = normalize_subtitle_style(style_config)

    font = style_config.get("font", "Pretendard Bold")
    size = int(style_config.get("size", 48) or 48)
    color_hex = style_config.get("color", "#FFFFFF")
    outline_color_hex = style_config.get("outline_color", "#000000")
    position = (style_config.get("position") or "bottom").lower()
    outline_width = int(style_config.get("outline_width", 3) or 3)
    shadow = int(style_config.get("shadow", 0) or 0)
    margin_v = int(style_config.get("margin_v", 60) or 60)

    bg_enabled = bool(style_config.get("bg_enabled", False))
    bg_color_hex = style_config.get("bg_color", "#000000")
    try:
        bg_opacity = float(style_config.get("bg_opacity", 0.6))
    except (TypeError, ValueError):
        bg_opacity = 0.6
    bg_opacity = max(0.0, min(1.0, bg_opacity))
    bg_alpha = int(round((1.0 - bg_opacity) * 255))

    bold_default = 1 if "bold" in font.lower() else 1
    bold = 1 if style_config.get("bold", bold_default) else 0

    primary = _hex_to_ass_color(color_hex)
    outline = _hex_to_ass_color(outline_color_hex)
    secondary = "&H000000FF"
    if bg_enabled:
        back_color = _hex_to_ass_color(bg_color_hex, alpha=bg_alpha)
    else:
        back_color = "&H64000000"
    border_style = 3 if bg_enabled else 1
    alignment = _POSITION_TO_ALIGNMENT.get(position, 2)
    play_w, play_h = _play_resolution(aspect_ratio)

    header = f"""[Script Info]
Title: LongTube Cut Subtitle
ScriptType: v4.00+
PlayResX: {play_w}
PlayResY: {play_h}
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},{primary},{secondary},{outline},{back_color},{bold},0,0,0,100,100,0,0,{border_style},{outline_width},{shadow},{alignment},60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    dur = float(duration or 0)
    if dur <= 0:
        # 길이를 모르면 자막 없음 — 빈 트랙 반환.
        return header

    sentences = split_sentences(narration or "")
    if not sentences:
        return header

    try:
        display_dur = float(display_duration) if display_duration is not None else dur
    except (TypeError, ValueError):
        display_dur = dur
    if display_dur <= 0:
        display_dur = dur

    start_sec = 0.0
    end_sec = display_dur
    if end_sec <= start_sec:
        return header

    sentence_dur = (end_sec - start_sec) / len(sentences)
    events: list[str] = []
    for i, sentence in enumerate(sentences):
        text = _wrap_two_lines(sentence, aspect_ratio)
        s_start = format_ass_time(start_sec + i * sentence_dur)
        s_end = format_ass_time(start_sec + (i + 1) * sentence_dur)
        events.append(
            f"Dialogue: 0,{s_start},{s_end},Default,,0,0,0,,{text}"
        )
    return header + "\n".join(events) + "\n"


def _cut_subtitle_marker_payload(
    narration: str,
    aspect_ratio: str,
    style_config: dict | None,
    duration: float,
    start_offset: float = 0.0,
    display_duration: float | None = None,
) -> dict:
    return {
        "version": CUT_SUBTITLE_MARKER_VERSION,
        "narration": re.sub(r"\s+", " ", (narration or "")).strip(),
        "aspect_ratio": aspect_ratio or "16:9",
        "style": normalize_subtitle_style(style_config or {}),
        "duration": round(float(duration or CUT_VIDEO_DURATION), 3),
        "display_duration": round(float(display_duration or duration or CUT_VIDEO_DURATION), 3),
        "start": CUT_SUBTITLE_START_SEC,
        "end": CUT_SUBTITLE_END_SEC,
        "start_offset": round(float(start_offset or 0.0), 3),
    }


def _cut_subtitle_digest(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


async def burn_cut_subtitle_file(
    cut_video_path: str,
    narration: str,
    aspect_ratio: str = "16:9",
    style_config: dict | None = None,
    duration: float = CUT_VIDEO_DURATION,
    start_offset: float = 0.0,
) -> bool:
    """Burn one cut subtitle directly into one mp4."""
    narration = (narration or "").strip()
    if not narration:
        return False

    cut_p = Path(cut_video_path)
    if not cut_p.exists() or cut_p.stat().st_size <= 0:
        return False

    dur = float(duration or CUT_VIDEO_DURATION)
    if dur <= 0:
        dur = float(CUT_VIDEO_DURATION)

    display_dur = 0.0
    try:
        from app.services.video.ffmpeg_service import FFmpegService
        display_dur = float(await FFmpegService.probe_duration(str(cut_p)) or 0.0)
    except Exception:
        display_dur = 0.0
    if display_dur <= 0:
        try:
            offset = max(0.0, float(start_offset or 0.0))
        except (TypeError, ValueError):
            offset = 0.0
        display_dur = offset + dur

    payload = _cut_subtitle_marker_payload(
        narration,
        aspect_ratio,
        style_config,
        dur,
        start_offset,
        display_duration=display_dur,
    )
    digest = _cut_subtitle_digest(payload)
    marker_p = cut_p.with_suffix(".subtitle.json")
    try:
        existing = json.loads(marker_p.read_text(encoding="utf-8"))
        marker_is_current = marker_p.stat().st_mtime >= (cut_p.stat().st_mtime - 0.5)
        if existing.get("digest") == digest and marker_is_current:
            return True
        # Existing cut videos are already burned-in subtitle outputs. Re-burning a
        # different style over them creates duplicated captions; clean source cuts
        # must be regenerated by the video step before a style change can apply.
        if existing.get("digest") and marker_is_current:
            return True
    except Exception:
        pass

    ass_text = generate_single_cut_ass(
        narration,
        dur,
        style_config or {},
        aspect_ratio,
        start_offset=start_offset,
        display_duration=display_dur,
    )
    ass_p = cut_p.with_suffix(".cut.ass")
    tmp_out = cut_p.with_suffix(".sub.mp4")
    ass_p.write_text(ass_text, encoding="utf-8")
    try:
        await FFmpegService.burn_subtitles(str(cut_p), str(ass_p), str(tmp_out))
        shutil.move(str(tmp_out), str(cut_p))
        marker_p.write_text(
            json.dumps({"digest": digest, **payload}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True
    finally:
        try:
            ass_p.unlink()
        except Exception:
            pass
        try:
            if tmp_out.exists():
                tmp_out.unlink()
        except Exception:
            pass


async def burn_cut_variety_highlight_file(
    cut_video_path: str,
    cut_data: dict,
    *,
    aspect_ratio: str = "16:9",
    duration: float = CUT_VIDEO_DURATION,
    panel_mode: str = "emotion_auto",
    fixed_panel: str = "neutral",
) -> bool:
    """Burn only an explicitly authored Korean-variety caption into one cut."""
    caption = explicit_variety_highlight_caption(cut_data or {})
    if not caption:
        return False

    cut_p = Path(cut_video_path)
    if not cut_p.exists() or cut_p.stat().st_size <= 0:
        return False

    display_dur = float(duration or CUT_VIDEO_DURATION)
    try:
        from app.services.video.ffmpeg_service import FFmpegService
        probed = float(await FFmpegService.probe_duration(str(cut_p)) or 0.0)
        if probed > 0.0:
            display_dur = probed
    except Exception:
        pass
    if display_dur <= 1.0:
        return False

    event_cut = dict(cut_data or {})
    event_cut["highlight_caption"] = caption
    event_cut["cut_video_duration"] = display_dur
    if not event_cut.get("tts_tags"):
        try:
            from app.services.tts.voice_cast import tts_tags_for_cut
            event_cut["tts_tags"] = list(tts_tags_for_cut(event_cut))
        except Exception:
            event_cut["tts_tags"] = []

    payload = {
        "version": CUT_SUBTITLE_MARKER_VERSION,
        "mode": "korean_variety_only",
        "caption": caption,
        "tts_tags": list(event_cut.get("tts_tags") or []),
        "aspect_ratio": aspect_ratio or "16:9",
        "duration": round(display_dur, 3),
        "panel_mode": panel_mode or "emotion_auto",
        "fixed_panel": fixed_panel or "neutral",
        "font_scale": VARIETY_HIGHLIGHT_FONT_SCALE,
    }
    digest = _cut_subtitle_digest(payload)
    marker_p = cut_p.with_suffix(".subtitle.json")
    try:
        existing = json.loads(marker_p.read_text(encoding="utf-8"))
        marker_is_current = marker_p.stat().st_mtime >= (cut_p.stat().st_mtime - 0.5)
        if existing.get("digest") == digest and marker_is_current:
            return True
    except Exception:
        pass

    ass_text = generate_variety_highlight_ass(
        [event_cut],
        aspect_ratio=aspect_ratio,
        panel_mode=panel_mode,
        fixed_panel=fixed_panel,
    )
    ass_p = cut_p.with_suffix(".variety.ass")
    tmp_out = cut_p.with_suffix(".variety.mp4")
    ass_p.write_text(ass_text, encoding="utf-8")
    try:
        await FFmpegService.burn_subtitles(str(cut_p), str(ass_p), str(tmp_out))
        shutil.move(str(tmp_out), str(cut_p))
        marker_p.write_text(
            json.dumps({"digest": digest, **payload}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True
    finally:
        try:
            ass_p.unlink()
        except Exception:
            pass
        try:
            if tmp_out.exists():
                tmp_out.unlink()
        except Exception:
            pass
