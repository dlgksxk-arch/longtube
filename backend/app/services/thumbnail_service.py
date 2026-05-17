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
import re
import shutil
import base64
import html
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont, ImageFilter

from app.config import resolve_project_dir

# YouTube 권장 썸네일 해상도
THUMB_W = 1280
THUMB_H = 720

# 폰트 탐색 후보 (OS 별)
FONT_CANDIDATES = [
    # Windows
    r"C:\Windows\Fonts\meiryob.ttc",        # Meiryo Bold (Japanese)
    r"C:\Windows\Fonts\meiryo.ttc",         # Meiryo (Japanese)
    r"C:\Windows\Fonts\YuGothB.ttc",        # Yu Gothic Bold (Japanese)
    r"C:\Windows\Fonts\YuGothM.ttc",        # Yu Gothic Medium (Japanese)
    r"C:\Windows\Fonts\msgothic.ttc",       # MS Gothic (Japanese)
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

DEVANAGARI_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\NirmalaB.ttf",
    r"C:\Windows\Fonts\Nirmala.ttf",
    r"C:\Windows\Fonts\NirmalaS.ttf",
    r"C:\Windows\Fonts\Mangal.ttf",
    r"C:\Windows\Fonts\Kokila.ttf",
    r"C:\Windows\Fonts\Aparajita.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
]

KOREAN_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\malgunbd.ttf",
    r"C:\Windows\Fonts\NotoSansKR-Bold.ttf",
    r"C:\Windows\Fonts\NotoSansKR-Black.ttf",
    r"C:\Windows\Fonts\NotoSansCJKkr-Bold.otf",
    r"C:\Windows\Fonts\NotoSansCJKkr-Black.otf",
    r"C:\Windows\Fonts\NotoSansKR-VF.ttf",
    r"C:\Windows\Fonts\malgun.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
]

THUMBNAIL_CLICK_FOCUS_PROMPT = (
    " YouTube thumbnail background, not a calm illustration. "
    "One large unmistakable foreground subject must occupy 45-65 percent of the frame. "
    "If the story contains any person, ruler, queen, warrior, envoy, mythic figure, "
    "or human-like character, that character's face must be the hero subject. "
    "Use a story-critical artifact, ritual object, map fragment, gold mirror, crown, "
    "seal, weapon, or burning evidence only when the topic has no usable person or "
    "human-like character. "
    "Use a low-angle or close-up composition with strong silhouette, sharp readable shape, "
    "hard rim light, saturated red/gold/cyan accents, dramatic contrast, visible emotion "
    "or conflict, and a simple darker background reserved for text overlay. "
    "No distant establishing shot. No empty scenery. No foggy castle background. "
    "No gray washed-out palette. No tiny subject. No decorative landscape."
)

THUMBNAIL_FACE_VISIBILITY_PROMPT = (
    " THUMBNAIL FACE VISIBILITY LOCK: when a person or human-like character is present, "
    "show the full face clearly in frame, front-facing or three-quarter view, head and "
    "shoulders visible, eyes nose and mouth visible, eyes sharp, expression readable. "
    "Do not use torso-only framing, body-only framing, cropped head, cropped face, "
    "back view, hidden face, faceless silhouette, blank face, or featureless face. "
    "This face rule overrides any earlier scenery, object, or full-body main subject."
)

THUMBNAIL_WEAK_IMAGE_NEGATIVE = (
    "distant castle, distant building, tiny subject, empty landscape, scenic background, "
    "wide establishing shot, foggy scenery, mist, haze, gray washed out image, low contrast, "
    "flat lighting, calm postcard, generic ruins, decorative background, tiny silhouettes, "
    "unreadable subject, blurry background-only image, torso-only framing, body-only framing, "
    "cropped head, cropped face, back view, hidden face, face out of frame, tiny face, "
    "faceless silhouette, blank face, featureless face, text, letters, words, numbers, watermark"
)

