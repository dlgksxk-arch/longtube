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
    "CHARACTERS, NO BOOK PAGES WITH WRITING, NO NEWSPAPERS, NO BILLBOARDS WITH COPY, NO "
    "SCREEN TEXT, NO SUBTITLES, NO WATERMARKS, NO FAKE GLYPHS, NO PSEUDO CALLIGRAPHY, "
    "NO FAKE KANJI, NO CRESTS, NO EMBLEMS, NO LOGOS, NO DECORATIVE SYMBOL MARKS "
    "anywhere in the image. All "
    "surfaces that might normally carry writing (signs, screens, posters, book "
    "covers, clothing, packaging, wall hangings, banners, flags, armor plates, "
    "ship sails, boxes, labels) must be completely BLANK and unmarked. This is a "
    "hard requirement — any glyph, fake character, crest, emblem, logo, or symbol "
    "mark is a failure."
)

NO_TEXT_NEGATIVE_PROMPT = (
    "text, letters, words, numbers, writing, typography, captions, subtitles, labels, "
    "sign, signage, readable sign, readable text, readable letters, readable words, "
    "glyphs, characters, writing on book pages, fake book text, newspaper, poster text, billboard text, screen text, "
    "fake glyphs, pseudo calligraphy, fake kanji, fake characters, decorative symbols, "
    "symbol marks, crests, emblems, heraldic marks, mon crest, family crest, armor emblem, "
    "banner symbol, flag symbol, sail symbol, watermark, logo, signature, title text, credits"
)

NO_MAP_DIRECTIVE = (
    " || ★ HARD CONSTRAINT — ABSOLUTELY NO MAPS, NO CARTOGRAPHY, NO ATLAS VIEW, "
    "NO TERRITORY MAP, NO BORDER MAP, NO ROUTE MAP, NO MIGRATION MAP, NO BATTLE "
    "MAP, NO GEOGRAPHIC DIAGRAM, NO TOPOGRAPHIC VIEW, NO COUNTRY OUTLINE, NO "
    "REGION OUTLINE, NO COASTLINE MAP, NO ARROWS ON A MAP, NO DOTTED ROUTE LINES, "
    "NO LOCATION PINS, NO COMPASS ROSE, NO LEGEND, NO SCALE BAR, NO GLOBE, NO "
    "SATELLITE VIEW. Depict the scene as a cinematic human-scale historical "
    "moment, artifact, landscape, architecture, or action instead. This applies "
    "even if the prompt mentions routes, migration, borders, kingdoms, territory, "
    "or geography."
)

NO_MAP_NEGATIVE_PROMPT = (
    "map, maps, cartography, atlas, territory map, border map, route map, migration map, "
    "battle map, geographic diagram, topographic map, country outline, region outline, "
    "coastline map, arrows on map, dotted route line, location pin, map marker, compass "
    "rose, legend, scale bar, globe, satellite view"
)

BOOK_RENDER_DIRECTIVE = (
    " || BOOK RENDERING LOCK - if any book, notebook, manuscript, codex, ledger, "
    "journal, scripture, archive volume, page spread, or document appears, draw it "
    "as one coherent physical object. For an open book: exactly one book, exactly "
    "two facing pages, one central spine/gutter, aligned covers, curved page edges, "
    "and stacked page thickness visible at the outer edges. No third page, no "
    "duplicated open books fused together, no floating pages, no impossible folds, "
    "no warped spine. All pages and covers must be blank paper or subtle paper "
    "grain only: no fake writing, no rows of text-like lines, no glyphs, no symbols."
)

BOOK_RENDER_NEGATIVE_PROMPT = (
    "extra book pages, three page spread, multiple fused books, duplicated open book, "
    "warped book spine, broken book geometry, floating pages, detached pages, "
    "impossible folded pages, melted book, fake writing on pages, rows of text lines, "
    "pseudo text, scribbles on book, glyphs on book, symbols on pages"
)

