from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import resolve_project_dir  # noqa: E402
from scripts.ch2_europe_titles_en import english_episode_title  # noqa: E402


DEFAULT_WORKBOOKS = (
    Path(r"Z:\HDD2\longtube\CH2 유럽사\유럽사\유럽사_시즌1_EP01-34_한영_5100컷_통합대본.xlsx"),
    Path(r"Z:\HDD2\longtube\CH2 유럽사\유럽사\유럽사_시즌2_EP035-069_한영_5250컷_통합대본.xlsx"),
    Path(r"Z:\HDD2\longtube\CH2 유럽사\유럽사\유럽사_시즌3_EP070-101_한영_4800컷_통합대본.xlsx"),
    Path(r"Z:\HDD2\longtube\CH2 유럽사\유럽사\유럽사_시즌4_EP102-130_한영_4350컷_통합대본.xlsx"),
    Path(r"Z:\HDD2\longtube\CH2 유럽사\유럽사\유럽사_시즌5_EP131-179_한영_7350컷_통합대본.xlsx"),
)
# Backward-compatible name for callers that still import it. Production uses
# DEFAULT_WORKBOOKS and convert_workbooks().
DEFAULT_WORKBOOK = DEFAULT_WORKBOOKS[0]
DEFAULT_OUTPUT_DIR = resolve_project_dir(
    "e6619f7e",
    {"channel": 2, "youtube_channel": 2},
    create=False,
) / "prepared_scripts"

LEGACY_EP_SHEET_RE = re.compile(r"^EP(\d{3})$")
INTEGRATED_EP_SHEET_RE = re.compile(r"^EP(\d{2,3})_(.+)$")
EP_SHEET_RE = LEGACY_EP_SHEET_RE
HANGUL_RE = re.compile(r"[가-힣]")
CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")
CUT_RE = re.compile(r"^(\d{3})")

EXPECTED_HEADER = [
    "컷번호 / Shorts 표시",
    "Shorts Series",
    "Shorts Cut",
    "Segment",
    "English Dialogue (4~7 sec)",
    "French Dialogue",
    "Spanish Dialogue",
    "German Dialogue",
    "FLUX2 4B Prompt",
    "Negative Prompt",
    "Cue Sheet Reference",
]

INTEGRATED_EXPECTED_HEADER = [
    "컷번호",
    "숏츠태그",
    "대사(한국어)",
    "Dialogue (English)",
    "이미지프롬프트",
]
INTEGRATED_META_LABELS = (
    "에피소드 번호",
    "에피소드 제목",
    "썸네일 문구",
    "썸네일 이미지 프롬프트",
    "시기",
    "배경 국가",
    "배경 지역",
)
EXPECTED_SOURCE_RANGES = {
    DEFAULT_WORKBOOKS[0].name: (1, 34),
    DEFAULT_WORKBOOKS[1].name: (35, 69),
    DEFAULT_WORKBOOKS[2].name: (70, 101),
    DEFAULT_WORKBOOKS[3].name: (102, 130),
    DEFAULT_WORKBOOKS[4].name: (131, 179),
}
SCRIPT_VERSION = "prepared-ch2-europe-en-v2"
SOURCE_LOCKED_VISUAL_POLICY_MODE = "source-locked"

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

_DIRECT_CAPTION_TEMPLATES = {
    1: {
        "en": "Before this became history, someone had to live through it.",
        "fr": "Avant que cela n'entre dans l'histoire, quelqu'un a dû le vivre.",
        "es": "Antes de que esto pasara a la historia, alguien tuvo que vivirlo.",
        "de": "Bevor dies Geschichte wurde, musste jemand es durchleben.",
    },
    2: {
        "en": "The shocking part is not what happened, but how normal it first seemed.",
        "fr": "Le plus choquant n'est pas ce qui s'est passé, mais l'apparente normalité du début.",
        "es": "Lo más impactante no es lo que ocurrió, sino lo normal que pareció al principio.",
        "de": "Das Erschreckende ist nicht, was geschah, sondern wie normal es anfangs wirkte.",
    },
    3: {
        "en": "In this world, one quiet decision began to tear everything apart.",
        "fr": "Dans ce monde, une décision discrète a commencé à tout déchirer.",
        "es": "En este mundo, una decisión silenciosa empezó a destrozarlo todo.",
        "de": "In dieser Welt begann eine stille Entscheidung, alles auseinanderzureißen.",
    },
    4: {
        "en": "This story begins {era}, when fear still wore a familiar face.",
        "fr": "Cette histoire commence {era}, quand la peur avait encore un visage familier.",
        "es": "Esta historia comienza {era}, cuando el miedo aún tenía un rostro familiar.",
        "de": "Diese Geschichte beginnt {era}, als die Angst noch ein vertrautes Gesicht trug.",
    },
    13: {
        "en": "That is why this story still feels unsettling today.",
        "fr": "Voilà pourquoi cette histoire reste troublante aujourd'hui.",
        "es": "Por eso esta historia sigue resultando inquietante hoy.",
        "de": "Deshalb wirkt diese Geschichte bis heute beunruhigend.",
    },
    16: {
        "en": "The world around them was not empty; it was already full of fear.",
        "fr": "Le monde qui les entourait n'était pas vide ; il était déjà rempli de peur.",
        "es": "El mundo que los rodeaba no estaba vacío; ya estaba lleno de miedo.",
        "de": "Die Welt um sie herum war nicht leer; sie war bereits voller Angst.",
    },
    19: {
        "en": "It was the first sign that the balance was already breaking.",
        "fr": "C'était le premier signe que l'équilibre était déjà en train de céder.",
        "es": "Fue la primera señal de que el equilibrio ya empezaba a romperse.",
        "de": "Es war das erste Zeichen dafür, dass das Gleichgewicht bereits zerbrach.",
    },
    23: {
        "en": "{era}, survival often meant obeying a system no one could question.",
        "fr": "{era}, survivre signifiait souvent obéir à un système que personne ne pouvait contester.",
        "es": "{era}, sobrevivir solía significar obedecer un sistema que nadie podía cuestionar.",
        "de": "{era} bedeutete Überleben oft, einem System zu gehorchen, das niemand infrage stellen durfte.",
    },
    32: {
        "en": "The crisis did not come from nowhere; it grew out of older fractures.",
        "fr": "La crise n'est pas sortie de nulle part ; elle est née de fractures plus anciennes.",
        "es": "La crisis no surgió de la nada; creció a partir de fracturas más antiguas.",
        "de": "Die Krise kam nicht aus dem Nichts; sie wuchs aus älteren Brüchen.",
    },
    42: {
        "en": "Ordinary people paid the price long before the victors wrote the chapter.",
        "fr": "Les gens ordinaires ont payé le prix bien avant que les vainqueurs n'écrivent le chapitre.",
        "es": "La gente común pagó el precio mucho antes de que los vencedores escribieran el capítulo.",
        "de": "Gewöhnliche Menschen zahlten den Preis, lange bevor die Sieger das Kapitel schrieben.",
    },
    47: {
        "en": "The crisis did not come from nowhere; it grew out of older fractures.",
        "fr": "La crise n'est pas sortie de nulle part ; elle est née de fractures plus anciennes.",
        "es": "La crisis no surgió de la nada; creció a partir de fracturas más antiguas.",
        "de": "Die Krise kam nicht aus dem Nichts; sie wuchs aus älteren Brüchen.",
    },
    61: {
        "en": "Then the buried tensions erupted into an open crisis.",
        "fr": "Puis les tensions enfouies ont éclaté en crise ouverte.",
        "es": "Entonces las tensiones soterradas estallaron en una crisis abierta.",
        "de": "Dann entluden sich die verborgenen Spannungen in einer offenen Krise.",
    },
    73: {
        "en": "This place became more than geography; it became a memory of pressure.",
        "fr": "Ce lieu est devenu plus qu'un point sur la carte ; il est devenu le souvenir d'une pression.",
        "es": "Este lugar se convirtió en algo más que un punto del mapa; se volvió un recuerdo de la presión.",
        "de": "Dieser Ort wurde zu mehr als einem Punkt auf der Karte; er wurde zur Erinnerung an den Druck.",
    },
    76: {
        "en": "For those caught in it, the crisis was not a map; it was a room falling silent.",
        "fr": "Pour ceux qui la subissaient, la crise n'était pas une carte, mais une pièce qui se taisait.",
        "es": "Para quienes la sufrieron, la crisis no era un mapa, sino una habitación que quedaba en silencio.",
        "de": "Für die Betroffenen war die Krise keine Karte, sondern ein Raum, der verstummte.",
    },
    88: {
        "en": "This place became more than geography; it became a memory of pressure.",
        "fr": "Ce lieu est devenu plus qu'un point sur la carte ; il est devenu le souvenir d'une pression.",
        "es": "Este lugar se convirtió en algo más que un punto del mapa; se volvió un recuerdo de la presión.",
        "de": "Dieser Ort wurde zu mehr als einem Punkt auf der Karte; er wurde zur Erinnerung an den Druck.",
    },
    92: {
        "en": "That reversal changed the meaning of everything that came before it.",
        "fr": "Ce renversement a changé le sens de tout ce qui l'avait précédé.",
        "es": "Ese giro cambió el significado de todo lo anterior.",
        "de": "Diese Wendung veränderte die Bedeutung von allem, was davor gekommen war.",
    },
    107: {
        "en": "That reversal changed the meaning of everything that came before it.",
        "fr": "Ce renversement a changé le sens de tout ce qui l'avait précédé.",
        "es": "Ese giro cambió el significado de todo lo anterior.",
        "de": "Diese Wendung veränderte die Bedeutung von allem, was davor gekommen war.",
    },
    124: {
        "en": "This became the official interpretation, but never the only one.",
        "fr": "Cela est devenu l'interprétation officielle, mais jamais la seule.",
        "es": "Esta se convirtió en la interpretación oficial, pero nunca en la única.",
        "de": "Dies wurde zur offiziellen Deutung, aber nie zur einzigen.",
    },
    136: {
        "en": "So this is not only a story about the past.",
        "fr": "Ce n'est donc pas seulement une histoire du passé.",
        "es": "Por eso, esta no es solo una historia del pasado.",
        "de": "Dies ist also nicht nur eine Geschichte über die Vergangenheit.",
    },
}


