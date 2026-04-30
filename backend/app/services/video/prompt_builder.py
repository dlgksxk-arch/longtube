"""영상 모션 프롬프트 빌더 + AI 비디오 타겟 선택 유틸.

v1.1.52: pipeline_tasks._step_video 와 routers/video.py 가 동일한 로직을
공유하기 위해 분리. 라우터를 직접 import 하면 FastAPI 의존성이 끌려오므로
순수 함수만 이 모듈에 배치한다.
"""
import re


VIDEO_TARGET_OPTIONS = {"all", "every_3", "every_4", "every_5", "character_only", "none"}


HUNYUAN_PROMPT_MODEL_IDS = {
    "comfyui-hunyuan15-480p",
    # Deprecated local IDs are remapped to Hunyuan by factory.resolve_video_model.
    "comfyui-ltxv-2b",
    "comfyui-ltxv-13b",
    "comfyui-wan22-i2v-fast",
    "comfyui-wan22-ti2v-5b",
    "comfyui-wan22-5b",
}


WAN_TI2V_PROMPT_MODEL_IDS: set[str] = set()


def _is_hunyuan_prompt_model(config: dict | None) -> bool:
    cfg = config or {}
    model_id = str(cfg.get("resolved_video_model") or cfg.get("video_model") or "").strip()
    if not model_id:
        return False
    return model_id in HUNYUAN_PROMPT_MODEL_IDS or model_id.startswith("comfyui-hunyuan")


def _is_wan_ti2v_prompt_model(config: dict | None) -> bool:
    cfg = config or {}
    model_id = str(cfg.get("resolved_video_model") or cfg.get("video_model") or "").strip()
    return model_id in WAN_TI2V_PROMPT_MODEL_IDS


VIDEO_NEGATIVE_PROMPT = (
    "low quality, blurry, watermark, text, logo, subtitles, flicker, jitter, "
    "camera shake, sudden cut, scene change, object popping, geometry warping, "
    "new object, new subject, new person, new character, new prop, appearing object, "
    "spawned object, hallucinated object, extra object, extra person, invented prop, "
    "new light source, new smoke, new dust cloud, new particles, new vehicle, new animal, "
    "person appearing, character appearing, face appearing, added face, new face, "
    "floating head, head-shaped glow, face in abstract pattern, face-like pattern, accidental face, pareidolia, "
    "anthropomorphic object, humanoid object, object with eyes, object with nose, "
    "object with mouth, object with face, eyes appearing, nose appearing, "
    "mouth appearing, facial features appearing, smiley face, simple face, "
    "cartoon face, drawn face, face on cartoon character, facial features on cartoon character, "
    "eyes on cartoon character, nose on cartoon character, mouth on cartoon character, "
    "eyebrows on cartoon character, anime face, human face on simple cartoon character, "
    "facial expression change, changing expression, smile, smiling, frown, frowning, "
    "mouth movement, talking mouth, lip sync, blinking, eye blink, moving eyes, eyebrow movement, "
    "unmotivated large motion, impossible object transformation, identity change, "
    "moving background, animated background, camera pan, camera zoom, camera drift, "
    "handheld camera, dolly movement, background parallax, moving horizon, "
    "melting buildings, wobbly houses, breathing walls, liquid background, "
    "morphing architecture, bending roof lines, distorted windows, warped doors, "
    "unstable perspective, background swimming, texture crawling, deformed hands, "
    "extra fingers, extra limbs, face morphing, identity drift, motion blur, "
    "afterimage, ghosting, double exposure, transparent duplicate, duplicate people, "
    "duplicate silhouette, translucent clone, frame echo, long exposure, speed lines, "
    "optical flow artifacts, temporal interpolation artifacts, frame blending, "
    "motion trails, trailing silhouette, smeared edges, smeared body, smeared hands, "
    "stretched limbs, multiple heads, multiple bodies"
)


