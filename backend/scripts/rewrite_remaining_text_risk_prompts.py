from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import CHANNELS_ROOT, SYSTEM_DIR


REWRITE_VERSION = "remaining-text-risk-v2"

_NEGATED_TEXT_RE = re.compile(
    r"(?i)\b(?:no|without|zero)\s+(?:readable\s+)?"
    r"(?:text|letters?|words?|writing|inscriptions?|signs?|symbols?|documents?|"
    r"scrolls?|books?|maps?|seals?|coins?|logos?|title cards?)"
    r"(?:\s+(?:or|and)\s+(?:readable\s+)?(?:text|letters?|words?|writing|"
    r"inscriptions?|signs?|symbols?|documents?|scrolls?|books?|maps?|seals?|"
    r"coins?|logos?|title cards?))*"
)

_RISK_PATTERNS = {
    "explicit": re.compile(
        r"(?i)\b(?:readable text|text|letters?|words?|writing|written|"
        r"inscriptions?|inscribed|engraved|etched|calligraphy|glyphs?|kanji|"
        r"chinese characters?|japanese characters?|korean characters?|hangul|hanja|typography|"
        r"question mark|logo|title card|headline|caption|subtitle|labels?|labeled|"
        r"numbers?|digits?|markings?|symbols?|emblems?)\b"
    ),
    "paper": re.compile(
        r"(?i)\b(?:newspaper|documents?|decrees?|edicts?|chronicles?|manuscripts?|"
        r"scrolls?|books?|journal|pages?|ledger|certificate|passport|dispatch|"
        r"message|letter)\b"
    ),
    "layout": re.compile(
        r"(?i)\b(?:maps?|blueprints?|diagrams?|charts?|calendars?|clock face|"
        r"signboards?|signage|placards?|posters?|plaques?|tablets?|steles?|"
        r"screens?|displays?|x-rays?|speech bubbles?|smartphones?|banners?|flags?)\b"
    ),
    "marked_object": re.compile(
        r"(?i)\b(?:royal seal|logo seal|title seal|wax seal|seals?|coins?|"
        r"banknotes?|stamps?|medallions?|tallies?)\b"
    ),
}

_FRAMINGS = (
    "Wide eye-level composition",
    "Ground-level three-quarter composition",
    "Restrained side-lit medium composition",
    "Layered documentary composition",
    "Natural long-lens composition",
    "Over-the-shoulder historical composition",
    "High three-quarter environmental composition",
    "Close material-detail composition",
)


def _compact(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\r", " ").replace("\n", " ")).strip()


def _normalized_status(value: Any) -> str:
    return _compact(value or "pending").lower()


def _episode_number(payload: dict[str, Any], path: Path) -> int:
    for value in (
        payload.get("episode_number"),
        payload.get("episode"),
        payload.get("ep"),
        payload.get("episode_code"),
        payload.get("episode_id"),
        path.stem,
    ):
        try:
            number = int(value)
            if number > 0:
                return number
        except (TypeError, ValueError):
            match = re.search(r"(?:episode|ep)\.?[-_ ]*0*(\d{1,4})", str(value or ""), re.I)
            if match:
                return int(match.group(1))
    return 0


def _episode_code(payload: dict[str, Any], path: Path) -> str:
    return _compact(
        payload.get("episode_code")
        or payload.get("episode_id")
        or payload.get("source_sheet")
        or path.stem
    ).casefold()


def _candidate_script_dirs(channel: int, template_id: str) -> list[Path]:
    candidates = [
        SYSTEM_DIR / "projects" / template_id / "prepared_scripts",
        CHANNELS_ROOT / f"CH{channel}" / "projects" / template_id / "prepared_scripts",
    ]
    return [path for path in candidates if path.is_dir()]


def _load_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("cuts"), list):
        raise ValueError(f"invalid prepared script: {path}")
    return payload


def _find_registered_script(
    *,
    channel: int,
    template_id: str,
    episode_number: int,
    episode_code: str,
) -> tuple[Path, dict[str, Any]]:
    wanted_code = _compact(episode_code).casefold()
    exact: list[tuple[Path, dict[str, Any]]] = []
    number_matches: list[tuple[Path, dict[str, Any]]] = []
    for script_dir in _candidate_script_dirs(channel, template_id):
        for path in sorted(script_dir.glob("*.json")):
            if "manifest" in path.name.casefold():
                continue
            try:
                payload = _load_payload(path)
            except Exception:
                continue
            code = _episode_code(payload, path)
            number = _episode_number(payload, path)
            if wanted_code and wanted_code == code:
                exact.append((path, payload))
            elif episode_number and episode_number == number:
                number_matches.append((path, payload))
    matches = exact or number_matches
    if len(matches) != 1:
        raise RuntimeError(
            f"registered script match failed: channel={channel}, template={template_id}, "
            f"episode={episode_number}, code={episode_code!r}, matches={[str(path) for path, _ in matches]}"
        )
    return matches[0]