_THUMBNAIL_WEAK_POSITIVE_RE = re.compile(
    r"\b("
    r"foggy|misty|hazy|distant|wide|establishing|landscape|scenery|"
    r"washed[- ]out|gray|grey|calm|peaceful|empty|tiny|small|generic|decorative"
    r")\b",
    re.IGNORECASE,
)


class ThumbnailError(RuntimeError):
    pass


def _thumbnail_click_focus_prompt(prompt: str) -> str:
    base = (prompt or "").strip()
    base = _THUMBNAIL_WEAK_POSITIVE_RE.sub("", base)
    base = re.sub(r"\s+", " ", base).strip(" ,.;")
    if not base:
        return f"{THUMBNAIL_CLICK_FOCUS_PROMPT}{THUMBNAIL_FACE_VISIBILITY_PROMPT}".strip()
    if "THUMBNAIL FACE VISIBILITY LOCK" in base:
        return base
    if "One large unmistakable foreground subject" in base:
        return f"{base.rstrip()} {THUMBNAIL_FACE_VISIBILITY_PROMPT}"
    return f"{base.rstrip()} {THUMBNAIL_CLICK_FOCUS_PROMPT}{THUMBNAIL_FACE_VISIBILITY_PROMPT}"


def build_standard_thumbnail_prompt(script: Optional[dict] = None, title: Optional[str] = None) -> str:
    """Build the single thumbnail prompt used by pipeline, oneclick, scheduler, and uploads."""
    script = script or {}
    thumb_prompt = (script.get("thumbnail_prompt") or "").strip()
    if thumb_prompt:
        return _thumbnail_click_focus_prompt(thumb_prompt)
    clean_title = (title or script.get("title") or "Untitled").strip()
    topic_hint = (script.get("topic") or clean_title).strip()
    return _thumbnail_click_focus_prompt(
        f"A high-tension YouTube thumbnail about this topic: {topic_hint}. "
        f"Create an extreme close-up of the most important person or human-like character "
        f"from the story when one exists. Use an object, artifact, evidence, or decisive "
        f"moment only when there is no usable person. Show the single most "
        f"dramatic conflict, secret, betrayal, danger, or impossible-looking evidence. "
        f"One dominant close-up subject only: "
        f"a shocked face, a threatening ruler, a queen, a warrior, an envoy, a mythic "
        f"figure, or a dangerous historical character. The subject must feel "
        f"urgent and clickable, not calm, wide, distant, generic, or decorative. "
        f"Cinematic lighting, hard "
        f"rim light, deep black shadows, high contrast, saturated red/yellow accent "
        f"colors, strong foreground silhouette, simple background, clean empty space "
        f"for large text overlay. 16:9 landscape composition, 4K ultra-detailed. "
        f"Do not draw the video title. Do not draw any writing. "
        f"ABSOLUTELY NO text, letters, words, numbers, watermarks, or UI elements."
    )


