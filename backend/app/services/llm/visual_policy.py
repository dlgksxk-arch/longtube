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
    """Default mode: leave script image prompts unchanged."""
    return _clean_spaces(prompt)


def normalize_motion_prompt(prompt: str, image_prompt: str = "") -> str:
    """Default mode: leave script motion prompts unchanged."""
    return _clean_spaces(prompt)


def apply_script_visual_policy(script: dict[str, Any]) -> dict[str, Any]:
    """Default mode: do not rewrite generated visual prompts."""
    return script
