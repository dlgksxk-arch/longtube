from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Mapping

from app.config import BASE_DIR, SYSTEM_DIR


# Manual overrides are for terms where generic kanji reading is often wrong in
# Japanese-history narration. Keep these narrow and source-like; user feedback
# entries should go to data/_system/japanese_readings.json.
JAPANESE_HISTORY_READING_OVERRIDES: tuple[tuple[str, str], ...] = (
    # Ancient Japanese royal / Yamato context
    ("ワカタケル大王", "わかたけるのおおきみ"),
    ("雄略大王", "ゆうりゃくのおおきみ"),
    ("倭王武", "わおうぶ"),
    ("倭王讃", "わおうさん"),
    ("倭王珍", "わおうちん"),
    ("倭王済", "わおうせい"),
    ("倭王興", "わおうこう"),
    ("倭の五王", "わのごおう"),
    ("大王墓", "おおきみのはか"),
    ("大王家", "おおきみけ"),
    ("大王号", "おおきみごう"),
    # Ancient / classical people
    ("蘇我稲目", "そがのいなめ"),
    ("蘇我馬子", "そがのうまこ"),
    ("蘇我蝦夷", "そがのえみし"),
    ("蘇我入鹿", "そがのいるか"),
    ("蘇我倉山田石川麻呂", "そがのくらのやまだのいしかわのまろ"),
    ("物部尾輿", "もののべのおこし"),
    ("物部守屋", "もののべのもりや"),
    ("大伴金村", "おおとものかなむら"),
    ("阿倍比羅夫", "あべのひらふ"),
    ("山背大兄王", "やましろのおおえのおう"),
    ("有間皇子", "ありまのみこ"),
    ("大海人皇子", "おおあまのおうじ"),
    ("大友皇子", "おおとものおうじ"),
    ("葛城襲津彦", "かずらきのそつひこ"),
    ("額田王", "ぬかたのおおきみ"),
    ("柿本人麻呂", "かきのもとのひとまろ"),
    ("山上憶良", "やまのうえのおくら"),
    ("大伴家持", "おおとものやかもち"),
    ("万葉仮名", "まんようがな"),
    ("万葉集", "まんようしゅう"),
    ("古今和歌集", "こきんわかしゅう"),
    ("防人歌", "さきもりうた"),
    ("東歌", "あずまうた"),
    ("和気清麻呂", "わけのきよまろ"),
    ("吉備真備", "きびのまきび"),
    ("橘諸兄", "たちばなのもろえ"),
    ("藤原広嗣", "ふじわらのひろつぐ"),
    ("藤原仲麻呂", "ふじわらのなかまろ"),
    ("藤原良房", "ふじわらのよしふさ"),
    ("藤原基経", "ふじわらのもとつね"),
    ("藤原頼通", "ふじわらのよりみち"),
    ("紀貫之", "きのつらゆき"),
    ("在原業平", "ありわらのなりひら"),
    ("平貞盛", "たいらのさだもり"),
    ("藤原秀郷", "ふじわらのひでさと"),
    ("藤原純友", "ふじわらのすみとも"),
    ("源義家", "みなもとのよしいえ"),
    ("源頼義", "みなもとのよりよし"),
    ("源義朝", "みなもとのよしとも"),
    ("源実朝", "みなもとのさねとも"),
    ("北条泰時", "ほうじょうやすとき"),
    ("北条義時", "ほうじょうよしとき"),
    ("後鳥羽上皇", "ごとばじょうこう"),
    ("日野富子", "ひのとみこ"),
    ("足利義政", "あしかがよしまさ"),
    ("浅井長政", "あざいながまさ"),
    ("朝倉義景", "あさくらよしかげ"),
    ("毛利元就", "もうりもとなり"),
    ("島津義弘", "しまづよしひろ"),
    ("黒田官兵衛", "くろだかんべえ"),
    ("千利休", "せんのりきゅう"),
    ("石田三成", "いしだみつなり"),
    ("大谷吉継", "おおたによしつぐ"),
    ("小早川秀秋", "こばやかわひであき"),
    ("井伊直弼", "いいなおすけ"),
    ("吉田松陰", "よしだしょういん"),
    ("高杉晋作", "たかすぎしんさく"),
    ("桂小五郎", "かつらこごろう"),
    ("木戸孝允", "きどたかよし"),
    ("大隈重信", "おおくましげのぶ"),
    ("板垣退助", "いたがきたいすけ"),
    ("伊藤博文", "いとうひろぶみ"),
    # Emperors / imperial names
    ("神功皇后", "じんぐうこうごう"),
    ("応神天皇", "おうじんてんのう"),
    ("仁徳天皇", "にんとくてんのう"),
    ("允恭天皇", "いんぎょうてんのう"),
    ("安閑天皇", "あんかんてんのう"),
    ("宣化天皇", "せんかてんのう"),
    ("敏達天皇", "びだつてんのう"),
    ("用明天皇", "ようめいてんのう"),
    ("崇峻天皇", "すしゅんてんのう"),
    ("皇極天皇", "こうぎょくてんのう"),
    ("孝徳天皇", "こうとくてんのう"),
    ("斉明天皇", "さいめいてんのう"),
    ("文武天皇", "もんむてんのう"),
    ("元明天皇", "げんめいてんのう"),
    ("元正天皇", "げんしょうてんのう"),
    ("称徳天皇", "しょうとくてんのう"),
    ("光仁天皇", "こうにんてんのう"),
    ("嵯峨天皇", "さがてんのう"),
    ("白河上皇", "しらかわじょうこう"),
    ("後白河法皇", "ごしらかわほうおう"),
    ("天皇", "てんのう"),
    ("上皇", "じょうこう"),
    ("法皇", "ほうおう"),
    # Events and institutions
    ("乙巳の変", "いっしのへん"),
    ("白村江の戦い", "はくすきのえのたたかい"),
    ("磐井の乱", "いわいのらん"),
    ("藤原広嗣の乱", "ふじわらのひろつぐのらん"),
    ("平将門の乱", "たいらのまさかどのらん"),
    ("藤原純友の乱", "ふじわらのすみとものらん"),
    ("保元の乱", "ほうげんのらん"),
    ("平治の乱", "へいじのらん"),
    ("治承・寿永の乱", "じしょうじゅえいのらん"),
    ("南北朝時代", "なんぼくちょうじだい"),
    ("長享の乱", "ちょうきょうのらん"),
    ("享徳の乱", "きょうとくのらん"),
    ("島原の乱", "しまばらのらん"),
    ("大塩平八郎の乱", "おおしおへいはちろうのらん"),
    ("桜田門外の変", "さくらだもんがいのへん"),
    ("安政の大獄", "あんせいのたいごく"),
    ("薩長同盟", "さっちょうどうめい"),
    ("大政奉還", "たいせいほうかん"),
    ("戊辰戦争", "ぼしんせんそう"),
    ("版籍奉還", "はんせきほうかん"),
    ("西南戦争", "せいなんせんそう"),
    ("自由民権運動", "じゆうみんけんうんどう"),
    ("日清戦争", "にっしんせんそう"),
    ("日露戦争", "にちろせんそう"),
    ("太閤検地", "たいこうけんち"),
    ("刀狩", "かたながり"),
    ("兵農分離", "へいのうぶんり"),
    ("廃仏毀釈", "はいぶつきしゃく"),
    ("王政復古の大号令", "おうせいふっこのだいごうれい"),
    ("五箇条の御誓文", "ごかじょうのごせいもん"),
    ("征韓論", "せいかんろん"),
    ("士族反乱", "しぞくはんらん"),
    ("民撰議院設立建白書", "みんせんぎいんせつりつけんぱくしょ"),
    ("御成敗式目", "ごせいばいしきもく"),
    ("建武式目", "けんむしきもく"),
    ("禁中並公家諸法度", "きんちゅうならびにくげしょはっと"),
    ("公地公民", "こうちこうみん"),
    ("戸籍", "こせき"),
    ("庚午年籍", "こうごねんじゃく"),
    ("庚寅年籍", "こういんねんじゃく"),
    ("租庸調", "そようちょう"),
    ("雑徭", "ぞうよう"),
    ("防人", "さきもり"),
    ("蔵人所", "くろうどどころ"),
    ("検非違使", "けびいし"),
    ("六波羅探題", "ろくはらたんだい"),
    ("問注所", "もんちゅうじょ"),
    ("侍所", "さむらいどころ"),
    ("評定衆", "ひょうじょうしゅう"),
    ("得宗", "とくそう"),
    ("惣領制", "そうりょうせい"),
    ("惣村", "そうそん"),
    ("一揆", "いっき"),
    ("土一揆", "つちいっき"),
    ("国一揆", "くにいっき"),
    ("一向一揆", "いっこういっき"),
    ("楽市楽座", "らくいちらくざ"),
    ("朱印船貿易", "しゅいんせんぼうえき"),
    ("参勤交代", "さんきんこうたい"),
    ("寺請制度", "てらうけせいど"),
    ("踏絵", "ふみえ"),
    ("鎖国", "さこく"),
    ("国学", "こくがく"),
    ("蘭学", "らんがく"),
    # Places, sources, sites
    ("箸墓古墳", "はしはかこふん"),
    ("纒向遺跡", "まきむくいせき"),
    ("百舌鳥古墳群", "もずこふんぐん"),
    ("古市古墳群", "ふるいちこふんぐん"),
    ("百舌鳥・古市古墳群", "もずふるいちこふんぐん"),
    ("稲荷山古墳", "いなりやまこふん"),
    ("江田船山古墳", "えたふなやまこふん"),
    ("登呂遺跡", "とろいせき"),
    ("板付遺跡", "いたづけいせき"),
    ("岩宿遺跡", "いわじゅくいせき"),
    ("平泉", "ひらいずみ"),
    ("奥州", "おうしゅう"),
    ("陸奥", "むつ"),
    ("出羽", "でわ"),
    ("大宰府", "だざいふ"),
    ("太宰府", "だざいふ"),
    ("出雲大社", "いずもたいしゃ"),
    ("伊勢神宮", "いせじんぐう"),
    ("厳島神社", "いつくしまじんじゃ"),
    ("宗像大社", "むなかたたいしゃ"),
    ("住吉大社", "すみよしたいしゃ"),
    ("鹿島神宮", "かしまじんぐう"),
    ("香取神宮", "かとりじんぐう"),
    ("高千穂", "たかちほ"),
    ("出雲", "いずも"),
    ("対馬", "つしま"),
    ("壱岐", "いき"),
    ("筑紫", "つくし"),
    ("筑前", "ちくぜん"),
    ("筑後", "ちくご"),
    ("吉備", "きび"),
    ("近江", "おうみ"),
    ("美濃", "みの"),
    ("尾張", "おわり"),
    ("三河", "みかわ"),
    ("駿河", "するが"),
    ("甲斐", "かい"),
    ("越後", "えちご"),
    ("安土桃山", "あづちももやま"),
    ("飛鳥時代", "あすかじだい"),
    ("奈良時代", "ならじだい"),
    ("平安時代", "へいあんじだい"),
    ("鎌倉時代", "かまくらじだい"),
    ("室町時代", "むろまちじだい"),
    ("江戸時代", "えどじだい"),
    ("明治時代", "めいじじだい"),
    ("大正時代", "たいしょうじだい"),
    ("昭和時代", "しょうわじだい"),
    # Sources / mythology
    ("天照大神", "あまてらすおおみかみ"),
    ("素戔嗚尊", "すさのおのみこと"),
    ("須佐之男命", "すさのおのみこと"),
    ("月読命", "つくよみのみこと"),
    ("大国主命", "おおくにぬしのみこと"),
    ("天孫降臨", "てんそんこうりん"),
    ("三種の神器", "さんしゅのじんぎ"),
    ("八咫鏡", "やたのかがみ"),
    ("草薙剣", "くさなぎのつるぎ"),
    ("八尺瓊勾玉", "やさかにのまがたま"),
    ("先代旧事本紀", "せんだいくじほんぎ"),
    ("延喜式", "えんぎしき"),
    ("六国史", "りっこくし"),
    ("扶桑略記", "ふそうりゃっき"),
    ("吾妻鏡", "あずまかがみ"),
    ("太平記", "たいへいき"),
    ("平家物語", "へいけものがたり"),
    ("愚管抄", "ぐかんしょう"),
    # Common counters in Japanese-history scripts where generic kana converters
    # frequently choose the wrong reading.
    ("全二十巻", "ぜんにじゅっかん"),
    ("二十巻", "にじゅっかん"),
    ("四千五百首前後", "よんせんごひゃくしゅぜんご"),
    ("四千五百首", "よんせんごひゃくしゅ"),
)

