"""Visual prompt policy for script-generated cuts.

The script step owns the scene idea. This module keeps that idea, but forces the
image/video prompts into the simple local-generation grammar we can reliably use.
"""
from __future__ import annotations

import json
import re
from typing import Any


IMAGE_PROMPT_REQUIRED_STYLE = "mature vintage dark historical manhwa illustration, variable-width scratchy dip-pen contours, thin angular interior lines, controlled heavy silhouette accents, dry-brush texture, dense hatching with intersecting hatch strokes, aged fibrous print-stock grain, muted watercolor and gouache washes, sepia dirty-ivory tobacco rust faded-burgundy soot-black palette, bleak ominous tension, dynamic full-bleed composition"
CH4_CINEMATIC_LIVE_ACTION_STYLE = (
    "cinematic live-action historical drama, photorealistic feature-film frame, "
    "period-authentic production design, dramatic lighting, 16:9"
)
SOURCE_LOCKED_VISUAL_POLICY_MODE = "source-locked"
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
    ("伊邪那岐命", "Izanagi"),
    ("伊邪那岐", "Izanagi"),
    ("伊弉諾尊", "Izanagi"),
    ("伊邪那美命", "Izanami"),
    ("伊邪那美", "Izanami"),
    ("伊弉冉尊", "Izanami"),
    ("天照大御神", "Amaterasu"),
    ("天照大神", "Amaterasu"),
    ("月読命", "Tsukuyomi"),
    ("月讀命", "Tsukuyomi"),
    ("須佐之男命", "Susanoo"),
    ("素戔嗚尊", "Susanoo"),
    ("保食神", "Uke Mochi"),
    ("黄泉の国", "Yomi underworld"),
    ("黄泉国", "Yomi underworld"),
    ("三貴子", "the three noble divine children"),
    ("신화시대", "Japanese mythic creation era"),
    ("신화 시대", "Japanese mythic creation era"),
    ("미소기 의식 (정화) / 태양, 달, 폭풍신의 탄생과 우주 질서의 분할", "misogi purification riverbank in mythic ancient Japan, birth of the sun, moon, and storm deities"),
    ("미소기 의식", "misogi purification ritual"),
    ("정화", "purification"),
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
        if re.search(r"\b(?:Sui|612)\b|(?:수나라|수\s*양제)", text or "", re.IGNORECASE):
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
    out = re.sub(r"\b(\d{3,4})\s*around\s+year\b", r"c. \1 AD", out, flags=re.IGNORECASE)
    out = re.sub(r"\b(\d{3,4})around\s+year\b", r"c. \1 AD", out, flags=re.IGNORECASE)
    out = re.sub(r"(\d)\s*년\b", r"\1 AD", out)
    out = re.sub(r"(\d{1,4})\s*[~～–—-]\s*(\d{1,4})\s*AD\b", r"\1-\2 AD", out)
    return _clean_spaces(out)


def _normalize_year_text(text: str) -> str:
    out = text or ""
    out = re.sub(r"\b(\d{3,4})\s*around\s+year\b", r"c. \1 AD", out, flags=re.IGNORECASE)
    out = re.sub(r"\b(\d{3,4})around\s+year\b", r"c. \1 AD", out, flags=re.IGNORECASE)
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


def _extract_cue_year_text(*parts: str) -> str:
    text = " ".join(str(part or "") for part in parts)
    if not text:
        return ""
    match = re.search(
        r"(?:큐시트\s*연도|\[연도\]|연도)\s*[:=]\s*"
        r"(?:c\.?\s*)?(\d{3,4})(?:\s*년\s*경|\s*경|\s*around\s+year)?",
        text,
        flags=re.IGNORECASE,
    )
    around = False
    if match:
        around = bool(re.search(r"(?:경|around\s+year)", match.group(0), flags=re.IGNORECASE))
    else:
        match = re.search(
            r"\bTime\s+range\s*:\s*(?:c\.?\s*)?(\d{3,4})"
            r"(?:\s*around\s+year|\s*AD|\s*CE|\s*년\s*경|\s*경)?\b",
            text,
            flags=re.IGNORECASE,
        )
        if match:
            around = bool(re.search(r"(?:c\.?|경|around\s+year)", match.group(0), flags=re.IGNORECASE))
    if not match:
        return ""
    year = match.group(1)
    return f"c. {year} AD" if around else f"{year} AD"


def _is_goguryeo_succession_cue_context(*parts: str) -> bool:
    text = " ".join(str(part or "") for part in parts)
    source_prompt = str(parts[0] or "") if parts else ""
    declared_period = ""
    for label in ("Era/period", "Year/period", "Time range"):
        match = re.search(
            rf"(?:^|;\s*){re.escape(label)}\s*:\s*([^;]+)",
            source_prompt,
            flags=re.IGNORECASE,
        )
        if match:
            declared_period = match.group(1)
            break
    declared_late_seventh = bool(re.search(
        r"\b(?:66[5-9]|67[0-9])\s*(?:AD|CE)?\b|"
        r"\b(?:late\s+)?(?:seventh|7th)[-\s]*(?:century|c(?:entury)?\.?)|"
        r"7세기\s*후반|서기\s*66[5-9]",
        declared_period,
        flags=re.IGNORECASE,
    ))
    explicit_late_seventh_cue = bool(re.search(
        r"\b(?:66[5-9]|67[0-9])\s*(?:AD|CE)?\b|"
        r"연개소문|남생|남건|남산|헌충|대막리지|"
        r"Namsaeng|Namgeon|Namsan|Yeon\s+Gaesomun|Yeon\s+Namsaeng|"
        r"Goguryeo\s+succession\s+crisis|"
        r"안에서\s*열린\s*성문|700년\s*제국의\s*몰락|고구려-?EP\s*\.?\s*30",
        text,
        flags=re.IGNORECASE,
    ))
    if declared_period and not declared_late_seventh and not explicit_late_seventh_cue:
        return False

    if not re.search(r"\bGoguryeo\b|고구려|Pyongyang|평양", text, flags=re.IGNORECASE):
        return False
    return bool(
        re.search(
            r"연개소문|남생|남건|남산|헌충|대막리지|형제|succession|successor|"
            r"Namsaeng|Namgeon|Namsan|Yeon\s+Gaesomun|Yeon\s+Namsaeng|"
            r"Goguryeo\s+succession|court\s+crisis|internal\s+power|"
            r"안에서\s*열린\s*성문|700년\s*제국의\s*몰락|고구려-?EP\s*\.?\s*30",
            text,
            flags=re.IGNORECASE,
        )
    )


def _is_sui_goguryeo_specific_context(*parts: str) -> bool:
    text = " ".join(str(part or "") for part in parts)
    return bool(
        re.search(
            r"\b(?:612|Sui|Yangdi|Emperor\s+Yang|Yang\s+of\s+Sui|Eulji|Mundeok|"
            r"Salsu|Yuwen\s+Shu|Yu\s+Zhongwen)\b|"
            r"수\s*양제|수나라|을지|문덕|살수|우문술|우중문",
            text,
            flags=re.IGNORECASE,
        )
    )


def _goguryeo_succession_evidence(year: str) -> str:
    return (
        f"The cut belongs to the {year} Goguryeo succession crisis at Pyongyang Fortress, "
        "after Yeon Gaesomun's death, with Yeon Namsaeng, Namgeon, Namsan, rebel palace guards, "
        "court officials, fortress halls, lamellar armor, plain hemp robes, iron weapons, smoke, and broken court order as relevant evidence."
    )


def _repair_goguryeo_succession_drift_scene(
    narration: str,
    subject: str,
    scene: str,
) -> tuple[str, str, str]:
    """Replace known 612/founder-era hallucinations inside the 665 succession episode."""
    combined = " ".join(str(part or "") for part in (narration, subject, scene))
    if not re.search(
        r"\b(?:Emperor\s+Yang(?:\s+of\s+Sui)?|Sui\s+soldiers?|Yuhwa|612\s+Goguryeo-Sui|"
        r"Sui-Goguryeo|open\s+river\s+battlefield)\b",
        combined,
        flags=re.IGNORECASE,
    ):
        return subject, scene, ""
    narration_text = str(narration or "")
    if re.search(r"궁궐|palace", narration_text, flags=re.IGNORECASE) and re.search(
        r"장악|반란군|seize|rebel", narration_text, flags=re.IGNORECASE
    ):
        return (
            "Namgeon and Namsan rebel palace guards",
            "Namgeon and Namsan's Goguryeo rebel guards seize the Pyongyang palace courtyard, forced doors open, blades held low, smoke, scattered court objects, frightened officials pushed aside, and fortress hall shadows",
            "Rebel palace seizure during the c. 665 Goguryeo succession crisis after Yeon Gaesomun's death.",
        )
    if re.search(r"외적|동족|same\s+people|civil", narration_text, flags=re.IGNORECASE):
        return (
            "Goguryeo soldiers turning blades against fellow Goguryeo soldiers",
            "Goguryeo soldiers turn iron blades against fellow Goguryeo soldiers inside a smoky fortress courtyard, torn lamellar armor, broken spear shafts, fallen shields, dust, hard torchlight, and divided banners",
            "Civil war violence inside Goguryeo during the c. 665 succession crisis, not a foreign battlefield.",
        )
    if re.search(r"당나라|살려달라|엎드린|Tang|asylum|surrender", narration_text, flags=re.IGNORECASE):
        return (
            "Yeon Namsaeng pleading toward Tang envoys",
            "Yeon Namsaeng kneels in desperate surrender before stern Tang envoys at a cold frontier court threshold, torn Goguryeo cloak, lowered head, sealed plea bundle, guarded doorway, and dark political shame",
            "Namsaeng seeks Tang protection during the Goguryeo succession crisis.",
        )
    if re.search(r"나비효과|탐욕|butterfly|greed", narration_text, flags=re.IGNORECASE):
        return (
            "blood-red butterfly effect of private power greed",
            "A huge blood-red butterfly-shaped shadow spreads across cracked Goguryeo court tablets, broken armor, spilled dark liquid, torn rope, and a split stone floor inside a dim Pyongyang fortress hall",
            "Symbolic consequence of elite greed in the c. 665 Goguryeo succession crisis.",
        )
    return (
        "Goguryeo succession crisis evidence",
        "A tense c. 665 Goguryeo court crisis scene at Pyongyang Fortress with divided officials, broken court objects, smoke, iron weapons, plain robes, lamellar armor, and hard shadow",
        "Corrected to the c. 665 Goguryeo succession crisis context.",
    )


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


def _has_explicit_sui_612_without_explicit_tang_645(narration: str, scene_text: str) -> bool:
    source = " ".join(str(part or "") for part in (narration, scene_text))
    explicit_sui_612 = bool(
        re.search(
            r"\b(?:612|Sui|Eulji\s+Mundeok|Salsu|Yuwen\s+Shu|Yu\s+Zhongwen)\b|"
            r"수\s*양제|수나라|을지\s*문덕|살수|우문술|우중문",
            source,
            flags=re.IGNORECASE,
        )
    )
    explicit_tang_645 = bool(
        re.search(
            r"\b(?:645|Tang\s+Taizong|Li\s+Shimin|Ansi)\b|"
            r"당\s*태종|이세민|안시성",
            source,
            flags=re.IGNORECASE,
        )
    )
    return explicit_sui_612 and not explicit_tang_645


def _repair_tang_645_sui_612_character_drift(prompt: str, narration: str = "", script_context: str = "") -> str:
    if _has_explicit_sui_612_without_explicit_tang_645(
        narration,
        _scene_text_for_policy(prompt),
    ):
        return prompt
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
    if _has_explicit_sui_612_without_explicit_tang_645(
        narration,
        _scene_text_for_policy(prompt),
    ):
        return prompt
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
    if (
        re.search(r"\bSource\s+workbook\s+row\s+08-\d{3}\b", text, flags=re.IGNORECASE)
        and re.search(r"\b475\s*(?:AD|CE)\b", text, flags=re.IGNORECASE)
        and re.search(r"\bBaekje\b", text, flags=re.IGNORECASE)
    ):
        return False
    explicit_sui_campaign = bool(
        re.search(
            r"\b(?:612|Sui\s+Yangdi|Emperor\s+Yang|Yang\s+of\s+Sui|Goguryeo-Sui|"
            r"Sui-Goguryeo|Salsu|Yuwen\s+Shu|Yu\s+Zhongwen)\b|"
            r"수\s*양제|수나라|살수|우문술|우중문",
            text,
            flags=re.IGNORECASE,
        )
    )
    explicit_sui_battle = bool(
        re.search(
            r"\b(?:612|Sui\s+Yangdi|Emperor\s+Yang|Yang\s+of\s+Sui|Goguryeo-Sui|"
            r"Sui-Goguryeo|Eulji|Mundeok|Salsu|Yuwen\s+Shu|Yu\s+Zhongwen)\b|"
            r"수\s*양제|수나라|을지|문덕|살수|우문술|우중문",
            text,
            flags=re.IGNORECASE,
        )
    )
    if re.search(
        r"\b(?:66[0-9]\s*(?:AD|CE|year)?|c\.\s*665\s*AD|Goguryeo\s+succession\s+crisis|"
        r"succession\s+crisis)\b|계승|남생|남건|남산|연개소문",
        text,
        flags=re.IGNORECASE,
    ) and not explicit_sui_campaign:
        return False
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
    return explicit_sui_battle


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
    if "Global visual world:" in out and "Scene evidence:" in out:
        return out
    return _clean_spaces(
        out
        + "; NARRATION VISUAL ALIGNMENT: match this cut's spoken moment through "
        "visible action, emotional expression, body posture, prop contact, "
        "setting pressure, or object evidence; avoid neutral generic portraits "
        "and unrelated scenery"
    )


def _goguryeo_succession_runtime_place(scene: str, narration: str) -> str:
    basis = f"{narration} {scene}"
    if re.search(r"장안|당나라\s*황제|당\s*고종|우위대장군|Tang\s+(?:imperial|emperor|court|palace)|Gaozong", basis, re.IGNORECASE):
        return "Tang imperial court at Chang'an, 666-668 AD"
    if re.search(r"국내성|도망|flee|fleeing|Gungnae", basis, re.IGNORECASE):
        return "Gungnae Fortress and its muddy northern approach, 665-666 AD"
    if re.search(r"요동|안동도호부|부흥\s*운동|Liaodong|Andong\s+Protectorate", basis, re.IGNORECASE):
        return "Liaodong frontier under Tang occupation, 668-677 AD"
    if re.search(r"평양성|평양|Pyongyang|포위|besieg|surround", basis, re.IGNORECASE):
        return "Pyongyang Fortress during the final siege, 667-668 AD"
    if re.search(r"당나라\s*대군|나당\s*연합군|Tang\s+(?:army|soldiers)|march", basis, re.IGNORECASE):
        return "Liaodong military road toward Pyongyang, 667 AD"
    return "Goguryeo court and fortress district, 666-668 AD"


def _goguryeo_succession_narration_override(narration: str) -> tuple[str, str, str] | None:
    spoken = str(narration or "")
    robust_overrides = (
        (
            r"침략군의\s*선봉.*서늘한\s*배신자",
            "exactly one adult Yeon Namsaeng leading the Tang vanguard",
            "Yeon Namsaeng stands alone in the foreground at the head of a distant Tang spear line, wearing fitted dark Tang iron lamellar over a closed round-collar robe, plain cloth sash, wrapped boots and one low conical iron helmet; one sheathed short straight ring-pommel sword stays at his left hip, both hands remain empty and his cold face looks toward Pyongyang",
            "Liaodong military road before Pyongyang, 668 AD",
        ),
        (
            r"조국의\s*기밀을\s*팔아넘긴.*맏아들\s*남생",
            "object-only betrayal evidence, zero people",
            "One palm-sized thin flat warm-brown wood-grain Goguryeo command tally lies diagonally alone on continuous rough dark timber planks filling every edge; exactly one object, zero people",
            "Tang command compound solid plaster alcove, 667 AD",
        ),
        (
            r"당나라\s*황제.*평양성을\s*부수기.*모든\s*힘",
            "exactly one adult male Emperor Gaozong directing the Pyongyang campaign, his hair knot fully covered by a black cloth futou headwrap",
            "Emperor Gaozong wears one clearly visible soft low black cloth futou headwrap fully enclosing his crown and tied hair while he leans over one plain timber table and points his empty right index finger directly at one solid three-dimensional unpainted rammed-earth terrain relief with raised fortress walls and recessed roads; its earth surfaces stay blank and unmarked, his left hand stays open beside his waist, exactly one complete adult body against continuous blank plaster walls",
            "windowless undecorated Chang'an Tang campaign room, 668 AD",
        ),
        (
            r"하늘을\s*새까맣게.*불화살.*성벽\s*너머",
            "parallel Tang fire arrows descending over Pyongyang ramparts",
            "Wide upward exterior view of dozens of separate small fire arrows descending in the same steep diagonal direction across a smoke-black night sky above one low sloped stone-and-earth Pyongyang rampart and timber parapet; every arrow remains thin and distant with a small flame at its rear, no people and no oversized foreground projectile",
            "Pyongyang Fortress outer rampart, 668 AD",
        ),
        (
            r"총사령관.*둘째\s*남건.*목숨.*항전",
            "exactly one adult Goguryeo commander Namgeon directing the defense",
            "Namgeon braces alone on one low Pyongyang rampart in fitted iron lamellar over a buttonless wrap-front robe, broad cloth sash, loose trousers, calf wraps and wrapped shoes; one shallow segmented iron cap with radial plate seams protects his tied hair, his empty right arm commands defenders beyond frame and his left hand grips the timber parapet, one sheathed guardless ring-pommel sword at his hip",
            "Pyongyang Fortress inner rampart, 668 AD",
        ),
        (
            r"빗발치는\s*화살.*직접\s*성벽을\s*오가며\s*지휘",
            "exactly one adult armored Namgeon running past three embedded arrows",
            "Namgeon runs alone on a timber rampart in rust-brown lamellar and a segmented iron cap while exactly three straight arrows are embedded arrowhead-first in the far-left timber parapet, with only three shafts and one rear fletching set per shaft visible clear of his body",
            "open Pyongyang Fortress rampart, 668 AD",
        ),
        (
            r"배신자\s*형.*끔찍한\s*분노.*지탱",
            "one adult Goguryeo commander Namgeon in a tight rage portrait",
            "Tight head-and-shoulders portrait of Namgeon with tied black hair, an angular middle-aged East Asian face, dark brown natural eyes, soot, clenched jaw and controlled rage; his neck stays straight between both shoulders, the collar of fitted lamellar and a buttonless wrap-front robe remains visible against opaque charcoal smoke",
            "Pyongyang Fortress rampart, 668 AD",
        ),
        (
            r"군민들.*최후의\s*순간.*활시위",
            "exactly one adult Goguryeo archer in the instant after release",
            "One waist-up side-profile Goguryeo archer wears fitted lamellar and one segmented iron cap; his forward hand holds exactly one recurved bow fully extended while his rear hand recoils open beside his cheek and the empty bowstring snaps forward, exactly two visible hands, zero visible projectiles, no quiver or spare shafts",
            "open Pyongyang Fortress rampart, 668 AD",
        ),
        (
            r"식량은\s*바닥.*부상자.*생지옥",
            "exactly three starving and wounded adult Goguryeo defenders and civilians",
            "Exactly three separated adults remain inside a completely empty smoke-dark granary, one seated Goguryeo defender at left has one broad off-white cloth bandage wrapped around his left forearm, one gaunt middle-aged woman stands at center and one exhausted elderly man kneels at right, exactly six visible empty hands remain anatomically connected, exactly one empty woven basket and exactly one overturned empty clay bowl lie apart on bare packed earth, and every wall shelf is bare with zero grain kernels or grain piles anywhere",
            "completely empty besieged Pyongyang granary interior, 668 AD",
        ),
        (
            r"국운이\s*완전히\s*기울.*신성.*음모",
            "object-only Sinseong plot evidence with zero people",
            "One walnut-sized beige soft cloth pouch has one gathered neck and one short tied hemp cord; one broad undyed hemp sash passes in front of it and covers its entire lower half across one folded monastic robe on warm amber-lit medium-brown timber; no people, body parts, writing or food",
            "warm timber tabletop inside Pyongyang north-gate passage, 668 AD",
        ),
        (
            r"신성과\s*그\s*무리.*성문의\s*빗장.*풀",
            "exactly two adult men, monk Sinseong and one tied-haired male Goguryeo accomplice carrying one fully removed gate beam",
            "Frontal waist-up night view against vertical gate planks, shaved-head Sinseong at left and one angular-faced tied-haired male Goguryeo accomplice at right carry the sole fully removed timber locking beam horizontally at chest height, exactly two visible hands total grip opposite beam ends with one hand from each adult while both far arms remain fully hidden behind their own torsos outside the frame, and a wide clear vertical air gap separates the beam from two empty U-shaped iron wall brackets mounted below it",
            "windowless Pyongyang north-gate interior, 668 AD",
        ),
        (
            r"700년.*제국의\s*문.*허무하게\s*열",
            "one massive Pyongyang timber gate opening into the enemy night",
            "Zero-person interior view of one massive studded timber double gate opened only into one narrow vertical gap where pitch-black night and hostile orange firelight enter, while exactly one removed locking beam lies fully inside on smoke-dark packed earth and blank vertical planks with earthen walls fill every edge",
            "windowless Pyongyang north-gate interior, 668 AD",
        ),
        (
            r"짐승처럼\s*밀려드는\s*적군.*아수라장",
            "exactly one adult Goguryeo defender overwhelmed by the breached gate",
            "Tight low-angle three-quarter view of one rust-brown lamellar Goguryeo defender crouching behind exactly one cracked tall oval timber shield, both shoulders recoil and his terrified face turns toward a dense surge of charcoal smoke, orange torchlight and airborne packed-earth dust rushing inward through the breached gate behind him, hostile pressure is shown only by smoke, light and dust while the complete frame contains exactly one adult, one shield and zero visible weapons or enemy silhouettes",
            "smoke-dark blank inner breach of Pyongyang, 668 AD",
        ),
        (
            r"믿었던\s*자의\s*배신.*남건.*끝났음을\s*깨닫",
            "exactly one adult Goguryeo commander Namgeon realizing defeat",
            "Namgeon stands alone in a burned courtyard wearing rust-brown fitted Goguryeo lamellar whose entire chest is covered by continuous uninterrupted rows of identical small iron lames from collar to sash over a buttonless wrap-front robe, both open empty hands hang lowered beside his slumped body, his shocked face turns toward distant Tang spear silhouettes behind the breached gate, and completely bare packed earth around his wrapped boots contains zero weapons",
            "Pyongyang Fortress inner courtyard, 668 AD",
        ),
        (
            r"쏟아지는\s*적군.*남건.*피눈물",
            "one adult Goguryeo commander Namgeon watching the breached gate",
            "Strict near-frontal head-and-shoulders view of Namgeon with his face turned less than ten degrees so both dark brown eyes and both full cheeks are equally visible, exactly one glossy wet narrow dark-red tear trail begins directly beneath his left lower eyelid and exactly one matching trail begins directly beneath his right lower eyelid before both flow separately down the cheeks and stop above the jaw, his forehead and skin have zero cuts or scars, his rust-brown lamellar collar and natural neck remain coherent while both hands stay outside the crop and opaque smoke fills every edge",
            "Pyongyang Fortress inner courtyard, 668 AD",
        ),
        (
            r"동북아시아를\s*호령.*고구려\s*왕.*비참.*최후",
            "one palm-sized Goguryeo gilt-bronze royal diadem ornament plate split into two halves",
            "Object-only straight-down macro view of one palm-sized flat gilt-bronze flame-shaped royal diadem ornament plate snapped once down its center into exactly two matching halves, the left half and right half lie flat with jagged matching break edges facing across one narrow gap, each half carries one part of the same simple rounded flame silhouette, and featureless cold rain mud fills every edge with zero band, ring, crown, people or buildings",
            "featureless cold rain mud in fallen Pyongyang, 668 AD",
        ),
        (
            r"거리마다\s*붉은\s*피.*궁궐.*거대한\s*불길",
            "burning Pyongyang palace street with a dark-red runoff stream",
            "Wide zero-person night view down one textless timber palace street as connected roof beams and wooden halls burn on both sides; one narrow irregular dark-red runoff stream crosses packed earth between ash and broken roof tiles, black smoke and orange fire fill every edge without signs, banners or writing",
            "burning Pyongyang palace district, 668 AD",
        ),
        (
            r"나라를\s*잃은\s*백성.*짐승보다\s*못한.*밑바닥",
            "one cangue-bound Goguryeo captive",
            "Exactly one adult Goguryeo captive kneels in cold mud wearing one rectangular timber neck cangue; his connected head and neck pass through its single centered opening and both hands stay hidden beneath the board",
            "featureless cold mud outside fallen Pyongyang, 668 AD",
        ),
        (
            r"매국노들의\s*삶은\s*어땠",
            "Tang rewards laid over discarded Goguryeo allegiance",
            "Straight-down object-only: exactly one face-down blank-backed square bronze Tang rank seal sits immediately above the jagged torn center of exactly one long narrow grey Goguryeo rank sash with exactly two frayed ends; clean dark timber fills the frame with zero garment, robe, folded cloth bundle, duplicate sash, people or writing",
            "Tang-held Liaodong residence, 668 AD",
        ),
        (
            r"적국의\s*관리가\s*되어\s*동포를\s*짓밟",
            "one blank-backed Tang rank seal block pinning one torn Goguryeo sash in mud",
            "Object-only straight-down macro: exactly one palm-sized heavy square bronze Tang rank seal rests face-down with its smooth completely blank back visible and directly pins the torn center of exactly one long grey woven Goguryeo rank sash into freezing mud; the sash extends left and right from beneath the block, while featureless mud fills every edge with zero seal-face glyph, paper, shoe, foot, leg, person or writing",
            "Tang-held Liaodong fortress ground, 668 AD",
        ),
        (
            r"황제.*죽음을\s*슬퍼.*3일.*조정\s*문",
            "one completely closed blank Tang court gate",
            "Zero-person tight frontal close-up of one completely closed plain Tang timber court gate: the two central adze-hewn plank leaves and their narrow closed seam fill every edge, with one plain iron ring pull on each leaf and zero doorway gap, side wing, roof, signboard, plaque, window, bowl, lamp, flame, smoke, person or writing",
            "Chang'an Tang court entrance, 679 AD",
        ),
        (
            r"5품\s*이상.*고위\s*관료.*국장급\s*장례",
            "one fully shrouded Tang funeral coffin under one plain hemp mourning canopy",
            "Object-only funeral close-up: exactly one plain hemp mourning canopy fills the upper half above exactly one long coffin fully covered by one plain undyed hemp shroud filling the lower half; packed earth only at frame edge, zero wall, cap, person, prop or writing",
            "Chang'an Tang funeral courtyard, 679 AD",
        ),
        (
            r"수백만\s*대군도\s*못\s*뚫은\s*철벽.*내부의\s*탐욕",
            "one Goguryeo gate beam split from inside by abandoned rank seals",
            "Object-only interior macro: exactly one massive horizontal Goguryeo timber gate beam splits outward from one rotten center notch, with exactly two small face-down blank-backed bronze rank seals wedged separately in the broken fibers; intact stone-and-earth wall and packed earth fill every edge, with zero chain, gear, person, signboard or writing",
            "Pyongyang Fortress inner gate, 668 AD",
        ),
        (
            r"압도적인\s*무력.*내부가\s*곪아\s*터진\s*제국",
            "one intact Goguryeo sword beside one rotten broken gate beam",
            "Object-only close view of exactly two separate artifacts on smoke-dark packed earth: one intact short straight guardless ring-pommel iron sword lies at left while one thick gate beam at right has split open around black internal rot; the weapon remains flawless but the structural timber has failed from within, zero people and no white background",
            "ruined Pyongyang inner gate, 668 AD",
        ),
        (
            r"처참한\s*몰락.*오늘날.*서늘한\s*경고",
            "one fresh green sprout emerging through a cracked blank Goguryeo rank seal",
            "Object-only low close view of one small fresh green sprout emerging through the center crack of one face-down blank bronze Goguryeo rank seal half-buried in cold ash; charred timber and packed earth fill every edge, the warning remains physical and historical with zero people, footwear or modern objects",
            "Pyongyang Fortress aftermath at cold dawn, 668 AD",
        ),
        (
            r"내부의\s*썩은\s*뿌리.*희망찬\s*미래",
            "one black-rotted root mass beneath a collapsed Goguryeo command floor",
            "Object-only cutaway-like close view of thick black-rotted tree roots splitting the underside of one collapsed timber command floor from within; one face-down blank bronze rank seal and broken mortised beam lie above, while dead soil and charred wood fill every edge with zero people or writing",
            "fallen Pyongyang command hall, 668 AD",
        ),
        (
            r"역사의\s*심판.*오만함.*서늘한\s*법정",
            "one empty Goguryeo command dais collapsing under a charred roof beam",
            "Object-only low view of one empty low timber command dais collapsing under one fallen charred mortised roof beam while exactly one face-down blank bronze rank seal splits at the impact point; packed earth, smoke and burned timber fill every edge with zero people, blades or writing",
            "fallen Pyongyang audience hall, 668 AD",
        ),
        (
            r"국가의\s*영광\s*아래\s*짓밟힌.*백성의\s*삶",
            "powerless civilian belongings crushed beneath one palace beam",
            "Object-only close view of exactly three mismatched worn wrapped-cloth shoes and one folded mud-dark hemp shroud pinned beneath one fallen gilt-edged mortised palace beam; ash and smoke-dark packed earth fill every edge, restrained dark-red stains remain small and no people, letters or modern objects appear",
            "Pyongyang palace district aftermath, 668 AD",
        ),
        (
            r"영웅\s*찬가\s*뒤.*핏빛\s*흑막",
            "one torn blank victory curtain exposing betrayal evidence",
            "Object-only close evidence view of one torn unmarked ochre silk victory curtain pulled aside across dark packed earth to expose exactly one freshly severed gate rope and one short straight guardless iron dagger in a restrained dark-red stain; all three objects remain separate, zero people and no writing",
            "Pyongyang inner-gate evidence ground, 668 AD",
        ),
        (
            r"제국의\s*그림자.*동아시아\s*대지",
            "long Tang army shadows crossing a ruined Goguryeo road",
            "Wide historical landscape of one distant orderly Tang infantry column moving along a ridge while their long human and spear shadows cross a ruined packed-earth road below, passing three empty low segmented Goguryeo iron cap helmets with radial plate seams and burned timber homes; no dragon, fantasy creature or modern soldier",
            "Liaodong road after Goguryeo's fall, 668 AD",
        ),
        (
            r"30화.*지켜봐\s*주셔서\s*감사",
            "one blank Goguryeo standard completing its collapse into ash",
            "Object-only quiet closing view of one unmarked solid-ochre Goguryeo hemp standard collapsed from one snapped plain timber pole into cold grey ash at dawn; only one charred cloth edge holds a faint final ember while smoke and ruined packed earth fill every edge, zero people and no symbols",
            "Pyongyang Fortress aftermath at dawn, 668 AD",
        ),
        (
            r"역사는\s*승자의\s*것.*패자의\s*피와\s*비명",
            "one blood-stained Goguryeo ring-pommel sword on cold ash",
            "Object-only close view of exactly one short straight guardless Goguryeo iron sword with one plain ring pommel resting across cold grey ash and broken shield planks; one restrained dark-red stain marks the blade, small embers glow beneath, and no katana guard, curved blade, writing or people appear",
            "Pyongyang battlefield aftermath, 668 AD",
        ),
        (
            r"승리의\s*이면.*지배층.*권력욕",
            "exactly one greedy adult Goguryeo court elite clutching a command seal",
            "Exactly one adult Goguryeo court elite in fitted lamellar over a buttonless wrap-front robe pulls one face-down blank bronze command seal toward his chest with exactly two coherent hands while the open inner gate burns behind him; tied black hair, wrapped shoes and a hard greedy expression remain visible against blank smoke-dark walls",
            "Pyongyang Fortress inner court, 667 AD",
        ),
        (
            r"영웅담의\s*포장지.*잔혹한\s*핏빛\s*진실",
            "blank heroic record slips burning beside period casualty gear",
            "Object-only close evidence view of exactly three face-down blank hardwood heroic record slips burning in one low bronze brazier beside one dented low segmented Goguryeo iron cap helmet with radial plate seams, one worn wrapped-cloth shoe and one snapped straight spear shaft; packed earth fills every edge with no book pages, modern shoes or writing",
            "Goguryeo fortress record room after battle, 668 AD",
        ),
        (
            r"살아남은\s*자가\s*정의를\s*독점",
            "one intact Tang rank seal placed above one shattered Goguryeo rank seal",
            "Object-only low close view of exactly two face-down blank bronze rank seals on smoke-dark packed earth: one intact Tang square seal stands on a dry raised threshold above while one shattered Goguryeo seal lies in dark-red mud below; a severed grey sash crosses only the broken lower seal, zero people, coins, glyphs or writing",
            "Tang-held Liaodong registry threshold, 668 AD",
        ),
        (
            r"지배층의\s*탐욕이\s*낳은.*파국",
            "one fallen plain roof beam above exactly three cracked clay grain bowls",
            "Still object-only aftermath view of one heavy plain unmarked mortised roof beam resting across exactly three separate cracked shallow clay grain bowls on smoke-dark packed earth; ash fills every edge and zero people, bodies, hands, baskets, plaques, seals, metal marks, symbols or writing appear",
            "Pyongyang command district aftermath, 668 AD",
        ),
        (
            r"환상을\s*버리고.*패배의\s*역사.*해부",
            "one broken Goguryeo ring-pommel sword beside one severed rank sash",
            "Object-only straight-down evidence view on edge-to-edge dark timber: exactly one short straight guardless ring-pommel iron sword lies broken once into two separated pieces beside exactly two halves of one severed grey Goguryeo rank sash; one clear central gap exposes the floor, no mat, basket weave, extra blade, text or person",
            "Goguryeo court evidence table, 668 AD",
        ),
        (
            r"비극적인\s*핏빛\s*역사.*다시\s*반복.*막",
            "one newly secured Goguryeo gate beam beside the discarded severed rope",
            "Object-only frontal view of one thick new timber locking beam seated fully inside two intact iron wall brackets across a closed vertical-plank gate; one short severed old rope lies outside the brackets on packed earth, blank wallboards fill every edge and zero people, writing or modern hardware appear",
            "rebuilt Goguryeo inner gate, late 7th century",
        ),
        (
            r"잊혀진\s*패자들의\s*비명.*귀\s*기울",
            "exactly three wounded Goguryeo refugees abandoned after battle",
            "Exactly three wounded adult Goguryeo refugees reach with empty hands toward one retreating open timber supply cart through snow and mud, their bodies separated in depth, torn buttonless wrap-front hemp clothing, wrapped shoes and grief-stricken faces visible; low segmented helmets with radial seams lie abandoned, with no speech text or callouts",
            "Liaodong battlefield aftermath, 668 AD",
        ),
        (
            r"차가운\s*잿더미.*진짜\s*역사의\s*민낯",
            "one cracked blank Goguryeo rank seal half-buried in cold ash",
            "Object-only straight-down close view of exactly one cracked face-down blank bronze Goguryeo rank seal and one short charred grey sash half-buried in pale cold ash; no flame remains, fine ash fills every edge and no blood pool, stone slab, rain, writing or person appears",
            "Pyongyang Fortress cold ash field, 668 AD",
        ),
        (
            r"동아시아의\s*피바람.*전쟁은\s*아직\s*끝나지",
            "ordered Tang columns advancing toward another storm-covered fortress",
            "Wide historical view of three orderly Tang infantry columns in fitted dark lamellar advancing across muddy open ground toward one distant low timber-and-earth fortress under a real storm front; separate straight spears, plain standards, windblown smoke and lightning remain period grounded, with no modern uniforms, maps or fantasy symbols",
            "Liaodong road after Pyongyang, late 7th century",
        ),
        (
            r"제국의\s*멸망.*외적보다\s*내부의\s*탐욕",
            "an intact outer wall above one command beam crushing a civilian home",
            "Wide zero-person physical view: one intact sloped Goguryeo stone-and-earth outer wall stands across the upper frame while inside it one fallen mortised command-hall beam bearing one face-down blank bronze rank seal crushes a small timber civilian home below; smoke and broken grain bowls show the internal cause without an attacking army",
            "Pyongyang Fortress inner settlement, 668 AD",
        ),
        (
            r"권력\s*정치의\s*섭리",
            "exactly two adult Goguryeo court elites plotting betrayal",
            "Exactly two adult Goguryeo court elites stand apart in one blank smoke-dark corridor: the left official faces away while studying three unmarked hardwood fortress key blocks, and the right noble hides exactly one short straight guardless iron dagger behind his own back with one hand while his other hand stays empty; fitted lamellar, buttonless robes and four grounded legs remain coherent",
            "Pyongyang Fortress court corridor, 666 AD",
        ),
        (
            r"환상에서\s*깨어나\s*핏빛\s*역사.*직시",
            "exactly one middle-aged wounded Goguryeo witness facing the viewer",
            "One middle-aged wounded Goguryeo witness with tied-back black hair and short stubble turns toward the viewer in a tight head-and-shoulders portrait; natural dark-brown eyes, soot, grief and one restrained cheek stain remain clear, his neck aligns naturally between both shoulders while one ruined blank timber gate burns behind him, no modern haircut or additional person",
            "Pyongyang Fortress aftermath, 668 AD",
        ),
        (
            r"한밤중.*평양성의\s*북쪽\s*문.*그림자",
            "exactly two adults: monk Sinseong and one Goguryeo accomplice",
            "Featureless vertical gate planks fill every background edge of a tight windowless night interior as shaved-head Sinseong and one Goguryeo accomplice creep in separate crouched body slots under one shielded bronze oil dish, exactly two complete adults and four coherent hands",
            "windowless Pyongyang north-gate interior passage, 668 AD",
        ),
        (
            r"포로로\s*끌려간\s*보장왕과\s*남건.*장안",
            "exactly two adults: captive King Bojang and wounded Namgeon",
            "Captive King Bojang kneels on both knees at lower left in one muted deep-grey buttonless wrap-front royal robe while wounded Namgeon kneels on both knees at lower right in torn rust-brown Goguryeo lamellar over a muted-grey wrap-front robe, both men face forward with exactly four visible empty hands resting separately on their own thighs, exactly two complete adult bodies stay below one uninterrupted blank plaster wall, and bare packed earth contains zero objects, weapons, paper or packets",
            "Chang'an Tang captive courtyard, 668 AD",
        ),
        (
            r"둘째\s*남건.*중국\s*변방.*유배",
            "exactly one adult exiled Goguryeo commander Namgeon",
            "Exactly one wounded Namgeon walks alone through a freezing Tang frontier pass in a torn plain hemp robe, one complete body, both empty hands and no escort visible",
            "Tang western frontier exile road, late 7th century",
        ),
        (
            r"679년.*남생.*46세.*죽",
            "exactly one adult deceased Yeon Namsaeng on blank dark silk",
            "Direct overhead edge-to-edge face-only mortuary close-up: Namsaeng's slack face fills frame on featureless dark silk, both eyelids fully shut with zero iris or pupil, exactly zero visible hands or forearms, short tied black hair with grey temples; dark shroud reaches the jawline, with zero room, wall, panel, screen, lantern, furniture or writing",
            "blank dark silk mortuary surface, Luoyang, 679 AD",
        ),
        (
            r"환상에서\s*깨어나.*고대인들의\s*무자비한\s*투쟁",
            "exactly one adult Goguryeo survivor facing the viewer",
            "Exactly one adult Goguryeo survivor faces the viewer in a tight head-and-shoulders portrait, tied black hair, one natural neck, soot and grief on an angular East Asian face, natural dark-brown irises with small orange fire reflections only, and no additional people",
            "Pyongyang Fortress aftermath, 668 AD",
        ),
        (
            r"조국을\s*버리고.*이세적.*내통",
            "exactly two adults: monk Sinseong and one Tang military messenger",
            "Shaved-head Sinseong in an undyed buttonless wrap-front robe passes exactly one small soft unmarked cloth packet to one Tang military messenger wearing fitted dark iron lamellar over a closed round-collar robe and one low conical iron helmet; exactly two separate adult bodies and four coherent hands face each other across a narrow torchlit drainage passage with blank stone and timber",
            "Pyongyang Fortress outer drainage passage, 668 AD",
        ),
        (
            r"목숨은\s*질겼고.*사로잡",
            "exactly one wounded captured Goguryeo commander Namgeon bound around the chest",
            "Tight chest-up frontal view of wounded Namgeon alone in continuous rust-brown Goguryeo lamellar rows over a muted-grey buttonless wrap-front robe, one continuous thick undyed hemp rope wraps three clearly visible horizontal turns around his chest and both upper arms and compresses them against his torso, one shared knot sits at his left side, one restrained dark-red wound stain marks his left cheek and shoulder, both hands remain below the lower crop, and opaque charcoal smoke plus one blank earthen wall fill every edge with zero bars, guards, weapons, buildings, signs or writing",
            "blank smoke-dark Pyongyang capture wall, 668 AD",
        ),
        (
            r"보장왕.*이세적.*항복",
            "exactly two adults: kneeling King Bojang and standing Tang general Li Ji",
            "Tang general Li Ji stands upright at upper right in fitted dark iron lamellar over one smooth closed round-collar robe with one close-fitting low conical riveted iron helmet, a narrow flush brow band and zero projecting brim, both empty hands hang beside his hips, King Bojang kneels on both knees at lower left in one muted deep-grey buttonless wrap-front royal robe with both open palms flat on bare packed earth, exactly four visible empty hands and exactly two separate complete adult bodies form a clear high-low surrender hierarchy against one smoke-dark blank earthen wall, and the complete frame contains zero weapons, packets, paper, buildings, signs or writing",
            "blank smoke-dark Pyongyang surrender ground, 668 AD",
        ),
        (
            r"권력자의\s*오만.*힘없는\s*백성.*생지옥",
            "exactly three injured adult Goguryeo civilians in a burning exterior alley",
            "Exactly three injured Goguryeo civilians crawl through a smoke-filled exterior alley in separated left, center and right body slots, torn soot-dark hemp robes, wrapped shoes, strained faces, small dark-red stains, burning debris and one blank collapsed timber wall make the danger visible",
            "burning Pyongyang exterior alley, 668 AD",
        ),
        (
            r"낭만을\s*걷어낸.*진짜\s*역사",
            "one adult Goguryeo survivor pulling down a luxurious court curtain",
            "One middle-aged adult Goguryeo survivor with tied black hair pulls one completely unmarked torn silk court curtain aside with exactly two coherent hands to expose burned timber homes and three abandoned low segmented iron cap helmets with radial plate seams beyond it; one complete body, blank walls and no painted image, calligraphy, sign or modern helmet",
            "Fallen Pyongyang palace district, 668 AD",
        ),
        (
            r"텅\s*빈\s*옥좌.*백성.*쓰러",
            "exactly one adult anonymous fallen Goguryeo soldier before an empty command seat",
            "Exactly one anonymous adult Goguryeo soldier lies on his back on packed earth in the foreground while an empty low wooden command seat stands inside the ruined hall behind him; his body has exactly one head, one torso, two connected arms, exactly two visible hands placed apart, two connected legs and a natural neck, with no hidden third limb, foreign desert or additional person",
            "Fallen Pyongyang audience hall, 668 AD",
        ),
        (
            r"권력욕이\s*빚어낸\s*거대한\s*비극.*고구려의\s*마지막",
            "abandoned Goguryeo command equipment after the final collapse",
            "Object-only wide view of one overturned low ruler seat, exactly three dented low segmented Goguryeo iron cap helmets with radial plate seams, cracked oval layered-timber shields, snapped straight spear shafts and severed red rank cords across a burned fortress court; zero people, writing or modern bowl helmets",
            "Pyongyang Fortress aftermath, 668 AD",
        ),
        (
            r"잿더미\s*위에서\s*살아남으려는\s*자들의\s*처절한\s*사투",
            "one heavily scarred Goguryeo survivor facing an unseen enemy line",
            "One heavily scarred Goguryeo survivor braces alone behind a cracked timber shield while a wall of spear shadows stretches across smoke ahead, one complete body and no other visible people",
            "Pyongyang Fortress breach, 668 AD",
        ),
        (
            r"성문이\s*열리자.*당나라\s*정예병",
            "exactly two adult Tang assault infantry, left shield-bearer and right spear-bearer at Pyongyang gate",
            "Left Tang shield-bearer braces one oval timber shield with both hands, right Tang spear-bearer grips one upright straight spear with both hands, both wear fitted iron lamellar and surge through a narrow gate gap lit by firelight from outside",
            "windowless Pyongyang north-gate interior breach, 668 AD",
        ),
        (
            r"명예로운\s*죽음을\s*스스로\s*택",
            "one adult Goguryeo commander Namgeon choosing death before capture",
            "Namgeon alone drops to one knee before one blank smoke-dark earthen wall wearing rust-brown fitted Goguryeo lamellar over a buttonless wrap-front robe, his right hand grips exactly one short straight single-edged guardless iron dagger with one handle and one blade held horizontally toward the center gap of his own armor with a clear finger-width air gap before contact, his empty left palm presses packed earth, no sword, scabbard or second weapon appears, and opaque smoke fills every background edge with zero building facade, signboard, door or window",
            "blank smoke-filled Pyongyang inner courtyard wall, 668 AD",
        ),
        (
            r"자신의\s*심장을\s*향해.*칼날",
            "one wounded adult Goguryeo commander Namgeon",
            "Namgeon collapses onto one knee after driving one short straight iron dagger into a gap in his own lamellar chest armor, his free hand flat on packed earth, one complete body and one restrained dark blood stain",
            "Pyongyang Fortress inner courtyard, 668 AD",
        ),
        (
            r"성\s*안으로\s*쏟아진\s*당나라\s*군대.*도살",
            "exactly three adults: two standing Tang infantry and one prone Goguryeo defender",
            "Only three adults fill a tight smoke-dark alley: two standing Tang infantry with one shield and one spear flank one prone Goguryeo defender against a blank charred wall",
            "tight smoke-dark Pyongyang inner alley, 668 AD",
        ),
        (
            r"화려한\s*문화를\s*꽃피.*평양성.*약탈.*파괴",
            "one uninscribed Goguryeo bronze mirror with one deep center split",
            "Object-only straight-down macro view of exactly one palm-sized thin flat round handleless cast-bronze mirror disk centered on fine grey ash, the disk remains one single circular object while exactly one deep jagged crack runs continuously from its top rim through the center to its bottom rim and visibly opens into one narrow dark fissure, the blank bronze surface carries soot and fire damage, tiny orange embers fill every edge, and zero second disk, raised rim, handle, people, buildings or writing appear",
            "bare ash floor in ruined Pyongyang, 668 AD",
        ),
        (
            r"영광스러운\s*고구려의\s*역사.*피비린내.*막을\s*내리",
            "one charred blank Goguryeo war banner falling from a snapped pole",
            "Object-only low close view of one unmarked ochre hemp banner sliding from one snapped plain timber pole into dark-red rain mud with one charred outer edge, zero people",
            "bare Pyongyang fortress ground, 668 AD",
        ),
        (
            r"지도층이\s*탐욕에\s*눈이\s*멀.*안에서부터\s*썩",
            "one plain unglazed Goguryeo grain jar ruptured open by black-green rot",
            "Object-only straight-on close view on continuous packed earth: exactly one large plain unglazed storage jar keeps one intact rim and intact side silhouette while one jagged front rupture exposes thick black-green mold, wet rot and clumped spoiled millet contained inside the jar; zero loose grain mound, shelf, room, people or writing",
            "bare packed-earth Goguryeo granary ground, 667 AD",
        ),
        (
            r"강대국의\s*무자비한\s*침략.*내부의\s*분열과\s*배신",
            "exactly one exhausted adult Goguryeo defender beside a freshly severed inner-gate rope",
            "One exhausted Goguryeo defender kneels alone inside the breached gate, gripping one split oval timber shield with his left hand while his empty right hand reaches toward one freshly severed gate rope on the ground, hostile torchlight enters through the open gap behind his solitary body",
            "smoke-dark Pyongyang inner-gate passage, 668 AD",
        ),
        (
            r"국가를\s*장기말처럼\s*버린\s*지배층",
            "one discarded cracked Goguryeo fortress tally beneath two intact elite rank fittings, both rectangular bronze belt plaques",
            "Object-only low view across one command-table edge: exactly two matching flat solid rectangular bronze belt plaques with closed faces and no holes sit apart on the tabletop above while one palm-sized cracked blank hardwood tally lies alone in ash below; all three objects remain isolated, zero people",
            "smoke-dark Goguryeo command room floor, 667 AD",
        ),
        (
            r"권력이라는\s*괴물.*삼켜진\s*제국",
            "one empty Goguryeo ruler seat crushed beneath a fallen command beam",
            "Object-only low view of one empty dark timber ruler seat pinned under one fallen mortised roof beam as black smoke fills a ruined hall, zero people",
            "ruined Pyongyang command hall, 668 AD",
        ),
        (
            r"무너진\s*평양성\s*잔해.*이름\s*없는\s*자들의\s*피눈물",
            "exactly three empty segmented Goguryeo iron cap helmets buried in mud",
            "Object-only ground view of exactly three empty low segmented iron cap helmets built from visible radial plates and riveted brow bands, two retaining short corded lamellar neck guards; they lie separately beside broken layered-timber shields and snapped straight spear shafts in cold mud beneath collapsed Pyongyang wall rubble, zero people",
            "Besieged Pyongyang Fortress rubble, 668 AD",
        ),
        (
            r"패자는\s*흔적도\s*못\s*남기고.*강자만\s*살아남",
            "one palm-sized scorched empty hemp identity pouch unraveling into ash",
            "Object-only close view: more than half of one small soft wrinkled plain-hemp drawstring pouch with a puckered mouth has collapsed into grey ash and loose blackened fibers; only one limp cloth edge and one short thin cut drawcord remain in orange embers, charcoal fills every edge, zero people",
            "open charcoal debris in fallen Pyongyang, 668 AD",
        ),
        (
            r"승자의\s*기록\s*속에\s*숨은\s*패자의\s*핏물",
            "exactly one adult Tang officer crushing one face-down blank-backed Goguryeo record-slip bundle",
            "The flat underside of one complete Tang officer's right wrapped boot visibly overlaps and presses the center of one face-down cord-tied hardwood record-slip bundle into mud while both empty hands stay behind his back; plain reverse wood grain faces the camera, fitted iron lamellar covers a dark round-collar robe above a plain cloth sash, loose trousers and one conical iron helmet",
            "smoke-dark Liaodong battlefield ground, 668 AD",
        ),
        (
            r"낡은\s*위인전을\s*찢어버린.*잔혹한\s*생존기",
            "exactly three separated face-down blank hardwood heroic record slips",
            "Object-only straight-down close view of exactly three rectangular plain-backed hardwood slips lying parallel with wide gaps on fine pale-grey ash; exactly one slip has one clearly blackened missing corner with tiny orange embers along that break, uninterrupted ember-flecked ash fills every edge, zero cord, rope, knot, rocks, border or people",
            "bare smoke-dark Pyongyang ash floor, 668 AD",
        ),
        (
            r"역사의\s*차가운\s*메스.*권력의\s*환상",
            "one short straight iron utility knife between two separated halves of one red hemp cord",
            "Object-only straight-down close view of one complete short straight single-edged iron knife resting vertically in a clear gap between exactly two separate red hemp cord halves, the two frayed cut ends face each other without touching, one cord half lies left and one lies right on rough timber, zero people",
            "Goguryeo court evidence table, 668 AD",
        ),
        (
            r"당나라\s*군대.*서적과\s*보물.*불태",
            "one blank wood-slip bundle overlapping one blank bronze plaque inside the same fire",
            "Object-only straight-down macro view of exactly one compact face-down blank-backed hardwood record-slip bundle centered on warm packed earth and exactly one small thin flat blank bronze treasure plaque tucked partly beneath its lower-right edge with half the plaque still visible, one connected bright orange fire visibly surrounds the lower half of the combined stack and directly touches both wood and bronze, both objects have blackened scorched edges and glowing embers on their surfaces, warm medium-brown firelit earth fills all four outer edge strips, and zero stones, people, soldiers, helmets, buildings, roofs, boxes, vessels, paper, ink marks or writing appear",
            "bare burned archive ground in Pyongyang, 668 AD",
        ),
        (
            r"수만\s*명.*포승줄.*노예",
            "exactly three bound adult Goguryeo civilians",
            "Exactly three exhausted adult Goguryeo civilians walk in separate side profiles with one short rope linking only their paired wrists, three complete bodies and six wrapped shoes visible while the rope continues beyond the frame without additional people",
            "Pyongyang Fortress north road, 668 AD",
        ),
        (
            r"이세적.*축배",
            "one adult Tang general Li Ji raising a victory cup",
            "Tang general Li Ji stands alone in fitted iron lamellar and a soft low black futou, raising exactly one shallow bronze cup in his right hand above one otherwise empty low timber table; his cold triumphant face, empty left hand and coherent body remain clear against blank walls, with no paper, packet, book or second vessel",
            "Chang'an Tang military residence, 668 AD",
        ),
        (
            r"당\s*황제\s*앞에서.*굴욕",
            "Emperor Gaozong confronting kneeling King Bojang",
            "Exactly four visible hands total; two separated men face a blank wall: black-capped Gaozong stands right in a dark smooth-front Tang paofu with one closed round collar and zero visible fasteners, both empty hands at his sides; grey-robed Bojang kneels left with both empty hands separately on his thighs",
            "blank plaster wall in Chang'an, 668 AD",
        ),
        (
            r"반역자\s*신성.*부귀영화",
            "one adult shaved-head Goguryeo monk Sinseong living in Tang luxury",
            "Shaved-head Sinseong sits alone in a clean high-quality undyed silk monastic robe at a low Tang table with one shallow bronze cup, glazed food bowls and folded silk behind him, one complete body and a cold satisfied expression",
            "Chang'an Tang residence, late 7th century",
        ),
        (
            r"남생.*최고의\s*대우",
            "one adult Yeon Namsaeng in high-ranking Tang command dress",
            "Yeon Namsaeng stands alone in fitted Tang lamellar over a dark round-collar robe with one blank gilt-bronze rank seal at his belt, both empty hands visible and a cold proud face under hard side light",
            "Chang'an Tang military court, 668 AD",
        ),
        (
            r"배신을\s*정당화.*괴물",
            "one cracked bronze mirror reflecting one collaborator face",
            "Sharply narrowed predatory eyes, deeply clenched brows and clearly bared teeth form one hostile snarling East Asian collaborator face reflected inside exactly one handleless round polished-bronze mirror disk with one deep jagged crack; object-only tight frontal view, warped only by the crack, while blank dark timber fills every edge with zero real body, hands, second face, writing or supernatural horns",
            "Tang-held Liaodong residence, late 7th century",
        ),
        (
            r"충신은\s*유배지.*매국노.*번성",
            "a forgotten exile grave outside a prosperous Tang traitor household",
            "One low sealed convex earth grave mound covered by unbroken cold snow rises in the foreground left with zero opening, hole, pit, stone lining or marker, while a distant warm Tang residence doorway at background right reveals one empty low feast table set with exactly three shallow bronze cups; one continuous landscape contains zero people, skulls, medals or split panels",
            "Tang frontier exile ground, late 7th century",
        ),
        (
            r"도덕과\s*정의.*고대\s*정치",
            "an overturned Goguryeo ruler seat beside broken rank objects",
            "Object-only view of one overturned low Goguryeo ruler seat beside exactly two cracked face-down plain bronze rank seals with blank backs and two severed red cord ends in an empty smoke-dark court; packed earth and burned timber fill every edge without glyphs, writing or people",
            "Fallen Pyongyang court, 668 AD",
        ),
        (
            r"남생\s*가문.*북망산.*무덤",
            "one large late-seventh-century Mangshan rammed-earth burial mound",
            "Low wide object-only view with distant dark hills filling both upper corners and no open blank sky: one large rammed-earth burial mound fills the upper two-thirds with its crest near the top edge, while one long plain stone approach and low flush curb stones fill the lower third; dry grass reaches every side with zero upright marker, post, statue, building, belt fitting, caption, title, writing or people",
            "Mangshan burial ground near Luoyang, late 7th century",
        ),
        (
            r"당\s*황제에게\s*바친\s*충성.*권력",
            "one Tang rank seal and one severed Goguryeo sash at the Yeon family mound",
            "Straight-down object-only macro on featureless dry reddish earth: exactly one palm-sized thin flat face-down blank-backed weathered bronze Tang rank seal lies flat at upper center and exactly one severed dark-grey Goguryeo sash forms exactly two straight aligned halves below; dry earth fills every edge, with zero cord, wire, marker, writing or people",
            "Mangshan burial ground near Luoyang, late 7th century",
        ),
        (
            r"조국의\s*피눈물.*수치스러운\s*비석",
            "one unmarked burial marker above a severed Goguryeo rank sash",
            "Low-angle object-only view of one rough unmarked stone marker while a severed grey Goguryeo rank sash lies in red-clay rainwater at its base, dry grass bent by cold wind and no carved characters",
            "Mangshan burial ground near Luoyang, late 7th century",
        ),
        (
            r"외적의\s*침략만으로\s*무너지지",
            "an intact Goguryeo outer wall with unseen interior fire behind it",
            "Landscape-only wide exterior view with zero people: one continuous intact sloped Goguryeo fieldstone-and-rammed-earth outer wall spans the full frame while orange firelight and thick black smoke rise from the unseen interior directly behind it; zero breach, collapsed wall, visible building, roof, gatehouse, signboard, attacking army, mechanical gear or writing",
            "Goguryeo fortress district, 668 AD",
        ),
        (
            r"연개소문.*권력의\s*사유화",
            "one Goguryeo command seal bound inside a private family sash",
            "Straight-down object-only: exactly one single straight dark family sash with exactly two ends crosses horizontally over the center of exactly one solid closed face-down blank-backed square bronze Goguryeo command seal on rough timber; the ends exit left and right, with zero knot, loop, cutout, opening, tally, glyph, writing or people",
            "Pyongyang court evidence table, 665 AD",
        ),
        (
            r"내가\s*못\s*가질\s*나라.*잿더미",
            "exactly one adult Goguryeo noble abandoning a burning command hall",
            "One adult Goguryeo noble turns away after dropping one torch onto a collapsed command table, his complete body silhouetted against spreading floor fire, broken rank seals and an empty ruler seat",
            "Pyongyang court hall, 666 AD",
        ),
        (
            r"성벽도\s*지배층의\s*부패",
            "an intact Goguryeo wall failing from rotten inner supports",
            "A wide cutaway-like physical view shows an intact stone-and-earth outer wall while rotten timber supports collapse inside the adjoining command hall, dust and broken rank objects exposing internal decay",
            "Pyongyang Fortress inner wall, 667 AD",
        ),
        (
            r"광개토대왕과\s*을지문덕",
            "exactly one adult late-Goguryeo veteran remembering earlier victories",
            "Exactly one elderly Goguryeo veteran kneels beside exactly two inherited victory objects, one intact worn recurved composite bow laid flat on a folded cloth and one plain bronze riding-tack fitting beside it; he looks from one shielded oil dish toward a damaged Pyongyang wall under cold smoke, no flame touches either object and both hands remain empty",
            "Pyongyang Fortress inner ward, 668 AD",
        ),
        (
            r"영웅담에\s*취해.*진실",
            "one overturned bronze victory cup beside Goguryeo defeat evidence",
            "Object-only close view of one overturned shallow bronze victory cup spilling dark wine beside one cracked face-down blank Goguryeo rank seal, one dented low segmented iron cap helmet with radial plate seams and one snapped straight spear shaft on dry earth; zero writing, modern bowl helmets or people",
            "Pyongyang Fortress aftermath, 668 AD",
        ),
        (
            r"핏빛\s*투기장에서\s*고구려.*패자",
            "one exhausted Goguryeo defender after the final defeat",
            "One exhausted adult Goguryeo defender with tied black hair kneels alone in torn fitted lamellar over a buttonless wrap-front robe beside one fallen oval layered-timber shield; three long spear shadows cross the breached gate, exactly two empty hands and one coherent body remain visible, zero additional people, modern clothing or arena architecture",
            "Pyongyang Fortress inner courtyard, 668 AD",
        ),
        (
            r"평양성이\s*불타던\s*밤.*원혼",
            "exactly three wounded Goguryeo civilians escaping the burning city",
            "Exactly three wounded adult Goguryeo civilians emerge in separate left, center and right depth slots from a burning textless Pyongyang alley, torn buttonless wrap-front robes, six empty hands, wrapped shoes and grief-stricken faces clear through smoke; blank charred walls contain no signboards or writing",
            "Burning Pyongyang Fortress, 668 AD",
        ),
        (
            r"멸망\s*속에서.*반성과.*통찰",
            "one elderly Goguryeo survivor studying the fallen gate",
            "One elderly Goguryeo survivor stands alone with empty hands before a collapsed timber gate at cold dawn, natural neck and shoulders, grief and hard reflection visible in both eyes",
            "Fallen Pyongyang Fortress, 668 AD",
        ),
        (
            r"환호와\s*비명이\s*교차",
            "one grieving Goguryeo refugee before a distant Tang celebration",
            "One grieving Goguryeo refugee crouches alone beside a tied cloth bundle while raised spear shadows and distant torchlight imply a Tang celebration beyond the gate, one complete body and zero additional visible people",
            "Pyongyang Fortress aftermath, 668 AD",
        ),
        (
            r"살기\s*위해\s*동족을\s*판",
            "exactly two adults: one Tang-clad Goguryeo collaborator and one wounded compatriot",
            "One Tang-clad Goguryeo collaborator at left wears fitted dark lamellar and a low conical iron helmet as he points exactly one straight spear toward one wounded compatriot at right in a torn buttonless wrap-front robe behind one cracked oval timber shield; exactly two separate adult bodies, four connected arms and four grounded legs",
            "Tang-held Liaodong stockade, 668 AD",
        ),
        (
            r"권력의\s*체스판.*소모품",
            "three shallow cracked household grain bowls pinned beneath one overturned command stool",
            "Object-only close view: one thick lower crossbar of one overturned heavy backless mortised-timber command stool visibly overlaps and rests across all three broken rims of exactly three shallow empty clay grain bowls in one row with no contact gap; smoke-dark packed earth fills every background edge, circular foot rings and a small amount of spilled millet remain visible, zero people",
            "Pyongyang command district aftermath, 668 AD",
        ),
        (
            r"단순한\s*비극.*인과응보",
            "one split Tang bronze cup beside a fallen Goguryeo rank seal",
            "Object-only close view of exactly two artifact groups on rough timber: one shallow Tang bronze cup split into exactly two adjacent pieces and one fallen face-down plain Goguryeo rank seal with a blank back beside it; a small spill of dark wine links them, with no teapot, jar, rope, glyph or additional vessel",
            "Fallen Pyongyang command room, 668 AD",
        ),
        (
            r"핏빛\s*투기장에서\s*권력.*본질",
            "exactly two rival adult elites struggling for one rank seal",
            "Exactly two rival adult Goguryeo court elites in fitted lamellar over buttonless wrap-front robes grapple across open mud for exactly one flat square face-down bronze rank seal with a completely blank back lying between them; two separate complete bodies, four coherent hands, wrapped shoes and no coin, glyph, arena or modern observer",
            "Goguryeo fortress court, 666 AD",
        ),
        (
            r"힘의\s*논리.*지옥도",
            "a dense Tang spear line advancing over shattered Goguryeo shields",
            "A dense but orderly Tang spear line advances across muddy open ground over three separate shattered Goguryeo timber shields, limited foreground soldiers kept in distinct body slots under hard smoke light",
            "Pyongyang siege ground, 668 AD",
        ),
        (
            r"도덕과\s*낭만.*차가운\s*공기",
            "an empty Goguryeo battlefield under thick white fog",
            "Wide zero-person view of thick white fog crossing exactly three abandoned low segmented Goguryeo iron cap helmets with visible radial plate seams and riveted brow bands, snapped straight spear shafts and cracked oval layered-timber shields on cold packed earth; no smooth modern bowl helmets, combat or arena architecture",
            "Pyongyang battlefield aftermath, 668 AD",
        ),
        (
            r"영광의\s*이면.*배신과\s*멸망",
            "one scorched blank victory standard above a collapsed inner gate",
            "One scorched completely unmarked solid-ochre Goguryeo victory standard hangs torn from a rough timber pole above a collapsed inner gate; three dented low segmented iron cap helmets with radial plate seams and cut red rank cords remain visible through smoke, without emblem, writing, painting, skull or modern helmet",
            "Fallen Pyongyang Fortress, 668 AD",
        ),
        (
            r"^\s*영웅담\s*$",
            "one scorched blank Goguryeo standard beside a broken spear",
            "Object-only closing image of one scorched completely unmarked solid-ochre Goguryeo standard collapsed beside one broken straight spear and one dented low segmented iron cap helmet with radial plate seams on cold ash at dawn; no writing, emblem, smooth modern bowl helmet or people",
            "Pyongyang Fortress aftermath, 668 AD",
        ),
        (
            r"조국을\s*팔아넘긴\s*매국노.*남생\s*가문",
            "one flat blood-smeared five-finger handprint on full-bleed textless packed-clay terrain",
            "Object-only straight-down evidence view: irregular packed-clay landform terrain extends beyond all four image edges; unmistakable raised mountain ridges, one winding recessed river channel and low fortress mounds remain visible around and beneath one flat matte palm silhouette with exactly five flat finger smears",
            "bare Goguryeo command-room floor, 666 AD",
        ),
        (
            r"아버지가\s*평생.*나라를\s*적국에\s*헌납",
            "one scarred Goguryeo layered-timber shield split into exactly two overlapping halves",
            "Object-only straight-down close view on freezing wet mud filling every edge: one plain convex oval Goguryeo shield of vertical layered timber planks with a rawhide rim has split once down its center; exactly two jagged halves overlap slightly at the break while preserving one complete oval silhouette, one small plain iron boss remains attached to the left half and broad mud margins surround the sole shield",
            "freezing muddy Goguryeo ground with no architecture, 666 AD",
        ),
        (
            r"최고\s*권력자.*처참한\s*도망자",
            "one abandoned rain-soaked Goguryeo command robe",
            "Object-only close ground view of exactly one dark buttonless wrap-front command robe lying alone in a muddy track; its plain grey cloth waist tie remains sewn into the robe seam, wrapped-shoe footprints recede through cold rain, and wet mud fills every edge",
            "muddy forest track outside Gungnae Fortress",
        ),
        (
            r"당나라에\s*투항.*목숨을\s*구걸",
            "exactly two adult males: kneeling Namsaeng; standing low-black-futou Tang envoy",
            "Grey buttonless wrap-robed Namsaeng kneels low left with bowed head and both empty open palms raised; one Tang envoy stands right wearing a soft low black cloth futou headwrap that covers all hair and a smooth-front dark round-neck paofu; exactly two male bodies against one blank wall",
            "windowless Gungnae Tang command hall, 666 AD",
        ),
        (
            r"늑대에게\s*스스로\s*성문을\s*열",
            "exactly one back-facing adult Goguryeo traitor guard lifting one locking beam with both hands",
            "Rear waist-up view: one back-facing guard in a rust buttonless pocketless wrap robe and broad knotted cloth sash lifts the sole thick horizontal timber locking beam at waist height; both complete hands are visible far apart beneath the beam, left palm under its left third and right palm under its right third, raising it just above two empty iron brackets against a closed field of vertical gate planks; his robe back is one uninterrupted cloth panel",
            "Goguryeo fortress inner gate, 667 AD",
        ),
        (
            r"16살\s*난\s*둘째\s*아들\s*헌성.*장안",
            "exactly one male: slender sixteen-year-old Heonseong leaving for Chang'an",
            "Slender sixteen-year-old male Heonseong walks alone to the right on a bare dirt road in a long-sleeved buttonless wrap jacket, loose trousers and closed wrapped shoes; one small soft square tan cloth parcel rests under his left arm as he looks back over his shoulder in fear",
            "bare rammed-earth outer road approaching Chang'an, 666 AD",
        ),
        (
            r"인질을\s*바치며.*납작\s*엎드",
            "exactly one teenage boy Heonseong fully prostrate with forehead and both hands pressed to the floor",
            "Straight-down extreme close crop: the frame contains only the crown of Heonseong's black hair, a narrow strip of upper forehead touching one bare dark timber floor, exactly two complete open hands placed apart at left and right, and two plain wide grey buttonless wrap-sleeve cuffs entering from the lower edge; the crop ends before shoulders, neck, torso, waist or legs, and continuous unadorned floorboards fill every remaining pixel",
            "bare dark timber floor in Chang'an, 666 AD",
        ),
        (
            r"당나라\s*대군이\s*오면.*정벌의\s*선봉",
            "exactly one weaponless adult Tang-armored Namsaeng pointing toward Goguryeo",
            "Tang-armored adult Namsaeng stands alone on a muddy ridge in fitted iron lamellar over a dark closed round-neck robe; his empty right hand extends forward with one straight index finger pointing toward distant low earthen Goguryeo ramparts and timber palisades while his empty left fist rests at his hip; no sword, sheath, bow, spear or weapon appears anywhere",
            "Liaodong military road toward Goguryeo, 667 AD",
        ),
        (
            r"지배하던\s*6개\s*성을\s*통째로\s*넘",
            "one textless defense-route handover layout with exactly six smooth grey river-stone fortress markers",
            "Object-only straight-down evidence view: exactly six smooth grey stones form a top row of three and a bottom row of three on continuous rough floor planks; one straight red route cord crosses the empty middle gap from one flat grey Goguryeo sash at left to one flat black Tang sash at right",
            "Gungnae Tang command-room floor, 666 AD",
        ),
        (
            r"10만\s*가구.*노예로\s*헌납",
            "exactly four adults: two exhausted Goguryeo civilians; two Tang guards",
            "Two exhausted Goguryeo civilians in worn wrap-front hemp robes carry separate tied cloth bundles through a muddy gate while two Tang guards in dark lamellar armor flank them; exactly four separated foreground adults, grief and coercion visible",
            "Gungnae Fortress captive gate, 666 AD",
        ),
        (
            r"백성의\s*목숨.*장기말",
            "exactly three adults: one gaunt Goguryeo civilian; two armored officials",
            "One gaunt Goguryeo civilian stands center behind one low dark table; one armored official at each side slides one palm-sized smooth pebble toward him, exactly two pebbles total and three separate bodies; one low blank rammed-earth wall fills the background",
            "bare packed-earth Goguryeo command yard",
        ),
        (
            r"약점을\s*가장\s*잘\s*아는\s*자.*스파이",
            "one secret red route cord joining one grey Goguryeo sash to one black Tang sash through exactly three small smooth grey stones",
            "Object-only extreme top-down crop on continuous dark brown floorboards filling every edge: one narrow soft wrinkled grey woven sash strip lies horizontally at far left and one narrow soft wrinkled black woven sash strip lies horizontally at far right; exactly three separate same-size smooth grey oval stones form one horizontal row between them with clear gaps, and one red cord crosses all three stone centers",
            "continuous dark floorboards, 667 AD",
        ),
        (
            r"당\s*고종.*극도로\s*기뻐",
            "exactly one adult male Emperor Gaozong",
            "Tight waist-up reaction portrait of adult male Emperor Gaozong wearing a soft low black Tang futou headwrap, short moustache and beard, and one dark round-neck paofu with uninterrupted plain chest cloth; he shows a cold triumphant smile and raises one open empty hand beside his face against one blank plaster wall",
            "windowless Chang'an Tang audience room",
        ),
        (
            r"우위대장군이라는\s*높은\s*벼슬",
            "one blank-backed Tang rank seal pressed into granted earth",
            "Straight-down object-only: exactly one palm-sized face-down blank-backed gilt-bronze Tang rank seal sits half-buried in rich dark earth inside exactly one plain shallow land-grant tray, its smooth blank back fully visible; earth reaches all four inner tray edges, with zero person, hand, clothing, map, paper, coin or writing",
            "plain Tang grant table, Chang'an, 666 AD",
        ),
        (
            r"대막리지가\s*적국\s*장수로\s*돌변",
            "exactly one adult male Namsaeng changing into a Tang commander",
            "Waist-up view of adult male Namsaeng alone in fitted Tang iron lamellar over a dark closed round-neck robe; his right hand tightens one shoulder fastening while his left hand pulls one plain grey Goguryeo rank sash away from his body, his expression cold and resolved",
            "plain Tang command changing room, 666 AD",
        ),
        (
            r"조국도.*가문의\s*이름도.*내던",
            "one severed grey woven Goguryeo clan sash",
            "Object-only straight-down close view on continuous dark brown floorboard grain filling every pixel and every edge: one single-layer grey woven clan sash forms one undivided horizontal band and is severed once at center into exactly two total objects, one left half and one right half only; one narrow clean gap separates their facing frayed edges and exposes the same floorboard grain beneath",
            "bare full-bleed Chang'an registry floorboards, 666 AD",
        ),
        (
            r"악마의\s*발밑을\s*기는.*생존",
            "one realistic brown rat beneath one enormous boot-shaped shadow",
            "Animal-only ground-level profile: exactly one realistic brown rat crouches belly-low in wet mud with four natural paws, one coherent spine, one intact head and one long unbroken tail; one enormous dark boot-shaped shadow falls across the rat from outside the frame",
            "muddy Tang-held fortress passage, 666 AD",
        ),
        (
            r"신라로\s*몽땅\s*넘어가\s*투항",
            "exactly two adults: one Silla guard in a low black segmented iron helmet, kneeling Yeon Jeongto",
            "One large plain ochre triangular standard rises in the upper background above low hide tents and one timber palisade; Yeon Jeongto kneels left offering one small soft tan tied cloth bundle while one Silla guard stands right in dark iron lamellar and a low shallow black segmented iron cap helmet with one narrow plain gilt brow band",
            "Silla northern frontier camp, 666 AD",
        ),
        (
            r"일인\s*독재의\s*축.*모래성처럼\s*붕괴",
            "one full-scale smooth unmarked Goguryeo rammed-earth defensive embankment collapsing into loose sand",
            "Wide low-angle close landscape of one low roofless and towerless sloped defensive earthwork filling the frame: the entire right half actively disintegrates into a cascading avalanche of loose granular sand reaching the lower and right canvas edges; the solid left half is one broad smooth unmarked ochre earthen slope with a sparse row of straight undecorated timber stakes along its crest beneath dark storm clouds",
            "isolated bare rammed-earth defensive slope on an empty plain, 667 AD",
        ),
        (
            r"113만\s*대군.*권력욕이라는\s*독약",
            "one thick Goguryeo granite fortress wall with its center melting into one broad low horizontal poison breach",
            "Object-only extreme close view filling every edge with irregular rough granite fieldstones: viscous green-black poison spreads across the center and transforms several stones into one broad low horizontal cavity at least twice as wide as it is tall, with jagged sagging liquid-rock edges and heavy mineral drips; solid stone remains above, below, left and right",
            "Goguryeo fortress wall, 665 AD",
        ),
        (
            r"권력\s*세습.*치명적인\s*자살골",
            "one blank square bronze succession plaque half-submerged in black poison",
            "Object-only extreme top-down macro: one thin flat blank bronze square fills the center while its lower half disappears beneath one viscous black poison pool; one continuous smooth unbroken ochre clay surface fills every edge",
            "featureless smooth clay ground, 665 AD",
        ),
        (
            r"자질\s*없는\s*후계자.*수백만\s*백성",
            "exactly three starving Goguryeo civilians",
            "Exactly three distinct adults kneel in a muddy drainage lane: one gaunt woman left, one elderly man center and one young man right, all in worn wrap-front hemp robes without buttons or pockets, beside separate empty grain baskets and a collapsed granary awning",
            "Pyongyang fortress settlement, 667 AD",
        ),
        (
            r"조국의\s*산천.*맹렬하게\s*진격",
            "one Tang-armored adult rider Namsaeng on one horse",
            "Tang-armored Namsaeng rides one galloping horse down a burning village road; both fists grip paired reins connected to one bridle; forward hooves kick one overturned grain basket and broken clay pots while timber-and-thatch homes burn on both sides",
            "Goguryeo village road under Tang attack, 667 AD",
        ),
        (
            r"백성들.*배신에\s*피눈물",
            "exactly three adult Goguryeo villagers with visible tear tracks",
            "Exactly three villagers stand before burned timber-and-thatch homes: one middle-aged woman, one elderly man and one young man in clean undyed buttonless wrap-front robes; all three have reddened eyes and clear wet tear tracks confined to their cheeks, with empty smoke-filled sky directly behind the rooflines",
            "Goguryeo village road, 667 AD",
        ),
        (
            r"1차\s*방어선\s*신성.*성문이\s*열",
            "one unlatched heavy iron gate chain laid as one open straight segment on smooth clay",
            "Object-only top-down evidence still life: exactly one short heavy chain segment forms one shallow diagonal line from upper left to lower right; its two free end links remain visible and far apart while the chain stays uncoiled; one continuous smooth clay surface fills every edge",
            "Sinseong Fortress inner ground, 667 AD",
        ),
        (
            r"동지를\s*팔고\s*적국에\s*엎드",
            "exactly three adults: two kneeling Goguryeo officials; one standing Tang soldier",
            "Two unarmored Goguryeo officials kneel separately at left and center in grey wrap-front robes before one standing Tang soldier at right in dark lamellar armor and a low black helmet; all six hands empty, clear vertical hierarchy, no weapons or tablets",
            "Tang-held Goguryeo fortress courtyard, 667 AD",
        ),
        (
            r"불만들이\s*조국을\s*팔아먹는\s*괴물",
            "one cracked stone kneeling statue releasing one distorted black betrayal shadow",
            "Object-only low dramatic view: one weathered stone kneeling statue carved with a plain wrap-front robe splits from chest to base; a single flat black shadow crawls out across the ground and distorts into long claw-like fingers while the statue remains the sole physical object",
            "Goguryeo fortress inner courtyard, 667 AD",
        ),
        (
            r"약점은\s*가장\s*처참하게\s*공격",
            "one cracked oval Goguryeo timber shield pierced by exactly one detached spearhead",
            "Object-only extreme close view: exactly one convex oval layered-plank timber shield with a rawhide rim lies on packed earth; exactly one large triangular iron spearhead blade, detached from its shaft, remains embedded at the central crack, and packed earth surrounds the sole shield",
            "Liaodong battlefield breach, 668 AD",
        ),
        (
            r"700년\s*사직의\s*핏빛\s*조종",
            "one upright uninscribed flared bronze alarm bell with one frayed rope stub",
            "Object-only close front view against featureless smoke-dark packed earth filling every edge: exactly one upright uninscribed bronze bell has a narrow domed crown, one top loop with one short frayed rope stub, a widening body, broad flared skirt, open mouth and thick blank rim; zero buildings, signboards, writing or people",
            "bare packed-earth Pyongyang court ground",
        ),
        (
            r"피\s*묻은\s*왕좌.*국가\s*전체",
            "one upright Goguryeo ceremonial throne sinking into a dark red pool",
            "Object-only low close view of one unmistakable Goguryeo ceremonial timber throne with a tall plain back, two armrests and restrained gilt-bronze edge fittings; the throne remains upright but half submerged and sinking into one deep dark red pool across the stone audience-hall floor",
            "Pyongyang audience hall floor, 666 AD",
        ),
        (
            r"이름\s*없는\s*병사들의\s*원혼",
            "exactly three empty dented Goguryeo segmented iron helmets",
            "Object-only straight-down close ground view of exactly three separate low segmented iron cap helmets lying on their sides; all three open undersides face camera and reveal dark empty interiors filled only with snow, beside exactly two snapped straight spear shafts and retreating cart tracks",
            "snowy Liaodong battlefield ground",
        ),
        (
            r"추악한\s*이기심.*거대한\s*지옥도",
            "exactly two adult Goguryeo civilian bearers carrying one fully shrouded casualty",
            "Exactly two Goguryeo civilian bearers in torn buttonless wrap-front hemp robes carry one fully covered human-shaped hemp shroud on one simple rectangular timber stretcher through a smoke-filled packed-earth lane; the two bearers remain separate with four visible hands on two stretcher poles",
            "smoke-filled Liaodong fortress evacuation lane",
        ),
        (
            r"동화\s*속\s*영웅담.*권력\s*정치의\s*잔혹",
            "one low segmented iron cap helmet beside one flattened gilt-bronze cover",
            "Object-only straight-down extreme close view on continuous packed earth: exactly one dented low segmented iron cap helmet with a narrow brow band sits beside exactly one separate thin gilt-bronze ceremonial shell collapsed visibly flat on the ground; both objects remain fully separate",
            "packed-earth Liaodong battlefield ground",
        ),
        (
            r"남건과\s*남산\s*형제.*평양성을\s*걸어\s*잠그고\s*결사항전",
            "exactly two adult male Goguryeo brothers: Namgeon and Namsan",
            "Exactly two complete commanders stand apart on one broad low Goguryeo rammed-earth rampart faced with irregular fieldstones: dark-lamellar Namgeon at left raises one empty clenched right fist and braces his empty left hand on the parapet; rust-lamellar Namsan at right points outward with one empty open right hand while his empty left fist stays at his chest; distant plain Tang tents and smoke remain below",
            "Pyongyang Goguryeo outer rampart, 668 AD",
        ),
        (
            r"밖에는\s*당나라\s*대군.*안에는\s*극도의\s*공포와\s*불신",
            "exactly three fearful Goguryeo soldiers with six empty hands",
            "Exactly three distinct adult soldiers stand apart in one tense triangle inside a plain windowless timber barracks: left soldier twists toward center, center soldier looks sharply over his shoulder and right soldier recoils; all six open empty hands remain fully visible at chest or waist height, with blank wallboards and drifting smoke behind them",
            "Pyongyang inner barracks, 668 AD",
        ),
        (
            r"백성은\s*굶주림에\s*쓰러지고.*병사는\s*절망적인\s*싸움",
            "exactly two adults: starving civilian and kneeling lamellar soldier",
            "Two adults at earthen wall: gaunt civilian left and lamellar soldier right kneel with four empty hands on knees",
            "windowless Pyongyang inner wall alcove, 668 AD",
        ),
        (
            r"지도자의\s*탐욕.*대제국의\s*비참하고\s*서늘한\s*최후",
            "one massive unpainted Goguryeo timber hall support column splitting at its base",
            "Object-only low close view inside a plain mortised-timber Goguryeo hall: exactly one thick unpainted support column tears open at its stone footing into long fresh splinters while the single crossbeam above visibly sags; bare rammed-earth wall and dark floor continue to every edge",
            "plain Pyongyang Goguryeo audience hall, 668 AD",
        ),
        (
            r"혈육의\s*정은\s*종이\s*조각",
            "one blank unmarked fibrous sheet burning into ash",
            "Object-only close view on one seamless cool grey stone surface where exactly one thin blank fibrous sheet fills the center, its broad left half remains pale and unmarked, and its right half is black, curled and actively burning along one jagged charred boundary with small orange flames attached directly to the sheet edge",
            "featureless seamless cool grey stone surface, 667 AD",
        ),
        (
            r"짐승\s*같은\s*생존\s*본능.*춤을\s*추는\s*지옥",
            "exactly two grey wolves in one dark earthen pit",
            "Animal-only low action view: exactly two separate grey wolves circle each other on bare mud, one crouched at left and one braced at right; each wolf has one head, four natural legs, two ears and one visible tail, with both mouths snarling and both bodies fully contained inside one steep dark earthen pit",
            "dark bare earthen pit outside Pyongyang, 667 AD",
        ),
        (
            r"고구려의\s*심장\s*평양성.*서서히\s*고립",
            "one full-scale Pyongyang Goguryeo fortress encircled by Tang tents",
            "Wide elevated landscape where one large roofless rammed-earth and irregular-fieldstone Goguryeo outer fortress occupies the center on a low hill while a continuous distant ring of many low plain tan Tang hide tents surrounds it across the entire plain, several small low campfires sit only in clear bare-ground gaps between neighboring tents, and dark open ground separates the fortress from the encirclement",
            "Pyongyang fortress outer plain, 668 AD",
        ),
        (
            r"대제국이\s*속에서부터\s*완전히\s*곪아\s*터져",
            "one plain unglazed Goguryeo grain jar ruptured open by black-green rot",
            "Object-only straight-on close view on continuous packed earth: exactly one large plain unglazed storage jar looks intact around its rim and sides but one jagged front rupture exposes clumped spoiled millet coated in thick black-green mold and wet rot; the diseased contents remain inside the single jar",
            "bare Pyongyang granary ground, 668 AD",
        ),
        (
            r"독재는\s*결국\s*제\s*살을\s*깎아\s*먹는.*독",
            "one dark snake clamping its own continuous mid-body between closed jaws",
            "Animal-only close view on featureless cold stone where exactly one complete dark snake forms one broad open S-curve, its single head bends down and closes upper and lower jaws around its own mid-body, and its single tapered tail ends far from the mouth",
            "featureless continuous cold stone surface, 667 AD",
        ),
        (
            r"내부\s*결속력이\s*파괴.*더\s*이상\s*버텨낼\s*힘",
            "exactly three separate Goguryeo oval timber shields, each with one iron boss",
            "Object-only straight-down view on continuous packed earth where exactly three convex layered-plank shields lie in left, center and right slots with wide empty gaps, every shield shows one small plain iron boss at its center, and all three rawhide-rimmed edges remain far apart",
            "bare Pyongyang armory ground, 667 AD",
        ),
        (
            r"외적보다\s*무서운.*썩어빠진\s*탐욕과\s*분열",
            "exactly two blank bronze seals divided by one deep floor crack",
            "Object-only straight-down view on continuous packed clay where one blank-backed bronze seal lies far left and one lies far right, both angle away from one single dark jagged fissure running vertically through the empty center gap",
            "open bare packed-clay ground, 667 AD",
        ),
        (
            r"국방력이\s*뛰어나도.*지배층이\s*부패.*단숨에\s*망",
            "one tall oval shield, back side up, with one broken leather grip",
            "Object-only straight-down close view on featureless packed earth where exactly one tall oval shield lies flat backside-up, its rawhide rim and outer planks remain intact while exactly one broad dark-brown horizontal leather grip crosses the exact center and is snapped once into two facing frayed ends over blackened rotten wood",
            "featureless Pyongyang packed-earth surface, 667 AD",
        ),
        (
            r"권력을\s*사유화.*끝없는\s*탐욕.*거대한\s*핏빛\s*파국",
            "one cracked bronze stamp with a low bridge knob in a dark-red stain",
            "Object-only low three-quarter macro on isolated rough charcoal stone where exactly one thick square cast-bronze authority stamp lies toppled, one short low bridge-shaped knob rises directly from the center of its back with both knob feet touching the stamp body, one chipped jagged fracture crosses the metal, and one matte asymmetric dark-red stain soaks into the stone beneath it",
            "isolated rough charcoal-grey stone surface, 668 AD",
        ),
        (
            r"백성들이\s*흘린.*피눈물.*씻을\s*수\s*없는\s*흉터",
            "one flat foundation stone with one permanent red scar",
            "Object-only straight-down rain view where exactly one rough natural granite slab lies embedded in packed earth, one single unbranched near-vertical fissure runs from top center to bottom center and remains dark-red-stained while pale rainwater crosses it, and irregular ground continues to every edge",
            "bare fallen Pyongyang foundation ground, 668 AD",
        ),
        (
            r"제국의\s*수레바퀴.*억울한\s*죽음.*짓밟으며",
            "one empty dented segmented iron helmet in one fresh cart-wheel track",
            "Object-only low oblique close-up on featureless churned mud. The empty shallow half-dome cap lies on its side with a dented crown, wide open bottom and plain interior partly visible. The dented cap rests directly on the floor of the broad fresh cart-wheel track while deep mud buries its lower third",
            "featureless churned mud on a Liaodong military road, 668 AD",
        ),
        (
            r"패자의\s*시체\s*위에서\s*춤추는\s*권력.*맨얼굴",
            "exactly one cropped Tang-era cloth-wrapped forefoot pressing exactly one dented Goguryeo iron cap",
            "Tight oblique ground close-up where crossed matte charcoal cloth bands cover the forefoot entering from upper left while the ankle and heel remain outside frame. The soft rounded toe and flat cloth underside press directly onto the shallow segmented iron cap as it sinks into deep mud",
            "muddy Liaodong battlefield ground, 668 AD",
        ),
        (
            r"낭만이\s*거세된.*고대\s*동아시아.*냉혹한\s*투기장",
            "exactly two weaponless fighters: rust Goguryeo and black Tang",
            "Exactly two complete adult soldiers fight in separate left and right slots on bare packed earth, the rust Goguryeo fighter at left drives one empty right fist toward his opponent and keeps one empty left fist beside his cheek, the black Tang fighter at right leans back and blocks with his left forearm across his chest while one empty right fist stays at his waist, all four closed empty fists and four grounded feet remain visible, and one continuous featureless ochre rammed-earth wall fills the background edge to edge",
            "bare Pyongyang outer earthen yard, 668 AD",
        ),
        (
            r"환상에서\s*깨어나.*진짜\s*역사의\s*비릿한\s*무게",
            "one torn golden silk veil beside one shallow segmented Goguryeo iron cap",
            "Object-only straight-down view on continuous rough timber where exactly one torn golden silk veil lies folded at left and exactly one shallow half-dome segmented iron cap helmet lies on its side at right with its wide open bottom and plain empty interior facing the viewer, with one wide gap separating the two objects",
            "dark Goguryeo evidence table, 668 AD",
        ),
    )
    for pattern, subject, action, place in robust_overrides:
        if re.search(pattern, spoken, re.IGNORECASE):
            return subject, action, place

    overrides = (
        (
            r"연개소문이\s*죽자.*형제들의\s*핏빛\s*내전",
            "exactly three adult Goguryeo brothers",
            "Three brothers form one violent empty-handed triangle: rust-clad left lunges with two empty fists, charcoal-clad center blocks with two open empty palms, and muted-blue right advances with two empty clenched fists; all three remain separate in one smoky courtyard",
            "Pyongyang Fortress court courtyard, 665 AD",
        ),
        (
            r"요동\s*방어선의\s*핵심\s*군사\s*기밀",
            "one textless Goguryeo defense-route handover layout",
            "Object-only overhead evidence: exactly six grey stones form a top row of three and a bottom row of three; one straight red cord in the empty middle gap joins one grey sash at left to one black sash at right; installed rough floor planks continue beyond every canvas edge",
            "windowless Liaodong Tang campaign room, 667 AD",
        ),
        (
            r"수백만\s*대군으로도\s*못\s*뚫은\s*철벽.*제풀에\s*무너",
            "one sabotaged Goguryeo timber gate brace",
            "Object-only interior close view of exactly one horizontal timber locking beam spanning one plank gate; one deep triangular V-shaped axe notch removes the lower half at exact center, exposing pale flat chopped facets and repeated axe scars while irregular small fieldstones embedded in rammed earth fill the intact wall",
            "Goguryeo frontier fortress inner gate, 667 AD",
        ),
        (
            r"스스로\s*성씨마저\s*바꾸는\s*치욕",
            "one severed grey woven Goguryeo clan sash",
            "Object-only straight-down close view on edge-to-edge dark timber: exactly one wide grey woven clan sash lies severed once across its width into exactly two separated halves; one clean empty gap divides the facing frayed cut edges",
            "dark timber registry wall at Chang'an, 666 AD",
        ),
        (
            r"제국의\s*숨통을\s*끊은.*내부의\s*배신",
            "one short dagger half-covered by one folded command sash",
            "Object-only straight-down overhead still life: one plain unmarked short straight iron dagger lies flat on rough timber floorboards with its middle half covered by one folded woven command sash; diffuse grey doorway light evenly reveals uninterrupted floorboard grain from corner to corner",
            "Pyongyang Fortress court corridor, 666 AD",
        ),
        (
            r"1차\s*방어선\s*신성.*성문이\s*열",
            "one Goguryeo fortress gate breached by internal sabotage",
            "Object-only wide interior view of one heavy plank gate hanging open after its inner timber bar was removed, with enemy spear tips and torchlight entering above one discarded woven guard sash",
            "Sinseong Fortress inner gate, 667 AD",
        ),
        (
            r"인간의\s*이기심과\s*더러운\s*권력욕",
            "exactly two adult Goguryeo nobles",
            "Two Goguryeo nobles crouch in separate left and right slots around one fallen plain bronze rank seal, each reaching with one sleeve-covered hand as greed and fear divide their faces",
            "Pyongyang Fortress court room, 666 AD",
        ),
        (
            r"핏빛\s*체스판.*소모품\s*장기말",
            "exactly three palm-sized grey stone tokens beside three worn Goguryeo cloth shoes",
            "Object-only straight-down close view of exactly three separate palm-sized flat grey stone tokens lying in dark mud beside exactly three mismatched worn Goguryeo cloth shoes; no people, hands, legs, table or architecture",
            "Pyongyang Fortress inner ward, 667 AD",
        ),
        (
            r"모든\s*지형과\s*성곽의\s*약점",
            "one textless Goguryeo defense layout installed directly on rough floorboards",
            "Object-only overhead evidence: exactly six smooth grey pebbles form two rows of three on installed edge-to-edge rough floorboards; one blue woven cord marks the river, three short red route cords cross it and one snapped timber bar marks a breached wall; no board, frame, white margin or people",
            "Liaodong Tang command hall, 667 AD",
        ),
        (
            r"국방력이\s*뛰어나도.*지배층이\s*부패",
            "one intact Goguryeo timber shield with rotten rear bindings",
            "Object-only evidence view of one intact curved timber shield standing upright while its hidden rear rawhide bindings split from black rot and the shield face begins to peel from inside",
            "Pyongyang Fortress armory, 667 AD",
        ),
        (
            r"외부의\s*적이\s*백만.*어떻게\s*망했",
            "one unbroken Goguryeo gate with its inner locking beam sawn through",
            "Object-only interior view of one heavy plank gate still unbroken while its thick locking beam shows a fresh saw cut from the courtyard side and enemy firelight enters through the opening seam",
            "Pyongyang Fortress inner gate, 668 AD",
        ),
        (
            r"가장\s*단단한\s*방패.*가장\s*예리한\s*창",
            "one adult Tang-clad Yeon Namsaeng",
            "Tang-clad Yeon Namsaeng stands in one complete body holding a single straight spear upright beside his abandoned curved Goguryeo timber shield and woven rank sash on muddy ground",
            "Tang-held Liaodong stockade, 668 AD",
        ),
        (
            r"천하를\s*호령하던.*곪아\s*터져",
            "one split Goguryeo granary support beam",
            "Object-only close evidence view of one thick granary support beam split lengthwise, exposing black inner rot and beetle damage beneath an intact hard outer surface",
            "Pyongyang Fortress granary, 667 AD",
        ),
        (
            r"외적보다\s*무서운.*탐욕과\s*분열",
            "two cracked bronze rank seals pulling apart one command cord",
            "Object-only overhead view of two plain bronze rank seals tied to opposite ends of one thick red command cord as the center fibers split across rough timber",
            "Pyongyang Fortress command room, 667 AD",
        ),
        (
            r"연개소문의\s*독재.*제\s*살을\s*깎",
            "one abandoned Goguryeo command seat encircled by severed cords",
            "Object-only low view of one empty dark timber command seat surrounded by exactly three severed red command cords and one fallen plain bronze rank seal on packed earth",
            "Pyongyang Fortress court hall, 666 AD",
        ),
        (
            r"제국의\s*심장에\s*스스로\s*비수",
            "one straight iron dagger driven into a Goguryeo rank seal",
            "Object-only close evidence view of one short straight iron dagger driven into the center of one plain bronze Goguryeo rank seal on an overturned low ruler seat",
            "Pyongyang Fortress audience hall, 667 AD",
        ),
        (
            r"동화\s*속\s*영웅담.*잔혹함",
            "one ornate ceremonial helmet cover removed from a battered war helmet",
            "Object-only close view of one bright gilt ceremonial helmet cover lying aside from the dented mud-dark iron war helmet it concealed, with one worn civilian sandal in the same packed-earth plane",
            "Liaodong battlefield aftermath, 668 AD",
        ),
        (
            r"낡은\s*동화책을\s*찢어버리고",
            "one torn dark-red ceremonial cloth exposing damaged Goguryeo war materials",
            "Object-only straight-down ground view of one plain unmarked dark-red woven cloth ripped open across three separate clusters of cord-tied lamellar plates and one snapped bow on bare cold mud; no helmet, footwear or body parts",
            "Liaodong battlefield aftermath, 668 AD",
        ),
        (
            r"민족이라는\s*개념.*휴지조각",
            "one Goguryeo hemp standard cut into wrapping around a plain bronze belt fitting",
            "Object-only straight-down close view of one solid-color hemp cloth cut into two frayed wrapping strips around one smooth face-down bronze belt clasp on light tan packed earth filling every edge; uninterrupted weave and blank metal back only",
            "open Tang-held Liaodong registry yard, 668 AD",
        ),
        (
            r"살아남아\s*권력을\s*쥐려는.*생존\s*본능",
            "one mud-covered adult Goguryeo survivor",
            "One mud-covered adult Goguryeo survivor climbs over a line of fallen shields with one connected body, empty hands, clenched jaw and terrified determination under cold firelight",
            "Pyongyang Fortress inner ward, 668 AD",
        ),
        (
            r"제국의\s*오만.*내부의\s*맹수",
            "one plain bronze plate split into two cord-tied halves",
            "Object-only straight-down close view of one smooth unmarked bronze plate split into exactly two halves on featureless packed earth, blank backs upward and each half pulled away by one thick red cord; no symbols, borders or writing",
            "Pyongyang Fortress court courtyard, 668 AD",
        ),
        (
            r"패망의\s*역사에서.*교훈",
            "one elderly adult Goguryeo witness",
            "One elderly Goguryeo witness kneels in a medium full-body view wearing wrapped cloth shoes beside several separate flat woven hemp sandals scattered in ash, shoulders collapsed with grief before a fallen timber granary",
            "Pyongyang Fortress aftermath, 668 AD",
        ),
        (
            r"핏빛\s*진실만이.*진짜\s*얼굴",
            "one wounded adult Goguryeo witness",
            "One middle-aged wounded Goguryeo witness with tied black hair turns directly toward the viewer with one complete body, exactly two visible empty hands, soot and controlled anger on his weathered East Asian face against blank smoke-dark rubble, with no seal, coin, mirror, modern haircut or writing",
            "Goguryeo fortress aftermath, 668 AD",
        ),
        (
            r"핏빛\s*생존\s*게임.*결말",
            "one lone adult Goguryeo survivor in a ruined inner ward",
            "A wide aftermath view centers one lone adult Goguryeo survivor standing with empty hands among separately scattered helmets, shields and abandoned cloth bundles under receding smoke",
            "Pyongyang Fortress aftermath, 668 AD",
        ),
        (
            r"그\s*뼈들을\s*잘근잘근",
            "one empty dented segmented iron helmet in one fresh cart-wheel track",
            "Object-only low oblique close-up on featureless churned mud. The empty shallow half-dome cap lies on its side with a crushed crown, wide open bottom and plain interior partly visible. The dented cap rests directly on the floor of the broad fresh cart-wheel track while deep mud buries its lower third",
            "featureless churned mud on a Liaodong military road, 668 AD",
        ),
        (
            r"시체\s*위에서\s*춤추는\s*권력의\s*잔혹한\s*야만성",
            "one low backless Tang command stool standing over fallen Goguryeo gear",
            "Object-only low view of one undecorated low backless Tang timber command stool with four short square legs; its front feet pin one torn Goguryeo rank sash and one mud-dark folded hemp shroud against one broken timber shield, while snapped spear shafts and packed earth fill every image edge",
            "Liaodong battlefield aftermath, 668 AD",
        ),
        (
            r"핏빛\s*투기장에\s*깊숙이",
            "exactly four adult fortress combatants",
            "Exactly four adults fight in separated depth slots across a smoky packed-earth breach, two Goguryeo defenders with curved timber shields facing two Tang spearmen with one straight spear each",
            "Pyongyang Fortress breach, 668 AD",
        ),
        (
            r"전쟁은\s*화려한\s*오락이\s*아닙니다",
            "one exhausted adult Goguryeo civilian survivor",
            "One exhausted civilian survivor crosses a burned fortress lane with empty hands, wrap-front hemp robe and complete body while abandoned helmets, a broken cart and two ruined timber homes show the slaughter around him",
            "Pyongyang Fortress settlement, 668 AD",
        ),
        (
            r"환상에서\s*깨어나\s*진짜\s*역사의\s*비릿한\s*무게",
            "one cracked gilt ceremonial mask over a dented iron helmet",
            "Object-only close view of one cracked gilt ceremonial face cover lifted aside to expose one dented mud-dark Goguryeo iron helmet on rough timber",
            "Goguryeo court evidence table, 668 AD",
        ),
        (
            r"피비린내\s*나는\s*전장에서.*권력의\s*민낯",
            "one heavy bronze command seal pressed into battlefield mud",
            "Object-only ground view of one heavy plain bronze command seal pressed into blood-dark mud beside one broken shield rim, one worn cloth shoe and one snapped straight spear shaft",
            "Liaodong battlefield aftermath, 668 AD",
        ),
        (
            r"생존\s*방정식에\s*전율",
            "one unarmored adult Goguryeo refugee",
            "One unarmored Goguryeo refugee squeezes through a collapsed timber palisade gap with one connected body and empty hands while distant patrol torchlight approaches through snow",
            "Liaodong frontier, 668 AD",
        ),
        (
            r"영웅\s*찬가에\s*속아",
            "exactly one adult Goguryeo survivor beside abandoned casualty gear",
            "One exhausted Goguryeo survivor kneels at right in a wrap-front hemp robe, broad cloth sash, loose trousers, calf wraps and wrapped cloth shoes; at left lie one folded mud-dark hemp shroud, one broken timber shield, one snapped straight spear shaft and one worn wrapped cloth shoe, with ash and low smoke across open ground",
            "Liaodong battlefield aftermath, 668 AD",
        ),
        (
            r"조국을\s*판\s*배신자.*대대손손.*부귀",
            "exactly two different Tang adult men, white-bearded elder in dark-red paofu and clean-shaven middle-aged man in muted-green paofu",
            "Red-robed elder sits left with one open palm while green-robed younger man sits right holding folded silk, with one bronze cup between and different faces and poses",
            "Chang'an Tang elite residence, late 7th century",
        ),
        (
            r"화려한\s*저택에서.*축배",
            "exactly two adult Tang-clad Yeon descendants",
            "Exactly two Tang-clad adult descendants sit in separated left and right slots at a low lacquer table, each raising one shallow bronze cup while confiscated Goguryeo cloth bundles remain beneath the table",
            "Chang'an Tang elite residence, late 7th century",
        ),
        (
            r"거대한\s*폭풍을\s*준비하는.*전쟁은\s*계속됩니다",
            "one bronze signal brazier and Tang troops mobilizing under storm clouds",
            "One bronze signal brazier flares in the foreground while limited Tang soldiers fasten fitted lamellar armor beneath dark storm clouds and ordered infantry columns form behind them",
            "Liaodong Tang camp, 667 AD",
        ),
        (
            r"유민들은\s*사슬에\s*묶여\s*끌려가",
            "exactly three adult Goguryeo prisoners: grey-haired elder, brown-robed man, young grey-robed man",
            "Short taut chains join iron wrist cuffs as all three walk in separate side profiles through a blizzard",
            "Liaodong prisoner road, 668 AD",
        ),
        (
            r"개인의\s*존엄성.*짓밟",
            "one torn Goguryeo silk robe beneath a military cart wheel",
            "Object-only low view of one torn Goguryeo silk robe and woven sash pinned into freezing mud beneath one heavy wooden military cart wheel, cloth fibers and wheel contact clearly visible",
            "Liaodong military road, 668 AD",
        ),
        (
            r"충신은\s*죽고\s*매국노만\s*번성",
            "one collapsed cluster of Goguryeo lamellar cap plates outside a Tang feast",
            "Object-only ground view of one collapsed cluster of cord-tied dark iron and rawhide Goguryeo cap plates in cold mud beside one snapped straight spear shaft, contrasted with one untouched shallow footless bronze cup and folded Tang silk on a raised dry threshold behind",
            "Chang'an Tang residence threshold, late 7th century",
        ),
        (
            r"역사의\s*메스로.*이면",
            "one short straight utility blade lifting a cracked ceremonial cover",
            "Object-only close evidence view of exactly one short straight single-edged period iron utility knife with a plain wood grip lifting one cracked gilt ceremonial cover from one face-down mud-dark plain bronze rank seal on rough timber; both metal surfaces remain completely uninscribed, with no chef knife, scalpel or hand",
            "Goguryeo court evidence table, 668 AD",
        ),
        (
            r"진실을\s*마주할\s*각오",
            "one wounded adult Goguryeo survivor isolated in smoke-filled ruins",
            "One middle-aged wounded adult Goguryeo survivor with tied-back hair, short stubble and a weathered East Asian face kneels alone in a tight frontal crop from head through mid-thigh; both lower legs and feet stay outside frame, exactly two visible empty hands remain apart, one torn soot-dark buttonless wrap-front robe bears one restrained dark-red side stain, his fixed gaze meets the camera while opaque charcoal smoke fills every other edge",
            "featureless smoke-dark inner ruin inside Pyongyang Fortress, 668 AD",
        ),
        (
            r"원혼들의\s*고통스러운\s*표정",
            "exactly three gaunt adult Goguryeo refugees",
            "Exactly three gaunt Goguryeo refugees emerge in separated depth slots from dense battlefield smoke, wrap-front hemp robes, empty hands and grief-struck faces lit by cold side fire",
            "Pyongyang Fortress aftermath, 668 AD",
        ),
        (
            r"낡은\s*위인전의\s*거짓\s*영웅\s*서사",
            "one face-down blank hardwood tablet bundle in an ash pit",
            "Object-only straight-down close view of one plain face-down hardwood tablet bundle tied with thick hemp cord and half-buried in featureless dark ash; uninterrupted wood grain, one charred corner and no helmet, shoe, symbols or people",
            "Pyongyang Fortress aftermath, 668 AD",
        ),
        (
            r"고구려의\s*처절한\s*투지.*기적",
            "one exhausted adult Goguryeo signal defender",
            "One exhausted Goguryeo defender crouches on a sloped earth-and-rubble battlement and shields one newly lit bronze signal brazier flame with both sleeve-covered hands while siege fires close below",
            "Pyongyang Fortress battlement, 668 AD",
        ),
        (
            r"악마에게\s*영혼을\s*판\s*자들",
            "exactly two visibly different adult collaborators in Tang dress",
            "Grey-bearded man in muted-red round-neck paofu stands left setting one plain confiscated hemp bundle on fire while clean-shaven man in dark-green paofu stands right holding one unmarked bronze seal face-down; separate poses on an open muddy stockade ground",
            "open Tang-held Liaodong stockade, 668 AD",
        ),
        (
            r"폭력에\s*짓밟힌\s*원혼",
            "exactly three adult Goguryeo refugee survivors",
            "Exactly three adult Goguryeo refugees in torn wrap-front hemp robes move through a blizzard in separated depth slots, empty hands and grief-struck faces emerging from blowing snow",
            "Liaodong refugee road, 668 AD",
        ),
        (
            r"안동도호부에\s*부임한\s*남생",
            "exactly three adults: Tang-clad Namsaeng; two Goguryeo prisoners",
            "Tang-clad Namsaeng stands centered on open packed earth behind exactly two kneeling unarmored Goguryeo prisoners in separate left and right slots; exactly three complete bodies, all feet visible, two short wrist chains and no platform, buildings or extra legs",
            "open Andong Protectorate yard, late 7th century",
        ),
        (
            r"권력이라는\s*마약에\s*중독",
            "one adult Goguryeo collaborator holding a Tang rank seal",
            "One adult Goguryeo collaborator in Tang round-collar dress clutches one face-down bronze rank seal to his chest while his discarded woven Goguryeo rank sash lies in spilled dark wine at his feet",
            "Chang'an Tang residence, late 7th century",
        ),
        (
            r"아들들이\s*보여준\s*이\s*참극",
            "exactly two adult Goguryeo brothers and their father's abandoned helmet",
            "Exactly two adult Goguryeo brothers walk away in opposite directions across open packed earth while one collapsed cord-tied lamellar command cap and one snapped red cord remain centered between them; no buildings, signs or extra people",
            "open Pyongyang court ground, 666 AD",
        ),
        (
            r"마지막\s*핏빛\s*숨소리",
            "Pyongyang Fortress under its final smoke-filled siege",
            "A wide night view shows sloped earth-and-rubble Pyongyang ramparts under dense smoke, low timber parapets burning at two breaches and the last torch points withdrawing inward",
            "Pyongyang Fortress final siege, 668 AD",
        ),
        (
            r"발버둥이\s*낳은\s*참혹한\s*핏빛\s*지옥도",
            "two rival Goguryeo rank seals among a destroyed inner ward",
            "Object-only wide ground view of two cracked plain bronze rank seals pulled apart by severed red cords among separate dented helmets, broken shields and burned civilian bundles",
            "Pyongyang Fortress inner ward, 668 AD",
        ),
        (
            r"승자의\s*역사\s*뒤에\s*버려진.*고통",
            "one flat worn Goguryeo wrapped-cloth shoe beneath three marching shadows",
            "Object-only straight-down ground view of one flat heel-less wrapped-cloth shoe with a thin woven sole beside one torn hemp bundle, crossed by exactly three long diagonal marching shadows; packed earth fills every edge with no visible people, legs, buildings or standards",
            "Liaodong occupation road, 668 AD",
        ),
        (
            r"단\s*한\s*가문의\s*탐욕으로\s*증발",
            "the last roofless Goguryeo timber command platform collapsing into ash",
            "Object-only close low-angle view of one low roofless timber command platform and plain palisade collapsing into ash on a broad sloped rammed-earth rampart; broken beams, packed earth and dense smoke fill every edge with exactly zero people, no visible sky band, tiled roof, tower, palace or sign",
            "Pyongyang Fortress, 668 AD",
        ),
        (
            r"아들들의\s*배신.*외부의\s*군대",
            "one collapsed Goguryeo lamellar command cap pierced from behind",
            "Object-only close ground view of one flattened cluster of cord-tied dark iron and rawhide command-cap plates pierced from the rear by one short iron arrow on bare packed earth; no wearer, head, face, smooth dome, visor or architecture",
            "Pyongyang Fortress wall, 668 AD",
        ),
        (
            r"역사\s*속으로\s*완벽하게\s*사라지는",
            "an abandoned Goguryeo rampart disappearing into ash and snow",
            "A wide empty view of sloped earth-and-rubble Goguryeo ramparts and a collapsed tiled timber gatehouse disappearing behind windblown ash and early snow at dusk",
            "Fallen Pyongyang Fortress, 668 AD",
        ),
        (
            r"제국\s*멸망의\s*마지막\s*핏빛\s*지옥도",
            "one wounded adult Goguryeo survivor before the fallen inner gate",
            "One wounded Goguryeo survivor stands empty-handed in wrapped cloth shoes before a fallen plank gate; burned timber homes, broken timber shields and empty cloth bundles recede through smoke",
            "Pyongyang Fortress final aftermath, 668 AD",
        ),
        (
            r"권력에\s*눈이\s*먼\s*지배층",
            "exactly three adult Goguryeo nobles",
            "Three distinct adult Goguryeo nobles lean over one plain bronze rank seal; sleeve-covered hands stay separate and cold greedy faces remain clear",
            "Pyongyang Fortress court room, 665 AD",
        ),
        (
            r"국방의\s*심장부를.*찔렀",
            "one textless clay fortress relief pierced by one straight iron dagger",
            "Object-only high-angle close view of one short straight iron dagger driven into the central miniature gatehouse of a textless clay-and-stone Goguryeo fortress relief; cracked clay radiates from the blade and the rough dark timber command table fills every image edge",
            "Goguryeo frontier command room, 666 AD",
        ),
        (
            r"동생들에게.*도망",
            "one adult Yeon Namsaeng fleeing on foot",
            "One adult Yeon Namsaeng runs through a muddy winter forest in a dark belted Goguryeo jacket, looking back while both arms and both legs remain connected in a natural stride",
            "Forest road outside Gungnae Fortress, 665 AD",
        ),
        (
            r"최고\s*권력자에서.*도망자",
            "one discarded Goguryeo command cloak and rank belt",
            "Object-only ground view of one dark silk Goguryeo command cloak and bronze rank belt abandoned in a muddy winter puddle under cold rain",
            "Forest road outside Gungnae Fortress, 665 AD",
        ),
        (
            r"벼랑\s*끝에\s*몰린\s*남생",
            "one trapped adult Yeon Namsaeng",
            "One adult Yeon Namsaeng braces against a dead-end rock ravine in a torn Goguryeo court jacket while approaching torchlight spills around the empty muddy path bend",
            "Ravine near Gungnae Fortress, 665 AD",
        ),
        (
            r"치명적인\s*스파이",
            "exactly two adults: Namsaeng; Tang intelligence officer",
            "Yeon Namsaeng places one plain fortress key block and one knotted route cord before a Tang intelligence officer, both adults separated across a low timber table",
            "Tang frontier intelligence room, 667 AD",
        ),
        (
            r"우위대장군.*높은",
            "one adult Yeon Namsaeng as a Tang commander",
            "One adult Yeon Namsaeng stands rigid in fitted Tang lamellar armor over a dark round-collar command robe, a square blank gilt-bronze rank seal at his belt and a cold proud face",
            "Tang imperial court at Chang'an, 666 AD",
        ),
        (
            r"황실\s*조상의\s*이름.*창씨개명",
            "exactly two plain square bronze seal blocks",
            "Object-only extreme close tabletop view: exactly two palm-sized squat square bronze seal blocks stand stamp-faces down; the dull charcoal left knob is completely bare, and only the green-brown right knob carries one compact red cord knot; rough timber fills the entire background",
            "bare rough timber evidence table at Chang'an, 666 AD",
        ),
        (
            r"조국도.*가문의\s*이름도",
            "one discarded Goguryeo clan seal and rank belt",
            "Object-only close view of one plain Goguryeo clan seal and one dark rank belt dropped beside a bronze brazier, their red cord cut on the timber floor",
            "Tang registry chamber at Chang'an, 666 AD",
        ),
        (
            r"연정토.*무리를\s*이끌고\s*도망",
            "exactly four adult riders: Yeon Jeongto and three followers",
            "Exactly four riders on exactly four separate horses flee along one muddy wilderness track in freezing rain; Yeon Jeongto leads front-left and three followers occupy open staggered slots; dense pine slopes, boulders and low earthen banks fill every edge",
            "Pyongyang southern mountain track, 666 AD",
        ),
        (
            r"권력\s*세습은.*자살골",
            "exactly two adult Goguryeo brothers",
            "Two Goguryeo brothers reach from opposite sides for one plain bronze succession seal on an overturned table; distinct armor and separate hands show the fatal struggle",
            "Pyongyang Fortress court hall, 665 AD",
        ),
        (
            r"자질\s*없는\s*후계자들",
            "exactly three starving adult Goguryeo civilians",
            "Exactly three starving adult Goguryeo civilians kneel beside empty grain baskets and a collapsed granary awning in a muddy drainage lane, separate bodies and exhausted faces",
            "Pyongyang fortress settlement, 667 AD",
        ),
        (
            r"투항\s*소식에.*100만\s*대군",
            "Tang invasion forces assembling for a renewed campaign",
            "A wide Tang camp shows limited foreground infantry fastening lamellar armor cords with empty hands while vertical spear racks and stacked timber shields remain behind the tents and long marching columns form in the distance",
            "Tang military camp in Liaodong, 667 AD",
        ),
        (
            r"조국의\s*산천을.*진격",
            "one adult rider Yeon Namsaeng on one horse",
            "One Tang-clad Yeon Namsaeng drives one horse through a muddy Goguryeo road bend, both fists on the reins as one broken plain boundary post falls beneath the horse's forward stride",
            "Liaodong road into Goguryeo, 667 AD",
        ),
        (
            r"어제까지\s*모시던\s*지도자의\s*배신",
            "exactly three adult Goguryeo villagers",
            "Exactly three adult Goguryeo villagers stand apart before burned timber homes, one holding a discarded plain rank belt while grief, disbelief and anger differ across their faces",
            "Goguryeo village road, 667 AD",
        ),
        (
            r"동지를\s*팔고.*적국에\s*엎드",
            "exactly three adults: two officials; soldier",
            "Two Goguryeo officials kneel in mud before one Tang soldier; all three bodies stay separate with period robes, lamellar armor and unarmed hands clear",
            "Tang-held Goguryeo fortress courtyard, 667 AD",
        ),
        (
            r"형제들의\s*권력\s*다툼.*조종",
            "one heavy bronze fortress alarm bell with a severed rope",
            "Object-only close view of one heavy bronze fortress alarm bell hanging silent above a severed hemp rope and an overturned plain rank tablet in an empty smoky courtyard",
            "Pyongyang Fortress court courtyard, 666 AD",
        ),
        (
            r"거대한\s*지옥도가\s*요동",
            "exactly four adults: two defenders; two soldiers",
            "Exactly four adults clash at a burning timber breach: two Goguryeo defenders and two Tang soldiers in separate body slots with straight weapons clear",
            "Liaodong fortress breach, 668 AD",
        ),
        (
            r"남건과\s*남산.*평양성",
            "one adult Goguryeo commander Namgeon",
            "One adult Namgeon braces on a Goguryeo stone-and-earth battlement, one hand gripping a timber parapet and the other holding a short straight command sword low as siege fires surround the wall",
            "Pyongyang Fortress battlement, 667 AD",
        ),
        (
            r"밖에는\s*당나라\s*대군.*불신",
            "exactly three adult Goguryeo defenders",
            "Exactly three adult Goguryeo defenders in distinct lamellar armor stand apart in a cramped timber guard room, suspicious side glances and guarded hands showing fear and distrust",
            "Pyongyang Fortress guard room, 667 AD",
        ),
        (
            r"백성은\s*굶주림.*병사는",
            "exactly three exhausted adult Goguryeo defenders",
            "Exactly three exhausted adult Goguryeo defenders sit separately against broken timber shields beside an empty grain basket, gaunt faces and slumped bodies under cold torchlight",
            "Pyongyang Fortress inner ward, 667 AD",
        ),
        (
            r"내부\s*결속력이\s*파괴",
            "three separated Goguryeo shield panels and one snapped binding cord",
            "Object-only close view of three adjacent timber shield panels separated by a widening gap where one thick red binding cord has snapped on packed earth",
            "Pyongyang Fortress armory yard, 667 AD",
        ),
        (
            r"핏빛\s*파국|single\s+drop.*clear\s+water",
            "one dark-red drop spreading beside a cracked rank seal",
            "Object-only macro view of one dark-red drop spreading through a shallow rain puddle beside one cracked plain bronze rank seal on packed earth",
            "Goguryeo fortress courtyard, 668 AD",
        ),
        (
            r"사슬에\s*묶여\s*끌려가",
            "exactly three adult Goguryeo prisoners: grey-haired elder, brown-robed man, young grey-robed man",
            "Short taut chains join iron wrist cuffs as all three walk in separate side profiles through a blizzard",
            "Liaodong prisoner road, 668 AD",
        ),
        (
            r"영웅담에\s*가려진|영웅\s*찬가에",
            "one torn mud-dark victory sash beside civilian sacrifice evidence",
            "Object-only straight-down ground view of one plain unmarked deep-red woven victory sash, fully mud-streaked and face-down, torn across one broken curved Goguryeo timber shield; exactly three mismatched worn cloth shoes and one folded mud-dark hemp shroud share the packed-earth plane",
            "Liaodong battlefield aftermath, 668 AD",
        ),
        (
            r"동화책은\s*태워버리고.*진짜\s*역사",
            "one blank wooden heroic record-tablet bundle burning beside casualty belongings",
            "Object-only close view of one face-down blank hardwood tablet bundle burning in one low bronze brazier, with two mud-caked woven sandals and scattered cord-tied lamellar shoulder plates on packed earth",
            "Goguryeo fortress record room after battle, 668 AD",
        ),
        (
            r"역사의\s*메스로",
            "one short straight period blade lifting a cracked ceremonial cover",
            "Object-only close evidence view of one short straight period utility blade lifting a cracked gilt ceremonial cover from a mud-stained plain rank seal on rough timber",
            "Goguryeo court evidence table, 668 AD",
        ),
        (
            r"약자는\s*도살당하고",
            "exactly two adults: Tang soldier; Goguryeo defender",
            "One Tang soldier levels a straight spear at one kneeling Goguryeo defender behind a cracked shield; exactly two separate bodies remain in deep snow",
            "Liaodong winter battlefield, 668 AD",
        ),
        (
            r"고대인들의\s*거친.*투쟁",
            "exactly four adult battlefield combatants",
            "Exactly four adult combatants clash across a smoky packed-earth breach, two per side in separate depth slots with straight spears, timber shields and coherent connected limbs",
            "Goguryeo fortress breach, 668 AD",
        ),
        (
            r"시체\s*위에서\s*쵤추는\s*권력|지배층의.*지옥도",
            "abandoned equipment of unnamed Goguryeo dead",
            "Object-only battlefield slope covered with separated broken helmets, snapped spear shafts, torn cloth bundles and deep boot tracks under smoke, with human bodies outside the frame",
            "Liaodong battlefield aftermath, 668 AD",
        ),
        (
            r"숨\s*막히는\s*긴장감\s*끝",
            "one heavy timber fortress gate closing under pressure",
            "Object-only low-angle view of one iron-studded timber fortress gate slamming into its stone threshold as torchlight narrows to one thin seam",
            "Pyongyang Fortress inner gate, 667 AD",
        ),
        (
            r"처절한\s*투지.*기적",
            "one exhausted adult Goguryeo signal defender",
            "One exhausted adult Goguryeo defender crouches behind a cracked timber parapet and shields one newly lit bronze signal brazier spark with both sleeve-covered hands",
            "Pyongyang Fortress battlement, 667 AD",
        ),
        (
            r"영혼을\s*판\s*자들",
            "one dark boot print across a plain Goguryeo command robe",
            "Object-only close view of one dark muddy boot print stamped across a plain folded Goguryeo command robe beside a cut red rank cord on rough stone",
            "Tang-held Goguryeo courtyard, 668 AD",
        ),
        (
            r"전설적인\s*투혼",
            "one adult Goguryeo defender raising a battered straight sword",
            "One adult Goguryeo defender rises beside a broken Tang shield and raises one battered short straight iron sword, coherent body and fierce exhausted face under blowing snow",
            "Liaodong battlefield, 668 AD",
        ),
        (
            r"상대를\s*제압하지\s*못하면",
            "exactly two adult soldiers in a locked struggle",
            "Exactly one Goguryeo defender and one Tang soldier lock separate straight blades above two grounded shields, both adult bodies fully separated in a narrow fortress breach",
            "Goguryeo fortress breach, 668 AD",
        ),
        (
            r"남생의\s*12년\s*당나라\s*충성",
            "exactly three adults: Namsaeng; two soldiers",
            "Tang-clad Namsaeng stands centered and points one short straight spear toward one fallen blank curved timber shield while exactly two Tang soldiers stand in separate left and right slots on open mud; no standards, tents, buildings or signs",
            "open Tang-held Liaodong drill ground, 668-677 AD",
        ),
        (
            r"동족의\s*가슴에\s*창",
            "exactly two adults: Namsaeng; Goguryeo defender",
            "Tang-clad Yeon Namsaeng confronts one Goguryeo defender across locked straight spear shafts, both adult bodies separated beside a fallen blank resistance standard",
            "Liaodong stockade breach, 668-677 AD",
        ),
        (
            r"안동도호부.*탄압하고\s*감시",
            "exactly three adults: Namsaeng; two Goguryeo prisoners",
            "Yeon Namsaeng stands on a low timber platform above exactly two chained Goguryeo prisoners, all three adults separated and each short chain connected only between paired wrists",
            "Andong Protectorate compound in Liaodong, late 7th century",
        ),
        (
            r"당나라\s*무장으로서.*토벌",
            "one adult rider Yeon Heonseong on one horse",
            "Adult Heonseong rides one horse in fitted Tang lamellar armor, bow case fixed to the saddle, both fists gripping reins in a fast side-profile stride",
            "Tang frontier training road, late 7th century",
        ),
        (
            r"이\s*추악한\s*흑막",
            "confiscated Goguryeo belongings behind one plain Tang silk curtain",
            "Object-only ground view of one plain unmarked silk curtain pulled aside over three tied refugee hemp bundles, two short loose iron chain lengths and one discarded woven rank sash on a dark timber floor; no cuffs, hands or people",
            "Tang-held Liaodong command residence, late 7th century",
        ),
        (
            r"눈앞에\s*닥친\s*죽음보다",
            "exactly three adult Goguryeo civilians",
            "Exactly three adult Goguryeo civilians stare at one discarded leader's rank belt in a muddy lane while distant invasion torchlight reaches the gate behind them, distinct faces showing betrayed trust",
            "Pyongyang fortress settlement, 667 AD",
        ),
        (
            r"백성들의\s*삶은.*깔려",
            "exactly two grieving Goguryeo villagers lifting one beam",
            "Exactly two grim Goguryeo villagers lift opposite ends of one fallen granary beam from one crushed timber home; dense collapsed timber rafters, wallboards, broken clay tiles, ruined grain baskets and torn bedding fill every background gap; both wear wrapped cloth shoes",
            "Goguryeo fortress settlement, 668 AD",
        ),
        (
            r"역사상\s*가장\s*서늘한\s*교훈",
            "one elderly adult Goguryeo witness",
            "One elderly adult Goguryeo witness faces the viewer in a tight portrait, natural neck and shoulders, deep grief and hard fire reflections in both eyes against a ruined timber gate",
            "Pyongyang Fortress aftermath, 668 AD",
        ),
        (
            r"피눈물이\s*요동을\s*붉게",
            "a rain-swollen Liaodong river carrying broken war equipment",
            "A wide rain-swollen Liaodong river runs dark with red-clay runoff while separate broken shields, snapped spear shafts and torn blank cloth drift between muddy reeds",
            "Liaodong riverbank after battle, 668 AD",
        ),
        (
            r"승자의\s*역사\s*뒤에\s*버려진",
            "one worn hemp sandal beneath a victory procession's shadows",
            "Object-only ground view of one worn hemp sandal and torn bundle beneath long marching boot shadows, with distant blank victory standards blurred above muddy packed earth",
            "Tang victory road in Liaodong, 668 AD",
        ),
        (
            r"권력에\s*미쳐버린\s*자들의\s*눈",
            "one adult Goguryeo noble clutching three severed red rank cords",
            "One adult Goguryeo noble in a belted wrap-front hemp robe clutches exactly three severed thick red rank cords to his chest with two coherent hands while one ground fire hardens his greedy face; open packed earth and smoke fill every edge with no walls, seals, writing or signs",
            "open Pyongyang Fortress court ground, 667 AD",
        ),
        (
            r"나당\s*연합군.*평양성.*포위",
            "Pyongyang Fortress enclosed by three Tang-Silla siege rings",
            "Wide night view of Pyongyang's stone-and-earth walls enclosed by three rings of tents, campfires, timber traction trebuchets and blank standards, with the last open road sealed",
            "Pyongyang Fortress siege perimeter, 668 AD",
        ),
        (
            r"승자의\s*역사\s*뒤에는\s*도살당한",
            "exactly three dented Goguryeo helmets abandoned in snow",
            "Object-only ground view of exactly three separate dented Goguryeo helmets beside snapped spear shafts and retreating cart tracks in snow under cold dawn light",
            "Liaodong battlefield aftermath, 668 AD",
        ),
        (
            r"억울한\s*원혼들의\s*고통스러운\s*표정",
            "exactly three wounded Goguryeo refugees",
            "Exactly three wounded adult Goguryeo refugees face the viewer from separate depth slots, grief and exhaustion distinct under cold firelight with abandoned helmets behind them",
            "Liaodong battlefield shelter, 668 AD",
        ),
        (
            r"폭력에\s*짓밟힌\s*원혼들.*눈보라",
            "exactly three adult Goguryeo refugees",
            "Exactly three adult Goguryeo refugees push through a blizzard in separate body slots, each carrying one tied hemp bundle while torn robes and exhausted faces remain distinct",
            "Liaodong refugee road, 668 AD",
        ),
        (
            r"체스판.*희생된",
            "three plain stone military counters beside three worn sandals",
            "Object-only close view of three separate plain stone military counters abandoned beside three worn Goguryeo sandals in windblown snow on an unmarked timber surface",
            "Liaodong battlefield command site, 668 AD",
        ),
        (
            r"묘지명에는.*죄책감",
            "one Tang-period family mound and one blank stone marker",
            "Object-only full-bleed view of one low earthen family mound behind one weathered blank stone marker, with a cut dark rank belt and plain face-down bronze clasp in dry grass under dark clouds",
            "dark overcast Mangshan burial ground near Luoyang, late 7th century",
        ),
        (
            r"오직\s*당나라에\s*대한\s*충성심",
            "Tang rank fittings at the Yeon family burial mound",
            "Object-only close view of a square blank Tang rank seal and bronze belt fittings placed before one low earthen burial mound, dry grass covering an old Goguryeo cord",
            "Mangshan burial ground near Luoyang, late 7th century",
        ),
        (
            r"배신자들의\s*이름은\s*돌에",
            "one weathered blank stone marker and one broken clan seal",
            "Object-only low-angle view of one weathered blank stone marker above one broken Goguryeo clan seal and cut red cord in dry grass, hard side light revealing tool scars without writing",
            "Mangshan burial ground near Luoyang, late 7th century",
        ),
        (
            r"북망산에\s*묻힌\s*천남생\s*일가",
            "three low Tang-period Yeon family burial mounds",
            "Wide object-only view of exactly three low earthen family mounds in a row with one plain blank stone marker, dry grass and bronze belt fittings under an overcast sky",
            "Mangshan burial ground near Luoyang, late 7th century",
        ),
        (
            r"내부\s*분열과\s*제국의\s*무자비한\s*침략",
            "a breached Goguryeo fortress district burning from within",
            "Wide view of collapsed timber command halls and breached stone-earth walls burning under storm clouds, broken shield lines and empty baggage carts scattered across packed earth",
            "Fallen Goguryeo fortress district, 668 AD",
        ),
        (
            r"100만\s*대군의\s*발걸음",
            "Tang infantry columns advancing toward Pyongyang",
            "Tang infantry in fitted lamellar armor march toward one distant broad sloped rammed-earth rampart faced with irregular rubble stone and topped only by a low timber palisade; no gatehouse, roof, plaque, banner or writing",
            "Liaodong road toward Pyongyang, 667 AD",
        ),
        (
            r"미친\s*발버둥이\s*낳은.*지옥도",
            "abandoned Goguryeo defense gear in a burned inner ward",
            "Object-only wide ground view of separate broken helmets, cracked shields, snapped spear shafts and torn bundles across a burned fortress inner ward, with human bodies outside the frame",
            "Pyongyang Fortress inner ward, 668 AD",
        ),
        (
            r"동생\s*남건이\s*총사령관",
            "one adult Goguryeo commander Namgeon",
            "One adult Namgeon in dark Goguryeo lamellar armor shouts orders from a damaged stone-earth battlement, one hand on the timber parapet and one short straight command sword held low",
            "Pyongyang Fortress battlement, 668 AD",
        ),
        (
            r"시체\s*위에서",
            "abandoned equipment of unnamed Goguryeo dead",
            "Object-only empty battlefield ground covered by separate broken helmets, snapped straight spear shafts, torn hemp cloth and deep boot tracks under dark smoke",
            "Liaodong battlefield aftermath, 668 AD",
        ),
        (
            r"한\s*번\s*배신한\s*자",
            "exactly three adults: Namsaeng; two prisoners",
            "Namsaeng turns away from two chained Goguryeo prisoners; exactly three separate adults remain, one short chain linking only the prisoners' inner wrists",
            "Tang-held Liaodong command compound, late 7th century",
        ),
    )
    for pattern, subject, action, place in overrides:
        if re.search(pattern, spoken, re.IGNORECASE):
            return subject, action, place
    return None


def _concretize_goguryeo_succession_runtime_scene(
    scene: str,
    narration: str,
) -> tuple[str, str, str]:
    """Turn late-Goguryeo metaphors into drawable, period-specific evidence."""
    source_scene = _clean_spaces(scene)
    spoken = str(narration or "")
    basis = f"{spoken} {source_scene}"
    place = _goguryeo_succession_runtime_place(source_scene, spoken)

    if re.search(r"제\s*29화|마칩니다|title\s*card|Episode\s*30", basis, re.IGNORECASE):
        return (
            "a scorched blank Goguryeo war standard",
            "A scorched blank Goguryeo war standard collapses beside a broken spear at dusk, ash crossing the packed-earth fortress courtyard under hard red firelight",
            "Pyongyang Fortress after the succession war, 668 AD",
        )
    narration_override = _goguryeo_succession_narration_override(spoken)
    if narration_override:
        return narration_override
    if re.search(r"16살|둘째\s*아들\s*헌성|young\s+boy", basis, re.IGNORECASE):
        return (
            "exactly two people: Heonseong; Tang escort",
            "Sixteen-year-old male Yeon Heonseong in a belted Goguryeo jacket and trousers kneels before one Tang escort in a round-collar robe and black futou, both bodies separate against plain timber walls",
            "Tang imperial court at Chang'an, 666 AD",
        )
    if re.search(r"인질을\s*바치|납작\s*엎드|살려달라|hostage|begging|pleading", basis, re.IGNORECASE):
        return (
            "exactly two people: teenage Heonseong; older Tang envoy",
            "Teenage Heonseong kneels on both knees before one standing older Tang envoy in black futou as a small tan cord-tied cloth packet lies flat between them",
            "Tang imperial court at Chang'an, 666 AD",
        )
    if re.search(r"적국인\s*당나라에\s*투항|목숨을\s*구걸|남생.*투항|Namsaeng.*(?:surrender|asylum)", basis, re.IGNORECASE):
        return (
            "exactly two adults: Namsaeng; Tang frontier envoy",
            "Yeon Namsaeng kneels before one Tang frontier envoy and offers a closed blank cloth petition packet with both sleeve-covered hands, his discarded Goguryeo rank belt lying behind him",
            "Gungnae Tang command hall, 666 AD",
        )
    if re.search(r"성문.*(?:열|열리)|내통.*성문|unlock(?:ing)?|opening\s+heavy\s+wooden\s+gates", basis, re.IGNORECASE):
        role = "one adult Goguryeo monk" if re.search(r"승려|monk", basis, re.IGNORECASE) else "one adult Goguryeo traitor guard"
        if "monk" in role:
            action = (
                "A shaved-head Goguryeo monk in an undyed wrap-front robe pulls one timber gate bar from iron brackets; "
                "enemy spear tips and torchlight press through the opening seam; one complete body"
            )
        else:
            action = (
                "One Goguryeo traitor guard pulls a timber gate bar from iron brackets at night; enemy torchlight enters "
                "through the opening seam; one complete body"
            )
        return (
            role,
            action,
            "Goguryeo fortress gate interior, 667-668 AD",
        )
    if re.search(r"6개\s*성|six\s+fortress|six\s+castles", basis, re.IGNORECASE):
        return (
            "exactly two adults: Namsaeng; Tang officer",
            "Namsaeng slides six separate unmarked bronze-bound fortress tallies across a low table to one Tang officer; both men remain tense under lamplight",
            "Tang frontier command hall near Gungnae Fortress, 666 AD",
        )
    if re.search(r"10만\s*가구|백성들.*(?:노예|헌납)|citizens?.*(?:captiv|march)", basis, re.IGNORECASE):
        return (
            "displaced Goguryeo families under Tang guard",
            "A limited foreground group of exhausted Goguryeo families walks under Tang guard through a muddy fortress gate, separate bodies carrying tied cloth bundles while a longer captive column recedes into smoke",
            "Gungnae Fortress under Tang control, 666 AD",
        )
    if re.search(r"원혼|ghostly|ghosts?|victory\s+painting.*skull", basis, re.IGNORECASE) and not re.search(
        r"영웅담에\s*가려진.*희생|영웅\s*찬가.*전쟁의\s*참혹",
        spoken,
        re.IGNORECASE,
    ):
        return (
            "exactly three wounded Goguryeo refugees abandoned after battle",
            "Three wounded Goguryeo refugees reach toward a retreating supply cart through snow and mud, their separate exhausted bodies, torn hemp clothing, abandoned helmets, and grief-stricken adult faces visible under cold dawn light",
            "Liaodong battlefield aftermath, 668 AD",
        )
    if re.search(r"장기말|체스판|소모품|pawn|chess", basis, re.IGNORECASE):
        return (
            "exactly three adults, one gaunt Goguryeo refugee and two armored officials",
            "One gaunt Goguryeo refugee is forced past a low command table while two armored officials move separate plain stone counters among route cords, all three bodies separated and every counter unmarked",
            "Goguryeo fortress command district, 666-668 AD",
        )
    if re.search(r"군사\s*기밀|모든\s*지형|성곽의\s*약점|detailed\s+map|tactical\s+map|map\s+showing|map\s+of\s+Goguryeo", basis, re.IGNORECASE):
        return (
            "one textless Goguryeo defense-route handover layout",
            "Object-only overhead evidence: exactly six grey stones form a top row of three and a bottom row of three; one straight red cord in the empty middle gap joins one grey sash at left to one black sash at right; installed rough floor planks continue beyond every canvas edge",
            "Liaodong Tang campaign room, 667 AD",
        )
    if re.search(r"핏자국|footprint.*map|dagger.*map", basis, re.IGNORECASE):
        return (
            "exactly two adults: Namsaeng; Tang commander",
            "Yeon Namsaeng places a mud- and blood-stained bundle of plain Goguryeo fortress tallies into a Tang commander's hands across a low table, his discarded Goguryeo rank belt on the floor",
            "Tang frontier command hall near Gungnae Fortress, 666 AD",
        )
    if re.search(r"성씨|창씨개명|가문의\s*이름|crossing\s+out\s+a\s+name|new\s+name|family\s+portrait", basis, re.IGNORECASE):
        return (
            "one severed grey woven Goguryeo clan sash",
            "Object-only straight-down close view on edge-to-edge dark timber: exactly one wide grey woven clan sash lies severed once across its width into exactly two separated halves; one clean empty gap divides the facing frayed cut edges",
            "dark timber registry wall at Chang'an, 666 AD",
        )
    if re.search(r"당\s*고종|golden\s+seal|Gaozong", basis, re.IGNORECASE):
        return (
            "exactly two adults: Emperor Gaozong; Namsaeng",
            "Tang Emperor Gaozong presents Yeon Namsaeng with a square gilt-bronze rank seal block with a short handle, its blank seal surface angled away, both men shown as separate bodies",
            "Tang imperial audience hall at Chang'an, 666 AD",
        )
    if re.search(
        r"대막리지가\s*적국\s*장수|적국\s*장수로\s*돌변|mirror.*turning|"
        r"shield.*(?:forged|turning|becoming).*weapon",
        basis,
        re.IGNORECASE,
    ):
        return (
            "exactly two adults: Namsaeng; Tang attendant",
            "Namsaeng removes his dark Goguryeo rank belt while one Tang attendant presents a lamellar command overcoat; two separate adults share one court moment",
            "Tang frontier command hall, 666 AD",
        )
    if re.search(r"대군이\s*오면.*선봉|정벌의\s*선봉", spoken, re.IGNORECASE):
        return (
            "exactly two adults: Namsaeng; Tang commander",
            "Namsaeng plants one short straight sword point-down and swears service before one Tang commander; two separate bodies stand in a cold timber hall",
            "Gungnae Tang command hall, 666 AD",
        )
    if re.search(r"앞잡이|선봉\s*길잡이|선봉에\s*서|조국의\s*산천|12년\s*당나라\s*충성", basis, re.IGNORECASE):
        return (
            "one adult rider Yeon Namsaeng on one horse",
            "Yeon Namsaeng leans forward as his horse turns into one muddy road fork. Both lowered fists grip the paired leather reins at the saddle pommel. Storm clouds and mortised split-log rails fill the frame",
            "storm-dark Liaodong muddy military road enclosed by thick split-log rails, 667 AD",
        )
    if re.search(r"장기말|핏빛\s*체스판|chessboard|pawn\s+on\s+a\s+board", basis, re.IGNORECASE):
        return (
            "Goguryeo refugees beneath elite military decisions",
            "Goguryeo refugees pass a low military table where separate plain stone counters and route cords are moved by two sleeve-covered officials, with no grid, board game, or marked surface",
            place,
        )
    if re.search(r"겉으로는\s*강철|속에서부터.*곪|내부의\s*부패|iron\s+apple|rotten\s+(?:core|fruit)|worm-infested\s+fruit", basis, re.IGNORECASE):
        return (
            "a cracked Goguryeo granary jar filled with spoiled millet",
            "Object-only close evidence view of one cracked plain clay granary jar spilling blackened spoiled millet through a hidden inner fracture onto bare packed earth",
            "Goguryeo fortress granary, 666-668 AD",
        )
    if re.search(r"권력\s*세습|자살골|독재.*독|독약|crown.*poison|acid.*fortress|snake.*tail", basis, re.IGNORECASE):
        return (
            "exactly two adult Goguryeo brothers",
            "Two adult Goguryeo brothers in distinct lamellar armor turn short straight iron blades against each other inside a smoky timber courtyard, separated silhouettes with broken spear shafts and an overturned rank table behind them",
            "Pyongyang Fortress court courtyard, 665-666 AD",
        )
    if re.search(r"한\s*번\s*배신|합리화.*괴물", spoken, re.IGNORECASE):
        return (
            "one adult Yeon Namsaeng ignoring Goguryeo prisoners",
            "One adult Yeon Namsaeng in Tang lamellar armor turns his face away from chained Goguryeo prisoners passing behind a timber screen, his jaw rigid and posture deliberately cold",
            "Tang-held Liaodong command compound, late 7th century",
        )
    if re.search(r"괴물로\s*돌변|monstrous\s+shadow|cracked\s+statue", basis, re.IGNORECASE):
        return (
            "exactly two adult Goguryeo guards arranging betrayal",
            "Two resentful Goguryeo guards exchange one plain fortress key block in a cracked timber passage; separate tense faces, smoke and an unguarded gate remain behind",
            "Goguryeo fortress interior, 667 AD",
        )
    if re.search(r"warrior'?s\s+face.*mud|face.*demon", source_scene, re.IGNORECASE):
        return (
            "one mud-caked adult Goguryeo soldier forcing himself upright",
            "One exhausted adult Goguryeo soldier drags himself upright against a broken shield; thick wet mud visibly cakes his forehead, both cheeks, hairline, jaw, hands, and torn wrap-front robe while his eyes and clenched teeth remain clear under cold firelight",
            "Goguryeo battlefield edge, 668 AD",
        )
    if re.search(r"cornered\s+rat|rat\s+bowing", source_scene, re.IGNORECASE):
        return (
            "exactly two adults: Namsaeng; Tang envoy",
            "A desperate Yeon Namsaeng kneels low before one Tang envoy and offers his plain fortress tally belt, both bodies separate while his abandoned Goguryeo cloak lies in mud",
            "Gungnae Tang command hall, 666 AD",
        )
    if re.search(r"rat.*escaping.*trap", source_scene, re.IGNORECASE):
        return (
            "one Goguryeo collaborator escaping through a guarded gate",
            "One adult Goguryeo collaborator slips through a half-open timber gate under Tang protection while confiscated refugee bundles remain behind in the mud",
            "Tang-held Goguryeo frontier gate, 668 AD",
        )
    if re.search(r"pack\s+of\s+wolves|wolves.*prey", source_scene, re.IGNORECASE):
        return (
            "Tang infantry overwhelming isolated Goguryeo defenders",
            "A limited foreground line of Tang infantry surrounds two exhausted Goguryeo defenders in deep snow, separate bodies and spear points forming visible pressure without animal imagery",
            "Liaodong winter battlefield, 668 AD",
        )
    if re.search(r"wolf.*weak\s+neck|wolf.*deer|predatory\s+wolf", source_scene, re.IGNORECASE):
        return (
            "one exhausted Goguryeo defender encircled by Tang soldiers",
            "One exhausted Goguryeo defender braces behind a cracked shield while three separated Tang spear points close on his exposed flank, his fear and physical weakness clearly visible",
            "Liaodong battlefield breach, 668 AD",
        )
    if re.search(r"two.*wolves|same\s+pack|tiger.*tiger", source_scene, re.IGNORECASE):
        return (
            "exactly two adult Goguryeo brothers attacking each other",
            "Two Goguryeo brothers in distinct rust-brown and charcoal lamellar armor clash with short straight blades on an open snowy packed-earth slope; separate complete bodies and anguished faces show destroyed kinship, with no buildings or signs",
            "open ground outside Pyongyang Fortress, 666 AD",
        )
    if re.search(
        r"짐승\s*같은|괴물이\s*된|야생의\s*법칙|내부의\s*맹수|"
        r"\b(?:rats?|wolves?|tigers?|predator|deer)\b",
        basis,
        re.IGNORECASE,
    ):
        return (
            "exactly two rival adult Goguryeo elites",
            "Two rival Goguryeo elites grapple in a muddy fortress passage while one reaches for a short straight iron blade, their separate adult bodies and faces showing fear, rage, and raw survival",
            "Goguryeo fortress district during the succession war, 666 AD",
        )
    if re.search(r"모래성|국가\s*전체.*붕괴|sandcastle", basis, re.IGNORECASE):
        return (
            "a sabotaged Goguryeo fortress gate collapsing inward",
            "A heavy timber Goguryeo fortress gate collapses inward after its braces are cut from inside, defenders stumbling apart through dust while enemy silhouettes approach beyond the breach",
            "Goguryeo frontier fortress, 667 AD",
        )
    if re.search(r"종이\s*조각|휴지조각|parchment.*(?:burn|dissolv)|piece\s+of\s+paper", basis, re.IGNORECASE):
        return (
            "a severed Goguryeo kinship seal cord",
            "Object-only close evidence view of one cut red kinship cord, two separated plain unmarked clan seals, and a scorched empty cloth packet on a low wooden table",
            "Goguryeo court archive chamber, 666 AD",
        )
    if re.search(r"영웅담에\s*가려진.*희생|영웅\s*찬가.*전쟁의\s*참혹", spoken, re.IGNORECASE):
        return (
            "exactly three adults: one wounded soldier; two stretcher bearers",
            "One wounded adult soldier lies full-length on one simple timber stretcher; one exhausted survivor kneels at the left head handle and one at the right foot handle, with three distinct heads and torsos in separated slots",
            "Liaodong battlefield aftermath, 668 AD",
        )
    if re.search(r"낡은\s*위인전|거짓\s*영웅\s*서사", spoken, re.IGNORECASE):
        return (
            "a discarded blank heroic tablet beside refugee belongings",
            "Object-only close evidence view of a discarded blank wooden heroic tablet bundle in wet mud beside worn refugee sandals, a torn hemp bundle, and one dented helmet",
            "Goguryeo refugee road, 668 AD",
        )
    if re.search(r"영웅\s*전설의\s*껍데기|껍데기를.*벗겨", spoken, re.IGNORECASE):
        return (
            "one cracked plain gilt-bronze cover plate exposing mud-damaged lamellar material",
            "Object-only straight-down view of one plain unmarked cracked gilt-bronze cover plate lifted aside from three separate mud-dark cord-tied lamellar plate clusters and one snapped bow on a bare rough stone slab; no people, clothing, footwear or writing",
            "Pyongyang battlefield aftermath, 668 AD",
        )
    if re.search(r"동화|위인전|영웅담|영웅\s*전설|history\s+book|fairy[- ]tale|old\s+book|painting.*(?:bones|skull)|historical\s+document.*skeletal", basis, re.IGNORECASE):
        return (
            "a blank heroic record tablet bundle burning beside war casualties' gear",
            "Object-only close evidence view of a blank wooden heroic record-tablet bundle burning in a low bronze brazier beside mud-caked abandoned sandals, a broken helmet, and a snapped spear",
            "Goguryeo fortress record room after battle, 668 AD",
        )
    if re.search(r"원혼|ghostly|ghosts?|victory\s+painting.*skull", basis, re.IGNORECASE):
        return (
            "wounded Goguryeo refugees abandoned after battle",
            "Wounded Goguryeo refugees reach toward a retreating supply cart through snow and mud, their separate exhausted bodies, torn hemp clothing, abandoned helmets, and grief-stricken adult faces visible under cold dawn light",
            "Liaodong battlefield aftermath, 668 AD",
        )
    if re.search(r"해골|skulls?|bones|도살당한.*병사|mountain\s+of\s+crushed", basis, re.IGNORECASE):
        return (
            "abandoned equipment of unnamed Goguryeo dead",
            "A battlefield slope is covered with separate broken helmets, snapped spear shafts, torn cloth bundles, and deep boot tracks while distant survivors carry one wounded soldier through smoke",
            "Liaodong battlefield aftermath, 668 AD",
        )
    if re.search(r"수레바퀴|iron\s+gear|mechanical|wheel.*(?:weapon|body)", basis, re.IGNORECASE):
        return (
            "a heavy wooden military cart wheel crushing abandoned equipment",
            "One heavy wooden military cart wheel rolls over a broken shield rim and snapped spear shafts in deep mud, the cart structure coherent and distant soldiers reduced to separated silhouettes",
            "Liaodong military road, 667-668 AD",
        )
    if re.search(r"씻을\s*수\s*없는\s*흉터|scar.*marble|piece\s+of\s+marble", basis, re.IGNORECASE):
        return (
            "a permanently cracked Goguryeo fortress foundation stone",
            "Object-only close evidence view of one rough fortress foundation stone split by a deep dark-red-stained crack, rainwater tracing the old damage across packed earth",
            "Fallen Goguryeo fortress, 668 AD",
        )
    if re.search(r"투기장|gladiator\s+arena", basis, re.IGNORECASE):
        return (
            "Goguryeo-Tang fortress combat",
            "Goguryeo and Tang soldiers clash in a smoky packed-earth fortress courtyard, limited foreground combatants with separate bodies, short straight iron weapons, broken shields, and hard torch shadows",
            "Pyongyang Fortress outer courtyard, 668 AD",
        )
    if re.search(r"메스|surgical\s+(?:blade|scalpel)|scalpel", basis, re.IGNORECASE):
        return (
            "a short straight period iron blade cutting an elite seal cord",
            "Object-only close evidence view of one short straight period iron utility blade cutting a red cord between two plain unmarked elite seals on rough timber",
            "Goguryeo court evidence table, 666-668 AD",
        )
    if re.search(r"나비효과|옥죄|hangman'?s\s+noose|noose", basis, re.IGNORECASE):
        return (
            "Pyongyang Fortress enclosed by tightening siege lines",
            "Pyongyang Fortress sits isolated beyond three tightening rings of Tang campfires, timber siege works, and guarded earthworks while smoke closes over the remaining open road",
            "Besieged Pyongyang Fortress",
        )
    if re.search(r"비단|silk\s+cloth.*trampled", basis, re.IGNORECASE):
        return (
            "one cropped Tang-era cloth-wrapped forefoot pressing one torn Goguryeo silk sash into mud",
            "Object-only extreme close view of one cropped Tang-era cloth-wrapped forefoot pressing exactly one torn Goguryeo silk sash into freezing mud, with only the smooth sole, short wrapped ankle crop, cloth and contact point visible",
            "Liaodong prisoner road, 668 AD",
        )
    if re.search(r"충신은\s*죽고.*매국노|chalice.*blood", basis, re.IGNORECASE):
        return (
            "a fallen Goguryeo loyalist's helmet outside a Tang feast",
            "Object-dominant ground view of one dented Goguryeo loyalist helmet and broken spear in cold mud, while a distant Tang residence doorway reveals small bronze cups raised at a low table",
            "Tang elite residence at Chang'an, late 7th century",
        )
    if re.search(r"권력이라는\s*마약|poisonous.*bubbling\s+liquid", basis, re.IGNORECASE):
        return (
            "a shallow bronze cup beside a discarded Goguryeo seal",
            "Object-only close evidence view of one shallow bronze cup spilling dark wine across a discarded plain Goguryeo seal and red rank cord on a low Tang table",
            "Tang elite residence at Chang'an, late 7th century",
        )
    if re.search(r"축배|부귀|wine|chalice|golden\s+cup|poisonous.*liquid", basis, re.IGNORECASE):
        return (
            "exactly three adult men in low black head-wrap caps: elderly, middle-aged, young adult",
            "Elderly left, middle-aged center and young adult right lean inward with cold smug half-smiles around one small shallow bronze cup resting at table center. Each man folds his own two hands together and wears a low black cloth cap covering tied hair plus a long dark robe with a smooth closed circular neckline and uninterrupted chest cloth",
            "plain undecorated Tang elite residence interior at Chang'an, late 7th century",
        )
    if re.search(r"현대인|modern\s+(?:person|face)|cracked.*mirror", basis, re.IGNORECASE):
        return (
            "an exhausted Goguryeo survivor facing a cracked bronze mirror",
            "One exhausted adult Goguryeo survivor studies a cracked polished-bronze mirror by oil-lamp light, one coherent reflection aligned with the same face, period hemp robe and timber room visible",
            "Goguryeo refugee shelter, 668 AD",
        )
    if re.search(r"정당화하며\s*변명|deceptive\s+calligraphy|parchment.*calligraphy", basis, re.IGNORECASE):
        return (
            "one closed plain wooden box between two snapped hemp ropes",
            "Object-only straight-down view of one plain closed wooden box with uninterrupted grain on featureless light packed earth, with exactly two short snapped natural hemp ropes lying loose beside it; no people, hands, cloth, tag, plaque, paper, seal, architecture or writing",
            "open Tang-held Liaodong registry yard, late 7th century",
        )
    if re.search(r"폭풍을\s*준비.*전쟁|storm\s+cloud.*ancient\s+map", basis, re.IGNORECASE):
        return (
            "Tang columns advancing toward a storm-covered Goguryeo fortress",
            "Several Tang infantry columns advance across muddy open ground toward a distant Goguryeo timber-and-earth fortress as a real storm front and windblown smoke close over the road",
            "Liaodong road toward Pyongyang, 667 AD",
        )
    if re.search(r"민낯을\s*봐야|unblinking\s+human\s+eye", basis, re.IGNORECASE):
        return (
            "one wounded adult Goguryeo witness",
            "One wounded adult Goguryeo witness turns toward the viewer in a tight face-focused moment, soot, grief, and controlled anger visible while a ruined timber gate burns behind him",
            "Goguryeo fortress aftermath, 668 AD",
        )
    if re.search(r"신라로.*투항|defector.*Silla", basis, re.IGNORECASE):
        return (
            "exactly two adults: Yeon Jeongto; Silla frontier guard",
            "Yeon Jeongto dismounts before one Silla frontier guard and presents a closed blank cloth surrender packet, both adults separate beside a plain unmarked Silla war standard in cold rain",
            "Silla northern frontier camp, 666 AD",
        )
    if re.search(r"묘지명|무덤|북망산|tombstone|epitaph|words\s+carved|tombs?", basis, re.IGNORECASE):
        return (
            "the Yeon Namsaeng family burial mound and blank stone marker",
            "Object-only wide evidence view of a low earthen Tang-period family burial mound behind one weathered plain unmarked stone marker angled away, dry grass and abandoned Goguryeo belt fittings at the base",
            "Mangshan burial ground near Luoyang, late 7th century",
        )
    if (
        re.search(r"\bHeonseong\b|헌성", basis, re.IGNORECASE)
        and re.search(r"활잡이|arrow.*camera|archer", basis, re.IGNORECASE)
    ):
        return (
            "one adult rider Heonseong on one horse",
            "Adult Heonseong releases one arrow from a recurved bow while riding one separate horse in side profile; dark overcast sky fills above and a rough timber palisade with packed earth fills every edge",
            "dark overcast Tang frontier training ground enclosed by timber palisade, late 7th century",
        )
    if re.search(r"안동도호부|탄압하고\s*감시|balcony.*chained", basis, re.IGNORECASE):
        return (
            "Yeon Namsaeng supervising Tang guards over Goguryeo prisoners",
            "Yeon Namsaeng stands on a timber watch platform while Tang guards inspect chained Goguryeo prisoners below, every body separated, chains connected only wrist to wrist, his expression cold and controlled",
            "Andong Protectorate compound in Liaodong, late 7th century",
        )
    if re.search(r"동족의\s*가슴|부흥\s*운동|compatriot|rebel\s+flag", basis, re.IGNORECASE):
        return (
            "Yeon Namsaeng's Tang unit suppressing Goguryeo resistance",
            "Tang-clad Yeon Namsaeng directs soldiers against Goguryeo resistance fighters in a muddy stockade breach, short straight spear points held away from fused bodies and one blank rebel standard falling under a grounded boot",
            "Liaodong frontier under Tang occupation, 668-677 AD",
        )
    if re.search(r"외부의\s*적에게\s*무너지지|700년\s*제국의\s*철벽", spoken, re.IGNORECASE):
        return (
            "an intact Goguryeo outer wall with its command hall burning inside",
            "A massive Goguryeo stone-and-earth fortress wall remains intact under a grey sky while smoke and fire rise from the timber command hall behind it, exposing collapse from within",
            "Goguryeo fortress district, 668 AD",
        )
    if re.search(r"지도자의\s*탐욕.*최후|stone\s+pillar\s+cracking", basis, re.IGNORECASE):
        return (
            "a cracked timber-and-stone Goguryeo court support",
            "One heavy timber court post tears free from its rough stone footing inside an abandoned Goguryeo hall, roof beams sagging through dust while broken rank objects lie below",
            "Pyongyang court hall, 668 AD",
        )
    if re.search(r"백성들의\s*삶.*깔려|pillar.*crushing.*houses", basis, re.IGNORECASE):
        return (
            "collapsed fortress granary beams over civilian homes",
            "Collapsed fortress granary beams and rough stones crush two small timber homes while displaced Goguryeo families pull one survivor from the debris, bodies separated under dust",
            "Goguryeo fortress settlement, 668 AD",
        )
    if (
        re.search(r"iron\s+shield|stone\s+pillar|국가의\s*기둥", basis, re.IGNORECASE)
        or (
            re.search(r"철벽", basis, re.IGNORECASE)
            and re.search(r"성문|빗장|gate|brace|locking|beam", basis, re.IGNORECASE)
        )
    ):
        return (
            "one sabotaged Goguryeo timber gate brace",
            "Object-only interior close view of exactly one horizontal timber locking beam spanning one plank gate; one deep triangular V-shaped axe notch removes the lower half at exact center, exposing pale flat chopped facets and repeated axe scars while irregular small fieldstones embedded in rammed earth fill the intact wall",
            "Goguryeo frontier fortress inner gate, 667 AD",
        )
    if re.search(r"대막리지의\s*아들.*충성을\s*맹세", spoken, re.IGNORECASE):
        return (
            "exactly two adult men with black-capped Emperor Gaozong seated right and grey-robed Namsaeng kneeling left in wrapped shoes",
            "Black-capped Gaozong in a dark closed round-neck robe sits right on a low dais opposite grey wrap-front-robed Namsaeng kneeling left in wrapped cloth shoes",
            "Chang'an Tang audience hall, 666 AD",
        )
    if re.search(r"iron\s+boot.*discarded\s+crown|시체\s*위에서\s*춤추는\s*권력", basis, re.IGNORECASE):
        return (
            "one Tang officer's boot crushing a discarded Goguryeo rank tablet",
            "One grounded Tang officer's leather boot presses a cracked plain Goguryeo bronze rank tablet into battlefield mud beside a torn blank standard and broken spear",
            "Liaodong battlefield, 668 AD",
        )
    if re.search(r"poisoned\s+arrow.*royal\s+emblem|아들들의\s*배신.*치명", basis, re.IGNORECASE):
        return (
            "a broken Goguryeo command standard struck from behind",
            "One short iron arrow pierces the back of a plain blank Goguryeo command standard mounted on rough timber, splitting the pole while the distant fortress wall remains under siege",
            "Pyongyang Fortress wall, 668 AD",
        )
    if re.search(r"왕좌|throne|royal\s+emblem|discarded\s+crown", basis, re.IGNORECASE):
        return (
            "a broken Goguryeo succession seat and rank tablet",
            "A low dark wooden ruler seat lies overturned beside one cracked plain bronze rank tablet while rival Goguryeo guards clash in the smoky hall behind it",
            "Pyongyang Fortress audience hall, 666 AD",
        )
    if re.search(r"나당\s*연합군.*무기|dagger.*(?:rope|cord)|slicing.*rope", basis, re.IGNORECASE):
        return (
            "a Tang iron dagger severing a Goguryeo defense cord",
            "Object-only macro view of one short straight Tang iron dagger cutting one thick red Goguryeo defense cord across bare rough timber grain; only the dagger, cord and unmarked timber surface are visible",
            "Liaodong Tang command hall, 667 AD",
        )
    if re.search(r"비수|dagger|knife\s+behind", basis, re.IGNORECASE):
        return (
            "a Goguryeo court guard concealing a short straight iron dagger",
            "One adult Goguryeo court guard watches an official's exposed back while concealing a short straight iron dagger close behind his own robe, one coherent body and a tense natural neck posture",
            "Pyongyang Fortress court corridor, 666 AD",
        )

    out = source_scene
    replacement_subject = ""
    if re.search(r"\b(?:heavy\s+)?iron\s+gate\b", source_scene, re.IGNORECASE):
        replacement_subject = "one heavy timber fortress gate with small iron studs"
    replacements = (
        (r"\b(?:heavy\s+)?iron\s+gate\b", "heavy timber fortress gate with small iron studs"),
        (r"\bmarble\s+floor\b", "dark timber court floor"),
        (r"\bgladiator\s+arena\b", "smoky packed-earth fortress courtyard"),
        (r"\bsurgical\s+(?:blade|scalpel)\b", "short straight period iron utility blade"),
        (r"\bchessboard\b", "plain low command table with route cords and separate stone counters"),
        (r"\bpawn\b", "plain stone military counter"),
        (r"\bgolden\s+throne\b", "low dark wooden ruler seat"),
        (r"\b(?:golden\s+)?chalice\b", "small shallow bronze cup"),
        (r"\bmodern\s+(?:person|face)\b", "adult Goguryeo survivor"),
        (r"\bmassive\s+iron\s+gear\b", "heavy wooden military cart wheel"),
    )
    for pattern, replacement in replacements:
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    return replacement_subject, _clean_spaces(out), place


def _goguryeo_succession_material_contract(subject: str, scene: str) -> str:
    text = f"{subject} {scene}"
    if re.search(r"wounded\s+captured\s+Goguryeo\s+commander\s+Namgeon\s+bound\s+around\s+the\s+chest", text, re.IGNORECASE):
        return "continuous rust-brown Goguryeo iron lamellar rows without front opening or buttons, muted-grey buttonless wrap-front robe, one continuous thick undyed hemp rope with three horizontal turns around chest and upper arms, blank earthen wall, charcoal smoke"
    if re.search(r"kneeling\s+King\s+Bojang\s+and\s+standing\s+Tang\s+general\s+Li\s+Ji", text, re.IGNORECASE):
        return "muted deep-grey buttonless wrap-front royal robe and wrapped cloth shoes on Bojang, fitted dark Tang iron lamellar over a smooth closed round-collar robe and one low close-fitting conical riveted iron helmet with zero brim on Li Ji, packed earth, blank burned earthen wall"
    if re.search(r"gilt-bronze\s+royal\s+diadem\s+ornament\s+plate\s+split\s+into\s+two\s+halves", text, re.IGNORECASE):
        return "one palm-sized thin flat gilt-bronze flame-shaped ornament plate, exactly two matching halves, one narrow break gap, cold rain mud"
    if re.search(r"uninscribed\s+Goguryeo\s+bronze\s+mirror\s+with\s+one\s+deep\s+center\s+split", text, re.IGNORECASE):
        return "exactly one palm-sized thin flat handleless round cast-bronze mirror disk, one deep top-to-bottom jagged center crack, soot, fine grey ash, tiny orange embers"
    if re.search(r"blank\s+wood-slip\s+bundle\s+overlapping\s+one\s+blank\s+bronze\s+plaque\s+inside\s+the\s+same\s+fire", text, re.IGNORECASE):
        return "exactly one face-down blank-backed hardwood record-slip bundle, exactly one small thin flat blank bronze plaque tucked partly beneath it, one connected bright orange fire touching both, blackened edges, warm medium-brown packed earth"
    if re.search(r"cangue-bound\s+Goguryeo\s+captive", text, re.IGNORECASE):
        return "muted-grey hemp wrap robe, plain rectangular split-board timber neck cangue, cold mud"
    if re.search(r"captive\s+King\s+Bojang\s+and\s+wounded\s+Namgeon", text, re.IGNORECASE):
        return "muted deep-grey buttonless wrap-front royal robe and wrapped cloth shoes on Bojang, torn rust-brown fitted Goguryeo iron lamellar over a muted-grey wrap-front robe and wrapped cloth shoes on Namgeon, bare packed earth, blank plaster wall"
    if re.search(r"Emperor\s+Gaozong\s+confronting\s+kneeling\s+King\s+Bojang", text, re.IGNORECASE):
        return "close black cloth Tang futou cap, dark smooth-front buttonless round-collar paofu on Gaozong, muted-grey wrap robe on Bojang"
    if re.search(r"Tang\s+rewards\s+laid\s+over\s+discarded\s+Goguryeo\s+allegiance", text, re.IGNORECASE):
        return "one torn grey sash with two frayed ends, one face-down blank-backed bronze Tang rank seal, clean dark timber"
    if re.search(r"Tang\s+rank\s+seal\s+and\s+one\s+severed\s+Goguryeo\s+sash\s+at\s+the\s+Yeon\s+family\s+mound", text, re.IGNORECASE):
        return "one thin flat blank-backed bronze Tang rank seal, exactly one severed dark-grey Goguryeo sash forming exactly two straight aligned halves, dry reddish earth"
    if re.search(r"intact\s+Goguryeo\s+outer\s+wall\s+with\s+unseen\s+interior\s+fire\s+behind\s+it", text, re.IGNORECASE):
        return "one unbroken sloped fieldstone-and-rammed-earth outer wall, sparse low timber parapet, orange firelight and thick black smoke rising behind"
    if re.search(r"Goguryeo\s+gate\s+beam\s+split\s+from\s+inside\s+by\s+abandoned\s+rank\s+seals", text, re.IGNORECASE):
        return "one massive adze-hewn timber gate beam, exactly two small blank-backed bronze rank seals, intact rubble-stone and rammed-earth wall, packed earth"
    if re.search(r"Goguryeo\s+command\s+seal\s+bound\s+inside\s+a\s+private\s+family\s+sash", text, re.IGNORECASE):
        return "one solid closed blank-backed square bronze command seal, one single straight dark woven family sash with two ends, rough timber"
    if re.search(r"blank-backed\s+Tang\s+rank\s+seal\s+pressed\s+into\s+granted\s+earth", text, re.IGNORECASE):
        return "exactly one blank-backed gilt-bronze Tang rank seal, rich dark earth, exactly one plain shallow land-grant tray"
    if re.search(r"Tang-ranked\s+Namsaeng\s+wearing\s+one\s+blank\s+rank\s+seal", text, re.IGNORECASE):
        return "one face-down blank-backed gilt-bronze square seal on one short red belt cord, one soft low black Tang futou, plain dark emblem-free lamellar, smooth buttonless round-collar robe, blank plaster wall"
    if re.search(r"blank-backed\s+Tang\s+rank\s+seal\s+block\s+pinning\s+one\s+torn\s+Goguryeo\s+sash", text, re.IGNORECASE):
        return "one palm-sized heavy square bronze seal block with smooth blank back, one torn grey woven rank sash, featureless freezing mud"
    if re.search(r"cracked\s+bronze\s+mirror\s+reflecting\s+one\s+collaborator\s+face", text, re.IGNORECASE):
        return "one handleless round polished-bronze mirror disk, one deep jagged crack, one coherent reflected male East Asian face, blank dark timber"
    if re.search(r"forgotten\s+exile\s+grave\s+outside\s+a\s+prosperous\s+Tang\s+traitor\s+household", text, re.IGNORECASE):
        return "one low sealed convex earth grave mound under unbroken cold snow, warm timber doorway, one low feast table, exactly three shallow footless bronze cups"
    if re.search(r"overturned\s+Goguryeo\s+ruler\s+seat\s+beside\s+broken\s+rank\s+objects", text, re.IGNORECASE):
        return "one overturned low timber ruler seat, exactly two face-down blank square bronze rank seals, exactly two severed red hemp cord ends, ash and burned timber"
    if re.search(r"deceased\s+Yeon\s+Namsaeng\s+on\s+blank\s+dark\s+silk", text, re.IGNORECASE):
        return "featureless dark silk, dark shroud at jawline, short tied black hair with grey temples"
    if re.search(r"completely\s+closed\s+blank\s+Tang\s+court\s+gate", text, re.IGNORECASE):
        return "two central plain adze-hewn timber gate leaves, one narrow closed seam, exactly two plain iron ring pulls"
    if re.search(r"fully\s+shrouded\s+Tang\s+funeral\s+coffin\s+under\s+one\s+plain\s+hemp\s+mourning\s+canopy", text, re.IGNORECASE):
        return "exactly one broad plain hemp mourning canopy, exactly one fully hemp-shrouded coffin, packed earth only at outer edge"
    if re.search(r"late-seventh-century\s+Mangshan\s+rammed-earth\s+burial\s+mound", text, re.IGNORECASE):
        return "one large rammed-earth burial mound, one long plain stone approach, low flush curb stones, dry grass, distant dark hills"
    if re.search(r"three\s+starving\s+and\s+wounded.*Goguryeo\s+defenders\s+and\s+civilians", text, re.IGNORECASE):
        return "worn buttonless Goguryeo wrap-front hemp robes, broad cloth sashes, wrapped shoes, one off-white forearm bandage, one empty woven basket, one overturned empty clay bowl, completely bare timber shelves, zero grain, packed earth"
    if re.search(r"object-only\s+betrayal\s+evidence", text, re.IGNORECASE):
        return "warm-brown hardwood tally on continuous rough dark timber planks"
    if re.search(r"Emperor\s+Gaozong\s+directing\s+the\s+Pyongyang\s+campaign", text, re.IGNORECASE):
        return "one soft low black Tang futou, smooth dark round-collar paofu, plain low timber table, solid three-dimensional unpainted rammed-earth relief with raised walls and recessed roads, blank plaster walls"
    if re.search(r"Namgeon\s+running\s+past\s+three\s+embedded\s+arrows", text, re.IGNORECASE):
        return "rust-brown Goguryeo lamellar with plain back, segmented iron cap, timber parapet, exactly three embedded straight arrow shafts with rear fletching"
    if re.search(r"Goguryeo\s+archer\s+in\s+the\s+instant\s+after\s+release", text, re.IGNORECASE):
        return "one recurved bow with empty string, fitted Goguryeo lamellar, segmented cap, timber parapet, open sky"
    if re.search(r"object-only\s+Sinseong\s+plot\s+evidence", text, re.IGNORECASE):
        return "one beige soft cloth pouch with gathered tied neck, one broad undyed hemp sash, one folded undyed monastic robe, medium-brown timber"
    if re.search(r"monk\s+Sinseong\s+concealing\s+a\s+plot", text, re.IGNORECASE):
        return "undyed robe, cloth sash, irregular rounded beige soft cloth bundle, shielded bronze oil dish, soot-black timber"
    if re.search(r"monk\s+Sinseong.*Tang\s+military\s+messenger", text, re.IGNORECASE):
        return "undyed buttonless wrap-front hemp robe and wrapped cloth shoes on shaved-head Sinseong; fitted dark Tang iron lamellar over a closed round-collar robe, low conical iron helmet and wrapped boots on the messenger; one small soft unmarked cloth packet; blank stone and timber"
    if re.search(r"monk\s+Sinseong.*Goguryeo\s+accomplice", text, re.IGNORECASE):
        return "shaved-head Sinseong in an undyed buttonless wrap-front hemp robe, angular-faced tied-haired male accomplice in a rust-brown buttonless wrap-front robe, one fully removed timber locking beam, two empty U-shaped iron wall brackets below it, vertical gate planks"
    if re.search(r"one\s+massive\s+Pyongyang\s+timber\s+gate\s+opening", text, re.IGNORECASE):
        return "one massive dark adze-hewn timber double gate with small iron studs, one narrow vertical opening, one removed timber locking beam, two empty iron brackets, smoke-dark packed earth, blank earthen walls"
    if re.search(r"one\s+adult\s+Goguryeo\s+defender\s+overwhelmed\s+by\s+the\s+breached\s+gate", text, re.IGNORECASE):
        return "rust-brown fitted Goguryeo iron lamellar, one close segmented iron cap, one cracked tall oval timber shield, buttonless wrap-front underrobe, packed-earth dust, charcoal smoke, orange torchlight, blank charred wall"
    if re.search(r"one\s+Goguryeo\s+defender.*two\s+Tang\s+assault\s+infantry", text, re.IGNORECASE):
        return "rust-brown fitted Goguryeo iron lamellar, one tall oval center shield, dark Tang iron lamellar, one smaller round left shield, one straight right spear, two close skull-fitting segmented iron caps with narrow flush brow bands, blank charred wall"
    if re.search(r"Goguryeo\s+commander\s+Namgeon\s+realizing\s+defeat", text, re.IGNORECASE):
        return "continuous rows of identical small rust-brown Goguryeo iron lames across the entire chest, buttonless wrap-front robe, tied black hair, broad cloth sash, wrapped boots, bare packed earth, zero weapons"
    if re.search(r"Goguryeo\s+commander\s+Namgeon\s+watching\s+the\s+breached\s+gate", text, re.IGNORECASE):
        return "rust-brown fitted Goguryeo iron-lamellar collar over a buttonless wrap-front robe, tied black hair, two fully visible dark brown eyes, two glossy wet dark-red tear trails beginning at the two lower eyelids, uncut forehead, opaque smoke"
    if re.search(r"Goguryeo\s+commander\s+Namgeon\s+choosing\s+death", text, re.IGNORECASE):
        return "rust-brown fitted Goguryeo iron lamellar over a buttonless wrap-front robe, tied black hair, exactly one short straight single-edged guardless iron dagger with one wood handle and one blade, packed earth, blank smoke-dark earthen wall"
    if re.search(r"Tang\s+assault\s+infantry.*(?:Pyongyang\s+gate|windowless\s+night\s+gate\s+passage)", text, re.IGNORECASE):
        return "two fitted Tang iron-lamellar coats, blank vertical gate planks, narrow firelit gap, exactly one oval timber shield, exactly one straight spear, dark round-collar robes, smooth boots, packed earth"
    if re.search(r"two\s+standing\s+Tang\s+infantry.*one\s+prone\s+Goguryeo\s+defender", text, re.IGNORECASE):
        return "blank charred timber wall, packed earth, smoke, two Tang iron lamellar coats over dark round-collar robes, one Goguryeo wrap-front robe, one oval timber shield, one straight spear"
    if re.search(r"three\s+injured.*Goguryeo\s+civilians.*(?:burned\s+shelter|burning\s+exterior\s+alley)", text, re.IGNORECASE):
        return "blank collapsed timber wall, orange fire, charcoal smoke, ash, three torn soot-dark undyed wrap-front hemp robes, cloth sashes, loose trousers, wrapped shoes, restrained dark-red stains"
    if re.search(r"shattered\s+uninscribed\s+Goguryeo\s+bronze\s+ritual\s+bell", text, re.IGNORECASE):
        return "upright blank flared bronze bell, domed crown, one loop, open mouth, one broken skirt section, three charred beams behind, packed earth, fire, smoke"
    if re.search(r"charred\s+blank\s+Goguryeo\s+war\s+banner", text, re.IGNORECASE):
        return "one unmarked ochre woven-hemp banner, one snapped plain timber pole, one charred outer cloth edge, dark-red rain mud"
    if re.search(r"cracked\s+Goguryeo\s+granary\s+jar.*spoiled\s+millet", text, re.IGNORECASE):
        return "one upright narrow-necked bulbous hand-built clay jar, continuous fine pale-yellow granular millet texture like coarse sand with individual kernels too tiny to resolve, fuzzy grey-green mold on fine grain clumps, smoke-dark packed earth, charred timber"
    if re.search(r"exhausted.*Goguryeo\s+defender.*severed\s+inner-gate\s+rope", text, re.IGNORECASE):
        return "one fitted Goguryeo iron-lamellar coat over a buttonless wrap-front robe, broad cloth sash, wrapped boots, one split oval timber shield, one severed plain gate rope, smoke-dark packed earth, hostile torchlight"
    if re.search(r"discarded\s+cracked\s+Goguryeo\s+fortress\s+tally.*two\s+intact\s+elite\s+rank\s+fittings", text, re.IGNORECASE):
        return "one palm-sized cracked blank hardwood fortress tally, exactly two matching flat solid rectangular plain bronze belt plaques with raised rims and closed faces without holes, one dark low mortised-timber command table edge, smoke-dark ash, hard side light"
    if re.search(r"empty\s+Goguryeo\s+ruler\s+seat.*fallen\s+command\s+beam", text, re.IGNORECASE):
        return "one empty dark mortised-timber ruler seat, one fallen mortised roof beam, packed earth, black smoke, charred wood splinters"
    if re.search(r"three\s+empty\s+segmented\s+Goguryeo\s+iron\s+cap\s+helmets.*mud", text, re.IGNORECASE):
        return "exactly three empty low iron helmets made from visible radial plates and riveted brow bands, two short corded lamellar neck guards, broken layered-timber shields with rawhide rims, snapped straight spear shafts, cold mud, collapsed rubble"
    if re.search(r"three\s+shallow\s+cracked\s+household\s+grain\s+bowls.*overturned\s+command\s+stool", text, re.IGNORECASE):
        return "smoke-dark packed earth filling every edge, exactly three shallow empty cracked clay grain bowls with broken rims and circular foot rings, one overturned heavy mortised-timber command stool with one thick crossbar touching all three rims, small spilled millet"
    if re.search(r"scorched\s+empty\s+hemp\s+identity\s+pouch", text, re.IGNORECASE):
        return "one small soft wrinkled plain-hemp fabric drawstring pouch with puckered mouth mostly collapsed into grey ash, one limp blackened cloth edge, one short thin cut drawcord, loose burned fibers, orange embers, charcoal"
    if re.search(r"one\s+adult\s+Tang\s+officer\s+crushing.*face-down\s+blank-backed\s+Goguryeo\s+record-slip\s+bundle", text, re.IGNORECASE):
        return "one face-down cord-tied hardwood record-slip bundle showing plain reverse wood grain only, battlefield mud, fitted Tang iron lamellar cuirass, dark round-collar robe, plain cloth sash, loose trousers, wrapped boots, conical iron helmet"
    if re.search(r"three\s+separated\s+face-down\s+blank\s+hardwood\s+heroic\s+record\s+slips", text, re.IGNORECASE):
        return "exactly three separated parallel plain-backed hardwood slips, wide gaps, zero cord or rope, one clearly blackened missing wood corner, fine pale-grey ash, tiny orange embers"
    if re.search(r"short\s+straight\s+iron\s+utility\s+knife\s+between\s+two\s+separated\s+halves.*red\s+hemp\s+cord", text, re.IGNORECASE):
        return "one complete short straight single-edged iron utility knife with plain wood grip, exactly two separate red hemp cord halves with frayed ends facing across one clear gap, uninterrupted rough timber"
    if re.search(r"two\s+adult\s+male\s+Goguryeo\s+brothers.*Namgeon.*Namsan", text, re.IGNORECASE):
        return "dark and rust Goguryeo iron lamellar over buttonless wrap-front underrobes, broad knotted cloth sashes, wrapped boots, four empty hands, low rammed-earth rampart with irregular fieldstone revetment, plain Tang tents"
    if re.search(r"three\s+fearful\s+Goguryeo\s+soldiers.*six\s+empty\s+hands", text, re.IGNORECASE):
        return "three distinct fitted Goguryeo iron-lamellar coats over buttonless wrap-front underrobes, broad cloth sashes, wrapped boots, six open empty hands, plain unmarked timber wallboards"
    if re.search(r"two\s+adults.*starving\s+civilian.*kneeling\s+lamellar\s+soldier", text, re.IGNORECASE):
        return "wrap-front robe, fitted Goguryeo lamellar, cloth sashes, wrapped shoes, mud"
    if re.search(r"Goguryeo\s+timber\s+hall\s+support\s+column\s+splitting", text, re.IGNORECASE):
        return "exactly one thick unpainted mortised timber column, one sagging timber crossbeam, long fresh wood splinters, rough stone footing, bare rammed-earth wall, dark timber floor"
    if re.search(r"blank\s+unmarked\s+fibrous\s+sheet\s+burning\s+into\s+ash", text, re.IGNORECASE):
        return "exactly one thin blank fibrous sheet, pale unmarked left half, black curled right half, small orange flames attached directly to one jagged charred sheet edge, seamless cool grey stone"
    if re.search(r"two\s+grey\s+wolves.*dark\s+earthen\s+pit", text, re.IGNORECASE):
        return "exactly two natural grey wolves, one head four legs two ears and one tail per wolf, natural paws and spines, bare mud, steep raw earthen pit walls"
    if re.search(r"full-scale\s+Pyongyang\s+Goguryeo\s+fortress\s+encircled\s+by\s+Tang\s+tents", text, re.IGNORECASE):
        return "large roofless ochre rammed-earth outer rampart with irregular fieldstone revetment and sparse timber stakes, many low plain tan Tang hide tents, small low campfires in bare gaps between tents, smoke, open dark ground"
    if re.search(r"unglazed\s+Goguryeo\s+grain\s+jar\s+ruptured\s+open\s+by\s+black-green\s+rot", text, re.IGNORECASE):
        return "exactly one large plain unglazed earthen storage jar, intact rim and sides, one jagged front rupture, clumped spoiled millet, thick black-green mold, wet rot, continuous packed earth"
    if re.search(r"dark\s+snake\s+clamping\s+its\s+own\s+continuous\s+mid-body\s+between\s+closed\s+jaws", text, re.IGNORECASE):
        return "one continuous dark snake, one head, two eyes, closed jaws, one tail, cold stone"
    if re.search(r"three\s+separate\s+Goguryeo\s+oval\s+timber\s+shields.*iron\s+boss", text, re.IGNORECASE):
        return "exactly three convex oval layered-timber shields, three rawhide rims, exactly one small plain iron boss per shield, packed earth"
    if re.search(r"two\s+blank\s+bronze\s+seals\s+divided\s+by\s+one\s+deep\s+floor\s+crack", text, re.IGNORECASE):
        return "exactly two palm-sized blank-backed bronze seals, one continuous packed-clay surface"
    if re.search(r"tall\s+oval\s+shield.*back\s+side\s+up.*one\s+broken\s+leather\s+grip", text, re.IGNORECASE):
        return "one tall oval layered-timber shield, intact rawhide rim, one broad dark-brown leather grip, blackened rotten center wood, packed earth"
    if re.search(r"cracked\s+bronze\s+stamp.*low\s+bridge\s+knob.*dark-red\s+stain", text, re.IGNORECASE):
        return "one thick square cast-bronze stamp, one short low bridge-shaped knob fixed to back center, one matte dark-red stain, rough charcoal stone"
    if re.search(r"flat\s+foundation\s+stone.*permanent\s+red\s+scar", text, re.IGNORECASE):
        return "one broad rough natural granite slab, pale rainwater, packed earth"
    if re.search(r"empty\s+dented\s+segmented\s+iron\s+helmet\s+in\s+one\s+fresh\s+cart-wheel\s+track", text, re.IGNORECASE):
        return "shallow half-dome crown, narrow iron segments, wide open bottom, plain empty interior, deep churned mud"
    if re.search(r"(?:exactly\s+)?one\s+cropped\s+Tang-era\s+cloth-wrapped\s+forefoot\s+pressing\s+(?:exactly\s+)?one\s+dented\s+Goguryeo\s+iron\s+cap(?:\s+into\s+mud)?", text, re.IGNORECASE):
        return "matte charcoal woven wraps, crossed cloth bands, soft rounded toe, flat cloth underside, narrow iron segments, deep mud"
    if re.search(r"two\s+weaponless\s+fighters.*rust\s+Goguryeo.*black\s+Tang", text, re.IGNORECASE):
        return "rust Goguryeo lamellar and dark Tang lamellar over distinct period robes, broad cloth sashes, wrapped cloth boots, four closed empty fists, plain ochre rammed-earth wall"
    if re.search(r"torn\s+golden\s+silk\s+veil.*shallow\s+segmented\s+Goguryeo\s+iron\s+cap", text, re.IGNORECASE):
        return "one torn golden woven veil, one shallow half-dome segmented iron cap with wide open bottom and plain interior, rough dark timber"
    if re.search(r"blood-smeared\s+five-finger\s+handprint", text, re.IGNORECASE):
        return "exactly one flat palm silhouette and exactly five flat finger smears, matte dried-blood stain flush with full-bleed packed-clay landform terrain, raised mountain ridges, one winding recessed river channel"
    if re.search(r"broken\s+Goguryeo\s+(?:guardless\s+)?ring-pommel\s+sword", text, re.IGNORECASE):
        return "exactly two horizontal iron sword fragments: left small open ring pommel no wider than grip length, narrow wrapped grip and guardless straight blade stump; right compact triangular pointed blade-tip shard; freezing wet mud"
    if re.search(r"layered-timber\s+shield\s+split\s+into\s+exactly\s+two", text, re.IGNORECASE):
        return "one plain convex oval shield of vertical layered timber planks, rawhide rim, exactly two slightly overlapping jagged halves, one small plain iron boss on left half, freezing wet mud"
    if re.search(r"abandoned\s+rain-soaked\s+Goguryeo\s+command\s+robe", text, re.IGNORECASE):
        return "exactly one dark buttonless wrap-front command robe, one attached plain grey cloth waist tie, woven hemp, wet mud, wrapped-shoe tracks"
    if re.search(r"traitor\s+guard.*locking\s+(?:bar|beam)|locking\s+(?:bar|beam).*traitor\s+guard", text, re.IGNORECASE):
        return "rust buttonless pocketless wrap guard robe with uninterrupted back, broad knotted cloth sash, heavy vertical-plank gate, one timber locking beam, two rough iron brackets, rammed earth"
    if re.search(r"unlatched\s+heavy\s+iron\s+gate\s+chain\s+laid\s+as\s+one\s+open\s+straight\s+segment", text, re.IGNORECASE):
        return "exactly one short forged-iron chain segment, one shallow diagonal line, two free end links far apart, continuous smooth clay"
    if re.search(r"heavy\s+iron\s+gate\s+chain\s+fully\s+detached\s+from\s+one\s+open\s+wall\s+hook", text, re.IGNORECASE):
        return "one continuous vertical timber gate surface, one heavy iron chain with final open link, one separate empty open iron wall hook on same plane, broad air gap, far-right torchlit seam"
    if re.search(r"iron\s+gate\s+chain.*one\s+sleeve-covered\s+right\s+hand|one\s+sleeve-covered\s+right\s+hand.*iron\s+gate\s+chain", text, re.IGNORECASE):
        return "one heavy iron chain, one open wall hook, exactly one complete right hand, one plain rust-brown buttonless wrap sleeve, vertical timber gate planks"
    if re.search(r"iron\s+gate\s+chain.*sleeve-covered\s+hands|sleeve-covered\s+hands.*iron\s+gate\s+chain", text, re.IGNORECASE):
        return "one heavy iron chain and one open iron wall hook, exactly two complete hands, two plain rust-brown buttonless woven wrap sleeves, vertical timber gate planks"
    if re.search(r"traitor\s+guard.*gate\s+chain|gate\s+chain.*traitor\s+guard", text, re.IGNORECASE):
        return "rust buttonless pocketless crossover guard jacket with uninterrupted front panels, broad knotted cloth sash, plain cloth headband, one iron gate chain, one open wall hook, vertical plank gate"
    if re.search(r"(?:sabotaged|opened).*Goguryeo.*plank\s+gate|Goguryeo\s+plank\s+gate.*opened", text, re.IGNORECASE):
        return "heavy adze-hewn plank gate, exactly one timber locking bar, two empty iron brackets, packed earth, enemy torchlight, straight iron spear tips"
    if re.search(r"Heonseong", text, re.IGNORECASE):
        if re.search(r"fully\s+prostrate|offered\s+as\s+a\s+hostage", text, re.IGNORECASE):
            return "one crown of black hair, narrow upper forehead at floor, exactly two open hands, two plain wide grey buttonless wrap-sleeve cuffs, continuous dark timber floorboards"
        return "one slender teenage male in a long-sleeved buttonless wrap jacket, loose trousers and closed wrapped shoes; one small soft square tan cloth parcel, bare dirt road, low rammed-earth banks"
    if re.search(r"kneeling\s+Namsaeng.*Tang\s+(?:frontier\s+)?envoy", text, re.IGNORECASE):
        return "Tang envoy in low black futou, smooth-front dark round-neck paofu and smooth-soled boots; Namsaeng in grey buttonless wrap-front robe, broad cloth sash and wrapped shoes; four empty hands"
    if re.search(r"Tang-armored\s+Namsaeng\s+pointing", text, re.IGNORECASE):
        if re.search(r"weaponless|empty\s+right\s+hand|straight\s+index\s+finger", text, re.IGNORECASE):
            return "fitted Tang iron lamellar over a dark closed round-neck robe, broad cloth sash, smooth-soled boots, two empty hands, one straight pointing index finger, low earthen ramparts and timber palisades"
        return "fitted Tang iron lamellar over a dark closed round-neck robe, broad cloth sash, smooth-soled boots, exactly one compact short straight ring-pommel sword, low earthen ramparts and timber palisades"
    if re.search(r"plants?\s+exactly\s+one\s+short\s+straight\s+ring-pommel\s+sword", text, re.IGNORECASE):
        return "grey buttonless wrap-front robe, broad cloth sash and wrapped shoes on Namsaeng; low black futou, dark closed round-collar robe and smooth-soled boots on Tang commander; exactly one short straight ring-pommel sword"
    if re.search(r"fully\s+prostrate\s+Namsaeng", text, re.IGNORECASE):
        return "grey buttonless wrap-front robe, broad cloth sash and wrapped shoes on Namsaeng; low black futou, dark closed round-collar robe and smooth-soled boots on Tang envoy; one palm-sized blank-backed hardwood fortress tally"
    if re.search(r"six\s+face-down\s+bronze-capped\s+hardwood\s+fortress\s+tallies", text, re.IGNORECASE):
        return "exactly six blank-backed hardwood tally blocks with small bronze corner caps, one grey woven sash, one black woven sash, continuous rough timber grain"
    if re.search(r"two\s+exhausted\s+Goguryeo\s+civilians.*two\s+Tang\s+guards", text, re.IGNORECASE):
        return "worn buttonless wrap-front hemp robes, tied cloth bundles and wrapped shoes on civilians; dark Tang lamellar armor over closed round-collar robes and smooth-soled boots on guards; muddy plank gate"
    if re.search(r"gaunt\s+Goguryeo\s+civilian.*two\s+armored\s+officials", text, re.IGNORECASE):
        return "buttonless wrap-front hemp robe on civilian; fitted iron lamellar over period robes on officials; exactly two palm-sized smooth pebbles, one low dark timber table, one blank rammed-earth wall"
    if re.search(r"Gaozong", text, re.IGNORECASE) and re.search(r"rank\s+seal", text, re.IGNORECASE):
        return "low black Tang futou and dark closed round-neck robe on Gaozong, fitted Tang lamellar armor on Namsaeng, one small blank gilt-bronze rank seal, low timber dais"
    if re.search(r"exactly\s+one\s+adult\s+male\s+Emperor\s+Gaozong", text, re.IGNORECASE):
        return "soft low black Tang futou headwrap, short moustache and beard, dark round-neck paofu with one hidden neck closure and uninterrupted plain chest cloth"
    if re.search(r"Tang-armored.*rider\s+Namsaeng|Namsaeng.*one\s+horse|paired\s+leather\s+reins", text, re.IGNORECASE):
        if re.search(r"burn(?:ed|ing)\s+Goguryeo\s+village|burning\s+village\s+road|grain\s+basket|broken\s+clay\s+pots", text, re.IGNORECASE):
            return "fitted Tang iron lamellar armor over a dark closed round-neck robe, one complete horse, one simple leather saddle and bridle, paired leather reins, muddy village road, broken clay pots, one overturned woven grain basket, burned timber-and-thatch homes"
        return "fitted Tang iron lamellar armor over a dark closed round-neck robe, one complete horse, one simple leather saddle and bridle, paired leather reins, muddy road"
    if re.search(r"Namsaeng", text, re.IGNORECASE) and re.search(
        r"Tang\s+attendant|pulls?\s+one\s+plain\s+grey\s+Goguryeo\s+rank\s+sash",
        text,
        re.IGNORECASE,
    ):
        return "fitted Tang iron lamellar armor over a dark closed round-neck robe on Namsaeng, one plain grey Goguryeo rank sash, one shoulder fastening, uninterrupted blank wallboards"
    if re.search(r"Tang-armored\s+Namsaeng", text, re.IGNORECASE):
        return "fitted Tang iron lamellar armor over a dark closed round-collar robe, broad cloth sash, smooth-soled boots"
    if re.search(r"discarded\s+Goguryeo\s+command\s+cloak.*cut\s+grey\s+rank\s+sash", text, re.IGNORECASE):
        return "one dark woven command cloak, exactly two halves of one cut grey woven rank sash, one small face-down unmarked bronze clasp, continuous dark floorboards"
    if re.search(r"Silla(?:\s+frontier)?\s+guard", text, re.IGNORECASE):
        return "one large plain ochre triangular hemp standard, hide tents and timber palisade; dark iron Silla lamellar, low shallow black segmented iron cap helmet and narrow plain gilt brow band on guard; grey buttonless wrap-front robe on Jeongto; one small soft tan cloth bundle"
    if re.search(r"full-scale[^.;]{0,60}Goguryeo\s+rammed-earth\s+(?:fortress|defensive\s+embankment)", text, re.IGNORECASE):
        return "cascading loose granular sand at collapsing right half; one broad smooth unmarked ochre rammed-earth slope at left, sparse straight undecorated timber palisade stakes, dark storm sky"
    if re.search(r"granite\s+fortress\s+wall.*center\s+melting", text, re.IGNORECASE):
        return "irregular rough granite fieldstones, lime-free earthen joints, viscous green-black poison, one broad low horizontal cavity at least twice as wide as tall, sagging liquid-rock edges and heavy mineral drips"
    if re.search(r"poisoned\s+Goguryeo\s+gilt-bronze\s+royal\s+diadem", text, re.IGNORECASE):
        return "one low gilt-bronze headband diadem laid flat on packed earth, one broad plain open band, exactly three modest rounded flame tabs, viscous black poison seeping into dirt"
    if re.search(r"blank\s+square\s+bronze\s+succession\s+plaque\s+half-submerged\s+in\s+black\s+poison", text, re.IGNORECASE):
        return "exactly one thin flat blank square bronze succession plaque, one viscous black poison pool covering its lower half, one continuous smooth unbroken ochre clay surface"
    if re.search(r"cracked\s+plain\s+square\s+bronze\s+succession\s+plaque", text, re.IGNORECASE):
        return "exactly one thin flat square bronze succession plaque with completely blank surface, one deep diagonal center crack, viscous black poison, continuous packed earth"
    if re.search(r"cracked\s+(?:face-down|handle-down)\s+plain\s+square\s+bronze\s+succession\s+seal", text, re.IGNORECASE):
        return "one low handle-down square bronze seal with blank flat stamping face upward and hidden handle underneath, one deep diagonal center crack, viscous black poison, packed earth"
    if re.search(r"secret\s+red\s+route\s+cord\s+joining\s+one\s+grey\s+Goguryeo\s+sash", text, re.IGNORECASE):
        return "one narrow soft wrinkled horizontal grey woven sash strip, one narrow soft wrinkled horizontal black woven sash strip, exactly one thin red route cord, exactly three separate same-size smooth grey oval stones, continuous dark brown floorboards"
    if re.search(r"blank-backed\s+hardwood\s+fortress\s+tally\s+sliding\s+under", text, re.IGNORECASE):
        return "one short red route cord, exactly one palm-sized blank hardwood fortress tally, one flat black woven Tang rank sash, one small torn grey Goguryeo sash fragment, dark floorboards"
    if re.search(r"realistic(?:\s+adult)?\s+brown\s+rat", text, re.IGNORECASE):
        return "one natural brown rat with four paws, one head, two rounded ears and one long unbroken tail, wet packed mud, one flat boot-shaped shadow"
    if re.search(r"three\s+starving\s+Goguryeo\s+civilians", text, re.IGNORECASE):
        return "worn buttonless wrap-front hemp robes, broad cloth sashes, loose trousers, calf wraps, soft cloth shoes, separate empty woven grain baskets, muddy drainage lane"
    if re.search(r"villagers\s+with\s+visible\s+tear\s+tracks", text, re.IGNORECASE):
        return "clean undyed buttonless wrap-front hemp robes, broad cloth sashes, loose trousers, closed wrapped shoes, reddened eyes, clear wet cheek tears, burned timber-and-thatch homes, empty smoky sky"
    if re.search(r"two\s+kneeling\s+Goguryeo\s+officials.*standing\s+Tang\s+soldier", text, re.IGNORECASE):
        return "grey buttonless wrap-front robes and wrapped shoes on kneeling officials; dark Tang iron lamellar and low black helmet on standing soldier; all hands empty"
    if re.search(r"guards\s+exchanging\s+one\s+fortress\s+key", text, re.IGNORECASE):
        return "rust and grey buttonless wrap-front guard jackets, broad cloth sashes, loose trousers, wrapped shoes, exactly one palm-sized blank bronze-bound hardwood key block"
    if re.search(r"cracked\s+oval\s+Goguryeo\s+timber\s+shield.*one\s+detached\s+spearhead", text, re.IGNORECASE):
        return "exactly one convex oval layered-plank timber shield with rawhide rim, exactly one detached triangular iron spearhead blade, packed earth"
    if re.search(r"upright\s+uninscribed\s+flared\s+bronze\s+alarm\s+bell", text, re.IGNORECASE):
        return "one smooth blank flared bronze bell, domed crown, top loop, broad skirt, thick rim, one frayed rope stub, packed earth"
    if re.search(r"cracked\s+stone\s+(?:official|kneeling)\s+statue", text, re.IGNORECASE):
        return "one weathered grey stone kneeling-official statue in plain wrap-front robes, one chest-to-base fissure, one flat black distorted shadow on packed earth"
    if re.search(r"Goguryeo\s+ceremonial\s+throne\s+sinking", text, re.IGNORECASE):
        return "one upright dark timber ceremonial throne, tall plain back, two armrests, restrained gilt-bronze edge fittings, one deep dark red pool, rough stone floor"
    if re.search(r"overturned\s+low\s+timber\s+command\s+seat", text, re.IGNORECASE):
        return "one low backless dark timber command seat, exactly one cracked face-down blank bronze rank tablet, packed-earth floor, shallow dark red rainwater"
    if re.search(r"segmented\s+iron\s+helmets", text, re.IGNORECASE):
        return "exactly three empty low segmented iron cap helmets with narrow brow bands and open undersides, exactly two snapped straight ash-wood spear shafts, snow and cart tracks"
    if re.search(r"two\s+adult\s+Goguryeo\s+civilian\s+bearers.*fully\s+shrouded\s+casualty", text, re.IGNORECASE):
        return "torn buttonless wrap-front hemp robes, broad cloth sashes, loose trousers, calf wraps, wrapped shoes, one rectangular timber stretcher, one plain fully closed hemp shroud, smoke and packed earth"
    if re.search(r"low\s+segmented\s+iron\s+cap\s+helmet.*flattened\s+gilt-bronze\s+cover", text, re.IGNORECASE):
        return "exactly one low segmented iron cap helmet with narrow brow band, exactly one thin flattened gilt-bronze sheet cover, continuous packed earth"
    if re.search(r"Gaozong", text, re.IGNORECASE):
        return "soft low black Tang futou, short moustache and beard, dark round-neck paofu with one hidden neck closure and uninterrupted plain chest cloth on Gaozong; close-fitting dark cloth cap and grey wrap-front robe on Namsaeng"
    if re.search(r"three\s+adult\s+Goguryeo\s+brothers", text, re.IGNORECASE):
        return "charcoal, rust and muted-blue wrap-front Goguryeo jackets, broad cloth sashes, wrapped shoes, six empty hands, packed earth"
    if re.search(r"defense-route\s+handover\s+layout|six\s+smooth\s+grey\s+river-stone", text, re.IGNORECASE):
        return "exactly six smooth grey stones, one straight red hemp cord, one flat grey sash, one flat black sash, installed rough timber floor planks"
    if re.search(r"severed\s+grey\s+woven\s+Goguryeo\s+clan\s+sash", text, re.IGNORECASE):
        return "continuous dark brown floorboard grain filling every edge; one single-layer grey woven clan sash severed once into exactly two halves, facing frayed edges, one narrow gap"
    if re.search(r"thirty-four-year-old\s+Yeon\s+Namsaeng", text, re.IGNORECASE) and re.search(
        r"Goguryeo\s+fortress\s+tally", text, re.IGNORECASE
    ):
        return "dark iron lamellar torso, low conical Tang helmet, thin flat horizontal warm-brown wood-grain tally on low table, solid pale plaster wall"
    if re.search(r"Namsaeng", text, re.IGNORECASE) and re.search(
        r"kneels\s+alone|exactly\s+one\s+adult\s+male",
        text,
        re.IGNORECASE,
    ):
        return "black-haired early-thirties man, dark cloth headband, grey wrap-front Goguryeo robe, broad cloth sash, exactly two halves of one snapped red hemp clan cord, unbroken dark wallboards"
    if re.search(r"Tang\s+military\s+registrar", text, re.IGNORECASE) and re.search(r"fortress\s+tally", text, re.IGNORECASE):
        return "one palm-sized flat solid rectangular blank hardwood fortress tally lying horizontally on a low table; fitted dark Tang iron lamellar over wrist-length black sleeves on male Namsaeng; unarmored registrar in black futou and smooth dark paofu; plain wallboards"
    if re.search(r"Namsaeng", text, re.IGNORECASE) and re.search(r"registrar|registry", text, re.IGNORECASE):
        return "low black futou and smooth dark round-collar robe on Tang registrar, black-haired early-thirties Namsaeng in grey wrap-front robe, palm-sized bronze seal, plain wallboards"
    if re.search(r"Namsaeng", text, re.IGNORECASE) and re.search(
        r"fortress\s+tally|route\s+cord|Tang\s+commander",
        text,
        re.IGNORECASE,
    ):
        return "low black futou and smooth dark round-collar robe on Tang commander, grey wrap-front robe on Namsaeng, palm-sized bronze-bound hardwood tally, red hemp cord, plain wallboards"
    if re.search(r"sabotaged\s+Goguryeo\s+timber\s+gate\s+brace", text, re.IGNORECASE):
        return "one adze-hewn horizontal locking beam, one deep triangular V-shaped axe notch, pale flat chopped facets, repeated axe scars, heavy plank gate, small fieldstones in rammed earth"
    if re.search(r"exactly\s+two\s+plain\s+square\s+bronze\s+seal\s+blocks", text, re.IGNORECASE):
        return "two low flat square bronze stamp seals, base height one-fifth width, one short vertical top knob each, dull-dark left bare, green-brown right tied with one red cord, rough timber"
    if re.search(r"dagger.*(?:command|guard)\s+sash|dagger\s+half[- ](?:covered|concealed)", text, re.IGNORECASE):
        return "one plain unmarked short straight iron dagger with wood grip, one folded woven command sash, continuous rough timber floorboards, diffuse grey daylight"
    if re.search(r"low\s+backless\s+Tang\s+command\s+stool", text, re.IGNORECASE):
        return "low undecorated four-legged timber stool, broken curved timber shield, woven rank sash, plain hemp shroud, packed earth"
    if re.search(r"abandoned\s+casualty\s+gear", text, re.IGNORECASE):
        return "wrap-front hemp robe, broad cloth sash, loose trousers, calf wraps, wrapped cloth shoes, broken curved timber shield, snapped straight spear shaft, plain hemp shroud"
    if re.search(r"granary\s+jar|spoiled\s+millet", text, re.IGNORECASE):
        return "one plain hand-built Goguryeo clay jar, millet, packed earth, firelight"
    if re.search(r"burial\s+mound|stone\s+marker", text, re.IGNORECASE):
        return (
            "low rammed-earth Tang burial mound, rough unmarked stone marker with natural grain, "
            "woven rank sash, small face-down bronze clasp, dry grass"
        )
    if re.search(r"bronze\s+mirror", text, re.IGNORECASE):
        return "round polished bronze mirror disk, wrap-front hemp robe, plain timber wall, low bronze oil dish"
    if re.search(
        r"exactly\s+two\s+(?:(?:hardened\s+)?adult\s+Tang-clad\s+descendants|hardened\s+Tang\s+adult\s+men)",
        text,
        re.IGNORECASE,
    ):
        cup_inventory = (
            "exactly one shallow footless bronze cup"
            if re.search(r"exactly\s+one\s+shallow\s+footless\s+bronze\s+cup", text, re.IGNORECASE)
            else "exactly two shallow footless bronze cups"
        )
        return (
            "low black Tang futou caps, dark round-neck paofu with uninterrupted chest cloth, "
            f"{cup_inventory}, low lacquer table, three limp folded dyed silk bundles with frayed woven edges, dark timber wallboards"
        )
    if re.search(r"bronze\s+(?:cup|drinking\s+(?:bowl|cup))|shallow\s+bronze|Tang\s+residence", text, re.IGNORECASE):
        return (
            "low black Tang futou caps covering tied hair, dark silk robes with smooth closed circular necklines and "
            "uninterrupted chest cloth, shallow footless bronze cups named by the scene, lacquer table"
        )
    if re.search(r"fully\s+covered\s+stretcher|timber\s+stretcher", text, re.IGNORECASE):
        return "simple timber stretcher with two side poles and cross slats, one plain hemp shroud, wrapped cloth shoes"
    if re.search(r"collapsed\s+granary\s+beam|crushed\s+timber\s+home", text, re.IGNORECASE):
        return "rough timber beam, collapsed rafters, broken clay roof tiles, wrap-front hemp robes, wrapped cloth shoes"
    if re.search(
        r"abandoned\s+(?:equipment|defense\s+gear)|broken\s+helmets|battlefield\s+(?:ground|slope)",
        text,
        re.IGNORECASE,
    ):
        return "dented Goguryeo iron helmets, broken timber shields, straight spear shafts, torn hemp, packed earth"

    materials: list[str] = []

    def add(value: str) -> None:
        if value and value not in materials:
            materials.append(value)

    has_human = bool(
        re.search(
            r"\b(?:adult|man|men|woman|women|noble|official|commander|emperor|envoy|registrar|"
            r"guard|soldier|defender|civilian|villager|refugee|prisoner|rider|monk|survivor)\b",
            text,
            re.IGNORECASE,
        )
    )
    object_only = bool(re.search(r"\bobject[- ]only\b", text, re.IGNORECASE))
    if has_human:
        if re.search(r"\bmonk\b", text, re.IGNORECASE):
            add("shaved head, wrapped cloth shoes, undyed wrap-front hemp monastic robe, broad cloth sash, loose trousers")
        elif re.search(r"civilian|villager|refugee|prisoner|survivor", text, re.IGNORECASE):
            add("wrap-front Goguryeo hemp robes, soft cloth shoes, cloth sashes, loose trousers, calf wraps")
        elif re.search(r"\bTang\b", text, re.IGNORECASE) and re.search(r"\bGoguryeo\b", text, re.IGNORECASE):
            add("Tang role in black futou, dark round-collar robe and smooth-soled boots; Goguryeo role in wrap-front robe, cloth sash and wrapped shoes")
        elif re.search(r"\b(?:Tang|Gaozong|futou|round-collar)\b", text, re.IGNORECASE):
            add("black Tang futou, smooth-soled boots, dark round-collar robes fastened at neck, broad cloth sashes")
        else:
            add("wrap-front Goguryeo robes, smooth-soled boots, broad cloth sashes, loose trousers, calf wraps")

    if re.search(r"lamellar|soldier|guard|defender|commander|battle|combat", text, re.IGNORECASE):
        add("fitted iron lamellar armor over period robes")
    if re.search(r"\b(?:horse|rides?|mounted|cavalry)\b", text, re.IGNORECASE):
        add("one simple leather saddle and bridle per horse, paired reins")
    if not object_only and re.search(
        r"gate|fortress|battlement|stockade|rampart|stone-and-earth\s+wall|Pyongyang\s+walls",
        text,
        re.IGNORECASE,
    ):
        add("sloped rubble-stone and rammed-earth rampart, low timber parapet, tiled timber gatehouse, plank gate with small iron studs")
    elif not object_only and re.search(r"hall|room|interior|residence|registry", text, re.IGNORECASE):
        add("plain post-and-beam timber interior with uninterrupted wall-board grain")

    if re.search(r"tall(?:y|ies)|tablet|marker", text, re.IGNORECASE):
        add("plain face-down hardwood tally blocks with uninterrupted grain")
    if re.search(r"\bseals?\b", text, re.IGNORECASE):
        add("small square bronze seals with stamp faces turned down")
    if re.search(r"cord|rope", text, re.IGNORECASE):
        add("thick braided hemp cord")
    if re.search(r"rank\s+belt|belt|clasp", text, re.IGNORECASE):
        add("woven rank sash with a face-down bronze clasp")
    if re.search(r"packet|bundle", text, re.IGNORECASE):
        add("closed cord-tied hemp cloth packet with uninterrupted weave")
    if re.search(r"sandals?", text, re.IGNORECASE):
        add("flat woven hemp sandals with cord edge binding")
    if re.search(r"brazier", text, re.IGNORECASE):
        add("low undecorated bronze charcoal brazier")
    if re.search(r"bell", text, re.IGNORECASE):
        add("plain cast-bronze alarm bell")
    if re.search(r"standard|banner|flag", text, re.IGNORECASE):
        add("plain hemp standard with uninterrupted cloth weave")
    if re.search(r"dagger|utility\s+blade", text, re.IGNORECASE):
        add("one short straight iron dagger with a plain wood grip")
    elif re.search(r"sword|blade", text, re.IGNORECASE):
        add("short straight ring-pommel iron swords in plain scabbards")
    if re.search(r"spear", text, re.IGNORECASE):
        add("straight iron spearheads on ash-wood shafts")
    if re.search(r"recurved\s+bow|archer|arrow|bow\s+case", text, re.IGNORECASE):
        add("one recurved composite bow and one closed bow case")
    if re.search(r"shield", text, re.IGNORECASE):
        add("curved timber shields with rawhide edging")

    if not materials:
        return "late seventh-century Northeast Asian woven hemp, rough timber, packed earth"
    return ", ".join(materials)


def _tighten_goguryeo_succession_scene_terms(subject: str, scene: str) -> tuple[str, str]:
    replacements = (
        (
            r"\b(?:dark\s+)?belted\s+Goguryeo\s+jacket\b",
            "dark wrap-front Goguryeo robe tied with a broad cloth sash",
        ),
        (
            r"\bGoguryeo\s+court\s+jacket\b",
            "wrap-front Goguryeo court robe tied with a broad cloth sash",
        ),
        (
            r"\b(?:bronze\s+)?rank\s+belt\b",
            "woven rank sash with a face-down bronze clasp",
        ),
        (
            r"\bfortress\s+tally\s+belt\b",
            "cord-tied bundle of plain face-down hardwood fortress tallies",
        ),
        (
            r"\bbelt\s+fittings\b",
            "small face-down bronze sash clasps",
        ),
        (
            r"\bleather\s+boots?\b",
            "smooth-soled riding boots",
        ),
        (
            r"\boil[- ]lamp\b",
            "low bronze oil dish",
        ),
        (
            r"\bclosed\s+blank\s+cloth\s+petition\s+packet\b",
            "closed cord-tied hemp cloth packet with uninterrupted weave",
        ),
        (
            r"\bunmarked\s+bronze-bound\s+fortress\s+tallies\b",
            "face-down hardwood fortress tallies with small bronze corner caps",
        ),
        (
            r"\bblank\s+(?=(?:war|resistance|victory|rebel|Silla|Goguryeo)\s+standard\b)",
            "solid-color ",
        ),
        (
            r"\bblank\s+standards?\b",
            "solid dark-red hemp standards seen edge-on",
        ),
        (
            r"\bblank\s+stone\s+marker\b",
            "rough unmarked stone marker showing only natural grain",
        ),
    )

    def apply(value: str) -> str:
        out = value
        for pattern, replacement in replacements:
            out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
        return _clean_spaces(out)

    return apply(subject), apply(scene)


def _goguryeo_succession_scene_evidence(subject: str, scene: str) -> str:
    text = f"{subject} {scene}"
    if re.search(r"wounded\s+captured\s+Goguryeo\s+commander\s+Namgeon\s+bound\s+around\s+the\s+chest", text, re.IGNORECASE):
        return "one chest-up wounded Namgeon, one rope with three horizontal turns around chest and both upper arms, one shared side knot, one cheek and shoulder wound stain, continuous lamellar chest, zero visible hands, blank smoke wall"
    if re.search(r"kneeling\s+King\s+Bojang\s+and\s+standing\s+Tang\s+general\s+Li\s+Ji", text, re.IGNORECASE):
        return "helmeted Li Ji standing upper right in dark lamellar, Bojang on both knees lower left in a grey wrap robe, four empty hands, two complete bodies, clear high-low surrender hierarchy, zero weapons or packets, blank wall"
    if re.search(r"gilt-bronze\s+royal\s+diadem\s+ornament\s+plate\s+split\s+into\s+two\s+halves", text, re.IGNORECASE):
        return "one flat royal ornament split into exactly two matching flame-shaped halves, jagged edges facing across one gap, mud only, zero band, ring, crown or buildings"
    if re.search(r"uninscribed\s+Goguryeo\s+bronze\s+mirror\s+with\s+one\s+deep\s+center\s+split", text, re.IGNORECASE):
        return "one single round mirror disk, one deep jagged crack from top rim through center to bottom rim, one narrow dark fissure, blank soot-dark bronze, fine ash and tiny embers, zero second disk"
    if re.search(r"blank\s+wood-slip\s+bundle\s+overlapping\s+one\s+blank\s+bronze\s+plaque\s+inside\s+the\s+same\s+fire", text, re.IGNORECASE):
        return "one blank-backed wood-slip bundle over one half-visible blank bronze plaque, one connected fire directly touches both objects, both edges blackened, warm brown earth at every edge, zero writing or buildings"
    if re.search(r"cangue-bound\s+Goguryeo\s+captive", text, re.IGNORECASE):
        return "one kneeling captive visibly wearing one neck cangue"
    if re.search(r"captive\s+King\s+Bojang\s+and\s+wounded\s+Namgeon", text, re.IGNORECASE):
        return "exactly two men kneeling on both knees, Bojang left in a grey wrap robe, Namgeon right in rust lamellar, four empty hands on separate thighs, zero objects, blank wall"
    if re.search(r"Emperor\s+Gaozong\s+confronting\s+kneeling\s+King\s+Bojang", text, re.IGNORECASE):
        return "one standing emperor facing one kneeling captive, four connected hands"
    if re.search(r"Tang\s+rewards\s+laid\s+over\s+discarded\s+Goguryeo\s+allegiance", text, re.IGNORECASE):
        return "one blank-backed Tang seal immediately above one torn grey sash, two frayed ends, clean timber, zero garment or duplicate sash"
    if re.search(r"Tang\s+rank\s+seal\s+and\s+one\s+severed\s+Goguryeo\s+sash\s+at\s+the\s+Yeon\s+family\s+mound", text, re.IGNORECASE):
        return "one flat Tang rank seal upper center, one severed Goguryeo sash in exactly two aligned halves below, dry earth at every edge"
    if re.search(r"intact\s+Goguryeo\s+outer\s+wall\s+with\s+unseen\s+interior\s+fire\s+behind\s+it", text, re.IGNORECASE):
        return "one continuous intact outer wall spans the frame, firelight and black smoke rise behind, zero visible building, gatehouse, breach or attackers"
    if re.search(r"Goguryeo\s+gate\s+beam\s+split\s+from\s+inside\s+by\s+abandoned\s+rank\s+seals", text, re.IGNORECASE):
        return "one gate beam splits outward from one rotten center notch, exactly two blank-backed bronze seals remain in broken fibers, zero chain or people"
    if re.search(r"Goguryeo\s+command\s+seal\s+bound\s+inside\s+a\s+private\s+family\s+sash", text, re.IGNORECASE):
        return "one straight family sash crosses one solid closed blank-backed command seal, exactly two ends extend left and right, zero knots, loops or glyphs"
    if re.search(r"blank-backed\s+Tang\s+rank\s+seal\s+pressed\s+into\s+granted\s+earth", text, re.IGNORECASE):
        return "exactly one blank-backed Tang seal half-buried in exactly one earth-filled land-grant tray, zero person or writing"
    if re.search(r"Tang-ranked\s+Namsaeng\s+wearing\s+one\s+blank\s+rank\s+seal", text, re.IGNORECASE):
        return "one face-down blank-backed rank seal at Namsaeng's left belt, exactly one waist-up Namsaeng, exactly zero visible hands, black futou covering all hair, plain emblem-free lamellar, blank wall"
    if re.search(r"blank-backed\s+Tang\s+rank\s+seal\s+block\s+pinning\s+one\s+torn\s+Goguryeo\s+sash", text, re.IGNORECASE):
        return "one face-down blank-backed square bronze seal directly pins the torn center of one grey sash into mud, sash ends extend left and right, zero shoe, person or writing"
    if re.search(r"cracked\s+bronze\s+mirror\s+reflecting\s+one\s+collaborator\s+face", text, re.IGNORECASE):
        return "one mirror disk, one deep crack, exactly one coherent reflected male face with narrowed predatory eyes and bared teeth, zero real body or second face"
    if re.search(r"forgotten\s+exile\s+grave\s+outside\s+a\s+prosperous\s+Tang\s+traitor\s+household", text, re.IGNORECASE):
        return "sealed convex snow-covered grave mound foreground left, warm open doorway background right, one feast table and exactly three bronze cups, one continuous landscape, zero opening, pit or people"
    if re.search(r"overturned\s+Goguryeo\s+ruler\s+seat\s+beside\s+broken\s+rank\s+objects", text, re.IGNORECASE):
        return "one overturned low seat, exactly two cracked face-down blank bronze seals, exactly two severed red cord ends, ash, zero people or writing"
    if re.search(r"deceased\s+Yeon\s+Namsaeng\s+on\s+blank\s+dark\s+silk", text, re.IGNORECASE):
        return "face fills frame on featureless dark silk, eyes fully shut, zero iris, pupil, hands or forearms"
    if re.search(r"completely\s+closed\s+blank\s+Tang\s+court\s+gate", text, re.IGNORECASE):
        return "one completely closed blank timber gate fills every edge, two central plank leaves, one closed seam, two plain ring pulls, zero gap, signboard, roof, people or writing"
    if re.search(r"fully\s+shrouded\s+Tang\s+funeral\s+coffin\s+under\s+one\s+plain\s+hemp\s+mourning\s+canopy", text, re.IGNORECASE):
        return "exactly one canopy above exactly one fully shrouded coffin, zero wall, cap, person, prop or writing"
    if re.search(r"late-seventh-century\s+Mangshan\s+rammed-earth\s+burial\s+mound", text, re.IGNORECASE):
        return "one large mound fills the upper two-thirds with crest near top edge, one stone approach below, dark hills fill upper corners, zero blank sky, upright marker, people, caption or writing"
    if re.search(r"three\s+starving\s+and\s+wounded.*Goguryeo\s+defenders\s+and\s+civilians", text, re.IGNORECASE):
        return "three separated adults, six empty hands, one forearm bandage, one empty basket, one overturned empty bowl, completely bare shelves, zero grain, packed earth"
    if re.search(r"monk\s+Sinseong.*Goguryeo\s+accomplice.*gate\s+beam", text, re.IGNORECASE):
        return "one shaved male head left, one tied-haired male head right, exactly two visible hands total on one fully removed locking beam, wide air gap, two empty U-shaped brackets below, vertical gate planks"
    if re.search(r"one\s+massive\s+Pyongyang\s+timber\s+gate\s+opening", text, re.IGNORECASE):
        return "zero people, one narrow firelit gap, one removed locking beam on packed earth, two empty brackets, blank vertical gate planks"
    if re.search(r"one\s+adult\s+Goguryeo\s+defender\s+overwhelmed\s+by\s+the\s+breached\s+gate", text, re.IGNORECASE):
        return "one crouching armored defender, one cracked shield, recoiling shoulders, terrified face, inward smoke and dust surge, hostile torchlight, zero visible weapons or enemies"
    if re.search(r"one\s+Goguryeo\s+defender.*two\s+Tang\s+assault\s+infantry", text, re.IGNORECASE):
        return "three separated armored bodies, one tall center shield touching one smaller left shield and one sole right spearhead, exactly two shields and one spear, two close-fitting iron caps, blank charred wall"
    if re.search(r"Goguryeo\s+commander\s+Namgeon\s+realizing\s+defeat", text, re.IGNORECASE):
        return "one armored Namgeon, continuous identical lamellar rows across chest, two open empty hands, slumped shoulders, bare weaponless earth, one breached gate, distant spear silhouettes"
    if re.search(r"Goguryeo\s+commander\s+Namgeon\s+watching\s+the\s+breached\s+gate", text, re.IGNORECASE):
        return "near-frontal face, two fully visible eyes and cheeks, two glossy tear trails beginning directly at lower eyelids, uncut forehead, lamellar collar, opaque smoke, zero visible hands"
    if re.search(r"Goguryeo\s+commander\s+Namgeon\s+choosing\s+death", text, re.IGNORECASE):
        return "one kneeling armored Namgeon, right hand on one single-blade dagger, empty left palm on earth, clear air gap before chest, zero other weapons, blank smoke wall"
    if re.search(r"object-only\s+betrayal\s+evidence", text, re.IGNORECASE):
        return "exactly one diagonal wood tally, uninterrupted rough timber grain at every edge, zero people"
    if re.search(r"thirty-four-year-old\s+Yeon\s+Namsaeng", text, re.IGNORECASE) and re.search(
        r"Goguryeo\s+fortress\s+tally", text, re.IGNORECASE
    ):
        return "helmet and lamellar torso, exactly zero visible hands, one flat horizontal warm-brown wood-grain tally alone on table, solid plaster wall"
    if re.search(r"Emperor\s+Gaozong\s+directing\s+the\s+Pyongyang\s+campaign", text, re.IGNORECASE):
        return "black cloth futou covering Gaozong's hair knot, right index finger above one solid unmarked earth relief with raised walls and recessed roads, low table, continuous blank plaster walls"
    if re.search(r"Namgeon\s+running\s+past\s+three\s+embedded\s+arrows", text, re.IGNORECASE):
        return "one running armored Namgeon, three arrows embedded arrowhead-first in far-left timber, only straight shafts and rear fletching visible, clear body"
    if re.search(r"Goguryeo\s+archer\s+in\s+the\s+instant\s+after\s+release", text, re.IGNORECASE):
        return "one side-profile archer, one recurved bow, empty string snapping forward, open release hand at cheek, exactly two visible hands, zero projectiles, lamellar, segmented cap"
    if re.search(r"object-only\s+Sinseong\s+plot\s+evidence", text, re.IGNORECASE):
        return "broad sash crosses in front of one tied beige cloth pouch and covers its lower half on one folded robe, zero people and body parts"
    if re.search(r"monk\s+Sinseong\s+concealing\s+a\s+plot", text, re.IGNORECASE):
        return "left hand opens robe, right hand pushes one irregular rounded soft cloth bundle halfway into sash, exactly two visible hands, no feet, dark edges"
    if re.search(r"monk\s+Sinseong.*Tang\s+military\s+messenger", text, re.IGNORECASE):
        return "shaved-head monk left, iron-lamellar helmeted Tang messenger right, one soft packet passing between them, blank drainage walls"
    if re.search(r"two\s+standing\s+Tang\s+infantry.*one\s+prone\s+Goguryeo\s+defender", text, re.IGNORECASE):
        return "exactly three bodies, two standing infantry, one prone defender, one shield, one spear, blank charred wall"
    if re.search(r"three\s+injured.*Goguryeo\s+civilians.*burned\s+shelter", text, re.IGNORECASE):
        return "exactly three separated crawling bodies, ash, one blank collapsed timber wall"
    if re.search(r"exhausted.*Goguryeo\s+defender.*converging\s+spear\s+shadows", text, re.IGNORECASE):
        return "one complete defender, one cracked shield, converging weapon shadows, bare mud"
    if re.search(r"one\s+adult\s+Tang\s+officer\s+crushing.*Goguryeo\s+rank\s+tablet", text, re.IGNORECASE):
        return "one complete officer, right boot in direct contact with one cracked blank rank tablet, both hands visible, bare mud"
    if re.search(r"two\s+adult\s+male\s+Goguryeo\s+brothers.*Namgeon.*Namsan", text, re.IGNORECASE):
        return "exactly two complete commanders, four empty hands, one earthen rampart with irregular stones, distant Tang tents and smoke"
    if re.search(r"three\s+fearful\s+Goguryeo\s+soldiers.*six\s+empty\s+hands", text, re.IGNORECASE):
        return "exactly three separate suspicious soldiers, six open empty hands, three distinct head directions, blank wallboards, drifting smoke"
    if re.search(r"two\s+adults.*starving\s+civilian.*kneeling\s+lamellar\s+soldier", text, re.IGNORECASE):
        return "two bodies, four hands on knees, tall wall"
    if re.search(r"Goguryeo\s+timber\s+hall\s+support\s+column\s+splitting", text, re.IGNORECASE):
        return "one support column splitting at stone footing, long fresh splinters, one sagging crossbeam, plain earthen wall and dark floor"
    if re.search(r"blank\s+unmarked\s+fibrous\s+sheet\s+burning\s+into\s+ash", text, re.IGNORECASE):
        return "one thin sheet, pale left half, black curled right half, attached flames, cool grey stone only"
    if re.search(r"two\s+grey\s+wolves.*dark\s+earthen\s+pit", text, re.IGNORECASE):
        return "exactly two separate wolves, eight total legs, two heads, two tails, snarling mouths, bare mud and one earthen pit"
    if re.search(r"full-scale\s+Pyongyang\s+Goguryeo\s+fortress\s+encircled\s+by\s+Tang\s+tents", text, re.IGNORECASE):
        return "one central full-scale earthen fortress, one continuous surrounding ring of low Tang tents, small fires only in bare gaps between tents, open isolation gap, smoke-filled plain"
    if re.search(r"unglazed\s+Goguryeo\s+grain\s+jar\s+ruptured\s+open\s+by\s+black-green\s+rot", text, re.IGNORECASE):
        return "one plain jar, one front rupture, black-green mold, clumped spoiled millet inside, intact rim and side silhouette, packed earth only"
    if re.search(r"dark\s+snake\s+clamping\s+its\s+own\s+continuous\s+mid-body\s+between\s+closed\s+jaws", text, re.IGNORECASE):
        return "closed jaws overlap own mid-body, one open S-body, tail far from mouth, stone only"
    if re.search(r"three\s+separate\s+Goguryeo\s+oval\s+timber\s+shields.*iron\s+boss", text, re.IGNORECASE):
        return "exactly three separate oval shields, one central iron boss on each shield, wide gaps, three rawhide rims"
    if re.search(r"two\s+blank\s+bronze\s+seals\s+divided\s+by\s+one\s+deep\s+floor\s+crack", text, re.IGNORECASE):
        return "two separate blank-backed seals angle away from one empty center fissure, packed clay only"
    if re.search(r"tall\s+oval\s+shield.*back\s+side\s+up.*one\s+broken\s+leather\s+grip", text, re.IGNORECASE):
        return "one backside-up tall oval shield, one center grip snapped once into two facing frayed ends, rotten wood beneath"
    if re.search(r"cracked\s+bronze\s+stamp.*low\s+bridge\s+knob.*dark-red\s+stain", text, re.IGNORECASE):
        return "one compact square stamp, low bridge knob attached directly to back center, one fracture, one ragged stain, charcoal stone only"
    if re.search(r"flat\s+foundation\s+stone.*permanent\s+red\s+scar", text, re.IGNORECASE):
        return "one natural slab, pale rain crosses its surface, packed earth only"
    if re.search(r"empty\s+dented\s+segmented\s+iron\s+helmet\s+in\s+one\s+fresh\s+cart-wheel\s+track", text, re.IGNORECASE):
        return "dented half-dome cap on its side, wide open bottom partly visible, broad diagonal track beneath, two irregular rut edges, deep mud only"
    if re.search(r"(?:exactly\s+)?one\s+cropped\s+Tang-era\s+cloth-wrapped\s+forefoot\s+pressing\s+(?:exactly\s+)?one\s+dented\s+Goguryeo\s+iron\s+cap(?:\s+into\s+mud)?", text, re.IGNORECASE):
        return "cropped wrapped forefoot, heel outside frame, soft rounded toe, flat cloth underside, direct toe-to-cap contact, rimless segmented cap in mud"
    if re.search(r"two\s+weaponless\s+fighters.*rust\s+Goguryeo.*black\s+Tang", text, re.IGNORECASE):
        return "two separate bodies, rust left and black right, four closed empty fists, four wrapped boots, continuous featureless ochre earthen wall"
    if re.search(r"torn\s+golden\s+silk\s+veil.*shallow\s+segmented\s+Goguryeo\s+iron\s+cap", text, re.IGNORECASE):
        return "two objects, torn golden veil left, shallow iron cap on its side right, open bottom and empty interior visible"
    if re.search(r"blood-smeared\s+five-finger\s+handprint", text, re.IGNORECASE):
        return "exactly one flat palm-shaped blood stain, exactly five flat finger smears, continuous packed-clay landform terrain, raised mountain ridges and one winding recessed river channel"
    if re.search(r"broken\s+Goguryeo\s+(?:guardless\s+)?ring-pommel\s+sword", text, re.IGNORECASE):
        return "right compact triangular tip with point inside frame; left horizontal hilt with small far-left ring, narrow grip and guardless blade stump; one center gap; freezing wet mud"
    if re.search(r"layered-timber\s+shield\s+split\s+into\s+exactly\s+two", text, re.IGNORECASE):
        return "one complete oval shield silhouette, exactly two overlapping jagged timber halves, one small plain boss on left half, broad freezing-mud margin"
    if re.search(r"abandoned\s+rain-soaked\s+Goguryeo\s+command\s+robe", text, re.IGNORECASE):
        return "one dark wrap-front robe, one attached grey cloth tie, receding wrapped-shoe tracks, uninterrupted wet mud"
    if re.search(r"Heonseong", text, re.IGNORECASE):
        if re.search(r"fully\s+prostrate|offered\s+as\s+a\s+hostage", text, re.IGNORECASE):
            return "one teenage male body fully prostrate, terrified side profile, two coherent hands, closed wrapped shoes, bare floor, plain dais edge and blank wall"
        return "one slender teenage male walking alone, one small square cloth parcel under left arm, fearful backward glance, one bare dirt road and low rammed-earth banks"
    if re.search(r"kneeling\s+Namsaeng.*Tang\s+(?:frontier\s+)?envoy", text, re.IGNORECASE) and re.search(r"empty\s+open\s+palms", text, re.IGNORECASE):
        return "Namsaeng's two empty open palms, envoy's two empty hands, bowed head, low black futou, one blank wall and dark floor"
    if re.search(r"traitor\s+guard.*locking\s+(?:bar|beam)|locking\s+(?:bar|beam).*traitor\s+guard", text, re.IGNORECASE):
        return "one back-facing guard body, two separated hands beneath one waist-high timber locking beam, two empty iron brackets, vertical gate planks"
    if re.search(r"unlatched\s+heavy\s+iron\s+gate\s+chain\s+laid\s+as\s+one\s+open\s+straight\s+segment", text, re.IGNORECASE):
        return "one open diagonal chain segment, two free end links far apart, smooth clay only"
    if re.search(r"heavy\s+iron\s+gate\s+chain\s+fully\s+detached\s+from\s+one\s+open\s+wall\s+hook", text, re.IGNORECASE):
        return "one chain at left and one empty hook at right on one continuous gate plane, final open link, broad clear air gap, far-right torchlit seam"
    if re.search(r"iron\s+gate\s+chain.*one\s+sleeve-covered\s+right\s+hand|one\s+sleeve-covered\s+right\s+hand.*iron\s+gate\s+chain", text, re.IGNORECASE):
        return "one right hand lifting final chain link clear above one open hook, remaining chain hanging freely, one sleeve-covered forearm only"
    if re.search(r"iron\s+gate\s+chain.*sleeve-covered\s+hands|sleeve-covered\s+hands.*iron\s+gate\s+chain", text, re.IGNORECASE):
        return "right hand lifting final chain link completely clear above one open hook, left hand supporting slack, exactly two sleeve-covered hands, head and torso outside frame"
    if re.search(r"traitor\s+guard.*iron\s+gate\s+chain|iron\s+gate\s+chain.*traitor\s+guard", text, re.IGNORECASE):
        return "one crouching guard, left hand under one iron chain, right hand at one wall hook, one narrow torchlit gate seam"
    if re.search(r"plants?\s+exactly\s+one\s+short\s+straight\s+ring-pommel\s+sword", text, re.IGNORECASE):
        return "one point-down ring-pommel sword, Namsaeng's two hands on its pommel, standing commander's two empty hands, plain wallboards"
    if re.search(r"Tang-armored\s+Namsaeng\s+pointing", text, re.IGNORECASE):
        if re.search(r"weaponless|empty\s+right\s+hand|straight\s+index\s+finger", text, re.IGNORECASE):
            return "one armored man, one empty right hand with one straight pointing index finger, one empty left fist, low earthen ramparts, timber palisades, muddy ridge"
        return "one compact short straight ring-pommel sword directed toward low earthen ramparts and timber palisades, one armored man, one empty left fist, muddy ridge"
    if re.search(r"six\s+face-down\s+bronze-capped\s+hardwood\s+fortress\s+tallies", text, re.IGNORECASE):
        return "six separate blank-backed tallies in two rows of three, grey left sash, black right sash, continuous timber grain"
    if re.search(r"two\s+exhausted\s+Goguryeo\s+civilians.*two\s+Tang\s+guards", text, re.IGNORECASE):
        return "two tied cloth bundles, four separate adults, muddy gate ground, coercive guard positions"
    if re.search(r"gaunt\s+Goguryeo\s+civilian.*two\s+armored\s+officials", text, re.IGNORECASE):
        return "one low dark timber table, exactly two small smooth pebbles, central gaunt civilian, two flanking officials, blank earthen wall"
    if re.search(r"Gaozong", text, re.IGNORECASE) and re.search(r"rank\s+seal", text, re.IGNORECASE):
        return "one small blank gilt-bronze rank seal between Gaozong and kneeling Namsaeng, plain timber wall, low dais"
    if re.search(r"Gaozong", text, re.IGNORECASE) and re.search(r"Namsaeng", text, re.IGNORECASE) and re.search(r"whisper(?:s|ing)?|mouth\s+directly\s+beside", text, re.IGNORECASE):
        return "Namsaeng's mouth beside Gaozong's ear, two separate male heads, two natural necks, one soft black futou, one blank wall"
    if re.search(r"exactly\s+one\s+adult\s+male\s+Emperor\s+Gaozong", text, re.IGNORECASE):
        return "cold triumphant smile, one raised open empty hand, soft black futou, blank plaster wall"
    if re.search(r"Gaozong", text, re.IGNORECASE):
        return "Gaozong's cold smile and raised open hand, Namsaeng's bowed head and two empty hands, uninterrupted blank plaster wall, cropped plain platform"
    if re.search(r"three\s+adult\s+Goguryeo\s+brothers", text, re.IGNORECASE):
        return "smoky timber court wall, packed earth, embers"
    if re.search(r"defense-route\s+handover\s+layout|six\s+smooth\s+grey\s+river-stone", text, re.IGNORECASE):
        return "top three stones, bottom three stones, empty middle gap, straight red cord, grey left sash, black right sash, continuous installed floor planks"
    if re.search(r"severed\s+grey\s+woven\s+Goguryeo\s+clan\s+sash", text, re.IGNORECASE):
        return "uninterrupted dark brown floorboard grain, exactly two grey sash halves, one narrow center gap, facing frayed cut fibers"
    if re.search(r"Namsaeng", text, re.IGNORECASE) and re.search(
        r"fortress\s+tally|route\s+cord|Tang\s+commander",
        text,
        re.IGNORECASE,
    ):
        if re.search(r"Tang\s+military\s+registrar", text, re.IGNORECASE):
            return "one palm-sized flat rectangular blank fortress tally lying horizontally untouched on one low table, fitted Tang lamellar and black sleeves on male Namsaeng, unarmored black-futou registrar, blank wall"
        return "plain wallboards, continuous dark floor, one palm-sized blank-backed tally, one red cord"
    if re.search(r"Tang-armored.*rider\s+Namsaeng|Namsaeng.*one\s+horse|paired\s+leather\s+reins", text, re.IGNORECASE):
        if re.search(r"burn(?:ed|ing)\s+Goguryeo\s+village|burning\s+village\s+road|grain\s+basket|broken\s+clay\s+pots", text, re.IGNORECASE):
            return "one complete horse and rider, both fists on paired reins, connected bridle, overturned grain basket, broken clay pots, burning timber-and-thatch homes"
        return "one complete horse and rider, both fists on paired reins, connected bridle, muddy road, broken boundary post"
    if re.search(r"Namsaeng", text, re.IGNORECASE) and re.search(r"Tang\s+attendant", text, re.IGNORECASE):
        return "one removed grey rank sash between Namsaeng and one attendant, two separate bodies, plain wallboards"
    if re.search(r"Namsaeng\s+changing\s+into\s+a\s+Tang\s+commander|pulls?\s+one\s+plain\s+grey\s+Goguryeo\s+rank\s+sash", text, re.IGNORECASE):
        return "one armored male body, right hand on one shoulder fastening, left hand holding one removed grey sash, one blank wall"
    if re.search(r"discarded\s+Goguryeo\s+command\s+cloak.*cut\s+grey\s+rank\s+sash", text, re.IGNORECASE):
        return "one dark cloak, exactly two separated grey sash halves, one face-down plain clasp, continuous floorboards"
    if re.search(r"fully\s+prostrate\s+Namsaeng", text, re.IGNORECASE):
        return "Namsaeng's forehead at the envoy's boots, one blank fortress tally, two separate bodies, continuous dark floor"
    if re.search(r"Silla(?:\s+frontier)?\s+guard", text, re.IGNORECASE):
        return "one large plain ochre triangular standard, low hide tents, timber palisade, one small soft tan tied cloth bundle, kneeling Jeongto and low-black-helmet Silla guard"
    if re.search(r"full-scale[^.;]{0,60}Goguryeo\s+rammed-earth\s+(?:fortress|defensive\s+embankment)", text, re.IGNORECASE):
        return "cascading granular collapse across entire right half, smooth unmarked low earthen slope at left, sparse plain timber stakes and dark storm sky"
    if re.search(r"granite\s+fortress\s+wall.*center\s+melting", text, re.IGNORECASE):
        return "one deep widening central cavity, visibly sagging and dripping granite edges, solid adjacent irregular fieldstones, poison entering from upper edge"
    if re.search(r"poisoned\s+Goguryeo\s+gilt-bronze\s+royal\s+diadem", text, re.IGNORECASE):
        return "one broad-band diadem, exactly three rounded flame uprights, black poison coating center, one rough stone pedestal"
    if re.search(r"blank\s+square\s+bronze\s+succession\s+plaque\s+half-submerged\s+in\s+black\s+poison", text, re.IGNORECASE):
        return "one blank square bronze plaque, lower half submerged beneath black poison, smooth unbroken ochre clay only"
    if re.search(r"cracked\s+plain\s+square\s+bronze\s+succession\s+plaque", text, re.IGNORECASE):
        return "one blank square bronze plaque, one diagonal center crack leaking black poison, packed earth only"
    if re.search(r"cracked\s+(?:face-down|handle-down)\s+plain\s+square\s+bronze\s+succession\s+seal", text, re.IGNORECASE):
        return "one blank handle-down square seal with stamping face upward, one diagonal center crack leaking black poison, uninterrupted packed earth"
    if re.search(r"secret\s+red\s+route\s+cord\s+joining\s+one\s+grey\s+Goguryeo\s+sash", text, re.IGNORECASE):
        return "narrow horizontal wrinkled grey cloth left, narrow horizontal wrinkled black cloth right, exactly three separate grey oval stones in one row, one red cord crossing all three centers, uninterrupted dark floorboards"
    if re.search(r"blank-backed\s+hardwood\s+fortress\s+tally\s+sliding\s+under", text, re.IGNORECASE):
        return "one blank tally halfway under one flat black Tang sash, one attached red route cord, one torn grey Goguryeo sash fragment, continuous dark floorboards"
    if re.search(r"realistic(?:\s+adult)?\s+brown\s+rat", text, re.IGNORECASE):
        return "one rat only, four natural paws, one coherent spine, one intact head, one long unbroken tail, one flat boot-shaped shadow"
    if re.search(r"three\s+starving\s+Goguryeo\s+civilians", text, re.IGNORECASE):
        return "three distinct adults, separate empty grain baskets, muddy lane, collapsed granary awning"
    if re.search(r"villagers\s+with\s+visible\s+tear\s+tracks", text, re.IGNORECASE):
        return "three distinct grief-stricken faces, reddened eyes, clear wet cheek tears, clean undyed robes, burned homes and empty sky behind roofs"
    if re.search(r"two\s+kneeling\s+Goguryeo\s+officials.*standing\s+Tang\s+soldier", text, re.IGNORECASE):
        return "two kneeling grey-robed officials, one standing armored soldier, six empty hands, plain courtyard"
    if re.search(r"guards\s+exchanging\s+one\s+fortress\s+key", text, re.IGNORECASE):
        return "one blank key block between four visible hands, two distinct guards, cracked timber passage"
    if re.search(r"cracked\s+oval\s+Goguryeo\s+timber\s+shield.*one\s+detached\s+spearhead", text, re.IGNORECASE):
        return "one convex oval layered-plank shield, one detached triangular spearhead blade in the central crack, uninterrupted packed earth"
    if re.search(r"upright\s+uninscribed\s+flared\s+bronze\s+alarm\s+bell", text, re.IGNORECASE):
        return "one upright flared bell, one top loop and frayed stub, smooth blank bronze, packed earth"
    if re.search(r"cracked\s+stone\s+(?:official|kneeling)\s+statue", text, re.IGNORECASE):
        return "one physical stone statue, one chest-to-base crack, one flat black ground shadow with elongated finger shapes, empty courtyard"
    if re.search(r"Goguryeo\s+ceremonial\s+throne\s+sinking", text, re.IGNORECASE):
        return "one upright tall-backed throne, two armrests, lower half submerged, one dark red pool, one continuous stone floor"
    if re.search(r"overturned\s+low\s+timber\s+command\s+seat", text, re.IGNORECASE):
        return "one overturned backless seat, one face-down cracked blank tablet, shallow dark red rainwater, continuous floor"
    if re.search(r"segmented\s+iron\s+helmets", text, re.IGNORECASE):
        return "three separate empty open helmet interiors, two snapped straight spear shafts, cart tracks and snow"
    if re.search(r"two\s+adult\s+Goguryeo\s+civilian\s+bearers.*fully\s+shrouded\s+casualty", text, re.IGNORECASE):
        return "two separate bearer bodies, four hands on two stretcher poles, one fully closed shroud, smoke-filled packed-earth lane"
    if re.search(r"low\s+segmented\s+iron\s+cap\s+helmet.*flattened\s+gilt-bronze\s+cover", text, re.IGNORECASE):
        return "one low segmented iron helmet, one visibly flattened thin gilt-bronze sheet cover, continuous packed earth"
    if re.search(r"Tang\s+assault\s+infantry.*Pyongyang\s+gate", text, re.IGNORECASE):
        return "two fitted lamellar coats, blank vertical gate planks, narrow firelit gap, one oval timber shield, one straight spear"
    if re.search(r"Goguryeo\s+defender.*severed\s+inner-gate\s+rope", text, re.IGNORECASE):
        return "one split oval timber shield, one severed gate rope, smoke-dark packed earth, open gate gap, hostile torchlight"
    if re.search(r"wounded.*Goguryeo\s+survivor.*smoke-filled", text, re.IGNORECASE):
        return "one grief-struck adult face, two empty hands, torn soot-dark buttonless wrap-front robe, one restrained dark-red side stain, opaque charcoal smoke only"
    if re.search(r"three\s+injured.*Goguryeo\s+civilians.*burning\s+exterior\s+alley", text, re.IGNORECASE):
        return "three separated crawling adults, torn hemp robes, wrapped shoes, blank collapsed timber wall, fire, smoke, ash"
    if re.search(r"discarded\s+cracked\s+Goguryeo\s+fortress\s+tally.*two\s+intact\s+elite\s+rank\s+fittings", text, re.IGNORECASE):
        return "one cracked blank hardwood tally below one table edge, exactly two matching flat solid rectangular bronze belt plaques with closed faces and no holes above, ash, hard side light"
    if re.search(r"shattered\s+uninscribed\s+Goguryeo\s+bronze\s+ritual\s+bell", text, re.IGNORECASE):
        return "one shattered upright flared bell, one large hand-width jagged section completely missing from its lower skirt, exactly three separate charred roof beams lying flat on the ground fully behind, fire, packed earth"
    if re.search(r"Tang\s+officer.*face-down\s+blank-backed\s+Goguryeo\s+record-slip\s+bundle", text, re.IGNORECASE):
        return "one Tang officer in iron lamellar and conical helmet, both hands behind his back, right wrapped boot underside overlapping the center of one face-down cord-tied hardwood slip bundle, plain reverse wood grain, mud, smoke"
    if re.search(r"cracked\s+Goguryeo\s+granary\s+jar.*spoiled\s+millet", text, re.IGNORECASE):
        return "one upright narrow-necked clay jar, one small side fracture, continuous fine millet texture like coarse sand with individual kernels too tiny to resolve, fuzzy mold on grain clumps, smoke-dark granary floor"
    if re.search(r"three\s+shallow\s+cracked\s+household\s+grain\s+bowls.*overturned\s+command\s+stool", text, re.IGNORECASE):
        return "smoke-dark earth filling every edge, three shallow cracked bowls, one overturned stool crossbar physically touching all three broken rims, small spilled millet"
    if re.search(r"scorched\s+empty\s+hemp\s+identity\s+pouch", text, re.IGNORECASE):
        return "one small soft wrinkled plain-hemp pouch with puckered mouth mostly reduced to ash, one limp cloth edge, one short thin cut drawcord, loose blackened fibers, embers, charcoal"
    if re.search(r"three\s+separated\s+face-down\s+blank\s+hardwood\s+heroic\s+record\s+slips", text, re.IGNORECASE):
        return "exactly three separated parallel plain-backed wood slips, wide gaps, zero cord or rope, one clearly blackened missing corner, fine pale-grey ash, embers"
    if re.search(r"short\s+straight\s+iron\s+utility\s+knife\s+between\s+two\s+separated\s+halves.*red\s+hemp\s+cord", text, re.IGNORECASE):
        return "one vertical knife in a clear gap, one separate red cord half left, one separate red cord half right, two facing frayed ends do not touch, rough timber"
    if re.search(r"Namsaeng", text, re.IGNORECASE) and re.search(r"(?:cut|snapped)\s+red\s+clan\s+cord", text, re.IGNORECASE):
        return "unbroken dark wallboards, bowed shoulders, two cord halves held apart with one empty gap between their frayed cut ends"
    if re.search(r"Tang\s+military\s+registrar", text, re.IGNORECASE) and re.search(r"fortress\s+tally", text, re.IGNORECASE):
        return "one palm-sized flat rectangular blank fortress tally lying horizontally untouched on one low table, fitted Tang lamellar and black sleeves on male Namsaeng, unarmored black-futou registrar, blank wall"
    if re.search(r"Namsaeng", text, re.IGNORECASE) and re.search(r"registrar|registry", text, re.IGNORECASE):
        return "unbroken dark wallboards, bowed shoulders, one palm-sized blank-backed bronze seal"
    if re.search(r"sabotaged\s+Goguryeo\s+timber\s+gate\s+brace", text, re.IGNORECASE):
        return "one horizontal beam, one deep V-shaped axe notch, pale chopped facets, small fieldstones in rammed earth"
    if re.search(r"exactly\s+two\s+plain\s+square\s+bronze\s+seal\s+blocks", text, re.IGNORECASE):
        return "two squat bronze blocks, two knob handles, red cord on right knob, rough timber"
    if re.search(r"dagger.*(?:command|guard)\s+sash|dagger\s+half[- ]covered", text, re.IGNORECASE):
        return "continuous rough floorboard grain, folded woven command sash, plain dagger blade, diffuse doorway light"
    if re.search(r"horse|rides?|mounted|cavalry", text, re.IGNORECASE):
        if re.search(r"wilderness\s+track|earthen\s+banks|pine\s+slopes", text, re.IGNORECASE):
            return "dense pine slopes, boulders, low earthen banks, muddy wilderness track, dark storm clouds"
        if re.search(r"storm|muddy|freezing\s+rain", text, re.IGNORECASE):
            return "muddy road, split-log rails, dark storm clouds"
        return "packed riding ground, leather tack, timber posts, overcast sky"
    if re.search(r"sandals?", text, re.IGNORECASE):
        return "flat woven hemp sandals, ash, collapsed timber granary"
    if re.search(r"stretcher", text, re.IGNORECASE):
        return "simple timber stretcher, broken timber shields, snapped spear shafts, packed earth, smoke"
    if re.search(r"abandoned\s+casualty\s+gear", text, re.IGNORECASE):
        return "broken timber shield, snapped straight spear shaft, folded hemp shroud, worn cloth shoe, ash, low smoke"
    if re.search(r"\b(?:kneels?|bows?|envoy|registrar|audience)\b", text, re.IGNORECASE):
        return "plain timber wall, dark floor, closed packet"
    if re.search(r"bronze\s+(?:cup|drinking\s+(?:bowl|cup))|footless\s+bronze|Tang\s+residence", text, re.IGNORECASE):
        return "limp folded dyed silk bundles, lacquer table, dark timber wallboards, translucent silk-backed timber lattice"
    if re.search(r"gate\s+bar|plank\s+gate|gate\s+seam", text, re.IGNORECASE):
        return "plank gate, timber bar, iron brackets, enemy torchlight"
    if re.search(r"granary\s+beam|collapsed\s+beam|damaged\s+timber\s+homes", text, re.IGNORECASE):
        return "one fallen beam, open packed earth, damaged timber homes"
    if re.search(r"prisoner|chain|wrist\s+iron", text, re.IGNORECASE):
        return "short wrist chain, wrapped shoes, snow, packed road"
    if re.search(r"fortress|wall|battlement|siege", text, re.IGNORECASE):
        return "sloped earth rampart, rubble stone, timber parapet, smoke"
    if re.search(r"standard|banner|flag", text, re.IGNORECASE):
        return "solid hemp cloth, rough timber pole, ash, hard side light"
    if re.search(r"object-only|jar|tablet|seal|marker|helmet|brazier", text, re.IGNORECASE):
        return "named object, rough grain, timber, hard side light"
    if re.search(r"battle|soldier|guard|sword|blade|spear", text, re.IGNORECASE):
        return "smoke, earth, snapped spears, timber, torchlight"
    return "Goguryeo succession crisis, 666-668 AD"


def _concretize_goguryeo_succession_runtime_prompt(
    prompt: str,
    narration: str = "",
    script_context: str = "",
) -> str:
    if not _is_goguryeo_succession_cue_context(prompt, narration, script_context):
        return prompt
    scene = _scene_text_for_policy(prompt)
    subject, concrete_scene, place = _concretize_goguryeo_succession_runtime_scene(scene, narration)
    subject, concrete_scene = _tighten_goguryeo_succession_scene_terms(subject, concrete_scene)
    place_rewrites = (
        (r"Tang imperial audience hall at Chang'an", "Chang'an Tang audience hall"),
        (r"Tang imperial registry chamber at Chang'an", "Chang'an Tang registry"),
        (r"Tang imperial court at Chang'an", "Chang'an Tang court"),
        (r"Tang elite residence at Chang'an", "Chang'an Tang residence"),
        (r"plain undecorated Tang elite residence interior at Chang'an", "Chang'an Tang residence"),
        (r"Tang military camp in Liaodong", "Liaodong Tang camp"),
        (r"dark overcast Tang frontier training ground enclosed by timber palisade", "Tang frontier palisade"),
        (r"Muddy road south of Pyongyang", "South Pyongyang road"),
        (r"Chang'an Tang elite residence", "Chang'an Tang residence"),
        (r"Chang'an Tang residence,\s*late 7th century", "Chang'an Tang residence, 7th c."),
        (r"Tang frontier command hall near Gungnae Fortress", "Gungnae Tang command hall"),
        (r"Tang frontier command hall in Liaodong", "Liaodong Tang command hall"),
        (r"Tang frontier command hall", "Tang command hall"),
        (r"Goguryeo fortress district during the succession war", "Goguryeo fortress district"),
        (r"Pyongyang Fortress court courtyard", "Pyongyang court courtyard"),
        (r"Pyongyang Fortress audience hall", "Pyongyang audience hall"),
        (r"Pyongyang Fortress outer courtyard", "Pyongyang outer courtyard"),
        (r"Pyongyang Fortress during the final siege", "Besieged Pyongyang Fortress"),
        (r"Pyongyang Fortress siege perimeter", "Pyongyang siege perimeter"),
        (r"Pyongyang Fortress after the succession war", "Fallen Pyongyang Fortress"),
        (r"Liaodong frontier under Tang occupation", "Tang-held Liaodong frontier"),
        (r"Liaodong military road toward Pyongyang", "Liaodong road"),
        (r"Liaodong road toward Pyongyang", "Liaodong-Pyongyang road"),
    )
    for pattern, replacement in place_rewrites:
        place = re.sub(pattern, replacement, place, flags=re.IGNORECASE)
    material = _goguryeo_succession_material_contract(subject, concrete_scene)
    scene_evidence = _goguryeo_succession_scene_evidence(subject, concrete_scene)
    out = prompt
    if subject:
        out = _set_prompt_field(out, "Main subject", subject)
    if concrete_scene:
        out = _set_prompt_field(out, "Scene", concrete_scene)
    out = re.sub(
        r"(?:^|;\s*)Year/period:\s*[^;]+;\s*Goguryeo succession crisis,\s*666-668 AD",
        "; Year/period: 666-668 AD Goguryeo succession",
        out,
        count=1,
        flags=re.IGNORECASE,
    ).lstrip("; ")
    out = _set_prompt_field(out, "Year/period", "666-668 AD Goguryeo succession")
    out = _set_prompt_field(out, "Exact place", place)
    out = _set_prompt_field(
        out,
        "Culture scope",
        "7th-c. Goguryeo and Tang",
    )
    out = _set_prompt_field(
        out,
        "Material culture",
        material,
    )
    out = _set_prompt_field(
        out,
        "Scene evidence",
        scene_evidence,
    )
    return _clean_spaces(out)


def normalize_cut_image_prompt(
    prompt: str,
    narration: str = "",
    script_context: str = "",
    *,
    enable_series_repairs: bool = True,
) -> str:
    """Normalize one cut with narration-aware role alignment."""
    safe_prompt = _strip_conflicting_year_period_segments(normalize_image_prompt(prompt))
    if not enable_series_repairs:
        normalized = strip_narration_leakage(safe_prompt, narration)
        return _append_narration_alignment_hint(
            _strip_conflicting_year_period_segments(normalized),
            narration,
        )
    safe_prompt = _concretize_goguryeo_succession_runtime_prompt(
        safe_prompt,
        narration,
        script_context,
    )
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
    scene_markers = list(
        re.finditer(r"(?:^|[.;]\s*)Scene\s*:\s*", out, re.IGNORECASE)
    )
    if scene_markers:
        scene = out[scene_markers[-1].end():]
        scene = re.split(
            r"(?:[.;]\s*)?NARRATION\s+VISUAL\s+ALIGNMENT\s*:|\s+\|\|\s+",
            scene,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        scene = _clean_spaces(scene).strip(" ;")
        if scene:
            return scene
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


_JAPANESE_CREATION_MYTH_CONTEXT_RE = re.compile(
    r"(?:신화\s*시대|미소기|日本\s*神話|神話\s*時代|古事記|日本書紀|"
    r"伊邪那岐|伊弉諾|伊邪那美|伊弉冉|天照|月読|月讀|須佐之男|素戔嗚|"
    r"黄泉(?:の)?国|禊|三貴子|保食神|"
    r"\b(?:Izanagi|Izanami|Amaterasu|Tsukuyomi|Susanoo|Uke\s+Mochi|"
    r"Yomi\s+underworld|Japanese\s+(?:creation\s+)?myth)\b)",
    re.IGNORECASE,
)

_JAPANESE_MYTH_IDENTITIES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("Izanagi", "male Japanese creator deity", ("Izanagi", "伊邪那岐", "伊弉諾", "イザナギ", "いざなぎ")),
    ("Izanami", "female Japanese creator deity", ("Izanami", "伊邪那美", "伊弉冉", "イザナミ", "いざなみ")),
    ("Amaterasu", "female Japanese sun deity", ("Amaterasu", "天照大御神", "天照大神", "天照", "アマテラス", "あまてらす")),
    ("Tsukuyomi", "male Japanese moon deity", ("Tsukuyomi", "月読命", "月讀命", "月読", "月讀", "ツクヨミ", "つくよみ")),
    ("Susanoo", "male Japanese storm deity", ("Susanoo", "須佐之男命", "須佐之男", "素戔嗚尊", "素戔嗚", "スサノオ", "すさのお")),
    ("Uke Mochi", "female Japanese food deity", ("Uke Mochi", "Ukemochi", "保食神", "ウケモチ", "うけもち")),
    ("Messenger deity", "unnamed Japanese messenger deity", ("Messenger deity",)),
)

_JAPANESE_MYTH_VISUAL_IDENTITY = {
    "Izanagi": "adult male Izanagi, lean angular middle-aged East Asian face, narrow eyes, high black topknot, pointed chin beard, clean-shaven cheeks, archaic white wide-sleeve robe",
    "Izanami": "adult female Izanami, mature East Asian face, long loose black hair, Japanese creator deity in an archaic earth-tone wide-sleeve robe",
    "Amaterasu": "adult female Amaterasu, mature East Asian face, long center-parted black hair, bare forehead, plain unpatterned pre-state ivory plant-fiber wrap",
    "Tsukuyomi": "adult male Tsukuyomi, mature East Asian face, long loose black hair, bare forehead, plain unpatterned pre-state pale-blue plant-fiber wrap",
    "Susanoo": "adult male Susanoo, mature East Asian face, wild shoulder-length black hair, bare forehead, stern angular brows, plain unpatterned pre-state earth-blue plant-fiber wrap",
    "Uke Mochi": "adult female Uke Mochi, mature East Asian face, long loose dark hair, bare forehead, plain unpatterned pre-state earth-tone plant-fiber wrap",
    "Messenger deity": "adult male unnamed Japanese messenger deity, mature East Asian face, long loose dark hair, bare forehead, plain unpatterned pre-state undyed plant-fiber wrap",
}

_JAPANESE_MYTH_PAIR_IDENTITY = {
    "Izanagi": "adult male Izanagi, high black topknot, pointed chin beard, plain ivory wrap",
    "Izanami": "adult female Izanami, long loose black hair, plain earth-tone wrap",
    "Amaterasu": "adult female Amaterasu, long black hair, plain ivory wrap",
    "Tsukuyomi": "adult male Tsukuyomi, long black hair, plain pale-blue wrap",
    "Susanoo": "adult male Susanoo, wild black hair, plain earth-blue wrap",
    "Uke Mochi": "adult female Uke Mochi, long dark hair, plain earth-tone wrap",
    "Messenger deity": "adult messenger deity, long dark hair, plain undyed wrap",
}

_JAPANESE_MYTH_PERSON_PROMPT_RE = re.compile(
    r"\b(?:adult|person|human|man|woman|male|female|deity|god|goddess|kami|"
    r"figure|face|body|torso|villager|farmer|caretaker|storyteller|listener|scribe|he|him|his|she|her|standing|"
    r"kneeling|running|wading|washing|looking|panting|recoiling|gripping)\b",
    re.IGNORECASE,
)


def _japanese_myth_generic_role_subject(scene: str) -> str:
    text = str(scene or "")
    if re.search(
        r"\bstoryteller\s+centered\b.*\btwo\s+listeners\b",
        text,
        re.IGNORECASE,
    ):
        return (
            "exactly three adult East Asian villagers: one elderly adult male storyteller centered "
            "between exactly two adult listeners in plain unpatterned plant-fiber robes"
        )
    if re.search(
        r"\bstoryteller\s+at\s+left\b.*\blistener\s+at\s+right\b",
        text,
        re.IGNORECASE,
    ):
        return (
            "exactly two adult East Asian villagers: one elderly adult male storyteller at left "
            "and exactly one adult listener at right, both in plain unpatterned plant-fiber robes"
        )
    if re.search(r"\b(?:elder\s+storyteller|storyteller)\b", text, re.IGNORECASE):
        return (
            "exactly one elderly adult East Asian male storyteller, lined mature face, long plain "
            "black hair, bare forehead, plain unpatterned undyed plant-fiber tunic"
        )
    if re.search(r"\btwo\s+adult\s+caretakers\b", text, re.IGNORECASE):
        return (
            "exactly two adult East Asian sericulture caretakers in separate plain unpatterned "
            "plant-fiber work robes"
        )
    if re.search(r"\bcaretaker\b", text, re.IGNORECASE):
        return (
            "exactly one adult East Asian sericulture caretaker in a plain unpatterned "
            "plant-fiber work robe"
        )
    if re.search(r"\bNara-period\s+scribe\b", text, re.IGNORECASE):
        return (
            "exactly one adult East Asian Nara-period scribe in a plain historically grounded court robe"
        )
    if re.search(r"\bvillager\b", text, re.IGNORECASE):
        return (
            "exactly one adult East Asian agrarian villager in a plain unpatterned plant-fiber work robe"
        )
    if re.search(r"\bfarmer\b", text, re.IGNORECASE):
        return (
            "exactly one adult East Asian rice farmer in a plain unpatterned plant-fiber work robe"
        )
    return ""


def _is_japanese_creation_myth_context(*parts: str) -> bool:
    return bool(
        _JAPANESE_CREATION_MYTH_CONTEXT_RE.search(
            " ".join(str(part or "") for part in parts)
        )
    )


def _japanese_myth_named_identities(text: str) -> list[str]:
    names: list[str] = []
    source = str(text or "")
    for canonical, _role, aliases in _JAPANESE_MYTH_IDENTITIES:
        if any(_alias_in_text(source, alias) for alias in aliases):
            names.append(canonical)
    return names


def _japanese_myth_identity_subject(names: list[str]) -> str:
    ordered: list[tuple[str, str]] = []
    wanted = set(names)
    for canonical, role, _aliases in _JAPANESE_MYTH_IDENTITIES:
        if canonical in wanted:
            ordered.append((canonical, role))
    if not ordered:
        return ""
    descriptors = [
        _JAPANESE_MYTH_VISUAL_IDENTITY.get(canonical, f"adult {role} {canonical}")
        for canonical, role in ordered
    ]
    if len(descriptors) == 1:
        return f"exactly one {descriptors[0]}"
    if len(descriptors) == 2:
        pair = [_JAPANESE_MYTH_PAIR_IDENTITY[canonical] for canonical, _role in ordered]
        return f"exactly two adult Japanese deities: {pair[0]}; {pair[1]}"
    trio = [_JAPANESE_MYTH_PAIR_IDENTITY[canonical] for canonical, _role in ordered[:3]]
    return "exactly three adult Japanese deities: " + "; ".join(trio)


def _japanese_myth_visual_world_fields() -> dict[str, str]:
    return {
        "time_range": "Japanese mythic creation era",
        "place_scope": "primordial Japanese islands, the Yomi boundary, misogi riverbanks, and Takamagahara only as named by each scene",
        "culture_scope": "Kojiki and Nihon Shoki Japanese creation myth",
        "material_culture": (
            "rough stone, unpainted timber only when named, woven white and earth-tone cloth, "
            "plain brown sashes, water, clay, plant fiber, and aged bronze"
        ),
        "continuity_rule": (
            "Named Japanese deities keep consistent adult East Asian identity and archaic ritual clothing. "
            "No European, Christian, Greco-Roman, Chinese imperial, fantasy-RPG, Edo, medieval castle-town, "
            "or modern visual language; no tiled urban compounds, utility poles, wires, roads, cars, trucks, "
            "or machinery. A building appears only when the scene names one and then uses plain unpainted archaic timber."
        ),
    }


def _japanese_myth_location(text: str) -> str:
    source = str(text or "")
    if re.search(r"(?:黄泉|地下\s*世界|Yomi|underworld|dark\s+cave|生還|逃げ帰)", source, re.IGNORECASE):
        return "bare rocky boundary between Yomi underworld and the living world"
    if re.search(r"(?:禊|みそぎ|ミソギ|misogi|purif|river|water|汚れ|穢れ|洗)", source, re.IGNORECASE):
        return "shallow purification riverbank in primordial mythic Japan"
    if re.search(r"(?:高天原|天上\s*界|Takamagahara|heavenly\s+realm)", source, re.IGNORECASE):
        return "Takamagahara divine realm in Japanese creation myth"
    if re.search(r"(?:海|ocean|sea|coast|shore)", source, re.IGNORECASE):
        return "bare primordial shore of the Japanese islands"
    return "primordial natural landscape of mythic Japan"


def _uke_mochi_afterlife_scene_override(
    cut: dict[str, Any],
    script_context: str,
) -> tuple[list[str], str, str]:
    """Keep CH3 EP07 narration-led without replacing people with artifact grids."""
    if not re.search(
        r"죽은\s*여신의\s*시신에서\s*피어난\s*생명|死んだ\s*女神.*(?:命|生命)",
        script_context,
        re.IGNORECASE,
    ):
        return [], "", ""

    cut_number = _script_text_number(cut.get("cut_number"))
    narration = str(cut.get("narration") or "")
    person_scenes: dict[int, tuple[list[str], str, str]] = {
        3: (["Uke Mochi", "Tsukuyomi"], "Extreme hand-free opposing-profile two-shot of Uke Mochi at right and Tsukuyomi at left at the instant his cold anger turns her welcome into dread; both complete adult faces and loose black hair fill the frame, with both jawlines cropped before any neck, shoulder, arm or hand", "bare packed-earth court beside a primordial field"),
        4: (["Tsukuyomi"], "Extreme hand-free face-only close-up of Tsukuyomi looking downward with cold, rigid contempt after the killing; his complete mature face fills the frame and the lower edge ends at the jawline before any robe or limb", "bare packed-earth court beneath a cold night sky"),
        5: (["Tsukuyomi"], "Extreme hand-free face-only close-up of Tsukuyomi recoiling in disgust from the unseen food offering, with narrowed eyes, wrinkled nose and tense mouth; complete face and hair only", "bare packed-earth court beside a primordial field"),
        6: (["Amaterasu", "Tsukuyomi"], "Tight hand-free opposing-profile two-shot as Amaterasu rebukes Tsukuyomi and he averts his eyes; both adult faces dominate beneath separate warm-gold and cold-silver light", "open cloud-lit Takamagahara plain"),
        7: (["Amaterasu"], "Extreme hand-free face-only close-up of Amaterasu speaking with fierce moral anger about the value of nurturing life; complete face and plain black hair fill the frame", "open cloud-lit Takamagahara plain"),
        8: (["Amaterasu", "Tsukuyomi"], "Tight hand-free two-shot of Amaterasu turning away in final rejection while Tsukuyomi remains separated behind her under retreating silver light; faces and upper posture dominate", "open cloud-lit Takamagahara threshold"),
        10: (["Amaterasu"], "Extreme hand-free facial close-up of Amaterasu looking downward toward the unseen earth with knitted brows and urgent concern", "open high Takamagahara plain above the primordial land"),
        11: (["Uke Mochi"], "Extreme side-profile face-only close-up of Uke Mochi resting motionless with closed eyes, loose dark hair on pale earth and one plain shroud edge below the jaw; no exposed body", "bare earth beside a newly fertile primordial field"),
        12: (["Uke Mochi"], "Extreme side-profile face-only close-up of motionless Uke Mochi with closed eyes while the first tiny green shoot enters the distant background; face, hair and one shroud edge only", "bare earth beside a newly fertile primordial field"),
        14: (["Amaterasu", "Messenger deity"], "Hand-free head-and-shoulders two-shot as Amaterasu urgently dispatches Ame no Kumahito toward the earth; her speaking face and his attentive adult face dominate, both hands outside the frame", "open high Takamagahara plain"),
        15: (["Amaterasu", "Messenger deity"], "Tight hand-free two-shot as Amaterasu gives the final urgent command and Ame no Kumahito answers with a grave nod; complete adult faces and robe collars only", "open high Takamagahara plain"),
        16: (["Messenger deity"], "Three-quarter rear view of Ame no Kumahito descending alone along a broad natural cloud gap toward the real green earth below; one coherent clothed body with both arms held close beneath an undyed robe", "sky above the primordial land"),
        17: (["Messenger deity"], "Three-quarter view of exactly one adult messenger man arriving beside one fully covered earth-tone shroud and stopping before one dark ground stain; his coherent clothed body and shocked face dominate", "bare earth beside a primordial field"),
        18: ([], "Landscape-only ground-level view of one fully covered earth-tone shroud beside a dark rain-soaked patch of bare soil, with the first irregular green grain shoots emerging farther back under pale dawn light; the non-graphic aftermath is exactly what the arriving messenger feared to see", "bare earth beside a primordial field"),
        19: (["Messenger deity"], "Extreme hand-free face-only close-up of Ame no Kumahito as fear changes into astonishment while warm dawn light and soft green blur rise from below frame", "newly fertile primordial field"),
        21: (["Uke Mochi", "Tsukuyomi"], "Extreme opposing-profile face-only recap of Uke Mochi's last calm expression and Tsukuyomi's cold anger beneath warm and silver light; both complete adult faces fill the frame", "bare packed-earth court beside a primordial field"),
        22: (["Amaterasu"], "Extreme hand-free facial close-up of Amaterasu looking downward in grief toward Uke Mochi's unseen body on earth", "open high Takamagahara plain"),
        23: (["Messenger deity"], "Tight hand-free head-and-shoulders view of Ame no Kumahito beginning the descent with a grave focused expression and wind moving his plain undyed robe collar", "sky above the primordial land"),
        24: (["Messenger deity"], "Extreme hand-free face-only close-up of Ame no Kumahito staring down at the miracle with widened eyes and an open mouth", "newly fertile primordial field"),
        25: (["Uke Mochi"], "Non-graphic side-profile facial close-up of motionless Uke Mochi with closed eyes while irregular young grain shoots rise beyond one plain shroud edge; face and natural growth dominate", "newly fertile primordial field"),
        32: (["Tsukuyomi"], "Extreme hand-free face-only close-up of Tsukuyomi turning away while cold silver light recedes from a living green field behind him; complete face and hair only", "newly fertile primordial field beneath fading moonlight"),
        34: ([], "Landscape-only low sweeping view across the dramatic transformation itself: young rice, millet and bean shoots rise at uneven natural distances through wet dark soil as warm dawn light breaks across the formerly barren field", "newly fertile primordial field"),
        36: (["Messenger deity"], "Three-quarter view of Ame no Kumahito kneeling beside a low woven harvest basket and gathering loose rice, millet and cocoons from the living field; one coherent clothed adult body, attached arms and grounded knees", "newly fertile primordial field"),
        37: (["Messenger deity"], "Three-quarter rear view of Ame no Kumahito ascending through a broad cloud gap with one woven harvest basket secured against his torso; one coherent clothed adult body", "sky between earth and Takamagahara"),
        38: (["Amaterasu", "Messenger deity"], "Waist-up two-shot as Ame no Kumahito presents the recovered seed basket and Amaterasu's grief changes to quiet joy; both adult faces and complete attached arms remain visible, hands small and secondary", "open high Takamagahara field"),
        39: (["Amaterasu"], "Three-quarter view of Amaterasu standing beside the recovered seeds and declaring them essential for human life; her coherent clothed body and speaking face dominate, hands small and secondary", "open high Takamagahara field"),
        40: (["Amaterasu"], "Three-quarter view of Amaterasu preparing to cultivate the recovered seed beside a real flooded paddy; one coherent clothed adult body, sleeves intact, hands low and secondary", "newly prepared Takamagahara paddy"),
        44: (["Amaterasu"], "Three-quarter view of Amaterasu planting young rice shoots in shallow paddy water, plain ivory robe gathered safely above the mud; one coherent adult body with attached arms and grounded legs", "flooded Takamagahara rice paddy"),
        46: (["Amaterasu"], "Tight hand-free facial close-up of Amaterasu looking across the living rice field with solemn reverence, showing agriculture as a life-giving rite rather than low labor", "flooded Takamagahara rice paddy"),
        47: ([], "Landscape-only present-day Imperial Palace rice paddy with clear water, living green rice, one low modern metal irrigation outlet and one dark rubber hose at the field edge, with a softened contemporary Tokyo office skyline beyond dense palace trees", "present-day Imperial Palace rice paddy"),
        48: ([], "Landscape-only present-day Imperial Palace rice paddy during the spring planting season, with newly transplanted green seedlings rooted in shallow water, clean modern mud ridges and one low metal irrigation outlet beside dense palace trees", "present-day Imperial Palace rice paddy"),
        49: ([], "Landscape-only present-day Imperial Palace rice paddy in early autumn with mature golden rice, clean modern irrigation channels and a distant contemporary Tokyo office skyline softened behind palace trees", "present-day Imperial Palace rice paddy"),
        50: ([], "Landscape-only wide present-day Imperial Palace rice paddy where living rice, clean modern irrigation hardware and a distant contemporary Tokyo skyline visibly connect the ancient cultivation story to a current state ceremony", "present-day Imperial Palace rice paddy"),
        51: ([], "Landscape-only continuous low view across a newly flooded Takamagahara rice paddy where clear shallow water fills the foreground and irregular young green rice shoots rise through bright natural reflections toward a living field beyond; water and growing plants fill the frame and show the recovered life beginning cultivation", "newly flooded Takamagahara rice paddy"),
        52: (["Amaterasu"], "Three-quarter view of Amaterasu beginning to cultivate millet, beans and rice in separate natural soil beds; one coherent clothed adult body and focused expression", "open Takamagahara cultivation field"),
        54: (["Amaterasu"], "EP07 rice-planting hands, exactly two natural adult female hands plant one young rice shoot in wet mud, extreme close-up with raw T-shaped pullover sleeve ends", "flooded Takamagahara rice paddy"),
        56: (["Amaterasu"], "Tight hand-free facial close-up of Amaterasu watching young rice shoots stand upright in water, her calm expression carrying the sacred meaning of giving life", "flooded Takamagahara rice paddy"),
        57: ([], "Landscape-only present-day Shinto harvest-festival grounds beside one real mature rice paddy, with one white modern pop-up canopy, one clean metal safety rail and distant rectangular glass-and-steel office towers establishing current Japan", "present-day Shinto shrine rice paddy"),
        58: ([], "Landscape-only present-day Imperial Palace rice paddy in autumn, where newly cut rice sheaves rest naturally along one clean concrete irrigation edge beside one dark rubber hose and a distant rectangular Tokyo office skyline", "present-day Imperial Palace rice paddy"),
        59: ([], "Landscape-only present-day central Tokyo ceremonial rice paddy after the annual harvest, with one clean metal irrigation outlet, dense green trees and one distant rectangular glass office tower under warm dusk light", "present-day central Tokyo ceremonial rice paddy"),
        60: (["Amaterasu"], "Tight hand-free head-and-shoulders view of Amaterasu before a real mature rice field, linking the new-rice rite back to her cultivation myth", "mature Takamagahara rice field"),
        61: ([], "Landscape-only ground-level fertile field where irregular new green grain shoots spread through wet dark soil toward one real winding freshwater river under warm dawn light", "newly fertile primordial river field"),
        62: ([], "Landscape-only wide continuous primordial cultivation field where living rice, millet and bean plants grow in irregular connected patches beside one real winding irrigation channel under warm sunlight", "newly fertile primordial cultivation field"),
        63: ([], "Landscape-only broad fertile river field filled edge to edge with naturally mixed mature rice, millet, wheat and bean plants under warm dawn light", "newly fertile primordial river field"),
        64: ([], "Landscape-only ground-level real primordial field where one fallen dry stalk lies naturally in dark soil beside one newly germinated green shoot while mature grain grows farther back under dawn light", "living primordial field"),
        65: ([], "Landscape-only extreme macro of exactly one natural rice grain germinating in real dark soil, with one pale root descending and one fresh green shoot rising through moist earth", "living fertile field soil"),
        66: ([], "Landscape-only non-graphic fertile field where exactly one fully covered earth-tone shroud rests naturally on wet dark soil while new rice, millet and bean shoots grow at irregular distances around its outer edge beside one winding freshwater channel", "newly fertile primordial cultivation field"),
        67: ([], "Landscape-only broad fertile river field filled edge to edge with naturally mixed rice, millet, wheat and bean plants under warm dawn light", "newly fertile primordial river field"),
        68: ([], "Landscape-only continuous tropical food garden filled with living taro, yam and other tuber plants rooted naturally in humid dark soil beneath dense forest light", "humid tropical food garden"),
        69: (["Hainuwele"], "Extreme hand-free face-only close-up of one mature young Indonesian woman named Hainuwele among softly blurred living taro and yam leaves; her complete natural face and dark hair fill the frame, with the lower crop ending at the jaw before any clothing or limb appears", "Indonesian tropical food garden"),
        70: ([], "Landscape-only Indonesian tropical garden floor with one irregular patch of newly disturbed dark soil surrounded by living taro and yam plants beneath storm-dark humid forest light", "Indonesian tropical food garden"),
        71: ([], "Landscape-only close tropical garden where many living taro and yam shoots emerge naturally from one continuous patch of humid dark soil beneath soft forest light", "Indonesian tropical food garden"),
        72: ([], "Landscape-only broad Southeast Asian and Oceanian tropical food garden where living taro, yam and breadfruit plants grow together in one humid forest clearing", "humid tropical food garden"),
        73: ([], "Landscape-only broad warm-climate food garden where living yam, cassava, maize and bean plants grow together naturally in one continuous dark-soil field", "warm-climate subsistence food garden"),
        74: ([], "Landscape-only uninhabited vegetation-only ground-level field where plain brown leaf litter settles naturally into moist dark soil around irregular fresh green grain sprouts under warm dawn light", "living fertile field soil"),
        75: ([], "Landscape-only uninhabited vegetation-only ground-level field where dark decomposed plant matter mixes naturally through rain-wet soil and separate newly opened green sprouts emerge across the continuous earth under fresh rain light", "living fertile field soil"),
        76: ([], "Landscape-only oblique wide view across one continuous real cultivation field where freshly turned dark soil in the near foreground leads naturally to irregular young green shoots in the middle distance and mature golden grain farther back under dawn light", "living fertile field"),
        77: ([], "Landscape-only uninhabited vegetation-only wide fertile river field filled with many separate living grain shoots emerging naturally through one continuous dark-soil field toward fresh water under pale dawn light", "living fertile river field"),
        78: ([], "EP07 present-day family meal, tight hand-free head-and-shoulders three-shot of exactly three visibly distinct adult Japanese family members from three age groups, one older adult, one middle-aged adult and one young adult, bowing before one simple meal in a bright contemporary apartment dining room; their separate faces and shared gravity dominate", "plain bright present-day Japanese apartment dining room"),
        79: (["Tsukuyomi"], "Extreme hand-free face-only close-up of Tsukuyomi's rigid expression after the killing, his cold eyes reflecting the violence contained in taking food from life", "bare packed-earth court beneath cold silver light"),
        80: ([], "EP07 present-day family meal, tight hand-free head-and-shoulders three-shot of exactly three visibly distinct adult Japanese diners from three age groups, one older adult, one middle-aged adult and one young adult, pausing before a simple meal in a bright contemporary apartment; conflicting gratitude and necessity show only in their separate faces", "plain bright present-day Japanese apartment dining room"),
        82: ([], "EP07 present-day family meal, tight hand-free head-and-shoulders three-shot of exactly three visibly distinct adult Japanese family members from three age groups, one older adult, one middle-aged adult and one young adult, bowing before a simple meal in a bright contemporary apartment; gratitude shows in their separate faces", "plain bright present-day Japanese apartment dining room"),
        83: ([], "EP07 present-day family meal, tight hand-free head-and-shoulders three-shot of exactly three visibly distinct adult Japanese diners from three age groups, one older adult, one middle-aged adult and one young adult, bowing together before eating in a bright contemporary apartment; their natural slightly parted lips and respectful faces convey itadakimasu", "plain bright present-day Japanese apartment dining room"),
        84: ([], "Landscape-only EP07 present-day empty meal room, steep overhead interior close view where exactly one continuous natural-wood dining tabletop fills the entire frame and exactly one simple place setting rests at center, consisting of one rice bowl, one soup bowl and one pair of chopsticks in daylight", "plain bright present-day Japanese apartment dining room"),
        85: ([], "EP07 present-day family meal, tight hand-free head-and-shoulders three-shot of exactly three visibly distinct adult Japanese diners from three age groups, one older adult, one middle-aged adult and one young adult, sharing a quiet moment before one meal in a bright contemporary apartment; their separate natural expressions carry the ancient spirit into daily life", "plain bright present-day Japanese apartment dining room"),
        86: (["Messenger deity"], "Extreme hand-free face-only close-up of Ame no Kumahito looking from the unseen grain below toward pale silk cocoons, new astonishment visible in his eyes", "newly fertile primordial field"),
        87: ([], "Landscape-only EP07 three-silkworm macro, extreme macro of exactly three separate large living white silkworms, one silkworm centered on each of exactly three separate fresh green mulberry leaves under soft daylight", "open mulberry garden in Takamagahara"),
        88: (["Amaterasu"], "Tight hand-free head-and-shoulders view of Amaterasu watching living silkworms feed on mulberry leaves below frame with careful attention", "open mulberry garden in Takamagahara"),
        89: (["Amaterasu"], "Three-quarter view of Amaterasu placing fresh mulberry leaves onto one low silkworm tray; one coherent clothed adult body with attached arms, grounded legs and hands small and secondary", "open mulberry garden in Takamagahara"),
        90: (["Amaterasu"], "EP07 silk-filament facial action, exactly one fine white silk filament visibly connects exactly one pale cocoon resting alone at the lower frame edge directly to the slightly parted lips of Amaterasu; her single complete mature side-profile face and dark hair fill the frame, with no hand, arm, shoulder, torso or garment visible", "soft leaf-green blur in Takamagahara"),
        91: ([], "EP07 three-silkworm macro, Landscape-only wide mulberry-garden view where exactly three small living white silkworms feed separately, one on each of exactly three foreground mulberry leaves across the lower third, while one plain open-sided unpainted weaving shelter occupies the upper center under soft daylight; every leaf and shelter surface is blank with no letters or numbers", "mulberry garden beside a plain Takamagahara weaving shelter"),
        92: (["Amaterasu"], "Three-quarter view of Amaterasu operating one plain vertical loom inside one open-sided unpainted weaving shelter as the first continuous white silk cloth takes shape; one coherent clothed adult body, complete attached arms and grounded legs", "plain unpainted Takamagahara weaving shelter"),
        93: (["Older weaver", "Middle-aged weaver", "Young adult weaver"], "Exactly three visibly different adult East Asian women from three age groups operate three separate plain vertical looms inside one unpainted open-sided weaving hall: an elderly silver-haired woman at the left loom, a middle-aged dark-haired woman at the center loom and a young adult dark-haired woman at the right loom; each wears one raw plant-fiber T-shaped pullover and one broad ankle-length straight skirt, and each complete coherent body remains separated with attached arms and grounded feet", "plain unpainted Takamagahara weaving hall"),
        94: ([], "Landscape-only EP07 finished-garment shelter, close interior view inside one open-sided unpainted weaving shelter where exactly one finished plain ivory short-sleeve crewneck shirt with a simple T-shirt silhouette and rough handwoven plant-fiber texture physically hangs from the upper crossbar of exactly one vertical loom, with taut loom threads visibly continuing above it; the shirt has one closed circular neck hole and one perfectly blank single-piece front surface with no diagonal line, overlap, lapel, cord, fastener, sash or belt; dense living mulberry foliage fills every open side and no person, animal, silkworm, cocoon, distant horizon, water or coast appears", "inland weaving shelter enclosed by dense mulberry foliage"),
        96: ([], "EP07 present-day sericulture figure, exactly one present-day adult Japanese woman in plain light-grey collarless work clothes carefully tends one living silkworm tray inside a clean Imperial Palace sericulture room; one coherent clothed body, attached arms and hands small and secondary", "present-day Imperial Palace sericulture room"),
        97: ([], "EP07 present-day sericulture figure, exactly one present-day adult Japanese woman in plain light-grey collarless work clothes checks fresh mulberry leaves and pale cocoons arranged together in exactly one low rectangular silkworm tray inside a clean Imperial Palace sericulture room; one coherent clothed body and complete attached arms; every tray surface is blank with no letters or numbers", "present-day Imperial Palace sericulture room"),
        98: ([], "EP07 present-day silk ceremony figure, exactly one present-day adult Japanese woman in a plain charcoal contemporary business suit presents one folded white silk cloth inside a clean neutral ceremonial room; her coherent clothed body and respectful expression dominate while the cloth stays secondary", "plain present-day ceremonial room in Japan"),
        99: ([], "EP07 present-day sericulture figure, exactly one present-day adult Japanese woman in plain light-grey collarless work clothes tends one living silkworm tray beside one simple vertical loom inside a clean Imperial Palace sericulture room, showing the unbroken practice through one coherent working body", "present-day Imperial Palace sericulture room"),
        100: ([], "Landscape-only EP07 rice-mulberry legacy landscape, one continuous living field where mature rice plants and orderly mulberry rows meet beside one plain open-sided unpainted sericulture shelter under warm daylight, connecting the episode's agriculture and silk legacy in one real place; no exposed silkworm, cocoon, sea, coast, text, panel or arranged artifact appears", "inland mulberry garden beside a fertile rice field"),
        101: ([], "Landscape-only EP07 sacred-weaving-hall landscape, wide interior of exactly one newly completed open-sided sacred weaving hall made from plain unpainted posts, containing exactly three separated vertical looms with clean ivory warp threads; dense inland green foliage fills every open side and every background edge above continuous bare earth, with no person, animal, silkworm, cocoon, water, sea, coast, distant horizon, text, panel or arranged artifact display", "newly completed inland Takamagahara weaving hall surrounded by dense foliage"),
        102: (["Older heavenly weaver", "Middle-aged heavenly weaver", "Young heavenly weaver"], "Exactly three visibly different adult East Asian women from three age groups work at three separate vertical looms inside one continuous unpainted hall: an elderly silver-haired woman at left, a middle-aged dark-haired woman at center and a young adult dark-haired woman at right; each wears one raw plant-fiber T-shaped pullover and one broad ankle-length straight skirt, and each complete body remains separated with attached arms, natural hands and grounded feet", "plain unpainted Takamagahara weaving hall"),
        103: (["Heavenly weaver"], "Exactly one mature adult East Asian woman carefully operates exactly one vertical loom inside the unpainted sacred weaving hall while one continuous ivory cloth visibly forms between the taut warp threads; her one coherent body has two attached arms and two small natural working hands, and she wears one raw plant-fiber T-shaped pullover with one broad ankle-length straight skirt", "plain unpainted Takamagahara weaving hall"),
        104: ([], "Landscape-only EP07 rice-mulberry legacy landscape, one continuous prosperous Takamagahara field where mature golden rice plants and orderly living mulberry rows meet beside exactly one plain open-sided unpainted weaving hall under warm sunlight; no person, animal, exposed silkworm, cocoon, sea, coast, text, panel or arranged artifact appears", "inland rice and mulberry fields beside the Takamagahara weaving hall"),
        105: ([], "Landscape-only wide fertile field filled edge to edge with mature golden rice heads bending naturally beneath strong warm sunlight and a clear open sky; no person, building, sea, coast, text, panel or arranged artifact appears", "fertile inland Takamagahara rice field under sunlight"),
        106: ([], "Landscape-only wide fertile field where mature golden rice and orderly green cultivation rows meet beside one narrow natural irrigation channel beneath calm warm sunlight; one continuous dense forest wall fills the entire background, with no person, animal, building, house, roof, pole, wire, road, sea, coast, text, panel or arranged artifact", "peaceful inland Takamagahara cultivation fields"),
        107: (["Amaterasu"], "Tight hand-free facial close-up of Amaterasu looking over the prosperous rice and weaving landscape with calm protective authority", "open Takamagahara field"),
        108: ([], "Landscape-only wide inland Takamagahara field at the moment calm sunlight begins to dim as one bank of dark storm clouds advances across the sky and wind bends the golden rice in one direction; dense low inland hills close the background with no person, building, water, sea, coast, text, panel or arranged artifact", "inland Takamagahara rice field before an approaching storm"),
        109: (["Susanoo"], "Tight hand-free head-and-shoulders portrait of Susanoo as one East Asian man in his thirties with a smooth beardless jaw and thick wild black hair fully visible from crown to both shoulder-length ends; dangerous resolve forms in his eyes beneath a darkening sky", "storm-dark bare primordial shore"),
        110: (["Susanoo"], "Three-quarter rear view of Susanoo with thick shoulder-length black hair covering his upper back, walking barefoot from the rough sea toward the cloud path in one coarse earth-blue T-shaped plant-fiber pullover and loose ankle trousers; his face is not visible", "bare primordial shore beneath a storm"),
        111: (["Susanoo"], "Tight hand-free head-and-shoulders portrait of exactly one Susanoo as one East Asian man in his thirties with a smooth beardless jaw and thick wild black hair visible from crown to both shoulder-length ends, looking alone toward the high cloud plain before his final visit; no second person appears", "bare rocky ridge above the primordial sea"),
        112: (["Susanoo"], "Tight hand-free head-and-shoulders portrait of exactly one Susanoo as one East Asian man in his thirties with a smooth beardless jaw and thick wild black hair visible from crown to both shoulder-length ends, deciding alone to make a final farewell as grief and resolve meet in his eyes; no second person appears", "bare rocky ridge below Takamagahara"),
        113: (["Susanoo"], "Dynamic three-quarter rear view of Susanoo with thick shoulder-length black hair striding barefoot up a bare rocky ridge in one coarse earth-blue T-shaped plant-fiber pullover and loose ankle trousers; one coherent adult body has attached arms, grounded legs and natural feet", "bare rocky ascent toward Takamagahara"),
        114: ([], "Landscape-only wide bare mountain ridge as a single violent storm front tears across it, bending grass flat in one direction and driving loose natural stones through the air; no person, building, text, panel or arranged artifact appears", "bare mountain ascent toward Takamagahara beneath a storm"),
        115: ([], "Landscape-only wide chain of bare mountains visibly trembling as small natural rockfalls descend several slopes and fresh irregular cracks open across the foreground earth; no person, building, sea, text, panel or arranged artifact appears", "bare mountain chain beneath a storm"),
        116: ([], "Landscape-only wide primordial sea churning into steep opposing waves beneath one vast spiral of dense black storm clouds, while an empty rocky shore anchors the foreground; no person, ship, building, text, panel or arranged artifact appears", "primordial sea and empty rocky shore beneath a black storm"),
        117: ([], "Landscape-only wide barren Takamagahara ridge struck by the terrifying roar of the approaching storm: dense black clouds crush the sky, violent wind drives dust and small natural stones in one direction, and one jagged ground crack crosses the foreground; no person, building, structure, gate, text, panel or arranged artifact appears", "barren Takamagahara ridge beneath a violent storm"),
        118: (["Elderly female deity", "Middle-aged male deity", "Young adult male deity"], "Tight hand-free head-and-shoulders three-shot of exactly three visibly different adult East Asian deities from three age groups, all recoiling open-mouthed and wide-eyed from the approaching storm with hunched shoulders: an elderly woman at left, a middle-aged man at center and a young adult man at right, each in one raw T-shaped pullover", "open Takamagahara plain beneath a storm"),
        119: (["Amaterasu"], "Extreme hand-free face-only close-up of Amaterasu detecting the violent approach, alarm sharpening into suspicion in her eyes", "open Takamagahara plain beneath a storm"),
        120: (["Amaterasu"], "Extreme hand-free face-only close-up of Amaterasu speaking the fear that Susanoo has come to seize her realm, jaw set and eyes fixed toward the storm", "open Takamagahara plain beneath a storm"),
        121: ([], "Landscape-only EP07 rice-mulberry legacy landscape, peaceful Takamagahara: golden rice at left, green rows at right, exactly one centered open-front unpainted weaving hall between them with exactly one upright loom visible inside, and dense forest filling every horizon pixel; the hall is the only roof or structure", "peaceful inland Takamagahara fields and weaving hall"),
        122: ([], "Landscape-only wide inland Takamagahara field as a dense black storm front abruptly covers the formerly bright sky, casting one advancing shadow across golden rice while violent wind bends every stalk in one direction; no person, building, water, sea, coast, text, panel or arranged artifact appears", "inland Takamagahara rice field beneath an advancing black storm"),
        123: (["Susanoo"], "Three-quarter rear view of Susanoo emerging alone from the storm, thick unbound black hair extending below both shoulders onto his upper back; one earth-blue short-sleeve crewneck T-shirt-shaped plant-fiber pullover has a flat back panel above loose ankle trousers and bare feet", "bare ridge at the edge of Takamagahara"),
        124: (["Susanoo"], "EP07 foot-impact crop: clean five-toed foot on dry brown rock; black jagged cracks radiate through ground from under heel; foot skin smooth and unmarked; no water", "bare rocky ridge at the edge of Takamagahara"),
        125: ([], "Landscape-only EP07 completely-dry-river landscape, wide landlocked mountain valley under black storm; one dry cracked bed, a serpentine sunken band of matte brown clay, fills the former river channel from foreground to distance; the full channel is solid opaque dry earth, never liquid or blue", "landlocked mountain valley at the edge of Takamagahara"),
        126: (["Amaterasu"], "Extreme hand-free face-only close-up of Amaterasu becoming intensely vigilant as the storm reaches her realm", "open Takamagahara plain beneath a storm"),
        127: (["Amaterasu"], "Tight hand-free head-and-shoulders view of Amaterasu convinced that Susanoo intends conquest, her stern gaze locked toward him outside frame", "open Takamagahara plain beneath a storm"),
        128: (["Amaterasu"], "Three-quarter view of Amaterasu shifting from peaceful ruler to battle readiness in one coarse ivory T-shaped plant-fiber pullover and one broad ankle-length straight skirt, with one long wooden bow visible at her side; one coherent adult body has attached arms and grounded feet", "open Takamagahara plain beneath a storm"),
        129: (["Amaterasu"], "Tight head-and-shoulders view of Amaterasu tying her long black hair into a firm archaic battle knot, both attached arms visible and hands small above shoulder level", "open Takamagahara plain beneath a storm"),
        130: (["Amaterasu"], "EP07 magatama armor crop: two green comma-bead strands both visible, one per upper arm; one green comma-bead necklace; every strand has many separate beads; ivory T-shirt", "open Takamagahara plain beneath a storm"),
        131: (["Amaterasu"], "EP07 dry-takamagahara figure, Amaterasu holds one large bow lowered at her right side; dense reed-arrow bundle on back; ivory T-shirt, long skirt, attached arms and hands", "dry inland Takamagahara plateau beneath a storm"),
        132: (["Amaterasu"], "EP07 dry-takamagahara figure, full stance Amaterasu plants two bare feet wide; unbroken dry brown earth continues from her feet to low hills; long skirt, attached legs, lowered arms and hands", "dry inland Takamagahara plateau beneath a storm"),
        133: ([], "Landscape-only EP07 dry-takamagahara landscape, unbroken dry brown earth and grass continue from foreground to low hills under black storm; one hard gold sun shaft strikes the ridge", "dry inland Takamagahara plateau beneath a storm"),
        134: (["Amaterasu"], "EP07 dry-takamagahara figure, Amaterasu becomes armed defender; unbroken dry brown earth reaches low hills; bow lowered, ivory T-shirt, long skirt, both arms lowered and attached", "dry inland Takamagahara plateau beneath a storm"),
        135: (["Amaterasu", "Susanoo"], "EP07 strict-profile faces, Extreme inward-facing two-profile confrontation of Amaterasu and Susanoo; left is adult woman Amaterasu with feminine face and center-parted hair; right is adult man Susanoo in his thirties with clean-shaven upper lip, chin and jaw", "windswept Takamagahara ridge"),
        136: ([], "Landscape-only EP07 covered-mound field, young rice, millet and bean shoots surround one low oval mound fully sealed beneath one continuous plain earth-brown woven cover; smooth closed cover, soil and plants only", "newly fertile primordial field after Uke Mochi's death"),
        137: ([], "Landscape-only EP07 covered-mound field, close ground view: irregular living grain shoots emerge from dark soil beside the edge of one continuous earth-brown woven cover lying smoothly over one low oval mound", "newly fertile primordial field after Uke Mochi's death"),
        138: ([], "Landscape-only one continuous soil-and-field view where one fallen dry stalk returns to dark earth beside one germinating seed, one young green shoot and mature golden rice under dawn light; no diagram, panel, text or artifact display", "living primordial field showing one natural life cycle"),
        139: ([], "Landscape-only present-day Imperial Palace ceremonial rice paddy with living rice, wet mud ridges and exactly one small plain unpainted harvest pavilion under clear daylight; no person, palace facade, sign, text, panel or artifact display", "present-day Imperial Palace ceremonial rice paddy"),
        140: ([], "Landscape-only EP07 present-day living-culture landscape, flat two-dimensional mature dark manhwa ink-and-wash illustration of one Japanese working plot: mature rice paddy at left, mulberry rows at right, exactly one small white flat-roof sericulture workroom between them, dense tree wall behind", "present-day Japanese rice and sericulture working grounds"),
        141: ([], "Landscape-only flat two-dimensional mature dark manhwa ink-and-wash illustration of one living primordial rice cultivation field at twilight where warm gold and cool blue natural light meet across the grain; wet dark soil and low grassy hills close the inland horizon; no sea, coast, person, sign, writing, symbol, interface, arranged object or artifact display", "open inland primordial rice cultivation field at twilight"),
        142: ([], "EP07 present-day creator group, flat 2D ink manhwa chest portrait, exactly four Japanese adults left-to-right: woman, man, woman, man; modern dark hair; plain modern crewneck shirts; attentively reading comments below frame; hands and screens below frame", "plain warm neutral present-day studio"),
        143: ([], "EP07 present-day creator group, flat 2D ink manhwa chest portrait, exactly four Japanese adults left-to-right: woman, man, woman, man; modern dark hair; plain modern crewneck shirts; smiling while reading comments below frame; hands and screens below frame", "plain warm neutral present-day studio"),
        144: ([], "EP07 present-day creator group, flat 2D ink manhwa chest portrait, exactly four Japanese adults left-to-right: woman, man, woman, man; modern dark hair; plain modern crewneck shirts; warm grateful direct eye contact; hands, symbols, screens and text below frame", "plain warm neutral present-day studio"),
        145: ([], "EP07 present-day creator group, flat 2D ink manhwa chest portrait, exactly four Japanese adults left-to-right: woman, man, woman, man; modern dark hair; plain modern crewneck shirts; quietly energized behind one blank light-wood desk; hands and equipment below frame", "plain warm neutral present-day studio"),
        146: (["Amaterasu", "Susanoo"], "EP07 strict-profile faces, extreme inward-facing two-profile confrontation before the oath; left is adult woman Amaterasu with feminine face and center-parted hair; right is adult man Susanoo in his thirties with clean-shaven upper lip, chin and jaw; opposing resolve fills the frame", "windswept Takamagahara ridge"),
        147: (["Susanoo"], "EP07 eyes-only crop, extreme macro of exactly one worried right eye shows adult Susanoo insisting he has no evil intent; eyebrow, eyelids, iris and temple fill frame; nose, mouth, upper lip, cheeks, chin and jaw fully outside frame", "windswept Takamagahara ridge"),
        148: (["Amaterasu", "Susanoo"], "EP07 attire topology, EP07 dry-takamagahara figure, exactly two full bodies: left adult woman Amaterasu in long straight skirt; right adult man Susanoo in loose ankle trousers; both wear T-shirt-shaped plant-fiber pullovers and solemnly agree to prove innocence by oath", "dry inland Takamagahara ridge"),
        149: ([], "Object-only EP07 oath-items macro, exactly two narration-critical objects lie separated on dry brown earth after the chewing rite: one short flat irregular dull-bronze shard at left with one tooth-shaped notch and no handle; one small green crescent-comma ornament stone at right with one round hole near its blunt end and one tapered curved tail; no person, blood, extra object, array or display", "dry inland Takamagahara ridge"),
        150: ([], "Landscape-only EP07 dry-takamagahara landscape, one unbroken dry brown Takamagahara ridge in the tense instant before the coming oath: natural gold sunlight advances from the left and cold blue storm light advances from the right, meeting across one narrow strip of bare ground at center; no water, sea or coast", "dry inland Takamagahara ridge"),
    }
    if cut_number in person_scenes:
        names, scene, location = person_scenes[cut_number]
        if cut_number in {90, 109, 111, 112, 135, 146, 147, 148, 149}:
            return names, scene, location
        if names:
            if cut_number != 17 and re.search(
                r"\b(?:face-only|facial\s+close-up|opposing-profile\s+two-shot|"
                r"faces?\s+(?:and\s+upper\s+posture\s+)?dominate|complete\s+adult\s+faces)\b",
                scene,
                re.IGNORECASE,
            ):
                face_reactions = {
                    3: "Uke Mochi's dread opposed by Tsukuyomi's cold anger at the killing",
                    4: "Tsukuyomi's cold rigid contempt after the killing",
                    5: "Tsukuyomi recoiling in disgust from the unseen offering",
                    6: "Amaterasu's fierce rebuke opposed by Tsukuyomi averting his eyes",
                    7: "Amaterasu's fierce moral anger about the value of nurturing life",
                    8: "Amaterasu's final rejection opposed by Tsukuyomi's stunned isolation",
                    10: "Amaterasu's urgent concern for the slain food deity below",
                    11: "motionless Uke Mochi with closed eyes after the killing",
                    12: "motionless Uke Mochi with closed eyes as the first life begins behind her",
                    14: "Amaterasu's urgent command opposed by the messenger's grave attention",
                    15: "Amaterasu's final command opposed by the messenger's grave nod",
                    69: "Hainuwele's calm living presence as the Indonesian girl named by the narration",
                }
                reaction = face_reactions.get(cut_number, "the narration-matched emotional reaction")
                if len(names) == 1:
                    scene = (
                        f"EP07 face-crop only, extreme facial-detail crop of {names[0]} showing {reaction}, "
                        "the face scaled taller than the full frame with forehead and chin beyond the image edges, "
                        "visible pixels limited to eyes, nose, cheeks, mouth, ears and natural hair"
                    )
                else:
                    scene = (
                        f"EP07 face-crop only, extreme paired facial-detail crop of {names[0]} and {names[1]} "
                        f"showing {reaction}, each face scaled taller than the full frame with foreheads and chins "
                        "beyond the image edges, visible pixels limited to eyes, noses, cheeks, mouths, ears and natural hair"
                    )
            else:
                scene = re.sub(
                    r"\b(?:plain\s+)?(?:archaic\s+)?(?:ivory\s+|undyed\s+|earth-tone\s+)?(?:robe|wrap)\b",
                    "plant-fiber pullover shirt",
                    scene,
                    flags=re.IGNORECASE,
                )
                visible_count = {
                    1: "exactly one visible adult",
                    2: "exactly two visible adults",
                    3: "exactly three visible adults",
                }.get(len(names), "visible adults")
                scene = f"EP07 attire topology, {visible_count}, " + scene
        return names, scene, location

    if re.search(r"コメント|応援|高評価|登録|どう\s*感じ|今回", narration, re.IGNORECASE):
        return [], "Landscape-only calm primordial rice field at twilight where warm gold and cool blue natural light meet across living grain; no person, sign, writing, symbol, interface, token, arranged object or artifact display", "open primordial rice field at twilight"
    if cut_number >= 108 or re.search(r"嵐|暴風|地震|山々|海\s*の\s*水|黒い\s*雲", narration, re.IGNORECASE):
        return [], "Landscape-only continuous storm across one bare mountain ridge, one open earth plain and the real sea beneath layered dark clouds; natural wind, rain and waves dominate with no person, building, symbol or arranged object", "primordial coast and mountain ridge beneath a storm"
    if re.search(r"現代|天皇|皇后|皇居|神社|新嘗祭", narration, re.IGNORECASE):
        if re.search(r"蚕|絹|養蚕|糸", narration, re.IGNORECASE):
            return [], "Landscape-only present-day Imperial Palace mulberry garden beside one clean sericulture building, living mulberry leaves moving in natural daylight; no portrait, costume display, map, timeline or artifact row", "present-day Imperial Palace mulberry garden"
        return [], "Landscape-only present-day Imperial Palace rice paddy with real water, mud ridges and living rice at the narrated season; no portrait, palace facade, shrine icon, map, timeline or arranged objects", "present-day Imperial Palace rice paddy"
    if re.search(r"ハイヌウェレ|インドネシア|東南\s*アジア|オセアニア|南米|アフリカ|先住民|世界中", narration, re.IGNORECASE):
        return [], "Landscape-only continuous tropical food garden with living taro, yam and other tuber plants rooted naturally in dark soil beneath humid forest light; no person, costume, map, island token, carving, treasure pile or writing", "tropical crop garden associated with Hainuwele-type myths"
    if re.search(r"蚕|繭|絹|養蚕|織物|糸|衣服|機屋", narration, re.IGNORECASE):
        if cut_number == 28:
            return [], (
                "Landscape-only macro natural view of exactly three living white silkworms feeding at irregular "
                "distances on fresh green mulberry leaves, with one fine naturally curved silk strand catching soft "
                "daylight between two leaves; the living silkworms and leaf anatomy fill the frame"
            ), "open primordial mulberry garden"
        variants = (
            "Landscape-only macro natural view of living silkworms feeding separately on fresh mulberry leaves, with one intact white cocoon in soft daylight; no person, mouth, map, loom display or arranged object row",
            "Landscape-only open mulberry garden leading naturally toward one plain unpainted weaving shelter in the distance, with living leaves and soft white silk thread moving in the breeze; no person, map, timeline or artifact display",
            "Landscape-only interior-wide view of one plain unpainted archaic weaving hall with upright looms integrated into the working space and natural light crossing unfinished silk cloth; no person, palace, map or object grid",
        )
        return [], variants[cut_number % len(variants)], "mulberry garden and plain Takamagahara weaving shelter"
    if cut_number == 1:
        return [], "Landscape-only one curving primordial sand-and-gravel shore beside dark jagged rocks and real ocean waves under clear natural daylight; no person, emblem, sign, writing or arranged object", "bare primordial shore of the Japanese islands"
    if cut_number in {2, 9}:
        return [], "Landscape-only broad primordial river valley beneath one continuous natural sky where warm gold daylight recedes left and cool silver-blue night recedes right, with the sky and terrain filling the entire frame", "primordial river valley of mythic Japan"
    if re.search(r"飢え死に|食糧\s*の\s*供給源\s*を\s*失", narration, re.IGNORECASE):
        return [], "Landscape-only broad barren primordial field with dry fissured earth and sparse withered grain reaching an empty horizon beneath cold light; no person, bowl, basket, token, building or arranged object", "barren primordial field of mythic Japan"
    if re.search(r"牛|馬", narration, re.IGNORECASE):
        return [], "Animal-only landscape with exactly one healthy cow and exactly one healthy horse standing as two complete separate animals in natural dawn mist beyond one low plain shroud edge and irregular young grain shoots; no person, harness, extra animal, token or object row", "newly fertile primordial field of mythic Japan"
    if re.search(r"米\s*一\s*粒|一\s*粒\s*に\s*神", narration, re.IGNORECASE):
        return [], "Landscape-only macro soil cross-section of exactly one natural rice grain beginning to germinate, with one pale root descending and one green shoot rising through real dark soil; no hand, dish, glow, symbol or arranged object", "living primordial field soil"
    if re.search(r"死\s*が\s*命\s*の\s*起源|枯れて|死\s*と\s*再生|自然\s*の\s*サイクル", narration, re.IGNORECASE):
        return [], "Landscape-only continuous natural soil cross-section where one fallen dry plant returns to earth beside one germinating seed and one rising green shoot under dawn light; no person, scale, lotus, token or object display", "living primordial field soil"
    fertile_variants = (
        "Landscape-only newly fertile field where irregular young rice, millet and bean shoots spread naturally from dark soil beside one low plain earth-tone shroud edge; no exposed body, token, grid, map or artifact display",
        "Landscape-only dawn field where irregular young grain shoots expand naturally from one low plain shroud edge toward a real river; no person, animal, token, object row or artifact display",
        "Landscape-only close natural soil view where one rice shoot, one millet shoot and one bean seedling emerge at uneven distances beside a frayed earth-tone shroud edge; no exposed body, bowl, blade, symbol, grid or artifact display",
        "Landscape-only broad primordial river field in which rice, millet, wheat and beans grow in natural mixed patches under warm dawn light; no person, building, map, token or arranged object",
    )
    return [], fertile_variants[cut_number % len(fertile_variants)], "newly fertile primordial field of mythic Japan"


def _japanese_myth_scene_override(
    cut: dict[str, Any],
    script_context: str,
) -> tuple[list[str], str, str]:
    ep7_override = _uke_mochi_afterlife_scene_override(cut, script_context)
    if ep7_override[1]:
        names, scene, location = ep7_override
        scene = re.sub(
            r"(?:;|,)\s*(?:no|without)\b[^.;]*|\s+with\s+no\b[^.;]*",
            "",
            scene,
            flags=re.IGNORECASE,
        ).strip(" ,;")
        return names, scene, location
    narration = str(cut.get("narration") or "")
    cut_number = _script_text_number(cut.get("cut_number"))
    sun_moon_episode = bool(
        re.search(
            r"태양.*달.*영원히.*갈라|太陽.*月.*永遠.*別れ",
            script_context,
            re.IGNORECASE,
        )
    )
    if sun_moon_episode:
        dialogue_safe_overrides = (
            (
                r"想像.*グロテスク.*残酷.*事件.*隠",
                [],
                "Object-only restrained omen on featureless bare packed earth: exactly one straight leaf-shaped aged-bronze ritual blade lies beside three small dark-red droplets and one overturned plain clay bowl under cold silver light, with no person, body, hand, limb, cave, building or writing",
                "featureless bare packed earth in primordial mythic Japan",
            ),
            (
                r"葦原中国.*食べ物.*司る.*女神.*住",
                [],
                "Landscape-only fertile primordial river plain with fresh rice, millet and bean plants growing beside natural wetlands and low bare hills, with zero visible people, buildings, shrines, tiled roofs, roads or modern objects",
                "fertile Ashihara no Nakatsukuni river plain in Japanese creation myth",
            ),
            (
                r"日本.*神話.*深い.*傷跡.*悲劇.*始まり",
                [],
                "Object-only tragic beginning on one continuous bare packed-earth court: exactly one untouched empty low rough-timber feast tray sits beside one long jagged dark-red crack in the soil and exactly three small dark-red droplets, with no blade, weapon, person, body, hand, limb or building",
                "bare packed-earth court in primordial mythic Japan",
            ),
            (
                r"最高.*おもてなし.*盛大.*宴.*準備",
                [],
                "Object-only strict top-down banquet preparation on bare packed earth: exactly three separated low rough-timber feast boards in one row, left board holding exactly one brown unglazed clay bowl of rice, center board holding exactly two whole silver fish, right board holding exactly three prepared game-meat portions directly on bare wood, with no extra bowl, plate, mat, person, hand, high table, chair, chopsticks, porcelain, writing or building",
                "featureless bare packed-earth court in primordial mythic Japan",
            ),
            (
                r"食べ物.*女神.*準備.*衝撃.*おもてなし",
                [],
                "Object-only strict top-down shocking hospitality tableau on exactly one low rough-timber feast board: upper left holds exactly one brown unglazed clay bowl filled with rice, lower center holds exactly two whole silver fish directly on bare wood, upper right holds exactly three prepared game-meat portions directly on bare wood, with no extra bowl, plate, mat, cloth, label, writing, person, hand, porcelain or extra board",
                "featureless bare packed-earth court in primordial mythic Japan",
            ),
            (
                r"招かれた.*月の神.*受け取り.*全く.*違",
                ["Tsukuyomi"],
                "Extreme hand-free face-only close-up of Tsukuyomi recoiling from the unseen feast in rigid disgust, complete face filling ninety-five percent of frame height, hard lower crop at the jaw, both shoulders outside frame, no neck, robe or limb visible, flat featureless blue-black sky in every corner, no secondary figure, architecture or ground",
                "featureless open blue-black sky in Japanese creation myth",
            ),
            (
                r"罪.*ない.*女神.*無残.*切り殺",
                [],
                "Object-only strict top-down restrained killing aftermath on featureless bare packed earth: exactly two separate torn halves of one earth-green woven sash lie flat left and right with freshly cut straight edges facing one empty gap, exactly one restrained dark-red stain and exactly seven scattered rice grains occupy the gap, with no long rigid object, board, tray, blade, sword, scabbard, weapon, person, body, hand, foot, limb, house or writing",
                "featureless bare packed-earth court in primordial mythic Japan",
            ),
            (
                r"ツクヨミ.*倒れた.*遺体.*見下ろ.*冷酷.*吐き捨て",
                ["Tsukuyomi"],
                "Extreme hand-free face-only close-up of Tsukuyomi looking sharply downward with cold contempt while speaking toward the unseen ground, complete face filling ninety percent of the frame, hard lower crop at the jaw before any robe appears, both shoulders and every limb outside, smooth blue-black night sky filling all corners",
                "open primordial night sky beneath the moon",
            ),
            (
                r"汚らわしく.*気持ち.*悪い.*女神",
                ["Tsukuyomi"],
                "Extreme hand-free face-only close-up of Tsukuyomi speaking the insult with a curled lip and cold narrowed eyes, complete face filling ninety percent of the frame, hard lower crop at the jaw before any robe appears, both shoulders and every limb outside, smooth blue-black night sky filling all corners",
                "open primordial night sky beneath the moon",
            ),
            (
                r"剣.*血.*拭い.*高天原.*戻",
                [],
                "Object-only departure evidence on bare packed earth: one straight leaf-shaped aged-bronze ritual blade lies beside one separate dark-red-stained plain white woven cloth while one narrow continuous silver moonlight trail recedes upward toward a distant golden cloud edge, with no person, hand, limb, katana, cave or building",
                "bare primordial slope below Takamagahara",
            ),
            (
                r"あの.*女神.*口.*汚い.*私.*食べさせ",
                ["Tsukuyomi"],
                "Extreme hand-free face-only close-up of Tsukuyomi accusing the unseen Uke Mochi mid-sentence, his mature adult nose sharply wrinkled, upper lip curled, mouth visibly open in speech and both brows pulled down in cold disgust, complete speaking face filling ninety percent of frame height, hard lower crop at the jaw before any robe appears, both shoulders and every limb outside, smooth pale-gold Takamagahara sky filling all corners",
                "open high Takamagahara plain beneath a smooth pale-gold sky",
            ),
            (
                r"太陽.*女神.*驚き.*凄まじい.*激怒",
                ["Amaterasu"],
                "Extreme hand-free face-only close-up of Amaterasu as shock transforms into fierce rage, complete face filling ninety percent of frame height, wet golden eyes and speaking mouth beneath one natural sun halo, hard lower crop at the jaw, both shoulders and every limb outside frame, bare unadorned forehead and plain center-parted black hair",
                "open high Takamagahara plain beneath a smooth pale-gold sky",
            ),
            (
                r"太陽.*月.*共に.*輝.*黄金.*時代.*終わり",
                [],
                "Landscape-only straight-down aerial view: one S-curved river and two low banks fill the frame; the entire left half is warm gold daylight, the entire right half is deep silver-blue night, and one smooth natural boundary follows the river",
                "empty primordial river valley of mythic Japan",
            ),
            (
                r"神様.*怒り.*嫌悪.*感情.*コントロール.*できない",
                [],
                "Object-only strict top-down loss-of-control symbol on one featureless flat river stone: exactly one plain handleless round aged-bronze ritual mirror disk, small and palm-sized, lies flat while one deep straight crack crosses the disk edge to edge and one smooth continuous warm-gold-to-silver-blue twilight gradient crosses the stone, with no upright monument, pedestal, face, mask, person, hand, building or writing",
                "featureless bare primordial riverbank in mythic Japan",
            ),
            (
                r"アマテラス.*ウケモチ.*命.*生み出す.*理解",
                [],
                "Object-only close view of one low woven basket filled with rice, millet and exactly three white silk cocoons resting beside the first tiny green shoots under one warm natural golden sunbeam, with no visible person, hand, limb, building, screen, wall or writing",
                "newly fertile primordial field of mythic Japan",
            ),
            (
                r"ある.*日.*太陽.*女神.*アマテラス.*地上.*世界.*気",
                ["Amaterasu"],
                "Extreme hand-free facial close-up of Amaterasu looking downward with alert curiosity through one open cloud gap toward the unseen green land, complete face, neck and white-gold collar only, with both shoulders and every limb outside the frame",
                "open high Takamagahara plain above the primordial land",
            ),
            (
                r"保食神.*ウケモチ.*豊穣.*神",
                ["Uke Mochi"],
                "Extreme hand-free facial close-up introducing Uke Mochi as the food and fertility goddess, her warm adult face framed by a real rice field, millet tufts and one clear river, with only face, neck and earth-tone collar visible and every limb outside the frame",
                "open fertile primordial field beside a clear river in mythic Japan",
            ),
            (
                r"月の神.*ツクヨミ.*姉.*頼み.*引き受け",
                ["Tsukuyomi"],
                "Extreme hand-free facial close-up of Tsukuyomi accepting Amaterasu's request with a calm respectful lowered gaze and one slight nod, complete face, neck and white-blue collar only, with both shoulders and every limb outside the frame",
                "open cloud-lit Takamagahara plain in Japanese creation myth",
            ),
            (
                r"歓迎.*宴.*血塗られた.*惨劇",
                [],
                "Object-only foreshadowing on one continuous bare packed-earth court: three intact low rough-timber feast trays of rice, silver fish and prepared meat stand beside one separate leaf-shaped aged-bronze ritual blade casting a cold shadow toward one restrained dark-red ground stain, with no person or body",
                "bare packed-earth court at an open-sided unpainted timber food shelter",
            ),
            (
                r"太陽.*女神.*アマテラス.*月.*男神.*ツクヨミ",
                ["Amaterasu", "Tsukuyomi"],
                "Tight hand-free head-and-shoulders two-shot introducing Amaterasu under warm gold light and Tsukuyomi under cool silver light on one open Takamagahara plain, both complete faces and collars visible with a hard lower crop before either upper arm begins",
                "open cloud-lit Takamagahara plain in Japanese creation myth",
            ),
            (
                r"ツクヨミ.*衝撃.*光景.*目の当たり",
                ["Tsukuyomi"],
                "Extreme hand-free facial close-up of Tsukuyomi staring downward at the unseen feast in sudden shock and disgust, widened silver eyes and tense mouth filling the frame, with only face, neck and white-blue collar visible and every limb outside the frame",
                "bare packed-earth court at an open-sided unpainted timber food shelter",
            ),
            (
                r"ウケモチ.*陸.*向いて.*口.*開",
                ["Uke Mochi"],
                "Extreme hand-free side-profile facial close-up of Uke Mochi turning toward the real green land and opening her mouth before any food appears, with only her complete face, hair, neck and earth-tone collar visible and every shoulder, arm and hand outside the frame",
                "bare packed-earth court facing a green primordial field",
            ),
            (
                r"口.*大量.*ご飯.*吐き出",
                ["Uke Mochi"],
                "Clean white rice grains arc outward through empty air away from Uke Mochi's open mouth toward one low unglazed clay bowl, shown in an extreme hand-free side-profile facial close-up with only face, hair, neck and collar visible and every shoulder, arm and hand outside the frame",
                "bare packed-earth court facing a green primordial field",
            ),
            (
                r"ウケモチ.*名前.*食べ物.*持つ.*意味",
                [],
                "Object-only close food-holder emblem on bare packed earth: one low rough-timber feast board supports exactly one shallow clay bowl of rice, two whole silver fish and exactly three clean prepared game-meat portions, all separated and fully visible with no person, writing or building",
                "bare packed-earth court in primordial mythic Japan",
            ),
            (
                r"体.*中.*生命.*生み出.*大地.*豊か.*象徴",
                [],
                "Landscape-only close view of fresh rice, millet and bean shoots emerging together from rich dark earth beside one clear primordial river under warm dawn light, with no person, body, building or modern field equipment",
                "fertile primordial river field of mythic Japan",
            ),
            (
                r"綺麗好き.*気位.*ツクヨミ.*反応.*違",
                ["Tsukuyomi"],
                "Extreme hand-free facial close-up of Tsukuyomi recoiling with rigid cleanliness and proud disgust toward the unseen offering, complete pale face, neck and white-blue collar only, with both shoulders and every limb outside the frame",
                "bare packed-earth court at an open-sided unpainted timber food shelter",
            ),
            (
                r"(?:嫌悪.*屈辱.*心.*支配|プライド.*傷.*ツクヨミ.*怒り.*我.*忘)",
                ["Tsukuyomi"],
                "Extreme hand-free facial close-up of Tsukuyomi as disgust and wounded pride harden into uncontrolled rage, narrowed silver eyes and clenched jaw filling the frame, with only face, neck and white-blue collar visible and every limb outside the frame",
                "bare packed-earth court at an open-sided unpainted timber food shelter",
            ),
            (
                r"ウケモチ.*悪意.*最大.*おもてなし",
                ["Uke Mochi"],
                "Extreme hand-free facial close-up of Uke Mochi smiling with innocent hospitality toward Tsukuyomi outside the frame, one orderly feast tray softly visible below her collar line, with both shoulders and every limb outside the frame",
                "bare packed-earth court at an open-sided unpainted timber food shelter",
            ),
            (
                r"怒り狂った.*ツクヨミ.*極端.*残酷",
                [],
                "Object-only close foreshadowing of one straight leaf-shaped aged-bronze ritual blade lying between one untouched feast tray and one torn earth-tone woven sash under cold silver light, with no person, body, hand, limb or building",
                "bare packed-earth court in primordial mythic Japan",
            ),
            (
                r"(?:宴.*準備.*ウケモチ.*一刀両断|食べ物.*女神.*斬り殺.*月の神.*ツクヨミ)",
                [],
                "Object-only restrained aftermath on bare packed earth: one straight blood-marked leaf-shaped aged-bronze ritual blade rests apart from one torn earth-green woven sash, one overturned feast tray and one dark-red ground stain, with no visible body, person, hand or limb",
                "bare packed-earth court in primordial mythic Japan",
            ),
            (
                r"美しい.*女神.*理由.*血.*海.*倒",
                [],
                "Object-only restrained death evidence: one soft irregular earth-green woven shroud with no body contour lies flat beside spilled white rice and one dark-red ground stain, while one aged-bronze ritual blade remains separated at the far edge, with no person or limb",
                "bare packed-earth court in primordial mythic Japan",
            ),
            (
                r"お\s*使い.*最悪.*結末",
                [],
                "Object-only empty moonlit aftermath with three overturned low feast trays, scattered rice, two silver fish, one torn earth-green sash and one separated aged-bronze ritual blade on continuous bare packed earth, with no person, body, hand or limb",
                "bare packed-earth court in primordial mythic Japan",
            ),
            (
                r"食べ物.*女神.*準備.*衝撃.*おもてなし",
                [],
                "Object-only shocking hospitality tableau on three separated low rough-timber feast trays: one clay bowl of rice, one clay platter with two silver fish and one clay platter with exactly three prepared game-meat portions, all on bare packed earth with no person or modern tableware",
                "bare packed-earth court in primordial mythic Japan",
            ),
            (
                r"口.*ご飯.*魚.*獣.*肉.*吐き出.*盛り付",
                ["Uke Mochi"],
                "Extreme hand-free side-profile facial close-up of Uke Mochi with three clearly separated food arcs moving outward through empty air: white rice grains above, two whole silver fish at center and exactly three prepared game-meat portions below, with only face, neck and collar visible and every limb outside the frame",
                "bare packed-earth court between a primordial field, sea and mountain",
            ),
            (
                r"彼女.*命.*生み出す.*神聖.*行為",
                [],
                "Landscape-only sacred abundance scene where fresh rice, millet and bean shoots rise from rich soil beside a clear river under one warm natural golden light, with three white silk cocoons resting on a bare stone and no person or building",
                "fertile primordial river field of mythic Japan",
            ),
            (
                r"腰.*剣.*抜.*満面.*笑み.*ウケモチ.*斬",
                [],
                "Object-only moment before violence: one freshly drawn straight leaf-shaped aged-bronze ritual blade points across bare packed earth toward one untouched feast tray and one folded earth-green woven sash, the separate plant-fiber-wrapped wooden sheath behind it, with no person, hand or body",
                "bare packed-earth court in primordial mythic Japan",
            ),
            (
                r"ツクヨミ.*倒れた.*遺体.*見下ろ.*冷酷.*吐き捨て",
                ["Tsukuyomi"],
                "Extreme hand-free facial close-up of Tsukuyomi looking sharply downward with cold contempt while speaking toward the unseen ground, complete face, neck and white-blue collar only, with both shoulders and every limb outside the frame",
                "moonlit bare packed-earth court in primordial mythic Japan",
            ),
            (
                r"汚らわしく.*気持ち.*悪い.*女神",
                ["Tsukuyomi"],
                "Extreme hand-free facial close-up of Tsukuyomi speaking the insult with a curled lip and cold narrowed eyes, complete face, neck and white-blue collar only, with both shoulders and every limb outside the frame",
                "moonlit bare packed-earth court in primordial mythic Japan",
            ),
            (
                r"(?:姉.*アマテラス.*地上.*出来事.*報告|天上.*戻り.*姉.*太陽.*アマテラス.*報告)",
                ["Amaterasu", "Tsukuyomi"],
                "Tight hand-free head-and-shoulders two-shot on one open Takamagahara plain: Tsukuyomi speaks without remorse while Amaterasu listens in growing alarm, both complete faces and collars visible with a hard lower crop before either upper arm begins",
                "open cloud-lit Takamagahara plain in Japanese creation myth",
            ),
            (
                r"ツクヨミ.*悪びれる.*堂々.*語",
                ["Tsukuyomi"],
                "Extreme hand-free facial close-up of Tsukuyomi reporting with proud composure and no remorse, complete face, neck and white-blue collar only, with both shoulders and every limb outside the frame",
                "open cloud-lit Takamagahara plain in Japanese creation myth",
            ),
            (
                r"姉.*褒め.*思",
                ["Tsukuyomi"],
                "Extreme hand-free facial close-up of Tsukuyomi waiting for praise with one faint expectant smile and confident silver eyes, complete face, neck and collar only, with every shoulder and limb outside the frame",
                "open cloud-lit Takamagahara plain in Japanese creation myth",
            ),
            (
                r"聞いた.*アマテラス.*表情.*凍",
                ["Amaterasu"],
                "Extreme hand-free facial close-up of Amaterasu as her expression freezes in shock and disbelief, wide golden eyes beneath one soft sun halo, with only complete face, neck and white-gold collar visible and every limb outside the frame",
                "open cloud-lit Takamagahara plain in Japanese creation myth",
            ),
            (
                r"(?:アマテラス.*立ち上がり.*激しく.*叱|聞いた.*アマテラス.*激しく.*怒り狂)",
                ["Amaterasu"],
                "Extreme hand-free facial close-up of Amaterasu condemning Tsukuyomi in fierce grief and anger, wet golden eyes and speaking mouth filling the frame beneath one natural sun halo, with both shoulders and every limb outside the frame",
                "open cloud-lit Takamagahara plain in Japanese creation myth",
            ),
            (
                r"ツクヨミ.*予想外.*怒られ",
                ["Tsukuyomi"],
                "Extreme hand-free facial close-up of Tsukuyomi recoiling in genuine surprise as his confidence vanishes, widened silver eyes and tense mouth filling the frame, with both shoulders and every limb outside the frame",
                "open cloud-lit Takamagahara plain in Japanese creation myth",
            ),
            (
                r"決定打.*アマテラス.*究極.*決断",
                ["Amaterasu"],
                "Extreme hand-free facial close-up of Amaterasu reaching a cold final decision, grief settling into an unwavering direct gaze under one golden sun halo, with only face, neck and collar visible and every limb outside the frame",
                "open cloud-lit Takamagahara plain in Japanese creation myth",
            ),
            (
                r"二度.*お前.*顔.*見たく",
                ["Amaterasu"],
                "Extreme hand-free opposing-profile close-up of Amaterasu turning her face decisively away from Tsukuyomi outside the frame, eyes closed in rejection, with only face, neck and white-gold collar visible and every limb outside the frame",
                "open cloud-lit Takamagahara threshold in Japanese creation myth",
            ),
            (
                r"ツクヨミ.*天上.*中心.*追放.*夜.*世界",
                [],
                "Landscape-only exile path where one narrow continuous silver moonlight trail leaves a warm golden Takamagahara cloud plain and descends into a vast empty blue-black night valley, with zero visible people, limbs, feet or footprints",
                "sky boundary between Takamagahara and the primordial night world",
            ),
            (
                r"褒められる.*ツクヨミ.*予想外.*困惑",
                ["Tsukuyomi"],
                "Extreme hand-free face-only close-up of Tsukuyomi in confused disbelief after the expected praise becomes anger, his complete face filling ninety-two percent of the frame with silver eyes widened and brow tightened, plain low-tied black hair and smooth bare unadorned forehead, a hard lower crop at the base of the jaw before any neck or robe appears, both shoulders and every limb outside the frame, smooth pale-blue sky filling both lower corners",
                "open cloud-lit Takamagahara plain in Japanese creation myth",
            ),
            (
                r"生み出す.*汚い.*月.*神.*尊い.*太陽.*神",
                [],
                "Object-only value contrast on featureless pale packed clay: exactly one detached dry ivory rice grain under warm gold light at left and exactly one cold silver-gray pebble under cool silver light at right, separated by one wide empty gap with no person, hand, plant or writing",
                "one seamless pale packed-clay surface in Japanese creation myth",
            ),
            (
                r"アマテラス.*弟.*冷たく.*絶縁.*宣言",
                ["Amaterasu", "Tsukuyomi"],
                "Tight hand-free opposing-profile head-and-shoulders two-shot as Amaterasu coldly ends the bond and Tsukuyomi stares back in shock, both lower crops ending at the collarbones before either upper arm begins beneath one gold-to-silver sky",
                "open cloud-lit Takamagahara threshold in Japanese creation myth",
            ),
            (
                r"二度.*お前.*顔.*合わせる.*ない",
                ["Amaterasu", "Tsukuyomi"],
                "Tight hand-free rear head-and-shoulders two-shot of Amaterasu and Tsukuyomi turning away toward opposite edges, both heads, necks and collar tops visible with every shoulder, arm, hand and leg outside the frame beneath one continuous gold-to-silver sky",
                "open cloud-lit Takamagahara threshold in Japanese creation myth",
            ),
            (
                r"アマテラス.*ツクヨミ.*完全.*別々.*領域",
                [],
                "Landscape-only one continuous primordial river valley permanently divided by a broad natural twilight corridor, warm gold daylight receding left and cool silver-blue night extending right, with no person, building, road or modern object",
                "primordial natural landscape of mythic Japan",
            ),
            (
                r"残念.*ウケモチ.*すでに.*命.*落",
                [],
                "Object-only quiet death evidence on bare packed earth: one soft irregular earth-green woven shroud with no body contour lies flat beside one fallen dry leaf and one extinguished clay lamp bowl, with no person, body, hand, limb, building or writing",
                "bare packed-earth court in primordial mythic Japan",
            ),
        )
        for pattern, subjects, scene, location in dialogue_safe_overrides:
            if re.search(pattern, narration):
                return subjects, scene, location
        if re.search(r"皆さん.*こんにちは.*日本.*歴史.*秘密.*時間", narration):
            return (
                [],
                "Landscape-only elevated view across one completely continuous primordial volcanic-island coast: one broad blue sea, one curving sand-and-gravel shore, low green hills covered edge-to-edge in wild scrub, clear sky, sparse flat shoreline stones",
                "bare primordial shore of the Japanese islands",
            )
        if re.search(r"前回.*穢れ.*(?:禊|秊)ぎ.*儀式", narration):
            return (
                [],
                "Landscape-only strict top-down view of clear shallow purification river water over many small rounded pebbles, one small diffuse gray-brown sediment cloud beneath the center surface fading into three pale concentric ripples, clean sunlight visible across the entire water surface",
                "clear shallow purification river in primordial mythic Japan",
            )
        if re.search(r"宇宙.*秩序.*三柱.*神々.*誕生", narration):
            return (
                [],
                "Landscape-only shallow primordial river with exactly three separated natural light columns rising from the water: warm gold at left, cool silver at center and blue-black storm light at right, open air between every column",
                "shallow purification riverbank in primordial mythic Japan",
            )
        if re.search(r"天照.*月読.*須佐之男", narration):
            return (
                [],
                "Landscape-only primordial sky containing exactly three separated natural celestial forms: one warm golden daylight halo at left, one cool silver moonlight halo at center and one blue-black storm spiral at right above one continuous river horizon",
                "sky above the primordial Japanese islands",
            )
        if re.search(r"今日.*太陽.*月.*衝撃.*エピソード.*紹介", narration):
            return (
                [],
                "Landscape-only one continuous primordial sky above a river valley where warm gold daylight and cool silver-blue night approach one jagged natural storm scar at center, tension gathering along the unbroken horizon",
                "primordial natural landscape of mythic Japan",
            )
        if re.search(r"日本.*神話.*太陽.*月.*元々.*仲.*良", narration):
            return (
                [],
                "Landscape-only one warm golden sunbeam and one cool silver moonbeam overlap across the same primordial river valley; no people, buildings, symbols or artifacts",
                "open cloud-lit Takamagahara plain in Japanese creation myth",
            )
        if re.search(r"(?:高天原|天上).*二人.*(?:協力|平和)", narration):
            return (
                [],
                "Landscape-only warm gold and cool silver light jointly illuminate one shared primordial land and river; no people, buildings, symbols or artifacts",
                "open cloud-lit Takamagahara plain in Japanese creation myth",
            )
        if re.search(r"現在.*太陽.*月.*同時.*空.*昇.*ありません", narration):
            return (
                [],
                "Landscape-only high aerial view of one very broad S-curving primordial river occupying the lower two-thirds of the frame between smooth continuous low grass slopes, warm gold afterglow remaining beyond the far left mountain edge and cool starry blue night extending above the far right horizon along one diagonal natural twilight gradient",
                "primordial natural landscape of mythic Japan",
            )
        if re.search(r"昼.*夜.*完全.*分離.*決して.*交わらない.*運命", narration):
            return (
                [],
                "Landscape-only one continuous primordial river valley where one long natural ridge carries warm golden light on its left slope and cool silver-blue night on its right slope beneath one unbroken sky, the empty river and bare banks remaining continuous through the center",
                "primordial natural landscape of mythic Japan",
            )
        if re.search(r"二柱.*天上.*共に.*平和.*暮", narration):
            return (
                ["Amaterasu", "Tsukuyomi"],
                "Waist-up Amaterasu and Tsukuyomi share one calm open cloud-lit Takamagahara plain above the same green primordial river valley, peaceful faces turned toward the land, long closed sleeves covering every wrist area",
                "open cloud-lit Takamagahara plain in Japanese creation myth",
            )
        if re.search(r"地上.*住む.*食べ物.*女神.*ウケモチ.*様子.*見", narration):
            return (
                ["Uke Mochi"],
                "Extreme facial close-up of Uke Mochi in one open green primordial field beside a clear river, her calm welcoming adult face filling seventy percent of frame height beneath open daylight; the frame contains only her hair crown, complete face, neck, crossed earth-tone collar tops and shoulder tops, with a hard lower crop at both collarbones before either upper arm begins",
                "open green primordial field beside a clear river in mythic Japan",
            )
        if re.search(r"なぜ.*二柱.*姉弟.*永遠.*顔.*合わせ", narration):
            return (
                [],
                "Landscape-only warm gold daylight and cool silver night move apart across one primordial river valley, leaving a broad natural twilight gap; no people, buildings, symbols or artifacts",
                "open cloud-lit Takamagahara threshold in Japanese creation myth",
            )
        if re.search(r"アマテラス.*(?:弟.*)?ツクヨミ.*(?:お\s*使い|頼み)", narration):
            return (
                ["Amaterasu", "Tsukuyomi"],
                "Waist-up two-shot of Amaterasu speaking directly to Tsukuyomi on one open Takamagahara cloud plain; Tsukuyomi listens with a respectful lowered gaze, long closed sleeves covering every wrist area",
                "open cloud-lit Takamagahara plain in Japanese creation myth",
            )
        if re.search(r"私.*代わり.*ウケモチ.*様子.*見", narration):
            return (
                ["Amaterasu", "Tsukuyomi"],
                "Waist-up Amaterasu asks Tsukuyomi to visit Uke Mochi while both look toward the distant green land below the cloud edge; Tsukuyomi listens attentively, long closed sleeves covering every wrist area",
                "open cloud-lit Takamagahara edge above the primordial land",
            )
        if re.search(r"(?:天上.*ウケモチ.*地上.*降|姉.*言いつけ.*月の神.*地上.*降り立)", narration):
            return (
                ["Tsukuyomi"],
                "Full-body Tsukuyomi descends through open silver-lit sky high above a tiny distant green field, hands hidden in sleeves, both feet fully visible, hair and robe streaming upward",
                "sky above the primordial land of mythic Japan",
            )
        if re.search(r"尊い.*客人.*ウケモチ.*大喜び", narration):
            return (
                ["Uke Mochi"],
                "Waist-up Uke Mochi bows in delighted welcome before a rough open-sided timber food shelter, bright smile and earth-tone robe visible, long closed sleeves covering both wrist areas",
                "bare packed-earth court at an open-sided unpainted timber food shelter",
            )
        if re.search(r"驚く.*ツクヨミ.*海.*向いて.*口.*開", narration):
            return (
                ["Tsukuyomi", "Uke Mochi"],
                "Waist-up two-shot under one rough open timber shelter: Uke Mochi turns toward the real blue sea and opens her mouth while Tsukuyomi recoils one step with rigid shoulders, long closed sleeves covering every wrist area",
                "bare packed-earth court beside the primordial sea",
            )
        if re.search(r"大小.*新鮮.*魚.*飛び出", narration):
            return (
                ["Uke Mochi", "Tsukuyomi"],
                "Waist-up two-shot beside the primordial sea: Uke Mochi faces the water with her mouth open as several clean silver fish arc outward in front of her toward one low rough-timber feast tray, while Tsukuyomi recoils in astonishment, long closed sleeves covering every wrist area",
                "bare packed-earth court beside the primordial sea",
            )
        if re.search(r"山.*獣.*肉.*吐き出", narration):
            return (
                ["Uke Mochi"],
                "Extreme facial close-up in a hand-free side profile of Uke Mochi facing distant primordial green mountain slopes as exactly three clean prepared game-meat portions arc leftward through empty air away from her open mouth with a clear air gap after her lips, each portion one small cube-like boneless chunk with open sky separating all three, complete face, hair, neck and narrow earth-tone collar only, both shoulders and every limb outside frame, with no platter, tray, table, wall, fence, building, person or hand",
                "bare packed-earth court beside a primordial mountain field",
            )
        if re.search(r"自分.*吐き出した.*綺麗.*盛り付", narration):
            return (
                [],
                "Object-only completed feast arrangement on three separated low rough-timber feast trays: one shallow unglazed clay bowl of rice, one shallow unglazed clay platter of silver fish and one shallow unglazed clay platter of exactly three clean prepared game-meat portions, evenly ordered on bare packed earth",
                "bare packed-earth court at an open-sided unpainted timber food shelter",
            )
        if re.search(r"どうぞ.*召し上がれ.*にこやか.*差し出", narration):
            return (
                ["Uke Mochi"],
                "Waist-up Uke Mochi smiles warmly behind three low rough-timber feast trays holding rice, silver fish and clean prepared game-meat portions in shallow unglazed clay bowls, her long closed earth-tone sleeves overlapping at the abdomen and covering both wrist areas",
                "bare packed-earth court at an open-sided unpainted timber food shelter",
            )
        if re.search(r"日本.*神話.*食べ物.*誕生.*シーン", narration):
            return (
                [],
                "Object-only feast-origin tableau on bare packed earth: exactly three separated low rough-timber boards form one row, left board holding exactly one brown unglazed clay bowl of rice and nothing else, center board holding exactly two whole silver fish directly on bare wood and nothing else, right board holding exactly three small prepared game-meat chunks directly on bare wood and nothing else, with distant real sea, field and bare mountain in natural depth layers, no extra bowl, platter, plate, stone pedestal, person, hand, wall or building",
                "bare packed-earth court between the primordial sea, field and mountains",
            )
        if re.search(r"現代.*感覚.*衝撃.*奇怪", narration):
            return (
                [],
                "Object-only evidence view of one handleless polished bronze ritual mirror disk lying beside one untouched low feast tray of rice, fish and meat on rough timber, the mirror reflecting the strange meal in a warped silver sheen",
                "bare packed-earth court at an open-sided unpainted timber food shelter",
            )
        if re.search(r"価値.*違い.*取り返し.*悲劇", narration):
            return (
                ["Amaterasu", "Tsukuyomi"],
                "Tight two-shot of Amaterasu and Tsukuyomi on one open Takamagahara plain as their calm expressions harden into opposing conviction, warm gold light and cool silver light separating their faces naturally, lower frame ending at the collarbones",
                "open cloud-lit Takamagahara threshold in Japanese creation myth",
            )
        if re.search(r"激怒.*月の神.*腰.*剣.*抜き放", narration):
            return (
                [],
                "Object-only immediate aftermath of the draw on bare packed earth: exactly one straight leaf-shaped aged-bronze double-edged ritual blade lies fully drawn diagonally beside exactly one plain plant-fiber-wrapped wooden sheath, both under cold moonlight with one fresh straight scrape mark in the soil",
                "bare packed-earth court at an open-sided unpainted timber food shelter",
            )
        if re.search(r"最高.*食材.*食卓.*凄惨.*殺人.*現場", narration):
            return (
                [],
                "Object-only aftermath on bare packed earth: three separated low rough-timber feast trays lie overturned beside spilled rice and silver fish, one straight blood-marked aged-bronze ritual blade resting apart near one dark red ground stain",
                "bare packed-earth court at an open-sided unpainted timber food shelter",
            )
        if re.search(r"豊穣.*女神.*血.*食べ物.*赤く.*染", narration):
            return (
                [],
                "Object-only close view of one low rough-timber feast tray where white rice and two silver fish carry restrained dark-red stains, with one straight blood-marked aged-bronze ritual blade lying separately on bare packed earth",
                "bare packed-earth court at an open-sided unpainted timber food shelter",
            )
        if re.search(r"生み出す.*尊い.*汚い.*勘違い.*弟.*愚", narration):
            return (
                ["Tsukuyomi"],
                "Extreme facial close-up of Tsukuyomi as rigid disgust gives way to troubled doubt, silver moon ornament and plain white-blue woven collar visible, lower frame ending at the collarbones",
                "open cloud-lit Takamagahara threshold in Japanese creation myth",
            )
        if re.search(r"招かれた.*月の神.*受け取り.*全く.*違", narration):
            return (
                ["Tsukuyomi"],
                "Single continuous hand-free view showing Tsukuyomi's recoiling different interpretation of Uke Mochi's offering across one rough-timber feast board with grain and two whole fish",
                "outdoor bare packed-earth feast court beneath open sky in primordial Japan",
            )
        if re.search(r"(?:吐き出した.*汚い.*尊い.*私|吐いた.*食べさせる.*侮辱)", narration):
            return (
                ["Tsukuyomi"],
                "Extreme facial close-up of Tsukuyomi as disgust turns into rage, jaw clenched, eyes narrowed, silver moon ornament and white-blue collar visible, lower frame ending at the collarbones",
                "bare packed-earth court at an open-sided unpainted timber food shelter",
            )
        if re.search(r"最も.*理不尽.*衝動.*殺人", narration):
            return (
                [],
                "Object-only strict top-down textless view of one leaf-shaped aged-bronze ritual blade beside one torn earth-tone woven sash and one dark-red stain on bare packed earth, with a clean lower-right corner and no human figure",
                "bare packed earth at the primordial outdoor feast court",
            )
        if re.search(r"報告.*さらに.*怒り.*悲しみ", narration):
            return (
                ["Amaterasu"],
                "Extreme facial close-up of Amaterasu hearing the report, shock and grief tightening her face beneath one golden sun halo, lower frame ending at the collarbones",
                "open cloud-lit Takamagahara threshold in Japanese creation myth",
            )
        if re.search(r"あの.*女神.*口.*汚い.*食べさせ", narration):
            return (
                ["Tsukuyomi"],
                "Chest-up Tsukuyomi recounts the feast with a cold disgusted expression, one low tray of rice and fish visible beside him as evidence, long closed white-blue sleeves covering both wrist areas",
                "open cloud-lit Takamagahara threshold in Japanese creation myth",
            )
        if re.search(r"(?:私.*手.*罰.*切り捨て|汚い.*食べ物.*罰.*殺して)", narration):
            return (
                ["Tsukuyomi"],
                "Extreme facial close-up of exactly one Tsukuyomi reporting the killing without remorse to Amaterasu outside the frame, his complete arrogant face and moving mouth filling seventy percent of frame height while cold silver eyes turn toward the empty right edge; the camera contains only his hair crown, complete face, neck, plain crossed white-blue collar tops and shoulder tops, with a hard lower crop at both collarbones before either upper arm begins; one smooth pale-gold Takamagahara sky fills the background with no cloud shapes, stone, structure, weapon or second person",
                "open high Takamagahara plain beneath a smooth pale-gold sky",
            )
        if re.search(r"(?:大切.*豊穣.*女神.*些細.*殺|命.*育む.*豊穣.*女神.*残酷)", narration):
            return (
                ["Amaterasu"],
                "Extreme facial close-up of Amaterasu grieving and condemning the killing of Uke Mochi, wet furious eyes beneath one golden sun halo, lower frame ending at the collarbones",
                "open cloud-lit Takamagahara threshold in Japanese creation myth",
            )
        if re.search(r"(?:お前.*残酷.*正しい.*神|お前.*悪しき.*神.*悪神)", narration):
            return (
                ["Amaterasu", "Tsukuyomi"],
                "Waist-up confrontation on one unbroken Takamagahara cloud plain: Amaterasu condemns Tsukuyomi with a stern direct gaze while he recoils under cold silver light, both complete bodies separated by clear shadow, long closed sleeves covering every wrist area",
                "open cloud-lit Takamagahara threshold in Japanese creation myth",
            )
        if re.search(r"悪しき.*神.*悪神.*強い.*言葉", narration):
            return (
                ["Amaterasu", "Tsukuyomi"],
                "Waist-up confrontation as Amaterasu rejects Tsukuyomi beneath opposing gold and silver light, her face severe and his face stunned, long closed sleeves covering every wrist area",
                "open cloud-lit Takamagahara threshold in Japanese creation myth",
            )
        if re.search(r"気高い.*行動.*なぜ.*悪神", narration):
            return (
                ["Tsukuyomi"],
                "Extreme hand-free face-only close-up of Tsukuyomi in confused disbelief, arrogant certainty collapsing in his eyes, complete face filling ninety-two percent of frame height, plain low-tied black hair and smooth bare unadorned forehead, hard lower crop at the jaw before any robe or shoulder appears, smooth pale-gold sky filling every corner",
                "open cloud-lit Takamagahara threshold in Japanese creation myth",
            )
        if re.search(r"(?:姉弟.*埋める.*溝|価値.*違い.*永遠.*決別)", narration):
            return (
                ["Amaterasu", "Tsukuyomi"],
                "Waist-up Amaterasu and Tsukuyomi stand on opposite sides of one broad natural shadow boundary across the same cloud plain, bodies turned away from each other, long closed sleeves covering every wrist area",
                "open cloud-lit Takamagahara threshold in Japanese creation myth",
            )
        if re.search(r"同じ.*場所.*許せない.*拒絶", narration):
            return (
                ["Amaterasu"],
                "Extreme hand-free facial close-up of exactly one Amaterasu declaring final rejection while turning her furious speaking face sharply left away from Tsukuyomi outside the right edge, complete face filling ninety percent of frame height, plain center-parted long black hair and smooth bare unadorned forehead, hard lower crop at the jaw before any robe or shoulder appears, one smooth pale-gold Takamagahara sky filling every corner",
                "open high Takamagahara plain beneath a smooth pale-gold sky",
            )
        if re.search(r"ウケモチ.*斬り殺した.*弟.*激怒.*永遠.*離縁.*アマテラス", narration):
            return (
                ["Amaterasu"],
                "Extreme hand-free facial close-up of exactly one Amaterasu alone as her furious final rejection permanently ends the sibling bond, her speaking face turned sharply left toward an empty frame edge, complete face filling ninety percent of frame height, plain center-parted long black hair and smooth bare unadorned forehead, hard lower crop at the jaw before any robe or shoulder appears, smooth pale-gold Takamagahara sky filling every corner and the entire right side empty, with no second figure",
                "open high Takamagahara plain beneath a smooth pale-gold sky",
            )
        if re.search(r"アマテラス.*地上.*殺された.*ウケモチ.*遺体.*心配", narration):
            return (
                ["Amaterasu"],
                "Tight hand-free facial close-up of exactly one Amaterasu looking downward in grief toward the unseen earth, plain long black hair, bare unadorned forehead, lower crop at collarbones, pale-gold sky and one low cloud band",
                "open high Takamagahara plain above the primordial land",
            )
        if re.search(r"黄金.*時代.*終わり", narration):
            return (
                [],
                "Landscape-only straight-down aerial view: one S-curved river and two low banks fill the frame; the entire left half is warm gold daylight, the entire right half is deep silver-blue night, and one smooth natural boundary follows the river",
                "empty primordial river valley of mythic Japan",
            )
        if re.search(r"昼.*夜.*交代.*新しい.*宇宙.*ルール.*始", narration):
            return (
                [],
                "Landscape-only high aerial view of one continuous empty primordial river valley at the start of a new cycle with both sun and moon outside the crop, warm gold dawn glow at far left and starry silver-blue night receding at far right along one curved natural twilight band",
                "primordial natural landscape of mythic Japan",
            )
        if re.search(r"太陽.*月.*決して.*出会わない.*理由", narration):
            return (
                [],
                "Landscape-only continuous primordial river valley with warm gold daylight receding beyond the far left mountains and cool silver-blue night receding beyond the far right mountains, one broad empty twilight corridor keeping both regions apart",
                "primordial natural landscape of mythic Japan",
            )
        if re.search(r"悲惨.*殺人.*昼.*夜.*宇宙.*摂理", narration):
            return (
                [],
                "Object-only close view of one leaf-shaped aged-bronze ritual blade centered on continuous bare earth under one diagonal natural twilight gradient blending warm gold daylight into cool silver-blue night",
                "bare packed-earth court at the edge of a primordial field",
            )
        if re.search(r"残酷.*暴力.*嫌悪.*世界.*バランス.*完成", narration):
            return (
                [],
                "Landscape-only high oblique aerial view into one steep primordial river canyon, warm gold daylight across the left cliff faces and cool silver-blue night across the right cliff faces along one diagonal stable natural twilight gradient, the river completely filling the narrow canyon floor between near-vertical rock walls from the lower center to the distant horizon",
                "steep primordial river canyon of mythic Japan",
            )
        if re.search(r"昼.*夜.*交代.*空.*完璧.*秩序", narration):
            return (
                [],
                "Landscape-only wide primordial sky above one river valley as a warm gold daylight band withdraws beyond the left horizon and a cool silver-blue night band advances from the right horizon, one orderly twilight boundary moving between them",
                "primordial natural landscape of mythic Japan",
            )
        if re.search(r"古代.*天体.*神々.*喧嘩.*説明", narration):
            return (
                ["Amaterasu", "Tsukuyomi"],
                "Waist-up Amaterasu and Tsukuyomi argue beneath one golden sun disk and one silver moon disk over a continuous primordial river valley, long closed sleeves covering every wrist area",
                "primordial natural landscape of mythic Japan",
            )
        if re.search(r"ギリシャ.*比較.*独特.*人間", narration):
            return (
                ["Amaterasu", "Tsukuyomi"],
                "Tight two-shot of Amaterasu and Tsukuyomi showing recognizably human grief, anger and regret beneath opposing gold and silver light, long closed sleeves covering every wrist area",
                "open cloud-lit Takamagahara threshold in Japanese creation myth",
            )
        if re.search(r"不完全.*日本.*神話.*キャラクター.*魅力", narration):
            return (
                ["Amaterasu", "Tsukuyomi"],
                "Waist-up two-shot of imperfect Japanese deities Amaterasu and Tsukuyomi with grief and stubborn pride visible in their faces, separate gold and silver light revealing small cracks in their ceremonial ornaments, long closed sleeves covering every wrist area",
                "open cloud-lit Takamagahara threshold in Japanese creation myth",
            )
        if re.search(r"潔癖.*月の神.*悲劇.*教訓", narration):
            return (
                [],
                "Object-only lesson tableau on bare packed earth: one handleless polished bronze ritual mirror disk reflects cold silver moonlight beside one straight blood-marked aged-bronze ritual blade and one overturned unglazed clay rice bowl",
                "bare packed-earth court at an open-sided unpainted timber food shelter",
            )
        if re.search(r"表面.*汚さ.*奥.*命.*尊さ.*見失", narration):
            return (
                [],
                "Object-only close view of one dark mud-coated grain husk split open to reveal one pale living rice seed and one tiny green root emerging into clean dawn light",
                "rich primordial soil of mythic Japan",
            )
        if re.search(r"その.*命.*奪った.*弟.*決して.*許さなかった", narration):
            return (
                ["Amaterasu"],
                "Extreme hand-free facial close-up of exactly one Amaterasu refusing to forgive Tsukuyomi, furious face and golden eyes fill eighty-five percent, hard collarbone crop, both shoulders outside frame, smooth empty pale-gold sky at every corner",
                "open high Takamagahara plain beneath a smooth pale-gold sky",
            )
        if re.search(r"アマテラス.*ウケモチ.*命.*生み出す.*理解", narration):
            return (
                ["Amaterasu"],
                "Waist-up Amaterasu kneels beside one low woven basket filled with rice grain, millet and silk cocoons, looking down with solemn respect, long closed white-gold sleeves covering both wrist areas",
                "bare packed-earth court at an open-sided unpainted timber food shelter",
            )
        if re.search(r"食べ物.*女神.*死.*地上.*食糧.*どう", narration):
            return (
                [],
                "Object-only four-item row on one barren field: empty brown unglazed clay bowl one at far left, empty brown unglazed clay bowl two at center-left, empty brown unglazed clay bowl three at center-right, and exactly one overturned empty woven grain basket at far right, all four separated on dry soil reaching the horizon, with no food, rock, boulder, extra bowl, second basket, person, hand, wall or building",
                "barren primordial field of mythic Japan",
            )
        if re.search(r"人間.*飢え死に.*不安", narration):
            return (
                [],
                "Landscape-only famine warning across one barren primordial field with dry furrows, withered grain stalks, exactly three empty clay bowls and one empty woven basket in the foreground",
                "barren primordial field of mythic Japan",
            )
        if re.search(r"(?:心配.*別.*神様.*地上.*派遣|別.*神様.*お\s*使い.*現場.*確認)", narration):
            return (
                [],
                "Extreme hand-free facial close-up of exactly one unnamed adult Japanese messenger deity, face filling ninety percent of the frame with only hair, complete face, neck and plain undyed archaic robe collar visible, both shoulders and every limb outside the frame, smooth natural golden light filling all four corners",
                "sky above the primordial land of mythic Japan",
            )
        if re.search(r"(?:急いで.*ウケモチ.*現場.*確認|派遣.*神様.*ウケモチ.*到着)", narration):
            return (
                [],
                "Object-only outdoor view of one soft irregular earth-tone woven shroud with no body contour lying flat on bare soil, beside one soft-edged natural golden light patch falling from the sky onto empty ground to indicate the messenger arrival, with no visible messenger, lamp, pole or body",
                "outdoor bare packed earth beside a primordial field",
            )
        if re.search(r"派遣.*神様.*目.*さらに.*驚", narration):
            return (
                [],
                "Extreme hand-free facial close-up of exactly one unnamed adult Japanese messenger deity staring downward in unmistakable astonishment, both eyes widened, eyebrows raised high and mouth visibly open, complete face filling ninety percent of frame height, only hair, neck and one narrow plain undyed archaic robe collar visible, both shoulders and every limb outside frame, smooth natural golden light",
                "outdoor bare packed earth beside a primordial field",
            )
        if re.search(r"(?:ウケモチ.*死体.*朽ち果て|その.*死体.*奇跡)", narration):
            return (
                [],
                "Object-only outdoor close view of one soft irregular earth-tone woven shroud with no body contour, lying flat on bare soil with loose cloth folds and frayed edges visible, exactly five tiny fresh-green shoots emerging through its center folds and warm golden light glowing beneath the cloth",
                "outdoor bare packed earth beside a primordial field",
            )
        if re.search(r"死.*究極.*破壊.*新しい.*命.*芽吹", narration):
            return (
                [],
                "Landscape-only straight-down close view of one irregular wild cluster of newly sprouted fresh-green two-leaf seedlings, varied small sizes and uneven natural spacing across one continuous riverbank soil patch",
                "isolated rocky river sandbar in primordial mythic Japan",
            )
        if re.search(r"彼女.*犠牲.*日本.*永遠.*豊か.*贈り物", narration):
            return (
                [],
                "Landscape-only wide fertile primordial island valley with rice, millet and bean fields spreading along one natural river under warm dawn light, bare mountains and sea visible beyond the fields",
                "fertile primordial landscape of mythic Japan",
            )
        if re.search(r"頭.*目.*お腹.*遺体.*奇跡", narration):
            return (
                [],
                "Object-only strict top-down outdoor view of one soft irregular earth-tone woven shroud bearing exactly three separated growth zones: one millet tuft at its upper fold, exactly three white silk cocoons at its center fold and one fresh rice cluster at its lower fold, with no body contour, loose cloth folds and frayed edges on bare soil",
                "outdoor bare packed earth beside a primordial field",
            )
        if re.search(r"悲劇.*死.*全て.*終わり.*メッセージ", narration):
            return (
                [],
                "Object-only view of one fresh golden-green plant sprout rising beside one cracked dark stone and one fallen dry leaf on rich soil, warm dawn light spreading outward",
                "rich primordial soil of mythic Japan",
            )
        if re.search(r"女神.*頭.*牛.*馬.*誕生", narration):
            return (
                [],
                "Object-only strict top-down animal-birth evidence on one featureless pale stone slab: exactly two separated dark-gray oval stone tokens only, one left token with a shallow uncolored incised cow sign and one right token with a shallow uncolored incised horse sign; cow grooves show two horns, two ears and a short muzzle, horse grooves show two upright ears and a long muzzle; no pigment, realistic animal, eyes, fur, mane, loose pebble, grain, plant, person or limb",
                "one continuous plain pale river-stone slab with no surrounding scenery",
            )
        if re.search(r"額.*粟.*眉毛.*絹.*蚕", narration):
            return (
                [],
                "Object-only strict top-down outdoor inventory on one soft irregular earth-tone woven shroud: exactly three separate short small cream-white segmented silkworm caterpillars, each isolated on its own separate small green mulberry leaf at upper left, upper center and upper right, exactly three oval white silk cocoons in one separated lower row, and one small millet tuft at far left, with no body contour on bare soil",
                "outdoor bare packed earth beside a primordial field",
            )
        if re.search(r"目.*稗.*お腹.*稲.*育", narration):
            return (
                [],
                "Object-only strict top-down outdoor view of one soft irregular earth-tone woven shroud bearing exactly two separated growth zones: exactly one small barnyard-millet tuft at its upper fold and exactly one fresh green rice cluster at its lower fold, with no body contour, loose cloth folds and frayed edges on bare soil",
                "outdoor bare packed earth beside a primordial field",
            )
        if re.search(r"遺体.*あらゆる.*作物.*動物.*溢", narration):
            return (
                [],
                "Object-only strict top-down harvest evidence on bare packed earth: exactly two separate flat oval rough-stone tokens, the left token carries one shallow carved cow-head profile with two horns and two ears, and the right token carries one shallow carved horse-head profile with one long muzzle and two upright ears, beside three small separated clusters of rice, millet and white silk cocoons, with no living animal, torso, leg, hoof or person",
                "outdoor bare packed earth beside a primordial field",
            )
        if re.search(r"ツクヨミ.*汚い.*切り捨てた.*命.*源", narration):
            return (
                [],
                "Object-only strict top-down view of one dull leaf-shaped aged-bronze ritual blade discarded beside one thriving cluster of fresh rice, millet and bean shoots with exposed roots in rich soil",
                "rich primordial soil of mythic Japan",
            )
        if re.search(r"死して.*世界.*豊か.*究極.*恵み", narration):
            return (
                [],
                "Object-only close view of one golden rice stalk and one tiny green seedling rising together from dark rich soil under warm dawn light, roots and grain clearly visible",
                "rich primordial soil of mythic Japan",
            )
        if re.search(r"昼.*夜.*完全.*分離.*太陽.*月.*決して.*交わらなく", narration):
            return (
                [],
                "Landscape-only high oblique river-canyon view with all sky outside the crop, one permanent curved natural twilight corridor following the empty river between warm-gold left slopes and cool silver-blue right slopes",
                "steep primordial river canyon of mythic Japan",
            )
        if re.search(r"アマテラス.*回収.*農業.*きっかけ", narration):
            return (
                [],
                "Object-only close view of one low woven basket filled with rice, millet and silk cocoons resting beside the first short fresh furrows and tiny green shoots under one warm natural golden sunbeam, with no visible person or hand",
                "newly fertile primordial field of mythic Japan",
            )
        if re.search(r"殺人.*農耕.*文明.*幕", narration):
            return (
                [],
                "Landscape-only first cultivated field with straight fresh furrows, one low woven seed basket resting on the soil and many small green shoots emerging under dawn light",
                "newly cultivated primordial field of mythic Japan",
            )
        if re.search(r"食べ物.*起源.*神々.*喧嘩.*どう.*感じ", narration):
            return (
                [],
                "Object-only strict top-down view of exactly three same-size separated flat circular stone medallions in one row: the left has exactly one plain oval rice-seed relief, the center has exactly one plain sun-circle relief, and the right has exactly one plain crescent relief, with only the three medallions and completely open bare stone between and below them",
                "bare primordial riverbank in mythic Japan",
            )
        if re.search(r"日本.*神話.*豊穣.*信仰.*犠牲", narration):
            return (
                [],
                "Landscape-only newly fertile primordial field where rice and millet rows grow around one dark weathered stone and one fallen dry leaf, warm dawn light revealing the living crops",
                "newly fertile primordial field of mythic Japan",
            )
        if re.search(r"今回.*ツクヨミ.*暴走.*昼夜.*分離.*いかが", narration):
            return (
                [],
                "Object-only strict top-down view of exactly one plain handleless round aged-bronze ritual mirror disk with exactly one deep straight crack through its center, resting across one smooth continuous warm-gold-to-silver-blue twilight gradient on one flat bare river stone, summarizing violence and day-night separation with no weapon, reflection, person or split screen",
                "bare primordial riverbank in mythic Japan",
            )
        if re.search(r"口.*吐き出した.*食べ物.*もてなす.*衝撃", narration):
            return (
                ["Uke Mochi"],
                "Clean rice grains arc outward through empty air away from Uke Mochi's open mouth with nothing touching her face and no fish visible, shown in an extreme hand-free side-profile facial close-up with only her complete face, hair, neck and robe collar visible and every shoulder, arm and hand outside the frame",
                "outdoor bare packed earth beside a primordial field",
            )
        if re.search(r"潔癖.*月の神.*命.*尊ぶ.*太陽.*決定.*対立", narration):
            return (
                [],
                "Object-only close value-conflict tableau in strict top-down view on featureless pale packed clay: exactly two loose objects only, one detached dry elongated pale ivory rice grain lying flat at left and one small cold silver-gray river pebble lying flat at right, both similar in visual size across a wide empty gap; no sprout, root, green tip, stem, leaf, rice stalk, support boulder, duplicate object, person, hand, dark border or vignette",
                "one seamless evenly lit pale packed-clay surface with no surrounding scenery",
            )
        if re.search(r"価値.*違い.*殺意.*宇宙.*構造.*変", narration):
            return (
                [],
                "Landscape-only one continuous primordial sky as a violent natural storm scar separates warm gold daylight from cool silver-blue night above one river valley, the curved boundary reshaping the whole horizon",
                "primordial natural landscape of mythic Japan",
            )
        if re.search(r"悲劇.*中.*農耕.*新たな.*豊か.*生まれ", narration):
            return (
                [],
                "Object-only close view of one dull leaf-shaped aged-bronze ritual blade half-buried in dark soil beside the first fresh rice, millet and bean shoots rising through short new furrows under warm dawn light",
                "newly cultivated primordial field of mythic Japan",
            )
        if re.search(r"食べ物.*神.*死.*地上.*五穀.*もたら", narration):
            return (
                [],
                "Object-only close view of exactly five separated shallow unglazed clay bowls, each holding one visibly different variety of grain or seed, arranged in one row on bare packed earth under warm dawn light",
                "newly fertile primordial field of mythic Japan",
            )
        if re.search(r"コメント.*自由.*意見.*聞かせ", narration):
            return (
                [],
                "Object-only strict top-down view of exactly three distinct piles of small smooth dark river pebbles below exactly three same-size separated flat circular stone medallions in one row, marked only by one oval rice seed, one plain sun circle and one plain crescent, with no figure, face, paper, card or writing",
                "bare primordial riverbank in mythic Japan",
            )
        if re.search(r"チーム.*コメント.*読", narration):
            return (
                [],
                "Object-only strict top-down view of many small smooth dark river pebbles gathered into exactly three large neat piles below exactly three same-size separated flat circular stone medallions marked only by one oval rice seed, one plain sun circle and one plain crescent, soft dawn light showing the accumulated responses, with no figure, face, fire, paper, card or writing",
                "bare primordial riverbank in mythic Japan",
            )
        if re.search(r"応援.*動画.*制作.*励み", narration):
            return (
                [],
                "Landscape-only view of many small golden lights moving together along a moonlit river path toward one bright horizon, bare stones and dark forest framing the route",
                "primordial river path in mythic Japan",
            )
        if re.search(r"海.*統治.*放棄.*追放.*スサノオ", narration):
            return (
                [],
                "Landscape-only empty primordial shore with one continuous narrow trail of disturbed wet sand leaving the waterline toward distant mountains and one abandoned plain earth-blue woven sash resting on a bare rock beneath a receding storm cloud, with zero visible people, zero human limbs, zero feet and zero footprints",
                "bare primordial shore of the Japanese islands",
            )
        if re.search(r"姉.*アマテラス.*別れ.*高天原.*登", narration):
            return (
                [],
                "Landscape-only steep bare rocky ascent with one narrow continuous blue storm-light trail winding upward toward the distant cloud-lit Takamagahara plain, with zero visible people, zero human limbs, zero feet and zero footprints",
                "rocky path below the cloud-lit Takamagahara plain in Japanese creation myth",
            )
        if re.search(r"天上.*恐怖.*大.*事件.*幕開け", narration):
            return (
                [],
                "Landscape-only single continuous sky where one broad horizontal blue-black storm shelf advances from the left toward a calm golden sunlit Takamagahara cloud plain at right, first lightning splitting their natural boundary above bare mountains, with no vertical cloud column",
                "sky boundary below Takamagahara in Japanese creation myth",
            )
        if re.search(r"次回.*荒ぶる.*弟.*太陽.*神.*激突.*誓約.*儀式", narration):
            return (
                [],
                "Object-only strict top-down next-episode ritual teaser on featureless pale stone: exactly three exact same-size same-orientation copies of one flat matte green hooked-comma magatama silhouette, one left, one center and one right, all curving right; every one of the three has a thick rounded head, one long visibly curved pointed tail and one clearly visible small black drilled hole near its head, making exactly three stones and exactly three holes total; the center is also a hooked comma, never a plain teardrop; no sphere, ring, C, U, horseshoe, side nub, fourth stone, cloth, water, plant, text, seal, logo or person",
                "one continuous smooth pale stone surface with no water, cloth, vegetation or surrounding objects",
            )
    if cut_number == 1 and re.search(r"(?:세\s*귀공자의\s*탄생|Three\s+Noble)", script_context, re.IGNORECASE):
        return (
            ["Izanagi"],
            "Golden sun disk, silver moon disk, and blue storm spiral rise as three lights above white-robed Izanagi kneeling in river spray",
            "shallow purification riverbank in primordial mythic Japan",
        )
    if re.search(r"前回.*地下\s*世界.*逃げ帰.*伊邪那岐", narration):
        return (
            ["Izanagi"],
            "Extreme facial close-up of white-robed Izanagi emerging from a black Yomi cave, his terrified face looking back over one shoulder, cold rim light across his eyes, face filling most of the frame",
            "bare rocky boundary between Yomi underworld and the living world",
        )
    if re.search(r"妻.*呪い.*地上.*生還", narration):
        return (
            ["Izanagi"],
            "Extreme facial close-up of torn white-robed Izanagi emerging from black Yomi shadow into cold daylight, relief and lingering terror across his eyes, face filling most of the frame",
            "bare rocky boundary between Yomi underworld and the living world",
        )
    if re.search(r"安堵.*(?:まだ|早)", narration):
        return (
            ["Izanagi"],
            "Oily black stains spread across white-robed Izanagi's chest cloth and sleeves while black vapor rises from the robe fabric; he recoils at a shallow riverbank with both hands hidden",
            "shallow purification riverbank in primordial mythic Japan",
        )
    if re.search(r"伊邪那岐.*身体.*汚", narration):
        return (
            ["Izanagi"],
            "Extreme facial close-up of white-robed Izanagi with oily black Yomi contamination staining his collar and both shoulders, black vapor clinging to the stained fabric, horrified eyes",
            "shallow purification riverbank in primordial mythic Japan",
        )
    if re.search(r"黄泉(?:の)?国.*死.*腐敗", narration):
        return (
            [],
            "Empty nonhuman view into Yomi underworld: a narrow black volcanic-stone cavern descends through cold mist, dead roots, stagnant dark water, and decaying leaves; no flower close-up, person, deity, building, vehicle, road, utility pole, wire, text, or Western object",
            "Yomi underworld in Japanese creation myth",
        )
    if re.search(r"(?:神道.*死.*(?:穢れ|けがれ)|死.*匂い.*(?:穢れ|けがれ))", narration):
        return (
            [],
            "Object-only close view of exactly one handleless flat solid round bronze ritual mirror disk standing upright against one rough stone, reflective face toward camera, dark mud streaks across the flat face, thin raised circular border, aged bronze patina",
            "bare purification riverbank in primordial mythic Japan",
        )
    if re.search(r"(?:穢れ|けがれ).*単なる.*汚れ.*(?:災い|邪悪)", narration):
        return (
            [],
            "Object-only view of a dense black vortex of kegare twisting above shallow water at a bare rocky riverbank, surrounding daylight dimmed, dead leaves and discolored stones forming one spreading ring",
            "bare purification riverbank in primordial mythic Japan",
        )
    if re.search(r"(?:地上.*世界|世界).*腐", narration):
        return (
            [],
            "Object-only macro view of one large green leaf attached to a living riverbank plant as branching black rot spreads from one edge through its veins, bare stone and water softly behind it",
            "bare purification riverbank in primordial mythic Japan",
        )
    if re.search(r"そこで.*伊邪那岐.*(?:穢れ|けがれ).*洗.*儀式.*決意", narration):
        return (
            ["Izanagi"],
            "White-robed Izanagi strides along a bare rocky bank toward rushing water, jaw set and eyes determined, wide sleeves and robe hem moving in the wind",
            "bare purification riverbank in primordial mythic Japan",
        )
    if re.search(r"現代.*神社.*(?:禊|みそぎ).*ルーツ", narration):
        return (
            [],
            "Object-only close view of exactly one slender bamboo purification ladle resting across one grey stone temizu water basin, one straight long handle joined to one small round cup, clear water droplets, unpainted modern Shinto shrine softly behind",
            "present-day Shinto shrine purification basin in Japan",
        )
    if re.search(r"神様.*自ら.*身体.*洗", narration):
        return (
            ["Izanagi"],
            "White-robed Izanagi steps knee-deep into a shallow clear river at dawn, body upright, both arms lowered beside him, solemn eyes fixed on the water",
            "bare purification riverbank in primordial mythic Japan",
        )
    if re.search(r"伊邪那岐.*川辺.*身.*着け.*物.*脱", narration):
        return (
            [],
            "Object-only close view of one folded white wide-sleeve robe, one unknotted plain brown cloth sash, and one straight wooden walking staff laid separately on bare river stones",
            "bare purification riverbank in primordial mythic Japan",
        )
    if re.search(r"杖.*投げ捨て.*帯.*ほどき.*衣服.*順番.*脱", narration):
        return (
            ["Izanagi"],
            "White-robed Izanagi releases one straight wooden walking staff from his lowered right hand toward bare grass, one loose brown sash and folded outer cloth already on stones beside him",
            "bare purification riverbank in primordial mythic Japan",
        )
    if re.search(r"脱ぎ捨てた.*物.*神.*生", narration):
        return (
            [],
            "Object-only view of five distinct golden light orbs rising from one discarded wooden staff, one loose brown sash, and one folded white robe arranged separately on bare river stones",
            "bare purification riverbank in primordial mythic Japan",
        )
    if re.search(r"一つ.*動作.*無数.*命.*誕生.*創造", narration):
        return (
            [],
            "Object-only view of one discarded wooden staff, one loose brown sash, and one folded white robe releasing many small golden sparks above bare river stones",
            "bare purification riverbank in primordial mythic Japan",
        )
    if re.search(r"海.*底.*中間.*水面.*命.*溢", narration):
        return (
            [],
            "Landscape-only underwater cross-section filling the frame with exactly three natural depth layers arranged as horizontal bands: small golden life sparks rise from the bare rocky seabed through clear open water and break the ocean surface into sunlight; only water, natural rock, sunlight, and golden sparks are visible",
            "primordial coastal water of mythic Japan",
        )
    if re.search(r"肉体.*清浄.*力.*満", narration):
        return (
            ["Izanagi"],
            "White-robed Izanagi stands waist-deep in the clear river with his high black topknot and robe intact, one coherent golden aura radiating around his entire clothed body",
            "bare purification riverbank in primordial mythic Japan",
        )
    if re.search(r"マイナス.*ゼロ.*プラス.*転", narration):
        return (
            [],
            "Object-only river view where black polluted water at left flows through one clear central current and becomes clean gold-lit water at right, one continuous visible transformation",
            "bare purification riverbank in primordial mythic Japan",
        )
    if re.search(r"最後.*洗浄.*最高.*傑作.*産声", narration):
        return (
            [],
            "Object-only view of one explosive golden-white burst rising from splashing river water, exactly three separated seed-like light cores visible inside the burst",
            "bare purification riverbank in primordial mythic Japan",
        )
    if re.search(r"最後.*仕上げ.*両手.*水.*顔.*洗", narration):
        return (
            ["Izanagi"],
            "Tight hand-focused view of exactly two bare hands joined edge-to-edge, ten fingers total, holding clear river water directly on the skin and lifting it toward Izanagi's face",
            "bare purification riverbank in primordial mythic Japan",
        )
    if re.search(r"両手.*澄み切った.*水.*すく", narration):
        return (
            ["Izanagi"],
            "Tight hand-focused view of exactly two bare hands joined edge-to-edge, ten fingers total, holding clear river water directly on the skin above the river surface",
            "bare purification riverbank in primordial mythic Japan",
        )
    if re.search(r"光.*中.*美しい.*女神.*姿", narration):
        return (
            ["Amaterasu"],
            "Adult Amaterasu emerges upright from one golden pillar of light above splashing river water, long straight black hair and small sun ornament visible, serene expression",
            "bare purification riverbank in primordial mythic Japan",
        )
    if re.search(r"伊邪那岐.*どの.*子供.*彼女.*愛", narration):
        return (
            ["Izanagi"],
            "White-robed Izanagi stands alone waist-up, looking toward warm off-frame golden sunlight with tears of parental joy, one soft sun-shaped reflection in his eyes",
            "bare purification riverbank in primordial mythic Japan",
        )
    if re.search(r"首.*勾玉.*首飾り.*外", narration):
        return (
            [],
            "Object-only close view of exactly one unfastened green jade magatama necklace with small comma-shaped beads resting on one folded strip of white cloth over a bare river stone",
            "bare purification riverbank in primordial mythic Japan",
        )
    if re.search(r"宝石.*太陽.*女神.*授", narration):
        return (
            [],
            "Object-only close view of exactly one unfastened green jade magatama necklace made from one large comma-shaped jade pendant threaded on one plain dark braided cord, resting across white-gold woven robe cloth beside one plain flat geometric golden sun disk with straight rays on a bare river stone",
            "bare purification riverbank in primordial mythic Japan",
        )
    if re.search(r"高天原.*天上.*治", narration):
        return (
            ["Amaterasu"],
            "Amaterasu stands alone on a vast cloud-lit Takamagahara plain beneath one golden sun disk, long straight black hair, small sun ornament and white-gold robe, open sky in every direction",
            "cloud-lit Takamagahara plain in Japanese creation myth",
        )
    if re.search(r"神道.*太陽.*全て.*中心.*理由", narration):
        return (
            [],
            "Object-only wide natural view of one golden sun centered above a primordial river valley, sunlight spreading across water, stone and forest in equal rays",
            "primordial natural landscape of mythic Japan",
        )
    if re.search(r"現在.*天皇家.*祖先.*尊い.*女神", narration):
        return (
            ["Amaterasu"],
            "Amaterasu stands alone before one golden sun halo, white-gold robe and small sun ornament clear, a single descending beam links her silhouette to the distant land below",
            "cloud-lit Takamagahara plain in Japanese creation myth",
        )
    if re.search(r"銀色.*輝き.*静寂.*男神.*誕生", narration):
        return (
            ["Tsukuyomi"],
            "Adult Tsukuyomi emerges upright from one silver moonlight pillar above the river, long black hair tied low, small silver moon ornament and archaic white-blue robe visible",
            "bare purification riverbank in primordial mythic Japan",
        )
    if re.search(r"太陽.*沈.*後.*世界.*照", narration):
        return (
            [],
            "Landscape-only night view of one bare forest path and river stones illuminated by one large silver moon, cool moonlight reaching every visible surface",
            "primordial natural landscape of mythic Japan at night",
        )
    if re.search(r"夜の食国.*夜.*世界.*治", narration):
        return (
            ["Tsukuyomi"],
            "Tsukuyomi stands alone on a vast cloud-lit night plain beneath one silver moon disk, white-blue robe and small moon ornament clear, open starry sky in every direction",
            "cloud-lit Takamagahara night plain in Japanese creation myth",
        )
    if re.search(r"昼.*夜.*分かれ.*時間.*秩序", narration):
        return (
            [],
            "Landscape-only view of one continuous river valley divided naturally by twilight, golden sunlit sky at left and silver moonlit night at right",
            "primordial natural landscape of mythic Japan",
        )
    if re.search(r"古代.*月.*満ち欠け.*カレンダー.*農業", narration):
        return (
            [],
            "Object-only sky sequence of five separate moon disks showing crescent, half, full, half and crescent phases above one bare cultivated field",
            "primordial agricultural field of mythic Japan at night",
        )
    if re.search(r"まだ.*一つ.*洗って.*顔.*パーツ.*残", narration):
        return (
            ["Izanagi"],
            "Extreme facial close-up of white-robed Izanagi with his nose centered, one clear water bead on his cheek, tense eyes realizing the final unwashed feature",
            "bare purification riverbank in primordial mythic Japan",
        )
    if re.search(r"前.*二柱.*全く.*違う.*恐ろしい.*神", narration):
        return (
            [],
            "Object-only view of one dense black storm spiral forming above the shallow river, reeds bending outward and dark wind lines converging toward its center",
            "bare purification riverbank in primordial mythic Japan",
        )
    if re.search(r"(?:太陽.*月.*比べ物.*爆風|鼻.*竜巻.*荒々しい.*光)", narration):
        return (
            ["Izanagi"],
            "Extreme facial close-up of white-robed Izanagi as a violent blue-black wind spiral and rough white light burst directly outward from his nose, terrified eyes, storm-dark riverbank behind",
            "bare purification riverbank in primordial mythic Japan",
        )
    if re.search(r"吹き荒れる.*暴風.*筋骨.*男神.*姿", narration):
        return (
            ["Susanoo"],
            "Adult Susanoo emerges waist-up from one blue-black storm spiral, archaic earth-blue wide-sleeve robe fully covering his torso and shoulders, wild shoulder-length black hair blown outward, fierce eyes, hands outside the frame",
            "bare primordial shore of the Japanese islands",
        )
    if re.search(r"海.*嵐.*司る.*破壊.*須佐之男.*誕生", narration):
        return (
            ["Susanoo"],
            "Extreme facial close-up of earth-blue-robed Susanoo at his birth, wild shoulder-length black hair, fierce clean-shaven face lit by blue lightning, real stormy ocean behind him, hands outside the frame",
            "bare primordial shore of the Japanese islands",
        )
    if re.search(r"産声.*雷.*鳴り響.*大地.*揺", narration):
        return (
            [],
            "Landscape-only primordial mountain valley as multiple blue lightning bolts strike bare rock, the river surface ripples and loose stones jump from the shaking ground; only natural rock, river water, storm sky, and lightning are visible",
            "primordial natural landscape of mythic Japan",
        )
    if re.search(r"太陽.*月.*秩序.*完全.*カオス", narration):
        return (
            [],
            "Landscape-only natural sky where one chaotic blue-black storm spiral tears across the center and shreds orderly cloud bands with blue lightning; only sky, clouds, storm wind, and lightning are visible",
            "primordial natural landscape of mythic Japan",
        )
    if re.search(r"海原.*荒れ狂う.*海.*治め", narration):
        return (
            [],
            "Landscape-only open ocean with one massive dark whirlpool rotating through violent waves beneath storm clouds; only seawater, white foam, natural coastal rock, and storm sky are visible",
            "bare primordial shore of the Japanese islands",
        )
    if re.search(r"天.*夜.*海.*三.*領域.*分割", narration):
        return (
            [],
            "Landscape-only single continuous primordial panorama with a golden sun above cloud peaks at left, a silver moon above a night valley at center, and a blue-black storm above the ocean at right; one uninterrupted natural horizon joins all three regions; only sky, mountains, ocean, sun, moon, clouds, and storm are visible",
            "primordial natural landscape of mythic Japan",
        )
    if re.search(r"三柱.*三貴子.*最高位", narration):
        return (
            [],
            "Landscape-only river valley beneath exactly three separated celestial forms: one golden sun disk, one silver moon disk, and one blue-black storm spiral aligned above the bare natural horizon; only sky, river, natural rock, and the three forms are visible",
            "primordial natural landscape of mythic Japan",
        )
    if re.search(r"泥だらけ.*禊ぎ.*生まれ.*日本.*神話.*主役", narration):
        return (
            [],
            "Landscape-only close river view where exactly three separated seed-like light cores rise from muddy purification water and become golden, silver, and blue light; only water, mud, natural stones, and three lights are visible",
            "bare purification riverbank in primordial mythic Japan",
        )
    if re.search(r"国作り.*伊邪那岐.*長い.*物語.*幕.*下", narration):
        return (
            ["Izanagi"],
            "Rear three-quarter view of white-robed Izanagi walking away alone from the purification river toward a quiet twilight horizon, high black topknot and pointed chin beard in profile, both empty hands resting naturally at his sides",
            "bare purification riverbank in primordial mythic Japan",
        )
    if re.search(r"世界.*全て.*役割.*決まり.*平和.*訪れ.*見え", narration):
        return (
            [],
            "Landscape-only tranquil primordial island valley at dawn with a calm sea, still river, untouched mountains, clear sky, and warm balanced light suggesting apparent peace; only sky, mountains, river water, seawater, natural rock, and plants are visible",
            "primordial natural landscape of mythic Japan",
        )
    if re.search(r"天照.*高天原.*暖かく.*照らし.*命.*育", narration):
        return (
            [],
            "Landscape-only Takamagahara meadow beneath warm golden sunlight as fresh green shoots open across natural soil beside a clear stream; only sunlight, sky, clouds, plants, soil, natural rock, and water are visible",
            "cloud-lit Takamagahara plain in Japanese creation myth",
        )
    if re.search(r"トラブル.*メーカー.*常に.*身内", narration):
        return (
            ["Susanoo"],
            "Extreme facial close-up of earth-blue-robed Susanoo with wild shoulder-length black hair, stubborn sideways gaze and clenched jaw beneath one gathering blue-black storm cloud, hands outside the frame",
            "bare primordial shore of the Japanese islands",
        )
    if re.search(r"父親.*命令.*無視.*海.*統治.*しよう.*しません", narration):
        return (
            ["Susanoo"],
            "Waist-up side view of earth-blue-robed Susanoo seated alone on bare shore stones with his shoulders turned away from the real ocean, wild shoulder-length black hair, stubborn resentful face, unmanaged waves behind him, hands outside the frame",
            "bare primordial shore of the Japanese islands",
        )
    if re.search(r"嵐.*神.*泣く.*世界中.*自然.*破壊", narration):
        return (
            [],
            "Landscape-only primordial forest under a violent hurricane as giant ancient trees bend, split, and lose branches across a bare river valley; only sky, trees, branches, natural rock, river water, and storm wind are visible",
            "primordial natural landscape of mythic Japan",
        )
    if re.search(r"青々.*山.*木々.*全て.*枯れ", narration):
        return (
            [],
            "Landscape-only mountain slope covered by leafless dead trees, brown withered brush, exposed roots, and fallen trunks beneath a cold gray sky; only natural rock, dry soil, dead trees, and withered plants are visible",
            "primordial natural landscape of mythic Japan",
        )
    if re.search(r"(?:豊か.*川.*海.*水.*干上が|青い.*山.*枯れ.*川.*海.*水.*完全.*干上が)", narration):
        return (
            [],
            "Landscape-only vast arid basin from foreground to horizon with deep empty channels, cracked matte mud, stranded stones, and leafless mountainsides; only natural rock, cracked mud, dry banks, dead trees, and pale sky are visible",
            "arid disaster basin in primordial mythic Japan",
        )
    if re.search(r"悪霊.*騒ぎ.*疫病.*蔓延", narration):
        return (
            [],
            "Landscape-only cracked wasteland where many nonhuman black shadow-smoke tendrils rise from fissures and spread one sickly gray-green mist across dead ground; only sky, cracked ground, shadow smoke, mist, and natural rock are visible",
            "primordial natural landscape of mythic Japan",
        )
    if re.search(r"泣き叫ぶ.*世界.*滅亡.*危機.*規格外.*パワー", narration):
        return (
            [],
            "Landscape-only disaster panorama as one blue-black storm shockwave tears across an uprooted forest, split rocks, and a cracked empty riverbed beneath lightning; only sky, natural rock, broken trees, storm wind, and lightning are visible",
            "primordial natural landscape of mythic Japan",
        )
    if re.search(r"なぜ.*言いつけ.*守ら.*世界.*壊す.*泣", narration):
        return (
            ["Izanagi"],
            "Extreme facial close-up of older white-robed Izanagi, mouth visibly open in a stern demand toward his off-camera son, furious narrow eyes, high black topknot and pointed chin beard visible, hands outside the frame",
            "bare primordial shore of the Japanese islands",
        )
    if re.search(r"母親.*いない.*孤独.*耐えられない.*大きな.*赤ん坊", narration):
        return (
            ["Susanoo"],
            "Adult earth-blue-robed Susanoo sits alone on bare ground hugging both knees tightly to his chest, wild shoulder-length black hair hanging forward, tearful adult face lowered in loneliness, bare feet grounded beside the shore",
            "bare primordial shore of the Japanese islands",
        )
    if re.search(r"最強.*破壊.*神.*マザコン.*人間味", narration):
        return (
            ["Susanoo"],
            "Extreme facial close-up of earth-blue-robed Susanoo, powerful adult storm deity with wild shoulder-length black hair, tear tracks on his fierce face softened by longing toward a distant blurred black Yomi cave, hands outside the frame",
            "bare rocky boundary between Yomi underworld and the living world",
        )
    if re.search(r"亡くなった.*母親.*死者.*世界.*黄泉.*行きたい", narration):
        return (
            ["Susanoo"],
            "Extreme facial close-up of earth-blue-robed Susanoo in side profile, wild shoulder-length black hair, tearful adult face looking toward the sealed black Yomi cave reflected in one eye, face filling most of the frame, hands outside the frame",
            "bare rocky boundary between Yomi underworld and the living world",
        )
    if re.search(r"海.*統治.*任命.*即座.*追放", narration):
        return (
            ["Susanoo"],
            "Rear three-quarter view of earth-blue-robed Susanoo walking away alone from the real ocean after exile, wild shoulder-length black hair, head lowered, both empty hands resting naturally at his sides",
            "bare primordial shore of the Japanese islands",
        )
    if re.search(r"須佐之男.*決定.*受け入れ.*旅立つ.*準備", narration):
        return (
            [],
            "Object-only close view of exactly one small tied plant-fiber travel bundle with one plain brown shoulder strap resting on a bare shore stone beside one folded strip of earth-blue woven robe cloth",
            "bare primordial shore of the Japanese islands",
        )
    if re.search(r"地下.*行く.*前.*姉.*天照.*別れ", narration):
        return (
            ["Susanoo"],
            "Rear three-quarter view of earth-blue-robed Susanoo standing on a bare rocky ridge and looking upward toward the distant cloud-lit Takamagahara plain, wild shoulder-length black hair, exactly one small plant-fiber travel bundle on his back",
            "rocky path below the cloud-lit Takamagahara plain in Japanese creation myth",
        )
    if re.search(r"天上.*界.*巻き込む.*兄弟.*喧嘩.*始まり", narration):
        return (
            [],
            "Landscape-only single continuous sky where one blue-black storm front advances toward a calm golden sunlit cloud plain, lightning beginning at the boundary above bare mountains; only sky, clouds, sunlight, lightning, and natural mountains are visible",
            "sky boundary below Takamagahara in Japanese creation myth",
        )
    if re.search(r"乱暴.*弟.*天上.*向かう.*宇宙.*危機", narration):
        return (
            [],
            "Landscape-only bare rocky ascent with one continuous line of fresh barefoot footprints and one blue-black storm trail climbing into the cloud-lit Takamagahara horizon; only sky, clouds, natural rock, footprints in dust, and storm wind are visible",
            "rocky path below the cloud-lit Takamagahara plain in Japanese creation myth",
        )
    if re.search(r"最悪.*死.*淵.*最高.*太陽.*神.*生ま", narration):
        return (
            [],
            "Landscape-only one continuous natural transition from a sealed black Yomi cave in cold shadow at left to a brilliant golden sun rising over a clear purification river at right; only sky, sunlight, cave rock, river water, and natural stones are visible",
            "natural boundary from Yomi shadow to the purification river in primordial mythic Japan",
        )
    if re.search(r"荒ぶる.*須佐之男命.*人間.*マザコン.*魅力", narration):
        return (
            ["Susanoo"],
            "Tight facial close-up of earth-blue-robed Susanoo with wild shoulder-length black hair, shoulders collapsed beneath storm wind, two visible tear tracks and an aching childlike longing toward one distant blurred black Yomi cave, hands outside the frame",
            "bare rocky boundary between Yomi underworld and the living world",
        )
    if re.search(r"三.*兄弟.*どの.*神様.*一番.*好き", narration):
        return (
            [],
            "Object-only riverbank arrangement of exactly three separated flat stone medallions with equal visual prominence: one plain golden sun disk relief, one silver crescent moon relief, and one blue-black storm spiral relief, open bare stone between all three",
            "bare purification riverbank in primordial mythic Japan",
        )
    if re.search(r"コメント.*推し.*神様.*教", narration):
        return (
            [],
            "Object-only close view of exactly three same-size separated flat stone medallions in one horizontal row, marked respectively by one plain sun disk, one crescent moon, and one storm spiral, with three distinct piles of small flat unmarked wooden vote chips below them",
            "bare purification riverbank in primordial mythic Japan",
        )
    if re.search(r"次回.*月.*神.*月読命.*食物.*女神.*保食神.*訪", narration):
        return (
            ["Tsukuyomi", "Uke Mochi"],
            "Single continuous view before a rough open timber shelter: white-blue-robed male Tsukuyomi approaches earth-tone-robed female Uke Mochi between two raw posts; they stop one arm's length apart on shared packed earth, both pairs of hands concealed inside opposite sleeves",
            "bare packed-earth court at an open-sided unpainted timber food shelter on Takamagahara",
        )
    if re.search(r"保食神.*自ら.*体.*食べ物.*取り出.*月読命.*もてなし", narration):
        return (
            ["Tsukuyomi", "Uke Mochi"],
            "Single continuous packed-earth view under a rough open timber shelter: earth-tone-robed female Uke Mochi kneels hands hidden as rice, grain, fish and leaves fall from gold light at her covered torso onto a low tray; white-blue-robed male Tsukuyomi recoils nearby",
            "bare packed-earth court at an open-sided unpainted timber food shelter on Takamagahara",
        )
    if re.search(r"穢らわしい.*月読命.*怒り.*保食神.*斬り殺", narration):
        return (
            ["Tsukuyomi", "Uke Mochi"],
            "Single continuous packed-earth action beside a rough open timber shelter: white-blue-robed male Tsukuyomi raises one short straight leaf-shaped bronze double-edged blade with both hands toward earth-tone-robed female Uke Mochi recoiling one step, hands hidden in sleeves",
            "bare packed-earth court at an open-sided unpainted timber food shelter on Takamagahara",
        )
    if re.search(r"天照大御神.*月読命.*拒絶.*二度.*会わ", narration):
        return (
            ["Amaterasu", "Tsukuyomi"],
            "Amaterasu turns away in grief beneath one golden sun halo while Tsukuyomi stands isolated behind her under cold silver moonlight, two complete bodies separated by empty shadow, both hands inside long sleeves",
            "open cloud-lit Takamagahara threshold in Japanese creation myth",
        )
    if re.search(r"太陽.*月.*永遠.*別れ.*昼.*夜.*起源", narration):
        return (
            [],
            "Landscape-only continuous panorama where one blazing golden sun moves toward the far left horizon and one cold silver moon moves toward the far right horizon above a primordial mountain river, a broad twilight boundary permanently separating day from night; only sky, sun, moon, clouds, mountains, river water, natural rock, and plants are visible",
            "primordial natural landscape of mythic Japan",
        )
    if re.search(r"汚れ.*八十禍津日神.*厄災", narration):
        return (
            [],
            "Object-only view of one jagged black-red calamity light core rising from polluted river foam, dark ripples spreading across bare stones",
            "bare purification riverbank in primordial mythic Japan",
        )
    if re.search(r"慌て.*災い.*打ち消す.*善き.*神", narration):
        return (
            [],
            "Object-only view of exactly three separated white-gold light cores descending onto black river ripples and calming the water around them",
            "bare purification riverbank in primordial mythic Japan",
        )
    if re.search(r"神直毘神.*大直毘神.*浄化", narration):
        return (
            [],
            "Object-only view of exactly two bright white light cores pushing one black mist bank backward across the river surface",
            "bare purification riverbank in primordial mythic Japan",
        )
    if re.search(r"顔.*人間.*神.*最も.*神聖", narration):
        return (
            ["Izanagi"],
            "Extreme facial close-up of white-robed Izanagi after purification, calm eyes, natural face and neck, clear water beads reflecting soft gold light",
            "bare purification riverbank in primordial mythic Japan",
        )
    if re.search(r"古代.*光.*闇.*嵐.*起源", narration):
        return (
            [],
            "Object-only natural sky view with one golden sun disk, one silver moon disk and one blue-black storm spiral separated above a bare primordial river valley",
            "primordial natural landscape of mythic Japan",
        )
    if re.search(r"天照.*産み出し.*伊邪那岐.*喜び.*震", narration):
        return (
            ["Izanagi"],
            "Extreme facial close-up of white-robed Izanagi smiling with overwhelmed joy, tears at his eyes, golden sunlight on his face, hands outside the frame",
            "bare purification riverbank in primordial mythic Japan",
        )
    if re.search(r"伊邪那岐.*激怒.*泣いて.*息子.*呼び出", narration):
        return (
            ["Izanagi"],
            "Extreme facial close-up of older white-robed Izanagi, mouth visibly open in a shout toward his off-camera son, furious narrow eyes, high black topknot and pointed chin beard visible, face filling most of the frame, hands outside the frame",
            "bare primordial shore of the Japanese islands",
        )
    if re.search(r"亡くなった.*母親.*伊邪那美.*地下.*世界.*行きたい", narration):
        return (
            ["Izanami"],
            "Adult Izanami stands alone in cold Yomi shadow, mature East Asian face, long loose black hair and archaic earth-tone robe dimly visible through mist",
            "Yomi underworld in Japanese creation myth",
        )
    if re.search(r"黄泉.*母.*会いたく.*悲しく.*泣", narration):
        return (
            ["Susanoo"],
            "Adult Susanoo kneels alone on bare shore stones, wild shoulder-length black hair, earth-blue robe, head bowed as heavy tears fall",
            "bare primordial shore of the Japanese islands",
        )
    if re.search(r"父親.*伊邪那岐.*海.*治め.*須佐之男", narration):
        return (
            ["Izanagi"],
            "Waist-up side view of one white-robed Izanagi using one open pointing hand and one index finger at the real ocean, stern face addressing his off-camera son, other arm outside the frame",
            "bare primordial shore of the Japanese islands",
        )
    if re.search(r"彼.*仕事.*せず.*毎日.*泣き", narration):
        return (
            ["Susanoo"],
            "Adult Susanoo sits alone on shore stones in an earth-blue robe, shoulders collapsed, wild black hair hanging forward, crying toward the sea",
            "bare primordial shore of the Japanese islands",
        )
    if re.search(r"黄泉.*妻.*殺され.*トラウマ", narration):
        return (
            ["Izanagi"],
            "White-robed Izanagi recoils alone before the sealed black Yomi cave mouth, face rigid with trauma, cold mist and one cracked boundary stone behind him",
            "bare rocky boundary between Yomi underworld and the living world",
        )
    if re.search(r"チャンネル.*登録.*お願い", narration):
        return (
            [],
            "Landscape-only closing tableau of one golden sun disk, one silver moon disk and one blue storm spiral above the calm primordial river at dusk",
            "primordial natural landscape of mythic Japan",
        )
    if re.search(r"高評価.*次.*動画.*原動力", narration):
        return (
            [],
            "Landscape-only view of three small golden lights moving forward along a moonlit river path toward a bright horizon, bare stones and forest framing the route",
            "primordial natural landscape of mythic Japan",
        )
    if re.search(r"忌まわしい.*名前.*息子.*許す.*でき", narration):
        return (
            ["Izanagi"],
            "Extreme facial close-up of white-robed Izanagi in furious disbelief, jaw clenched, eyes hard, cold Yomi shadow reflected across one cheek, hands outside frame",
            "bare primordial shore of the Japanese islands",
        )
    return [], "", ""


def _humanize_sun_moon_object_scene(
    cut: dict[str, Any],
    script_context: str,
    names: list[str],
    scene: str,
    location: str,
) -> tuple[list[str], str, str]:
    """Keep the Uke Mochi episode narration-led instead of repeating artifact still lifes."""
    narration = str(cut.get("narration") or "")
    cut_number = _script_text_number(cut.get("cut_number"))
    if re.search(
        r"태양.*달.*영원히.*갈라|太陽.*月.*永遠.*別れ",
        script_context,
        re.IGNORECASE,
    ):
        closing_landscape_by_cut = {
            144: "Landscape-only closing view of one calm primordial river beneath a single continuous gold-to-silver twilight sky while one broad blue storm bank recedes at the far horizon; no person, celestial disk, spiral, circle, token, emblem, sign, writing, arranged object or artifact display",
            147: "Landscape-only empty primordial shore beneath a receding storm, one broad diffuse blue-grey light band fading naturally across wet sand toward distant mountains; no person, body part, footprint, track, sash, cloth, rope, narrow line, object or artifact display",
            148: "Landscape-only steep bare rocky ascent where one broad diffuse blue storm shadow climbs naturally across the whole slope toward a cloud-lit high plain; no person, body part, footprint, track, sash, rope, cable, narrow line, object or artifact display",
        }
        if cut_number in closing_landscape_by_cut:
            return (
                [],
                closing_landscape_by_cut[cut_number],
                "primordial natural landscape of mythic Japan",
            )
    if cut_number == 137 and re.search(
        r"宴|もてなし|食べ物|ご飯|魚|肉|盛り付|食べさせ|吐き出",
        narration,
        re.IGNORECASE,
    ):
        return (
            [],
            "Object-only close view of one small irregular arc of clean rice grains moving through empty air above bare packed soil, their source remaining outside the frame; no person, face, mouth, body part, garment, hand, fish, corpse, building, bowl, grid or object pile",
            "bare packed-earth court in primordial mythic Japan",
        )
    if not scene.startswith("Object-only") or not re.search(
        r"태양.*달.*영원히.*갈라|太陽.*月.*永遠.*別れ",
        script_context,
        re.IGNORECASE,
    ):
        return names, scene, location

    if re.search(r"次回.*荒ぶる.*弟.*太陽.*神.*激突", narration, re.IGNORECASE):
        return (
            ["Amaterasu", "Susanoo"],
            "Extreme macro inward profiles; adult woman Amaterasu at left faces strict right and adult man Susanoo at right faces strict left, their noses meet at center and eyes lock directly. Only eyes, noses, mouths and black hair occupy the frame; both chins extend below the bottom edge and black hair fills every corner",
            "open windswept Takamagahara ridge in Japanese creation myth",
        )
    if cut_number in {114, 125}:
        if cut_number == 125:
            return (
                [],
                "Landscape-only empty packed-earth path ending beside one plain shroud edge at the bottom frame and one fresh green shoot; no person, body, garment, limb, animal, object row or artifact display",
                "bare packed-earth court beside a newly fertile primordial field",
            )
        return (
            ["Messenger deity"],
            "Extreme hand-free face-only messenger stares downward, eyes wide and mouth open in shock and grief; face fills ninety percent, jawline crop, no object, body, garment or hands",
            "bare packed-earth court beside a newly fertile primordial field",
        )
    if cut_number == 107:
        return (
            ["Amaterasu"],
            "Extreme hand-free face-only Amaterasu at right looks left toward one cracked grain husk with one green shoot beside a plain shroud edge; jawline crop, no body, garment or hands",
            "newly fertile primordial field of mythic Japan",
        )
    if cut_number == 131:
        return (
            [],
            "Landscape-only one living green shoot rising beside one plain shroud edge while a cold silver moonlit band visibly recedes away across the bare soil; no person, face, body part, garment, hand, blade, ornament, arranged grid or artifact display",
            "newly fertile primordial field beneath cold moonlight",
        )
    if re.search(
        r"死|朽|奇跡|作物|動物|牛|馬|稲|粟|蚕|五穀|農耕|農業|食糧|豊か|恵み|犠牲|命.*(?:生み出|落)",
        narration,
        re.IGNORECASE,
    ):
        if cut_number == 108:
            return (
                ["Amaterasu"],
                "Face-only Amaterasu grieving at right; one green shoot and plain shroud edge at left; no body, garment or hands",
                "newly fertile primordial field of mythic Japan",
            )
        if cut_number == 110:
            return (
                ["Uke Mochi"],
                "Extreme hand-free face-only Uke Mochi lies still with eyes closed; pale mature face fills ninety percent, lower crop at jaw, loose dark hair and one plain shroud edge only, no body, garment, hands or feet",
                "bare packed-earth court beside a newly fertile primordial field",
            )
        if cut_number == 111:
            return (
                [],
                "Landscape-only famine threat across one broad barren primordial field: dry cracked soil and sparse withered grain reach an empty horizon beneath cold dim light, with no person, body, bowl, basket, token, emblem, building or arranged object",
                "barren primordial field of mythic Japan",
            )
        if cut_number == 116:
            return (
                [],
                "Object-only low close view of one plain earth-tone shroud mound as an irregular cluster of tiny fresh-green shoots rises along its edge; no body part, person, animal or artifact grid",
                "bare packed-earth court beside a newly fertile primordial field",
            )
        if cut_number == 118:
            return (
                [],
                "Object-only overhead view: irregular rice, millet and green shoots emerge naturally from soil beside one plain shroud edge; no body part, person, arranged row or artifact grid",
                "newly fertile primordial field of mythic Japan",
            )
        if cut_number == 120:
            return (
                [],
                "Landscape-only dawn close view of one vigorous green seedling rising beside a plain shroud edge as warm light replaces cold shadow; no person, body, token, emblem or artifact layout",
                "newly fertile primordial field of mythic Japan",
            )
        if cut_number == 133:
            return (
                ["Amaterasu"],
                "Extreme face-only close-up of adult Amaterasu looking downward at a small irregular patch of tiny two-leaf seedlings on distant wild soil, resolved realization as the first young crops are gathered below frame; complete mature face, plain center-parted hair and bare forehead",
                "newly fertile primordial field of mythic Japan",
            )
        fertile_scene_by_cut = {
            126: "Object-only low view of one plain shroud mound as one vigorous green shoot breaks through cracked soil in a natural shaft of dawn light; no person, body part, animal, garment, object row or artifact display",
            127: "Landscape-only distant silhouettes of exactly one cow and one horse standing beyond one plain shroud edge in dawn mist; no person, exposed body, extra animal, harness, building or artifact display",
            128: "Object-only close view of one millet panicle and one plain silk cocoon resting naturally beside one plain shroud edge; no person, body part, animal, bowl, row, grid or artifact display",
            129: "Object-only close view of exactly two separate plants divided by a wide bare-soil gap: one barnyard-millet panicle at left and one young rice seedling at right, beside one plain shroud edge; no person, body part, animal, bowl, row, grid or artifact display",
            130: "Landscape-only one plain shroud mound in a newly fertile field, irregular grain shoots at its edge and exactly one cow and one horse far in dawn mist; no person, exposed body, object row or artifact display",
            132: "Landscape-only broad newly fertile field where irregular green grain shoots spread naturally outward from one plain shroud mound under dawn light; no person, body part, animal, basket, arranged row or artifact display",
            140: "Landscape-only dawn field where living green grain shoots spread naturally beyond one dark shroud edge, with the separated gold-day and silver-night sky far behind; no person, body part, animal, basket, row or artifact display",
            146: "Landscape-only broad mixed field of rice, millet and other grains growing naturally from dark soil beside one low plain shroud edge at dawn; no person, body part, animal, basket, arranged grid or artifact display",
        }
        if cut_number in fertile_scene_by_cut:
            return (
                [],
                fertile_scene_by_cut[cut_number],
                "newly fertile primordial field of mythic Japan",
            )
        return (
            ["Messenger deity"],
            "Hand-free waist-up view of a solemn adult Japanese messenger deity kneeling beside Uke Mochi's fully covered earth-tone shroud as fresh grain shoots and distant cattle emerge, the grieving face dominant, both hands outside frame, non-graphic, no stone tokens, medallions or artifact grid",
            "newly fertile primordial field of mythic Japan",
        )
    if re.search(
        r"斬|剣|殺|血|残酷|惨劇|倒|遺体|最悪|戻|悲劇|傷跡|一刀",
        narration,
        re.IGNORECASE,
    ):
        if cut_number == 20:
            return (
                ["Uke Mochi", "Tsukuyomi"],
                "Extreme face-only two-shot at the instant welcome turns to dread: right adult woman Uke Mochi's warm sealed-lip smile fades as her eyes widen; left adult man Tsukuyomi recoils with a rigid jaw and disgusted eyes; only both complete faces and fully loose black hair fill the frame, with the lower edge at both jawlines",
                "bare packed-earth court at an open-sided unpainted timber food shelter",
            )
        if cut_number == 63:
            return (
                ["Tsukuyomi"],
                "Tsukuyomi holds one clean leaf-shaped bronze blade down; one red-stained wiping cloth is tied below its hilt",
                "bare primordial slope below Takamagahara",
            )
        if cut_number in {48, 49, 50, 58, 59, 62, 86, 99, 106}:
            return (
                ["Tsukuyomi"],
                "Hand-free three-quarter aftermath view of Tsukuyomi turning away from Uke Mochi's fully covered earth-tone shroud, his rigid expression and retreating posture dominant, both hands outside frame, one leaf-shaped aged-bronze ritual blade secondary, non-graphic, no blood pool or artifact layout",
                "bare packed-earth court at an open-sided unpainted timber food shelter",
            )
        if cut_number in {45, 46, 47, 57}:
            return (
                ["Tsukuyomi", "Uke Mochi"],
                "Hand-free three-quarter confrontation as Tsukuyomi steps forward with one straight leaf-shaped aged-bronze ritual blade low at his side while Uke Mochi recoils, both adult faces and separated postures dominant, both hands outside frame, non-graphic, long closed sleeves, no artifact layout",
                "bare packed-earth court at an open-sided unpainted timber food shelter",
            )
        return (
            ["Tsukuyomi", "Uke Mochi"],
            "Hand-free waist-up tense two-shot of Tsukuyomi recoiling in cold anger while Uke Mochi faces him in shocked restraint, expressions and separated postures dominant, both hands outside frame, one straight leaf-shaped aged-bronze double-edged ritual blade secondary, non-graphic, long closed sleeves, no artifact display",
            "bare packed-earth court at an open-sided unpainted timber food shelter",
        )
    if re.search(
        r"起源|喧嘩|感情|価値|対立|月.*太陽|コメント|応援|今回|どう.*感じ|意見|高評価|登録",
        narration,
        re.IGNORECASE,
    ):
        if cut_number == 104:
            return (
                ["Tsukuyomi"],
                "Extreme face-only Tsukuyomi close-up: his nose wrinkles, jaw clenches and eyes narrow as anger overwhelms restraint",
                "open primordial twilight riverbank in mythic Japan",
            )
        reflective_scene_by_cut = {
            136: "Landscape-only empty primordial river valley divided naturally between warm-gold daylight and cool silver-blue night; no person, body, garment, structure, emblem, sign, writing or artifact display",
            138: "Landscape-only one empty primordial river valley divided by a sharp natural twilight boundary, warm gold sunlight withdrawing left and cold silver moonlight withdrawing right; no person, face, body, garment, hand, structure, emblem, sign, writing or artifact display",
            141: "Landscape-only empty twilight river where a warm-gold reflection and a cool silver-blue reflection remain separated by one dark natural current; no person, body, garment, sign, writing or artifact display",
            142: "Landscape-only calm empty riverbank beneath one gold-to-silver twilight sky, open foreground soil left deliberately bare; no person, body, garment, paper, sign, writing, symbol or artifact display",
            143: "Landscape-only calm primordial river at twilight where one warm-gold reflection and one cool-silver reflection meet in a single empty frame; no person, body, garment, paper, sign, writing, symbol or artifact display",
        }
        if cut_number in reflective_scene_by_cut:
            return (
                [],
                reflective_scene_by_cut[cut_number],
                "open primordial riverbank divided by natural twilight in mythic Japan",
            )
        return (
            ["Amaterasu", "Tsukuyomi"],
            "Hand-free waist-up two-shot of Amaterasu and Tsukuyomi standing apart across a natural twilight boundary, opposing grief and rigid conviction carried by faces and posture, both hands outside frame, long closed sleeves, no emblem, token, sign, writing or artifact display",
            "open primordial riverbank divided by natural twilight in mythic Japan",
        )
    if re.search(
        r"宴|もてなし|食べ物|ご飯|魚|肉|盛り付|食べさせ|吐き出",
        narration,
        re.IGNORECASE,
    ):
        if cut_number in {27, 34}:
            return (
                ["Uke Mochi", "Tsukuyomi"],
                "Extreme face-only two-shot cropped at both jawlines; only faces and fully loose black hair fill the frame. Right adult woman Uke Mochi smiles with one sealed lip line. Left adult man Tsukuyomi has narrowed disbelieving eyes. Both have flat hair crowns and long loose hair flowing past the shoulders",
                "bare packed-earth court at an open-sided unpainted timber food shelter",
            )
        if cut_number == 51:
            return (
                ["Uke Mochi", "Tsukuyomi"],
                "Extreme macro face pair; only two enormous faces and fully loose black hair occupy the frame, with both chins extending below the bottom edge. Right adult woman Uke Mochi shows bright welcome: her eyes curve upward and both corners of her sealed lips rise. Left adult man Tsukuyomi has narrowed disgusted eyes and a tense closed mouth",
                "bare packed-earth court at an open-sided unpainted timber food shelter",
            )
        return (
            ["Uke Mochi", "Tsukuyomi"],
            "Tight face-dominant head-and-shoulders two-shot: Uke Mochi welcomes at right, Tsukuyomi recoils in disgust at left, both complete faces dominant",
            "bare packed-earth court at an open-sided unpainted timber food shelter",
        )
    return (
        ["Uke Mochi", "Tsukuyomi"],
        "Hand-free waist-up narration-led two-shot of Uke Mochi and Tsukuyomi in a tense exchange, both adult faces and contrasting reactions dominant, both hands outside frame, long closed sleeves, no object grid, symbolic token, writing or artifact display",
        location or "bare packed-earth court in primordial mythic Japan",
    )


def _apply_japanese_myth_cut_context(
    cut: dict[str, Any],
    active_names: list[str],
    script_context: str,
) -> list[str]:
    cut_number = _script_text_number(cut.get("cut_number"))
    existing_location = str(cut.get("visual_location") or "").strip()
    explicit_scene = str(cut.get("visual_scene") or "").strip()
    forced_visual_subject = _japanese_myth_generic_role_subject(explicit_scene)
    if re.search(
        r"\bUkemochi\s+lowered\s+at\s+left\b.*\bTsukuyomi\s+half-shadowed\s+at\s+right\b.*\boverturned\s+vessels\b",
        explicit_scene,
        re.IGNORECASE,
    ):
        explicit_scene = (
            "strict head-and-shoulders close-up of Tsukuyomi alone looking down at one overturned clay "
            "vessel rim small at the bottom edge, tense doubt in his face, exactly zero visible arms, "
            "hands or fingers; lower frame ends above both elbows"
        )
        cut["visual_scene"] = explicit_scene
    elif re.search(
        r"\bAmaterasu\s+seated\s+upright\s+at\s+center\b.*\bmessenger\s+kneeling\s+at\s+left\b",
        explicit_scene,
        re.IGNORECASE,
    ):
        explicit_scene = (
            "strict head-and-shoulders close-up of the adult messenger alone reporting in alarm inside "
            "a simple heavenly audience hall, speaking toward the unseen listener outside the frame, "
            "exactly zero visible arms, hands or fingers; lower frame ends above both elbows"
        )
        cut["visual_scene"] = explicit_scene
    elif re.search(
        r"\bmessenger\s+presenting\s+a\s+covered\s+basket\s+at\s+left\b.*\bAmaterasu\s+leaning\s+forward\b",
        explicit_scene,
        re.IGNORECASE,
    ):
        explicit_scene = (
            "strict head-and-shoulders close-up of Amaterasu alone looking down with a resolved gaze, "
            "the upper rim of one covered woven seed basket small at the bottom edge, exactly zero "
            "visible arms, hands or fingers; lower frame ends above both elbows"
        )
        cut["visual_scene"] = explicit_scene
    elif re.search(
        r"\bmessenger(?:'s)?\s+frightened\s+face\s+reflected\s+in\s+(?:a|the)\s+dark\s+clay\s+bowl\b",
        explicit_scene,
        re.IGNORECASE,
    ):
        explicit_scene = (
            "strict head-and-shoulders close-up of the adult messenger alone looking down in fear, "
            "one small dark clay bowl rim and fresh sprouts at the bottom edge, exactly zero visible "
            "hands or arms"
        )
        cut["visual_scene"] = explicit_scene
    elif re.search(
        r"\bthe\s+messenger\s+leaning\s+forward\b.*\btoward\s+sprouting\s+grains\b",
        explicit_scene,
        re.IGNORECASE,
    ):
        explicit_scene = (
            "strict head-and-shoulders close-up of the adult male messenger alone looking down with "
            "fearful concentration, one small clay vessel rim and several grain sprouts at the bottom "
            "edge, exactly zero visible arms, hands or fingers; lower frame ends above both elbows"
        )
        cut["visual_scene"] = explicit_scene
    elif re.search(
        r"\belder\s+storyteller\s+leaning\s+toward\s+several\s+grain\s+piles\b",
        explicit_scene,
        re.IGNORECASE,
    ):
        forced_visual_subject = (
            "exactly one elderly adult East Asian male storyteller, lined mature face, long plain "
            "black hair, bare forehead, plain unpatterned undyed plant-fiber tunic"
        )
        explicit_scene = (
            "strict head-and-shoulders view of exactly one elderly adult East Asian male storyteller "
            "inside one enclosed reed-mat timber hall, exactly zero visible arms, hands or fingers, "
            "with three separated grain piles small along the bottom edge and his lined face looking "
            "down seriously; lower frame ends above both elbows"
        )
        cut["visual_scene"] = explicit_scene
    if re.search(
        r"\bpale\s+cocoons\s+clustered\s+among\s+twig\s+frames\b",
        explicit_scene,
        re.IGNORECASE,
    ):
        explicit_scene = (
            "Object-only macro close-up of pale intact cocoons resting among dry twig frames in one "
            "flat woven tray on a cool reed-mat floor inside an enclosed silkworm room, soft indirect "
            "amber light from outside the frame, no flame, no fire, no smoke, no glowing coal, no people, "
            "no human body parts"
        )
        cut["visual_scene"] = explicit_scene
    if re.search(
        r"\bsealed\s+woven\s+seed\s+baskets?\s+under\s+a\s+raised-floor\s+granary\b",
        explicit_scene,
        re.IGNORECASE,
    ):
        explicit_scene = (
            "Object-only close-up of exactly one closed woven seed basket under a raised-floor granary, "
            "one fitted flat woven lid completely covers the basket opening, the basket interior and seeds "
            "are not visible, no second basket, no open basket, no people, no human body parts"
        )
        cut["visual_scene"] = explicit_scene
    if re.search(
        r"\bfolded\s+white\s+robe\s+on\s+reed\s+mats\b",
        explicit_scene,
        re.IGNORECASE,
    ):
        explicit_scene = (
            "Object-only straight overhead view of exactly one empty white robe folded into a compact flat "
            "rectangular stack on reed mats, crisp empty sleeve folds lie entirely inside the rectangle, "
            "bright rice shoots visible beyond one doorway, no body-shaped mound, no head, no face, no hands, "
            "no feet, no person"
        )
        cut["visual_scene"] = explicit_scene
    if re.search(
        r"\bwhite\s+robe\s+folded\s+where\s+Ukemochi\s+once\s+lay\b",
        explicit_scene,
        re.IGNORECASE,
    ):
        forced_visual_subject = ""
        explicit_scene = (
            "Landscape-only wide interior of one completely empty reed sleeping space, exactly one empty "
            "white robe folded into a compact flat rectangular stack against the far wall, faint rice shoots "
            "near one doorway, no body-shaped garment, no head, no face, no hand, no foot, no person"
        )
        cut["visual_scene"] = explicit_scene
    if re.search(
        r"\bview\s+from\s+an\s+empty\s+reed\s+mat\s+through\s+an\s+open\s+doorway\b",
        explicit_scene,
        re.IGNORECASE,
    ):
        explicit_scene = (
            "Landscape-only view from one completely empty bare reed-mat floor through an open doorway "
            "toward green paddy shoots, exactly one compact flat rectangular stack of white cloth lies in "
            "the far interior corner, no upright robe, no body-shaped garment, no person, no human body parts, "
            "no animal, no silkworm, no cocoon"
        )
        cut["visual_scene"] = explicit_scene
    if re.search(
        r"\brice\s+basket\s+beside\s+freshly\s+cut\s+mulberry\s+leaves\b",
        explicit_scene,
        re.IGNORECASE,
    ):
        explicit_scene = (
            "Object-only close-up of exactly one full woven rice basket and exactly one separate low pile of "
            "freshly detached mulberry leaves lying motionless on a field path, both objects fully visible with "
            "clear ground around every edge, no cropped body, no arm, no hand, no feet, no person, no animal, "
            "no silkworm, no cocoon"
        )
        cut["visual_scene"] = explicit_scene
    if re.search(
        r"\blow\s+close\s+view\s+of\s+rice\s+sprouts\s+standing\s+in\s+shallow\s+water\b",
        explicit_scene,
        re.IGNORECASE,
    ):
        explicit_scene = (
            "Landscape-only low close view of only young rice sprouts standing in shallow paddy water, "
            "split daylight reflected on the surface, no person, no human body parts, no animal, no silkworm, "
            "no cocoon, no basket, no building"
        )
        cut["visual_scene"] = explicit_scene
    if re.search(
        r"\brice\s+bowl\s+casting\s+a\s+long\s+shadow\s+shaped\s+by\s+a\s+folded\s+robe\b",
        explicit_scene,
        re.IGNORECASE,
    ):
        forced_visual_subject = ""
        explicit_scene = (
            "Object-only low close-up inside one enclosed reed-mat room: exactly one rough clay rice bowl "
            "in the foreground casts one long plain shadow toward exactly one compact flat rectangular stack "
            "of folded white cloth at the far wall, no upright robe, no body-shaped garment, no head, no face, "
            "no hand, no foot, no person"
        )
        cut["visual_scene"] = explicit_scene
    if re.search(
        r"\bsealed\s+clay\s+jars\s+beside\s+woven\s+seed\s+baskets\s+inside\s+a\s+raised-floor\s+granary\b",
        explicit_scene,
        re.IGNORECASE,
    ):
        forced_visual_subject = ""
        explicit_scene = (
            "Object-only closed interior of one raised-floor granary with exactly two sealed plain clay jars "
            "and exactly two closed woven seed baskets on one continuous wooden plank floor, narrow slatted "
            "light crosses the containers, all lids fully closed, no doorway, no outdoor view, no sea, no shore, "
            "no people, no human body parts"
        )
        cut["visual_scene"] = explicit_scene
    if re.search(
        r"\bworried\s+villager\s+at\s+a\s+granary\s+doorway\b",
        explicit_scene,
        re.IGNORECASE,
    ):
        explicit_scene = (
            "strict head-and-shoulders close-up of exactly one worried adult East Asian agrarian villager "
            "inside one closed raised-floor granary, gaunt face under cold slatted dawn light, two closed seed "
            "basket lids small along the bottom edge, exactly zero visible arms, hands or fingers, no doorway, "
            "no background person, no bystander"
        )
        cut["visual_scene"] = explicit_scene
    if re.search(
        r"\braised-floor\s+thatched\s+granary\b",
        explicit_scene,
        re.IGNORECASE,
    ):
        forced_visual_subject = ""
        explicit_scene = (
            "Landscape-only dramatic low exterior view of exactly one raised-floor thatched granary standing "
            "on tall plain timber posts above wind-bent night grass, exactly two closed seed baskets visible "
            "through narrow wall slats, dark inland field behind, no open room, no sea, no shore, no coast, "
            "no person, no animal"
        )
        cut["visual_scene"] = explicit_scene
    if re.search(
        r"\bplain\s+unmarked\s+stone\s+at\s+the\s+edge\s+of\s+a\s+lush\s+paddy\b",
        explicit_scene,
        re.IGNORECASE,
    ):
        forced_visual_subject = ""
        explicit_scene = (
            "Object-only low close-up of exactly one low irregular natural fieldstone lying flat and horizontal "
            "at the edge of a lush rice paddy, rice heads lean over its completely blank rough top surface, "
            "no upright stone, no monument, no carving, no inscription, no mark, no text, no symbol, no people"
        )
        cut["visual_scene"] = explicit_scene
    if re.search(
        r"\bfolded\s+white\s+robe\s+opposite\s+a\s+plain\s+blade\b",
        explicit_scene,
        re.IGNORECASE,
    ):
        forced_visual_subject = ""
        explicit_scene = (
            "Object-only straight overhead view inside one enclosed reed-mat room: exactly one empty white robe "
            "folded into a compact flat rectangular stack at left and exactly one plain sheathed blade at right, "
            "a narrow line of rice grains remains between them, no body-shaped garment, no head, no face, no hand, "
            "no foot, no person"
        )
        cut["visual_scene"] = explicit_scene
    if re.search(
        r"\bwhite\s+robe\s+edge\s+laid\s+beside\s+seeds\s+and\s+new\s+sprouts\b",
        explicit_scene,
        re.IGNORECASE,
    ):
        forced_visual_subject = ""
        explicit_scene = (
            "Object-only close-up of exactly one narrow flat strip of empty white woven cloth lying fully "
            "flat beside rice seeds and new sprouts in wet soil, one plain natural stone behind, no folded "
            "garment mound, no body shape, no head, no face, no hand, no foot, no person"
        )
        cut["visual_scene"] = explicit_scene
    if re.search(
        r"\bwhite\s+hemp\s+robe\s+folds\s+surrounded\s+by\s+rice\s+grains,\s*beans,\s*and\s+cocoons\b",
        explicit_scene,
        re.IGNORECASE,
    ):
        forced_visual_subject = ""
        explicit_scene = (
            "Object-only straight overhead view of exactly one empty white hemp cloth folded into a compact "
            "flat rectangular stack at center, with four small separated groups of rice grains, beans, cocoons "
            "and millet around it under one clay lamp, no body-shaped garment, no person, no human body parts"
        )
        cut["visual_scene"] = explicit_scene
    if re.search(
        r"\brice\s+bowl\s+on\s+a\s+reed\s+mat,\s*dark\s+shadow\s+of\s+a\s+folded\s+robe\b",
        explicit_scene,
        re.IGNORECASE,
    ):
        forced_visual_subject = ""
        explicit_scene = (
            "Object-only low close-up inside one enclosed reed-mat room: exactly one clay rice bowl in the "
            "foreground and exactly one compact flat rectangular stack of folded white cloth at the far wall, "
            "one plain dark cast shadow connects the two objects, no upright robe, no body-shaped garment, "
            "no person, no human body parts"
        )
        cut["visual_scene"] = explicit_scene
    if re.search(
        r"\bpale\s+cocoons\s+clustered\s+beside\s+the\s+shadow\s+of\s+a\s+white\s+robe\b",
        explicit_scene,
        re.IGNORECASE,
    ):
        forced_visual_subject = ""
        explicit_scene = (
            "Object-only close-up of pale cocoons clustered beside exactly one compact flat rectangular stack "
            "of folded white cloth on a reed mat, dark mulberry leaves remain separate around them, no upright "
            "robe, no body-shaped garment, no person, no human body parts"
        )
        cut["visual_scene"] = explicit_scene
    if re.search(
        r"\bdramatic\s+overhead\s+view\s+of\s+rice\s+grains\s+and\s+cocoons\s+placed\s+on\s+a\s+plain\s+wooden\s+platform\b",
        explicit_scene,
        re.IGNORECASE,
    ):
        forced_visual_subject = ""
        explicit_scene = (
            "Object-only straight overhead evidence layout on uninterrupted bare wooden planks: exactly one small "
            "flat pile of narrow pale rice grains at left, exactly one separate group of twenty thumb-sized smooth "
            "ivory oval silk cocoons with fine loose silk fibers at right, and exactly one compact flat rectangular "
            "stack of folded white woven cloth along the top edge, with clear bare wood gaps between all three groups, "
            "no potato, no tuber, no fruit, no stone, no silkworm, no mulberry branch, no body-shaped garment, "
            "no person, no people, no human body parts"
        )
        cut["visual_scene"] = explicit_scene
    if re.search(
        r"\bfull\s+rice\s+heads\s+swaying\s+before\s+a\s+dark\s+empty\s+reed\s+hall\b",
        explicit_scene,
        re.IGNORECASE,
    ):
        forced_visual_subject = ""
        explicit_scene = (
            "Landscape-only wide exterior field view under an open sky: full ripe golden rice fills the foreground "
            "and middle distance, with exactly one small closed dark reed hall beyond the rice at the far horizon, "
            "the camera remaining outside the hall, with no interior room, no interior wall, no interior floor, no "
            "ceiling, no foreground stone, no sack, no skull, no body shape, no figure, no person, no people, "
            "no human body parts, no animal, no silkworm, no cocoon, no marking, no text"
        )
        cut["visual_scene"] = explicit_scene
    if re.search(
        r"\b(?:Object-only\s+)?macro\s+cutaway-like\s+view\s+of\s+a\s+rice\s+seed\s+partly\s+buried\b",
        explicit_scene,
        re.IGNORECASE,
    ):
        forced_visual_subject = ""
        explicit_scene = (
            "Object-only extreme macro soil cross-section of exactly one intact natural rice seed embedded at the "
            "center of moist dark mud, exactly one short pale root descending from that same seed, and exactly one "
            "tiny fresh green shoot rising from it into a narrow band of shallow water at the top edge, with the seed, "
            "root, shoot, soil, and water filling the entire frame, no mature rice stalk, no tiller, no tall leaf "
            "cluster, no hand, no finger, no arm, no leg, no foot, no person, no people, no human body parts, "
            "no village, no building, no horizon, no second seed, no animal, no marking, no text"
        )
        cut["visual_scene"] = explicit_scene
    if re.search(
        r"\b(?:Object-only\s+)?close-up\s+of\s+a\s+bright\s+rice\s+sprout\s+breaking\s+through\s+dark\s+mud\b",
        explicit_scene,
        re.IGNORECASE,
    ):
        forced_visual_subject = ""
        explicit_scene = (
            "Object-only extreme macro soil-level view of exactly one intact natural rice seed half exposed in "
            "dark wet mud, exactly one tiny two-leaf fresh green sprout emerging from that same seed, and small old "
            "husk fragments touching only its base, with mud and a thin ring of shallow water filling the entire "
            "frame, no mature rice stalk, no tiller, no tall leaf cluster, no hand, no finger, no arm, no leg, "
            "no foot, no person, no people, no human body parts, no village, no building, no horizon, no second "
            "seed, no animal, no marking, no text"
        )
        cut["visual_scene"] = explicit_scene
    if re.search(
        r"\bmacro\s+view\s+of\s+one\s+rice\s+grain\s+resting\s+on\s+rough\s+wooden\s+granary\s+planks\b",
        explicit_scene,
        re.IGNORECASE,
    ):
        explicit_scene = (
            "Object-only extreme macro of exactly one raw unhulled rice seed filling sixty percent of the frame "
            "width on rough wooden granary planks, one narrow tapered pale hull with one lengthwise seam and fine "
            "husk ridges, no shadow, no basket, no bowl, no tray, no sack, no second grain, no people, no human "
            "body parts"
        )
        cut["visual_scene"] = explicit_scene
    if re.search(
        r"\boverhead\s+close-up\s+of\s+rice,\s*beans,\s*millet,\s*and\s*cocoons\b",
        explicit_scene,
        re.IGNORECASE,
    ):
        explicit_scene = (
            "Object-only overhead close-up of exactly four separated groups around one plain clay lamp: one "
            "rice pile, one bean pile, one millet pile, and one group of pale cocoons, all on one clean reed mat, "
            "no other food or object, no animal, no meat, no fish, no root vegetables, no people, no human body parts"
        )
        cut["visual_scene"] = explicit_scene
    person_prompt = re.split(
        r";\s*NARRATION\s+VISUAL\s+ALIGNMENT\b",
        str(cut.get("image_prompt") or ""),
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    cut_basis = " ".join(
        str(cut.get(key) or "")
        for key in (
            "narration",
            "image_prompt",
            "visual_subject",
            "visual_scene",
            "visual_location",
        )
    )
    named = (
        []
        if forced_visual_subject
        else _japanese_myth_named_identities(cut_basis)
    )
    if named:
        active_names = named[:3]

    override_names, override_scene, override_location = _japanese_myth_scene_override(
        cut,
        script_context,
    )
    override_names, override_scene, override_location = _humanize_sun_moon_object_scene(
        cut,
        script_context,
        override_names,
        override_scene,
        override_location,
    )
    if forced_visual_subject:
        override_names = []
        override_scene = explicit_scene
        override_location = ""
    if override_names:
        active_names = override_names
    scene_names = _japanese_myth_named_identities(explicit_scene)
    if (
        re.search(
            r"\b(?:heavenly\s+messenger|adult\s+messenger|the\s+messenger|messenger)\b",
            explicit_scene,
            re.IGNORECASE,
        )
        and "Messenger deity" not in scene_names
    ):
        scene_names.append("Messenger deity")
    explicit_zero_people = bool(
        re.search(
            r"\b(?:no\s+(?:visible\s+)?people|no\s+(?:visible\s+)?person|without\s+people|zero\s+people)\b",
            explicit_scene,
            re.IGNORECASE,
        )
    )
    if (
        explicit_zero_people
        and re.search(
            r"\b(?:paddy|rice\s+(?:rows?|shoots?|plants?)|field|mud|grove|mulberry\s+leaves?)\b",
            explicit_scene,
            re.IGNORECASE,
        )
        and not re.search(
            r"\b(?:silkworms?|cocoons?)\b",
            explicit_scene,
            re.IGNORECASE,
        )
    ):
        explicit_scene = explicit_scene.rstrip(" ,;.")
        explicit_scene += ", no animal, no silkworm, no cocoon"
        cut["visual_scene"] = explicit_scene
    absent_named_person_scene = bool(
        re.search(
            r"\bempty\b[^.;]{0,220}\bwhere\b[^.;]{0,100}\bonce\b",
            explicit_scene,
            re.IGNORECASE,
        )
    )
    if absent_named_person_scene or explicit_zero_people:
        scene_names = []
    scene_explicitly_nonhuman = bool(
        explicit_zero_people
        or (
            explicit_scene
            and not scene_names
            and not _JAPANESE_MYTH_PERSON_PROMPT_RE.search(explicit_scene)
        )
    )
    if scene_explicitly_nonhuman:
        override_names = []
        override_scene = explicit_scene
        override_location = ""
    explicit_nonhuman_override = bool(
        (override_scene and not override_names)
        or (not override_scene and scene_explicitly_nonhuman)
    )
    subject_names = (
        []
        if explicit_nonhuman_override
        else (override_names or scene_names or named)
    )
    person_basis = " ".join(
        str(value or "")
        for value in (
            cut.get("narration"),
            person_prompt,
            cut.get("visual_subject"),
            cut.get("visual_scene"),
        )
    )
    # Carry a previously introduced deity forward only when the current cut
    # itself names that identity.  The broad person-role regex also matches
    # global metadata such as "named deities" and was incorrectly turning
    # object/landscape cuts into portraits of the last active deity.
    current_named = _japanese_myth_named_identities(
        " ".join((str(cut.get("narration") or ""), person_prompt, explicit_scene))
    )
    if (
        not subject_names
        and not explicit_nonhuman_override
        and active_names
        and current_named
    ):
        subject_names = [name for name in active_names if name in current_named] or current_named[:3]

    modern_shrine_cut = bool(re.search(r"現代.*神社.*(?:禊|みそぎ).*ルーツ", str(cut.get("narration") or "")))
    ep7_modern_cut = bool(
        re.search(
            r"죽은\s*여신의\s*시신에서\s*피어난\s*생명|死んだ\s*女神.*(?:命|生命)",
            script_context,
            re.IGNORECASE,
        )
        and cut_number in {47, 48, 49, 50, 57, 58, 59, 78, 80, 82, 83, 84, 85, 95, 96, 97, 98, 99, 140, 142, 143, 144, 145}
    )
    modern_context_cut = modern_shrine_cut or ep7_modern_cut
    cut["visual_year"] = "present-day Japan" if modern_context_cut else "Japanese mythic creation era"
    cut["visual_period"] = (
        "modern Shinto purification ritual continuity"
        if modern_shrine_cut
        else "present-day Japanese cultural continuity"
        if ep7_modern_cut
        else "Kojiki and Nihon Shoki Japanese creation myth"
    )
    usable_existing_location = bool(
        existing_location
        and re.search(r"[A-Za-z]", existing_location)
        and "/" not in existing_location
    )
    local_location_basis = " ".join(
        str(value or "")
        for value in (
            cut.get("narration"),
            explicit_scene,
            _strip_visual_context_prefix(person_prompt),
        )
    )
    cut["visual_location"] = (
        override_location
        or (existing_location if usable_existing_location else "")
        or _japanese_myth_location(local_location_basis)
    )
    if modern_shrine_cut:
        cut["visual_evidence"] = "One modern temizu stone basin and one bamboo ladle show the narrated present-day ritual continuity."
    elif ep7_modern_cut:
        cut["visual_evidence"] = (
            "The present-day apartment meal and dining place directly show the narrated act of receiving life as food."
            if cut_number == 84
            else "The present-day Japanese people, clothing, place, and activity directly show the narrated living cultural continuity."
        )
    else:
        cut["visual_evidence"] = (
            "The visible action follows the narrated Japanese creation-myth moment and keeps named deities, "
            "primordial setting, and archaic ritual material culture consistent."
        )
    if forced_visual_subject:
        cut["visual_subject"] = forced_visual_subject
    elif subject_names:
        cut["visual_subject"] = _japanese_myth_identity_subject(subject_names)
    elif explicit_nonhuman_override:
        cut.pop("visual_subject", None)
    if scene_explicitly_nonhuman:
        if not explicit_zero_people:
            explicit_scene = explicit_scene.rstrip(" ,;.")
            explicit_scene += ", no people, no human body parts"
        object_focused_scene = bool(
            re.match(
                r"\s*(?:Object-only|(?:intense\s+)?close-up|tight\s+(?:close-up|view)|macro|overhead|"
                r"low\s+(?:close-up|view)|wide\s+(?:low|close-ground)\s+view)\b",
                explicit_scene,
                re.IGNORECASE,
            )
        )
        landscape_focused_scene = bool(
            re.match(
                r"\s*(?:Landscape-only|wide\s+(?:dawn|angled|natural|landscape)\s+view|"
                r"panoramic|distant\s+view)\b",
                explicit_scene,
                re.IGNORECASE,
            )
        )
        if object_focused_scene and not re.match(r"\s*Object-only\b", explicit_scene, re.IGNORECASE):
            explicit_scene = f"Object-only {explicit_scene}"
        elif landscape_focused_scene and not re.match(
            r"\s*Landscape-only\b",
            explicit_scene,
            re.IGNORECASE,
        ):
            explicit_scene = f"Landscape-only {explicit_scene}"
        elif explicit_zero_people and not re.match(
            r"\s*(?:Object-only|Landscape-only|Animal-only)\b",
            explicit_scene,
            re.IGNORECASE,
        ):
            explicit_scene = f"Landscape-only {explicit_scene}"
        cut["visual_scene"] = explicit_scene
        override_scene = explicit_scene
    if ep7_modern_cut:
        if cut_number in {78, 80, 82, 83, 85}:
            cut["visual_subject"] = "exactly three present-day adult Japanese family members in plain contemporary casual clothing"
        elif cut_number in {96, 97, 98, 99}:
            cut["visual_subject"] = "exactly one present-day adult Japanese woman in plain light-grey professional work clothing"
        elif cut_number in {142, 143, 144, 145}:
            cut["visual_subject"] = "exactly four present-day adult Japanese creators, exactly two women and exactly two men, with natural dark hair and plain contemporary clothing"
    elif re.search(
        r"죽은\s*여신의\s*시신에서\s*피어난\s*생명|死んだ\s*女神.*(?:命|生命)",
        script_context,
        re.IGNORECASE,
    ) and cut.get("visual_subject"):
        cut["visual_subject"] = re.sub(
            r",\s*(?:plain\s+unpatterned\s+pre-state\s+)?[^,;]*(?:wrap|robe)(?=\s*(?:;|$))",
            "",
            str(cut["visual_subject"]),
            flags=re.IGNORECASE,
        ).strip(" ,;")
    sun_moon_separation_episode = bool(
        re.search(
            r"태양.*달.*영원히.*갈라|太陽.*月.*永遠.*別れ",
            script_context,
            re.IGNORECASE,
        )
    )
    if cut_number == 133 and sun_moon_separation_episode:
        cut["visual_subject"] = (
            "exactly one adult female Amaterasu, East Asian face, plain center-parted long black hair, "
            "bare unadorned forehead, Japanese sun deity with one plain white woven crossed collar"
        )
    if cut_number == 34 and sun_moon_separation_episode:
        cut["visual_subject"] = (
            "exactly two adult Japanese deity faces: adult woman Uke Mochi, mature East Asian face, plain loose "
            "black hair, smooth bare forehead; adult man Tsukuyomi, mature East Asian face, long fully loose black "
            "hair, smooth bare forehead"
        )
    if cut_number == 51 and sun_moon_separation_episode:
        cut["visual_subject"] = (
            "exactly two adult Japanese deity faces: adult woman Uke Mochi, mature East Asian face, long plain "
            "fully loose black hair, smooth bare forehead; adult man Tsukuyomi, mature East Asian face, long plain "
            "fully loose black hair, smooth bare forehead"
        )
    if cut_number == 20 and re.search(
        r"ウケモチ.*歓迎.*宴.*(?:血塗|惨劇)",
        str(cut.get("narration") or ""),
        re.IGNORECASE,
    ):
        cut["visual_subject"] = (
            "exactly two adult Japanese deity faces: adult woman Uke Mochi, mature East Asian face, long plain "
            "fully loose black hair, smooth bare forehead; adult man Tsukuyomi, mature East Asian face, long plain "
            "fully loose black hair, smooth bare forehead"
        )
    if cut_number == 104 and re.search(
        r"怒り.*嫌悪.*感情.*コントロール",
        str(cut.get("narration") or ""),
        re.IGNORECASE,
    ):
        cut["visual_subject"] = (
            "exactly one adult male Tsukuyomi face, mature East Asian features, long fully loose black hair, "
            "smooth bare forehead"
        )
    if re.search(r"次回.*荒ぶる.*弟.*太陽.*神.*激突", str(cut.get("narration") or ""), re.IGNORECASE):
        cut["visual_subject"] = (
            "exactly two adult Japanese deity faces: adult woman Amaterasu, mature East Asian face, long straight "
            "black hair, smooth bare forehead; adult man Susanoo, mature East Asian face, wild shoulder-length "
            "black hair, smooth bare forehead"
        )
    if re.search(
        r"(?:ツクヨミ.*倒れた.*遺体.*見下ろ.*冷酷.*吐き捨て|汚らわしく.*気持ち.*悪い.*女神|あの.*女神.*口.*汚い.*私.*食べさせ|褒められる.*ツクヨミ.*予想外.*困惑|気高い.*行動.*なぜ.*悪神)",
        str(cut.get("narration") or ""),
    ):
        cut["visual_subject"] = (
            "exactly one adult male Tsukuyomi, East Asian face, plain low-tied long black hair, "
            "smooth bare unadorned forehead, Japanese moon deity in an archaic plain white-blue robe"
        )
    if re.search(
        r"太陽.*女神.*驚き.*凄まじい.*激怒",
        str(cut.get("narration") or ""),
    ):
        cut["visual_subject"] = (
            "exactly one adult female Amaterasu, East Asian face, plain center-parted long straight black hair, "
            "bare unadorned forehead, Japanese sun deity in an archaic white-gold wide-sleeve robe"
        )
    if re.search(
        r"同じ.*場所.*許せない.*拒絶",
        str(cut.get("narration") or ""),
    ):
        cut["visual_subject"] = (
            "exactly one adult female Amaterasu, East Asian face, plain center-parted long straight black hair, "
            "bare unadorned forehead, Japanese sun deity in an archaic white-gold robe"
        )
    if re.search(
        r"その.*命.*奪った.*弟.*決して.*許さなかった",
        str(cut.get("narration") or ""),
    ):
        cut["visual_subject"] = (
            "exactly one adult female Amaterasu, East Asian face, plain center-parted long straight black hair, "
            "bare unadorned forehead, Japanese sun deity in an archaic white-gold wide-sleeve robe"
        )
    if re.search(
        r"ウケモチ.*斬り殺した.*弟.*激怒.*永遠.*離縁.*アマテラス",
        str(cut.get("narration") or ""),
    ):
        cut["visual_subject"] = (
            "exactly one adult female Amaterasu, East Asian face, plain center-parted long straight black hair, "
            "bare unadorned forehead, Japanese sun deity in an archaic white-gold robe"
        )
    if re.search(
        r"アマテラス.*地上.*殺された.*ウケモチ.*遺体.*心配",
        str(cut.get("narration") or ""),
    ):
        cut["visual_subject"] = (
            "exactly one adult female Amaterasu, East Asian face, plain center-parted long straight black hair, "
            "bare unadorned forehead, Japanese sun deity in an archaic white-gold robe"
        )
    if override_scene:
        cut["visual_scene"] = override_scene
    return active_names


def _repair_ch3_ep10_visual_scene(
    cut: dict[str, Any],
    script_context: str,
) -> None:
    """Replace the known symbolic EP10 prompts with concrete myth scenes.

    EP10 was prepared with abstract poster/still-life language (exclamation
    marks, crowns, maps, theatre curtains and mirror effects).  Those tokens
    produce repetitive or modern-looking images, so keep the source script
    intact and repair the scene contract at runtime before generation.
    """
    if not re.search(r"CH3_C1_EP010|EP\.10|하늘을\s*피로\s*물들인\s*난동", script_context, re.IGNORECASE):
        return
    number = _script_text_number(cut.get("cut_number"))
    if number is None or not 61 <= number <= 150:
        return

    person = {
        "amaterasu": (
            "exactly one adult female Amaterasu, mature East Asian face, plain center-parted long black hair, "
            "bare forehead, archaic white woven robe with restrained red trim"
        ),
        "susanoo": (
            "exactly one adult male Susanoo, mature East Asian face, wild shoulder-length black hair, "
            "bare forehead, rough undyed warrior robe"
        ),
        "omoi": (
            "exactly one adult male Omoikane, mature East Asian face, long plain black hair, "
            "bare forehead, plain undyed robe"
        ),
        "uzume": (
            "exactly one adult female Ame-no-Uzume, mature East Asian face, long black hair tied simply, "
            "plain white woven robe with red sash"
        ),
    }
    scenes: dict[int, tuple[str, str | None, str]] = {
        61: ("Object-only close view of one plain white woven ritual cloth spread on a rough wooden loom, one dark red stain soaking into the fibers, no person, no human body parts", None, "heavenly weaving hut in Takamagahara"),
        62: ("Object-only close view of the same white woven ritual cloth hanging from the loom with several dark red stains running through the threads, no person, no human body parts", None, "heavenly weaving hut in Takamagahara"),
        63: ("Amaterasu stands inside the weaving hut and recoils from the blood-stained cloth, her face shocked, the loom and scattered white fibers visible behind her", person["amaterasu"], "heavenly weaving hut in Takamagahara"),
        64: ("Amaterasu remains frozen beside the loom after the disaster, staring toward the open doorway where her brother has fled, scattered fibers on the reed floor", person["amaterasu"], "heavenly weaving hut in Takamagahara"),
        65: ("Amaterasu sits rigidly beside the damaged loom, her expression collapsing with grief while the blood-stained cloth hangs behind her, no mirror, no symbol", person["amaterasu"], "heavenly weaving hut in Takamagahara"),
        66: ("Object-only view of a horse carcass with its hide removed lying on a rough reed mat beside the loom, rendered non-graphically with no visible gore, no person", None, "heavenly weaving hut in Takamagahara"),
        67: ("Object-only close view of the horse hide laid inside out beside a broken loom beam and torn white fibers, a plain archaic ritual workspace, no writing, no person", None, "heavenly weaving hut in Takamagahara"),
        68: ("Susanoo stands in the doorway of the weaving hut after the violent act, shoulders tense and face defiant, the damaged loom visible behind him", person["susanoo"], "heavenly weaving hut in Takamagahara"),
        69: ("A single weaving woman lies motionless beside the overturned loom, shown from a distant respectful angle with the face obscured by cloth, no graphic gore, no other person", "exactly one adult Japanese weaving woman in a plain undyed plant-fiber robe", "heavenly weaving hut in Takamagahara"),
        70: ("Amaterasu kneels beside the fallen weaving woman and reaches toward the blood-stained floor, her face trembling with horror, the overturned loom behind her", person["amaterasu"], "heavenly weaving hut in Takamagahara"),
        71: ("Amaterasu kneels alone beside the spreading dark stain and torn white cloth, head lowered in guilt, the empty loom behind her, no punctuation or symbol", person["amaterasu"], "heavenly weaving hut in Takamagahara"),
        72: ("Amaterasu stands beside the broken loom with her shoulders lowered, her authority and affection visibly shattered, plain reed walls and torn cloth around her", person["amaterasu"], "heavenly weaving hut in Takamagahara"),
        73: ("Tight portrait of Amaterasu staring toward the doorway in fear and despair, wet eyes and rigid posture, the damaged weaving hut softly visible behind her", person["amaterasu"], "heavenly weaving hut in Takamagahara"),
        74: ("Amaterasu turns away from the weaving hut toward the dark open path, fear replacing anger, her full figure visible against the reed doorway", person["amaterasu"], "heavenly weaving hut in Takamagahara"),
        75: ("Amaterasu leaves the heavenly weaving hut alone along a rough stone path, white robe trailing behind her, storm clouds gathering over Takamagahara", person["amaterasu"], "stone path between heavenly halls in Takamagahara"),
        76: ("Landscape-only wide view of the enormous natural cliff containing Ama-no-Iwato, a dark cave mouth above a narrow mountain path, no person", None, "mountain cliff of Ama-no-Iwato"),
        77: ("Object-only close view of the rough circular stone door of Ama-no-Iwato filling the cave entrance, deep darkness behind the sealed gap, no writing, no person", None, "entrance of Ama-no-Iwato"),
        78: ("Amaterasu steps into the dark cave of Ama-no-Iwato, her white robe catching the last warm light at the threshold, one huge stone door behind her", person["amaterasu"], "entrance of Ama-no-Iwato"),
        79: ("Amaterasu braces both hands against the massive stone door and pulls it shut from inside the cave, her face resolved, no other person", person["amaterasu"], "inside Ama-no-Iwato"),
        80: ("Landscape-only wide exterior of Ama-no-Iwato sealed beneath a darkening sky, the mountain path empty and the cave mouth completely closed by stone, no stage or curtain, no person", None, "mountain cliff of Ama-no-Iwato"),
        81: ("Landscape-only wide view of Takamagahara as daylight fades across the heavenly plain, smoke-blue clouds replacing the sun, no map, no writing, no person", None, "heavenly plain of Takamagahara"),
        82: ("Landscape-only wide view from the heavenly plain toward the darkened reed fields below, the last daylight disappearing over the horizon, no map, no sun-face, no person", None, "Takamagahara overlooking the earthly reed plain"),
        83: ("Landscape-only view of the same plain under continuous night, a cold blue-black sky above silent fields with no visible horizon light, no person", None, "earthly reed plain beneath Takamagahara"),
        84: ("Landscape-only close view of rice and reed plants bending under sudden cold darkness, frost forming on the leaves and shallow water going still, no glass or crystals, no person", None, "cold field on the earthly reed plain"),
        85: ("Landscape-only wide view of withered plants and dark empty paddies under a starless sky, broken stems and frozen soil show life stopping, no person", None, "earthly reed plain"),
        86: ("Amaterasu stands at the ruined weaving hut while Susanoo remains in the doorway behind her, their distance and opposing postures show the aftermath, no weapons raised", person["amaterasu"] + "; " + person["susanoo"], "heavenly weaving hut in Takamagahara"),
        87: ("Object-only close view framed from the waist-high loom upward: one empty wooden loom with torn white cloth hanging from the beam and one small dark stain on the cloth, the floor and any body completely outside the frame, no person, no human figure, no body, no graphic gore", None, "heavenly weaving hut in Takamagahara"),
        88: ("Amaterasu sits alone beside the sealed cave path, face lowered with guilt and grief, the rough stone entrance behind her, no mirror, no halo", person["amaterasu"], "outside Ama-no-Iwato"),
        89: ("Amaterasu walks into Ama-no-Iwato carrying no object, her back receding into the cave as the stone door begins to close, no other person", person["amaterasu"], "entrance of Ama-no-Iwato"),
        90: ("Landscape-only wide view of the enormous natural rock cavern entrance of Ama-no-Iwato in a sheer cliff, dark opening and rough stone, no building, no person", None, "mountain cliff of Ama-no-Iwato"),
        91: ("Amaterasu disappears into Ama-no-Iwato as the massive stone door closes across the cave mouth, one narrow strip of daylight remains, no other person", person["amaterasu"], "inside Ama-no-Iwato"),
        92: ("Landscape-only wide view of the sealed stone entrance of Ama-no-Iwato beneath a dark sky, an empty mountain path in front, no curtain, no stage, no person", None, "mountain cliff of Ama-no-Iwato"),
        93: ("Landscape-only wide view of the heavenly plain after the sun goddess vanishes, cold clouds spreading over the reed fields, no person", None, "heavenly plain of Takamagahara"),
        94: ("Landscape-only wide view from the dark heavenly plain down to the earthly fields, both horizons swallowed by blue-black night, no red sun, no map, no person", None, "Takamagahara overlooking the earthly reed plain"),
        95: ("Landscape-only close view of frozen paddies and brittle dead plants under a lightless sky, frost coating the leaves, no person", None, "earthly reed plain"),
        96: ("Landscape-only wide view of abandoned ancient rice fields with cracked soil and empty granaries in the distance, the harvest lost, no person", None, "ancient farming plain below Takamagahara"),
        97: ("Landscape-only night view of dark birds and moths circling above a deserted field while low storm clouds gather, natural animals only, no demons, no person", None, "earthly reed plain"),
        98: ("Exactly six adult Japanese deities gather in alarm around a small open fire on a riverbank, each looking in a different direction, no crowd beyond them", "exactly six adult Japanese deities in plain undyed robes", "Amano-Yasukawara riverbank"),
        99: ("Susanoo stands alone beside the damaged weaving hut and broken loom, the darkened plain behind him showing the scale of the aftermath, no symbol", person["susanoo"], "heavenly weaving hut in Takamagahara"),
        100: ("Exactly six adult Japanese deities sit in a tense council around a low ring of natural stones, an empty cave path behind them, no writing or scrolls", "exactly six adult Japanese deities in plain undyed robes", "Amano-Yasukawara riverbank"),
        101: ("Landscape-only wide view of dead paddies, dark clouds, abandoned reed huts and a distant sealed cave, a grounded ancient apocalypse, no text, no person", None, "ancient plain below Takamagahara"),
        102: ("Exactly six adult Japanese deities react to a sudden cold wind and smoke-dark sky on a barren riverbank, several point toward the sealed cave, no symbol", "exactly six adult Japanese deities in plain undyed robes", "Amano-Yasukawara riverbank"),
        103: ("Landscape-only view combining one dark storm front, frozen rice plants and a dry riverbed in one continuous ancient landscape, no diagram, no boxes, no writing, no person", None, "ancient plain below Takamagahara"),
        104: ("Landscape-only view of a natural partial solar eclipse above the ancient Japanese plain, the sun partly covered by the moon, no face, no calendar, no writing, no person", None, "ancient plain below Takamagahara"),
        105: ("Exactly five adult ancient Japanese villagers stand in a field looking upward at a natural partial solar eclipse, plain plant-fiber robes, no modern objects", "exactly five adult ancient Japanese villagers in plain plant-fiber robes", "ancient rice field below Takamagahara"),
        106: ("Exactly five adult villagers huddle beside a low fire beneath an eclipsed dark sky, their faces fearful but natural, no exclamation mark, no person beyond the group", "exactly five adult ancient Japanese villagers in plain plant-fiber robes", "ancient rice field below Takamagahara"),
        107: ("Landscape-only wide view of a winter plain with a low pale sun setting early, bare reeds and long blue shadows, no calendar, no writing, no person", None, "ancient winter plain below Takamagahara"),
        108: ("Landscape-only view of a frozen field at winter solstice twilight, the last weak daylight at the horizon and frost on the soil, no calendar, no person", None, "ancient winter plain below Takamagahara"),
        109: ("Object-only overhead view of exactly one unhulled rice seed lying alone on a flat frost-covered natural stone, clear empty ground surrounds it on every side, no hand, no arm, no sleeve, no person, no living thing, no writing, no symbol", None, "frozen ancient rice field"),
        110: ("Susanoo stands beside a broken loom beam and scattered reed fibers while the dead fields recede behind him, the destructive act made concrete, no symbol", person["susanoo"], "heavenly weaving hut in Takamagahara"),
        111: ("Exactly six adult Japanese deities walk toward the Amano-Yasukawara riverbank carrying no weapons, storm clouds and the sealed cave behind them, no crowd", "exactly six adult Japanese deities in plain undyed robes", "path beside Amano-Yasukawara"),
        112: ("A group of adult Japanese deities gathers along the rocky Amano-Yasukawara riverbank, some kneeling and some standing in discussion, no writing or banners", "exactly eight adult Japanese deities in plain undyed robes", "Amano-Yasukawara riverbank"),
        113: ("Exactly six adult Japanese deities stand before the sealed stone entrance of Ama-no-Iwato, looking toward it with determined faces, no person inside the cave", "exactly six adult Japanese deities in plain undyed robes", "entrance of Ama-no-Iwato"),
        114: ("Omoikane kneels beside a low ring of stones and gestures toward the cave entrance while five other deities listen, no scroll, no writing, no diagram", person["omoi"] + "; five other adult Japanese deities in plain undyed robes", "Amano-Yasukawara riverbank"),
        115: ("Exactly six adult Japanese deities exchange ideas around a small fire beside the sealed cave, one points toward a simple drum and another toward the dark doorway, no question mark, no writing", "exactly six adult Japanese deities in plain undyed robes", "entrance of Ama-no-Iwato"),
        116: ("Ame-no-Uzume begins a bold dance on the flat ground before Ama-no-Iwato while several deities watch from behind her, torches and rough stones only", person["uzume"], "entrance of Ama-no-Iwato"),
        117: ("Ame-no-Uzume dances beside a low wooden drum as the gathered deities clap and laugh near the sealed cave, natural faces and archaic robes, no modern stage", person["uzume"] + "; several adult Japanese deities in plain undyed robes", "entrance of Ama-no-Iwato"),
        118: ("Landscape-only wide view of the sealed cave, a ring of torchlight and distant figures gathering outside, rough cliff and dark sky, no text, no person in foreground", None, "mountain cliff of Ama-no-Iwato"),
        119: ("Landscape-only view of an empty mountain path leading from the darkened fields to Ama-no-Iwato, torchlight beginning near the cave, no person in foreground", None, "path to Ama-no-Iwato"),
        120: ("Susanoo stands beside the abandoned loom and the blood-stained cloth after his violent prank, head lowered as the dark world stretches behind him, no mirror, no text", person["susanoo"], "heavenly weaving hut in Takamagahara"),
        121: ("A single weaving woman lies motionless beside the overturned loom, shown from a distant respectful angle with the face covered by white cloth, no graphic gore, no other person", "exactly one adult Japanese weaving woman in a plain undyed plant-fiber robe", "heavenly weaving hut in Takamagahara"),
        122: ("Amaterasu stands at the doorway of the weaving hut looking down at the covered fallen weaver, the damaged loom and white cloth visible, no graphic gore", person["amaterasu"], "heavenly weaving hut in Takamagahara"),
        123: ("Amaterasu sits alone on a rough stone outside the weaving hut, face lowered in fear and guilt, the sealed cave path behind her, no mirror, no symbol", person["amaterasu"], "path between Takamagahara and Ama-no-Iwato"),
        124: ("Landscape-only wide view of Ama-no-Iwato towering above a narrow path as Amaterasu approaches the cave mouth, no other person", None, "mountain cliff of Ama-no-Iwato"),
        125: ("Amaterasu pulls the huge stone door shut from inside Ama-no-Iwato, both hands on the rough stone and only a thin line of daylight remaining, no other person", person["amaterasu"], "inside Ama-no-Iwato"),
        126: ("Landscape-only wide view of the heavenly plain and its reed halls beneath a continuous black sky after the sun vanishes, no person", None, "heavenly plain of Takamagahara"),
        127: ("Landscape-only wide view of darkened earthly fields, empty paths and cold water channels under a starless sky, no person", None, "earthly reed plain"),
        128: ("Landscape-only close view of rice plants frozen and bent into the mud, pale frost on every leaf, no glass, no crystals, no person", None, "cold rice field below Takamagahara"),
        129: ("Landscape-only wide view of abandoned farm plots and a silent raised-floor granary under darkness, cracked soil in the foreground, no person", None, "ancient farming plain"),
        130: ("Exactly five adult villagers sit weakly around a small fire in a dark field while moths circle the smoke, plain ancient robes, no demons, no modern objects", "exactly five adult ancient Japanese villagers in plain plant-fiber robes", "ancient farming plain"),
        131: ("Exactly eight adult Japanese deities hold a desperate council around a low fire beside the river, faces turned toward Omoikane, no writing or scrolls", "exactly eight adult Japanese deities in plain undyed robes", "Amano-Yasukawara riverbank"),
        132: ("Omoikane kneels at the center of a circle of deities and points from the sealed cave to a plain wooden drum, the others listen, no diagram, no writing", person["omoi"] + "; seven other adult Japanese deities in plain undyed robes", "entrance of Ama-no-Iwato"),
        133: ("Ame-no-Uzume practices a lively dance beside a wooden drum while the gathered deities prepare torches outside Ama-no-Iwato, no stage, no text", person["uzume"] + "; several adult Japanese deities in plain undyed robes", "entrance of Ama-no-Iwato"),
        134: ("Several adult Japanese deities share a simple archaic feast of rice, clay cups and drums outside the sealed cave, the stone door visible behind them, no modern objects", "exactly eight adult Japanese deities in plain undyed robes", "entrance of Ama-no-Iwato"),
        135: ("Landscape-only wide view of the natural cliff and sealed stone door of Ama-no-Iwato at dusk, torchlight from the distant gathering below, no text, no person in foreground", None, "mountain cliff of Ama-no-Iwato"),
        136: ("Landscape-only view of a natural partial solar eclipse above a dark ancient plain, cold clouds and a fading horizon, no face, no map, no writing, no person", None, "ancient plain below Takamagahara"),
        137: ("Exactly six adult Japanese deities stand in stunned silence on the dark riverbank while the sealed cave and black sky loom behind them, no symbol", "exactly six adult Japanese deities in plain undyed robes", "Amano-Yasukawara riverbank"),
        138: ("Amaterasu sits alone deep inside Ama-no-Iwato with her back to the stone wall, knees drawn close and face lowered, one faint strip of cave light, no halo", person["amaterasu"], "inside Ama-no-Iwato"),
        139: ("Exactly one elderly Japanese storyteller sits on a plain woven mat beneath a broad tree in an open mountain clearing, speaking to unseen listeners around one clay lamp, no building, no sign, no banner, no writing, no modern objects", "exactly one elderly adult Japanese male storyteller in a plain undyed robe", "open mountain clearing"),
        140: ("Exactly two elderly Japanese storytellers sit across from each other in a torchlit reed hall, listening seriously, plain ancient robes, no writing, no modern objects", "exactly two elderly adult Japanese storytellers in plain undyed robes", "torchlit reed-mat hall"),
        141: ("Landscape-only view of a quiet torchlit reed hall after the story, an empty woven mat and clay lamp in the foreground, no writing, no person", None, "torchlit reed-mat hall"),
        142: ("Exactly four adult Japanese listeners sit around a low clay lamp inside a completely bare, unmarked reed-mat hall, attentive faces and plain ancient robes, no banners, no hanging strips, no painted signs, no writing, no modern objects", "exactly four adult Japanese listeners in plain undyed robes", "bare torchlit reed-mat hall"),
        143: ("Exactly eight adult Japanese deities walk together toward Ama-no-Iwato carrying torches and one plain wooden drum, the dark fields behind them, no banners", "exactly eight adult Japanese deities in plain undyed robes", "path to Ama-no-Iwato"),
        144: ("Ame-no-Uzume performs a comic but dignified dance directly before the sealed stone door while the gathered deities watch, one wooden drum, no stage, no modern costume", person["uzume"], "entrance of Ama-no-Iwato"),
        145: ("Several adult Japanese deities laugh openly around Ame-no-Uzume as she dances beside the drum, the sealed cave behind them, natural faces, no modern stage", person["uzume"] + "; several adult Japanese deities in plain undyed robes", "entrance of Ama-no-Iwato"),
        146: ("A circle of adult Japanese deities performs a torchlit ritual dance around Ame-no-Uzume outside the sealed cave, archaic robes and wooden drum, no text", person["uzume"] + "; several adult Japanese deities in plain undyed robes", "entrance of Ama-no-Iwato"),
        147: ("Ame-no-Uzume dances beside a simple wooden drum while villagers and deities clap around a natural stone clearing, early ritual performance, no shrine building, no text", person["uzume"] + "; adult Japanese villagers and deities in plain undyed robes", "natural stone clearing before Ama-no-Iwato"),
        148: ("Landscape-only view of torches, a wooden drum and dancing silhouettes breaking the darkness at the cave entrance, the rough stone door behind them, no person in foreground", None, "entrance of Ama-no-Iwato"),
        149: ("Ame-no-Uzume and the gathered deities continue their torchlit dance outside Ama-no-Iwato, the sealed stone door and dark field framing the celebration, no text", person["uzume"] + "; several adult Japanese deities in plain undyed robes", "entrance of Ama-no-Iwato"),
        150: ("Landscape-only dawn view of Ama-no-Iwato and the torchlit gathering outside, the natural cliff and sealed stone door fill the frame, no text, no person in foreground", None, "mountain cliff of Ama-no-Iwato"),
    }
    scene, subject, location = scenes[number]
    cut["visual_scene"] = scene
    cut["visual_location"] = location
    if subject:
        cut["visual_subject"] = subject
    else:
        cut.pop("visual_subject", None)


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


def uses_source_locked_visual_policy(script: Any) -> bool:
    return bool(
        isinstance(script, dict)
        and str(script.get("visual_policy_mode") or "").strip().lower()
        == SOURCE_LOCKED_VISUAL_POLICY_MODE
    )


_CH4_IMAGE_CONTEXTS = {
    "1233년": (
        "1233 AD, 13th-century Catholic Western Europe",
        "Western Europe",
        "Western European features and period-accurate 13th-century dress",
    ),
    "897년": (
        "897 AD, late 9th-century Papal Rome",
        "Basilica of Saint John Lateran and the Papal court in Rome, Italy",
        "Western European and Italian features with period-accurate Roman Catholic dress for each source-named person",
    ),
    "1522년": (
        "1522 AD, early 16th-century France at the late medieval-Renaissance transition",
        "ecclesiastical court in Autun, Burgundy, France",
        "Western European French features with early modern French dress for each source-named person",
    ),
    "1692년": (
        "1692 AD, late 17th-century Puritan Massachusetts Bay Colony",
        "Salem village court, Massachusetts Bay Colony, English America",
        "English colonial European features with 17th-century Puritan dress for each source-named person",
    ),
    "855년경": (
        "circa 855 AD, mid-9th-century Papal Rome",
        "Papal Rome, Italy, near Saint Peter's Basilica procession street",
        "Western European and Italian features with 9th-century Roman Catholic dress for each source-named person",
    ),
}


def _ch4_image_generation_context(year: str, period: str, location: str) -> tuple[str, str, str, str]:
    """Translate the four registered CH4 workbook settings for image models."""
    source = " ".join((year or "", period or "", location or ""))
    for marker, (english_year, english_place, casting) in _CH4_IMAGE_CONTEXTS.items():
        if marker in source:
            return english_year, "", english_place, casting
    return year, period, location, ""


def _spoken_dialogue_direction(cut: dict[str, Any]) -> str:
    speaker = str(cut.get("speaker") or "").strip()
    if not speaker or speaker.casefold() in {"해설자", "narrator", "narration"}:
        return ""
    return (
        "the named speaking character is visibly delivering this line mid-sentence, "
        "with parted lips, active facial expression, and natural speaking posture; "
        "the speaker remains the dominant focal subject and the full facial expression stays clearly readable"
    )


_EMOTION_VISUAL_TAG_ORDER = (
    "crying",
    "angry",
    "sorrowful",
    "worried",
    "happily",
    "sarcastic",
    "mischievously",
    "curious",
    "thoughtful",
    "dramatic",
    "flatly",
    "shouts",
    "stammers",
    "whispers",
    "questioning",
    "sighs",
    "booming",
    "softly",
    "quietly",
    "rushed",
    "slowly",
)


_CHARACTER_EMOTION_VISUAL_CUES = {
    "angry": "deeply furrowed brows, hard focused eyes, a tense jaw, and forceful posture",
    "booming": "commanding chest-open posture and emphatic projected delivery",
    "crying": (
        "two clearly visible continuous wet tear streams running from both lower eyelids down both cheeks "
        "and catching the light, reddened glossy eyes, pinched tearful brows, and a trembling face"
    ),
    "curious": "a clearly raised brow, searching eyes, and attentive forward focus",
    "dramatic": "grave high-stakes tension in the eyes, face, and decisive body posture",
    "flatly": "a controlled unreadable face, steady eyes, and deliberately restrained posture",
    "happily": "a clearly visible warm smile, bright eyes, and relaxed open posture",
    "mischievously": "a sly side glance and restrained knowing half-smile",
    "questioning": "raised brows, a searching gaze, and a visibly questioning expression",
    "quietly": "restrained low-intensity body language and close attentive focus",
    "rushed": "urgent forward motion, breathless tension, and quick reactive body language",
    "sarcastic": "one skeptical raised brow, narrowed eyes, and a tight asymmetric half-smile",
    "shouts": "a mouth clearly open mid-shout, engaged jaw and throat, and a forceful outward gesture",
    "sighs": "a visible exhale, lowered shoulders, and a weary release in the face",
    "slowly": "measured deliberate movement and a sustained readable expression",
    "softly": "gentle eyes, relaxed brows, and tender restrained posture",
    "sorrowful": "downcast wet eyes, tightened inner brows, and visibly heavy grief",
    "stammers": (
        "quivering parted lips caught mid-word, interrupted breath, uncertain eye contact, "
        "and a small hesitant gesture"
    ),
    "thoughtful": "a focused distant gaze, slightly furrowed brows, and reflective stillness",
    "whispers": (
        "lips narrowly parted mid-whisper, the face angled toward the listener, guarded eye contact, "
        "and a confidential lean"
    ),
    "worried": "widened tense eyes, pinched brows, a tight mouth, and guarded posture",
}


_NARRATOR_ATMOSPHERE_CUES = {
    "angry": "oppressive conflict, hard directional tension, and severe contrast",
    "booming": "monumental scale, forceful visual weight, and resonant spatial depth",
    "crying": "grief-heavy atmosphere, subdued light, and irreversible loss",
    "curious": "investigative framing, a selectively revealed clue, and unresolved visual mystery",
    "dramatic": "high-stakes contrast, tense staging, and a decisive turning point",
    "flatly": "restrained neutral staging, steady composition, and minimal visual flourish",
    "happily": "warm relief, brighter balanced light, and open visual spacing",
    "mischievously": "secretive shadowed staging, a half-concealed clue, and restrained visual irony",
    "questioning": "an unresolved focal clue, visual ambiguity, and investigative composition",
    "quietly": "subdued light, intimate scale, and restrained composition",
    "rushed": "urgent motion, compressed spacing, and mounting pressure",
    "sarcastic": "ironic contrast between confident appearances and visible consequences",
    "shouts": "forceful spatial impact, sharp directional movement, and high visual intensity",
    "sighs": "a visual release of pressure, easing movement, and lowered tension",
    "slowly": "deliberate pacing, sustained composition, and gradual visual reveal",
    "softly": "gentle light, quiet spatial rhythm, and restrained warmth",
    "sorrowful": "grief-heavy atmosphere, subdued light, and visible aftermath of loss",
    "stammers": "interrupted motion, hesitant spatial rhythm, and unstable tension",
    "thoughtful": "contemplative pacing, layered depth, and meaningful stillness",
    "whispers": "secretive shadowed staging, concealed visual information, and intimate tension",
    "worried": "compressed framing, looming pressure, and unstable visual balance",
}


_SOURCE_SCENE_HUMAN_RE = re.compile(
    r"\b(?:adult|man|men|woman|women|person|people|crowd|villager|villagers|peasant|peasants|"
    r"priest|pope|cleric|bishop|inquisitor|noble|noblewoman|lady|lord|monk|nun|soldier|guard|"
    r"executioner|family|mother|father|boy|girl|king|queen|emperor|empress|judge|official|"
    r"merchant|farmer|worker|doctor|scientist|researcher|historian|speaker|citizen|survivor|"
    r"victim|blacksmith|witch|colonist|puritan|pilgrim|warrior)\b",
    re.IGNORECASE,
)
_SOURCE_SCENE_ANIMAL_RE = re.compile(
    r"\b(?:(?:black|white|brown|grey|gray|dark|pale|soft|wild|domestic)\s+)?"
    r"(?:rats?|mice|mouse|cats?|dogs?|horses?|cows?|cattle|birds?|bats?|wolves?|"
    r"goats?|sheep|pigs?|rabbits?|snakes?|fleas?|ravens?|crows?)\b",
    re.IGNORECASE,
)
_SOURCE_SCENE_SUPPORTING_PEOPLE_RE = re.compile(
    r"\b(?:crowd|cardinals|soldiers|figures|villagers|villager|people|citizens|guards|"
    r"clergy|monks|nuns|family|families|patient|victim|prisoner|witnesses|spectators)\b",
    re.IGNORECASE,
)
_SOURCE_SCENE_SETTING_RE = re.compile(
    r"\b(?:town square|village square|city square|street|alleyway|chapel|churchyard|"
    r"garden|forest|village|plaza|room|hall|altar|throne room|Vatican chapel)\b",
    re.IGNORECASE,
)
_SOURCE_SCENE_NAMED_CHARACTER_RE = re.compile(
    r"\b(?:Pope|Lady|Inquisitor|King|Queen|Emperor|Empress|Lord)\s+"
    r"[A-Z][a-z]+(?:\s+(?:von\s+)?[A-Z][a-z]+|\s+[IVX]+)?\b"
)


def _is_narrator_cut(cut: dict[str, Any]) -> bool:
    speaker = str(cut.get("speaker") or "").strip().casefold()
    return not speaker or speaker in {"해설자", "narrator", "narration"}


def _ordered_visual_emotion_tags(cut: dict[str, Any]) -> list[str]:
    emotion = str(cut.get("emotion") or "").strip()
    present = {
        tag.strip().lower()
        for tag in re.findall(r"\[([^\]]+)\]", emotion)
        if tag.strip()
    }
    return [tag for tag in _EMOTION_VISUAL_TAG_ORDER if tag in present]


def _visible_emotion_direction(cut: dict[str, Any]) -> str:
    tags = _ordered_visual_emotion_tags(cut)
    cue_map = (
        _NARRATOR_ATMOSPHERE_CUES
        if _is_narrator_cut(cut)
        else _CHARACTER_EMOTION_VISUAL_CUES
    )
    cues = [cue_map[tag] for tag in tags if tag in cue_map]
    if not cues:
        return ""
    if _is_narrator_cut(cut):
        return "; ".join(cues)
    return "the named speaking character visibly performs: " + "; ".join(cues)


def _source_scene_has_human_subject(cut: dict[str, Any], scene: str) -> bool:
    return not _is_narrator_cut(cut) or bool(_SOURCE_SCENE_HUMAN_RE.search(scene or ""))


def _nonhuman_source_inventory_priority(cut: dict[str, Any], scene: str) -> str:
    if not _is_narrator_cut(cut) or _source_scene_has_human_subject(cut, scene):
        return ""
    animals = list(
        dict.fromkeys(
            match.group(0).strip().lower()
            for match in _SOURCE_SCENE_ANIMAL_RE.finditer(scene or "")
        )
    )
    if animals:
        return (
            f"a completely deserted empty setting populated exclusively by {', '.join(animals)}; "
            f"{', '.join(animals)} fill the foreground, middle ground, and background between vacant "
            "source-named buildings, terrain, and objects"
        )
    return (
        "a pure environment or object shot where the source-named architecture, landscape, objects, "
        "terrain, and weather fill every layer of the frame"
    )


def _compact_ch4_visual_direction(
    cut: dict[str, Any],
    scene: str,
    visible_emotion: str,
) -> str:
    if _is_narrator_cut(cut):
        # Narration can still describe a named person or crowd.  In that case
        # adding an environment-only direction contradicts the workbook Scene.
        if _source_scene_has_human_subject(cut, scene):
            return ""
        animals = list(
            dict.fromkeys(
                match.group(0).strip().lower()
                for match in _SOURCE_SCENE_ANIMAL_RE.finditer(scene or "")
            )
        )
        setting_match = _SOURCE_SCENE_SETTING_RE.search(scene or "")
        setting = setting_match.group(0).lower() if setting_match else "setting"
        if animals:
            names = ", ".join(animals)
            return (
                f"The {setting} is completely deserted and populated exclusively by {names}. "
                f"Every street, doorway, window, and bench is visibly unoccupied. "
                f"The sole living subjects in frame are {names}. "
                f"{names.capitalize()} fill the foreground, middle ground, and background between vacant period buildings."
            )
        return (
            "A pure environment or object shot: source-named architecture, terrain, weather, and objects fill every layer of the frame."
        )

    name_match = _SOURCE_SCENE_NAMED_CHARACTER_RE.search(scene or "")
    name = name_match.group(0) if name_match else "source-named speaking character"
    supporting_people = bool(_SOURCE_SCENE_SUPPORTING_PEOPLE_RE.search(scene or ""))
    subject = (
        f"{name} dominates a tight foreground close-up; source-named supporting people remain secondary."
        if supporting_people
        else f"A solitary {name} is the sole visible human in a tight medium close-up."
    )
    tags = _ordered_visual_emotion_tags(cut)
    if "crying" in tags:
        return " ".join(
            (
                subject,
                "The character actively speaks mid-sentence while sobbing and holds the source-named animal or props.",
                "The face is visibly soaked with tears: clear droplets overflow both reddened eyes and form two glossy wet tracks to the jaw.",
                "Pinched brows and trembling wet lips are parted mid-word.",
            )
        )
    cue_text = visible_emotion.removeprefix(
        "the named speaking character visibly performs: "
    ).strip()
    return " ".join(
        part
        for part in (
            subject,
            cue_text,
            "The lips are visibly caught mid-word while delivering this line.",
        )
        if part
    )


def _compact_ch4_source_locked_prompt(
    cut: dict[str, Any],
    *,
    image_year: str,
    image_location: str,
    scene: str,
    visible_emotion: str,
) -> str:
    year = (image_year or "historical").split(",", 1)[0].strip()
    place = (image_location or "Western Europe").strip()
    header = f"{year} {place}."
    style = (
        "Cinematic live-action historical drama, photorealistic feature-film frame, "
        "period-authentic production design, dramatic lighting, 16:9."
    )
    direction = _compact_ch4_visual_direction(cut, scene, visible_emotion)
    parts = [header, style]
    if scene:
        parts.append(f"Scene: {scene.rstrip('.')}.")
    if direction:
        parts.append(f"Visual direction: {direction}")
    return " ".join(parts).strip()


def _character_performance_priority(
    cut: dict[str, Any],
    scene: str,
    visible_emotion: str,
    dialogue_direction: str,
) -> str:
    if _is_narrator_cut(cut) or not dialogue_direction:
        return ""
    tags = _ordered_visual_emotion_tags(cut)
    cue_text = visible_emotion.removeprefix(
        "the named speaking character visibly performs: "
    ).strip()
    supporting_people = bool(_SOURCE_SCENE_SUPPORTING_PEOPLE_RE.search(scene or ""))
    subject_clause = (
        "the source-named speaker dominates a tight foreground close-up; source-named supporting people remain secondary"
        if supporting_people
        else "a solitary source-named speaker is the sole visible human in a tight medium close-up"
    )
    clauses: list[str] = [subject_clause]
    if "crying" in tags:
        clauses.extend(
            (
                "actively speaking through sobs while holding the source-named animal or props",
                "the face is visibly soaked with tears: clear droplets overflow both reddened eyes and form two glossy wet tracks to the jaw",
                "pinched brows and trembling wet lips parted mid-word",
            )
        )
    elif cue_text:
        clauses.append(cue_text)
        clauses.append("the lips are visibly caught mid-word while delivering this line")
    clauses.append("the source Scene is the complete cast, animal, prop, and action inventory")
    return "; ".join(clauses)


def _source_locked_cut_visual_world(
    cut: dict[str, Any],
    episode_visual_world: str,
) -> str:
    """Use guarded cut metadata when a prepared row leaves the episode's era."""
    if not bool(cut.get("source_context_override")):
        return episode_visual_world
    year = image_prompt_safe_text(cut.get("visual_year"), allow_year_normalization=True)
    period = image_prompt_safe_text(cut.get("visual_period"))
    location = image_prompt_safe_text(cut.get("visual_location"))
    if not (year and period and location):
        return episode_visual_world
    return (
        f"Global visual world: Time range: {year}; Place scope: {location}; "
        f"Culture scope: {period}; Continuity rule: this guarded cut-specific source context "
        "supersedes the episode-wide background range, and the narrated action remains "
        "the dominant visible event"
    )


def inject_source_locked_visual_context(
    cut: dict[str, Any],
    visual_world: str = "",
    *,
    required_style: str = IMAGE_PROMPT_REQUIRED_STYLE,
) -> None:
    """Compile declared prepared-source metadata without series-specific rewrites."""
    if not isinstance(cut, dict):
        return
    raw_prompt = str(cut.get("image_prompt") or "")
    prompt = image_prompt_safe_text(raw_prompt)
    raw_year = str(cut.get("visual_year") or "")
    raw_period = str(cut.get("visual_period") or "")
    raw_location = str(cut.get("visual_location") or "")
    raw_evidence = str(cut.get("visual_evidence") or "")
    year = image_prompt_safe_text(cut.get("visual_year"), allow_year_normalization=True)
    period = image_prompt_safe_text(cut.get("visual_period"))
    location = image_prompt_safe_text(cut.get("visual_location"))
    evidence = image_prompt_safe_text(cut.get("visual_evidence"))
    # Workbook-prepared local scripts can carry Korean metadata.  It is source
    # metadata, not generated prompt prose, so keep it when the English-only
    # sanitizer returns an empty value.
    year = year or raw_year.strip()
    period = period or raw_period.strip()
    location = location or raw_location.strip()
    evidence = evidence or raw_evidence.strip()
    subject = image_prompt_safe_text(cut.get("visual_subject"))
    raw_explicit_scene = str(cut.get("visual_scene") or "")
    explicit_scene = image_prompt_safe_text(raw_explicit_scene)
    if not (prompt or year or period or location or evidence or subject or explicit_scene):
        return

    if year:
        cut["visual_year"] = year
    if period:
        cut["visual_period"] = period
    if location:
        cut["visual_location"] = location
    if evidence:
        cut["visual_evidence"] = evidence
    if subject:
        cut["visual_subject"] = subject
    if explicit_scene:
        cut["visual_scene"] = explicit_scene

    visual_world = _source_locked_cut_visual_world(cut, visual_world)
    image_year, image_period, image_location, casting = _ch4_image_generation_context(
        year, period, location
    )

    # The saved source-locked prompt can contain Korean metadata before the
    # final English Scene field.  Extract that raw Scene before applying the
    # English-only sanitizer, otherwise a second policy pass drops the source
    # scene and leaves only the shared episode metadata.
    scene_source = raw_explicit_scene or _strip_visual_context_prefix(raw_prompt)
    scene = image_prompt_safe_text(scene_source)
    if not scene:
        scene = _strip_visual_context_prefix(explicit_scene or prompt)
    scene = re.split(
        r";\s*NARRATION VISUAL ALIGNMENT:",
        scene,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip()
    # Character performance is deliberately repeated after Scene so the local
    # image model gives it enough weight.  Remove the previous compiled suffix
    # first so repeated policy application remains idempotent.
    scene = re.split(
        r"(?:[.;]\s*)(?:Performance close-up priority|Character performance priority|Source inventory priority|Visual direction)\s*:",
        scene,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip()

    narrator_cut = _is_narrator_cut(cut)
    visible_emotion = _visible_emotion_direction(cut)
    dialogue_direction = _spoken_dialogue_direction(cut)
    ch4_live_action = required_style == CH4_CINEMATIC_LIVE_ACTION_STYLE
    if ch4_live_action:
        cut["image_prompt"] = _compact_ch4_source_locked_prompt(
            cut,
            image_year=image_year,
            image_location=image_location,
            scene=scene,
            visible_emotion=visible_emotion,
        )
        return
    parts: list[str] = []
    if visual_world and not ch4_live_action:
        parts.append(visual_world)
    year_period = "; ".join(part for part in (image_year, image_period) if part)
    if year_period:
        parts.append(f"Year/period: {year_period}")
    if image_location:
        parts.append(f"Exact place: {image_location}")
    if casting and _source_scene_has_human_subject(cut, scene):
        parts.append(f"Character identity: {casting}")
    parts.append(f"Style: {required_style}")
    if narrator_cut:
        if visible_emotion:
            parts.append(f"Mood and camera: {visible_emotion}")

    scene_parts: list[str] = []
    if subject:
        scene_parts.append(f"Main subject: {subject}")
    if scene:
        scene_parts.append(f"Scene: {scene}")
    source_inventory_priority = _nonhuman_source_inventory_priority(cut, scene)
    if source_inventory_priority:
        scene_parts.append(f"Source inventory priority: {source_inventory_priority}")
    performance_priority = _character_performance_priority(
        cut,
        scene,
        visible_emotion,
        dialogue_direction,
    )
    if performance_priority:
        scene_parts.append(f"Character performance priority: {performance_priority}")
    prefix = "; ".join(parts)
    suffix = "; ".join(scene_parts)
    cut["image_prompt"] = f"{prefix}; {suffix}" if suffix else prefix


def inject_cut_visual_context(
    cut: dict[str, Any],
    visual_world: str = "",
    seen_major_characters: set[str] | None = None,
    forced_entrance_identities: list[tuple[str, str]] | None = None,
    script_context: str = "",
) -> None:
    """Force year/period/place metadata into the stored image prompt."""
    if not isinstance(cut, dict):
        return
    prompt = image_prompt_safe_text(cut.get("image_prompt") or "")
    raw_year = str(cut.get("visual_year") or "")
    raw_period = str(cut.get("visual_period") or "")
    raw_location = str(cut.get("visual_location") or "")
    raw_evidence = str(cut.get("visual_evidence") or "")
    raw_subject = str(cut.get("visual_subject") or "")
    raw_scene = str(cut.get("visual_scene") or "")
    year = image_prompt_safe_text(cut.get("visual_year"), allow_year_normalization=True)
    period = image_prompt_safe_text(cut.get("visual_period"))
    original_period = period
    period = drop_conflicting_visual_period(year, period)
    location = image_prompt_safe_text(cut.get("visual_location"))
    evidence = image_prompt_safe_text(cut.get("visual_evidence"))
    year = year or raw_year.strip()
    period = period or raw_period.strip()
    location = location or raw_location.strip()
    evidence = evidence or raw_evidence.strip()
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
    raw_context_text = " ".join(
        part
        for part in (
            visual_world,
            prompt,
            raw_year,
            raw_period,
            raw_location,
            raw_evidence,
            raw_subject,
            raw_scene,
            str(cut.get("narration") or ""),
            script_context,
        )
        if part
    )
    cue_year = _extract_cue_year_text(raw_context_text)
    is_goguryeo_succession_override = False
    if (
        cue_year
        and _is_goguryeo_succession_cue_context(raw_context_text)
    ):
        is_goguryeo_succession_override = True
        if not year or visual_period_conflicts_with_year(cue_year, year):
            year = cue_year
        period = drop_conflicting_visual_period(year, period)
        if re.search(r"\b(?:Sui|Goguryeo-Sui|Sui-Goguryeo|612|Yangdi|Salsu|Eulji|Mundeok)\b", period, re.IGNORECASE):
            period = ""
        if not period:
            period = f"Goguryeo succession crisis, {year}"
        if not evidence:
            evidence = _goguryeo_succession_evidence(year)
        repaired_subject, repaired_scene, repaired_evidence = _repair_goguryeo_succession_drift_scene(
            str(cut.get("narration") or ""),
            subject or raw_subject,
            explicit_scene or raw_scene or prompt,
        )
        if repaired_evidence:
            subject = image_prompt_safe_text(repaired_subject) or subject
            explicit_scene = image_prompt_safe_text(repaired_scene) or explicit_scene
            evidence = image_prompt_safe_text(repaired_evidence) or evidence
            location = "Pyongyang Fortress"
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
    is_sui_goguryeo_context = (
        not is_goguryeo_succession_override
        and _is_sui_goguryeo_war_context(context_text, sui_scene_basis)
    )
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
    explicit_japanese_myth_subject = bool(_japanese_myth_named_identities(subject))
    explicit_present_day_japanese_subject = bool(
        re.search(r"\bpresent-day\s+adult\s+Japanese\b", subject, re.IGNORECASE)
        and re.search(r"\bpresent-day\s+Japan\b", year, re.IGNORECASE)
    )
    explicit_japanese_myth_storyteller_subject = bool(
        _is_japanese_creation_myth_context(raw_context_text)
        and re.search(
            r"\bexactly\s+one\s+elderly\s+adult\s+East\s+Asian\s+male\s+storyteller\b",
            subject,
            re.IGNORECASE,
        )
        and re.search(
            r"\bexactly\s+one\s+elderly\s+adult\s+East\s+Asian\s+male\s+storyteller\b",
            explicit_scene,
            re.IGNORECASE,
        )
    )
    explicit_japanese_myth_generic_role_subject = bool(
        _is_japanese_creation_myth_context(raw_context_text)
        and re.search(
            r"\b(?:villagers?|farmers?|caretakers?|storytellers?|listeners?|scribes?)\b",
            subject,
            re.IGNORECASE,
        )
        and re.search(
            r"\b(?:villagers?|farmers?|caretakers?|storytellers?|listeners?|scribes?)\b",
            explicit_scene,
            re.IGNORECASE,
        )
    )
    explicit_japanese_myth_nonhuman_scene = bool(
        not subject
        and (
            re.match(r"\s*(?:Landscape-only|Object-only|Animal-only)\b", explicit_scene or "", re.IGNORECASE)
            or re.search(
                r"\b(?:no\s+(?:visible\s+)?people|no\s+(?:visible\s+)?person|without\s+people|zero\s+people)\b",
                explicit_scene or "",
                re.IGNORECASE,
            )
        )
        and _is_japanese_creation_myth_context(raw_context_text)
    )
    entrance_identities = (
        []
        if (
            explicit_japanese_myth_subject
            or explicit_japanese_myth_storyteller_subject
            or explicit_japanese_myth_generic_role_subject
            or explicit_japanese_myth_nonhuman_scene
            or explicit_present_day_japanese_subject
        )
        else list(forced_entrance_identities or [])[:2]
    )
    if (
        not explicit_japanese_myth_subject
        and not explicit_japanese_myth_storyteller_subject
        and not explicit_japanese_myth_generic_role_subject
        and not explicit_present_day_japanese_subject
        and not explicit_japanese_myth_nonhuman_scene
        and not entrance_identities
        and not is_sui_open_river_cut
        and not is_goguryeo_succession_override
    ):
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

    image_year, image_period, image_location, casting = _ch4_image_generation_context(
        year, period, location
    )
    parts: list[str] = []
    if visual_world:
        parts.append(visual_world)
    year_period = "; ".join(part for part in (image_year, image_period) if part)
    if year_period:
        parts.append(f"Year/period: {year_period}")
    if image_location:
        parts.append(f"Exact place: {image_location}")
    if casting:
        parts.append(f"Casting: {casting}")
    parts.append(f"Style: {IMAGE_PROMPT_REQUIRED_STYLE}")
    emotion = str(cut.get("emotion") or "").strip()
    if emotion:
        parts.append(f"Emotion direction: {emotion}")
    dialogue_direction = _spoken_dialogue_direction(cut)
    if dialogue_direction:
        parts.append(f"Dialogue direction: {dialogue_direction}")

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
    source_locked = uses_source_locked_visual_policy(script)
    if not source_locked:
        script = limit_modern_japanese_history_visuals(script)
    if isinstance(script.get("thumbnail_prompt"), str):
        script["thumbnail_prompt"] = normalize_image_prompt(script["thumbnail_prompt"])
    cuts = script.get("cuts")
    if isinstance(cuts, list):
        if source_locked:
            visual_world = _compiled_visual_world(script)
            source_schema = str(script.get("source_schema") or "").strip().lower()
            script_version = str(script.get("script_version") or "").strip().lower()
            required_style = (
                CH4_CINEMATIC_LIVE_ACTION_STYLE
                if source_schema == "ch4-time-explorers-season1-xlsx-v1"
                or script_version.startswith("prepared-ch4-time-explorers-")
                else IMAGE_PROMPT_REQUIRED_STYLE
            )
            for cut in cuts:
                if isinstance(cut, dict) and isinstance(cut.get("image_prompt"), str):
                    cut["image_prompt"] = normalize_cut_image_prompt(
                        cut["image_prompt"],
                        str(cut.get("narration") or ""),
                        enable_series_repairs=False,
                    )
                    inject_source_locked_visual_context(
                        cut,
                        visual_world,
                        required_style=required_style,
                    )
            return script
        script_context = " ".join(
            str(value or "")
            for value in (
                script.get("title"),
                script.get("topic"),
                script.get("description"),
                script.get("source_sheet"),
                json.dumps(script.get("story_core") or {}, ensure_ascii=False),
            )
        )
        japanese_myth_scan = " ".join(
            str(cut.get(key) or "")
            for cut in cuts[:30]
            if isinstance(cut, dict)
            for key in ("narration", "image_prompt", "visual_year", "visual_period", "visual_location")
        )
        japanese_myth_script = _is_japanese_creation_myth_context(
            script_context,
            japanese_myth_scan,
        )
        if japanese_myth_script and not _compiled_visual_world(script):
            script["visual_world"] = _japanese_myth_visual_world_fields()
        visual_world = _compiled_visual_world(script)
        seen_major_characters: set[str] = set()
        forced_entrances_by_cut = _script_character_introduction_identities(script)
        active_japanese_myth_names: list[str] = []
        for idx, cut in enumerate(cuts, start=1):
            if isinstance(cut, dict) and isinstance(cut.get("image_prompt"), str):
                cut_number = _script_text_number(cut.get("cut_number")) or idx
                cut["image_prompt"] = normalize_cut_image_prompt(
                    cut["image_prompt"],
                    str(cut.get("narration") or ""),
                    script_context,
                )
                if japanese_myth_script:
                    active_japanese_myth_names = _apply_japanese_myth_cut_context(
                        cut,
                        active_japanese_myth_names,
                        script_context,
                    )
                    _repair_ch3_ep10_visual_scene(cut, script_context)
                cut_visual_world = visual_world
                if (
                    str(cut.get("visual_year") or "").strip() == "present-day Japan"
                    and re.search(
                        r"죽은\s*여신의\s*시신에서\s*피어난\s*생명|死んだ\s*女神.*(?:命|生命)",
                        script_context,
                        re.IGNORECASE,
                    )
                ):
                    cut_visual_world = (
                        "Global visual world: Time range: present-day Japan; Place scope: the exact present-day Japanese place named by each scene; "
                        "Culture scope: present-day Japanese daily life and Imperial household cultural continuity; Material culture: plain contemporary work or casual clothing, "
                        "real rice paddies, mulberry leaves, silkworm trays, unpainted wood, and restrained modern interiors only; Continuity rule: people, clothing, architecture, "
                        "and tools remain present-day Japanese and the narrated activity stays visually dominant"
                    )
                ep7_scene_locked = bool(re.search(
                    r"죽은\s*여신의\s*시신에서\s*피어난\s*생명|死んだ\s*女神.*(?:命|生命)",
                    script_context,
                    re.IGNORECASE,
                ))
                forced_entrance = forced_entrances_by_cut.get(cut_number)
                introduction_state = seen_major_characters
                if ep7_scene_locked:
                    forced_entrance = None
                    introduction_state = None
                inject_cut_visual_context(
                    cut,
                    cut_visual_world,
                    introduction_state,
                    forced_entrance,
                    script_context,
                )
    return script
