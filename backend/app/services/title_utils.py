"""Shared helpers for video title formatting."""

from __future__ import annotations

import re
from typing import Any, Iterable, Optional

_EP_PREFIX_RE = re.compile(r"^\s*EP\.?\s*0*\d+\s*[-:.)]?\s*", re.IGNORECASE)
_EPISODE_PREFIX_RE = re.compile(
    r"^\s*(?:episode|ep)\s*0*\d+\s*[-:.)]\s*",
    re.IGNORECASE,
)
_EP_TAIL_RE = re.compile(
    r"\s*(?:[|/\\\-–—:·]\s*)?"
    r"(?:"
    r"EP\.?\s*0*\d+"
    r"|episode\s*0*\d+"
    r"|episodes?\s*0*\d+"
    r"|에피소드\s*0*\d+"
    r"|第\s*0*\d+\s*[話话集]"
    r"|第\s*[一二三四五六七八九十百千〇零]+\s*[話话集]"
    r"|एपिसोड\s*0*\d+"
    r"|भाग\s*0*\d+"
    r")\s*$",
    re.IGNORECASE,
)
_EP_PIPE_TAIL_RE = re.compile(
    r"\s*[|/\\]\s*"
    r"(?:"
    r".{0,48}?"
    r"(?:EP\.?\s*0*\d+|episode\s*0*\d+|에피소드\s*0*\d+|एपिसोड\s*0*\d+|भाग\s*0*\d+)"
    r")\s*$",
    re.IGNORECASE,
)
_EP_MARKER_RE = re.compile(
    r"\s*(?:[-–—:·]\s*)?"
    r"(?:EP\.?\s*0*\d+|episode\s*0*\d+|에피소드\s*0*\d+|एपिसोड\s*0*\d+|भाग\s*0*\d+)"
    r"\s*(?:[-–—:·]\s*)?",
    re.IGNORECASE,
)
_WHITESPACE_RE = re.compile(r"\s+")
_HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
_JAPANESE_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")
_SHORTS_NUMBER_HASHTAG_RE = re.compile(r"\s+#\d+\b")
_SHORTS_HASHTAG_RE = re.compile(r"\s+#Shorts\b", re.IGNORECASE)
_HASHTAG_TOKEN_RE = re.compile(r"^#?[0-9A-Za-z가-힣\u0900-\u097Fぁ-んァ-ン一-龥]+$")
_SHORTS_PART_MARKER_RE = re.compile(
    r"\s*(?:[|/\\\-–—:·]\s*)?"
    r"(?:part|pt\.?|파트|भाग)\s*0*\d+\b"
    r"\s*(?:[|/\\\-–—:·]\s*)?",
    re.IGNORECASE,
)
_TITLE_HASHTAG_RE = re.compile(r"\s+#[0-9A-Za-z가-힣\u0900-\u097Fぁ-んァ-ン一-龥]+\b")
_GENERIC_KO_HOOK_PREFIX_RE = re.compile(
    r"^\s*(?:"
    r"결말을\s*바꿔버린|운명을\s*바꾼|판을\s*뒤집은|역사를\s*바꾼|"
    r"교과서가\s*놓친|숨겨진|실패에서\s*시작된|끝까지\s*숨긴|"
    r"모두가\s*속은|아무도\s*몰랐던|진짜\s*무서운"
    r")\s+"
)
_GENERIC_EN_HOOK_PREFIX_RE = re.compile(
    r"^\s*(?:the\s+)?(?:moment|mistake|secret|truth|deal|choice|disaster)\s+that\s+",
    re.IGNORECASE,
)
_GENERIC_EN_SHORTS_TITLE_RE = re.compile(
    r"^\s*(?:"
    r"this\s+choice\s+ruined\s+everything"
    r"|one\s+deal\.?\s+total\s+humiliation\.?"
    r"|the\s+mistake\s+nobody\s+survived"
    r"|the\s+ugly\s+truth\s+behind\b.*"
    r"|.+:\s*the\s+moment\s+it\s+snapped"
    r"|.+\s+went\s+horribly\s+wrong"
    r")\s*$",
    re.IGNORECASE,
)
_EN_TRAILING_STOPWORDS = {
    "a", "an", "and", "as", "at", "because", "but", "by", "for", "from",
    "in", "into", "of", "on", "or", "that", "the", "then", "to", "with",
    "without",
}
_EN_MAIN_TITLE_STRONG_RE = re.compile(
    r"\b("
    r"fatal|death|dead|died|dies|killed|assassination|murder|poisoned|"
    r"burned|drowned|collapse|collapsed|split|betrayal|betrayed|disaster|"
    r"ruined|lost|no\s+proof|no\s+body|truth|secret|mistake"
    r")\b",
    re.IGNORECASE,
)
_EN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'’_-]*")