_FLAG_MOTIF_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\bmodern\s+national\s+flags?\b",
    r"\bnational\s+flags?\b",
    r"\bcountry\s+flags?\b",
    r"\bstate\s+flags?\b",
    r"\bflagpoles?\b",
    r"\bflags?\b",
    r"\bnational\s+emblems?\b",
    r"\bnational\s+symbols?\b",
    r"\btricolor\b",
    r"\bstars\s+and\s+stripes\b",
    r"\bcanton\s+stars\b",
    r"\bflag\s+stripes\b",
    r"\bnational\s+color\s+blocks\b",
    r"\bJapanese\s+flags?\b",
    r"\bhinomaru\b",
    r"\brising\s+sun\s+flags?\b",
    r"\brising\s+sun\s+rays\b",
    r"\bred\s+sun\s+disc\b",
    r"\bred\s+circle\s+on\s+white\s+background\b",
    r"\bcentered\s+red\s+(?:circle|disc)\b",
    r"\bwhite\s+field\s+with\s+red\s+circle\b",
    r"\bred\s+radial\s+rays\b",
    r"\bsunburst\s+flags?\b",
    r"\bimperial\s+Japanese\s+flags?\b",
)

KOREAN_HISTORY_ACCURACY_DIRECTIVE = (
    " || HISTORICAL ACCURACY LOCK - this scene is Korean history. Match the exact "
    "This fixed lock has higher priority than any user-entered image prompt or style prompt. "
    "era, kingdom, region, material culture, clothing, hairstyle, headwear, "
    "jewelry and accessories, architecture, weapons, armor, tools, everyday "
    "objects, ritual objects, vehicles, vessels, landscape, and materials implied "
    "by the subject. If the subject is "
    "Goguryeo, Baekje, Silla, Gaya, Balhae, Gojoseon, Buyeo, Three Kingdoms, "
    "Goryeo, or Joseon, use period-correct Korean visual culture only. "
    "The specified time period, region, and place in the prompt are non-negotiable "
    "and must be considered before choosing any costume, prop, architecture, or vehicle. "
    "Visible costume, hair, armor, tools, and props must prove the exact period; "
    "do not use generic fantasy, cosplay, stage costume, or famous wrong-era looks. "
    "Do not mix in modern national symbols or anachronistic props. "
    "Forbidden unless the prompt explicitly says the scene is in Japan: Japanese "
    "flag, rising sun flag, red sun disc flag, torii gate, Shinto shrine, samurai, "
    "ninja, katana, kimono, Japanese castle, Japanese text, modern flags, modern "
    "uniforms, modern buildings, vehicles, power lines, neon signs, logos."
)

KOREAN_HISTORY_NEGATIVE_PROMPT = (
    "Japanese flag, rising sun flag, red sun disc flag, hinomaru, torii gate, "
    "Shinto shrine, samurai, ninja, katana, kimono, Japanese castle, Japanese text, "
    "steamship, steamboat, steam engine, locomotive, train, railroad, railway, "
    "factory chimney, smokestack, industrial machinery, modern flag, modern national "
    "flag, modern uniform, modern building, car, truck, power line, neon sign, logo"
)

GENERAL_HISTORY_NEGATIVE_PROMPT = (
    "anachronism, wrong era, mixed era, mixed culture, out of period object, "
    "wrong-era clothing, wrong-era hairstyle, wrong-era headwear, wrong-era armor, "
    "wrong-era weapon, wrong-era tool, wrong-era jewelry, fantasy costume, cosplay, "
    "theatrical costume, generic historical costume, modern jewelry, modern accessory, "
    "modern clothing, modern uniform, modern building, skyscraper, concrete city, "
    "car, truck, bus, motorcycle, bicycle, train, railroad, railway, airplane, "
    "helicopter, steamship, steamboat, steam engine, locomotive, factory, factory "
    "chimney, smokestack, industrial machinery, gun, rifle, pistol, cannon unless "
    "period-correct, electric light, power line, utility pole, neon sign, screen, "
    "computer, phone, camera, printed newspaper, modern book, modern national flag, "
    "logo, watermark, readable text"
)