def _risk_categories(prompt: str) -> list[str]:
    scan = _NEGATED_TEXT_RE.sub("", _compact(prompt))
    return [name for name, pattern in _RISK_PATTERNS.items() if pattern.search(scan)]


def _special_semantic_beat(narration: str, prompt: str) -> str:
    source = _compact(prompt)
    lowered = f"{_compact(narration)} {source}".casefold()
    if ("agricultur" in lowered or "farming" in lowered) and ("productiv" in lowered or "nation" in lowered):
        return "farmers harvest abundant grain beside full granaries while state officials organize irrigation labor and transport"
    if ("transmission" in lowered or "arrival" in lowered) and ("writing" in lowered or "characters" in lowered or "letters" in lowered):
        return "a Baekje scholar orally instructs Japanese court officials using plain counting pieces and demonstrative hand movements"
    if "honor" in lowered and ("restored" in lowered or "worship" in lowered or "god" in lowered):
        return "court officials restore the disgraced scholar's status as worshippers enshrine him through a solemn public ritual"
    if "keyhole" in lowered and ("tomb" in lowered or "shape" in lowered or "sky" in lowered):
        return "a high aerial view reveals the immense keyhole-shaped burial mound surrounded by moats, forest, and tiny excavation crews"
    if ("baekje" in lowered or "百済" in lowered) and ("noble" in lowered or "貴族" in lowered):
        return "a Baekje noble arrives by boat and steps ashore before an early Japanese delegation, distinguished by period dress and bearing"
    if ("world record" in lowered or "guinness" in lowered) and ("fall" in lowered or "surviv" in lowered or "height" in lowered):
        return "the recovered flight attendant stands before astonished doctors and witnesses as they acknowledge her unprecedented survival"
    if ("10,000" in lowered or "10000" in lowered) and "surviv" in lowered and "fall" in lowered:
        return "the recovered flight attendant stands before astonished rescuers after surviving the extreme fall without a parachute"
    if ("medical miracle" in lowered or "healed spine" in lowered) and ("surviv" in lowered or "human" in lowered):
        return "the recovered survivor takes supported steps before astonished doctors, showing the physical result of long rehabilitation"
    if "kentucky" in lowered and ("meat" in lowered or "flesh" in lowered) and ("rain" in lowered or "falling" in lowered):
        return "pieces of raw meat fall from a clear sky onto an 1876 Kentucky farm as the family recoils across the field"
    if "strasbourg" in lowered and ("danc" in lowered or "plague" in lowered):
        return "hundreds of exhausted townspeople dance uncontrollably in the summer street while physicians and city guards struggle to intervene"
    if "토끼" in lowered or "rabbit" in lowered:
        if "berthier" in lowered or "베르티에" in lowered:
            return "Chief of Staff Alexandre Berthier angrily confronts aides beside open rabbit cages as domestic rabbits scatter across the imperial hunting ground"
        return "domestic rabbits swarm through the hunting ground while imperial officers stumble backward and servants rush to contain them"
    if "hii river" in lowered and ("snake" in lowered or "serpent" in lowered):
        return "the swollen Hii River coils through the Izumo valley like a living serpent while riverside residents flee the rising water"
    if "different crafts" in lowered or "different trades" in lowered:
        return "specialist craftspeople demonstrate distinct trades side by side, each using period tools and raw materials"
    if "three-legged" in lowered and ("crow" in lowered or "samjogo" in lowered):
        return "ritual artists present a three-legged crow figure in fired clay relief while court observers compare its form"
    if "trade route" in lowered and "iron" in lowered:
        return "heavily loaded boats carry iron across rough water as crews strain at oars and guards protect the cargo"
    if "split straight down the middle" in lowered and "buddh" in lowered:
        return "two rival court factions confront each other around a newly arrived Buddhist statue, their hostility visible in posture and distance"
    if "chain" in lowered and "izumo" in lowered:
        return "armed conquerors drag captured defenders from an Izumo stronghold while surviving residents recoil from the violent seizure"
    if "book" in lowered and ("aristocrat" in lowered or "scholar" in lowered):
        return "stern court aristocrats and scholars debate the official account face to face in an eighth-century Nara hall"
    if "economic ledger" in lowered or ("scholar writing" in lowered and "ledger" in lowered):
        return "a dedicated scholar sorts notched tally sticks, cord-bound bundles, and pebble counters late at night"
    if "official seal" in lowered or "royal seal" in lowered:
        return "the ruler issues a decision face to face as officials react through bows, guarded posture, and shifting distance"
    if "death certificate" in lowered:
        return "a period doctor gives a hesitant diagnosis directly to the grieving family while avoiding their accusing gaze"
    if "medical book" in lowered:
        return "period physicians debate beside an exhausted patient, comparing visible symptoms through urgent gestures"
    if "newspaper" in lowered or "news clipping" in lowered or "news broadcast" in lowered:
        return "reporters and grieving members of the public react to the historical event through faces, movement, and period equipment with every surface left plain"
    if "computer screen" in lowered or "museum display" in lowered:
        return "a modern historian examines unlabeled period artifacts under neutral museum light and reacts to the evidence"
    if "radar screen" in lowered or ("control tower" in lowered and "flight path" in lowered):
        return "armed airport security patrols watch a passenger aircraft through control-tower windows as tension spreads across the dark room"
    if "x-ray" in lowered:
        return "a forensic doctor demonstrates the fatal neck injury on an anatomical model while investigators react"
    if "manifesto" in lowered:
        return "the prosecutor delivers a firm pledge directly to fellow officers, his expression showing resolve"
    if "number four" in lowered and "death" in lowered:
        return "four plain pottery lamps surround a funerary offering as one flame dies and witnesses recoil"
    if "myth scroll" in lowered or "rewriting itself" in lowered:
        return "a court storyteller changes the myth through an intense oral performance while armed listeners react to the new version"
    if "puzzle box" in lowered and ("trap" in lowered or "strategy" in lowered):
        return "strategists reveal an unexpected physical trap while nearby warriors exchange startled reactions"
    if "puzzle box" in lowered and ("flipping" in lowered or "upside down" in lowered or "plot twist" in lowered):
        return "opposing ritual figures abruptly exchange positions as startled witnesses realize the balance of power has reversed"
    if "puzzle box" in lowered:
        return "ritual specialists open a plain wooden chest to reveal an ancient iron sword and unmarked ceremonial artifacts"
    if "question mark" in lowered:
        return "period observers exchange uncertain glances around a broken sword while opposing gestures reveal unresolved doubt"
    if "split screen" in lowered and "flood" in lowered and "warrior" in lowered:
        return "iron-armed warriors clash at the edge of a flooded village as residents struggle through rising water behind them"
    if "split screen" in lowered and ("napoleon" in lowered or "rabbit" in lowered):
        return "Napoleon recoils as domestic rabbits surge around his boots and officers rush to shield him"
    if "blueprint" in lowered and "dam" in lowered:
        return "laborers build a massive earthen dam under a foreman's urgent hand signals while water pressure rises behind them"
    if "blueprint" in lowered and ("strategist" in lowered or "calculating" in lowered or "tactical" in lowered):
        return "a calculating commander arranges plain stones on bare ground and directs warriors toward an unexpected ambush position"
    if "blueprint" in lowered or "blueprints" in lowered:
        return "period leaders inspect a full-scale construction site while craftspeople demonstrate the proposed structure with timber and rope"
    if "diagram" in lowered and ("bowing" in lowered or "clapping" in lowered):
        return "ritual participants physically perform the prescribed sequence of bows and claps before a shrine"
    if "diagram" in lowered and ("falling" in lowered or "fuselage" in lowered):
        return "a torn aircraft fuselage falls through dense cloud while the survivor's body position and wind resistance remain clearly visible"
    if "calendar" in lowered or "abacus" in lowered:
        return "court astronomers compare the changing sun angle with pebble counters and observe the season from a palace courtyard"
    if "lineage chart" in lowered:
        return "an aging ruler ceremonially hands an iron sword to a younger heir while assembled relatives react"
    if "glowing tactical" in lowered and "japan" in lowered:
        return "rival armed factions confront one another across an ancient Japanese court, divided by allegiance and visible hostility"
    if "map" in lowered and ("battle" in lowered or "war" in lowered or "conquest" in lowered or "sword" in lowered):
        return "rival period forces clash across the actual river valley as commanders signal advances and defenders retreat through the terrain"
    if "map" in lowered and ("route" in lowered or "location" in lowered or "land" in lowered or "japan" in lowered or "izumo" in lowered):
        return "period travelers cross the actual landscape toward the narrated destination, carrying practical cargo while local residents react"
    if "scroll" in lowered and ("edict" in lowered or "political" in lowered):
        return "a ruler announces a harsh political command directly to a tense court while guards close ranks around dissenting officials"
    if "scroll" in lowered and ("sword" in lowered or "iron" in lowered):
        return "ritual specialists present an ancient iron sword to gathered witnesses as its physical condition provokes alarm"
    if "scroll" in lowered and "river" in lowered:
        return "a violent river floods a period settlement while residents flee and rescue one another through the current"
    if "scroll" in lowered or "manuscript" in lowered:
        return "elders orally recount the narrated event to attentive listeners while period artifacts anchor the historical setting"
    if "locked book" in lowered or ("book" in lowered and "chain" in lowered):
        return "guarded officials hide a period artifact inside a locked chest while excluded witnesses protest"
    if "book" in lowered and ("buddh" in lowered or "scripture" in lowered or "lotus" in lowered):
        return "monks recite teachings before a blooming lotus offering while royal patrons and worshippers listen"
    if "history book" in lowered and ("napoleon" in lowered or "rabbit" in lowered):
        return "Napoleon runs across the imperial hunting ground as domestic rabbits chase him and officers scatter"
    if "display" in lowered and "sword" in lowered:
        return "a ritual keeper presents the legendary iron sword on plain cloth inside a dim shrine while witnesses bow"
    if "certificate" in lowered and ("record" in lowered or "guinness" in lowered):
        return "the survivor receives a public ovation as officials and witnesses acknowledge the extraordinary feat through applause and expression"
    if "decree" in lowered and ("construction" in lowered or "shrine" in lowered):
        return "the emperor directs builders at a massive shrine construction site while laborers raise timber under urgent supervision"
    if "document of surrender" in lowered or ("surrender" in lowered and "stamp" in lowered):
        return "the defeated leader kneels and lays down a weapon before the victorious delegation as guards close in"
    if "documents" in lowered and ("scribe" in lowered or "political" in lowered):
        return "court officials argue over the narrated political decision while attendants carry plain cord-bound bundles in the background"
    if "courier" in lowered and ("letter" in lowered or "dispatch" in lowered):
        return "a mounted courier races across the border carrying a plain cord-tied satchel as guards turn toward him"
    if "microscope" in lowered and ("medical" in lowered or "pathology" in lowered):
        return "nineteenth-century physicians examine a specimen through a microscope while colleagues debate the visible findings"
    if "plaque" in lowered and "lil" in lowered:
        return "mourners place white lilies beside a plain memorial stone and bow in silence"
    if "symbol" in lowered or "emblem" in lowered or "glyph" in lowered:
        if "sun" in lowered or "crow" in lowered:
            return "a three-legged crow crosses the blazing sun above astonished ritual observers"
        if "cave" in lowered:
            return "a fierce ritual figure emerges from a dark cave while companions recoil from the sudden appearance"
        return "ritual figures physically enact the narrated conflict through opposing movement, posture, and witness reactions"
    if "stone beast" in lowered and ("king's name" in lowered or "kings name" in lowered):
        return "entrants discover a stone beast beside a plain weathered burial slab and recoil at the untouched royal tomb chamber"
    return ""


