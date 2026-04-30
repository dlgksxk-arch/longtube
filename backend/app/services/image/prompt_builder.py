"""이미지 프롬프트 빌더 + 레퍼런스 수집 유틸.

v1.1.52: pipeline_tasks._step_image 와 routers/image.py 가 동일한 로직을
공유하기 위해 분리. 라우터를 직접 import 하면 FastAPI 의존성(python-multipart 등)이
끌려오므로, 순수 함수만 이 모듈에 배치한다.

v1.1.58: 레퍼런스 이미지가 있으면 스타일은 100% 레퍼런스에서 가져온다.
global_style, 스타일 큐 제거 등 복잡한 우회 로직 삭제 — 단순하고 명확하게.

v1.1.55: 모든 이미지 생성(컷, 썸네일, 재생성) 경로에서 동일한 REFERENCE_STYLE_PREFIX
를 사용한다. 문구가 3 곳에서 제각각이던 상태를 단일 상수로 통합해 스타일 일관성을
강제한다.
"""
import re
from pathlib import Path
from app.config import DATA_DIR, resolve_project_dir


# ── 레퍼런스 스타일 락 (모든 이미지 생성 경로 공용) ──
#
# 이 프리픽스는 레퍼런스 이미지가 하나라도 첨부된 모든 프롬프트에 예외 없이
# 앞자리로 붙는다. 목적은 "이 프로젝트 안의 모든 이미지가 같은 그림체·같은
# 팔레트·같은 조명으로 나온다" 는 것을 모델 수준에서 강제하는 것이다.
#
# 사용처:
# - build_image_prompt (컷 이미지, has_reference=True 분기)
# - apply_reference_style_prefix (썸네일 자동/재생성, 그 외 외부 호출)
#
# 끝에 " || " 구분자를 두어 사용자 프롬프트가 바로 이어 붙을 수 있게 한다.
REFERENCE_STYLE_PREFIX = (
    "★ STYLE REFERENCE LOCK — the attached reference images are the absolute "
    "ground truth for art direction, color palette, lighting, texture, "
    "line/stroke character, and rendering technique. COPY that exact style "
    "pixel-for-pixel feel. Do NOT reinterpret, stylize, or drift. Keep every "
    "new image visually indistinguishable in style from the references. "
    "Change ONLY composition, subject, pose, and action as described below. || "
)

# v1.1.72: 모든 이미지 생성 경로에 공통으로 붙는 "문자 금지" 지시.
# 이미지 생성 모델이 그리는 문자는 거의 항상 깨져 나와 영상 완성도를
# 깎아먹으므로, 긍정 프롬프트(positive) 에서 강하게 차단한다.
# - ComfyUI 로컬은 추가로 DEFAULT_NEGATIVE_PROMPT 에서도 걸린다 (이중 차단).
# - OpenAI Image / Nano Banana 등 API 모델은 negative 가 없으므로 이 지시가 유일한 방벽.
# 맨 끝 " || " 로 분리해서 기존 프롬프트 뒤에 붙는다.
NO_TEXT_DIRECTIVE = (
    " || ★ HARD CONSTRAINT — ABSOLUTELY NO TEXT, NO LETTERS, NO WORDS, NO NUMBERS, "
    "NO WRITING, NO TYPOGRAPHY, NO CAPTIONS, NO LABELS, NO SIGNS WITH READABLE "
    "CHARACTERS, NO BOOK PAGES, NO NEWSPAPERS, NO BILLBOARDS WITH COPY, NO "
    "SCREEN TEXT, NO SUBTITLES, NO WATERMARKS anywhere in the image. All "
    "surfaces that might normally carry writing (signs, screens, posters, book "
    "covers, clothing, packaging) must be BLANK or show only abstract non-"
    "linguistic shapes. This is a hard requirement — any readable glyph is a "
    "failure."
)

I2V_SAFE_STILL_DIRECTIVE = (
    " || sharp single-exposure still image for image-to-video, crisp subject edges, "
    "clear solid silhouettes, no motion blur, no afterimage, no double exposure, "
    "no ghosting, no speed lines, no translucent duplicate bodies"
)

ANATOMY_SAFE_DIRECTIVE = (
    " || ANATOMY SAFETY — every living subject must have one complete coherent body. "
    "All visible limbs must be attached to the correct torso, inside the frame, and "
    "not floating, duplicated, cropped off, pasted onto the background, or fused with "
    "another subject. Keep bodies separated with clear silhouettes and simple poses."
)

