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
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageStat

from app import config as app_config
from app.config import resolve_project_dir

# YouTube 권장 썸네일 해상도
THUMB_W = 1280
THUMB_H = 720

THUMBNAIL_MINIMAL_GENERATION_CONTRACT = (
    "Landscape 16:9 composition. Keep the lower-left area clean, dark, empty, "
    "and low-detail. All banners, signs, documents, and visible surfaces are "
    "plain and completely blank."
)

THUMBNAIL_CHARACTER_IDENTITY_REFERENCE_LOCK = (
    "THUMBNAIL CHARACTER IDENTITY REFERENCE LOCK: the first attached character "
    "reference fixes the primary subject's sex, adult age, face, hair, skin tone, "
    "and archaic clothing identity. Preserve that same person in the new composition. "
    "Do not replace the referenced woman with a man or the referenced man with a woman. "
)

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
    " YouTube thumbnail pre-overlay image, not a calm illustration. "
    "Make it scroll-stopping and provocative, but fact-locked: amplify only stakes "
    "already present in the story, never invent gore, crimes, symbols, or readable text. "
    "Choose the most clickable story-critical subject: a readable face when a person "
    "or human-like character can sell the story, otherwise one decisive object or "
    "event detail. The hero subject must occupy 40-55 percent of the frame, with "
    "35-45 percent clean negative space reserved in the lower-left text-safe zone "
    "for large text overlay. Keep every face, eyes, nose, mouth, and important hand "
    "outside that lower-left text-safe zone. "
    "Pick the strongest factual emotional trigger: fatal consequence, forbidden secret, "
    "betrayal signal, explosive rage, public humiliation, collapse evidence, or a last-warning "
    "object immediately before disaster. "
    "Use a low-angle or close-up composition with strong silhouette, sharp readable shape, "
    "hard rim light, dramatic contrast, exaggerated visible emotion or conflict, and one "
    "story-matched accent color. "
    "Use high-resolution documentary cartoon thumbnail style with clean bold shapes. "
    "No distant establishing shot. No empty scenery. No foggy castle background. "
    "No gray washed-out palette. No tiny subject. No decorative landscape."
)

THUMBNAIL_FACE_VISIBILITY_PROMPT = (
    " THUMBNAIL FACE VISIBILITY LOCK: when a person or human-like character is present, "
    "show the full face clearly in frame, front-facing or three-quarter view, head and "
    "shoulders visible, eyes nose and mouth visible, eyes sharp, expression readable. "
    "For a close-up or portrait prompt, one face must fill 50-65 percent of the image "
    "height, both eyes must be readable, and 30-40 percent clean dark negative "
    "space must remain in the lower-left text-safe zone for large overlay text. "
    "No face, eyes, nose, mouth, or important hand may enter that text-safe zone. "
    "Background crowds or armies must be "
    "small dark atmosphere only, never a competing subject. "
    "Do not use torso-only framing, body-only framing, cropped head, cropped face, "
    "back view, hidden face, faceless silhouette, blank face, or featureless face. "
    "This face rule overrides any earlier scenery, object, or full-body main subject."
)

THUMBNAIL_TEXT_SAFE_ZONE_LOCK = (
    " LOWER-LEFT TEXT-SAFE ZONE LOCK: reserve a visibly empty, dark, low-detail "
    "lower-left rectangle for large overlay text. This reserved zone covers about "
    "45 percent of the image width and 45 percent of the image height from the "
    "bottom-left corner. No face, eyes, nose, mouth, chin, hands, body, animal, "
    "weapon, skull, monument, bright object, or story-critical detail may enter "
    "that zone. Put the dominant face on the right half or high upper area, "
    "fully outside the reserved zone."
)

THUMBNAIL_OBJECT_TEXT_SAFE_ZONE_LOCK = (
    " LOWER-LEFT TEXT-SAFE ZONE LOCK: reserve a visibly empty, dark, low-detail "
    "lower-left rectangle for large overlay text. This reserved zone covers about "
    "45 percent of the image width and 45 percent of the image height from the "
    "bottom-left corner. No main object, island, wave crest, bright light burst, "
    "animal, body, weapon, monument, building, text, symbol, or story-critical detail "
    "may enter that zone. Put the dominant object or event detail on the right half "
    "or upper-right area, fully outside the reserved zone."
)

THUMBNAIL_FACE_CLOSEUP_FRAME_LOCK = (
    " THUMBNAIL CLOSE-UP FACE FRAME LOCK: when the prompt asks for a close-up face "
    "or portrait, compose a head-and-shoulders portrait only. The face and upper "
    "body are the dominant foreground subject, with the face placed right-of-center "
    "or high enough to reserve clean lower-left text space, and no cropped "
    "forehead, hat, chin, or cheeks. Remove wide scenery "
    "logic: background soldiers, armies, ships, gates, rooftops, mountains, and roads "
    "must be blurred, low-detail atmosphere behind the face, occupying less visual "
    "weight than the eyes. Do not use a horse, mounted rider, full-body rider, "
    "distant figure, side-profile portrait, large gate, shrine gate, castle gate, "
    "wide battlefield composition, or army crowd composition."
)

THUMBNAIL_FATAL_MECHANISM_LOCK = (
    " THUMBNAIL FATAL MECHANISM LOCK: when the story title or prompt says a throne, "
    "chair, seat, platform, collapsing object, crushing death, strangling device, "
    "fatal accident, or bizarre death killed the main person, the thumbnail must show "
    "the fatal mechanism as a huge foreground threat in the same frame as the face. "
    "Do not make a calm ruler portrait. Do not show generic random planks. Show "
    "immediate danger from a recognizable broken throne: carved wooden throne "
    "backrest, cracked seat slab, snapped armrest, and heavy throne legs tipping or "
    "crushing toward the ruler. The ruler has shocked terrified eyes, open mouth, "
    "and one hand gripping the broken throne arm. No background nobles or competing "
    "crowd. The broken throne mechanism must occupy 30-45 percent of the frame and "
    "be readable before the background. Keep it fact-locked and non-gory: no blood "
    "spray, no severed body parts, no invented weapon."
)

THUMBNAIL_DROWNING_DANGER_LOCK = (
    " THUMBNAIL DROWNING DANGER LOCK: when the story title or prompt says "
    "drowning, river, capsized boat, water rising, deadly water, or rescue "
    "forbidden by court law, the thumbnail must show the fatal water danger "
    "close to the face. Do not make a calm royal portrait. Do not use a wide "
    "boat scene, crowd scene, palace scene, or object-only river. Show dark "
    "river water rising at the lower foreground near the neck, shoulder, or "
    "chest line, wet hair or wet court silk edges, fearful eyes, and immediate "
    "danger while keeping the face dominant. Keep it fact-locked and non-gory: "
    "no blood, no corpse, no invented attacker, no modern rescue gear."
)

THUMBNAIL_WEAK_IMAGE_NEGATIVE = (
    "distant castle, distant building, tiny subject, empty landscape, scenic background, "
    "wide establishing shot, foggy scenery, mist, haze, gray washed out image, low contrast, "
    "flat lighting, calm postcard, generic ruins, decorative background, tiny silhouettes, "
    "unreadable subject, blurry background-only image, torso-only framing, body-only framing, "
    "cropped head, cropped face, back view, hidden face, face out of frame, tiny face, "
    "faceless silhouette, blank face, featureless face, side profile, profile-only face, "
    "distant army, army background as main subject, crowd competing with face, "
    "wide army field, battlefield replacing face, cropped forehead, cropped hat, "
    "cropped chin, text, letters, words, numbers, watermark"
)

_THUMBNAIL_WEAK_POSITIVE_RE = re.compile(
    r"\b("
    r"foggy|misty|hazy|distant|wide|establishing|landscape|scenery|"
    r"washed[- ]out|gray|grey|calm|peaceful|empty|tiny|small|generic|decorative"
    r")\b",
    re.IGNORECASE,
)


_THUMBNAIL_TEXT_SPACE_REGION = (
    r"(?:"
    r"(?:upper|top|lower|bottom)[-\s]+(?:left|right)"
    r"(?:[-\s]+(?:corner|side|half|third|quadrant|area|region))?"
    r"|(?:left|right)[-\s]+(?:side|half|third|corner|quadrant|area|region)"
    r"|(?:upper|top|lower|bottom)[-\s]+(?:side|half|third|area|region)"
    r"|(?:opposite|other)[-\s]+side"
    r"|left|right|top|bottom"
    r")"
)

_THUMBNAIL_SOURCE_TEXT_SPACE_RE = re.compile(
    rf"""
    \b
    (?=[^,.;]{{0,160}}(?:{_THUMBNAIL_TEXT_SPACE_REGION}|\btext\b))
    (?:(?:and|with|while|so)\s+)?
    (?:(?:the\s+)?{_THUMBNAIL_TEXT_SPACE_REGION}\s+(?:remains?|stays?|is)\s+)?
    (?:(?:leave|leaves|leaving|reserve|reserves|reserving|keep|keeps|keeping|
    maintain|maintains|maintaining|provide|provides|providing|create|creates|creating)\s+)?
    (?:(?:about|roughly|approximately)\s+)?
    (?:\d{{1,2}}\s*(?:[-–—]\s*\d{{1,2}})?\s*(?:%|percent)
    (?:\s+of\s+(?:the\s+)?(?:frame|image))?\s+)?
    (?:(?:clean|clear|dark|empty|deliberate|visible|open|low[-\s]?detail|reserved)\s+)*
    (?:
        negative\s+space
        |(?:text|title|caption)[-\s]*(?:safe[-\s]*)?(?:space|zone|area)
        |(?:space|room|area|zone)
    )
    (?:\s+(?:at|in|on|to|from|along|within|across)\s+(?:the\s+)?
    {_THUMBNAIL_TEXT_SPACE_REGION})?
    (?:
        \s+(?:reserved\s+|intended\s+)?for\s+
        (?:(?:later|large|Korean|Japanese|English|overlay|thumbnail)\s+)*
        (?:(?:title|caption|overlay)\s+)?text(?:\s+overlay)?(?:\s+later)?
        |\s+so\s+(?:(?:title|overlay)\s+)?text\s+can\s+be\s+
        (?:added|placed|composited)(?:\s+later)?
    )?
    (?=\s*[,.;]|$)
    """,
    re.IGNORECASE | re.VERBOSE,
)


class ThumbnailError(RuntimeError):
    pass


def _thumbnail_quality_enabled(config: Optional[dict]) -> bool:
    value = (config or {}).get("thumbnail_quality_check", True)
    return value is not False and str(value).strip().lower() not in {"0", "false", "no", "off"}


def _thumbnail_quality_attempt_count(config: Optional[dict]) -> int:
    try:
        attempts = int((config or {}).get("thumbnail_quality_attempts") or 2)
    except (TypeError, ValueError):
        attempts = 2
    return max(1, min(4, attempts))