def build_clickbait_thumbnail_overlay(
    script: Optional[dict] = None,
    title: Optional[str] = None,
    config: Optional[dict] = None,
) -> str:
    """Return short, high-impact overlay text instead of copying the full title."""
    script = script or {}
    config = config or {}
    for key in ("thumbnail_hook", "thumbnail_text", "thumbnail_overlay", "thumbnail_title"):
        value = sanitize_thumbnail_title(script.get(key))
        if value:
            return _wrap_overlay_lines(value)

    base = sanitize_thumbnail_title(title or script.get("title") or script.get("topic") or "")
    if not base:
        return ""

    language = str(config.get("language") or script.get("language") or "").lower()
    has_hangul = _has_hangul(base)
    if language in {"ko", "kr", "kor", "korean", ""} and has_hangul:
        compact = re.sub(r"\s+", " ", base).strip()
        compact = re.sub(r"^EP\.?\s*\d+\s*[-:·]?\s*", "", compact, flags=re.IGNORECASE).strip()
        compact = re.sub(r"^(왜|어째서|어떻게)\s+", "", compact)
        if any(word in compact for word in ("누구", "정체")):
            subject = re.sub(r"(누구일까|누구인가|누구였나|누구였을까|정체는|정체가|정체)", "", compact).strip(" ?!-·")
            return _wrap_overlay_lines(f"정체가 뭐냐\n{_short_korean_subject(subject)}")
        if "이유" in compact:
            subject = compact.replace("이유", "").strip(" -·")
            return _wrap_overlay_lines(f"진짜 이유\n{_short_korean_subject(subject)}")
        if "비밀" in compact:
            subject = compact.replace("비밀", "").strip(" -·")
            return _wrap_overlay_lines(f"숨겨진 비밀\n{_short_korean_subject(subject)}")
        if "최초" in compact:
            return _wrap_overlay_lines(f"최초의 진실\n{_short_korean_subject(compact)}")
        if any(word in compact for word in ("잃은", "죽", "멸망", "무너", "사라")):
            return _wrap_overlay_lines(f"결말이 바뀐\n{_short_korean_subject(compact)}")
        if any(word in compact for word in ("왕", "여왕", "황제", "전쟁", "군대")):
            return _wrap_overlay_lines(f"왕보다 무서운\n{_short_korean_subject(compact)}")
        if any(word in compact for word in ("한반도", "한국", "조선", "고려", "신라", "백제", "고구려")):
            return _wrap_overlay_lines(f"교과서가 뺀\n{_short_korean_subject(compact)}")
        return _wrap_overlay_lines(f"아무도 몰랐던\n{_short_korean_subject(compact)}")

    return _wrap_overlay_lines(base)


