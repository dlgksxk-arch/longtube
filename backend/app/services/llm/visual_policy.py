"""Visual prompt policy for script-generated cuts.

The script step owns the scene idea. This module keeps that idea, but forces the
image/video prompts into the simple local-generation grammar we can reliably use.
"""
from __future__ import annotations

import re
from typing import Any


IMAGE_PROMPT_REQUIRED_STYLE = "serious adult graphic novel illustration, mature documentary manhwa style, bold black ink outlines, heavy black contour linework, gritty dark cinematic mood, high-contrast shadow blocks, stylish single-frame dynamic composition, varied camera rhythm, emotion-forward staging"
_NON_ENGLISH_IMAGE_TEXT_RE = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ一-龥ぁ-ゟ゠-ヿऀ-ॿ]")

_KNOWN_IMAGE_TEXT_ALIASES: tuple[tuple[str, str], ...] = (
    ("광개토대왕", "King Gwanggaeto"),
    ("광개토대 왕", "King Gwanggaeto"),
    ("장수왕", "King Jangsu"),
    ("모용성", "Murong Sheng"),
    ("모용희", "Murong Xi"),
    ("모용귀", "Murong Gui"),
    ("후연", "Later Yan"),
    ("거란", "Khitan"),
    ("고구려", "Goguryeo"),
    ("백제", "Baekje"),
    ("신라", "Silla"),
    ("요동성", "Liaodong Fortress"),
    ("요하", "Liao River"),
    ("수 양제", "Emperor Yang of Sui"),
    ("우문술", "Yuwen Shu"),
    ("우중문", "Yu Zhongwen"),
    ("유사룡", "Liu Shirong"),
    ("내호아", "General Laihu'er"),
    ("을지문덕", "Eulji Mundeok"),
    ("살수대첩", "Goguryeo-Sui open river battlefield"),
    ("살수", "Goguryeo-Sui open river battlefield"),
    ("북방", "northern frontier"),
    ("평양성", "Pyongyang Fortress"),
    ("국내성", "Gungnae Fortress"),
    ("혼노지", "Honno-ji"),
    ("오다 노부나가", "Oda Nobunaga"),
    ("織田信長", "Oda Nobunaga"),
    ("아케치 미쓰히데", "Akechi Mitsuhide"),
    ("明智光秀", "Akechi Mitsuhide"),
    ("도요토미 히데요시", "Toyotomi Hideyoshi"),
    ("豊臣秀吉", "Toyotomi Hideyoshi"),
    ("히데요시", "Hideyoshi"),
    ("朝鮮のおう 宣祖", "King Seonjo of Joseon"),
    ("宣祖", "King Seonjo of Joseon"),
    ("선조", "King Seonjo of Joseon"),
    ("발렌티니아누스 1세", "Valentinian I"),
    ("발렌티니아누스", "Valentinian I"),
    ("클레오파트라", "Cleopatra"),
    ("측천무후", "Wu Zetian"),
    ("선덕 여왕", "Queen Seondeok"),
    ("선덕여왕", "Queen Seondeok"),
    ("소서노", "Soseono"),
    ("유화", "Yuhwa"),
)


_MAJOR_CHARACTER_ENTRANCE_ALIASES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("Emperor Yang of Sui", ("Emperor Yang of Sui", "Sui Yangdi", "Yangdi", "수 양제", "양제"), "male"),
    ("King Yeongyang of Goguryeo", ("King Yeongyang", "Yeongyang", "영양왕"), "male"),
    ("Eulji Mundeok", ("Eulji Mundeok", "Eulji", "을지문덕"), "male"),
    ("Liu Shirong", ("Liu Shirong", "유사룡"), "male"),
    ("General Laihu'er", ("General Laihu'er", "Laihu'er", "Lai Huer", "내호아"), "male"),
    ("Yu Zhongwen", ("Yu Zhongwen", "우중문"), "male"),
    ("Yuwen Shu", ("Yuwen Shu", "우문술"), "male"),
    ("Prince Geonmu", ("Prince Geonmu", "Geonmu", "건무"), "male"),
    ("King Gwanggaeto", ("King Gwanggaeto", "Gwanggaeto", "Gwanggaeto the Great", "광개토대왕", "광개토대 왕"), "male"),
    ("Murong Sheng", ("Murong Sheng", "모용성"), "male"),
    ("Murong Xi", ("Murong Xi", "모용희"), "male"),
    ("Murong Gui", ("Murong Gui", "모용귀"), "male"),
    ("Toyotomi Hideyoshi", ("Toyotomi Hideyoshi", "Hideyoshi", "도요토미 히데요시", "豊臣秀吉"), "male"),
    ("Oda Nobunaga", ("Oda Nobunaga", "Nobunaga", "오다 노부나가", "織田信長"), "male"),
    ("Akechi Mitsuhide", ("Akechi Mitsuhide", "Mitsuhide", "아케치 미쓰히데", "明智光秀"), "male"),
    ("King Seonjo of Joseon", ("King Seonjo of Joseon", "King Seonjo", "Seonjo", "朝鮮のおう 宣祖", "宣祖", "선조"), "male"),
    ("Emperor Valentinian I", ("Emperor Valentinian I", "Valentinian I", "Valentinian", "Valentinian the Great", "발렌티니아누스 1세", "발렌티니아누스"), "male"),
    ("Cleopatra", ("Cleopatra", "클레오파트라"), "female"),
    ("Wu Zetian", ("Wu Zetian", "측천무후"), "female"),
    ("Queen Seondeok", ("Queen Seondeok", "Seondeok", "선덕 여왕", "선덕여왕"), "female"),
    ("Soseono", ("Soseono", "소서노"), "female"),
    ("Yuhwa", ("Yuhwa", "유화"), "female"),
    ("Yaa Asantewaa", ("Yaa Asantewaa", "Asantewaa"), "female"),
)

_ADULT_FEMALE_ENTRANCE_RE = re.compile(
    r"\b(?:adult\s+woman|adult\s+female|woman\s+leader|female\s+leader|female\s+commander|"
    r"female\s+warrior|queen|princess|empress|noblewoman|Cleopatra|Wu\s+Zetian|"
    r"Yaa\s+Asantewaa|Asantewaa)\b|(?:여성|여인|여장군|여왕|왕비|공주|황후|소서노|유화)",
    re.IGNORECASE,
)


def _alias_in_text(text: str, alias: str) -> bool:
    if not alias:
        return False
    if _NON_ENGLISH_IMAGE_TEXT_RE.search(alias):
        return alias in text
    return bool(re.search(rf"\b{re.escape(alias)}\b", text, re.IGNORECASE))


def _major_character_entrance_identities(text: str) -> list[tuple[str, str]]:
    identities: list[tuple[str, str]] = []
    seen: set[str] = set()
    for canonical, aliases, gender in _MAJOR_CHARACTER_ENTRANCE_ALIASES:
        if any(_alias_in_text(text, alias) for alias in aliases):
            key = canonical.lower()
            if key not in seen:
                seen.add(key)
                identities.append((canonical, gender))
    if not identities and re.search(r"\b(?:emperor|imperial\s+ruler)\b|(?:황제|제국의\s+권력자)", text or "", re.IGNORECASE):
        if re.search(r"\b(?:Sui|Goguryeo|Liaodong|612)\b|(?:수나라|수\s*양제|고구려|요동)", text or "", re.IGNORECASE):
            identities.append(("Emperor Yang of Sui", "male"))
    if not identities and _ADULT_FEMALE_ENTRANCE_RE.search(text or ""):
        identities.append(("the scene-named adult woman", "female"))
    return identities


def _major_character_entrance_emotion_phrase(text: str, *, default: str) -> str:
    scan = re.sub(r"\s+", " ", text or "").strip()
    emotion_patterns = (
        (
            r"\b(?:completely\s+devastated|devastated|crushed|shattered|ruined)\b|"
            r"(?:망연자실|절망|충격|패닉)",
            "intense eyes, devastated expression, visible shock",
        ),
        (
            r"\b(?:cold\s+glare|glaring|glare)\b|(?:노려보|냉혹한\s+눈빛)",
            "intense eyes, cold glare",
        ),
        (
            r"\b(?:greedy|ambitious|covetous)\b|(?:탐욕|야심)",
            "greedy ambitious stare",
        ),
        (
            r"\b(?:arrogant|smirking|smirk|sneer)\b|(?:오만|비웃)",
            "arrogant smirk, intense eyes",
        ),
        (
            r"\b(?:furious|angry|rage|wrath)\b|(?:분노|격노)",
            "intense eyes, furious expression",
        ),
        (
            r"\b(?:terrified|fearful|afraid|panic|panicked)\b|(?:두려움|공포)",
            "wide fearful eyes, panic-struck expression",
        ),
        (
            r"\b(?:grief|grieving|sorrow|mourning)\b|(?:비통|슬픔)",
            "grieving eyes, pained expression",
        ),
        (
            r"\b(?:determined|resolute|unyielding)\b|(?:결연|단호)",
            "intense determined eyes",
        ),
        (
            r"\b(?:exhausted|wounded|weary|strained)\b|(?:지친|부상|상처)",
            "exhausted eyes, strained expression",
        ),
    )
    for pattern, phrase in emotion_patterns:
        if re.search(pattern, scan, re.IGNORECASE):
            return phrase
    return default