CARTOON_FACELESS_VIDEO_DIRECTIVE = (
    "Cartoon/simple character face lock: if a cartoon, mascot, or simple character is already visible, "
    "keep the head as the same blank simple shape from the source image. Do not create or reveal eyes, "
    "nose, mouth, eyebrows, smile, frown, expression, anime face, or detailed human face. The body, "
    "head, and face area stay source-locked unless a separate prompt explicitly allows body motion."
)


NO_PERSON_SOURCE_LOCK = (
    "SOURCE PRESERVATION LOCK: the input image is the only allowed visual inventory. "
    "Preserve every already-visible source element exactly, including any faceless cartoon "
    "figure that the source image may already contain. Do not add, remove, replace, or "
    "reinterpret subjects. Object count, character count, object identity, character identity, "
    "and scene layout must remain identical to frame one. Existing blank heads stay blank. "
    "Animate only an already-visible light, node, line, screen, paper, cloth, machine part, "
    "water surface, smoke, dust, or foreground object with local shimmer, pulse, rotation, "
    "tilt, or sway. If no clearly visible existing element can move safely, keep the clip "
    "source-locked with only tiny local shimmer instead of inventing anything."
)


PERSON_FACE_FREEZE_LOCK = (
    "PERSON/FACE LOCK: keep the already visible body and object silhouette source-locked. "
    "If a head or face is blank, faceless, tiny, hidden, or simplified in the source image, "
    "keep it exactly that way. Do not add eyes, nose, mouth, eyebrows, teeth, pupils, "
    "smile, frown, expression, lip motion, blinking, or detailed facial texture."
)


_PERSON_RE = re.compile(
    r"\b(person|people|man|woman|boy|girl|child|character|figure|silhouette|"
    r"researcher|scholar|professor|scientist|engineer|worker|soldier|king|queen|"
    r"farmer|teacher|student|detective|doctor|human|robot|android|humanoid|mascot|cartoon)\b",
    flags=re.IGNORECASE,
)


_NEGATED_PERSON_RE = re.compile(
    r"\b(?:no|without|zero|none|not\s+any|absence\s+of|empty\s+of|lacking)\s+"
    r"(?:visible\s+)?(?:person|persons|people|man|men|woman|women|boy|girl|child|"
    r"children|character|characters|figure|figures|silhouette|silhouettes|human|"
    r"humans|robot|robots|android|androids|humanoid|humanoids|mascot|mascots|cartoon|cartoons)\b",
    flags=re.IGNORECASE,
)


def _has_visible_person_reference(text: str) -> bool:
    """Avoid treating negative phrases like 'no people' as visible people."""
    cleaned = _NEGATED_PERSON_RE.sub(" ", text or "")
    return bool(_PERSON_RE.search(cleaned))


_HUMAN_MOTION_RE = re.compile(
    r"\b(person|people|man|woman|boy|girl|child|character|figure|silhouette|"
    r"face|head|eyes?|mouth|scientist|researcher|scholar|professor|worker|soldier|human|"
    r"robot|android|humanoid|mascot|cartoon|subject|reacts?|looks?|turns?|walks?|steps?|leans?|"
    r"smiles?|speaks?|talks?)\b",
    flags=re.IGNORECASE,
)


_CAMERA_ONLY_MOTION_RE = re.compile(
    r"^\s*(?:locked\s+tripod\s+shot|fixed\s+camera|static\s+camera|almost\s+static\s+frame|almost\s+static\s+shot)\s*[.;]?\s*$",
    flags=re.IGNORECASE,
)