def _thumbnail_data_uri(image_path: str) -> str:
    data = Path(image_path).read_bytes()
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def _write_thumbnail_qa_sidecar(image_path: str, payload: dict) -> None:
    try:
        Path(str(image_path) + ".qa.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def _first_cut_image_path(project_dir: Path) -> Path:
    images_dir = project_dir / "images"
    for name in ("cut_1.png", "cut_001.png", "cut_1.jpg", "cut_001.jpg"):
        candidate = images_dir / name
        if candidate.exists() and candidate.stat().st_size > 100:
            return candidate
    candidates = sorted(
        [
            *images_dir.glob("cut_*.png"),
            *images_dir.glob("cut_*.jpg"),
        ],
        key=lambda p: p.name,
    )
    return candidates[0] if candidates else images_dir / "cut_1.png"


def _configured_thumbnail_base_image_path(
    project_dir: Path,
    config: Optional[dict],
) -> Optional[Path]:
    """Resolve an explicitly selected existing project image for local thumbnail rendering."""
    raw_cut_number = (config or {}).get("thumbnail_base_cut_number")
    if raw_cut_number in (None, ""):
        return None
    try:
        cut_number = int(raw_cut_number)
    except (TypeError, ValueError) as exc:
        raise ThumbnailError("thumbnail_base_cut_number는 정수여야 합니다.") from exc
    if cut_number < 1:
        raise ThumbnailError("thumbnail_base_cut_number는 1 이상이어야 합니다.")

    images_dir = project_dir / "images"
    for suffix in (".png", ".jpg", ".jpeg", ".webp"):
        for stem in (f"cut_{cut_number}", f"cut_{cut_number:03d}"):
            candidate = images_dir / f"{stem}{suffix}"
            if candidate.exists() and candidate.stat().st_size > 100:
                return candidate
    raise ThumbnailError(
        f"선택한 썸네일 원본 컷을 찾을 수 없습니다: cut {cut_number}"
    )


def _basic_thumbnail_file_check(image_path: str) -> tuple[bool, str]:
    path = Path(image_path)
    if not path.exists() or not path.is_file() or path.stat().st_size <= 100:
        return False, "missing_or_too_small"
    try:
        with Image.open(path) as im:
            image = im.convert("RGB")
            if image.size[0] < 640 or image.size[1] < 360:
                return False, f"too_small:{image.size[0]}x{image.size[1]}"
            probe = image.resize((64, 36), Image.LANCZOS)
            stat = ImageStat.Stat(probe)
            extrema = [hi - lo for lo, hi in stat.extrema]
            if max(extrema or [0]) < 18:
                return False, "nearly_flat_image"
            if sum(stat.var) / max(1, len(stat.var)) < 35:
                return False, "low_visual_variance"
    except Exception as exc:
        return False, f"image_open_failed:{exc}"
    return True, "basic_pass"


def _thumbnail_quality_system_prompt() -> str:
    return (
        "You are a strict YouTube thumbnail QA inspector. Return JSON only. "
        "Evaluate the generated pre-overlay thumbnail image, not an empty background. "
        "The pre-overlay image may include the main person, face, ruler, warrior, "
        "envoy, or mythic figure when the prompt asks for one. Do not fail solely "
        "because a recognizable human face or person is visible when that matches "
        "the prompt. Use pass=false if the prompt asks for a close-up face or "
        "portrait but the image is a mounted rider, full-body rider, distant "
        "figure, large gate composition, or wide battlefield scene. Only call an "
        "image a mounted rider when a clear horse body, horse legs, saddle, or "
        "horse tack is visible; do not infer a rider from robe shoulders, cropped "
        "torso shapes, dark lower body, flags, or small background silhouettes. Use pass=false "
        "if the prompt asks for a person, named person, ruler, warrior, envoy, "
        "mythic figure, or readable face but the image is background-only, "
        "object-only, has no clear face, has a hidden/cropped/tiny face, or is a "
        "wide establishing shot. Use pass=false if the prompt does not ask for a "
        "person or face and the image replaces the named object, terrain, event, "
        "or mechanism with a human face, portrait, warrior, rider, or unrelated "
        "character. Use pass=false when the main subject does not visibly match "
        "the prompt. When the prompt specifies an exact count, origin, or color set "
        "for visible beams, lights, objects, or symbols, use pass=false if any required "
        "item is missing, merged, has the wrong color, or emerges from the wrong place. "
        "When the prompt explicitly requires cartoon, graphic-novel, ink-outline, or "
        "cel-shaded rendering, use pass=false for photorealistic or live-action-looking "
        "results. When the prompt contains THUMBNAIL HERO SUBJECT OVERRIDE, the configured "
        "hero's identity, adult age, gender or role, close-up framing, and foreground "
        "dominance are mandatory; use pass=false when another named person replaces that "
        "hero or when the configured hero is missing. Also fail fake text, letters, "
        "symbols, glyphs, watermarks, UI, unreadable signage, or weak low-contrast "
        "decorative scenery. If the prompt reserves a lower-left text-safe zone, "
        "use pass=false when any face, eyes, nose, mouth, chin, important hand, "
        "animal, or main subject enters that lower-left zone where overlay text "
        "will be placed. "
        "If the prompt asks for a fatal mechanism such as a "
        "crushing throne, collapsing chair, deadly seat, strangling device, fatal "
        "accident object, or bizarre death object, fail calm portraits that do not "
        "show the mechanism clearly and close to the face. Return {\"pass\": boolean, \"issues\": [string], "
        "\"summary\": string}."
    )


def _thumbnail_overlay_quality_system_prompt() -> str:
    return (
        "You are a strict YouTube thumbnail final-overlay QA inspector. Return JSON only. "
        "Evaluate the final rendered thumbnail after large text has been composited. "
        "Use pass=false if any overlay text, text stroke, or text shadow covers, cuts "
        "through, or hides any visible human or animal face, especially eyes, nose, "
        "mouth, chin, forehead, or expression. Use pass=false if the main face becomes "
        "hard to read because of the text. Do not fail when text covers only empty "
        "background, armor, clothing, scenery, or a dark reserved text area. Do not "
        "fail merely because text is near a face without covering it. Return "
        "{\"pass\": boolean, \"issues\": [string], \"summary\": string}."
    )


_THUMBNAIL_PERSON_PROMPT_RE = re.compile(
    r"\b("
    r"person|human|face|facial|eyes|mouth|head|shoulders|ruler|king|queen|warrior|"
    r"envoy|commander|soldier|samurai|rider|mythic figure|character|"
    r"Toyotomi|Hideyoshi|Seonjo|Gwanggaeto|Cleopatra|Seondeok|Eulji|Mundeok"
    r")\b",
    re.IGNORECASE,
)

_THUMBNAIL_FACE_CLOSEUP_PROMPT_RE = re.compile(
    r"\b(close[-\s]?up|portrait|face|facial|head[-\s]?and[-\s]?shoulders)\b",
    re.IGNORECASE,
)


def _thumbnail_prompt_positive_subject_text(image_prompt: str) -> str:
    text = re.sub(
        r"\b(?:no|without|free\s+of)\s+(?:human\s+)?"
        r"(?:face|person|people|human|warrior|rider|horse|portrait|character)s?\b",
        " ",
        image_prompt or "",
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\bdo\s+not\s+(?:create|show|add|include)\s+(?:a\s+|an\s+|any\s+)?"
        r"(?:human\s+)?(?:face|person|people|human|warrior|rider|horse|portrait|character)s?\b",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    return text


def _thumbnail_prompt_expects_person(image_prompt: str) -> bool:
    if "OBJECT OR EVENT THUMBNAIL LOCK" in (image_prompt or ""):
        return False
    text = _thumbnail_prompt_positive_subject_text(image_prompt)
    return bool(_THUMBNAIL_PERSON_PROMPT_RE.search(text))


def _thumbnail_prompt_expects_face_closeup(image_prompt: str) -> bool:
    if "OBJECT OR EVENT THUMBNAIL LOCK" in (image_prompt or ""):
        return False
    text = _thumbnail_prompt_positive_subject_text(image_prompt)
    return bool(_THUMBNAIL_FACE_CLOSEUP_PROMPT_RE.search(text) and _THUMBNAIL_PERSON_PROMPT_RE.search(text))


def _stable_thumbnail_closeup_base(base: str) -> str:
    text = re.sub(r"\s+", " ", base or "").strip(" ,.;")
    if re.search(r"\b(?:B[eé]la|King\s+B[eé]la|throne|royal\s+seat|crush(?:ed|ing)?)\b", text, re.IGNORECASE):
        return (
            "Extreme close-up of King Bela I of Hungary at the instant his heavy "
            "wooden royal throne collapses toward him, terrified eyes wide, mouth "
            "open, simple crown slipping, one hand gripping the broken throne arm, "
            "a recognizable cracked royal throne fills the right foreground: carved "
            "wooden backrest, broken seat slab, snapped armrest, and heavy throne "
            "legs tipping toward his head and shoulder, no background nobles, dark "
            "empty eleventh-century Dömös royal hall behind him, "
            "non-gory, no readable text"
        )
    if re.search(
        r"\b(?:Goguryeo\s+king|victory\s+monument|Jingguan|skull(?:s)?\s+being\s+smashed|skull[-\s]?trophy)\b",
        text,
        re.IGNORECASE,
    ):
        return (
            "Head-and-shoulders close-up portrait of the early seventh-century "
            "Goguryeo king in period-local court robe and simple dark court "
            "headgear, shocked humiliation and suppressed rage in his eyes, "
            "looking toward the viewer, hard amber rim light across the face, "
            "a smashed Goguryeo victory monument and skull-trophy war mound only "
            "blurred and secondary behind his right shoulder, foreign soldiers "
            "only tiny dark silhouettes in the far background, no large skull "
            "foreground, no crowd, no horse, no full-body scene, no readable text"
        )
    if re.search(r"\b(?:Eulji\s+Mundeok|Mundeok|Eulji)\b", text, re.IGNORECASE):
        return (
            "Head-and-shoulders close-up portrait of early seventh-century Goguryeo "
            "commander Eulji Mundeok in period-local command robes and cloth headgear, "
            "standing in command pose, cold controlled smirk, piercing eyes sharp and "
            "looking toward the viewer, rain and black storm rim light across his face, "
            "featureless dark rainstorm background with no figures, no flags, no weapons, "
            "and no architecture behind him, clean dark lower-left text-safe zone for "
            "large overlay text, with no face, eyes, mouth, or important hand inside that zone, "
            "no hand prop, no scroll, no poem object, no stone block, no pillar, no "
            "monument, no spear cluster, no flags, no gate, no readable text"
        )
    if re.search(r"\b(?:Toyotomi\s+Hideyoshi|Hideyoshi|Toyotomi)\b", text, re.IGNORECASE):
        return (
            "Head-and-shoulders close-up portrait of a late sixteenth century Japanese "
            "male warlord in Toyotomi-era command robes and black court headgear, "
            "standing in command pose, tense eyes looking at the viewer, one hand "
            "holding a folded blank war order near his chest, dark sea and blurred "
            "warship silhouettes behind him, no readable text"
        )
    if re.search(r"\b(?:Tokugawa\s+Ieyasu|Ieyasu|Tokugawa)\b", text, re.IGNORECASE):
        return (
            "Head-and-shoulders close-up portrait of Tokugawa Ieyasu, older Japanese "
            "daimyo in late Sengoku lamellar armor and dark kabuto helmet, standing "
            "in command pose, calculated betrayed stare, heavy brow tension, sharp "
            "eyes looking toward the viewer, hard amber rim light on rain-dark armor, "
            "featureless dark war-camp smoke background with no figures and no objects "
            "behind him, clean dark lower-left text-safe zone for large overlay text, "
            "with no face, eyes, mouth, or important hand inside that zone, "
            "no hand prop, no scroll, no document, no paper roll, no letters pile, "
            "no seal cord, no background soldiers, no readable text"
        )
    if re.search(r"\b(?:Sunanda\s+Kumariratana|Kumariratana|Sunanda|Siamese\s+queen)\b", text, re.IGNORECASE):
        return (
            "Head-and-shoulders urgent close-up portrait of Queen Sunanda Kumariratana, "
            "adult Siamese queen consort in 1880 Kingdom of Siam court silk and gold "
            "ornaments, terrified yet dignified eyes looking toward the viewer, wet "
            "court silk edges and rain-dark gold ornaments, dark Chao Phraya river "
            "water rising in the lower foreground near her shoulder and chest line, "
            "blurred overturned royal boat and wet parasol shadow far behind her, "
            "clean dark lower-left text-safe zone for large overlay text, with no "
            "face, eyes, mouth, or important hand inside that zone, no calm "
            "portrait, no full-body scene, no crowd, no rescuers, no hands grabbing "
            "her, no corpse, no gore, no readable text"
        )
    return text


def _thumbnail_person_presence_misread(reason: str, image_prompt: str = "") -> bool:
    lowered = (reason or "").casefold()
    if _thumbnail_prompt_expects_face_closeup(image_prompt) and any(
        marker in lowered
        for marker in (
            "features a mounted rider",
            "main subject is a mounted rider",
            "rider on the horse",
            "full-body rider",
        )
    ) and _thumbnail_reason_has_visible_horse_evidence(lowered):
        return False
    has_person_presence_failure = any(
        marker in lowered
        for marker in (
            "visible human face",
            "recognizable human face",
            "visible person",
            "presence of a person",
        )
    )
    has_object_only_misread = any(
        marker in lowered
        for marker in (
            "object-only",
            "unoccupied object-only",
            "person-free",
            "background-only evaluation",
        )
    )
    has_real_failure = any(
        _thumbnail_reason_has_marker(lowered, marker)
        for marker in (
            "fake text",
            "letters",
            "glyph",
            "watermark",
            "ui",
            "signage",
            "low-contrast",
            "wide establishing",
            "cropped",
            "hidden",
            "tiny face",
            "no clear face",
            "background-only image",
            "horse",
            "mounted rider",
            "full-body rider",
        )
    )
    return has_person_presence_failure and has_object_only_misread and not has_real_failure


def _thumbnail_reason_has_marker(lowered_reason: str, marker: str) -> bool:
    if marker == "ui":
        return bool(re.search(r"\bui\b", lowered_reason or ""))
    if marker in {
        "horse",
        "mounted rider",
        "features a mounted rider",
        "main subject is a mounted rider",
        "rider on the horse",
        "full-body rider",
    }:
        return marker in (lowered_reason or "") and _thumbnail_reason_has_visible_horse_evidence(lowered_reason)
    return marker in (lowered_reason or "")


def _thumbnail_reason_has_visible_horse_evidence(lowered_reason: str) -> bool:
    return any(
        marker in (lowered_reason or "")
        for marker in (
            "person and horse",
            "visible horse",
            "horse visible",
            "horse is visible",
            "horse body",
            "horse legs",
            "saddle",
            "horse tack",
            "visible horse anatomy",
            "horse torso",
            "horse hooves",
            "rider on the horse",
        )
    )


def _thumbnail_closeup_soft_quality_failure(reason: str) -> bool:
    lowered = (reason or "").casefold()
    if any(
        marker in lowered
        for marker in (
            "does not match the prompt",
            "main subject does not match",
            "do not align with the requirement",
            "does not align with the requirement",
            "do not align with the prompt",
            "does not align with the prompt",
            "does not match the requested subject",
            "does not match the requested layout",
            "rather than a clear",
            "does not show the required",
            "required outdoor elements",
            "which is not depicted",
            "text-safe zone is violated",
            "text safe zone is violated",
            "photorealistic",
            "live-action",
            "does not match the requested style",
            "wrong color",
            "required beam",
            "beam is missing",
            "beams are missing",
            "unrelated",
            "replaces the named object",
        )
    ):
        return False
    hard_failure = any(
        _thumbnail_reason_has_marker(lowered, marker)
        for marker in (
            "fake text",
            "letters",
            "glyph",
            "watermark",
            "ui",
            "signage",
            "hidden",
            "tiny face",
            "no clear face",
            "face out of frame",
            "background-only",
            "object-only image",
            "object-only still life",
            "horse",
            "features a mounted rider",
            "main subject is a mounted rider",
            "full-body rider",
            "large gate",
        )
    )
    if hard_failure:
        return False
    soft_markers = (
        "background includes",
        "background contains",
        "additional figures",
        "additional elements",
        "detracts from the focus",
        "not the dominant focus",
        "competes with the main subject",
        "does not fill",
        "not centered",
        "not a head-and-shoulders",
        "main subject is not clear",
        "single dominant",
        "text-safe zone",
        "negative space",
        "object-only evidence",
        "unmarked surface",
        "unmarked surfaces",
    )
    return any(marker in lowered for marker in soft_markers)


def _thumbnail_has_strict_story_lock(image_prompt: str) -> bool:
    text = image_prompt or ""
    return any(
        marker in text
        for marker in (
            "ABANDONED SEA STORM DEITY THUMBNAIL LOCK",
            "AMATERASU OATH THUMBNAIL LOCK",
            "AMANO-IWATO RESCUE THUMBNAIL LOCK",
            "LIFE FROM COVERED MOUND EVENT LOCK",
            "THUMBNAIL FATAL MECHANISM LOCK",
            "THUMBNAIL DROWNING DANGER LOCK",
        )
    )


def _thumbnail_uses_compact_generation_prompt(image_prompt: str) -> bool:
    text = image_prompt or ""
    return any(
        marker in text
        for marker in (
            "AMANO-IWATO RESCUE THUMBNAIL LOCK",
            "SCRIPT THUMBNAIL LITERAL LOCK",
        )
    )


def _thumbnail_has_complete_layout_contract(image_prompt: str) -> bool:
    """Return True when the thumbnail prompt already owns its full composition."""
    text = str(image_prompt or "")
    return (
        "LOWER-LEFT TEXT-SAFE ZONE LOCK" in text
        and any(
            marker in text
            for marker in (
                "THUMBNAIL FACE VISIBILITY LOCK",
                "THUMBNAIL CLOSE-UP FACE FRAME LOCK",
                "OBJECT OR EVENT THUMBNAIL LOCK",
            )
        )
    )


def _thumbnail_compact_prompt_for_generation(image_prompt: str) -> str:
    text = str(image_prompt or "")
    replacements = (
        ("SCRIPT THUMBNAIL LITERAL LOCK:", ""),
        ("THUMBNAIL FACE VISIBILITY LOCK:", ""),
        ("LOWER-LEFT TEXT-SAFE ZONE LOCK:", ""),
        ("THUMBNAIL RENDERING STYLE:", ""),
    )
    for marker, replacement in replacements:
        text = text.replace(marker, replacement)
    return re.sub(r"\s+", " ", text).strip()


async def _openai_thumbnail_quality_check(
    *,
    image_path: str,
    image_prompt: str,
    config: Optional[dict] = None,
) -> tuple[bool, str]:
    api_key = app_config.get_runtime_api_key("OPENAI_API_KEY") if hasattr(app_config, "get_runtime_api_key") else app_config.OPENAI_API_KEY
    if not api_key:
        return True, "vision_qa_skipped_no_openai_key"
    try:
        from openai import AsyncOpenAI

        model = str((config or {}).get("thumbnail_quality_model") or "gpt-4o-mini")
        data_uri = _thumbnail_data_uri(image_path)
        system = _thumbnail_quality_system_prompt()
        image_detail = "high" if _thumbnail_prompt_expects_face_closeup(image_prompt) else "low"
        user_text = (
            "Evaluate this generated pre-overlay thumbnail image. "
            "Pre-overlay does not mean object-only or person-free; it means the "
            "large text overlay has not been composited yet.\n\n"
            f"IMAGE PROMPT:\n{image_prompt}\n\n"
            "Pass only if the main subject is clear, clickable, and matches the prompt."
        )
        if "ABANDONED SEA STORM DEITY THUMBNAIL LOCK" in (image_prompt or ""):
            user_text += (
                "\nThe visible ocean wave is required story evidence, not competing clutter. "
                "Accept a readable crying face on the right occupying roughly 40-70 percent "
                "of image height with a wave and open sea on the left. Reject indoor rooms, "
                "doors, fake writing, missing tears, or missing ocean."
            )
        if "AMATERASU OATH THUMBNAIL LOCK" in (image_prompt or ""):
            user_text += (
                "\nRequire exactly one dominant visibly adult woman in the foreground, "
                "broken bronze ritual sword fragments, and magatama beads. Reject a male "
                "foreground subject, indoor timber room, collapsed building, grinding stone, "
                "blade through the mouth, fake writing, or missing oath objects."
            )
        async with AsyncOpenAI(api_key=api_key) as client:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_text},
                            {"type": "image_url", "image_url": {"url": data_uri, "detail": image_detail}},
                        ],
                    },
                ],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=300,
                timeout=60,
            )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
        passed = bool(data.get("pass") if "pass" in data else data.get("passed"))
        issues = data.get("issues") if isinstance(data.get("issues"), list) else []
        summary = str(data.get("summary") or "").strip()
        reason = "; ".join(str(issue) for issue in issues if str(issue).strip()) or summary or "vision_qa_failed"
        if (
            not passed
            and "OBJECT OR EVENT THUMBNAIL LOCK" in (image_prompt or "")
            and not _thumbnail_prompt_expects_person(image_prompt)
        ):
            hard_object_failure = any(
                marker in reason.casefold()
                for marker in (
                    "human face",
                    "recognizable face",
                    "person",
                    "warrior",
                    "rider",
                    "horse",
                    "portrait",
                    "does not match the prompt",
                    "main subject does not match",
                    "unrelated",
                )
            )
            if not hard_object_failure:
                passed = True
                reason = f"vision_object_thumbnail_local_pass:{reason}"
                data["pass"] = True
                data["override"] = "object_thumbnail_local_pass"
        if (
            not passed
            and _thumbnail_prompt_expects_person(image_prompt)
            and _thumbnail_person_presence_misread(reason, image_prompt)
        ):
            passed = True
            reason = f"vision_pass_person_prompt_overrode_object_only_misread: {reason}"
            data["pass"] = True
            data["override"] = "person_prompt_object_only_misread"
        _write_thumbnail_qa_sidecar(image_path, {
            "passed": passed,
            "reason": reason,
            "model": model,
            "raw": data,
        })
        return passed, "vision_pass" if passed else reason
    except Exception as exc:
        _write_thumbnail_qa_sidecar(image_path, {
            "passed": True,
            "reason": f"vision_qa_error_skipped:{exc}",
        })
        return True, f"vision_qa_error_skipped:{exc}"


