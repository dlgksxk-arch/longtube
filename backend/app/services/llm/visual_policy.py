"""Visual prompt policy for script-generated cuts.

The script step owns the scene idea. This module keeps that idea, but forces the
image/video prompts into the simple local-generation grammar we can reliably use.
"""
from __future__ import annotations

import re
from typing import Any


IMAGE_PROMPT_REQUIRED_STYLE = "simple cartoon illustration, documentary cartoon style, clean thick outlines, soft natural shadows"


_PERSON_COUNT_RE = re.compile(
    r"\b(?:a\s+)?(?:single|one|two)\s+(?:simplified\s+)?(?:faceless\s+)?"
    r"(?:round[- ]head|rounded[- ]head)\s+"
    r"(?:characters?|figures?|students?|workers?|researchers?|scientists?|teachers?|observers?)\b",
    re.IGNORECASE,
)

_SCENE_OBJECT_HINTS = (
    "machine",
    "device",
    "robot",
    "computer",
    "server",
    "book",
    "paper",
    "map",
    "chart",
    "tool",
    "lamp",
    "wheel",
    "door",
    "box",
    "crate",
    "barrel",
    "stone",
    "artifact",
    "symbol",
    "screen",
    "board",
    "orb",
    "table",
)

_PROMPT_REWRITES: tuple[tuple[str, str], ...] = (
    (r"\b(?:a\s+)?classroom\s+full\s+of\s+(?:students|people|children|workers|researchers|scientists)\b", "single faceless round-head character beside an unmarked board"),
    (r"\b(?:a\s+)?(?:meeting\s+room|room)\s+full\s+of\s+(?:people|characters|workers|researchers|scientists)\b", "single faceless round-head character beside one story object"),
    (r"\bhuman\s+hand\s+and\s+robotic\s+hand\b", "single faceless round-head character beside a glowing orb and small robot device"),
    (r"\btwo\s+hands\s+touching\b", "single faceless round-head character beside a glowing orb"),
    (r"\bglow\s+between\s+(?:fingertips|fingers|hands)\b", "glowing orb near the character"),
    (r"\b(?:a\s+)?crowd\s+of\s+people\b", "single faceless round-head character"),
    (r"\bcrowded\s+(?:scene|room|classroom|meeting)\b", "single faceless round-head character with one story object"),
    (r"\bclassroom\s+full\s+of\s+people\b", "single faceless round-head character beside an unmarked board"),
    (r"\bmeeting\s+room\s+full\s+of\s+people\b", "single faceless round-head character beside one unmarked table object"),
    (r"\broom\s+full\s+of\s+people\b", "single faceless round-head character beside one story object"),
    (r"\b(?:large\s+)?audience\b", "single faceless round-head character"),
    (r"\bmany\s+people\b", "single faceless round-head character"),
    (r"\bseveral\s+people\b", "single faceless round-head character"),
    (r"\bmultiple\s+people\b", "single faceless round-head character"),
    (r"\bgroup\s+of\s+(?:people|characters|students|workers|researchers|scientists)\b", "single faceless round-head character"),
    (r"\b(?:two|three|four|five|six|seven|eight|nine|ten)\s+(?:people|characters|students|workers|researchers|scientists)\b", "single faceless round-head character"),
    (r"\b(?:dozens|hundreds|thousands)\s+of\s+(?:people|characters|students|workers|researchers|scientists)\b", "single faceless round-head character"),
    (r"\bworkers\b", "single faceless round-head worker"),
    (r"\bresearchers\b", "single faceless round-head researcher"),
    (r"\bscientists\b", "single faceless round-head scientist"),
    (r"\bstudents\b", "single faceless round-head student"),
    (r"\bsoldiers\b", "single faceless round-head figure"),
    (r"\b(?:old|young|middle-aged|bearded|handsome|beautiful)(?:\s+(?:old|young|middle-aged|bearded|handsome|beautiful))*\s+(?:man|woman|person)\b", "single faceless round-head character"),
    (r"\b(?:a|one)\s+(?:person|human|man|woman|figure)\b", "single faceless round-head character"),
    (r"\b(?:man|woman|person|human|figure|character)\s+with\s+(?:a\s+)?(?:detailed\s+)?face\b", "faceless round-head character"),
    (r"\bdetailed\s+face\b", "blank round head"),
    (r"\brealistic\s+face\b", "blank round head"),
    (r"\bexpressive\s+face\b", "blank round head"),
    (r"\beyes?\b", "blank head surface"),
    (r"\bnose\b", "blank head surface"),
    (r"\bmouth\b", "blank head surface"),
    (r"\bsmil(?:e|ing)\b", "neutral blank head"),
    (r"\bfrown(?:ing)?\b", "neutral blank head"),
    (r"\bfingertips?\b", "small arm gesture"),
    (r"\bfingers?\b", "small arm gesture"),
    (r"\btoes?\b", "simple feet"),
    (r"\b(?:in|inside)\s+(?:a\s+)?(?:classroom|meeting room|office|laboratory|library|city|street|landscape|forest)\b", "on a plain white background"),
    (r"\b(?:classroom|meeting room|office|laboratory|library|city skyline|landscape|forest|street)\s+background\b", "plain white background"),
    (r"\bbackground\s+(?:crowd|people|characters)\b", "plain white background"),
)