KOREAN_HISTORY_READING_OVERRIDES: tuple[tuple[str, str], ...] = (
    # Korean strings should not appear in Japanese narration, but Korean topics
    # and manually edited text can leak into CH3. Convert them before TTS.
    ("다이카 개신", "たいかのかいしん"),
    ("대화개신", "たいかのかいしん"),
    ("백촌강 전투", "はくすきのえのたたかい"),
    ("백촌강의 전투", "はくすきのえのたたかい"),
    ("세키가하라 전투", "せきがはらのたたかい"),
    ("단노우라 전투", "だんのうらのたたかい"),
    ("오케하자마 전투", "おけはざまのたたかい"),
    ("나가시노 전투", "ながしののたたかい"),
    ("혼노지의 변", "ほんのうじのへん"),
    ("메이지 유신", "めいじいしん"),
    ("나라 시대", "ならじだい"),
    ("아스카 시대", "あすかじだい"),
    ("헤이안 시대", "へいあんじだい"),
    ("가마쿠라 시대", "かまくらじだい"),
    ("무로마치 시대", "むろまちじだい"),
    ("에도 시대", "えどじだい"),
    ("메이지 시대", "めいじじだい"),
    ("조몬 토기", "じょうもんどき"),
    ("야요이 토기", "やよいどき"),
    ("만요슈", "まんようしゅう"),
    ("만엽집", "まんようしゅう"),
    ("고사기", "こじき"),
    ("고지키", "こじき"),
    ("일본서기", "にほんしょき"),
    ("니혼쇼키", "にほんしょき"),
    ("위지왜인전", "ぎしわじんでん"),
    ("수서왜국전", "ずいしょわこくでん"),
    ("송서왜국전", "そうしょわこくでん"),
    ("동가", "あずまうた"),
    ("아즈마우타", "あずまうた"),
    ("사키모리우타", "さきもりうた"),
    ("방인가", "さきもりうた"),
    ("만요가나", "まんようがな"),
    ("쇼무천황", "しょうむてんのう"),
    ("덴무천황", "てんむてんのう"),
    ("텐무천황", "てんむてんのう"),
    ("덴지천황", "てんじてんのう"),
    ("텐지천황", "てんじてんのう"),
    ("스이코천황", "すいこてんのう"),
    ("진무천황", "じんむてんのう"),
    ("유랴쿠천황", "ゆうりゃくてんのう"),
    ("게이타이천황", "けいたいてんのう"),
    ("오토모노 야카모치", "おおとものやかもち"),
    ("오토모노야카모치", "おおとものやかもち"),
    ("소가노 이루카", "そがのいるか"),
    ("소가노이루카", "そがのいるか"),
    ("소가노 우마코", "そがのうまこ"),
    ("소가노우마코", "そがのうまこ"),
    ("후지와라노 후히토", "ふじわらのふひと"),
    ("후지와라노후히토", "ふじわらのふひと"),
    ("쇼토쿠태자", "しょうとくたいし"),
    ("쇼토쿠 태자", "しょうとくたいし"),
    ("히미코", "ひみこ"),
    ("야마타이국", "やまたいこく"),
    ("야마토 왕권", "やまとおうけん"),
    ("야마토정권", "やまとせいけん"),
    ("야마토 정권", "やまとせいけん"),
    ("조몬인", "じょうもんじん"),
    ("야요이인", "やよいじん"),
    ("조몬", "じょうもん"),
    ("야요이", "やよい"),
    ("신라", "しらぎ"),
    ("백제", "くだら"),
    ("고구려", "こうくり"),
    ("가야", "かや"),
    ("가라", "から"),
    ("임나", "みまな"),
    ("왜국", "わこく"),
    ("왜", "わ"),
    ("당나라", "とう"),
    ("수나라", "ずい"),
    ("한나라", "かん"),
    ("위나라", "ぎ"),
    ("오나라", "ご"),
    ("연나라", "えん"),
    ("중국", "ちゅうごく"),
    ("한국", "かんこく"),
    ("한반도", "ちょうせんはんとう"),
    ("일본", "にほん"),
)