def _column_name(column: int) -> str:
    out = ""
    while column:
        column, remainder = divmod(column - 1, 26)
        out = chr(65 + remainder) + out
    return out


def _column_index(reference: str) -> int:
    match = re.match(r"([A-Z]+)", reference.upper())
    if not match:
        raise ValueError(f"invalid cell reference: {reference}")
    out = 0
    for char in match.group(1):
        out = out * 26 + ord(char) - 64
    return out


@dataclass(frozen=True)
class _Cell:
    value: Any
    coordinate: str


class _Worksheet:
    def __init__(self, title: str, cells: dict[tuple[int, int], Any]):
        self.title = title
        self._cells = cells
        self.max_row = max((row for row, _ in cells), default=0)
        self.max_column = max((column for _, column in cells), default=0)

    def cell(self, row: int, column: int) -> _Cell:
        return _Cell(
            value=self._cells.get((row, column)),
            coordinate=f"{_column_name(column)}{row}",
        )


class _Workbook:
    def __init__(self, sheets: dict[str, _Worksheet]):
        self._sheets = sheets
        self.sheetnames = list(sheets)

    def __getitem__(self, name: str) -> _Worksheet:
        return self._sheets[name]


def _xml_text(node: ET.Element, tag: str) -> str:
    return "".join(
        child.text or "" for child in node.iter(f"{{{_MAIN_NS}}}{tag}")
    )


def _xlsx_cell_value(cell: ET.Element, shared_strings: list[str]) -> Any:
    cell_type = cell.attrib.get("t", "")
    if cell_type == "inlineStr":
        return _xml_text(cell, "t")
    value_node = cell.find(f"{{{_MAIN_NS}}}v")
    raw = value_node.text if value_node is not None and value_node.text is not None else ""
    if cell_type == "s" and raw:
        return shared_strings[int(raw)]
    if cell_type == "b":
        return raw == "1"
    return raw


def _load_xlsx_workbook(
    path: Path,
    *,
    sheet_names: set[str] | None = None,
) -> _Workbook:
    with zipfile.ZipFile(path) as archive:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared_strings = [
                _xml_text(item, "t")
                for item in root.findall(f"{{{_MAIN_NS}}}si")
            ]

        workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
        rels_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        relationships = {
            rel.attrib["Id"]: rel.attrib["Target"]
            for rel in rels_root.findall(f"{{{_PACKAGE_REL_NS}}}Relationship")
        }
        sheets: dict[str, _Worksheet] = {}
        sheets_node = workbook_root.find(f"{{{_MAIN_NS}}}sheets")
        if sheets_node is None:
            raise ValueError("workbook contains no sheets")
        for sheet_node in sheets_node:
            name = sheet_node.attrib["name"]
            if sheet_names is not None and name not in sheet_names:
                continue
            rel_id = sheet_node.attrib[f"{{{_OFFICE_REL_NS}}}id"]
            target = relationships[rel_id].replace("\\", "/")
            if target.startswith("/"):
                sheet_path = target.lstrip("/")
            else:
                sheet_path = posixpath.normpath(posixpath.join("xl", target))
            sheet_root = ET.fromstring(archive.read(sheet_path))
            cells: dict[tuple[int, int], Any] = {}
            for cell in sheet_root.iter(f"{{{_MAIN_NS}}}c"):
                reference = cell.attrib.get("r", "")
                row_match = re.search(r"(\d+)$", reference)
                if not row_match:
                    continue
                row = int(row_match.group(1))
                column = _column_index(reference)
                cells[(row, column)] = _xlsx_cell_value(cell, shared_strings)
            sheets[name] = _Worksheet(name, cells)
    return _Workbook(sheets)


def _compact_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\r", " ").replace("\n", " ")).strip()


def _clean_flux_prompt(value: Any) -> str:
    text = _compact_text(value)
    text = re.sub(r"^\s*FLUX2\s+4B\s+optimized\s+prompt:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(
        r";\s*narration\s+beat:\s*[“\"].*?[”\"]",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r";\s*context:\s*.*?(?=;\s*(?:ancient|medieval|early|modern|mythic|unique|blue|silver|moonlit|greenish|cinematic)\b|$)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", text).strip(" ;")


_INTEGRATED_PERIOD_OVERRIDES = {
    1: ("기원전 4500~2500년경으로 재구성되는 신화적 선사", "c. 4500-2500 BCE, reconstructed mythic prehistory"),
    3: ("기원전 3000~1000년경과 후대에 기록된 비교 전승", "c. 3000-1000 BCE and later comparative traditions"),
    4: ("신화적으로 재구성되는 선사와 후대 인도·이란·그리스·로마 전승", "mythic prehistory and later Indo-Iranian, Greek, and Roman traditions"),
    5: ("기원전 2000~1200년경을 배경으로 형성된 그리스 신화와 후대 지명 전승", "c. 2000-1200 BCE and later Greek place-name traditions"),
    6: ("기원전 1600~1450년경을 중심으로 한 크레타 청동기시대", "c. 1600-1450 BCE, Bronze Age Crete"),
    8: ("기원전 12세기 전승과 기원전 8세기경 정리된 서사시", "12th-century BCE tradition and epics compiled around the 8th century BCE"),
    9: ("기원전 776년경부터 고대 후기", "from c. 776 BCE through Late Antiquity"),
    10: ("기원전 753년으로 전하는 건국 신화와 초기 철기시대 로마", "753 BCE traditional foundation date and early Iron Age Rome"),
    11: ("기원전 8세기로 전하는 초기 로마 건국 전승", "8th-century BCE Roman foundation tradition"),
    12: ("기원전 594~508년 개혁을 중심으로 한 고대 아테네", "594-508 BCE, ancient Athens"),
    13: ("기원전 509년으로 전하는 왕정 종말과 초기 공화정", "509 BCE traditional fall of the monarchy and early Roman Republic"),
    21: ("서기 64년을 중심으로 한 네로 치세", "64 CE, reign of Nero"),
    22: ("서기 66~73년, 예루살렘 함락은 70년", "66-73 CE, including the fall of Jerusalem in 70 CE"),
}