_LEGACY_POLICY_MARKERS = (
    "only the simplified character(s)",
    "story-relevant object(s)",
    "no room",
    "no scenery",
    "no crowd",
    "no character lineup",
    "no character sheet",
    "blank round head with no",
    "mitten-like hands with no",
    "one or two characters only",
    "centered simple composition",
    "empty white space",
    "blank round head",
    "exactly four short rounded cartoon fingers per hand",
    "four simple rounded fingers per hand",
)

_BANNED_BACKGROUND_RE = re.compile(
    r"\b(?:room|classroom|meeting room|office|laboratory|library|city|street|landscape|forest|window|wall|floor|ceiling|skyline)\b",
    re.IGNORECASE,
)
_CLASSICAL_JAPAN_TOPIC_RE = re.compile(
    r"(万葉|古事記|日本書紀|奈良|飛鳥|平安|鎌倉|室町|戦国|江戸|"
    r"古代|中世|ヤマト|大和|倭|古墳|和歌|東歌|防人|藤原|源氏|平家|幕府|国学)"
)
_MODERN_JAPAN_VISUAL_RE = re.compile(
    r"\b(?:20\d{2}|2020s|contemporary|present[- ]day|modern|current|today|"
    r"university|researcher|modern scholar|facsimile|classroom|public archive|"
    r"modern archive|modern library|modern museum|tokyo classroom)\b",
    re.IGNORECASE,
)