_OKIMI_CONTEXT_RE = re.compile(
    r"(大和|ヤマト|倭|古墳|飛鳥|王権|豪族|蘇我|物部|百済|新羅|高句麗|雄略|継体|欽明|推古|斉明|天智|天武|持統|ワカタケル)"
)
_SPACE_RE = re.compile(r"\s+")
_KATAKANA_RE = re.compile(r"[\u30a1-\u30f6]")
_KANJI_RE = re.compile(r"[\u3400-\u9fff]")
_HANGUL_RE = re.compile(r"[\uac00-\ud7a3]+")
_UNRESOLVED_TERM_RE = re.compile(r"[\u3400-\u9fff\uac00-\ud7a3]{1,24}")


def katakana_to_hiragana(text: str) -> str:
    def _one(ch: str) -> str:
        code = ord(ch)
        if 0x30A1 <= code <= 0x30F6:
            return chr(code - 0x60)
        return ch

    return "".join(_one(ch) for ch in str(text or ""))


def _reading_files() -> tuple[Path, ...]:
    return (
        SYSTEM_DIR / "japanese_readings.json",
        SYSTEM_DIR / "japanese_readings.generated.json",
        BASE_DIR / "data" / "_system" / "japanese_readings.json",
        BASE_DIR / "data" / "_system" / "japanese_readings.generated.json",
    )