_SCRIPT_MOTION_REPLACEMENTS = (
    (r"\bmotion\s+blur\b", "sharp single-exposure motion"),
    (r"\bspeed\s+lines?\b", "clean readable motion"),
    (r"\blong\s+exposure\b", "sharp single-exposure motion"),
    (r"\bdouble\s+exposure\b", "single solid subject"),
    (r"\bafter\s*image\b", "single solid subject"),
    (r"\bghost(?:ing|ly|s)?\b", "single solid subject"),
    (r"\btrail(?:ing|s)?\b", "clean sharp edges"),
    (r"\bfast\s+pan\b", "locked tripod shot while the subject turns"),
    (r"\bwhip\s+pan\b", "locked tripod shot while the subject turns"),
    (
        r"\b(?:very\s+)?(?:slow\s+)?(?:tiny\s+)?push[\s-]?in\s+toward\s+[^,.]+?\s+as\s+",
        "locked tripod shot as ",
    ),
    (
        r"\b(?:very\s+)?(?:slow\s+)?(?:tiny\s+)?push[\s-]?in\s+toward\s+[^,.]+?\s+(with|while)\s+",
        r"locked tripod shot \1 ",
    ),
    (
        r"\b(?:very\s+)?(?:slow\s+)?(?:tiny\s+)?pull[\s-]?back\s+from\s+[^,.]+?\s+as\s+",
        "locked tripod shot as ",
    ),
    (
        r"\b(?:very\s+)?(?:slow\s+)?(?:tiny\s+)?pull[\s-]?back\s+from\s+[^,.]+?\s+(with|while)\s+",
        r"locked tripod shot \1 ",
    ),
    (
        r"\b(?:very\s+)?(?:slow\s+)?(?:tiny\s+)?push[\s-]?in(?:\s+toward\s+[^,.]+)?",
        "locked tripod shot",
    ),
    (
        r"\b(?:very\s+)?(?:slow\s+)?(?:tiny\s+)?pull[\s-]?back(?:\s+from\s+[^,.]+)?",
        "locked tripod shot",
    ),
    (r"\brun(?:s|ning)?\s+across\s+the\s+frame\b", "takes one controlled small in-place step"),
    (r"\bpoints?\s+with\s+(?:one\s+)?finger\s+toward\s+[^,.]+", "turns the torso toward the subject"),
    (r"\bpoints?\s+with\s+(?:one\s+)?finger\b", "turns the torso toward the subject"),
    (r"\breaches?\s+with\s+(?:a\s+)?hand\b", "leans slightly toward the subject"),
    (r"\bfingertips?\b", "hands kept still"),
    (r"\bfingers?\b", "hands kept still"),
    (
        r"\b(?:the\s+)?(?:room|scene|background|air)\s+fills?\s+with\s+(?:energy|light|smoke|mist|particles)\b",
        "existing source elements pulse or shift locally",
    ),
    (
        r"\b(?:new|another|extra)\s+[^,.]+?\s+(?:appears?|emerges?|materializes?|forms?)\b",
        "existing source elements pulse or shift locally",
    ),
    (
        r"\b[^,.]+?\s+(?:appears?|emerges?|materializes?|forms?)\b",
        "existing source elements pulse or shift locally",
    ),
    (r"\btransforms?\s+into\s+[^,.]+", "moves without changing identity"),
    (r"\bturns?\s+into\s+[^,.]+", "moves without changing identity"),
)


def _source_inventory_clause(image_context: str) -> str:
    if not image_context:
        return "the visible source image elements"
    return image_context


def has_visible_person_hint(cut_data: dict | None, config: dict | None = None) -> bool:
    """Text-side guard for whether generative I2V may animate a person.

    Hunyuan can hallucinate people/faces when the source prompt is object-only
    or abstract. We only allow generative I2V when the image prompt itself
    clearly says a person/character/silhouette is visible.
    """
    if not isinstance(cut_data, dict):
        return False
    image_context = _compact_text(cut_data.get("image_prompt"), limit=420)
    if _has_visible_person_reference(image_context):
        return True
    return False


def should_force_safe_motion(
    cut_data: dict | None,
    config: dict | None = None,
    video_model: str | None = None,
) -> bool:
    """Return True when local source-locked motion should replace generative I2V."""
    cfg = config or {}
    # Disabled by default: a fully static/FFmpeg-safe clip avoids hallucination
    # but is not acceptable as the normal viewing experience.
    if cfg.get("video_safe_motion_guard", False) is not True:
        return False
    model_id = str(video_model or cfg.get("video_model") or "")
    if model_id and not model_id.startswith("comfyui-hunyuan"):
        return False
    return not has_visible_person_hint(cut_data, cfg)