def _clean_spaces(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(
        r"(?:exactly four short rounded cartoon\s+){2,}fingers",
        "tiny four-lobed mitten hands",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"(?:tiny\s+)?four-lobed\s+mitten\s+hands(?:\s+per\s+hand)?(?:,\s*(?:tiny\s+)?four-lobed\s+mitten\s+hands(?:\s+per\s+hand)?)+",
        "tiny four-lobed mitten hands",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r",\s*,+", ", ", text)
    return text.strip(" ,")


def _looks_like_classical_japanese_history(script: dict[str, Any]) -> bool:
    context = " ".join(str(script.get(key) or "") for key in ("title", "topic", "description"))
    return bool(_CLASSICAL_JAPAN_TOPIC_RE.search(context))


def _is_modern_japan_visual(cut: dict[str, Any]) -> bool:
    fields = " ".join(
        str(cut.get(key) or "")
        for key in (
            "visual_year",
            "visual_period",
            "visual_location",
            "visual_evidence",
            "visual_subject",
            "visual_scene",
            "image_prompt",
        )
    )
    return bool(_MODERN_JAPAN_VISUAL_RE.search(fields))


def _historical_japan_replacement(narration: str) -> dict[str, str]:
    text = str(narration or "")
    if any(term in text for term in ("江戸", "国学")):
        return {
            "visual_year": "c. 1700-1800",
            "visual_period": "Edo period kokugaku manuscript study",
            "visual_location": "quiet Edo-period scholar room with blank manuscript copies",
            "visual_evidence": "The narration discusses later interpretation, so an Edo-period study scene fits without using a present-day archive.",
            "visual_subject": "Edo-period scholar comparing blank manuscript copies",
            "visual_scene": "A robed scholar leans over blank manuscript copies beside an inkstone and low wooden desk",
        }
    if any(term in text for term in ("近代", "文学")):
        return {
            "visual_year": "c. 1900-1930",
            "visual_period": "early twentieth-century Japanese literary study",
            "visual_location": "plain study room with blank manuscript reproductions",
            "visual_evidence": "The narration mentions modern literary value, so an early scholarly setting is enough without repeating present-day archives.",
            "visual_subject": "early twentieth-century literary scholar studying blank manuscript copies",
            "visual_scene": "A scholar in plain period clothing compares blank manuscript copies at a simple wooden desk",
        }
    if any(term in text for term in ("鎌倉", "写本", "注釈", "写し")):
        return {
            "visual_year": "c. 1200-1300",
            "visual_period": "Kamakura period manuscript transmission",
            "visual_location": "monastic manuscript copying room in medieval Japan",
            "visual_evidence": "The narration concerns copied manuscripts, so a medieval transmission scene matches the historical process.",
            "visual_subject": "medieval scribe handling a blank copied scroll",
            "visual_scene": "A scribe carefully compares blank scrolls on a low desk under quiet lamplight",
        }
    if any(term in text for term in ("平安", "古今", "和歌")):
        return {
            "visual_year": "c. 905-950",
            "visual_period": "Heian period court poetry culture",
            "visual_location": "Heian court writing room with blank poetry scrolls",
            "visual_evidence": "The narration concerns waka reception, so a Heian poetry scene is closer than a present-day archive.",
            "visual_subject": "Heian court poet reviewing blank scrolls",
            "visual_scene": "A court poet studies blank scrolls near a low desk, sleeves resting beside an inkstone",
        }
    return {
        "visual_year": "c. 759",
        "visual_period": "Nara period manuscript compilation and preservation",
        "visual_location": "Heijo-kyo record room with blank scroll bundles",
        "visual_evidence": "The narration concerns ancient voices and surviving records, so a Nara manuscript scene fits the source world.",
        "visual_subject": "Nara-period scribe guarding blank scroll bundles",
        "visual_scene": "A court scribe steadies blank scroll bundles inside a wooden record room under soft lamplight",
    }


def limit_modern_japanese_history_visuals(script: dict[str, Any]) -> dict[str, Any]:
    """Cap present-day archive/researcher scenes in classical Japanese history scripts."""
    if not isinstance(script, dict) or not _looks_like_classical_japanese_history(script):
        return script
    cuts = script.get("cuts")
    if not isinstance(cuts, list):
        return script
    modern_cuts = [cut for cut in cuts if isinstance(cut, dict) and _is_modern_japan_visual(cut)]
    if not modern_cuts:
        return script
    cap = 5 if len(cuts) >= 100 else max(1, min(3, len(cuts) // 30 or 1))
    for cut in modern_cuts[cap:]:
        replacement = _historical_japan_replacement(str(cut.get("narration") or ""))
        cut.update(replacement)
        cut["image_prompt"] = ""
    return script


_SOFT_IDENTITY_REWRITES: tuple[tuple[str, str], ...] = (
    (r"\bant[-\s]*like\s+(?:office\s+)?(?:worker|person|character|figure)\b", "anthropomorphic ant character"),
    (r"\b(?:office\s+)?(?:worker|person|character|figure)\s+that\s+looks\s+like\s+an\s+ant\b", "anthropomorphic ant character"),
    (r"\b(?:office\s+)?(?:worker|person|character|figure)\s+like\s+an\s+ant\b", "anthropomorphic ant character"),
    (r"\bgrasshopper[-\s]*like\s+(?:office\s+)?(?:worker|person|character|figure)\b", "anthropomorphic grasshopper character"),
    (r"\b(?:office\s+)?(?:worker|person|character|figure)\s+that\s+looks\s+like\s+a\s+grasshopper\b", "anthropomorphic grasshopper character"),
    (r"\b(?:office\s+)?(?:worker|person|character|figure)\s+like\s+a\s+grasshopper\b", "anthropomorphic grasshopper character"),
    (r"\b(?:bug|insect)[-\s]*like\s+(?:office\s+)?(?:worker|person|character|figure)\b", "simple cartoon character"),
    (r"\b(?:inspired\s+by|similar\s+to)\s+an\s+ant\b", "anthropomorphic ant character"),
    (r"\b(?:inspired\s+by|similar\s+to)\s+a\s+grasshopper\b", "anthropomorphic grasshopper character"),
    (r"개미\s*같은\s*(?:사무실\s*)?(?:노동자|인물|캐릭터|사람)", "의인화된 개미 캐릭터"),
    (r"(?:사무실\s*)?(?:노동자|인물|캐릭터|사람)\s*같은\s*개미", "의인화된 개미 캐릭터"),
    (r"메뚜기\s*같은\s*(?:사무실\s*)?(?:노동자|인물|캐릭터|사람)", "의인화된 메뚜기 캐릭터"),
    (r"(?:사무실\s*)?(?:노동자|인물|캐릭터|사람)\s*같은\s*메뚜기", "의인화된 메뚜기 캐릭터"),
    (r"(?:곤충|벌레)\s*같은\s*(?:사무실\s*)?(?:노동자|인물|캐릭터|사람)", "간단한 2D 카툰 캐릭터"),
)


def sanitize_softened_identity_phrases(text: str) -> str:
    out = text or ""
    for pattern, replacement in _SOFT_IDENTITY_REWRITES:
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    out = re.sub(r"\bant[-\s]*like\b", "anthropomorphic ant", out, flags=re.IGNORECASE)
    out = re.sub(r"\bgrasshopper[-\s]*like\b", "anthropomorphic grasshopper", out, flags=re.IGNORECASE)
    out = re.sub(r"\bbug[-\s]*like\b|\binsect[-\s]*like\b", "simple cartoon", out, flags=re.IGNORECASE)
    out = re.sub(r"개미\s*같은|개미같은", "의인화된 개미", out)
    out = re.sub(r"메뚜기\s*같은|메뚜기같은", "의인화된 메뚜기", out)
    out = re.sub(r"곤충\s*같은|곤충같은|벌레\s*같은|벌레같은", "간단한 2D 카툰", out)
    return _clean_spaces(out)


_REPETITIVE_STYLE_PHRASES: tuple[str, ...] = (
    r"\b(?:simple\s+)?2D\s+cartoon\s+scene\b",
    r"\bflat\s+2D\s+cartoon\s+style\b",
    r"\bflat\s+cartoon\s+style\b",
    r"\bflat\s+colors?\b",
    r"\bthick\s+outlines?\b",
    r"\bclean\s+minimal\s+scene\b",
    r"\bminimal\s+scene\b",
    r"\bminimal\s+flat\s+background\b",
    r"\bpale\s+(?:blue|gray|grey)\s+background\b",
    r"\blight\s+(?:gray|grey)\s+background\b",
    r"\bsoft\s+neutral\s+lighting\b",
    r"\bneutral\s+cool\s+daylight\b",
    r"\billustration\s+not\s+photo\b",
)


def strip_repetitive_style_fillers(text: str) -> str:
    out = text or ""
    for pattern in _REPETITIVE_STYLE_PHRASES:
        out = re.sub(pattern, "", out, flags=re.IGNORECASE)
    return _clean_spaces(out)


_ANT_GRASSHOPPER_CONTEXT_RE = re.compile(
    r"\b(ant|grasshopper|anthill)\b",
    re.IGNORECASE,
)

_NARRATION_LEAK_LABEL_RE = re.compile(
    r"(?:^|[;,.]\s*)"
    r"(?:spoken\s+cue|narration\s+cue|narration|dialogue|voiceover|transcript|quote|line)"
    r"\s*:\s*[^;]+;?",
    re.IGNORECASE,
)

_ANT_WORK_NARRATION_RE = re.compile(
    r"\b(quietly|effort|work(?:er|ing|ed)?|prepar(?:e|es|ed|ing|ation)|"
    r"noticed|unseen|steady|satisfaction|stores?|saving|saved|grain|seed)\b",
    re.IGNORECASE,
)

_GRASSHOPPER_NARRATION_RE = re.compile(
    r"\b(grasshopper|sing(?:s|ing)?|rest(?:s|ed|ing)?|relax(?:es|ed|ing)?|"
    r"idle|carefree|hungry|regret(?:s|ting)?|shiver(?:s|ing)?|winter)\b",
    re.IGNORECASE,
)

_IDLE_WORK_MISMATCH_REWRITES: tuple[tuple[str, str], ...] = (
    (r"\bsitting idly at (?:a )?desk\b", "working quietly at a desk with organized folders"),
    (r"\bsitting idly\b", "working quietly"),
    (r"\blounging\b", "working quietly"),
    (r"\bresting\b", "working quietly"),
    (r"\brelaxing\b", "working quietly"),
)


def repair_ant_grasshopper_alignment(prompt: str, narration: str = "", script_context: str = "") -> str:
    """Prevent obvious ant/grasshopper role swaps in fable scripts."""
    out = prompt or ""
    combined = " ".join([narration or "", prompt or "", script_context or ""])
    if not _ANT_GRASSHOPPER_CONTEXT_RE.search(combined):
        return out

    prompt_l = out.lower()
    narration_l = (narration or "").lower()
    has_ant = bool(re.search(r"\bant\b|\banthill\b", prompt_l))
    has_grasshopper = bool(re.search(r"\bgrasshopper\b", prompt_l))
    effort_cut = bool(_ANT_WORK_NARRATION_RE.search(narration_l)) and not bool(
        re.search(r"\b(grasshopper|sing|rest|relax|idle|carefree|hungry|regret|shiver|winter)\b", narration_l)
    )
    if effort_cut and has_grasshopper and not has_ant:
        out = re.sub(
            r"\banthropomorphic grasshopper character\b",
            "anthropomorphic ant character",
            out,
            count=1,
            flags=re.IGNORECASE,
        )
        out = re.sub(r"\bgrasshopper character\b", "ant character", out, count=1, flags=re.IGNORECASE)
        for pattern, replacement in _IDLE_WORK_MISMATCH_REWRITES:
            out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
        if re.search(r"\bdesk\b", out, flags=re.IGNORECASE) and not re.search(r"\bfolders?\b|\bnotebooks?\b", out, flags=re.IGNORECASE):
            out = _clean_spaces(out + ", organized folders and notebook visible")

    grasshopper_cut = bool(_GRASSHOPPER_NARRATION_RE.search(narration_l))
    prompt_l = out.lower()
    has_ant = bool(re.search(r"\bant\b|\banthill\b", prompt_l))
    has_grasshopper = bool(re.search(r"\bgrasshopper\b", prompt_l))
    if grasshopper_cut and has_ant and not has_grasshopper:
        out = re.sub(
            r"\banthropomorphic ant character\b",
            "anthropomorphic grasshopper character",
            out,
            count=1,
            flags=re.IGNORECASE,
        )
        out = re.sub(r"\bant character\b", "grasshopper character", out, count=1, flags=re.IGNORECASE)

    return _clean_spaces(out)


def _strip_legacy_policy_text(text: str) -> str:
    out = text or ""
    lower = out.lower()
    cut_at = len(out)
    for marker in _LEGACY_POLICY_MARKERS:
        idx = lower.find(marker)
        if idx >= 0:
            cut_at = min(cut_at, idx)
    if cut_at < len(out):
        out = out[:cut_at]
    out = re.sub(r"\bonly\s+the\s+character\s+and\s+the\s+[^,.;]+", "", out, flags=re.IGNORECASE)
    out = re.sub(r"\bonly\s+the\s+character\s+and\s+[^,.;]+", "", out, flags=re.IGNORECASE)
    return _clean_spaces(out)


def normalize_image_prompt(prompt: str) -> str:
    """Keep scene content, remove identity softeners and repeated style filler."""
    return strip_repetitive_style_fillers(sanitize_softened_identity_phrases(prompt))


def strip_narration_leakage(prompt: str, narration: str = "") -> str:
    """Remove narration/script text that leaked into an image prompt."""
    out = prompt or ""
    out = _NARRATION_LEAK_LABEL_RE.sub("; ", out)
    current = (narration or "").strip()
    if current:
        candidates = {current, current.rstrip(".!?。！？")}
        candidates.update(part.strip() for part in re.split(r"[.!?。！？]\s*", current) if part.strip())
        for candidate in sorted(candidates, key=len, reverse=True):
            if len(candidate) >= 6:
                out = re.sub(re.escape(candidate), "", out, flags=re.IGNORECASE)
    out = re.sub(r";\s*;", "; ", out)
    out = re.sub(r":\s*,", ":", out)
    return _clean_spaces(out)


def normalize_cut_image_prompt(prompt: str, narration: str = "", script_context: str = "") -> str:
    """Normalize one cut with narration-aware role alignment."""
    normalized = strip_narration_leakage(normalize_image_prompt(prompt), narration)
    return repair_ant_grasshopper_alignment(normalized, narration, script_context)


def _strip_visual_context_prefix(prompt: str) -> str:
    out = prompt or ""
    out = re.sub(
        r"^\s*Year/period:\s*[^;]+(?:;\s*[^;]+)?;\s*"
        r"(?:Historically accurate period details:\s*[^;]+;\s*)?"
        r"(?:Exact place:\s*[^;]+;\s*)?"
        r"(?:Scene evidence:\s*[^;]+;\s*)?"
        r"(?:Style:\s*[^;]+;\s*)?"
        r"Scene:\s*",
        "",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(r"(?:^|;\s*)Style:\s*[^;]*;?", "; ", out, flags=re.IGNORECASE)
    out = re.sub(
        rf"\b{re.escape(IMAGE_PROMPT_REQUIRED_STYLE)}\b\s*;?",
        "",
        out,
        flags=re.IGNORECASE,
    )
    out = _clean_spaces(out).strip(" ;")
    out = re.sub(r"^\s*Scene:\s*", "", out, flags=re.IGNORECASE).strip(" ;")
    return _clean_spaces(out)


def inject_cut_visual_context(cut: dict[str, Any]) -> None:
    """Force year/period/place metadata into the stored image prompt."""
    if not isinstance(cut, dict):
        return
    prompt = str(cut.get("image_prompt") or "").strip()
    year = str(cut.get("visual_year") or "").strip()
    period = str(cut.get("visual_period") or "").strip()
    location = str(cut.get("visual_location") or "").strip()
    evidence = str(cut.get("visual_evidence") or "").strip()
    subject = str(cut.get("visual_subject") or cut.get("main_subject") or "").strip()
    explicit_scene = str(cut.get("visual_scene") or "").strip()
    if not (year or period or location or evidence or subject or explicit_scene):
        return
    scene = explicit_scene or prompt

    parts: list[str] = []
    year_period = "; ".join(part for part in (year, period) if part)
    if year_period:
        parts.append(f"Year/period: {year_period}")
    if location:
        parts.append(f"Exact place: {location}")
    if evidence:
        parts.append(f"Scene evidence: {evidence}")
    parts.append(f"Style: {IMAGE_PROMPT_REQUIRED_STYLE}")

    scene = _strip_visual_context_prefix(scene)
    scene_parts: list[str] = []
    if subject:
        scene_parts.append(f"Main subject: {subject}")
    if scene:
        scene_parts.append(f"Scene: {scene}")
    prefix = "; ".join(parts)
    suffix = "; ".join(scene_parts)
    cut["image_prompt"] = f"{prefix}; {suffix}" if suffix else prefix


def normalize_motion_prompt(prompt: str, image_prompt: str = "") -> str:
    """Default mode: leave script motion prompts unchanged."""
    return _clean_spaces(prompt)


def apply_script_visual_policy(script: dict[str, Any]) -> dict[str, Any]:
    """Keep generated prompts, but block known broken identity softeners."""
    if not isinstance(script, dict):
        return script
    script = limit_modern_japanese_history_visuals(script)
    if isinstance(script.get("thumbnail_prompt"), str):
        script["thumbnail_prompt"] = normalize_image_prompt(script["thumbnail_prompt"])
    cuts = script.get("cuts")
    if isinstance(cuts, list):
        script_context = " ".join(
            str(script.get(key) or "") for key in ("title", "topic", "description")
        )
        for cut in cuts:
            if isinstance(cut, dict) and isinstance(cut.get("image_prompt"), str):
                cut["image_prompt"] = normalize_cut_image_prompt(
                    cut["image_prompt"],
                    str(cut.get("narration") or ""),
                    script_context,
                )
                inject_cut_visual_context(cut)
    return script
