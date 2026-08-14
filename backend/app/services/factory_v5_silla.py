"""Factory V5 adapter for one-XLSX-per-episode Silla production scripts."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import posixpath
import re
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from PIL import Image

from app.config import resolve_project_dir


SOURCE_SCHEMA = "silla-episode-xlsx-v2"
LEGACY_SOURCE_SCHEMA = "silla-episode-xlsx-v1"
DEFAULT_SOURCE_ROOT = Path(
    os.getenv("FACTORY_SILLA_SCRIPT_DIR", r"D:\#대본\채널1_신라사")
)
DEFAULT_ACTUAL_ASSET_ROOT = Path(
    os.getenv(
        "FACTORY_SILLA_ACTUAL_ASSET_DIR",
        r"\\M9\롱폼공장\#대본\실제사진 저장소",
    )
)
EXPECTED_CUT_COUNT = 150

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
_DRAWING_MAIN_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_CJK_RE = re.compile(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]")
_EPISODE_RE = re.compile(r"(?:^|[_\-. ])EP\.?\s*0*(\d{1,4})(?:[_\-. ]|$)", re.IGNORECASE)
_SHORTS_RE = re.compile(r"^S0*([1-9]\d*)-0*([1-9]\d*)$", re.IGNORECASE)
_USAGE_CONDITION_MARKERS = (
    "이용",
    "공공누리",
    "public domain",
    "creative commons",
    "cc by",
)
_TRUSTED_OFFICIAL_SOURCE_DOMAINS = (
    "heritage.go.kr",
    "history.go.kr",
)
_SOURCE_URL_RE = re.compile(r"https?://[^\s|<>]+", re.IGNORECASE)
_SOURCE_REFERENCE_TOKEN_RE = re.compile(r"[0-9a-z가-힣]{2,}", re.IGNORECASE)
_SOURCE_REFERENCE_STOPWORDS = {
    "실제자료", "실제", "자료", "사진", "이미지", "해설", "중심", "별도",
    "효과음", "고정", "음성", "우선", "단순", "표시", "공식", "출처",
    "관련", "공개자료", "기준", "현재", "위치", "경로", "컷",
}


@dataclass(frozen=True)
class EmbeddedAsset:
    row: int
    column: int
    member: str
    data: bytes
    sha256: str


@dataclass
class ParsedSillaWorkbook:
    path: Path
    payload: dict[str, Any]
    summary: dict[str, Any]
    assets_by_cut: dict[int, EmbeddedAsset]


def _text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\r", " ").replace("\n", " ")).strip()


def _has_source_usage_contract(value: object) -> bool:
    note = _text(value).lower()
    urls = [match.rstrip(".,;:)]}") for match in _SOURCE_URL_RE.findall(note)]
    if not urls:
        return False
    if any(marker in note for marker in _USAGE_CONDITION_MARKERS):
        return True
    for url in urls:
        hostname = (urlsplit(url).hostname or "").lower().rstrip(".")
        if any(
            hostname == domain or hostname.endswith(f".{domain}")
            for domain in _TRUSTED_OFFICIAL_SOURCE_DOMAINS
        ):
            return True
    return False


def _source_reference_tokens(value: object) -> set[str]:
    note = _SOURCE_URL_RE.sub(" ", _text(value).lower())
    return {
        token
        for token in _SOURCE_REFERENCE_TOKEN_RE.findall(note)
        if token not in _SOURCE_REFERENCE_STOPWORDS and not token.isdigit()
    }


def _has_shared_source_usage_contract(value: object, contracted_notes: list[str]) -> bool:
    """Allow one source declaration to cover later cuts using the same material.

    The workbook instructions do not require duplicated URLs on every reuse.
    Two non-generic reference tokens must match so an unrelated episode source
    cannot satisfy the cut.
    """
    target_tokens = _source_reference_tokens(value)
    if len(target_tokens) < 2:
        return False
    for contracted_note in contracted_notes:
        if len(target_tokens & _source_reference_tokens(contracted_note)) >= 2:
            return True
    return False


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _column_index(reference: str) -> int:
    match = re.match(r"([A-Z]+)", reference.upper())
    if not match:
        raise ValueError(f"잘못된 XLSX 셀 주소: {reference}")
    out = 0
    for char in match.group(1):
        out = out * 26 + ord(char) - 64
    return out


def _xml_text(node: ET.Element, tag: str) -> str:
    return "".join(child.text or "" for child in node.iter(f"{{{_MAIN_NS}}}{tag}"))


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> Any:
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


def _relationship_map(archive: zipfile.ZipFile, rels_member: str) -> dict[str, str]:
    root = ET.fromstring(archive.read(rels_member))
    return {
        rel.attrib["Id"]: rel.attrib["Target"].replace("\\", "/")
        for rel in root.findall(f"{{{_PACKAGE_REL_NS}}}Relationship")
    }


def _resolve_member(base_member: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join(posixpath.dirname(base_member), target))


def _rels_member(member: str) -> str:
    return posixpath.join(posixpath.dirname(member), "_rels", posixpath.basename(member) + ".rels")


def _read_first_sheet(path: Path) -> tuple[str, dict[tuple[int, int], Any], list[EmbeddedAsset]]:
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in names:
            shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared_strings = [
                _xml_text(item, "t")
                for item in shared_root.findall(f"{{{_MAIN_NS}}}si")
            ]

        workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
        workbook_rels = _relationship_map(archive, "xl/_rels/workbook.xml.rels")
        sheets_node = workbook_root.find(f"{{{_MAIN_NS}}}sheets")
        if sheets_node is None or len(sheets_node) != 1:
            raise ValueError("신라사 에피소드 XLSX는 대본 시트 1개여야 합니다.")
        sheet_node = sheets_node[0]
        sheet_name = sheet_node.attrib.get("name", "")
        rel_id = sheet_node.attrib[f"{{{_OFFICE_REL_NS}}}id"]
        sheet_member = _resolve_member("xl/workbook.xml", workbook_rels[rel_id])
        sheet_root = ET.fromstring(archive.read(sheet_member))

        cells: dict[tuple[int, int], Any] = {}
        for cell in sheet_root.iter(f"{{{_MAIN_NS}}}c"):
            reference = cell.attrib.get("r", "")
            row_match = re.search(r"(\d+)$", reference)
            if not row_match:
                continue
            cells[(int(row_match.group(1)), _column_index(reference))] = _cell_value(
                cell, shared_strings
            )

        assets: list[EmbeddedAsset] = []
        drawing_node = sheet_root.find(f"{{{_MAIN_NS}}}drawing")
        sheet_rels_member = _rels_member(sheet_member)
        if drawing_node is not None and sheet_rels_member in names:
            sheet_rels = _relationship_map(archive, sheet_rels_member)
            drawing_rel_id = drawing_node.attrib.get(f"{{{_OFFICE_REL_NS}}}id", "")
            drawing_member = _resolve_member(sheet_member, sheet_rels[drawing_rel_id])
            drawing_root = ET.fromstring(archive.read(drawing_member))
            drawing_rels_member = _rels_member(drawing_member)
            drawing_rels = _relationship_map(archive, drawing_rels_member)
            ns = {
                "xdr": _DRAWING_NS,
                "a": _DRAWING_MAIN_NS,
                "r": _OFFICE_REL_NS,
            }
            for anchor in list(drawing_root):
                from_node = anchor.find("xdr:from", ns)
                blip = anchor.find(".//a:blip", ns)
                if from_node is None or blip is None:
                    continue
                row_node = from_node.find("xdr:row", ns)
                col_node = from_node.find("xdr:col", ns)
                embed_id = blip.attrib.get(f"{{{_OFFICE_REL_NS}}}embed", "")
                if row_node is None or col_node is None or not embed_id:
                    continue
                media_member = _resolve_member(drawing_member, drawing_rels[embed_id])
                data = archive.read(media_member)
                assets.append(
                    EmbeddedAsset(
                        row=int(row_node.text or 0) + 1,
                        column=int(col_node.text or 0) + 1,
                        member=media_member,
                        data=data,
                        sha256=_sha256_bytes(data),
                    )
                )
        return sheet_name, cells, assets


def _episode_number(path: Path) -> int:
    match = _EPISODE_RE.search(path.stem)
    if not match:
        raise ValueError("파일명에서 EP 번호를 찾을 수 없습니다. 예: 황금의_나라_EP01.xlsx")
    episode = int(match.group(1))
    if episode < 1:
        raise ValueError("EP 번호는 1 이상이어야 합니다.")
    return episode


def _metadata_before_header(cells: dict[tuple[int, int], Any], header_row: int) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in range(1, header_row):
        key = _text(cells.get((row, 1)))
        value = _text(cells.get((row, 2)))
        if key and value:
            out[key] = value
    return out


def _find_cut_header(cells: dict[tuple[int, int], Any]) -> int:
    max_row = max((row for row, _column in cells), default=0)
    for row in range(1, max_row + 1):
        if _text(cells.get((row, 1))) == "컷번호" and _text(cells.get((row, 4))).startswith("대사"):
            return row
    raise ValueError("21열 컷 테이블 헤더를 찾을 수 없습니다.")


def _character_manifest(cells: dict[tuple[int, int], Any], cut_header_row: int) -> list[dict[str, str]]:
    header_row = 0
    for row in range(1, cut_header_row):
        if _text(cells.get((row, 1))) == "인물명" and _text(cells.get((row, 5))) == "Voice Design Prompt":
            header_row = row
            break
    if not header_row:
        return []
    headers = [_text(cells.get((header_row, column))) for column in range(1, 15)]
    items: list[dict[str, str]] = []
    for row in range(header_row + 1, cut_header_row):
        name = _text(cells.get((row, 1)))
        if not name:
            if items:
                break
            continue
        item = {
            headers[column - 1]: _text(cells.get((row, column)))
            for column in range(1, 15)
            if headers[column - 1]
        }
        items.append(item)
    return items


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _validate_external_asset_path(
    raw_path: str,
    *,
    episode_number: int,
    cut_number: int,
    workbook_stem: str,
) -> tuple[Path, bytes]:
    asset_path = Path(raw_path)
    if not asset_path.is_absolute() or not str(asset_path).startswith("\\\\"):
        raise ValueError(f"cut {cut_number}: 실제이미지는 전체 네트워크 경로여야 합니다.")
    if not _is_within(asset_path, DEFAULT_ACTUAL_ASSET_ROOT):
        raise ValueError(
            f"cut {cut_number}: 실제이미지 저장소 경로를 벗어났습니다. "
            f"root={DEFAULT_ACTUAL_ASSET_ROOT}"
        )
    if asset_path.parent.name != workbook_stem:
        raise ValueError(
            f"cut {cut_number}: 실제이미지 에피소드 폴더명이 일치하지 않습니다. "
            f"expected={workbook_stem}, actual={asset_path.parent.name}"
        )
    expected_prefix = f"EP{episode_number:02d}_C{cut_number:03d}_"
    if not asset_path.name.startswith(expected_prefix):
        raise ValueError(
            f"cut {cut_number}: 실제이미지 파일명 규칙 위반. expected prefix={expected_prefix}"
        )
    if asset_path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise ValueError(f"cut {cut_number}: 지원하지 않는 실제이미지 형식 {asset_path.suffix}")
    if not asset_path.is_file() or asset_path.stat().st_size <= 50:
        raise ValueError(f"cut {cut_number}: 실제이미지 파일이 없거나 비어 있습니다: {asset_path}")
    data = asset_path.read_bytes()
    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
    except Exception as exc:
        raise ValueError(f"cut {cut_number}: 실제이미지 파일 검수 실패: {asset_path}") from exc
    return asset_path, data


def parse_silla_workbook(path: Path) -> ParsedSillaWorkbook:
    path = path.resolve()
    if not path.is_file() or path.suffix.lower() != ".xlsx":
        raise FileNotFoundError(path)
    episode_number = _episode_number(path)
    sheet_name, cells, embedded_assets = _read_first_sheet(path)
    if embedded_assets:
        raise ValueError(
            f"새 지침 위반: XLSX 내부 실제이미지 삽입 금지. 내장 이미지 {len(embedded_assets)}개를 제거하고 "
            "P열에 실제사진 저장소의 전체 네트워크 경로를 입력해야 합니다."
        )
    header_row = _find_cut_header(cells)
    headers = tuple(_text(cells.get((header_row, column))) for column in range(1, 22))
    expected_prefix = ("컷번호", "숏츠번호", "인물")
    if headers[:3] != expected_prefix or len(headers) != 21:
        raise ValueError(f"신라사 21열 헤더가 일치하지 않습니다: {headers!r}")

    metadata = _metadata_before_header(cells, header_row)
    title = metadata.get("에피소드 제목", "")
    period = metadata.get("시대 (연도)", "")
    background = metadata.get("배경", "")
    source_layer = metadata.get("사료 층위", "")
    required_metadata = {
        "에피소드 제목": title,
        "시대 (연도)": period,
        "배경": background,
        "등장인물": metadata.get("등장인물", ""),
        "사료 층위": source_layer,
        "유튜브 설명": metadata.get("유튜브 설명", ""),
    }
    missing_metadata = [key for key, value in required_metadata.items() if not value]
    if missing_metadata:
        raise ValueError(f"필수 메타데이터 누락: {missing_metadata}")
    cuts: list[dict[str, Any]] = []
    assets_by_cut: dict[int, EmbeddedAsset] = {}
    shorts_groups: dict[int, list[int]] = {}
    narration_counts: dict[str, int] = {}
    source_contract_notes = [
        note
        for cut_number in range(1, EXPECTED_CUT_COUNT + 1)
        if (note := _text(cells.get((header_row + cut_number, 21))))
        and _has_source_usage_contract(note)
    ]
    for cut_number in range(1, EXPECTED_CUT_COUNT + 1):
        row = header_row + cut_number
        raw_cut = _text(cells.get((row, 1)))
        try:
            actual_cut = int(float(raw_cut))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"cut {cut_number}: 컷번호가 없습니다. row={row}") from exc
        if actual_cut != cut_number:
            raise ValueError(f"cut {cut_number}: 컷번호 불일치 actual={actual_cut}")

        narration = _text(cells.get((row, 4)))
        speaker = _text(cells.get((row, 3)))
        image_prompt = _text(cells.get((row, 14)))
        actual_source = _text(cells.get((row, 16)))
        source_and_usage_note = _text(cells.get((row, 21)))
        if not narration or not speaker:
            raise ValueError(f"cut {cut_number}: 인물 또는 대사 누락")
        narration_counts[narration] = narration_counts.get(narration, 0) + 1
        if actual_source:
            if image_prompt or _text(cells.get((row, 15))):
                raise ValueError(
                    f"cut {cut_number}: 실제자료 컷은 KREA2·H3에서 제외해야 합니다."
                )
            if speaker != "해설자":
                raise ValueError(f"cut {cut_number}: 실제자료 컷은 해설자가 자료 의미를 설명해야 합니다.")
            if not (
                _has_source_usage_contract(source_and_usage_note)
                or _has_shared_source_usage_contract(source_and_usage_note, source_contract_notes)
            ):
                raise ValueError(
                    f"cut {cut_number}: U열 또는 같은 대본의 동일 자료 출처 정보에 "
                    "출처 URL·자료 설명·이용조건이 필요합니다."
                )
            asset_path, asset_data = _validate_external_asset_path(
                actual_source,
                episode_number=episode_number,
                cut_number=cut_number,
                workbook_stem=path.stem,
            )
            assets_by_cut[cut_number] = EmbeddedAsset(
                row=row,
                column=16,
                member=str(asset_path),
                data=asset_data,
                sha256=_sha256_bytes(asset_data),
            )
        else:
            if not image_prompt:
                raise ValueError(f"cut {cut_number}: KREA 프롬프트와 실제자료가 모두 없습니다.")
            if _CJK_RE.search(image_prompt):
                raise ValueError(f"cut {cut_number}: KREA 프롬프트에 한중일 문자가 포함되어 있습니다.")

        shorts_marker = _text(cells.get((row, 2)))
        shorts_candidate = False
        shorts_group = 0
        shorts_order = 0
        if shorts_marker:
            marker_match = _SHORTS_RE.fullmatch(shorts_marker)
            if not marker_match:
                raise ValueError(f"cut {cut_number}: 숏츠번호 형식 오류 {shorts_marker!r}")
            shorts_group = int(marker_match.group(1))
            shorts_order = int(marker_match.group(2))
            shorts_groups.setdefault(shorts_group, []).append(shorts_order)
            shorts_candidate = True

        actual_asset: dict[str, Any] | None = None
        if actual_source:
            asset = assets_by_cut[cut_number]
            actual_asset = {
                "source_note": source_and_usage_note,
                "source_member": asset.member,
                "source_sha256": asset.sha256,
                "path": asset.member,
            }

        cut: dict[str, Any] = {
            "cut_number": cut_number,
            "narration": narration,
            "speaker": speaker,
            "image_prompt": image_prompt,
            "visual_year": period,
            "visual_period": period,
            "visual_location": background,
            "visual_evidence": actual_source or source_layer,
            "scene_type": "source_asset" if actual_source else "narration",
            "shorts_candidate": shorts_candidate,
            "shorts_group": shorts_group,
            "shorts_order": shorts_order,
            "shorts_reason": f"source workbook marker {shorts_marker}" if shorts_marker else "",
            "shorts_title": "",
            "shorts_score": 0,
            "voice_generation_mode": _text(cells.get((row, 5))),
            "dialogue_group": _text(cells.get((row, 6))),
            "voice_direction": _text(cells.get((row, 7))),
            "emotion_intensity": _text(cells.get((row, 8))),
            "tts_speed": _text(cells.get((row, 9))),
            "audio_lead_in_sec": _text(cells.get((row, 10))),
            "audio_tail_sec": _text(cells.get((row, 11))),
            "quote_candidate": _text(cells.get((row, 12))).upper() == "Y",
            "highlight_caption": _text(cells.get((row, 13))),
            "video_tag": _text(cells.get((row, 15))),
            "amb_id": _text(cells.get((row, 17))),
            "sfx_id": _text(cells.get((row, 18))),
            "sfx_timing_sec": _text(cells.get((row, 19))),
            "sfx_volume_db": _text(cells.get((row, 20))),
            "sfx_direction": _text(cells.get((row, 21))),
        }
        if actual_asset:
            cut["actual_asset"] = actual_asset
        if speaker != "해설자" and not re.match(r"^\[[^\]]+\]\s*\S", narration):
            raise ValueError(f"cut {cut_number}: 인물 대사 일레븐랩스 감성태그 누락")
        caption_length = len(cut["highlight_caption"])
        if caption_length < 6 or caption_length > 15:
            raise ValueError(
                f"cut {cut_number}: 한국식 예능 자막은 6~15자여야 합니다. "
                f"actual={caption_length}, caption={cut['highlight_caption']!r}"
            )
        if 6 <= cut_number <= 10 and speaker != "해설자":
            raise ValueError(f"cut {cut_number}: 6~10컷은 해설자 전용이어야 합니다.")
        cuts.append(cut)

    for group, orders in sorted(shorts_groups.items()):
        if orders != list(range(1, len(orders) + 1)) or len(orders) < 10:
            raise ValueError(f"숏츠 그룹 S{group} 순번 오류: {orders}")
    if set(shorts_groups) != {1, 2, 3, 4}:
        raise ValueError(f"숏츠 그룹은 S1~S4여야 합니다. actual={sorted(shorts_groups)}")
    shorts_counts = {group: len(orders) for group, orders in shorts_groups.items()}
    if any(count != 15 for count in shorts_counts.values()):
        raise ValueError(
            f"숏츠는 편당 정확히 15컷이어야 합니다. "
            f"actual={shorts_counts}"
        )
    s1_cuts = [int(cut["cut_number"]) for cut in cuts if cut["shorts_group"] == 1]
    if s1_cuts != list(range(1, 16)):
        raise ValueError(f"숏츠1은 1~15컷이어야 합니다. actual={s1_cuts}")
    if len(assets_by_cut) < 3:
        raise ValueError(f"실제자료는 편당 최소 3컷이어야 합니다. actual={len(assets_by_cut)}")
    duplicated_narration = [text for text, count in narration_counts.items() if count > 1]
    if duplicated_narration:
        raise ValueError(f"동일 대사 완전 중복: {duplicated_narration[:3]}")
    quote_count = sum(1 for cut in cuts if cut["quote_candidate"])
    if quote_count < 3 or quote_count > 5:
        raise ValueError(f"명대사 Y는 편당 3~5개여야 합니다. actual={quote_count}")
    expected_h3_cuts = {
        int(cut["cut_number"])
        for cut in cuts
        if not cut.get("actual_asset")
        and (int(cut["cut_number"]) <= 10 or int(cut["shorts_group"] or 0) in {2, 3, 4})
    }
    actual_h3_cuts = {int(cut["cut_number"]) for cut in cuts if cut["video_tag"]}
    if actual_h3_cuts != expected_h3_cuts:
        missing_h3 = sorted(expected_h3_cuts - actual_h3_cuts)
        extra_h3 = sorted(actual_h3_cuts - expected_h3_cuts)
        raise ValueError(
            f"H3 대상 컷 불일치. missing={missing_h3[:12]}, extra={extra_h3[:12]}"
        )

    voice_cast = _character_manifest(cells, header_row)
    if len(voice_cast) < 4:
        raise ValueError(f"주요 등장인물은 남성 2명·여성 2명, 최소 4명이 필요합니다. actual={len(voice_cast)}")
    primary_voice_cast = voice_cast[:4]
    gender_counts = {
        "남성": sum(1 for item in primary_voice_cast if item.get("성별") == "남성"),
        "여성": sum(1 for item in primary_voice_cast if item.get("성별") == "여성"),
    }
    if gender_counts != {"남성": 2, "여성": 2}:
        raise ValueError(f"주요 등장인물 성별 구성 오류: {gender_counts}")
    cast_names = [str(item.get("인물명") or "") for item in voice_cast]
    primary_cast_names = [str(item.get("인물명") or "") for item in primary_voice_cast]

    def _speaker_matches_cast(speaker: str, cast_name: str) -> bool:
        return bool(speaker and cast_name) and (
            speaker == cast_name or cast_name.startswith(speaker) or speaker.startswith(cast_name)
        )

    dialogue_speakers = {str(cut["speaker"]) for cut in cuts if cut["speaker"] != "해설자"}
    unmapped_speakers = sorted(
        speaker
        for speaker in dialogue_speakers
        if not any(_speaker_matches_cast(speaker, cast_name) for cast_name in cast_names)
    )
    if unmapped_speakers:
        raise ValueError(f"Voice Design 표에 없는 인물 화자: {unmapped_speakers}")
    speaker_counts = {
        cast_name: sum(
            1
            for cut in cuts
            if _speaker_matches_cast(str(cut["speaker"]), cast_name)
        )
        for cast_name in primary_cast_names
    }
    underused = {name: count for name, count in speaker_counts.items() if not name or count < 5}
    if underused:
        raise ValueError(f"주요 인물은 최소 5컷 이상 대사가 필요합니다: {underused}")
    final_ten = cuts[-10:]
    if any(cut["speaker"] != "해설자" for cut in final_ten):
        raise ValueError("마지막 10컷은 해설자 중심의 정리·해석·예고·구독 요청이어야 합니다.")

    footer_notes = [
        _text(cells.get((row, 1)))
        for row in range(header_row + EXPECTED_CUT_COUNT + 1, header_row + EXPECTED_CUT_COUNT + 12)
        if _text(cells.get((row, 1)))
    ]
    footer_text = " ".join(footer_notes)
    content_qa_declared = "최종 qa" in footer_text.casefold() or "최종 재검수" in footer_text

    source_sha256 = _sha256_path(path)
    episode_code = f"SILLA_EP{episode_number:02d}"
    tags = [item.strip() for item in metadata.get("유튜브 태그", "").split(",") if item.strip()]
    shorts_metadata = {
        str(group): {
            "title": metadata.get(f"숏츠{group} 제목", ""),
            "hero_text": metadata.get(f"숏츠{group} 히어로문구", ""),
        }
        for group in sorted(shorts_groups)
    }
    payload: dict[str, Any] = {
        "script_version": "prepared-5.0",
        "prepared_source": True,
        "source_schema": SOURCE_SCHEMA,
        "visual_policy_mode": "source-locked",
        "title": title,
        "topic": title,
        "series": "신라사",
        "episode_number": episode_number,
        "episode": episode_code,
        "episode_code": episode_code,
        "episode_id": episode_code,
        "source_sheet": episode_code,
        "description": metadata.get("유튜브 설명", ""),
        "tags": tags,
        "thumbnail_hook": metadata.get("썸네일 문구", ""),
        "thumbnail_prompt": metadata.get("KREA 썸네일 프롬프트", ""),
        "pinned_comment": metadata.get("첫 번째 댓글", ""),
        "youtube_hashtags": metadata.get("유튜브 설명용 해시태그", ""),
        "source_timeline_draft": metadata.get("유튜브 설명용 타임라인", ""),
        "shorts_metadata": shorts_metadata,
        "voice_cast": voice_cast,
        "source": {
            "schema": SOURCE_SCHEMA,
            "actual_asset_mode": "external-network-path",
            "script_xlsx": str(path),
            "script_xlsx_sha256": source_sha256,
            "script_sheet": sheet_name,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "series": "신라사",
            "episode_code": episode_code,
        },
        "cuts": cuts,
    }
    summary = {
        "filename": path.name,
        "path": str(path),
        "source_sha256": source_sha256,
        "size_bytes": path.stat().st_size,
        "modified_at": datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds"),
        "episode_number": episode_number,
        "episode_code": episode_code,
        "title": title,
        "cut_count": len(cuts),
        "krea_prompt_count": sum(1 for cut in cuts if cut["image_prompt"]),
        "actual_asset_count": len(assets_by_cut),
        "h3_tag_count": sum(1 for cut in cuts if cut["video_tag"]),
        "shorts_cut_count": sum(1 for cut in cuts if cut["shorts_candidate"]),
        "quote_count": sum(1 for cut in cuts if cut["quote_candidate"]),
        "speaker_count": len({cut["speaker"] for cut in cuts}),
        "actual_asset_mode": "external-network-path",
        "content_qa_declared": content_qa_declared,
        "emotion_tag_missing_count": 0,
        "caption_error_count": 0,
        "duplicate_narration_count": 0,
        "valid": True,
        "errors": [],
    }
    return ParsedSillaWorkbook(path=path, payload=payload, summary=summary, assets_by_cut=assets_by_cut)


def resolve_source_workbook(filename: str, root: Path = DEFAULT_SOURCE_ROOT) -> Path:
    clean_name = Path(str(filename or "")).name
    if not clean_name or clean_name != str(filename or "") or Path(clean_name).suffix.lower() != ".xlsx":
        raise ValueError("올바른 XLSX 파일명을 지정하세요.")
    root = root.resolve()
    candidate = (root / clean_name).resolve()
    if candidate.parent != root or not candidate.is_file():
        raise FileNotFoundError(candidate)
    return candidate


def list_silla_workbooks(root: Path = DEFAULT_SOURCE_ROOT) -> dict[str, Any]:
    root = root.resolve()
    items: list[dict[str, Any]] = []
    if root.is_dir():
        for path in sorted(root.glob("*.xlsx"), key=lambda item: item.name.casefold()):
            if path.name.startswith("~$") or not _EPISODE_RE.search(path.stem):
                continue
            try:
                items.append(parse_silla_workbook(path).summary)
            except Exception as exc:
                items.append(
                    {
                        "filename": path.name,
                        "path": str(path),
                        "size_bytes": path.stat().st_size,
                        "modified_at": datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds"),
                        "valid": False,
                        "errors": [f"{type(exc).__name__}: {exc}"],
                    }
                )
    return {
        "factory_version": 5,
        "source_schema": SOURCE_SCHEMA,
        "source_root": str(root),
        "source_root_exists": root.is_dir(),
        "actual_asset_root": str(DEFAULT_ACTUAL_ASSET_ROOT),
        "actual_asset_root_exists": DEFAULT_ACTUAL_ASSET_ROOT.is_dir(),
        "workbooks": items,
    }


def list_silla_registrations(project_dir: Path) -> dict[str, dict[str, Any]]:
    """Return persisted Silla prepared-script registrations by source XLSX filename."""
    registrations: dict[str, dict[str, Any]] = {}
    prepared_dir = project_dir.resolve() / "prepared_scripts"
    if not prepared_dir.is_dir():
        return registrations
    for path in sorted(prepared_dir.glob("*.json"), key=lambda item: item.name.casefold()):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict) or not _is_silla_prepared_payload(payload):
            continue
        source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
        source_filename = Path(str(source.get("script_xlsx") or "")).name
        if not source_filename:
            continue
        registrations[source_filename] = {
            "registered": True,
            "episode_code": _text(payload.get("episode_code") or source.get("episode_code")),
            "prepared_script": str(path),
            "prepared_script_sha256": _sha256_path(path),
            "source_sha256": _text(source.get("script_xlsx_sha256")).upper(),
        }
    return registrations


def _is_silla_prepared_payload(payload: dict[str, Any]) -> bool:
    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    schema = _text(payload.get("source_schema") or source.get("schema"))
    return schema in {SOURCE_SCHEMA, LEGACY_SOURCE_SCHEMA}


def _write_png(data: bytes, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    with Image.open(BytesIO(data)) as image:
        image.load()
        converted = image.convert("RGB") if image.mode not in {"RGB", "RGBA"} else image
        converted.save(temporary, format="PNG", optimize=True)
    temporary.replace(target)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def import_silla_workbook(parsed: ParsedSillaWorkbook, project_dir: Path) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    payload = copy.deepcopy(parsed.payload)
    source_sha = str(parsed.summary["source_sha256"])
    episode_code = str(payload["episode_code"])
    asset_dir = project_dir / "prepared_assets" / "silla" / episode_code / source_sha[:12]
    for cut in payload["cuts"]:
        cut_number = int(cut["cut_number"])
        actual_asset = cut.get("actual_asset")
        if not isinstance(actual_asset, dict):
            continue
        embedded = parsed.assets_by_cut[cut_number]
        target = asset_dir / f"cut_{cut_number:03d}.png"
        _write_png(embedded.data, target)
        actual_asset["path"] = str(target)
        actual_asset["project_relative_path"] = str(target.relative_to(project_dir)).replace("\\", "/")
        actual_asset["normalized_sha256"] = _sha256_path(target)

    from app.tasks.pipeline_tasks import _validate_prepared_script

    _validate_prepared_script(payload, parsed.path, expected_cut_count=EXPECTED_CUT_COUNT)
    output_dir = project_dir / "prepared_scripts"
    target = output_dir / f"{episode_code}_script.json"
    backup_path = ""
    if target.is_file():
        current = json.loads(target.read_text(encoding="utf-8"))
        current_sha = _text((current.get("source") or {}).get("script_xlsx_sha256"))
        if current_sha and current_sha != source_sha:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = output_dir / "_backup" / f"silla_before_{stamp}"
            backup_dir.mkdir(parents=True, exist_ok=False)
            backup_target = backup_dir / target.name
            shutil.copy2(target, backup_target)
            backup_path = str(backup_target)
    _write_json_atomic(target, payload)

    manifest_path = output_dir / "신라사_manifest.json"
    manifest: dict[str, Any] = {
        "factory_version": 5,
        "source_schema": SOURCE_SCHEMA,
        "series": "신라사",
        "episodes": {},
    }
    if manifest_path.is_file():
        try:
            current_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(current_manifest, dict):
                manifest.update(current_manifest)
        except Exception:
            pass
    episodes = manifest.get("episodes")
    if not isinstance(episodes, dict):
        episodes = {}
    episodes[episode_code] = {
        **parsed.summary,
        "prepared_script": str(target),
        "prepared_script_sha256": _sha256_path(target),
        "asset_dir": str(asset_dir),
        "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "backup_path": backup_path,
    }
    manifest["episodes"] = episodes
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    _write_json_atomic(manifest_path, manifest)
    return {
        "episode_code": episode_code,
        "prepared_script": str(target),
        "prepared_script_sha256": _sha256_path(target),
        "asset_dir": str(asset_dir),
        "actual_asset_count": len(parsed.assets_by_cut),
        "backup_path": backup_path,
        "manifest": str(manifest_path),
    }


def apply_actual_assets_to_cut_rows(
    project_id: str,
    config: dict[str, Any] | None,
    script: dict[str, Any],
    cut_rows: dict[int, Any],
) -> int:
    """Materialize prepared source assets as canonical custom cut images."""
    project_dir = resolve_project_dir(project_id, config or {}, create=True)
    applied = 0
    for cut_data in script.get("cuts", []) or []:
        if not isinstance(cut_data, dict):
            continue
        actual_asset = cut_data.get("actual_asset")
        if not isinstance(actual_asset, dict):
            continue
        cut_number = int(cut_data.get("cut_number") or 0)
        cut_row = cut_rows.get(cut_number)
        source_path = Path(_text(actual_asset.get("path")))
        expected_sha = _text(actual_asset.get("source_sha256")).upper()
        normalized_sha = _text(actual_asset.get("normalized_sha256")).upper()
        source_note = _text(actual_asset.get("source_note"))
        if cut_row is None or cut_number < 1:
            raise RuntimeError(f"실제자료 cut 행을 찾을 수 없습니다: {cut_number}")
        if not source_path.is_file():
            raise RuntimeError(f"실제자료 파일이 없습니다: cut {cut_number}, {source_path}")
        if normalized_sha and _sha256_path(source_path) != normalized_sha:
            raise RuntimeError(f"실제자료 해시 검증 실패: cut {cut_number}")
        target = project_dir / "images" / f"cut_{cut_number}.png"
        with Image.open(source_path) as image:
            image.load()
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(".png.tmp")
            converted = image.convert("RGB") if image.mode not in {"RGB", "RGBA"} else image
            converted.save(temporary, format="PNG", optimize=True)
            temporary.replace(target)
        target.with_name(target.name + ".prompt.json").unlink(missing_ok=True)
        sidecar = target.with_name(target.name + ".source.json")
        _write_json_atomic(
            sidecar,
            {
                "source_schema": SOURCE_SCHEMA,
                "cut_number": cut_number,
                "source_path": str(source_path),
                "source_sha256": expected_sha,
                "source_note": source_note,
            },
        )
        cut_row.image_prompt = ""
        cut_row.image_path = f"images/cut_{cut_number}.png"
        cut_row.image_model = "source-asset"
        cut_row.is_custom_image = True
        cut_row.status = "completed"
        applied += 1
    return applied