def _sanitize_motion_for_source(script_motion: str, *, has_visible_person: bool) -> str:
    text = _compact_text(script_motion, limit=520)
    if not text:
        return ""
    if has_visible_person:
        return text
    if _HUMAN_MOTION_RE.search(text):
        return "existing source elements pulse or shift locally"
    return text


def _safe_prop_motion_for_person(script_motion: str, image_context: str) -> str:
    """Return a prop/light/screen-only motion cue for person cuts."""
    text = _compact_text(script_motion, limit=360)
    lowered = text.lower()
    if text and not _CAMERA_ONLY_MOTION_RE.match(text):
        # Keep only safe non-body motion clauses. Human/body verbs are too
        # likely to produce ghosting in Hunyuan cartoon shots.
        if any(token in lowered for token in ("monitor", "screen", "glow", "light", "bulb", "panel", "display")):
            return re.sub(
                r"\b(?:researcher|person|character|figure|human|head|body|arm|hand|torso|face)\b",
                "visible prop",
                text,
                flags=re.IGNORECASE,
            )
        if any(token in lowered for token in ("paper", "cloth", "smoke", "dust", "snow", "water", "machine", "computer")):
            return text

    ctx = (image_context or "").lower()
    if any(token in ctx for token in ("monitor", "screen", "display")):
        return "the existing monitor and screen glow softly pulses"
    if any(token in ctx for token in ("light", "bulb", "lamp", "glow")):
        return "the existing light source softly pulses"
    if any(token in ctx for token in ("computer", "machine", "panel")):
        return "existing machine panel lights blink subtly"
    if any(token in ctx for token in ("paper", "newspaper", "document")):
        return "existing paper edges flutter slightly"
    return "one existing nearby prop or light source moves softly"


def _compact_text(value: object, limit: int = 520) -> str:
    if value is None:
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip().strip('"').strip("'")
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(" ,.;")
    return text


def _clean_script_motion_prompt(cut_data: dict | None) -> str:
    if not isinstance(cut_data, dict):
        return ""
    text = _compact_text(
        cut_data.get("motion_prompt") or cut_data.get("video_motion_prompt"),
        limit=520,
    )
    if not text:
        return ""
    for pattern, replacement in _SCRIPT_MOTION_REPLACEMENTS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:a|an|the)\s+one already visible\b", "one already visible", text, flags=re.IGNORECASE)
    return _compact_text(text, limit=520)


def _raw_script_motion_prompt(cut_data: dict | None) -> str:
    if not isinstance(cut_data, dict):
        return ""
    return _compact_text(
        cut_data.get("motion_prompt") or cut_data.get("video_motion_prompt"),
        limit=420,
    )


def _build_generic_video_motion_prompt(
    cut_number: int,
    total_cuts: int,
    config: dict,
    cut_data: dict | None = None,
) -> str:
    """Cloud/API models get a lighter, non-Hunyuan prompt path."""
    cfg = config or {}
    is_first = cut_number == 1
    is_last = total_cuts > 0 and cut_number == total_cuts
    character_description = (cfg.get("character_description") or "").strip()
    has_character_anchor = bool(character_description or (cfg.get("character_images") or []))
    is_character_cut = has_character_anchor and (cut_number - 1) % 5 == 0
    script_motion = _raw_script_motion_prompt(cut_data)
    image_context = _compact_text((cut_data or {}).get("image_prompt"), limit=220)

    if script_motion:
        if is_first:
            opener = "Opening 5-second image-to-video shot."
        elif is_last:
            opener = "Ending 5-second image-to-video shot."
        else:
            opener = "Cinematic 5-second image-to-video shot."
        parts = [
            opener,
            f"Follow the scripted motion cue: {script_motion}.",
            "Preserve the source image's main subject, style, and composition.",
            "Natural coherent motion, no sudden scene change, no extra people or props unless already visible in the source image.",
        ]
        if image_context:
            parts.append(f"Keep the motion consistent with the source image content: {image_context}.")
        return " ".join(parts)

    parts: list[str] = []
    if is_first:
        parts.append(
            "Gentle cinematic opening movement with a slow push-in, subtle ambient motion, and stable composition."
        )
    elif is_last:
        parts.append(
            "Gentle cinematic ending movement with a slow pull-back, subtle ambient motion, and stable composition."
        )
    else:
        parts.append(
            "Smooth cinematic motion with a slow controlled camera move and subtle natural movement in the scene."
        )

    if is_character_cut and character_description:
        parts.append(
            f"The main character ({character_description}) moves naturally but subtly while preserving identity and style."
        )
    elif is_character_cut:
        parts.append("The main character moves naturally but subtly while preserving identity and style.")
    else:
        parts.append("Keep motion smooth, coherent, and faithful to the source image.")

    if image_context:
        parts.append(f"Source image context: {image_context}.")
    parts.append("Avoid sudden cuts, heavy warping, or adding unrelated new subjects.")
    return " ".join(parts)