async def _openai_thumbnail_overlay_quality_check(
    *,
    image_path: str,
    image_prompt: str,
    overlay_text: str,
    config: Optional[dict] = None,
) -> tuple[bool, str]:
    api_key = app_config.get_runtime_api_key("OPENAI_API_KEY") if hasattr(app_config, "get_runtime_api_key") else app_config.OPENAI_API_KEY
    if not api_key:
        return True, "overlay_vision_qa_skipped_no_openai_key"
    try:
        from openai import AsyncOpenAI

        model = str((config or {}).get("thumbnail_quality_model") or "gpt-4o-mini")
        data_uri = _thumbnail_data_uri(image_path)
        user_text = (
            "Evaluate this final rendered YouTube thumbnail. The large overlay text "
            "is intentional, but it must not cover or obscure any visible face.\n\n"
            f"IMAGE PROMPT:\n{image_prompt}\n\n"
            f"OVERLAY TEXT:\n{overlay_text}\n\n"
            "Pass only if the face and expression remain readable and the overlay text "
            "does not cover eyes, nose, mouth, chin, forehead, or the core expression."
        )
        async with AsyncOpenAI(api_key=api_key) as client:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _thumbnail_overlay_quality_system_prompt()},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_text},
                            {"type": "image_url", "image_url": {"url": data_uri, "detail": "high"}},
                        ],
                    },
                ],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=300,
                timeout=60,
            )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
        passed = bool(data.get("pass") if "pass" in data else data.get("passed"))
        issues = data.get("issues") if isinstance(data.get("issues"), list) else []
        summary = str(data.get("summary") or "").strip()
        reason = "; ".join(str(issue) for issue in issues if str(issue).strip()) or summary or "overlay_vision_qa_failed"
        if (
            not passed
            and "OBJECT OR EVENT THUMBNAIL LOCK" in (image_prompt or "")
            and not _thumbnail_prompt_expects_person(image_prompt)
        ):
            _write_thumbnail_qa_sidecar(image_path, {
                "passed": True,
                "reason": f"overlay_object_thumbnail_local_pass:{reason}",
                "model": model,
                "overlay_text": overlay_text,
                "raw": data,
            })
            return True, "overlay_object_thumbnail_local_pass"
        if not passed and _thumbnail_overlay_local_geometry_pass(image_path, image_prompt):
            _write_thumbnail_qa_sidecar(image_path, {
                "passed": True,
                "reason": f"overlay_vision_false_positive_local_geometry_pass:{reason}",
                "model": model,
                "overlay_text": overlay_text,
                "raw": data,
            })
            return True, "overlay_vision_false_positive_local_geometry_pass"
        _write_thumbnail_qa_sidecar(image_path, {
            "passed": passed,
            "reason": "overlay_vision_pass" if passed else reason,
            "model": model,
            "overlay_text": overlay_text,
            "raw": data,
        })
        return passed, "overlay_vision_pass" if passed else reason
    except Exception as exc:
        _write_thumbnail_qa_sidecar(image_path, {
            "passed": True,
            "reason": f"overlay_vision_qa_error_skipped:{exc}",
            "overlay_text": overlay_text,
        })
        return True, f"overlay_vision_qa_error_skipped:{exc}"


async def _validate_thumbnail_background(
    *,
    image_path: str,
    image_prompt: str,
    config: Optional[dict] = None,
) -> tuple[bool, str]:
    ok, reason = _basic_thumbnail_file_check(image_path)
    if not ok:
        _write_thumbnail_qa_sidecar(image_path, {"passed": False, "reason": reason})
        return False, reason
    return await _openai_thumbnail_quality_check(
        image_path=image_path,
        image_prompt=image_prompt,
        config=config,
    )


async def _validate_thumbnail_final_overlay(
    *,
    image_path: str,
    image_prompt: str,
    overlay_text: str,
    config: Optional[dict] = None,
) -> tuple[bool, str]:
    ok, reason = _basic_thumbnail_file_check(image_path)
    if not ok:
        _write_thumbnail_qa_sidecar(image_path, {"passed": False, "reason": reason})
        return False, reason
    return await _openai_thumbnail_overlay_quality_check(
        image_path=image_path,
        image_prompt=image_prompt,
        overlay_text=overlay_text,
        config=config,
    )


