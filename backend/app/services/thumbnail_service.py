"""YouTube 썸네일 생성 서비스.

두 가지 모드를 제공합니다:

1. **AI 이미지 기반 (generate_ai_thumbnail)** — 프로젝트의 image 모델
   (Nano Banana / DALL-E / Flux 등) 을 재사용해 1280x720 배경을 새로 생성.
   선택적으로 그 위에 Pillow 로 제목 텍스트 오버레이.

2. **Pillow 텍스트 오버레이 (generate_thumbnail)** — 기존 결정론적 경로.
   첫 번째 컷 이미지를 베이스로 크롭 + 하단 밴드 + 제목 텍스트 렌더.
   AI 썸네일이 실패하거나 사용자가 선택한 경우 폴백으로도 사용됨.

폰트 탐색 우선순위:
- Windows: Malgun Gothic (한글 기본), Arial Bold
- Linux: DejaVu Sans Bold / Nanum Gothic Bold
- 실패 시 ImageFont.load_default() (영문만 렌더 됨)
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont, ImageFilter

from app.config import DATA_DIR

# YouTube 권장 썸네일 해상도
THUMB_W = 1280
THUMB_H = 720

# 폰트 탐색 후보 (OS 별)
FONT_CANDIDATES = [
    # Windows
    r"C:\Windows\Fonts\malgunbd.ttf",       # Malgun Gothic Bold (한글)
    r"C:\Windows\Fonts\malgun.ttf",         # Malgun Gothic Regular
    r"C:\Windows\Fonts\arialbd.ttf",        # Arial Bold
    r"C:\Windows\Fonts\arial.ttf",
    # Linux
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    # macOS
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/Library/Fonts/Arial Bold.ttf",
]


class ThumbnailError(RuntimeError):
    pass


def _find_font(size: int) -> ImageFont.ImageFont:
    """가능한 한 한글 지원 + 볼드 폰트를 찾아 반환. 실패 시 default."""
    for path in FONT_CANDIDATES:
        try:
            if os.path.exists(path):
                return ImageFont.truetype(path, size=size)
        except Exception:
            continue
    # 최후 폴백
    return ImageFont.load_default()


def _cover_resize(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """이미지를 target 해상도에 맞춰 cover(크롭) 리사이즈."""
    src_w, src_h = img.size
    src_ratio = src_w / src_h
    tgt_ratio = target_w / target_h

    if src_ratio > tgt_ratio:
        # 소스가 더 가로로 김 → 높이 맞추고 좌우 크롭
        new_h = target_h
        new_w = int(round(src_ratio * new_h))
    else:
        new_w = target_w
        new_h = int(round(new_w / src_ratio))

    resized = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def _wrap_text(text: str, font: ImageFont.ImageFont, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    """주어진 폰트 크기에서 한 줄 최대 너비를 넘지 않도록 단어/문자 단위로 줄바꿈.

    한글은 띄어쓰기가 적으므로 단어 단위로 우선 시도하고,
    단어 하나가 너비를 넘으면 문자 단위로 폴백.
    """
    words = text.split()
    if not words:
        return []

    lines: list[str] = []
    current = ""

    def width_of(s: str) -> int:
        try:
            bbox = draw.textbbox((0, 0), s, font=font)
            return bbox[2] - bbox[0]
        except Exception:
            return len(s) * font.size // 2  # 폴백 근사

    for word in words:
        candidate = (current + " " + word).strip()
        if width_of(candidate) <= max_width:
            current = candidate
            continue
        # 줄을 넘김 → 현재 줄 flush
        if current:
            lines.append(current)
            current = ""
        # 단어 하나가 혼자서도 너비 초과? → 문자 단위 쪼개기
        if width_of(word) > max_width:
            chunk = ""
            for ch in word:
                if width_of(chunk + ch) <= max_width:
                    chunk += ch
                else:
                    if chunk:
                        lines.append(chunk)
                    chunk = ch
            if chunk:
                current = chunk
        else:
            current = word

    if current:
        lines.append(current)

    return lines


# ─── 레퍼런스 스타일 (EP. 배지 + 컬러 텍스트 박스) 팔레트 ───
# 좌측 상단 EP 배지, 하단 2줄 텍스트(각각 배경 박스 + 두꺼운 검정 테두리).
# 밝은 색상 박스 + 검정 스트로크 + 흰/검정 텍스트로 모바일 해상도에서도 확 튐.
BADGE_FILL = (255, 222, 23)       # 노랑
BADGE_STROKE = (0, 0, 0)
HOOK_BG_1 = (255, 222, 23)        # 노랑 (상단 라인)
HOOK_BG_2 = (182, 255, 0)         # 라임 (하단 라인)
TEXT_STROKE = (0, 0, 0)
TEXT_FILL_DARK = (20, 20, 20)
FRAME_COLOR = (0, 220, 120)       # 외곽 프레임(초록)


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        sz = getattr(font, "size", 60)
        return len(text) * sz // 2, sz


def _fit_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_w: int,
    max_h: int,
    candidates: tuple[int, ...],
) -> ImageFont.ImageFont:
    """주어진 너비/높이 안에 들어가는 가장 큰 폰트를 후보 중에서 선택."""
    for size in candidates:
        font = _find_font(size)
        w, h = _text_size(draw, text, font)
        if w <= max_w and h <= max_h:
            return font
    return _find_font(candidates[-1])


def _draw_rounded_box(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    fill,
    outline=(0, 0, 0),
    outline_width: int = 6,
    radius: int = 18,
) -> None:
    try:
        draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=outline_width)
    except AttributeError:
        # 아주 구버전 Pillow 대비
        draw.rectangle(xy, fill=fill, outline=outline, width=outline_width)


def _draw_stroked_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill,
    stroke_fill=TEXT_STROKE,
    stroke_width: int = 6,
) -> None:
    try:
        draw.text(xy, text, font=font, fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill)
    except TypeError:
        draw.text(xy, text, font=font, fill=fill)


def generate_thumbnail(
    project_id: str,
    title: str,
    base_image_path: Optional[str] = None,
    output_path: Optional[str] = None,
    episode_label: Optional[str] = None,
    subtitle: Optional[str] = None,
) -> str:
    """YouTube 썸네일 생성 — v1.1.27 그림텍스트 스타일.

    레이아웃:
    - 배경: base_image_path (cover-crop) 또는 다크 폴백
    - 좌측 상단: `episode_label` 이 있으면 "EP. 1" 같은 노랑 배지 (작게 유지)
    - 하단: 큰 흰색 글자 + 두꺼운 검정 아웃라인 + 드롭섀도 (박스 없음).
      MrBeast / Veritasium 스타일의 그림텍스트. 박스로 이미지를 가리지 않고,
      아웃라인 + 섀도로 가독성 확보.
    - 마지막 줄은 노랑 강조 색으로 포인트 주기 (여러 줄일 때).

    Args:
        project_id: 프로젝트 ID.
        title: 메인 후크 텍스트 (썸네일의 가장 큰 글자).
        base_image_path: 배경 이미지 경로.
        output_path: 저장 경로.
        episode_label: "EP. 1" 같은 에피소드 배지 텍스트. None 이면 배지 생략.
        subtitle: 메인 후크 위에 들어갈 보조 라인. None 이면 생략.

    Returns:
        저장된 파일의 절대 경로 (str).
    """
    if not title or not title.strip():
        raise ThumbnailError("제목이 비어있습니다.")

    if output_path is None:
        out_dir = Path(DATA_DIR) / project_id / "output"
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(out_dir / "thumbnail.png")
    else:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # ── 배경 ──
    if base_image_path and os.path.exists(base_image_path):
        try:
            base = Image.open(base_image_path).convert("RGB")
            base = _cover_resize(base, THUMB_W, THUMB_H)
        except Exception as e:
            raise ThumbnailError(f"베이스 이미지 로드 실패: {e}") from e
    else:
        base = Image.new("RGB", (THUMB_W, THUMB_H), (20, 20, 30))

    # 전체적으로 살짝 어둡게 (그림텍스트 가독성)
    darken = Image.new("RGB", base.size, (0, 0, 0))
    base = Image.blend(base, darken, 0.12)

    # 하단 1/3 강한 radial-ish darken — 그림텍스트가 놓일 영역
    bottom_overlay = Image.new("RGBA", (THUMB_W, THUMB_H), (0, 0, 0, 0))
    bo_draw = ImageDraw.Draw(bottom_overlay)
    for i in range(20):
        alpha = int(120 * (i / 20))
        y = int(THUMB_H * (0.55 + 0.45 * i / 20))
        bo_draw.rectangle((0, y, THUMB_W, THUMB_H), fill=(0, 0, 0, alpha))
    composed = base.convert("RGBA")
    composed = Image.alpha_composite(composed, bottom_overlay)
    draw = ImageDraw.Draw(composed)

    pad_x = 60  # 좌우 안전 여백
    text = title.strip()
    sub = (subtitle or "").strip() or None
    max_text_w = THUMB_W - 2 * pad_x

    # ── 메인 후크: 큰 그림텍스트 ──
    # 박스 없이 크게 — 박스가 먹던 공간이 없으므로 폰트를 확 키움.
    # 후보 사이즈를 높은 것부터 내려가며 2줄 이내, 높이 35% 이내에 맞추기.
    candidates = (160, 140, 124, 108, 96, 86, 76, 68, 60)
    max_title_block_h = int(THUMB_H * 0.38)

    def pick_title_font() -> tuple[ImageFont.ImageFont, list[str]]:
        for size in candidates:
            f = _find_font(size)
            lines = _wrap_text(text, f, max_text_w, draw)
            if not lines:
                continue
            if len(lines) > 3:
                continue
            lh = _text_size(draw, "가Ag", f)[1]
            total_h = len(lines) * lh + (len(lines) - 1) * int(lh * 0.15)
            if total_h <= max_title_block_h:
                return f, lines
        # 폴백: 가장 작은 폰트
        f = _find_font(candidates[-1])
        return f, _wrap_text(text, f, max_text_w, draw) or [text]

    title_font, title_lines = pick_title_font()
    title_size = getattr(title_font, "size", 96)
    # 아웃라인 두께는 폰트 크기에 비례 (굵은 카툰풍)
    title_stroke_w = max(6, min(14, title_size // 9))

    # subtitle — 있을 때만. title 보다 작게.
    sub_font = None
    sub_stroke_w = 0
    if sub:
        sub_size = max(44, int(title_size * 0.55))
        sub_font = _find_font(sub_size)
        # 너무 길면 쪼개지 않고 폰트만 낮춤
        while _text_size(draw, sub, sub_font)[0] > max_text_w and sub_size > 32:
            sub_size -= 4
            sub_font = _find_font(sub_size)
        sub_stroke_w = max(4, min(10, sub_size // 10))

    # 라인 높이
    def line_h(font):
        _, h = _text_size(draw, "가Ag", font)
        return h

    title_lh = line_h(title_font)
    sub_lh = line_h(sub_font) if sub_font else 0

    # 하단 배치
    bottom_margin = 60
    line_gap = int(title_lh * 0.12)
    current_bottom = THUMB_H - bottom_margin

    # title 라인들 역순으로 좌표 계산
    title_placed: list[tuple[str, int, int]] = []  # (line, x, y_top)
    for line in reversed(title_lines):
        tw, _ = _text_size(draw, line, title_font)
        x = pad_x  # 좌측 정렬
        y_top = current_bottom - title_lh
        title_placed.append((line, x, y_top))
        current_bottom = y_top - line_gap
    title_placed.reverse()

    sub_placed: Optional[tuple[str, int, int]] = None
    if sub and sub_font:
        y_top = current_bottom - int(line_gap * 2) - sub_lh
        sub_placed = (sub, pad_x, y_top)

    # ── 드롭섀도 레이어 (별도 알파 레이어에 오프셋 그리고 블러) ──
    shadow_layer = Image.new("RGBA", composed.size, (0, 0, 0, 0))
    sh_draw = ImageDraw.Draw(shadow_layer)
    SHADOW_OFFSET = 6
    if sub_placed:
        s_text, sx, sy = sub_placed
        assert sub_font is not None
        sh_draw.text(
            (sx + SHADOW_OFFSET, sy + SHADOW_OFFSET),
            s_text,
            font=sub_font,
            fill=(0, 0, 0, 180),
        )
    for line_text, tx, ty in title_placed:
        sh_draw.text(
            (tx + SHADOW_OFFSET, ty + SHADOW_OFFSET),
            line_text,
            font=title_font,
            fill=(0, 0, 0, 200),
        )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=6))
    composed = Image.alpha_composite(composed, shadow_layer)
    draw = ImageDraw.Draw(composed)

    # ── 실제 그림텍스트: 아웃라인 스트로크 + 흰색/노랑 fill ──
    # 여러 줄 title 이면 마지막 줄을 노랑으로 강조 (MrBeast 스타일)
    for idx, (line_text, tx, ty) in enumerate(title_placed):
        is_last = idx == len(title_placed) - 1
        fill = (255, 226, 32) if (is_last and len(title_placed) > 1) else (255, 255, 255)
        _draw_stroked_text(
            draw,
            (tx, ty),
            line_text,
            title_font,
            fill=fill,
            stroke_fill=(0, 0, 0),
            stroke_width=title_stroke_w,
        )

    if sub_placed and sub_font is not None:
        s_text, sx, sy = sub_placed
        _draw_stroked_text(
            draw,
            (sx, sy),
            s_text,
            sub_font,
            fill=(255, 226, 32),
            stroke_fill=(0, 0, 0),
            stroke_width=sub_stroke_w,
        )

    # ── 좌상단 EP 배지 ──
    if episode_label:
        ep = episode_label.strip()
        ep_font = _fit_font(draw, ep, 200, 72, (64, 56, 48, 42, 36))
        tw, th = _text_size(draw, ep, ep_font)
        bx_pad = 18
        by_pad = 10
        ep_x0 = pad_x
        ep_y0 = 36
        ep_x1 = ep_x0 + tw + 2 * bx_pad
        ep_y1 = ep_y0 + th + 2 * by_pad
        _draw_rounded_box(
            draw,
            (ep_x0, ep_y0, ep_x1, ep_y1),
            fill=BADGE_FILL,
            outline=BADGE_STROKE,
            outline_width=4,
            radius=12,
        )
        _draw_stroked_text(
            draw,
            (ep_x0 + bx_pad, ep_y0 + by_pad - 2),
            ep,
            ep_font,
            fill=(20, 20, 20),
            stroke_width=0,
        )

    # v1.1.26: 외곽 초록 프레임 제거 — 이미지가 액자처럼 보이는 문제 해결

    try:
        composed.convert("RGB").save(output_path, "PNG", optimize=True)
    except Exception as e:
        raise ThumbnailError(f"썸네일 저장 실패: {e}") from e

    return output_path


# ─────────────────────────── AI 썸네일 ───────────────────────────


async def generate_ai_thumbnail(
    project_id: str,
    image_prompt: str,
    image_model_id: str,
    overlay_title_text: Optional[str] = None,
    overlay_subtitle: Optional[str] = None,
    overlay_episode_label: Optional[str] = None,
    output_path: Optional[str] = None,
    reference_images: Optional[list[str]] = None,
) -> dict:
    """AI image 모델로 1280x720 배경을 생성하고 선택적으로 텍스트 오버레이.

    Args:
        project_id: 프로젝트 ID. 출력 경로 결정 및 로깅용.
        image_prompt: image 모델에 전달할 프롬프트. 영어 권장.
        image_model_id: `IMAGE_REGISTRY` 에 등록된 모델 ID
            (예: "openai-image-1", "nano-banana-pro", "flux-dev", "seedream-v4.5").
        overlay_title_text: None 이면 AI 출력 원본 그대로 저장. 문자열이 주어지면
            Pillow 로 하단 밴드 + 제목 텍스트 오버레이 합성.
        output_path: 최종 썸네일 저장 경로. None 이면
            DATA_DIR/{project_id}/output/thumbnail.png.
        reference_images: image 서비스에 그대로 전달할 참조 이미지 절대경로 목록.

    Returns:
        {
            "path": str,            # 최종 저장 경로 (overlay 여부와 무관하게 이것)
            "bg_path": str,         # AI 원본 배경 저장 경로 (overlay 적용 시 별도 파일)
            "model": str,           # 사용된 image 모델 ID
            "prompt_used": str,     # image 모델에 넘긴 프롬프트
            "overlay_applied": bool # 텍스트 오버레이 합성 여부
        }

    Raises:
        ThumbnailError: image 서비스 호출이 실패했거나 파일을 쓰지 못한 경우.
    """
    from app.services.image.factory import get_image_service

    if not image_prompt or not image_prompt.strip():
        raise ThumbnailError("image_prompt 가 비어있습니다.")

    # 경로 결정
    if output_path is None:
        out_dir = Path(DATA_DIR) / project_id / "output"
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(out_dir / "thumbnail.png")
    else:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    bg_path = str(Path(output_path).with_name("thumbnail_bg.png"))

    # AI 이미지 생성
    try:
        image_service = get_image_service(image_model_id)
    except Exception as e:
        raise ThumbnailError(f"image 모델 로드 실패 ({image_model_id}): {e}") from e

    try:
        saved_bg = await image_service.generate(
            image_prompt,
            THUMB_W,
            THUMB_H,
            bg_path,
            reference_images=reference_images or None,
        )
    except Exception as e:
        raise ThumbnailError(f"AI 썸네일 배경 생성 실패: {e}") from e

    if not saved_bg or not os.path.exists(saved_bg):
        raise ThumbnailError(f"AI 이미지가 저장되지 않았습니다: {saved_bg!r}")

    # 혹시 image 서비스가 반환 경로를 다르게 줬으면 기대 위치로 복사
    if os.path.abspath(saved_bg) != os.path.abspath(bg_path):
        try:
            shutil.copyfile(saved_bg, bg_path)
        except Exception:
            bg_path = saved_bg  # 그냥 반환된 경로 쓴다

    overlay_applied = False
    final_path = output_path

    if overlay_title_text and overlay_title_text.strip():
        # Pillow 로 텍스트 오버레이 합성 — bg 는 읽기만, 최종 파일은 output_path 에 씀
        try:
            generate_thumbnail(
                project_id=project_id,
                title=overlay_title_text.strip(),
                base_image_path=bg_path,
                output_path=output_path,
                episode_label=(overlay_episode_label or "").strip() or None,
                subtitle=(overlay_subtitle or "").strip() or None,
            )
            overlay_applied = True
        except Exception as e:
            raise ThumbnailError(f"텍스트 오버레이 합성 실패: {e}") from e
    else:
        # 오버레이 없이 AI 원본 그대로를 최종 경로로
        try:
            if os.path.abspath(bg_path) != os.path.abspath(output_path):
                # 원본을 final 위치에 복사 (PNG 로 재인코딩해서 파일 포맷 확실히)
                with Image.open(bg_path) as im:
                    im.convert("RGB").save(output_path, "PNG", optimize=True)
        except Exception as e:
            raise ThumbnailError(f"AI 썸네일 저장 실패: {e}") from e

    return {
        "path": final_path,
        "bg_path": bg_path,
        "model": image_model_id,
        "prompt_used": image_prompt,
        "overlay_applied": overlay_applied,
    }