def _compact_compare_text(value: Any) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣\u0900-\u097Fぁ-んァ-ン一-龥]+", "", str(value or "")).casefold()


def _title_language(text: str) -> str:
    if _HANGUL_RE.search(text):
        return "ko"
    if re.search(r"[\u3040-\u30ff]", text):
        return "ja"
    if re.search(r"[\u0900-\u097F]", text):
        return "hi"
    return "en"


def _clean_shorts_title_base(base_title: Any) -> str:
    text = without_episode_prefix(base_title) or "Shorts"
    text = _TITLE_HASHTAG_RE.sub("", text)
    text = _SHORTS_NUMBER_HASHTAG_RE.sub("", text)
    text = _SHORTS_HASHTAG_RE.sub("", text)
    text = _SHORTS_PART_MARKER_RE.sub(" ", text)
    return _WHITESPACE_RE.sub(" ", text).strip(" |/-–—:·")


def _specific_title_core(text: str) -> str:
    core = _GENERIC_KO_HOOK_PREFIX_RE.sub("", text).strip(" |/-–—:·")
    core = _GENERIC_EN_HOOK_PREFIX_RE.sub("", core).strip(" |/-–—:·")
    return core or text


def _english_words(text: str) -> list[str]:
    return _EN_WORD_RE.findall(text or "")


def _english_specific_word_count(text: str) -> int:
    count = 0
    for word in _english_words(text):
        normalized = word.strip("'’_-").casefold()
        if len(normalized) >= 3 and normalized not in _EN_TRAILING_STOPWORDS:
            count += 1
    return count


def _trim_english_title(text: str, max_len: int) -> str:
    value = _WHITESPACE_RE.sub(" ", str(text or "")).strip(" |/-–—:·")
    if len(value) <= max_len:
        return value
    if max_len <= 8:
        return value[:max_len].rstrip(" |/-–—:·,.;!?")

    window = value[: max_len + 1]
    cut_at = -1
    for pattern in (r"\s+[|/:–—-]\s*", r"[,:;]\s+", r"\s+"):
        matches = list(re.finditer(pattern, window))
        if matches:
            candidate = matches[-1].start()
            if candidate >= max(18, int(max_len * 0.55)):
                cut_at = candidate
                break
    if cut_at <= 0:
        cut_at = max_len
    trimmed = value[:cut_at].rstrip(" |/-–—:·,.;!?")
    while True:
        words = _english_words(trimmed)
        if not words:
            break
        last = words[-1].strip("'’_-").casefold()
        if last not in _EN_TRAILING_STOPWORDS:
            break
        trimmed = trimmed[: trimmed.rfind(words[-1])].rstrip(" |/-–—:·,.;!?")
    return trimmed or value[:max_len].rstrip(" |/-–—:·,.;!?")


def _english_context_core(context: str) -> str:
    value = _specific_title_core(_clean_shorts_title_base(context))
    if not value:
        return ""
    for marker in (":", " - ", " — ", " – "):
        if marker in value:
            left, right = [part.strip(" |/-–—:·") for part in value.split(marker, 1)]
            if (
                right
                and _EN_MAIN_TITLE_STRONG_RE.search(right)
                and not _EN_MAIN_TITLE_STRONG_RE.search(left)
                and _english_specific_word_count(right) >= 2
            ):
                value = right
                break
            if _english_specific_word_count(left) >= 2:
                value = left
                break
    for marker in (" That ", " Which "):
        if marker in value:
            left = value.split(marker, 1)[0].strip(" |/-–—:·")
            if _english_specific_word_count(left) >= 2:
                value = left
                break
    return _trim_english_title(value, 52)


def _is_generic_english_shorts_title(text: str) -> bool:
    value = _WHITESPACE_RE.sub(" ", text or "").strip(" |/-–—:·")
    if not value:
        return True
    if _GENERIC_EN_SHORTS_TITLE_RE.match(value):
        return True
    words = _english_words(value)
    if len(words) <= 2 or _english_specific_word_count(value) < 2:
        return True
    last = words[-1].strip("'’_-").casefold()
    return last in _EN_TRAILING_STOPWORDS


