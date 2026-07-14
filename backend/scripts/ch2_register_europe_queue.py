from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import DB_PATH, SYSTEM_DIR  # noqa: E402
from scripts.ch2_europe_titles_en import english_episode_title  # noqa: E402
from scripts.ch2_europe_workbook_to_prepared_scripts import (  # noqa: E402
    CJK_RE,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_WORKBOOKS,
    EXPECTED_SOURCE_RANGES,
    INTEGRATED_EP_SHEET_RE,
    SCRIPT_VERSION,
    SOURCE_LOCKED_VISUAL_POLICY_MODE,
    _compact_text,
    _load_xlsx_workbook,
)


TEMPLATE_PROJECT_ID = "e6619f7e"
CHANNEL = 2
SERIES_NAME = "Scartography"
# Proven by the completed CH2 English projects already stored in the project DB.
CH2_ENGLISH_VOICE_ID = "fIGaHjfrR8KmMy0vGEVJ"
DEFAULT_QUEUE_WORKBOOK = Path(
    r"Z:\HDD2\longtube\CH2 유럽사\유럽사\유럽사_시크릿_179부작_큐시트_설계.xlsx"
)
QUEUE_SHEET_NAME = "에피소드_설계"
EXPECTED_QUEUE_HEADER = (
    "EP 번호",
    "시즌",
    "시대",
    "정렬연도",
    "연도/시기",
    "주요국가/지역",
    "피해/파급국가",
    "연결축",
    "어그로 제목",
    "본편 주제",
    "썸네일 문구",
    "사건의 출발",
    "주요사건",
    "갈림길/반전",
    "핵심내용",
    "결과/의미",
    "이전회 연결",
    "다음회 떡밥",
    "대본 3막 구조",
    "필수 전쟁/사고/인물",
    "피해국 관점 삽입",
    "검증 메모",
)
QUEUE_EP_RE = re.compile(r"^유럽사 시크릿-EP(\d{3})$")
EXPECTED_EPISODE_CODES = {f"EP{number:03d}" for number in range(1, 180)}
EXPECTED_SOURCE_NAMES = {path.name for path in DEFAULT_WORKBOOKS}
ACTIVE_QUEUE_STATUSES = {
    "running",
    "queued",
    "prepared",
    "uploading",
    "upload_pending",
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _int_value(value: Any, default: int = -1) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _manifest_file_index(
    manifest: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], list[str]]:
    errors: list[str] = []
    checks = (
        (manifest.get("script_version") == SCRIPT_VERSION, "script_version"),
        (_compact_text(manifest.get("language")) == "en", "language"),
        (manifest.get("caption_languages") == ["en"], "caption_languages"),
        (_int_value(manifest.get("episode_count")) == 179, "episode_count"),
        (_int_value(manifest.get("cut_count")) == 26850, "cut_count"),
    )
    errors.extend(f"manifest {label} mismatch" for ok, label in checks if not ok)

    source_index: dict[str, dict[str, Any]] = {}
    for entry in manifest.get("sources") or []:
        if not isinstance(entry, dict):
            errors.append("manifest contains a non-object source entry")
            continue
        source_path = Path(str(entry.get("path") or ""))
        source_name = source_path.name
        if not source_name:
            errors.append("manifest source path is missing")
            continue
        if source_name in source_index:
            errors.append(f"manifest duplicate source workbook: {source_name}")
            continue
        source_index[source_name] = entry
        if source_name not in EXPECTED_SOURCE_NAMES:
            errors.append(f"manifest unexpected source workbook: {source_name}")
        expected_range = EXPECTED_SOURCE_RANGES.get(source_name)
        if expected_range is not None:
            first_episode, last_episode = expected_range
            expected_count = last_episode - first_episode + 1
            if _int_value(entry.get("episode_count")) != expected_count:
                errors.append(f"manifest source episode count mismatch: {source_name}")
            if _int_value(entry.get("first_episode")) != first_episode:
                errors.append(f"manifest source first episode mismatch: {source_name}")
            if _int_value(entry.get("last_episode")) != last_episode:
                errors.append(f"manifest source last episode mismatch: {source_name}")
        if not re.fullmatch(r"[0-9A-Fa-f]{64}", str(entry.get("sha256") or "")):
            errors.append(f"manifest invalid source hash: {source_name}")
        if not source_path.is_file():
            errors.append(f"manifest source workbook is missing: {source_path}")
        elif _sha256_file(source_path) != str(entry.get("sha256") or "").upper():
            errors.append(f"manifest source hash mismatch: {source_name}")
    if set(source_index) != EXPECTED_SOURCE_NAMES:
        errors.append(
            "manifest source workbook coverage mismatch: "
            f"found {len(source_index)}, expected {len(EXPECTED_SOURCE_NAMES)}"
        )

    file_index: dict[str, dict[str, Any]] = {}
    for entry in manifest.get("files") or []:
        if not isinstance(entry, dict):
            errors.append("manifest contains a non-object file entry")
            continue
        episode_code = _compact_text(entry.get("episode_code"))
        expected_file = f"{episode_code}.json"
        if episode_code not in EXPECTED_EPISODE_CODES:
            errors.append(f"manifest invalid episode code: {episode_code!r}")
            continue
        if episode_code in file_index:
            errors.append(f"manifest duplicate file entry: {episode_code}")
            continue
        file_index[episode_code] = entry
        if _compact_text(entry.get("file")) != expected_file:
            errors.append(f"manifest filename mismatch: {episode_code}")
        if _int_value(entry.get("cuts")) != 150:
            errors.append(f"manifest cut count mismatch: {episode_code}")
        if not re.fullmatch(r"[0-9A-Fa-f]{64}", str(entry.get("sha256") or "")):
            errors.append(f"manifest invalid file hash: {episode_code}")
    if set(file_index) != EXPECTED_EPISODE_CODES:
        errors.append(
            f"manifest episode coverage mismatch: found {len(file_index)}, expected 179"
        )
    return file_index, source_index, errors


