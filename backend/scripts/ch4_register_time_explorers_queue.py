"""Register CH4 Time Explorers season 1 prepared scripts in the existing queue."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import socket
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import SYSTEM_DIR  # noqa: E402
from app.tasks.pipeline_tasks import _validate_prepared_script  # noqa: E402
from scripts.ch4_time_explorers_workbook_to_prepared_scripts import (  # noqa: E402
    CHANNEL,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_WORKBOOK,
    SERIES_NAME,
    TEMPLATE_PROJECT_ID,
    build_prepared_scripts,
    write_prepared_scripts,
)


ACTIVE_STATUSES = {"running", "paused"}
SEASON_EPISODE_PREFIX = "CH4-WH-S01-EP"


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"queue read failed: {type(exc).__name__}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("queue payload must be an object")
    return payload


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.ch4_time_explorers.tmp")
    temporary.write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    temporary.replace(path)


def _queue_item(script: dict[str, Any], filename: str, *, item_id: str, queued_at: str) -> dict[str, Any]:
    cuts = script.get("cuts") or []
    cut_count = len(cuts)
    episode_number = int(script["episode_number"])
    episode_code = str(script["episode_code"])
    return {
        "id": item_id,
        "topic": str(script["topic"]),
        "template_project_id": TEMPLATE_PROJECT_ID,
        "target_duration": cut_count * 4,
        "target_cuts": cut_count,
        "channel": CHANNEL,
        "openings": [],
        "endings": [],
        "core_content": (
            f"[Prepared Script] {filename}\n"
            f"[Source Workbook Sheet] {script['source_sheet']}\n"
            f"[Cuts] {cut_count}\n"
            f"[Series] {SERIES_NAME}"
        ),
        "episode_number": episode_number,
        "series": SERIES_NAME,
        "episode_code": episode_code,
        "episode_id": episode_code,
        "next_episode_preview": "",
        "queued_source": "import",
        "queued_at": queued_at,
        "queued_note": "기괴와 변칙의 세계사 시즌1 원본 대본 검증 완료",
        "requeued_from_task_id": "",
        "restored_from_project_id": "",
        "status": "pending",
    }


def _manifest_file_index(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for entry in manifest.get("files") or []:
        if not isinstance(entry, dict):
            raise ValueError("prepared manifest has an invalid file entry")
        filename = Path(str(entry.get("path") or "")).name
        if not filename or filename in index:
            raise ValueError(f"prepared manifest has duplicate or invalid path: {filename!r}")
        index[filename] = entry
    return index


def validate_prepared_scripts(workbook_path: Path, prepared_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    canonical_scripts, canonical_manifest = build_prepared_scripts(workbook_path)
    manifest_path = prepared_dir / str(canonical_manifest["manifest_file"])
    if not manifest_path.is_file():
        raise FileNotFoundError(f"prepared manifest missing: {manifest_path}")
    written_manifest = _load_json(manifest_path)
    for key in (
        "script_version",
        "source_schema",
        "source_workbook",
        "source_sha256",
        "source_size",
        "channel",
        "template_project_id",
        "series",
        "episode_count",
        "cut_count",
        "shorts_cut_count",
    ):
        if written_manifest.get(key) != canonical_manifest.get(key):
            raise ValueError(
                f"prepared manifest {key} mismatch: "
                f"{written_manifest.get(key)!r} != {canonical_manifest.get(key)!r}"
            )
    file_index = _manifest_file_index(written_manifest)
    scripts: list[dict[str, Any]] = []
    for filename, expected_script in canonical_scripts:
        path = prepared_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"prepared script missing: {path}")
        script = _load_json(path)
        if script != expected_script:
            raise ValueError(f"prepared script differs from source conversion: {filename}")
        entry = file_index.get(filename)
        if entry is None:
            raise ValueError(f"prepared manifest file entry missing: {filename}")
        actual_hash = _sha256_file(path)
        if actual_hash != str(entry.get("sha256") or "").upper():
            raise ValueError(f"prepared script hash mismatch: {filename}")
        _validate_prepared_script(script, path, expected_cut_count=len(script.get("cuts") or []))
        scripts.append(script)
    if len(file_index) != len(scripts):
        raise ValueError("prepared manifest has an unexpected file count")
    return scripts, written_manifest


def _registration_state(
    current: dict[str, Any],
    scripts: list[dict[str, Any]],
    *,
    queued_at: str,
    add_missing: bool = False,
    remove_stale: bool = False,
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    state = copy.deepcopy(current)
    items = state.get("items")
    if not isinstance(items, list):
        return state, ["queue items must be a list"]

    channel_presets = state.get("channel_presets")
    if not isinstance(channel_presets, dict):
        channel_presets = {}
        state["channel_presets"] = channel_presets
    current_preset = str(channel_presets.get(str(CHANNEL)) or "").strip()
    if current_preset and current_preset != TEMPLATE_PROJECT_ID:
        errors.append(
            f"CH4 preset mismatch: {current_preset!r} != {TEMPLATE_PROJECT_ID!r}"
        )
    else:
        channel_presets[str(CHANNEL)] = TEMPLATE_PROJECT_ID

    target_codes = {str(script["episode_code"]) for script in scripts}
    if remove_stale:
        items[:] = [
            item
            for item in items
            if not (
                isinstance(item, dict)
                and int(item.get("channel") or 1) == CHANNEL
                and str(item.get("episode_code") or item.get("episode_id") or "").startswith(SEASON_EPISODE_PREFIX)
                and str(item.get("episode_code") or item.get("episode_id") or "") not in target_codes
            )
        ]

    for script in scripts:
        code = str(script["episode_code"])
        matches = [
            index
            for index, item in enumerate(items)
            if isinstance(item, dict)
            and int(item.get("channel") or 1) == CHANNEL
            and str(item.get("episode_code") or item.get("episode_id") or "").strip() == code
        ]
        if not matches and add_missing:
            insert_at = next(
                (
                    index
                    for index, item in enumerate(items)
                    if isinstance(item, dict)
                    and int(item.get("channel") or 1) == CHANNEL
                    and int(item.get("episode_number") or 0) > int(script["episode_number"])
                ),
                len(items),
            )
            items.insert(
                insert_at,
                _queue_item(
                    script,
                    f"{code}.json",
                    item_id=f"ch4-{uuid.uuid4().hex}",
                    queued_at=queued_at,
                ),
            )
            continue
        if len(matches) != 1:
            errors.append(f"expected one existing CH4 queue item for {code}, found {len(matches)}")
            continue
        current_item = items[matches[0]]
        status = str(current_item.get("status") or "pending").strip().lower()
        if status in ACTIVE_STATUSES:
            errors.append(f"cannot replace active CH4 queue item {code}: status={status}")
            continue
        item_id = str(current_item.get("id") or "").strip()
        if not item_id:
            errors.append(f"CH4 queue item {code} is missing id")
            continue
        filename = f"{code}.json"
        items[matches[0]] = _queue_item(
            script,
            filename,
            item_id=item_id,
            queued_at=queued_at,
        )
    return state, errors


def _backend_port_is_open() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 8000), timeout=0.5):
            return True
    except OSError:
        return False


def register_queue(
    workbook_path: Path,
    prepared_dir: Path,
    *,
    write: bool = False,
    merge_existing: bool = False,
    add_missing: bool = False,
    remove_stale: bool = False,
) -> dict[str, Any]:
    queue_file = SYSTEM_DIR / "oneclick_queue.json"
    current = _load_json(queue_file)
    canonical_scripts, canonical_manifest = build_prepared_scripts(workbook_path)
    planned_scripts = [script for _filename, script in canonical_scripts]
    target_episode_codes = {
        str(script["episode_code"])
        for script in planned_scripts
    }
    state, errors = _registration_state(
        current,
        planned_scripts,
        queued_at=_utc_timestamp(),
        add_missing=add_missing,
        remove_stale=remove_stale,
    )
    if prepared_dir.exists() and not write and not merge_existing:
        errors.append(f"prepared script directory already exists: {prepared_dir}")
    if write and errors:
        raise SystemExit("CH4 registration blocked by validation errors: " + "; ".join(errors))

    queue_backup = ""
    written_manifest: dict[str, Any] | None = None
    result_state = state
    preserved_hashes: dict[str, str] = {}
    if write:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        first_episode = min(int(script["episode_number"]) for script in planned_scripts)
        last_episode = max(int(script["episode_number"]) for script in planned_scripts)
        backup_path = queue_file.with_name(
            f"oneclick_queue.before_ch4_time_explorers_ep{first_episode:02d}-{last_episode:02d}_{stamp}.json"
        )
        shutil.copy2(queue_file, backup_path)
        queue_backup = str(backup_path)
        target_files = {
            filename
            for filename, _script in canonical_scripts
        }
        target_files.add(str(canonical_manifest["manifest_file"]))
        if merge_existing and prepared_dir.is_dir():
            preserved_hashes = {
                path.name: _sha256_file(path)
                for path in prepared_dir.iterdir()
                if path.is_file() and path.name not in target_files
            }
        write_prepared_scripts(
            workbook_path,
            prepared_dir,
            replace=prepared_dir.exists(),
            preserve_existing=merge_existing,
        )
        for filename, expected_hash in preserved_hashes.items():
            path = prepared_dir / filename
            if not path.is_file() or _sha256_file(path) != expected_hash:
                raise RuntimeError(f"existing prepared script changed during merge: {filename}")
        validated_scripts, written_manifest = validate_prepared_scripts(workbook_path, prepared_dir)
        result_state, validation_errors = _registration_state(
            current,
            validated_scripts,
            queued_at=_utc_timestamp(),
            add_missing=add_missing,
            remove_stale=remove_stale,
        )
        if validation_errors:
            raise SystemExit("CH4 registration blocked after prepared-script validation: " + "; ".join(validation_errors))
        _write_json_atomic(queue_file, result_state)
        result_state = _load_json(queue_file)

    final_items = [item for item in result_state.get("items") or [] if isinstance(item, dict)]
    target_items = [
        item
        for item in final_items
        if int(item.get("channel") or 1) == CHANNEL
        and str(item.get("episode_code") or item.get("episode_id") or "") in target_episode_codes
    ]
    return {
        "write": write,
        "merge_existing": merge_existing,
        "add_missing": add_missing,
        "remove_stale": remove_stale,
        "workbook": str(Path(workbook_path).resolve()),
        "workbook_sha256": canonical_manifest["source_sha256"],
        "prepared_dir": str(prepared_dir),
        "existing_total": len(current.get("items") or []),
        "final_total": len(final_items),
        "registered_ch4": len(target_items),
        "registered_codes": [item.get("episode_code") for item in target_items],
        "cut_counts": [item.get("target_cuts") for item in target_items],
        "durations": [item.get("target_duration") for item in target_items],
        "channel_4_preset": (result_state.get("channel_presets") or {}).get("4"),
        "queue_backup": queue_backup,
        "preserved_file_count": len(preserved_hashes),
        "manifest": written_manifest,
        "errors": errors,
    }


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(DEFAULT_WORKBOOK))
    parser.add_argument("--prepared-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--merge-existing", action="store_true")
    parser.add_argument("--add-missing", action="store_true")
    parser.add_argument("--remove-stale", action="store_true")
    args = parser.parse_args()
    if args.write and _backend_port_is_open():
        raise SystemExit(
            "backend port 8000 is open; stop or restart the backend with the updated code before offline queue registration"
        )
    result = register_queue(
        Path(args.input),
        Path(args.prepared_dir),
        write=bool(args.write),
        merge_existing=bool(args.merge_existing),
        add_missing=bool(args.add_missing),
        remove_stale=bool(args.remove_stale),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
