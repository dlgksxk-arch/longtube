"""Standalone Script Studio storage and generation helpers."""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import uuid
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.config import BASE_DIR, resolve_cut_video_duration, resolve_project_dir
from app.models.cut import Cut
from app.models.database import SessionLocal
from app.models.project import Project
from app.services import oneclick_service
from app.services.llm.base import BaseLLMService, normalize_language_code
from app.services.llm.factory import get_llm_service, list_llm_models
from app.services.llm.ollama_service import OLLAMA_BASE_URL, OLLAMA_NUM_CTX, OllamaService
from app.services.llm.script_quality import assert_script_quality
from app.services.llm.visual_policy import apply_script_visual_policy, normalize_image_prompt
from app.services.shorts_service import annotate_script_shorts
from app.services.story_plan_stage import assert_llm_provider_key
from app.services.title_utils import script_title_for_language
from app.services.tts.voice_profile import ensure_voice_profile_from_config


SCRIPT_STUDIO_ROOT = BASE_DIR / "data" / "script_studio"
DRAFTS_ROOT = SCRIPT_STUDIO_ROOT / "drafts"
DELETED_DRAFTS_ROOT = SCRIPT_STUDIO_ROOT / "deleted_drafts"
DEFAULT_SCRIPT_STUDIO_MODEL = "qwen3:32b"
VALIDATION_GEMMA_MODEL = "gemma4:26b-a4b-it-q4_K_M"
MAX_VALIDATION_RECHECKS = 3
VALIDATION_PIPELINE_TOTAL_STEPS = 47
_RUNNING_JOBS: dict[str, asyncio.Task] = {}
TIMED_JOB_STAGES = {"story", "script"}
SCRIPT_FORBIDDEN_TERMS = (
    "충격",
    "소름",
    "대박",
    "미쳤다",
    "레전드",
    "알아보자",
    "역사 이야기",
    "진짜 이유",
)
COMMON_REPEAT_WORDS = {
    "그리고",
    "하지만",
    "그런데",
    "그래서",
    "이제",
    "바로",
    "정말",
    "당시",
    "이후",
    "이번",
    "영상",
    "대본",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _elapsed_seconds(started_at: Any, finished_at: Any = None) -> int:
    started = _parse_iso(started_at)
    if not started:
        return 0
    finished = _parse_iso(finished_at) or datetime.now(timezone.utc)
    return max(0, int(round((finished - started).total_seconds())))


def _process_exists(pid: Any) -> bool:
    try:
        value = int(pid or 0)
    except (TypeError, ValueError):
        return False
    if value <= 0:
        return False
    if value == os.getpid():
        return True
    if os.name == "nt":
        try:
            import ctypes

            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, value)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:
            return False
    try:
        os.kill(value, 0)
        return True
    except OSError:
        return False


def _job_stats_from_history(history: list[dict]) -> dict:
    stats: dict[str, dict] = {}
    for stage in sorted(TIMED_JOB_STAGES):
        rows = [
            row for row in history
            if row.get("stage") == stage
            and row.get("status") == "completed"
            and isinstance(row.get("elapsed_seconds"), int)
        ]
        if not rows:
            stats[stage] = {"count": 0, "avg_elapsed_seconds": 0, "last_elapsed_seconds": 0}
            continue
        total = sum(int(row.get("elapsed_seconds") or 0) for row in rows)
        stats[stage] = {
            "count": len(rows),
            "avg_elapsed_seconds": int(round(total / len(rows))),
            "last_elapsed_seconds": int(rows[-1].get("elapsed_seconds") or 0),
        }
    return stats


def _append_job_history(
    meta: dict,
    *,
    stage: str,
    status: str,
    job_id: str | None,
    model: str = "",
    message: str = "",
) -> dict:
    if stage not in TIMED_JOB_STAGES:
        return meta
    progress = meta.get("generation_progress") if isinstance(meta.get("generation_progress"), dict) else {}
    started_at = (
        progress.get("started_at")
        or meta.get("active_job_started_at")
        or progress.get("updated_at")
        or _now_iso()
    )
    finished_at = _now_iso()
    entry = {
        "job_id": str(job_id or progress.get("job_id") or ""),
        "stage": stage,
        "status": status,
        "model": str(_strip_ollama_prefix(model or progress.get("model") or "") or ""),
        "message": str(message or progress.get("message") or ""),
        "started_at": started_at,
        "finished_at": finished_at,
        "elapsed_seconds": _elapsed_seconds(started_at, finished_at),
    }
    history = meta.get("job_history") if isinstance(meta.get("job_history"), list) else []
    if entry["job_id"]:
        history = [row for row in history if not isinstance(row, dict) or row.get("job_id") != entry["job_id"]]
    history = [row for row in history if isinstance(row, dict)]
    history.append(entry)
    meta["job_history"] = history[-100:]
    meta["job_stats"] = _job_stats_from_history(meta["job_history"])
    return meta


def _safe_id() -> str:
    return uuid.uuid4().hex[:10]


def _draft_dir(draft_id: str) -> Path:
    return DRAFTS_ROOT / str(draft_id)


def _deleted_draft_dir(draft_id: str) -> Path:
    return DELETED_DRAFTS_ROOT / str(draft_id)


def _meta_path(draft_id: str) -> Path:
    return _draft_dir(draft_id) / "draft.json"


def _story_path(draft_id: str) -> Path:
    return _draft_dir(draft_id) / "story_plan.json"


def _script_path(draft_id: str) -> Path:
    return _draft_dir(draft_id) / "script.json"


def _partial_script_path(draft_id: str) -> Path:
    return _draft_dir(draft_id) / "partial_script.json"


def _validation_path(draft_id: str) -> Path:
    return _draft_dir(draft_id) / "validation_report.json"


def _soft_delete_draft_dir(draft_id: str, *, reason: str = "deleted") -> dict:
    draft_id = str(draft_id or "").strip()
    if not re.fullmatch(r"[0-9a-f]{10}", draft_id):
        raise FileNotFoundError(f"Script Studio draft not found: {draft_id}")
    meta = _load_meta(draft_id)
    task = _RUNNING_JOBS.get(draft_id)
    if task and not task.done():
        task.cancel()
    _RUNNING_JOBS.pop(draft_id, None)

    target = _draft_dir(draft_id).resolve()
    root = DRAFTS_ROOT.resolve()
    if target == root or root not in target.parents:
        raise ValueError("삭제 대상 경로가 대본실 초안 폴더 밖입니다.")
    if not target.exists():
        return {"ok": True, "draft_id": meta.get("id") or draft_id, "deleted_path": ""}

    deleted_root = DELETED_DRAFTS_ROOT.resolve()
    deleted_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = deleted_root / f"{draft_id}_{stamp}"
    counter = 1
    while destination.exists():
        destination = deleted_root / f"{draft_id}_{stamp}_{counter}"
        counter += 1

    meta["deleted_at"] = _now_iso()
    meta["delete_reason"] = reason
    _save_meta(meta)
    shutil.move(str(target), str(destination))
    return {"ok": True, "draft_id": meta.get("id") or draft_id, "deleted_path": str(destination)}