def _safe_semantic_beat(narration: str, prompt: str) -> str:
    source = _compact(prompt)
    marker = re.search(r"(?i)visualizing this decisive historical beat:\s*", source)
    if marker:
        source = source[marker.end():]
    else:
        special = _special_semantic_beat(narration, source)
        if special:
            return special
    source = re.split(r"(?<=[.!?])\s+", source, maxsplit=1)[0]

    special = _special_semantic_beat(narration, source)
    if special and not re.search(r"(?i)\b(?:royal seal|seal)\b", prompt):
        return special

    replacements = (
        (r"(?i)\b(?:the )?(?:record|chronicle|manuscript)\s+(?:states?|says?|reports?|shows?)\s+that\b", ""),
        (r"(?i)\bin the end,?\s+the shocking record continues that\b", ""),
        (r"(?i)\bthe record is absent of\b", "historians do not know"),
        (r"(?i)\bwere not recorded\b", "remain unknown"),
        (r"(?i)\bwas not recorded\b", "remains unknown"),
        (r"(?i)\brecorded facts?\b", "confirmed events"),
        (r"(?i)\brecorded as\b", "remembered as"),
        (r"(?i)\brecorded\b", "confirmed"),
        (r"(?i)\brecords?\b", "surviving evidence"),
        (r"(?i)\btranslated scriptures?\b", "directed court monks in formal recitation"),
        (r"(?i)\b(?:written|inscribed|engraved|etched)\b", "preserved"),
        (r"(?i)\b(?:letters?|words?|writing|inscriptions?|calligraphy|glyphs?|kanji|text)\b", "spoken details"),
        (r"(?i)\b(?:newspaper|documents?|decrees?|edicts?|chronicles?|manuscripts?|scrolls?|books?|journal|pages?|ledger|certificate|passport|dispatch|message|letter)\b", "physical evidence"),
        (r"(?i)\b(?:maps?|blueprints?|diagrams?|charts?)\b", "real terrain"),
        (r"(?i)\b(?:calendars?|clock face)\b", "changing daylight"),
        (r"(?i)\b(?:signboards?|signage|placards?|posters?|plaques?|tablets?|steles?)\b", "a plain period artifact"),
        (r"(?i)\b(?:royal seal|logo seal|title seal|wax seal|seals?|coins?|banknotes?|stamps?|medallions?|tallies?)\b", "a guarded ceremonial focal point"),
        (r"(?i)\b(?:question mark|logo|title card|headline|caption|subtitle|labels?|labeled|numbers?|digits?|markings?|symbols?|emblems?)\b", "uncertain reactions"),
        (r"(?i)\b(?:screens?|displays?|x-rays?)\b", "direct physical observation"),
    )
    for pattern, replacement in replacements:
        source = re.sub(pattern, replacement, source)
    source = re.sub(r"[\"'“”‘’『』「」]", "", source)
    source = re.sub(r"\b(?:on|with|beside|around)\s+(?:a|an|the)\s+physical evidence\b", "", source, flags=re.I)
    source = re.sub(r"\bphysical evidence paper\b", "physical evidence", source, flags=re.I)
    source = re.sub(r"(?i)\bthere is also a surviving evidence that\b", "", source)
    source = re.sub(r"(?i)\bthe surviving evidence(?: also)? says that\b", "", source)
    source = re.sub(r"(?i)\bthe surviving evidence that\b", "the fact that", source)
    source = re.sub(r"(?i)\bin the surviving evidence\b", "in historical reality", source)
    source = re.sub(r"(?i)\bsurviving evidence\b", "historical reality", source)
    source = re.sub(r"\bthe real terrain of\b", "the terrain of", source, flags=re.I)
    source = re.sub(r"\s+([,.])", r"\1", source)
    source = _compact(source).strip(" ,;:-")
    if any(
        token in source.casefold()
        for token in (
            "physical evidence",
            "spoken details",
            "real terrain",
            "direct physical observation",
            "guarded ceremonial focal point",
        )
    ):
        return ""
    if _risk_categories(source):
        return ""
    return source if len(source) >= 18 else ""


