"""YouTube description and tag normalization helpers."""
from __future__ import annotations

import re
from collections import Counter
from typing import Iterable


YOUTUBE_TAG_CHAR_BUDGET = 480
DEFAULT_MAX_TAGS = 30


_WORD_RE = re.compile(r"[가-힣]{2,}|[\u0900-\u097F]{2,}|[A-Za-z][A-Za-z0-9'-]{1,}|\d{2,}")
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
}
_GENERIC_TAGS = {
    "\ud568\uaed8", "\uc788\uc5c8\uc8e0", "\uadf8\ub7f0\ub370", "\ud1b5\uc9f8\ub85c",
    "\ub9dd\ud55c", "\uc5b4\ub514\uc11c", "\ub2e4\uc2dc", "\uc2dc\uc791\ub410\uc744\uae4c",
    "\uc65c\ub294", "\uc65c\uc758", "\uc655\uc871\uacfc", "\ubc14\ub2e4\ub97c", "\ud568\ub300\uac00",
}


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


def _phrase_candidates(title: str, topic: str, narration: str) -> list[str]:
    candidates: list[str] = []
    for source in (title, topic):
        source = str(source or "").strip()
        if source and len(source) <= 30:
            candidates.append(source)
        parts = [p.strip(" -:|,./[]()") for p in re.split(r"[:|,\-·/]", source) if p.strip()]
        candidates.extend(p for p in parts if 2 <= len(p) <= 30)

    lang = detect_metadata_language(" ".join([title, topic, narration]))
    stop = _STOPWORDS.get(lang, set())
    words = [
        w for w in _tokens(title, topic, narration[:2500])
        if w not in stop and w.lower() not in stop and len(w) >= 3
    ]
    counter = Counter(w for w in words if len(w) >= 2 and w.upper() != "EP")
    candidates.extend(word for word, _ in counter.most_common(30))

    # Add adjacent word pairs for more specific discoverability.
    for a, b in zip(words, words[1:]):
        if a.isdigit() or b.isdigit() or a.upper() == "EP" or b.upper() == "EP":
            continue
        if a in _GENERIC_TAGS or b in _GENERIC_TAGS:
            continue
        phrase = f"{a} {b}"
        if 4 <= len(phrase) <= 30:
            candidates.append(phrase)
    return candidates


def expand_tags(
    base_tags: Iterable[str],
    *,
    title: str = "",
    topic: str = "",
    narration: str = "",
    language: str | None = None,
    max_tags: int = DEFAULT_MAX_TAGS,
    shorts: bool = False,
) -> list[str]:
    lang = (language or detect_metadata_language(" ".join([title, topic, narration]))).lower()
    broad = {
        "ko": [
            "역사", "한국사", "세계사", "역사이야기", "역사다큐", "지식", "교양",
            "인문학", "사건", "인물", "전쟁사", "고대사", "문화사", "10분역공",
            "역사해설", "역사지식", "역사속이야기", "다큐멘터리", "교양채널",
        ],
        "ja": [
            "歴史", "世界史", "日本史", "歴史解説", "教養", "知識", "人物史",
            "古代史", "戦争史", "文化史", "ドキュメンタリー",
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
    shorts_tags = {
        "ko": ["Shorts", "쇼츠", "역사쇼츠"],
        "ja": ["Shorts", "ショート"],
        "en": ["Shorts", "YouTube Shorts"],
    }.get(lang, ["Shorts"])

    candidates: list[str] = []
    candidates.extend(base_tags or [])
    candidates.extend(broad)
    candidates.extend(_phrase_candidates(title, topic, narration))
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


def _hashtags(title: str, topic: str, narration: str, lang: str, *, shorts: bool = False) -> str:
    tags = expand_tags(
        [],
        title=title,
        topic=topic,
        narration=narration,
        language=lang,
        max_tags=12,
        shorts=shorts,
    )
    clean: list[str] = []
    for tag in tags:
        compact = re.sub(r"[^0-9A-Za-z가-힣\u0900-\u097Fぁ-んァ-ン一-龥]+", "", tag)
        if 2 <= len(compact) <= 24:
            clean.append(f"#{compact}")
        if len(clean) >= 10:
            break
    return " ".join(clean)


def format_description(
    description: str,
    *,
    title: str = "",
    topic: str = "",
    narration: str = "",
    language: str | None = None,
    shorts: bool = False,
) -> str:
    text = str(description or "").strip()
    lang = (language or detect_metadata_language(" ".join([title, topic, text, narration]))).lower()
    facts = _sentences(narration, 8)
    if shorts:
        marker = "#Shorts" if lang != "ko" else "#Shorts #쇼츠"
        seed = text or topic or title
        if lang == "hi":
            body = "\n\n".join([
                seed,
                f"{topic or title} से जुड़ा यह छोटा हिस्सा कहानी के उस मोड़ पर ध्यान देता है जहां सब कुछ बदलना शुरू होता है.",
                "पूरी पृष्ठभूमि, घटनाक्रम और असर समझने के लिए मुख्य एपिसोड देखें.",
                marker,
                _hashtags(title, topic, narration, lang, shorts=True),
            ])
        elif lang == "en":
            body = "\n\n".join([
                seed,
                f"A condensed moment from {topic or title}, focused on the turn that makes the full story worth watching.",
                "Watch the main episode for the full setup, timeline, and aftermath.",
                marker,
                _hashtags(title, topic, narration, lang, shorts=True),
            ])
        elif lang == "ja":
            body = "\n\n".join([
                seed,
                f"「{topic or title}」から、流れが変わる場面だけを短くまとめました。",
                "本編では背景、経緯、その後の意味まで詳しく追っています。",
                marker,
                _hashtags(title, topic, narration, lang, shorts=True),
            ])
        else:
            body = "\n\n".join([
                seed,
                f"{topic or title} 중에서 흐름이 확 바뀌는 장면만 짧게 잘라 담았습니다.",
                "본편에서는 배경, 전개, 이후에 남은 의미까지 더 자세히 따라갑니다.",
                marker,
                _hashtags(title, topic, narration, lang, shorts=True),
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
    hashtag_block = _hashtags(title, topic, narration, lang)
    rich = "\n\n".join(
        part for part in [
            hook,
            summary,
            context,
            bullet_title,
            bullet_block,
            extra_title,
            why,
            closing,
            hashtag_block,
        ]
        if part
    )
    if len(rich) < 950 and lang == "ko":
        rich += (
            "\n\n짧게 지나가는 장면들도 그냥 배경으로 넘기지 않고, 이야기의 흐름 안에서 왜 중요한지 "
            "살펴봅니다. 처음 보면 단순한 사건처럼 보이지만, 끝까지 따라가면 권력, 선택, 기억이 "
            "서로 어떻게 연결되는지 더 분명하게 보입니다."
        )
    elif len(rich) < 950 and lang == "en":
        rich += (
            "\n\nSmall details are not treated as decoration here. Each one is tied back to the "
            "larger chain of decisions, consequences, fear, memory, and cause-and-effect that "
            "shaped what happened next. The episode is paced for viewers who want a clear story, "
            "but also want enough detail to understand why the ending lands the way it does."
        )
    return rich[:5000]