_GLOBAL_ENGLISH_FIXES = {
    "Now, let's follow the steps one by one, starting with the selection of the first character.": (
        "Now, let's follow the story step by step, beginning with the first person's decision.",
        145,
    ),
    "No one could have predicted the final twist yet.": (
        "At that point, no one could foresee the final twist.",
        145,
    ),
    "As you follow the choices of years and people, the results become clearer.": (
        "Following the chronology and each person's decisions makes the outcome clearer.",
        132,
    ),
    "However, controversial parts must be viewed separately between fact and tradition.": (
        "However, disputed passages require us to distinguish fact from tradition.",
        13,
    ),
}

# Every entry is guarded by the exact source sentence. A changed workbook fails
# closed instead of receiving a stale correction.
_VERIFIED_ENGLISH_OVERRIDES = {
    (10, 111): ("753 BC is the traditional date calculated and widely established by later scholar Pharaoh.", "753 BC is the traditional date calculated and popularized by the later Roman scholar Varro."),
    (10, 150): ("Please join us by subscribing and liking Daum Roman History.", "Please subscribe and like so you don't miss the next episode."),
    (11, 150): ("Please join us by subscribing and liking Daum Democracy.", "Please subscribe and like so you don't miss the next episode."),
    (13, 150): ("Please join us by subscribing and liking Daum War History.", "Please subscribe and like so you don't miss the next episode."),
    (15, 150): ("Please join us by subscribing and liking Daum Boksa’s one-way tour.", "Please subscribe and like so you don't miss the next episode."),
    (20, 150): ("Please subscribe and like the next Emperor's Disaster Politics.", "Please subscribe and like so you don't miss the next episode."),
    (21, 150): ("Please join us by subscribing and liking Daum War History.", "Please subscribe and like so you don't miss the next episode."),
    (40, 42): ("The etymology of Scoringa is uncertain, but it probably refers to the coastal coastal region.", "The etymology of Scoringa is uncertain, but it probably refers to a coastal region."),
    (42, 7): ("The stage was Frankfurt-Tours/Poitiers, early medieval to early medieval Europe.", "The setting was the Frankish realm around Tours and Poitiers in early medieval Europe."),
    (53, 148): ("A new dynasty began with the election of Wig Cafe.", "A new dynasty began with the election of Hugh Capet."),
    (54, 3): ("A new dynasty began with the election of Wig Cafe.", "A new dynasty began with the election of Hugh Capet."),
    (54, 109): ("Includes male, male lineage, and legitimate non-maternal members of the family who lived to adulthood or held ownership as children.", "This includes legitimate, non-morganatic male-line members of the house who either lived to adulthood or held a title as children."),
    (54, 137): ("Then, a new dynasty began with the election of Wig Cafe.", "Then, a new dynasty began with the election of Hugh Capet."),
    (55, 132): ("By whom are statements and foundations often interpreted? It symbolizes God's people before and after Christ.", "The gates and foundations are often interpreted as symbols of God's people before and after Christ."),
    (59, 146): ("The next episode deals with the Erfurt Ratrine disaster.", "The next episode deals with the Erfurt latrine disaster."),
    (60, 10): ("At the center was the Erfurt Ratrine disaster.", "At the center was the Erfurt latrine disaster."),
    (60, 12): ("The core of this incident was the Erfurt Ratrine disaster.", "The core of this incident was the Erfurt latrine disaster."),
    (60, 14): ("Against that backdrop, the story of the Erfurt Ratrine disaster begins.", "Against that backdrop, the story of the Erfurt latrine disaster begins."),
    (60, 142): ("This passage is the historical significance of the Erfurt Ratrine disaster.", "This passage is the historical significance of the Erfurt latrine disaster."),
    (61, 11): ("The results of the previous episode's 'Erfurt Ratrine disaster' serve as the background for this conflict.", "The results of the previous episode's 'Erfurt latrine disaster' serve as the background for this conflict."),
    (68, 85): ("Corn Corn was resold for a penny a pound.", "Grain was resold for one penny per pound."),
    (69, 1): ("The legend of Pharaoh killing a king and washing himself in the blood of a horse.", "This is the legend of a king killed and washed in horse's blood."),
    (69, 17): ("There is a record that the tomb of the 18th Duke of Gong Gong, who died in 537 BC, has been excavated.", "Records state that the tomb of Duke Jing of Qin, the state's eighteenth ruler, who died in 537 BC, was excavated."),
    (71, 40): ("At this time, this flea species is the main vector for transmitting Yersinia pestis, the organism that spreads bubonic plague in most infectious diseases.", "This flea species is a major vector of Yersinia pestis, the bacterium that causes bubonic plague."),
    (72, 45): ("This flea species is the main vector for transmitting Yersinia pestis, the organism that spreads bubonic plague in most infectious diseases.", "This flea species is a major vector of Yersinia pestis, the bacterium that causes bubonic plague."),
    (89, 55): ("Others acted like animals, running, jumping, and jumping around.", "Others behaved like animals, running and leaping about."),
    (92, 40): ("At this time, the First Act of Supremacy made Henry supreme head of the Church of England, disregarding all customs, customs, foreign laws, foreign authorities or prescriptions.", "At that point, the First Act of Supremacy made Henry the supreme head of the Church of England, overriding contrary customs, foreign laws, foreign authorities, and prescriptions."),
    (105, 110): ("Gustav Adolphus is widely celebrated by European Protestants as a key figure who championed their cause during the Thirty Years' War, and is celebrated in several churches, churches, and churches.", "Gustavus Adolphus is widely commemorated by European Protestants as a leading defender of their cause during the Thirty Years' War."),
    (107, 41): ("Later variants were given even fancier names derived from Alexander the Great, Scipio, and even Admiral Admiral and Admiral General.", "Later tulip varieties received even more extravagant names, drawing on Alexander the Great, Scipio, admirals, and generals."),
    (123, 34): ("Looking closely at the records at the time, was it a rebellion? Lewis asked.", "According to contemporary accounts, Louis XVI asked, ‘Is this a revolt?’"),
    (123, 35): ("This resulted in state-sponsored persecution of refractory clergy, many of whom were forcibly exiled, exiled, or executed.", "This led to state-sponsored persecution of refractory clergy; many were expelled, deported, or executed."),
    (127, 91): ("Loyalist and local rebellions were dealt with with amnesty for those who laid down their arms and brutal repression of those who continued to resist.", "Royalist and local rebellions were met with amnesty for those who laid down their arms and brutal repression for those who continued to resist."),
    (140, 29): ("The liberal nationalist idea of a unified Germany became unpopular after the fall of the Frankfurt Reichstag in 1849.", "The liberal nationalist idea of a unified Germany lost support after the collapse of the Frankfurt Parliament in 1849."),
    (144, 17): ("It is estimated that more than 100,000 indigenous warriors were invested.", "Portugal is estimated to have deployed more than 100,000 indigenous warriors."),
    (162, 120): ("Over the course of three days, the Red Army crossed the Naref River on a wide four-front front and launched the Vistula-Oder Offensive from Warsaw.", "Over three days, the Red Army crossed the Narew River along a broad line formed by four fronts and launched the Vistula-Oder Offensive from Warsaw."),
    (172, 22): ("It was the largest mass exodus since the Berlin Wall was built in 1961.", "Reform pressure, the East German exodus, and a wave of protests across Eastern Europe were converging."),
    (172, 23): ("It was the largest exodus from East Germany since the construction of the Berlin Wall in 1961.", "Confusion over the border-opening announcement culminated in citizens surging through the Wall."),
}