def _scene_action(
    narration: str,
    prompt: str,
    *,
    channel: int = 0,
    episode_number: int = 0,
) -> str:
    source = f"{_compact(narration)} {_compact(prompt)}".casefold()

    if channel == 4 and episode_number in {9, 13}:
        return (
            "Napoleon and his officers are physically overwhelmed by domestic rabbits surging across "
            "the imperial hunting ground, with the narrated reaction visible in their faces and movement"
        )
    if channel == 4 and episode_number == 10:
        if re.search(r"doctor|physician|medical|diagnos|patient|hospital", source):
            return (
                "doctors examine the injured survivor and demonstrate the narrated condition through "
                "body position, rehabilitation movement, expression, and physical symptoms"
            )
        return (
            "the aircraft disaster and survival are shown through the damaged fuselage, violent weather, "
            "altitude, the survivor's body position, and rescuers' immediate reaction"
        )
    if channel == 4 and episode_number == 11:
        if re.search(r"doctor|physician|medical|diagnos|patient|hospital|autopsy", source):
            return (
                "the period doctor examines the victim while investigators and witnesses react to the "
                "narrated physical finding"
            )
        return (
            "the accused, investigators, and witnesses confront the narrated evidence inside the period "
            "location through examination, gesture, fear, and visible physical clues"
        )
    if channel == 4 and episode_number == 12:
        if "kentucky" in source and ("meat" in source or "flesh" in source) and ("rain" in source or "fall" in source):
            return (
                "pieces of raw meat fall from a clear sky onto an 1876 Kentucky farm while the family "
                "recoils and searches the empty sky"
            )
        if re.search(r"doctor|physician|medical|diagnos|patient|hospital", source):
            return (
                "period physicians confront exhausted dancers and city officials, with the mistaken "
                "diagnosis and worsening symptoms visible through gesture and physical condition"
            )
        return (
            "the Strasbourg crowd physically enacts the narrated dancing crisis while exhausted residents, "
            "physicians, and city authorities react in the street"
        )

    if re.search(r"archaeolog|excavat|tomb|burial|grave|artifact|유물|무덤|묘|발굴|墓|古墳", source):
        return (
            "excavators and period specialists reveal one weathered artifact within its soil layer, "
            "shown from the broken edge while nearby observers react to the discovery"
        )
    if re.search(r"battle|army|soldier|warrior|siege|combat|attack|defend|전투|군대|병사|공격|전쟁|戦|兵|武", source):
        return (
            "period warriors move through real terrain under immediate pressure as commanders use "
            "hand signals and the opposing force reacts in depth"
        )
    if re.search(r"aircraft|airliner|flight|crash|falling|비행기|추락|항공", source):
        return (
            "the aircraft event unfolds through a clear physical action, weather, altitude, debris, "
            "and the central survivor's visible response"
        )
    if re.search(r"trial|courtroom|judge|jury|investigat|murder|ghost|재판|법정|수사|살인|유령", source):
        return (
            "the central witnesses, investigators, and accused person confront one another through "
            "specific gestures in the historically accurate location"
        )
    if re.search(r"temple|buddh|monk|ritual|shrine|prayer|god|goddess|사찰|불교|승려|제사|신앙|神|仏|寺|祭", source):
        return (
            "period worshippers and ritual leaders perform the narrated action within grounded sacred "
            "architecture, using body posture, offerings, smoke, and witness reactions"
        )
    if re.search(r"doctor|physician|medical|diagnos|patient|hospital|의사|진단|환자|병원", source):
        return (
            "the period doctor confronts the affected person and nearby witnesses, with the diagnosis "
            "communicated through examination, gesture, expression, and physical symptoms"
        )
    if re.search(r"king|queen|emperor|royal|court|noble|throne|왕|황제|왕비|귀족|조정|天皇|王|宮廷", source):
        return (
            "the ruler and period officials negotiate the turning point face to face, with hierarchy "
            "shown by posture, distance, guards, and the surrounding architecture"
        )
    if re.search(r"build|construct|craft|artisan|engineer|technology|workshop|건설|장인|기술|공사|職人|技術", source):
        return (
            "period craftspeople carry out the narrated work with timber, earth, stone, tools, and "
            "coordinated hand actions visible across the frame"
        )
    if re.search(r"travel|migrat|envoy|trade|ship|road|journey|이주|사신|교역|항해|渡来|移住|使節", source):
        return (
            "period travelers move through the actual landscape with practical cargo and escorts, "
            "their route and purpose shown only through direction, terrain, and interaction"
        )
    if re.search(r"death|funeral|corpse|dead|죽|장례|시신|사망|死|葬", source):
        return (
            "the narrated loss is shown through the central figure, mourners, guarded distance, and "
            "the physical setting at the decisive moment"
        )
    if re.search(r"dance|crowd|plague|disease|panic|춤|군중|역병|질병", source):
        return (
            "the crowd physically enacts the narrated crisis in the street while exhausted witnesses, "
            "period authorities, and the surrounding town react"
        )
    if re.search(r"rabbit|animal|emu|meat rain|토끼|동물|에뮤|고기 비", source):
        return (
            "the animals and period people perform the narrated action in one coherent location, with "
            "scale, movement, weather, and reactions carrying the comedy or danger"
        )
    if re.search(r"question mark|uncertain|mystery|why|whether|의문|논쟁|왜|미스터리|どう|なぜ", source):
        return (
            "period-appropriate observers exchange uncertain glances and opposing gestures around the "
            "central physical situation described by the narration"
        )
    return (
        "period-appropriate people enact the narration's central turning point through clear movement, "
        "facial response, spatial tension, and contact with ordinary physical surroundings"
    )