def _build_wan_ti2v_motion_prompt(
    cut_number: int,
    total_cuts: int,
    config: dict,
    cut_data: dict | None = None,
) -> str:
    """Wan TI2V is hybrid T2V/I2V, so make the uploaded image the hard anchor."""
    script_motion = _raw_script_motion_prompt(cut_data)
    image_context = _compact_text((cut_data or {}).get("image_prompt"), limit=180)
    has_visible_person = _has_visible_person_reference(" ".join([image_context, script_motion]))
    is_first = cut_number == 1
    is_last = total_cuts > 0 and cut_number == total_cuts
    shot_type = "opening" if is_first else "ending" if is_last else "cinematic"
    weak_motion = not script_motion or bool(
        re.search(r"\b(almost static|static shot|tiny|subtle|very slight|slow push|push-in|pull-back)\b", script_motion, re.IGNORECASE)
    )

    parts = [
        f"{shot_type.capitalize()} 5-second image-to-video shot.",
        (
            "Use the uploaded source image as the exact first frame and the hard visual anchor. "
            "This is image-to-video; the text is only a motion hint, never permission to redraw the scene."
        ),
        (
            "Preserve the source image composition, subject count, object count, silhouettes, layout, "
            "style, colors, camera angle, and background identity throughout the clip."
        ),
    ]
    if image_context:
        parts.append(
            f"Reference-only source description: {image_context}. If this text conflicts with the uploaded image, obey the uploaded image."
        )
    if script_motion:
        parts.append(
            f"Apply only this motion cue to the already visible source-image elements: {script_motion}."
        )
    else:
        parts.append("Add gentle natural motion only to already visible source-image elements.")
    if has_visible_person:
        if weak_motion:
            parts.append(
                "Visible motion is required: the already visible person or character makes one controlled body action, "
                "such as a clear in-place weight shift, a slight torso turn, shoulder sway, backpack or clothing sway, "
                "or soft jacket movement. Both feet stay planted on the floor; no walking, no foot lifting, no leg crossing. "
                "Keep the head shape and any face area unchanged."
            )
        else:
            parts.append(
                "Make the existing person or character visibly move through in-place body posture, shoulders, torso, clothing, "
                "or carried props only. Both feet stay planted; no walking or large limb swing. Do not animate facial features."
            )
    elif weak_motion:
        parts.append(
            "Visible motion is required: animate one already visible source object through most of the clip, such as a light pulse, "
            "screen glow change, machine part movement, paper or cloth sway, water ripple, node shimmer, or object tilt. "
            "Do not rely on camera push-in as the main motion."
        )
    parts.append(
        "Do not invent a new scene from text. No new people, no new characters, no new faces, "
        "no new props, no scene replacement, no identity change, no sudden composition change. "
        "Move only already visible pixels and objects. Keep the source image recognizable in every frame. "
        "For Wan local generation, avoid gait animation; prefer planted-feet upper-body and prop motion."
    )
    return " ".join(parts)


