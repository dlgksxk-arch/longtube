from __future__ import annotations

import copy
import re
from typing import Any


_KO_DIGITS = ["", "\uc77c", "\uc774", "\uc0bc", "\uc0ac", "\uc624", "\uc721", "\uce60", "\ud314", "\uad6c"]
_KO_SMALL_UNITS = ["", "\uc2ed", "\ubc31", "\ucc9c"]
_KO_BIG_UNITS = ["", "\ub9cc", "\uc5b5", "\uc870"]

_EN_UNDER_20 = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen",
]
_EN_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]

_HI_UNDER_100 = [
    "\u0936\u0942\u0928\u094d\u092f", "\u090f\u0915", "\u0926\u094b", "\u0924\u0940\u0928", "\u091a\u093e\u0930", "\u092a\u093e\u0901\u091a",
    "\u091b\u0939", "\u0938\u093e\u0924", "\u0906\u0920", "\u0928\u094c", "\u0926\u0938", "\u0917\u094d\u092f\u093e\u0930\u0939",
    "\u092c\u093e\u0930\u0939", "\u0924\u0947\u0930\u0939", "\u091a\u094c\u0926\u0939", "\u092a\u0902\u0926\u094d\u0930\u0939",
    "\u0938\u094b\u0932\u0939", "\u0938\u0924\u094d\u0930\u0939", "\u0905\u0920\u093e\u0930\u0939", "\u0909\u0928\u094d\u0928\u0940\u0938",
    "\u092c\u0940\u0938", "\u0907\u0915\u094d\u0915\u0940\u0938", "\u092c\u093e\u0908\u0938", "\u0924\u0947\u0908\u0938",
    "\u091a\u094c\u092c\u0940\u0938", "\u092a\u091a\u094d\u091a\u0940\u0938", "\u091b\u092c\u094d\u092c\u0940\u0938",
    "\u0938\u0924\u094d\u0924\u093e\u0908\u0938", "\u0905\u0920\u094d\u0920\u093e\u0908\u0938", "\u0909\u0928\u0924\u0940\u0938",
    "\u0924\u0940\u0938", "\u0907\u0915\u0924\u0940\u0938", "\u092c\u0924\u094d\u0924\u0940\u0938", "\u0924\u0948\u0902\u0924\u0940\u0938",
    "\u091a\u094c\u0902\u0924\u0940\u0938", "\u092a\u0948\u0902\u0924\u0940\u0938", "\u091b\u0924\u094d\u0924\u0940\u0938",
    "\u0938\u0948\u0902\u0924\u0940\u0938", "\u0905\u0921\u093c\u0924\u0940\u0938", "\u0909\u0928\u093e\u0932\u0940\u0938",
    "\u091a\u093e\u0932\u0940\u0938", "\u0907\u0915\u0924\u093e\u0932\u0940\u0938", "\u092c\u092f\u093e\u0932\u0940\u0938",
    "\u0924\u0948\u0902\u0924\u093e\u0932\u0940\u0938", "\u091a\u0935\u093e\u0932\u0940\u0938", "\u092a\u0948\u0902\u0924\u093e\u0932\u0940\u0938",
    "\u091b\u093f\u092f\u093e\u0932\u0940\u0938", "\u0938\u0948\u0902\u0924\u093e\u0932\u0940\u0938", "\u0905\u0921\u093c\u0924\u093e\u0932\u0940\u0938",
    "\u0909\u0928\u091a\u093e\u0938", "\u092a\u091a\u093e\u0938", "\u0907\u0915\u094d\u092f\u093e\u0935\u0928", "\u092c\u093e\u0935\u0928",
    "\u0924\u093f\u0930\u0947\u092a\u0928", "\u091a\u094c\u0935\u0928", "\u092a\u091a\u092a\u0928", "\u091b\u092a\u094d\u092a\u0928",
    "\u0938\u0924\u094d\u0924\u093e\u0935\u0928", "\u0905\u0920\u094d\u0920\u093e\u0935\u0928", "\u0909\u0928\u0938\u0920",
    "\u0938\u093e\u0920", "\u0907\u0915\u0938\u0920", "\u092c\u093e\u0938\u0920", "\u0924\u093f\u0930\u0938\u0920",
    "\u091a\u094c\u0902\u0938\u0920", "\u092a\u0948\u0902\u0938\u0920", "\u091b\u093f\u092f\u093e\u0938\u0920",
    "\u0938\u0921\u093c\u0938\u0920", "\u0905\u0921\u093c\u0938\u0920", "\u0909\u0928\u0939\u0924\u094d\u0924\u0930",
    "\u0938\u0924\u094d\u0924\u0930", "\u0907\u0915\u0939\u0924\u094d\u0924\u0930", "\u092c\u0939\u0924\u094d\u0924\u0930",
    "\u0924\u093f\u0939\u0924\u094d\u0924\u0930", "\u091a\u094c\u0939\u0924\u094d\u0924\u0930", "\u092a\u091a\u0939\u0924\u094d\u0924\u0930",
    "\u091b\u093f\u0939\u0924\u094d\u0924\u0930", "\u0938\u0924\u0939\u0924\u094d\u0924\u0930", "\u0905\u0920\u0939\u0924\u094d\u0924\u0930",
    "\u0909\u0928\u094d\u092f\u093e\u0938\u0940", "\u0905\u0938\u094d\u0938\u0940", "\u0907\u0915\u094d\u092f\u093e\u0938\u0940",
    "\u092c\u092f\u093e\u0938\u0940", "\u0924\u093f\u0930\u093e\u0938\u0940", "\u091a\u094c\u0930\u093e\u0938\u0940",
    "\u092a\u091a\u093e\u0938\u0940", "\u091b\u093f\u092f\u093e\u0938\u0940", "\u0938\u0924\u094d\u0924\u093e\u0938\u0940",
    "\u0905\u0920\u094d\u0920\u093e\u0938\u0940", "\u0928\u0935\u093e\u0938\u0940", "\u0928\u092c\u094d\u092c\u0947",
    "\u0907\u0915\u094d\u092f\u093e\u0928\u0935\u0947", "\u092c\u093e\u0928\u0935\u0947", "\u0924\u093f\u0930\u093e\u0928\u0935\u0947",
    "\u091a\u094c\u0930\u093e\u0928\u0935\u0947", "\u092a\u091a\u093e\u0928\u0935\u0947", "\u091b\u093f\u092f\u093e\u0928\u0935\u0947",
    "\u0938\u0924\u094d\u0924\u093e\u0928\u0935\u0947", "\u0905\u0920\u094d\u0920\u093e\u0928\u0935\u0947", "\u0928\u093f\u0928\u094d\u092f\u093e\u0928\u0935\u0947",
]