def _json_read(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _expected_cut_count(config: dict | None) -> int:
    cfg = config or {}
    try:
        target_cuts = int(cfg.get("target_cuts") or 0)
    except (TypeError, ValueError):
        target_cuts = 0
    if target_cuts > 0:
        return target_cuts
    try:
        target_duration = float(cfg.get("target_duration") or 600)
    except (TypeError, ValueError):
        target_duration = 600
    return max(1, math.ceil(target_duration / resolve_cut_video_duration(cfg)))


def _strip_ollama_prefix(value: Any) -> Any:
    text = str(value or "").strip()
    return text.split(":", 1)[1] if text.startswith("ollama:") else value


def _normalize_config(config: dict | None) -> dict:
    cfg = dict(config or {})
    for key in (
        "story_model",
        "script_model",
        "validation_gemma_model",
    ):
        if cfg.get(key):
            cfg[key] = _strip_ollama_prefix(cfg.get(key))
    if not cfg.get("language"):
        cfg["language"] = "ko"
    if not cfg.get("style"):
        cfg["style"] = "news_explainer"
    if not cfg.get("target_duration"):
        cfg["target_duration"] = 600
    if not cfg.get("cut_video_duration"):
        cfg["cut_video_duration"] = 4.0
    cfg["target_cuts"] = _expected_cut_count(cfg)
    if not cfg.get("story_model"):
        cfg["story_model"] = cfg.get("script_model") or DEFAULT_SCRIPT_STUDIO_MODEL
    if not cfg.get("script_model"):
        cfg["script_model"] = cfg.get("story_model") or DEFAULT_SCRIPT_STUDIO_MODEL
    return cfg


def _runtime_config(meta: dict) -> dict:
    cfg = _normalize_config(meta.get("config") or {})
    draft_id = meta["id"]
    cfg["__project_id"] = f"scriptstudio_{draft_id}"
    cfg["result_dir"] = str(_draft_dir(draft_id))
    if meta.get("story_plan"):
        cfg["story_plan"] = meta["story_plan"]
    return cfg


def _draft_summary(meta: dict) -> dict:
    draft_id = meta.get("id")
    script = _json_read(_script_path(draft_id), {}) if draft_id else {}
    partial_script = _json_read(_partial_script_path(draft_id), {}) if draft_id else {}
    story_exists = _story_path(draft_id).exists() if draft_id else False
    script_exists = _script_path(draft_id).exists() if draft_id else False
    partial_script_exists = _partial_script_path(draft_id).exists() if draft_id else False
    visible_script = script if script_exists and isinstance(script, dict) else partial_script
    script_is_partial = (
        not script_exists
        and isinstance(partial_script, dict)
        and (
            (isinstance(partial_script.get("cuts"), list) and bool(partial_script.get("cuts")))
            or _script_has_text_blocks(partial_script)
        )
    )
    summary = dict(meta)
    if isinstance(summary.get("config"), dict):
        summary["config"] = _normalize_config(summary.get("config") or {})
    progress = summary.get("generation_progress") if isinstance(summary.get("generation_progress"), dict) else None
    if progress and progress.get("status") == "running" and progress.get("started_at"):
        progress = dict(progress)
        progress["elapsed_seconds"] = _elapsed_seconds(progress.get("started_at"))
        progress["updated_at"] = _now_iso()
        summary["generation_progress"] = progress
    return {
        **summary,
        "story_exists": story_exists,
        "script_exists": script_exists,
        "script_partial_exists": partial_script_exists,
        "script_is_partial": script_is_partial,
        "cut_count": (
            len((visible_script or {}).get("cuts") or [])
            if isinstance(visible_script, dict) and isinstance((visible_script or {}).get("cuts"), list)
            else _script_text_line_count(visible_script) if isinstance(visible_script, dict) else 0
        ),
        "path": str(_draft_dir(draft_id)) if draft_id else "",
    }


def _draft_has_live_job(meta: dict) -> bool:
    draft_id = str(meta.get("id") or "")
    if not draft_id:
        return False
    task = _RUNNING_JOBS.get(draft_id)
    return bool(task and not task.done())


def _reconcile_stale_running_job(meta: dict) -> dict:
    draft_id = str(meta.get("id") or "")
    if not draft_id:
        return meta
    progress = meta.get("generation_progress") if isinstance(meta.get("generation_progress"), dict) else {}
    stage = str(meta.get("active_stage") or progress.get("stage") or "")
    is_running = (
        progress.get("status") == "running"
        or meta.get("story_status") == "running"
        or meta.get("script_status") == "running"
    )
    if not is_running or _draft_has_live_job(meta):
        return meta
    active_pid = meta.get("active_job_pid")
    if active_pid:
        try:
            active_pid_value = int(active_pid or 0)
        except (TypeError, ValueError):
            active_pid_value = 0
        if active_pid_value != os.getpid() and _process_exists(active_pid_value):
            return meta
    else:
        last_update = progress.get("updated_at") or meta.get("updated_at")
        if _elapsed_seconds(last_update) < 1800:
            return meta
    job_id = str(meta.get("active_job_id") or progress.get("job_id") or "")
    if stage not in {"story", "script", "validate", "apply"}:
        stage = "script" if meta.get("script_status") == "running" else "story"
    _mark_job_cancelled(
        draft_id,
        stage,
        job_id or None,
        "서버에 실행 중인 작업이 없어 중단됨으로 정리됨",
    )
    try:
        return _load_meta(draft_id)
    except Exception:
        return meta


def _draft_rank(meta: dict) -> tuple[int, str]:
    meta = _reconcile_stale_running_job(meta)
    draft_id = str(meta.get("id") or "")
    if _draft_has_live_job(meta):
        score = 1000
    elif _script_path(draft_id).exists():
        score = 800
    elif meta.get("status") in {"script_ready", "needs_review"}:
        score = 750
    elif _story_path(draft_id).exists() or meta.get("story_status") == "completed":
        score = 600
    elif meta.get("story_status") == "running" or meta.get("script_status") == "running":
        score = 400
    elif meta.get("status") == "failed" or meta.get("story_status") == "failed" or meta.get("script_status") == "failed":
        score = 100
    else:
        score = 200
    return score, str(meta.get("updated_at") or "")


def _dedupe_draft_rows(rows: list[dict]) -> list[dict]:
    chosen: dict[str, dict] = {}
    for meta in rows:
        queue_item_id = str(meta.get("source_queue_item_id") or "").strip()
        key = f"queue:{queue_item_id}" if queue_item_id else f"draft:{meta.get('id')}"
        current = chosen.get(key)
        if current is None or _draft_rank(meta) > _draft_rank(current):
            chosen[key] = meta
    return list(chosen.values())


def _find_existing_queue_draft_id(queue_item_id: str) -> str:
    needle = str(queue_item_id or "").strip()
    if not needle or not DRAFTS_ROOT.exists():
        return ""
    matches: list[dict] = []
    for path in DRAFTS_ROOT.glob("*/draft.json"):
        meta = _json_read(path)
        if isinstance(meta, dict) and str(meta.get("source_queue_item_id") or "").strip() == needle:
            matches.append(_reconcile_stale_running_job(meta))
    if not matches:
        return ""
    matches.sort(key=_draft_rank, reverse=True)
    return str(matches[0].get("id") or "")


def _load_meta(draft_id: str) -> dict:
    meta = _json_read(_meta_path(draft_id))
    if not isinstance(meta, dict):
        raise FileNotFoundError(f"Script Studio draft not found: {draft_id}")
    return meta


def _save_meta(meta: dict) -> dict:
    meta = dict(meta)
    meta["updated_at"] = _now_iso()
    _json_write(_meta_path(meta["id"]), meta)
    return meta


def _is_active_job(meta: dict, job_id: str | None) -> bool:
    if not job_id:
        return True
    return str(meta.get("active_job_id") or "") == str(job_id) and not meta.get("cancel_requested_at")


def _raise_if_job_cancelled(draft_id: str, job_id: str | None) -> None:
    if not job_id:
        return
    meta = _load_meta(draft_id)
    if not _is_active_job(meta, job_id):
        raise asyncio.CancelledError("Script Studio job cancelled")


def _mark_job_started(draft_id: str, *, stage: str, job_id: str) -> dict:
    meta = _load_meta(draft_id)
    meta["active_job_id"] = job_id
    meta["active_stage"] = stage
    meta["active_job_started_at"] = _now_iso()
    meta["active_job_pid"] = os.getpid()
    meta["cancel_requested_at"] = None
    meta["last_error"] = ""
    _save_meta(meta)
    return meta


def _clear_active_job(meta: dict, job_id: str | None) -> dict:
    if not job_id:
        return meta
    if str(meta.get("active_job_id") or "") != str(job_id):
        return meta
    meta.pop("active_job_id", None)
    meta.pop("active_stage", None)
    meta.pop("active_job_started_at", None)
    meta.pop("active_job_pid", None)
    meta.pop("cancel_requested_at", None)
    return meta


def _set_generation_progress(
    draft_id: str,
    *,
    stage: str,
    status: str,
    completed: int,
    total: int,
    message: str,
    model: str = "",
    job_id: str | None = None,
    block_event: dict | None = None,
) -> None:
    try:
        meta = _load_meta(draft_id)
    except Exception:
        return
    if job_id and not _is_active_job(meta, job_id):
        return
    total = max(0, int(total or 0))
    completed = max(0, min(int(completed or 0), total if total else int(completed or 0)))
    progress_pct = round((completed / total) * 100, 1) if total else 0.0
    previous = meta.get("generation_progress") if isinstance(meta.get("generation_progress"), dict) else {}
    current_job_id = str(job_id or meta.get("active_job_id") or "")
    if str(previous.get("job_id") or "") == current_job_id and previous.get("started_at"):
        started_at = str(previous.get("started_at"))
    else:
        started_at = str(meta.get("active_job_started_at") or _now_iso())
    block_progress = previous.get("block_progress") if isinstance(previous.get("block_progress"), dict) else {}
    if isinstance(block_event, dict):
        if block_event.get("reset"):
            block_progress = {
                "total_blocks": int(block_event.get("total_blocks") or total or 0),
                "current_block": 0,
                "blocks": {},
            }
        blocks = block_progress.get("blocks") if isinstance(block_progress.get("blocks"), dict) else {}
        block_index = block_event.get("block_index")
        try:
            block_index_int = int(block_index or 0)
        except (TypeError, ValueError):
            block_index_int = 0
        if block_index_int > 0:
            key = str(block_index_int)
            current = blocks.get(key) if isinstance(blocks.get(key), dict) else {}
            current.update({
                "block_index": block_index_int,
                "cut_range": str(block_event.get("cut_range") or current.get("cut_range") or ""),
                "generation_status": str(block_event.get("generation_status") or current.get("generation_status") or "pending"),
                "validation_status": str(block_event.get("validation_status") or current.get("validation_status") or "pending"),
                "generation_model": str(_strip_ollama_prefix(block_event.get("generation_model") or current.get("generation_model") or "") or ""),
                "validation_model": str(_strip_ollama_prefix(block_event.get("validation_model") or current.get("validation_model") or "") or ""),
                "generation_failures": int(block_event.get("generation_failures") if block_event.get("generation_failures") is not None else current.get("generation_failures") or 0),
                "validation_failures": int(block_event.get("validation_failures") if block_event.get("validation_failures") is not None else current.get("validation_failures") or 0),
                "fallback_used": bool(block_event.get("fallback_used") if block_event.get("fallback_used") is not None else current.get("fallback_used") or False),
                "message": str(block_event.get("message") or current.get("message") or ""),
                "updated_at": _now_iso(),
            })
            blocks[key] = current
            block_progress["blocks"] = blocks
            block_progress["current_block"] = block_index_int
        if block_event.get("total_blocks") is not None:
            try:
                block_progress["total_blocks"] = int(block_event.get("total_blocks") or 0)
            except (TypeError, ValueError):
                pass

    progress_payload = {
        "stage": stage,
        "status": status,
        "completed": completed,
        "total": total,
        "progress_pct": progress_pct,
        "message": str(message or "").strip(),
        "model": str(_strip_ollama_prefix(model) or "").strip(),
        "job_id": current_job_id,
        "started_at": started_at,
        "elapsed_seconds": _elapsed_seconds(started_at),
        "updated_at": _now_iso(),
    }
    if block_progress:
        progress_payload["block_progress"] = block_progress
    meta["generation_progress"] = progress_payload
    _save_meta(meta)


def _script_progress_callback(draft_id: str, job_id: str | None = None):
    def _callback(event: dict) -> None:
        if not isinstance(event, dict):
            return
        _raise_if_job_cancelled(draft_id, job_id)
        _set_generation_progress(
            draft_id,
            stage=str(event.get("stage") or "script"),
            status=str(event.get("status") or "running"),
            completed=int(event.get("completed") or 0),
            total=int(event.get("total") or 0),
            message=str(event.get("message") or ""),
            model=str(event.get("model") or ""),
            job_id=job_id,
            block_event=event.get("block") if isinstance(event.get("block"), dict) else None,
        )

    return _callback


def list_drafts() -> list[dict]:
    DRAFTS_ROOT.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for path in DRAFTS_ROOT.glob("*/draft.json"):
        meta = _json_read(path)
        if isinstance(meta, dict):
            meta = _reconcile_stale_running_job(meta)
            rows.append(_draft_summary(meta))
    rows = _dedupe_draft_rows(rows)
    rows.sort(key=lambda x: str(x.get("updated_at") or ""), reverse=True)
    return rows


def get_draft(draft_id: str) -> dict:
    meta = _reconcile_stale_running_job(_load_meta(draft_id))
    story_plan = _json_read(_story_path(draft_id))
    script = _json_read(_script_path(draft_id))
    script_is_partial = False
    if not isinstance(script, dict):
        partial_script = _json_read(_partial_script_path(draft_id))
        if (
            isinstance(partial_script, dict)
            and (
                (isinstance(partial_script.get("cuts"), list) and bool(partial_script.get("cuts")))
                or _script_has_text_blocks(partial_script)
            )
        ):
            script = partial_script
            script_is_partial = True
    validation = _json_read(_validation_path(draft_id))
    return {
        **_draft_summary(meta),
        "story_plan": story_plan if isinstance(story_plan, dict) else None,
        "script": script if isinstance(script, dict) else None,
        "script_is_partial": script_is_partial,
        "validation_report": validation if isinstance(validation, dict) else None,
    }


def delete_draft(draft_id: str) -> dict:
    return _soft_delete_draft_dir(draft_id, reason="user_delete")


def list_source_projects(db: Session) -> list[dict]:
    rows = db.query(Project).order_by(Project.updated_at.desc()).all()
    out: list[dict] = []
    for p in rows:
        cfg = p.config or {}
        if cfg.get("__oneclick__"):
            continue
        out.append({
            "id": p.id,
            "title": p.title,
            "topic": p.topic,
            "language": normalize_language_code(cfg.get("language", "ko")),
            "target_cuts": _expected_cut_count(cfg),
            "story_model": _strip_ollama_prefix(cfg.get("story_model") or cfg.get("script_model")),
            "script_model": _strip_ollama_prefix(cfg.get("script_model")),
            "updated_at": str(p.updated_at),
        })
    return out


def _queue_channel(value: Any) -> int:
    try:
        channel = int(value or 1)
    except (TypeError, ValueError):
        channel = 1
    return max(1, channel)


def _resolve_queue_project_id(queue: dict, item: dict) -> str | None:
    """Match the V3 one-click queue preset resolution used by the factory."""
    channel = _queue_channel(item.get("channel"))
    channel_presets = queue.get("channel_presets") if isinstance(queue.get("channel_presets"), dict) else {}
    preset_id = str(channel_presets.get(str(channel)) or "").strip()
    if preset_id:
        return preset_id
    template_id = str(item.get("template_project_id") or "").strip()
    return template_id or None


def _project_label_map(db: Session, project_ids: set[str]) -> dict[str, str]:
    ids = {str(pid).strip() for pid in project_ids if str(pid or "").strip()}
    if not ids:
        return {}
    rows = db.query(Project).filter(Project.id.in_(ids)).all()
    return {str(p.id): p.title for p in rows}


def _queue_item_existing_script(db: Session, item: dict) -> tuple[bool, str]:
    result_dir = str(item.get("result_dir") or "").strip()
    if result_dir:
        path = Path(result_dir) / "script.json"
        if path.exists():
            return True, str(path)

    candidate_ids = [
        str(item.get("project_id") or "").strip(),
        str(item.get("restored_from_project_id") or "").strip(),
    ]
    for project_id in [pid for pid in candidate_ids if pid]:
        project = db.query(Project).filter(Project.id == project_id).first()
        cfg = project.config if project else {}
        try:
            path = resolve_project_dir(project_id, cfg or {}, create=False) / "script.json"
            if path.exists():
                return True, str(path)
        except Exception:
            continue
    return False, ""


def _queue_item_summary(
    db: Session,
    item: dict,
    resolved_project_id: str | None,
    project_titles: dict[str, str],
) -> dict:
    topic = str(item.get("topic") or "").strip()
    title = str(item.get("title") or "").strip()
    has_script, script_path = _queue_item_existing_script(db, item)
    return {
        "id": str(item.get("id") or "").strip(),
        "channel": _queue_channel(item.get("channel")),
        "topic": topic,
        "title": title or topic,
        "episode_number": item.get("episode_number"),
        "status": str(item.get("status") or "pending"),
        "queued_source": str(item.get("queued_source") or ""),
        "queued_note": str(item.get("queued_note") or ""),
        "queued_at": item.get("queued_at"),
        "template_project_id": item.get("template_project_id"),
        "resolved_project_id": resolved_project_id,
        "resolved_project_title": project_titles.get(str(resolved_project_id or ""), ""),
        "target_duration": item.get("target_duration"),
        "target_cuts": item.get("target_cuts"),
        "core_content": str(item.get("core_content") or ""),
        "openings": item.get("openings") if isinstance(item.get("openings"), list) else [],
        "endings": item.get("endings") if isinstance(item.get("endings"), list) else [],
        "next_episode_preview": str(item.get("next_episode_preview") or ""),
        "has_existing_script": has_script,
        "existing_script_path": script_path,
    }


def list_queue_topics(db: Session) -> dict:
    queue = oneclick_service.get_queue()
    items = [dict(item or {}) for item in (queue.get("items") or []) if isinstance(item, dict)]
    resolved_ids = {_resolve_queue_project_id(queue, item) for item in items}
    channel_presets = queue.get("channel_presets") if isinstance(queue.get("channel_presets"), dict) else {}
    resolved_ids.update(str(pid) for pid in channel_presets.values() if pid)
    project_titles = _project_label_map(db, {str(pid) for pid in resolved_ids if pid})

    channel_numbers = {1, 2, 3, 4}
    channel_numbers.update(_queue_channel(item.get("channel")) for item in items)

    grouped: dict[int, list[dict]] = {channel: [] for channel in sorted(channel_numbers)}
    for item in items:
        channel = _queue_channel(item.get("channel"))
        resolved_project_id = _resolve_queue_project_id(queue, item)
        grouped.setdefault(channel, []).append(_queue_item_summary(db, item, resolved_project_id, project_titles))

    channels = []
    for channel in sorted(grouped):
        preset_project_id = str(channel_presets.get(str(channel)) or "").strip() or None
        channels.append({
            "channel": channel,
            "preset_project_id": preset_project_id,
            "preset_project_title": project_titles.get(str(preset_project_id or ""), ""),
            "items": grouped[channel],
        })

    return {
        "channel_times": dict(queue.get("channel_times") or {}),
        "channel_presets": dict(channel_presets or {}),
        "channels": channels,
        "total": len(items),
    }


def create_draft_from_queue_item(
    db: Session,
    item_id: str,
    config_overrides: dict | None = None,
    replace_existing: bool = False,
) -> dict:
    queue = oneclick_service.get_queue()
    needle = str(item_id or "").strip()
    item = next(
        (dict(row or {}) for row in (queue.get("items") or []) if str((row or {}).get("id") or "").strip() == needle),
        None,
    )
    if not item:
        raise ValueError("제작큐 주제를 찾을 수 없습니다.")

    source_project_id = _resolve_queue_project_id(queue, item)
    overrides: dict[str, Any] = {
        "channel": _queue_channel(item.get("channel")),
        "episode_openings": item.get("openings") if isinstance(item.get("openings"), list) else [],
        "episode_endings": item.get("endings") if isinstance(item.get("endings"), list) else [],
        "episode_core_content": str(item.get("core_content") or ""),
        "next_episode_preview": str(item.get("next_episode_preview") or ""),
    }
    if item.get("target_duration") is not None:
        overrides["target_duration"] = item.get("target_duration")
    if item.get("target_cuts") is not None:
        overrides["target_cuts"] = item.get("target_cuts")
    if item.get("episode_number") is not None:
        overrides["episode_number"] = item.get("episode_number")
    if isinstance(config_overrides, dict):
        overrides.update(config_overrides)

    topic = str(item.get("topic") or "").strip()
    title = str(item.get("title") or topic).strip()
    existing_draft_id = _find_existing_queue_draft_id(needle)
    if existing_draft_id:
        if replace_existing:
            _soft_delete_draft_dir(existing_draft_id, reason="queue_replace")
        else:
            meta = _reconcile_stale_running_job(_load_meta(existing_draft_id))
            if not _draft_has_live_job(meta):
                source = db.query(Project).filter(Project.id == source_project_id).first() if source_project_id else None
                meta["source_project_id"] = source.id if source else source_project_id
                meta["source_project_title"] = source.title if source else meta.get("source_project_title", "")
                meta["topic"] = topic or meta.get("topic", "")
                meta["title"] = title or meta.get("title", "")
                meta["config"] = _normalize_config({**dict(meta.get("config") or {}), **overrides})
            meta["source_queue_item_id"] = needle
            meta["source_queue_channel"] = _queue_channel(item.get("channel"))
            meta["source_queue_status"] = str(item.get("status") or "pending")
            _save_meta(meta)
            return get_draft(existing_draft_id)

    draft = create_draft(
        db,
        source_project_id=source_project_id,
        topic=topic,
        title=title,
        config_overrides=overrides,
    )
    meta = _load_meta(draft["id"])
    meta["source_queue_item_id"] = needle
    meta["source_queue_channel"] = _queue_channel(item.get("channel"))
    meta["source_queue_status"] = str(item.get("status") or "pending")
    _save_meta(meta)
    return get_draft(draft["id"])


def create_draft(
    db: Session,
    *,
    source_project_id: str | None,
    topic: str | None,
    title: str | None,
    config_overrides: dict | None = None,
) -> dict:
    source = None
    base_config: dict = {}
    if source_project_id:
        source = db.query(Project).filter(Project.id == source_project_id).first()
        if not source:
            raise ValueError("연결할 롱폼공장 프로젝트를 찾을 수 없습니다.")
        base_config = dict(source.config or {})
    cfg = _normalize_config({**base_config, **(config_overrides or {})})
    draft_id = _safe_id()
    meta = {
        "id": draft_id,
        "source_project_id": source.id if source else None,
        "source_project_title": source.title if source else "",
        "title": (title or (source.title if source else "") or topic or "대본 초안").strip(),
        "topic": (topic or (source.topic if source else "") or "").strip(),
        "config": cfg,
        "status": "draft",
        "story_status": "empty",
        "script_status": "empty",
        "last_error": "",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    if not meta["topic"]:
        raise ValueError("주제가 비어 있습니다.")
    _save_meta(meta)
    return get_draft(draft_id)


def update_draft(draft_id: str, patch: dict) -> dict:
    meta = _load_meta(draft_id)
    for key in ("title", "topic"):
        if key in patch and patch[key] is not None:
            meta[key] = str(patch[key]).strip()
    if isinstance(patch.get("config"), dict):
        meta["config"] = _normalize_config({**(meta.get("config") or {}), **patch["config"]})
    _save_meta(meta)
    return get_draft(draft_id)


async def list_script_studio_models() -> list[dict]:
    models = [dict(m) for m in list_llm_models()]
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(3.0, connect=1.5)) as client:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            response.raise_for_status()
            for item in (response.json().get("models") or []):
                name = str(item.get("name") or item.get("model") or "").strip()
                if not name:
                    continue
                models.append({
                    "id": name,
                    "name": name,
                    "provider": "ollama",
                    "description": "로컬 모델",
                    "cost_per_unit": "local",
                    "cost_input": 0.0,
                    "cost_output": 0.0,
                    "available": True,
                })
    except Exception:
        pass
    return models


def _llm_service(model_id: str):
    value = str(model_id or "").strip()
    if value.startswith("ollama:"):
        return OllamaService(value)
    if value in {item["id"] for item in list_llm_models()}:
        assert_llm_provider_key(value)
        return get_llm_service(value)
    return OllamaService(value)


def _set_error(meta: dict, status_key: str, exc: Exception, job_id: str | None = None) -> None:
    try:
        latest = _load_meta(str(meta.get("id") or ""))
        latest.update({k: v for k, v in meta.items() if k in {"id", "story_plan"}})
        meta = latest
    except Exception:
        pass
    if job_id and not _is_active_job(meta, job_id):
        return
    meta.pop("story_plan", None)
    meta[status_key] = "failed"
    meta["status"] = "failed"
    meta["last_error"] = humanize_generation_error(exc)
    progress = meta.get("generation_progress") if isinstance(meta.get("generation_progress"), dict) else {}
    if progress:
        started_at = progress.get("started_at") or meta.get("active_job_started_at") or progress.get("updated_at") or _now_iso()
        finished_at = _now_iso()
        progress["status"] = "failed"
        progress["message"] = meta["last_error"]
        progress["started_at"] = started_at
        progress["finished_at"] = finished_at
        progress["elapsed_seconds"] = _elapsed_seconds(started_at, finished_at)
        progress["updated_at"] = finished_at
        meta["generation_progress"] = progress
    stage = "story" if status_key == "story_status" else "script" if status_key == "script_status" else ""
    if stage:
        meta = _append_job_history(
            meta,
            stage=stage,
            status="failed",
            job_id=job_id,
            message=meta["last_error"],
        )
    meta = _clear_active_job(meta, job_id)
    _save_meta(meta)


def humanize_generation_error(exc: Exception) -> str:
    text = str(exc or "").strip()
    if "invalid shorts candidate count" in text or "invalid shorts group" in text:
        return "쇼츠 후보 구간이 기준과 맞지 않습니다. 15컷짜리 쇼츠 그룹은 최소 3개, 목표 4개가 필요합니다."
    if "story plan topic alignment failed" in text:
        return f"스토리 설계가 입력 주제에서 벗어났습니다. 주제의 핵심 명칭이 스토리에 반영되지 않았습니다. 원문 오류: {text}"
    if "story plan validation failed" in text:
        return f"스토리 설계가 기준과 맞지 않습니다. 150컷 기준 10컷 씬 블록 15개와 필수 필드가 필요합니다. 원문 오류: {text}"
    if "scene_block" in text:
        return f"10컷 씬 블록 대본 생성이 기준과 맞지 않습니다. 컷 범위, 컷 수, 또는 블록 필드가 어긋났습니다. 원문 오류: {text}"
    if "returned" in text and "cuts, expected" in text:
        return f"컷 수가 설정과 다릅니다. 원문 오류: {text}"
    if "not valid JSON" in text or "JSON" in text:
        return f"모델 응답이 올바른 JSON이 아닙니다. 원문 오류: {text}"
    if "API_KEY" in text:
        return f"API 키가 설정되지 않았습니다. 원문 오류: {text}"
    if "Ollama" in text or "Connection" in text or "ConnectError" in text:
        return f"Ollama 로컬 모델 호출에 실패했습니다. Ollama 실행 상태와 모델 설치를 확인해야 합니다. 원문 오류: {text}"
    return text or exc.__class__.__name__


async def generate_story_for_draft(draft_id: str, job_id: str | None = None) -> dict:
    meta = _load_meta(draft_id)
    _raise_if_job_cancelled(draft_id, job_id)
    meta["story_status"] = "running"
    meta["last_error"] = ""
    _save_meta(meta)
    cfg = _runtime_config(meta)
    model_id = str(cfg.get("story_model") or cfg.get("script_model") or "claude-sonnet-4-6")
    cfg["story_model"] = model_id
    _set_generation_progress(
        draft_id,
        stage="story",
        status="running",
        completed=0,
        total=1,
        message="스토리 설계 요청 중",
        model=model_id,
        job_id=job_id,
    )
    try:
        service = _llm_service(model_id)
        story_plan = await service.generate_story_plan(meta["topic"], cfg)
        _raise_if_job_cancelled(draft_id, job_id)
        _json_write(_story_path(draft_id), story_plan)
        meta = _load_meta(draft_id)
        if not _is_active_job(meta, job_id):
            raise asyncio.CancelledError("Script Studio story job cancelled")
        meta["story_status"] = "completed"
        meta["status"] = "story_ready"
        meta["config"] = _normalize_config(cfg)
        meta["config"].pop("__project_id", None)
        meta["config"].pop("result_dir", None)
        meta["last_error"] = ""
        current_progress = meta.get("generation_progress") if isinstance(meta.get("generation_progress"), dict) else {}
        started_at = current_progress.get("started_at") or meta.get("active_job_started_at") or _now_iso()
        finished_at = _now_iso()
        meta["generation_progress"] = {
            "stage": "story",
            "status": "completed",
            "completed": 1,
            "total": 1,
            "progress_pct": 100.0,
            "message": "스토리 설계 완료",
            "model": model_id,
            "job_id": str(job_id or meta.get("active_job_id") or ""),
            "started_at": started_at,
            "finished_at": finished_at,
            "elapsed_seconds": _elapsed_seconds(started_at, finished_at),
            "updated_at": finished_at,
        }
        meta = _append_job_history(
            meta,
            stage="story",
            status="completed",
            job_id=job_id,
            model=model_id,
            message="스토리 설계 완료",
        )
        meta = _clear_active_job(meta, job_id)
        _save_meta(meta)
        return get_draft(draft_id)
    except Exception as exc:
        _set_error(meta, "story_status", exc, job_id=job_id)
        raise


def _strip_shorts_metadata(script: dict) -> dict:
    for cut in script.get("cuts", []) or []:
        if not isinstance(cut, dict):
            continue
        cut["shorts_candidate"] = False
        for key in ("shorts_group", "shorts_reason", "shorts_score", "shorts_title"):
            cut.pop(key, None)
    return script


def _finalize_script_for_draft(script: dict, meta: dict, cfg: dict, *, include_shorts: bool = False) -> dict:
    script = apply_script_visual_policy(script)
    script = annotate_script_shorts(script) if include_shorts else _strip_shorts_metadata(script)
    BaseLLMService.assert_script_timing(script, cfg)
    script["title"] = script_title_for_language(
        generated_title=script.get("title"),
        project_title=meta.get("title") or "",
        topic=meta.get("topic") or "",
        episode_number=cfg.get("episode_number"),
        language=cfg.get("language", "ko"),
    )
    for key in ("partial", "completed_scene_blocks", "total_scene_blocks"):
        script.pop(key, None)
    for cut in script.get("cuts", []) or []:
        if isinstance(cut, dict):
            cut.pop("motion_prompt", None)
            cut.pop("video_motion_prompt", None)
    return script


def _normalize_script_mode(mode: str | None) -> str:
    value = str(mode or "new").strip().lower()
    if value in {"resume", "continue"}:
        return "resume"
    if value in {"block", "regenerate_block", "block_regenerate"}:
        return "block"
    return "new"


async def generate_script_for_draft(
    draft_id: str,
    job_id: str | None = None,
    mode: str | None = None,
    block_index: int | None = None,
) -> dict:
    meta = _load_meta(draft_id)
    _raise_if_job_cancelled(draft_id, job_id)
    script_mode = _normalize_script_mode(mode)
    story_plan = _json_read(_story_path(draft_id))
    if isinstance(story_plan, dict):
        meta["story_plan"] = story_plan
    meta["script_status"] = "running"
    meta["last_error"] = ""
    _save_meta(meta)
    cfg = _runtime_config(meta)
    cfg["script_generation_mode"] = script_mode
    if script_mode == "new":
        for path in (_partial_script_path(draft_id), _script_path(draft_id), _validation_path(draft_id)):
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
    elif script_mode == "resume":
        partial_script = _json_read(_partial_script_path(draft_id))
        if isinstance(partial_script, dict):
            cfg["script_resume_partial"] = partial_script
    elif script_mode == "block":
        try:
            target_block_index = int(block_index or 0)
        except (TypeError, ValueError):
            target_block_index = 0
        if target_block_index <= 0:
            raise ValueError("재생성할 블럭 번호가 없습니다.")
        existing_script = _json_read(_script_path(draft_id))
        if not isinstance(existing_script, dict):
            existing_script = _json_read(_partial_script_path(draft_id))
        if not isinstance(existing_script, dict) or (not isinstance(existing_script.get("cuts"), list) and not _script_has_text_blocks(existing_script)):
            raise ValueError("재생성할 기존 대본 결과가 없습니다.")
        cfg["script_had_final_script"] = _script_path(draft_id).exists()
        cfg["script_regenerate_block_index"] = target_block_index
        cfg["script_existing_script"] = existing_script
        try:
            _validation_path(draft_id).unlink(missing_ok=True)
        except Exception:
            pass
    model_id = str(cfg.get("script_model") or "claude-sonnet-4-6")
    cfg["script_progress_callback"] = _script_progress_callback(draft_id, job_id)
    cfg["script_cancel_checker"] = lambda: _raise_if_job_cancelled(draft_id, job_id)
    ready_message = {
        "resume": "대본 이어서 생성 준비 중",
        "block": f"블럭 {cfg.get('script_regenerate_block_index')} 재생성 준비 중",
        "new": "새 대본 생성 준비 중",
    }.get(script_mode, "대본 생성 준비 중")
    _set_generation_progress(
        draft_id,
        stage="script",
        status="running",
        completed=0,
        total=0,
        message=ready_message,
        model=model_id,
        job_id=job_id,
    )
    try:
        try:
            await ensure_voice_profile_from_config(cfg, log=print)
        except Exception as profile_error:
            print(f"[script-studio] voice profile warning: {profile_error}")
        _raise_if_job_cancelled(draft_id, job_id)
        service = _llm_service(model_id)
        script = await service.generate_script(meta["topic"], cfg)
        _raise_if_job_cancelled(draft_id, job_id)
        if _script_has_text_blocks(script):
            partial_script = _deepcopy_jsonable(script)
            if not isinstance(partial_script, dict):
                partial_script = dict(script)
            partial_script["partial"] = True
            partial_script["text_only"] = True
            expected_cuts = _expected_cut_count(cfg)
            completed_blocks = len(_script_text_blocks(partial_script))
            partial_script["completed_scene_blocks"] = completed_blocks
            partial_script["total_scene_blocks"] = math.ceil(expected_cuts / 10)
        else:
            script = _finalize_script_for_draft(script, meta, cfg, include_shorts=False)
            partial_script = dict(script)
            cuts = partial_script.get("cuts") if isinstance(partial_script.get("cuts"), list) else []
            expected_cuts = _expected_cut_count(cfg)
            if len(cuts) < expected_cuts:
                partial_script["completed_scene_blocks"] = len(cuts) // 10
                partial_script["total_scene_blocks"] = math.ceil(expected_cuts / 10)
        partial_script["partial"] = True
        _json_write(_partial_script_path(draft_id), partial_script)
        if script_mode == "block" and cfg.get("script_had_final_script") and not _script_has_text_blocks(partial_script):
            _json_write(_script_path(draft_id), script)
        meta = _load_meta(draft_id)
        if not _is_active_job(meta, job_id):
            raise asyncio.CancelledError("Script Studio script job cancelled")
        meta.pop("story_plan", None)
        meta["script_status"] = "completed"
        meta["status"] = "script_partial_ready"
        meta["last_error"] = ""
        current_progress = meta.get("generation_progress") if isinstance(meta.get("generation_progress"), dict) else {}
        total = int(current_progress.get("total") or 1)
        started_at = current_progress.get("started_at") or meta.get("active_job_started_at") or _now_iso()
        finished_at = _now_iso()
        meta["generation_progress"] = {
            "stage": "script",
            "status": "completed",
            "completed": total,
            "total": total,
            "progress_pct": 100.0,
            "message": "대본 생성 완료, 1차 검사 대기",
            "model": model_id,
            "job_id": str(job_id or meta.get("active_job_id") or ""),
            "started_at": started_at,
            "finished_at": finished_at,
            "elapsed_seconds": _elapsed_seconds(started_at, finished_at),
            "updated_at": finished_at,
        }
        meta = _append_job_history(
            meta,
            stage="script",
            status="completed",
            job_id=job_id,
            model=model_id,
            message=str(meta["generation_progress"]["message"]),
        )
        meta = _clear_active_job(meta, job_id)
        _save_meta(meta)
        return get_draft(draft_id)
    except Exception as exc:
        _set_error(meta, "script_status", exc, job_id=job_id)
        raise


def validate_script(script: dict | None, config: dict | None) -> dict:
    issues: list[dict] = []
    cfg = _normalize_config(config or {})
    expected = _expected_cut_count(cfg)
    if not isinstance(script, dict):
        return {"ok": False, "issues": [{"level": "error", "message": "script가 JSON 객체가 아닙니다."}]}
    cuts = script.get("cuts")
    if not isinstance(cuts, list):
        issues.append({"level": "error", "message": "cuts 배열이 없습니다."})
        cuts = []
    if len(cuts) != expected:
        issues.append({"level": "error", "message": f"컷 수가 설정과 다릅니다. 현재 {len(cuts)}컷, 설정 {expected}컷입니다."})
    for idx, cut in enumerate(cuts, start=1):
        if not isinstance(cut, dict):
            issues.append({"level": "error", "cut_number": idx, "message": "컷 항목이 객체가 아닙니다."})
            continue
        if cut.get("cut_number") != idx:
            issues.append({"level": "error", "cut_number": idx, "message": f"cut_number가 연속되지 않습니다. 현재 값: {cut.get('cut_number')}"})
        if not str(cut.get("narration") or "").strip():
            issues.append({"level": "error", "cut_number": idx, "message": "내레이션이 비어 있습니다."})
        for field in ("visual_year", "visual_period", "visual_location", "visual_evidence", "visual_subject", "visual_scene"):
            if not str(cut.get(field) or "").strip():
                issues.append({"level": "warn", "cut_number": idx, "message": f"{field}가 비어 있습니다."})
    try:
        timing_issues = BaseLLMService.validate_script_timing(script, cfg)
        for item in timing_issues[:40]:
            issues.append({
                "level": "warn",
                "cut_number": item.get("cut_number"),
                "message": f"내레이션 길이 확인 필요: {item.get('amount')}{item.get('unit')} / 목표 {item.get('target_range')}",
            })
        if len(timing_issues) > 40:
            issues.append({"level": "warn", "message": f"내레이션 길이 이슈가 추가로 {len(timing_issues) - 40}개 있습니다."})
    except Exception as exc:
        issues.append({"level": "warn", "message": f"내레이션 길이 검사를 완료하지 못했습니다: {exc}"})
    try:
        assert_script_quality(script, str(script.get("title") or ""))
    except Exception as exc:
        issues.append({"level": "error", "message": humanize_generation_error(exc)})
    return {
        "ok": not any(issue.get("level") == "error" for issue in issues),
        "issue_count": len(issues),
        "issues": issues,
        "checked_at": _now_iso(),
    }


def _json_read_with_error(path: Path, default: Any = None) -> tuple[Any, str]:
    if not path.exists():
        return default, ""
    try:
        return json.loads(path.read_text(encoding="utf-8")), ""
    except Exception as exc:
        return default, f"{type(exc).__name__}: {exc}"


def _deepcopy_jsonable(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False))
    except Exception:
        return value