def _coerce_entries(payload: object) -> Iterable[tuple[str, str]]:
    if isinstance(payload, dict):
        entries = payload.get("entries") if isinstance(payload.get("entries"), (list, dict)) else payload
        if isinstance(entries, dict):
            for source, reading in entries.items():
                yield str(source), str(reading)
            return
        payload = entries
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                source = item.get("source") or item.get("term") or item.get("surface")
                reading = item.get("reading") or item.get("yomi") or item.get("spoken")
                if source and reading:
                    yield str(source), str(reading)
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                yield str(item[0]), str(item[1])


def _generated_entry_allowed(source: str) -> bool:
    # Generic dictionaries include foreign names such as アレクサンドロス大王.
    # Do not let generated data override context-sensitive 大王 handling.
    if "大王" in source and not _OKIMI_CONTEXT_RE.search(source):
        return False
    return True


@lru_cache(maxsize=1)
def load_local_japanese_readings() -> tuple[tuple[str, str], ...]:
    out: list[tuple[str, str]] = []
    for path in _reading_files():
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        is_generated = path.name.endswith(".generated.json")
        for source, reading in _coerce_entries(payload):
            source = source.strip()
            reading = katakana_to_hiragana(reading.strip())
            if is_generated and not _generated_entry_allowed(source):
                continue
            if source and reading and source != reading:
                out.append((source, reading))
    return tuple(out)


