"""YouTube description and tag normalization helpers."""
from __future__ import annotations

import re
from collections import Counter
from typing import Iterable


YOUTUBE_TAG_CHAR_BUDGET = 480
DEFAULT_MAX_TAGS = 30
EUROPEAN_HISTORY_PROFILE = "european_history"


def append_video_chapters(description: str, cuts: list[dict] | None, duration_seconds: int | float | None) -> str:
    """Append factual upload chapters from the prepared cut timeline."""
    body = str(description or "").strip()
    if re.search(r"(?m)^0{1,2}:00\s+", body) or not isinstance(cuts, list) or not cuts:
        return body
    total = max(1, len(cuts))
    try:
        duration = max(1, int(float(duration_seconds or 0)))
    except (TypeError, ValueError):
        duration = total * 4
    starts = list(range(0, total, 30))
    lines: list[str] = []
    for index in starts:
        cut = cuts[index] if isinstance(cuts[index], dict) else {}
        narration = re.sub(r"\s+", " ", str(cut.get("narration") or "")).strip()
        label = narration[:54].rstrip(" ,.;:") or f"파트 {len(lines) + 1}"
        seconds = int(round(duration * index / total))
        lines.append(f"{seconds // 60:02d}:{seconds % 60:02d} {label}")
    return f"{body}\n\n[챕터]\n" + "\n".join(lines)

_METADATA_PROFILE_ALIASES = {
    "europe": EUROPEAN_HISTORY_PROFILE,
    "europe_history": EUROPEAN_HISTORY_PROFILE,
    "european-history": EUROPEAN_HISTORY_PROFILE,
    "european_history": EUROPEAN_HISTORY_PROFILE,
    "scartography": EUROPEAN_HISTORY_PROFILE,
}
_EUROPEAN_HISTORY_BLOCKED_PHRASES = {
    "scary story",
    "horror story",
    "creepy story",
    "psychological horror",
    "unexplained mystery",
    "mystery story",
    "suspense story",
    "locked room",
    "creepy mystery",
    "nightmare story",
}
_EUROPEAN_HISTORY_DESCRIPTION_BLOCKS = {
    "if you enjoy mystery, suspense, strange incidents",
    "where the situation stops feeling ordinary",
    "what people noticed first, what they missed",
}
_EUROPEAN_HISTORY_NARRATION_BLOCKS = {
    "could not escape",
    "the shocking part is not",
    "a quiet decision began to pull",
    "fear still wore familiar clothes",
    "people did not wake up knowing",
    "it looked like rumor, pride, hunger",
}