_MODERN_SETTING_RE = re.compile(
    r"\b(modern|office|workplace|desk|laptop|computer|screen|phone|water\s+cooler|"
    r"coffee\s+cup|city|skyscraper|car|truck|bus|motorcycle|bicycle|neon|"
    r"electric|power\s+line|utility\s+pole)\b",
    re.IGNORECASE,
)

_GLOBAL_STYLE_PUBLIC_PATTERNS: tuple[str, ...] = (
    r"\bColoringBookAF\b",
    r"\bColoring Book\b",
    r"\bsubject[- ]faithful\b",
    r"\b2D webtoon cartoon frame\b",
    r"\bstrict 2D webtoon cartoon only\b",
    r"\bflat vector[- ]like colors\b",
    r"\bthick clean black outlines\b",
    r"\bsimple cel shading\b",
    r"\bdrawn illustration only\b",
    r"\bnon[- ]photographic\b",
    r"\billustration not photo\b",
)

_GLOBAL_STYLE_NON_STYLE_PATTERNS: tuple[str, ...] = (
    r"\badult office fable mood\b",
    r"\boffice fable mood\b",
    r"\bmodern office mood\b",
    r"\bmodern office\b",
    r"\bworkplace mood\b",
)


def _clean_prompt_commas(text: str) -> str:
    out = re.sub(r"\s+", " ", text or "").strip()
    out = re.sub(r"\s+,", ",", out)
    out = re.sub(r",\s*,+", ", ", out)
    return out.strip(" ,.;")


def _sanitize_flag_motif_positive_prompt(text: str) -> str:
    """Keep forbidden flag words out of the positive prompt."""
    out = text or ""
    for pattern in _FLAG_MOTIF_POSITIVE_PATTERNS:
        out = re.sub(pattern, "plain unmarked cloth", out, flags=re.IGNORECASE)
    out = re.sub(r"\bplain unmarked cloth(?:\s*,\s*plain unmarked cloth)+\b", "plain unmarked cloth", out, flags=re.IGNORECASE)
    return _clean_prompt_commas(out)


def sanitize_global_style_for_prompt(global_style: str, image_prompt: str = "") -> str:
    """Keep channel style as style only; do not let it inject scene settings."""
    style = global_style or ""
    if not re.search(r"\b(korea|korean|joseon|goryeo|hanbok|seoul)\b", image_prompt or "", re.IGNORECASE):
        style = re.sub(r"\bKorean\s+YouTube\b", "YouTube", style, flags=re.IGNORECASE)
        style = re.sub(r"\bKorean\s+", "", style, flags=re.IGNORECASE)
    for pattern in _GLOBAL_STYLE_PUBLIC_PATTERNS:
        style = re.sub(pattern, "", style, flags=re.IGNORECASE)

    # Global style is shared by every cut. Setting words in it must not turn
    # source-story meadow/winter cuts into office/city scenes.
    if not _MODERN_SETTING_RE.search(image_prompt or ""):
        for pattern in _GLOBAL_STYLE_NON_STYLE_PATTERNS:
            style = re.sub(pattern, "", style, flags=re.IGNORECASE)

    return _sanitize_flag_motif_positive_prompt(style)

INDIAN_HISTORY_ACCURACY_DIRECTIVE = (
    " For Indian history scenes, use period-correct South Asian visual culture only: "
    "regional clothing, architecture, tools, vehicles, ritual objects, landscapes, "
    "and materials appropriate to the exact era named in the prompt. Never import "
    "Japanese, East Asian, European industrial, or modern nationalist symbols unless "
    "the narration explicitly places the scene there. Forbidden in Indian history: "
    "Japanese flag, rising sun flag, red sun disc flag, torii gate, Shinto shrine, "
    "samurai, ninja, katana, kimono, Japanese castle, Japanese text, steamship, "
    "steamboat, locomotive, train, factory chimney, modern flags, cars, power lines, "
    "neon signs, screens, logos."
)