HUMAN_ANATOMY_DIRECTIVE = (
    " Human/character anatomy: one head, one torso, two arms, two legs, natural "
    "shoulders and elbows, no extra arms, no extra hands, no detached hands, no "
    "missing limbs. Hands must stay small or simplified."
)

QUADRUPED_ANATOMY_DIRECTIVE = (
    " Quadruped anatomy: every dog, cat, horse, cow, deer, wolf, fox, bear, or similar "
    "animal has exactly one head, one torso, four attached legs/paws/hooves, and one "
    "tail if visible. Prefer side-view or three-quarter standing/walking poses with "
    "all four feet grounded and separated. No fifth leg, no extra paws, no merged legs."
)

HAND_SAFE_DIRECTIVE = (
    " || HAND SAFETY — avoid close-up hands, foreground fingers, fingertips, palms, "
    "knuckles, gripping poses, and detailed hand anatomy. If a gesture is necessary, "
    "keep arms simple and hands as tiny four-lobed mitten shapes."
)

LIMB_FRAME_SAFE_DIRECTIVE = (
    " || LIMB FRAMING SAFETY — avoid close-up isolated limbs, paws, feet, cropped "
    "bodies, partial bodies, and out-of-frame anatomy. Use medium or wide framing "
    "with the whole subject visible and all limbs attached."
)

CARTOON_FACELESS_DIRECTIVE = (
    " || CARTOON CHARACTER FACE LOCK — for any cartoon, simple, mascot, or stylized "
    "character, keep the head as a blank simple shape. Do not draw or imply eyes, "
    "nose, mouth, eyebrows, smile, frown, facial expression, anime face, or detailed "
    "human face. Communicate the scene with silhouette, body pose, clothing, props, "
    "and lighting only."
)

# Local SDXL follows positive tokens too literally. Keep additional safety
# suffixes disabled in the default LoRA path.
I2V_SAFE_STILL_DIRECTIVE = " || crisp single-subject still frame, sharp subject edges, clean solid silhouette"
ANATOMY_SAFE_DIRECTIVE = " || one complete coherent body, attached simple limbs, centered readable pose"
HUMAN_ANATOMY_DIRECTIVE = " Simple character body with one head, one torso, two arms, two legs, tube-like arms and tiny four-lobed mitten hands."
HAND_SAFE_DIRECTIVE = " || tiny four-lobed mitten hands, hands kept small and away from the foreground, simple gesture"
LIMB_FRAME_SAFE_DIRECTIVE = " || medium shot, whole subject visible, centered composition"
CARTOON_FACELESS_DIRECTIVE = " || blank smooth round head, featureless face area, simple silhouette, readable body pose"

SIMPLE_CHARACTER_COUNT_DIRECTIVE = (
    " || single faceless round-head character, plain white background, centered "
    "simple composition, empty white space, blank round head, tube-like arms, "
    "tiny four-lobed mitten hands, simple feet"
)

_VIDEO_UNFRIENDLY_IMAGE_PATTERNS = [
    (r"\bmotion\s+blur\s+on\s+[^,.;]+", "sharp subject edges"),
    (r"\bmotion\s+blur\b", "sharp freeze-frame motion"),
    (r"\bblurred\s+motion\b", "sharp freeze-frame motion"),
    (r"\bblurred\s+face\b", "distant face in soft shadow"),
    (r"\bspeed\s+lines?\b", "clean action pose"),
    (r"\blong\s+exposure\b", "single-exposure still"),
    (r"\bdouble\s+exposure\b", "single-exposure still"),
    (r"\bghost(?:ing)?\b", "solid silhouette"),
    (r"\bafterimage\b", "solid silhouette"),
]