def merged_japanese_readings(
    base_replacements: Iterable[tuple[str, str]] = (),
) -> tuple[tuple[str, str], ...]:
    # Later sources are lower priority. Local feedback wins over manual and old
    # built-ins, because comments can reveal the channel's exact mistake.
    ordered_sources = (
        load_local_japanese_readings(),
        KOREAN_HISTORY_READING_OVERRIDES,
        JAPANESE_HISTORY_READING_OVERRIDES,
        tuple(base_replacements),
    )
    merged: dict[str, str] = {}
    for source_entries in ordered_sources:
        for source, reading in source_entries:
            source = str(source or "").strip()
            reading = katakana_to_hiragana(str(reading or "").strip())
            if not source or not reading or source in merged:
                continue
            merged[source] = reading
    return tuple(sorted(merged.items(), key=lambda item: len(item[0]), reverse=True))


def apply_japanese_context_readings(text: str) -> str:
    result = str(text or "")
    # 大王 is context-dependent. Avoid changing Alexander/foreign "大王" uses
    # into おおきみ. In Yamato/ancient Japan context it is normally the requested
    # reading.
    if "大王" in result and _OKIMI_CONTEXT_RE.search(result):
        result = result.replace("大王", "おおきみ")
    return result


@lru_cache(maxsize=1)
def _kana_converter():
    try:
        import pykakasi

        return pykakasi.kakasi()
    except Exception:
        return None