def _rewrite_prompt(
    *,
    cut: dict[str, Any],
    channel: int,
    episode_number: int,
    translated_narration: str = "",
) -> str:
    narration = _compact(cut.get("narration"))
    original = _compact(cut.get("image_prompt"))
    cut_number = int(cut.get("cut_number") or 0)
    framing = _FRAMINGS[(cut_number + episode_number + channel) % len(_FRAMINGS)]
    narration_context = _compact(translated_narration) or narration
    action = _scene_action(
        narration_context,
        original,
        channel=channel,
        episode_number=episode_number,
    )
    if channel == 1:
        beat = _safe_semantic_beat(narration, original)
    elif translated_narration:
        beat = _safe_semantic_beat(translated_narration, translated_narration)
        if not beat:
            beat = _special_semantic_beat(translated_narration, original)
    else:
        beat = _safe_semantic_beat(narration, original)
    beat_clause = f" Specific narrated event: {beat.rstrip('.')}." if beat else ""
    if channel == 1:
        style = (
            "Grounded Korean historical realism, period-accurate clothing and architecture, tactile "
            "earth, timber, stone, and metal, natural directional light, restrained color, 35mm lens"
        )
    elif channel == 3:
        style = (
            "Grounded ancient Japanese historical and mythic realism, period-appropriate clothing, "
            "landscape, architecture, and ritual materials, natural cinematic light, 35mm lens"
        )
    else:
        style = (
            "Grounded historical documentary realism appropriate to the narrated year and location, "
            "natural materials, believable anatomy, cinematic directional light, 35mm lens"
        )
    prompt = (
        f"{framing}: {action}.{beat_clause} Plain undecorated surfaces and ordinary physical props "
        f"throughout; meaning is carried by action, expression, distance, and material evidence. "
        f"{style}, cinematic 16:9 composition."
    )
    prompt = _compact(prompt).replace(". .", ".")
    remaining = _risk_categories(prompt)
    if remaining:
        raise RuntimeError(
            f"rewritten prompt still contains risk terms: channel={channel}, episode={episode_number}, "
            f"cut={cut_number}, categories={remaining}, prompt={prompt!r}"
        )
    return prompt


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _update_manifest(path: Path, modified_files: set[Path], report_meta: dict[str, Any]) -> bool:
    if not path.exists():
        return False
    payload = json.loads(path.read_text(encoding="utf-8"))
    changed = False
    file_rows = payload.get("files")
    if isinstance(file_rows, list):
        by_name = {item.name: item for item in modified_files}
        for row in file_rows:
            if not isinstance(row, dict):
                continue
            row_path = Path(str(row.get("path") or row.get("filename") or ""))
            target = by_name.get(row_path.name)
            if target is None:
                continue
            row["bytes"] = target.stat().st_size
            row["sha256"] = _sha256(target)
            changed = True
    payload["text_risk_prompt_rewrite"] = report_meta
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return changed