_HAND_ANATOMY_RE = re.compile(
    r"\b(hand|hands|finger|fingers|fingertip|fingertips|palm|palms|knuckle|knuckles)\b",
    re.IGNORECASE,
)
_HAND_ACTION_RE = re.compile(
    r"\b(holding|gripping|grabbing|pointing|reaching)\b",
    re.IGNORECASE,
)
_HUMAN_SUBJECT_RE = re.compile(
    r"\b(person|people|human|man|woman|boy|girl|child|kid|adult|character|figure|"
    r"researcher|scientist|engineer|explorer|worker|soldier|farmer|teacher|student|"
    r"crowd|silhouette|narrator)\b",
    re.IGNORECASE,
)
_QUADRUPED_SUBJECT_RE = re.compile(
    r"\b(dog|puppy|cat|kitten|horse|pony|cow|bull|deer|wolf|fox|bear|lion|tiger|"
    r"leopard|cheetah|goat|sheep|pig|boar|rabbit|quadruped|animal)\b",
    re.IGNORECASE,
)
_CROP_RISK_RE = re.compile(
    r"\b(cropped|cut\s*off|out\s+of\s+frame|partial\s+body|fragmented|severed|"
    r"dismembered|detached|floating\s+limb|floating\s+hand|floating\s+leg)\b",
    re.IGNORECASE,
)

_HAND_RISK_IMAGE_PATTERNS = [
    (
        r"\ba\s+human\s+hand\s+and\s+a\s+robotic\s+hand\s+almost\s+touching\b",
        "a human silhouette and a robotic silhouette facing the same glowing orb",
    ),
    (
        r"\btwo\s+hands?\s+(?:almost\s+)?touching\b",
        "two simplified silhouettes facing the same glowing orb",
    ),
    (
        r"\bhands?\s+(?:almost\s+)?touching\b",
        "two simplified figures facing the same glowing orb",
    ),
    (r"\bholding\s+([^,.;]+)", r"standing beside \1"),
    (r"\bgripping\s+([^,.;]+)", r"standing beside \1"),
    (r"\bgrabbing\s+([^,.;]+)", r"standing beside \1"),
    (r"\bpointing\s+at\s+([^,.;]+)", r"looking toward \1"),
    (r"\breaching\s+toward\s+([^,.;]+)", r"leaning toward \1"),
    (r"\bfaint\s+glow\s+between\s+fingertips\b", "faint glow between two floating abstract symbols"),
    (r"\bglow\s+between\s+fingertips\b", "glow between two floating abstract symbols"),
    (r"\bbetween\s+fingertips\b", "between two floating abstract symbols"),
    (r"\bfingertips?\b", "small arm gesture"),
    (r"\bfingers?\b", "small arm gesture"),
    (r"\bclose-up\s+of\s+(?:a\s+)?hands?\b", "close-up of a symbolic object"),
    (r"\bforeground\s+hands?\b", "foreground symbolic objects"),
]

_ANATOMY_RISK_IMAGE_PATTERNS = [
    (r"\bclose-up\s+of\s+(?:a\s+)?(?:leg|legs|foot|feet|paw|paws|hoof|hooves)\b", "medium shot of the full subject"),
    (r"\bforeground\s+(?:leg|legs|foot|feet|paw|paws|hoof|hooves)\b", "full subject visible in the foreground"),
    (r"\bcropped\s+(?:body|person|animal|dog|cat|horse)\b", "complete subject fully inside the frame"),
    (r"\bpartial\s+(?:body|person|animal|dog|cat|horse)\b", "complete subject fully inside the frame"),
    (r"\bcut\s*off\s+(?:body|limbs?|legs?|arms?|paws?)\b", "complete subject fully inside the frame"),
    (r"\bdetached\s+(?:limbs?|legs?|arms?|hands?|paws?)\b", "all limbs attached to the correct body"),
    (r"\bfloating\s+(?:limbs?|legs?|arms?|hands?|paws?)\b", "all limbs attached to the correct body"),
    (r"\bfused\s+(?:bodies|people|animals|limbs?|legs?|arms?|hands?|paws?)\b", "separated bodies with clear silhouettes"),
    (r"\bcrowd\s+of\s+people\b", "one simplified faceless rounded-head character"),
    (r"\bgroup\s+of\s+people\s+overlapping\b", "one simplified faceless rounded-head character"),
    (r"\bgroup\s+of\s+people\b", "one simplified faceless rounded-head character"),
    (r"\baudience\b", "one simplified faceless rounded-head observer"),
    (r"\bclassroom\s+full\s+of\s+people\b", "classroom with one faceless rounded-head teacher"),
    (r"\bmeeting\s+room\s+full\s+of\s+people\b", "meeting room with one faceless rounded-head character"),
    (r"\barmy\s+of\s+people\b", "one symbolic faceless character"),
    (r"\bworkers\b", "one faceless rounded-head worker"),
    (r"\bresearchers\b", "one faceless rounded-head researcher"),
    (r"\boverlapping\b", "standing apart"),
    (r"\ba\s+pack\s+of\s+dogs\b", "two separated side-view dogs"),
    (r"\bpack\s+of\s+dogs\b", "two separated side-view dogs"),
    (r"\bdog\s+running\b", "side-view dog walking with all four paws visible"),
    (r"\bdog\s+jumping\b", "side-view dog standing with all four paws visible"),
    (r"\bhorse\s+galloping\b", "side-view horse walking with all four legs visible"),
    (r"\bcat\s+jumping\b", "side-view cat standing with all four paws visible"),
]