_JA_DIGITS = ["", "\u4e00", "\u4e8c", "\u4e09", "\u56db", "\u4e94", "\u516d", "\u4e03", "\u516b", "\u4e5d"]
_JA_SMALL_UNITS = ["", "\u5341", "\u767e", "\u5343"]
_JA_BIG_UNITS = ["", "\u4e07", "\u5104", "\u5146"]
_EPISODE_MARKER_RE = re.compile(
    r"(^|[\s|/\\\-–—:·(\[])"
    r"(?:"
    r"EP\.?\s*0*\d+"
    r"|episode\s*0*\d+"
    r"|\uc5d0\ud53c\uc18c\ub4dc\s*0*\d+"
    r"|\u090f\u092a\u093f\u0938\u094b\u0921\s*0*\d+"
    r"|\u092d\u093e\u0917\s*0*\d+"
    r")"
    r"(?:\s*(?:\u092e\u0947\u0902|\u0915\u0940|\u0915\u093e|\u0915\u0947|\u0938\u0947|\u092a\u0930))?"
    r"(?:(?:\uc5d0\uc11c|\uc5d0\ub294|\uc740|\ub294|\uc774|\uac00|\uc744|\ub97c|\uc758|\uc73c\ub85c|\ub85c))?"
    r"(?=$|[\s|/\\\-–—:·)\],.?!])",
    re.IGNORECASE,
)
_TTS_SPACE_RE = re.compile(r"\s+")


def strip_episode_markers_for_tts(text: str) -> str:
    """Remove visual episode labels so TTS does not spell out EP.07."""
    if not text:
        return text

    def repl(match: re.Match[str]) -> str:
        prefix = match.group(1) or ""
        return prefix if prefix and prefix.strip() else " "

    cleaned = _EPISODE_MARKER_RE.sub(repl, str(text))
    cleaned = _TTS_SPACE_RE.sub(" ", cleaned)
    return cleaned.strip(" |/-–—:·")


