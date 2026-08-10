"""Convert the reviewed CH4 Time Explorers workbook into prepared scripts.

The source workbook remains read-only. This converter preserves its spoken
narration, speaker, source-authored audio tags, thumbnail assets, and image
prompts while adding the fields required by the prepared-script loader.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree as ET


BACKEND_DIR = Path(__file__).resolve().parents[1]


def _configured_data_dir() -> Path:
    configured = str(os.getenv("DATA_DIR") or "").strip()
    if configured:
        return Path(configured)
    env_path = BACKEND_DIR / ".env"
    if env_path.is_file():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            key, separator, value = raw_line.partition("=")
            if separator and key.strip() == "DATA_DIR":
                configured = value.strip().strip('"').strip("'")
                if configured:
                    return Path(configured)
    return BACKEND_DIR.parent / "data" / "outputs"


CHANNEL = 4
TEMPLATE_PROJECT_ID = "83cca89d"
SERIES_NAME = "기괴와 변칙의 세계사 시즌1"
SCRIPT_VERSION = "prepared-ch4-time-explorers-s1-v2"
SOURCE_SCHEMA = "ch4-time-explorers-season1-xlsx-v1"
DEFAULT_WORKBOOK = Path(
    r"Z:\HDD2\longtube\CH4 시간탐구회\대본\기괴와변칙의세계사_시즌1_1~4편.xlsx"
)
DEFAULT_OUTPUT_DIR = (
    _configured_data_dir() / "channels" / f"CH{CHANNEL}" / "projects" / TEMPLATE_PROJECT_ID / "prepared_scripts"
)

_SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_SHEET_NAME_RE = re.compile(r"^Ep(?P<episode>\d{2})_(?P<label>.+)$")
_NUMERIC_SHEET_NAME_RE = re.compile(r"^(?P<episode>\d{1,2})$")
_TITLE_RE = re.compile(r"^Ep\.(?P<episode>\d{2})\s+(?P<topic>.+?)\s+\([^()]+\)\s*$")

_METADATA_LABELS = {
    1: "항목",
    2: "에피소드 제목",
    3: ("시대 (연도)", "시대"),
    4: ("배경 (장소/국가/문화권)", "배경"),
    5: ("등장인물 (최대 4인)", "등장인물 (총 4명)", "등장인물"),
    6: ("단일 썸네일 문구", "단일 썸네일 문구 (13자)", "썸네일 문구"),
    7: ("KREA AI 썸네일 프롬프트", "썸네일 프롬프트"),
}
_OPTIONAL_VARIETY_CAPTION_HEADER = "한국식 예능 자막 (주요 장면용)"
_SOURCE_VARIETY_CAPTION_HEADERS = (
    "한국식 예능 자막 (핵심 포인트)",
    _OPTIONAL_VARIETY_CAPTION_HEADER,
    "한국식 예능 자막 (선택적 하이라이트)",
    "한국식 예능 자막 (전 컷 수록)",
    "한국식 예능 자막",
    "한국식 예능 자막 (~40% 선택 수록)",
    "예능 자막 (10자 이내/이모티콘 없음)",
)
_SPEAKER_HEADERS = ("인물", "인물 (태그명)")
_PLAIN_NARRATION_HEADERS = ("대사 (ElevenLabs V3 순수 텍스트)",)
_TAGGED_NARRATION_HEADERS = ("대사 (ElevenLabs V3 감성 태그 포함)",)
_EMOTION_HEADERS = (
    "감성상태 (V3 연출)",
    "감성상태 (ElevenLabs V3 Audio Tag)",
)
_IMAGE_PROMPT_HEADERS = ("이미지 프롬프트 (KREA Local AI)",)
_AUDIO_TAG_RE = re.compile(r"\[([a-z][a-z0-9_ -]{0,31})\]", re.IGNORECASE)
_LEADING_AUDIO_TAGS_RE = re.compile(
    r"^\s*(?P<tags>(?:\[[a-z][a-z0-9_ -]{0,31}\]\s*)+)(?P<narration>.*)$",
    re.IGNORECASE | re.DOTALL,
)
_SPEAKER_ROLE_RE = re.compile(r"^\s*(?P<role>남성[12]|여성[12])(?:\s*[:：\-]?\s+)(?P<speaker>.+?)\s*$")
_VOICE_ROLE_BY_SOURCE_LABEL = {
    "남성1": "male_1",
    "남성2": "male_2",
    "여성1": "female_1",
    "여성2": "female_2",
}
_EMOJI_RE = re.compile(
    r"[\U0001F000-\U0001FAFF\U0001FC00-\U0001FFFD\U0001F1E6-\U0001F1FF"
    r"\u2300-\u23FF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D\u20E3]+"
)
_KOREAN_EMOTION_TAG_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("angry", ("분노", "격앙", "사나운", "증오", "폭발", "폭주", "독설", "폭언", "매서운")),
    ("shouts", ("고함", "내지르는", "지르는", "비명")),
    ("whispers", ("속삭", "나지막")),
    ("crying", ("울", "애원")),
    ("nervously", ("떨", "불안", "긴장", "기어들어")),
    ("booming", ("위압", "억압", "선언", "엄포")),
    ("sorrowful", ("슬픔", "비통", "서글")),
    ("slowly", ("느리", "천천히")),
)


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _column_index(reference: str) -> int:
    letters = "".join(character for character in reference if character.isalpha()).upper()
    if not letters:
        raise ValueError(f"invalid worksheet cell reference: {reference!r}")
    value = 0
    for character in letters:
        value = value * 26 + (ord(character) - ord("A") + 1)
    return value


def _cell_text(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.get("t") or ""
    if cell_type == "inlineStr":
        inline = cell.find(f"{{{_SPREADSHEET_NS}}}is")
        return "".join(node.text or "" for node in inline.iter(f"{{{_SPREADSHEET_NS}}}t")) if inline is not None else ""
    value_node = cell.find(f"{{{_SPREADSHEET_NS}}}v")
    if value_node is None or value_node.text is None:
        return ""
    value = value_node.text
    if cell_type == "s":
        try:
            return shared_strings[int(value)]
        except (IndexError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid shared string reference: {value!r}") from exc
    return value


def _read_shared_strings(book: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(book.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    values: list[str] = []
    for item in root.findall(f"{{{_SPREADSHEET_NS}}}si"):
        values.append("".join(node.text or "" for node in item.iter(f"{{{_SPREADSHEET_NS}}}t")))
    return values


def _read_sheet_rows(
    book: zipfile.ZipFile,
    sheet_path: str,
    shared_strings: list[str],
) -> dict[int, dict[int, str]]:
    root = ET.fromstring(book.read(sheet_path))
    rows: dict[int, dict[int, str]] = {}
    for row in root.findall(f".//{{{_SPREADSHEET_NS}}}row"):
        row_ref = row.get("r")
        if not row_ref:
            continue
        try:
            row_number = int(row_ref)
        except ValueError as exc:
            raise ValueError(f"invalid worksheet row reference: {row_ref!r}") from exc
        cells: dict[int, str] = {}
        for cell in row.findall(f"{{{_SPREADSHEET_NS}}}c"):
            reference = cell.get("r") or ""
            cells[_column_index(reference)] = _cell_text(cell, shared_strings)
        if cells:
            rows[row_number] = cells
    return rows


def _load_xlsx_workbook(workbook_path: Path) -> list[tuple[str, dict[int, dict[int, str]]]]:
    if not workbook_path.is_file():
        raise FileNotFoundError(workbook_path)
    with zipfile.ZipFile(workbook_path) as book:
        shared_strings = _read_shared_strings(book)
        workbook = ET.fromstring(book.read("xl/workbook.xml"))
        relationships = ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))
        targets = {
            rel.get("Id"): rel.get("Target")
            for rel in relationships.findall(f"{{{_PACKAGE_REL_NS}}}Relationship")
        }
        result: list[tuple[str, dict[int, dict[int, str]]]] = []
        for sheet in workbook.findall(f".//{{{_SPREADSHEET_NS}}}sheet"):
            name = str(sheet.get("name") or "").strip()
            relationship_id = sheet.get(f"{{{_OFFICE_REL_NS}}}id")
            target = targets.get(relationship_id)
            if not name or not target:
                raise ValueError(f"worksheet relationship is incomplete: {name!r}")
            sheet_path = str(PurePosixPath("xl") / PurePosixPath(target)).replace("xl/xl/", "xl/")
            result.append((name, _read_sheet_rows(book, sheet_path, shared_strings)))
    return result


def _text(value: Any) -> str:
    return str(value or "").strip()


def _row_value(rows: dict[int, dict[int, str]], row_number: int, column: int) -> str:
    return _text(rows.get(row_number, {}).get(column))


def _topic_from_title(title: str, episode_number: int) -> str:
    match = _TITLE_RE.fullmatch(title)
    if match is None:
        raise ValueError(f"episode {episode_number}: title format is invalid: {title!r}")
    title_episode = int(match.group("episode"))
    if title_episode != episode_number:
        raise ValueError(
            f"episode {episode_number}: title episode {title_episode} does not match worksheet"
        )
    return _text(match.group("topic"))


def _shorts_candidate(value: str) -> bool:
    return _text(value) not in {"", "-", "—"}


def _tts_tags(emotion: str) -> list[str]:
    """Preserve explicit V3 tags or deterministically map Korean direction notes."""
    tags: list[str] = []
    for raw_tag in _AUDIO_TAG_RE.findall(emotion):
        tag = raw_tag.strip().lower()
        if tag and tag not in tags:
            tags.append(tag)
    if tags:
        return tags
    for tag, keywords in _KOREAN_EMOTION_TAG_RULES:
        if any(keyword in emotion for keyword in keywords) and tag not in tags:
            tags.append(tag)
    return tags


def _split_tagged_narration(value: str) -> tuple[str, str, list[str]]:
    """Separate source-authored leading ElevenLabs tags from spoken narration."""
    raw = _text(value)
    match = _LEADING_AUDIO_TAGS_RE.fullmatch(raw)
    if match is None:
        return raw, "", []
    emotion = _text(match.group("tags"))
    narration = _text(match.group("narration"))
    return narration, emotion, _tts_tags(emotion)


def _split_speaker_role(value: str) -> tuple[str, str]:
    """Remove source role labels from display names while retaining TTS routing."""
    raw = _text(value)
    match = _SPEAKER_ROLE_RE.fullmatch(raw)
    if match is None:
        return raw, ""
    return _text(match.group("speaker")), _VOICE_ROLE_BY_SOURCE_LABEL[match.group("role")]


def _clean_variety_caption(value: str) -> str:
    """Keep source wording, removing emoji only from Korean-variety overlay text."""
    return re.sub(r"\s{2,}", " ", _EMOJI_RE.sub("", _text(value))).strip()


def _resolve_sheet_layout(
    sheet_name: str,
    rows: dict[int, dict[int, str]],
) -> tuple[tuple[str, ...], str, int | None]:
    """Resolve one of the two reviewed CH4 worksheet column contracts."""
    headers = tuple(_row_value(rows, 9, column) for column in range(1, 7))
    fixed_errors: list[tuple[int, str, tuple[str, ...]]] = []
    for column, accepted in (
        (1, ("컷번호", "실제 배열순번")),
        (2, ("숏츠번호",)),
        (3, _SPEAKER_HEADERS),
        (6, _IMAGE_PROMPT_HEADERS),
    ):
        value = headers[column - 1]
        if value not in accepted:
            fixed_errors.append((column, value, accepted))
    if fixed_errors:
        raise ValueError(f"{sheet_name}: row 9 header mismatch: {fixed_errors!r}")

    exact_caption_columns = [
        column
        for column, value in rows.get(9, {}).items()
        if _text(value) == _OPTIONAL_VARIETY_CAPTION_HEADER
    ]
    if len(exact_caption_columns) > 1:
        raise ValueError(
            f"{sheet_name}: duplicate {_OPTIONAL_VARIETY_CAPTION_HEADER!r} columns: "
            f"{exact_caption_columns!r}"
        )
    narration_header = headers[3]
    column_e_header = headers[4]
    if narration_header in _PLAIN_NARRATION_HEADERS and column_e_header in _EMOTION_HEADERS:
        layout = "separate-emotion"
        caption_column = exact_caption_columns[0] if exact_caption_columns else None
        return headers, layout, caption_column

    if narration_header in _TAGGED_NARRATION_HEADERS and column_e_header in _SOURCE_VARIETY_CAPTION_HEADERS:
        # EP.5–7 use different, explicitly authored Korean variety-caption
        # column labels.  Every declared source label maps to highlight_caption.
        return headers, "inline-emotion-tags", 5

    raise ValueError(
        f"{sheet_name}: unsupported narration/caption headers at D9:E9: "
        f"{(narration_header, column_e_header)!r}"
    )


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _episode_code(episode_number: int) -> str:
    return f"CH4-WH-S01-EP{episode_number:02d}"


def _build_episode_script(
    *,
    workbook_path: Path,
    workbook_sha256: str,
    sheet_name: str,
    rows: dict[int, dict[int, str]],
    episode_number: int,
) -> dict[str, Any]:
    for row_number, expected_label in _METADATA_LABELS.items():
        actual_label = _row_value(rows, row_number, 1)
        expected_labels = (
            expected_label if isinstance(expected_label, tuple) else (expected_label,)
        )
        if actual_label not in expected_labels:
            raise ValueError(
                f"{sheet_name}: metadata label A{row_number}={actual_label!r}, expected one of {expected_labels!r}"
            )
    headers, sheet_layout, variety_caption_column = _resolve_sheet_layout(
        sheet_name,
        rows,
    )

    title = _row_value(rows, 2, 2)
    period = _row_value(rows, 3, 2)
    place = _row_value(rows, 4, 2)
    characters = _row_value(rows, 5, 2)
    thumbnail_text = _row_value(rows, 6, 2)
    thumbnail_prompt = _row_value(rows, 7, 2)
    required_metadata = {
        "title": title,
        "period": period,
        "place": place,
        "characters": characters,
        "thumbnail_text": thumbnail_text,
        "thumbnail_prompt": thumbnail_prompt,
    }
    missing_metadata = [key for key, value in required_metadata.items() if not value]
    if missing_metadata:
        raise ValueError(f"{sheet_name}: missing metadata values: {missing_metadata}")

    topic = _topic_from_title(title, episode_number)
    cuts: list[dict[str, Any]] = []
    internal_cut_number = 1
    for row_number in sorted(row for row in rows if row >= 10):
        row = rows[row_number]
        raw_cut_number = _text(row.get(1))
        if not raw_cut_number:
            has_numberless_caption = (
                variety_caption_column is not None
                and bool(_text(row.get(variety_caption_column)))
            )
            if any(_text(row.get(column)) for column in range(2, 7)) or has_numberless_caption:
                raise ValueError(f"{sheet_name}: row {row_number} has cut data without cut number")
            continue
        try:
            cut_number = int(raw_cut_number)
        except ValueError as exc:
            raise ValueError(f"{sheet_name}: invalid cut number at row {row_number}: {raw_cut_number!r}") from exc
        shorts_tag = _text(row.get(2))
        speaker, voice_role = _split_speaker_role(row.get(3))
        raw_narration = _text(row.get(4))
        if sheet_layout == "inline-emotion-tags":
            narration, emotion, tts_tags = _split_tagged_narration(raw_narration)
        else:
            narration = raw_narration
            emotion = _text(row.get(5))
            tts_tags = _tts_tags(emotion)
        image_prompt = _text(row.get(6))
        highlight_caption = (
            _clean_variety_caption(row.get(variety_caption_column))
            if variety_caption_column is not None
            else ""
        )
        required_values = {
            "speaker": speaker,
            "narration": narration,
            "image_prompt": image_prompt,
        }
        if sheet_layout == "separate-emotion":
            required_values["emotion"] = emotion
        missing = [
            name
            for name, value in required_values.items()
            if not value
        ]
        if missing:
            raise ValueError(f"{sheet_name}: cut {cut_number} missing {missing}")
        cut_payload = {
            "cut_number": internal_cut_number,
            "source_cut_number": cut_number,
            "shorts_candidate": _shorts_candidate(shorts_tag),
            "shorts_source_tag": shorts_tag,
            "speaker": speaker,
            "emotion": emotion,
            "tts_tags": tts_tags,
            "narration": narration,
            "image_prompt": image_prompt,
            "visual_year": period,
            "visual_period": period,
            "visual_location": place,
            "visual_evidence": (
                f"Source workbook={workbook_path.name}; worksheet={sheet_name}; "
                f"row={row_number}; period={period}; place={place}; "
                "image prompt preserved from source workbook."
            ),
        }
        if voice_role:
            cut_payload["voice_role"] = voice_role
        if highlight_caption and highlight_caption not in {"-", "—"}:
            cut_payload["highlight_caption"] = highlight_caption
        cuts.append(cut_payload)
        internal_cut_number += 1
    if not cuts:
        raise ValueError(f"{sheet_name}: no cuts found")

    code = _episode_code(episode_number)
    return {
        "script_version": SCRIPT_VERSION,
        "prepared_source": True,
        "visual_policy_mode": "source-locked",
        "source_schema": SOURCE_SCHEMA,
        "title": title,
        "topic": topic,
        "series": SERIES_NAME,
        "episode_number": episode_number,
        "episode_code": code,
        "episode_id": code,
        "source_sheet": sheet_name,
        "thumbnail_text": thumbnail_text,
        "thumbnail_prompt": thumbnail_prompt,
        "visual_world": {
            "time_range": period,
            "place_scope": place,
            "culture_scope": place,
            "source_characters": characters,
        },
        "source": {
            "workbook": str(workbook_path),
            "workbook_sha256": workbook_sha256,
            "worksheet": sheet_name,
            "schema": SOURCE_SCHEMA,
            "header_row": 9,
            "cut_start_row": 10,
        },
        "cuts": cuts,
    }


def build_prepared_scripts(workbook_path: Path) -> tuple[list[tuple[str, dict[str, Any]]], dict[str, Any]]:
    workbook_path = workbook_path.resolve()
    workbook_sha256 = _sha256_file(workbook_path)
    sheets = _load_xlsx_workbook(workbook_path)
    if not sheets:
        raise ValueError("workbook has no worksheets")

    parsed_sheets: list[tuple[int, str, dict[int, dict[int, str]]]] = []
    for sheet_name, rows in sheets:
        match = _SHEET_NAME_RE.fullmatch(sheet_name) or _NUMERIC_SHEET_NAME_RE.fullmatch(sheet_name)
        if match is None:
            raise ValueError(f"invalid worksheet name: {sheet_name!r}")
        parsed_sheets.append((int(match.group("episode")), sheet_name, rows))
    first_episode = parsed_sheets[0][0]
    expected_episode_numbers = list(range(first_episode, first_episode + len(parsed_sheets)))
    actual_episode_numbers = [episode for episode, _sheet_name, _rows in parsed_sheets]
    if actual_episode_numbers != expected_episode_numbers:
        raise ValueError(
            "worksheet episode sequence mismatch: "
            f"expected {expected_episode_numbers}, found {actual_episode_numbers}"
        )

    scripts: list[tuple[str, dict[str, Any]]] = []
    for episode_number, sheet_name, rows in parsed_sheets:
        script = _build_episode_script(
            workbook_path=workbook_path,
            workbook_sha256=workbook_sha256,
            sheet_name=sheet_name,
            rows=rows,
            episode_number=episode_number,
        )
        scripts.append((f"{script['episode_code']}.json", script))

    total_cuts = sum(len(script["cuts"]) for _filename, script in scripts)
    last_episode = actual_episode_numbers[-1]
    manifest_file = (
        "manifest.json"
        if actual_episode_numbers == [1, 2, 3, 4]
        else f"manifest_ep{first_episode:02d}-{last_episode:02d}.json"
    )
    manifest = {
        "manifest_version": 1,
        "manifest_file": manifest_file,
        "script_version": SCRIPT_VERSION,
        "source_schema": SOURCE_SCHEMA,
        "source_workbook": str(workbook_path),
        "source_sha256": workbook_sha256,
        "source_size": workbook_path.stat().st_size,
        "source_contract": {
            "worksheet_count": len(sheets),
            "first_episode": first_episode,
            "last_episode": last_episode,
            "metadata_rows": "A1:B7",
            "header_row": 9,
            "cut_start_row": 10,
            "headers_by_sheet": {
                sheet_name: [_row_value(rows, 9, column) for column in range(1, 7)]
                for _episode, sheet_name, rows in parsed_sheets
            },
            "renderable_variety_caption_headers": list(_SOURCE_VARIETY_CAPTION_HEADERS),
        },
        "channel": CHANNEL,
        "template_project_id": TEMPLATE_PROJECT_ID,
        "series": SERIES_NAME,
        "episode_count": len(scripts),
        "cut_count": total_cuts,
        "shorts_cut_count": sum(
            1
            for _filename, script in scripts
            for cut in script["cuts"]
            if cut["shorts_candidate"]
        ),
        "episodes": [
            {
                "episode_number": script["episode_number"],
                "episode_code": script["episode_code"],
                "title": script["title"],
                "topic": script["topic"],
                "source_sheet": script["source_sheet"],
                "cut_count": len(script["cuts"]),
                "shorts_cut_count": sum(bool(cut["shorts_candidate"]) for cut in script["cuts"]),
            }
            for _filename, script in scripts
        ],
    }
    return scripts, manifest


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def write_prepared_scripts(
    workbook_path: Path,
    output_dir: Path,
    *,
    replace: bool = False,
    preserve_existing: bool = False,
) -> dict[str, Any]:
    scripts, manifest = build_prepared_scripts(workbook_path)
    output_dir = output_dir.resolve()
    if output_dir.exists() and not replace and not preserve_existing:
        raise FileExistsError(f"prepared script directory already exists: {output_dir}")

    stage_dir = output_dir.parent / f".{output_dir.name}.ch4_stage_{uuid.uuid4().hex[:8]}"
    backup_dir: Path | None = None
    try:
        if output_dir.exists() and preserve_existing:
            shutil.copytree(output_dir, stage_dir)
        else:
            stage_dir.mkdir(parents=True, exist_ok=False)
        files: list[dict[str, Any]] = []
        for filename, script in scripts:
            payload = _json_bytes(script)
            path = stage_dir / filename
            _write_bytes(path, payload)
            files.append(
                {
                    "path": filename,
                    "sha256": _sha256_bytes(payload),
                    "episode_number": script["episode_number"],
                    "episode_code": script["episode_code"],
                    "cut_count": len(script["cuts"]),
                }
            )
        manifest = dict(manifest)
        manifest["created_at"] = _utc_timestamp()
        manifest["files"] = files
        _write_bytes(stage_dir / str(manifest["manifest_file"]), _json_bytes(manifest))

        if output_dir.exists():
            first_episode = int(manifest["source_contract"]["first_episode"])
            last_episode = int(manifest["source_contract"]["last_episode"])
            backup_dir = output_dir.parent / (
                f"{output_dir.name}_backup_before_ch4_ep{first_episode:02d}-{last_episode:02d}_"
                f"{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            output_dir.replace(backup_dir)
        stage_dir.replace(output_dir)
    except Exception:
        if backup_dir is not None and backup_dir.exists() and not output_dir.exists():
            backup_dir.replace(output_dir)
        raise
    return manifest


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(DEFAULT_WORKBOOK))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--merge-existing", action="store_true")
    args = parser.parse_args()
    manifest = write_prepared_scripts(
        Path(args.input),
        Path(args.output),
        replace=bool(args.replace),
        preserve_existing=bool(args.merge_existing),
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