INDIAN_HISTORY_NEGATIVE_PROMPT = (
    "Japanese flag, rising sun flag, red sun disc flag, hinomaru, torii gate, "
    "Shinto shrine, samurai, ninja, katana, kimono, Japanese castle, Japanese text, "
    "East Asian temple, pagoda unless historically specified, steamship, steamboat, "
    "steam engine, locomotive, train, railroad, railway, factory chimney, smokestack, "
    "industrial machinery, British colonial uniform unless narration says colonial "
    "period, modern Indian flag unless modern period, modern flag, modern building, "
    "car, truck, power line, neon sign, logo"
)

GENERAL_HISTORY_ACCURACY_DIRECTIVE = (
    " || HARD HISTORICAL MATERIAL CULTURE LOCK - match the exact time period, "
    "This fixed lock has higher priority than any user-entered image prompt or style prompt. "
    "season, time of day, region, place type, interior/exterior setting, and social "
    "setting stated in the prompt. The specified time period, region, and place are "
    "non-negotiable and must be considered before choosing any costume, prop, "
    "architecture, or vehicle. All visible material culture must be period-correct: "
    "clothing, hairstyle, headwear, armor, jewelry and accessories, tools, weapons, "
    "vehicles, vessels, furniture, architecture, ritual objects, everyday objects, "
    "landscape, and materials. The image must depict the concrete setting and action "
    "from the narration, not a generic metaphor. If the prompt is modern, keep it "
    "modern. If it is a fable or historical source scene, keep that source world "
    "consistent. Visible costume, hair, armor, tools, and props must prove the "
    "era; do not use generic historical costume, fantasy costume, cosplay, or "
    "famous wrong-era items. If the exact detail is uncertain, choose conservative "
    "plain period-plausible elements and avoid recognizable later inventions. "
    "Avoid anachronisms and mixed settings: no wrong-era clothing, hairstyles, "
    "headwear, armor, weapons, tools, buildings, vehicles, screens, electric poles, "
    "flags, logos, or culturally unrelated architecture unless the prompt explicitly "
    "names them."
)

_KOREAN_HISTORY_RE = re.compile(
    r"(고구려|goguryeo|koguryo|백제|baekje|paekche|신라|silla|가야|gaya|"
    r"발해|balhae|고조선|gojoseon|부여|buyeo|삼국시대|three kingdoms|"
    r"ancient korea|korean kingdom|korean kingdoms|"
    r"고려|goryeo|koryo|조선|joseon|choson|백제의|신라의|고구려의)",
    re.IGNORECASE,
)

_INDIAN_HISTORY_RE = re.compile(
    r"(india|indian|bharat|harappa|harappan|mohenjo|daro|indus|vedic|veda|aryan|"
    r"sanskrit|mauryan|maurya|gupta|magadha|ashoka|chandragupta|sindhu|"
    r"hindustan|ancient india|indian civilization|indian civilisation|"
    r"भार[ततीय]|हड़प्पा|सिंधु|मोहनजोदड़ो|वैदिक|मौर्य|गुप्त)",
    re.IGNORECASE,
)

_EXPLICIT_JAPAN_RE = re.compile(
    r"(japan|japanese|일본|왜국|yamato|일장기|hinomaru|samurai|shinto|torii)",
    re.IGNORECASE,
)