def normalize_metadata_profile(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    return _METADATA_PROFILE_ALIASES.get(raw, raw)


def metadata_profile_from_config(config: dict | None) -> str:
    cfg = config or {}
    return normalize_metadata_profile(
        cfg.get("youtube_metadata_profile") or cfg.get("metadata_profile")
    )


_WORD_RE = re.compile(
    r"[가-힣]{2,}|[\u0900-\u097F]{2,}|[ぁ-んァ-ン一-龥]+|"
    r"[A-Za-z][A-Za-z0-9'-]{1,}|\d{2,}"
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+|(?<=[다요죠음함까])\.\s*")
_STOPWORDS = {
    "ko": {
        "영상에서는", "배경부터", "결정적인", "장면", "그리고", "뒤에", "남은", "의미까지",
        "차근차근", "따라갑니다", "핵심", "포인트", "끝까지", "보고", "여러분은",
        "어떻게", "생각하는지", "댓글로", "남겨주세요", "이번", "영상", "이야기",
    },
    "en": {
        "this", "video", "follows", "unpacking", "background", "turning", "points",
        "details", "watch", "comments", "story", "worth", "key", "the", "and",
        "but", "for", "with", "that", "from", "into", "onto", "what", "when",
        "where", "why", "how", "who", "was", "were", "are", "is", "it", "its",
        "his", "her", "she", "he", "they", "them", "their", "you", "your",
        "young", "first", "looks", "like", "begins", "began", "toward", "behind",
        "every", "thing", "something", "nothing", "again", "still", "then", "than",
        "one", "two", "three", "episode",
    },
    "ja": {
        "この", "その", "あの", "そして", "しかし", "という", "ため", "から",
        "まで", "まだ", "だけ", "こと", "もの", "よう", "です", "でした",
        "ます", "ました", "います", "いました", "前回", "今回", "皆さん",
        "こんにちは", "時間", "お話", "けれど", "けれども", "本編", "本編は",
        "とはいえ", "ところが", "でも", "つぎに",
    },
}
_GENERIC_TAGS = {
    "\ud568\uaed8", "\uc788\uc5c8\uc8e0", "\uadf8\ub7f0\ub370", "\ud1b5\uc9f8\ub85c",
    "\ub9dd\ud55c", "\uc5b4\ub514\uc11c", "\ub2e4\uc2dc", "\uc2dc\uc791\ub410\uc744\uae4c",
    "\uc65c\ub294", "\uc65c\uc758", "\uc655\uc871\uacfc", "\ubc14\ub2e4\ub97c", "\ud568\ub300\uac00",
}
_SHORTS_TITLE_HASHTAG_BLOCK_RE = re.compile(
    r"(결말을바꿔버린|운명을바꾼|판을뒤집은|이장면|진짜이유|"
    r"momentit|choice|ruinedeverything|uglytruth|horriblywrong)",
    re.IGNORECASE,
)
_SHORTS_TITLE_WORD_BLOCK = {
    "ko": {
        "반격의", "고구려의", "낙랑공주의", "비극의", "사랑의", "장면", "순간", "진짜", "결말",
        "엎어진", "흔들린", "바꿔버린", "바꾼", "숨겨진", "놓친", "끝났습니다", "터졌습니다",
    },
    "en": {
        "wall", "price", "choice", "moment", "truth", "mistake", "story", "deal",
        "forced", "look", "give", "away", "longing", "said", "most", "like", "great",
        "make", "made", "take", "took", "come", "came", "goes", "went",
    },
    "ja": {"瞬間", "本当", "選択"},
    "hi": set(),
}


def _shorts_title_hashtag_too_noisy(body: str, *, title: str, topic: str, lang: str) -> bool:
    compact = re.sub(r"[^0-9A-Za-z가-힣\u0900-\u097Fぁ-んァ-ン一-龥]+", "", body or "")
    if not compact:
        return True
    if compact.casefold() in {"ep", "episode", "episodes"}:
        return True
    if _SHORTS_TITLE_HASHTAG_BLOCK_RE.search(compact):
        return True
    if re.search(r"[가-힣ぁ-んァ-ン一-龥]", compact):
        if len(compact) > 8:
            return True
    elif len(compact) > 16:
        return True
    title_compact = re.sub(r"[^0-9A-Za-z가-힣\u0900-\u097Fぁ-んァ-ン一-龥]+", "", title or "").casefold()
    topic_compact = re.sub(r"[^0-9A-Za-z가-힣\u0900-\u097Fぁ-んァ-ン一-龥]+", "", topic or "").casefold()
    key = compact.casefold()
    if len(key) >= 8 and title_compact and key in title_compact:
        return True
    if lang == "ko" and key in {"역사쇼츠", "역사이야기"}:
        return False
    if topic_compact and len(key) >= 10 and key == topic_compact:
        return True
    if key in {w.casefold() for w in _SHORTS_TITLE_WORD_BLOCK.get(lang, set())}:
        return True
    return False


def _shorts_title_priority_hashtags(*, title: str, topic: str, narration: str, lang: str, max_count: int) -> list[str]:
    source = " ".join([topic or "", title or "", narration[:800] or ""])
    out: list[str] = []
    seen: set[str] = set()
    stop = _STOPWORDS.get(lang, set()) | _SHORTS_TITLE_WORD_BLOCK.get(lang, set())
    for raw in _tokens(source):
        word = str(raw or "").strip()
        if lang == "ko":
            word = re.sub(r"(에게|으로|에서|부터|까지|은|는|이|가|을|를|의|와|과|에|도|만|로)$", "", word)
            if not (2 <= len(word) <= 5):
                continue
        elif lang == "ja":
            if not (2 <= len(word) <= 8):
                continue
        elif lang == "hi":
            if not (3 <= len(word) <= 14):
                continue
        else:
            if not (4 <= len(word) <= 14):
                continue
        if word in stop or word.lower() in stop or word.casefold() in {w.casefold() for w in stop}:
            continue
        tag = _compact_hashtag(word, max_len=12 if lang in {"ko", "ja"} else 16)
        if not tag:
            continue
        body = tag.lstrip("#")
        if _shorts_title_hashtag_too_noisy(body, title=title, topic=topic, lang=lang):
            continue
        key = tag.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(tag)
        if len(out) >= max_count:
            break
    return out


def detect_metadata_language(text: str, fallback: str = "ko") -> str:
    hangul = sum(1 for ch in text if "\uac00" <= ch <= "\ud7a3")
    devanagari = sum(1 for ch in text if "\u0900" <= ch <= "\u097f")
    latin = sum(1 for ch in text if ("A" <= ch <= "Z") or ("a" <= ch <= "z"))
    kana = sum(1 for ch in text if "\u3040" <= ch <= "\u30ff")
    if kana >= 6:
        return "ja"
    if devanagari >= 6:
        return "hi"
    if hangul >= latin:
        return "ko"
    return "en" if latin else fallback


def _strip_hash(tag: str) -> str:
    return str(tag or "").strip().lstrip("#").strip()


def clean_tags(tags: Iterable[str], max_tags: int = DEFAULT_MAX_TAGS) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    total_chars = 0
    for raw in tags:
        tag = _strip_hash(raw)
        tag = re.sub(r"\s+", " ", tag)
        tag = re.sub(r"(은|는|을|를|에서|에게|으로|와|과)$", "", tag)
        if not tag or len(tag) > 30:
            continue
        if tag[0].isdigit():
            continue
        if "?" in tag or not _WORD_RE.search(tag):
            continue
        if tag.isdigit():
            continue
        if tag in _GENERIC_TAGS or any(part in _GENERIC_TAGS for part in tag.split()):
            continue
        if tag.endswith(("습니다", "는데요")) or tag in {"그래서", "있던"}:
            continue
        if tag.upper().startswith("EP.") or tag.upper() == "EP" or tag.upper().startswith("EP "):
            continue
        if any(noisy in tag for noisy in ("지난 시간", "오늘", "재미있", "아름다운 우리", "역공입니다")):
            continue
        key = tag.casefold()
        if key in seen:
            continue
        next_total = total_chars + len(tag)
        if out:
            next_total += 1  # YouTube counts comma separators in the 500 char tag budget.
        if next_total > YOUTUBE_TAG_CHAR_BUDGET:
            break
        seen.add(key)
        out.append(tag)
        total_chars = next_total
        if len(out) >= max_tags:
            break
    return out


def _tokens(*texts: str) -> list[str]:
    words: list[str] = []
    for text in texts:
        words.extend(_WORD_RE.findall(str(text or "")))
    return words


def _phrase_candidates(
    title: str,
    topic: str,
    narration: str,
    language: str | None = None,
) -> list[str]:
    candidates: list[str] = []
    for source in (title, topic):
        source = str(source or "").strip()
        if source and len(source) <= 30:
            candidates.append(source)
        parts = [p.strip(" -:|,./[]()") for p in re.split(r"[:|,\-·/]", source) if p.strip()]
        candidates.extend(p for p in parts if 2 <= len(p) <= 30)

    lang = (language or detect_metadata_language(" ".join([title, topic, narration]))).lower()
    stop = _STOPWORDS.get(lang, set())
    token_sources = (title, topic) if lang == "ja" else (title, topic, narration[:2500])
    words = [
        w for w in _tokens(*token_sources)
        if w not in stop and w.lower() not in stop and len(w) >= 3
    ]
    counter = Counter(w for w in words if len(w) >= 2 and w.upper() != "EP")
    candidates.extend(word for word, _ in counter.most_common(30))

    # Add adjacent word pairs for more specific discoverability.
    for a, b in zip(words, words[1:]) if lang != "ja" else ():
        if a.isdigit() or b.isdigit() or a.upper() == "EP" or b.upper() == "EP":
            continue
        if a in _GENERIC_TAGS or b in _GENERIC_TAGS:
            continue
        phrase = f"{a} {b}"
        if 4 <= len(phrase) <= 30:
            candidates.append(phrase)
    return candidates


def _european_history_phrase_candidates(title: str, topic: str) -> list[str]:
    stop = _STOPWORDS["en"] | {
        "about", "after", "before", "between", "during", "through",
        "history", "european", "europe", "explained", "documentary",
    }
    candidates: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        phrase = re.sub(r"\s+", " ", str(value or "")).strip(" -:|,./[]()")
        phrase = re.sub(r"\b(?:EP|Episode)\.?\s*\d+\b", "", phrase, flags=re.IGNORECASE)
        phrase = re.sub(r"\s+", " ", phrase).strip(" -:|,./[]()")
        if not (3 <= len(phrase) <= 30):
            return
        if phrase.casefold() in stop:
            return
        if " " not in phrase and phrase.casefold() in {
            "creation", "myth", "war", "king", "queen", "empire", "kingdom",
        }:
            return
        key = phrase.casefold()
        if key not in seen:
            seen.add(key)
            candidates.append(phrase)

    for source in dict.fromkeys([str(title or "").strip(), str(topic or "").strip()]):
        if not source:
            continue
        for chunk in re.split(r"[:|,/\u2013\u2014]", source):
            chunk = chunk.strip()
            if not chunk:
                continue
            add(chunk)
            words = [
                word for word in _tokens(chunk)
                if len(word) >= 4 and word.casefold() not in stop
            ]
            for word in words:
                add(word)
            for size in (2, 3):
                for start in range(0, max(0, len(words) - size + 1)):
                    add(" ".join(words[start:start + size]))
    return candidates


def _european_history_tag_allowed(value: str) -> bool:
    lowered = re.sub(r"\s+", " ", str(value or "")).strip().casefold()
    return bool(lowered) and not any(
        blocked in lowered for blocked in _EUROPEAN_HISTORY_BLOCKED_PHRASES
    )


def expand_tags(
    base_tags: Iterable[str],
    *,
    title: str = "",
    topic: str = "",
    narration: str = "",
    language: str | None = None,
    max_tags: int = DEFAULT_MAX_TAGS,
    shorts: bool = False,
    profile: str | None = None,
) -> list[str]:
    lang = (language or detect_metadata_language(" ".join([title, topic, narration]))).lower()
    profile_id = normalize_metadata_profile(profile)
    if profile_id == EUROPEAN_HISTORY_PROFILE:
        broad = [
            "European history",
            "history of Europe",
            "European history documentary",
            "history documentary",
            "historical borders",
            "history explained",
        ]
        contextual: list[str] = []
        subject_probe = f"{title} {topic}".casefold()
        if any(term in subject_probe for term in (
            "ancient", "proto-", "myth", "greek", "roman", "celt", "viking",
        )):
            contextual.extend(["ancient Europe", "European mythology"])
        if any(term in subject_probe for term in (
            "medieval", "feudal", "crusade", "caroling", "norman",
        )):
            contextual.append("medieval Europe")
        if any(term in subject_probe for term in (
            "renaissance", "reformation", "early modern", "enlightenment",
        )):
            contextual.append("early modern Europe")
        candidates: list[str] = []
        candidates.extend(base_tags or [])
        candidates.extend(_european_history_phrase_candidates(title, topic))
        candidates.extend(contextual)
        candidates.extend(broad)
        if shorts:
            candidates.extend(["history shorts", "European history shorts"])
        return clean_tags(
            [tag for tag in candidates if _european_history_tag_allowed(tag)],
            max_tags=min(max(1, int(max_tags or 1)), 12),
        )

    broad = {
        "ko": [
            "역사", "한국사", "세계사", "역사이야기", "역사다큐", "지식", "교양",
            "인문학", "사건", "인물", "전쟁사", "고대사", "문화사", "10분역공",
            "역사해설", "역사지식", "역사속이야기", "다큐멘터리", "교양채널",
        ],
        "ja": [
            "歴史", "日本史", "歴史解説", "教養", "知識", "古代史",
            "ドキュメンタリー",
        ],
        "en": [
            "history", "documentary", "explained", "education", "facts",
            "story", "ancient history", "world history", "inventions",
            "science history", "mystery", "biography", "true story",
            "storytelling", "dark story", "scary story", "suspense",
            "unexplained mystery", "horror story", "creepy story",
        ],
        "hi": [
            "Hindi", "India", "history", "documentary", "explained",
            "education", "facts", "mystery", "biography", "true story",
            "Indian history", "Hindi documentary",
        ],
    }.get(lang, [])
    lower_blob = " ".join([title, topic, narration]).lower()
    if lang == "en":
        if any(word in lower_blob for word in ("locked", "cctv", "caller", "footsteps", "room", "door", "house")):
            broad.extend([
                "psychological horror", "mystery story", "suspense story",
                "locked room", "creepy mystery", "nightmare story",
            ])
        if any(word in lower_blob for word in ("invent", "science", "engineer", "experiment")):
            broad.extend(["invention story", "science documentary", "engineering history"])
    elif lang == "ko":
        if any(word in lower_blob for word in ("백제", "신라", "고구려", "고조선", "전쟁", "왕")):
            broad.extend(["한국고대사", "삼국시대", "왕조사", "전쟁이야기", "역사인물"])
    elif lang == "ja":
        if any(word in lower_blob for word in ("神話", "古事記", "日本書紀")):
            broad.extend(["日本神話", "古事記", "日本書紀"])
        if any(word in lower_blob for word in ("戦争", "合戦", "戦い", "軍事")):
            broad.append("戦争史")
        if any(word in lower_blob for word in ("文化", "芸術", "風俗", "生活史")):
            broad.append("文化史")
    shorts_tags = {
        "ko": ["Shorts", "쇼츠", "역사쇼츠"],
        "ja": ["Shorts", "ショート"],
        "en": ["Shorts", "YouTube Shorts"],
    }.get(lang, ["Shorts"])

    candidates: list[str] = []
    candidates.extend(base_tags or [])
    candidates.extend(broad)
    candidates.extend(_phrase_candidates(title, topic, narration, lang))
    if shorts:
        candidates.extend(shorts_tags)
    return clean_tags(candidates, max_tags=max_tags)


def _sentences(text: str, limit: int = 8) -> list[str]:
    raw = re.split(r"[\r\n]+|(?<=[.!?。！？])\s+", str(text or ""))
    out: list[str] = []
    for item in raw:
        line = item.strip(" -•\t")
        if 12 <= len(line) <= 180:
            out.append(line)
        if len(out) >= limit:
            break
    return out


def _compact_hashtag(tag: str, *, max_len: int = 24) -> str:
    compact = re.sub(r"[^0-9A-Za-z가-힣\u0900-\u097Fぁ-んァ-ン一-龥]+", "", str(tag or ""))
    compact = re.sub(r"(?:EP|Episode|에피소드)0*\d+$", "", compact, flags=re.IGNORECASE)
    if compact.casefold() in {"ep", "episode", "episodes"}:
        return ""
    if 2 <= len(compact) <= max_len and not compact.isdigit():
        return f"#{compact}"
    return ""


def recommended_hashtags(
    *,
    title: str = "",
    topic: str = "",
    narration: str = "",
    language: str | None = None,
    shorts: bool = False,
    max_count: int = 14,
    max_len: int = 24,
    profile: str | None = None,
) -> list[str]:
    lang = (language or detect_metadata_language(" ".join([title, topic, narration]))).lower()
    profile_id = normalize_metadata_profile(profile)
    candidates: list[str] = []
    if profile_id == EUROPEAN_HISTORY_PROFILE:
        candidates.extend(_european_history_phrase_candidates(title, topic))
    else:
        candidates.extend(_phrase_candidates(title, topic, narration, lang))
    candidates.extend(expand_tags(
        [],
        title=title,
        topic=topic,
        narration=narration,
        language=lang,
        max_tags=max(24, max_count * 2),
        shorts=shorts,
        profile=profile_id,
    ))
    out: list[str] = []
    seen: set[str] = set()
    for tag in candidates:
        hashtag = _compact_hashtag(tag, max_len=max_len)
        if not hashtag:
            continue
        key = hashtag.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(hashtag)
        if len(out) >= max_count:
            break
    return out


def recommended_shorts_title_hashtags(
    *,
    title: str = "",
    topic: str = "",
    narration: str = "",
    language: str | None = None,
    max_count: int = 3,
    profile: str | None = None,
) -> list[str]:
    blocked = {"#shorts", "#쇼츠", "#youtubeshorts", "#ショート"}
    lang = (language or detect_metadata_language(" ".join([title, topic, narration]))).lower()
    profile_id = normalize_metadata_profile(profile)
    priority = []
    if profile_id != EUROPEAN_HISTORY_PROFILE:
        priority = _shorts_title_priority_hashtags(
            title=title,
            topic="" if lang == "ja" else topic,
            narration="" if lang == "ja" else narration,
            lang=lang,
            max_count=max_count,
        )
    tags = []
    if lang != "ja":
        tags = recommended_hashtags(
            title=title,
            topic=topic,
            narration=narration,
            language=lang,
            shorts=True,
            max_count=max_count + 4,
            max_len=16,
            profile=profile_id,
        )
    out: list[str] = []
    seen: set[str] = set()
    for tag in [*priority, *tags]:
        if tag.casefold() in blocked:
            continue
        body = tag.lstrip("#")
        if _shorts_title_hashtag_too_noisy(body, title=title, topic=topic, lang=lang):
            continue
        if lang == "ja" and re.search(r"[가-힣\u0900-\u097F]", body):
            continue
        if lang == "ko" and re.search(r"[\u3040-\u30ff\u0900-\u097F]", body):
            continue
        if lang == "en" and re.search(r"[가-힣\u0900-\u097F\u3040-\u30ff]", body):
            continue
        if lang == "hi" and re.search(r"[가-힣\u3040-\u30ff]", body):
            continue
        key = tag.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(tag)
        if len(out) >= max_count:
            break
    fallback_by_lang = {
        "ja": ["#歴史", "#日本史", "#歴史解説"],
        "ko": ["#역사", "#역사쇼츠", "#역사이야기"],
        "en": ["#history", "#historyshorts", "#documentary"],
        "hi": ["#history", "#Hindi", "#documentary"],
    }
    fallback = fallback_by_lang.get(lang, ["#history"])
    japanese_context = " ".join([title, topic, narration])
    if lang == "ja" and any(
        word in japanese_context
        for word in ("神話", "女神", "アマテラス", "ツクヨミ", "ウケモチ", "古事記")
    ):
        fallback = ["#日本神話", "#古事記", "#日本史"]
    if profile_id == EUROPEAN_HISTORY_PROFILE:
        fallback = ["#EuropeanHistory", "#HistoryShorts", "#Scartography"]
    for tag in fallback:
        if len(out) >= max_count:
            break
        key = tag.casefold()
        if key in blocked or key in seen:
            continue
        seen.add(key)
        out.append(tag)
    return out


def _hashtags(
    title: str,
    topic: str,
    narration: str,
    lang: str,
    *,
    shorts: bool = False,
    max_count: int = 14,
    profile: str | None = None,
) -> str:
    return " ".join(recommended_hashtags(
        title=title,
        topic=topic,
        narration=narration,
        language=lang,
        shorts=shorts,
        max_count=max_count,
        profile=profile,
    ))


def _hashtag_block(
    title: str,
    topic: str,
    narration: str,
    lang: str,
    *,
    shorts: bool = False,
    profile: str | None = None,
) -> str:
    profile_id = normalize_metadata_profile(profile)
    max_count = 5 if profile_id == EUROPEAN_HISTORY_PROFILE else (18 if shorts else 16)
    tags = _hashtags(
        title,
        topic,
        narration,
        lang,
        shorts=shorts,
        max_count=max_count,
        profile=profile_id,
    )
    if not tags:
        return ""
    if profile_id == EUROPEAN_HISTORY_PROFILE:
        return tags
    if lang == "hi":
        label = "सुझाए गए हैशटैग:"
    elif lang == "en":
        label = "Recommended hashtags:"
    elif lang == "ja":
        label = "おすすめハッシュタグ:"
    else:
        label = "추천 해시태그:"
    return f"{label}\n{tags}"


def _european_history_facts(
    narration: str,
    subject: str,
    limit: int = 5,
) -> list[str]:
    subject_terms = {
        term.casefold() for term in _tokens(subject)
        if len(term) >= 4 and term.casefold() not in _STOPWORDS["en"]
    }
    facts: list[str] = []
    for sentence in _sentences(narration, limit=16):
        lowered = sentence.casefold()
        if any(blocked in lowered for blocked in _EUROPEAN_HISTORY_NARRATION_BLOCKS):
            continue
        if subject_terms and not any(term in lowered for term in subject_terms):
            if not re.search(r"\b(?:BCE|CE|BC|AD|\d{3,4})\b", sentence, re.IGNORECASE):
                continue
        facts.append(sentence)
        if len(facts) >= limit:
            break
    return facts


def _format_european_history_description(
    description: str,
    *,
    title: str,
    topic: str,
    narration: str,
    shorts: bool,
) -> str:
    text = re.sub(r"\n{3,}", "\n\n", str(description or "").strip())
    subject = str(topic or title or "European history").strip()
    if text.casefold() in {str(title or "").strip().casefold(), subject.casefold()}:
        text = ""
    facts = _european_history_facts(
        narration,
        subject,
        limit=3 if shorts else 5,
    )
    hashtag_block = _hashtag_block(
        title,
        subject,
        narration,
        "en",
        shorts=shorts,
        profile=EUROPEAN_HISTORY_PROFILE,
    )
    accessibility = (
        "English narration. Subtitles available in English, French, Spanish, and German."
    )

    if shorts:
        lead = text or subject
        parts = [
            lead,
            (
                "A focused moment from Scartography's European history series, "
                "placed in its historical context."
            ),
        ]
        if facts:
            parts.extend(["Historical context:", "\n".join(f"- {fact}" for fact in facts)])
        parts.extend([accessibility, hashtag_block])
        return "\n\n".join(part for part in parts if part).strip()[:5000]

    lead = text or (
        f"This Scartography episode examines {subject} in its historical context, "
        "tracing the people, beliefs, evidence, and consequences behind the subject."
    )
    parts = [lead]
    if facts:
        parts.extend(["In this episode:", "\n".join(f"- {fact}" for fact in facts)])
    parts.extend([
        (
            "Scartography follows the myths, rulers, wars, revolutions, and borders "
            "that shaped Europe."
        ),
        accessibility,
        hashtag_block,
    ])
    return "\n\n".join(part for part in parts if part).strip()[:5000]


def validate_metadata_for_profile(
    *,
    title: str,
    description: str,
    tags: Iterable[str],
    profile: str | None,
) -> None:
    profile_id = normalize_metadata_profile(profile)
    if profile_id != EUROPEAN_HISTORY_PROFILE:
        return
    if not str(title or "").strip():
        raise ValueError("European-history YouTube title is empty")
    if not str(description or "").strip():
        raise ValueError("European-history YouTube description is empty")
    if re.search(r"[\uac00-\ud7a3]", f"{title}\n{description}"):
        raise ValueError("European-history default metadata must be English")
    tag_list = [str(tag or "") for tag in tags]
    joined_tags = " | ".join(tag_list)
    probe = f"{description}\n{joined_tags}".casefold()
    blocked = sorted(
        phrase for phrase in _EUROPEAN_HISTORY_BLOCKED_PHRASES
        if phrase in probe
    )
    blocked.extend(
        phrase for phrase in sorted(_EUROPEAN_HISTORY_DESCRIPTION_BLOCKS)
        if phrase in probe
    )
    if blocked:
        raise ValueError(
            "European-history metadata contains unrelated generic terms: "
            + ", ".join(dict.fromkeys(blocked))
        )
    if len(tag_list) > 12:
        raise ValueError("European-history metadata exceeds the 12-tag limit")


def format_description(
    description: str,
    *,
    title: str = "",
    topic: str = "",
    narration: str = "",
    language: str | None = None,
    shorts: bool = False,
    profile: str | None = None,
) -> str:
    text = str(description or "").strip()
    lang = (language or detect_metadata_language(" ".join([title, topic, text, narration]))).lower()
    profile_id = normalize_metadata_profile(profile)
    if profile_id == EUROPEAN_HISTORY_PROFILE:
        return _format_european_history_description(
            text,
            title=title,
            topic=topic,
            narration=narration,
            shorts=shorts,
        )
    facts = _sentences(narration, 8)
    if shorts:
        marker = "#Shorts" if lang != "ko" else "#Shorts #쇼츠"
        seed = text or topic or title
        hashtags = _hashtag_block(title, topic, narration, lang, shorts=True)
        if lang == "hi":
            body = "\n\n".join([
                seed,
                f"{topic or title} से जुड़ा यह छोटा हिस्सा कहानी के उस मोड़ पर ध्यान देता है जहां सब कुछ बदलना शुरू होता है.",
                "पूरी पृष्ठभूमि, घटनाक्रम और असर समझने के लिए मुख्य एपिसोड देखें.",
                marker,
                hashtags,
            ])
        elif lang == "en":
            body = "\n\n".join([
                seed,
                f"A condensed moment from {topic or title}, focused on the turn that makes the full story worth watching.",
                "Watch the main episode for the full setup, timeline, and aftermath.",
                marker,
                hashtags,
            ])
        elif lang == "ja":
            body = "\n\n".join([
                seed,
                f"「{topic or title}」から、流れが変わる場面だけを短くまとめました。",
                "本編では背景、経緯、その後の意味まで詳しく追っています。",
                marker,
                hashtags,
            ])
        else:
            body = "\n\n".join([
                seed,
                f"{topic or title} 중에서 흐름이 확 바뀌는 장면만 짧게 잘라 담았습니다.",
                "본편에서는 배경, 전개, 이후에 남은 의미까지 더 자세히 따라갑니다.",
                "짧은 장면이지만 본편의 핵심 감정, 갈등, 반전 포인트가 드러나도록 골라낸 클립입니다.",
                marker,
                hashtags,
            ])
        return body.strip()[:5000]

    # Normalize line breaks first: blank lines between paragraphs, single lines for bullets.
    lines = [ln.strip() for ln in text.replace("\r\n", "\n").split("\n")]
    normalized: list[str] = []
    prev_blank = False
    for line in lines:
        if not line:
            if normalized and not prev_blank:
                normalized.append("")
            prev_blank = True
            continue
        if line.startswith(("•", "-", "*")) and normalized and normalized[-1] != "":
            normalized.append("")
        normalized.append(line)
        prev_blank = False
    text = "\n".join(normalized).strip()

    if len(text) >= 1100 and "\n\n" in text and ("Key points" in text or "핵심" in text or "主な" in text):
        hashtags = _hashtag_block(title, topic, narration, lang)
        if hashtags and "#" not in text[-700:]:
            text = f"{text}\n\n{hashtags}"
        return text[:5000]

    seed = text or topic or title

    if lang == "hi":
        hook = seed or title or "यह कहानी अंत तक देखने लायक है."
        summary = (
            f"इस एपिसोड में हम {topic or title} को शुरुआत से उस मोड़ तक समझते हैं "
            "जहां कहानी साधारण नहीं रह जाती. मकसद सिर्फ घटना सुनाना नहीं, बल्कि "
            "समय, कारण, फैसले और नतीजों को साफ तरीके से जोड़ना है."
        )
        context = (
            "कहानी को कदम दर कदम रखा गया है: पहले लोगों ने क्या देखा, कौन सी बातें छूट गईं, "
            "कौन से छोटे संकेत बाद में महत्वपूर्ण निकले, और अंत पूरी समयरेखा के बाद अलग क्यों लगता है."
        )
        why = (
            "अगर आपको रहस्य, इतिहास, अजीब घटनाएं, निर्णायक मोड़ या डॉक्यूमेंट्री शैली की कहानियां पसंद हैं, "
            "तो यह एपिसोड आसान गति में पूरी तस्वीर समझाने के लिए बनाया गया है."
        )
        bullets = facts[:6] or [topic or title]
        closing = "अंत तक देखें और अपनी राय बताएं: आपको कौन सा विवरण सबसे महत्वपूर्ण लगा?"
        bullet_title = "मुख्य बिंदु:"
        extra_title = "यह क्यों मायने रखता है:"
    elif lang == "en":
        hook = seed or title or "A story worth watching."
        summary = (
            f"In this episode, we follow {topic or title} from the opening setup to the moment "
            "where the situation stops feeling ordinary. The goal is not just to retell what "
            "happened, but to make the timing, motives, clues, and consequences easy to follow."
        )
        context = (
            "The story is built step by step: what people noticed first, what they missed, "
            "which small details mattered, and why the ending feels different once the whole "
            "timeline is in view."
        )
        why = (
            "If you enjoy mystery, suspense, strange incidents, historical turning points, "
            "or tightly narrated documentary-style stories, this episode is made to be easy "
            "to watch while still giving enough context to understand the bigger picture."
        )
        bullets = facts[:6] or [topic or title]
        closing = (
            "Watch to the end, then leave your take in the comments: what detail felt most "
            "important, and what would you have done in the same situation?"
        )
        bullet_title = "Key points:"
        extra_title = "Why it matters:"
    elif lang == "ja":
        hook = seed or title or "見逃せない物語です。"
        summary = f"この動画では「{topic or title}」を、背景、転換点、後に残した意味まで順番に追います。"
        context = "表面的な出来事だけでなく、人々の選択、場所、利害関係、その後の影響までつなげて見ていきます。"
        why = "細かな場面も流さず、なぜその出来事が重要だったのかを物語の流れの中で整理します。"
        bullets = facts[:6] or [topic or title]
        closing = "最後まで見て、あなたの考えもコメントで教えてください。"
        bullet_title = "主なポイント:"
        extra_title = "見どころ:"
    else:
        hook = seed or title or "이번 이야기는 그냥 지나치기 어렵습니다."
        summary = (
            f"이 영상에서는 {topic or title}의 배경부터 결정적인 장면, 그리고 뒤에 남은 의미까지 "
            "차근차근 따라갑니다."
        )
        context = (
            "익숙한 한 줄 요약에서 멈추지 않고, 누가 움직였고 무엇이 달라졌는지, "
            "그 선택이 다음 시대에 어떤 흔적을 남겼는지까지 이어서 보겠습니다."
        )
        why = (
            "겉으로는 단순한 사건처럼 보여도, 끝까지 따라가면 인물의 선택과 상황의 흐름이 "
            "서로 어떻게 맞물렸는지 더 선명하게 보입니다."
        )
        bullets = facts[:6] or [topic or title]
        closing = "끝까지 보고, 여러분은 어떻게 생각하는지 댓글로 남겨주세요."
        bullet_title = "핵심 포인트:"
        extra_title = "왜 볼 만한가:"

    bullet_block = "\n".join(f"- {item.strip()}" for item in bullets if item.strip())
    hashtag_block = _hashtag_block(title, topic, narration, lang)
    rich_parts = [
        hook,
        summary,
        context,
        bullet_title,
        bullet_block,
        extra_title,
        why,
        closing,
    ]
    rich_probe = "\n\n".join(part for part in rich_parts if part)
    if len(rich_probe) < 950 and lang == "ko":
        rich_parts.append(
            "짧게 지나가는 장면들도 그냥 배경으로 넘기지 않고, 이야기의 흐름 안에서 왜 중요한지 "
            "살펴봅니다. 처음 보면 단순한 사건처럼 보이지만, 끝까지 따라가면 권력, 선택, 기억이 "
            "서로 어떻게 연결되는지 더 분명하게 보입니다."
        )
    elif len(rich_probe) < 950 and lang == "en":
        rich_parts.append(
            "Small details are not treated as decoration here. Each one is tied back to the "
            "larger chain of decisions, consequences, fear, memory, and cause-and-effect that "
            "shaped what happened next. The episode is paced for viewers who want a clear story, "
            "but also want enough detail to understand why the ending lands the way it does."
        )
    rich_parts.append(hashtag_block)
    rich = "\n\n".join(
        part for part in [
            *rich_parts,
        ]
        if part
    )
    return rich[:5000]