_SPOKEN_EPISODE_MARKER_RE = re.compile(
    r"(^|[\s|/\\\-:·(\[])"
    r"(?P<label>EP\.?|episode|\uc5d0\ud53c\uc18c\ub4dc|\u090f\u092a\u093f\u0938\u094b\u0921|\u092d\u093e\u0917)"
    r"\s*0*(?P<num>\d+)"
    r"(?P<suffix>\s*(?:\u092e\u0947\u0902|\u0915\u0940|\u0915\u093e|\u0915\u0947|\u0938\u0947|\u092a\u0930)"
    r"|(?:\uc5d0\uc11c|\uc5d0\ub294|\uc740|\ub294|\uc774|\uac00|\uc744|\ub97c|\uc758|\uc73c\ub85c|\ub85c))?"
    r"(?=$|[\s|/\\\-:·)\],.?!])",
    re.IGNORECASE,
)


def _episode_word(language: str, label: str) -> str:
    lang = str(language or "").lower()
    label_lower = str(label or "").lower()
    if lang.startswith("hi") or "\u0900" <= (label[:1] or "") <= "\u097f":
        return "\u090f\u092a\u093f\u0938\u094b\u0921"
    if lang.startswith("ko") or label_lower.startswith("\uc5d0\ud53c"):
        return "\uc5d0\ud53c\uc18c\ub4dc"
    if lang.startswith("ja"):
        return "\u7b2c"
    return "episode"


def _episode_number_word(number: int, language: str) -> str:
    lang = str(language or "").lower()
    if lang.startswith("hi"):
        return number_to_hindi(number)
    if lang.startswith("ko"):
        return number_to_korean_sino(number)
    if lang.startswith("ja"):
        return number_to_japanese_kanji(number)
    return number_to_english(number)


def normalize_episode_markers_for_tts(text: str, language: str = "ko") -> str:
    """Read visual episode labels as words instead of spelling EP.07."""
    if not text:
        return text

    def repl(match: re.Match[str]) -> str:
        prefix = match.group(1) or ""
        try:
            number = int(match.group("num"))
        except Exception:
            return match.group(0)
        label = match.group("label") or ""
        suffix = match.group("suffix") or ""
        lang = str(language or "ko").lower()
        if lang.startswith("ja"):
            spoken = f"{_episode_word(language, label)}{_episode_number_word(number, language)}\u8a71"
        else:
            spoken = f"{_episode_word(language, label)} {_episode_number_word(number, language)}"
        return f"{prefix}{spoken}{suffix}"

    cleaned = _SPOKEN_EPISODE_MARKER_RE.sub(repl, str(text))
    cleaned = _TTS_SPACE_RE.sub(" ", cleaned)
    return cleaned.strip(" |/-:·")


def strip_episode_markers_for_tts(text: str, language: str = "ko") -> str:
    return normalize_episode_markers_for_tts(text, language)


def _under_10000_to_sino(num: int, digits: list[str], small_units: list[str]) -> str:
    if num <= 0:
        return ""
    parts: list[str] = []
    raw_digits = list(map(int, str(num)))
    length = len(raw_digits)
    for idx, digit in enumerate(raw_digits):
        if digit == 0:
            continue
        unit_pos = length - idx - 1
        digit_text = "" if digit == 1 and unit_pos > 0 else digits[digit]
        parts.append(digit_text + small_units[unit_pos])
    return "".join(parts)


def _grouped_sino(num: int, digits: list[str], small_units: list[str], big_units: list[str], zero_word: str) -> str:
    if num == 0:
        return zero_word
    if num < 0:
        return number_to_english(abs(num))
    groups: list[int] = []
    n = num
    while n:
        groups.append(n % 10000)
        n //= 10000
    parts: list[str] = []
    for idx in range(len(groups) - 1, -1, -1):
        group = groups[idx]
        if group:
            parts.append(_under_10000_to_sino(group, digits, small_units) + big_units[idx])
    return "".join(parts)


def number_to_korean_sino(num: int) -> str:
    return _grouped_sino(num, _KO_DIGITS, _KO_SMALL_UNITS, _KO_BIG_UNITS, "\uc601")


def number_to_japanese_kanji(num: int) -> str:
    return _grouped_sino(num, _JA_DIGITS, _JA_SMALL_UNITS, _JA_BIG_UNITS, "\u96f6")