def should_generate_ai_video(cut_number: int, selection: str, ai_first_n: int = 5) -> bool:
    """주어진 cut 이 primary video_model 로 처리돼야 하는지 판단.

    v1.1.55: `ai_first_n` 이 양수이면 컷 1..N 은 selection 과 무관하게 무조건
    AI. 인트로 5컷의 임팩트가 영상 후킹의 핵심이라 사용자가 매번 강제했다.
    DEFAULT_CONFIG 의 `ai_video_first_n` (기본 5) 가 여기로 흘러들어온다.
    """
    if cut_number is None or cut_number < 1:
        return False
    # ★ 앞 N 컷 강제 AI — 모든 selection 위에 군림하는 규칙
    try:
        n = int(ai_first_n)
    except (TypeError, ValueError):
        n = 0
    if selection == "none":
        return False
    if n > 0 and cut_number <= n:
        return True
    if selection not in VIDEO_TARGET_OPTIONS:
        return True
    if selection == "all":
        return True
    if selection == "every_3":
        return (cut_number - 1) % 3 == 0
    if selection == "every_4":
        return (cut_number - 1) % 4 == 0
    if selection == "every_5":
        return (cut_number - 1) % 5 == 0
    if selection == "character_only":
        return (cut_number - 1) % 5 == 0
    return True