def _sanitize_i2v_source_prompt(text: str) -> str:
    """Remove still-image cues that Hunyuan I2V tends to turn into ghost trails."""
    out = text or ""
    for pattern, replacement in _VIDEO_UNFRIENDLY_IMAGE_PATTERNS:
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", out).strip()


def _sanitize_hand_risky_prompt(text: str) -> tuple[str, bool]:
    """Avoid foreground hand anatomy, which SDXL local models often deform."""
    out = text or ""
    had_hand_risk = bool(_HAND_ANATOMY_RE.search(out) or _HAND_ACTION_RE.search(out))
    for pattern, replacement in _HAND_RISK_IMAGE_PATTERNS:
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    out = re.sub(
        r"(?:exactly four short rounded cartoon\s+){2,}fingers",
        "tiny four-lobed mitten hands",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"(?:four simple rounded|exactly four short rounded cartoon) (?:simple rounded shapes|four simple rounded fingers|exactly four short rounded cartoon fingers)",
        "tiny four-lobed mitten hands",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"(?:tiny\s+)?four-lobed\s+mitten\s+hands(?:,\s*(?:tiny\s+)?four-lobed\s+mitten\s+hands)+",
        "tiny four-lobed mitten hands",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out, had_hand_risk


def _sanitize_anatomy_risky_prompt(text: str) -> tuple[str, dict[str, bool]]:
    """Normalize high-risk anatomy compositions before they reach the image model."""
    out = text or ""
    flags = {
        "human": bool(_HUMAN_SUBJECT_RE.search(out)),
        "quadruped": bool(_QUADRUPED_SUBJECT_RE.search(out)),
        "crop": bool(_CROP_RISK_RE.search(out)),
    }
    for pattern, replacement in _ANATOMY_RISK_IMAGE_PATTERNS:
        if re.search(pattern, out, flags=re.IGNORECASE):
            flags["crop"] = True
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out, flags


def _build_anatomy_suffix(base: str, anatomy_flags: dict[str, bool], had_hand_risk: bool) -> str:
    suffix = I2V_SAFE_STILL_DIRECTIVE + ANATOMY_SAFE_DIRECTIVE + SIMPLE_CHARACTER_COUNT_DIRECTIVE
    if anatomy_flags.get("human"):
        suffix += HUMAN_ANATOMY_DIRECTIVE
    if anatomy_flags.get("quadruped"):
        suffix += QUADRUPED_ANATOMY_DIRECTIVE
    if had_hand_risk:
        suffix += HAND_SAFE_DIRECTIVE
    if anatomy_flags.get("crop"):
        suffix += LIMB_FRAME_SAFE_DIRECTIVE
    if anatomy_flags.get("human"):
        suffix += CARTOON_FACELESS_DIRECTIVE
    return suffix


def _append_no_text(prompt: str) -> str:
    """프롬프트 끝에 NO_TEXT_DIRECTIVE 를 중복 없이 부착."""
    p = (prompt or "").strip()
    if not p:
        return p
    if "NO TEXT, NO LETTERS" in p or "readable glyph-free image" in p:
        return p
    return p + NO_TEXT_DIRECTIVE


def apply_reference_style_prefix(prompt: str, has_reference: bool) -> str:
    """썸네일/재생성 등 외부 경로용 프리픽스 적용 헬퍼.

    이미 프리픽스가 붙어 있으면 중복 부착을 피한다. has_reference=False 이면
    스타일 프리픽스는 생략하되 **문자 금지 지시는 항상** 뒤에 붙인다
    (v1.1.72). 레퍼런스 유무와 무관하게 이미지에 텍스트가 끼어드는 걸 차단.
    """
    p = (prompt or "").strip()
    if has_reference:
        if "STYLE REFERENCE LOCK" not in p and not p.startswith("STYLE:"):
            p = REFERENCE_STYLE_PREFIX + p
    return _append_no_text(p)


# ── 캐릭터 슬롯 규칙 ──

def cut_has_character(cut_number: int) -> bool:
    """캐릭터 등장 비율 제한 해제.

    캐릭터 앵커(캐릭터 이미지 또는 설명)가 있으면 모든 컷이 캐릭터 등장 가능 컷이다.
    """
    if cut_number is None or cut_number < 1:
        return False
    return True


# ── 레퍼런스/캐릭터 이미지 수집 ──

def collect_reference_images(project_id: str, config: dict) -> list[str]:
    """config 의 reference_images 에서 절대 경로 목록을 반환."""
    ref_imgs = config.get("reference_images", [])
    project_dir = resolve_project_dir(project_id)
    paths = []
    for rel in ref_imgs:
        p = Path(rel)
        abs_path = p if p.is_absolute() else project_dir / rel
        if abs_path.exists():
            paths.append(str(abs_path))
    return paths


def collect_character_images(project_id: str, config: dict) -> list[str]:
    """config 의 character_images 에서 절대 경로 목록을 반환."""
    char_imgs = config.get("character_images", [])
    project_dir = resolve_project_dir(project_id)
    paths = []
    for rel in char_imgs:
        p = Path(rel)
        abs_path = p if p.is_absolute() else project_dir / rel
        if abs_path.exists():
            paths.append(str(abs_path))
    return paths


# ── 프롬프트 빌더 ──

def build_image_prompt(
    image_prompt: str,
    global_style: str,
    *,
    has_reference: bool = False,
    has_character_slot: bool = False,
    character_description: str = "",
) -> str:
    """최종 이미지 프롬프트 조합.

    v1.1.58: 레퍼런스 이미지가 있으면 스타일은 전적으로 레퍼런스에 위임.
    프롬프트에는 피사체/구도/동작만 남기고, global_style 등 스타일 텍스트는 주입하지 않는다.
    레퍼런스가 없을 때만 global_style 을 폴백으로 사용.
    """
    base = (image_prompt or "").strip()

    if has_reference:
        # ── 레퍼런스 있음 ──
        # v1.1.61: global_style 도 항상 포함. 이유: 로컬 ComfyUI 모델 중 일부는
        # IPAdapter 가 안 깔려있어서 레퍼런스 픽셀이 모델에 안 들어갈 수 있다.
        # 그 경우 스타일 정보가 텍스트 프리픽스뿐인데 그게 "스타일 복사하라" 는
        # 메타 지시라 실제 스타일 단어(예: "cartoon illustration")가 전혀 없다.
        # 결과가 기본값(실사)로 돌아가는 원인. global_style 을 항상 끼워넣어 안전.
        parts: list[str] = [REFERENCE_STYLE_PREFIX]

        style_hint = (global_style or "").strip()
        if style_hint:
            parts.append(f"Style keywords: {style_hint}.")

        if has_character_slot:
            char_desc = character_description.strip()
            if char_desc:
                parts.append(
                    f"This cut features the main character: {char_desc}. "
                    "From the character reference image, use ONLY shape, silhouette, and design. "
                    "Recolor and restyle the character to match the style reference images."
                )
            else:
                parts.append(
                    "This cut features the main character from the attached character "
                    "reference image. Use ONLY the character's shape and design. "
                    "Recolor and restyle the character to match the style reference images."
                )

        if base:
            parts.append(base)

        # v1.1.72: 모든 컷 프롬프트에 "문자 금지" 지시를 마지막에 강제 append
        return _append_no_text(" ".join(parts).strip())

    else:
        # ── 레퍼런스 없음: global_style 폴백 ──
        parts = []
        if global_style:
            parts.append(global_style.strip())
        if base:
            parts.append(base)

        if has_character_slot:
            char_desc = character_description.strip()
            if char_desc:
                parts.append(
                    f"This cut features the main character: {char_desc}. "
                    "Place the character clearly in frame, pose matching the scene."
                )

        # v1.1.72: 레퍼런스 없는 경로에도 동일하게 "문자 금지" 지시 강제
        return _append_no_text(" ".join(parts).strip())