def _collect_remaining_scripts() -> list[dict[str, Any]]:
    queue_path = SYSTEM_DIR / "oneclick_queue.json"
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    presets = queue.get("channel_presets") if isinstance(queue.get("channel_presets"), dict) else {}
    rows: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for item in queue.get("items") or []:
        if not isinstance(item, dict) or _normalized_status(item.get("status")) == "completed":
            continue
        channel = int(item.get("channel") or 1)
        template_id = _compact(item.get("template_project_id") or presets.get(str(channel)))
        if not template_id:
            raise RuntimeError(f"queue item has no template: {item.get('id')}")
        episode_number = int(item.get("episode_number") or 0)
        episode_code = _compact(item.get("episode_code") or item.get("episode_id"))
        path, payload = _find_registered_script(
            channel=channel,
            template_id=template_id,
            episode_number=episode_number,
            episode_code=episode_code,
        )
        resolved = path.resolve()
        if resolved in seen:
            raise RuntimeError(f"duplicate remaining script match: {path}")
        seen.add(resolved)
        rows.append({
            "channel": channel,
            "episode_number": episode_number,
            "episode_code": episode_code,
            "queue_status": _normalized_status(item.get("status")),
            "task_id": _compact(item.get("task_id")),
            "project_id": _compact(item.get("project_id")),
            "path": path,
            "payload": payload,
        })
    return rows