def _english_shorts_title_base(text: str, idx: int, context: str = "") -> str:
    context_core = _english_context_core(context)
    if _is_generic_english_shorts_title(text) and context_core:
        core = context_core
        templates = [
            "{core}: the fatal turn",
            "{core}: the moment it broke",
            "{core}: no way back",
            "The brutal truth about {core}",
            "{core}: disaster in seconds",
            "Why {core} collapsed",
        ]
        return _trim_english_title(templates[(idx - 1) % len(templates)].format(core=core), 72)
    if context_core and not _EN_MAIN_TITLE_STRONG_RE.search(text):
        core = context_core
        templates = [
            "{core}: the fatal turn",
            "The mistake inside {core}",
            "{core}: how it collapsed",
            "The cost of {core}",
        ]
        return _trim_english_title(templates[(idx - 1) % len(templates)].format(core=core), 72)
    if len(text) > 72 and context_core:
        return context_core
    return _trim_english_title(text, 72)


def _hooked_shorts_title_base(base_title: Any, index: Any = None, context_title: Any = None) -> str:
    text = _clean_shorts_title_base(base_title)
    lang = _title_language(text)
    try:
        idx = max(1, int(index or 1))
    except (TypeError, ValueError):
        idx = 1
    if lang == "en":
        return _english_shorts_title_base(text, idx, _clean_shorts_title_base(context_title) if context_title else "")
    return text


def _first_title_variant(text: str) -> str:
    parts = [p.strip() for p in text.split("|") if p.strip()]
    if not parts:
        return text
    for part in parts:
        cleaned = _EP_MARKER_RE.sub(" ", part).strip(" |/-–—:·")
        if cleaned:
            return part
    return parts[0]


def coerce_episode_number(value: Any) -> Optional[int]:
    try:
        number = int(value)
    except (TypeError, ValueError):
        text = str(value or "")
        match = re.search(r"(?:episode|ep)\.?\s*0*(\d{1,4})", text, re.IGNORECASE)
        if not match:
            return None
        try:
            number = int(match.group(1))
        except (TypeError, ValueError):
            return None
    return number if number > 0 else None


def episode_label(value: Any) -> str:
    number = coerce_episode_number(value)
    return f"EP.{number:02d}" if number else ""


def with_episode_prefix(title: Any, episode_number: Any) -> str:
    text = str(title or "").strip()
    prefix = episode_label(episode_number)
    if not prefix:
        return text
    text = _EP_PREFIX_RE.sub("", text, count=1).strip()
    text = _EPISODE_PREFIX_RE.sub("", text, count=1).strip()
    text = _first_title_variant(text)
    previous = None
    while previous != text:
        previous = text
        text = _EP_PIPE_TAIL_RE.sub("", text).strip()
        text = _EP_TAIL_RE.sub("", text).strip()
        text = _EP_MARKER_RE.sub(" ", text).strip()
    text = _WHITESPACE_RE.sub(" ", text).strip(" |/-–—:·")
    return f"{text} {prefix}".strip()


def _strong_english_main_title(base_title: Any, *, max_len: int = 92) -> str:
    text = without_episode_prefix(base_title)
    text = _TITLE_HASHTAG_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text).strip(" |/-–—:·")
    if not text:
        return "The Story That Went Wrong"

    lower = text.casefold()
    candidates: list[str] = []

    if "peace" in lower and "england" in lower:
        candidates.append("The Peace That Lost England")
    if "death" in lower and "empire" in lower:
        candidates.append("The Death That Split an Empire")
    if "assassination" in lower and "rasputin" in lower:
        candidates.append("Rasputin's Assassination: The Night He Wouldn't Die")
    if "poison" in lower and "progress" in lower:
        candidates.append("The Fatal Choice That Poisoned Progress")
    if "burn" in lower and "alive" in lower:
        candidates.append("The King Who Burned Alive")
    if "drown" in lower and "emperor" in lower:
        candidates.append("The Emperor Who Drowned in a River")
    if "fatal" in lower and "raid" in lower and "empire" in lower:
        candidates.append("The Fatal Raid That Broke an Empire")

    if _EN_MAIN_TITLE_STRONG_RE.search(text):
        candidates.append(text)
    else:
        core = _trim_english_title(text, 54)
        candidates.extend([
            f"{core}: The Shocking Turn",
            f"{core}: What Went Wrong",
        ])

    for candidate in candidates:
        candidate = _trim_english_title(candidate, max_len)
        if candidate and _english_specific_word_count(candidate) >= 3:
            return candidate
    return _trim_english_title(text, max_len)