def _english_only_script_errors(script: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if _compact_text(script.get("language")) != "en":
        errors.append("language must be en")
    if script.get("caption_languages") != ["en"]:
        errors.append("caption_languages must be ['en']")
    if _compact_text(script.get("caption_source")) != "script_tracks":
        errors.append("caption_source must be script_tracks")
    for index, cut in enumerate(script.get("cuts") or [], start=1):
        narration = _compact_text(cut.get("narration"))
        tracks = cut.get("caption_tracks")
        if not isinstance(tracks, dict) or set(tracks) != {"en"}:
            errors.append(f"cut {index}: caption_tracks must contain only en")
            continue
        english_caption = _compact_text(tracks.get("en"))
        if english_caption != narration:
            errors.append(f"cut {index}: English caption does not match narration")
        if CJK_RE.search(narration) or CJK_RE.search(english_caption):
            errors.append(f"cut {index}: narration/caption contains CJK")
    return errors


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _backend_port_is_open() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 8000), timeout=0.3):
            return True
    except OSError:
        return False


def _english_only_project_config(current: dict[str, Any]) -> dict[str, Any]:
    config = dict(current or {})
    config.update(
        {
            "language": "en",
            "tts_voice_lang": "en",
            "caption_languages": ["en"],
            "caption_source": "script_tracks",
            "youtube_captions_enabled": True,
        }
    )
    if not _compact_text(config.get("tts_voice_id")):
        config["tts_voice_id"] = CH2_ENGLISH_VOICE_ID
    return config