def number_to_english(num: int) -> str:
    if num < 0:
        return "minus " + number_to_english(abs(num))
    if num < 20:
        return _EN_UNDER_20[num]
    if num < 100:
        tens, rem = divmod(num, 10)
        return _EN_TENS[tens] if rem == 0 else f"{_EN_TENS[tens]}-{_EN_UNDER_20[rem]}"
    if num < 1000:
        hundreds, rem = divmod(num, 100)
        return f"{_EN_UNDER_20[hundreds]} hundred" + (f" {number_to_english(rem)}" if rem else "")
    if num < 1_000_000:
        thousands, rem = divmod(num, 1000)
        return f"{number_to_english(thousands)} thousand" + (f" {number_to_english(rem)}" if rem else "")
    millions, rem = divmod(num, 1_000_000)
    return f"{number_to_english(millions)} million" + (f" {number_to_english(rem)}" if rem else "")


def number_to_hindi(num: int) -> str:
    if num < 0:
        return "\u092e\u093e\u0907\u0928\u0938 " + number_to_hindi(abs(num))
    if num < 100:
        return _HI_UNDER_100[num]
    if num < 1000:
        hundreds, rem = divmod(num, 100)
        text = f"{_HI_UNDER_100[hundreds]} \u0938\u094c"
        return text if rem == 0 else f"{text} {_HI_UNDER_100[rem]}"
    if num < 100_000:
        thousands, rem = divmod(num, 1000)
        text = f"{number_to_hindi(thousands)} \u0939\u091c\u093c\u093e\u0930"
        return text if rem == 0 else f"{text} {number_to_hindi(rem)}"
    lakhs, rem = divmod(num, 100_000)
    text = f"{number_to_hindi(lakhs)} \u0932\u093e\u0916"
    return text if rem == 0 else f"{text} {number_to_hindi(rem)}"


def _parse_int(raw: str) -> int | None:
    try:
        return int(raw.replace(",", ""))
    except ValueError:
        return None


def _replace_year_suffix(text: str, suffix_pattern: str, converter, joiner: str = "") -> str:
    def repl(match: re.Match[str]) -> str:
        value = _parse_int(match.group(1))
        if value is None:
            return match.group(0)
        return f"{converter(value)}{joiner}{match.group(2)}"

    return re.sub(rf"(?<![A-Za-z0-9])([0-9][0-9,]{{0,8}})\s*({suffix_pattern})", repl, text)


def normalize_year_numbers_for_tts(text: str, language: str = "ko") -> str:
    if not text:
        return text
    lang = str(language or "ko").lower()
    s = strip_episode_markers_for_tts(str(text), lang)
    if lang.startswith("ko"):
        return _replace_year_suffix(s, "\ub144", number_to_korean_sino)
    if lang.startswith("ja"):
        return _replace_year_suffix(s, "\u5e74", number_to_japanese_kanji)
    if lang.startswith("hi"):
        s = _replace_year_suffix(s, "\u0908\u0938\u094d\u0935\u0940|\u0935\u0930\u094d\u0937|\u0938\u093e\u0932", number_to_hindi, " ")
        s = re.sub(
            r"(?<![A-Za-z0-9])([0-9][0-9,]{0,8})\s+(\u0908\u0938\u093e\s+\u092a\u0942\u0930\u094d\u0935)",
            lambda m: f"{number_to_hindi(_parse_int(m.group(1)) or 0)} {m.group(2)}",
            s,
        )
        return s
    if lang.startswith("en"):
        s = _replace_year_suffix(s, "AD|CE|BCE|BC", number_to_english, " ")
        s = re.sub(
            r"\byear\s+([0-9][0-9,]{0,8})\b",
            lambda m: f"year {number_to_english(_parse_int(m.group(1)) or 0)}",
            s,
            flags=re.IGNORECASE,
        )
        return s
    return s


def normalize_script_tts_numbers(script: dict[str, Any], language: str = "ko") -> dict[str, Any]:
    result = copy.deepcopy(script)
    for cut in result.get("cuts", []) or []:
        if not isinstance(cut, dict):
            continue
        narration = cut.get("narration")
        if isinstance(narration, str):
            cut["narration"] = normalize_year_numbers_for_tts(narration, language)
    return result