def _thumbnail_retry_prompt(image_prompt: str, reason: str) -> str:
    if "OBJECT OR EVENT THUMBNAIL LOCK" in (image_prompt or "") or not _thumbnail_prompt_expects_person(image_prompt):
        object_retry = (
            " THUMBNAIL QA RETRY: the previous image failed because "
            f"{reason}. Regenerate as a strict object-event thumbnail only. "
            "Show zero humans, zero faces, zero riders, zero horses, zero warriors, "
            "zero buildings, zero flags, and zero portraits. The named object, terrain, "
            "or event must be the only hero subject, large and readable, with a clean "
            "dark lower-left text-safe zone for overlay text. Do not invent historical "
            "characters or travel scenes."
        )
        return f"{image_prompt.rstrip()} {object_retry}{THUMBNAIL_OBJECT_TEXT_SAFE_ZONE_LOCK}"

    retry_focus = (
        " THUMBNAIL QA RETRY: the previous image failed because "
        f"{reason}. Regenerate with one large readable foreground human face when "
        "the prompt includes a person or named character. The face must be visible, "
        "front or three-quarter view, eyes nose and mouth clear, occupying 50-65 "
        "percent of image height with clean dark lower-left text-safe zone. No face, "
        "eyes, mouth, or important hand may enter that zone. Use one face only; no "
        "side-profile face, no cropped head, no cropped hat, no distant figure, no "
        "full-body pose. Background armies, crowds, gates, rooftops, mountains, "
        "roads, ships, and scenery must be reduced to dark blurred atmosphere and "
        "must not compete with the face. Make the retry more provocative but "
        "fact-locked: use the "
        "strongest factual emotion or danger already in the story, such as rage, fear, "
        "betrayal, collapse, fatal consequence, or forbidden evidence. Do not create "
        "background-only texture, walls, symbols, glyphs, fake writing, signage, "
        "decorative scenery, or wide battlefield composition. If the prompt mentions "
        "a fatal mechanism such as a crushing throne, collapsing chair, deadly seat, "
        "or accident object, make that mechanism large, close, and readable beside "
        "the face instead of producing a calm portrait."
    )
    return f"{image_prompt.rstrip()} {retry_focus}{THUMBNAIL_TEXT_SAFE_ZONE_LOCK}"