def _short_korean_subject(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip(" -·")
    if "바다" in text and any(word in text for word in ("여인", "여자", "사람")):
        return "바다 건넌 여인"
    if "왕" in text and any(word in text for word in ("죽", "잃", "무너", "멸망")):
        return "무너진 왕의 비밀"
    return text


def _wrap_overlay_lines(text: str) -> str:
    text = re.sub(r"\s+", " ", (text or "").replace("\n", " ")).strip()
    if not text:
        return ""
    words = text.split()
    if len(words) <= 2:
        return text
    target_lines = 2 if len(words) <= 6 else 3 if len(words) <= 12 else 4
    per_line = max(1, (len(words) + target_lines - 1) // target_lines)
    lines = [" ".join(words[i:i + per_line]) for i in range(0, len(words), per_line)]
    return "\n".join(lines).strip()


async def ensure_standard_thumbnail(
    project_id: str,
    config: Optional[dict] = None,
    script: Optional[dict] = None,
    title: Optional[str] = None,
    topic: Optional[str] = None,
    episode_number: Optional[object] = None,
    overwrite: bool = False,
) -> str:
    """Generate output/thumbnail.png with the shared AI+overlay logic and return its path."""
    from app.services.image.factory import (
        DEFAULT_THUMBNAIL_MODEL,
        get_image_service,
        resolve_image_model,
        IMAGE_REGISTRY,
    )
    from app.services.image.prompt_builder import (
        apply_reference_style_prefix,
        collect_character_images,
        collect_reference_images,
        should_enable_historical_guard_for_context,
    )

    config = config or {}
    script = script or {}
    project_dir = resolve_project_dir(project_id, config)
    thumb_path = project_dir / "output" / "thumbnail.png"
    if not overwrite and thumb_path.exists() and thumb_path.stat().st_size > 100:
        return str(thumb_path)

    thumb_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_title = (title or script.get("title") or topic or "Untitled").strip()
    thumb_prompt = build_standard_thumbnail_prompt(script, prompt_title)
    image_model = resolve_image_model(config.get("thumbnail_model") or DEFAULT_THUMBNAIL_MODEL)

    overlay_seed = build_clickbait_thumbnail_overlay(script, prompt_title, config)
    overlay_title, extracted_episode_label = extract_thumbnail_text_parts(overlay_seed or prompt_title, None)
    overlay_title = suppress_foreign_hangul_thumbnail_overlay(overlay_title, config)
    ep_raw = episode_number if episode_number is not None else config.get("episode_number")
    overlay_episode_label = normalize_episode_label(str(ep_raw)) if ep_raw else extracted_episode_label

    char_paths = collect_character_images(project_id, config)
    ref_paths = collect_reference_images(project_id, config)
    seen: set[str] = set()
    combined_refs: list[str] = []
    for p in [*char_paths, *ref_paths]:
        if p not in seen:
            seen.add(p)
            combined_refs.append(p)

    enable_historical_guard = should_enable_historical_guard_for_context(
        config,
        project_id,
        prompt_title,
        topic or script.get("topic"),
    )

    if combined_refs:
        probe = get_image_service(image_model)
        if not getattr(probe, "supports_reference_images", False):
            is_comfyui = IMAGE_REGISTRY.get(image_model, {}).get("provider") == "comfyui"
            if is_comfyui:
                combined_refs = []
            else:
                raise ThumbnailError(
                    f"Selected thumbnail model '{image_model}' does not support reference images."
                )

    if combined_refs and thumb_prompt:
        thumb_prompt = apply_reference_style_prefix(
            thumb_prompt,
            has_reference=True,
            enable_historical_guard=enable_historical_guard,
        )

    try:
        result = await generate_ai_thumbnail(
            project_id=project_id,
            image_prompt=thumb_prompt,
            image_model_id=image_model,
            overlay_title_text=overlay_title,
            overlay_subtitle=None,
            overlay_episode_label=overlay_episode_label,
            output_path=str(thumb_path),
            reference_images=combined_refs or None,
            enable_historical_guard=enable_historical_guard,
            config=config,
        )
        return str(result.get("path") or thumb_path)
    except Exception:
        base_cut = project_dir / "images" / "cut_001.png"
        if not base_cut.exists():
            raise
        return generate_thumbnail(
            project_id=project_id,
            title=overlay_title or prompt_title,
            base_image_path=str(base_cut),
            output_path=str(thumb_path),
            episode_label=overlay_episode_label,
            config=config,
        )



def normalize_episode_label(label: Optional[str]) -> Optional[str]:
    text = (label or "").strip()
    if not text:
        return None
    match = re.search(r"(\d{1,3})", text)
    if match:
        return f"EP.{int(match.group(1)):02d}"
    return text


def sanitize_thumbnail_title(text: Optional[str]) -> str:
    value = (text or "").strip()
    if not value:
        return ""
    value = re.sub(r"\bEP\.?\s*0*\d{1,3}\b", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*[\[\(【][^\]\)】]{1,30}[\]\)】]\s*$", "", value)
    value = re.sub(r"\s{2,}", " ", value).strip(" -·")
    return value.strip()


def extract_thumbnail_text_parts(
    title: Optional[str],
    episode_label: Optional[str] = None,
) -> tuple[str, Optional[str]]:
    raw_title = (title or "").strip()
    raw_label = normalize_episode_label(episode_label)

    extracted_label = None
    match = re.search(r"\bEP\.?\s*0*(\d{1,3})\b", raw_title, flags=re.IGNORECASE)
    if match:
        extracted_label = f"EP.{int(match.group(1)):02d}"
        raw_title = re.sub(r"\bEP\.?\s*0*\d{1,3}\b", "", raw_title, flags=re.IGNORECASE)

    clean_title = sanitize_thumbnail_title(raw_title)
    final_label = raw_label or extracted_label
    return clean_title, final_label


def _has_devanagari(text: Optional[str]) -> bool:
    return any(0x0900 <= ord(ch) <= 0x097F for ch in (text or ""))


def _find_browser_executable() -> Optional[str]:
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        shutil.which("chrome"),
        shutil.which("msedge"),
        shutil.which("chromium"),
        shutil.which("google-chrome"),
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return str(candidate)
    return None


def _render_devanagari_thumbnail_with_browser(
    *,
    base_image_path: Optional[str],
    output_path: str,
    title: str,
    episode_label: Optional[str],
    subtitle: Optional[str],
) -> Optional[str]:
    """Render Hindi/Devanagari overlays through Chrome for proper shaping."""
    browser = _find_browser_executable()
    if not browser or not base_image_path or not os.path.exists(base_image_path):
        return None

    bg_data = base64.b64encode(Path(base_image_path).read_bytes()).decode("ascii")
    ep = html.escape(normalize_episode_label(episode_label) or (episode_label or "").strip())
    title_words = title.strip().split()
    if len(title_words) >= 3:
        title_main = " ".join(title_words[:-2])
        title_impact = " ".join(title_words[-2:])
    else:
        title_main = ""
        title_impact = title.strip()
    title_html = (
        f'<span class="title-main">{html.escape(title_main)}</span> '
        f'<span class="title-impact">{html.escape(title_impact)}</span>'
        if title_main
        else f'<span class="title-impact">{html.escape(title_impact)}</span>'
    )
    subtitle_html = html.escape((subtitle or "").strip())
    badge_block = f'<div class="top">{ep}</div>' if ep else ""
    subtitle_block = f'<div class="subtitle">{subtitle_html}</div>' if subtitle_html else ""
    html_doc = f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box}}