_CUT_VISUAL_PERIOD_OVERRIDES = {
    (84, 65): ("The arrival of the Court will lead to more rebellions.", "Portuguese royal court in Brazil, from 1808"),
    (84, 66): ("Portugal also entered World War I.", "World War I, 1914-1918"),
    (84, 67): ("In the early stages of the war, Portugal mainly participated in supplying the Allied forces stationed in France.", "World War I, 1914-1918"),
    (84, 68): ("In the middle of that year, Portugal suffered its first casualties in World War I.", "World War I, 1914-1918"),
    (84, 69): ("Later that year, U-boats again entered Portuguese waters and once again attacked Madeira, sinking several Portuguese ships.", "World War I, 1917"),
    (84, 70): ("After almost three years of fighting, World War I ended and Germany signed an armistice.", "1918"),
    (84, 71): ("After World War II, decolonization movements began to gain momentum in the empires of European powers.", "post-1945 decolonization"),
    (84, 72): ("The ensuing Cold War created instability among Portugal's overseas population as the United States and the Soviet Union competed to expand their influence.", "Cold War, 1947-1991"),
    (84, 73): ("Portugal's new ruling authorities also recognized Goa and other territories of Portuguese India invaded by Indian troops as Indian territory.", "Portuguese decolonization, 1974-1975"),
    (84, 74): ("Portuguese is one of the world's major languages, ranked 6th overall with approximately 240 million speakers worldwide.", "contemporary period"),
    (86, 48): ("Luis Philippe's younger brother Manuel became King Manuel II of Portugal.", "1908"),
    (86, 49): ("Fighting ensued between Portuguese and German forces, resulting in reinforcements being sent from the mainland.", "World War I, 1914-1918"),
    (86, 50): ("The main goal of these soldiers was to retake the Kionga Triangle in northern Mozambique, a territory conquered by Germany.", "World War I, 1914-1918"),
    (86, 51): ("Portugal also participated in World War I.", "World War I, 1914-1918"),
    (86, 52): ("As the situation became more difficult, in the early stages of the war, Portugal mainly participated in supplying the Allied forces stationed in France.", "World War I, 1914-1918"),
    (86, 53): ("Later that year, U-boats again entered Portuguese waters and once again attacked Madeira, sinking several Portuguese ships.", "World War I, 1917"),
    (86, 54): ("After World War II, decolonization movements began to gain momentum in the empires of European powers.", "post-1945 decolonization"),
    (86, 55): ("Portugal's new ruling authorities also recognized Goa and other Portuguese Indian territories invaded by Indian troops as Indian territory.", "Portuguese decolonization, 1974-1975"),
    (86, 56): ("The Azores and Madeira Islands are the only overseas territories politically connected to Portugal.", "contemporary period"),
    (86, 57): ("Eight of Portugal's former colonies have Portuguese as their official language.", "contemporary period"),
    (86, 58): ("Additionally, 12 candidate countries or regions have applied for membership to the CPLP and are awaiting approval.", "contemporary period"),
}