def _narration_words(text: str) -> set[str]:
    words = {
        word.lower()
        for word in re.findall(r"[A-Za-z0-9가-힣]{2,}", str(text or ""))
        if len(word.strip()) >= 2
    }
    return {word for word in words if word not in COMMON_REPEAT_WORDS}


def _sentence_ending(text: str) -> str:
    value = re.sub(r"\s+", " ", str(text or "").strip())
    value = re.sub(r"[\"'“”‘’\]\)]*$", "", value)
    value = re.sub(r"[.!?。！？…]+$", "", value).strip()
    endings = (
        "었습니다",
        "했습니다",
        "였습니다",
        "입니다",
        "습니다",
        "는데요",
        "거든요",
        "였어요",
        "했어요",
        "어요",
        "였죠",
        "했죠",
        "이죠",
        "고요",
        "니다",
        "죠",
        "요",
        "다",
    )
    for ending in endings:
        if value.endswith(ending):
            return ending
    tail = value.split(" ")[-1] if value else ""
    return tail[-4:] if len(tail) > 4 else tail


def _ending_group(ending: str) -> str:
    ending = str(ending or "")
    if ending in {"죠", "했죠", "였죠", "이죠"}:
        return "죠"
    if ending in {"요", "어요", "했어요", "였어요", "는데요", "거든요", "고요"}:
        return "요"
    if ending in {"습니다", "입니다", "했습니다", "였습니다", "었습니다", "니다"}:
        return "습니다"
    return ending