def _major_character_entrance_scene(identity_names: list[str], gender: str, scene_text: str = "") -> str:
    names = " and ".join(identity_names[:2])
    if len(identity_names) > 1:
        emotion = _major_character_entrance_emotion_phrase(scene_text, default="hard eyes, controlled tension")
        return (
            f"stylish two-character medium-close entrance of {names}, {emotion}, "
            "angled shoulders, period command armor, dramatic rim light"
        )
    if gender == "female":
        emotion = _major_character_entrance_emotion_phrase(scene_text, default="confident eyes")
        return (
            f"stylish medium-close entrance of {names}, adult woman with attractive charisma, "
            f"{emotion}, elegant period clothing, strong silhouette, dramatic rim light"
        )
    emotion = _major_character_entrance_emotion_phrase(scene_text, default="intense eyes, controlled expression")
    return (
        f"stylish medium-close entrance of {names}, {emotion}, "
        "angled shoulders, period command clothing, strong silhouette, dramatic rim light"
    )


def _major_character_entrance_evidence(gender: str) -> str:
    if gender == "female":
        return (
            "adult female face, confident eyes, elegant period-correct clothing, tasteful mature styling, "
            "local architecture or terrain evidence"
        )
    return (
        "face, eyes, readable emotion, period-correct command clothing or armor, "
        "weapon or command setting evidence"
    )


_INTRO_GROUP_NAME_RE = re.compile(
    r"\b(?:army|armies|soldiers|warriors|forces|people|farmers|peasants|villagers|"
    r"officials|guards|envoys|civilians|nobles|court|clan|administration|state|"
    r"kingdom|empire|policy|survey|tax|weapon hunt)\b|"
    r"(?:군대|병사|군사|전사|백성|농민|관리들|사신단|조정|국가|제국|정책|검지|도검몰수)",
    re.IGNORECASE,
)

_PERSONAL_NAME_HINT_RE = re.compile(
    r"\b(?:emperor|king|queen|prince|princess|general|commander|ruler|leader|minister|"
    r"warlord|adult\s+man|adult\s+woman)\b|(?:황제|왕|여왕|왕비|공주|장군|지휘관|군주|지도자)",
    re.IGNORECASE,
)


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
    (r"\bglow\s+between\s+(?:fingertips|fingers|hands)\b", "glowing orb near the character"),
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
)