def strong_main_upload_title(
    title: Any,
    episode_number: Any = None,
    *,
    max_len: int = 100,
) -> str:
    """Build a stronger factual long-form upload title."""
    lang = _title_language(str(title or ""))
    prefix = episode_label(episode_number)
    reserve = len(prefix) + 1 if prefix else 0
    max_body_len = max(20, int(max_len or 100) - reserve)
    if lang == "en":
        body = _strong_english_main_title(title, max_len=max_body_len)
    else:
        body = without_episode_prefix(title) or str(title or "").strip() or "Untitled"
        body = body[:max_body_len].rstrip(" |/-–—:·")
    return with_episode_prefix(body, episode_number)


def without_episode_prefix(title: Any) -> str:
    """Remove visual episode markers for contexts that must not show EP numbers."""
    text = str(title or "").strip()
    text = _EP_PREFIX_RE.sub("", text, count=1).strip()
    text = _EPISODE_PREFIX_RE.sub("", text, count=1).strip()
    text = _first_title_variant(text)
    previous = None
    while previous != text:
        previous = text
        text = _EP_PIPE_TAIL_RE.sub("", text).strip()
        text = _EP_TAIL_RE.sub("", text).strip()
        text = _EP_MARKER_RE.sub(" ", text).strip()
    return _WHITESPACE_RE.sub(" ", text).strip(" |/-–—:·")


def _clean_shorts_title_hashtags(values: Iterable[Any] | None, *, title_text: Any = "") -> list[str]:
    out: list[str] = []
    seen: set[str] = {"#shorts"}
    title_compact = _compact_compare_text(title_text)
    for raw in values or []:
        tag = str(raw or "").strip()
        if not tag:
            continue
        tag = tag if tag.startswith("#") else f"#{tag}"
        compact = re.sub(r"[^0-9A-Za-z가-힣\u0900-\u097Fぁ-んァ-ン一-龥#]+", "", tag)
        if not compact.startswith("#") or not _HASHTAG_TOKEN_RE.match(compact):
            continue
        if compact[1:].isdigit() or len(compact) > 20:
            continue
        body_compact = compact[1:].casefold()
        if len(body_compact) >= 8 and title_compact and body_compact in title_compact:
            continue
        key = compact.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(compact)
        if len(out) >= 3:
            break
    return out


def shorts_upload_title(
    base_title: Any,
    *,
    index: Any = None,
    total: Any = None,
    max_len: int = 100,
    recommended_hashtags: Iterable[Any] | None = None,
    context_title: Any = None,
) -> str:
    """Build a YouTube Shorts title without part numbers or numeric hashtags."""
    text = _hooked_shorts_title_base(base_title, index=index, context_title=context_title)
    tags = _clean_shorts_title_hashtags(recommended_hashtags, title_text=text)
    suffix_parts = ["#Shorts", *tags]
    max_len_i = max(20, int(max_len or 100))
    suffix = " " + " ".join(suffix_parts)
    while tags and max_len_i - len(suffix) < 30:
        tags.pop()
        suffix_parts = ["#Shorts", *tags]
        suffix = " " + " ".join(suffix_parts)
    while tags and len(text) + len(suffix) > max_len_i:
        tags.pop()
        suffix_parts = ["#Shorts", *tags]
        suffix = " " + " ".join(suffix_parts)
    max_base_len = max(1, max_len_i - len(suffix))
    if len(text) > max_base_len:
        if _title_language(text) == "en":
            text = _trim_english_title(text, max_base_len)
        else:
            text = text[:max_base_len].rstrip(" |/-–—:·")
    return f"{text}{suffix}".strip()


def script_title_for_language(
    *,
    generated_title: Any,
    project_title: Any,
    topic: Any,
    episode_number: Any,
    language: Any,
    first_narration: Any = None,
) -> str:
    lang = str(language or "ko").strip().lower()
    if lang in {"ko", "kr", "kor", "korean"}:
        base = project_title or topic or generated_title or "Untitled"
    else:
        base = generated_title or project_title or topic or "Untitled"
        if lang in {"ja", "jp", "jpn", "japanese"} and _HANGUL_RE.search(str(base or "")):
            narration = without_episode_prefix(first_narration)
            if narration and _JAPANESE_RE.search(narration) and not _HANGUL_RE.search(narration):
                base = narration
    return with_episode_prefix(base, episode_number)
