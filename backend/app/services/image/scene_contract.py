"""Explicit-only scene facts used by the image prompt pipeline.

The parser intentionally leaves fields unknown when the visual subject or visual
scene does not state them. Narration is retained as a source fact, but is not
converted into visual geometry because a narrated person is not necessarily a
visible person.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Any


SCENE_CONTRACT_VERSION = "scene_contract/3"

_COUNT_VALUES = {
    "zero": 0,
    "single": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
_COUNT_TOKEN = r"zero|single|one|two|three|four|five|six|seven|eight|nine|ten|\d+"
_HUMAN_NOUN = (
    r"people|persons?|adults?|men|women|males?|females?|figures?|"
    r"commanders?|generals?|officials?|officers?|soldiers?|guards?|"
    r"messengers?|envoys?|monks?|civilians?|witnesses?|attendants?|elites?"
)
_PERSON_COUNT_RE = re.compile(
    rf"\b(?P<exact>exactly\s+)?(?P<count>{_COUNT_TOKEN})\s+"
    rf"(?:[a-z][a-z'-]*\s+){{0,5}}(?P<noun>{_HUMAN_NOUN})\b",
    re.IGNORECASE,
)
_ADULT_BODY_COUNT_RE = re.compile(
    rf"\b(?P<exact>exactly\s+)?(?P<count>{_COUNT_TOKEN})\s+"
    r"(?:(?:visible|separate|coherent)\s+){0,3}(?:adult|human)\s+bodies?\b",
    re.IGNORECASE,
)
_NO_PERSON_RE = re.compile(
    rf"\b(?P<phrase>no\s+(?:visible\s+)?(?:{_HUMAN_NOUN}))\b",
    re.IGNORECASE,
)

_FRAMING_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"\bobject-only\s+straight-down(?:\s+(?:macro|close-up))?(?:\s+view)?\b",
            re.IGNORECASE,
        ),
        "object-only straight-down",
    ),
    (
        re.compile(r"\bextreme\s+(?:facial|face)\s+close-up\b", re.IGNORECASE),
        "extreme facial close-up",
    ),
    (
        re.compile(r"\btight\s+(?:facial|face)\s+close-up\b", re.IGNORECASE),
        "tight facial close-up",
    ),
    (
        re.compile(r"\bmedium\s+three-quarter(?:\s+(?:shot|view))?\b", re.IGNORECASE),
        "medium three-quarter",
    ),
    (
        re.compile(r"\bhead-and-shoulders(?:\s+(?:shot|view|portrait))?\b", re.IGNORECASE),
        "head-and-shoulders",
    ),
    (re.compile(r"\bchest-up(?:\s+(?:shot|view|portrait))?\b", re.IGNORECASE), "chest-up"),
    (re.compile(r"\bwaist-up(?:\s+(?:shot|view|portrait))?\b", re.IGNORECASE), "waist-up"),
    (re.compile(r"\bfull[- ]body(?:\s+(?:shot|view))?\b", re.IGNORECASE), "full-body"),
    (re.compile(r"\bthree-quarter(?:\s+(?:shot|view))?\b", re.IGNORECASE), "three-quarter"),
    (re.compile(r"\bstraight-down(?:\s+(?:shot|view))?\b", re.IGNORECASE), "straight-down"),
    (re.compile(r"\boverhead(?:\s+(?:shot|view))\b", re.IGNORECASE), "overhead"),
    (re.compile(r"\bmacro\s+close-up\b", re.IGNORECASE), "macro close-up"),
    (
        re.compile(r"\bwide(?:\s+(?:shot|view|composition|scene|action))\b", re.IGNORECASE),
        "wide",
    ),
)

_FACE_VISIBLE_PATTERNS = (
    re.compile(r"\b(?:the\s+|his\s+|her\s+|their\s+)?face\s+(?:is\s+)?(?:fully\s+|clearly\s+)?visible\b", re.IGNORECASE),
    re.compile(r"\bcomplete\s+face\s+(?:is\s+)?visible\b", re.IGNORECASE),
    re.compile(r"\bboth\s+eyes\s+(?:are\s+)?visible\b", re.IGNORECASE),
)
_FACE_HIDDEN_PATTERNS = (
    re.compile(r"\b(?:the\s+|his\s+|her\s+|their\s+)?face\s+(?:is\s+)?(?:fully\s+)?hidden\b", re.IGNORECASE),
    re.compile(r"\b(?:the\s+|his\s+|her\s+|their\s+)?face\s+(?:is\s+)?not\s+visible\b", re.IGNORECASE),
    re.compile(r"\b(?:the\s+|his\s+|her\s+|their\s+)?face\s+(?:stays?\s+|is\s+)?outside\s+(?:the\s+)?(?:frame|crop)\b", re.IGNORECASE),
)

_SLOT_TOKEN = r"far[- ]left|center[- ]left|left|centre|center|center[- ]right|far[- ]right|right"
_SLOT_RELATION_RE = re.compile(
    rf"\b(?:(?:stands?|kneels?|sits?|waits?|appears?|remains?|occupies?)\s+)?"
    rf"(?:at|on|in)\s+(?:the\s+)?(?P<slot>{_SLOT_TOKEN})(?:\s+slot)?\b",
    re.IGNORECASE,
)
_SLOT_AFTER_ACTION_RE = re.compile(
    rf"\b(?:stands?|kneels?|sits?|waits?|appears?|remains?|occupies?)\s+"
    rf"(?:the\s+)?(?P<slot>{_SLOT_TOKEN})(?:\s+slot)?\b",
    re.IGNORECASE,
)
_SLOT_PREFIX_RE = re.compile(
    rf"^\s*(?:the\s+)?(?P<slot>{_SLOT_TOKEN})(?:\s+slot)?\s*(?::|-|,)\s*",
    re.IGNORECASE,
)
_SLOT_ACTOR_PREFIX_RE = re.compile(
    rf"^\s*(?:the\s+)?(?P<slot>{_SLOT_TOKEN})\s+"
    rf"(?P<identity>(?:[a-z][a-z'-]*\s+){{0,3}}(?:{_HUMAN_NOUN}))"
    r"(?:['’]s)?\b",
    re.IGNORECASE,
)
_IDENTITY_ACTION_RE = re.compile(
    r"\b(?:stands?|kneels?|sits?|waits?|appears?|remains?|occupies?|faces?|"
    r"holds?|grips?|carries|passes?|gives?|receives?|supports?|presses?|"
    r"touches?|points?|looks?|turns?|raises?|lowers?|wears?|with)\b",
    re.IGNORECASE,
)
_HUMAN_IDENTITY_RE = re.compile(rf"\b(?:{_HUMAN_NOUN})\b", re.IGNORECASE)
_PROPER_NAME_RE = re.compile(r"\b[A-Z][A-Za-z.'-]*(?:\s+[A-Z][A-Za-z.'-]*)*\b")

_VISIBLE_HAND_COUNT_RE = re.compile(
    rf"\b(?P<count>{_COUNT_TOKEN})\s+(?:clearly\s+)?visible\s+"
    r"(?:[a-z][a-z-]*\s+){0,4}hands?\b",
    re.IGNORECASE,
)
_TRAILING_VISIBLE_HAND_COUNT_RE = re.compile(
    rf"\b(?P<count>{_COUNT_TOKEN})\s+(?:[a-z][a-z-]*\s+){{0,4}}hands?\s+"
    r"(?:are\s+|is\s+)?visible\b",
    re.IGNORECASE,
)
_BOTH_VISIBLE_HANDS_RE = re.compile(
    r"\bboth\s+(?:(?:clearly\s+)?visible\s+(?:[a-z][a-z-]*\s+){0,3}hands|"
    r"(?:[a-z][a-z-]*\s+){0,3}hands\s+(?:are\s+)?visible)\b",
    re.IGNORECASE,
)
_HAND_POSE_RE = re.compile(
    r"\b(?:(?:his|her|their)\s+)?(?:(?:exactly\s+)?(?:zero|one|two)\s+"
    r"(?:clearly\s+)?visible\s+)?(?:[a-z][a-z-]*\s+){0,3}hands?\s+"
    r"(?:is\s+|are\s+)?(?:grips?|gripping|holds?|holding|carries|carrying|"
    r"supports?|supporting|passes?|passing|gives?|giving|receives?|receiving|"
    r"presses?|pressing|touches?|touching|points?|pointing|rests?|resting|"
    r"opens?|opening|clenches?|clenching|reaches?|reaching)\b[^,;.]*",
    re.IGNORECASE,
)
_HAND_STATE_PATTERNS = (
    re.compile(
        r"\b(?:(?:his|her|their)\s+)?(?:(?:left|right|both)\s+)?"
        r"(?:fully\s+)?open\s+palms?\b[^,;.]*",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:(?:his|her|their)\s+)?(?:(?:left|right|both)\s+)?palms?\s+"
        r"(?:is\s+|are\s+)?(?:fully\s+)?open\b[^,;.]*",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:(?:his|her|their)\s+)?(?:(?:left|right|both)\s+)?"
        r"(?:closed|clenched)\s+fists?\b[^,;.]*",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:(?:his|her|their)\s+)?(?:(?:left|right|both)\s+)?fists?\s+"
        r"(?:is\s+|are\s+)?(?:closed|clenched)\b[^,;.]*",
        re.IGNORECASE,
    ),
)

_GLOBAL_EXACT_VISIBLE_HANDS_RE = re.compile(
    rf"\bexactly\s+(?P<count>{_COUNT_TOKEN})\s+(?:clearly\s+)?visible\s+"
    r"(?:[a-z][a-z-]*\s+){0,3}hands?\b",
    re.IGNORECASE,
)
_GLOBAL_TOTAL_VISIBLE_HANDS_RE = re.compile(
    rf"\b(?P<count>{_COUNT_TOKEN})\s+(?:clearly\s+)?visible\s+"
    r"(?:[a-z][a-z-]*\s+){0,3}hands?\s+(?:in\s+)?total\b",
    re.IGNORECASE,
)
_GLOBAL_ALL_HANDS_VISIBLE_RE = re.compile(
    rf"\ball\s+(?P<count>{_COUNT_TOKEN})\s+(?:[a-z][a-z-]*\s+){{0,3}}hands?\s+"
    r"(?:are\s+)?(?:clearly\s+)?visible\b",
    re.IGNORECASE,
)
_GLOBAL_BOTH_HANDS_VISIBLE_RE = re.compile(
    r"\b(?:both\s+(?:clearly\s+)?visible\s+(?:[a-z][a-z-]*\s+){0,3}hands|"
    r"both\s+(?:[a-z][a-z-]*\s+){0,3}hands\s+(?:are\s+)?(?:clearly\s+)?visible)\b",
    re.IGNORECASE,
)
_GLOBAL_ZERO_HANDS_FINGERS_RE = re.compile(
    r"\bzero\s+(?:clearly\s+)?visible\s+hands(?:\s*(?:/|and|or)\s*"
    r"(?:zero\s+)?(?:clearly\s+)?visible\s+fingers)?\b",
    re.IGNORECASE,
)
_GLOBAL_SCOPE_PREFIX_RE = re.compile(
    r"^(?:there\s+(?:are|is)|overall|in\s+total|"
    r"the\s+(?:frame|image|scene|composition)\s+(?:contains|shows|has))\s*[:,-]?\s*$",
    re.IGNORECASE,
)
_GLOBAL_SCOPE_CUE_RE = re.compile(
    r"\b(?:in|across|throughout)\s+(?:the\s+)?(?:frame|image|scene|composition)\b|"
    r"\boverall\b|\bin\s+total\b",
    re.IGNORECASE,
)
_POSSESSIVE_SCOPE_RE = re.compile(r"\b(?:his|her|their|its)\b|\b[A-Za-z][A-Za-z.'-]*['’]s\b", re.IGNORECASE)
_GLOBAL_PREFIX_NAME_STOPWORDS = {
    "all",
    "both",
    "composition",
    "exactly",
    "frame",
    "image",
    "in",
    "overall",
    "scene",
    "the",
    "there",
    "zero",
}
_EACH_ACTOR_ONE_HAND_PATTERNS = (
    re.compile(
        r"\bone\s+(?:visible\s+)?(?:[a-z][a-z-]*\s+){0,3}hand\s+from\s+each\s+"
        r"(?:adult|actor|person|figure|man|woman)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\beach\s+(?:adult|actor|person|figure|man|woman)\s+"
        r"(?:uses?|shows?|has|extends?|holds?|grips?|carries|reaches?\s+with)\s+"
        r"(?:only\s+|exactly\s+)?one\s+(?:visible\s+)?(?:[a-z][a-z-]*\s+){0,3}hand\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\beach\s+(?:[a-z][a-z-]*\s+){0,4}with\s+(?:only\s+|exactly\s+)?"
        r"one\s+(?:visible\s+)?(?:[a-z][a-z-]*\s+){0,3}hand\b",
        re.IGNORECASE,
    ),
)
_UNUSED_HAND_OUTSIDE_RE = re.compile(
    r"\b(?P<clause>(?:(?:each|every)\s+(?:adult|actor|person|figure|man|woman)(?:['’]s)?\s+)?"
    r"(?:(?:all|both|every|the|their|his|her)\s+)?(?:other|unused|remaining|far)\s+"
    r"(?:hands?|arms?)\b(?:"
    r"[^,;.]{0,140}?\boutside\s+(?:the\s+)?(?:frame|crop)\b|"
    r"[^,;.]{0,100}?\b(?:fully|completely|entirely)\s+hidden\b"
    r"(?:\s+behind\b[^,;.]{0,60})?))",
    re.IGNORECASE,
)

_PROP_NOUNS = (
    "locking beam",
    "gate beam",
    "gate bar",
    "command tally",
    "cloth packet",
    "rank seal",
    "timber gate",
    "sealed packet",
    "message packet",
    "wooden tablet",
    "stone marker",
    "sword",
    "dagger",
    "spear",
    "shield",
    "bow",
    "packet",
    "bundle",
    "seal",
    "tally",
    "tablet",
    "gate",
    "beam",
    "bar",
    "chain",
    "rope",
    "sash",
    "standard",
    "banner",
    "flag",
    "mirror",
    "jar",
    "cup",
    "bowl",
    "bowls",
    "helmet",
    "stretcher",
    "scroll",
    "document",
    "letter",
    "message",
    "map",
    "chair",
    "stool",
    "table",
)
_PROP_RE = re.compile(
    rf"\b(?:{'|'.join(re.escape(noun) for noun in _PROP_NOUNS)})\b",
    re.IGNORECASE,
)
_CONTACT_RE = re.compile(
    r"\b(?:grips?|gripping|holds?|holding|carries|carrying|passes?|passing|"
    r"gives?|giving|receives?|receiving|supports?|supporting|presses?|pressing|"
    r"touches?|touching|rests?|resting|lies?|lying|plants?|planting|pulls?|"
    r"pulling|pushes?|pushing|reaches?\s+for|reaching\s+for|steps?\s+on)\b",
    re.IGNORECASE,
)
_QUANTIFIED_PROP_PREFIX_RE = re.compile(
    rf"(?P<phrase>(?:(?:exactly\s+)?(?:{_COUNT_TOKEN})|a|an|the)\s+"
    r"(?:[A-Za-z][A-Za-z'-]*\s+){0,5})$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SourceFact:
    source: str
    text: str

    def to_dict(self) -> dict[str, str]:
        return {"source": self.source, "text": self.text}


@dataclass(frozen=True)
class ActorSlot:
    identity: str
    slot: str | None
    visible_hand_count: int | None = None
    hand_poses: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "slot": self.slot,
            "visible_hand_count": self.visible_hand_count,
            "hand_poses": list(self.hand_poses),
        }


@dataclass(frozen=True)
class SceneContract:
    person_count: int | None
    visible_hand_count: int | None
    framing: str | None
    face_visibility: str | None
    actors: tuple[ActorSlot, ...]
    unused_hand_constraints: tuple[str, ...]
    essential_props: tuple[str, ...]
    contacts: tuple[str, ...]
    source_facts: tuple[SourceFact, ...]
    diagnostics: tuple[str, ...]
    version: str = SCENE_CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "person_count": self.person_count,
            "visible_hand_count": self.visible_hand_count,
            "framing": self.framing,
            "face_visibility": self.face_visibility,
            "actors": [actor.to_dict() for actor in self.actors],
            "unused_hand_constraints": list(self.unused_hand_constraints),
            "essential_props": list(self.essential_props),
            "contacts": list(self.contacts),
            "source_facts": [fact.to_dict() for fact in self.source_facts],
            "diagnostics": list(self.diagnostics),
        }

    def canonical_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def stable_hash(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class _CountCandidate:
    value: int
    phrase: str
    exact: bool


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip(" \t\r\n;,.")


def _normalize_input(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _count_value(token: str) -> int:
    lowered = token.lower()
    if lowered.isdigit():
        return int(lowered)
    return _COUNT_VALUES[lowered]


def _count_candidates(text: str) -> tuple[_CountCandidate, ...]:
    candidates: list[_CountCandidate] = []
    seen: set[tuple[int, str]] = set()
    for match in _PERSON_COUNT_RE.finditer(text):
        value = _count_value(match.group("count"))
        phrase = _clean(match.group(0)).lower()
        key = (value, phrase)
        if key not in seen:
            candidates.append(_CountCandidate(value, phrase, bool(match.group("exact"))))
            seen.add(key)
    for match in _ADULT_BODY_COUNT_RE.finditer(text):
        value = _count_value(match.group("count"))
        phrase = _clean(match.group(0)).lower()
        key = (value, phrase)
        if key not in seen:
            candidates.append(_CountCandidate(value, phrase, bool(match.group("exact"))))
            seen.add(key)
    for match in _NO_PERSON_RE.finditer(text):
        phrase = _clean(match.group("phrase")).lower()
        key = (0, phrase)
        if key not in seen:
            candidates.append(_CountCandidate(0, phrase, True))
            seen.add(key)
    return tuple(candidates)


def _extract_person_count(subject: str, scene: str) -> tuple[int | None, tuple[str, ...]]:
    diagnostics: list[str] = []
    subject_counts = _count_candidates(subject)
    scene_counts = _count_candidates(scene)

    if subject_counts:
        exact_subject_counts = tuple(candidate for candidate in subject_counts if candidate.exact)
        authoritative_subject_counts = exact_subject_counts or subject_counts
        subject_values = {candidate.value for candidate in authoritative_subject_counts}
        if len(subject_values) != 1:
            return None, ("person_count:conflicting_visual_subject_values",)
        value = next(iter(subject_values))
        scene_totals = [
            candidate.value
            for candidate in scene_counts
            if candidate.exact or candidate.value == 0 or candidate.value > 1
        ]
        if any(scene_value != value for scene_value in scene_totals):
            return None, ("person_count:visual_subject_scene_conflict",)
        return value, ()

    if not scene_counts:
        return None, ("person_count:unknown",)
    if len(scene_counts) > 1:
        return None, ("person_count:multiple_scene_count_phrases",)
    return scene_counts[0].value, tuple(diagnostics)


def _extract_framing(subject: str, scene: str) -> tuple[str | None, tuple[str, ...]]:
    text = f"{scene}; {subject}"
    matches: list[tuple[int, int, str]] = []
    for pattern, canonical in _FRAMING_PATTERNS:
        for match in pattern.finditer(text):
            matches.append((match.start(), match.end(), canonical))
    matches.sort(key=lambda item: (item[0], -(item[1] - item[0])))

    accepted: list[tuple[int, int, str]] = []
    for candidate in matches:
        start, end, _ = candidate
        if any(start < accepted_end and end > accepted_start for accepted_start, accepted_end, _ in accepted):
            continue
        accepted.append(candidate)
    values = tuple(dict.fromkeys(value for _, _, value in accepted))
    if not values:
        return None, ("framing:unknown",)
    if len(values) > 1:
        return None, ("framing:conflicting_explicit_values",)
    return values[0], ()


def _extract_face_visibility(subject: str, scene: str) -> tuple[str | None, tuple[str, ...]]:
    text = f"{scene}; {subject}"
    visible = any(pattern.search(text) for pattern in _FACE_VISIBLE_PATTERNS)
    hidden = any(pattern.search(text) for pattern in _FACE_HIDDEN_PATTERNS)
    if visible and hidden:
        return None, ("face_visibility:conflicting_explicit_values",)
    if visible:
        return "visible", ()
    if hidden:
        return "hidden", ()
    return None, ("face_visibility:unknown",)


def _scene_segments(text: str) -> tuple[str, ...]:
    pieces = re.split(
        rf"\s*;\s*|\.\s+|,\s+(?=(?:the\s+)?(?:{_SLOT_TOKEN})\b)",
        text,
        flags=re.IGNORECASE,
    )
    return tuple(cleaned for piece in pieces if (cleaned := _clean(piece)))


def _normalize_slot(slot: str) -> str:
    return slot.lower().replace("centre", "center").replace(" ", "-")


def _valid_identity(identity: str) -> bool:
    return bool(_HUMAN_IDENTITY_RE.search(identity) or _PROPER_NAME_RE.search(identity))


def _identity_before_relation(
    segment: str,
    relation_start: int,
    lower_bound: int = 0,
) -> tuple[str | None, int]:
    prefix = segment[lower_bound:relation_start]
    delimiter_end = 0
    for delimiter in re.finditer(r"[,;:]|\band\b", prefix, re.IGNORECASE):
        delimiter_end = delimiter.end()
    identity_start = lower_bound + delimiter_end
    before = _clean(segment[identity_start:relation_start])
    leading = re.match(r"^(?:and|while|with)\s+", before, re.IGNORECASE)
    if leading:
        identity_start += leading.end()
        before = _clean(before[leading.end() :])
    action = _IDENTITY_ACTION_RE.search(before)
    if action:
        before = _clean(before[: action.start()])
    if len(before.split()) > 10:
        before = " ".join(before.split()[-10:])
    return (before if before and _valid_identity(before) else None), identity_start


def _identity_after_prefix(segment: str, prefix_end: int) -> str | None:
    after = _clean(segment[prefix_end:])
    action = _IDENTITY_ACTION_RE.search(after)
    if action:
        after = _clean(after[: action.start()])
    if len(after.split()) > 10:
        after = " ".join(after.split()[:10])
    return after if after and _valid_identity(after) else None


def _extract_visible_hand_count(segment: str) -> tuple[int | None, bool]:
    values: set[int] = set()
    for match in _VISIBLE_HAND_COUNT_RE.finditer(segment):
        suffix = segment[match.end() : match.end() + 20]
        if re.match(r"\s+(?:in\s+)?total\b", suffix, re.IGNORECASE):
            continue
        values.add(_count_value(match.group("count")))
    values.update(
        _count_value(match.group("count"))
        for match in _TRAILING_VISIBLE_HAND_COUNT_RE.finditer(segment)
    )
    if _BOTH_VISIBLE_HANDS_RE.search(segment):
        values.add(2)
    if len(values) == 1:
        return next(iter(values)), False
    return None, len(values) > 1


def _extract_hand_poses(segment: str) -> tuple[str, ...]:
    matches: list[tuple[int, int, str]] = []
    for pattern in (_HAND_POSE_RE, *_HAND_STATE_PATTERNS):
        for match in pattern.finditer(segment):
            matches.append((match.start(), match.end(), _clean(match.group(0))))
    matches.sort(key=lambda item: (item[0], -(item[1] - item[0])))

    accepted: list[tuple[int, int, str]] = []
    for candidate in matches:
        start, end, text = candidate
        if not text:
            continue
        if any(start >= accepted_start and end <= accepted_end for accepted_start, accepted_end, _ in accepted):
            continue
        if text.casefold() in {accepted_text.casefold() for _, _, accepted_text in accepted}:
            continue
        accepted.append(candidate)
    return tuple(text for _, _, text in accepted)


def _slot_relation_matches(segment: str) -> tuple[re.Match[str], ...]:
    matches = [
        *list(_SLOT_RELATION_RE.finditer(segment)),
        *list(_SLOT_AFTER_ACTION_RE.finditer(segment)),
    ]
    matches.sort(key=lambda match: (match.start(), -(match.end() - match.start())))
    accepted: list[re.Match[str]] = []
    for match in matches:
        if any(match.start() < prior.end() and match.end() > prior.start() for prior in accepted):
            continue
        accepted.append(match)
    return tuple(accepted)


def _actor_hand_scope(segment: str) -> str:
    starts = [match.start() for match in _GLOBAL_TOTAL_VISIBLE_HANDS_RE.finditer(segment)]
    starts.extend(match.start() for match in _GLOBAL_ALL_HANDS_VISIBLE_RE.finditer(segment))
    if any(pattern.search(segment) for pattern in _EACH_ACTOR_ONE_HAND_PATTERNS):
        starts.extend(match.start() for match in _GLOBAL_EXACT_VISIBLE_HANDS_RE.finditer(segment))
    if not starts:
        return segment
    return segment[: min(starts)]


def _extract_actor_slots(scene: str) -> tuple[tuple[ActorSlot, ...], tuple[str, ...]]:
    actors: list[ActorSlot] = []
    diagnostics: list[str] = []

    for segment in _scene_segments(scene):
        slot_matches = _slot_relation_matches(segment)
        prefix_match = _SLOT_PREFIX_RE.search(segment)
        actor_prefix_match = _SLOT_ACTOR_PREFIX_RE.search(segment)
        actor_records: list[tuple[str, str, int]] = []
        lower_bound = 0
        for slot_match in slot_matches:
            identity, identity_start = _identity_before_relation(
                segment,
                slot_match.start(),
                lower_bound,
            )
            lower_bound = slot_match.end()
            if identity:
                actor_records.append(
                    (identity, _normalize_slot(slot_match.group("slot")), identity_start)
                )
        if not actor_records and prefix_match:
            identity = _identity_after_prefix(segment, prefix_match.end())
            if identity:
                actor_records.append(
                    (identity, _normalize_slot(prefix_match.group("slot")), prefix_match.end())
                )
        if not actor_records and actor_prefix_match:
            identity = _clean(actor_prefix_match.group("identity"))
            if _valid_identity(identity):
                actor_records.append(
                    (
                        identity,
                        _normalize_slot(actor_prefix_match.group("slot")),
                        actor_prefix_match.start("identity"),
                    )
                )

        for index, (identity, slot, identity_start) in enumerate(actor_records):
            scope_end = actor_records[index + 1][2] if index + 1 < len(actor_records) else len(segment)
            actor_segment = _actor_hand_scope(segment[identity_start:scope_end])
            hand_count, hand_conflict = _extract_visible_hand_count(actor_segment)
            if hand_conflict:
                diagnostics.append(f"visible_hand_count:conflict:{identity}")
            actors.append(
                ActorSlot(
                    identity=identity,
                    slot=slot,
                    visible_hand_count=hand_count,
                    hand_poses=_extract_hand_poses(actor_segment),
                )
            )

    merged: list[ActorSlot] = []
    for actor in actors:
        existing_index = next(
            (
                index
                for index, existing in enumerate(merged)
                if existing.identity.casefold() == actor.identity.casefold() and existing.slot == actor.slot
            ),
            None,
        )
        if existing_index is None:
            merged.append(actor)
            continue
        existing = merged[existing_index]
        counts = {
            count
            for count in (existing.visible_hand_count, actor.visible_hand_count)
            if count is not None
        }
        if len(counts) > 1:
            diagnostics.append(f"visible_hand_count:conflict:{actor.identity}")
            merged_count = None
        else:
            merged_count = next(iter(counts), None)
        merged[existing_index] = ActorSlot(
            identity=existing.identity,
            slot=existing.slot,
            visible_hand_count=merged_count,
            hand_poses=tuple(dict.fromkeys((*existing.hand_poses, *actor.hand_poses))),
        )

    slots: dict[str, set[str]] = {}
    for actor in merged:
        if actor.slot:
            slots.setdefault(actor.slot, set()).add(actor.identity.casefold())
    for slot, identities in slots.items():
        if len(identities) > 1:
            diagnostics.append(f"actor_slot:conflict:{slot}")
    if not merged:
        diagnostics.append("actor_slots:none")
    return tuple(merged), tuple(dict.fromkeys(diagnostics))


def _apply_explicit_each_actor_hand_count(
    actors: tuple[ActorSlot, ...],
    person_count: int | None,
    scene: str,
) -> tuple[tuple[ActorSlot, ...], tuple[str, ...]]:
    if not any(pattern.search(scene) for pattern in _EACH_ACTOR_ONE_HAND_PATTERNS):
        return actors, ()
    if person_count is None or person_count <= 0 or len(actors) != person_count:
        return actors, ("actor_hand_distribution:unresolved",)

    diagnostics: list[str] = []
    updated: list[ActorSlot] = []
    for actor in actors:
        hand_count = actor.visible_hand_count
        if hand_count not in {None, 1}:
            diagnostics.append(f"actor_hand_distribution:conflict:{actor.identity}")
            hand_count = None
        elif hand_count is None:
            hand_count = 1
        updated.append(
            ActorSlot(
                identity=actor.identity,
                slot=actor.slot,
                visible_hand_count=hand_count,
                hand_poses=actor.hand_poses,
            )
        )
    return tuple(updated), tuple(diagnostics)


def _extract_unused_hand_constraints(subject: str, scene: str) -> tuple[str, ...]:
    constraints: list[str] = []
    for text in (subject, scene):
        for match in _UNUSED_HAND_OUTSIDE_RE.finditer(text):
            clause = _clean(match.group("clause"))
            if clause and clause.casefold() not in {
                constraint.casefold() for constraint in constraints
            }:
                constraints.append(clause)
    return tuple(constraints)


def _has_nontrivial_proper_name(text: str) -> bool:
    tokens = re.findall(r"\b[A-Z][A-Za-z.'-]*\b", text)
    return any(token.casefold() not in _GLOBAL_PREFIX_NAME_STOPWORDS for token in tokens)


def _is_actor_scoped_hand_phrase(
    segment: str,
    match: re.Match[str],
    actors: tuple[ActorSlot, ...],
) -> bool:
    lowered_segment = segment.casefold()
    if any(actor.identity.casefold() in lowered_segment for actor in actors):
        return True
    if (
        _SLOT_RELATION_RE.search(segment)
        or _SLOT_AFTER_ACTION_RE.search(segment)
        or _SLOT_PREFIX_RE.search(segment)
    ):
        return True

    prefix = segment[: match.start()]
    if _POSSESSIVE_SCOPE_RE.search(prefix):
        return True
    cleaned_prefix = _clean(prefix)
    if not cleaned_prefix or _GLOBAL_SCOPE_PREFIX_RE.fullmatch(cleaned_prefix):
        return False
    if _GLOBAL_SCOPE_CUE_RE.search(segment) and not _has_nontrivial_proper_name(prefix):
        return False

    aggregate_counts = _count_candidates(cleaned_prefix)
    if (
        len(aggregate_counts) == 1
        and aggregate_counts[0].value > 1
        and not _has_nontrivial_proper_name(prefix)
    ):
        return False
    return bool(_HUMAN_IDENTITY_RE.search(cleaned_prefix))


def _explicit_global_hand_values(
    subject: str,
    scene: str,
    actors: tuple[ActorSlot, ...],
) -> tuple[int, ...]:
    patterns: tuple[tuple[re.Pattern[str], int | None], ...] = (
        (_GLOBAL_EXACT_VISIBLE_HANDS_RE, None),
        (_GLOBAL_TOTAL_VISIBLE_HANDS_RE, None),
        (_GLOBAL_ALL_HANDS_VISIBLE_RE, None),
        (_GLOBAL_BOTH_HANDS_VISIBLE_RE, 2),
        (_GLOBAL_ZERO_HANDS_FINGERS_RE, 0),
    )
    values: list[int] = []
    for text in (subject, scene):
        for segment in _scene_segments(text):
            for pattern, fixed_value in patterns:
                for match in pattern.finditer(segment):
                    if _is_actor_scoped_hand_phrase(segment, match, actors):
                        continue
                    value = fixed_value
                    if value is None:
                        value = _count_value(match.group("count"))
                    values.append(value)
    return tuple(values)


def _complete_actor_hand_sum(
    person_count: int | None,
    actors: tuple[ActorSlot, ...],
) -> int | None:
    if person_count is None or person_count <= 0 or len(actors) != person_count:
        return None
    if len({actor.identity.casefold() for actor in actors}) != len(actors):
        return None
    if any(actor.visible_hand_count is None for actor in actors):
        return None
    return sum(actor.visible_hand_count or 0 for actor in actors)


def _extract_global_visible_hand_count(
    subject: str,
    scene: str,
    actors: tuple[ActorSlot, ...],
    person_count: int | None,
) -> tuple[int | None, tuple[str, ...]]:
    explicit_values = set(_explicit_global_hand_values(subject, scene, actors))
    actor_sum = _complete_actor_hand_sum(person_count, actors)
    if len(explicit_values) > 1:
        return None, ("visible_hand_count:conflicting_explicit_values",)
    if explicit_values:
        explicit_value = next(iter(explicit_values))
        if actor_sum is not None and actor_sum != explicit_value:
            return None, ("visible_hand_count:explicit_actor_sum_conflict",)
        return explicit_value, ()
    if actor_sum is not None:
        return actor_sum, ()
    return None, ("visible_hand_count:unknown",)


def _prop_phrase(text: str, match: re.Match[str]) -> str:
    prefix = text[max(0, match.start() - 100) : match.start()]
    boundary = max(prefix.rfind(mark) for mark in (";", ",", ".", ":"))
    if boundary >= 0:
        prefix = prefix[boundary + 1 :]
    quantified = _QUANTIFIED_PROP_PREFIX_RE.search(prefix)
    if quantified:
        return _clean(f"{quantified.group('phrase')} {match.group(0)}").lower()
    return _clean(match.group(0)).lower()


def _extract_props(subject: str, scene: str) -> tuple[str, ...]:
    props: list[str] = []
    for text in (subject, scene):
        for match in _PROP_RE.finditer(text):
            phrase = _prop_phrase(text, match)
            if phrase and phrase.casefold() not in {prop.casefold() for prop in props}:
                props.append(phrase)
    return tuple(props)


def _extract_contacts(subject: str, scene: str) -> tuple[str, ...]:
    contacts: list[str] = []
    for segment in (*_scene_segments(subject), *_scene_segments(scene)):
        if not _CONTACT_RE.search(segment) or not _PROP_RE.search(segment):
            continue
        if segment.casefold() not in {contact.casefold() for contact in contacts}:
            contacts.append(segment)
    return tuple(contacts)


def build_scene_contract(
    *,
    narration: str = "",
    visual_subject: str = "",
    visual_scene: str = "",
) -> SceneContract:
    """Build an explicit-only scene contract from current pipeline inputs."""

    narration = _normalize_input(narration)
    visual_subject = _normalize_input(visual_subject)
    visual_scene = _normalize_input(visual_scene)

    person_count, person_diagnostics = _extract_person_count(visual_subject, visual_scene)
    framing, framing_diagnostics = _extract_framing(visual_subject, visual_scene)
    face_visibility, face_diagnostics = _extract_face_visibility(visual_subject, visual_scene)
    actors, actor_diagnostics = _extract_actor_slots(visual_scene)
    actors, actor_hand_diagnostics = _apply_explicit_each_actor_hand_count(
        actors,
        person_count,
        visual_scene,
    )
    visible_hand_count, global_hand_diagnostics = _extract_global_visible_hand_count(
        visual_subject,
        visual_scene,
        actors,
        person_count,
    )

    source_facts = tuple(
        SourceFact(source, text)
        for source, text in (
            ("narration", narration),
            ("visual_subject", visual_subject),
            ("visual_scene", visual_scene),
        )
        if text
    )
    diagnostics = tuple(
        dict.fromkeys(
            (
                *person_diagnostics,
                *framing_diagnostics,
                *face_diagnostics,
                *actor_diagnostics,
                *actor_hand_diagnostics,
                *global_hand_diagnostics,
            )
        )
    )
    return SceneContract(
        person_count=person_count,
        visible_hand_count=visible_hand_count,
        framing=framing,
        face_visibility=face_visibility,
        actors=actors,
        unused_hand_constraints=_extract_unused_hand_constraints(
            visual_subject,
            visual_scene,
        ),
        essential_props=_extract_props(visual_subject, visual_scene),
        contacts=_extract_contacts(visual_subject, visual_scene),
        source_facts=source_facts,
        diagnostics=diagnostics,
    )


__all__ = [
    "ActorSlot",
    "SCENE_CONTRACT_VERSION",
    "SceneContract",
    "SourceFact",
    "build_scene_contract",
]