_ONE_MINUTE_YEOKGONG_RE = re.compile(
    r"(1\s*분\s*역공|일\s*분\s*역공|one\s*minute\s*yeokgong|one\s*minute\s*counter)",
    re.IGNORECASE,
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
    r"\b(holding|gripping|grabbing|pointing|reaching|pressing|pressed|placing|sprinkling)\b",
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
_BOOK_OBJECT_RE = re.compile(
    r"\b(book|books|notebook|manuscript|codex|ledger|journal|diary|scripture|"
    r"archive\s+volume|page\s+spread|open\s+pages|document|scroll|library|"
    r"bookshelf)\b|"
    r"(책|서책|고서|고문서|문서|필사본|원고|두루마리|서재|책장|책상 위의 책)",
    re.IGNORECASE,
)

_HAND_RISK_IMAGE_PATTERNS = [
    (
        r"\bclose-up\s+of\s+[^,.;]*\bhands?\s+pressed\s+(?:gently\s+)?together\s+in\s+a\s+prayer\s+gesture\b",
        "medium shot of a respectful seated figure bowing at the dining table",
    ),
    (
        r"\b(?:both\s+)?hands?\s+pressed\s+(?:gently\s+)?together\s+in\s+a\s+prayer\s+gesture\b",
        "respectful upper-body bowing posture",
    ),
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
    (
        r"\b(?:both\s+)?hands?\s+pressed\s+(?:gently\s+)?together\b",
        "respectful upper-body bowing posture",
    ),
    (
        r"\bpressed\s+(?:gently\s+)?together\s+in\s+a\s+prayer\s+gesture\b",
        "shown with a respectful upper-body bowing posture",
    ),
    (
        r"\bprayer\s+gesture\b",
        "respectful upper-body bowing posture",
    ),
    (
        r"\bholding\s+chopsticks\b",
        "chopsticks resting beside the bowl",
    ),
    (
        r"\bholding\s+green\s+onions\b",
        "green onions arranged on the food",
    ),
    (
        r"\bplacing\s+green\s+onions\b",
        "green onions arranged on the food",
    ),
    (
        r"\bsprinkling\s+green\s+onions\b",
        "green onions scattered on the food",
    ),
    (
        r"\bholding\s+(?:a\s+)?(?:bowl|plate|cup|dish)\b",
        "bowl or dish resting on a visible table in front of the person",
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
    (r"\bclose-up\s+hands?\b", "close-up of the main object"),
    (r"\bclose-up\s+of\s+(?:wrinkled|old|elderly|human)\s+hands?\b", "close-up of the main object"),
    (r"\b(?:wrinkled|old|elderly|human|visible|detailed|foreground)\s+hands?\b", "sleeve-covered arm gesture"),
    (r"\bhands?\b", "sleeve-covered arm gesture"),
    (r"\bpalms?\b", "sleeve-covered arm gesture"),
    (r"\bknuckles?\b", "sleeve-covered arm gesture"),
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

_PHYSICS_RISK_IMAGE_PATTERNS = [
    (
        r"\b(?:person|people|man|woman|child|figure|character|soldier|worker|farmer|monk|noble|samurai)\s+standing\s+on\s+(?:the\s+)?water\b",
        "person standing on a visible wooden dock beside the water",
    ),
    (
        r"\b(?:person|people|man|woman|child|figure|character|soldier|worker|farmer|monk|noble|samurai)\s+walking\s+on\s+(?:the\s+)?water\b",
        "person walking along the shoreline beside the water",
    ),
    (
        r"\b(?:standing|walking)\s+on\s+(?:the\s+)?water\b",
        "standing on visible solid ground beside the water",
    ),
    (
        r"\bon\s+the\s+surface\s+of\s+(?:the\s+)?water\b",
        "on a visible wooden dock beside the water",
    ),
    (
        r"\bmiddle\s+of\s+(?:a\s+)?river\b",
        "riverbank beside the river",
    ),
    (
        r"\bmiddle\s+of\s+(?:a\s+)?lake\b",
        "shoreline beside the lake",
    ),
    (
        r"\b(?:person|people|man|woman|child|figure|character)\s+in\s+(?:a\s+)?boat\b",
        "person seated inside a boat with the boat hull clearly visible",
    ),
    (
        r"\b(?:floating|hovering)\s+(?:bowl|plate|cup|book|scroll|box|object|tool|weapon|sword|lantern|document)s?\b",
        "object resting firmly on a visible table or ground surface",
    ),
    (
        r"\b(?:bowl|plate|cup|book|scroll|box|object|tool|weapon|sword|lantern|document)s?\s+(?:floating|hovering)\b",
        "object resting firmly on a visible table or ground surface",
    ),
    (
        r"\bfood\s+floating\b",
        "food placed clearly on a plate or inside a bowl",
    ),
    (
        r"\bobjects?\s+floating\s+in\s+the\s+air\b",
        "objects resting on visible shelves, tables, or ground surfaces",
    ),
    (
        r"\bin\s+midair\b",
        "resting on a visible physical support",
    ),
    (
        r"\bfull\s+meal\s+of\s+rice,\s*miso\s+soup,\s*grilled\s+fish,\s*and\s*pickles\b",
        "full meal with separate visible dishes: rice bowl, miso soup bowl, grilled fish plate, and pickle dish",
    ),
    (
        r"\brice,\s*miso\s+soup,\s*grilled\s+fish,\s*and\s*pickles\b",
        "separate visible dishes of rice, miso soup, grilled fish, and pickles",
    ),
    (
        r"\bmultiple\s+people\s+overlapping\b",
        "two separated people with clear space between their silhouettes",
    ),
    (
        r"\boverlapping\s+people\b",
        "separated people with clear space between their silhouettes",
    ),
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
        "simple sleeve-covered arm gesture",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"(?:four simple rounded|exactly four short rounded cartoon) (?:simple rounded shapes|four simple rounded fingers|exactly four short rounded cartoon fingers)",
        "simple sleeve-covered arm gesture",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"(?:tiny\s+)?four-lobed\s+mitten\s+hands(?:,\s*(?:tiny\s+)?four-lobed\s+mitten\s+hands)+",
        "simple sleeve-covered arm gesture",
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


def _sanitize_physics_risky_prompt(text: str) -> str:
    """Keep SDXL scenes physically grounded without adding negative prompt tokens."""
    out = text or ""
    for pattern, replacement in _PHYSICS_RISK_IMAGE_PATTERNS:
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    out = re.sub(r"\bin\s+the\s+riverbank\b", "on the riverbank", out, flags=re.IGNORECASE)
    out = re.sub(r"\bin\s+the\s+shoreline\b", "on the shoreline", out, flags=re.IGNORECASE)
    out = re.sub(r"\bin\s+the\s+air\b", "on a visible table or ground surface", out, flags=re.IGNORECASE)
    out = re.sub(r"\bstanding\s+apart\s+people\b", "people standing apart", out, flags=re.IGNORECASE)
    out = re.sub(r"\bseparated\s+people\s+with\s+clear\s+space\s+between\s+their\s+silhouettes\s+people\b", "separated people with clear space between their silhouettes", out, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", out).strip()


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
    p = _sanitize_flag_motif_positive_prompt(prompt or "")
    if not p:
        return p
    if "NO TEXT, NO LETTERS" in p or "readable glyph-free image" in p:
        return p
    return p + NO_TEXT_DIRECTIVE


def _append_no_maps(prompt: str) -> str:
    p = (prompt or "").strip()
    if not p:
        return p
    if "ABSOLUTELY NO MAPS" in p or "NO CARTOGRAPHY" in p:
        return p
    return p + NO_MAP_DIRECTIVE


def needs_book_render_guard(prompt: str) -> bool:
    return bool(_BOOK_OBJECT_RE.search(prompt or ""))


def _append_book_render_guard(prompt: str) -> str:
    p = (prompt or "").strip()
    if not p or not needs_book_render_guard(p):
        return p
    if "BOOK RENDERING LOCK" in p:
        return p
    return p + BOOK_RENDER_DIRECTIVE


def _apply_common_image_constraints(prompt: str, enable_historical_guard: bool = False) -> str:
    p = _sanitize_flag_motif_positive_prompt(prompt)
    p = apply_historical_accuracy_guard(p, enable_historical_guard)
    p = _append_book_render_guard(p)
    p = _append_no_text(p)
    p = _append_no_maps(p)
    return p


def needs_korean_history_guard(prompt: str) -> bool:
    return bool(_KOREAN_HISTORY_RE.search(prompt or ""))


def apply_historical_accuracy_guard(prompt: str, enabled: bool = False) -> str:
    p = (prompt or "").strip()
    if not enabled:
        return p
    if not p or "HISTORICAL ACCURACY LOCK" in p:
        return p
    if not needs_korean_history_guard(p):
        guard = GENERAL_HISTORY_ACCURACY_DIRECTIVE
        if _INDIAN_HISTORY_RE.search(p):
            guard += INDIAN_HISTORY_ACCURACY_DIRECTIVE
        return p + guard

    guard = KOREAN_HISTORY_ACCURACY_DIRECTIVE
    if _EXPLICIT_JAPAN_RE.search(p):
        guard = guard.replace(
            "Forbidden unless the prompt explicitly says the scene is in Japan: ",
            "Because the subject includes Japan/Yamato, include only the historically correct "
            "Japan/Yamato material culture for the exact era: period-correct clothing, "
            "hairstyle, headwear, armor, tools, weapons, vessels, architecture, ritual "
            "objects, everyday objects, and materials. Do not mix samurai, kimono, torii, "
            "katana, ninja, or castle imagery unless that exact era and narration justify "
            "them. Still avoid modern Japanese symbols: ",
        )
    return p + guard


def historical_negative_prompt(prompt: str, enabled: bool = False) -> str:
    if not enabled:
        return ""
    p = prompt or ""
    parts = [NO_TEXT_NEGATIVE_PROMPT, NO_MAP_NEGATIVE_PROMPT]
    if not _MODERN_SETTING_RE.search(p):
        parts.insert(0, GENERAL_HISTORY_NEGATIVE_PROMPT)
    if needs_book_render_guard(p):
        parts.append(BOOK_RENDER_NEGATIVE_PROMPT)
    if needs_korean_history_guard(p):
        parts.append(KOREAN_HISTORY_NEGATIVE_PROMPT)
    if _INDIAN_HISTORY_RE.search(p):
        parts.append(INDIAN_HISTORY_NEGATIVE_PROMPT)
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        for token in [x.strip() for x in part.split(",") if x.strip()]:
            key = token.lower()
            if key not in seen:
                seen.add(key)
                out.append(token)
    return ", ".join(out)


def map_negative_prompt() -> str:
    """Negative prompt tokens that block generated maps in every channel."""
    return NO_MAP_NEGATIVE_PROMPT


def text_negative_prompt() -> str:
    """Negative prompt tokens that block generated text in every channel."""
    return NO_TEXT_NEGATIVE_PROMPT


def book_negative_prompt(prompt: str) -> str:
    """Prompt-specific negative tokens for coherent blank books/documents."""
    return BOOK_RENDER_NEGATIVE_PROMPT if needs_book_render_guard(prompt or "") else ""


def append_prompt_specific_negative_prompt(base_negative: str, prompt: str) -> str:
    current = (base_negative or "").strip()
    extras = [book_negative_prompt(prompt)]
    for extra in extras:
        if extra and extra not in current:
            current = f"{extra}, {current}".strip(" ,")
    return current


def symbol_negative_prompt() -> str:
    """Negative prompt tokens for symbol generation."""
    return ""


def should_enable_historical_guard_for_context(
    config: dict | None = None,
    *values,
) -> bool:
    cfg = config or {}
    explicit = cfg.get("historical_accuracy_guard")
    if explicit is True or str(explicit).strip().lower() in {"1", "true", "yes", "on"}:
        return True
    if explicit is False or str(explicit).strip().lower() in {"0", "false", "no", "off"}:
        return False

    haystack: list[str] = []
    for key in (
        "preset_name",
        "preset_full_name",
        "channel_name",
        "youtube_channel_name",
        "series_name",
        "project_name",
        "form_name",
        "name",
        "full_name",
    ):
        value = cfg.get(key)
        if value is not None:
            haystack.append(str(value))
    haystack.extend(str(v) for v in values if v is not None)
    joined = " ".join(haystack)
    if _ONE_MINUTE_YEOKGONG_RE.search(joined):
        return True
    if str(cfg.get("language") or "").strip().lower() == "hi":
        return True
    return bool(
        re.search(
            r"(history|historical|ancient|civilization|civilisation|empire|kingdom|"
            r"india|indian|bharat|harappa|harappan|mohenjo|indus|vedic|veda|aryan|"
            r"sanskrit|mauryan|gupta|temple|fort|palace|dynasty)",
            joined,
            re.IGNORECASE,
        )
    )


def apply_reference_style_prefix(
    prompt: str,
    has_reference: bool,
    *,
    enable_historical_guard: bool = False,
) -> str:
    """썸네일/재생성 등 외부 경로용 프리픽스 적용 헬퍼.

    이미 프리픽스가 붙어 있으면 중복 부착을 피한다. has_reference=False 이면
    스타일 프리픽스는 생략하되 **문자 금지 지시는 항상** 뒤에 붙인다
    (v1.1.72). 레퍼런스 유무와 무관하게 이미지에 텍스트가 끼어드는 걸 차단.
    """
    p = (prompt or "").strip()
    if has_reference:
        if "STYLE REFERENCE LOCK" not in p and not p.startswith("STYLE:"):
            p = REFERENCE_STYLE_PREFIX + p
    return _apply_common_image_constraints(p, enable_historical_guard)


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
    enable_historical_guard: bool = False,
) -> str:
    """최종 이미지 프롬프트 조합.

    v1.1.58: 레퍼런스 이미지가 있으면 스타일은 전적으로 레퍼런스에 위임.
    프롬프트에는 피사체/구도/동작만 남기고, global_style 등 스타일 텍스트는 주입하지 않는다.
    레퍼런스가 없을 때만 global_style 을 폴백으로 사용.
    """
    base = _sanitize_flag_motif_positive_prompt(image_prompt or "")
    base, _ = _sanitize_hand_risky_prompt(base)
    base, _ = _sanitize_anatomy_risky_prompt(base)
    base = _sanitize_physics_risky_prompt(base)
    style_hint = sanitize_global_style_for_prompt(global_style, base)

    if has_reference:
        # ── 레퍼런스 있음 ──
        # v1.1.61: global_style 도 항상 포함. 이유: 로컬 ComfyUI 모델 중 일부는
        # IPAdapter 가 안 깔려있어서 레퍼런스 픽셀이 모델에 안 들어갈 수 있다.
        # 그 경우 스타일 정보가 텍스트 프리픽스뿐인데 그게 "스타일 복사하라" 는
        # 메타 지시라 실제 스타일 단어(예: "cartoon illustration")가 전혀 없다.
        # 결과가 기본값(실사)로 돌아가는 원인. global_style 을 항상 끼워넣어 안전.
        parts: list[str] = [REFERENCE_STYLE_PREFIX]

        if style_hint:
            parts.append(
                f"Style/tone only, do not change the subject, action, setting, period, or props: {style_hint}."
            )

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
        return _apply_common_image_constraints(" ".join(parts).strip(), enable_historical_guard)

    else:
        # ── 레퍼런스 없음: global_style 폴백 ──
        parts = []
        if base:
            parts.append(base)
        if style_hint:
            parts.append(
                f"Style/tone only, do not change the subject, action, setting, period, or props: {style_hint}."
            )

        if has_character_slot:
            char_desc = character_description.strip()
            if char_desc:
                parts.append(
                    f"This cut features the main character: {char_desc}. "
                    "Place the character clearly in frame, pose matching the scene."
                )

        # v1.1.72: 레퍼런스 없는 경로에도 동일하게 "문자 금지" 지시 강제
        return _apply_common_image_constraints(" ".join(parts).strip(), enable_historical_guard)