def _configure_project_english_only(*, write: bool) -> tuple[dict[str, Any], list[str]]:
    from sqlalchemy.orm.attributes import flag_modified

    from app.models.database import SessionLocal
    from app.models.project import Project

    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == TEMPLATE_PROJECT_ID).first()
        if project is None:
            return {}, [f"CH2 template project is missing: {TEMPLATE_PROJECT_ID}"]
        current = dict(project.config or {})
        try:
            project_channel = int(current.get("channel") or current.get("youtube_channel") or 0)
        except (TypeError, ValueError):
            project_channel = 0
        if project_channel != CHANNEL:
            return {}, [f"CH2 template project channel mismatch: {project_channel}"]
        target = _english_only_project_config(current)
        changed_keys = sorted(
            key for key, value in target.items() if current.get(key) != value
        )
        if write and changed_keys:
            project.config = target
            flag_modified(project, "config")
            db.commit()
        return {
            "project_id": TEMPLATE_PROJECT_ID,
            "write": write,
            "changed_keys": changed_keys,
            "language": target.get("language"),
            "tts_voice_lang": target.get("tts_voice_lang"),
            "tts_voice_id": target.get("tts_voice_id"),
            "caption_languages": target.get("caption_languages"),
            "caption_source": target.get("caption_source"),
            "youtube_captions_enabled": target.get("youtube_captions_enabled"),
        }, []
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _queue_item(
    *,
    episode_number: int,
    episode_code: str,
    title: str,
    queued_at: str,
) -> dict[str, Any]:
    return {
        "id": f"ch2-europe-ep{episode_number:03d}",
        "topic": title,
        "template_project_id": TEMPLATE_PROJECT_ID,
        "target_duration": 600,
        "target_cuts": 150,
        "channel": CHANNEL,
        "openings": [],
        "endings": [],
        "core_content": (
            f"[Prepared Script] {episode_code}.json\n"
            "[Source] Europe integrated workbooks (5 files)\n"
            "[Cuts] 150\n"
            "[Audio] English\n"
            "[Captions] English"
        ),
        "episode_number": episode_number,
        "series": SERIES_NAME,
        "episode_code": episode_code,
        "episode_id": episode_code,
        "next_episode_preview": "",
        "queued_source": "import",
        "queued_at": queued_at,
        "queued_note": "Integrated Europe workbooks / English prepared script ready",
        "requeued_from_task_id": "",
        "restored_from_project_id": "",
        "status": "pending",
    }