def _configured_forbidden_terms(config: dict) -> list[str]:
    raw = str(config.get("content_forbidden") or config.get("content_constraints") or "")
    terms = [term.strip(" -•·\t") for term in re.split(r"[\n,/·]+", raw) if term.strip(" -•·\t")]
    return [*SCRIPT_FORBIDDEN_TERMS, *terms]


def _script_text_blocks(script: dict | None) -> list[dict]:
    if not isinstance(script, dict):
        return []
    blocks = script.get("script_text_blocks")
    return [block for block in blocks if isinstance(block, dict)] if isinstance(blocks, list) else []


def _script_text_line_count(script: dict | None) -> int:
    total = 0
    for block in _script_text_blocks(script):
        lines = block.get("lines")
        if isinstance(lines, list):
            total += len([line for line in lines if isinstance(line, dict)])
    return total


def _script_has_final_cuts(script: dict | None) -> bool:
    return isinstance(script, dict) and isinstance(script.get("cuts"), list) and bool(script.get("cuts"))


def _script_has_text_blocks(script: dict | None) -> bool:
    return bool(_script_text_blocks(script))


def _normalize_shorts_candidate(value: Any) -> tuple[bool, bool]:
    if isinstance(value, bool):
        return value, False
    if value is None:
        return False, True
    if isinstance(value, (int, float)):
        return bool(value), True
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True, True
        if lowered in {"0", "false", "no", "n", "off", ""}:
            return False, True
    return False, True


def _finalized_script_copy(script: dict, meta: dict, cfg: dict, *, include_shorts: bool = False) -> dict:
    copy = _deepcopy_jsonable(script)
    return _finalize_script_for_draft(copy if isinstance(copy, dict) else {}, meta, cfg, include_shorts=include_shorts)


def _python_mechanical_fix_script(
    script: dict | None,
    config: dict,
    *,
    parse_error: str = "",
) -> tuple[dict | None, dict, int]:
    issues: list[dict] = []
    patches: list[dict] = []
    changed = 0
    cfg = _normalize_config(config or {})
    expected = _expected_cut_count(cfg)
    if parse_error:
        issues.append({"level": "error", "cut_number": None, "category": "json", "message": f"JSON 파싱 오류: {parse_error}"})
    if not isinstance(script, dict):
        issues.append({"level": "error", "cut_number": None, "category": "json", "message": "script가 JSON 객체가 아닙니다."})
        return script, {
            "stage": "local",
            "model": "python",
            "passed": False,
            "score": 0,
            "summary": "Python 기계 검수에서 JSON 구조 오류가 발견되었습니다.",
            "issues": issues,
            "fix_plan": [],
            "patches": patches,
            "patch_count": 0,
            "applied_patch_count": 0,
            "checked_at": _now_iso(),
        }, changed

    revised = _deepcopy_jsonable(script)
    if not isinstance(revised, dict):
        revised = dict(script)
    cuts = revised.get("cuts")
    if not isinstance(cuts, list):
        if _script_has_text_blocks(revised):
            line_count = _script_text_line_count(revised)
            if line_count != expected:
                issues.append({
                    "level": "error",
                    "cut_number": None,
                    "category": "text_blocks",
                    "message": f"블럭 텍스트 컷 수가 설정과 다릅니다. 현재 {line_count}컷, 설정 {expected}컷입니다.",
                })
            for block in _script_text_blocks(revised):
                block_id = int(block.get("block_id") or 0)
                lines = block.get("lines") if isinstance(block.get("lines"), list) else []
                if len(lines) != 10:
                    issues.append({
                        "level": "error",
                        "cut_number": None,
                        "block_id": block_id,
                        "category": "text_blocks",
                        "message": f"Block {block_id}: 블럭 텍스트가 10컷이 아닙니다. 현재 {len(lines)}컷입니다.",
                    })
                for line in lines:
                    if not isinstance(line, dict):
                        continue
                    if not str(line.get("narration") or "").strip():
                        issues.append({"level": "error", "cut_number": line.get("cut_number"), "block_id": block_id, "category": "narration", "message": "대사가 비어 있습니다."})
                    if not str(line.get("visual_scene") or "").strip():
                        issues.append({"level": "error", "cut_number": line.get("cut_number"), "block_id": block_id, "category": "visual_scene", "message": "이미지 프롬프트가 비어 있습니다."})
            passed = not any(issue.get("level") == "error" for issue in issues)
            return revised, {
                "stage": "local",
                "model": "python",
                "passed": passed,
                "score": 10 if passed and not issues else 7 if passed else 0,
                "summary": "Python 블럭 텍스트 구조 검수 통과" if passed else "Python 블럭 텍스트 구조 오류가 발견되었습니다.",
                "issues": issues,
                "fix_plan": [
                    {"cut_number": issue.get("cut_number"), "block_id": issue.get("block_id"), "instruction": issue.get("message")}
                    for issue in issues
                ][:80],
                "patches": patches,
                "patch_count": 0,
                "applied_patch_count": 0,
                "checked_at": _now_iso(),
            }, changed
        issues.append({"level": "error", "cut_number": None, "category": "cuts", "message": "cuts 배열이 없습니다."})
        return revised, {
            "stage": "local",
            "model": "python",
            "passed": False,
            "score": 0,
            "summary": "Python 기계 검수에서 cuts 배열 오류가 발견되었습니다.",
            "issues": issues,
            "fix_plan": [],
            "patches": patches,
            "patch_count": 0,
            "applied_patch_count": 0,
            "checked_at": _now_iso(),
        }, changed

    if len(cuts) != expected:
        issues.append({
            "level": "error",
            "cut_number": None,
            "category": "cut_count",
            "message": f"cut_number 1~{expected} 구성 실패: 현재 {len(cuts)}컷입니다.",
        })
    elif any(not isinstance(cut, dict) or cut.get("cut_number") != idx for idx, cut in enumerate(cuts, start=1)):
        for idx, cut in enumerate(cuts, start=1):
            if isinstance(cut, dict) and cut.get("cut_number") != idx:
                old = cut.get("cut_number")
                cut["cut_number"] = idx
                changed += 1
                patches.append({"cut_number": idx, "fields": {"cut_number": idx}, "reason": f"cut_number 연속성 보정: {old} -> {idx}"})
        issues.append({"level": "warn", "cut_number": None, "category": "cut_number", "message": "cut_number를 1부터 연속되도록 보정했습니다."})

    for idx, cut in enumerate(cuts, start=1):
        if not isinstance(cut, dict):
            issues.append({"level": "error", "cut_number": idx, "category": "cuts", "message": "컷 항목이 객체가 아닙니다."})
            continue
        narration = str(cut.get("narration") or "").strip()
        if not narration:
            issues.append({"level": "error", "cut_number": idx, "category": "narration", "message": "narration이 비어 있습니다."})
        if str(cut.get("image_prompt") or "") != "":
            cut["image_prompt"] = ""
            changed += 1
            patches.append({"cut_number": idx, "fields": {"image_prompt": ""}, "reason": "LLM 검수 입력용 image_prompt를 빈 문자열로 정리"})
        for field in ("visual_year", "visual_period", "visual_location"):
            if not str(cut.get(field) or "").strip():
                issues.append({"level": "error", "cut_number": idx, "category": field, "message": f"{field}가 비어 있습니다."})
        for field in ("visual_evidence", "visual_subject", "visual_scene"):
            if not str(cut.get(field) or "").strip():
                issues.append({"level": "warn", "cut_number": idx, "category": field, "message": f"{field}가 비어 있습니다."})
        had_shorts_metadata = (
            cut.get("shorts_candidate") is not False
            or any(key in cut for key in ("shorts_group", "shorts_reason", "shorts_score", "shorts_title"))
        )
        cut["shorts_candidate"] = False
        for key in ("shorts_group", "shorts_reason", "shorts_score", "shorts_title"):
            cut.pop(key, None)
        if had_shorts_metadata:
            changed += 1
            patches.append({"cut_number": idx, "fields": {"shorts_candidate": False}, "reason": "1차 검수 전 쇼츠 후보 메타데이터 제거"})
        for term in _configured_forbidden_terms(cfg):
            if term and term in narration:
                issues.append({"level": "error", "cut_number": idx, "category": "forbidden", "message": f"금지어 사용: {term}"})

    try:
        timing_issues = BaseLLMService.validate_script_timing(revised, cfg)
        for item in timing_issues[:80]:
            issues.append({
                "level": "warn",
                "cut_number": item.get("cut_number"),
                "category": "timing",
                "message": f"글자 수/TTS 범위 이탈: {item.get('amount')}{item.get('unit')} / 목표 {item.get('target_range')}",
            })
        if len(timing_issues) > 80:
            issues.append({"level": "warn", "cut_number": None, "category": "timing", "message": f"글자 수/TTS 범위 이슈가 추가로 {len(timing_issues) - 80}개 있습니다."})
    except Exception as exc:
        issues.append({"level": "warn", "cut_number": None, "category": "timing", "message": f"글자 수/TTS 검사를 완료하지 못했습니다: {exc}"})

    word_sets = [_narration_words(cut.get("narration") if isinstance(cut, dict) else "") for cut in cuts]
    for idx in range(2, len(word_sets)):
        repeated = sorted(word_sets[idx - 2] & word_sets[idx - 1] & word_sets[idx])
        if repeated:
            issues.append({
                "level": "warn",
                "cut_number": idx + 1,
                "category": "word_repeat",
                "message": f"같은 단어가 3컷 이상 반복됩니다: {', '.join(repeated[:6])}",
            })

    endings = [_sentence_ending(cut.get("narration") if isinstance(cut, dict) else "") for cut in cuts]
    for idx in range(2, len(endings)):
        if endings[idx] and endings[idx] == endings[idx - 1] == endings[idx - 2]:
            issues.append({
                "level": "warn",
                "cut_number": idx + 1,
                "category": "ending_repeat",
                "message": f"같은 종결어가 3컷 이상 반복됩니다: {endings[idx]}",
            })
    for block_start in range(0, len(cuts), 10):
        block = cuts[block_start:block_start + 10]
        if len(block) < 10:
            continue
        groups = [
            _ending_group(_sentence_ending(cut.get("narration") if isinstance(cut, dict) else ""))
            for cut in block
        ]
        jyos = groups.count("죠")
        if jyos >= 4:
            issues.append({
                "level": "error",
                "cut_number": block_start + 1,
                "category": "narration_tone",
                "message": f"Block {block_start // 10 + 1}: `죠` 계열 종결이 {jyos}컷입니다. 10컷 안에서는 최대 3컷만 허용합니다.",
            })
        if groups.count("습니다") < 1:
            issues.append({
                "level": "error",
                "cut_number": block_start + 1,
                "category": "narration_tone",
                "message": f"Block {block_start // 10 + 1}: `습니다/입니다` 계열 종결이 최소 1컷 필요합니다.",
            })

    passed = not any(issue.get("level") == "error" for issue in issues)
    summary = (
        f"Python 기계 검수 완료: 자동 보정 {changed}개, 확인 필요 {len(issues)}개"
        if issues or changed
        else "Python 기계 검수 통과"
    )
    return revised, {
        "stage": "local",
        "model": "python",
        "passed": passed,
        "score": 10 if passed and not issues else 7 if passed else 0,
        "summary": summary,
        "issues": issues,
        "fix_plan": [
            {"cut_number": issue.get("cut_number"), "instruction": issue.get("message")}
            for issue in issues
            if issue.get("level") in {"error", "warn"}
        ][:80],
        "patches": patches,
        "patch_count": len(patches),
        "applied_patch_count": changed,
        "checked_at": _now_iso(),
    }, changed


def _validation_model_config(config: dict | None) -> dict[str, str]:
    cfg = config or {}
    return {
        "gemma": str(cfg.get("validation_gemma_model") or VALIDATION_GEMMA_MODEL),
    }


def _ollama_model_name(model_id: str) -> str:
    value = str(model_id or "").strip()
    return value.split(":", 1)[1] if value.startswith("ollama:") else value


def _compact_story_for_validation(story_plan: dict | None) -> dict:
    plan = story_plan if isinstance(story_plan, dict) else {}
    return {
        "story_core": plan.get("story_core") or {},
        "character_map": plan.get("character_map") or [],
        "causality_chain": plan.get("causality_chain") or [],
        "fact_ledger": plan.get("fact_ledger") or {},
        "visual_world": plan.get("visual_world") or {},
        "scene_blocks": plan.get("scene_blocks") or [],
        "script_checklist": plan.get("script_checklist") or {},
    }


def _compact_script_for_validation(script: dict | None) -> dict:
    if not isinstance(script, dict):
        return {}
    cuts: list[dict] = []
    source_cuts = script.get("cuts") if isinstance(script.get("cuts"), list) else []
    if not source_cuts and _script_has_text_blocks(script):
        for block in _script_text_blocks(script):
            for line in block.get("lines") or []:
                if isinstance(line, dict):
                    source_cuts.append(line)
    for cut in source_cuts:
        if isinstance(cut, dict):
            cuts.append({
                "cut_number": cut.get("cut_number"),
                "scene_block_id": cut.get("scene_block_id"),
                "narration": cut.get("narration"),
                "visual_year": cut.get("visual_year"),
                "visual_period": cut.get("visual_period"),
                "visual_location": cut.get("visual_location"),
                "visual_subject": cut.get("visual_subject"),
                "visual_scene": cut.get("visual_scene"),
            })
    return {
        "title": script.get("title"),
        "description": script.get("description"),
        "thumbnail_hook": script.get("thumbnail_hook"),
        "story_core": script.get("story_core") or {},
        "fact_ledger": script.get("fact_ledger") or {},
        "scene_blocks": script.get("scene_blocks") or [],
        "cuts": cuts,
    }