def _translation_key(*, channel: int, episode_number: int, cut_number: int) -> str:
    return f"CH{channel}-EP{episode_number:03d}-CUT{cut_number:03d}"


def _load_translations(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    source = payload.get("translations") if isinstance(payload, dict) else None
    if not isinstance(source, dict):
        raise ValueError(f"invalid translation cache: {path}")
    return {str(key): _compact(value) for key, value in source.items() if _compact(value)}


def run(*, write: bool, translations_path: Path | None = None) -> dict[str, Any]:
    scripts = _collect_remaining_scripts()
    translations = _load_translations(translations_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = SYSTEM_DIR / "backups" / f"text_risk_prompt_rewrite_{timestamp}"
    changed_by_channel: Counter[int] = Counter()
    category_counts: Counter[str] = Counter()
    episode_reports: list[dict[str, Any]] = []
    changed_files: set[Path] = set()
    translated_cut_count = 0
    missing_translation_keys: list[str] = []

    if write:
        backup_root.mkdir(parents=True, exist_ok=False)
        shutil.copy2(SYSTEM_DIR / "oneclick_queue.json", backup_root / "oneclick_queue.json")

    for row in scripts:
        path: Path = row["path"]
        payload: dict[str, Any] = row["payload"]
        changed_cuts: list[int] = []
        before_sha = _sha256(path)
        if write:
            backup_path = backup_root / f"CH{row['channel']}" / path.name
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup_path)

        for cut in payload.get("cuts") or []:
            if not isinstance(cut, dict):
                continue
            categories = _risk_categories(_compact(cut.get("image_prompt")))
            if not categories:
                continue
            cut_number = int(cut.get("cut_number") or 0)
            translation_key = _translation_key(
                channel=int(row["channel"]),
                episode_number=int(row["episode_number"]),
                cut_number=cut_number,
            )
            translated_narration = translations.get(translation_key, "")
            if translations_path is not None and not translated_narration:
                missing_translation_keys.append(translation_key)
            if translated_narration:
                translated_cut_count += 1
            new_prompt = _rewrite_prompt(
                cut=cut,
                channel=int(row["channel"]),
                episode_number=int(row["episode_number"]),
                translated_narration=translated_narration,
            )
            if new_prompt == _compact(cut.get("image_prompt")):
                raise RuntimeError(f"prompt did not change: {path}, cut={cut.get('cut_number')}")
            category_counts.update(categories)
            changed_cuts.append(int(cut.get("cut_number") or 0))
            cut["image_prompt"] = new_prompt
            cut["visual_subject"] = _scene_action(
                translated_narration or _compact(cut.get("narration")),
                new_prompt,
                channel=int(row["channel"]),
                episode_number=int(row["episode_number"]),
            )
            cut["visual_scene"] = new_prompt
            cut["image_prompt_rewrite"] = {
                "version": REWRITE_VERSION,
                "reason": "removed text-generating visual instruction",
            }

        for cut in payload.get("cuts") or []:
            if isinstance(cut, dict) and _risk_categories(_compact(cut.get("image_prompt"))):
                raise RuntimeError(f"risk prompt remains after rewrite: {path}, cut={cut.get('cut_number')}")

        if changed_cuts:
            changed_by_channel[int(row["channel"])] += len(changed_cuts)
            changed_files.add(path)
            if write:
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        episode_reports.append({
            "channel": row["channel"],
            "episode_number": row["episode_number"],
            "episode_code": row["episode_code"],
            "queue_status": row["queue_status"],
            "task_id": row["task_id"],
            "project_id": row["project_id"],
            "path": str(path),
            "cut_count": len(payload.get("cuts") or []),
            "changed_cut_count": len(changed_cuts),
            "changed_cuts": changed_cuts,
            "before_sha256": before_sha,
            "after_sha256": _sha256(path) if write and changed_cuts else before_sha,
        })

    if translations_path is not None and missing_translation_keys:
        raise RuntimeError(
            f"translation cache is missing {len(missing_translation_keys)} targeted cuts: "
            f"{missing_translation_keys[:10]}"
        )

    report_meta = {
        "version": REWRITE_VERSION,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "remaining_episode_count": len(scripts),
        "changed_episode_count": sum(1 for item in episode_reports if item["changed_cut_count"]),
        "changed_cut_count": sum(item["changed_cut_count"] for item in episode_reports),
        "translated_cut_count": translated_cut_count,
    }
    updated_manifests: list[str] = []
    if write:
        manifests = {
            path.parent / "백제사_manifest.json"
            for path in changed_files
            if path.name.startswith("백제사-")
        }
        manifests.update(
            path.parent / "manifest_ep01-13.json"
            for path in changed_files
            if path.name.startswith("CH4-WH-")
        )
        for manifest in sorted(manifests):
            if manifest.exists():
                backup_manifest = backup_root / "manifests" / manifest.name
                backup_manifest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(manifest, backup_manifest)
                _update_manifest(manifest, changed_files, report_meta)
                updated_manifests.append(str(manifest))

    report = {
        **report_meta,
        "write": write,
        "backup_root": str(backup_root) if write else None,
        "total_cut_count": sum(item["cut_count"] for item in episode_reports),
        "changed_by_channel": {str(key): value for key, value in sorted(changed_by_channel.items())},
        "category_counts": dict(category_counts),
        "updated_manifests": updated_manifests,
        "episodes": episode_reports,
    }
    if write:
        (backup_root / "rewrite_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="backup and update remaining registered scripts")
    parser.add_argument("--translations", type=Path, help="local narration translation cache JSON")
    args = parser.parse_args()
    report = run(write=bool(args.write), translations_path=args.translations)
    print(json.dumps({
        key: report[key]
        for key in (
            "write",
            "remaining_episode_count",
            "total_cut_count",
            "changed_episode_count",
            "changed_cut_count",
            "translated_cut_count",
            "changed_by_channel",
            "category_counts",
            "backup_root",
            "updated_manifests",
        )
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
