"""Visual prompt policy for script-generated cuts.

The script step owns the scene idea. This module keeps that idea, but forces the
image/video prompts into the simple local-generation grammar we can reliably use.
"""
from __future__ import annotations

import re
from typing import Any


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


def normalize_cut_image_prompt(prompt: str, narration: str = "", script_context: str = "") -> str:
    """Normalize one cut with narration-aware role alignment."""
    normalized = normalize_image_prompt(prompt)
    return repair_ant_grasshopper_alignment(normalized, narration, script_context)


def _strip_visual_context_prefix(prompt: str) -> str:
    out = prompt or ""
    out = re.sub(
        r"^\s*Year/period:\s*[^;]+(?:;\s*[^;]+)?;\s*"
        r"(?:Historically accurate period details:\s*[^;]+;\s*)?"
        r"(?:Exact place:\s*[^;]+;\s*)?"
        r"(?:Scene evidence:\s*[^;]+;\s*)?"
        r"Scene:\s*",
        "",
        out,
        flags=re.IGNORECASE,
    )
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
    if not (year or period or location):
        return

    parts: list[str] = []
    year_period = "; ".join(part for part in (year, period) if part)
    if year_period:
        parts.append(f"Year/period: {year_period}")
    if period:
        parts.append(f"Historically accurate period details: {period}")
    if location:
        parts.append(f"Exact place: {location}")
    if evidence:
        parts.append(f"Scene evidence: {evidence}")

    scene = _strip_visual_context_prefix(prompt)
    prefix = "; ".join(parts)
    cut["image_prompt"] = f"{prefix}; Scene: {scene}" if scene else prefix


def normalize_motion_prompt(prompt: str, image_prompt: str = "") -> str:
    """Default mode: leave script motion prompts unchanged."""
    return _clean_spaces(prompt)


def apply_script_visual_policy(script: dict[str, Any]) -> dict[str, Any]:
    """Keep generated prompts, but block known broken identity softeners."""
    if not isinstance(script, dict):
        return script
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
