"""Subtitle generation service (ASS format)"""
import re

from app.config import CUT_VIDEO_DURATION


def format_ass_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def split_sentences(text: str) -> list[str]:
    """한국어 문장 분리"""
    parts = re.split(r"(?<=[.!?。])\s+", text.strip())
    return [p for p in parts if p.strip()]


def _ass_escape(text: str) -> str:
    return (text or "").replace("\r", " ").replace("\n", " ").strip()


def _wrap_two_lines(text: str, aspect_ratio: str = "16:9") -> str:
    text = re.sub(r"\s+", " ", _ass_escape(text))
    if not text:
        return ""
    max_chars = 24 if aspect_ratio == "9:16" else 42
    if len(text) <= max_chars:
        return text

    target = len(text) // 2
    candidates = [m.start() for m in re.finditer(r"\s+", text)]
    if candidates:
        split_at = min(candidates, key=lambda idx: abs(idx - target))
        first = text[:split_at].strip()
        second = text[split_at:].strip()
    else:
        split_at = min(max_chars, max(1, target))
        first = text[:split_at].strip()
        second = text[split_at:].strip()
    return first if not second else f"{first}\\N{second}"


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


def generate_ass(
    cuts: list[dict],
    style_config: dict,
    aspect_ratio: str = "16:9",
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
    for cut in cuts:
        cut_window = float(CUT_VIDEO_DURATION)
        speech_dur = float(cut.get("actual_duration") or cut.get("duration_estimate") or cut_window)
        if speech_dur <= 0:
            speech_dur = cut_window
        if speech_dur > cut_window:
            speech_dur = cut_window

        narration = cut.get("narration", "")
        sentences = split_sentences(narration)

        if not sentences:
            current_time += cut_window
            continue

        sentence_dur = speech_dur / len(sentences)

        for i, sentence in enumerate(sentences):
            text = _wrap_two_lines(sentence, aspect_ratio)
            s_start = format_ass_time(current_time + i * sentence_dur)
            s_end = format_ass_time(current_time + (i + 1) * sentence_dur)
            events.append(
                f"Dialogue: 0,{s_start},{s_end},Default,,0,0,0,,{text}"
            )

        current_time += cut_window

    return header + "\n".join(events) + "\n"


def generate_single_cut_ass(
    narration: str,
    duration: float,
    style_config: dict,
    aspect_ratio: str = "16:9",
) -> str:
    """단일 컷용 ASS — 시작 0초, 끝 = `duration` (= 실제 오디오 길이).

    v1.1.55: 컷별 영상 생성 직후 자막을 바로 입히기 위한 헬퍼. 머지 전에
    각 mp4 가 자기 대사를 0~duration 구간에 정확히 표시하므로 이후 concat 에서
    `ensure_min_duration` 등으로 클립 길이가 늘어나도 싱크가 깨지지 않는다.

    `generate_ass` 와 헤더/스타일 규칙은 동일. 이벤트만 0..duration 한 컷에
    대해 문장 단위로 균등 분배.
    """
    # ── 헤더/스타일은 generate_ass 와 동일 로직을 재사용 ──
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

    sentence_dur = dur / len(sentences)
    events: list[str] = []
    for i, sentence in enumerate(sentences):
        text = _wrap_two_lines(sentence, aspect_ratio)
        s_start = format_ass_time(i * sentence_dur)
        s_end = format_ass_time((i + 1) * sentence_dur)
        events.append(
            f"Dialogue: 0,{s_start},{s_end},Default,,0,0,0,,{text}"
        )
    return header + "\n".join(events) + "\n"