_CAMERA_CLAUSE_RE = re.compile(
    r"\b(?:extreme wide establishing shot|medium tracking shot|tight emotional close-up|"
    r"low-angle medium shot|high-angle overview|over-the-shoulder composition|"
    r"ground-level action shot|three-quarter(?: historical)? portrait|wide lateral composition|"
    r"intimate interior scene|documentary-style observational shot|somber aftermath tableau|"
    r"telephoto compression (?:shot|across)|dynamic diagonal composition|cinematic transition frame)\b",
    re.IGNORECASE,
)
_FORBIDDEN_ENGLISH_FRAGMENTS = (
    "Wig Cafe",
    "Ratrine",
    "Daum",
    "Frankfurt Reichstag",
    "coastal coastal",
    "Corn Corn",
    "customs, customs",
    "churches, churches",
    "Admiral Admiral",
    "exiled, exiled",
    "dealt with with",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _integrated_episode_period(episode_number: int, source_period: str) -> str:
    override = _INTEGRATED_PERIOD_OVERRIDES.get(episode_number)
    if override is not None:
        expected, translated = override
        if source_period != expected:
            raise ValueError(
                f"EP{episode_number:03d}: period override source mismatch: {source_period!r}"
            )
        return translated
    return _localized_era(source_period, "en")


def _apply_verified_english_fix(
    episode_number: int,
    cut_number: int,
    source_text: str,
    applied: set[tuple[int, int]],
    global_counts: dict[str, int],
) -> str:
    key = (episode_number, cut_number)
    specific = _VERIFIED_ENGLISH_OVERRIDES.get(key)
    if specific is not None:
        expected, replacement = specific
        if source_text != expected:
            raise ValueError(
                f"EP{episode_number:03d} cut {cut_number:03d}: correction source mismatch"
            )
        applied.add(key)
        return replacement
    global_fix = _GLOBAL_ENGLISH_FIXES.get(source_text)
    if global_fix is not None:
        replacement, _expected_count = global_fix
        global_counts[source_text] = global_counts.get(source_text, 0) + 1
        return replacement
    return source_text


def _clean_integrated_prompt(value: Any) -> str:
    text = _compact_text(value)
    labels = list(re.finditer(r"Narrative (?:moment|beat):", text, flags=re.IGNORECASE))
    if len(labels) != 1:
        raise ValueError(f"expected exactly one Narrative label, got {len(labels)}")
    label = labels[0]
    prefix = text[: label.start()].strip(" .;")
    remainder = text[label.end() :].strip()
    camera = _CAMERA_CLAUSE_RE.search(remainder)
    if camera is None:
        raise ValueError("camera clause not found after Narrative label")
    scene_tail = remainder[camera.start() :].strip()
    cleaned = f"{prefix}. {scene_tail}" if prefix else scene_tail
    cleaned = re.sub(
        r"\bno modern objects\b",
        "no objects, clothing, architecture, vehicles, or weapons outside the depicted period",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\bis led toward the next episode\b",
        "is led forward",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\.{2,}", ".", cleaned)
    cleaned = re.sub(r",\s*\.", ".", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ;")
    if re.search(r"Narrative (?:moment|beat):", cleaned, flags=re.IGNORECASE):
        raise ValueError("Narrative label remains after prompt cleanup")
    if re.search(r"\bno modern objects\b", cleaned, flags=re.IGNORECASE):
        raise ValueError("no modern objects remains after prompt cleanup")
    if re.search(r"\bnext episode\b", cleaned, flags=re.IGNORECASE):
        raise ValueError("next episode remains after prompt cleanup")
    if CJK_RE.search(cleaned):
        raise ValueError("CJK remains after prompt cleanup")
    if re.search(r"\.{2,}", cleaned):
        raise ValueError("duplicate period remains after prompt cleanup")
    return cleaned


def _set_prompt_period(prompt: str, visual_period: str) -> str:
    replacement = f", set during {visual_period}."
    out, count = re.subn(
        r",\s*set around [^.]+\.",
        replacement,
        prompt,
        count=1,
        flags=re.IGNORECASE,
    )
    return out if count else prompt


def _integrated_shorts_tag(value: Any) -> tuple[int, int] | None:
    text = _compact_text(value)
    if not text:
        return None
    match = re.fullmatch(r"#([1-4])-(\d{1,2})", text)
    if not match:
        raise ValueError(f"invalid shorts tag: {text!r}")
    return int(match.group(1)), int(match.group(2))


def _roman_number(value: int) -> str:
    numerals = (
        (1000, "M"),
        (900, "CM"),
        (500, "D"),
        (400, "CD"),
        (100, "C"),
        (90, "XC"),
        (50, "L"),
        (40, "XL"),
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    )
    out = ""
    remaining = value
    for number, numeral in numerals:
        while remaining >= number:
            out += numeral
            remaining -= number
    return out


def _english_ordinal(value: int) -> str:
    if 10 < value % 100 < 14:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"


def _year_label(value: str, lang: str, bce: bool) -> str:
    if not bce:
        return value
    return {
        "en": f"{value} BCE",
        "fr": f"{value} av. J.-C.",
        "es": f"{value} a. C.",
        "de": f"{value} v. Chr.",
    }[lang]


def _localized_era(value: Any, lang: str) -> str:
    if lang not in {"en", "fr", "es", "de"}:
        raise ValueError(f"unsupported era language: {lang}")
    text = _compact_text(value).replace("〜", "~").replace("–", "~")
    exact = {
        "신화적 선사": {
            "en": "in mythic prehistory",
            "fr": "dans la préhistoire mythique",
            "es": "en la prehistoria mítica",
            "de": "in mythischer Vorzeit",
        },
        "중세 전승": {
            "en": "in a medieval tradition",
            "fr": "dans une tradition médiévale",
            "es": "en una tradición medieval",
            "de": "in einer mittelalterlichen Überlieferung",
        },
        "총결산": {
            "en": "in the final overview",
            "fr": "dans le bilan final",
            "es": "en el balance final",
            "de": "in der abschließenden Bilanz",
        },
    }
    if text in exact:
        return exact[text][lang]

    bce = text.startswith("기원전")
    if bce:
        text = text.removeprefix("기원전").strip()

    if re.fullmatch(r"\d{3,4}년~현재", text):
        year = re.match(r"(\d+)", text).group(1)
        return {
            "en": f"from {year} to the present",
            "fr": f"de {year} à aujourd'hui",
            "es": f"desde {year} hasta la actualidad",
            "de": f"von {year} bis heute",
        }[lang]

    tradition = False
    if text.endswith("전승·인물"):
        tradition = True
        text = text[: -len("전승·인물")].strip()
    elif text.endswith("전승"):
        tradition = True
        text = text[: -len("전승")].strip()

    modifier = ""
    for suffix, name in (
        ("이후", "after"),
        ("전후", "around"),
        ("전반", "early"),
        ("후반", "late"),
        ("말", "late"),
    ):
        if text.endswith(suffix):
            modifier = name
            text = text[: -len(suffix)].strip()
            break
    if text.endswith("경"):
        modifier = "around"
        text = text[:-1].strip()

    month_match = re.fullmatch(r"(\d+)년\s+(\d+)월", text)
    if month_match:
        year, month_text = month_match.groups()
        month = int(month_text)
        month_names = {
            "en": ("", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"),
            "fr": ("", "janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"),
            "es": ("", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"),
            "de": ("", "Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"),
        }
        if not 1 <= month <= 12:
            raise ValueError(f"invalid month in era: {value}")
        name = month_names[lang][month]
        return {
            "en": f"in {name} {year}",
            "fr": f"en {name} {year}",
            "es": f"en {name} de {year}",
            "de": f"im {name} {year}",
        }[lang]

    year_range = re.fullmatch(r"(\d+)~(\d+)년", text)
    if year_range:
        first, second = year_range.groups()
        first_label = _year_label(first, lang, False)
        second_label = _year_label(second, lang, bce)
        if modifier == "around":
            joined = f"{first}-{second}"
            label = _year_label(joined, lang, bce)
            return {
                "en": f"around {label}",
                "fr": f"vers {label}",
                "es": f"hacia {label}",
                "de": f"etwa {label}",
            }[lang]
        if tradition:
            return {
                "en": f"in traditions from {first_label} to {second_label}",
                "fr": f"dans des traditions allant de {first_label} à {second_label}",
                "es": f"en tradiciones de {first_label} a {second_label}",
                "de": f"in Überlieferungen aus der Zeit von {first_label} bis {second_label}",
            }[lang]
        return {
            "en": f"between {first_label} and {second_label}",
            "fr": f"entre {first_label} et {second_label}",
            "es": f"entre {first_label} y {second_label}",
            "de": f"zwischen {first_label} und {second_label}",
        }[lang]

    year_match = re.fullmatch(r"(\d+)년", text)
    if year_match:
        label = _year_label(year_match.group(1), lang, bce)
        if tradition:
            return {
                "en": f"in a tradition dated to {label}",
                "fr": f"dans une tradition datée de {label}",
                "es": f"en una tradición fechada en {label}",
                "de": f"in einer Überlieferung aus dem Jahr {label}",
            }[lang]
        if modifier == "after":
            return {
                "en": f"after {label}",
                "fr": f"après {label}",
                "es": f"después de {label}",
                "de": f"nach {label}",
            }[lang]
        if modifier == "around":
            return {
                "en": f"around {label}",
                "fr": f"vers {label}",
                "es": f"hacia {label}",
                "de": f"um das Jahr {label}",
            }[lang]
        return {
            "en": f"in {label}",
            "fr": f"en {label}",
            "es": f"en {label}",
            "de": f"im Jahr {label}",
        }[lang]

    century_range = re.fullmatch(r"(\d+)~(\d+)세기", text)
    if century_range:
        first, second = map(int, century_range.groups())
        if bce:
            raise ValueError(f"unsupported BCE century range: {value}")
        if tradition:
            return {
                "en": f"in traditions from the {_english_ordinal(first)} and {_english_ordinal(second)} centuries",
                "fr": f"dans des traditions des {_roman_number(first)}e et {_roman_number(second)}e siècles",
                "es": f"en tradiciones de los siglos {_roman_number(first)} y {_roman_number(second)}",
                "de": f"in Überlieferungen aus dem {first}. und {second}. Jahrhundert",
            }[lang]
        return {
            "en": f"between the {_english_ordinal(first)} and {_english_ordinal(second)} centuries",
            "fr": f"entre les {_roman_number(first)}e et {_roman_number(second)}e siècles",
            "es": f"entre los siglos {_roman_number(first)} y {_roman_number(second)}",
            "de": f"zwischen dem {first}. und {second}. Jahrhundert",
        }[lang]

    century_match = re.fullmatch(r"(\d+)세기", text)
    if century_match:
        century = int(century_match.group(1))
        labels = {
            "en": f"{_english_ordinal(century)} century" + (" BCE" if bce else ""),
            "fr": f"{_roman_number(century)}e siècle" + (" av. J.-C." if bce else ""),
            "es": f"siglo {_roman_number(century)}" + (" a. C." if bce else ""),
            "de": f"{century}. Jahrhundert" + (" v. Chr." if bce else ""),
        }
        label = labels[lang]
        if tradition:
            return {
                "en": f"in a tradition from the {label}",
                "fr": f"dans une tradition du {label}",
                "es": f"en una tradición del {label}",
                "de": f"in einer Überlieferung aus dem {label}",
            }[lang]
        if modifier == "early":
            return {
                "en": f"in the early {label}",
                "fr": f"au début du {label}",
                "es": f"a comienzos del {label}",
                "de": f"im frühen {label}",
            }[lang]
        if modifier == "late":
            return {
                "en": f"in the late {label}",
                "fr": f"à la fin du {label}",
                "es": f"a finales del {label}",
                "de": f"im späten {label}",
            }[lang]
        return {
            "en": f"in the {label}",
            "fr": f"au {label}",
            "es": f"en el {label}",
            "de": f"im {label}",
        }[lang]

    raise ValueError(f"unrecognized era: {value}")


def _sentence_initial(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def _direct_caption_translation(cut_number: int, era: Any) -> dict[str, str]:
    templates = _DIRECT_CAPTION_TEMPLATES.get(cut_number)
    if templates is None:
        raise ValueError(f"no direct translation template for cut {cut_number:03d}")
    tracks: dict[str, str] = {}
    for lang, template in templates.items():
        localized_era = _localized_era(era, lang) if "{era}" in template else ""
        if cut_number == 23:
            localized_era = _sentence_initial(localized_era)
        tracks[lang] = _compact_text(template.format(era=localized_era))
    return tracks


def _shorts_group(value: Any) -> int:
    match = re.search(r"(\d+)\s*/\s*4", str(value or ""))
    if not match:
        return 0
    try:
        return int(match.group(1))
    except ValueError:
        return 0


def _required_cell(ws, row: int, col: int, label: str, errors: list[str]) -> str:
    value = _compact_text(ws.cell(row, col).value)
    if not value:
        errors.append(f"{ws.title}: missing {label} at {ws.cell(row, col).coordinate}")
    return value


def _build_script_for_sheet(
    ws,
    workbook_path: Path,
) -> tuple[dict[str, Any] | None, list[str], int]:
    errors: list[str] = []
    match = EP_SHEET_RE.fullmatch(ws.title)
    if not match:
        return None, [f"invalid episode sheet name: {ws.title}"], 0
    episode_number = int(match.group(1))

    header = [ws.cell(9, c).value for c in range(1, 12)]
    if header != EXPECTED_HEADER:
        errors.append(f"{ws.title}: header row 9 mismatch")

    korean_title = _required_cell(ws, 2, 2, "episode title", errors)
    thumbnail_prompt = _required_cell(ws, 4, 2, "thumbnail prompt", errors)
    era = _required_cell(ws, 5, 2, "era", errors)
    background = _required_cell(ws, 6, 2, "background", errors)
    title = english_episode_title(episode_number)
    try:
        visual_year = _localized_era(era, "en")
    except ValueError as exc:
        errors.append(f"{ws.title}: {exc}")
        visual_year = ""

    cuts: list[dict[str, Any]] = []
    caption_repair_count = 0
    for row in range(10, ws.max_row + 1):
        cut_id = _compact_text(ws.cell(row, 1).value)
        cut_match = CUT_RE.match(cut_id)
        if not cut_match:
            continue
        cut_number = int(cut_match.group(1))
        en = _compact_text(ws.cell(row, 5).value)
        fr = _compact_text(ws.cell(row, 6).value)
        es = _compact_text(ws.cell(row, 7).value)
        de = _compact_text(ws.cell(row, 8).value)
        image_prompt = _clean_flux_prompt(ws.cell(row, 9).value)
        cue = _compact_text(ws.cell(row, 11).value)
        source_tracks = {"en": en, "fr": fr, "es": es, "de": de}
        missing = [
            name
            for name, value in (
                ("English", en),
                ("French", fr),
                ("Spanish", es),
                ("German", de),
                ("image_prompt", image_prompt),
            )
            if not value
        ]
        if missing:
            errors.append(f"{ws.title}: cut {cut_number:03d} missing {', '.join(missing)}")
        tracks = source_tracks
        if any(HANGUL_RE.search(text) for text in source_tracks.values()):
            try:
                tracks = _direct_caption_translation(cut_number, era)
                caption_repair_count += 1
            except ValueError as exc:
                errors.append(f"{ws.title}: {exc}")
        for lang, text in tracks.items():
            if HANGUL_RE.search(text):
                errors.append(f"{ws.title}: cut {cut_number:03d} {lang} caption contains Hangul")
        if HANGUL_RE.search(image_prompt):
            errors.append(f"{ws.title}: cut {cut_number:03d} image_prompt contains Hangul after cleanup")

        group = _shorts_group(ws.cell(row, 2).value)
        cut: dict[str, Any] = {
            "cut_number": cut_number,
            "narration": tracks["en"],
            "caption_tracks": tracks,
            "image_prompt": image_prompt,
            "visual_year": visual_year,
            "visual_period": f"European historical documentary scene, {visual_year}",
            "visual_location": "Europe",
            "visual_evidence": "Derived from the EP sheet cue and English dialogue.",
            "visual_subject": image_prompt.split(";", 1)[0][:180],
            "visual_scene": image_prompt,
            "scene_type": "body",
            "source_cue": cue,
            "shorts_candidate": group > 0,
            "shorts_group": group,
        }
        if group > 0:
            cut["shorts_reason"] = _compact_text(ws.cell(row, 4).value) or "workbook-marked shorts cut"
        cuts.append(cut)

    if len(cuts) != 150:
        errors.append(f"{ws.title}: expected 150 cuts, got {len(cuts)}")

    script = {
        "title": title,
        "topic": title,
        "language": "en",
        "episode_number": episode_number,
        "episode_code": ws.title,
        "episode_id": ws.title,
        "source_sheet": ws.title,
        "source_workbook": str(workbook_path),
        "source_title_ko": korean_title,
        "source_background_ko": background,
        "thumbnail_prompt": thumbnail_prompt,
        "caption_languages": ["en", "fr", "es", "de"],
        "caption_source": "script_tracks",
        "cuts": cuts,
    }
    if HANGUL_RE.search(title):
        errors.append(f"{ws.title}: generated English title still contains Hangul")
    if HANGUL_RE.search(thumbnail_prompt):
        errors.append(f"{ws.title}: thumbnail_prompt contains Hangul")
    return script, errors, caption_repair_count


def _build_integrated_script_for_sheet(
    ws: _Worksheet,
    workbook_path: Path,
    workbook_sha256: str,
    *,
    applied_corrections: set[tuple[int, int]],
    global_fix_counts: dict[str, int],
    applied_period_overrides: set[tuple[int, int]],
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    match = INTEGRATED_EP_SHEET_RE.fullmatch(ws.title)
    if not match:
        return None, [f"invalid integrated episode sheet name: {ws.title}"]
    episode_number = int(match.group(1))
    episode_code = f"EP{episode_number:03d}"
    sheet_title = _compact_text(match.group(2))

    if ws.max_row != 159 or ws.max_column != 5:
        errors.append(
            f"{ws.title}: expected used range A1:E159, got rows={ws.max_row}, cols={ws.max_column}"
        )
    header = [_compact_text(ws.cell(9, column).value) for column in range(1, 6)]
    if header != INTEGRATED_EXPECTED_HEADER:
        errors.append(f"{ws.title}: header row 9 mismatch: {header}")
    labels = tuple(_compact_text(ws.cell(row, 1).value) for row in range(2, 9))
    if labels != INTEGRATED_META_LABELS:
        errors.append(f"{ws.title}: metadata labels mismatch: {labels}")

    source_code = _required_cell(ws, 2, 2, "episode code", errors)
    korean_title = _required_cell(ws, 3, 2, "episode title", errors)
    thumbnail_copy = _required_cell(ws, 4, 2, "thumbnail copy", errors)
    thumbnail_prompt = _required_cell(ws, 5, 2, "thumbnail prompt", errors)
    source_period = _required_cell(ws, 6, 2, "period", errors)
    background_country = _required_cell(ws, 7, 2, "background country", errors)
    background_region = _required_cell(ws, 8, 2, "background region", errors)
    expected_source_code = f"유럽사 시크릿-{episode_code}"
    if source_code != expected_source_code:
        errors.append(
            f"{ws.title}: episode code {source_code!r} != {expected_source_code!r}"
        )
    if korean_title != sheet_title:
        errors.append(f"{ws.title}: sheet suffix does not match row 3 title")
    expected_banner = f"유럽사 시크릿 | {episode_code} | {korean_title}"
    if _compact_text(ws.cell(1, 1).value) != expected_banner:
        errors.append(f"{ws.title}: title banner mismatch")
    if CJK_RE.search(thumbnail_prompt):
        errors.append(f"{ws.title}: thumbnail prompt contains CJK")

    try:
        episode_period = _integrated_episode_period(episode_number, source_period)
    except ValueError as exc:
        errors.append(str(exc))
        episode_period = ""

    title = english_episode_title(episode_number)
    cuts: list[dict[str, Any]] = []
    shorts_groups: dict[int, list[tuple[int, int]]] = {}
    for cut_number in range(1, 151):
        row = cut_number + 9
        raw_cut = _compact_text(ws.cell(row, 1).value)
        try:
            parsed_cut = int(float(raw_cut))
        except (TypeError, ValueError):
            parsed_cut = 0
        if parsed_cut != cut_number:
            errors.append(
                f"{ws.title}: cut row {row} has {raw_cut!r}, expected {cut_number}"
            )

        short_tag = _compact_text(ws.cell(row, 2).value)
        korean_narration = _compact_text(ws.cell(row, 3).value)
        source_english = _compact_text(ws.cell(row, 4).value)
        source_prompt = _compact_text(ws.cell(row, 5).value)
        if not korean_narration:
            errors.append(f"{ws.title}: cut {cut_number:03d} missing Korean narration")
        if not source_english:
            errors.append(f"{ws.title}: cut {cut_number:03d} missing English narration")
        if not source_prompt:
            errors.append(f"{ws.title}: cut {cut_number:03d} missing image prompt")
        if CJK_RE.search(source_english):
            errors.append(f"{ws.title}: cut {cut_number:03d} English narration contains CJK")
        if CJK_RE.search(source_prompt):
            errors.append(f"{ws.title}: cut {cut_number:03d} source prompt contains CJK")

        try:
            narration = _apply_verified_english_fix(
                episode_number,
                cut_number,
                source_english,
                applied_corrections,
                global_fix_counts,
            )
        except ValueError as exc:
            errors.append(str(exc))
            narration = source_english
        for forbidden in _FORBIDDEN_ENGLISH_FRAGMENTS:
            if forbidden.lower() in narration.lower():
                errors.append(
                    f"{ws.title}: cut {cut_number:03d} forbidden English fragment {forbidden!r}"
                )

        visual_period = episode_period
        period_override = _CUT_VISUAL_PERIOD_OVERRIDES.get((episode_number, cut_number))
        if period_override is not None:
            expected_english, visual_period = period_override
            if source_english != expected_english:
                errors.append(
                    f"{ws.title}: cut {cut_number:03d} visual-period source mismatch"
                )
            else:
                applied_period_overrides.add((episode_number, cut_number))

        try:
            image_prompt = _set_prompt_period(
                _clean_integrated_prompt(source_prompt), visual_period
            )
        except ValueError as exc:
            errors.append(f"{ws.title}: cut {cut_number:03d}: {exc}")
            image_prompt = ""
        if CJK_RE.search(narration):
            errors.append(
                f"{ws.title}: cut {cut_number:03d} final English narration contains CJK"
            )
        if CJK_RE.search(image_prompt) or CJK_RE.search(visual_period):
            errors.append(
                f"{ws.title}: cut {cut_number:03d} final visual data contains CJK"
            )
        if re.search(r"\bset around\b", image_prompt, flags=re.IGNORECASE):
            errors.append(
                f"{ws.title}: cut {cut_number:03d} source period remains in final prompt"
            )
        if source_english and len(source_english) >= 20 and source_english in image_prompt:
            errors.append(f"{ws.title}: cut {cut_number:03d} narration leaked into prompt")

        shorts_group = 0
        try:
            parsed_tag = _integrated_shorts_tag(short_tag)
            if parsed_tag is not None:
                shorts_group, shorts_sequence = parsed_tag
                shorts_groups.setdefault(shorts_group, []).append(
                    (cut_number, shorts_sequence)
                )
        except ValueError as exc:
            errors.append(f"{ws.title}: cut {cut_number:03d}: {exc}")

        visual_subject = image_prompt.split(".", 1)[0].strip()[:220]
        cut: dict[str, Any] = {
            "cut_number": cut_number,
            "narration": narration,
            "caption_tracks": {"en": narration},
            "image_prompt": image_prompt,
            "visual_year": visual_period,
            "visual_period": f"European historical documentary scene, {visual_period}",
            "visual_location": "Europe and connected historical regions named by the source scene",
            "visual_evidence": "Physical people, objects, and setting preserved from the source scene",
            "visual_subject": visual_subject,
            "visual_scene": image_prompt,
            "scene_type": "body",
            "source_cue": thumbnail_copy,
            "source_narration_ko": korean_narration,
            "shorts_candidate": shorts_group > 0,
            "shorts_group": shorts_group,
        }
        if shorts_group > 0:
            cut["shorts_reason"] = f"workbook tag {short_tag}"
        cuts.append(cut)

    if set(shorts_groups) != {1, 2, 3, 4}:
        errors.append(f"{ws.title}: expected shorts groups 1-4, got {sorted(shorts_groups)}")
    for group in range(1, 5):
        entries = shorts_groups.get(group, [])
        sequences = [sequence for _, sequence in entries]
        cut_numbers = [number for number, _ in entries]
        if len(entries) < 10:
            errors.append(f"{ws.title}: shorts group {group} has only {len(entries)} cuts")
        if sequences != list(range(1, len(entries) + 1)):
            errors.append(f"{ws.title}: shorts group {group} sequence is not contiguous")
        if cut_numbers and cut_numbers != list(range(cut_numbers[0], cut_numbers[-1] + 1)):
            errors.append(f"{ws.title}: shorts group {group} cut block is not contiguous")

    for left in range(len(cuts)):
        for right in range(left + 1, min(len(cuts), left + 6)):
            if cuts[left]["narration"] == cuts[right]["narration"]:
                errors.append(
                    f"{ws.title}: near duplicate narration at cuts {left + 1} and {right + 1}"
                )

    script = {
        "script_version": SCRIPT_VERSION,
        "prepared_source": True,
        "visual_policy_mode": SOURCE_LOCKED_VISUAL_POLICY_MODE,
        "title": title,
        "topic": title,
        "language": "en",
        "episode_number": episode_number,
        "episode_code": episode_code,
        "episode_id": episode_code,
        "source_sheet": episode_code,
        "source_workbook": str(workbook_path),
        "source": {
            "workbook": str(workbook_path),
            "workbook_sha256": workbook_sha256,
            "worksheet": ws.title,
            "episode_code": source_code,
        },
        "source_title_ko": korean_title,
        "source_background_ko": f"{background_country} | {background_region}",
        "source_period_ko": source_period,
        "source_thumbnail_copy_ko": thumbnail_copy,
        "thumbnail_prompt": thumbnail_prompt,
        "caption_languages": ["en"],
        "caption_source": "script_tracks",
        "cuts": cuts,
    }
    return (script if not errors else None), errors


def convert_workbooks(
    workbook_paths: list[Path] | tuple[Path, ...],
    output_dir: Path,
    *,
    write: bool = False,
    limit: int | None = None,
    require_full: bool = True,
) -> dict[str, Any]:
    if write and limit:
        raise ValueError("--limit is dry-run only and cannot be combined with --write")
    paths = [Path(path) for path in workbook_paths]
    errors: list[str] = []
    sources: list[dict[str, Any]] = []
    sheets: list[tuple[int, _Worksheet, Path, str]] = []
    seen_episodes: set[int] = set()
    seen_sheet_names: set[tuple[str, str]] = set()

    for path in paths:
        if not path.is_file():
            errors.append(f"source workbook not found: {path}")
            continue
        workbook_sha256 = _sha256_file(path)
        try:
            workbook = _load_xlsx_workbook(path)
        except Exception as exc:
            errors.append(f"failed to read {path}: {type(exc).__name__}: {exc}")
            continue
        names = [
            name for name in workbook.sheetnames if INTEGRATED_EP_SHEET_RE.fullmatch(name)
        ]
        if not names:
            errors.append(f"{path}: zero integrated episode sheets")
            continue
        source_episode_numbers: list[int] = []
        for name in names:
            match = INTEGRATED_EP_SHEET_RE.fullmatch(name)
            assert match is not None
            episode_number = int(match.group(1))
            source_episode_numbers.append(episode_number)
            if episode_number in seen_episodes:
                errors.append(f"duplicate episode number: EP{episode_number:03d}")
                continue
            sheet_key = (str(path), name)
            if sheet_key in seen_sheet_names:
                errors.append(f"duplicate source sheet: {path}::{name}")
                continue
            seen_episodes.add(episode_number)
            seen_sheet_names.add(sheet_key)
            sheets.append((episode_number, workbook[name], path, workbook_sha256))
        expected_range = EXPECTED_SOURCE_RANGES.get(path.name)
        if expected_range is not None:
            expected_numbers = list(range(expected_range[0], expected_range[1] + 1))
            if sorted(source_episode_numbers) != expected_numbers:
                errors.append(
                    f"{path.name}: episode coverage mismatch, expected {expected_range[0]}-{expected_range[1]}"
                )
        sources.append(
            {
                "path": str(path),
                "sha256": workbook_sha256,
                "size": path.stat().st_size,
                "episode_count": len(names),
                "first_episode": min(source_episode_numbers),
                "last_episode": max(source_episode_numbers),
            }
        )

    sheets.sort(key=lambda item: item[0])
    if limit:
        sheets = sheets[:limit]
    applied_corrections: set[tuple[int, int]] = set()
    global_fix_counts: dict[str, int] = {}
    applied_period_overrides: set[tuple[int, int]] = set()
    scripts: list[tuple[str, dict[str, Any]]] = []
    for episode_number, worksheet, path, workbook_sha256 in sheets:
        script, sheet_errors = _build_integrated_script_for_sheet(
            worksheet,
            path,
            workbook_sha256,
            applied_corrections=applied_corrections,
            global_fix_counts=global_fix_counts,
            applied_period_overrides=applied_period_overrides,
        )
        errors.extend(sheet_errors)
        if script is not None:
            scripts.append((f"EP{episode_number:03d}", script))

    if require_full and not limit:
        expected_episodes = set(range(1, 180))
        if seen_episodes != expected_episodes:
            missing = sorted(expected_episodes - seen_episodes)
            extra = sorted(seen_episodes - expected_episodes)
            errors.append(
                f"global episode coverage mismatch: found={len(seen_episodes)}, missing={missing}, extra={extra}"
            )
        if len(scripts) != 179:
            errors.append(f"script count mismatch: expected 179, got {len(scripts)}")
        cut_count = sum(len(script.get("cuts") or []) for _, script in scripts)
        if cut_count != 26850:
            errors.append(f"cut count mismatch: expected 26850, got {cut_count}")
        missing_corrections = sorted(set(_VERIFIED_ENGLISH_OVERRIDES) - applied_corrections)
        if missing_corrections:
            errors.append(f"verified corrections not applied: {missing_corrections}")
        missing_period_overrides = sorted(
            set(_CUT_VISUAL_PERIOD_OVERRIDES) - applied_period_overrides
        )
        if missing_period_overrides:
            errors.append(f"cut period overrides not applied: {missing_period_overrides}")
        for source_text, (_replacement, expected_count) in _GLOBAL_ENGLISH_FIXES.items():
            actual_count = global_fix_counts.get(source_text, 0)
            if actual_count != expected_count:
                errors.append(
                    f"global correction count mismatch: {source_text!r}: expected {expected_count}, got {actual_count}"
                )

    if write and errors:
        raise SystemExit("conversion blocked by validation errors; run without --write for report")

    output_dir = output_dir.resolve()
    written: list[str] = []
    manifest_path = ""
    if write:
        if output_dir.exists() and any(output_dir.iterdir()):
            raise SystemExit(f"output directory must be empty: {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)
        file_entries: list[dict[str, Any]] = []
        for episode_code, script in scripts:
            payload = json.dumps(script, ensure_ascii=False, indent=2) + "\n"
            payload_bytes = payload.encode("utf-8")
            path = output_dir / f"{episode_code}.json"
            path.write_bytes(payload_bytes)
            written.append(str(path))
            file_entries.append(
                {
                    "episode_code": episode_code,
                    "file": path.name,
                    "sha256": hashlib.sha256(payload_bytes).hexdigest().upper(),
                    "cuts": len(script["cuts"]),
                }
            )
        manifest = {
            "script_version": SCRIPT_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "language": "en",
            "caption_languages": ["en"],
            "episode_count": len(scripts),
            "cut_count": sum(len(script["cuts"]) for _, script in scripts),
            "cleaned_prompt_count": sum(len(script["cuts"]) for _, script in scripts),
            "verified_cell_corrections": [
                f"EP{episode:03d}:{cut:03d}" for episode, cut in sorted(applied_corrections)
            ],
            "global_correction_counts": global_fix_counts,
            "cut_period_overrides": [
                f"EP{episode:03d}:{cut:03d}"
                for episode, cut in sorted(applied_period_overrides)
            ],
            "sources": sources,
            "files": file_entries,
        }
        manifest_file = output_dir / "manifest.json"
        manifest_file.write_bytes(
            (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        )
        manifest_path = str(manifest_file)

    return {
        "workbooks": [str(path) for path in paths],
        "output_dir": str(output_dir),
        "write": write,
        "sheet_count": len(sheets),
        "script_count": len(scripts),
        "cut_count": sum(len(script.get("cuts") or []) for _, script in scripts),
        "verified_correction_count": len(applied_corrections),
        "global_correction_count": sum(global_fix_counts.values()),
        "cut_period_override_count": len(applied_period_overrides),
        "written_count": len(written),
        "manifest": manifest_path,
        "error_count": len(errors),
        "errors": errors[:300],
    }


def convert_workbook(
    workbook_path: Path,
    output_dir: Path,
    *,
    write: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    wb = _load_xlsx_workbook(workbook_path)
    episode_sheets = [name for name in wb.sheetnames if EP_SHEET_RE.fullmatch(name)]
    if limit:
        episode_sheets = episode_sheets[:limit]

    output_dir = output_dir.resolve()
    scripts: list[tuple[str, dict[str, Any]]] = []
    errors: list[str] = []
    caption_repair_count = 0
    for name in episode_sheets:
        script, sheet_errors, sheet_repair_count = _build_script_for_sheet(
            wb[name], workbook_path
        )
        errors.extend(sheet_errors)
        caption_repair_count += sheet_repair_count
        if script:
            scripts.append((name, script))

    if write and errors:
        raise SystemExit(
            "conversion blocked by validation errors; run without --write for report"
        )

    written: list[str] = []
    if write:
        output_dir.mkdir(parents=True, exist_ok=True)
        for name, script in scripts:
            path = output_dir / f"{name}.json"
            path.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
            written.append(str(path))

    return {
        "workbook": str(workbook_path),
        "output_dir": str(output_dir),
        "write": write,
        "sheet_count": len(episode_sheets),
        "script_count": len(scripts),
        "caption_repair_count": caption_repair_count,
        "written_count": len(written),
        "written": written[:10],
        "error_count": len(errors),
        "errors": errors[:200],
    }


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        action="append",
        dest="inputs",
        help="integrated source workbook; repeat for multiple files",
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="use the retired single-workbook multilingual converter",
    )
    args = parser.parse_args()

    if args.legacy:
        legacy_inputs = args.inputs or [str(DEFAULT_WORKBOOK)]
        if len(legacy_inputs) != 1:
            parser.error("--legacy accepts exactly one --input")
        result = convert_workbook(
            Path(legacy_inputs[0]),
            Path(args.output_dir),
            write=bool(args.write),
            limit=args.limit,
        )
    else:
        result = convert_workbooks(
            [Path(value) for value in (args.inputs or DEFAULT_WORKBOOKS)],
            Path(args.output_dir),
            write=bool(args.write),
            limit=args.limit,
            require_full=not bool(args.limit),
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["error_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
