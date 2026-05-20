from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))

from app.services.tts.japanese_reading_dictionary import (  # noqa: E402
    JAPANESE_HISTORY_READING_OVERRIDES,
    katakana_to_hiragana,
)


SOURCES = {
    "jmdict": {
        "url": "http://ftp.edrdg.org/pub/Nihongo/JMdict_e.gz",
        "filename": "JMdict_e.gz",
    },
    "jmnedict": {
        "url": "http://ftp.edrdg.org/pub/Nihongo/JMnedict.xml.gz",
        "filename": "JMnedict.xml.gz",
    },
}

HISTORY_SURFACE_HINTS = (
    "天皇", "上皇", "法皇", "皇子", "皇后", "王権", "大王", "倭", "大和", "飛鳥", "奈良", "平安",
    "鎌倉", "室町", "戦国", "江戸", "明治", "古墳", "遺跡", "神宮", "大社", "神社", "寺",
    "幕府", "将軍", "摂政", "関白", "朝廷", "律令", "荘園", "守護", "地頭", "豪族", "氏",
    "戦い", "合戦", "乱", "変", "維新", "一揆", "蝦夷", "百済", "新羅", "高句麗", "任那",
    "遣唐使", "遣隋使", "国司", "郡司", "大宰府", "太宰府", "蘇我", "物部", "藤原", "源",
    "平", "北条", "足利", "徳川", "織田", "豊臣",
)
HISTORY_GLOSS_HINTS = (
    "history", "historical", "emperor", "empress", "imperial", "shogun",
    "shogunate", "samurai", "ritsuryo", "buddhist", "shinto",
)
EXTRA_TARGET_TERMS = {
    "大王", "大王墓", "山背大兄王", "蘇我馬子", "蘇我入鹿", "蘇我蝦夷", "乙巳の変", "白村江の戦い",
    "磐井の乱", "倭の五王", "倭王武", "雄略大王", "ワカタケル大王", "纒向遺跡", "箸墓古墳",
    "百舌鳥古墳群", "古市古墳群", "天孫降臨", "三種の神器", "大宰府", "蔵人所", "検非違使",
}
TARGET_TERMS = set(EXTRA_TARGET_TERMS) | {term for term, _ in JAPANESE_HISTORY_READING_OVERRIDES}
KANJI_RE = re.compile(r"[\u3400-\u9fff]")


def has_kanji(text: str) -> bool:
    return bool(KANJI_RE.search(text or ""))


def download(url: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "LongTube Japanese reading dictionary builder"})
    with urllib.request.urlopen(req, timeout=60) as response, path.open("wb") as fh:
        fh.write(response.read())


def ensure_sources(cache_dir: Path, force: bool = False) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for key, meta in SOURCES.items():
        path = cache_dir / meta["filename"]
        if force or not path.exists() or path.stat().st_size == 0:
            print(f"[download] {key}: {meta['url']}")
            download(meta["url"], path)
        out[key] = path
    return out


def include_entry(surface: str, glosses: list[str], *, allow_gloss_hints: bool = True) -> bool:
    if surface in TARGET_TERMS:
        return True
    if "大王" in surface and not any(ctx in surface for ctx in ("大和", "ヤマト", "倭", "雄略", "ワカタケル")):
        return False
    if any(hint in surface for hint in HISTORY_SURFACE_HINTS):
        return True
    if not allow_gloss_hints:
        return False
    haystack = " ".join(glosses).lower()
    return any(hint in haystack for hint in HISTORY_GLOSS_HINTS)


def first_texts(node: ET.Element, path: str) -> list[str]:
    values: list[str] = []
    for child in node.findall(path):
        if child.text and child.text.strip():
            values.append(child.text.strip())
    return values


def parse_jmdict(path: Path, limit: int) -> dict[str, str]:
    found: dict[str, str] = {}
    with gzip.open(path, "rb") as fh:
        for _event, elem in ET.iterparse(fh, events=("end",)):
            if elem.tag != "entry":
                continue
            surfaces = first_texts(elem, "k_ele/keb")
            readings = first_texts(elem, "r_ele/reb")
            glosses = first_texts(elem, "sense/gloss")
            if surfaces and readings:
                reading = katakana_to_hiragana(readings[0])
                for surface in surfaces:
                    if has_kanji(surface) and include_entry(surface, glosses, allow_gloss_hints=True):
                        found.setdefault(surface, reading)
                        if len(found) >= limit:
                            return found
            elem.clear()
    return found


def parse_jmnedict(path: Path, limit: int) -> dict[str, str]:
    found: dict[str, str] = {}
    with gzip.open(path, "rb") as fh:
        for _event, elem in ET.iterparse(fh, events=("end",)):
            if elem.tag != "entry":
                continue
            surfaces = first_texts(elem, "k_ele/keb")
            readings = first_texts(elem, "r_ele/reb")
            translations = first_texts(elem, "trans/trans_det")
            if surfaces and readings:
                reading = katakana_to_hiragana(readings[0])
                for surface in surfaces:
                    if has_kanji(surface) and include_entry(surface, translations, allow_gloss_hints=False):
                        found.setdefault(surface, reading)
                        if len(found) >= limit:
                            return found
            elem.clear()
    return found


def build(cache_dir: Path, max_entries: int) -> dict:
    sources = ensure_sources(cache_dir)
    entries: dict[str, str] = {}
    for surface, reading in JAPANESE_HISTORY_READING_OVERRIDES:
        entries.setdefault(surface, reading)
    for surface, reading in parse_jmdict(sources["jmdict"], max_entries).items():
        entries.setdefault(surface, reading)
    for surface, reading in parse_jmnedict(sources["jmnedict"], max_entries).items():
        entries.setdefault(surface, reading)
    entries = dict(sorted(entries.items(), key=lambda item: (-len(item[0]), item[0]))[:max_entries])
    return {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sources": {
                "EDRDG JMdict_e": SOURCES["jmdict"]["url"],
                "EDRDG JMnedict": SOURCES["jmnedict"]["url"],
                "manual_overrides": "backend/app/services/tts/japanese_reading_dictionary.py",
            },
            "license_note": (
                "EDRDG dictionary data is used for local reading support. Keep attribution when redistributing."
            ),
            "entry_count": len(entries),
        },
        "entries": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build LongTube Japanese TTS reading dictionary.")
    parser.add_argument(
        "--output",
        default=str(REPO / "data" / "_system" / "japanese_readings.generated.json"),
    )
    parser.add_argument(
        "--cache-dir",
        default=str(REPO / "data" / "_system" / "japanese_reading_sources"),
    )
    parser.add_argument("--max-entries", type=int, default=5000)
    args = parser.parse_args()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = build(Path(args.cache_dir), max(100, int(args.max_entries or 5000)))
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] wrote {payload['metadata']['entry_count']} entries: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