_LEGACY_POLICY_MARKERS = (
    "only the simplified character(s)",
    "story-relevant object(s)",
    "no room",
    "no scenery",
    "blank round head with no",
    "mitten-like hands with no",
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


def _replace_known_image_aliases(text: str) -> str:
    out = str(text or "")
    for source, target in _KNOWN_IMAGE_TEXT_ALIASES:
        out = out.replace(source, target)
    out = re.sub(r"(\d)\s*년\b", r"\1 AD", out)
    out = re.sub(r"(\d{1,4})\s*[~～–—-]\s*(\d{1,4})\s*AD\b", r"\1-\2 AD", out)
    return _clean_spaces(out)


def _normalize_year_text(text: str) -> str:
    out = text or ""
    out = re.sub(r"(\d)\s*년\b", r"\1 AD", out)
    out = re.sub(r"(\d{1,4})\s*[~～–—-]\s*(\d{1,4})\s*AD\b", r"\1-\2 AD", out)
    out = re.sub(r"\s+", " ", out).strip()
    if _NON_ENGLISH_IMAGE_TEXT_RE.search(out):
        match = re.search(
            r"\b\d{1,4}\s*(?:[~～–—-]\s*\d{1,4})?\s*(?:AD|CE|BCE|BC)?\b",
            out,
            flags=re.IGNORECASE,
        )
        if not match:
            return ""
        out = match.group(0)
        out = re.sub(r"(\d{1,4})\s*[~～–—-]\s*(\d{1,4})", r"\1-\2", out)
        if not re.search(r"\b(?:AD|CE|BCE|BC)\b", out, flags=re.IGNORECASE):
            out = f"{out} AD"
    return _clean_spaces(out)


_YEAR_INTERVAL_RE = re.compile(
    r"\b(?:c\.?\s*)?(\d{1,4})(?:\s*[~～–—-]\s*(\d{1,4}))?\s*(AD|CE|BCE|BC)?\b",
    re.IGNORECASE,
)


def _year_intervals(text: str) -> list[tuple[int, int]]:
    intervals: list[tuple[int, int]] = []
    for match in _YEAR_INTERVAL_RE.finditer(text or ""):
        first_text = match.group(1)
        second_text = match.group(2)
        era = (match.group(3) or "").upper()
        if len(first_text) < 3 and not era:
            continue
        if second_text and len(second_text) < 3 and not era:
            continue
        first = int(first_text)
        second = int(second_text or first_text)
        sign = -1 if era in {"BCE", "BC"} else 1
        a, b = sign * first, sign * second
        intervals.append((min(a, b), max(a, b)))
    return intervals


def _year_interval_sets_overlap(left: list[tuple[int, int]], right: list[tuple[int, int]]) -> bool:
    return any(max(a0, b0) <= min(a1, b1) for a0, a1 in left for b0, b1 in right)


def visual_period_conflicts_with_year(year: str, period: str) -> bool:
    """Return true when a period phrase names a different concrete year."""
    year_ranges = _year_intervals(year)
    period_ranges = _year_intervals(period)
    if not year_ranges or not period_ranges:
        return False
    return not _year_interval_sets_overlap(year_ranges, period_ranges)


def drop_conflicting_visual_period(year: str, period: str) -> str:
    if visual_period_conflicts_with_year(year, period):
        return ""
    return period


_PROMPT_FIELD_LABEL_RE = re.compile(
    r"^(?:Global visual world|Time range|Place scope|Culture scope|Material culture|"
    r"Continuity rule|Year/period|Exact place|Scene evidence|Historically accurate "
    r"period details|Style|Main subject|Scene|NARRATION VISUAL ALIGNMENT)\s*:",
    re.IGNORECASE,
)


def _strip_conflicting_year_period_segments(prompt: str) -> str:
    parts = [part.strip() for part in (prompt or "").split(";")]
    if not parts:
        return prompt or ""
    out: list[str] = []
    index = 0
    while index < len(parts):
        part = parts[index]
        if not part:
            index += 1
            continue
        year_match = re.match(r"^Year/period\s*:\s*(.+)$", part, flags=re.IGNORECASE)
        if not year_match:
            out.append(part)
            index += 1
            continue

        year_value = year_match.group(1).strip()
        out.append(part)
        index += 1
        while index < len(parts):
            trailing = parts[index]
            if not trailing:
                index += 1
                continue
            if _PROMPT_FIELD_LABEL_RE.match(trailing):
                break
            if not visual_period_conflicts_with_year(year_value, trailing):
                out.append(trailing)
            index += 1
        continue
    return "; ".join(out)


def image_prompt_safe_text(value: Any, *, allow_year_normalization: bool = False) -> str:
    """Return text safe for image prompts; drop non-English prompt metadata."""
    text = _replace_known_image_aliases(str(value or ""))
    if not text:
        return ""
    if allow_year_normalization:
        text = _normalize_year_text(text)
    if _NON_ENGLISH_IMAGE_TEXT_RE.search(text):
        return ""
    return text


def _script_text_number(value: Any) -> int:
    match = re.search(r"\d+", str(value or ""))
    return int(match.group(0)) if match else 0


def _looks_like_person_character_name(name: str, explanation: str = "") -> bool:
    text = _replace_known_image_aliases(f"{name} {explanation}")
    if not text.strip():
        return False
    if _major_character_entrance_identities(text):
        return True
    if _ADULT_FEMALE_ENTRANCE_RE.search(text):
        return True
    if _INTRO_GROUP_NAME_RE.search(text):
        return False
    if _PERSONAL_NAME_HINT_RE.search(text):
        return True
    words = re.findall(r"\b[A-Z][A-Za-z'.-]*\b", text)
    return 2 <= len(words) <= 5


def _intro_identity_from_name(name: Any, explanation: Any = "") -> tuple[str, str] | None:
    raw_name = str(name or "").strip()
    raw_explanation = str(explanation or "").strip()
    if not raw_name:
        return None
    scan = f"{raw_name} {raw_explanation}"
    identities = _major_character_entrance_identities(scan)
    if identities:
        return identities[0]
    if not _looks_like_person_character_name(raw_name, raw_explanation):
        return None
    name_en = image_prompt_safe_text(raw_name)
    if not name_en:
        name_en = image_prompt_safe_text(raw_explanation)
    if not name_en:
        return None
    gender = "female" if _ADULT_FEMALE_ENTRANCE_RE.search(scan) else "male"
    return (name_en, gender)


def _script_character_introduction_identities(script: dict[str, Any]) -> dict[int, list[tuple[str, str]]]:
    by_cut: dict[int, list[tuple[str, str]]] = {}

    def add(cut_number: Any, name: Any, explanation: Any = "") -> None:
        cut = _script_text_number(cut_number)
        identity = _intro_identity_from_name(name, explanation)
        if cut <= 0 or not identity:
            return
        bucket = by_cut.setdefault(cut, [])
        key = identity[0].lower()
        if all(existing[0].lower() != key for existing in bucket):
            bucket.append(identity)

    for block in script.get("scene_blocks") or []:
        if not isinstance(block, dict):
            continue
        for intro in block.get("character_introductions") or []:
            if not isinstance(intro, dict):
                continue
            add(
                intro.get("cut_number"),
                intro.get("name"),
                intro.get("explanation_goal") or " ".join(str(x) for x in intro.get("followup_cuts") or []),
            )

    for character in script.get("character_map") or []:
        if not isinstance(character, dict):
            continue
        add(
            character.get("first_appearance_cut"),
            character.get("name"),
            character.get("first_appearance_explanation") or character.get("identity"),
        )

    return by_cut


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
        )
    )
    fields = re.sub(
        r"\b(?:no|not|without|avoid|exclude|excluding)\s+modern(?:[- ]day)?(?:\s+objects?)?\b",
        "",
        fields,
        flags=re.IGNORECASE,
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


def _remove_readable_text_scene_requests(prompt: str) -> str:
    out = prompt or ""
    replacements = [
        (
            r"\bthe\s+word\s+['\"][^'\"]+['\"]\s+carved\s+deeply\s+into\s+a\s+[^.;]+",
            "an unmarked rough stone monument with deep chisel grooves, cracks, dried mud, and blood stains",
        ),
        (
            r"\bthe\s+word\s+['\"][^'\"]+['\"]\s+(?:written|painted|printed|displayed|shown)\s+[^.;]+",
            "a blank period object with scratches, stains, and strong directional light",
        ),
        (
            r"\b(?:famous\s+)?five[-\s]+word\s+poem\s+(?:unrolled|written|displayed|shown)\s+[^.;]+",
            "a blank unrolled parchment on a low wooden table with brush, seal cord, tense hands, and plain untouched surface",
        ),
        (
            r"\b(?:ancient\s+)?scroll\s+unrolling,\s*revealing\s+[^.;]*(?:calligraphy|letters|text|writing)[^.;]*",
            "a blank ancient scroll unrolling beside plain bronze weights and dust",
        ),
        (
            r"\b(?:inscription|calligraphy|letters|readable\s+text|readable\s+words)\s+[^.;]*(?:stone|scroll|paper|tablet|sign|monument)[^.;]*",
            "blank material texture with scratches, cracks, dust, and shadow only",
        ),
    ]
    for pattern, replacement in replacements:
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    return _clean_spaces(out)


def _sanitize_historical_vehicle_prompt(prompt: str) -> str:
    out = prompt or ""
    historical = bool(
        re.search(
            r"\b(?:ancient|historical|period|AD|BCE|BC|CE|Goguryeo|Liaodong|fortress|emperor)\b",
            out,
            flags=re.IGNORECASE,
        )
    )
    if not historical or not re.search(r"\b(?:carriage|coach|wagon|cart)\b", out, flags=re.IGNORECASE):
        return out
    out = re.sub(
        r"\b(?:the\s+)?(?:chinese\s+)?emperor'?s?\s+carriage\b",
        "an ancient animal-drawn open wooden command cart with spoked wooden wheels and rope harness",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"\bcarriage\b",
        "animal-drawn open wooden cart with spoked wooden wheels and rope harness",
        out,
        flags=re.IGNORECASE,
    )
    return _clean_spaces(out)


def _concretize_supernatural_strategy_metaphors(prompt: str) -> str:
    out = prompt or ""
    if re.search(
        r"\b(?:glowing,\s*)?(?:sarcastic\s+)?illustration\s+of\s+a\s+tactical\s+genius\s+in\s+the\s+sky\b",
        out,
        flags=re.IGNORECASE,
    ):
        out = re.sub(
            r"\b(?:a\s+)?(?:glowing,\s*)?(?:sarcastic\s+)?illustration\s+of\s+a\s+tactical\s+genius\s+in\s+the\s+sky\b",
            "a stern commander standing beside a low wooden strategy table under oil-lamp light while officers study blank route cords",
            out,
            flags=re.IGNORECASE,
        )
    return _clean_spaces(out)


def _scene_text_for_policy(prompt: str) -> str:
    out = prompt or ""
    match = re.search(
        r"(?:^|;\s*)Scene:\s*(.*?)(?=;\s*(?:Time range|Place scope|Culture scope|"
        r"Material culture|Continuity rule|Year/period|Exact place|Scene evidence|"
        r"Style|Main subject|Scene|NARRATION VISUAL ALIGNMENT)\s*:|\s+\|\|\s+|$)",
        out,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match:
        out = match.group(1)
    out = re.split(r";\s*NARRATION VISUAL ALIGNMENT:", out, maxsplit=1, flags=re.IGNORECASE)[0]
    return _clean_spaces(out)


def _set_prompt_field(text: str, label: str, value: str) -> str:
    pattern = rf"(?:^|;\s*){re.escape(label)}:\s*[^;]+"
    replacement = f"{label}: {value}"
    if re.search(pattern, text or "", flags=re.IGNORECASE):
        return re.sub(
            pattern,
            lambda match: ("; " if match.group(0).lstrip().startswith(";") else "") + replacement,
            text or "",
            count=1,
            flags=re.IGNORECASE,
        )
    return f"{(text or '').rstrip(' ;')}; {replacement}" if text else replacement


def _is_tang_645_liaodong_context(*parts: str) -> bool:
    text = " ".join(str(part or "") for part in parts)
    return bool(
        re.search(
            r"\b(?:645|Tang|Taizong|Li\s+Shimin|Anshi|Liaodong\s+campaign|Liaodong\s+Fortress)\b|"
            r"당\s*태종|당나라|이세민|요동성|안시성|요하",
            text,
            flags=re.IGNORECASE,
        )
    )


def _has_sui_612_river_drift(prompt: str) -> bool:
    text = prompt or ""
    return bool(
        re.search(
            r"\b(?:612\s+Goguryeo-Sui|Goguryeo-Sui\s+open\s+river|"
            r"Sui\s+soldiers|Salsu)\b|"
            r"살수",
            text,
            flags=re.IGNORECASE,
        )
    )


def _has_sui_612_character_drift(prompt: str) -> bool:
    return bool(
        re.search(
            r"\b(?:Emperor\s+Yang\s+of\s+Sui|Sui\s+Yangdi|Yangdi|Eulji\s+Mundeok|"
            r"Yuwen\s+Shu|Yu\s+Zhongwen|Prince\s+Geonmu|Sui\s+soldiers?)\b|"
            r"수\s*양제|을지|문덕|우문술|우중문|건무|수나라",
            prompt or "",
            flags=re.IGNORECASE,
        )
    )


def _tang_645_liaodong_character_repair_scene(narration: str, scene_text: str) -> tuple[str, str, str, str]:
    basis = " ".join(str(part or "") for part in (narration, scene_text))
    if re.search(r"감탄|훌륭한\s+품격|용기|courage|admiration|admire", basis, re.IGNORECASE):
        return (
            "Tang Taizong acknowledging the Ansi defender's courage",
            "Tang command tent facing Ansi Fortress",
            "Tang Taizong, controlled admiration, narrowed eyes, sleeve-covered hands on plain belt knot, blank command-tent curtains, timber posts, smoke, distant Ansi Fortress glimpse",
            (
                "Tang Taizong stands in a medium-close command-tent view facing Ansi Fortress with controlled admiration, "
                "narrowed eyes, sleeve-covered hands resting on a plain belt knot, blank curtains, timber posts, smoke, and hard rim light"
            ),
        )
    if re.search(r"시해|자극|regicide|provok", basis, re.IGNORECASE):
        return (
            "Tang Taizong and court officials",
            "Tang imperial command hall",
            "Tang Taizong, court officials, sealed border report, tense sleeves, low wooden table, oil-lamp shadow, blank packet surfaces",
            (
                "Tang Taizong and court officials receive a sealed border report about Goguryeo regicide inside a tense Tang imperial command hall, "
                "with a low wooden table, blank packet surfaces, and hard oil-lamp shadow"
            ),
        )
    return (
        "Tang and Goguryeo forces",
        "Liaodong Fortress",
        "Tang-Goguryeo siege pressure, fortress ramparts, lamellar armor, plain shields, wooden siege equipment, dust, cold wind",
        (
            "Tang-Goguryeo siege pressure builds around Liaodong Fortress, with fortress ramparts, lamellar armor, "
            "plain shields, wooden siege equipment, dust, and cold wind"
        ),
    )


def _repair_tang_645_sui_612_character_drift(prompt: str, narration: str = "", script_context: str = "") -> str:
    if not _has_sui_612_character_drift(prompt):
        return prompt
    if not _is_tang_645_liaodong_context(prompt, narration, script_context):
        return prompt

    subject, exact_place, evidence, scene = _tang_645_liaodong_character_repair_scene(
        narration,
        _scene_text_for_policy(prompt),
    )
    out = prompt or ""
    replacements = {
        "Place scope": "Liaodong Fortress and 645 Tang-Goguryeo Liaodong campaign routes",
        "Culture scope": "Goguryeo and Tang military-political world",
        "Material culture": (
            "iron weapons, bows, leather armor, lamellar armor, hemp garments, wooden halls, "
            "fortress walls, river crossings, horses, animal-drawn command carts, wooden siege equipment, sealed report packets"
        ),
        "Continuity rule": (
            "every visible surface uses 645 ancient Northeast Asian court, fortress, and campaign material culture, "
            "blank physical texture, wood, cloth, leather, iron, stone, mud, and river water when the cut requires it"
        ),
        "Year/period": "645 AD; Tang-Goguryeo Liaodong campaign",
        "Exact place": exact_place,
        "Scene evidence": evidence,
        "Main subject": subject,
        "Scene": scene,
    }
    for label, value in replacements.items():
        out = _set_prompt_field(out, label, value)
    out = re.sub(r"\b(?:Goguryeo-Sui|Sui-Goguryeo)\b", "Tang-Goguryeo", out, flags=re.IGNORECASE)
    out = re.sub(r"\bEmperor\s+Yang\s+of\s+Sui\b", "Tang Taizong", out, flags=re.IGNORECASE)
    out = re.sub(r"\bSui\s+soldiers\b", "Tang soldiers", out, flags=re.IGNORECASE)
    out = re.sub(r"\bEulji\s+Mundeok\b", "Goguryeo elder commander", out, flags=re.IGNORECASE)
    out = re.sub(r"\b612\s+AD\b", "645 AD", out, flags=re.IGNORECASE)
    return _clean_spaces(out)


def _tang_645_liaodong_repair_scene(narration: str, scene_text: str) -> tuple[str, str, str]:
    basis = " ".join(str(part or "") for part in (narration, scene_text))
    if re.search(r"\bLiao\s+River\b|요하|cross(?:es|ing)?|건너", basis, re.IGNORECASE):
        return (
            "Liao River crossing toward Liaodong Fortress",
            "Tang soldiers, muddy Liao River crossing, horse tack, plain shields, wet reeds, distant Liaodong ramparts, cold wind",
            (
                "Tang soldiers cross the wide muddy Liao River toward Liaodong Fortress, "
                "with horse tack, plain shields, wet reeds, water spray, cold wind, and distant fortress ramparts"
            ),
        )
    if re.search(r"고정의|신중|전략|strategy|cautious|elder|old\s+general", basis, re.IGNORECASE):
        return (
            "Liaodong Fortress command room",
            "elder Goguryeo commander, fortress officers, low wooden strategy table, blank route cords, oil-lamp shadow, lamellar armor",
            (
                "An elder Goguryeo commander proposes a cautious defense inside a dark Liaodong Fortress command room, "
                "with officers around a low wooden strategy table, blank route cords, and oil-lamp shadow"
            ),
        )
    if re.search(r"지연|전술|delay|delaying|tactic", basis, re.IGNORECASE):
        return (
            "Liaodong Fortress command room",
            "Goguryeo defense officers, low wooden strategy table, blank route cords, fortress timber walls, lamellar armor, oil-lamp shadow",
            (
                "Goguryeo defense officers plan a cold delaying tactic around a low wooden strategy table inside Liaodong Fortress, "
                "with blank route cords, lamellar armor, and hard oil-lamp shadow"
            ),
        )
    if re.search(r"해일|멸망|wave|flood|crash", basis, re.IGNORECASE):
        return (
            "Liaodong Fortress wall",
            "Goguryeo defenders, fortress ramparts, approaching Tang army pressure, dust, storm clouds, plain shields, no literal flood",
            (
                "Goguryeo defenders brace on the Liaodong Fortress wall as immense Tang army pressure gathers beyond the ramparts, "
                "with dust, storm clouds, plain shields, and no literal floodwater"
            ),
        )
    if re.search(r"진흙탕|굴욕|도망|withdraw|mud|humiliation|Taizong|당\s*태종|이세민", basis, re.IGNORECASE):
        return (
            "muddy withdrawal road near Liaodong",
            "Tang Taizong, animal-drawn open wooden command cart, deep mud, exhausted Tang guards, rope harness, cold haze",
            (
                "Tang Taizong stands beside an animal-drawn open wooden command cart stuck in deep mud near Liaodong, "
                "with spoked wheels, rope harness, exhausted Tang guards, cold haze, and a humiliated command mood"
            ),
        )
    return (
        "Liaodong Fortress",
        "Tang-Goguryeo siege pressure, fortress ramparts, lamellar armor, plain shields, wooden siege equipment, dust, cold wind",
        (
            "Tang-Goguryeo siege pressure builds around Liaodong Fortress, with fortress ramparts, lamellar armor, "
            "plain shields, wooden siege equipment, dust, and cold wind"
        ),
    )


def _repair_tang_645_sui_612_river_drift(prompt: str, narration: str = "", script_context: str = "") -> str:
    if not _has_sui_612_river_drift(prompt):
        return prompt
    if not _is_tang_645_liaodong_context(prompt, narration, script_context):
        return prompt

    scene_text = _scene_text_for_policy(prompt)
    exact_place, evidence, scene = _tang_645_liaodong_repair_scene(narration, scene_text)
    out = prompt or ""
    replacements = {
        "Place scope": "Liaodong Fortress and 645 Tang-Goguryeo Liaodong campaign routes",
        "Material culture": (
            "iron weapons, bows, leather armor, lamellar armor, hemp garments, wooden halls, "
            "fortress walls, river crossings, horses, animal-drawn command carts, wooden siege equipment"
        ),
        "Continuity rule": (
            "every visible surface uses 645 ancient Northeast Asian fortress and campaign material culture, "
            "blank physical texture, wood, cloth, leather, iron, stone, mud, and river water when the cut requires it"
        ),
        "Year/period": "645 AD; Tang-Goguryeo Liaodong campaign",
        "Exact place": exact_place,
        "Scene evidence": evidence,
        "Main subject": "Tang Taizong" if "Tang Taizong" in scene else ("Goguryeo defenders" if "defenders" in scene else "Tang and Goguryeo forces"),
        "Scene": scene,
    }
    for label, value in replacements.items():
        out = _set_prompt_field(out, label, value)
    out = re.sub(r"\b(?:Goguryeo-Sui|Sui-Goguryeo)\b", "Tang-Goguryeo", out, flags=re.IGNORECASE)
    out = re.sub(r"\bSui\s+soldiers\b", "Tang soldiers", out, flags=re.IGNORECASE)
    out = re.sub(r"\bEmperor\s+Yang\s+of\s+Sui\b", "Tang Taizong", out, flags=re.IGNORECASE)
    out = re.sub(r"\bEulji\s+Mundeok\b", "Goguryeo elder commander", out, flags=re.IGNORECASE)
    out = re.sub(r"\b612\s+AD\b", "645 AD", out, flags=re.IGNORECASE)
    out = re.sub(r"\b612\s+Tang-Goguryeo\b", "645 Tang-Goguryeo", out, flags=re.IGNORECASE)
    out = re.sub(r"\bopen\s+river\s+battlefield,\s*muddy\s+river\s+crossing\b", exact_place, out, flags=re.IGNORECASE)
    return _clean_spaces(out)


def _is_sui_goguryeo_war_context(*parts: str) -> bool:
    text = " ".join(str(part or "") for part in parts)
    if re.search(
        r"\b(?:645|Tang|Taizong|Li\s+Shimin|Anshi|安市|Liaodong\s+campaign)\b|"
        r"당\s*태종|이세민|안시성|요동성\s*함락",
        text,
        flags=re.IGNORECASE,
    ) and not re.search(
        r"\b(?:612|Sui\s+Yangdi|Emperor\s+Yang|Yang\s+of\s+Sui|Eulji|Mundeok|"
        r"Salsu|Yuwen\s+Shu|Yu\s+Zhongwen)\b|"
        r"수\s*양제|을지|문덕|살수|우문술|우중문",
        text,
        flags=re.IGNORECASE,
    ):
        return False
    return bool(
        re.search(
            r"\b(?:612|Sui|Yangdi|Emperor\s+Yang|Yang\s+of\s+Sui|Liaodong|"
            r"Liao\s+River|Yodong|Eulji|Mundeok|Pyongyang|Yuwen\s+Shu|Yu\s+Zhongwen)\b|"
            r"수\s*양제|수나라|요동성|요하|을지|문덕|평양|우문술|우중문|살수",
            text,
            flags=re.IGNORECASE,
        )
    )


def _sui_goguryeo_open_river_scene_trigger(*parts: str) -> bool:
    text = " ".join(str(part or "") for part in parts)
    text = re.sub(r"\benemy\s+wave\b", "enemy formation", text, flags=re.IGNORECASE)
    return bool(
        re.search(
            r"\b(?:Salsu|river|riverbank|river\s+bank|river\s+valley|middle\s+of\s+the\s+river|"
            r"northern\s+bank|flood|floodwater|wave|dam|water\s+pressure|lake|crossing|"
            r"retreat|withdraw|"
            r"survivors?|staggering|swept\s+away|swallowed|carriage|cart\s+stuck)\b|"
            r"살수|강물|강가|강둑|도하|홍수|댐|둑|물살|퇴각|쓸려|수몰|진흙탕",
            text,
            flags=re.IGNORECASE,
        )
    )


def _sui_goguryeo_command_strategy_trigger(*parts: str) -> bool:
    text = " ".join(str(part or "") for part in parts)
    return bool(
        re.search(
            r"\b(?:five[-\s]+word\s+poem|poem|Eulji|Mundeok|command\s+mat|bamboo\s+slips?|"
            r"strategy\s+table|route\s+cords|tactical\s+genius|strateg(?:y|ic))\b|"
            r"오언시|을지|문덕|지휘|죽간|전략|하늘의\s*이치",
            text,
            flags=re.IGNORECASE,
        )
    )


def _append_sui_cut_specific_detail(base: str, scene_text: str) -> str:
    cue = _clean_spaces(scene_text or "")
    if not cue:
        return base
    if re.search(
        r"\b(?:word|carved|Salsu|carriage|tactical\s+genius|in\s+the\s+sky|glowing\s+illustration)\b|살수",
        cue,
        re.IGNORECASE,
    ):
        return base
    cue = re.sub(r"^(?:Scene:\s*)", "", cue, flags=re.IGNORECASE).strip(" .")
    if not cue:
        return base
    if cue.casefold() in base.casefold():
        return base
    words = cue.split()
    if len(words) > 18:
        cue = " ".join(words[:18])
    cue = cue[:1].lower() + cue[1:]
    return f"{base}, also showing {cue}"


def _sui_goguryeo_river_scene(scene_text: str) -> str:
    scene_for_wave = re.sub(r"\benemy\s+wave\b", "enemy formation", scene_text or "", flags=re.IGNORECASE)
    if re.search(
        r"\b(?:five[-\s]+word\s+poem|poem|Eulji|Mundeok|command\s+mat|bamboo\s+slips?|"
        r"strategy\s+table|route\s+cords|tactical\s+genius|strateg(?:y|ic))\b|"
        r"오언시|을지|문덕|지휘|죽간|전략|하늘의\s*이치",
        scene_for_wave,
        re.IGNORECASE,
    ):
        return _append_sui_cut_specific_detail(
            "Eulji Mundeok stands at an outdoor riverbank command mat with closed "
            "cord-tied bamboo slip packets, blank bamboo slips, brush resting aside, "
            "Goguryeo officers, cold river water behind them, muddy bank, low hills, "
            "and dusk wind",
            scene_for_wave,
        )
    if re.search(r"\b(?:carriage|cart\s+stuck|retreat|withdraw)\b|퇴각|진흙탕", scene_for_wave, re.IGNORECASE):
        return _append_sui_cut_specific_detail(
            "Emperor Yang of Sui withdraws beside an animal-drawn open wooden command "
            "cart stuck in deep muddy open ground near a riverbank, with spoked wheels, "
            "rope harness, exhausted guards, cold river haze, and low hills",
            scene_for_wave,
        )
    if re.search(r"\b(?:dam|water\s+pressure|lake)\b|댐|둑", scene_for_wave, re.IGNORECASE):
        return _append_sui_cut_specific_detail(
            "Rough earth-and-log temporary river dam under heavy water pressure, "
            "muddy banks, leaking seams, broken branches, cold lake water, open sky, "
            "and distant low hills",
            scene_for_wave,
        )
    if re.search(r"\b(?:wave|flood|floodwater|swept|swallowed|dark\s+red)\b|홍수|물살|쓸려|수몰", scene_for_wave, re.IGNORECASE):
        return _append_sui_cut_specific_detail(
            "Dark floodwater surges through an open river valley, sweeping broken "
            "spear shafts, shattered shields, torn lamellar armor, exhausted Sui soldiers, "
            "muddy banks, spray, open sky, and low hills",
            scene_for_wave,
        )
    if re.search(r"\b(?:word|stone\s+monument|carved|Salsu)\b|살수", scene_for_wave, re.IGNORECASE):
        return (
            "Unmarked blood-stained river stone lying on a muddy open riverbank among "
            "broken spear shafts, cold water eddies, torn armor plates, wet reeds, "
            "open sky, and distant low hills"
        )
    if re.search(r"\b(?:middle\s+of\s+the\s+river|northern\s+bank|river|bank|survivors?|staggering)\b|강물|강가|강둑|도하", scene_for_wave, re.IGNORECASE):
        return _append_sui_cut_specific_detail(
            "Exhausted Sui soldiers struggle across a cold open river crossing while "
            "Goguryeo infantry wait on muddy banks with plain spears, broken shields, "
            "water spray, wet reeds, open sky, and low hills",
            scene_for_wave,
        )
    return _append_sui_cut_specific_detail(
        "Open 612 Goguryeo-Sui river battlefield with muddy banks, cold water, broken "
        "spear shafts, torn lamellar armor, exhausted Sui soldiers, Goguryeo pressure "
        "from the bank, open sky, and low hills",
        scene_for_wave,
    )


def _route_sui_goguryeo_open_river_prompt(
    prompt: str,
    narration: str = "",
    script_context: str = "",
    original_prompt: str = "",
) -> str:
    source = original_prompt or prompt or ""
    scene_basis = " ".join(
        part
        for part in (
            _scene_text_for_policy(source),
            _scene_text_for_policy(prompt),
            narration,
            script_context,
        )
        if part
    )
    replacement_basis = " ".join(
        part
        for part in (
            _scene_text_for_policy(source),
            _scene_text_for_policy(prompt),
            narration,
        )
        if part
    )
    if not _is_sui_goguryeo_war_context(source, prompt, narration, script_context):
        return prompt
    if not (
        _sui_goguryeo_open_river_scene_trigger(scene_basis)
        or _sui_goguryeo_command_strategy_trigger(replacement_basis)
    ):
        return prompt

    out = prompt or ""
    location = "612 Goguryeo-Sui open river battlefield, muddy river crossing"
    evidence = (
        "open river water, muddy banks, broken spear shafts, torn lamellar armor, "
        "exhausted Sui soldiers, Goguryeo pressure from the bank, open sky, low hills"
    )
    replacement_scene = _sui_goguryeo_river_scene(replacement_basis)
    out = re.sub(
        r"Place scope:\s*Liaodong Fortress(?:,\s*Liaodong)?",
        f"Place scope: {location}",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"Material culture:\s*[^;]+",
        (
            "Material culture: iron weapons, bows, leather armor, lamellar armor, "
            "hemp garments, riverbank mud, cold water, broken spear shafts, horse tack, "
            "rough open wooden carts, wet reeds, low hills"
        ),
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"Continuity rule:\s*[^;]+",
        (
            "Continuity rule: every visible surface uses ancient Northeast Asian "
            "outdoor material culture, blank physical texture, water, mud, cloth, "
            "leather, wood, iron, and stone"
        ),
        out,
        flags=re.IGNORECASE,
    )
    if re.search(r"(?:^|;\s*)Exact place:\s*[^;]+", out, flags=re.IGNORECASE):
        out = re.sub(
            r"Exact place:\s*[^;]+",
            f"Exact place: {location}",
            out,
            flags=re.IGNORECASE,
        )
    else:
        out = re.sub(
            r"(Year/period:\s*[^;]+;\s*)",
            rf"\1Exact place: {location}; Scene evidence: {evidence}; ",
            out,
            count=1,
            flags=re.IGNORECASE,
        )
    if re.search(r"(?:^|;\s*)Scene evidence:\s*[^;]+", out, flags=re.IGNORECASE):
        out = re.sub(
            r"Scene evidence:\s*[^;]+",
            f"Scene evidence: {evidence}",
            out,
            flags=re.IGNORECASE,
        )
    out = re.sub(
        r"(?:^|;\s*)Scene:\s*.*$",
        f"; Scene: {replacement_scene}",
        out,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if "Scene:" not in out:
        out = f"{out.rstrip(' ;')}; Scene: {replacement_scene}"
    return _clean_spaces(out)


def _territory_demand_prompt_from_narration(
    prompt: str,
    narration: str = "",
    script_context: str = "",
) -> str:
    narration_text = str(narration or "")
    source = " ".join(str(part or "") for part in (prompt, script_context))
    if not re.search(r"죽령\s*이북|땅을\s*모두\s*내놓|내놓아라|영토|territor", narration_text, re.IGNORECASE):
        return prompt
    if not re.search(
        r"\b(?:Sui\s+soldiers?|Goguryeo-Sui\s+open\s+river\s+battlefield|river\s+crossing|"
        r"Han\s+River\s+on\s+a\s+map|Salsu|exhausted\s+Sui)\b|수나라|살수|도하",
        source,
        re.IGNORECASE,
    ):
        return prompt

    out = prompt or ""
    location = "Pyongyang Fortress audience hall"
    evidence = (
        "cord-and-stone territorial layout, dark timber hall, low wooden diplomatic table, "
        "raised route cords, separated stone clusters, one firm sleeve-covered pointing gesture, "
        "kneeling Silla envoy, Goguryeo commander, oil-lamp shadow, blank surfaces"
    )
    subject = "Yeon Gaesomun and Kim Chunchu"
    scene = (
        "Yeon Gaesomun points firmly at a low tabletop cord-and-stone territorial layout while "
        "Kim Chunchu kneels tense in a dark Pyongyang Fortress audience hall, with separated stones "
        "and one boundary cord showing the demanded northern territory"
    )

    replacements = {
        "Time range": "642 AD",
        "Place scope": "ancient Northeast Asian Goguryeo court and fortress setting",
        "Culture scope": "Goguryeo and Silla diplomatic world",
        "Material culture": (
            "iron weapons, lamellar armor, hemp garments, wooden halls, fortress walls, "
            "raised route cords, stone markers, bronze weights, oil lamps"
        ),
        "Continuity rule": (
            "every visible surface uses ancient Northeast Asian court material culture, blank "
            "physical texture, wood, cloth, leather, iron, stone, and soot"
        ),
        "Year/period": "642 AD; Goguryeo-Silla territorial demand at Pyongyang Fortress",
        "Exact place": location,
        "Scene evidence": evidence,
        "Main subject": subject,
    }

    def set_field(text: str, label: str, value: str) -> str:
        if label == "Time range" and re.search(r"\bTime range:\s*[^;]+", text, flags=re.IGNORECASE):
            return re.sub(
                r"\bTime range:\s*[^;]+",
                f"Time range: {value}",
                text,
                count=1,
                flags=re.IGNORECASE,
            )
        pattern = rf"(?:^|;\s*){re.escape(label)}:\s*[^;]+"
        replacement = f"{label}: {value}"
        if re.search(pattern, text, flags=re.IGNORECASE):
            return re.sub(
                pattern,
                lambda match: ("; " if match.group(0).lstrip().startswith(";") else "") + replacement,
                text,
                count=1,
                flags=re.IGNORECASE,
            )
        return f"{text.rstrip(' ;')}; {replacement}" if text else replacement

    for label, value in replacements.items():
        out = set_field(out, label, value)
    out = re.sub(r";\s*(?:Goguryeo-Sui|Sui-Goguryeo)\s+war,\s*612\s*AD\b", "", out, flags=re.IGNORECASE)
    if re.search(r"(?:^|;\s*)Scene:\s*.*$", out, flags=re.IGNORECASE | re.DOTALL):
        out = re.sub(
            r"(?:^|;\s*)Scene:\s*.*$",
            f"; Scene: {scene}",
            out,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        )
    else:
        out = f"{out.rstrip(' ;')}; Scene: {scene}"
    return _clean_spaces(out)


def _sui_goguryeo_open_river_visual_world(visual_world: str) -> str:
    out = visual_world or ""
    if not out:
        return (
            "Global visual world: Time range: 612 AD; "
            "Place scope: 612 Goguryeo-Sui open river battlefield, muddy river crossing; "
            "Culture scope: Goguryeo and Sui military world; "
            "Material culture: iron weapons, bows, lamellar armor, hemp garments, "
            "riverbank mud, cold water, broken spear shafts, horse tack, rough open "
            "wooden carts, wet reeds, low hills; "
            "Continuity rule: every visible surface uses ancient Northeast Asian "
            "outdoor material culture, blank physical texture, water, mud, cloth, "
            "leather, wood, iron, and stone"
        )
    out = re.sub(
        r"Place scope:\s*Liaodong Fortress(?:,\s*Liaodong)?",
        "Place scope: 612 Goguryeo-Sui open river battlefield, muddy river crossing",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"Material culture:\s*[^;]+",
        (
            "Material culture: iron weapons, bows, lamellar armor, hemp garments, "
            "riverbank mud, cold water, broken spear shafts, horse tack, rough open "
            "wooden carts, wet reeds, low hills"
        ),
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"Continuity rule:\s*[^;]+",
        (
            "Continuity rule: every visible surface uses ancient Northeast Asian "
            "outdoor material culture, blank physical texture, water, mud, cloth, "
            "leather, wood, iron, and stone"
        ),
        out,
        flags=re.IGNORECASE,
    )
    return _clean_spaces(out)


def _sanitize_scene_conflicts(prompt: str, narration: str = "", script_context: str = "") -> str:
    original = prompt or ""
    out = _remove_readable_text_scene_requests(prompt)
    out = _sanitize_historical_vehicle_prompt(out)
    out = _concretize_supernatural_strategy_metaphors(out)
    territory_fixed = _territory_demand_prompt_from_narration(out, narration, script_context)
    if territory_fixed != out:
        return _clean_spaces(territory_fixed)
    out = _route_sui_goguryeo_open_river_prompt(out, narration, script_context, original)
    return _clean_spaces(out)


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


def _append_narration_alignment_hint(prompt: str, narration: str = "") -> str:
    out = prompt or ""
    if not out or not str(narration or "").strip():
        return out
    if "NARRATION VISUAL ALIGNMENT" in out:
        return out
    return _clean_spaces(
        out
        + "; NARRATION VISUAL ALIGNMENT: match this cut's spoken moment through "
        "visible action, emotional expression, body posture, prop contact, "
        "setting pressure, or object evidence; avoid neutral generic portraits "
        "and unrelated scenery"
    )


def normalize_cut_image_prompt(prompt: str, narration: str = "", script_context: str = "") -> str:
    """Normalize one cut with narration-aware role alignment."""
    safe_prompt = _strip_conflicting_year_period_segments(normalize_image_prompt(prompt))
    safe_prompt = _repair_tang_645_sui_612_river_drift(safe_prompt, narration, script_context)
    safe_prompt = _repair_tang_645_sui_612_character_drift(safe_prompt, narration, script_context)
    normalized = strip_narration_leakage(
        _sanitize_scene_conflicts(safe_prompt, narration, script_context),
        narration,
    )
    aligned = _append_narration_alignment_hint(
        _strip_conflicting_year_period_segments(normalized),
        narration,
    )
    return repair_ant_grasshopper_alignment(aligned, narration, script_context)


def _strip_visual_context_prefix(prompt: str) -> str:
    out = prompt or ""
    out = re.sub(
        r"^\s*Global visual world:\s*.*?(?=(?:Year/period|Exact place|Scene evidence|Style|Main subject|Scene):)",
        "",
        out,
        flags=re.IGNORECASE | re.DOTALL,
    )
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


def _is_goguryeo_campaign_context(*parts: str) -> bool:
    text = " ".join(str(part or "") for part in parts)
    if not re.search(r"\bGoguryeo\b", text, re.IGNORECASE):
        return False
    return bool(
        re.search(
            r"\b(?:399|400|401|402|403|404|405|406|407|408|409|410|411|412|413|414|415)\b|"
            r"\b402\s*[~\-–]\s*410\b|"
            r"\b5th[-\s]+century\b|\bfifth[-\s]+century\b",
            text,
            re.IGNORECASE,
        )
    )


def _concretize_goguryeo_campaign_scene(scene: str, context_text: str = "") -> str:
    """Replace metaphor-only Goguryeo scenes with visible period action."""
    out = _clean_spaces(scene)
    if not out or not _is_goguryeo_campaign_context(context_text, out):
        return out
    lower = out.lower()

    if re.search(r"\b(?:map|strategy\s+map|borders?|peninsula|neighboring\s+country)\b", lower):
        pressure = (
            "dark red-stained cord marking the dangerous route"
            if re.search(r"\b(?:blood|red|crimson|dark)\b", lower)
            else "warm oil-lamp light catching dull bronze weights"
        )
        return (
            "Two to four Goguryeo officers lean over a low wooden campaign table "
            f"with blank route cords, separated stone markers, {pressure}, dust, "
            "and sleeve-covered hands pointing toward the western frontier cluster"
        )

    if re.search(r"\b(?:sword|blade)\b", lower) and re.search(r"\b(?:blizzard|snow|fog|veil)\b", lower):
        weather = "diagonal blowing snow" if re.search(r"\b(?:blizzard|snow)\b", lower) else "thick battlefield fog"
        return (
            "A Goguryeo commander in dark lamellar armor grips a short straight "
            f"iron sword while soldiers push forward through {weather} near a "
            "low rough palisade edge"
        )

    if re.search(r"\b(?:eye|eyes|unblinking|staring|lens|close-up)\b", lower):
        if re.search(r"\b(?:gwanggaeto|king)\b", lower):
            return (
                "King Gwanggaeto stands in a dark timber command room watching a "
                "burning frontier fortress through the open doorway, lamellar armor "
                "and oil-lamp shadows framing his tense face"
            )
        return (
            "A Goguryeo commander studies firelit battlefield evidence inside a "
            "dark timber command room, one oil lamp and broken helmets casting hard shadows"
        )

    if (
        re.search(r"\bking\b", lower)
        and re.search(r"\b(?:armor|armour)\b", lower)
        and re.search(r"\b(?:bow|bowing|fear|starving)\b", lower)
    ):
        return (
            "A Goguryeo armored ruler stands in an open packed-earth courtyard while "
            "frightened villagers bow low before him, with blank palisade stakes and "
            "open sky behind the group"
        )

    if re.search(r"\bchinese\s+governor\b", lower):
        return (
            "Later Yan governor Murong Gui flees a low fortress gate in panic, "
            "dropping a short spear while attendants scatter across muddy packed earth"
        )

    if re.search(r"\byan\s+soldiers?\b", lower) and re.search(r"\b(?:wave|march|marching|fortress)\b", lower):
        return (
            "Later Yan soldiers march in dense ranks toward a low Goguryeo "
            "stone-and-earth fortress, blank dark banners bent by cold frontier wind"
        )

    if re.search(r"\b(?:chinese\s+fortress|fortress\s+looming|imposing\s+(?:stone\s+)?fortress)\b", lower):
        if re.search(r"\b(?:storm|standing\s+firmly)\b", lower):
            return (
                "A low Goguryeo stone-and-earth frontier fortress stands under storm clouds, "
                "with single-level timber watch posts, rough ramparts, and wet packed earth"
            )
        return (
            "The Later Yan frontier fortress at Sukgunseong rises from dense fog as low "
            "packed-earth ramparts, timber watch posts, rough stonework, and blank gates"
        )

    if "dragon banner" in lower or re.search(r"\b(?:banner|standard)\b", lower):
        action = "falls into muddy snow" if re.search(r"\b(?:fall|falling|mud|snow)\b", lower) else "whips in harsh frontier wind"
        return (
            f"A blank dark Later Yan war standard on a rough wooden pole {action}, "
            "with Goguryeo soldiers and churned snow-mud visible around the pole"
        )

    if re.search(r"\b(?:wolves?|tiger|predator|prey|monster|monstrous|beast|animal)\b", lower):
        if "three" in lower:
            return (
                "Goguryeo, Baekje, and Silla armed envoys confront each other in a "
                "tight frontier pass, hands near weapons and faces tense under torchlight"
            )
        return (
            "Two hostile frontier forces face each other across frozen ground, "
            "Goguryeo riders tense on one side and rival soldiers bracing on the other"
        )

    if re.search(r"\b(?:rope|cord)\b", lower) and re.search(r"\b(?:snap|snapping|break|broken|cut)\b", lower):
        return (
            "A blank sealed treaty bundle lies split on a low wooden table while "
            "Goguryeo and Later Yan envoys pull their sleeve-covered hands back"
        )

    if re.search(r"\barrows?\b", lower) and re.search(r"\b(?:retreat|army|descending|cloud)\b", lower):
        return (
            "Goguryeo archers release arrows from behind a low rough palisade toward "
            "retreating Later Yan soldiers crossing muddy frontier ground"
        )

    if re.search(r"\b(?:treaty|document|scroll)\b", lower) and re.search(r"\b(?:flame|fire|burn|burst)\b", lower):
        return (
            "A blank sealed treaty bundle catches fire on a low wooden table while "
            "two sleeve-covered diplomatic hands pull back in alarm"
        )

    if re.search(r"\b(?:scroll|calligraphy|golden\s+calligraphy)\b", lower):
        return (
            "A blank wooden record tablet bundle opens under oil-lamp light on a "
            "rough stone table, with sleeve-covered hands and plain bronze weights"
        )

    if "buddha" in lower:
        return (
            "Craftsmen set a plain gilt Buddha statue inside a dim timber temple "
            "hall, with oil lamps, hemp sleeves, bare wood beams, and blank walls"
        )

    if re.search(r"\b(?:tomb|royal\s+tomb)\b", lower):
        return (
            "Disciplined Goguryeo guards patrol before a low stone-mound royal tomb, "
            "spears upright, lamellar armor dark, and packed earth under their boots"
        )

    if re.search(r"\b(?:wheat|grain|peasants?|field)\b", lower):
        if re.search(r"\b(?:blood|red|dark)\b", lower):
            return (
                "A trampled grain field holds broken helmets, muddy footprints, "
                "dark red-stained soil, and scattered millet under a cold sky"
            )
        return (
            "Goguryeo farmers harvest ripe millet and barley near low timber homes, "
            "with baskets, sickles, hemp garments, and guarded frontier hills behind them"
        )

    if re.search(r"\b(?:stone\s+monument|stele|monument)\b", lower):
        return (
            "A blank stone stele casts a long shadow while elite Goguryeo officials "
            "stand above weary displaced villagers on packed earth"
        )

    if re.search(r"\b(?:foundation|foundations|palace)\b", lower) and re.search(r"\b(?:blood|red|dark)\b", lower):
        return (
            "Laborers and guards stand around rough stone palace foundations, where "
            "dark red mud stains cracks between heavy foundation stones"
        )

    if re.search(r"\b(?:throne|conquered\s+banners?)\b", lower):
        return (
            "King Gwanggaeto sits on a low wooden ruler seat inside a plain timber "
            "audience hall, with blank folded war standards stacked beside armored guards"
        )

    if re.search(r"\b(?:severed\s+head|behead|beheaded|decapitat|head\s+of\s+a\s+king)\b", lower):
        return (
            "A fallen Baekje royal helmet and a broken plain war banner lie in muddy "
            "battlefield grass, with distant armored soldiers blurred behind smoke"
        )

    if re.search(r"\b(?:sparks?|clash)\b", lower) and re.search(r"\b(?:iron\s+weapons?|blade|sword)\b", lower):
        return (
            "Goguryeo armored soldiers clash short iron weapons in a torchlit "
            "packed-earth courtyard, sparks at the blade contact and shields raised"
        )

    if re.search(r"\b(?:glint|sharpened|sharpen|blade)\b", lower) and re.search(r"\b(?:pitch\s+black|darkness|dark)\b", lower):
        return (
            "King Jangsu sharpens a short iron blade on a stone whetstone inside a "
            "dark timber room, one oil lamp catching a small metal glint"
        )

    if re.search(r"\b(?:vase|jar)\b", lower) and re.search(r"\b(?:shatter|shattering|broken|pieces)\b", lower):
        return (
            "A shattered plain clay storage jar lies on packed earth beside a low "
            "wooden table, shards, dust, and startled Goguryeo attendants around it"
        )

    if re.search(r"\b(?:crown|prince)\b", lower):
        return (
            "A young Goguryeo prince grips a plain bronze-bound succession tablet box "
            "on a low table while older officials watch silently under torchlight"
        )

    if re.search(r"\b(?:textbook|painting|page)\b", lower):
        return (
            "A blank wooden record-tablet bundle and small bronze royal figurine "
            "sit under golden lamplight on a rough stone table"
        )

    if re.search(r"\b(?:door|gate)\b", lower) and re.search(r"\b(?:slamming|shut|darkness)\b", lower):
        return (
            "A heavy timber fortress gate closes behind weary Goguryeo soldiers, "
            "iron studs, rope pulls, dust, and torch shadows filling the frame"
        )

    if re.search(r"\b(?:chalice|cup)\b", lower):
        return (
            "A bronze cup tips over on a low court table, spilling dark red liquid "
            "across plain white cloth while tense sleeve-covered hands recoil"
        )

    if re.search(r"\b(?:mirror|modern\s+face)\b", lower):
        return (
            "An exhausted young Goguryeo ruler studies a cracked bronze mirror by "
            "oil-lamp light, his period robe and tense reflection visible in the metal"
        )

    if re.search(r"\broyal\s+bedchamber\b", lower):
        return (
            "A dim Goguryeo royal bedchamber holds a low wooden sleeping platform, "
            "plain closed curtains, oil lamps, and silent court attendants on the packed floor"
        )

    if re.search(r"\b(?:fairy[- ]tale|history\s+book|old\s+book|book)\b", lower) and re.search(r"\b(?:fire|blazing|burn|thrown)\b", lower):
        return (
            "A Goguryeo scribe pushes a blank wooden tale tablet into a low bronze "
            "brazier, smoke rising beside stone weights and plain record bundles"
        )

    if "hourglass" in lower:
        return (
            "An older Goguryeo ruler studies worn tally cords and wooden counters on "
            "a low desk, measuring a long reign under cold lamplight"
        )

    if re.search(r"\b(?:gear|gears|mechanical|machine|pedal|bicycle|engine)\b", lower):
        return (
            "Goguryeo soldiers strain to haul a heavy wooden siege cart through "
            "churned frontier mud while an officer drives the advance beside broken "
            "spear shafts and torchlit supply ropes"
        )

    if re.search(r"\b(?:wooden\s+wheel|stone\s+wheel|heavy\s+stone\s+wheel|massive.*wheel|cart\s+wheel)\b", lower):
        return (
            "A heavy wooden supply cart wheel grinds through dark red battlefield mud "
            "beside broken shields, low stone tomb markers, and weary Goguryeo soldiers"
        )

    if "teardrop" in lower:
        return (
            "A displaced villager kneels beside a muddy red rain puddle, torn hemp "
            "sleeve and abandoned helmet visible on the packed earth"
        )

    return out


def _infer_visual_subject_from_scene(scene: str) -> str:
    text = _clean_spaces(scene)
    if not text:
        return ""
    known_patterns = (
        (r"\bMurong\s+Sheng\b", "Murong Sheng"),
        (r"\bMurong\s+Xi\b", "Murong Xi"),
        (r"\bMurong\s+Gui\b", "Murong Gui"),
        (r"\bKing\s+Jangsu\b", "King Jangsu"),
        (r"\bKing\s+Gwanggaeto\b", "King Gwanggaeto"),
        (r"\bEulji\s+Mundeok\b", "Eulji Mundeok"),
        (r"\bEmperor\s+Yang\s+of\s+Sui\b", "Emperor Yang of Sui"),
        (r"\bSui\s+soldiers?\b", "Sui soldiers"),
        (r"\bGoguryeo\s+infantry\b", "Goguryeo infantry"),
        (r"\bdark\s+floodwater\b", "dark floodwater"),
        (r"\bunmarked\s+blood-stained\s+river\s+stone\b", "unmarked blood-stained river stone"),
        (r"\brough\s+earth-and-log\s+temporary\s+river\s+dam\b", "rough earth-and-log river dam"),
        (r"\bfallen\s+Baekje\s+royal\s+helmet\b", "fallen Baekje royal helmet"),
        (r"\bLater\s+Yan\s+war\s+standard\b", "Later Yan war standard"),
        (r"\bLater\s+Yan\s+frontier\s+fortress\b", "Later Yan frontier fortress"),
        (r"\bGoguryeo\s+archers?\b", "Goguryeo archers"),
        (r"\bLater\s+Yan\s+soldiers?\b", "Later Yan soldiers"),
        (r"\bblank\s+sealed\s+treaty\s+bundle\b", "blank sealed treaty bundle"),
        (r"\bGoguryeo\s+stone-and-earth\s+frontier\s+fortress\b", "Goguryeo frontier fortress"),
        (r"\bGoguryeo\s+frontier\s+fortress\b", "Goguryeo frontier fortress"),
        (r"\bGoguryeo\s+officers?\b", "Goguryeo officers"),
        (r"\bGoguryeo\s+commander\b", "Goguryeo commander"),
        (r"\bGoguryeo\s+armored\s+soldiers?\b", "Goguryeo armored soldiers"),
        (r"\bheavy\s+wooden\s+supply\s+cart\s+wheel\b", "heavy wooden supply cart wheel"),
        (r"\bGoguryeo\s+soldiers?\b", "Goguryeo soldiers"),
        (r"\bGoguryeo\s+riders?\b", "Goguryeo riders"),
        (r"\bGoguryeo\s+farmers?\b", "Goguryeo farmers"),
        (r"\bGoguryeo\s+guards?\b", "Goguryeo guards"),
        (r"\bGoguryeo\s+royal\s+bedchamber\b", "Goguryeo royal bedchamber"),
        (r"\bGoguryeo\s+scribe\b", "Goguryeo scribe"),
        (r"\bblank\s+wooden\s+record\s+tablet\s+bundle\b", "blank wooden record tablet bundle"),
        (r"\bshattered\s+plain\s+clay\s+storage\s+jar\b", "shattered plain clay storage jar"),
        (r"\byoung\s+Goguryeo\s+prince\b", "young Goguryeo prince"),
        (r"\bexhausted\s+young\s+Goguryeo\s+ruler\b", "exhausted young Goguryeo ruler"),
        (r"\bolder\s+Goguryeo\s+ruler\b", "older Goguryeo ruler"),
        (r"\bdisplaced\s+villager\b", "displaced villager"),
    )
    for pattern, replacement in known_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return replacement
    stripped = re.sub(
        r"^(?:a|an|the|one|two|three|two\s+to\s+four|several|many)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )
    subject = re.split(
        r"\b(?:leans?|grips?|push(?:es)?|faces?|confronts?|catches?|falls?|whips?|"
        r"harvests?|patrols?|stands?|studies?|sits?|kneels?|turns?|spills?|"
        r"attacks?|draws?|drawing|exchanges?|points?|closes?|carries?)\b",
        stripped,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    subject = re.split(r",| with | while | under | near | beside | inside | by ", subject, maxsplit=1, flags=re.IGNORECASE)[0]
    words = subject.strip(" ,.;").split()
    if not words:
        return ""
    return _clean_spaces(" ".join(words[:10]))


def _compiled_visual_world(script: dict[str, Any]) -> str:
    world = script.get("visual_world") if isinstance(script, dict) else None
    if not isinstance(world, dict):
        return ""
    labels = (
        ("time_range", "Time range"),
        ("place_scope", "Place scope"),
        ("culture_scope", "Culture scope"),
        ("material_culture", "Material culture"),
        ("continuity_rule", "Continuity rule"),
    )
    parts: list[str] = []
    for key, label in labels:
        value = image_prompt_safe_text(
            world.get(key),
            allow_year_normalization=(key == "time_range"),
        )
        if value:
            parts.append(f"{label}: {value}")
    if not parts:
        return ""
    return "Global visual world: " + "; ".join(parts)


def inject_cut_visual_context(
    cut: dict[str, Any],
    visual_world: str = "",
    seen_major_characters: set[str] | None = None,
    forced_entrance_identities: list[tuple[str, str]] | None = None,
) -> None:
    """Force year/period/place metadata into the stored image prompt."""
    if not isinstance(cut, dict):
        return
    prompt = image_prompt_safe_text(cut.get("image_prompt") or "")
    year = image_prompt_safe_text(cut.get("visual_year"), allow_year_normalization=True)
    period = image_prompt_safe_text(cut.get("visual_period"))
    original_period = period
    period = drop_conflicting_visual_period(year, period)
    location = image_prompt_safe_text(cut.get("visual_location"))
    evidence = image_prompt_safe_text(cut.get("visual_evidence"))
    # visual_subject must be cut-specific. Do not fall back to a global
    # main_subject, because that pins every landscape/object cut to one person.
    raw_visual_subject = str(cut.get("visual_subject") or "")
    subject_from_non_english = bool(_NON_ENGLISH_IMAGE_TEXT_RE.search(raw_visual_subject))
    subject = image_prompt_safe_text(raw_visual_subject)
    explicit_scene = image_prompt_safe_text(cut.get("visual_scene"))
    if subject_from_non_english and explicit_scene:
        inferred_subject = image_prompt_safe_text(_infer_visual_subject_from_scene(explicit_scene))
        if inferred_subject:
            subject = inferred_subject
    context_text = " ".join(
        part
        for part in (
            visual_world,
            prompt,
            year,
            period,
            location,
            evidence,
            subject,
            explicit_scene,
        )
        if part
    )
    sui_scene_basis = " ".join(
        str(cut.get(key) or "")
        for key in (
            "narration",
            "image_prompt",
            "visual_subject",
            "visual_scene",
            "visual_location",
        )
    )
    sui_trigger_basis = " ".join(
        str(cut.get(key) or "")
        for key in (
            "visual_scene",
            "visual_location",
        )
    )
    is_sui_goguryeo_context = _is_sui_goguryeo_war_context(context_text, sui_scene_basis)
    is_sui_open_river_cut = (
        is_sui_goguryeo_context
        and _sui_goguryeo_open_river_scene_trigger(sui_trigger_basis)
    )
    if is_sui_goguryeo_context:
        if not year:
            year = "612 AD"
        if not period:
            period = "Sui-Goguryeo war, 612 AD"
    if is_sui_open_river_cut:
        location = "612 Goguryeo-Sui open river battlefield, muddy river crossing"
        evidence = (
            "open river water, muddy banks, broken spear shafts, torn lamellar armor, "
            "exhausted Sui soldiers, Goguryeo pressure from the bank, open sky, low hills"
        )
        explicit_scene = _sui_goguryeo_river_scene(explicit_scene or sui_trigger_basis)
        inferred_subject = image_prompt_safe_text(_infer_visual_subject_from_scene(explicit_scene))
        if inferred_subject:
            subject = inferred_subject
        visual_world = _sui_goguryeo_open_river_visual_world(visual_world)
    if _is_goguryeo_campaign_context(context_text):
        if not period:
            period = "Goguryeo northern campaigns, 402-410 AD"
        if not location:
            location = "Liao River northern frontier"
        if not evidence:
            evidence = (
                "The scene uses Goguryeo frontier clothing, weapons, fortifications, "
                "campaign tables, and everyday materials from the 402-410 AD campaigns."
            )
        if not subject and _NON_ENGLISH_IMAGE_TEXT_RE.search(str(cut.get("visual_subject") or "")):
            subject = image_prompt_safe_text(cut.get("visual_subject"))
    explicit_scene = _concretize_goguryeo_campaign_scene(explicit_scene, context_text)
    if _is_goguryeo_campaign_context(context_text) and explicit_scene:
        inferred_subject = image_prompt_safe_text(_infer_visual_subject_from_scene(explicit_scene))
        if inferred_subject:
            subject = inferred_subject
    character_basis = " ".join(
        str(cut.get(key) or "")
        for key in (
            "narration",
            "image_prompt",
            "visual_subject",
            "visual_scene",
        )
    )
    entrance_identities = list(forced_entrance_identities or [])[:2]
    if not entrance_identities and not is_sui_open_river_cut:
        for name, gender in _major_character_entrance_identities(character_basis):
            key = name.lower()
            if seen_major_characters is not None and key in seen_major_characters:
                continue
            entrance_identities.append((name, gender))
            if len(entrance_identities) >= 2:
                break
    if entrance_identities:
        entrance_names = [name for name, _gender in entrance_identities]
        entrance_gender = "female" if len(entrance_identities) == 1 and entrance_identities[0][1] == "female" else "male"
        subject = " and ".join(entrance_names)
        explicit_scene = _major_character_entrance_scene(entrance_names, entrance_gender, character_basis)
        entrance_evidence = _major_character_entrance_evidence(entrance_gender)
        evidence = f"{evidence}, {entrance_evidence}" if evidence else entrance_evidence
        if seen_major_characters is not None:
            for name in entrance_names:
                seen_major_characters.add(name.lower())
    if not (year or period or location or evidence or subject or explicit_scene):
        return
    scene = explicit_scene or prompt

    if year:
        cut["visual_year"] = year
    if period:
        cut["visual_period"] = period
    elif original_period:
        cut["visual_period"] = ""
    if location:
        cut["visual_location"] = location
    if evidence:
        cut["visual_evidence"] = evidence
    if subject:
        cut["visual_subject"] = subject
    if explicit_scene:
        cut["visual_scene"] = explicit_scene

    parts: list[str] = []
    if visual_world:
        parts.append(visual_world)
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
        visual_world = _compiled_visual_world(script)
        seen_major_characters: set[str] = set()
        forced_entrances_by_cut = _script_character_introduction_identities(script)
        script_context = " ".join(
            str(script.get(key) or "") for key in ("title", "topic", "description")
        )
        for idx, cut in enumerate(cuts, start=1):
            if isinstance(cut, dict) and isinstance(cut.get("image_prompt"), str):
                cut_number = _script_text_number(cut.get("cut_number")) or idx
                cut["image_prompt"] = normalize_cut_image_prompt(
                    cut["image_prompt"],
                    str(cut.get("narration") or ""),
                    script_context,
                )
                inject_cut_visual_context(
                    cut,
                    visual_world,
                    seen_major_characters,
                    forced_entrances_by_cut.get(cut_number),
                )
    return script