def build_queue_items(
    workbook_path: Path,
    prepared_dir: Path,
    *,
    queued_at: str | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    from app.tasks.pipeline_tasks import _validate_prepared_script

    queued_at = queued_at or _utc_timestamp()
    errors: list[str] = []
    manifest_path = prepared_dir / "manifest.json"
    if not manifest_path.is_file():
        return [], [f"prepared-script manifest is missing: {manifest_path}"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [], [f"invalid manifest JSON: {type(exc).__name__}: {exc}"]
    if not isinstance(manifest, dict):
        return [], ["prepared-script manifest must be a JSON object"]
    manifest_files, manifest_sources, manifest_errors = _manifest_file_index(manifest)
    errors.extend(manifest_errors)

    workbook = _load_xlsx_workbook(workbook_path)
    if QUEUE_SHEET_NAME not in workbook.sheetnames:
        return [], errors + [f"workbook {QUEUE_SHEET_NAME} sheet is missing"]
    ws = workbook[QUEUE_SHEET_NAME]
    if ws.max_row != 180 or ws.max_column != 22:
        errors.append(
            f"{QUEUE_SHEET_NAME} used range mismatch: "
            f"rows={ws.max_row}, cols={ws.max_column}, expected 180x22"
        )
    header = tuple(_compact_text(ws.cell(1, col).value) for col in range(1, 23))
    if header != EXPECTED_QUEUE_HEADER:
        errors.append(f"{QUEUE_SHEET_NAME} header mismatch: {header}")

    items: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for row in range(2, ws.max_row + 1):
        values = tuple(_compact_text(ws.cell(row, col).value) for col in range(1, 23))
        ep_text = values[0]
        if not any(values):
            continue
        if any(not value for value in values):
            errors.append(f"{QUEUE_SHEET_NAME} row {row}: one or more cells are blank")
        match = QUEUE_EP_RE.fullmatch(ep_text)
        if not match:
            errors.append(f"{QUEUE_SHEET_NAME} row {row}: invalid EP value {ep_text!r}")
            continue
        episode_number = int(match.group(1))
        expected_code = f"EP{episode_number:03d}"
        if episode_number < 1 or episode_number > 179:
            errors.append(f"{QUEUE_SHEET_NAME} row {row}: out-of-range {expected_code}")
            continue
        if expected_code in seen_codes:
            errors.append(f"{QUEUE_SHEET_NAME} row {row}: duplicate {expected_code}")
            continue
        seen_codes.add(expected_code)

        script_path = prepared_dir / f"{expected_code}.json"
        if not script_path.exists():
            errors.append(f"{expected_code}: prepared script is missing")
            continue
        try:
            script = json.loads(script_path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{expected_code}: invalid JSON: {type(exc).__name__}: {exc}")
            continue
        if not isinstance(script, dict):
            errors.append(f"{expected_code}: prepared script must be a JSON object")
            continue

        expected_title = english_episode_title(episode_number)
        source = script.get("source") if isinstance(script.get("source"), dict) else {}
        source_workbook = Path(str(source.get("workbook") or ""))
        source_manifest = manifest_sources.get(source_workbook.name)
        source_worksheet = _compact_text(source.get("worksheet"))
        source_match = INTEGRATED_EP_SHEET_RE.fullmatch(source_worksheet)
        checks = (
            (script.get("script_version") == SCRIPT_VERSION, "script_version"),
            (script.get("prepared_source") is True, "prepared_source"),
            (
                _compact_text(script.get("visual_policy_mode"))
                == SOURCE_LOCKED_VISUAL_POLICY_MODE,
                "visual_policy_mode",
            ),
            (int(script.get("episode_number") or 0) == episode_number, "episode_number"),
            (_compact_text(script.get("episode_code")) == expected_code, "episode_code"),
            (_compact_text(script.get("source_sheet")) == expected_code, "source_sheet"),
            (_compact_text(script.get("title")) == expected_title, "English title"),
            (len(script.get("cuts") or []) == 150, "cut count"),
            (
                _compact_text(source.get("episode_code"))
                == f"유럽사 시크릿-{expected_code}",
                "source episode_code",
            ),
            (
                source_match is not None and int(source_match.group(1)) == episode_number,
                "source worksheet",
            ),
            (source_manifest is not None, "source workbook manifest"),
            (
                source_manifest is not None
                and str(source_workbook) == str(source_manifest.get("path") or ""),
                "source workbook path",
            ),
            (
                source_manifest is not None
                and str(source.get("workbook_sha256") or "").upper()
                == str(source_manifest.get("sha256") or "").upper(),
                "source workbook hash",
            ),
        )
        failed_checks = [label for ok, label in checks if not ok]
        if failed_checks:
            errors.append(f"{expected_code}: mismatch in {', '.join(failed_checks)}")
            continue
        manifest_entry = manifest_files.get(expected_code)
        if manifest_entry is None:
            errors.append(f"{expected_code}: manifest file entry is missing")
            continue
        if _sha256_file(script_path) != str(manifest_entry.get("sha256") or "").upper():
            errors.append(f"{expected_code}: prepared script hash mismatch")
            continue
        try:
            _validate_prepared_script(script, script_path, expected_cut_count=150)
        except Exception as exc:
            errors.append(
                f"{expected_code}: pipeline validation failed: {type(exc).__name__}: {exc}"
            )
            continue
        language_errors = _english_only_script_errors(script)
        if language_errors:
            errors.append(f"{expected_code}: " + "; ".join(language_errors[:8]))
            continue

        items.append(
            _queue_item(
                episode_number=episode_number,
                episode_code=expected_code,
                title=expected_title,
                queued_at=queued_at,
            )
        )

    if seen_codes != EXPECTED_EPISODE_CODES:
        errors.append(
            f"{QUEUE_SHEET_NAME} episode coverage mismatch: "
            f"found {len(seen_codes)}, expected 179"
        )
    if len(items) != 179:
        errors.append(f"queue item count mismatch: built {len(items)}, expected 179")
    return items, errors


def _registration_state(
    current: dict[str, Any],
    ch2_items: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    current_items = [dict(item or {}) for item in current.get("items") or []]
    active_ch2 = [
        item
        for item in current_items
        if int(item.get("channel") or 1) == CHANNEL
        and str(item.get("status") or "").strip().lower() in ACTIVE_QUEUE_STATUSES
    ]
    if active_ch2:
        errors.append(f"active CH2 queue items exist: {len(active_ch2)}")

    preserved_items = [
        item for item in current_items if int(item.get("channel") or 1) != CHANNEL
    ]
    channel_times = dict(current.get("channel_times") or {})
    channel_times[str(CHANNEL)] = None
    channel_presets = dict(current.get("channel_presets") or {})
    channel_presets[str(CHANNEL)] = TEMPLATE_PROJECT_ID
    state = dict(current)
    state.update(
        {
            "channel_times": channel_times,
            "channel_presets": channel_presets,
            "items": preserved_items + ch2_items,
        }
    )
    return state, errors


def _load_queue_state(path: Path) -> dict[str, Any]:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"failed to read current queue: {type(exc).__name__}: {exc}") from exc
    if not isinstance(state, dict):
        raise RuntimeError("current queue must be a JSON object")
    return state


def _write_queue_state(path: Path, state: dict[str, Any]) -> None:
    payload = (json.dumps(state, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    temp_path = path.with_name(f"{path.name}.tmp_ch2_europe")
    temp_path.write_bytes(payload)
    temp_path.replace(path)


def register_queue(
    workbook_path: Path,
    prepared_dir: Path,
    *,
    write: bool = False,
) -> dict[str, Any]:
    queue_file = SYSTEM_DIR / "oneclick_queue.json"
    current = _load_queue_state(queue_file)
    queued_at = _utc_timestamp()
    ch2_items, errors = build_queue_items(
        workbook_path,
        prepared_dir,
        queued_at=queued_at,
    )
    state, state_errors = _registration_state(current, ch2_items)
    errors.extend(state_errors)
    project_config, project_errors = _configure_project_english_only(write=False)
    errors.extend(project_errors)
    if write and errors:
        raise SystemExit("queue registration blocked by validation errors")

    backup_path = ""
    db_backup_path = ""
    result_state = state
    if write:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = SYSTEM_DIR / f"oneclick_queue.before_ch2_europe_179_{stamp}.json"
        if queue_file.exists():
            shutil.copy2(queue_file, backup)
            backup_path = str(backup)
        db_backup = DB_PATH.with_name(f"longtube.before_ch2_europe_179_{stamp}.db")
        shutil.copy2(DB_PATH, db_backup)
        db_backup_path = str(db_backup)
        project_config, project_errors = _configure_project_english_only(write=True)
        if project_errors:
            raise SystemExit("CH2 English project configuration failed")
        _write_queue_state(queue_file, state)
        result_state = _load_queue_state(queue_file)

    result_items = result_state.get("items") or []
    result_ch2 = [item for item in result_items if int(item.get("channel") or 1) == CHANNEL]
    return {
        "write": write,
        "workbook": str(workbook_path),
        "prepared_dir": str(prepared_dir),
        "existing_total": len(current.get("items") or []),
        "existing_ch2": sum(
            1
            for item in current.get("items") or []
            if int(item.get("channel") or 1) == CHANNEL
        ),
        "preserved_other_channels": sum(
            1
            for item in result_items
            if int(item.get("channel") or 1) != CHANNEL
        ),
        "registered_ch2": len(result_ch2),
        "final_total": len(result_items),
        "channel_2_time": (result_state.get("channel_times") or {}).get("2"),
        "channel_2_preset": (result_state.get("channel_presets") or {}).get("2"),
        "first_ch2": result_ch2[0] if result_ch2 else None,
        "last_ch2": result_ch2[-1] if result_ch2 else None,
        "project_config": project_config,
        "backup": backup_path,
        "db_backup": db_backup_path,
        "error_count": len(errors),
        "errors": errors[:100],
    }


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(DEFAULT_QUEUE_WORKBOOK))
    parser.add_argument("--prepared-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.write and _backend_port_is_open():
        raise SystemExit("stop the backend before --write so its in-memory queue cannot overwrite the file")
    result = register_queue(
        Path(args.input),
        Path(args.prepared_dir),
        write=bool(args.write),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["error_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