def build_video_motion_prompt(
    cut_number: int,
    total_cuts: int,
    config: dict,
    cut_data: dict | None = None,
) -> str:
    """컷별 영상 모션 프롬프트 생성. routers/video.py 의 _build_video_motion_prompt 와 동일."""
    cfg = config or {}
    if not _is_hunyuan_prompt_model(cfg):
        if _is_wan_ti2v_prompt_model(cfg):
            return _build_wan_ti2v_motion_prompt(cut_number, total_cuts, cfg, cut_data=cut_data)
        return _build_generic_video_motion_prompt(cut_number, total_cuts, cfg, cut_data=cut_data)

    is_first = cut_number == 1
    is_last = total_cuts > 0 and cut_number == total_cuts
    character_description = (cfg.get("character_description") or "").strip()
    has_character_anchor = bool(character_description or (cfg.get("character_images") or []))
    is_character_cut = has_character_anchor and (cut_number - 1) % 5 == 0
    script_motion = _clean_script_motion_prompt(cut_data)
    image_context = _compact_text((cut_data or {}).get("image_prompt"), limit=220)
    # Hunyuan must not create a character just because the preset has one.
    # Only treat this as a person/character clip when the source image prompt
    # itself says a person-like subject is visible.
    has_visible_person = _has_visible_person_reference(image_context)
    script_motion = _sanitize_motion_for_source(script_motion, has_visible_person=has_visible_person)
    script_motion_clause = script_motion.rstrip(" .;")
    source_inventory = _source_inventory_clause(image_context)

    if has_visible_person:
        prop_motion = _safe_prop_motion_for_person(script_motion_clause, image_context)
        person_parts = [
            "Locked tripod shot. Preserve the exact source image composition.",
            f"Source image content: {source_inventory}.",
            (
                "Every visible person or character remains completely still, solid opaque, crisp black outline, "
                "same pose, same hands, same head shape, same clothing, same seated or standing position for every frame."
            ),
            (
                "For faceless or simple cartoon characters, the blank head stays blank and unchanged for every frame."
            ),
            (
                f"Express the motion cue ({prop_motion}) only through existing light sources, monitor screens, machinery, "
                "paper, cloth, smoke, dust, or glow that is already visible in the input image."
            ),
            (
                "The desk, chair, body, arms, hands, head, clothing, face area, and background stay fixed and composition-locked. "
                "Smooth clean source-preserving animation."
            ),
            CARTOON_FACELESS_VIDEO_DIRECTIVE,
        ]
        return " ".join(person_parts)

    parts: list[str] = []

    # Local I2V models tend to animate the whole frame unless told otherwise.
    # Lock the background first, then describe stronger foreground/person motion.
    if is_first:
        parts.append(
            "Locked tripod opening shot. The camera is completely fixed: no pan, "
            "no zoom, no push-in, no pull-back, no drift."
        )
    elif is_last:
        parts.append(
            "Locked tripod ending shot. The camera is completely fixed: no pan, "
            "no zoom, no push-in, no pull-back, no drift."
        )
    else:
        parts.append(
            "Locked tripod documentary shot. The camera is completely fixed: no pan, "
            "no zoom, no push-in, no pull-back, no drift."
        )

    if script_motion:
        if has_visible_person:
            parts.append(
                "Script-planned motion based on this cut's image prompt, narration, "
                f"and episode mood: {script_motion_clause}. Apply it as existing prop, light, screen, machinery, paper, cloth, smoke, or glow motion only. "
                "Keep the visible inventory unchanged: same people, same props, same scene, same identities, same composition. "
                "Keep any visible person completely source-locked: exact pose, solid opaque body, crisp black outline, same body silhouette, same head shape, same clothing, same hands, and same seated/standing position for every frame. "
                "Use motion only on existing nearby props, light sources, screens, machinery, paper, cloth, smoke, or glow. "
                "Keep the face, head shape, and expression frozen exactly as in the source image: no smile, no frown, no mouth movement, no blinking, no eye movement. "
                "For cartoon/simple characters, keep the head blank with no eyes, nose, mouth, eyebrows, or expression. "
                "Never animate the background."
            )
        else:
            parts.append(
                "Source-preserving animation based on this cut's image prompt, narration, "
                f"and episode mood: {script_motion_clause}. Map that motion only onto existing source elements. "
                f"Source inventory: {source_inventory}. "
                "Do not add or remove any visible subject. If the actual input image already contains a faceless cartoon figure, keep that exact figure faceless, unchanged in identity, and mostly still. "
                "Animate existing nodes, lines, lights, screens, machinery, paper, cloth, water, smoke, dust, or foreground objects only when already present in the input image. "
                "Prefer local pulse, shimmer, small in-place rotation, slight tilt, or gentle sway while preserving the exact same layout and identities. "
                "If the requested motion cannot be mapped to a clearly visible existing source element, use only a tiny local shimmer on existing lights, nodes, or lines. "
                "Camera and background stay fixed. Source image remains recognizable and composition-locked. "
                f"{NO_PERSON_SOURCE_LOCK}"
            )
        if image_context:
            parts.append(
                "Keep the animated scene consistent with the source image content: "
                f"{image_context}. Treat this source image as the complete inventory of allowed visible objects."
            )
    elif is_character_cut and character_description and has_visible_person:
        parts.append(
            f"The main character ({character_description}) is the only preserved subject: "
            f"If the actual input image does not visibly contain this character, do not create the character; animate one existing non-human foreground object instead. "
            f"keep the character completely source-locked and still. Use motion only on existing nearby props, light, screens, machinery, paper, cloth, smoke, or glow. "
            f"Avoid detailed finger or hand motion. Keep the face, head shape, body silhouette, and expression completely frozen: no smile, no frown, "
            f"no blinking, no eye movement, no mouth movement. For cartoon/simple characters, keep the head blank with no eyes, nose, mouth, eyebrows, or expression. Keep a crisp solid silhouette with no ghost trail. Keep the outfit, "
            f"body shape, and identity exactly consistent."
        )
    elif is_character_cut and has_visible_person:
        parts.append(
            "The main character is source-locked and still. "
            "If the actual input image does not visibly contain this character, do not create the character; animate one existing non-human foreground object instead. "
            "Use motion only on existing nearby props, light, screens, machinery, paper, cloth, smoke, or glow. "
            "Avoid detailed finger or hand motion. Keep the face, head shape, body silhouette, and expression completely frozen: "
            "no smile, no frown, no blinking, no eye movement, no mouth movement. For cartoon/simple characters, keep the head blank with no eyes, nose, mouth, eyebrows, or expression. Keep a crisp solid "
            "silhouette with no ghost trail. Preserve identity exactly."
        )
    else:
        if has_visible_person:
            parts.append(
                "Choose only existing prop, light, screen, machinery, paper, cloth, smoke, or glow motion while all visible people remain still. "
                "If the actual input image does not visibly contain a person, do not create one; animate one existing non-human foreground object instead. "
                "Keep every visible person completely source-locked: exact pose, solid opaque body, crisp black outline, same body silhouette, same head shape, same clothing, same hands, and same seated/standing position for every frame. "
                "Use motion only on existing nearby props, light, screens, machinery, paper, cloth, smoke, or glow. "
                "Keep face and expression frozen: "
                "no smile, no frown, no blinking, no eye movement, no mouth movement. For cartoon/simple characters, keep the head blank with no eyes, nose, mouth, eyebrows, or expression."
            )
        else:
            parts.append(
                "Source-preserving animation. Use only the existing source elements and keep the "
                "background locked. Do not add or remove any visible subject. If the source already "
                "contains a faceless cartoon figure, keep that exact figure faceless, unchanged in identity, "
                "and mostly still. Animate one already visible source element "
                "with local motion through most of the 5-second clip: an existing light "
                "or screen glow pulses, an existing node or line shimmers, an existing machine part "
                "rotates in place, an existing paper or cloth edge sways, an existing water surface "
                "ripples, or one existing source object tilts slightly without changing identity. "
                "Only use smoke, dust, particles, symbols, or extra light when those elements are "
                "already visible in the input image. If a requested element is not visible, use "
                "small local shimmer on an existing light, node, line, or object instead. "
                "Source image remains recognizable and composition-locked. "
                f"{NO_PERSON_SOURCE_LOCK}"
            )

    if has_visible_person:
        parts.append(
            "I2V source-image lock: animate only existing pixels/objects from the input image. "
            "If a person is mentioned in text but is not visibly present in the actual input image, do not create that person. "
            "No new people, no new faces, no new silhouettes, no new bodies, no new characters, no new props, no new vehicles, no new animals, no new symbols, no added text, "
            "no new lights, no new smoke, no new dust, no extra silhouettes, no newly appearing objects. "
            "Every visible person remains exactly one solid opaque body with a crisp black outline and stable frame-to-frame silhouette. "
            "Faces and facial expressions must remain unchanged and frozen. No blinking, no eye movement, no mouth movement, no smile, no frown. "
            "For cartoon/simple characters, do not generate facial features: no eyes, no nose, no mouth, no eyebrows, no expression. "
            f"{PERSON_FACE_FREEZE_LOCK} "
            "Prefer readable motion on existing props, light, screens, machinery, paper, cloth, smoke, or glow from the first second to the last, while every visible person remains source-locked and the background remains locked. "
            "Preserve the original image composition. Background is fixed like a still photograph. "
            "Background buildings, houses, roofs, "
            "windows, doors, furniture, mountains, roads, and horizon lines must stay rigid "
            "and geometrically stable with zero motion. No background parallax, no camera movement, "
            "stable architecture, stable textures, crisp solid outlines, smooth clean motion only."
        )
    else:
        parts.append(
            "I2V source-image lock: the source image inventory is complete, and only existing pixels/objects may animate. "
            f"Source inventory: {source_inventory}. "
            "All circles, orbs, lights, stones, monitors, boards, symbols, shadows, glows, lines, nodes, and abstract patterns remain their original object type. "
            "Object count, object identity, and scene layout must stay identical to frame one. "
            "No anthropomorphic transformation and no scene reinterpretation. "
            "Prefer a readable local motion arc only on one already visible source element "
            "from the first second to the last, while the background remains locked. "
            "If the model cannot move an existing source element safely, keep the frame mostly source-locked with local shimmer instead of inventing motion. "
            "Preserve the original image composition. Background is fixed like a still photograph. "
            "Background buildings, houses, roofs, "
            "windows, doors, furniture, mountains, roads, and horizon lines must stay rigid "
            "and geometrically stable with zero motion. No background parallax, no camera movement, "
            "no melting, no wobbling, no breathing walls, no liquid background, "
            "no morphing architecture, no texture crawling. No afterimages, no "
            "motion trails, no transparent duplicate objects. Smooth crisp motion only. "
            f"{NO_PERSON_SOURCE_LOCK}"
        )

    parts.append(CARTOON_FACELESS_VIDEO_DIRECTIVE)

    return " ".join(parts)