async def _ollama_validation_chat(
    *,
    model_id: str,
    system: str,
    user: str,
    temperature: float = 0.1,
    num_predict: int = 8192,
    draft_id: str | None = None,
    raw_label: str = "",
) -> dict:
    def _raw_paths(label_suffix: str = "") -> tuple[str, str]:
        if not draft_id:
            return "", ""
        try:
            safe_label = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw_label or "validation").strip("_") or "validation"
            if label_suffix:
                safe_label = f"{safe_label}_{label_suffix}"
            raw_dir = _draft_dir(draft_id) / "validation_raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            return (
                str(raw_dir / f"{stamp}_{safe_label}.txt"),
                str(raw_dir / f"{stamp}_{safe_label}_response.json"),
            )
        except Exception:
            return "", ""

    async def _call_once(label_suffix: str = "", repair_note: str = "") -> tuple[dict, str, str]:
        user_content = user
        if repair_note:
            user_content = (
                user
                + "\n\n이전 응답은 JSON 형식이 깨졌습니다. "
                + repair_note
                + " JSON 객체 하나만 다시 출력하세요. "
                "summary/message/instruction/reason은 짧게 쓰고, 예시 설명과 반복 문장은 금지합니다."
            )
        payload = {
            "model": _ollama_model_name(model_id),
            "stream": False,
            "format": "json",
            "think": False,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        system
                        + "\n\n반드시 JSON 객체 하나만 반환합니다. 마크다운, 설명, 추론 과정은 금지합니다. "
                        "긴 예시, 괄호 안 장문 설명, 같은 어구 반복은 금지합니다."
                    ),
                },
                {"role": "user", "content": user_content},
            ],
            "options": {
                "temperature": temperature,
                "num_ctx": OLLAMA_NUM_CTX,
                "num_predict": max(512, num_predict),
            },
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(None, connect=10.0)) as client:
            response = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
            response.raise_for_status()
        data = response.json()
        raw_text = str(((data.get("message") or {}).get("content")) or "").strip()
        raw_path, response_path = _raw_paths(label_suffix)
        if raw_path:
            try:
                Path(raw_path).write_text(raw_text, encoding="utf-8")
                if not raw_text and response_path:
                    Path(response_path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                raw_path = ""
        return data, raw_text, raw_path

    def _parse_raw_json(raw_text: str) -> dict | None:
        try:
            parsed_value = json.loads(raw_text)
        except json.JSONDecodeError:
            parsed_value = BaseLLMService._extract_json_object(raw_text)
        return parsed_value if isinstance(parsed_value, dict) else None

    data, raw, raw_path = await _call_once()
    if not raw:
        data, raw, raw_path = await _call_once("retry")
    if not raw:
        done_reason = str(data.get("done_reason") or "").strip()
        suffix = f" done_reason={done_reason}" if done_reason else ""
        suffix += f" raw={raw_path}" if raw_path else ""
        raise RuntimeError(f"Ollama validation response was empty: {_ollama_model_name(model_id)}{suffix}")
    parsed = _parse_raw_json(raw)
    if not isinstance(parsed, dict):
        data, raw, raw_path = await _call_once(
            "json_retry",
            repair_note="문자열을 반드시 닫고, 배열과 객체를 끝까지 닫아야 합니다.",
        )
        if raw:
            parsed = _parse_raw_json(raw)
    if not isinstance(parsed, dict):
        suffix = f" raw={raw_path}" if raw_path else ""
        raise RuntimeError(f"Ollama validation response was not valid JSON: {_ollama_model_name(model_id)}{suffix}")
    return parsed


def _validation_system_prompt(stage: str, focus_stage: int = 0) -> str:
    base = (
        "당신은 LongTube 대본 검사관입니다.\n"
        "입력 자료 안에서 확인되는 문제만 다룹니다.\n"
        "출력 형식은 반드시 다음 JSON입니다:\n"
        "{\"passed\": true/false, \"score\": 1-10, \"summary\": \"짧은 요약\", "
        "\"issues\": [{\"level\": \"error 또는 warn\", \"cut_number\": 숫자 또는 null, "
        "\"block_id\": 숫자 또는 null, \"cut_range\": \"예: 11-15 또는 빈 문자열\", "
        "\"category\": \"분류\", \"message\": \"사용자가 알아들을 수 있는 한국어 사유\"}], "
        "\"fix_plan\": [{\"block_id\": 숫자 또는 null, \"cut_range\": \"예: 11-15\", "
        "\"affected_cuts\": [숫자], \"cut_number\": 숫자 또는 null, "
        "\"instruction\": \"다음 수정자가 따라야 할 구체 지시\"}], "
        "\"patches\": [{\"cut_number\": 숫자, \"fields\": {\"narration\": \"수정문\", "
        "\"visual_subject\": \"수정문\", \"visual_scene\": \"수정문\"}, \"reason\": \"수정 이유\"}]}\n"
        "문자 길이 제한: summary 80자 이하, issues.message 120자 이하, fix_plan.instruction 160자 이하, patches.reason 80자 이하.\n"
        "예시를 길게 풀어 쓰지 않습니다. 같은 단어/어구를 3회 이상 반복하지 않습니다.\n"
        "없는 문제를 만들지 말고, 패치는 필요한 컷과 필드에만 작성합니다.\n"
        "Python 기계 검수 결과가 previous_reports에 있으면 그 결과를 참고만 하고, "
        "cut_number, 빈 값, 글자 수, image_prompt, shorts_candidate, JSON 파싱 같은 기계 항목을 반복 검사하지 않습니다.\n"
        "중요: 대본이 이미 자연스럽고 기준을 충족하면 반드시 passed=true, issues=[], patches=[]로 둡니다. "
        "할 말이 없어서 억지로 트집 잡거나, 취향 차이 수준의 문장을 수정하거나, 같은 뜻의 문장으로 바꾸는 것은 실패입니다."
    )
    if stage == "gemma":
        if focus_stage == 1:
            focus = (
                "1차 검사 초점: 각 블럭 설계와 실제 대본의 연관성, 블럭 안팎의 중복입니다. "
                "scene_blocks의 new_information/tension/turn과 해당 블럭 대사가 맞는지, "
                "같은 문장이나 같은 정보가 반복되는지, 다음 블럭 내용을 앞당기는지 우선 봅니다. "
            )
        elif focus_stage == 2:
            focus = (
                "2차 검사 초점: 대본 전체 흐름, 어색한 말맛, 과도한 반복, 컷별 대사와 이미지 프롬프트의 연관성입니다. "
                "대사가 자연스럽게 이어지는지, 같은 표현이 질리게 반복되는지, 각 컷의 visual_scene이 narration과 실제로 맞는지 봅니다. "
            )
        elif focus_stage == 3:
            focus = (
                "3차 검사 초점: 종합검사입니다. 바로 공장에 적용할 수 있는지 최종 판정합니다. "
                "1차와 2차 수정 결과가 실제로 해결됐는지, 남은 치명 문제가 없는지 확인합니다. "
            )
        else:
            focus = ""
        return (
            base
            + "\n\n역할: 최종 검사관입니다. "
            + focus
            + "당신은 검사표를 읽는 기계가 아니라, 휴대폰으로 이 영상을 실제로 보는 한 명의 시청자라고 생각합니다. "
            "처음 10초에 이해되는지, 중간에 길을 잃는지, 대사가 사람 말처럼 들리는지, 다음 컷을 계속 보고 싶은지, "
            "마지막에 한 문장이 남는지를 전체 흐름으로 판단합니다. "
            "시청자 이해도, 한국어/일본어 말맛, 자연스러운 흐름, 끝까지 보게 만드는 연결감을 최종 판정합니다. "
            "이전 Gemma 수정 결과를 참고하되, 최종 통과 여부는 당신이 결정합니다. "
            "이전 수정 단계의 block_reports, patches, applied_patch_count가 있으면 그 블럭들이 실제로 해결됐는지 반드시 다시 확인합니다. "
            "바로 공장에 적용해도 되는 수준일 때만 passed=true입니다. "
            "Gemma는 patches를 작성하지 않습니다. 실패하면 fix_plan을 반드시 블럭 단위로 작성합니다. "
            "fix_plan 각 항목에는 block_id, cut_range, affected_cuts, instruction을 넣고, "
            "같은 문제에 속한 여러 컷은 하나의 블럭 지시로 묶습니다. "
            "단일 컷 문제라도 해당 컷이 속한 block_id와 cut_range를 함께 적습니다. "
            "다음 Gemma 수정자가 그 블럭 안에서 그대로 수행할 수 있을 만큼 구체적으로 씁니다."
        )
    if stage == "gemma_revision":
        return (
            base
            + "\n\n역할: Gemma 블럭 수정자입니다. "
            "previous_reports에 있는 직전 Gemma의 block_id/cut_range/affected_cuts 기반 fix_plan만 대상으로 삼습니다. "
            "당신은 최종 판정자가 아니라 수정자입니다. passed는 false로 두어도 됩니다. "
            "해당 블럭 안에서 반복 문장, 같은 정보 반복, 흐름 단절, 사실성 오류, 말맛, 이미지 장면 연결을 실제로 개선하는 patches만 작성합니다. "
            "전체 script를 다시 쓰지 말고 필요한 컷과 필드만 고칩니다."
        )
    return (
        base
        + "\n\n역할: 추가 검사관입니다. "
        "재생성 또는 수정 로직에 넘길 핵심 실패 사유를 우선순위대로 정리합니다."
    )


def _parse_validation_cut_range(value: Any) -> tuple[int, int] | None:
    match = re.search(r"(\d+)\s*[-~]\s*(\d+)", str(value or ""))
    if not match:
        return None
    start = int(match.group(1))
    end = int(match.group(2))
    if start <= 0 or end < start:
        return None
    return start, end


def _block_range_from_id(block_id: int) -> tuple[int, int]:
    start = (max(1, int(block_id)) - 1) * 10 + 1
    return start, start + 9


def _block_id_from_cut(cut_number: int) -> int:
    return max(1, math.ceil(max(1, int(cut_number)) / 10))


def _validation_revision_targets(stage_report: dict | None) -> list[dict]:
    targets: dict[int, dict] = {}
    for item in (stage_report or {}).get("fix_plan") or []:
        if not isinstance(item, dict):
            continue
        try:
            block_id = int(item.get("block_id") or 0)
        except (TypeError, ValueError):
            block_id = 0
        affected_cuts = []
        for cut_number in item.get("affected_cuts") or []:
            try:
                cut_int = int(cut_number)
            except (TypeError, ValueError):
                continue
            if cut_int > 0 and cut_int not in affected_cuts:
                affected_cuts.append(cut_int)
        try:
            single_cut = int(item.get("cut_number") or 0)
        except (TypeError, ValueError):
            single_cut = 0
        if single_cut > 0 and single_cut not in affected_cuts:
            affected_cuts.append(single_cut)
        if block_id <= 0 and affected_cuts:
            block_id = _block_id_from_cut(affected_cuts[0])
        parsed_range = _parse_validation_cut_range(item.get("cut_range"))
        if block_id <= 0 and parsed_range:
            block_id = _block_id_from_cut(parsed_range[0])
        if block_id <= 0:
            continue
        block_start, block_end = _block_range_from_id(block_id)
        if not affected_cuts:
            if parsed_range:
                range_start = max(block_start, parsed_range[0])
                range_end = min(block_end, parsed_range[1])
                affected_cuts = list(range(range_start, range_end + 1)) if range_start <= range_end else []
            if not affected_cuts:
                affected_cuts = list(range(block_start, block_end + 1))
        start, end = block_start, block_end
        target = targets.get(block_id)
        if not target:
            target = {
                "block_id": block_id,
                "cut_range": f"{start}-{end}",
                "allowed_cuts": list(range(start, end + 1)),
                "affected_cuts": [],
                "instructions": [],
                "source_fix_plan": [],
            }
            targets[block_id] = target
        for cut_number in affected_cuts:
            if start <= cut_number <= end and cut_number not in target["affected_cuts"]:
                target["affected_cuts"].append(cut_number)
        instruction = str(item.get("instruction") or "").strip()
        if instruction:
            target["instructions"].append(instruction)
        target["source_fix_plan"].append(item)
    return [targets[key] for key in sorted(targets)]


def _validation_all_block_targets(config: dict, story_plan: dict | None, script: dict | None) -> list[dict]:
    expected_blocks = max(1, math.ceil(_expected_cut_count(config) / 10))
    story_blocks = {}
    if isinstance(story_plan, dict):
        for block in story_plan.get("scene_blocks") or []:
            if not isinstance(block, dict):
                continue
            try:
                block_id = int(block.get("block_id") or 0)
            except (TypeError, ValueError):
                block_id = 0
            if block_id > 0:
                story_blocks[block_id] = block
    if _script_has_text_blocks(script):
        for block in _script_text_blocks(script):
            try:
                block_id = int(block.get("block_id") or 0)
            except (TypeError, ValueError):
                block_id = 0
            if block_id > expected_blocks:
                expected_blocks = block_id
    targets: list[dict] = []
    for block_id in range(1, expected_blocks + 1):
        block_start, block_end = _block_range_from_id(block_id)
        story_block = story_blocks.get(block_id) or {}
        parsed_range = _parse_validation_cut_range(story_block.get("cut_range"))
        if parsed_range:
            block_start, block_end = parsed_range
        allowed = list(range(block_start, block_end + 1))
        targets.append({
            "block_id": block_id,
            "cut_range": f"{block_start}-{block_end}",
            "allowed_cuts": allowed,
            "affected_cuts": allowed,
            "instructions": [],
            "source_fix_plan": [],
        })
    return targets


def _ensure_block_report_revision_target(report: dict, target: dict, focus_stage: int) -> dict:
    if bool(report.get("passed")):
        return report
    block_id = int(target.get("block_id") or 0)
    cut_range = str(target.get("cut_range") or "")
    allowed_cuts = [int(cut) for cut in target.get("allowed_cuts") or []]
    issues = [item for item in report.get("issues") or [] if isinstance(item, dict)]
    fix_plan = [item for item in report.get("fix_plan") or [] if isinstance(item, dict)]
    if not issues:
        issues = [{
            "level": "error",
            "cut_number": None,
            "block_id": block_id,
            "cut_range": cut_range,
            "category": f"gemma_stage_{focus_stage}",
            "message": "Gemma가 실패로 판정했지만 사유를 비워 반환했습니다.",
        }]
        report["issues"] = issues
    if not fix_plan:
        messages = [
            str(item.get("message") or "").strip()
            for item in issues
            if str(item.get("message") or "").strip()
        ]
        instruction = " / ".join(messages[:4]) or "해당 블럭을 단계 기준에 맞게 다시 점검하고 필요한 컷을 수정합니다."
        fix_plan = [{
            "cut_number": None,
            "block_id": block_id,
            "cut_range": cut_range,
            "affected_cuts": allowed_cuts,
            "instruction": instruction,
        }]
        report["fix_plan"] = fix_plan
    normalized_plan = []
    for item in fix_plan:
        fixed = dict(item)
        fixed["block_id"] = int(fixed.get("block_id") or block_id)
        fixed["cut_range"] = str(fixed.get("cut_range") or cut_range)
        affected = []
        for cut in fixed.get("affected_cuts") or []:
            try:
                cut_int = int(cut)
            except (TypeError, ValueError):
                continue
            if cut_int in allowed_cuts and cut_int not in affected:
                affected.append(cut_int)
        if not affected:
            try:
                single_cut = int(fixed.get("cut_number") or 0)
            except (TypeError, ValueError):
                single_cut = 0
            if single_cut in allowed_cuts:
                affected = [single_cut]
        fixed["affected_cuts"] = affected or allowed_cuts
        normalized_plan.append(fixed)
    report["fix_plan"] = normalized_plan
    return report


def _script_validation_block_scope(script: dict | None, target: dict) -> dict:
    if not isinstance(script, dict):
        return {}
    allowed = set(int(cut) for cut in target.get("allowed_cuts") or [])
    cuts = []
    source_cuts = script.get("cuts") if isinstance(script.get("cuts"), list) else []
    if not source_cuts and _script_has_text_blocks(script):
        source_cuts = []
        for block in _script_text_blocks(script):
            for line in block.get("lines") or []:
                if isinstance(line, dict):
                    source_cuts.append(line)
    for cut in source_cuts:
        if not isinstance(cut, dict):
            continue
        try:
            cut_number = int(cut.get("cut_number") or 0)
        except (TypeError, ValueError):
            continue
        if cut_number in allowed:
            cuts.append(cut)
    return {
        "title": script.get("title"),
        "description": script.get("description"),
        "story_core": script.get("story_core") or {},
        "fact_ledger": script.get("fact_ledger") or {},
        "scene_blocks": [
            block for block in script.get("scene_blocks") or []
            if isinstance(block, dict) and int(block.get("block_id") or 0) == int(target.get("block_id") or 0)
        ],
        "cuts": cuts,
    }


def _story_validation_block_scope(story_plan: dict | None, target: dict) -> dict:
    if not isinstance(story_plan, dict):
        return {}
    block_id = int(target.get("block_id") or 0)
    return {
        "story_core": story_plan.get("story_core") or {},
        "character_map": story_plan.get("character_map") or [],
        "causality_chain": story_plan.get("causality_chain") or [],
        "fact_ledger": story_plan.get("fact_ledger") or {},
        "visual_world": story_plan.get("visual_world") or {},
        "scene_blocks": [
            block for block in story_plan.get("scene_blocks") or []
            if isinstance(block, dict) and int(block.get("block_id") or 0) == block_id
        ],
    }


def _validation_block_user_prompt(
    *,
    topic: str,
    config: dict,
    story_plan: dict | None,
    script: dict | None,
    previous_reports: list[dict],
    target: dict,
) -> str:
    target_report = {
        "stage": "target_block",
        "model": "system",
        "passed": False,
        "score": 0,
        "summary": "이번 호출은 지정된 한 블럭만 수정합니다.",
        "issues": [],
        "fix_plan": target.get("source_fix_plan") or [],
        "patches": [],
        "target_block": {
            "block_id": target.get("block_id"),
            "cut_range": target.get("cut_range"),
            "affected_cuts": target.get("affected_cuts") or [],
            "allowed_cuts": target.get("allowed_cuts") or [],
            "instructions": target.get("instructions") or [],
        },
    }
    payload = {
        "topic": topic,
        "language": normalize_language_code(config.get("language", "ko")),
        "target_cuts": len(target.get("allowed_cuts") or []),
        "validation_scope": "single_block_revision",
        "target_block": target_report["target_block"],
        "story_plan": _story_validation_block_scope(story_plan, target),
        "script": _script_validation_block_scope(script, target),
        "previous_reports": [*previous_reports, target_report],
        "hard_rules": [
            "이번 호출은 target_block.allowed_cuts 안의 컷만 patches로 수정합니다.",
            "다른 블럭이나 다른 컷을 수정하지 않습니다.",
            "전체 script를 다시 쓰지 않습니다.",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _validation_check_block_user_prompt(
    *,
    topic: str,
    config: dict,
    story_plan: dict | None,
    script: dict | None,
    previous_reports: list[dict],
    target: dict,
    focus_stage: int,
) -> str:
    payload = {
        "topic": topic,
        "language": normalize_language_code(config.get("language", "ko")),
        "target_cuts": len(target.get("allowed_cuts") or []),
        "validation_scope": f"single_block_check_stage_{focus_stage}",
        "target_block": {
            "block_id": target.get("block_id"),
            "cut_range": target.get("cut_range"),
            "allowed_cuts": target.get("allowed_cuts") or [],
        },
        "story_plan": _story_validation_block_scope(story_plan, target),
        "script": _script_validation_block_scope(script, target),
        "previous_reports": previous_reports or [],
        "hard_rules": [
            "이번 호출은 target_block.allowed_cuts 안의 한 블럭만 검사합니다.",
            "문제가 있으면 passed=false와 함께 issues와 fix_plan을 반드시 작성합니다.",
            "문제가 없으면 passed=true, issues=[], fix_plan=[], patches=[]로 둡니다.",
            "검사 단계에서는 patches를 작성하지 않습니다.",
            "다른 블럭 문제를 끌어오지 않습니다.",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _filter_stage_report_to_target(report: dict, target: dict) -> dict:
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    allowed = set(int(cut) for cut in target.get("allowed_cuts") or [])
    block_id = int(target.get("block_id") or 0)
    filtered = dict(report)
    filtered["issues"] = [
        item for item in report.get("issues") or []
        if not isinstance(item, dict)
        or _safe_int(item.get("block_id"), block_id) == block_id
        or _safe_int(item.get("cut_number")) in allowed
    ]
    filtered["fix_plan"] = [
        item for item in report.get("fix_plan") or []
        if isinstance(item, dict)
        and (_safe_int(item.get("block_id"), block_id) == block_id or _safe_int(item.get("cut_number")) in allowed)
    ]
    filtered_patches = []
    for patch in report.get("patches") or []:
        if not isinstance(patch, dict):
            continue
        try:
            cut_number = int(patch.get("cut_number"))
        except (TypeError, ValueError):
            continue
        if cut_number in allowed:
            filtered_patches.append(patch)
    filtered["patches"] = filtered_patches
    filtered["patch_count"] = len(filtered_patches)
    return filtered


def _normalize_validation_stage_report(raw: dict, *, stage: str, model_id: str) -> dict:
    def _clip_text(value, limit: int) -> str:
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 1)].rstrip() + "…"

    def _optional_int(value) -> int | None:
        try:
            return int(value) if value is not None and str(value).strip() else None
        except (TypeError, ValueError):
            return None

    def _int_list(value) -> list[int]:
        if not isinstance(value, list):
            return []
        out: list[int] = []
        for item in value[:20]:
            try:
                number = int(item)
            except (TypeError, ValueError):
                continue
            if number > 0 and number not in out:
                out.append(number)
        return out

    passed_value = raw.get("passed", raw.get("ok", False))
    passed = passed_value is True or str(passed_value).strip().lower() in {"true", "1", "yes", "y", "pass", "passed"}
    try:
        score = int(raw.get("score") or 0)
    except (TypeError, ValueError):
        score = 0
    raw_issues = raw.get("issues") if isinstance(raw.get("issues"), list) else []
    issues: list[dict] = []
    for item in raw_issues[:80]:
        if not isinstance(item, dict):
            continue
        cut_number = _optional_int(item.get("cut_number"))
        block_id = _optional_int(item.get("block_id") or item.get("scene_block_id"))
        cut_range = str(item.get("cut_range") or "").strip()
        level = str(item.get("level") or "warn").strip().lower()
        if level not in {"error", "warn"}:
            level = "warn"
        message = _clip_text(item.get("message"), 180)
        if not message:
            continue
        issues.append({
            "level": level,
            "cut_number": cut_number,
            "block_id": block_id,
            "cut_range": cut_range,
            "category": _clip_text(item.get("category") or stage, 40) or stage,
            "message": message,
        })
    raw_fix_plan = raw.get("fix_plan") if isinstance(raw.get("fix_plan"), list) else []
    fix_plan: list[dict] = []
    for item in raw_fix_plan[:80]:
        if not isinstance(item, dict):
            continue
        cut_number = _optional_int(item.get("cut_number"))
        block_id = _optional_int(item.get("block_id") or item.get("scene_block_id"))
        cut_range = str(item.get("cut_range") or "").strip()
        affected_cuts = _int_list(item.get("affected_cuts") or item.get("cuts"))
        instruction = _clip_text(item.get("instruction") or item.get("message"), 240)
        if instruction:
            fix_item = {
                "cut_number": cut_number,
                "block_id": block_id,
                "cut_range": cut_range,
                "affected_cuts": affected_cuts,
                "instruction": instruction,
            }
            fix_plan.append(fix_item)
    raw_patches = raw.get("patches") if isinstance(raw.get("patches"), list) else []
    patches: list[dict] = []
    for item in raw_patches[:200]:
        if not isinstance(item, dict):
            continue
        try:
            cut_number = int(item.get("cut_number"))
        except (TypeError, ValueError):
            continue
        fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
        if not fields:
            fields = {k: v for k, v in item.items() if k not in {"cut_number", "reason", "category"}}
        clean_fields = {
            str(k): v for k, v in fields.items()
            if str(k) in {
                "narration",
                "visual_year",
                "visual_period",
                "visual_location",
                "visual_evidence",
                "visual_subject",
                "visual_scene",
                "scene_type",
            }
        }
        if clean_fields:
            patches.append({
                "cut_number": cut_number,
                "fields": clean_fields,
                "reason": _clip_text(item.get("reason"), 120),
            })
    return {
        "stage": stage,
        "model": model_id,
        "passed": passed,
        "score": max(0, min(score, 10)),
        "summary": _clip_text(raw.get("summary"), 160),
        "issues": issues,
        "fix_plan": fix_plan,
        "patches": patches,
        "patch_count": len(patches),
        "checked_at": _now_iso(),
    }


def _validation_model_error_block_report(
    *,
    stage: str,
    model_id: str,
    target: dict,
    exc: Exception,
    focus_stage: int | None = None,
    revision: bool = False,
) -> dict:
    def _safe_int_value(value, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    block_id = _safe_int_value(target.get("block_id"), 0)
    cut_range = str(target.get("cut_range") or "").strip()
    allowed_cuts = [
        int(cut)
        for cut in (target.get("allowed_cuts") or target.get("affected_cuts") or [])
        if _safe_int_value(cut, 0) > 0
    ]
    message = str(exc or "").strip()
    message = message.split(" raw=", 1)[0].strip()
    if len(message) > 180:
        message = message[:179].rstrip() + "…"
    summary = (
        f"Block {block_id} Gemma 수정 응답 JSON 오류"
        if revision
        else f"Block {block_id} Gemma 검사 응답 JSON 오류"
    )
    issue_message = (
        f"{summary}: {message}"
        if message
        else summary
    )
    report = {
        "stage": stage,
        "model": model_id,
        "passed": False,
        "score": 0,
        "summary": summary,
        "issues": [{
            "level": "error",
            "cut_number": None,
            "block_id": block_id or None,
            "cut_range": cut_range,
            "category": "model_response",
            "message": issue_message,
        }],
        "fix_plan": [] if revision else [{
            "cut_number": None,
            "block_id": block_id or None,
            "cut_range": cut_range,
            "affected_cuts": allowed_cuts,
            "instruction": "Gemma 검사 응답이 JSON으로 닫히지 않아 자동 판정을 완료하지 못했습니다. 같은 블럭을 재검수해야 합니다.",
        }],
        "patches": [],
        "patch_count": 0,
        "checked_at": _now_iso(),
        "block_id": block_id,
        "cut_range": cut_range,
        "model_response_error": True,
    }
    if focus_stage is not None:
        report["attempt"] = focus_stage
    return report


async def _run_validation_revision_blocks(
    *,
    draft_id: str,
    job_id: str | None,
    stage: str,
    model_id: str,
    topic: str,
    config: dict,
    story_plan: dict | None,
    script: dict | None,
    previous_reports: list[dict],
    source_report: dict,
    completed: int,
    total: int,
) -> dict:
    labels = {
        "gemma_revision": "Gemma 블럭 수정",
    }
    targets = _validation_revision_targets(source_report)
    if not targets:
        return {
            "stage": stage,
            "model": model_id,
            "passed": True,
            "score": 0,
            "summary": f"{labels.get(stage, stage)} 대상 블럭이 없습니다.",
            "issues": [],
            "fix_plan": [],
            "patches": [],
            "patch_count": 0,
            "checked_at": _now_iso(),
        }
    combined = {
        "stage": stage,
        "model": model_id,
        "passed": True,
        "score": 0,
        "summary": f"{labels.get(stage, stage)} {len(targets)}개 블럭 처리",
        "issues": [],
        "fix_plan": [],
        "patches": [],
        "patch_count": 0,
        "checked_at": _now_iso(),
        "block_reports": [],
    }
    total_blocks = max(15, math.ceil(_expected_cut_count(config) / 10))
    for order, target in enumerate(targets, start=1):
        _raise_if_job_cancelled(draft_id, job_id)
        block_id = int(target.get("block_id") or 0)
        cut_range = str(target.get("cut_range") or "")
        stage_label = labels.get(stage, "블럭 수정")
        _set_generation_progress(
            draft_id,
            stage="validate",
            status="running",
            completed=completed,
            total=total,
            message=f"{stage_label} 중: Block {block_id} ({order}/{len(targets)})",
            model=model_id,
            job_id=job_id,
            block_event={
                "block_index": block_id,
                "total_blocks": total_blocks,
                "cut_range": cut_range,
                "generation_status": "completed",
                "validation_status": "running",
                "generation_model": (script or {}).get("generation_model") or "",
                "validation_model": model_id,
                "message": f"{stage_label} 진행",
            },
        )
        try:
            raw = await _ollama_validation_chat(
                model_id=model_id,
                system=_validation_system_prompt(stage),
                user=_validation_block_user_prompt(
                    topic=topic,
                    config=config,
                    story_plan=story_plan,
                    script=script,
                    previous_reports=previous_reports,
                    target=target,
                ),
                temperature=0.1,
                num_predict=8192,
                draft_id=draft_id,
                raw_label=f"{stage}_block_{block_id}_{order}",
            )
            _raise_if_job_cancelled(draft_id, job_id)
            block_report = _normalize_validation_stage_report(raw, stage=stage, model_id=model_id)
            block_report["block_id"] = block_id
            block_report["cut_range"] = cut_range
            block_report = _filter_stage_report_to_target(block_report, target)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            block_report = _validation_model_error_block_report(
                stage=stage,
                model_id=model_id,
                target=target,
                exc=exc,
                revision=True,
            )
        combined["block_reports"].append(block_report)
        combined["issues"].extend(block_report.get("issues") or [])
        combined["fix_plan"].extend(block_report.get("fix_plan") or [])
        combined["patches"].extend(block_report.get("patches") or [])
        combined["passed"] = bool(combined["passed"] and block_report.get("passed", True))
        combined["score"] = max(int(combined.get("score") or 0), int(block_report.get("score") or 0))
        _set_generation_progress(
            draft_id,
            stage="validate",
            status="running",
            completed=completed,
            total=total,
            message=f"{stage_label} 완료: Block {block_id} ({order}/{len(targets)})",
            model=model_id,
            job_id=job_id,
            block_event={
                "block_index": block_id,
                "total_blocks": total_blocks,
                "cut_range": cut_range,
                "generation_status": "completed",
                "validation_status": "completed" if block_report.get("passed", True) else "failed",
                "generation_model": (script or {}).get("generation_model") or "",
                "validation_model": model_id,
                "message": "모델 응답 오류" if block_report.get("model_response_error") else f"patch {len(block_report.get('patches') or [])}건",
            },
        )
    combined["patch_count"] = len(combined["patches"])
    if combined["patch_count"]:
        combined["summary"] += f", patch {combined['patch_count']}건"
    return combined


def _write_validation_script_state(draft_id: str, script: dict | None, meta: dict, cfg: dict) -> None:
    if not isinstance(script, dict):
        return
    if _script_has_text_blocks(script):
        _json_write(_partial_script_path(draft_id), script)
    elif _script_has_final_cuts(script):
        _json_write(_script_path(draft_id), _finalized_script_copy(script, meta, cfg, include_shorts=True))


def _empty_block_stage_report(stage: str, model_id: str, attempt: int, summary: str) -> dict:
    return {
        "stage": stage,
        "model": model_id,
        "passed": True,
        "score": 0,
        "summary": summary,
        "issues": [],
        "fix_plan": [],
        "patches": [],
        "patch_count": 0,
        "checked_at": _now_iso(),
        "attempt": attempt,
        "block_reports": [],
    }


async def _run_validation_block_stage(
    *,
    draft_id: str,
    job_id: str | None,
    model_id: str,
    topic: str,
    config: dict,
    story_plan: dict | None,
    script: dict | None,
    previous_reports: list[dict],
    focus_stage: int,
    completed_start: int,
    total: int,
    meta: dict,
    backup_path: str,
) -> tuple[dict | None, dict, dict, str]:
    labels = {
        1: "Gemma 1차 블럭검사",
        2: "Gemma 2차 블럭검사",
        3: "Gemma 3차 블럭검사",
    }
    stage_label = labels.get(focus_stage, "Gemma 블럭검사")
    revision_label = f"Gemma {focus_stage}차 블럭수정"
    targets = _validation_all_block_targets(config, story_plan, script)
    total_blocks = len(targets)
    check_report = _empty_block_stage_report("gemma", model_id, focus_stage, f"{stage_label} {total_blocks}개 블럭 처리")
    revision_report = _empty_block_stage_report("gemma_revision", model_id, focus_stage, f"{revision_label} 처리")
    revision_report["block_reports"] = []
    detected_blocks = 0
    resolved_blocks = 0
    unresolved_blocks: list[int] = []
    applied_total = 0

    for order, target in enumerate(targets, start=1):
        _raise_if_job_cancelled(draft_id, job_id)
        block_id = int(target.get("block_id") or 0)
        cut_range = str(target.get("cut_range") or "")
        completed_now = completed_start + order - 1
        _set_generation_progress(
            draft_id,
            stage="validate",
            status="running",
            completed=completed_now,
            total=total,
            message=f"{stage_label} 중: Block {block_id} ({order}/{total_blocks})",
            model=model_id,
            job_id=job_id,
            block_event={
                "block_index": block_id,
                "total_blocks": total_blocks,
                "cut_range": cut_range,
                "generation_status": "completed",
                "validation_status": "running",
                "generation_model": (script or {}).get("generation_model") or "",
                "validation_model": model_id,
                "message": f"{focus_stage}차 검사",
            },
        )
        try:
            raw = await _ollama_validation_chat(
                model_id=model_id,
                system=_validation_system_prompt("gemma", focus_stage=focus_stage),
                user=_validation_check_block_user_prompt(
                    topic=topic,
                    config=config,
                    story_plan=story_plan,
                    script=script,
                    previous_reports=previous_reports,
                    target=target,
                    focus_stage=focus_stage,
                ),
                temperature=0.1,
                num_predict=3072,
                draft_id=draft_id,
                raw_label=f"gemma_stage_{focus_stage}_block_{block_id}",
            )
            _raise_if_job_cancelled(draft_id, job_id)
            block_report = _normalize_validation_stage_report(raw, stage="gemma", model_id=model_id)
            block_report["attempt"] = focus_stage
            block_report["block_id"] = block_id
            block_report["cut_range"] = cut_range
            block_report = _filter_stage_report_to_target(block_report, target)
            block_report = _ensure_block_report_revision_target(block_report, target, focus_stage)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            block_report = _validation_model_error_block_report(
                stage="gemma",
                model_id=model_id,
                target=target,
                exc=exc,
                focus_stage=focus_stage,
            )
        check_report["block_reports"].append(block_report)
        check_report["issues"].extend(block_report.get("issues") or [])
        check_report["fix_plan"].extend(block_report.get("fix_plan") or [])
        check_report["score"] = max(int(check_report.get("score") or 0), int(block_report.get("score") or 0))

        block_changed = 0
        if not block_report.get("passed"):
            detected_blocks += 1
            if block_report.get("model_response_error"):
                unresolved_blocks.append(block_id)
            else:
                single_revision = await _run_validation_revision_blocks(
                    draft_id=draft_id,
                    job_id=job_id,
                    stage="gemma_revision",
                    model_id=model_id,
                    topic=topic,
                    config=config,
                    story_plan=story_plan,
                    script=script,
                    previous_reports=[*previous_reports, check_report],
                    source_report=block_report,
                    completed=completed_now,
                    total=total,
                )
                single_revision["attempt"] = focus_stage
                revised, block_changed = _apply_script_revision_patches(script, single_revision)
                if block_changed:
                    if not backup_path:
                        backup_path = _backup_script_before_validation_revision(draft_id)
                    script = revised
                    _write_validation_script_state(draft_id, script, meta, config)
                    single_revision["applied_patch_count"] = block_changed
                    applied_total += block_changed
                    resolved_blocks += 1
                else:
                    unresolved_blocks.append(block_id)
                revision_report["block_reports"].extend(single_revision.get("block_reports") or [])
                revision_report["issues"].extend(single_revision.get("issues") or [])
                revision_report["fix_plan"].extend(single_revision.get("fix_plan") or [])
                revision_report["patches"].extend(single_revision.get("patches") or [])
                revision_report["patch_count"] = len(revision_report["patches"])
                revision_report["score"] = max(int(revision_report.get("score") or 0), int(single_revision.get("score") or 0))

        _set_generation_progress(
            draft_id,
            stage="validate",
            status="running",
            completed=completed_start + order,
            total=total,
            message=f"{stage_label} 완료: Block {block_id} ({order}/{total_blocks})",
            model=model_id,
            job_id=job_id,
            block_event={
                "block_index": block_id,
                "total_blocks": total_blocks,
                "cut_range": cut_range,
                "generation_status": "completed",
                "validation_status": "completed" if block_id not in unresolved_blocks else "failed",
                "generation_model": (script or {}).get("generation_model") or "",
                "validation_model": model_id,
                "message": (
                    "모델 응답 오류"
                    if block_report.get("model_response_error")
                    else f"{focus_stage}차 {'수정' if block_changed else '통과' if block_report.get('passed') else '미해결'}"
                ),
            },
        )

    check_report["patches"] = revision_report.get("patches") or []
    check_report["patch_count"] = len(check_report["patches"])
    check_report["applied_patch_count"] = applied_total
    check_report["passed"] = not unresolved_blocks
    check_report["summary"] = (
        f"{stage_label} 완료: {total_blocks}개 블럭 검사, "
        f"문제 {detected_blocks}개 블럭, 수정 {resolved_blocks}개 블럭, 미해결 {len(unresolved_blocks)}개 블럭"
    )
    if unresolved_blocks:
        check_report["issues"].append({
            "level": "error",
            "cut_number": None,
            "block_id": None,
            "cut_range": "",
            "category": "unresolved",
            "message": f"{focus_stage}차 검사에서 수정 패치가 적용되지 않은 블럭: {', '.join(map(str, unresolved_blocks))}",
        })
    revision_report["passed"] = not unresolved_blocks
    revision_report["applied_patch_count"] = applied_total
    revision_report["summary"] = (
        f"{revision_label} 완료: 수정 {resolved_blocks}개 블럭, patch {len(revision_report.get('patches') or [])}건, "
        f"적용 {applied_total}건"
    )
    return script, check_report, revision_report, backup_path


def _append_stage_issues(issues: list[dict], stage_report: dict, *, final_stage: bool = False) -> None:
    stage_label = {
        "gemma": "Gemma",
        "gemma_revision": "Gemma 수정",
    }.get(str(stage_report.get("stage") or ""), str(stage_report.get("stage") or "LLM"))
    if stage_report.get("attempt"):
        stage_label = f"{stage_label} {stage_report.get('attempt')}회"
    for item in stage_report.get("issues") or []:
        if not isinstance(item, dict):
            continue
        raw_level = str(item.get("level") or "warn").strip().lower()
        level = raw_level if final_stage and raw_level == "error" else "warn"
        issues.append({
            "level": level,
            "cut_number": item.get("cut_number"),
            "message": f"{stage_label}: {item.get('message')}",
        })


def _backup_script_before_validation_revision(draft_id: str) -> str:
    source = _script_path(draft_id)
    if not source.exists():
        return ""
    versions_dir = _draft_dir(draft_id) / "validation_versions"
    versions_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = versions_dir / f"script_before_validation_{stamp}.json"
    counter = 1
    while destination.exists():
        destination = versions_dir / f"script_before_validation_{stamp}_{counter}.json"
        counter += 1
    shutil.copy2(source, destination)
    return str(destination)


def _apply_script_revision_patches(script: dict | None, stage_report: dict) -> tuple[dict, int]:
    if not isinstance(script, dict):
        return {}, 0
    try:
        revised = json.loads(json.dumps(script, ensure_ascii=False))
    except Exception:
        revised = dict(script)
    cuts = revised.get("cuts")
    if not isinstance(cuts, list):
        if _script_has_text_blocks(revised):
            cuts = []
            for block in _script_text_blocks(revised):
                for line in block.get("lines") or []:
                    if isinstance(line, dict):
                        cuts.append(line)
        else:
            return revised, 0
    cut_map: dict[int, dict] = {}
    for cut in cuts:
        if not isinstance(cut, dict):
            continue
        try:
            cut_map[int(cut.get("cut_number"))] = cut
        except (TypeError, ValueError):
            continue
    allowed_fields = {
        "narration",
        "visual_year",
        "visual_period",
        "visual_location",
        "visual_evidence",
        "visual_subject",
        "visual_scene",
        "scene_type",
    }
    changed = 0
    for patch in stage_report.get("patches") or []:
        if not isinstance(patch, dict):
            continue
        try:
            cut_number = int(patch.get("cut_number"))
        except (TypeError, ValueError):
            continue
        cut = cut_map.get(cut_number)
        fields = patch.get("fields") if isinstance(patch.get("fields"), dict) else {}
        if not cut or not fields:
            continue
        for field, value in fields.items():
            if field not in allowed_fields:
                continue
            if value is None:
                continue
            text = " ".join(str(value).split()) if field == "narration" else str(value).strip()
            if text and str(cut.get(field) or "") != text:
                cut[field] = text
                changed += 1
    return revised, changed


def _assemble_script_json_after_validation(script: dict | None, story_plan: dict | None, cfg: dict) -> dict:
    if not isinstance(script, dict):
        raise ValueError("조립할 대본이 없습니다.")
    if _script_has_final_cuts(script):
        return _deepcopy_jsonable(script)
    text_blocks = _script_text_blocks(script)
    if not text_blocks:
        raise ValueError("조립할 블럭 텍스트가 없습니다.")
    visual_world = story_plan.get("visual_world") if isinstance(story_plan, dict) else {}
    if not isinstance(visual_world, dict):
        visual_world = {}
    assembled = _deepcopy_jsonable(script)
    if not isinstance(assembled, dict):
        assembled = dict(script)
    cuts: list[dict] = []
    for block in text_blocks:
        try:
            block_id = int(block.get("block_id") or 0)
        except (TypeError, ValueError):
            block_id = 0
        for line in block.get("lines") or []:
            if not isinstance(line, dict):
                continue
            try:
                cut_number = int(line.get("cut_number") or 0)
            except (TypeError, ValueError):
                cut_number = 0
            if cut_number <= 0:
                continue
            visual_scene = str(line.get("visual_scene") or "").strip()
            visual_subject = str(line.get("visual_subject") or "").strip()
            cuts.append({
                "cut_number": cut_number,
                "scene_block_id": block_id or math.ceil(cut_number / 10),
                "narration": str(line.get("narration") or "").strip(),
                "image_prompt": "",
                "visual_year": str(line.get("visual_year") or visual_world.get("time_range") or "historical period").strip(),
                "visual_period": str(line.get("visual_period") or visual_world.get("culture_scope") or visual_world.get("time_range") or "historical period").strip(),
                "visual_location": str(line.get("visual_location") or visual_world.get("place_scope") or "story location").strip(),
                "visual_evidence": str(line.get("visual_evidence") or "Derived from validated block text.").strip(),
                "visual_subject": visual_subject or "validated historical scene",
                "visual_scene": visual_scene,
                "scene_type": str(line.get("scene_type") or "body").strip() or "body",
                "shorts_candidate": False,
            })
    cuts.sort(key=lambda item: int(item.get("cut_number") or 0))
    expected = _expected_cut_count(cfg)
    if len(cuts) != expected:
        raise ValueError(f"Python JSON 조립 실패: 현재 {len(cuts)}컷, 설정 {expected}컷입니다.")
    for idx, cut in enumerate(cuts, start=1):
        cut["cut_number"] = idx
    assembled["cuts"] = cuts
    assembled.pop("script_text_blocks", None)
    assembled.pop("text_only", None)
    assembled.pop("partial", None)
    assembled.pop("completed_scene_blocks", None)
    assembled.pop("total_scene_blocks", None)
    return assembled


def _read_script_or_partial_with_error(draft_id: str) -> tuple[Any, str, str]:
    if _script_path(draft_id).exists():
        script, error = _json_read_with_error(_script_path(draft_id))
        return script, error, "script"
    script, error = _json_read_with_error(_partial_script_path(draft_id))
    return script, error, "partial"


def _promote_script_after_first_check(
    draft_id: str,
    script: dict,
    meta: dict,
    cfg: dict,
    *,
    source: str,
) -> tuple[dict, dict]:
    finalized = _finalized_script_copy(script, meta, cfg, include_shorts=True)
    _json_write(_script_path(draft_id), finalized)
    cuts = [cut for cut in finalized.get("cuts", []) or [] if isinstance(cut, dict)]
    selected = [cut for cut in cuts if cut.get("shorts_candidate") is True]
    groups = sorted({
        int(cut.get("shorts_group") or 0)
        for cut in selected
        if int(cut.get("shorts_group") or 0) > 0
    })
    return finalized, {
        "stage": "shorts_selection",
        "model": "python",
        "passed": True,
        "score": 0,
        "summary": (
            f"1차 검사 통과 후 {source} 대본을 script.json으로 승격하고 "
            f"쇼츠 후보 {len(selected)}컷, 그룹 {len(groups)}개를 선정했습니다."
        ),
        "issues": [],
        "fix_plan": [],
        "patches": [],
        "patch_count": 0,
        "selected_cut_count": len(selected),
        "selected_group_count": len(groups),
        "checked_at": _now_iso(),
    }


async def validate_draft_with_llm(draft_id: str, job_id: str | None = None) -> dict:
    meta = _load_meta(draft_id)
    cfg = _normalize_config(meta.get("config") or {})
    try:
        _validation_path(draft_id).unlink(missing_ok=True)
    except Exception:
        pass
    script, parse_error, script_source = _read_script_or_partial_with_error(draft_id)
    story_plan = _json_read(_story_path(draft_id))
    if isinstance(story_plan, dict):
        meta["story_plan"] = story_plan
    models = _validation_model_config(cfg)
    block_targets = _validation_all_block_targets(cfg, story_plan if isinstance(story_plan, dict) else None, script if isinstance(script, dict) else None)
    pipeline_total = 2 + (len(block_targets) * 3)
    backup_path = ""
    _set_generation_progress(
        draft_id,
        stage="validate",
        status="running",
        completed=0,
        total=pipeline_total,
        message="블럭 텍스트 구조 확인 중",
        model="python",
        job_id=job_id,
    )
    script, local_report, local_changed = _python_mechanical_fix_script(script, cfg, parse_error=parse_error)
    pipeline = [local_report]
    if bool(local_report.get("passed")) and _script_has_final_cuts(script):
        if _script_path(draft_id).exists():
            backup_path = _backup_script_before_validation_revision(draft_id)
        script, shorts_report = _promote_script_after_first_check(
            draft_id,
            script,
            meta,
            cfg,
            source=script_source,
        )
        pipeline.append(shorts_report)

    can_run_llm = _script_has_final_cuts(script) or _script_has_text_blocks(script)
    gemma_report: dict | None = None
    if can_run_llm:
        completed_steps = len(pipeline)
        for attempt in range(1, 4):
            _raise_if_job_cancelled(draft_id, job_id)
            script, gemma_report, revision_report, backup_path = await _run_validation_block_stage(
                draft_id=draft_id,
                job_id=job_id,
                model_id=models["gemma"],
                topic=str(meta.get("topic") or ""),
                config=cfg,
                story_plan=story_plan if isinstance(story_plan, dict) else None,
                script=script if isinstance(script, dict) else None,
                previous_reports=pipeline,
                focus_stage=attempt,
                completed_start=completed_steps,
                total=pipeline_total,
                meta=meta,
                backup_path=backup_path,
            )
            pipeline.append(gemma_report)
            pipeline.append(revision_report)
            completed_steps += len(block_targets)
    else:
        pipeline.append({
            "stage": "gemma",
            "model": models["gemma"],
            "passed": False,
            "score": 0,
            "summary": "LLM 검사를 실행할 수 있는 블럭 텍스트가 없습니다.",
            "issues": [{"level": "error", "cut_number": None, "category": "script", "message": "대본 블럭 텍스트가 없습니다."}],
            "fix_plan": [{
                "block_id": None,
                "cut_range": "",
                "affected_cuts": [],
                "cut_number": None,
                "instruction": "대본 생성 단계에서 블럭 텍스트를 다시 생성해야 합니다.",
            }],
            "patches": [],
            "patch_count": 0,
            "checked_at": _now_iso(),
        })

    assembly_report: dict | None = None
    if _script_has_text_blocks(script) and gemma_report and gemma_report.get("passed"):
        assembled = _assemble_script_json_after_validation(script, story_plan if isinstance(story_plan, dict) else None, cfg)
        script = _finalized_script_copy(assembled, meta, cfg, include_shorts=True)
        _json_write(_script_path(draft_id), script)
        assembly_report = {
            "stage": "python_json_assembly",
            "model": "python",
            "passed": True,
            "score": 0,
            "summary": "Gemma 3차 종합검사 통과 후 Python이 최종 JSON cuts를 조립했습니다.",
            "issues": [],
            "fix_plan": [],
            "patches": [],
            "patch_count": 0,
            "checked_at": _now_iso(),
        }
        pipeline.append(assembly_report)
    final_local_report = validate_script(script, cfg) if _script_has_final_cuts(script) else {
        "ok": False,
        "issues": [{"level": "error", "message": "최종 JSON cuts가 아직 조립되지 않았습니다."}],
    }
    final_local_issues = list(final_local_report.get("issues") or [])
    local_errors = any(issue.get("level") == "error" for issue in final_local_issues if isinstance(issue, dict))
    gemma = gemma_report or next((item for item in reversed(pipeline) if item.get("stage") == "gemma"), None)
    ok = (not local_errors) and bool(gemma and gemma.get("passed"))
    issues = list(final_local_issues)
    if gemma and not gemma.get("passed"):
        issues.append({
            "level": "error",
            "message": f"Gemma 최종 검사 실패: {gemma.get('summary') or '통과 기준에 도달하지 못했습니다.'}",
        })
        for item in gemma.get("issues") or []:
            if isinstance(item, dict) and str(item.get("message") or "").strip():
                issues.append({
                    "level": "error" if str(item.get("level") or "").lower() == "error" else "warn",
                    "cut_number": item.get("cut_number"),
                    "block_id": item.get("block_id"),
                    "cut_range": item.get("cut_range"),
                    "message": f"Gemma: {item.get('message')}",
                })
        for item in gemma.get("fix_plan") or []:
            if isinstance(item, dict) and str(item.get("instruction") or "").strip():
                block_prefix = ""
                if item.get("block_id"):
                    block_prefix = f"Block {item.get('block_id')}"
                    if item.get("cut_range"):
                        block_prefix += f" ({item.get('cut_range')})"
                    block_prefix += ": "
                issues.append({
                    "level": "warn",
                    "cut_number": item.get("cut_number"),
                    "block_id": item.get("block_id"),
                    "cut_range": item.get("cut_range"),
                    "message": f"Gemma 수정방안: {block_prefix}{item.get('instruction')}",
                })

    if backup_path:
        pipeline.append({
            "stage": "script_revision_saved",
            "model": "system",
            "passed": True,
            "score": 0,
            "summary": f"검수 수정 전 대본 백업: {backup_path}",
            "issues": [],
            "fix_plan": [],
            "patches": [],
            "patch_count": 0,
            "checked_at": _now_iso(),
        })
    checked_at = _now_iso()
    report = {
        "ok": ok,
        "issue_count": len(issues),
        "issues": issues,
        "validation_pipeline": pipeline,
        "final_model": models["gemma"],
        "final_stage": "gemma",
        "checked_at": checked_at,
    }
    _json_write(_validation_path(draft_id), report)
    meta = _load_meta(draft_id)
    meta["status"] = "script_ready" if ok else "needs_review"
    meta["last_error"] = "" if ok else "Gemma 최종 검사 실패. 검수 결과를 확인해야 합니다."
    _save_meta(meta)
    return get_draft(draft_id)


def validate_draft(draft_id: str) -> dict:
    meta = _load_meta(draft_id)
    cfg = _normalize_config(meta.get("config") or {})
    script, parse_error, script_source = _read_script_or_partial_with_error(draft_id)
    if parse_error:
        report = {
            "ok": False,
            "issue_count": 1,
            "issues": [{"level": "error", "message": f"JSON 파싱 오류: {parse_error}"}],
            "checked_at": _now_iso(),
        }
    else:
        report = validate_script(script, cfg)
    if report.get("ok") and isinstance(script, dict):
        script, shorts_report = _promote_script_after_first_check(
            draft_id,
            script,
            meta,
            cfg,
            source=script_source,
        )
        report["validation_pipeline"] = [shorts_report]
    _json_write(_validation_path(draft_id), report)
    meta["status"] = "script_ready" if report["ok"] else "needs_review"
    meta["last_error"] = "" if report["ok"] else "검사 항목을 확인해야 합니다."
    _save_meta(meta)
    return get_draft(draft_id)


def export_draft_script(draft_id: str) -> dict:
    script = _json_read(_script_path(draft_id))
    if not isinstance(script, dict):
        raise ValueError("내보낼 대본이 없습니다.")
    export_path = _draft_dir(draft_id) / "longtube_script.json"
    _json_write(export_path, script)
    return {"ok": True, "path": str(export_path), "script": script}


def apply_draft_to_project(db: Session, draft_id: str, target_project_id: str | None = None) -> dict:
    meta = _load_meta(draft_id)
    script = _json_read(_script_path(draft_id))
    if not isinstance(script, dict):
        raise ValueError("적용할 대본이 없습니다.")
    project_id = target_project_id or meta.get("source_project_id")
    if not project_id:
        raise ValueError("적용할 롱폼공장 프로젝트가 연결되어 있지 않습니다.")
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("적용할 롱폼공장 프로젝트를 찾을 수 없습니다.")

    project_dir = resolve_project_dir(project_id, project.config or {}, create=True)
    script_path = project_dir / "script.json"
    if script_path.exists():
        versions_dir = project_dir / "script_studio_versions"
        versions_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(script_path, versions_dir / f"script_before_{draft_id}_{stamp}.json")

    script = _finalize_script_for_draft(script, meta, project.config or {}, include_shorts=True)
    _json_write(script_path, script)

    existing_cuts = {
        c.cut_number: c
        for c in db.query(Cut).filter(Cut.project_id == project_id).all()
    }
    seen: set[int] = set()
    for cut_data in script.get("cuts", []) or []:
        if not isinstance(cut_data, dict):
            continue
        cut_number = int(cut_data.get("cut_number") or 0)
        if cut_number <= 0:
            continue
        seen.add(cut_number)
        cut = existing_cuts.get(cut_number)
        if not cut:
            cut = Cut(project_id=project_id, cut_number=cut_number, status="pending")
            db.add(cut)
        cut.narration = cut_data.get("narration")
        cut.image_prompt = normalize_image_prompt(cut_data.get("image_prompt") or "")
        cut.scene_type = cut_data.get("scene_type") or "narration"
        cut.audio_path = None
        cut.audio_duration = None
        cut.audio_original_duration = None
        cut.image_path = None
        cut.image_model = None
        cut.video_path = None
        cut.video_model = None
        cut.status = "pending"
    for number, cut in existing_cuts.items():
        if number not in seen:
            db.delete(cut)

    project.total_cuts = len(script.get("cuts") or [])
    states = dict(project.step_states or {})
    states["story"] = "completed" if _story_path(draft_id).exists() else states.get("story", "completed")
    states["2"] = "completed"
    for key in ("3", "4", "5", "6", "7"):
        states.pop(key, None)
    project.step_states = states
    project.current_step = max(project.current_step or 0, 2)
    flag_modified(project, "step_states")
    db.commit()

    meta["last_applied_project_id"] = project_id
    meta["last_applied_at"] = _now_iso()
    _save_meta(meta)
    return {"ok": True, "project_id": project_id, "script_path": str(script_path), "cut_count": project.total_cuts}


def _mark_job_cancelled(draft_id: str, stage: str, job_id: str | None, message: str = "작업 중지됨") -> None:
    try:
        meta = _load_meta(draft_id)
    except Exception:
        return
    if job_id and str(meta.get("active_job_id") or "") != str(job_id):
        return
    if stage == "story":
        meta["story_status"] = "cancelled"
        meta["status"] = "draft"
    elif stage == "script":
        meta["script_status"] = "cancelled"
        meta["status"] = "story_ready" if _story_path(draft_id).exists() else "draft"
    elif stage == "validate":
        meta["status"] = "script_ready" if _script_path(draft_id).exists() else "draft"
    elif stage == "apply":
        meta["status"] = meta.get("status") or ("script_ready" if _script_path(draft_id).exists() else "draft")
    meta["last_error"] = message
    progress = meta.get("generation_progress") if isinstance(meta.get("generation_progress"), dict) else {}
    total = int(progress.get("total") or 1)
    completed = int(progress.get("completed") or 0)
    started_at = progress.get("started_at") or meta.get("active_job_started_at") or progress.get("updated_at") or _now_iso()
    finished_at = _now_iso()
    meta["generation_progress"] = {
        "stage": stage,
        "status": "cancelled",
        "completed": completed,
        "total": total,
        "progress_pct": round((completed / max(total, 1)) * 100, 1),
        "message": message,
        "model": str(progress.get("model") or ""),
        "job_id": str(job_id or ""),
        "started_at": started_at,
        "finished_at": finished_at,
        "elapsed_seconds": _elapsed_seconds(started_at, finished_at),
        "updated_at": finished_at,
    }
    meta = _append_job_history(
        meta,
        stage=stage,
        status="cancelled",
        job_id=job_id,
        model=str(progress.get("model") or ""),
        message=message,
    )
    meta = _clear_active_job(meta, job_id)
    _save_meta(meta)


def _mark_job_failed(draft_id: str, stage: str, job_id: str | None, exc: Exception) -> None:
    try:
        meta = _load_meta(draft_id)
    except Exception:
        return
    if job_id and not _is_active_job(meta, job_id):
        return
    if stage == "story":
        status_key = "story_status"
    elif stage == "script":
        status_key = "script_status"
    else:
        status_key = ""
    if status_key:
        _set_error(meta, status_key, exc, job_id=job_id)
        return
    meta["status"] = "failed"
    meta["last_error"] = humanize_generation_error(exc)
    progress = meta.get("generation_progress") if isinstance(meta.get("generation_progress"), dict) else {}
    progress["stage"] = stage
    progress["status"] = "failed"
    progress["message"] = meta["last_error"]
    started_at = progress.get("started_at") or meta.get("active_job_started_at") or progress.get("updated_at") or _now_iso()
    finished_at = _now_iso()
    progress["started_at"] = started_at
    progress["finished_at"] = finished_at
    progress["elapsed_seconds"] = _elapsed_seconds(started_at, finished_at)
    progress["updated_at"] = finished_at
    meta["generation_progress"] = progress
    meta = _clear_active_job(meta, job_id)
    _save_meta(meta)


async def _run_validate_job(draft_id: str, job_id: str) -> dict:
    _raise_if_job_cancelled(draft_id, job_id)
    _set_generation_progress(
        draft_id,
        stage="validate",
        status="running",
        completed=0,
        total=VALIDATION_PIPELINE_TOTAL_STEPS,
        message="검사 대기 중",
        model="Gemma 블럭검사/수정 → python-json",
        job_id=job_id,
    )
    result = await validate_draft_with_llm(draft_id, job_id=job_id)
    _raise_if_job_cancelled(draft_id, job_id)
    meta = _load_meta(draft_id)
    if not _is_active_job(meta, job_id):
        raise asyncio.CancelledError("Script Studio validate job cancelled")
    report = result.get("validation_report") if isinstance(result, dict) else None
    ok = bool(report and report.get("ok"))
    current_progress = meta.get("generation_progress") if isinstance(meta.get("generation_progress"), dict) else {}
    total = int(current_progress.get("total") or 4)
    started_at = current_progress.get("started_at") or meta.get("active_job_started_at") or _now_iso()
    finished_at = _now_iso()
    meta["generation_progress"] = {
        "stage": "validate",
        "status": "completed",
        "completed": total,
        "total": total,
        "progress_pct": 100.0,
        "message": "Gemma 최종 검사 통과" if ok else "Gemma 최종 검사 실패",
        "model": str((report or {}).get("final_model") or VALIDATION_GEMMA_MODEL),
        "job_id": job_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "elapsed_seconds": _elapsed_seconds(started_at, finished_at),
        "updated_at": finished_at,
    }
    meta = _clear_active_job(meta, job_id)
    _save_meta(meta)
    return result


async def _run_apply_job(draft_id: str, job_id: str, target_project_id: str | None = None) -> dict:
    _raise_if_job_cancelled(draft_id, job_id)
    _set_generation_progress(
        draft_id,
        stage="apply",
        status="running",
        completed=0,
        total=1,
        message="롱폼공장 적용 중",
        job_id=job_id,
    )

    def _work() -> dict:
        db = SessionLocal()
        try:
            return apply_draft_to_project(db, draft_id, target_project_id=target_project_id)
        finally:
            db.close()

    result = await asyncio.to_thread(_work)
    _raise_if_job_cancelled(draft_id, job_id)
    meta = _load_meta(draft_id)
    if not _is_active_job(meta, job_id):
        raise asyncio.CancelledError("Script Studio apply job cancelled")
    meta["generation_progress"] = {
        "stage": "apply",
        "status": "completed",
        "completed": 1,
        "total": 1,
        "progress_pct": 100.0,
        "message": "공장 적용 완료",
        "model": "",
        "job_id": job_id,
        "updated_at": _now_iso(),
    }
    meta = _clear_active_job(meta, job_id)
    _save_meta(meta)
    return result


def start_draft_job(
    draft_id: str,
    stage: str,
    target_project_id: str | None = None,
    script_mode: str | None = None,
    block_index: int | None = None,
) -> dict:
    draft_id = str(draft_id or "").strip()
    meta = _load_meta(draft_id)
    running = _RUNNING_JOBS.get(draft_id)
    if running and not running.done():
        return get_draft(draft_id)
    if running and running.done():
        _RUNNING_JOBS.pop(draft_id, None)

    job_id = uuid.uuid4().hex[:12]
    meta = _mark_job_started(draft_id, stage=stage, job_id=job_id)
    cfg = _normalize_config(meta.get("config") or {})
    if stage == "story":
        model = str(cfg.get("story_model") or "")
    elif stage == "script":
        model = str(cfg.get("script_model") or "")
    elif stage == "validate":
        model = "Gemma 블럭검사/수정 → python-json"
    else:
        model = ""
    normalized_script_mode = _normalize_script_mode(script_mode) if stage == "script" else ""
    initial_messages = {
        "story": "스토리 생성 대기 중",
        "script": (
            f"블럭 {block_index} 재생성 대기 중"
            if normalized_script_mode == "block"
            else "대본 이어서 생성 대기 중"
            if normalized_script_mode == "resume"
            else "새 대본 생성 대기 중"
        ),
        "validate": "검사 대기 중",
        "apply": "공장 적용 대기 중",
    }
    _set_generation_progress(
        draft_id,
        stage=stage,
        status="running",
        completed=0,
        total=VALIDATION_PIPELINE_TOTAL_STEPS if stage == "validate" else 1 if stage in {"story", "apply"} else 0,
        message=initial_messages.get(stage, "작업 대기 중"),
        model=model,
        job_id=job_id,
    )

    async def _runner() -> None:
        task = asyncio.current_task()
        try:
            if stage == "story":
                await generate_story_for_draft(draft_id, job_id=job_id)
            elif stage == "script":
                await generate_script_for_draft(
                    draft_id,
                    job_id=job_id,
                    mode=normalized_script_mode,
                    block_index=block_index,
                )
            elif stage == "validate":
                await _run_validate_job(draft_id, job_id)
            elif stage == "apply":
                await _run_apply_job(draft_id, job_id, target_project_id=target_project_id)
            else:
                raise ValueError(f"지원하지 않는 대본실 작업 단계입니다: {stage}")
        except asyncio.CancelledError:
            _mark_job_cancelled(draft_id, stage, job_id)
            raise
        except Exception as exc:
            _mark_job_failed(draft_id, stage, job_id, exc)
        finally:
            if _RUNNING_JOBS.get(draft_id) is task:
                _RUNNING_JOBS.pop(draft_id, None)

    _RUNNING_JOBS[draft_id] = asyncio.create_task(_runner())
    return get_draft(draft_id)


def cancel_draft_job(draft_id: str) -> dict:
    draft_id = str(draft_id or "").strip()
    meta = _load_meta(draft_id)
    stage = str(meta.get("active_stage") or (meta.get("generation_progress") or {}).get("stage") or "script")
    job_id = str(meta.get("active_job_id") or (meta.get("generation_progress") or {}).get("job_id") or "")
    meta["cancel_requested_at"] = _now_iso()
    _save_meta(meta)
    task = _RUNNING_JOBS.get(draft_id)
    if task and not task.done():
        task.cancel()
    _mark_job_cancelled(draft_id, stage, job_id or None, "작업 중지 요청 완료")
    return get_draft(draft_id)