body{{margin:0;width:{THUMB_W}px;height:{THUMB_H}px;overflow:hidden;background:#111}}
.canvas{{position:relative;width:{THUMB_W}px;height:{THUMB_H}px;font-family:"Nirmala UI","Mangal","Arial Unicode MS",sans-serif;background-image:linear-gradient(180deg,rgba(0,0,0,.04) 0%,rgba(0,0,0,.12) 42%,rgba(0,0,0,.64) 100%),linear-gradient(90deg,rgba(0,0,0,.46),rgba(0,0,0,.04) 58%,rgba(0,0,0,.18)),url(data:image/png;base64,{bg_data});background-size:cover;background-position:center}}
.top{{position:absolute;left:60px;top:40px;padding:8px 16px 9px;border-radius:14px;background:#ffd32a;color:#111;font-weight:900;font-size:38px;line-height:1;box-shadow:0 5px 15px rgba(0,0,0,.35)}}
.copy{{position:absolute;left:64px;right:76px;bottom:104px}}
.title{{font-weight:900;font-size:82px;line-height:1.06;letter-spacing:0;text-wrap:balance;-webkit-text-stroke:4px #050505;text-shadow:0 7px 0 rgba(0,0,0,.86),0 0 22px rgba(0,0,0,.90),5px 0 0 #050505,-5px 0 0 #050505,0 5px 0 #050505,0 -5px 0 #050505,4px 4px 0 #050505,-4px 4px 0 #050505,4px -4px 0 #050505,-4px -4px 0 #050505}}
.title-main{{display:block;color:#fff}}
.title-impact{{display:block;color:#ffe736}}
.subtitle{{margin-top:10px;color:#ffe736;font-weight:900;font-size:64px;line-height:1.04;letter-spacing:0;-webkit-text-stroke:4px #050505;text-shadow:0 6px 0 rgba(0,0,0,.86),0 0 20px rgba(0,0,0,.86),5px 0 0 #050505,-5px 0 0 #050505,0 5px 0 #050505,0 -5px 0 #050505;text-wrap:balance}}
</style></head><body><div class="canvas">{badge_block}<div class="copy"><div class="title">{title_html}</div>{subtitle_block}</div></div></body></html>"""

    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            html_path = tmp_dir / "thumbnail.html"
            png_path = tmp_dir / "thumbnail.png"
            html_path.write_text(html_doc, encoding="utf-8")
            subprocess.run(
                [
                    browser,
                    "--headless=new",
                    "--disable-gpu",
                    "--hide-scrollbars",
                    f"--window-size={THUMB_W},{THUMB_H}",
                    f"--screenshot={png_path}",
                    html_path.as_uri(),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if not png_path.exists() or png_path.stat().st_size < 10_000:
                return None
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(png_path, output_path)
            return output_path
    except Exception as e:
        print(f"[thumbnail] browser Devanagari render failed; falling back to Pillow: {e}")
        return None


def _has_hangul(text: Optional[str]) -> bool:
    return any(0xAC00 <= ord(ch) <= 0xD7A3 for ch in (text or ""))


def suppress_foreign_hangul_thumbnail_overlay(
    overlay_title: Optional[str],
    config: Optional[dict] = None,
) -> Optional[str]:
    """Do not render Korean overlay text on non-Korean channel thumbnails."""
    language = str((config or {}).get("language") or "").strip().lower()
    if language and language not in {"ko", "kr", "kor", "korean"} and _has_hangul(overlay_title):
        return None
    return overlay_title


def _find_font(size: int, text: Optional[str] = None) -> ImageFont.ImageFont:
    """가능한 한 한글 지원 + 볼드 폰트를 찾아 반환. 실패 시 default."""
    if _has_devanagari(text):
        candidates = [*DEVANAGARI_FONT_CANDIDATES, *FONT_CANDIDATES]
    elif _has_hangul(text):
        candidates = [*KOREAN_FONT_CANDIDATES, *FONT_CANDIDATES]
    else:
        candidates = FONT_CANDIDATES
    for path in candidates:
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


def _text_bbox(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
) -> tuple[int, int, int, int]:
    try:
        return draw.textbbox((0, 0), text, font=font)
    except Exception:
        w, h = _text_size(draw, text, font)
        return (0, 0, w, h)


def _fit_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_w: int,
    max_h: int,
    candidates: tuple[int, ...],
) -> ImageFont.ImageFont:
    """주어진 너비/높이 안에 들어가는 가장 큰 폰트를 후보 중에서 선택."""
    for size in candidates:
        font = _find_font(size, text)
        w, h = _text_size(draw, text, font)
        if w <= max_w and h <= max_h:
            return font
    return _find_font(candidates[-1], text)


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
    embolden: int = 0,
) -> None:
    try:
        draw.text(xy, text, font=font, fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill)
        if embolden > 0:
            x, y = xy
            offsets = [
                (-embolden, 0),
                (embolden, 0),
                (0, -embolden),
                (0, embolden),
                (-embolden, -embolden),
                (embolden, -embolden),
                (-embolden, embolden),
                (embolden, embolden),
            ]
            for dx, dy in offsets:
                draw.text((x + dx, y + dy), text, font=font, fill=fill)
    except TypeError:
        draw.text(xy, text, font=font, fill=fill)


def generate_thumbnail(
    project_id: str,
    title: str,
    base_image_path: Optional[str] = None,
    output_path: Optional[str] = None,
    episode_label: Optional[str] = None,
    subtitle: Optional[str] = None,
    config: Optional[dict] = None,
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
    title, episode_label = extract_thumbnail_text_parts(title, episode_label)
    if not title or not title.strip():
        raise ThumbnailError("제목이 비어있습니다.")

    if output_path is None:
        out_dir = resolve_project_dir(project_id, config or {}, create=True) / "output"
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(out_dir / "thumbnail.png")
    else:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if _has_devanagari(" ".join([title or "", subtitle or "", episode_label or ""])):
        browser_output = _render_devanagari_thumbnail_with_browser(
            base_image_path=base_image_path,
            output_path=output_path,
            title=title,
            episode_label=episode_label,
            subtitle=subtitle,
        )
        if browser_output:
            return browser_output

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
    # 후보 사이즈를 높은 것부터 내려가며 전체 문장이 잘리지 않도록 줄바꿈/축소한다.
    # v2.1.2: 폰트 크기 상향 — 제목이 짧아졌으므로 더 크게 표시
    candidates = (200, 180, 160, 140, 124, 108, 96, 86, 76, 68, 60, 54, 48, 42, 36, 32, 28, 24)
    max_title_block_h = int(THUMB_H * 0.62)

    def pick_title_font() -> tuple[ImageFont.ImageFont, list[str]]:
        for size in candidates:
            f = _find_font(size, text)
            lines = _wrap_text(text, f, max_text_w, draw)
            if not lines:
                continue
            lh = _text_size(draw, "가Ag", f)[1]
            total_h = len(lines) * lh + (len(lines) - 1) * int(lh * 0.15)
            if total_h <= max_title_block_h:
                return f, lines
        # 폴백: 가장 작은 폰트
        f = _find_font(candidates[-1], text)
        return f, _wrap_text(text, f, max_text_w, draw) or [text]

    title_font, title_lines = pick_title_font()
    title_size = getattr(title_font, "size", 96)
    # 아웃라인 두께는 폰트 크기에 비례 (굵은 카툰풍)
    title_stroke_w = max(6, min(14, title_size // 9))
    title_embolden = max(2, min(5, title_size // 42))

    # subtitle — 있을 때만. title 보다 작게.
    sub_font = None
    sub_stroke_w = 0
    if sub:
        sub_size = max(44, int(title_size * 0.55))
        sub_font = _find_font(sub_size, sub)
        # 너무 길면 쪼개지 않고 폰트만 낮춤
        while _text_size(draw, sub, sub_font)[0] > max_text_w and sub_size > 32:
            sub_size -= 4
            sub_font = _find_font(sub_size, sub)
        sub_stroke_w = max(4, min(10, sub_size // 10))
        sub_embolden = max(2, min(4, sub_size // 40))
    else:
        sub_embolden = 0

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
            embolden=title_embolden,
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
            embolden=sub_embolden,
        )

    # ── 좌상단 EP 배지 ──
    if episode_label:
        ep = normalize_episode_label(episode_label) or episode_label.strip()
        # EP 배지는 작고 또렷하게만 보이면 된다.
        ep_font = _fit_font(draw, ep, 150, 42, (42, 36, 32, 28, 24))
        bbox = _text_bbox(draw, ep, ep_font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        bx_pad = 14
        by_pad = 8
        # 상단 여백이 너무 타이트하면 미리보기/실제 썸네일에서 배지가 잘려 보인다.
        # 좌측 상단 안쪽으로 조금 더 밀어 넣어 안전 여백을 확보한다.
        ep_x0 = pad_x + 8
        ep_y0 = 40
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
            (ep_x0 + bx_pad - bbox[0], ep_y0 + by_pad - bbox[1]),
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
    enable_historical_guard: bool = False,
    config: Optional[dict] = None,
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
            프로젝트 디렉토리의 output/thumbnail.png.
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
        out_dir = resolve_project_dir(project_id, config or {}, create=True) / "output"
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

    from app.services.image.prompt_builder import (
        append_prompt_specific_negative_prompt,
        apply_reference_style_prefix,
        historical_negative_prompt,
        map_negative_prompt,
        symbol_negative_prompt,
        text_negative_prompt,
    )

    image_prompt = _thumbnail_click_focus_prompt(image_prompt)
    image_prompt = apply_reference_style_prefix(
        image_prompt,
        has_reference=bool(reference_images),
        enable_historical_guard=enable_historical_guard,
    )
    try:
        current_neg = (getattr(image_service, "negative_prompt", "") or "").strip()
        for required_negative in (text_negative_prompt(), map_negative_prompt(), symbol_negative_prompt()):
            if required_negative and required_negative not in current_neg:
                current_neg = f"{required_negative}, {current_neg}".strip(" ,")
        guard_negative = historical_negative_prompt(image_prompt, enable_historical_guard)
        if guard_negative and guard_negative not in current_neg:
            current_neg = f"{guard_negative}, {current_neg}".strip(" ,")
        for weak_negative in THUMBNAIL_WEAK_IMAGE_NEGATIVE.split(","):
            weak_negative = weak_negative.strip()
            if weak_negative and weak_negative not in current_neg:
                current_neg = f"{weak_negative}, {current_neg}".strip(" ,")
        image_service.negative_prompt = append_prompt_specific_negative_prompt(current_neg, image_prompt)
    except Exception:
        pass

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