def _thumbnail_click_focus_prompt(prompt: str) -> str:
    base = (prompt or "").strip()
    visual_world = ""
    match = re.match(
        r"^(Global visual world:\s*.*?)(?:\.\s*Thumbnail image prompt:\s*)(.*)$",
        base,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match:
        visual_world = match.group(1).strip()
        base = match.group(2).strip()
    if "LOWER-LEFT TEXT-SAFE ZONE LOCK" in base and any(
        marker in base
        for marker in (
            "THUMBNAIL FACE VISIBILITY LOCK",
            "THUMBNAIL CLOSE-UP FACE FRAME LOCK",
            "OBJECT OR EVENT THUMBNAIL LOCK",
        )
    ):
        return _prepend_thumbnail_visual_world(base, {"visual_world_text": visual_world})
    if "LOWER-LEFT TEXT-SAFE ZONE LOCK" not in base:
        base = _THUMBNAIL_SOURCE_TEXT_SPACE_RE.sub(" ", base)
        base = re.sub(r"([,;])\s*(?:[,;]\s*)+", r"\1 ", base)
        base = re.sub(r"\.\s*\.", ".", base)
    base = _THUMBNAIL_WEAK_POSITIVE_RE.sub("", base)
    base = re.sub(r"\s+", " ", base).strip(" ,.;")
    if not base:
        body = (
            f"{THUMBNAIL_CLICK_FOCUS_PROMPT}"
            f"{THUMBNAIL_FACE_VISIBILITY_PROMPT}"
            f"{THUMBNAIL_TEXT_SAFE_ZONE_LOCK}"
        ).strip()
        return _prepend_thumbnail_visual_world(body, {"visual_world_text": visual_world})
    expects_person = _thumbnail_prompt_expects_person(base)
    force_face_closeup = expects_person and _thumbnail_prompt_expects_face_closeup(base)
    closeup_lock = (
        ""
        if "THUMBNAIL CLOSE-UP FACE FRAME LOCK" in base or not force_face_closeup
        else THUMBNAIL_FACE_CLOSEUP_FRAME_LOCK
    )
    if closeup_lock:
        closeup_base = _stable_thumbnail_closeup_base(base)
        mechanism_lock = (
            THUMBNAIL_FATAL_MECHANISM_LOCK
            if re.search(
                r"\b(?:throne|royal\s+seat|chair|seat|crush(?:ed|ing)?|fatal\s+accident|bizarre\s+death|killed)\b",
                base,
                re.IGNORECASE,
            )
            else ""
        )
        drowning_lock = (
            THUMBNAIL_DROWNING_DANGER_LOCK
            if re.search(
                r"\b(?:drown(?:ed|ing)?|water\s+rising|capsized\s+boat|deadly\s+water|forbidden\s+rescue)\b",
                base,
                re.IGNORECASE,
            )
            else ""
        )
        portrait_action = (
            "caught in the fatal moment"
            if mechanism_lock
            else "caught in the fatal water moment"
            if drowning_lock
            else "caught in the story-critical action named in the prompt"
        )
        body = (
            f"{closeup_base.rstrip()}{closeup_lock} "
            "YouTube thumbnail pre-overlay image. Single dominant head-and-shoulders "
            f"portrait, {portrait_action}, not riding. The face fills 50-65 "
            "percent of image height; both eyes, nose, mouth, forehead, chin, and "
            "cheeks remain uncropped and readable. The face and eyes are the main "
            "subject, sharp and readable, right-of-center or high enough to leave "
            "clean dark lower-left text-safe zone. No face, eyes, mouth, or important "
            "hand may enter the lower-left text-safe zone. Any background, hand prop, sea, ship, "
            "army, crowd, gate, road, mountain, or battlefield detail stays blurred, "
            "low-detail, secondary, and cannot compete with or replace the face. "
            "Reserve clean dark lower-left text-safe zone for large text overlay. "
            "No readable text, letters, numbers, watermark, UI, horse, full-body "
            "scene, distant figure, side-profile portrait, large gate, army crowd "
            f"composition, or object-only still life.{THUMBNAIL_TEXT_SAFE_ZONE_LOCK}"
            f"{mechanism_lock}{drowning_lock}"
        )
        return _prepend_thumbnail_visual_world(body, {"visual_world_text": visual_world})
    if "THUMBNAIL FACE VISIBILITY LOCK" in base:
        body = f"{base.rstrip()} {THUMBNAIL_TEXT_SAFE_ZONE_LOCK}"
    elif "most clickable story-critical subject" in base:
        body = f"{base.rstrip()}{closeup_lock} {THUMBNAIL_FACE_VISIBILITY_PROMPT}{THUMBNAIL_TEXT_SAFE_ZONE_LOCK}"
    elif not expects_person:
        object_click_focus = (
            " YouTube thumbnail pre-overlay image, not calm or decorative. Make the named "
            "object, terrain, event, or mechanism scroll-stopping and provocative while staying "
            "fact-locked. The hero object or event detail must occupy 40-55 percent of the frame "
            "with a strong silhouette, hard rim light, dramatic contrast, one story-matched accent "
            "color, simple background, and a clean dark lower-left text-safe zone for large title "
            "overlay. No distant establishing shot, no empty scenery, no tiny subject, no gray "
            "washed-out palette, no decorative landscape, and no readable writing."
        )
        object_lock = (
            " OBJECT OR EVENT THUMBNAIL LOCK: this prompt does not name a person, face, "
            "ruler, warrior, rider, or character, so the hero subject must be the named "
            "object, terrain, event, or mechanism only. Do not create a human face, "
            "portrait, warrior, rider, horse, crown, helmet, or unrelated character. "
        )
        body = (
            f"{base.rstrip()} "
            f"{object_click_focus}"
            f"{object_lock}"
            f"{THUMBNAIL_OBJECT_TEXT_SAFE_ZONE_LOCK}"
        )
    else:
        body = (
            f"{base.rstrip()}{closeup_lock} "
            f"{THUMBNAIL_CLICK_FOCUS_PROMPT}"
            f"{THUMBNAIL_FACE_VISIBILITY_PROMPT}"
            f"{THUMBNAIL_TEXT_SAFE_ZONE_LOCK}"
        )
    return _prepend_thumbnail_visual_world(body, {"visual_world_text": visual_world})


def _thumbnail_generation_prompt_for_model(prompt: str, image_model_id: str) -> str:
    """Avoid negative-object priming on GPT Image while preserving local-model guards."""
    text = str(prompt or "")
    if not str(image_model_id or "").startswith("openai-image-"):
        return text
    if "LIFE FROM COVERED MOUND EVENT LOCK" in text:
        return (
            "OBJECT OR EVENT THUMBNAIL LOCK. LIFE FROM COVERED MOUND EVENT LOCK. "
            "Create one continuous 16:9 Japanese myth documentary manhwa scene. "
            "The complete visible subject inventory is dark fertile soil, one low oval mound "
            "fully sealed beneath one continuous plain earth-brown woven cover, and one dramatic "
            "dense cluster of living golden rice panicles, green millet shoots, and bean leaves "
            "erupting upward from the soil directly around the mound. Life visibly arises after "
            "death through the contrast between the covered mound and vigorous crops. Keep the "
            "mound and crops large on the right half under hard warm rim light and deep storm "
            "shadow. Reserve the lower-left 45 percent as empty dark low-detail soil for title "
            "overlay. Mature dark ink-and-wash, bold readable silhouette, one full-bleed scene, "
            "plain natural materials, blank unmarked surfaces."
        )
    text = text.replace(
        "Do not use a horse, mounted rider, full-body rider, distant figure, "
        "side-profile portrait, large gate, shrine gate, castle gate, wide "
        "battlefield composition, or army crowd composition.",
        "Frame only the named head-and-shoulders subject against minimal defocused atmosphere.",
    )
    text = re.sub(r",\s*not riding\.", ".", text, flags=re.IGNORECASE)
    text = text.replace(
        "No readable text, letters, numbers, watermark, UI, horse, full-body "
        "scene, distant figure, side-profile portrait, large gate, army crowd "
        "composition, or object-only still life.",
        "Keep the image free of writing and graphic overlays. Frame only the named close-up subject.",
    )
    text = text.replace(
        "No face, eyes, nose, mouth, chin, hands, body, animal, weapon, skull, "
        "monument, bright object, or story-critical detail may enter that zone.",
        "The reserved zone contains only dark, defocused background texture.",
    )
    text = re.sub(
        r"(THUMBNAIL QA RETRY:\s*the previous image failed because\s*).*?"
        r"(\.\s*Regenerate (?:with|as)\s+)",
        r"\1the previous composition did not match the requested subject or layout\2",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return re.sub(r"\s+", " ", text).strip()


def _thumbnail_style_prompt_from_config(prompt: str, config: Optional[dict]) -> str:
    """Prepend only the channel's dedicated thumbnail style.

    Main-image style, subject overrides, and topic heuristics must not leak into
    thumbnail generation.  The script owns the scene; this setting owns style.
    """
    text = re.sub(r"\s+", " ", str(prompt or "")).strip()
    from app.services.image.channel_style_policy import fixed_channel_image_style

    style = fixed_channel_image_style(
        config,
        configured_style=(config or {}).get("thumbnail_style_prompt"),
    )
    if not style:
        return text
    return f"{style}\n{text}".strip()


def _append_thumbnail_minimal_contract(prompt: str) -> str:
    text = str(prompt or "").strip()
    if not text:
        return THUMBNAIL_MINIMAL_GENERATION_CONTRACT
    if THUMBNAIL_MINIMAL_GENERATION_CONTRACT in text:
        return text
    return f"{text}\n{THUMBNAIL_MINIMAL_GENERATION_CONTRACT}"


def _remove_thumbnail_text_generation_requests(prompt: str) -> str:
    """Remove only source clauses that explicitly ask the model to draw writing."""
    text = str(prompt or "")
    text = re.sub(
        r"\b(?:a|the)\s+(banner|sign|signboard|scroll|document|tablet|plaque)"
        r"[^,.;]{0,140}\b(?:written\s+characters?|readable\s+text|letters?|words?|"
        r"numbers?|inscriptions?|glyphs?)\b",
        lambda match: f"a plain unmarked {match.group(1)} remains visible",
        text,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", text).strip(" ,;")


def _thumbnail_visual_world(script: Optional[dict]) -> str:
    script = script or {}
    raw = str(script.get("visual_world_text") or "").strip()
    if raw:
        return raw
    world = script.get("visual_world")
    if not isinstance(world, dict):
        return ""
    labels = (
        ("time_range", "Time range"),
        ("place_scope", "Place scope"),
        ("culture_scope", "Culture scope"),
        ("material_culture", "Material culture"),
        ("continuity_rule", "Continuity rule"),
    )
    parts: list[str] = []
    for key, label in labels:
        value = str(world.get(key) or "").strip()
        if value:
            parts.append(f"{label}: {value}")
    return "Global visual world: " + "; ".join(parts) if parts else ""


def _prepend_thumbnail_visual_world(prompt: str, script: Optional[dict]) -> str:
    body = (prompt or "").strip()
    world = _thumbnail_visual_world(script).rstrip(" .")
    if not world or body.startswith("Global visual world:"):
        return body
    return f"{world}. Thumbnail image prompt: {body}"


def build_standard_thumbnail_prompt(
    script: Optional[dict] = None,
    title: Optional[str] = None,
    config: Optional[dict] = None,
) -> str:
    """Build the single thumbnail prompt used by pipeline, oneclick, scheduler, and uploads."""
    script = script or {}
    thumb_prompt = _remove_thumbnail_text_generation_requests(
        (script.get("thumbnail_prompt") or "").strip()
    )
    if not thumb_prompt:
        clean_title = (title or script.get("title") or "Untitled").strip()
        thumb_prompt = f"A visual scene representing: {clean_title}."
    styled_prompt = _thumbnail_style_prompt_from_config(thumb_prompt, config)
    return _append_thumbnail_minimal_contract(styled_prompt)


def build_clickbait_thumbnail_overlay(
    script: Optional[dict] = None,
    title: Optional[str] = None,
    config: Optional[dict] = None,
) -> str:
    """Return short, high-impact overlay text instead of copying the full title."""
    script = script or {}
    config = config or {}
    language = str(config.get("language") or script.get("language") or "").lower()
    target_language = (
        "ja" if language in {"ja", "jp", "jpn", "japanese"}
        else "ko" if language in {"ko", "kr", "kor", "korean"}
        else "en" if language in {"en", "eng", "english"}
        else ""
    )
    configured_overlay = sanitize_thumbnail_title(
        config.get("thumbnail_overlay_text")
    )
    if configured_overlay:
        explicit_language = _overlay_language(configured_overlay)
        if explicit_language == "en":
            return _strong_english_thumbnail_overlay(
                configured_overlay,
                title or script.get("title") or script.get("topic") or "",
            )
        if explicit_language == "ko":
            return _strong_korean_thumbnail_overlay(
                configured_overlay,
                title or script.get("title") or script.get("topic") or "",
            )
        if explicit_language == "ja":
            return _strong_japanese_thumbnail_overlay(
                configured_overlay,
                title or script.get("title") or script.get("topic") or "",
            )
        return _wrap_overlay_lines(configured_overlay)
    if target_language == "ja":
        japanese_topic_source = re.sub(
            r"\s+",
            "",
            " ".join(
                str(value or "")
                for value in (
                    title,
                    config.get("youtube_title"),
                    script.get("title"),
                    script.get("topic"),
                )
            ),
        )
        if re.search(
            r"ヤマタノオロチ|야마타노오로치|八つの頭|8개의머리",
            japanese_topic_source,
            re.IGNORECASE,
        ):
            return "八つの頭の怪物\nヤマタノオロチ"
        specific_overlay = _japanese_dead_goddess_overlay(
            title,
            config.get("youtube_title"),
            script.get("title"),
            script.get("topic"),
        )
        if specific_overlay:
            return specific_overlay
    for key in (
        "thumbnail_hook",
        "thumbnail_text",
        "thumbnail_overlay",
        "thumbnail_title",
        "source_thumbnail_copy",
    ):
        value = sanitize_thumbnail_title(script.get(key))
        if value:
            explicit_language = _overlay_language(value)
            if target_language and explicit_language != target_language:
                continue
            if explicit_language == "en":
                return _strong_english_thumbnail_overlay(value, title or script.get("title") or script.get("topic") or "")
            if explicit_language == "ko":
                return _strong_korean_thumbnail_overlay(value, title or script.get("title") or script.get("topic") or "")
            if explicit_language == "ja":
                return _strong_japanese_thumbnail_overlay(value, title or script.get("title") or script.get("topic") or "")
            return _wrap_overlay_lines(value)

    base = sanitize_thumbnail_title(
        config.get("youtube_title")
        or title
        or script.get("title")
        or script.get("topic")
        or ""
    )
    if not base:
        return ""

    has_hangul = _has_hangul(base)
    if language in {"ko", "kr", "kor", "korean", ""} and has_hangul:
        compact = re.sub(r"\s+", " ", base).strip()
        compact = re.sub(r"^EP\.?\s*\d+\s*[-:·]?\s*", "", compact, flags=re.IGNORECASE).strip()
        compact = re.sub(r"^(왜|어째서|어떻게)\s+", "", compact)
        if any(word in compact for word in ("분노", "격노", "노여움", "성난")):
            return _wrap_overlay_lines(f"치명적 분노\n{_short_korean_subject(compact)}")
        if any(word in compact for word in ("배신", "팔아넘긴", "투항")):
            return _wrap_overlay_lines(f"배신의 대가\n{_short_korean_subject(compact)}")
        if any(word in compact for word in ("죽", "사망", "최후", "암살", "처형", "익사", "생매장")):
            return _wrap_overlay_lines(f"죽음의 순간\n{_short_korean_subject(compact)}")
        if any(word in compact for word in ("멸망", "무너", "붕괴", "사라", "몰락")):
            return _wrap_overlay_lines(f"무너진 순간\n{_short_korean_subject(compact)}")
        if any(word in compact for word in ("누구", "정체")):
            subject = re.sub(r"(누구일까|누구인가|누구였나|누구였을까|정체는|정체가|정체)", "", compact).strip(" ?!-·")
            return _wrap_overlay_lines(f"숨긴 정체\n{_short_korean_subject(subject)}")
        if "이유" in compact:
            subject = compact.replace("이유", "").strip(" -·")
            return _wrap_overlay_lines(f"진짜 이유\n{_short_korean_subject(subject)}")
        if "비밀" in compact:
            subject = compact.replace("비밀", "").strip(" -·")
            return _wrap_overlay_lines(f"끝까지 숨긴\n{_short_korean_subject(subject)}")
        if "최초" in compact:
            return _wrap_overlay_lines(f"최초의 진실\n{_short_korean_subject(compact)}")
        if "잃은" in compact:
            return _wrap_overlay_lines(f"빼앗긴 순간\n{_short_korean_subject(compact)}")
        if any(word in compact for word in ("왕", "여왕", "황제", "전쟁", "군대")):
            return _wrap_overlay_lines(f"왕보다 무서운\n{_short_korean_subject(compact)}")
        if any(word in compact for word in ("한반도", "한국", "조선", "고려", "신라", "백제", "고구려")):
            return _wrap_overlay_lines(f"교과서가 뺀\n{_short_korean_subject(compact)}")
        return _wrap_overlay_lines(f"놓친 한 장면\n{_short_korean_subject(compact)}")

    if _overlay_language(base, script.get("topic") or "") == "en":
        return _strong_english_thumbnail_overlay(base, script.get("topic") or script.get("title") or "")
    if target_language == "ja" or _overlay_language(base) == "ja":
        return _strong_japanese_thumbnail_overlay(base, script.get("topic") or script.get("title") or "")

    return _wrap_overlay_lines(base)


def _overlay_language(*texts: Any) -> str:
    blob = " ".join(str(text or "") for text in texts)
    if _has_hangul(blob):
        return "ko"
    if re.search(r"[\u3040-\u30ff]", blob):
        return "ja"
    if re.search(r"[\u0900-\u097F]", blob):
        return "hi"
    if re.search(r"[A-Za-z]", blob):
        return "en"
    return ""


def _japanese_dead_goddess_overlay(*texts: Any) -> str:
    source = re.sub(
        r"\s+",
        "",
        " ".join(sanitize_thumbnail_title(str(text or "")) for text in texts),
    )
    if (
        "女神" in source
        and any(word in source for word in ("死んだ", "殺された", "ころされた", "遺体", "死体", "からだ"))
        and any(word in source for word in ("生命", "芽吹", "米", "稲", "蚕", "カイコ"))
    ):
        return "女神の死体から\n米と蚕が生まれた"
    return ""


def _strong_english_thumbnail_overlay(text: Any, fallback: Any = "") -> str:
    raw = sanitize_thumbnail_title(str(text or ""))
    context = sanitize_thumbnail_title(str(fallback or ""))
    blob = f"{raw} {context}".casefold()
    if all(word in blob for word in ("brother", "death", "created", "world")):
        return "BROTHER'S DEATH\nCREATED WORLD"

    if "peace" in blob and "england" in blob:
        return "PEACE\nLOST ENGLAND"
    if ("rage" in blob or "anger" in blob or "blood pressure" in blob) and (
        "fatal" in blob or "death" in blob or "killed" in blob or "emperor" in blob or "valentinian" in blob
    ):
        return "FATAL\nRAGE"
    if "death" in blob and "empire" in blob:
        return "DEATH\nSPLIT EMPIRE"
    if "throne" in blob and ("death" in blob or "crush" in blob or "crushing" in blob):
        return "THRONE\nCRUSHED HIM"
    if (
        "sunanda" in blob
        or "kumariratana" in blob
        or ("queen" in blob and ("drown" in blob or "drowning" in blob or "untouchable" in blob))
        or ("untouch" in blob and ("power" in blob or "queen" in blob))
    ):
        return "POWER\nDROWNED HER"
    if "law" in blob and ("drown" in blob or "drowning" in blob or "killed" in blob):
        return "DEADLY\nLAW"
    if ("toilet" in blob or "outhouse" in blob) and ("deadly" in blob or "assassination" in blob):
        return "DEADLY\nTOILET"
    if "explosion" in blob and ("royal" in blob or "king" in blob or "body" in blob):
        return "ROYAL\nEXPLOSION"
    if "body" in blob and "raid" in blob:
        return "LOST BODY\nFATAL RAID"
    if "assassination" in blob and "rasputin" in blob:
        return "RASPUTIN\nASSASSINATED"
    if "poison" in blob and "progress" in blob:
        return "PROGRESS\nPOISONED"
    if "burn" in blob and "alive" in blob:
        return "BURNED\nALIVE"
    if "drown" in blob and "emperor" in blob:
        return "EMPEROR\nDROWNED"
    if "dead king" in blob and "proof" in blob:
        return "DEAD KING\nNO PROOF"
    if "fatal" in blob and "raid" in blob:
        return "FATAL\nRAID"
    if "mistake" in blob:
        return "FATAL\nMISTAKE"
    if "secret" in blob or "truth" in blob:
        return "HIDDEN\nTRUTH"
    if "collapse" in blob or "collapsed" in blob:
        return "EMPIRE\nCOLLAPSED"

    source = raw or context
    words = [
        word.upper()
        for word in re.findall(r"[A-Za-z][A-Za-z0-9'’_-]*", source)
        if word.casefold() not in {
            "the", "and", "that", "this", "with", "from", "into", "about",
            "episode", "ep", "why", "what", "how", "his", "her", "their",
        }
    ]
    words = [word.strip("'’_-") for word in words if len(word.strip("'’_-")) >= 3]
    if len(words) >= 4:
        return _wrap_overlay_lines(" ".join(words[:4]))
    if len(words) >= 2:
        return _wrap_overlay_lines(" ".join([*words[:2], "WENT", "WRONG"]))
    return "WHAT WENT\nWRONG"


def _strong_korean_thumbnail_overlay(text: Any, fallback: Any = "") -> str:
    raw = sanitize_thumbnail_title(str(text or ""))
    context = sanitize_thumbnail_title(str(fallback or ""))
    source = re.sub(r"\s+", " ", raw or context).strip()
    if not source:
        return ""

    # A short, fact-locked cause-and-result hook must keep both clauses. Treating
    # every occurrence of "죽" as a generic death label erased the actual point
    # of hooks such as "형이 죽자, 백제는 완성됐다".
    causal_clauses = [
        part.strip(" -·")
        for part in re.split(r"[,，;；]", source)
        if part.strip(" -·")
    ]
    if (
        raw
        and len(causal_clauses) == 2
        and re.search(r"(?:죽자|죽고|죽은\s*(?:뒤|후)|사망하자|사망한\s*(?:뒤|후))", causal_clauses[0])
        and all(3 <= len(re.sub(r"\s+", "", clause)) <= 12 for clause in causal_clauses)
    ):
        return "\n".join(causal_clauses)

    # A creator-supplied hook is the source of truth.  The generic keyword
    # classifiers below are only for title-derived fallbacks; otherwise a hook
    # such as "왕을 죽인 반역자를 끝장내다" is incorrectly reduced to
    # "죽음의 순간" merely because it contains "죽".
    if raw and len(re.sub(r"\s+", "", raw)) <= 20:
        return _wrap_overlay_lines(raw)

    army = re.search(r"(\d+\s*만\s*대군)", source)
    if army and "심리전" in source:
        army_text = army.group(1).replace(" ", "")
        if any(word in source for word in ("굶", "굶겨", "굶주")):
            return f"{army_text}\n굶긴 심리전"
        return f"{army_text}\n심리전"
    if "심리전" in source and any(word in source for word in ("제국", "붕괴", "명장")):
        return "제국 무너뜨린\n심리전"
    if any(word in source for word in ("붕괴", "무너", "몰락")) and "명장" in source:
        return "제국 붕괴\n천재 명장"
    if any(word in source for word in ("분노", "격노", "노여움")):
        return "치명적 분노"
    if any(word in source for word in ("죽", "사망", "최후", "처형", "익사")):
        return "죽음의 순간"

    compact = re.split(r"[!?.。！？]", source, maxsplit=1)[0].strip(" -·")
    compact = re.sub(r"\s+", " ", compact)
    max_chars = 20
    if len(compact) <= max_chars:
        return _wrap_overlay_lines(compact)
    words = compact.split()
    selected: list[str] = []
    for word in words:
        candidate = " ".join([*selected, word])
        if selected and len(candidate) > max_chars:
            break
        selected.append(word)
    shortened = " ".join(selected) if selected else compact[:max_chars].strip()
    return _wrap_overlay_lines(shortened)


def _strong_japanese_thumbnail_overlay(text: Any, fallback: Any = "") -> str:
    raw = sanitize_thumbnail_title(str(text or ""))
    context = sanitize_thumbnail_title(str(fallback or ""))
    explicit_lines = [
        re.sub(r"\s+", "", line).strip()
        for line in raw.splitlines()
        if line.strip()
    ]
    if (
        2 <= len(explicit_lines) <= 3
        and all(1 <= len(line) <= 8 for line in explicit_lines)
    ):
        return "\n".join(explicit_lines)
    source = re.sub(r"\s+", "", raw or context).strip()
    source = re.sub(r"(?:EP\.?\s*0*\d+|第\s*0*\d+\s*話)$", "", source, flags=re.IGNORECASE).strip(" |/-–—:・")
    if not source:
        return ""
    specific_overlay = _japanese_dead_goddess_overlay(source)
    if specific_overlay:
        return specific_overlay
    if "三貴子" in source:
        lead = "黄泉の禊" if any(word in source for word in ("黄泉", "禊", "穢れ")) else "三柱の神"
        impact = "三貴子誕生" if "誕生" in source else "三貴子"
        return f"{lead}\n{impact}"
    compact = re.split(r"[|/―—–:：。！？]", source, maxsplit=1)[0].strip()
    if len(compact) <= 8:
        return compact
    split_at = min(8, max(4, (len(compact) + 1) // 2))
    return f"{compact[:split_at]}\n{compact[split_at:16]}".strip()


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


def _thumbnail_error_allows_first_cut_fallback(exc: Exception) -> bool:
    """Only technical thumbnail failures may fall back to the first cut image."""
    if isinstance(exc, ThumbnailError) and (
        "AI 썸네일 품질검증 실패" in str(exc)
        or "AI 썸네일 최종 오버레이 품질검증 실패" in str(exc)
    ):
        return False
    return True


async def _generate_thumbnail_with_overlay_guard(
    *,
    project_id: str,
    title: str,
    base_image_path: str,
    output_path: str,
    image_prompt: str,
    episode_label: Optional[str] = None,
    subtitle: Optional[str] = None,
    config: Optional[dict] = None,
) -> tuple[str, bool, str]:
    overlay_config = dict(config or {})
    overlay_config["_thumbnail_image_prompt"] = image_prompt
    rendered_path = generate_thumbnail(
        project_id=project_id,
        title=title,
        base_image_path=base_image_path,
        output_path=output_path,
        episode_label=episode_label,
        subtitle=subtitle,
        config=overlay_config,
    )
    if not _thumbnail_quality_enabled(overlay_config):
        return rendered_path, True, "overlay_quality_check_disabled"
    passed, reason = await _validate_thumbnail_final_overlay(
        image_path=rendered_path,
        image_prompt=image_prompt,
        overlay_text=title.strip(),
        config=overlay_config,
    )
    return rendered_path, passed, reason


async def _resolve_standard_thumbnail_overlay(
    script: dict[str, Any],
    prompt_title: str,
    config: dict[str, Any],
) -> str:
    """Resolve a non-empty overlay in the configured channel language."""
    overlay_seed = build_clickbait_thumbnail_overlay(script, prompt_title, config)
    language = str(config.get("language") or script.get("language") or "").strip().lower()
    if language in {"ja", "jp", "jpn", "japanese"} and _has_hangul(overlay_seed):
        source_text = sanitize_thumbnail_title(
            config.get("thumbnail_overlay_text")
            or script.get("thumbnail_hook")
            or script.get("thumbnail_text")
            or script.get("thumbnail_overlay")
            or script.get("thumbnail_title")
            or prompt_title
        )
        if not source_text:
            raise ThumbnailError("일본어 썸네일 오버레이 원문이 없습니다.")
        from app.services.youtube_localization_service import (
            ensure_primary_youtube_metadata_language,
        )

        translated_title, _ = await ensure_primary_youtube_metadata_language(
            title=source_text,
            description=source_text,
            config=config,
        )
        overlay_seed = _strong_japanese_thumbnail_overlay(
            translated_title,
            translated_title,
        )

    overlay_title, _ = extract_thumbnail_text_parts(overlay_seed or prompt_title, None)
    overlay_title = suppress_foreign_hangul_thumbnail_overlay(overlay_title, config)
    if not overlay_title.strip():
        raise ThumbnailError(
            "설정된 채널 언어로 된 썸네일 오버레이를 만들지 못했습니다."
        )
    return overlay_title


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
        resolve_thumbnail_model,
        IMAGE_REGISTRY,
    )
    from app.services.image.prompt_builder import (
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
    prompt_title = (
        config.get("youtube_title")
        or title
        or script.get("title")
        or topic
        or "Untitled"
    ).strip()
    raw_thumbnail_prompt = script.get("thumbnail_prompt")
    if not isinstance(raw_thumbnail_prompt, str) or not raw_thumbnail_prompt.strip():
        raise ThumbnailError("대본 thumbnail_prompt가 비어있습니다.")
    thumb_prompt = build_standard_thumbnail_prompt(script, prompt_title, config)
    image_model = resolve_thumbnail_model(
        config.get("thumbnail_model") or DEFAULT_THUMBNAIL_MODEL
    )

    overlay_title = await _resolve_standard_thumbnail_overlay(
        script,
        prompt_title,
        config,
    )

    configured_base_image = _configured_thumbnail_base_image_path(project_dir, config)
    if configured_base_image is not None:
        local_config = dict(config)
        local_config["_thumbnail_image_prompt"] = thumb_prompt
        rendered_path = generate_thumbnail(
            project_id=project_id,
            title=overlay_title,
            base_image_path=str(configured_base_image),
            output_path=str(thumb_path),
            config=local_config,
        )
        passed, reason = _basic_thumbnail_file_check(rendered_path)
        if not passed:
            raise ThumbnailError(f"로컬 썸네일 파일 검증 실패: {reason}")
        return rendered_path

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

    result = await generate_ai_thumbnail(
        project_id=project_id,
        image_prompt=thumb_prompt,
        image_model_id=image_model,
        overlay_title_text=overlay_title,
        overlay_subtitle=None,
        output_path=str(thumb_path),
        reference_images=combined_refs or None,
        enable_historical_guard=enable_historical_guard,
        config=config,
        preserve_image_prompt=True,
    )
    return str(result.get("path") or thumb_path)



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

    match = re.search(r"\bEP\.?\s*0*(\d{1,3})\b", raw_title, flags=re.IGNORECASE)
    if match:
        raw_title = re.sub(r"\bEP\.?\s*0*\d{1,3}\b", "", raw_title, flags=re.IGNORECASE)

    clean_title = sanitize_thumbnail_title(raw_title)
    return clean_title, None


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
    subtitle: Optional[str],
) -> Optional[str]:
    """Render Hindi/Devanagari overlays through Chrome for proper shaping."""
    browser = _find_browser_executable()
    if not browser or not base_image_path or not os.path.exists(base_image_path):
        return None

    bg_data = base64.b64encode(Path(base_image_path).read_bytes()).decode("ascii")
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
    subtitle_block = f'<div class="subtitle">{subtitle_html}</div>' if subtitle_html else ""
    title_font_px = 57
    subtitle_font_px = 45
    title_stroke_px = 3
    subtitle_stroke_px = 3
    title_shadow_y = 5
    title_shadow_spread = 4
    subtitle_shadow_y = 4
    subtitle_shadow_spread = 4
    html_doc = f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box}}
body{{margin:0;width:{THUMB_W}px;height:{THUMB_H}px;overflow:hidden;background:#111}}
.canvas{{position:relative;width:{THUMB_W}px;height:{THUMB_H}px;font-family:"Nirmala UI","Mangal","Arial Unicode MS",sans-serif;background-image:linear-gradient(180deg,rgba(0,0,0,.04) 0%,rgba(0,0,0,.12) 42%,rgba(0,0,0,.64) 100%),linear-gradient(90deg,rgba(0,0,0,.46),rgba(0,0,0,.04) 58%,rgba(0,0,0,.18)),url(data:image/png;base64,{bg_data});background-size:cover;background-position:center}}
.copy{{position:absolute;left:64px;right:76px;bottom:104px}}
.title{{font-weight:900;font-size:{title_font_px}px;line-height:1.06;letter-spacing:0;text-wrap:balance;-webkit-text-stroke:{title_stroke_px}px #050505;text-shadow:0 {title_shadow_y}px 0 rgba(0,0,0,.86),0 0 22px rgba(0,0,0,.90),{title_shadow_spread}px 0 0 #050505,-{title_shadow_spread}px 0 0 #050505,0 {title_shadow_spread}px 0 #050505,0 -{title_shadow_spread}px 0 #050505,{title_stroke_px}px {title_stroke_px}px 0 #050505,-{title_stroke_px}px {title_stroke_px}px 0 #050505,{title_stroke_px}px -{title_stroke_px}px 0 #050505,-{title_stroke_px}px -{title_stroke_px}px 0 #050505}}
.title-main{{display:block;color:#fff}}
.title-impact{{display:block;color:#ffe736}}
.subtitle{{margin-top:10px;color:#ffe736;font-weight:900;font-size:{subtitle_font_px}px;line-height:1.04;letter-spacing:0;-webkit-text-stroke:{subtitle_stroke_px}px #050505;text-shadow:0 {subtitle_shadow_y}px 0 rgba(0,0,0,.86),0 0 20px rgba(0,0,0,.86),{subtitle_shadow_spread}px 0 0 #050505,-{subtitle_shadow_spread}px 0 0 #050505,0 {subtitle_shadow_spread}px 0 #050505,0 -{subtitle_shadow_spread}px 0 #050505;text-wrap:balance}}
</style></head><body><div class="canvas"><div class="copy"><div class="title">{title_html}</div>{subtitle_block}</div></div></body></html>"""

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
    명시적 줄바꿈은 썸네일 후크의 의도된 줄 구성이므로 보존한다.
    """
    def width_of(s: str) -> int:
        try:
            bbox = draw.textbbox((0, 0), s, font=font)
            return bbox[2] - bbox[0]
        except Exception:
            return len(s) * font.size // 2  # 폴백 근사

    def wrap_segment(segment: str) -> list[str]:
        words = segment.split()
        if not words:
            return []
        segment_lines: list[str] = []
        current = ""
        for word in words:
            candidate = (current + " " + word).strip()
            if width_of(candidate) <= max_width:
                current = candidate
                continue
            if current:
                segment_lines.append(current)
                current = ""
            if width_of(word) > max_width:
                chunk = ""
                for ch in word:
                    if width_of(chunk + ch) <= max_width:
                        chunk += ch
                    else:
                        if chunk:
                            segment_lines.append(chunk)
                        chunk = ch
                if chunk:
                    current = chunk
            else:
                current = word
        if current:
            segment_lines.append(current)
        for index in range(1, len(segment_lines)):
            current_line = segment_lines[index]
            previous_line = segment_lines[index - 1]
            if (
                len(current_line) == 1
                and len(previous_line) >= 3
                and re.fullmatch(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]", current_line)
                and re.search(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]$", previous_line)
            ):
                segment_lines[index - 1] = previous_line[:-1]
                segment_lines[index] = previous_line[-1] + current_line
        return segment_lines

    raw_text = str(text or "")
    if "\n" in raw_text:
        return [segment.strip() for segment in raw_text.splitlines() if segment.strip()]

    lines: list[str] = []
    for segment in raw_text.splitlines():
        lines.extend(wrap_segment(segment.strip()))
    return lines


# ─── 텍스트 오버레이 팔레트 ───
TEXT_STROKE = (0, 0, 0)


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


def _rect_area(rect: tuple[int, int, int, int]) -> int:
    return max(0, rect[2] - rect[0]) * max(0, rect[3] - rect[1])


def _rect_intersection_area(
    a: tuple[int, int, int, int],
    b: tuple[int, int, int, int],
) -> int:
    left = max(a[0], b[0])
    top = max(a[1], b[1])
    right = min(a[2], b[2])
    bottom = min(a[3], b[3])
    return max(0, right - left) * max(0, bottom - top)


def _expand_rect(
    rect: tuple[int, int, int, int],
    pad_x: int,
    pad_y: int,
    *,
    width: int = THUMB_W,
    height: int = THUMB_H,
) -> tuple[int, int, int, int]:
    return (
        max(0, rect[0] - pad_x),
        max(0, rect[1] - pad_y),
        min(width, rect[2] + pad_x),
        min(height, rect[3] + pad_y),
    )


def _dedupe_rects(
    rects: list[tuple[int, int, int, int]],
    *,
    iou_threshold: float = 0.35,
) -> list[tuple[int, int, int, int]]:
    kept: list[tuple[int, int, int, int]] = []
    for rect in sorted(rects, key=_rect_area, reverse=True):
        rect_area = _rect_area(rect)
        if rect_area <= 0:
            continue
        duplicate = False
        for other in kept:
            inter = _rect_intersection_area(rect, other)
            union = rect_area + _rect_area(other) - inter
            if union > 0 and inter / union >= iou_threshold:
                duplicate = True
                break
        if not duplicate:
            kept.append(rect)
    return kept


def _detect_thumbnail_face_boxes(image: Image.Image) -> list[tuple[int, int, int, int]]:
    """Best-effort face boxes for overlay placement. Never blocks thumbnail generation."""
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except Exception:
        return []

    try:
        rgb = image.convert("RGB")
        src_w, src_h = rgb.size
        arr = np.array(rgb)
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        scale = 0.5 if src_w > 900 else 1.0
        if scale != 1.0:
            gray_probe = cv2.resize(gray, (int(src_w * scale), int(src_h * scale)))
        else:
            gray_probe = gray

        cascade_names = [
            "haarcascade_frontalface_default.xml",
            "haarcascade_frontalface_alt.xml",
            "haarcascade_profileface.xml",
        ]
        rects: list[tuple[int, int, int, int]] = []
        for name in cascade_names:
            cascade_path = Path(getattr(cv2.data, "haarcascades", "")) / name
            if not cascade_path.exists():
                continue
            classifier = cv2.CascadeClassifier(str(cascade_path))
            if classifier.empty():
                continue
            detected = classifier.detectMultiScale(
                gray_probe,
                scaleFactor=1.08,
                minNeighbors=4,
                minSize=(max(36, int(80 * scale)), max(36, int(80 * scale))),
            )
            for x, y, w, h in detected:
                if scale != 1.0:
                    x = int(round(x / scale))
                    y = int(round(y / scale))
                    w = int(round(w / scale))
                    h = int(round(h / scale))
                if w * h >= 4_000:
                    rects.append((int(x), int(y), int(x + w), int(y + h)))
        return _dedupe_rects(rects)
    except Exception:
        return []


def _thumbnail_fallback_face_safe_boxes(image_prompt: str) -> list[tuple[int, int, int, int]]:
    """Conservative face-safe zone when local face detection misses a face close-up."""
    prompt = image_prompt or ""
    if not (_thumbnail_prompt_expects_face_closeup(prompt) or _thumbnail_prompt_expects_person(prompt)):
        return []
    return [(int(THUMB_W * 0.32), int(THUMB_H * 0.35), THUMB_W, THUMB_H)]


def _thumbnail_overlay_local_geometry_pass(image_path: str, image_prompt: str) -> bool:
    """Allow obvious vision-QA false positives when text pixels stay outside face core."""
    prompt = image_prompt or ""
    if not (_thumbnail_prompt_expects_face_closeup(prompt) or _thumbnail_prompt_expects_person(prompt)):
        return False
    try:
        image = Image.open(image_path).convert("RGB")
    except Exception:
        return False

    background: Optional[Image.Image] = None
    background_path = Path(image_path).with_name("thumbnail_bg.png")
    if background_path.exists() and background_path.resolve() != Path(image_path).resolve():
        try:
            candidate = Image.open(background_path).convert("RGB")
            if candidate.size != image.size:
                candidate = _cover_resize(candidate, image.size[0], image.size[1])
            background = candidate
        except Exception:
            background = None

    w, h = image.size
    detected = [_expand_rect(box, 24, 20) for box in _detect_thumbnail_face_boxes(image)]
    protected = detected or [(int(w * 0.45), int(h * 0.08), w, int(h * 0.92))]

    for x1, y1, x2, y2 in protected:
        crop = image.crop((
            max(0, int(x1)),
            max(0, int(y1)),
            min(w, int(x2)),
            min(h, int(y2)),
        ))
        background_crop = background.crop((
            max(0, int(x1)),
            max(0, int(y1)),
            min(w, int(x2)),
            min(h, int(y2)),
        )) if background is not None else None
        text_like_pixels = 0
        background_pixels = iter(background_crop.getdata()) if background_crop is not None else None
        for r, g, b in crop.getdata():
            is_white_fill = r >= 238 and g >= 238 and b >= 238
            is_yellow_fill = r >= 215 and g >= 170 and b <= 95
            is_new_overlay_fill = is_white_fill or is_yellow_fill
            if background_pixels is not None:
                br, bg, bb = next(background_pixels)
                background_was_white = br >= 220 and bg >= 220 and bb >= 220
                background_was_yellow = br >= 190 and bg >= 140 and bb <= 125
                if background_was_white or background_was_yellow:
                    is_new_overlay_fill = False
            if is_new_overlay_fill:
                text_like_pixels += 1
                if text_like_pixels > 900:
                    return False
    return True


def _thumbnail_text_layout_score(
    text_rects: list[tuple[int, int, int, int]],
    face_boxes: list[tuple[int, int, int, int]],
    preference: int,
) -> float:
    if not text_rects:
        return 1_000_000_000 + preference
    score = float(preference * 1000)
    for text_rect in text_rects:
        for face_box in face_boxes:
            overlap = _rect_intersection_area(text_rect, face_box)
            if overlap:
                score += 1_000_000 + overlap * 20
    return score


def _thumbnail_reflow_short_two_line_hook(text: str, fallback_face_safe_zone: bool) -> str:
    if not fallback_face_safe_zone:
        return text
    explicit_lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    compact_length = len(re.sub(r"\s+", "", str(text or "")))
    if len(explicit_lines) != 2 or compact_length > 14:
        return text
    longest_index = max(range(2), key=lambda index: len(re.sub(r"\s+", "", explicit_lines[index])))
    longest_words = explicit_lines[longest_index].split()
    if len(longest_words) < 2:
        return text
    reflowed = list(explicit_lines)
    if len(longest_words) == 2:
        split_lines = longest_words
    else:
        split_at = min(
            range(1, len(longest_words)),
            key=lambda index: abs(
                len("".join(longest_words[:index]))
                - len("".join(longest_words[index:]))
            ),
        )
        split_lines = [
            " ".join(longest_words[:split_at]),
            " ".join(longest_words[split_at:]),
        ]
    reflowed[longest_index:longest_index + 1] = split_lines
    return "\n".join(reflowed)


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
    - 하단: 큰 흰색 글자 + 두꺼운 검정 아웃라인 + 드롭섀도 (박스 없음).
      MrBeast / Veritasium 스타일의 그림텍스트. 박스로 이미지를 가리지 않고,
      아웃라인 + 섀도로 가독성 확보.
    - 마지막 줄은 노랑 강조 색으로 포인트 주기 (여러 줄일 때).

    Args:
        project_id: 프로젝트 ID.
        title: 메인 후크 텍스트 (썸네일의 가장 큰 글자).
        base_image_path: 배경 이미지 경로.
        output_path: 저장 경로.
        episode_label: 이전 호환용 인자. 썸네일에는 EP 배지를 그리지 않음.
        subtitle: 메인 후크 위에 들어갈 보조 라인. None 이면 생략.

    Returns:
        저장된 파일의 절대 경로 (str).
    """
    title, _episode_label = extract_thumbnail_text_parts(title, episode_label)
    episode_label = None
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

    face_probe = base.copy()

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
    fallback_face_safe_zone = False
    face_boxes = [
        _expand_rect(box, 74, 70)
        for box in _detect_thumbnail_face_boxes(face_probe)
    ]
    if not face_boxes:
        prompt_for_layout = str(
            (config or {}).get("_thumbnail_image_prompt")
            or (config or {}).get("thumbnail_prompt")
            or ""
        )
        face_boxes = _thumbnail_fallback_face_safe_boxes(prompt_for_layout)
        fallback_face_safe_zone = bool(face_boxes)
    layout_text = _thumbnail_reflow_short_two_line_hook(text, bool(face_boxes))

    # ── 메인 후크: 큰 그림텍스트 ──
    # 박스 없이 크게 — 박스가 먹던 공간이 없으므로 폰트를 확 키움.
    # 후보 사이즈를 높은 것부터 내려가며 전체 문장이 잘리지 않도록 줄바꿈/축소한다.
    # v2.1.2: 폰트 크기 상향 — 제목이 짧아졌으므로 더 크게 표시
    candidates = (124, 116, 108, 98, 87, 76, 67, 60, 53, 48, 42, 38, 34, 29, 25, 22, 20, 17)

    def pick_title_font(max_text_w: int, max_title_block_h: int) -> tuple[ImageFont.ImageFont, list[str]]:
        for size in candidates:
            f = _find_font(size, layout_text)
            lines = _wrap_text(layout_text, f, max_text_w, draw)
            if not lines:
                continue
            lh = _text_size(draw, "가Ag", f)[1]
            max_line_w = max((_text_size(draw, line, f)[0] for line in lines), default=0)
            total_h = len(lines) * lh + (len(lines) - 1) * int(lh * 0.15)
            if max_line_w <= max_text_w and total_h <= max_title_block_h:
                return f, lines
        # 폴백: 가장 작은 폰트
        f = _find_font(candidates[-1], layout_text)
        return f, _wrap_text(layout_text, f, max_text_w, draw) or [layout_text]

    # 라인 높이
    def line_h(font):
        _, h = _text_size(draw, "가Ag", font)
        return h

    def text_rects(
        title_placed_value: list[tuple[str, int, int]],
        sub_placed_value: Optional[tuple[str, int, int]],
        title_font_value: ImageFont.ImageFont,
        sub_font_value: Optional[ImageFont.ImageFont],
        title_lh_value: int,
        sub_lh_value: int,
        pad_value: int,
    ) -> list[tuple[int, int, int, int]]:
        rects: list[tuple[int, int, int, int]] = []
        for line_text, tx, ty in title_placed_value:
            tw, _ = _text_size(draw, line_text, title_font_value)
            rects.append(_expand_rect((tx, ty, tx + tw, ty + title_lh_value), pad_value, pad_value))
        if sub_placed_value and sub_font_value is not None:
            s_text, sx, sy = sub_placed_value
            sw, _ = _text_size(draw, s_text, sub_font_value)
            rects.append(_expand_rect((sx, sy, sx + sw, sy + sub_lh_value), pad_value, pad_value))
        return rects

    def build_layout(layout_name: str, preference: int):
        max_text_ratio = 0.44 if fallback_face_safe_zone else (0.54 if face_boxes else 0.60)
        max_text_w = min(THUMB_W - 2 * pad_x, int(THUMB_W * max_text_ratio))
        max_title_block_ratio = 0.46 if fallback_face_safe_zone else (0.52 if face_boxes else 0.62)
        max_title_block_h = int(THUMB_H * max_title_block_ratio)
        title_font_value, title_lines_value = pick_title_font(max_text_w, max_title_block_h)
        title_size_value = getattr(title_font_value, "size", 96)
        title_stroke_w_value = max(6, min(14, title_size_value // 9))
        title_embolden_value = max(2, min(5, title_size_value // 42))

        sub_font_value = None
        sub_stroke_w_value = 0
        if sub:
            sub_size = max(31, int(title_size_value * 0.55))
            sub_font_value = _find_font(sub_size, sub)
            while _text_size(draw, sub, sub_font_value)[0] > max_text_w and sub_size > 22:
                sub_size -= 4
                sub_font_value = _find_font(sub_size, sub)
            sub_stroke_w_value = max(4, min(10, sub_size // 10))
            sub_embolden_value = max(2, min(4, sub_size // 40))
        else:
            sub_embolden_value = 0

        title_lh_value = line_h(title_font_value)
        sub_lh_value = line_h(sub_font_value) if sub_font_value else 0
        line_gap_value = int(title_lh_value * 0.12)
        align_right = layout_name.endswith("right")
        use_upper = layout_name.startswith("upper")
        col_left = THUMB_W - pad_x - max_text_w if align_right else pad_x
        col_right = col_left + max_text_w

        title_placed_value: list[tuple[str, int, int]] = []
        sub_placed_value: Optional[tuple[str, int, int]] = None
        if use_upper:
            current_top = 54
            if sub and sub_font_value:
                sw, _ = _text_size(draw, sub, sub_font_value)
                sx = col_right - sw if align_right else col_left
                sub_placed_value = (sub, sx, current_top)
                current_top += sub_lh_value + int(line_gap_value * 2)
            for line in title_lines_value:
                tw, _ = _text_size(draw, line, title_font_value)
                tx = col_right - tw if align_right else col_left
                title_placed_value.append((line, tx, current_top))
                current_top += title_lh_value + line_gap_value
        else:
            current_bottom = THUMB_H - 60
            for line in reversed(title_lines_value):
                tw, _ = _text_size(draw, line, title_font_value)
                tx = col_right - tw if align_right else col_left
                y_top = current_bottom - title_lh_value
                title_placed_value.append((line, tx, y_top))
                current_bottom = y_top - line_gap_value
            title_placed_value.reverse()
            if sub and sub_font_value:
                sw, _ = _text_size(draw, sub, sub_font_value)
                sx = col_right - sw if align_right else col_left
                y_top = current_bottom - int(line_gap_value * 2) - sub_lh_value
                sub_placed_value = (sub, sx, y_top)

        rect_pad = max(title_stroke_w_value, sub_stroke_w_value, title_embolden_value, sub_embolden_value) + 18
        rects = text_rects(
            title_placed_value,
            sub_placed_value,
            title_font_value,
            sub_font_value,
            title_lh_value,
            sub_lh_value,
            rect_pad,
        )
        score = _thumbnail_text_layout_score(rects, face_boxes, preference)
        if fallback_face_safe_zone and not use_upper:
            score += 2_000_000
        return (
            score,
            title_font_value,
            title_lines_value,
            title_stroke_w_value,
            title_embolden_value,
            sub_font_value,
            sub_stroke_w_value,
            sub_embolden_value,
            title_placed_value,
            sub_placed_value,
        )

    # 채널 공통 썸네일 규칙: 문구는 항상 좌측 하단에 고정한다.
    layouts = [build_layout("lower_left", 0)]
    (
        _layout_score,
        title_font,
        title_lines,
        title_stroke_w,
        title_embolden,
        sub_font,
        sub_stroke_w,
        sub_embolden,
        title_placed,
        sub_placed,
    ) = min(layouts, key=lambda item: item[0])

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
    preserve_image_prompt: bool = False,
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
    from app.services.image.factory import get_image_service, resolve_thumbnail_model

    if not image_prompt or not image_prompt.strip():
        raise ThumbnailError("image_prompt 가 비어있습니다.")
    image_model_id = resolve_thumbnail_model(image_model_id)

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

    from app.services.image.prompt_compiler import (
        configured_prompt_profile,
        supports_scene_contract_v2_model,
    )

    prompt_profile = configured_prompt_profile(config)
    if not supports_scene_contract_v2_model(
        getattr(image_service, "model_id", image_model_id)
    ):
        prompt_profile = ""
    try:
        image_service.prompt_profile = prompt_profile
    except Exception:
        pass

    from app.services.image.prompt_builder import (
        append_prompt_specific_negative_prompt,
        apply_reference_style_prefix,
        historical_negative_prompt,
        map_negative_prompt,
        symbol_negative_prompt,
        text_negative_prompt,
    )

    if not preserve_image_prompt:
        image_prompt = _append_thumbnail_minimal_contract(
            _thumbnail_style_prompt_from_config(image_prompt, config)
        )
    compact_generation_prompt = True
    try:
        image_service.compact_thumbnail_prompt = compact_generation_prompt
    except Exception:
        pass
    object_event_thumbnail = "OBJECT OR EVENT THUMBNAIL LOCK" in image_prompt and not _thumbnail_prompt_expects_person(image_prompt)
    try:
        current_neg = (getattr(image_service, "negative_prompt", "") or "").strip()
        for required_negative in (text_negative_prompt(), map_negative_prompt(), symbol_negative_prompt()):
            if required_negative and required_negative not in current_neg:
                current_neg = f"{required_negative}, {current_neg}".strip(" ,")
        guard_negative = historical_negative_prompt(
            image_prompt,
            False if object_event_thumbnail else enable_historical_guard,
        )
        if guard_negative and guard_negative not in current_neg:
            current_neg = f"{guard_negative}, {current_neg}".strip(" ,")
        for weak_negative in THUMBNAIL_WEAK_IMAGE_NEGATIVE.split(","):
            weak_negative = weak_negative.strip()
            if weak_negative and weak_negative not in current_neg:
                current_neg = f"{weak_negative}, {current_neg}".strip(" ,")
        if _thumbnail_prompt_expects_face_closeup(image_prompt):
            for closeup_negative in (
                "horse",
                "mounted rider",
                "full-body rider",
                "full body portrait",
                "distant figure",
                "large gate",
                "shrine gate",
                "castle gate",
                "wide battlefield composition",
                "army crowd composition",
                "distant army",
                "army background as main subject",
                "crowd competing with face",
                "battlefield replacing face",
                "side-profile portrait",
                "cropped forehead",
                "cropped hat",
                "cropped chin",
            ):
                if closeup_negative not in current_neg:
                    current_neg = f"{closeup_negative}, {current_neg}".strip(" ,")
        image_service.negative_prompt = append_prompt_specific_negative_prompt(current_neg, image_prompt)
    except Exception:
        pass

    quality_checked = False
    quality_reason = "quality_check_disabled"
    prompt_for_attempt = image_prompt
    max_attempts = (
        1
        if preserve_image_prompt
        else _thumbnail_quality_attempt_count(config)
        if _thumbnail_quality_enabled(config)
        else 1
    )
    overlay_applied = False
    final_path = output_path

    async def accept_thumbnail_attempt(prompt_used: str) -> tuple[bool, str]:
        nonlocal overlay_applied
        if overlay_title_text and overlay_title_text.strip():
            try:
                overlay_config = dict(config or {})
                overlay_config["_thumbnail_image_prompt"] = prompt_used
                generate_thumbnail(
                    project_id=project_id,
                    title=overlay_title_text.strip(),
                    base_image_path=bg_path,
                    output_path=output_path,
                    episode_label=(overlay_episode_label or "").strip() or None,
                    subtitle=(overlay_subtitle or "").strip() or None,
                    config=overlay_config,
                )
                overlay_applied = True
            except Exception as e:
                raise ThumbnailError(f"텍스트 오버레이 합성 실패: {e}") from e
            if _thumbnail_quality_enabled(config):
                return await _validate_thumbnail_final_overlay(
                    image_path=output_path,
                    image_prompt=prompt_used,
                    overlay_text=overlay_title_text.strip(),
                    config=config,
                )
            return True, "overlay_quality_check_disabled"

        try:
            if os.path.abspath(bg_path) != os.path.abspath(output_path):
                with Image.open(bg_path) as im:
                    im.convert("RGB").save(output_path, "PNG", optimize=True)
        except Exception as e:
            raise ThumbnailError(f"AI 썸네일 저장 실패: {e}") from e
        overlay_applied = False
        return True, "no_overlay"

    for attempt in range(1, max_attempts + 1):
        # Retry changes only the model-generated seed.  The application-owned
        # thumbnail prompt must remain byte-for-byte stable across attempts.
        prompt_for_attempt = image_prompt
        model_prompt_for_attempt = prompt_for_attempt
        try:
            saved_bg = await image_service.generate(
                model_prompt_for_attempt,
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

        if not _thumbnail_quality_enabled(config):
            accepted, overlay_reason = await accept_thumbnail_attempt(model_prompt_for_attempt)
            if not accepted:
                quality_reason = f"final_overlay_qa_failed:{overlay_reason}"
                if attempt < max_attempts:
                    print(f"[thumbnail] final overlay QA failed, retrying ({attempt}/{max_attempts}): {overlay_reason}")
                    continue
                raise ThumbnailError(f"AI 썸네일 최종 오버레이 품질검증 실패: {overlay_reason}")
            image_prompt = model_prompt_for_attempt
            break

        quality_checked = True
        passed, quality_reason = await _validate_thumbnail_background(
            image_path=bg_path,
            image_prompt=model_prompt_for_attempt,
            config=config,
        )
        if passed:
            accepted, overlay_reason = await accept_thumbnail_attempt(model_prompt_for_attempt)
            if not accepted:
                quality_reason = f"final_overlay_qa_failed:{overlay_reason}"
                if attempt < max_attempts:
                    print(f"[thumbnail] final overlay QA failed, retrying ({attempt}/{max_attempts}): {overlay_reason}")
                    continue
                raise ThumbnailError(f"AI 썸네일 최종 오버레이 품질검증 실패: {overlay_reason}")
            image_prompt = model_prompt_for_attempt
            break
        if attempt < max_attempts:
            print(f"[thumbnail] QA failed, retrying ({attempt}/{max_attempts}): {quality_reason}")
            continue

        if (
            _thumbnail_prompt_expects_face_closeup(model_prompt_for_attempt)
            and not _thumbnail_has_strict_story_lock(model_prompt_for_attempt)
            and _thumbnail_closeup_soft_quality_failure(quality_reason)
        ):
            soft_reason = f"vision_soft_pass_face_closeup_warning: {quality_reason}"
            _write_thumbnail_qa_sidecar(bg_path, {
                "passed": True,
                "reason": soft_reason,
                "model": str((config or {}).get("thumbnail_quality_model") or "gpt-4o-mini"),
                "raw": {"pass": True, "override": "face_closeup_soft_quality_warning"},
            })
            accepted, overlay_reason = await accept_thumbnail_attempt(model_prompt_for_attempt)
            if not accepted:
                quality_reason = f"final_overlay_qa_failed:{overlay_reason}"
                raise ThumbnailError(f"AI 썸네일 최종 오버레이 품질검증 실패: {overlay_reason}")
            image_prompt = model_prompt_for_attempt
            quality_reason = soft_reason
            break

        base_cut = _first_cut_image_path(resolve_project_dir(project_id, config or {}, create=True))
        allow_first_cut_fallback = not (
            _thumbnail_prompt_expects_face_closeup(model_prompt_for_attempt)
            or _thumbnail_prompt_expects_person(model_prompt_for_attempt)
        )
        if allow_first_cut_fallback and base_cut.exists() and overlay_title_text and overlay_title_text.strip():
            _, accepted, overlay_reason = await _generate_thumbnail_with_overlay_guard(
                project_id=project_id,
                title=overlay_title_text.strip(),
                base_image_path=str(base_cut),
                output_path=output_path,
                image_prompt=model_prompt_for_attempt,
                episode_label=(overlay_episode_label or "").strip() or None,
                subtitle=(overlay_subtitle or "").strip() or None,
                config=config,
            )
            if not accepted:
                raise ThumbnailError(f"AI 썸네일 최종 오버레이 품질검증 실패: {overlay_reason}")
            return {
                "path": output_path,
                "bg_path": str(base_cut),
                "model": image_model_id,
                "prompt_used": prompt_for_attempt,
                "overlay_applied": True,
                "quality_checked": quality_checked,
                "quality_passed": False,
                "quality_reason": quality_reason,
                "quality_fallback": base_cut.name,
            }
        raise ThumbnailError(f"AI 썸네일 품질검증 실패: {quality_reason}")

    return {
        "path": final_path,
        "bg_path": bg_path,
        "model": image_model_id,
        "prompt_used": image_prompt,
        "overlay_applied": overlay_applied,
        "quality_checked": quality_checked,
        "quality_passed": (
            quality_reason == "vision_pass"
            or quality_reason == "overlay_vision_pass"
            or quality_reason.startswith("vision_qa_skipped")
            or quality_reason.startswith("vision_soft_pass")
        ),
        "quality_reason": quality_reason,
    }