def _convert_remaining_kanji_to_hiragana(text: str) -> str:
    result = str(text or "")
    if not _KANJI_RE.search(result):
        return result
    converter = _kana_converter()
    if converter is None:
        return result
    try:
        converted = converter.convert(result)
    except Exception:
        return result
    out = "".join(
        str(item.get("hira") or item.get("kana") or item.get("orig") or "")
        for item in converted
    )
    return katakana_to_hiragana(out or result)


def _normalize_leaked_korean_particles(text: str) -> str:
    result = str(text or "")
    result = re.sub(r"(?<=[ぁ-ん])\s*(?:와|과)\s*(?=[ぁ-ん])", "と", result)
    result = re.sub(r"(?<=[ぁ-ん])(?:은|는)", "は", result)
    result = re.sub(r"(?<=[ぁ-ん])(?:이|가)", "が", result)
    result = re.sub(r"(?<=[ぁ-ん])(?:을|를)", "を", result)
    result = re.sub(r"(?<=[ぁ-ん])의", "の", result)
    result = re.sub(r"(?<=[ぁ-ん])에서", "で", result)
    result = re.sub(r"(?<=[ぁ-ん])(?:으로|로)", "で", result)
    return result


def unresolved_japanese_reading_terms(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for match in _UNRESOLVED_TERM_RE.finditer(str(text or "")):
        term = match.group(0)
        if term and term not in seen:
            seen.add(term)
            out.append(term)
    return out


def log_unresolved_japanese_readings(source_text: str, spoken_text: str) -> None:
    terms = unresolved_japanese_reading_terms(spoken_text)
    if not terms:
        return
    try:
        path = SYSTEM_DIR / "japanese_reading_missing.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "terms": terms,
            "source_text": str(source_text or "")[:500],
            "spoken_text": str(spoken_text or "")[:500],
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def normalize_japanese_readings(
    text: str,
    base_replacements: Iterable[tuple[str, str]] = (),
) -> str:
    result = apply_japanese_context_readings(str(text or ""))
    for source, reading in merged_japanese_readings(base_replacements):
        if source in result:
            result = result.replace(source, reading)
    result = _normalize_leaked_korean_particles(result)
    result = _convert_remaining_kanji_to_hiragana(result)
    result = _normalize_leaked_korean_particles(result)
    return _SPACE_RE.sub(" ", result).strip()


def contains_katakana(text: str) -> bool:
    return bool(_KATAKANA_RE.search(str(text or "")))
