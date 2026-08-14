"""Resolve per-cut Studio voice casting and ElevenLabs v3 emotion cues."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


_ROLE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("male_1", re.compile(r"^\s*(?:남성|남자)\s*1(?:\b|\s|[.:：-])", re.IGNORECASE)),
    ("male_2", re.compile(r"^\s*(?:남성|남자)\s*2(?:\b|\s|[.:：-])", re.IGNORECASE)),
    ("female_1", re.compile(r"^\s*(?:여성|여자)\s*1(?:\b|\s|[.:：-])", re.IGNORECASE)),
    ("female_2", re.compile(r"^\s*(?:여성|여자)\s*2(?:\b|\s|[.:：-])", re.IGNORECASE)),
)
_BRACKET_TAG_RE = re.compile(r"\[([a-z][a-z0-9_ -]{0,31})\]", re.IGNORECASE)
_VOICE_ROLES = frozenset(("male_1", "male_2", "female_1", "female_2"))

# The workbook's Korean direction notes are normalized only to ElevenLabs v3
# audio tags. Unknown notes remain metadata and are never spoken as narration.
_EMOTION_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("angry", ("분노", "격앙", "사나운", "증오", "폭발", "폭주", "독설", "폭언", "매서운")),
    ("shouts", ("고함", "내지르는", "지르는", "비명")),
    ("whispers", ("속삭", "나지막")),
    ("crying", ("울", "애원")),
    ("nervously", ("떨", "불안", "긴장", "기어들어")),
    ("booming", ("위압", "억압", "선언", "엄포")),
    ("sorrowful", ("슬픔", "비통", "서글")),
    ("slowly", ("느리", "천천히")),
)


@dataclass(frozen=True)
class ResolvedTTSVoice:
    voice_id: str
    role: str
    speaker: str
    emotion: str
    emotion_tags: tuple[str, ...]


def resolve_tts_voice(cut_data: dict[str, Any] | None, config: dict[str, Any] | None) -> ResolvedTTSVoice:
    """Use an explicitly mapped or role-tagged character voice, otherwise narrator."""
    cut = cut_data or {}
    cfg = config or {}
    speaker = str(cut.get("speaker") or "").strip()
    emotion = str(cut.get("emotion") or "").strip()
    role = "narrator"
    voice_id = str(cfg.get("tts_voice_id") or "").strip()
    direct_voice_id = str(cut.get("voice_id") or "").strip()
    character_voice_ids = cfg.get("tts_character_voice_ids")
    if not direct_voice_id and isinstance(character_voice_ids, dict):
        normalized_speaker = speaker.casefold()
        for character_name, candidate_voice_id in character_voice_ids.items():
            if str(character_name or "").strip().casefold() == normalized_speaker:
                direct_voice_id = str(candidate_voice_id or "").strip()
                break
    if direct_voice_id:
        role = "character"
        voice_id = direct_voice_id
    explicit_role = str(cut.get("voice_role") or "").strip().lower()
    mapped_role = explicit_role if explicit_role in _VOICE_ROLES else _mapped_character_role(speaker, cfg)
    if direct_voice_id:
        pass
    elif mapped_role:
        configured = str(cfg.get(f"tts_voice_{mapped_role}_id") or "").strip()
        if configured:
            role = mapped_role
            voice_id = configured
    else:
        for candidate, pattern in _ROLE_PATTERNS:
            if pattern.search(speaker):
                configured = str(cfg.get(f"tts_voice_{candidate}_id") or "").strip()
                if configured:
                    role = candidate
                    voice_id = configured
                break
    if (
        str(cut.get("voice_generation_mode") or "").strip().upper() == "DIALOGUE"
        and role == "narrator"
    ):
        raise ValueError(f"DIALOGUE 화자 전용 voice_id가 없습니다: {speaker or '(빈 화자)'}")
    return ResolvedTTSVoice(
        voice_id=voice_id,
        role=role,
        speaker=speaker,
        emotion=emotion,
        emotion_tags=tts_tags_for_cut(cut),
    )


def tts_tags_for_cut(cut_data: dict[str, Any] | None) -> tuple[str, ...]:
    """Use registered prepared-script tags; retain legacy emotion-note fallback."""
    cut = cut_data or {}
    if "tts_tags" in cut:
        raw_tags = cut.get("tts_tags")
        if not isinstance(raw_tags, list):
            return ()
        tags: list[str] = []
        for raw_tag in raw_tags:
            tag = str(raw_tag or "").strip().lower()
            if tag and tag not in tags:
                tags.append(tag)
        return tuple(tags)
    return emotion_tags_for_tts(str(cut.get("emotion") or ""))


def _mapped_character_role(speaker: str, config: dict[str, Any]) -> str:
    """Return only an explicitly configured character-to-Studio-voice role."""
    mapping = config.get("tts_character_voice_map")
    if not isinstance(mapping, dict):
        return ""
    normalized_speaker = speaker.casefold()
    for character_name, candidate in mapping.items():
        if str(character_name or "").strip().casefold() != normalized_speaker:
            continue
        role = str(candidate or "").strip().lower()
        return role if role in _VOICE_ROLES else ""
    return ""


def emotion_tags_for_tts(emotion: str | None) -> tuple[str, ...]:
    raw = str(emotion or "").strip()
    found: list[str] = []
    for tag in _BRACKET_TAG_RE.findall(raw):
        normalized = tag.strip().lower()
        if normalized and normalized not in found:
            found.append(normalized)
    lowered = raw.lower()
    for tag, keywords in _EMOTION_KEYWORDS:
        if any(keyword in lowered for keyword in keywords) and tag not in found:
            found.append(tag)
    return tuple(found)


def apply_emotion_to_tts_text(text: str, resolved: ResolvedTTSVoice, tts_model: str) -> str:
    """ElevenLabs v3 consumes bracketed audio tags; other engines get clean text."""
    narration = str(text or "").strip()
    if str(tts_model or "").strip().lower() != "elevenlabs" or not resolved.emotion_tags:
        return narration
    prefix = " ".join(f"[{tag}]" for tag in resolved.emotion_tags)
    return f"{prefix} {narration}".strip()
