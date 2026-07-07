"""v1.1.34 — '딸깍 제작' 서비스.

템플릿 프로젝트 1 개를 골라 topic 만 교체한 **새 프로젝트** 를 만들고,
대본 → 음성 → 이미지 → 영상 → 최종 렌더링까지 백그라운드로 직렬 실행한다.

설계 원칙
---------
1. **격리**: FastAPI 안의 `asyncio.create_task` 로 돈다. Celery 큐에 섞이지
   않아 사용자가 Studio 에서 다른 프로젝트를 손보는 동안 영향받지 않는다.
2. **상태는 in-memory + Redis**: 태스크 메타(제목/토픽/현재 단계/에러/시작시각)
   는 모듈 전역 `_TASKS` dict 에 둔다. 컷 단위 진행 카운터는 기존
   `pipeline:step_progress:{pid}:{step}` Redis 키를 그대로 쓴다.
3. **단계 함수 재사용**: `app.tasks.pipeline_tasks._step_*` 는 sync 함수.
   v1.1.51 부터 `_run_sync_pipeline` 에서 **단일 스레드** 순차 직접 호출한다.
   run_pipeline(Celery) 과 완전히 동일한 실행 환경. 이전 개별
   `asyncio.to_thread` 래핑은 이벤트 루프 불일치(TTS/FFmpeg 에러)의 근본
   원인이어서 제거. 최종 렌더 단계는 `routers/subtitle.py` 의
   `render_video_with_subtitles` (async) 를 직접 호출.
4. **업로드 제외**: 사용자는 "최종 렌더링까지" 라고 명시했다. YouTube 업로드는
   별도 스텝에서 수동으로 돌린다.
5. **서버 재시작 복구**: oneclick 태스크는 디스크 상태를 기준으로 복원한다.
   재시작 시 in-flight 태스크는 첫 미완료 단계부터 자동으로 다시 큐에 올린다.

v1.1.38
-------
- 세밀한 진행률 노출: `current_step_completed` / `current_step_total` 을
  task dict 에 실시간 반영하여 UI 가 "N/M 컷" 을 표시할 수 있게 한다.

v1.1.42
-------
- 스케줄러(매일 HH:MM 자동 실행) 전면 삭제. 사용자 요구: "자동화 스케쥴
  삭제하고 그자리에 버튼 넣어". 딸깍은 이제 모달 팝업에서 주제/시간을
  즉시 입력해 순차 실행하는 "인스턴트" 경로만 남는다.
- `prepare_task` 가 `target_duration` 파라미터를 받아 모달의 "시간" 입력을
  새 프로젝트 config 에 반영한다.
- 클론된 딸깍 프로젝트는 `config["__oneclick__"] = True` 마커로 식별되며,
  projects.list 엔드포인트가 이 플래그가 켜진 행을 제외한다. 더이상 딸깍
  실행이 대시보드 프리셋 목록을 오염시키지 않는다.

v1.1.43
-------
- "딸깍제작 주제 입력 리스트 만들고 매일 몇시에 시작 할지 입력 할 수 있게해".
  스케줄을 다시 도입하되 **주제 큐(queue)** 형태로 재설계.
- 각 큐 항목은 `{id, topic, template_project_id, target_duration}` 를 가진다.
  주제마다 프리셋/길이 개별 지정 가능.
- 하루 1회, 사용자가 지정한 HH:MM 에 큐의 **맨 위 1건** 을 pop 해 실행.
  성공/실패 상관없이 pop on start (일회성 소비 시맨틱).
- 큐가 비면 조용히 대기 — 토글/알림 없음. 사용자가 채울 때까지 아무것도 안 함.
- 상태 영속화: `SYSTEM_DIR / oneclick_queue.json`. 프로세스 재시작에도 복원.
- 중복 발화 방지: `last_run_date` (YYYY-MM-DD) 를 저장해 같은 날 두 번
  안 돌게 한다. 서버가 09:00 에 죽었다가 09:30 에 올라와도 오늘 아직 안
  돌았으면 catch-up 으로 즉시 발화.
- 즉시 실행 팝업(v1.1.42) 은 제거. 모달은 이제 큐 편집기 역할만 한다.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import re
import shutil
import subprocess
import time
import traceback
import threading
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

if os.name == "nt":
    import msvcrt

from app.config import (
    BASE_DIR,
    DATA_DIR,
    SYSTEM_DIR,
    RESULT_ARCHIVE_DIR,
    parse_v3_oneclick_project_id,
    resolve_project_dir,
    get_channel_projects_root,
)
from app.models.database import SessionLocal
from app.models.api_log import ApiLog
from app.models.cut import Cut
from app.models.project import Project
from app.models.scheduled_episode import ScheduledEpisode
from app.services.estimation_service import estimate_project
from app.services.oneclick_queue_normalizer import normalize_queue_state
from app.services.oneclick_stability_helpers import (
    is_immediate_queue_item as _is_immediate_queue_item,
    is_active_queue_status as _is_active_queue_status,
    is_terminal_queue_status as _is_terminal_queue_status,
    normalized_queue_status as _normalized_queue_status,
    queue_item_channel as _helper_queue_item_channel,
    sort_queue_items_for_execution,
    task_progress_signature as _task_progress_signature,
    task_rank_for_project_dedupe as _task_rank_for_project_dedupe,
)
from app.services.title_utils import coerce_episode_number, shorts_upload_title, strong_main_upload_title, with_episode_prefix, without_episode_prefix
from app.services.youtube_metadata import expand_tags, format_description, recommended_shorts_title_hashtags

# v1.1.52: pipeline_tasks 의 _redis_get 을 사용 — 인메모리 fallback 포함이라
# Redis 없어도 같은 프로세스 내에서 진행률을 정확히 읽는다.
from app.tasks.pipeline_tasks import _redis_get, _redis_delete, run_async, PipelineCancelled


# --------------------------------------------------------------------------- #
# Task registry
# --------------------------------------------------------------------------- #

# task_id → dict[str, Any]
_TASKS: dict[str, dict[str, Any]] = {}
_STATE_LOADED = False

# v1.1.52: 태스크 상태 영속화 — 서버 재시작 후에도 실패/취소 태스크를 복원해서
# "이어서 하기" 가능하게 한다. running 중이던 태스크는 "interrupted" 로 표시.
_TASKS_FILE = SYSTEM_DIR / "oneclick_tasks.json"
_TASKS_SAVE_LOCK = threading.RLock()
_QUEUE_RECOVER_LOCK = threading.RLock()
_TASKS_FILE_MTIME_NS = 0
_TASKS_FILE_OWN_SAVE_MTIME_NS = 0
_EXTERNALLY_MANAGED_TASK_IDS: set[str] = set()
_EXTERNAL_TASK_LAST_SEEN: dict[str, float] = {}

try:
    _EXTERNAL_TASK_HEARTBEAT_SECONDS = float(os.getenv("ONECLICK_EXTERNAL_TASK_HEARTBEAT_SECONDS", "1800"))
except (TypeError, ValueError):
    _EXTERNAL_TASK_HEARTBEAT_SECONDS = 1800.0

try:
    ONECLICK_LOG_RETENTION_HOURS = float(os.getenv("ONECLICK_LOG_RETENTION_HOURS", "36"))
except (TypeError, ValueError):
    ONECLICK_LOG_RETENTION_HOURS = 36.0
ONECLICK_LOG_RETENTION_SECONDS = max(3600.0, ONECLICK_LOG_RETENTION_HOURS * 3600.0)


def _project_storage_exists(project_id: str, config: Optional[dict] = None) -> bool:
    """현재 저장소 기준으로 프로젝트 폴더가 실제 존재하는지 확인한다."""
    pid = str(project_id or "").strip()
    if not pid:
        return False
    try:
        cfg = dict(config or {}) if isinstance(config, dict) else {}
        if not cfg.get("result_dir"):
            project = _load_project(pid)
            project_cfg = dict(project.config or {}) if project and isinstance(project.config, dict) else {}
            if project_cfg:
                project_cfg.update(cfg)
                cfg = project_cfg
        return resolve_project_dir(pid, config=cfg, create=False).exists()
    except Exception:
        return False


def _sync_queue_items_from_tasks_for_save(*, save: bool = True) -> bool:
    """Keep queue rows aligned with linked task status without starting work."""
    if "_QUEUE" not in globals():
        return False
    queue_file = globals().get("_QUEUE_FILE")
    if not globals().get("_STATE_LOADED", False) and queue_file is not None:
        try:
            if queue_file.exists():
                return False
        except Exception:
            return False
    items = list((_QUEUE or {}).get("items") or [])

    changed = False
    next_items: list[dict[str, Any]] = []
    for raw in items:
        item = dict(raw or {})
        item_status = _normalized_queue_status(item.get("status"))
        task = None
        tid = str(item.get("task_id") or "").strip()
        pid = str(item.get("project_id") or "").strip()
        if tid:
            task = _TASKS.get(tid)
        if task is None and pid:
            task = next((t for t in _TASKS.values() if str(t.get("project_id") or "") == pid), None)

        if task is None:
            if _is_terminal_queue_status(item_status):
                changed = True
                continue
            if _is_active_queue_status(item_status):
                item["status"] = "pending"
                for key in ("task_id", "project_id", "source_project_id", "result_dir", "title", "started_at", "finished_at"):
                    item.pop(key, None)
                changed = True
            if item.get("queued_note") in ("실행 중", "YouTube 업로드 쿼터 대기"):
                item["queued_note"] = "대기"
                changed = True
            next_items.append(item)
            continue

        if not _task_matches_queue_item(task, item, None):
            for key in ("task_id", "project_id", "source_project_id", "result_dir", "title", "started_at", "finished_at"):
                if key in item:
                    item.pop(key, None)
                    changed = True
            if item_status != "pending":
                item["status"] = "pending"
                changed = True
            if item.get("queued_note") in (None, "", "실행 중", "YouTube 업로드 쿼터 대기"):
                item["queued_note"] = "대기"
                changed = True
            next_items.append(item)
            continue

        task_id_for_status = str(task.get("task_id") or tid).strip()
        status = str(task.get("status") or "").strip().lower()
        if _is_terminal_queue_status(status):
            changed = True
            continue
        queue_status = "running" if _is_active_queue_status(status) else "pending"

        linked = {
            "status": queue_status,
            "task_id": task_id_for_status,
            "project_id": str(task.get("project_id") or pid),
            "source_project_id": str(task.get("source_project_id") or task.get("template_project_id") or ""),
            "result_dir": str(task.get("result_dir") or ""),
            "title": str(task.get("title") or ""),
            "started_at": str(task.get("started_at") or item.get("started_at") or ""),
        }
        if item.get("finished_at") not in (None, ""):
            item.pop("finished_at", None)
            changed = True
        desired_queue_note = "실행 중" if queue_status == "running" else "대기"
        if queue_status == "running" and item.get("queued_note") != desired_queue_note:
            item["queued_note"] = desired_queue_note
            changed = True
        if queue_status != "running" and item.get("queued_note") in (None, "", "실행 중", "YouTube 업로드 쿼터 대기"):
            item["queued_note"] = "대기"
            changed = True
        for key, value in linked.items():
            if value and item.get(key) != value:
                item[key] = value
                changed = True
        next_items.append(item)

    active_identities: set[str] = set()
    for item in next_items:
        active_identities.update(_queue_item_identity_values(item))

    for task in list(_TASKS.values()):
        status = str(task.get("status") or "").strip().lower()
        if status not in ("running", "queued", "prepared"):
            continue
        task_id_for_status = str(task.get("task_id") or "").strip()
        queue_status = "running" if _is_active_queue_status(status) else "pending"
        task_identity = {
            f"task_id:{task_id_for_status}",
            f"project_id:{str(task.get('project_id') or '').strip()}",
            f"result_dir:{str(task.get('result_dir') or '').strip()}",
        }
        task_identity = {value for value in task_identity if not value.endswith(":")}
        if task_identity & active_identities:
            continue
        task_queue_item = _queue_item_from_v3_task(task) or {}
        topic = str(task_queue_item.get("topic") or task.get("topic") or task.get("title") or "").strip()
        if not topic:
            continue
        try:
            ch = int(task_queue_item.get("channel") or task.get("channel") or 1)
        except Exception:
            ch = 1
        try:
            ep = int(task_queue_item.get("episode_number") or task.get("episode_number") or 0)
        except Exception:
            ep = 0
        item = {
            "id": f"task-{str(task.get('task_id') or uuid.uuid4().hex[:8])}",
            "topic": topic,
            "template_project_id": task_queue_item.get("template_project_id") or task.get("template_project_id") or task.get("source_project_id") or None,
            "target_duration": task_queue_item.get("target_duration") or ONECLICK_MAIN_TARGET_DURATION,
            "target_cuts": task_queue_item.get("target_cuts") or ONECLICK_MAIN_CUT_COUNT,
            "channel": ch if ch in CHANNELS else 1,
            "openings": task_queue_item.get("openings") if isinstance(task_queue_item.get("openings"), list) else [],
            "endings": task_queue_item.get("endings") if isinstance(task_queue_item.get("endings"), list) else [],
            "core_content": str(task_queue_item.get("core_content") or ""),
            "episode_number": ep if ep > 0 else None,
            "series": str(task_queue_item.get("series") or task.get("series") or ""),
            "episode_code": str(task_queue_item.get("episode_code") or task.get("episode_code") or ""),
            "episode_id": str(task_queue_item.get("episode_id") or task.get("episode_id") or task_queue_item.get("episode_code") or task.get("episode_code") or ""),
            "next_episode_preview": str(task_queue_item.get("next_episode_preview") or ""),
            "queued_source": "system",
            "queued_at": str(task.get("created_at") or task.get("started_at") or "") or None,
            "queued_note": "실행 중" if queue_status == "running" else "대기",
            "requeued_from_task_id": "",
            "restored_from_project_id": "",
            "status": queue_status,
            "task_id": task_id_for_status,
            "project_id": str(task.get("project_id") or ""),
            "source_project_id": str(task.get("source_project_id") or task.get("template_project_id") or ""),
            "result_dir": str(task.get("result_dir") or ""),
            "title": str(task.get("title") or ""),
            "started_at": str(task.get("started_at") or ""),
        }
        next_items.append(item)
        active_identities.update(_queue_item_identity_values(item))
        changed = True

    if changed:
        _QUEUE["items"] = next_items
    if changed and save:
        try:
            saver = globals().get("_save_queue_to_disk")
            if callable(saver):
                saver()
            elif "_QUEUE_FILE" in globals():
                _QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
                _QUEUE_FILE.write_text(
                    json.dumps(_QUEUE, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
        except Exception as e:
            print(f"[oneclick.queue] task sync save failed: {e}")
    return changed


def _save_tasks_to_disk() -> None:
    """_TASKS 를 JSON 으로 영속화. running 태스크 중단 감지를 위해 상태 보존."""
    global _TASKS_FILE_MTIME_NS, _TASKS_FILE_OWN_SAVE_MTIME_NS
    try:
        with _TASKS_SAVE_LOCK:
            _sync_queue_items_from_tasks_for_save()
            _TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
            for task in _TASKS.values():
                if isinstance(task, dict):
                    _prune_task_logs_for_retention(task)
            items = list(_TASKS.items())
            recent_task_ids = {tid for tid, _task in items[-50:]}
            recent = {
                tid: task
                for tid, task in items
                if tid in recent_task_ids or _task_within_log_retention(task)
            }
            _TASKS_FILE.write_text(
                json.dumps(recent, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            try:
                _TASKS_FILE_MTIME_NS = _TASKS_FILE.stat().st_mtime_ns
                _TASKS_FILE_OWN_SAVE_MTIME_NS = _TASKS_FILE_MTIME_NS
            except OSError:
                pass
    except Exception as e:
        print(f"[oneclick] tasks save failed: {e}")


def _dedupe_tasks_by_project_id() -> bool:
    """Keep exactly one OneClick task per project_id.

    Failed/orphan recovery can be triggered repeatedly from the UI. The project
    folder is the unit of work, so duplicate task rows for the same project must
    be collapsed before the UI lists or resumes them.
    """
    global _TASKS
    best_by_pid: dict[str, tuple[str, dict[str, Any]]] = {}
    changed = False

    for tid, task in list(_TASKS.items()):
        pid = str(task.get("project_id") or "").strip()
        if not pid:
            continue
        current = best_by_pid.get(pid)
        if current is None:
            best_by_pid[pid] = (tid, task)
            continue
        keep_tid, keep_task = current
        if _task_rank_for_project_dedupe(task) >= _task_rank_for_project_dedupe(keep_task):
            best_by_pid[pid] = (tid, task)
            changed = True
        else:
            changed = True

    if not changed:
        return False

    keep_ids = {tid for tid, _task in best_by_pid.values()}
    for tid in list(_TASKS.keys()):
        task = _TASKS.get(tid) or {}
        pid = str(task.get("project_id") or "").strip()
        if pid and tid not in keep_ids:
            _TASKS.pop(tid, None)
            active = _ACTIVE_RUNS.pop(tid, None)
            if active is not None and not active.done():
                try:
                    active.cancel()
                except Exception:
                    pass
    return True


def _task_work_key(task: dict[str, Any]) -> str:
    pid = str(task.get("project_id") or "").strip()
    if parse_v3_oneclick_project_id(pid):
        return ""
    topic = str(task.get("topic") or "").strip().casefold()
    if not topic:
        return ""
    try:
        channel = str(int(task.get("channel") or 0))
    except (TypeError, ValueError):
        channel = "0"
    config = task.get("config") if isinstance(task.get("config"), dict) else {}
    template = str(task.get("template_project_id") or config.get("template_project_id") or "").strip()
    return f"{channel}|{template}|{topic}"


def _project_work_key(project: Project, config: dict[str, Any]) -> str:
    if parse_v3_oneclick_project_id(project.id or ""):
        return ""
    topic = str(project.topic or "").strip().casefold()
    if not topic:
        return ""
    try:
        channel = str(int(config.get("channel") or 0))
    except (TypeError, ValueError):
        channel = "0"
    template = str(config.get("template_project_id") or "").strip()
    return f"{channel}|{template}|{topic}"


def _dedupe_tasks_by_work_key() -> bool:
    """Keep one task for one channel/template/topic work item."""
    global _TASKS
    best_by_key: dict[str, tuple[str, dict[str, Any]]] = {}
    changed = False

    for tid, task in list(_TASKS.items()):
        key = _task_work_key(task)
        if not key:
            continue
        current = best_by_key.get(key)
        if current is None:
            best_by_key[key] = (tid, task)
            continue
        keep_tid, keep_task = current
        if _task_rank_for_project_dedupe(task) >= _task_rank_for_project_dedupe(keep_task):
            best_by_key[key] = (tid, task)
            changed = True
        else:
            changed = True

    if not changed:
        return False

    keep_ids = {tid for tid, _task in best_by_key.values()}
    for tid in list(_TASKS.keys()):
        task = _TASKS.get(tid) or {}
        key = _task_work_key(task)
        if key and tid not in keep_ids:
            pid = str(task.get("project_id") or "").strip()
            status = str(task.get("status") or "")
            _TASKS.pop(tid, None)
            active = _ACTIVE_RUNS.pop(tid, None)
            if active is not None and not active.done():
                try:
                    active.cancel()
                except Exception:
                    pass
            if pid and status not in ("running", "queued"):
                try:
                    _cleanup_project_files(pid, task.get("config") if isinstance(task.get("config"), dict) else None)
                    _delete_project_db_record(pid)
                    print(f"[oneclick] removed duplicate work project: {pid}")
                except Exception as e:
                    print(f"[oneclick] duplicate work cleanup failed ({pid}): {e}")
    return True


def _dedupe_tasks() -> bool:
    changed_project = _dedupe_tasks_by_project_id()
    changed_work = _dedupe_tasks_by_work_key()
    return changed_project or changed_work


def _restart_resume_step(task: dict[str, Any]) -> int:
    """Return the step that should be retried after backend/ComfyUI restart."""
    current_step = task.get("current_step")
    try:
        if current_step:
            return int(current_step)
    except (TypeError, ValueError):
        pass
    for _slug, step_num, _label in STEP_ORDER:
        if (task.get("step_states") or {}).get(str(step_num)) != "completed":
            return int(step_num)
    return 2


def _prepare_inflight_task_for_restart(task: dict[str, Any]) -> bool:
    """Convert a persisted in-flight task into a queued resume task."""
    status = str(task.get("status") or "")
    if status not in ("running", "queued", "prepared"):
        return False
    project_id = str(task.get("project_id") or "").strip()
    if project_id and _complete_task_from_existing_upload(
        task,
        project_id,
        task.get("config") if isinstance(task.get("config"), dict) else None,
        log_prefix="서버 재시작 복구 중 기존 YouTube URL 확인",
    ):
        return True
    resume_step = _restart_resume_step(task)
    step_states = dict(task.get("step_states") or {})
    for _slug, step_num, _label in STEP_ORDER:
        key = str(step_num)
        if step_num >= resume_step and step_states.get(key) in ("running", "in_progress", "failed", "cancelled"):
            step_states[key] = "pending"
    task["step_states"] = step_states
    task["status"] = "queued"
    task["error"] = None
    task["finished_at"] = None
    task["resume_from_step"] = resume_step
    task["current_step"] = None
    task["current_step_name"] = None
    task["current_step_label"] = None
    task["current_step_progress_text"] = None
    task["current_step_cut_progress_pct"] = None
    task["sub_status"] = None
    project_id = str(task.get("project_id") or "").strip()
    if project_id:
        try:
            _reset_project_steps_for_resume(project_id, resume_step)
        except Exception as e:
            print(f"[oneclick] project resume state reset failed: {e}")
    _add_log(task, f"↻ 서버 재시작 복구: Step {resume_step}부터 자동 재개 대기", "warn")
    return True


def _tasks_file_mtime_ns() -> int:
    try:
        return int(_TASKS_FILE.stat().st_mtime_ns)
    except OSError:
        return 0


def _tasks_file_age_seconds() -> float:
    try:
        return max(0.0, time.time() - float(_TASKS_FILE.stat().st_mtime))
    except OSError:
        return 999999.0


def _remember_external_task(task_id: str, task: dict[str, Any]) -> None:
    tid = str(task_id or task.get("task_id") or "").strip()
    if not tid:
        return
    status = str(task.get("status") or "").strip().lower()
    runner = _ACTIVE_RUNS.get(tid)
    if status == "running" and (runner is None or runner.done()):
        _EXTERNALLY_MANAGED_TASK_IDS.add(tid)
        _EXTERNAL_TASK_LAST_SEEN[tid] = time.monotonic()
        return
    _EXTERNALLY_MANAGED_TASK_IDS.discard(tid)
    _EXTERNAL_TASK_LAST_SEEN.pop(tid, None)


def _is_externally_managed_task(task_id: str, task: Optional[dict[str, Any]] = None) -> bool:
    tid = str(task_id or (task or {}).get("task_id") or "").strip()
    if not tid or tid not in _EXTERNALLY_MANAGED_TASK_IDS:
        return False
    current = task or _TASKS.get(tid) or {}
    if str(current.get("status") or "").strip().lower() != "running":
        _EXTERNALLY_MANAGED_TASK_IDS.discard(tid)
        _EXTERNAL_TASK_LAST_SEEN.pop(tid, None)
        return False
    runner = _ACTIVE_RUNS.get(tid)
    if runner is not None and not runner.done():
        _EXTERNALLY_MANAGED_TASK_IDS.discard(tid)
        _EXTERNAL_TASK_LAST_SEEN.pop(tid, None)
        return False
    last_seen = float(_EXTERNAL_TASK_LAST_SEEN.get(tid) or 0.0)
    if last_seen and time.monotonic() - last_seen <= _EXTERNAL_TASK_HEARTBEAT_SECONDS:
        return True
    _EXTERNALLY_MANAGED_TASK_IDS.discard(tid)
    _EXTERNAL_TASK_LAST_SEEN.pop(tid, None)
    return False


def _should_preserve_loaded_external_task(task_id: str, task: dict[str, Any]) -> bool:
    if str(task.get("status") or "").strip().lower() != "running":
        return False
    if _tasks_file_age_seconds() > _EXTERNAL_TASK_HEARTBEAT_SECONDS:
        return False
    _remember_external_task(task_id, task)
    return True


def _refresh_tasks_from_disk_if_newer() -> bool:
    """Merge task progress written by an external runner into this API process."""
    global _TASKS_FILE_MTIME_NS
    try:
        mtime_ns = _tasks_file_mtime_ns()
        if not mtime_ns or mtime_ns <= _TASKS_FILE_MTIME_NS:
            return False
        raw = json.loads(_TASKS_FILE.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return False
        changed = False
        for tid, task in raw.items():
            if not isinstance(task, dict):
                continue
            if not _project_storage_exists(task.get("project_id"), task.get("config")):
                continue
            runner = _ACTIVE_RUNS.get(str(tid))
            if runner is not None and not runner.done():
                continue
            if _TASKS.get(tid) != task:
                _TASKS[tid] = task
                changed = True
            _remember_external_task(str(tid), task)
        for tid in list(_EXTERNALLY_MANAGED_TASK_IDS):
            if tid not in raw:
                _EXTERNALLY_MANAGED_TASK_IDS.discard(tid)
                _EXTERNAL_TASK_LAST_SEEN.pop(tid, None)
        _TASKS_FILE_MTIME_NS = mtime_ns
        return changed
    except Exception as e:
        print(f"[oneclick] external task state refresh skipped: {e}")
        return False


def _load_tasks_from_disk() -> None:
    """서버 시작 시 이전 태스크 복원. in-flight 작업은 queued 로 자동 재개."""
    global _TASKS, _TASKS_FILE_MTIME_NS
    try:
        if not _TASKS_FILE.exists():
            print("[oneclick] task state file not found; orphan recovery skipped")
            return
        raw = json.loads(_TASKS_FILE.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            print("[oneclick] invalid task state file; orphan recovery skipped")
            return
        skipped_missing = 0
        for tid, task in raw.items():
            if not isinstance(task, dict):
                continue
            if not _project_storage_exists(task.get("project_id"), task.get("config")):
                skipped_missing += 1
                continue
            # running/queued 상태였으면 서버가 중간에 죽은 것 — 실패로 끝내지 않고
            # 실제 산출물 기준으로 첫 미완료 단계부터 자동 재개한다.
            if task.get("status") in ("running", "queued", "prepared"):
                _reconcile_task_outputs(task, clear_terminal_cursor=True, cleanup_broken=False)
                if not _should_preserve_loaded_external_task(tid, task):
                    _prepare_inflight_task_for_restart(task)
            elif task.get("status") == "uploading":
                pass
            elif task.get("status") in ("failed", "cancelled", "paused", "completed"):
                _reconcile_task_outputs(task, clear_terminal_cursor=True, cleanup_broken=False)
                _restore_executed_models_from_logs(task)
            _TASKS[tid] = task
        if _dedupe_tasks() or skipped_missing:
            _save_tasks_to_disk()
        print(f"[oneclick] restored tasks: {len(_TASKS)}")
        if skipped_missing:
            print(f"[oneclick] dropped missing-storage tasks: {skipped_missing}")
            _save_tasks_to_disk()
        # 고아 프로젝트는 조회 화면 진입만으로 태스크를 되살리지 않는다.
        # 사용자가 복구 버튼/고아 프로젝트 API 를 명시적으로 눌렀을 때만 처리한다.
        _TASKS_FILE_MTIME_NS = _tasks_file_mtime_ns()
    except Exception as e:
        print(f"[oneclick] tasks load failed: {e}")


def _recover_orphaned_projects() -> None:
    """v1.1.56: DB 에서 __oneclick__ 프로젝트 중 _TASKS 에 없는 것을 자동 복구.

    서버 재시작 시 자동 호출. 태스크 JSON 에서 유실된 딸깍 프로젝트를
    디스크 파일 기반으로 감지해서 태스크 목록에 다시 추가한다.
    """
    known_pids = {t.get("project_id") for t in _TASKS.values()}
    try:
        db = SessionLocal()
        try:
            # __oneclick__ 마커가 있는 프로젝트만 조회
            from sqlalchemy import text as sql_text
            candidates = (
                db.query(Project)
                .filter(Project.id.like("딸깍_%"))
                .order_by(Project.created_at.desc())
                .limit(100)
                .all()
            )
        finally:
            db.close()

        recovered = 0
        for proj in candidates:
            if proj.id in known_pids:
                continue
            # config 에 __oneclick__ 확인
            cfg = dict(proj.config or {})
            if not cfg.get("__oneclick__"):
                continue
            if not _project_storage_exists(proj.id, cfg):
                continue

            # v1.2.28: "완료된 스텝 0개면 무시" 규칙 삭제.
            # 이유: 사용자가 "이미지 삭제" 등으로 출력 파일을 비우면 detected 가
            # 전부 pending 이 된다. 이 상태에서 서버 재시작이 일어나면 해당
            # 프로젝트가 _TASKS 에서 영구적으로 사라져 "복구 하고 다른 페이지
            # 다녀오니까 없어졌다" 증상이 발생. 이제는 __oneclick__ 마커만
            # 있으면 실패 상태로 되살려, 사용자가 실패/취소 섹션에서 보고
            # 재실행/복귀/삭제 할 수 있게 한다. 정말로 비어있는 테스트
            # 프로젝트가 섞여 나올 수는 있지만, 그건 "선택 N건 삭제" 로 쓸어
            # 담게 한다 (사용자 요구 우선: "계속 없어지자나").
            detected, _counts, _total, _removed = _cleanup_and_detect_completed_steps(proj.id, cfg)

            # 태스크 레코드 생성
            task_id = str(uuid.uuid4())[:8]
            estimate = estimate_project(cfg)
            task = _make_task_record(
                task_id,
                template_project_id=cfg.get("template_project_id"),
                project_id=proj.id,
                topic=proj.topic or "",
                title=proj.title or "",
                estimate=estimate,
                config=cfg,
            )
            task["config"] = cfg
            if cfg.get("result_dir"):
                task["result_dir"] = str(cfg.get("result_dir"))
            task["step_states"] = detected

            # total_cuts 복원
            script_path = resolve_project_dir(proj.id, cfg) / "script.json"
            if script_path.exists():
                try:
                    script = json.loads(script_path.read_text(encoding="utf-8"))
                    task["total_cuts"] = len(script.get("cuts", []))
                except Exception:
                    pass

            # 첫 번째 미완료 스텝
            first_pending = None
            for _slug, step_num, _label in STEP_ORDER:
                if detected.get(str(step_num)) != "completed":
                    first_pending = step_num
                    break

            all_done = all(v == "completed" for v in detected.values())
            task["status"] = "completed" if all_done else "failed"
            task["error"] = None if all_done else "태스크 복구됨 — 이어서 하기를 눌러주세요"
            task["finished_at"] = _utcnow_iso() if all_done else None
            if first_pending:
                task["resume_from_step"] = first_pending

            _TASKS[task_id] = task
            recovered += 1
            completed_labels = [
                label for _slug, sn, label in STEP_ORDER
                if detected.get(str(sn)) == "completed"
            ]
            print(
                f"[oneclick] recovered orphan project "
                f"(completed_steps={len(completed_labels)}, "
                f"next_step={first_pending or 'done'})"
            )

        if recovered > 0:
            _save_tasks_to_disk()
        print(f"[oneclick] recovered orphan projects: {recovered}")
    except Exception as e:
        print(f"[oneclick] orphan recovery failed: {e}")
        import traceback
        traceback.print_exc()


def _normalize_uploaded_title(title: str) -> str:
    """유튜브 업로드 제목 비교용 정규화."""
    text = unicodedata.normalize("NFKC", str(title or "")).lower().strip()
    if not text:
        return ""
    text = (
        text.replace("’", "'")
        .replace("‘", "'")
        .replace("“", '"')
        .replace("”", '"')
        .replace("—", "-")
        .replace("–", "-")
    )
    text = re.sub(r"^ep\.\s*\d+\s*[째-]?\s*", "", text)
    return "".join(ch for ch in text if ch.isalnum())


def _project_has_uploaded_video(project: Optional[Project]) -> bool:
    if not project:
        return False
    return bool(_youtube_video_id_from_url(project.youtube_url))


def _project_upload_step_complete(project: Optional[Project], config: Optional[dict[str, Any]] = None) -> bool:
    if not _project_has_uploaded_video(project):
        return False
    cfg = dict(config or getattr(project, "config", None) or {})
    shorts_state = _shorts_upload_completion(str(getattr(project, "id", "") or ""), cfg)
    return not (shorts_state.get("enabled") and not shorts_state.get("complete"))


def _mark_project_uploaded(db, project: Project) -> bool:
    """본편과 필수 쇼츠 업로드가 확인된 프로젝트를 완료 상태로 맞춘다."""
    if not _project_upload_step_complete(project, dict(project.config or {})):
        return False

    changed = False
    states = dict(project.step_states or {})
    if project.status != "completed":
        project.status = "completed"
        changed = True
    if (project.current_step or 0) < 7:
        project.current_step = 7
        changed = True
    if states.get("7") != "completed":
        states["7"] = "completed"
        project.step_states = states
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(project, "step_states")
        changed = True
    return changed


def _mark_task_completed(task: dict[str, Any], detected_states: dict[str, str]) -> bool:
    """프로젝트가 이미 업로드 완료라면 딸깍 task 도 완료 상태로 승격."""
    changed = False
    total_cuts = int(task.get("total_cuts") or 0)

    if task.get("step_states") != detected_states:
        task["step_states"] = detected_states
        changed = True

    if total_cuts > 0:
        done_map = dict(task.get("completed_cuts_by_step") or {})
        for step in ("2", "3", "4", "5"):
            target = total_cuts if detected_states.get(step) == "completed" else done_map.get(step, 0)
            if done_map.get(step) != target:
                done_map[step] = target
                changed = True
        task["completed_cuts_by_step"] = done_map

    if task.get("status") != "completed":
        task["status"] = "completed"
        changed = True
    if task.get("error") is not None:
        task["error"] = None
        changed = True
    if task.get("progress_pct") != 100.0:
        task["progress_pct"] = 100.0
        changed = True
    if task.get("current_step") is not None:
        task["current_step"] = None
        changed = True
    if task.get("current_step_name") is not None:
        task["current_step_name"] = None
        changed = True
    if task.get("sub_status") is not None:
        task["sub_status"] = None
        changed = True
    if task.get("current_step_completed") not in (None, 0):
        task["current_step_completed"] = 0
        changed = True
    if task.get("current_step_total") not in (None, 0):
        task["current_step_total"] = 0
        changed = True
    if task.get("current_step_label") is not None:
        task["current_step_label"] = None
        changed = True
    if task.get("current_step_progress_text") is not None:
        task["current_step_progress_text"] = None
        changed = True
    if task.get("current_step_cut_progress_pct") is not None:
        task["current_step_cut_progress_pct"] = None
        changed = True
    if task.get("current_step_active_cut") is not None:
        task["current_step_active_cut"] = None
        changed = True
    if task.get("_existing_upload_missing_shorts_log_key") is not None:
        task.pop("_existing_upload_missing_shorts_log_key", None)
        changed = True
    if task.get("resume_from_step") is not None:
        task.pop("resume_from_step", None)
        changed = True
    if not task.get("finished_at"):
        task["finished_at"] = _utcnow_iso()
        changed = True

    return changed


def _reconcile_tasks_from_project_state() -> None:
    """서버 재시작 후 stale 한 실패 task 를 실제 project 상태와 다시 맞춘다.

    핵심 목적:
    - project.youtube_url 과 project.step_states["7"] 완료 기록이 모두 있는 항목만
      task 도 completed 로 승격
    """
    if not _TASKS:
        return

    project_ids = sorted({
        str(t.get("project_id") or "").strip()
        for t in _TASKS.values()
        if str(t.get("project_id") or "").strip()
    })
    if not project_ids:
        return

    db = SessionLocal()
    try:
        projects = (
            db.query(Project)
            .filter(Project.id.in_(project_ids))
            .all()
        )
        projects_by_id = {p.id: p for p in projects}

        project_changed = False
        for project in projects:
            if _mark_project_uploaded(db, project):
                project_changed = True

        if project_changed:
            db.commit()

        task_changed = False
        for task in _TASKS.values():
            if task.get("status") in ("failed", "cancelled", "completed"):
                if _clear_runtime_cursor(task):
                    task_changed = True
            if task.get("status") in ("running", "queued", "prepared"):
                continue
            pid = str(task.get("project_id") or "").strip()
            if not pid:
                continue
            project = projects_by_id.get(pid)
            if not _project_upload_step_complete(project, dict((project.config if project else None) or {})):
                continue

            detected = _detect_completed_steps(pid, dict((project.config if project else None) or {}))
            if detected.get("7") != "completed":
                detected["7"] = "completed"
            if _mark_task_completed(task, detected):
                task_changed = True

        if task_changed:
            _save_tasks_to_disk()
    except Exception as e:
        print(f"[oneclick] reconcile from project state failed: {e}")
        traceback.print_exc()
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


# 동시성: 같은 프로세스에서 oneclick 여러 건이 동시에 돌면 GPU/FFmpeg 자원이
# 겹칠 수 있다. scheduler 와 동일한 보수적 정책 — 한 번에 하나만.
_RUN_LOCK = asyncio.Lock()

# v1.1.58: task_id → asyncio.Task 매핑. resume / start 가 중복으로 _run_oneclick_task
# 를 스케줄해서 _RUN_LOCK 에 영원히 갇히는 것을 막는다. 이전 인스턴스가 살아있으면
# 새로 스케줄하지 않는다(또는 끝날 때까지 짧게 기다린 뒤 새로 시작한다).
_ACTIVE_RUNS: dict[str, "asyncio.Task"] = {}
_UPLOAD_PENDING_RUN: Optional["asyncio.Task"] = None
_UPLOAD_ACTIVE_TASK_IDS: set[str] = set()
_EMERGENCY_STOP_UNTIL = 0.0
_AUTO_PRODUCTION_PAUSED_UNTIL = 0.0
_AUTO_NEXT_DELAY_SECONDS = 10
_AUTO_NEXT_DISPATCH_NOT_BEFORE = 0.0
_AUTO_NEXT_DISPATCH_TASK: Optional["asyncio.Task"] = None
_SAFETY_FILE = SYSTEM_DIR / "oneclick_safety.json"
_SAFETY_STALL_WARN_SECONDS = 480


def _emergency_stop_active() -> bool:
    return time.monotonic() < _EMERGENCY_STOP_UNTIL


def _set_emergency_stop_guard(seconds: float = 600.0) -> None:
    """Temporarily block automatic queue dispatch after a global stop.

    A user-facing "stop all" must mean no hidden scheduler/queued item can
    immediately occupy ComfyUI again while the user is trying to regain control.
    Manual start/resume paths clear this guard explicitly.
    """
    global _EMERGENCY_STOP_UNTIL
    _EMERGENCY_STOP_UNTIL = time.monotonic() + max(1.0, float(seconds))


def _clear_emergency_stop_guard() -> None:
    global _EMERGENCY_STOP_UNTIL
    _EMERGENCY_STOP_UNTIL = 0.0


def _auto_production_pause_remaining() -> int:
    return max(0, int(round(_AUTO_PRODUCTION_PAUSED_UNTIL - time.monotonic())))


def _auto_production_paused() -> bool:
    return _auto_production_pause_remaining() > 0


def get_auto_production_state() -> dict[str, Any]:
    remaining = _auto_production_pause_remaining()
    return {
        "enabled": remaining <= 0,
        "remaining_seconds": remaining,
    }


def set_auto_production_enabled(enabled: bool, pause_seconds: int = 1800) -> dict[str, Any]:
    global _AUTO_PRODUCTION_PAUSED_UNTIL
    if enabled:
        _AUTO_PRODUCTION_PAUSED_UNTIL = 0.0
    else:
        _AUTO_PRODUCTION_PAUSED_UNTIL = time.monotonic() + max(1, int(pause_seconds or 1800))
    return get_auto_production_state()


def _load_safety_state() -> dict[str, Any]:
    try:
        if _SAFETY_FILE.exists():
            return json.loads(_SAFETY_FILE.read_text(encoding="utf-8")) or {}
    except Exception:
        pass
    return {
        "status": "ok",
        "last_event": None,
        "leak_events": [],
        "stall_events": [],
    }


def _save_safety_state(state: dict[str, Any]) -> None:
    try:
        _SAFETY_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SAFETY_FILE.write_text(
            json.dumps(state, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"[oneclick.safety] save failed: {e}")


def _record_safety_event(kind: str, message: str, payload: Optional[dict[str, Any]] = None) -> None:
    state = _load_safety_state()
    event = {
        "ts": _utcnow_iso(),
        "kind": kind,
        "message": message,
        "payload": payload or {},
    }
    state["status"] = "alert" if kind in {"spend_leak", "stalled_stop"} else "ok"
    state["last_event"] = event
    key = "leak_events" if kind == "spend_leak" else "stall_events"
    rows = list(state.get(key) or [])
    rows.append(event)
    state[key] = rows[-50:]
    _save_safety_state(state)


def get_safety_state() -> dict[str, Any]:
    """Return the persisted factory safety status for the Live UI."""
    _ensure_state_loaded()
    _refresh_tasks_from_disk_if_newer()
    state = _load_safety_state()
    running = [
        {
            "task_id": t.get("task_id"),
            "project_id": t.get("project_id"),
            "title": t.get("title"),
            "current_step": t.get("current_step"),
            "current_step_name": t.get("current_step_name"),
            "safety": t.get("safety") or {},
        }
        for t in _TASKS.values()
        if t.get("status") == "running"
    ]
    return {
        "status": state.get("status") or "ok",
        "last_event": state.get("last_event"),
        "running": running,
        "auto_production": get_auto_production_state(),
    }


def _refresh_task_safety(task: dict[str, Any], *, force: bool = False) -> bool:
    """Update stall watchdog metadata. Returns True when task changed."""
    if task.get("status") != "running":
        return False
    now = time.monotonic()
    wall_now = _utcnow_iso()
    signature = _task_progress_signature(task)
    safety = task.setdefault("safety", {})
    changed = False

    if force or safety.get("signature") != signature:
        safety["signature"] = signature
        safety["last_change_monotonic"] = now
        safety["last_change_at"] = wall_now
        safety["stale_seconds"] = 0
        safety["stalled_warned"] = False
        changed = True
    else:
        last = float(safety.get("last_change_monotonic") or now)
        stale = max(0, int(now - last))
        stale_bucket = (stale // 10) * 10
        if int(safety.get("stale_seconds") or 0) != stale_bucket:
            safety["stale_seconds"] = stale_bucket
            changed = True
        try:
            step = int(task.get("current_step") or 0)
        except Exception:
            step = 0
        if stale >= _SAFETY_STALL_WARN_SECONDS and not safety.get("stalled_warned"):
            safety["stalled_warned"] = True
            _add_log(task, f"[안전장치] {stale}초 동안 진행 변화 없음", "warn")
            changed = True
    task["safety"] = safety
    return changed


def _complete_task_from_existing_upload(
    task: dict[str, Any],
    project_id: str,
    config: Optional[dict[str, Any]] = None,
    *,
    log_prefix: str = "기존 YouTube URL 확인",
) -> bool:
    project_id = str(project_id or "").strip()
    if not project_id:
        return False

    uploaded_project = _load_project(project_id)
    uploaded_url = str(getattr(uploaded_project, "youtube_url", "") or "").strip() if uploaded_project else ""
    if not _youtube_video_id_from_url(uploaded_url):
        return False

    effective_config = dict(config or getattr(uploaded_project, "config", None) or {})
    shorts_state = _shorts_upload_completion(project_id, effective_config)
    if shorts_state.get("enabled") and not shorts_state.get("complete"):
        task["youtube_url"] = uploaded_url
        key = (
            f"{project_id}:"
            f"{shorts_state.get('uploaded_count', 0)}:"
            f"{shorts_state.get('file_count', 0)}:"
            f"{shorts_state.get('required', 0)}"
        )
        if task.get("_existing_upload_missing_shorts_log_key") != key:
            _add_log(
                task,
                f"↪ {log_prefix} — 본편 URL 확인, 쇼츠 업로드 미완료로 Step 7 유지: {uploaded_url} "
                f"(쇼츠 기록 {shorts_state.get('uploaded_count', 0)}/{shorts_state.get('required', 0)})",
                "warn",
            )
            task["_existing_upload_missing_shorts_log_key"] = key
        return False

    states = dict(task.get("step_states") or {})
    states["7"] = "completed"
    task["youtube_url"] = uploaded_url
    _mark_task_completed(task, states)

    _mark_project_upload_completed(project_id, states)

    _add_log(task, f"✓ {log_prefix} — 업로드 완료 처리: {uploaded_url}")
    return True


def register_spend_record(record: dict[str, Any]) -> None:
    """Called by spend_ledger after a positive-cost API ledger append.

    If a paid record appears without a matching active OneClick task, pause
    automatic production and leave a durable alert. This is the guard for
    "UI says no job, but credits keep moving".
    """
    try:
        amount = float(record.get("amount_usd") or 0.0)
    except Exception:
        amount = 0.0
    if amount <= 0:
        return

    _ensure_state_loaded()
    project_id = str(record.get("project_id") or "").strip()
    matching = [
        t for t in _TASKS.values()
        if t.get("status") in ("running", "queued", "prepared")
        and (not project_id or str(t.get("project_id") or "") == project_id)
    ]
    if matching:
        return
    if project_id:
        try:
            db = SessionLocal()
            try:
                project = db.query(Project).filter(Project.id == project_id).first()
                if project and str(project.status or "").lower() in {"processing", "running", "queued"}:
                    cfg = dict(project.config or {})
                    if resolve_project_dir(project_id, config=cfg, create=False).exists():
                        return
            finally:
                db.close()
        except Exception:
            pass

    msg = (
        "[안전장치] 실행 중인 OneClick 작업이 없는데 API 비용 기록이 발생했습니다. "
        "자동제작을 30분간 중지했습니다."
    )
    set_auto_production_enabled(False, pause_seconds=1800)
    _set_emergency_stop_guard(1800)
    if project_id:
        try:
            from app.tasks.pipeline_tasks import _redis_set
            _redis_set(f"pipeline:cancel:{project_id}", "1")
        except Exception:
            pass
        try:
            from app.services.cancel_ctx import mark_halted
            mark_halted(project_id)
        except Exception:
            pass
        for task in _TASKS.values():
            if str(task.get("project_id") or "") == project_id:
                _add_log(task, msg, "error")
                break
    _record_safety_event("spend_leak", msg, record)


def _auto_next_delay_remaining() -> int:
    return max(0, int(round(_AUTO_NEXT_DISPATCH_NOT_BEFORE - time.monotonic())))


def _auto_next_delay_active() -> bool:
    return _auto_next_delay_remaining() > 0


def _clear_runtime_cursor(task: dict) -> bool:
    """UI 가 보고 있는 실행 커서를 비운다."""
    changed = False
    if task.get("current_step") is not None:
        task["current_step"] = None
        changed = True
    if task.get("current_step_name") is not None:
        task["current_step_name"] = None
        changed = True
    if task.get("current_step_completed") not in (None, 0):
        task["current_step_completed"] = 0
        changed = True
    if task.get("current_step_total") not in (None, 0):
        task["current_step_total"] = 0
        changed = True
    if task.get("current_step_label") is not None:
        task["current_step_label"] = None
        changed = True
    if task.get("sub_status") is not None:
        task["sub_status"] = None
        changed = True
    return changed


def _normalize_interrupted_task(task: dict) -> bool:
    """취소/강제정지 뒤 남아 있는 running 흔적을 정리한다."""
    changed = _clear_runtime_cursor(task)
    step_states = dict(task.get("step_states") or {})
    for step_key, state in list(step_states.items()):
        if state in ("running", "in_progress"):
            step_states[step_key] = "pending"
            changed = True
    if task.get("step_states") != step_states:
        task["step_states"] = step_states
        changed = True
    return changed


def _has_live_runner(*, exclude_task_id: Optional[str] = None) -> bool:
    """실제로 돌아가는 asyncio runner 가 있는지 확인."""
    for tid, runner in list(_ACTIVE_RUNS.items()):
        if exclude_task_id is not None and tid == exclude_task_id:
            continue
        if runner is not None and not runner.done():
            return True
    return False


def _task_has_live_runner(task_id: str, task: Optional[dict[str, Any]] = None) -> bool:
    """Queue 표시 기준: 실제 asyncio runner 가 살아있는 작업만 running."""
    tid = str(task_id or "").strip()
    if not tid and task is not None:
        tid = str(task.get("task_id") or "").strip()
    if not tid:
        return False
    runner = _ACTIVE_RUNS.get(tid)
    if runner is None or runner.done():
        return False
    if task is not None and str(task.get("status") or "").lower() not in ("running", "uploading"):
        return False
    return True


def _has_running_task(*, exclude_task_id: Optional[str] = None) -> bool:
    """지금 제작 작업이 실행 중인지 확인."""
    if _has_live_runner(exclude_task_id=exclude_task_id):
        return True
    for tid, task in _TASKS.items():
        if exclude_task_id is not None and tid == exclude_task_id:
            continue
        status = str(task.get("status") or "").strip().lower()
        if status == "running":
            return True
    return False


def _has_inflight_task(*, exclude_task_id: Optional[str] = None) -> bool:
    """running/queued 제작 태스크가 이미 있으면 새 작업을 끼워 넣지 않는다."""
    if _has_running_task(exclude_task_id=exclude_task_id):
        return True
    for tid, task in _TASKS.items():
        if exclude_task_id is not None and tid == exclude_task_id:
            continue
        if task.get("status") in ("queued", "prepared"):
            return True
    return False


def _pick_next_queued_task_id(*, exclude_task_id: Optional[str] = None) -> Optional[str]:
    """가장 오래 기다린 queued 태스크 1건을 고른다."""
    waiting: list[tuple[str, str]] = []
    for tid, task in _TASKS.items():
        if exclude_task_id is not None and tid == exclude_task_id:
            continue
        if task.get("status") != "queued":
            continue
        runner = _ACTIVE_RUNS.get(tid)
        if runner is not None and not runner.done():
            continue
        waiting.append((str(task.get("created_at") or ""), tid))
    waiting.sort(key=lambda item: item[0])
    return waiting[0][1] if waiting else None


def _dispatch_next_queued_task(
    *,
    exclude_task_id: Optional[str] = None,
    respect_auto_pause: bool = True,
    respect_auto_delay: bool = True,
) -> Optional[str]:
    """현재 실행이 비었을 때 queued 1건만 다음 순서로 시작."""
    if _emergency_stop_active():
        return None
    if respect_auto_pause and _auto_production_paused():
        return None
    if respect_auto_delay and _auto_next_delay_active():
        return None
    if _has_running_task(exclude_task_id=exclude_task_id):
        return None
    next_task_id = _pick_next_queued_task_id(exclude_task_id=exclude_task_id)
    if not next_task_id:
        return None
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return None
    _schedule_oneclick_run(next_task_id)
    return next_task_id


def _dispatch_next_persisted_queue_item() -> Optional[int]:
    """현재 실행이 비었을 때 저장된 제작 큐의 다음 1건을 시작한다."""
    if _emergency_stop_active():
        return None
    if _auto_production_paused():
        return None
    if _auto_next_delay_active():
        return None
    if _has_inflight_task():
        return None
    _normalize_queue_runtime_state()
    items = list(_QUEUE.get("items") or [])
    if not items:
        return None
    if not _is_immediate_queue_item(items[0]):
        return None
    try:
        ch = _queue_item_channel(items[0])
    except Exception:
        ch = 1
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_fire_queue_for_channel(ch, "manual"))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_fire_queue_for_channel(ch, "manual"))
        finally:
            loop.close()
    return ch


def resume_recovered_inflight_tasks_on_startup() -> Optional[str]:
    """Start the first recovered queued task after backend restart."""
    _ensure_state_loaded()
    if _QUEUE_SCHEDULER_LOCK_HANDLE is None:
        return None
    if _emergency_stop_active() or _auto_next_delay_active() or _has_running_task():
        return None
    next_task_id = _pick_next_queued_task_id()
    if not next_task_id:
        return None
    task = _TASKS.get(next_task_id)
    if task:
        _add_log(task, "▶ 서버 재시작 후 자동 재개 시작", "info")
        _save_tasks_to_disk()
    _schedule_oneclick_run(next_task_id)
    return next_task_id


def _should_auto_dispatch_after_task(task: dict[str, Any] | None) -> bool:
    """렌더 완료 후 업로드 대기로 넘어간 작업은 다음 제작을 바로 연결한다."""
    if not task:
        return False
    states = dict(task.get("step_states") or {})
    if (
        str(task.get("status") or "").strip().lower() in ("completed", "upload_pending", "uploading", "upload_failed")
        and states.get("6") == "completed"
        and states.get("7") != "completed"
    ):
        return True
    return str(task.get("triggered_by") or "").strip().lower() == "manual"


# Step 2~5 는 pipeline_tasks._step_* 가 담당, Step 6 은 subtitle.render 가 담당
STEP_ORDER = [
    ("script",  2, "대본 생성"),
    ("voice",   3, "음성 생성"),
    ("image",   4, "이미지 생성"),
    ("video",   5, "영상 생성"),
    ("render",  6, "최종 렌더링"),
    ("upload",  7, "유튜브 업로드"),
]

# UI 상 단계별 "총 진행률" 기여도 (합=100).
# render 는 컷 단위 카운터가 없어 고정 15% 를 부여하고 단계 시작/끝으로만 진행.
ONECLICK_MAIN_CUT_COUNT = 150
ONECLICK_SECONDS_PER_CUT = 4.0
ONECLICK_MAIN_TARGET_DURATION = int(ONECLICK_MAIN_CUT_COUNT * ONECLICK_SECONDS_PER_CUT)


def _force_oneclick_main_length(config: dict, target_duration: Optional[int] = None) -> dict:
    """Apply OneClick clip timing and derive cut count from the configured duration."""
    config["cut_video_duration"] = ONECLICK_SECONDS_PER_CUT
    try:
        duration = int(float(target_duration if target_duration is not None else config.get("target_duration") or 0))
    except (TypeError, ValueError):
        duration = 0
    if duration <= 0:
        duration = ONECLICK_MAIN_TARGET_DURATION
    config["target_duration"] = duration
    config["target_cuts"] = max(1, math.ceil(duration / ONECLICK_SECONDS_PER_CUT))
    config["script_tts_min_sec"] = 4.0
    config["script_tts_target_sec"] = 5.0
    config["script_tts_max_sec"] = 6.0
    return config

STEP_WEIGHTS = {
    2: 5,    # 대본 — 짧은 단일 호출
    3: 18,   # 음성 — 컷 수만큼 호출
    4: 32,   # 이미지 — 가장 무거움
    5: 23,   # 영상 — ffmpeg/AI 비디오
    6: 14,   # 렌더 — concat + 자막 + 페이드
    7: 8,    # 업로드 — 썸네일 생성 + YouTube 업로드
}


def _utcnow_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _utc_age_seconds(iso_value: Any) -> Optional[float]:
    text = str(iso_value or "").strip()
    if not text:
        return None
    try:
        started = datetime.fromisoformat(text.replace("Z", "+00:00"))
        now = datetime.utcnow().replace(tzinfo=started.tzinfo)
        return max(0.0, (now - started).total_seconds())
    except Exception:
        return None


def _prune_task_logs_for_retention(task: dict) -> bool:
    logs = task.get("logs")
    if not isinstance(logs, list):
        if logs is None:
            return False
        task["logs"] = []
        return True
    kept = []
    changed = False
    for row in logs:
        if not isinstance(row, dict):
            changed = True
            continue
        age = _utc_age_seconds(row.get("ts_iso") or row.get("created_at"))
        if age is None or age <= ONECLICK_LOG_RETENTION_SECONDS:
            kept.append(row)
        else:
            changed = True
    if changed:
        task["logs"] = kept
    return changed


def _task_within_log_retention(task: dict) -> bool:
    status = str(task.get("status") or "").lower()
    if status in ("running", "queued", "prepared", "uploading", "paused"):
        return True
    logs = task.get("logs") if isinstance(task.get("logs"), list) else []
    for row in reversed(logs):
        if not isinstance(row, dict):
            continue
        age = _utc_age_seconds(row.get("ts_iso") or row.get("created_at"))
        if age is not None:
            return age <= ONECLICK_LOG_RETENTION_SECONDS
    for key in ("finished_at", "started_at", "created_at"):
        age = _utc_age_seconds(task.get(key))
        if age is not None:
            return age <= ONECLICK_LOG_RETENTION_SECONDS
    return False


def _make_task_record(
    task_id: str,
    *,
    template_project_id: Optional[str],
    project_id: str,
    topic: str,
    title: str,
    estimate: dict,
    config: Optional[dict] = None,
) -> dict:
    # v1.1.52: 각 스텝에서 사용하는 AI 모델명을 task 에 포함 — UI 표시용
    cfg = config or {}
    try:
        from app.services.video.factory import DEFAULT_VIDEO_MODEL, resolve_video_model
        video_model = resolve_video_model(cfg.get("video_model", DEFAULT_VIDEO_MODEL))
    except Exception:
        video_model = cfg.get("video_model", "")
    effective_template_project_id = (
        template_project_id
        or cfg.get("template_project_id")
        or None
    )
    models = {
        "script": cfg.get("script_model", ""),
        "tts": cfg.get("tts_model", ""),
        "tts_voice": cfg.get("tts_voice_id", ""),
        "image": cfg.get("image_model", ""),
        "video": video_model,
        # v1.1.55: 썸네일 모델 — 프론트 드롭다운 기본값 용
        "thumbnail": cfg.get("thumbnail_model", ""),
    }
    # v1.2.17: episode_number 를 task 상단에 노출. 완료/실패 목록에서 EP 배지
    # 표시에 사용된다. project.config 에 보관된 값을 그대로 승계.
    _ep_num = coerce_episode_number(cfg.get("episode_number"))
    display_title = with_episode_prefix(title, _ep_num)
    record = {
        "task_id": task_id,
        "template_project_id": effective_template_project_id,
        "source_project_id": cfg.get("source_project_id") or effective_template_project_id,
        "project_id": project_id,
        "result_dir": cfg.get("result_dir"),
        "topic": topic,
        "title": display_title,
        "episode_number": _ep_num,
        "status": "prepared",   # prepared | running | completed | failed | cancelled
        "current_step": None,
        "current_step_name": None,
        "step_states": {str(n): "pending" for _, n, _ in STEP_ORDER},
        "progress_pct": 0.0,
        "total_cuts": int(estimate.get("estimated_cuts") or 0),
        "completed_cuts_by_step": {str(n): 0 for _, n, _ in STEP_ORDER if n not in (6, 7)},
        # v1.1.38: 현재 실행 중 단계의 세부 컷 진행 상황 — UI 가 "N/M 컷" 표시.
        "current_step_completed": 0,
        "current_step_total": 0,
        "current_step_label": None,
        # v1.2.26: 실행 중 서브단계 텍스트 — 프론트 Live 페이지가 "191초 동안
        # 변화 없음" 처럼 먹통처럼 보이지 않도록, 현재 진행 중인 서브작업을
        # 실시간 노출 (예: "LLM 응답 대기 중 (0:45 경과)", "컷 3/10 호출 중",
        # "썸네일 오버레이 중"). step 이 바뀌면 None 으로 초기화된다.
        "sub_status": None,
        "estimate": estimate,
        "models": models,
        "error": None,
        "started_at": None,
        "finished_at": None,
        "created_at": _utcnow_iso(),
        "triggered_by": "manual",   # "manual" | "schedule"
        # v2.1.2: 제작 로그 — UI 에서 진행 상황/문제를 실시간 확인.
        # 각 항목: {"ts": "HH:MM:SS", "ts_iso": "...Z", "level": "info"|"warn"|"error", "msg": "..."}
        "logs": [],
    }
    raw_episode_code = str(cfg.get("episode_code") or cfg.get("episode_id") or "").strip()
    if raw_episode_code:
        record["episode_code"] = raw_episode_code
        record["episode_id"] = raw_episode_code
    series = str(cfg.get("series") or "").strip()
    if series:
        record["series"] = series
    return record


# --------------------------------------------------------------------------- #
# v2.1.2: 제작 로그 헬퍼
# --------------------------------------------------------------------------- #

def _add_log(task: dict, msg: str, level: str = "info") -> None:
    """Append a production log row and keep server-side rows for 36 hours."""
    from datetime import datetime as _dt
    now_utc = _dt.utcnow()
    logs = task.setdefault("logs", [])
    logs.append({
        "ts": _dt.now().strftime("%H:%M:%S"),
        "ts_iso": now_utc.isoformat(timespec="seconds") + "Z",
        "level": level,
        "msg": msg,
    })
    _prune_task_logs_for_retention(task)
    try:
        _refresh_task_safety(task, force=False)
    except Exception:
        pass
    _save_tasks_to_disk()


def _human_readable_failure_reason(label: str, error: Any) -> str:
    """Convert known validator errors into operator-readable Korean logs."""
    raw = str(error or "").strip()
    if not raw:
        return "알 수 없는 오류입니다."
    lower = raw.lower()

    if "script quality validation failed" in lower:
        total_match = re.search(r"invalid shorts candidate count:\s*(\d+)", raw, re.IGNORECASE)
        group_matches = re.findall(r"invalid shorts group\s+(\d+)\s+count:\s*(\d+)", raw, re.IGNORECASE)
        if total_match or group_matches:
            parts: list[str] = []
            if total_match:
                parts.append(f"전체 쇼츠 후보 {total_match.group(1)}/60개")
            for group, count in group_matches:
                parts.append(f"{group}그룹 {count}/15개")
            detail = ", ".join(parts) if parts else "쇼츠 후보 개수 불일치"
            return (
                "LLM 응답은 도착했지만 저장 전 검증에서 막혔습니다. "
                f"쇼츠 후보 개수가 규칙과 맞지 않습니다: {detail}. "
                "목표 조건은 총 60개, 4개 그룹 각각 15개이며, 최소 통과 조건은 총 45개, 3개 그룹 각각 15개입니다."
            )
        return "LLM 응답은 도착했지만 대본 품질 검증에서 막혔습니다. 원본 검증 메시지: " + raw

    if "story plan validation failed" in lower:
        return "스토리 설계 응답은 도착했지만 구조 검증에서 막혔습니다. 원본 검증 메시지: " + raw

    return f"{type(error).__name__}: {raw}" if not isinstance(error, str) else raw


def _normalize_failure_logs_for_readability(task: dict) -> bool:
    """Rewrite old technical validation log lines into readable messages."""
    logs = task.get("logs")
    if not isinstance(logs, list):
        return False
    changed = False
    for row in logs:
        if not isinstance(row, dict):
            continue
        msg = str(row.get("msg") or "")
        lower = msg.lower()
        if "script quality validation failed" not in lower and "story plan validation failed" not in lower:
            continue
        label_match = re.search(r"✗\s*(.*?)\s*실패:", msg)
        label = label_match.group(1).strip() if label_match else "작업"
        new_msg = f"✗ {label} 실패: {_human_readable_failure_reason(label, msg)}"
        if row.get("msg") != new_msg:
            row["msg"] = new_msg
            changed = True
    return changed


# --------------------------------------------------------------------------- #
# 공용 DB 헬퍼
# --------------------------------------------------------------------------- #

def _load_project(project_id: str) -> Optional[Project]:
    db = SessionLocal()
    try:
        return db.query(Project).filter(Project.id == project_id).first()
    finally:
        db.close()


def _probe_media_ok(path: Path) -> bool:
    if not path.exists() or not path.is_file() or path.stat().st_size <= 100:
        return False
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            ffprobe = str(Path(ffmpeg).with_name("ffprobe.exe"))
    if not ffprobe or not Path(ffprobe).exists():
        return True
    try:
        proc = subprocess.run(
            [
                ffprobe,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if proc.returncode != 0:
            return False
        return float((proc.stdout or "0").strip() or 0) > 0.05
    except Exception:
        return False


def _image_ok(path: Path) -> bool:
    if not path.exists() or not path.is_file() or path.stat().st_size <= 50:
        return False
    try:
        from PIL import Image
        with Image.open(path) as img:
            img.verify()
        return True
    except Exception:
        return False


def _media_file_present(path: Path, *, min_size: int = 100) -> bool:
    try:
        return path.exists() and path.is_file() and path.stat().st_size > min_size
    except Exception:
        return False


def _unlink_quiet(path: Path) -> bool:
    try:
        if path.exists() and path.is_file():
            path.unlink()
            return True
    except Exception as e:
        print(f"[oneclick] broken output delete failed: {path} ({type(e).__name__}: {e})")
    return False


def _scan_project_outputs(
    project_id: str,
    *,
    config: Optional[dict] = None,
    cleanup_broken: bool = False,
    verify_media: Optional[bool] = None,
) -> tuple[dict[str, str], dict[str, int], int, list[str]]:
    if verify_media is None:
        verify_media = cleanup_broken
    if cleanup_broken:
        verify_media = True

    project_dir = resolve_project_dir(project_id, config or {}, create=False)
    states: dict[str, str] = {}
    counts = {"2": 0, "3": 0, "4": 0, "5": 0}
    removed: list[str] = []

    script_path = project_dir / "script.json"
    script_ok = False
    cuts: list[dict[str, Any]] = []
    if script_path.exists():
        try:
            script = json.loads(script_path.read_text(encoding="utf-8"))
            raw_cuts = script.get("cuts", [])
            if isinstance(raw_cuts, list) and raw_cuts:
                cuts = [c for c in raw_cuts if isinstance(c, dict)]
                script_ok = bool(cuts)
        except Exception:
            script_ok = False

    if not script_ok:
        if cleanup_broken and script_path.exists() and _unlink_quiet(script_path):
            removed.append(str(script_path))
            for sub in ("audio", "images", "videos"):
                subdir = project_dir / sub
                if subdir.exists():
                    for f in subdir.glob("cut_*.*"):
                        if _unlink_quiet(f):
                            removed.append(str(f))
            outdir = project_dir / "output"
            if outdir.exists():
                for f in outdir.iterdir():
                    if f.is_file() and not f.name.lower().startswith("thumbnail"):
                        if _unlink_quiet(f):
                            removed.append(str(f))
        states.update({"2": "pending", "3": "pending", "4": "pending", "5": "pending", "6": "pending", "7": "pending"})
        output_dir = project_dir / "output"
        final_candidates = [
            output_dir / "final_with_subtitles.mp4",
            output_dir / "final.mp4",
            output_dir / "merged.mp4",
        ]
        if any(
            (_probe_media_ok(p) if verify_media else _media_file_present(p))
            for p in final_candidates
        ):
            states["6"] = "completed"
        db = SessionLocal()
        try:
            proj = db.query(Project).filter(Project.id == project_id).first()
            proj_states = (proj.step_states or {}) if proj else {}
            states["7"] = "completed" if _project_upload_step_complete(proj, config) else "pending"
        finally:
            db.close()
        return states, counts, 0, removed

    total_cuts = len(cuts)
    counts["2"] = total_cuts
    states["2"] = "completed"
    expected_nums: list[int] = []
    for cut in cuts:
        try:
            num = int(cut.get("cut_number") or 0)
            if num > 0:
                expected_nums.append(num)
        except (TypeError, ValueError):
            continue

    broken_audio: list[int] = []
    broken_image: list[int] = []
    broken_video: list[int] = []
    for num in expected_nums:
        audio_candidates = [
            project_dir / "audio" / f"cut_{num}.mp3",
            project_dir / "audio" / f"cut_{num:03d}.mp3",
        ]
        audio = next((p for p in audio_candidates if p.exists()), audio_candidates[0])
        image_candidates = [
            project_dir / "images" / f"cut_{num}.png",
            project_dir / "images" / f"cut_{num:03d}.png",
        ]
        image = next((p for p in image_candidates if p.exists()), image_candidates[0])
        video_candidates = [
            project_dir / "videos" / f"cut_{num}.mp4",
            project_dir / "videos" / f"cut_{num:03d}.mp4",
        ]
        video = next((p for p in video_candidates if p.exists()), video_candidates[0])

        audio_ok = _probe_media_ok(audio) if verify_media else _media_file_present(audio)
        if audio_ok:
            counts["3"] += 1
        elif audio.exists():
            broken_audio.append(num)
            if cleanup_broken and _unlink_quiet(audio):
                removed.append(str(audio))

        image_ok = _image_ok(image) if verify_media else _media_file_present(image, min_size=50)
        if image_ok:
            counts["4"] += 1
        elif image.exists():
            broken_image.append(num)
            if cleanup_broken and _unlink_quiet(image):
                removed.append(str(image))

        video_ok = _probe_media_ok(video) if verify_media else _media_file_present(video)
        if video_ok:
            counts["5"] += 1
        elif video.exists():
            broken_video.append(num)
            if cleanup_broken and _unlink_quiet(video):
                removed.append(str(video))

    states["3"] = "completed" if counts["3"] >= total_cuts else "pending"
    states["4"] = "completed" if counts["4"] >= total_cuts else "pending"
    states["5"] = "completed" if counts["5"] >= total_cuts else "pending"

    output_dir = project_dir / "output"
    final_candidates = [
        p for p in (output_dir / "final_with_subtitles.mp4", output_dir / "final.mp4")
        if p.exists()
    ]
    states["6"] = "completed" if any(
        (_probe_media_ok(p) if verify_media else _media_file_present(p))
        for p in final_candidates
    ) else "pending"
    if cleanup_broken:
        for p in final_candidates:
            if not _probe_media_ok(p) and _unlink_quiet(p):
                removed.append(str(p))
        if removed:
            merged = output_dir / "merged.mp4"
            if merged.exists() and _unlink_quiet(merged):
                removed.append(str(merged))

    db = SessionLocal()
    try:
        proj = db.query(Project).filter(Project.id == project_id).first()
        proj_states = (proj.step_states or {}) if proj else {}
        states["7"] = "completed" if _project_upload_step_complete(proj, config) else "pending"

        if cleanup_broken and (broken_audio or broken_image or broken_video):
            for num in sorted(set(broken_audio + broken_image + broken_video)):
                cut = db.query(Cut).filter(Cut.project_id == project_id, Cut.cut_number == num).first()
                if not cut:
                    continue
                if num in broken_audio:
                    cut.audio_path = None
                    cut.audio_duration = None
                    cut.audio_original_duration = None
                if num in broken_image:
                    cut.image_path = None
                    cut.image_model = None
                if num in broken_video:
                    cut.video_path = None
                    cut.video_model = None
                cut.status = "pending"
            db.commit()
    finally:
        db.close()

    return states, counts, total_cuts, removed


def _cleanup_and_detect_completed_steps(
    project_id: str,
    config: Optional[dict] = None,
) -> tuple[dict[str, str], dict[str, int], int, list[str]]:
    return _scan_project_outputs(project_id, config=config, cleanup_broken=False)


def _detect_completed_steps(project_id: str, config: Optional[dict] = None) -> dict[str, str]:
    """v1.1.52: 프로젝트 디렉토리와 DB 를 스캔해서 실제 완료된 스텝을 감지한다.

    실패/중단된 프로젝트를 재사용할 때, 이미 만들어진 생성물이 있으면
    해당 스텝을 "completed" 로 표시해서 _run_sync_pipeline 이 건너뛸 수 있게 한다.

    반환: { "2": "completed", "3": "completed", "4": "pending", ... }
    """
    states, _counts, _total, _removed = _scan_project_outputs(project_id, config=config, cleanup_broken=False)
    return states

    from app.models.cut import Cut

    project_dir = resolve_project_dir(project_id, config or {}, create=False)
    states: dict[str, str] = {}

    # Step 2 (대본): script.json 존재 + cuts 배열 비어있지 않으면 완료
    script_path = project_dir / "script.json"
    script_ok = False
    total_cuts = 0
    if script_path.exists():
        try:
            script = json.loads(script_path.read_text(encoding="utf-8"))
            cuts = script.get("cuts", [])
            if cuts and not script.get("_partial"):
                script_ok = True
                total_cuts = len(cuts)
        except Exception:
            pass
    states["2"] = "completed" if script_ok else "pending"

    if not script_ok:
        # 대본도 없으면 나머지 다 pending
        for s in ("3", "4", "5", "6", "7"):
            states[s] = "pending"
        return states

    # Step 3 (음성): audio/ 폴더에 cut_NNN.mp3 파일이 total_cuts 만큼 있으면 완료
    audio_dir = project_dir / "audio"
    audio_count = sum(1 for f in audio_dir.glob("cut_*.mp3")) if audio_dir.exists() else 0
    states["3"] = "completed" if audio_count >= total_cuts else "pending"

    # Step 4 (이미지): images/ 폴더에 cut_NNN.png 파일이 total_cuts 만큼 있으면 완료
    image_dir = project_dir / "images"
    image_count = sum(1 for f in image_dir.glob("cut_*.png")) if image_dir.exists() else 0
    states["4"] = "completed" if image_count >= total_cuts else "pending"

    # Step 5 (영상): videos/ 폴더에 cut_NNN.mp4 파일이 total_cuts 만큼 있으면 완료
    # merged.mp4 는 렌더링(Step 6) 산출물이므로 Step 5 판정에서 제외
    video_dir = project_dir / "videos"
    video_count = sum(1 for f in video_dir.glob("cut_*.mp4")) if video_dir.exists() else 0
    states["5"] = "completed" if video_count >= total_cuts else "pending"

    # Step 6 (렌더): output/final_with_subtitles.mp4 또는 output/final.mp4 존재하면 완료
    final_sub = project_dir / "output" / "final_with_subtitles.mp4"
    final_old = project_dir / "output" / "final.mp4"
    states["6"] = "completed" if (final_sub.exists() or final_old.exists()) else "pending"

    # Step 7 (업로드): DB 의 youtube_url 있으면 완료
    db = SessionLocal()
    try:
        proj = db.query(Project).filter(Project.id == project_id).first()
        proj_states = (proj.step_states or {}) if proj else {}
        states["7"] = "completed" if _project_upload_step_complete(proj, config) else "pending"
    finally:
        db.close()

    return states


def _reconcile_task_outputs(
    task: dict[str, Any],
    *,
    clear_terminal_cursor: bool = False,
    cleanup_broken: bool = False,
) -> bool:
    """디스크 실물 기준으로 task step 상태를 보정한다.

    서버 재시작이나 강제 종료 뒤에는 step_states/current_step 이 중간 상태로
    남을 수 있다. 이 함수는 실제 생성물 개수를 기준으로 완료된 step 을 다시
    맞추고, 필요하면 이어서 시작할 step 번호를 갱신한다.
    """
    project_id = str(task.get("project_id") or "").strip()
    if not project_id:
        return False
    task_config = task.get("config") if isinstance(task.get("config"), dict) else {}

    if cleanup_broken:
        detected, scanned_counts, scanned_total, removed = _cleanup_and_detect_completed_steps(project_id, task_config)
    else:
        detected, scanned_counts, scanned_total, removed = _scan_project_outputs(
            project_id,
            config=task_config,
            cleanup_broken=False,
            verify_media=False,
        )
    if removed:
        _add_log(task, f"깨진 산출물 {len(removed)}개 삭제 후 이어가기 상태 재계산", "warn")
    forced_completed_steps = {
        str(step)
        for step in (task.get("force_completed_steps") or [])
        if str(step).strip()
    }
    step_states = dict(task.get("step_states") or {})
    changed = False

    for step_key, state in detected.items():
        if step_key in forced_completed_steps:
            state = "completed"
        if step_states.get(step_key) != state:
            step_states[step_key] = state
            changed = True

    if task.get("step_states") != step_states:
        task["step_states"] = step_states
        changed = True

    completed_cuts = dict(task.get("completed_cuts_by_step") or {})
    for step_key, count in scanned_counts.items():
        if step_key in forced_completed_steps:
            continue
        if completed_cuts.get(step_key) != count:
            completed_cuts[step_key] = count
            changed = True
    if scanned_total and task.get("total_cuts") != scanned_total:
        task["total_cuts"] = scanned_total
        changed = True
    for step_key in ("2", "3", "4", "5"):
        if step_key in forced_completed_steps:
            continue
        if step_states.get(step_key) != "completed" and int(completed_cuts.get(step_key) or 0) > scanned_total:
            completed_cuts[step_key] = scanned_counts.get(step_key, 0)
            changed = True
    if task.get("completed_cuts_by_step") != completed_cuts:
        task["completed_cuts_by_step"] = completed_cuts

    first_pending = None
    for _slug, step_num, _label in STEP_ORDER:
        if step_states.get(str(step_num), "pending") != "completed":
            first_pending = step_num
            break

    if first_pending is None:
        if task.get("resume_from_step") is not None:
            task.pop("resume_from_step", None)
            changed = True
    else:
        if task.get("resume_from_step") != first_pending:
            task["resume_from_step"] = first_pending
            changed = True
        if task.get("status") == "completed":
            if first_pending == 7:
                _mark_task_upload_pending(task, str(task.get("project_id") or ""))
            else:
                task["status"] = "failed"
                task["error"] = f"완료 상태 정정: Step {first_pending} 미완료"
                task["finished_at"] = _utcnow_iso()
            changed = True

    if clear_terminal_cursor:
        if task.get("current_step") is not None:
            task["current_step"] = None
            changed = True
        if task.get("current_step_name") is not None:
            task["current_step_name"] = None
            changed = True
        if task.get("current_step_completed") not in (None, 0):
            task["current_step_completed"] = 0
            changed = True
        if task.get("current_step_total") not in (None, 0):
            task["current_step_total"] = 0
            changed = True
        if task.get("current_step_label") is not None:
            task["current_step_label"] = None
            changed = True
        if task.get("sub_status") is not None:
            task["sub_status"] = None
            changed = True

    if not clear_terminal_cursor and _restore_terminal_step_from_logs(task):
        changed = True

    return changed


def _find_reusable_project(
    template_project_id: Optional[str],
    topic: str,
    channel: Optional[int] = None,
) -> Optional[tuple[Project, dict[str, str]]]:
    """v1.1.52: 동일 주제로 이미 생성된 미완성 프로젝트가 있으면 반환한다.

    조건:
    1. topic 이 일치
    2. __oneclick__ 마커가 있음 (딸깍으로 만든 프로젝트)
    3. status 가 completed 가 아님 (이미 완성된 건 재사용 안 함)
    4. 스캔 결과 1개 이상의 스텝이 completed

    여러 개 있으면 가장 최근(id desc) 것을 사용한다.
    """
    db = SessionLocal()
    try:
        candidates = (
            db.query(Project)
            .filter(
                Project.topic == topic.strip(),
            )
            .order_by(Project.created_at.desc())
            .limit(10)
            .all()
        )
        for proj in candidates:
            cfg = proj.config or {}
            if not cfg.get("__oneclick__"):
                continue
            # 생성물 스캔
            if template_project_id and cfg.get("template_project_id") != template_project_id:
                continue
            if channel is not None:
                try:
                    if int(cfg.get("channel") or 0) != int(channel):
                        continue
                except (TypeError, ValueError):
                    continue
            detected, _counts, _total, _removed = _cleanup_and_detect_completed_steps(proj.id, cfg)
            completed_count = sum(1 for v in detected.values() if v == "completed")
            if completed_count > 0:
                return (proj, detected)
        return None
    finally:
        db.close()


def _find_existing_unfinished_oneclick_project(
    topic: str,
    *,
    template_project_id: Optional[str] = None,
    channel: Optional[int] = None,
) -> Optional[str]:
    """Return an existing unfinished oneclick project for the same queue item.

    This catches the dangerous window where a project has been created and is
    running, but no step has reached "completed" yet. `_find_reusable_project`
    intentionally skips that case, which can otherwise allow duplicate folders
    like `...-1` and `...-2` for the same topic.
    """
    normalized_topic = str(topic or "").strip()
    if not normalized_topic:
        return None
    try:
        channel_int = int(channel) if channel is not None else None
    except (TypeError, ValueError):
        channel_int = None

    db = SessionLocal()
    try:
        candidates = (
            db.query(Project)
            .filter(
                Project.topic == normalized_topic,
            )
            .order_by(Project.created_at.desc())
            .limit(20)
            .all()
        )
        matches: list[tuple[int, str]] = []
        for proj in candidates:
            cfg = dict(proj.config or {})
            if not cfg.get("__oneclick__"):
                continue
            if template_project_id and cfg.get("template_project_id") != template_project_id:
                continue
            if channel_int is not None:
                try:
                    if int(cfg.get("channel") or 0) != channel_int:
                        continue
                except (TypeError, ValueError):
                    continue

            pdir = None
            try:
                pdir = resolve_project_dir(proj.id, cfg, create=False)
                if not pdir.exists():
                    continue
            except Exception:
                continue

            if any(t.get("project_id") == proj.id for t in _TASKS.values()):
                matches.append((10_000_000, proj.id))
                continue

            score = 0
            try:
                if (pdir / "script.json").exists():
                    score += 1_000
                for sub, weight in (("audio", 10), ("images", 10), ("videos", 20), ("output", 50)):
                    subdir = pdir / sub
                    if subdir.exists():
                        score += sum(1 for f in subdir.iterdir() if f.is_file()) * weight
            except Exception:
                pass
            if score <= 0 and str(proj.status or "").lower() in {"failed", "cancelled"}:
                continue
            matches.append((score, proj.id))

        if not matches:
            return None
        matches.sort(key=lambda item: item[0], reverse=True)
        return matches[0][1]
    finally:
        db.close()


def _sync_completed_projects_into_tasks() -> bool:
    """Expose completed OneClick projects in the work-history task list.

    Some V3 runs are persisted as Project rows and archived result folders
    without a matching entry in _TASKS. The work-history screen is task based,
    so create stable read-only task records from the real Project state.
    """
    _dedupe_tasks()
    tasks_by_pid = {
        str(t.get("project_id") or "").strip(): t
        for t in _TASKS.values()
        if str(t.get("project_id") or "").strip()
    }
    changed = False
    db = SessionLocal()
    try:
        projects = (
            db.query(Project)
            .filter(Project.status == "completed")
            .order_by(Project.updated_at.desc())
            .limit(300)
            .all()
        )
        for project in projects:
            pid = str(project.id or "").strip()
            if not pid:
                continue
            cfg = dict(project.config or {})
            if not cfg.get("__oneclick__"):
                continue
            project_dir = resolve_project_dir(pid, cfg, create=False)
            if not project_dir.exists():
                continue

            detected, counts, detected_total, _removed = _scan_project_outputs(
                pid,
                config=cfg,
                cleanup_broken=False,
                verify_media=False,
            )
            output_dir = project_dir / "output"
            if any(
                (output_dir / name).exists()
                for name in ("final_with_subtitles.mp4", "final.mp4", "merged.mp4")
            ):
                detected["6"] = "completed"
            if _project_upload_step_complete(project, cfg):
                detected["7"] = "completed"
            if not any(detected.get(step) == "completed" for step in ("2", "3", "4", "5", "6", "7")):
                continue

            existing_task = tasks_by_pid.get(pid)
            if existing_task is not None:
                if existing_task.get("status") == "completed":
                    if _project_has_uploaded_video(project) and existing_task.get("youtube_url") != project.youtube_url:
                        existing_task["youtube_url"] = project.youtube_url
                        changed = True
                    if existing_task.get("step_states") != detected:
                        existing_task["step_states"] = detected
                        changed = True
                    merged_counts = dict(existing_task.get("completed_cuts_by_step") or {})
                    merged_counts.update(counts)
                    if existing_task.get("completed_cuts_by_step") != merged_counts:
                        existing_task["completed_cuts_by_step"] = merged_counts
                        changed = True
                    total = int(detected_total or project.total_cuts or existing_task.get("total_cuts") or 0)
                    if total and existing_task.get("total_cuts") != total:
                        existing_task["total_cuts"] = total
                        changed = True
                continue

            task_id = uuid.uuid5(uuid.NAMESPACE_URL, f"longtube-library:{pid}").hex[:8]
            if task_id in _TASKS:
                continue
            estimate = estimate_project(cfg)
            task = _make_task_record(
                task_id,
                template_project_id=cfg.get("template_project_id"),
                project_id=pid,
                topic=project.topic or "",
                title=project.title or "",
                estimate=estimate,
                config=cfg,
            )
            task["status"] = "completed"
            task["step_states"] = detected
            task["completed_cuts_by_step"].update(counts)
            task["total_cuts"] = int(detected_total or project.total_cuts or task.get("total_cuts") or 0)
            task["progress_pct"] = 100.0
            task["error"] = None
            task["youtube_url"] = project.youtube_url
            task["created_at"] = project.created_at.isoformat() if project.created_at else task["created_at"]
            task["started_at"] = task["created_at"]
            task["finished_at"] = project.updated_at.isoformat() if project.updated_at else task["created_at"]
            if cfg.get("channel") is not None:
                try:
                    task["channel"] = int(cfg.get("channel"))
                except (TypeError, ValueError):
                    pass
            task["logs"] = task.get("logs") or [{"ts": "", "level": "info", "msg": "DB 완료 프로젝트에서 작업기록 복구"}]
            _TASKS[task_id] = task
            tasks_by_pid[pid] = task
            changed = True
    finally:
        db.close()
    return changed


def _drop_tasks_without_project_rows() -> bool:
    """Remove task-cache rows whose Project record no longer exists."""
    project_ids = sorted({
        str(t.get("project_id") or "").strip()
        for t in _TASKS.values()
        if str(t.get("project_id") or "").strip()
    })
    if not project_ids:
        return False
    db = SessionLocal()
    try:
        existing = {
            row[0]
            for row in db.query(Project.id).filter(Project.id.in_(project_ids)).all()
        }
    finally:
        db.close()

    changed = False
    for tid, task in list(_TASKS.items()):
        pid = str(task.get("project_id") or "").strip()
        if pid and pid not in existing:
            _TASKS.pop(tid, None)
            _ACTIVE_RUNS.pop(tid, None)
            changed = True
    return changed


def _project_channel_from_id_or_config(project: Project, config: dict[str, Any]) -> Optional[int]:
    try:
        parsed = parse_v3_oneclick_project_id(project.id or "")
        if parsed:
            return parsed[0]
        m = re.match(r"^딸깍_CH(\d+)_", project.id or "")
        if m:
            ch = int(m.group(1))
            if 1 <= ch <= 4:
                return ch
    except Exception:
        pass
    try:
        ch = int(config.get("channel") or 0)
        if 1 <= ch <= 4:
            return ch
    except (TypeError, ValueError):
        pass
    return None


def _project_episode_from_id_or_config(project: Project, config: dict[str, Any]) -> Optional[int]:
    try:
        ep = int(config.get("episode_number") or 0)
        if ep > 0:
            return ep
    except (TypeError, ValueError):
        pass
    try:
        m = re.search(r"_EP(\d+)_", project.id or "", re.IGNORECASE)
        if m:
            ep = int(m.group(1))
            if ep > 0:
                return ep
    except Exception:
        pass
    return None


def _project_total_cuts_from_disk(project_id: str, config: Optional[dict] = None) -> int:
    try:
        script_path = resolve_project_dir(project_id, config or {}, create=False) / "script.json"
        if script_path.exists():
            data = json.loads(script_path.read_text(encoding="utf-8"))
            cuts = data.get("cuts") or []
            if isinstance(cuts, list):
                return len(cuts)
    except Exception:
        pass
    return 0


def _project_cut_row_count(project_id: str) -> int:
    db = SessionLocal()
    try:
        return int(db.query(Cut).filter(Cut.project_id == project_id).count() or 0)
    except Exception:
        return 0
    finally:
        db.close()


def _backup_dir_for_queue_item(item: dict[str, Any], project_id: str | None = None) -> Optional[Path]:
    try:
        ch = int(item.get("channel") or 0)
        ep = int(item.get("episode_number") or 0)
    except (TypeError, ValueError):
        return None
    if ch <= 0 or ep <= 0:
        return None
    pattern = f"CH{ch}_EP{ep}_"
    candidates: list[Path] = []
    try:
        for root in SYSTEM_DIR.iterdir():
            if not root.is_dir() or "backup" not in root.name.lower():
                continue
            for child in root.iterdir():
                if not child.is_dir():
                    continue
                name = child.name
                if pattern not in name:
                    continue
                if project_id and project_id in name:
                    candidates.append(child)
                elif not project_id:
                    candidates.append(child)
    except Exception:
        return None
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return candidates[0]


def _inspect_backup_progress(path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {
        "has_script": (path / "script.json").exists(),
        "audio_count": 0,
        "image_count": 0,
        "video_count": 0,
        "has_merged": False,
        "has_thumbnail": False,
        "total_cuts": 0,
        "progress_pct": 0.0,
        "disk_bytes": _dir_size(path),
    }
    script_total = 0
    try:
        if out["has_script"]:
            payload = json.loads((path / "script.json").read_text(encoding="utf-8"))
            cuts = payload.get("cuts") or []
            if isinstance(cuts, list):
                script_total = len(cuts)
    except Exception:
        script_total = 0
    for sub, key, exts in [
        ("audio", "audio_count", (".mp3", ".wav", ".m4a", ".ogg")),
        ("images", "image_count", (".png", ".jpg", ".jpeg", ".webp")),
        ("videos", "video_count", (".mp4", ".mov", ".webm")),
    ]:
        try:
            d = path / sub
            if d.exists():
                out[key] = sum(1 for f in d.iterdir() if f.is_file() and f.suffix.lower() in exts)
        except Exception:
            pass
    try:
        out["has_merged"] = any((path / "output" / name).exists() for name in ("merged.mp4", "final.mp4", "final_with_subtitles.mp4"))
        out["has_thumbnail"] = (path / "output" / "thumbnail.png").exists()
    except Exception:
        pass
    total = max(int(out["audio_count"] or 0), int(out["image_count"] or 0), int(out["video_count"] or 0))
    out["total_cuts"] = script_total or total
    denom = max(1, total)
    out["progress_pct"] = round(
        (10.0 if out["has_script"] else 0.0)
        + 20.0 * min(1.0, int(out["audio_count"] or 0) / denom)
        + 30.0 * min(1.0, int(out["image_count"] or 0) / denom)
        + 30.0 * min(1.0, int(out["video_count"] or 0) / denom)
        + (5.0 if out["has_merged"] else 0.0)
        + (5.0 if out["has_thumbnail"] else 0.0),
        1,
    )
    return out


def _write_script_from_cut_rows(project_id: str, project: Project, dest_dir: Path) -> bool:
    script_path = dest_dir / "script.json"
    if script_path.exists():
        return True
    db = SessionLocal()
    try:
        rows = (
            db.query(Cut)
            .filter(Cut.project_id == project_id)
            .order_by(Cut.cut_number.asc())
            .all()
        )
        if not rows:
            return False
        cuts = []
        for row in rows:
            cuts.append({
                "cut_number": int(row.cut_number or len(cuts) + 1),
                "narration": row.narration or "",
                "image_prompt": row.image_prompt or "",
                "scene_type": row.scene_type or "narration",
            })
        payload = {
            "title": project.title or project.topic or "",
            "topic": project.topic or project.title or "",
            "cuts": cuts,
        }
        script_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    finally:
        db.close()


def _restore_backup_for_queue_item(project_id: str, item: dict[str, Any]) -> bool:
    project = _load_project(project_id)
    if not project:
        return False
    backup_dir = _backup_dir_for_queue_item(item, project_id) or _backup_dir_for_queue_item(item)
    if not backup_dir or not backup_dir.exists():
        return False
    config = dict(project.config or {})
    config["__oneclick__"] = True
    try:
        ch = int(item.get("channel") or config.get("channel") or 0)
        if 1 <= ch <= 4:
            config["channel"] = ch
    except (TypeError, ValueError):
        pass
    try:
        ep = int(item.get("episode_number") or config.get("episode_number") or 0)
        if ep > 0:
            config["episode_number"] = ep
    except (TypeError, ValueError):
        pass
    if item.get("template_project_id"):
        config["template_project_id"] = item.get("template_project_id")

    db = SessionLocal()
    try:
        row = db.query(Project).filter(Project.id == project_id).first()
        if row:
            row.config = config
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(row, "config")
            db.commit()
            db.refresh(row)
            project = row
    finally:
        db.close()

    dest_dir = resolve_project_dir(project_id, config, create=True)
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(str(backup_dir), str(dest_dir), dirs_exist_ok=True)
    except Exception as e:
        print(f"[oneclick] backup restore copy failed: {backup_dir} -> {dest_dir}: {e}")
        return False
    _write_script_from_cut_rows(project_id, project, dest_dir)
    return True


def _restore_backup_project_record_for_queue_item(item: dict[str, Any]) -> Optional[str]:
    if _normalize_episode_code(item.get("episode_code") or item.get("episode_id")):
        return None
    backup_dir = _backup_dir_for_queue_item(item)
    if not backup_dir or not backup_dir.exists():
        return None
    try:
        ch = int(item.get("channel") or 0)
        ep = int(item.get("episode_number") or 0)
    except (TypeError, ValueError):
        ch = 0
        ep = 0
    unique_id = backup_dir.name
    m = re.search(rf"CH{ch}_EP{ep}_(.+)$", backup_dir.name) if ch > 0 and ep > 0 else None
    if m:
        unique_id = m.group(1)
    project_id = f"V3_CH{ch}_EP{ep}_{unique_id}" if ch > 0 and ep > 0 else backup_dir.name
    config = {
        "__oneclick__": True,
        "__oneclick_v3__": True,
        "template_project_id": item.get("template_project_id") or None,
        "cut_video_duration": ONECLICK_SECONDS_PER_CUT,
        "target_duration": ONECLICK_MAIN_TARGET_DURATION,
        "target_cuts": ONECLICK_MAIN_CUT_COUNT,
        "result_dir": str(resolve_project_dir(project_id, create=False)),
        "result_episode_dir": resolve_project_dir(project_id, create=False).name,
    }
    try:
        ch = int(item.get("channel") or 0)
        if 1 <= ch <= 4:
            config["channel"] = ch
    except (TypeError, ValueError):
        pass
    try:
        ep = int(item.get("episode_number") or 0)
        if ep > 0:
            config["episode_number"] = ep
    except (TypeError, ValueError):
        pass

    progress = _inspect_backup_progress(backup_dir)
    step_states = {
        "2": "completed" if progress.get("has_script") else "pending",
        "3": "completed" if int(progress.get("audio_count") or 0) >= int(progress.get("total_cuts") or 1) else "pending",
        "4": "completed" if int(progress.get("image_count") or 0) >= int(progress.get("total_cuts") or 1) else "pending",
        "5": "completed" if int(progress.get("video_count") or 0) >= int(progress.get("total_cuts") or 1) else "pending",
        "6": "completed" if progress.get("has_merged") else "pending",
        "7": "pending",
    }
    topic = str(item.get("topic") or "").strip() or project_id
    title = with_episode_prefix(topic, item.get("episode_number"))

    db = SessionLocal()
    try:
        row = db.query(Project).filter(Project.id == project_id).first()
        if not row:
            row = Project(
                id=project_id,
                title=title,
                topic=topic,
                config=config,
                status="completed" if progress.get("has_merged") else "draft",
                current_step=6 if progress.get("has_merged") else 0,
                step_states=step_states,
                total_cuts=int(progress.get("total_cuts") or ONECLICK_MAIN_CUT_COUNT),
            )
            db.add(row)
        else:
            row.config = {**dict(row.config or {}), **config}
            row.step_states = {**dict(row.step_states or {}), **step_states}
            row.total_cuts = int(progress.get("total_cuts") or row.total_cuts or ONECLICK_MAIN_CUT_COUNT)
        db.commit()
    finally:
        db.close()

    dest_dir = resolve_project_dir(project_id, config, create=True)
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(str(backup_dir), str(dest_dir), dirs_exist_ok=True)
    except Exception as e:
        print(f"[oneclick] backup project restore failed: {backup_dir} -> {dest_dir}: {e}")
        return None
    return project_id


def _v3_project_id_from_result_dir(channel: int, episode_number: int, result_dir: Path) -> Optional[str]:
    parts = result_dir.name.split(".", 2)
    if len(parts) != 3 or parts[0] != "EP":
        return None
    try:
        if int(parts[1]) != int(episode_number):
            return None
    except (TypeError, ValueError):
        return None
    unique_id = parts[2].strip()
    if not unique_id:
        return None
    return f"V3_CH{int(channel)}_EP{int(episode_number)}_{unique_id}"


def _has_meaningful_generation_progress(progress: dict[str, Any]) -> bool:
    return bool(
        progress.get("has_script")
        or int(progress.get("audio_count") or 0) > 0
        or int(progress.get("image_count") or 0) > 0
        or int(progress.get("video_count") or 0) > 0
        or progress.get("has_merged")
        or progress.get("has_thumbnail")
    )


def _find_orphan_v3_result_project_for_queue_item(item: dict[str, Any]) -> Optional[tuple[str, Path, dict[str, Any]]]:
    if _normalize_episode_code(item.get("episode_code") or item.get("episode_id")):
        return None
    try:
        channel = int(item.get("channel") or 0)
        episode_number = int(item.get("episode_number") or 0)
    except (TypeError, ValueError):
        return None
    if channel <= 0 or episode_number <= 0:
        return None

    channel_dir = RESULT_ARCHIVE_DIR / f"CH{channel}"
    if not channel_dir.exists():
        return None

    candidates: list[tuple[float, str, Path, dict[str, Any]]] = []
    try:
        for result_dir in channel_dir.iterdir():
            if not result_dir.is_dir():
                continue
            project_id = _v3_project_id_from_result_dir(channel, episode_number, result_dir)
            if not project_id:
                continue
            progress = _inspect_backup_progress(result_dir)
            if not _has_meaningful_generation_progress(progress):
                continue
            try:
                mtime = result_dir.stat().st_mtime
            except OSError:
                mtime = 0.0
            candidates.append((mtime, project_id, result_dir, progress))
    except Exception:
        return None

    if not candidates:
        return None
    candidates.sort(key=lambda row: row[0], reverse=True)
    _mtime, project_id, result_dir, progress = candidates[0]
    return project_id, result_dir, progress


def _restore_orphan_v3_project_record_for_queue_item(item: dict[str, Any]) -> Optional[str]:
    found = _find_orphan_v3_result_project_for_queue_item(item)
    if not found:
        return None
    project_id, result_dir, progress = found

    try:
        channel = int(item.get("channel") or 0)
    except (TypeError, ValueError):
        channel = 0
    try:
        episode_number = int(item.get("episode_number") or 0)
    except (TypeError, ValueError):
        episode_number = 0
    episode_code = _normalize_episode_code(item.get("episode_code") or item.get("episode_id"))

    source_project_id = _channel_studio_project_id(channel, item.get("template_project_id"))
    config: dict[str, Any] = {
        "__oneclick__": True,
        "__oneclick_v3__": True,
        "template_project_id": source_project_id or item.get("template_project_id") or None,
        "source_project_id": source_project_id or item.get("template_project_id") or None,
        "cut_video_duration": ONECLICK_SECONDS_PER_CUT,
        "target_duration": ONECLICK_MAIN_TARGET_DURATION,
        "target_cuts": ONECLICK_MAIN_CUT_COUNT,
        "result_dir": str(result_dir),
        "result_channel_dir": f"CH{channel}" if channel > 0 else None,
        "result_episode_dir": result_dir.name,
        "topic": str(item.get("topic") or "").strip(),
    }
    if channel > 0:
        config["channel"] = channel
    if episode_number > 0:
        config["episode_number"] = episode_number
    if episode_code:
        raw_episode_code = str(item.get("episode_code") or item.get("episode_id") or "").strip()
        config["episode_code"] = raw_episode_code
        config["episode_id"] = raw_episode_code

    for item_key, config_key in (
        ("openings", "episode_openings"),
        ("endings", "episode_endings"),
        ("core_content", "episode_core_content"),
        ("next_episode_preview", "next_episode_preview"),
    ):
        value = item.get(item_key)
        if value:
            config[config_key] = value
    config = _force_oneclick_main_length(config)

    total_cuts = int(progress.get("total_cuts") or ONECLICK_MAIN_CUT_COUNT)
    step_states = {
        "2": "completed" if progress.get("has_script") else "pending",
        "3": "completed" if int(progress.get("audio_count") or 0) >= total_cuts else "pending",
        "4": "completed" if int(progress.get("image_count") or 0) >= total_cuts else "pending",
        "5": "completed" if int(progress.get("video_count") or 0) >= total_cuts else "pending",
        "6": "completed" if progress.get("has_merged") else "pending",
        "7": "pending",
    }
    topic = str(item.get("topic") or "").strip() or project_id
    title = with_episode_prefix(topic, episode_number)

    db = SessionLocal()
    try:
        row = db.query(Project).filter(Project.id == project_id).first()
        if not row:
            row = Project(
                id=project_id,
                title=title,
                topic=topic,
                config=config,
                status="draft",
                current_step=6 if progress.get("has_merged") else 0,
                step_states=step_states,
                total_cuts=total_cuts,
            )
            db.add(row)
        else:
            row.title = row.title or title
            row.topic = row.topic or topic
            row.config = {**dict(row.config or {}), **config}
            row.step_states = {**dict(row.step_states or {}), **step_states}
            row.total_cuts = int(row.total_cuts or total_cuts)
            if str(row.status or "").lower() in ("failed", "cancelled"):
                row.status = "draft"
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(row, "config")
            flag_modified(row, "step_states")
        db.commit()
    finally:
        db.close()

    return project_id


def _find_existing_project_for_queue_item(item: dict[str, Any], *, allow_implicit: bool = True) -> Optional[str]:
    """작업대 큐 항목과 같은 에피소드의 기존 산출물 프로젝트를 찾는다."""
    topic = str(item.get("topic") or "").strip()
    template_project_id = str(item.get("template_project_id") or "").strip() or None
    try:
        channel = int(item.get("channel") or 0)
    except (TypeError, ValueError):
        channel = 0
    try:
        episode_number = int(item.get("episode_number") or 0)
    except (TypeError, ValueError):
        episode_number = 0
    episode_code = _normalize_episode_code(item.get("episode_code") or item.get("episode_id"))

    explicit_ids: list[str] = []
    for key in ("restored_from_project_id", "project_id"):
        pid = str(item.get(key) or "").strip()
        if pid:
            explicit_ids.append(pid)
    old_task_id = str(item.get("requeued_from_task_id") or "").strip()
    if old_task_id and old_task_id in _TASKS:
        pid = str(_TASKS[old_task_id].get("project_id") or "").strip()
        if pid:
            explicit_ids.append(pid)

    has_explicit_id = bool(explicit_ids)
    if not has_explicit_id and not allow_implicit:
        return None
    if not has_explicit_id and episode_number <= 0:
        return None

    db = SessionLocal()
    try:
        candidates: list[Project] = []
        if explicit_ids:
            candidates.extend(
                db.query(Project)
                .filter(Project.id.in_(list(dict.fromkeys(explicit_ids))))
                .all()
            )

        if allow_implicit:
            candidates.extend(
                db.query(Project)
                .filter(Project.id.like("딸깍_%"))
                .order_by(Project.created_at.desc())
                .limit(500)
                .all()
            )
            candidates.extend(
                db.query(Project)
                .filter(Project.id.like("V3_CH%"))
                .order_by(Project.created_at.desc())
                .limit(500)
                .all()
            )

        scored: list[tuple[int, str]] = []
        seen: set[str] = set()
        for project in candidates:
            if not project or project.id in seen:
                continue
            seen.add(project.id)
            config = dict(project.config or {})
            if not config.get("__oneclick__"):
                continue
            if str(project.status or "").lower() == "completed" and _project_upload_step_complete(project, config):
                continue
            backup_dir: Optional[Path] = None
            cut_row_count = _project_cut_row_count(project.id)
            try:
                pdir = resolve_project_dir(project.id, config, create=False)
                if not pdir.exists():
                    backup_dir = _backup_dir_for_queue_item(item, project.id) or _backup_dir_for_queue_item(item)
                    if not backup_dir and cut_row_count <= 0:
                        continue
            except Exception:
                backup_dir = _backup_dir_for_queue_item(item, project.id) or _backup_dir_for_queue_item(item)
                if not backup_dir and cut_row_count <= 0:
                    continue

            score = 0
            if project.id in explicit_ids:
                score += 100_000

            proj_ch = _project_channel_from_id_or_config(project, config)
            proj_ep = _project_episode_from_id_or_config(project, config)
            proj_episode_code = _normalize_episode_code(config.get("episode_code") or config.get("episode_id"))
            if episode_code:
                if proj_episode_code != episode_code:
                    continue
                score += 40_000
            if episode_number > 0:
                if proj_ep != episode_number:
                    continue
                score += 20_000
            if channel > 0:
                if proj_ch is not None and proj_ch != channel:
                    continue
                if proj_ch == channel:
                    score += 10_000
            if template_project_id:
                if config.get("template_project_id") == template_project_id:
                    score += 2_000
                elif episode_number <= 0:
                    continue
            if topic and str(project.topic or "").strip() == topic:
                score += 5_000

            total_cuts = _project_total_cuts_from_disk(project.id, config)
            progress = _inspect_backup_progress(backup_dir) if backup_dir else _inspect_project_progress(project.id, total_cuts, config)
            if cut_row_count > 0 and not progress.get("has_script"):
                progress["has_script"] = True
                progress["total_cuts"] = max(int(progress.get("total_cuts") or 0), cut_row_count)
                progress["progress_pct"] = max(float(progress.get("progress_pct") or 0.0), 10.0)
            progress_score = int(progress.get("progress_pct") or 0)
            has_files = bool(progress.get("disk_bytes")) and (
                progress.get("has_script")
                or int(progress.get("audio_count") or 0) > 0
                or int(progress.get("image_count") or 0) > 0
                or int(progress.get("video_count") or 0) > 0
                or progress.get("has_merged")
                or progress.get("has_thumbnail")
            )
            has_files = has_files or cut_row_count > 0
            if not has_files:
                continue
            score += progress_score
            scored.append((score, project.id))

        if not scored:
            if not allow_implicit:
                return None
            return (
                _restore_orphan_v3_project_record_for_queue_item(item)
                or _restore_backup_project_record_for_queue_item(item)
            )
        scored.sort(key=lambda row: row[0], reverse=True)
        return scored[0][1]
    finally:
        db.close()


def _queue_item_from_v3_task(task: dict[str, Any]) -> Optional[dict[str, Any]]:
    project_id = str(task.get("project_id") or "").strip()
    parsed = parse_v3_oneclick_project_id(project_id)
    if not parsed:
        return None
    channel, episode_number, _unique_id = parsed
    cfg = _task_project_metadata_config(task)
    raw_episode_code = (
        task.get("episode_code")
        or task.get("episode_id")
        or cfg.get("episode_code")
        or cfg.get("episode_id")
    )
    return {
        "topic": str(task.get("topic") or task.get("title") or cfg.get("topic") or "").strip(),
        "template_project_id": task.get("source_project_id") or task.get("template_project_id") or cfg.get("source_project_id") or cfg.get("template_project_id"),
        "target_duration": cfg.get("target_duration") or ONECLICK_MAIN_TARGET_DURATION,
        "target_cuts": cfg.get("target_cuts") or ONECLICK_MAIN_CUT_COUNT,
        "channel": channel,
        "openings": cfg.get("episode_openings") if isinstance(cfg.get("episode_openings"), list) else [],
        "endings": cfg.get("episode_endings") if isinstance(cfg.get("episode_endings"), list) else [],
        "core_content": str(cfg.get("episode_core_content") or ""),
        "episode_number": episode_number,
        "series": str(task.get("series") or cfg.get("series") or "").strip(),
        "episode_code": str(raw_episode_code or "").strip(),
        "episode_id": str(raw_episode_code or "").strip(),
        "next_episode_preview": str(cfg.get("next_episode_preview") or ""),
    }


def _redirect_empty_v3_task_to_existing_episode(task_id: str, task: dict[str, Any]) -> dict[str, Any]:
    item = _queue_item_from_v3_task(task)
    if not item:
        return task

    project_id = str(task.get("project_id") or "").strip()
    progress = _inspect_project_progress(
        project_id,
        task.get("total_cuts"),
        task.get("config") if isinstance(task.get("config"), dict) else {},
    )
    if _has_meaningful_generation_progress(progress):
        return task

    existing_project_id = _find_existing_project_for_queue_item(item)
    if not existing_project_id or existing_project_id == project_id:
        return task

    old_logs = list(task.get("logs") or [])
    recovered = recover_project(existing_project_id)
    recovered_task_id = str(recovered.get("task_id") or "")
    merged = dict(recovered)
    merged["task_id"] = task_id
    merged["triggered_by"] = task.get("triggered_by") or recovered.get("triggered_by")
    try:
        ch = int(item.get("channel") or 0)
        if 1 <= ch <= 4:
            merged["channel"] = ch
    except (TypeError, ValueError):
        pass
    try:
        ep = int(item.get("episode_number") or 0)
        if ep > 0:
            merged["episode_number"] = ep
    except (TypeError, ValueError):
        pass
    raw_episode_code = str(item.get("episode_code") or item.get("episode_id") or "").strip()
    if raw_episode_code:
        merged["episode_code"] = raw_episode_code
        merged["episode_id"] = raw_episode_code
    logs = old_logs + list(recovered.get("logs") or [])
    merged["logs"] = logs
    task.clear()
    task.update(merged)
    _TASKS[task_id] = task
    if recovered_task_id and recovered_task_id != task_id:
        _TASKS.pop(recovered_task_id, None)
        _ACTIVE_RUNS.pop(recovered_task_id, None)
    _add_log(task, f"빈 V3 재시작 작업을 기존 에피소드 산출물로 대체: {existing_project_id}", "info")
    _save_tasks_to_disk()
    return task


def _find_blocking_broken_project(topic: str) -> Optional[str]:
    """같은 주제의 깨진 딸깍 프로젝트가 있으면 project_id 를 반환한다.

    조건:
    - __oneclick__ 프로젝트
    - completed 아님
    - script.json 없음
    - 대신 audio/images/videos/output 중 하나에는 생성물이 남아 있음

    이런 상태에서 새 project_id 를 또 만들면 사용자가 모르는 사이에
    대본/이미지/영상 API가 다시 호출될 수 있으므로 prepare 단계에서 차단한다.
    """
    safe_topic = _sanitize_for_filename(topic)
    try:
        for ch in range(1, 5):
            root = get_channel_projects_root(ch)
            if not root.exists():
                continue
            for project_dir in sorted(root.iterdir(), key=lambda p: p.name, reverse=True):
                if not project_dir.is_dir():
                    continue
                if not project_dir.name.startswith("딸깍"):
                    continue
                if safe_topic not in project_dir.name:
                    continue
                script_path = project_dir / "script.json"
                if script_path.exists():
                    continue
                for sub in ("audio", "images", "videos", "output"):
                    subdir = project_dir / sub
                    if not subdir.exists():
                        continue
                    if sub == "output":
                        blocking = [
                            p for p in subdir.iterdir()
                            if p.is_file() and not p.name.lower().startswith("thumbnail")
                        ]
                        if blocking:
                            return project_dir.name
                    elif any(subdir.iterdir()):
                        return project_dir.name
        return None
    except Exception:
        return None


def _sanitize_for_filename(text: str, max_len: int = 30) -> str:
    """파일명에 안전한 문자만 남긴다. 한글/영문/숫자/하이픈/언더스코어 허용."""
    text = unicodedata.normalize("NFC", str(text or "")).replace("\ufffd", "")
    # 공백 → 언더스코어
    text = text.strip().replace(" ", "_")
    text = re.sub(r'[\x00-\x1f<>:"/\\|?*]+', "", text)
    # 허용 문자만 남김 (한글, 영문, 숫자, 하이픈, 언더스코어)
    text = re.sub(r'[^\w가-힣-]', '', text, flags=re.UNICODE)
    return text[:max_len] or "Untitled"


def _generate_oneclick_project_id(
    topic: str,
    db,
    channel: Optional[int] = None,
    episode_number: Optional[int] = None,
) -> str:
    """딸깍 project_id 를 생성한다.

    v1.2.29: channel 이 주어지면 딸깍_CH{ch}_주제_YYMMDD-N 로 채널 번호를
    prefix 에 박아 생성. 사용자 요구: "앞으로 결과물 생성할 때 파일명에
    채널 번호도 표기 해 — 딸깍_CH1_뭐뭐_날짜_순번 이렇게". 채널이 None 이면
    (미지정 호출 경로) 기존 포맷 유지 — 모든 채널에서 접근 가능한 레거시로 취급.
    v1.2.30: episode_number 가 있으면 채널 바로 뒤에 EP{n} 을 붙인다.
    v1.2.31: 새 딸깍 폴더명에서 제목/주제 제거.

    같은 날짜/채널에 이미 생성된 딸깍 프로젝트 수를 세서 순번(N)을 매긴다.
    예:
      채널+EP 지정: 딸깍_CH1_EP30_260413-1
      채널 지정: 딸깍_CH1_260413-1, 딸깍_CH1_260413-2
      채널 미지정: 딸깍_260413-1
    """
    date_str = datetime.now().strftime("%y%m%d")
    ep_part = ""
    try:
        ep_int = int(episode_number) if episode_number is not None else 0
        if ep_int > 0:
            ep_part = f"_EP{ep_int}"
    except (TypeError, ValueError):
        ep_part = ""
    if channel is not None:
        try:
            ch_int = int(channel)
            if 1 <= ch_int <= 4:
                prefix = f"딸깍_CH{ch_int}{ep_part}_{date_str}"
            else:
                prefix = f"딸깍_{date_str}"
        except (TypeError, ValueError):
            prefix = f"딸깍_{date_str}"
    else:
        prefix = f"딸깍_{date_str}"

    # 같은 prefix 로 시작하는 기존 프로젝트 수 카운트
    existing = (
        db.query(Project.id)
        .filter(Project.id.like(f"{prefix}-%"))
        .all()
    )
    seq = len(existing) + 1
    project_id = f"{prefix}-{seq}"

    # 혹시 충돌하면 순번 올림
    while db.query(Project).filter(Project.id == project_id).first():
        seq += 1
        project_id = f"{prefix}-{seq}"

    return project_id


def _is_titleless_oneclick_project_id(project_id: str) -> bool:
    pid = str(project_id or "").strip()
    return bool(
        re.fullmatch(r"딸깍_CH[1-4](?:_EP\d+)?_\d{6}-\d+", pid)
        or re.fullmatch(r"딸깍_\d{6}-\d+", pid)
    )


def _rename_existing_oneclick_project_to_titleless(
    project_id: str,
    *,
    channel: Optional[int] = None,
    episode_number: Optional[int] = None,
) -> str:
    """기존 제목 포함 딸깍 project_id 를 새 제목 없는 규칙으로 바꾼다."""
    old_id = str(project_id or "").strip()
    if not old_id or _is_titleless_oneclick_project_id(old_id):
        return old_id

    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == old_id).first()
        if not project:
            return old_id
        cfg = dict(project.config or {})
        if not cfg.get("__oneclick__"):
            return old_id

        ch = channel
        if ch is None:
            ch = cfg.get("channel")
        ep = episode_number
        if ep is None:
            ep = cfg.get("episode_number")

        new_id = _generate_oneclick_project_id(project.topic or "", db, channel=ch, episode_number=ep)
        if new_id == old_id:
            return old_id

        old_dir = resolve_project_dir(old_id, cfg)
        new_dir = resolve_project_dir(new_id, cfg)
        if old_dir.exists():
            if new_dir.exists():
                print(f"[oneclick] project_id rename skipped: target exists {new_dir}")
                return old_id
            new_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old_dir), str(new_dir))

        db.query(Cut).filter(Cut.project_id == old_id).update({"project_id": new_id}, synchronize_session=False)
        db.query(ApiLog).filter(ApiLog.project_id == old_id).update({"project_id": new_id}, synchronize_session=False)
        for row in db.query(ScheduledEpisode).filter(ScheduledEpisode.project_id == old_id).all():
            row.project_id = new_id
        project.id = new_id
        db.commit()

        for task in _TASKS.values():
            if task.get("project_id") == old_id:
                task["project_id"] = new_id
                try:
                    _add_log(task, f"프로젝트 폴더명 정리: {old_id} → {new_id}", "info")
                except Exception:
                    pass
        print(f"[oneclick] project_id renamed: {old_id} -> {new_id}")
        return new_id
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        print(f"[oneclick] project_id rename failed {old_id}: {e}")
        return old_id
    finally:
        db.close()


def _copy_template_assets(tmpl_dir: Path, dest_dir: Path, config: dict):
    """템플릿 프로젝트의 에셋 파일(레퍼런스/캐릭터/로고/간지/BGM)을 새 프로젝트 디렉토리에 복사.

    v1.1.52: config 에 상대 경로로 기록된 에셋 파일이 새 project_id
    디렉토리에도 물리적으로 존재해야 collect_reference_images /
    collect_character_images 가 제대로 동작한다.
    """
    import shutil

    ch = _valid_channel(config.get("channel") or config.get("youtube_channel"))
    if ch is None:
        m = re.fullmatch(r"CH([1-9]\d*)", str(config.get("result_channel_dir") or ""), flags=re.IGNORECASE)
        if m:
            ch = _valid_channel(m.group(1))

    def _dedupe_source_roots(paths: list[Path]) -> list[Path]:
        seen: set[str] = set()
        result: list[Path] = []
        for path in paths:
            try:
                key = str(path.resolve())
            except Exception:
                key = str(path)
            if key in seen:
                continue
            seen.add(key)
            result.append(path)
        return result

    source_roots = [tmpl_dir, SYSTEM_DIR / "projects" / tmpl_dir.name]
    if ch is not None:
        source_roots.append(get_channel_projects_root(ch) / tmpl_dir.name)
    source_roots = _dedupe_source_roots(source_roots)

    # 1) config 에 기록된 상대 경로 기반 에셋 복사
    for key in ("reference_images", "character_images", "logo_images"):
        for rel in config.get(key, []) or []:
            dst = dest_dir / rel
            for source_root in source_roots:
                src = source_root / rel
                if not src.exists():
                    continue
                dst.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(str(src), str(dst))
                except Exception as e:
                    print(f"[oneclick] 에셋 복사 실패 {rel}: {e}")
                break

    bgm_rel = str(config.get("bgm_path") or "").strip()
    if bgm_rel:
        dst = dest_dir / bgm_rel
        src_candidates = [Path(bgm_rel)] if Path(bgm_rel).is_absolute() else []
        src_candidates.extend(source_root / bgm_rel for source_root in source_roots)
        for src in src_candidates:
            if not src.exists() or not src.is_file():
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(str(src), str(dst))
            except Exception as e:
                print(f"[oneclick] BGM 복사 실패 {bgm_rel}: {e}")
            break

    # 2) 간지(interlude)/BGM/사전작성 대본 디렉토리가 있으면 통째로 복사
    for dirname, label in (
        ("interlude", "간지"),
        ("bgm", "BGM"),
        ("scripts", "사전작성 대본"),
        ("prepared_scripts", "사전작성 대본"),
        ("대본", "사전작성 대본"),
    ):
        for source_root in source_roots:
            tmpl_interlude = source_root / dirname
            if not tmpl_interlude.is_dir():
                continue
            dest_interlude = dest_dir / dirname
            try:
                shutil.copytree(str(tmpl_interlude), str(dest_interlude), dirs_exist_ok=True)
            except Exception as e:
                print(f"[oneclick] {label} 복사 실패: {e}")

    # 채널 공통 리브랜딩 인터루드가 있으면 다음 생성 프로젝트에도 기본 제공한다.
    if ch is not None:
        data_root = Path(str(DATA_DIR))
        rebrand_roots = [
            data_root / "channel_rebrand",
            data_root.parent / "channel_rebrand",
            BASE_DIR / "data" / "channel_rebrand",
        ]
        source_dirs: list[Path] = []
        seen_rebrand_dirs: set[str] = set()
        for rebrand_root in rebrand_roots:
            try:
                candidates = [
                    p for p in sorted(rebrand_root.glob(f"ch{ch}_*/interludes"))
                    if p.is_dir()
                ]
            except Exception:
                candidates = []
            for candidate in candidates:
                key = str(candidate)
                if key not in seen_rebrand_dirs:
                    seen_rebrand_dirs.add(key)
                    source_dirs.append(candidate)
        if source_dirs:
            dest_interlude = dest_dir / "interlude"
            dest_interlude.mkdir(parents=True, exist_ok=True)
            for source_dir in source_dirs:
                for src in source_dir.iterdir():
                    if not src.is_file():
                        continue
                    dst = dest_interlude / src.name
                    if dst.exists():
                        continue
                    try:
                        shutil.copy2(str(src), str(dst))
                    except Exception as e:
                        print(f"[oneclick] 채널 공통 간지 복사 실패 {src.name}: {e}")

    # 3) v1.1.55 hotfix: 프리셋에 연결된 YouTube 토큰을 클론으로 복사.
    # 프리셋(예: "무서운이야기")에 OAuth 인증한 youtube_token.json 이
    # tmpl_dir 에 있으면 클론에도 똑같이 깔아준다. 이게 빠지면 업로드 시
    # _step_youtube_upload 가 채널 기본값(CH1) 토큰으로 폴백해서
    # 전혀 다른 계정("제리스 아키오") 으로 올라가는 사고가 난다.
    src_token = tmpl_dir / "youtube_token.json"
    if src_token.exists():
        dst_token = dest_dir / "youtube_token.json"
        try:
            shutil.copy2(str(src_token), str(dst_token))
            print(f"[oneclick] 프리셋 YouTube 토큰 복사: {src_token.name}")
        except Exception as e:
            print(f"[oneclick] YouTube 토큰 복사 실패: {e}")


def _ensure_project_layout(project_id: str, config: Optional[dict] = None) -> Path:
    project_dir = resolve_project_dir(project_id, config or {}, create=True)
    project_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("audio", "images", "videos", "subtitles", "output"):
        (project_dir / sub).mkdir(parents=True, exist_ok=True)
    return project_dir


def _channel_studio_project_id(channel: Optional[int], fallback_project_id: Optional[str] = None) -> Optional[str]:
    """Return the Studio project linked to the channel."""
    ch = _valid_channel(channel)
    if ch is not None:
        cp = (_QUEUE.get("channel_presets") or {}).get(str(ch))
        if cp:
            return str(cp).strip() or None
    fallback = str(fallback_project_id or "").strip()
    return fallback or None


def _generate_v3_run_project_id(channel: Optional[int], episode_number: Optional[int], db) -> str:
    ch = _valid_channel(channel) or 1
    ep = coerce_episode_number(episode_number) or 0
    while True:
        unique_id = f"{datetime.now().strftime('%y%m%d%H%M%S')}{uuid.uuid4().hex[:6]}"
        project_id = f"V3_CH{ch}_EP{ep}_{unique_id}"
        if not db.query(Project).filter(Project.id == project_id).first():
            return project_id


def _series_result_folder_name(series: Optional[str] = None, episode_code: Optional[str] = None) -> str:
    raw = str(series or "").strip()
    if not raw:
        m = re.match(r"^(.+?)[\s_-]*EP\d+", str(episode_code or "").strip(), flags=re.IGNORECASE)
        raw = (m.group(1).strip() if m else "")
    if not raw:
        return ""
    raw = unicodedata.normalize("NFC", raw)
    raw = re.sub(r'[\x00-\x1f<>:"/\\|?*]+', "", raw)
    raw = re.sub(r"\s+", " ", raw).strip().strip(".")
    return raw[:60]


def _v3_result_dir_for_run(
    project_id: str,
    *,
    series: Optional[str] = None,
    episode_code: Optional[str] = None,
) -> Path:
    parsed = parse_v3_oneclick_project_id(project_id)
    if not parsed:
        return RESULT_ARCHIVE_DIR / project_id
    channel, episode_number, unique_id = parsed
    base = RESULT_ARCHIVE_DIR / f"CH{channel}"
    folder = _series_result_folder_name(series, episode_code)
    if folder:
        base = base / folder
    return base / f"EP.{episode_number}.{unique_id}"


def _apply_v3_episode_overrides(
    config: dict[str, Any],
    *,
    source_project_id: str,
    project_id: str,
    result_dir: Path,
    topic: str,
    channel: Optional[int],
    episode_openings: Optional[List[str]] = None,
    episode_endings: Optional[List[str]] = None,
    episode_core_content: Optional[str] = None,
    episode_number: Optional[int] = None,
    series: Optional[str] = None,
    episode_code: Optional[str] = None,
    next_episode_preview: Optional[str] = None,
) -> dict[str, Any]:
    cfg = dict(config or {})
    cfg["__oneclick__"] = True
    cfg["__oneclick_v3__"] = True
    cfg["template_project_id"] = source_project_id
    cfg["source_project_id"] = source_project_id
    cfg["auto_pause_after_step"] = False
    cfg["topic"] = topic
    cfg["result_dir"] = str(result_dir)
    parsed = parse_v3_oneclick_project_id(project_id)
    if parsed:
        ch_from_id, ep_from_id, _uid = parsed
        cfg["result_channel_dir"] = f"CH{ch_from_id}"
        cfg["result_episode_dir"] = Path(result_dir).name
        cfg["episode_number"] = ep_from_id if ep_from_id > 0 else cfg.get("episode_number")

    ch = _valid_channel(channel)
    if ch is not None:
        cfg["channel"] = ch

    def _clean_list(xs: Optional[List[str]]) -> list[str]:
        return [x for x in [str(v or "").strip() for v in (xs or [])] if x]

    if episode_openings is not None:
        filtered = _clean_list(episode_openings)
        if filtered:
            cfg["episode_openings"] = filtered
        else:
            cfg.pop("episode_openings", None)
    if episode_endings is not None:
        filtered = _clean_list(episode_endings)
        if filtered:
            cfg["episode_endings"] = filtered
        else:
            cfg.pop("episode_endings", None)
    if episode_core_content is not None:
        cc = str(episode_core_content or "").strip()
        if cc:
            cfg["episode_core_content"] = cc
        else:
            cfg.pop("episode_core_content", None)
    if episode_number is not None:
        ep = coerce_episode_number(episode_number)
        if ep:
            cfg["episode_number"] = ep
        else:
            cfg.pop("episode_number", None)
    if series is not None:
        clean_series = str(series or "").strip()
        if clean_series:
            cfg["series"] = clean_series
        else:
            cfg.pop("series", None)
    if episode_code is not None:
        code = str(episode_code or "").strip()
        if code:
            cfg["episode_code"] = code
            cfg["episode_id"] = code
        else:
            cfg.pop("episode_code", None)
            cfg.pop("episode_id", None)
    if next_episode_preview is not None:
        nep = str(next_episode_preview or "").strip()
        if nep:
            cfg["next_episode_preview"] = nep
        else:
            cfg.pop("next_episode_preview", None)
    series_folder = _series_result_folder_name(cfg.get("series"), cfg.get("episode_code") or cfg.get("episode_id"))
    if series_folder:
        cfg["result_series_dir"] = series_folder
    return _force_oneclick_main_length(cfg)


def _is_v3_studio_linked_project(project_id: str, config: Optional[dict] = None) -> bool:
    cfg = config or {}
    return bool(
        parse_v3_oneclick_project_id(project_id)
        or cfg.get("__oneclick_v3__")
        or cfg.get("source_project_id")
    )


def _prepare_v3_studio_linked_task(
    *,
    source_project_id: str,
    topic: str,
    title: Optional[str] = None,
    episode_openings: Optional[List[str]] = None,
    episode_endings: Optional[List[str]] = None,
    episode_core_content: Optional[str] = None,
    episode_number: Optional[int] = None,
    series: Optional[str] = None,
    episode_code: Optional[str] = None,
    next_episode_preview: Optional[str] = None,
    channel: Optional[int] = None,
) -> dict:
    db = SessionLocal()
    try:
        source = db.query(Project).filter(Project.id == source_project_id).first()
        if not source:
            raise ValueError(f"채널 연결 스튜디오 프로젝트를 찾을 수 없습니다: {source_project_id}")

        clean_topic = (topic or "").strip() or "Untitled"
        ep = coerce_episode_number(episode_number)
        clean_title = with_episode_prefix((title or clean_topic[:50]).strip() or clean_topic[:50], ep)
        project_id = _generate_v3_run_project_id(channel, ep, db)
        result_dir = _v3_result_dir_for_run(project_id, series=series, episode_code=episode_code)
        result_dir.mkdir(parents=True, exist_ok=True)
        config = _apply_v3_episode_overrides(
            dict(source.config or {}),
            source_project_id=source_project_id,
            project_id=project_id,
            result_dir=result_dir,
            topic=clean_topic,
            channel=channel,
            episode_openings=episode_openings,
            episode_endings=episode_endings,
            episode_core_content=episode_core_content,
            episode_number=ep,
            series=series,
            episode_code=episode_code,
            next_episode_preview=next_episode_preview,
        )

        project = Project(
            id=project_id,
            title=clean_title,
            topic=clean_topic,
            config=config,
            status="draft",
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        for sub in ("audio", "images", "videos", "subtitles", "output"):
            (result_dir / sub).mkdir(parents=True, exist_ok=True)
        try:
            _copy_template_assets(resolve_project_dir(source_project_id, source.config or {}), result_dir, config)
        except Exception as e:
            print(f"[oneclick.v3] source asset sync skipped: {e}")

        task_id = str(uuid.uuid4())[:8]
        estimate = estimate_project(config)
        task = _make_task_record(
            task_id,
            template_project_id=source_project_id,
            project_id=project.id,
            topic=project.topic,
            title=project.title,
            estimate=estimate,
            config=config,
        )
        task["source_project_id"] = source_project_id
        task["template_project_id"] = source_project_id
        task["result_dir"] = str(result_dir)
        ch = _valid_channel(channel)
        if ch is not None:
            task["channel"] = ch
        if episode_code:
            task["episode_code"] = str(episode_code).strip()
        _add_log(
            task,
            f"V3 작업 생성: Studio={source_project_id}, 결과={result_dir}",
            "info",
        )
        _TASKS[task_id] = task
        _save_tasks_to_disk()
        return task
    finally:
        db.close()


def _clone_project_from_template(
    template_project_id: Optional[str],
    topic: str,
    title: Optional[str],
    target_duration: Optional[int] = None,
    *,
    episode_openings: Optional[List[str]] = None,
    episode_endings: Optional[List[str]] = None,
    episode_core_content: Optional[str] = None,
    episode_number: Optional[int] = None,
    next_episode_preview: Optional[str] = None,
    channel: Optional[int] = None,
) -> Project:
    """템플릿의 config 를 얕은 복사해 새 Project 를 만든다.

    template_project_id 가 None 이면 DEFAULT_CONFIG 사용.

    v1.1.42
    -------
    - `target_duration` (초) 이 지정되면 config 에 덮어쓴다. 딸깍 모달의
      "시간" 입력을 그대로 반영한다.
    - `config["__oneclick__"] = True` 마커를 심어 대시보드의 프리셋 목록에서
      자동 제외한다. 사용자 요구: "딸깍 셋팅하면 프리셋이 생성되네? 이럼
      안되지. 프리셋이 중요한거라고". 더 이상 딸깍 실행이 프리셋을 오염시키
      지 않는다. 실제 파이프라인 함수들은 Project 행이 DB 에 있어야 동작하
      므로 행 자체는 계속 만들되, UI 리스트에서만 숨긴다.
    """
    from app.routers.projects import DEFAULT_CONFIG

    db = SessionLocal()
    try:
        base_config: dict = dict(DEFAULT_CONFIG)
        if template_project_id:
            tmpl = (
                db.query(Project)
                .filter(Project.id == template_project_id)
                .first()
            )
            if tmpl and tmpl.config:
                base_config.update(tmpl.config)
            base_config["template_project_id"] = template_project_id
        else:
            base_config.pop("template_project_id", None)

        # oneclick 은 사용자 개입 없이 끝까지 달려야 한다.
        base_config["auto_pause_after_step"] = False

        # v1.1.42: 모달 "시간" 입력 반영
        _force_oneclick_main_length(base_config, target_duration)

        # v1.1.42: 프리셋 목록에서 숨길 마커
        base_config["__oneclick__"] = True

        # v1.2.9: 에피소드 상세 (주제 팝업에서 입력한 값) → config 에 박아두면
        # 이후 스크립트 단계에서 LLM 프롬프트에 주입된다. 빈 배열/빈 문자열은
        # 저장하지 않아 프롬프트 노이즈를 줄인다.
        if episode_openings is not None:
            filtered_op = [str(x or "").strip() for x in (episode_openings or [])]
            filtered_op = [x for x in filtered_op if x]
            if filtered_op:
                base_config["episode_openings"] = filtered_op
        if episode_endings is not None:
            filtered_en = [str(x or "").strip() for x in (episode_endings or [])]
            filtered_en = [x for x in filtered_en if x]
            if filtered_en:
                base_config["episode_endings"] = filtered_en
        if episode_core_content is not None:
            cc = str(episode_core_content or "").strip()
            if cc:
                base_config["episode_core_content"] = cc

        # v1.2.10: 시리즈 연속성 필드.
        if episode_number is not None:
            try:
                n = int(episode_number)
                if n > 0:
                    base_config["episode_number"] = n
            except (TypeError, ValueError):
                pass
        if next_episode_preview is not None:
            nep = str(next_episode_preview or "").strip()
            if nep:
                base_config["next_episode_preview"] = nep

        clean_topic = (topic or "").strip() or "Untitled"
        clean_title = (title or "").strip() or clean_topic[:50]
        clean_title = with_episode_prefix(clean_title, base_config.get("episode_number"))

        # v1.2.29: 채널 번호가 주어지면 config 에 박아둔다. 이후 고아 프로젝트
        # 복구 기능이 이 값을 근거로 해당 채널에 귀속한다.
        try:
            if channel is not None:
                ch_int = int(channel)
                if 1 <= ch_int <= 4:
                    base_config["channel"] = ch_int
        except (TypeError, ValueError):
            pass

        # v1.1.52: 딸깍_주제_YYMMDD-N 형식 project_id 생성
        # v1.2.29: channel 이 지정되면 딸깍_CH{n}_주제_YYMMDD-N 형식으로 생성
        # v1.2.30: episode_number 가 있으면 딸깍_CH{n}_EP{m}_주제_YYMMDD-N 형식으로 생성
        project_id = _generate_oneclick_project_id(
            clean_topic,
            db,
            channel=channel,
            episode_number=base_config.get("episode_number"),
        )

        project = Project(
            id=project_id,
            title=clean_title,
            topic=clean_topic,
            config=base_config,
            status="draft",
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        # 디렉토리 레이아웃 확보
        project_dir = resolve_project_dir(project_id, config=base_config, create=True)
        for sub in ["audio", "images", "videos", "subtitles", "output"]:
            (project_dir / sub).mkdir(parents=True, exist_ok=True)

        # v1.1.52: 템플릿의 에셋 파일을 새 프로젝트로 복사.
        # config 에 상대 경로로 기록된 레퍼런스/캐릭터/로고/간지(interlude)
        # 파일이 새 project_id 디렉토리에도 존재해야 collect_*_images 가
        # 파일을 찾을 수 있다.
        if template_project_id:
            tmpl_dir = resolve_project_dir(template_project_id)
            _copy_template_assets(tmpl_dir, project_dir, base_config)

        return project
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# 진행률 계산
# --------------------------------------------------------------------------- #

def _compute_progress_pct(task: dict) -> float:
    """task 상태 + Redis 컷 카운터를 읽어 0~100 의 총 진행률을 계산.

    각 step_num 의 기여도(STEP_WEIGHTS) 는 완료 시 100% 더해지고, 실행 중인
    스텝은 (컷카운터 / 총 컷 수) 비율만큼 부분 가산된다. render(6) 만 컷 단위
    카운터가 없어 'running' 이면 0, 'completed' 면 풀 가산.

    v1.1.38: 부수효과로 task["current_step_completed/total/label"] 도 갱신하여
    UI 가 "N/M 컷" 표시를 바로 쓸 수 있게 한다.
    """
    project_id = task["project_id"]
    total_cuts = max(1, int(task.get("total_cuts") or 1))
    step_states = task.get("step_states") or {}
    actual_image_count = 0
    try:
        image_dir = resolve_project_dir(
            project_id,
            task.get("config") if isinstance(task.get("config"), dict) else {},
            create=False,
        ) / "images"
        if image_dir.exists():
            actual_image_count = sum(
                1
                for f in image_dir.glob("cut_*.png")
                if f.is_file() and f.stat().st_size > 50
            )
    except Exception:
        actual_image_count = 0
    task.setdefault("completed_cuts_by_step", {})
    task["completed_cuts_by_step"]["4"] = actual_image_count
    # 현재 단계 세부 카운터 초기화 (running 인 스텝을 만나면 덮어씀)
    task["current_step_completed"] = 0
    task["current_step_total"] = 0
    task["current_step_label"] = None

    pct = 0.0
    running_labels = []  # v1.1.53: 병렬 실행 시 여러 라벨 수집
    for _name, step_num, label in STEP_ORDER:
        state = step_states.get(str(step_num), "pending")
        weight = STEP_WEIGHTS.get(step_num, 0)
        if state == "completed":
            if step_num == 4:
                ratio = min(1.0, actual_image_count / total_cuts)
                pct += weight * ratio
                task["completed_cuts_by_step"]["4"] = actual_image_count
            else:
                pct += weight
                # 완료된 단계는 total 만큼 다 채워둔다 — UI 기록용
                task["completed_cuts_by_step"][str(step_num)] = (
                    total_cuts if step_num != 6 else 0
                )
        elif state == "running":
            studio_state = _task_manager_state(project_id, step_num)
            if studio_state is not None and studio_state.status == "running":
                if step_num == 4:
                    completed = actual_image_count
                    total_for_step = total_cuts
                    ratio = min(1.0, completed / max(1, total_for_step))
                else:
                    completed = int(studio_state.completed or 0)
                    total_for_step = int(studio_state.total or 0)
                    ratio = max(0.0, min(1.0, float(studio_state.progress_pct or 0) / 100.0))
                pct += weight * ratio
                task["completed_cuts_by_step"][str(step_num)] = completed
                task["current_step_completed"] = completed
                task["current_step_total"] = total_for_step
                running_labels.append(label)
                continue
            if step_num == 6:
                # 렌더링은 컷 단위 카운터가 없음 — 단계 라벨만 노출
                running_labels.append(label)
                task["current_step_completed"] = 0
                task["current_step_total"] = 0
                continue
            if step_num == 2:
                raw = _redis_get(f"pipeline:step_progress:{project_id}:{step_num}")
                try:
                    completed = int(raw) if raw else 0
                except (TypeError, ValueError):
                    completed = 0
                total_for_step = int(task.get("total_cuts") or total_cuts or 0)
                if completed > 0 and total_for_step > 0:
                    ratio = min(1.0, completed / total_for_step)
                    pct += weight * ratio
                    task["completed_cuts_by_step"][str(step_num)] = completed
                    task["current_step_completed"] = completed
                    task["current_step_total"] = total_for_step
                    task["current_step_cut_progress_pct"] = round(ratio * 100, 1)
                else:
                    pct += weight * 0.5
                    task["current_step_completed"] = 0
                    task["current_step_total"] = 0
                running_labels.append(label)
                continue
            if step_num == 4:
                completed = actual_image_count
            else:
                raw = _redis_get(f"pipeline:step_progress:{project_id}:{step_num}")
                try:
                    completed = int(raw) if raw else 0
                except (TypeError, ValueError):
                    completed = 0
            task["completed_cuts_by_step"][str(step_num)] = completed
            ratio = min(1.0, completed / total_cuts)
            pct += weight * ratio
            task["current_step_completed"] = completed
            task["current_step_total"] = int(task.get("total_cuts") or 0)
            running_labels.append(label)
    # v1.1.53: 병렬 실행 시 "음성 생성 + 이미지 생성" 으로 표시
    task["current_step_label"] = " + ".join(running_labels) if running_labels else None
    return round(min(100.0, pct), 1)


# --------------------------------------------------------------------------- #
# Step 7: 썸네일 생성 + 유튜브 업로드
# --------------------------------------------------------------------------- #

ONECLICK_REQUIRED_SHORTS_UPLOAD_COUNT = 4
ONECLICK_MIN_SHORTS_UPLOAD_COUNT = 3


def _bool_config(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"0", "false", "no", "off", "disabled"}:
            return False
        if text in {"1", "true", "yes", "on", "enabled"}:
            return True
    return bool(value)


def _required_shorts_count(config: Optional[dict]) -> int:
    raw = (config or {}).get("shorts_required_count")
    try:
        return max(1, int(raw or ONECLICK_REQUIRED_SHORTS_UPLOAD_COUNT))
    except (TypeError, ValueError):
        return ONECLICK_REQUIRED_SHORTS_UPLOAD_COUNT


def _minimum_shorts_count(config: Optional[dict]) -> int:
    cfg = config or {}
    raw = cfg.get("shorts_min_required_count")
    try:
        minimum = max(1, int(raw or ONECLICK_MIN_SHORTS_UPLOAD_COUNT))
    except (TypeError, ValueError):
        minimum = ONECLICK_MIN_SHORTS_UPLOAD_COUNT
    return min(minimum, _required_shorts_count(cfg))


def _usable_shorts_files(
    shorts_files: list[Path],
    *,
    min_required: int,
    target_count: int,
    validator: Any | None = None,
) -> tuple[list[Path], list[str]]:
    usable: list[Path] = []
    errors: list[str] = []
    for short_path in shorts_files:
        if len(usable) >= target_count:
            break
        if not short_path.exists() or short_path.stat().st_size <= 0:
            errors.append(f"{short_path.name}: 파일 없음 또는 빈 파일")
            continue
        if validator is not None:
            try:
                error = validator(short_path)
            except Exception as exc:
                error = str(exc)
            if error:
                errors.append(f"{short_path.name}: {str(error)[:300]}")
                continue
        usable.append(short_path)
    if len(usable) < min_required and errors:
        return usable, errors
    return usable, errors


def _youtube_video_id_from_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    m = re.search(r"(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{6,})", text)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{6,}", text):
        return text
    return ""


def _is_youtube_upload_quota_error(exc: BaseException) -> bool:
    text = str(exc or "").lower()
    return any(
        marker in text
        for marker in (
            "uploadlimitexceeded",
            "exceeded the number of videos",
            "video uploads per day",
            "quota metric 'video uploads'",
            'quota metric "video uploads"',
            "videouploadsperday",
            "youtube 영상 업로드 일일 제한",
        )
    )


def _shorts_upload_completion(project_id: str, config: Optional[dict] = None) -> dict[str, Any]:
    cfg = dict(config or {})
    if not _bool_config(cfg.get("shorts_enabled"), True):
        return {
            "enabled": False,
            "required": 0,
            "file_count": 0,
            "uploaded_count": 0,
            "complete": True,
        }

    target = _required_shorts_count(cfg)
    required = _minimum_shorts_count(cfg)
    try:
        project_dir = resolve_project_dir(project_id, cfg, create=False)
        shorts_dir = project_dir / "output" / "shorts"
        shorts_files = sorted(p for p in shorts_dir.glob("short_*.mp4") if p.is_file()) if shorts_dir.exists() else []
        uploads_path = shorts_dir / "shorts_uploads.json"
        uploads: dict[str, Any] = {}
        if uploads_path.exists():
            loaded = json.loads(uploads_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                uploads = loaded
        uploaded_names = {
            str(name)
            for name, item in uploads.items()
            if isinstance(item, dict) and str(item.get("url") or "").strip()
        }
        legacy_uploads = cfg.get("shorts_uploads")
        if isinstance(legacy_uploads, list):
            for item in legacy_uploads:
                if not isinstance(item, dict) or not str(item.get("url") or "").strip():
                    continue
                path_name = Path(str(item.get("path") or item.get("file") or "")).name
                if not path_name:
                    try:
                        path_name = f"short_{int(item.get('index') or 0)}.mp4"
                    except (TypeError, ValueError):
                        path_name = ""
                if path_name:
                    uploaded_names.add(path_name)
        legacy_urls = cfg.get("youtube_shorts_urls")
        if isinstance(legacy_urls, list):
            for idx, url in enumerate(legacy_urls, start=1):
                if str(url or "").strip():
                    uploaded_names.add(f"short_{idx}.mp4")
        uploaded_count = sum(1 for path in shorts_files if path.name in uploaded_names)
        return {
            "enabled": True,
            "required": required,
            "target": target,
            "file_count": len(shorts_files),
            "uploaded_count": uploaded_count,
            "complete": len(shorts_files) >= required and uploaded_count >= required,
            "shorts_dir": str(shorts_dir),
        }
    except Exception as exc:
        return {
            "enabled": True,
            "required": required,
            "target": target,
            "file_count": 0,
            "uploaded_count": 0,
            "complete": False,
            "error": str(exc),
        }


def _render_outputs_ready_for_upload(project_id: str, config: Optional[dict] = None) -> tuple[bool, str]:
    """Validate rendered main/shorts files before entering YouTube upload."""
    from app.services.youtube_service import _validate_upload_media_file

    cfg = dict(config or {})
    project_dir = resolve_project_dir(project_id, cfg, create=False)
    output_dir = project_dir / "output"
    final_video = next(
        (
            p
            for p in (
                output_dir / "final_with_subtitles.mp4",
                output_dir / "final.mp4",
                output_dir / "merged.mp4",
            )
            if p.exists() and p.is_file()
        ),
        None,
    )
    if final_video is None:
        return False, "최종 영상 파일 없음"
    final_error = _validate_upload_media_file(final_video)
    if final_error:
        return False, f"최종 영상 디코딩 실패: {final_video.name} ({final_error[:300]})"

    if not _bool_config(cfg.get("shorts_enabled"), True):
        return True, ""

    target = _required_shorts_count(cfg)
    required = _minimum_shorts_count(cfg)
    shorts_dir = output_dir / "shorts"
    shorts_files = sorted(shorts_dir.glob("short_*.mp4")) if shorts_dir.exists() else []
    if len(shorts_files) < required:
        return False, f"쇼츠 렌더 결과 부족: {len(shorts_files)}/{target} (최소 {required}개 필요)"
    usable, errors = _usable_shorts_files(
        shorts_files,
        min_required=required,
        target_count=target,
        validator=_validate_upload_media_file,
    )
    if len(usable) < target:
        detail = "; ".join(errors[:3]) if errors else "사용 가능한 쇼츠 파일 부족"
        return False, f"쇼츠 사용 가능 결과 부족: {len(usable)}/{target} ({detail})"
    return True, ""


def _mark_project_steps_pending(project_id: str, from_step: int) -> None:
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return
        states = dict(project.step_states or {})
        for _slug, step_num, _label in STEP_ORDER:
            if step_num >= from_step:
                states[str(step_num)] = "pending"
        project.step_states = states
        if project.status in ("completed", "failed", "cancelled"):
            project.status = "draft"
        try:
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(project, "step_states")
        except Exception:
            pass
        db.commit()
    finally:
        db.close()


async def _step_youtube_upload(
    project_id: str,
    config: dict,
    channel: Optional[int] = None,
    task_id: Optional[str] = None,
) -> dict:
    """썸네일을 자동 생성하고 YouTube 에 업로드한다.

    channel (1~4) 가 지정되면 채널별 OAuth 토큰을 우선 사용한다.
    채널 토큰이 없으면 프로젝트 토큰 → 전역 토큰 순으로 폴백.
    """
    from app.services.thumbnail_service import (
        generate_ai_thumbnail,
        suppress_foreign_hangul_thumbnail_overlay,
    )
    from app.services.youtube_service import (
        YouTubeUploader,
        YouTubeAuthError,
        YouTubeUploadError,
        _validate_upload_media_file,
    )
    from pathlib import Path

    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise RuntimeError("project not found")

        # 1) 썸네일 자동 생성 (AI overlay 모드)
        # v1.1.55: script.json 에서 LLM 이 생성한 title 을 우선 사용
        script_path_t = resolve_project_dir(project_id, config, create=False) / "script.json"
        script_title = ""
        if script_path_t.exists():
            try:
                with open(script_path_t, "r", encoding="utf-8") as f:
                    _sd = json.load(f)
                script_title = (_sd.get("title") or "").strip()
            except Exception:
                pass
        title = strong_main_upload_title(
            script_title or (project.title or project.topic or "Untitled").strip(),
            config.get("episode_number") or (project.config or {}).get("episode_number"),
        )

        thumb_dir = resolve_project_dir(project_id, config, create=True) / "output"
        thumb_path = thumb_dir / "thumbnail.png"

        if not thumb_path.exists():
            try:
                from app.services.image.factory import resolve_image_model

                image_model = resolve_image_model(
                    config.get("thumbnail_model") or config.get("image_model")
                )
                # script.json 에서 thumbnail_prompt 를 가져온다
                thumb_prompt = "YouTube thumbnail: " + title
                script_data = {}
                if script_path_t.exists():
                    try:
                        with open(script_path_t, "r", encoding="utf-8") as f:
                            script_data = json.load(f)
                        tp = script_data.get("thumbnail_prompt") or ""
                        if tp.strip():
                            thumb_prompt = tp.strip()
                    except Exception:
                        pass

                from app.services.thumbnail_service import build_clickbait_thumbnail_overlay
                overlay_text = build_clickbait_thumbnail_overlay(script_data, title, config)
                result = await generate_ai_thumbnail(
                    project_id=project_id,
                    image_prompt=thumb_prompt,
                    image_model_id=image_model,
                    overlay_title_text=suppress_foreign_hangul_thumbnail_overlay(overlay_text or title, config),
                    config=config,
                )
                print(f"[oneclick] thumbnail generated: {result.get('path')}")
            except Exception as e:
                import traceback
                # 썸네일 실패해도 업로드는 진행 (썸네일 없이)
                print(f"[oneclick] thumbnail generation FAILED (continuing without): {e}\n{traceback.format_exc()}")

        # 2) YouTube 업로드
        final_video = thumb_dir / "final_with_subtitles.mp4"
        if not final_video.exists():
            # merged.mp4 폴백
            final_video = thumb_dir / "merged.mp4"
        if not final_video.exists():
            raise RuntimeError("최종 영상 파일이 없습니다.")

        # v1.1.60 → v1.1.55 hotfix: 채널 결정 우선순위 재정렬.
        # **프리셋의 youtube_channel 이 항상 최우선** 이다. 큐 row 의 channel 은
        # 사용자가 UI 에서 명시 선택하지 않으면 _queue_normalize 가 1 로 기본값을
        # 박는데, 그 기본값 1 이 프리셋의 실제 채널을 덮어써서 "무서운이야기"
        # 프리셋이 CH1(=다른 계정) 으로 잘못 업로드되던 사고가 났다.
        # 이제는:
        #   1. config["youtube_channel"]  (프리셋 — 가장 신뢰도 높음)
        #   2. 호출 시 명시한 channel (큐 row)
        # 두 값이 충돌하면 프리셋 우선 + 경고 로그.
        ch_int: Optional[int] = None
        cfg_ch_raw = config.get("youtube_channel")
        cfg_ch_int: Optional[int] = None
        if cfg_ch_raw is not None and str(cfg_ch_raw).strip() != "":
            try:
                cfg_ch_int = int(cfg_ch_raw)
            except Exception:
                cfg_ch_int = None
        queue_ch_int: Optional[int] = None
        if channel is not None:
            try:
                queue_ch_int = int(channel)
            except Exception:
                queue_ch_int = None
        if cfg_ch_int is not None:
            ch_int = cfg_ch_int
            if queue_ch_int is not None and queue_ch_int != cfg_ch_int:
                print(
                    f"[oneclick] ⚠ 채널 충돌: 큐 row 는 CH{queue_ch_int}, "
                    f"프리셋 youtube_channel 은 CH{cfg_ch_int} → 프리셋 우선 적용. "
                    f"(과거에는 큐 row 가 이겨서 잘못된 계정으로 업로드되던 사고)"
                )
        else:
            ch_int = queue_ch_int

        # 업로드 OAuth 우선순위
        # 1) 프리셋 프로젝트의 youtube_token.json
        # 2) 현재 생성 프로젝트의 youtube_token.json
        # 3) 채널별 token_chN.json
        #
        # 전역 token.json 으로 조용히 폴백하면 엉뚱한 계정으로 업로드될 수 있으므로
        # oneclick 에서는 사용하지 않는다.
        uploader = None
        uploader_token_source = None
        uploader_project_id = None
        uploader_channel_id = None
        template_project_id = (
            config.get("template_project_id")
            or (project.config or {}).get("template_project_id")
            or None
        )
        if template_project_id:
            template_uploader = YouTubeUploader(project_id=str(template_project_id))
            if template_uploader.is_authenticated():
                uploader = template_uploader
                uploader_token_source = "project"
                uploader_project_id = str(template_project_id)
                print(f"[oneclick] using preset-bound YouTube token ({template_project_id})")

        if uploader is None:
            project_uploader = YouTubeUploader(project_id=project_id)
            if project_uploader.is_authenticated():
                uploader = project_uploader
                uploader_token_source = "project"
                uploader_project_id = project_id
                print(f"[oneclick] using project-bound YouTube token ({project_id})")

        if uploader is None and ch_int is not None:
            ch_uploader = YouTubeUploader(channel_id=ch_int)
            if ch_uploader.is_authenticated():
                uploader = ch_uploader
                uploader_token_source = "channel"
                uploader_channel_id = ch_int
                print(f"[oneclick] using channel {ch_int} YouTube token")
            else:
                # v1.1.60: 프리셋이 채널을 명시했는데 그 채널이 인증 안 된 상태라면
                # 잘못된 계정으로 올라가는 사고를 막기 위해 즉시 실패시킨다.
                raise RuntimeError(
                    f"CH{ch_int} YouTube 인증이 안 되어 있습니다. "
                    f"딸깍 위젯 → 채널별 YouTube 계정 → CH{ch_int} '연결' 을 먼저 해 주세요. "
                    f"(다른 계정 토큰으로 잘못 업로드되는 것을 막기 위해 업로드를 중단합니다.)"
                )
        if uploader is None or not uploader.is_authenticated():
            raise RuntimeError(
                "YouTube 인증이 설정되지 않았습니다. "
                "프리셋 또는 현재 프로젝트에 연결된 YouTube OAuth를 먼저 확인해주세요."
            )

        # v1.1.55: script.json 에서 description/tags 를 가져와서 config 폴백보다 우선
        script_description = ""
        script_tags: list[str] = []
        script_topic = ""
        narration_seed = ""
        script_path = resolve_project_dir(project_id, config, create=False) / "script.json"
        if script_path.exists():
            try:
                with open(script_path, "r", encoding="utf-8") as f:
                    script_data = json.load(f)
                script_description = (script_data.get("description") or "").strip()
                script_topic = (script_data.get("topic") or script_data.get("title") or "").strip()
                raw_tags = script_data.get("tags") or []
                if isinstance(raw_tags, list):
                    script_tags = [t.strip() for t in raw_tags if isinstance(t, str) and t.strip()]
                cuts = script_data.get("cuts") or []
                if isinstance(cuts, list):
                    narration_seed = " ".join(
                        (cut.get("narration") or "").strip()
                        for cut in cuts[:30]
                        if isinstance(cut, dict) and (cut.get("narration") or "").strip()
                    )
            except Exception:
                pass

        # 우선순위: config(프리셋) > script.json(LLM생성) > project.topic(폴백)
        description = (
            (config.get("youtube_description") or "").strip()
            or script_description
            or (project.topic or "").strip()
        )
        config_tags = [t.strip() for t in (config.get("youtube_tags") or "").split(",") if t.strip()] if config.get("youtube_tags") else []
        metadata_language = config.get("language") or "ko"
        metadata_topic = script_topic or project.topic or title
        description = format_description(
            description,
            title=title,
            topic=metadata_topic,
            narration=narration_seed,
            language=metadata_language,
        )
        tags = expand_tags(
            config_tags if config_tags else script_tags,
            title=title,
            topic=metadata_topic,
            narration=narration_seed,
            language=metadata_language,
        )
        privacy = config.get("youtube_privacy") or "private"
        print(f"[oneclick] YouTube upload: privacy={privacy}, desc_len={len(description)}, tags={len(tags)}, thumb={thumb_path.exists()}")

        use_thumb = thumb_path.exists()
        upload_progress_last = {"pct": -1}

        def _upload_progress_callback(pct: int) -> None:
            if not task_id:
                return
            task = _TASKS.get(str(task_id))
            if not task:
                return
            try:
                pct_i = max(0, min(100, int(pct)))
            except Exception:
                return
            # Persist coarse progress only. This keeps the safety watchdog alive
            # during long uploads without hammering the task JSON file.
            if pct_i < 100 and pct_i - int(upload_progress_last.get("pct") or 0) < 5:
                return
            upload_progress_last["pct"] = pct_i
            task["sub_status"] = f"uploading:{pct_i}"
            task["current_step_cut_progress_pct"] = pct_i
            task["current_step_completed"] = pct_i
            task["current_step_total"] = 100
            task["current_step_label"] = f"유튜브 업로드 {pct_i}%"
            task["progress_pct"] = _compute_progress_pct(task)
            _save_tasks_to_disk()

        existing_video_url = str(project.youtube_url or "").strip()
        existing_video_id = _youtube_video_id_from_url(existing_video_url)
        if existing_video_url and existing_video_id:
            video_url = existing_video_url
            main_video_id = existing_video_id
            main_state = {"processed": False}
            main_visible = {"verification_method": "existing_url"}
            print(f"[oneclick] YouTube main already uploaded, skip main upload: {video_url}")
        else:
            result = await asyncio.to_thread(
                uploader.upload,
                str(final_video),
                title,
                description,
                tags,
                str(thumb_path) if use_thumb else None,
                privacy,
                config.get("language") or "ko",
                None,   # category_id
                False,  # made_for_kids
                _upload_progress_callback,   # progress_callback
            )

            video_url = result.get("url")
            if video_url:
                print(f"[oneclick] YouTube uploaded: {video_url}")
            else:
                raise RuntimeError(f"업로드 성공했으나 URL 이 비어있습니다: {result!r}")

            main_video_id = str(result.get("video_id") or "").strip()
            if not main_video_id:
                raise YouTubeUploadError("본편 업로드 응답에 video_id가 없습니다.")
            main_state = {"processed": False}
            main_visible = {"verification_method": "videos.insert_response"}

        main_playlist_result = None
        main_playlist_id = str(
            config.get("youtube_playlist_id")
            or ((config.get("upload") or {}).get("playlist_id") if isinstance(config.get("upload"), dict) else "")
            or ""
        ).strip()
        if main_playlist_id:
            try:
                main_playlist_result = await asyncio.to_thread(
                    uploader.add_to_playlist_if_missing,
                    main_playlist_id,
                    main_video_id,
                )
                print(
                    "[oneclick] YouTube main playlist linked: "
                    f"{main_playlist_id} already={bool(main_playlist_result.get('already_present'))}"
                )
            except Exception as exc:
                print(f"[oneclick] YouTube main playlist link failed: {exc}")

        uploaded_videos: list[dict[str, Any]] = [{
            "kind": "main",
            "title": title,
            "url": video_url,
            "video_id": main_video_id,
            "processing_verified": False,
            "processed": False,
            "terminal_failure": False,
            "failed_reason": None,
            "studio_verified": False,
            "verification_method": main_visible.get("verification_method"),
            "playlist_id": main_playlist_id or None,
            "playlist_item_id": (main_playlist_result or {}).get("item_id"),
            "playlist_already_present": bool((main_playlist_result or {}).get("already_present")),
            "last_checked_at": _utcnow_iso(),
        }]
        print(f"[oneclick] YouTube upload accepted: {video_url}")
        project.youtube_url = video_url
        db.commit()

        # 3) Shorts 자동 업로드
        # 최종 렌더 단계(render_video_with_subtitles)가 output/shorts/short_*.mp4 를
        # 생성한다. 딸깍 업로드는 본편만 올리고 끝나면 사용자가 기대한 자동화와 다르므로,
        # 같은 채널/프라이버시로 숏츠도 이어서 업로드한다.
        shorts_enabled = _bool_config(config.get("shorts_enabled"), True)
        shorts_dir = thumb_dir / "shorts"
        shorts_files = sorted(shorts_dir.glob("short_*.mp4")) if shorts_enabled and shorts_dir.exists() else []
        target_shorts = _required_shorts_count(config)
        required_shorts = _minimum_shorts_count(config)
        usable_shorts_files, unusable_shorts_errors = _usable_shorts_files(
            shorts_files,
            min_required=required_shorts,
            target_count=target_shorts,
            validator=_validate_upload_media_file,
        )
        if shorts_enabled and len(usable_shorts_files) < target_shorts:
            detail = "; ".join(unusable_shorts_errors[:3]) if unusable_shorts_errors else ""
            raise RuntimeError(
                f"숏츠 렌더 결과 부족: {len(usable_shorts_files)}/{target_shorts} "
                f"({shorts_dir})"
                + (f" — {detail}" if detail else "")
            )
        if usable_shorts_files:
            shorts_uploads_path = shorts_dir / "shorts_uploads.json"
            shorts_meta_by_file: dict[str, dict[str, Any]] = {}
            try:
                shorts_meta_path = shorts_dir / "shorts.json"
                if shorts_meta_path.exists():
                    shorts_meta = json.loads(shorts_meta_path.read_text(encoding="utf-8"))
                    for entry in shorts_meta.get("results") or []:
                        if not isinstance(entry, dict):
                            continue
                        path_name = Path(str(entry.get("path") or "")).name
                        if path_name:
                            shorts_meta_by_file[path_name] = entry
                        idx_val = entry.get("index")
                        if idx_val:
                            shorts_meta_by_file[f"short_{idx_val}.mp4"] = entry
            except Exception as e:
                print(f"[oneclick] shorts metadata load skipped: {e}")
            shorts_uploads: dict[str, Any] = {}
            if shorts_uploads_path.exists():
                try:
                    loaded = json.loads(shorts_uploads_path.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        shorts_uploads = loaded
                except Exception:
                    shorts_uploads = {}

            uploaded_items: list[dict[str, Any]] = []
            short_upload_errors: list[str] = []
            for idx, short_path in enumerate(usable_shorts_files, start=1):
                key = short_path.name
                existing = shorts_uploads.get(key)
                if isinstance(existing, dict) and existing.get("url"):
                    print(f"[oneclick] Shorts already uploaded, skip: {key} -> {existing.get('url')}")
                    uploaded_items.append(existing)
                    continue

                shorts_meta = shorts_meta_by_file.get(key) or {}
                short_title_base = (
                    str(shorts_meta.get("title") or "").replace("\n", " ").strip()
                    or title.strip()
                    or project.title
                    or project.topic
                    or "Shorts"
                )
                short_title_base = without_episode_prefix(short_title_base) or "Shorts"
                short_title = shorts_upload_title(
                    short_title_base,
                    index=idx,
                    total=len(usable_shorts_files),
                    context_title=metadata_topic or project.title or project.topic,
                    recommended_hashtags=recommended_shorts_title_hashtags(
                        title=short_title_base,
                        topic=metadata_topic,
                        narration=narration_seed,
                        language=metadata_language,
                    ),
                )
                short_description = format_description(
                    description or project.topic or "",
                    title=short_title,
                    topic=metadata_topic,
                    narration=narration_seed,
                    language=metadata_language,
                    shorts=True,
                )
                short_tags = expand_tags(
                    tags or [],
                    title=short_title,
                    topic=metadata_topic,
                    narration=narration_seed,
                    language=metadata_language,
                    shorts=True,
                )

                print(f"[oneclick] YouTube Shorts upload: {key}, title={short_title!r}")
                def _shorts_progress_callback(pct: int, _key: str = key) -> None:
                    if not task_id:
                        return
                    task = _TASKS.get(str(task_id))
                    if not task:
                        return
                    try:
                        pct_i = max(0, min(100, int(pct)))
                    except Exception:
                        return
                    task["sub_status"] = f"shorts-uploading:{_key}:{pct_i}"
                    task["current_step_cut_progress_pct"] = pct_i
                    task["current_step_label"] = f"쇼츠 업로드 {pct_i}%"
                    _save_tasks_to_disk()

                try:
                    short_result = await asyncio.to_thread(
                        uploader.upload,
                        str(short_path),
                        short_title,
                        short_description,
                        short_tags,
                        None,  # thumbnail_path
                        privacy,
                        config.get("language") or "ko",
                        None,   # category_id
                        False,  # made_for_kids
                        _shorts_progress_callback,   # progress_callback
                    )
                except Exception as exc:
                    message = f"{key}: {type(exc).__name__}: {exc}"
                    short_upload_errors.append(message)
                    raise
                short_url = short_result.get("url")
                if not short_url:
                    raise RuntimeError(f"숏츠 업로드 성공했으나 URL 이 비어있습니다: {short_result!r}")
                item = {
                    "file": key,
                    "title": short_title,
                    "url": short_url,
                    "video_id": short_result.get("video_id"),
                    "studio_verified": True,
                    "processing_verified": False,
                }
                shorts_playlist_id = str(
                    config.get("youtube_shorts_playlist_id")
                    or config.get("shorts_playlist_id")
                    or ""
                ).strip()
                shorts_playlist_result = None
                if shorts_playlist_id and item.get("video_id"):
                    try:
                        shorts_playlist_result = await asyncio.to_thread(
                            uploader.add_to_playlist_if_missing,
                            shorts_playlist_id,
                            str(item.get("video_id")),
                        )
                        item["playlist_id"] = shorts_playlist_id
                        item["playlist_item_id"] = shorts_playlist_result.get("item_id")
                        item["playlist_already_present"] = bool(shorts_playlist_result.get("already_present"))
                        print(
                            "[oneclick] YouTube Shorts playlist linked: "
                            f"{shorts_playlist_id} already={bool(shorts_playlist_result.get('already_present'))}"
                        )
                    except Exception as exc:
                        item["playlist_error"] = str(exc)
                        print(f"[oneclick] YouTube Shorts playlist link failed: {exc}")
                uploaded_videos.append({
                    "kind": "shorts",
                    "file": key,
                    "title": short_title,
                    "url": short_url,
                    "video_id": short_result.get("video_id"),
                    "processing_verified": False,
                    "playlist_id": shorts_playlist_id or None,
                    "playlist_item_id": (shorts_playlist_result or {}).get("item_id"),
                    "playlist_already_present": bool((shorts_playlist_result or {}).get("already_present")),
                })
                shorts_uploads[key] = item
                uploaded_items.append(item)
                shorts_uploads_path.write_text(
                    json.dumps(shorts_uploads, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                print(f"[oneclick] YouTube Shorts upload accepted, processing pending: {short_url}")

            if shorts_enabled and len(uploaded_items) < target_shorts:
                detail = "; ".join(short_upload_errors[:3]) if short_upload_errors else ""
                raise RuntimeError(
                    f"숏츠 업로드 결과 부족: {len(uploaded_items)}/{target_shorts} "
                    + (f" — {detail}" if detail else "")
                )

            cfg = dict(project.config or {})
            cfg["youtube_shorts_urls"] = [
                item.get("url") for item in uploaded_items
                if isinstance(item, dict) and item.get("url")
            ]
            if short_upload_errors:
                cfg["youtube_shorts_partial_errors"] = short_upload_errors
            project.config = cfg
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(project, "config")
            db.commit()
            print(f"[oneclick] YouTube Shorts uploaded count: {len(uploaded_items)}")

        cfg = dict(project.config or {})
        cfg["youtube_upload_result"] = {
            "status": "completed",
            "channel": ch_int,
            "uploader_token_source": uploader_token_source,
            "uploader_project_id": uploader_project_id,
            "uploader_channel_id": uploader_channel_id,
            "completed_at": _utcnow_iso(),
            "videos": uploaded_videos,
        }
        project.config = cfg
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(project, "config")
        db.commit()
        return cfg["youtube_upload_result"]
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# 실제 실행 코루틴
# --------------------------------------------------------------------------- #

def _sync_task_models_from_config(task: dict, config: dict) -> None:
    """v1.2.16: 현재 실행 중인 config 기준으로 task["models"] 를 최신화.

    사용자 요구: "이거 실제로 사용 되는 AI 모델로 실시간 변경 되게 해."
    task["models"] 는 prepare_task 시점의 config 에서 한 번만 채워졌다.
    prepare 와 실제 실행 사이에 프리셋/모델 설정이 바뀌면 Live UI 에 구식
    값이 보이는 문제가 있었다. 실행 단계 진입 직전/각 스텝 시작 직전에
    이 헬퍼로 task["models"] 를 덮어써, 현재 실제로 전달 중인 config 값을
    노출한다. 이미지 스텝의 런타임 폴백(예: nano-banana-3) 은 별도 경로
    (update_task_image_model) 로 반영된다.
    """
    try:
        from app.services.video.factory import DEFAULT_VIDEO_MODEL, resolve_video_model
        video_model = resolve_video_model(config.get("video_model", DEFAULT_VIDEO_MODEL))
        models = task.setdefault("models", {})
        models["script"] = config.get("script_model", "") or ""
        models["tts"] = config.get("tts_model", "") or ""
        models["tts_voice"] = config.get("tts_voice_id", "") or ""
        models["image"] = config.get("image_model", "") or ""
        models["video"] = video_model or ""
        # thumbnail 은 Step 6 직전에만 쓰이고, UI 스텝 라벨과는 무관하지만
        # 일관성 위해 같이 갱신.
        models["thumbnail"] = config.get("thumbnail_model", "") or ""
    except Exception:
        # 모델 라벨 갱신 실패는 파이프라인 동작에 영향 없음 — 조용히 무시.
        pass


def _backfill_task_models_from_estimate(task: dict) -> bool:
    """Fill empty task model labels from estimate.models_used."""
    if not isinstance(task, dict):
        return False
    estimate_models = dict((task.get("estimate") or {}).get("models_used") or {})
    if not estimate_models:
        return False
    models = task.setdefault("models", {})
    changed = False
    for key in ("script", "tts", "image", "video", "thumbnail"):
        value = str(estimate_models.get(key) or "").strip()
        if value and not str(models.get(key) or "").strip():
            models[key] = value
            changed = True
    return changed


_LIVE_REFRESH_STATUSES = {"prepared", "queued", "running", "paused"}
_LIVE_MODEL_KEYS = ("script", "tts", "tts_voice", "image", "video", "thumbnail")
_HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
_JAPANESE_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")


def _sync_task_display_language(task: dict) -> bool:
    """Keep live task title aligned with the generated script language."""
    if not isinstance(task, dict):
        return False
    pid = task.get("project_id")
    if not pid:
        return False
    try:
        project = _load_project(pid)
        cfg = dict((project.config if project else None) or {})
        lang = str(cfg.get("language") or "").strip().lower()
        if lang not in {"ja", "jp", "jpn", "japanese"}:
            return False
        current = str(task.get("title") or "")
        if current and not _HANGUL_RE.search(current):
            return False
        script_path = resolve_project_dir(pid, cfg, create=False) / "script.json"
        if not script_path.exists():
            return False
        script = json.loads(script_path.read_text(encoding="utf-8"))
        title = str(script.get("title") or "").strip()
        if not title or _HANGUL_RE.search(title) or not _JAPANESE_RE.search(title):
            return False
        if task.get("title") == title:
            return False
        task["title"] = title
        return True
    except Exception:
        return False
_ONECLICK_CLONE_PRESERVE_KEYS = (
    "__oneclick__",
    "__oneclick_v3__",
    "template_project_id",
    "source_project_id",
    "result_dir",
    "result_series_dir",
    "result_channel_dir",
    "result_episode_dir",
    "topic",
    "episode_number",
    "series",
    "episode_code",
    "episode_id",
    "episode_openings",
    "episode_endings",
    "episode_core_content",
    "next_episode_preview",
    "cut_video_duration",
    "script_tts_target_sec",
    "script_tts_tolerance_sec",
    "target_duration",
    "target_cuts",
    "channel",
)


def _valid_channel(value: Any) -> Optional[int]:
    try:
        ch = int(value)
        if 1 <= ch <= 4:
            return ch
    except (TypeError, ValueError):
        pass
    return None


def _merge_template_config(
    clone_config: Optional[dict],
    template_config: Optional[dict],
    template_project_id: Optional[str],
) -> dict:
    """Build the effective config for a oneclick clone linked to a Studio preset."""
    clone_cfg = dict(clone_config or {})
    template_cfg = dict(template_config or {})
    effective = {**clone_cfg, **template_cfg}
    for key in _ONECLICK_CLONE_PRESERVE_KEYS:
        if key in clone_cfg:
            effective[key] = clone_cfg[key]
    if template_project_id:
        effective["template_project_id"] = str(template_project_id)
    return effective


def _effective_live_config_for_task(task: dict) -> dict:
    """Return the config Live UI should display for an active oneclick task."""
    project_id = str(task.get("project_id") or "").strip()
    project = _load_project(project_id) if project_id else None
    project_config = dict(project.config or {}) if project and isinstance(project.config, dict) else {}
    template_project_id = (
        task.get("template_project_id")
        or project_config.get("template_project_id")
        or None
    )
    if not template_project_id:
        return project_config

    template = _load_project(str(template_project_id))
    template_config = dict(template.config or {}) if template and isinstance(template.config, dict) else {}
    effective = _merge_template_config(project_config, template_config, str(template_project_id))
    return effective


def _refresh_task_estimate(task: dict) -> bool:
    project_id = str(task.get("project_id") or "").strip()
    config = _effective_live_config_for_task(task) if project_id else dict(task.get("config") or {})
    if not config:
        config = dict(task.get("config") or {})
    if not config:
        return False
    estimate = estimate_project(config)
    if task.get("estimate") == estimate:
        return False
    task["estimate"] = estimate
    return True


def _effective_project_config(project_id: str, fallback_config: Optional[dict] = None) -> dict:
    """Return project config with the linked preset's current values applied."""
    project = _load_project(project_id)
    project_config = (
        dict(project.config or {})
        if project and isinstance(project.config, dict)
        else dict(fallback_config or {})
    )
    template_project_id = project_config.get("template_project_id") or (fallback_config or {}).get("template_project_id")
    if not template_project_id:
        return project_config

    template = _load_project(str(template_project_id))
    template_config = dict(template.config or {}) if template and isinstance(template.config, dict) else {}
    if not template_config:
        return project_config
    effective = _merge_template_config(project_config, template_config, str(template_project_id))
    return effective


def _project_has_db_script_cuts(project_id: str) -> tuple[bool, int]:
    if not project_id:
        return False, 0
    db = SessionLocal()
    try:
        total = (
            db.query(Cut)
            .filter(Cut.project_id == project_id)
            .count()
        )
        if total <= 0:
            return False, 0
        usable = (
            db.query(Cut)
            .filter(
                Cut.project_id == project_id,
                Cut.narration.isnot(None),
                Cut.image_prompt.isnot(None),
            )
            .count()
        )
        return usable > 0, int(total)
    finally:
        db.close()


def _link_existing_audio_files(project_id: str, project_dir: Path) -> tuple[int, int]:
    """Attach existing audio/cut_N files to DB cuts without calling TTS APIs."""
    if not project_id:
        return 0, 0
    audio_dir = project_dir / "audio"
    if not audio_dir.exists():
        return 0, 0
    db = SessionLocal()
    linked = 0
    total = 0
    try:
        cuts = db.query(Cut).filter(Cut.project_id == project_id).order_by(Cut.cut_number).all()
        total = len(cuts)
        for cut in cuts:
            try:
                num = int(cut.cut_number)
            except (TypeError, ValueError):
                continue
            candidates = [
                audio_dir / f"cut_{num}.mp3",
                audio_dir / f"cut_{num:03d}.mp3",
                audio_dir / f"cut_{num}.wav",
                audio_dir / f"cut_{num:03d}.wav",
            ]
            found = None
            for candidate in candidates:
                try:
                    if candidate.exists() and candidate.stat().st_size > 100:
                        found = candidate
                        break
                except OSError:
                    continue
            if not found:
                continue
            rel = found.relative_to(project_dir).as_posix()
            if cut.audio_path != rel:
                cut.audio_path = rel
            if not cut.status or str(cut.status).lower() in {"pending", "failed", "cancelled"}:
                cut.status = "completed"
            linked += 1
        if linked:
            project = db.query(Project).filter(Project.id == project_id).first()
            if project:
                states = dict(project.step_states or {})
                if total and linked >= total:
                    states["3"] = "completed"
                project.step_states = states
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(project, "step_states")
            db.commit()
        return linked, total
    finally:
        db.close()


def _persist_project_config_if_changed(project_id: str, config: dict) -> bool:
    db = SessionLocal()
    try:
        from sqlalchemy.orm.attributes import flag_modified

        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return False
        old_config = dict(project.config or {}) if isinstance(project.config, dict) else {}
        if old_config == config:
            return False
        project.config = dict(config or {})
        flag_modified(project, "config")
        db.commit()
        return True
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        print(f"[oneclick] project config persist failed ({project_id}): {e}")
        return False
    finally:
        db.close()


def _refresh_task_from_current_preset(task: dict, *, persist_project: bool = True) -> dict:
    """Apply the linked preset's current config to the task and project clone."""
    project_id = str(task.get("project_id") or "").strip()
    if not project_id:
        return {}

    old_models = dict(task.get("models") or {})
    old_estimate_models = dict((task.get("estimate") or {}).get("models_used") or {})
    config = _effective_project_config(project_id, task.get("config") if isinstance(task.get("config"), dict) else None)
    if not config:
        return {}

    if persist_project:
        _persist_project_config_if_changed(project_id, config)

    _sync_task_models_from_config(task, config)
    try:
        task["estimate"] = estimate_project(config)
    except Exception:
        pass

    changes = []
    new_models = task.get("models") or {}
    for key in _LIVE_MODEL_KEYS:
        if old_models.get(key, "") != new_models.get(key, ""):
            changes.append(f"{key}: {old_models.get(key, '') or '(없음)'} -> {new_models.get(key, '') or '(없음)'}")

    new_estimate_models = dict((task.get("estimate") or {}).get("models_used") or {})
    for key in ("script", "tts", "image", "video"):
        if old_estimate_models.get(key, "") != new_estimate_models.get(key, ""):
            changes.append(
                f"estimate.{key}: {old_estimate_models.get(key, '') or '(없음)'}"
                f" -> {new_estimate_models.get(key, '') or '(없음)'}"
            )

    if changes:
        _add_log(task, "ℹ 프리셋 현재 설정 반영: " + "; ".join(changes))
    return config


_STUDIO_STEP_KEYS = {
    2: "script",
    3: "voice",
    4: "image",
    5: "video",
    6: "render",
}


def _task_manager_state(project_id: str, step_num: int):
    step_key = _STUDIO_STEP_KEYS.get(int(step_num))
    if not step_key:
        return None
    try:
        from app.services import task_manager

        return task_manager.get_task(project_id, step_key)
    except Exception:
        return None


def _cancel_studio_task_manager_steps(project_id: str | None) -> None:
    if not project_id:
        return
    try:
        from app.services import task_manager

        for step_key in _STUDIO_STEP_KEYS.values():
            task_manager.cancel_task(str(project_id), step_key)
    except Exception:
        pass


def _sync_v3_run_project_from_source(task: dict, *, step_label: str = "") -> dict:
    """Copy the linked Studio project's latest config into the run project."""
    project_id = str(task.get("project_id") or "").strip()
    if not project_id:
        return {}

    project = _load_project(project_id)
    project_config = dict(project.config or {}) if project and isinstance(project.config, dict) else {}
    source_project_id = str(
        task.get("source_project_id")
        or project_config.get("source_project_id")
        or task.get("template_project_id")
        or project_config.get("template_project_id")
        or ""
    ).strip()
    if not source_project_id:
        return project_config

    source = _load_project(source_project_id)
    if not source:
        raise RuntimeError(f"연결된 Studio 프로젝트를 찾을 수 없습니다: {source_project_id}")

    source_config = dict(source.config or {})
    config = _merge_template_config(project_config, source_config, source_project_id)
    # V3 작업대 본편은 원본 Studio 프리셋의 짧은 테스트 길이를 따라가면 안 된다.
    # 연결된 Studio가 60초 테스트폼이어도 실행 프로젝트는 항상 150컷/600초로 고정한다.
    _force_oneclick_main_length(config)
    config["__oneclick__"] = True
    config["__oneclick_v3__"] = True
    config["template_project_id"] = source_project_id
    config["source_project_id"] = source_project_id
    config["auto_pause_after_step"] = False
    if project:
        config["topic"] = project.topic or config.get("topic") or ""

    result_dir = resolve_project_dir(project_id, config, create=True)
    config["result_dir"] = str(result_dir)
    parsed = parse_v3_oneclick_project_id(project_id)
    if parsed:
        ch, _ep, _uid = parsed
        config["result_channel_dir"] = f"CH{ch}"
        config["result_episode_dir"] = result_dir.name

    _persist_project_config_if_changed(project_id, config)
    task["source_project_id"] = source_project_id
    task["template_project_id"] = source_project_id
    task["result_dir"] = str(result_dir)
    _sync_task_models_from_config(task, config)
    try:
        task["estimate"] = estimate_project(config)
    except Exception:
        pass

    try:
        _copy_template_assets(resolve_project_dir(source_project_id, source.config or {}), result_dir, config)
    except Exception as e:
        _add_log(task, f"⚠ Studio 에셋 동기화 실패: {type(e).__name__}: {e}", "warn")

    if step_label:
        _add_log(task, f"↻ Studio 현재 설정 반영 후 {step_label} 실행: {source_project_id}", "info")
    return config


async def _start_studio_router_step(project_id: str, step_num: int) -> None:
    db = SessionLocal()
    try:
        if step_num == 2:
            from app.routers.script import generate_script_async

            await generate_script_async(project_id, db=db)
            return
        if step_num == 3:
            from app.routers.voice import generate_all_voices_async

            await generate_all_voices_async(project_id, db=db)
            return
        if step_num == 4:
            from app.routers.image import resume_images_async

            result = await resume_images_async(project_id, db=db)
            if isinstance(result, dict) and result.get("status") == "nothing_to_resume":
                project = db.query(Project).filter(Project.id == project_id).first()
                if project:
                    step_states = dict(project.step_states or {})
                    step_states["4"] = "completed"
                    project.step_states = step_states
                    db.commit()
            return
        if step_num == 5:
            from app.routers.video import generate_all_videos_async

            await generate_all_videos_async(project_id, db=db)
            return
        if step_num == 6:
            from app.routers.subtitle import render_video_async

            await render_video_async(project_id, db=db)
            return
        raise RuntimeError(f"지원하지 않는 Studio 단계: {step_num}")
    except Exception as e:
        detail = getattr(e, "detail", None)
        if detail:
            raise RuntimeError(str(detail)) from e
        raise
    finally:
        db.close()


def _project_step_state(project_id: str, step_num: int) -> Optional[str]:
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return None
        return str((project.step_states or {}).get(str(step_num)) or "")
    finally:
        db.close()


async def _wait_studio_router_step(task: dict, step_num: int, label: str) -> None:
    project_id = str(task.get("project_id") or "")
    step_key = _STUDIO_STEP_KEYS.get(step_num)
    if not project_id or not step_key:
        raise RuntimeError(f"Studio 단계 키를 찾을 수 없습니다: {step_num}")

    missing_state_ticks = 0
    while True:
        if task.get("status") == "cancelled":
            _cancel_studio_task_manager_steps(project_id)
            raise PipelineCancelled("사용자 취소")

        state = _task_manager_state(project_id, step_num)
        if state is None:
            missing_state_ticks += 1
            db_state = _project_step_state(project_id, step_num)
            if db_state == "completed":
                return
            if db_state == "failed":
                raise RuntimeError(f"{label} 실패")
            if missing_state_ticks > 10:
                raise RuntimeError(f"{label} Studio task 상태를 찾을 수 없습니다")
            await asyncio.sleep(1)
            continue

        if step_num == 4:
            try:
                scan_config = task.get("config") if isinstance(task.get("config"), dict) else _effective_project_config(project_id)
                image_dir = resolve_project_dir(project_id, scan_config, create=False) / "images"
                actual_completed = sum(
                    1
                    for f in image_dir.glob("cut_*.png")
                    if f.is_file() and f.stat().st_size > 50
                ) if image_dir.exists() else int(state.completed or 0)
            except Exception:
                actual_completed = int(state.completed or 0)
            task["current_step_completed"] = actual_completed
            task["current_step_total"] = int(task.get("total_cuts") or state.total or 0)
            task["sub_status"] = (
                f"{task['current_step_completed']}/{task['current_step_total']}"
                if task["current_step_total"]
                else state.status
            )
        else:
            task["current_step_completed"] = int(state.completed or 0)
            task["current_step_total"] = int(state.total or 0)
            task["sub_status"] = f"{state.completed}/{state.total}" if state.total else state.status
        task["current_step_label"] = label
        task["progress_pct"] = _compute_progress_pct(task)
        _save_tasks_to_disk()

        if state.status == "completed":
            return
        if state.status == "failed":
            raise RuntimeError(state.error or f"{label} 실패")
        if state.status == "cancelled":
            raise PipelineCancelled("사용자 취소")
        await asyncio.sleep(1)


async def _run_studio_router_step(task: dict, step_num: int, label: str) -> None:
    project_id = task["project_id"]
    config = _sync_v3_run_project_from_source(task, step_label=label)
    task["config"] = config
    task["current_step"] = step_num
    task["current_step_name"] = label
    task["step_states"][str(step_num)] = "running"
    task["sub_status"] = None
    _sync_task_models_from_config(task, config)
    _add_log(task, f"▶ Studio {label} 시작")
    _save_tasks_to_disk()
    import time as _time

    t0 = _time.monotonic()
    await _start_studio_router_step(project_id, step_num)
    await _wait_studio_router_step(task, step_num, label)
    elapsed = _time.monotonic() - t0
    task["step_states"][str(step_num)] = "completed"
    task["sub_status"] = None
    if step_num == 2:
        fresh = _load_project(project_id)
        if fresh and fresh.total_cuts:
            task["total_cuts"] = int(fresh.total_cuts)
    _add_log(task, f"✓ Studio {label} 완료 ({elapsed:.1f}초)")
    _save_tasks_to_disk()


def _truthy_task_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _task_requires_image_qa_hold(task: dict, config: Optional[dict] = None) -> bool:
    cfg = config if isinstance(config, dict) else {}
    task_cfg = task.get("config") if isinstance(task.get("config"), dict) else {}
    required = (
        _truthy_task_flag(task.get("image_qa_required_before_video"))
        or _truthy_task_flag(task_cfg.get("image_qa_required_before_video"))
        or _truthy_task_flag(cfg.get("image_qa_required_before_video"))
    )
    approved = (
        _truthy_task_flag(task.get("image_qa_approved_before_video"))
        or _truthy_task_flag(task_cfg.get("image_qa_approved_before_video"))
        or _truthy_task_flag(cfg.get("image_qa_approved_before_video"))
    )
    states = dict(task.get("step_states") or {})
    return required and not approved and states.get("4") == "completed" and states.get("5") != "completed"


def _update_project_image_qa_hold_state(project_id: str) -> None:
    db = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == project_id).first()
        if not p:
            return
        states = dict(p.step_states or {})
        states["4"] = "completed"
        for step_num in range(5, 8):
            states[str(step_num)] = "pending"
        p.status = "paused"
        p.current_step = 4
        p.step_states = states
        try:
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(p, "step_states")
        except Exception:
            pass
        db.commit()
    finally:
        db.close()


def _mark_task_image_qa_hold(task: dict, project_id: str) -> None:
    states = dict(task.get("step_states") or {})
    states["4"] = "completed"
    for step_num in range(5, 8):
        states[str(step_num)] = "pending"
    task["step_states"] = states
    task["status"] = "paused"
    task["error"] = None
    task["finished_at"] = None
    task["resume_from_step"] = 5
    task["current_step"] = None
    task["current_step_name"] = "이미지 QA 대기"
    task["current_step_label"] = "이미지 QA 대기"
    task["current_step_progress_text"] = None
    task["current_step_cut_progress_pct"] = None
    task["current_step_active_cut"] = None
    total = int(task.get("total_cuts") or 0)
    task["current_step_completed"] = total
    task["current_step_total"] = total
    task["sub_status"] = "image_qa_pending"
    task["progress_pct"] = _compute_progress_pct(task)
    _update_project_image_qa_hold_state(project_id)
    _add_log(task, "이미지 150장 생성 완료 — QA 검수 전 영상/업로드 대기", "warn")
    _save_tasks_to_disk()


async def _run_studio_router_pipeline(task: dict, project_id: str, resume_from) -> str:
    """Run Workbench by pressing the linked Studio project's actual step routes."""
    steps = [
        (2, "대본 생성"),
        (3, "음성 생성"),
        (4, "이미지 생성"),
        (5, "영상 생성"),
    ]
    thumbnail_checked_after_voice = False

    def _should_skip(step_num: int) -> bool:
        if resume_from is not None and step_num < int(resume_from):
            return task["step_states"].get(str(step_num)) == "completed"
        return task["step_states"].get(str(step_num)) == "completed"

    async def _ensure_thumbnail_after_voice_once() -> None:
        nonlocal thumbnail_checked_after_voice
        if thumbnail_checked_after_voice:
            return
        thumbnail_checked_after_voice = True
        thumb_config = _sync_v3_run_project_from_source(task, step_label="썸네일 생성")
        _add_log(task, "▶ 음성 생성 완료 후 썸네일 생성 확인", "info")
        ok = await asyncio.to_thread(_ensure_thumbnail_generated, project_id, thumb_config)
        if ok:
            _add_log(task, "✓ 음성 생성 완료 후 썸네일 생성 확인 완료", "info")
        else:
            _add_log(task, "⚠ 음성 생성 완료 후 썸네일 생성 실패 — 파이프라인 계속", "warn")
        _save_tasks_to_disk()

    try:
        for step_num, label in steps:
            if step_num == 4 and task["step_states"].get("3") == "completed":
                await _ensure_thumbnail_after_voice_once()
            if _should_skip(step_num):
                continue
            if task.get("status") == "cancelled":
                raise PipelineCancelled("사용자 취소")
            await _run_studio_router_step(task, step_num, label)
            if step_num == 3:
                await _ensure_thumbnail_after_voice_once()
            if step_num == 4 and _task_requires_image_qa_hold(task, task.get("config")):
                _mark_task_image_qa_hold(task, project_id)
                return "paused"
        return "ok"
    except PipelineCancelled as e:
        current_step = int(task.get("current_step") or 0)
        current_label = str(task.get("current_step_name") or "작업")
        if current_step:
            task["step_states"][str(current_step)] = "cancelled"
        task["status"] = "cancelled"
        task["error"] = task.get("error") or str(e) or "사용자 취소"
        task["finished_at"] = task.get("finished_at") or _utcnow_iso()
        _update_project_status(project_id, "cancelled")
        _add_log(task, f"⏹ {current_label} 취소: {e}", "warn")
        _save_tasks_to_disk()
        return "cancelled"
    except Exception as e:
        current_step = int(task.get("current_step") or 0)
        current_label = str(task.get("current_step_name") or "작업")
        if current_step:
            task["step_states"][str(current_step)] = "failed"
        task["status"] = "failed"
        task["error"] = f"{current_label} 실패: {type(e).__name__}: {e}"
        task["finished_at"] = _utcnow_iso()
        _update_project_status(project_id, "failed")
        _add_log(task, f"✗ {current_label} 실패: {_human_readable_failure_reason(current_label, e)}", "error")
        _save_tasks_to_disk()
        return f"failed:{task['error']}"


def _apply_live_config_to_task(task: dict, config: dict, *, update_channel: bool) -> list[str]:
    old_models = dict(task.get("models") or {})
    old_channel = task.get("channel")
    old_estimate_models = dict((task.get("estimate") or {}).get("models_used") or {})
    _sync_task_models_from_config(task, config)
    new_models = task.get("models") or {}

    changes = [
        f"{key}: {old_models.get(key, '') or '(없음)'} -> {new_models.get(key, '') or '(없음)'}"
        for key in _LIVE_MODEL_KEYS
        if old_models.get(key, "") != new_models.get(key, "")
    ]

    if update_channel:
        new_channel = _valid_channel(config.get("youtube_channel") or config.get("channel"))
        if new_channel is not None and old_channel != new_channel:
            task["channel"] = new_channel
            changes.append(f"channel: CH{old_channel or '?'} -> CH{new_channel}")

    try:
        task["estimate"] = estimate_project(config)
        new_estimate_models = dict((task.get("estimate") or {}).get("models_used") or {})
        for key in ("script", "tts", "image", "video"):
            if old_estimate_models.get(key, "") != new_estimate_models.get(key, ""):
                label = f"estimate.{key}"
                change = (
                    f"{label}: {old_estimate_models.get(key, '') or '(없음)'}"
                    f" -> {new_estimate_models.get(key, '') or '(없음)'}"
                )
                if change not in changes:
                    changes.append(change)
    except Exception:
        pass

    return changes


def _restore_executed_models_from_logs(task: dict) -> bool:
    """Keep terminal task model labels tied to what actually ran."""
    if task.get("status") not in ("failed", "cancelled", "completed"):
        return False
    logs = task.get("logs") or []
    if not isinstance(logs, list):
        return False

    patterns = (
        ("script", re.compile(r"▶ 대본 생성 시작 \[(.+?)\]")),
        ("tts", re.compile(r"▶ 음성 생성 시작 \[(.+?)\]")),
        ("image", re.compile(r"▶ 이미지 생성 시작 \[(.+?)\]")),
        ("video", re.compile(r"▶ 영상 생성 시작 \[(.+?)\]")),
    )
    models = task.setdefault("models", {})
    changed = False

    for model_key, pattern in patterns:
        found = None
        for row in reversed(logs):
            if not isinstance(row, dict):
                continue
            msg = str(row.get("msg") or "")
            match = pattern.search(msg)
            if match:
                found = match.group(1).strip()
                break
        if not found:
            continue

        if model_key == "tts":
            parts = [p.strip() for p in found.split("/", 1)]
            if parts and models.get("tts") != parts[0]:
                models["tts"] = parts[0]
                changed = True
            if len(parts) > 1 and models.get("tts_voice") != parts[1]:
                models["tts_voice"] = parts[1]
                changed = True
            continue

        if models.get(model_key) != found:
            models[model_key] = found
            changed = True

    return changed


def _restore_terminal_step_from_logs(task: dict) -> bool:
    """Keep failed/cancelled terminal tasks tied to the step that actually stopped."""
    status = task.get("status")
    if status not in ("failed", "cancelled", "paused"):
        return False
    logs = task.get("logs") or []
    if not isinstance(logs, list):
        logs = []

    step_by_label = {
        "대본 생성": (2, "대본 생성"),
        "음성 생성": (3, "음성 생성"),
        "이미지 생성": (4, "이미지 생성"),
        "영상 생성": (5, "영상 생성"),
        "최종 렌더링": (6, "최종 렌더링"),
        "유튜브 업로드": (7, "유튜브 업로드"),
    }
    found: Optional[tuple[int, str, str]] = None

    for row in reversed(logs):
        if not isinstance(row, dict):
            continue
        msg = str(row.get("msg") or "")
        for label, (step_num, step_name) in step_by_label.items():
            if f"{label} 실패" in msg:
                found = (step_num, step_name, "failed")
                break
            if f"{label} 취소" in msg:
                found = (step_num, step_name, "cancelled")
                break
        if found:
            break

    if not found:
        error = str(task.get("error") or "")
        for label, (step_num, step_name) in step_by_label.items():
            if error.startswith(f"{label} 실패"):
                found = (step_num, step_name, "failed")
                break
            if error.startswith(f"{label} 취소"):
                found = (step_num, step_name, "cancelled")
                break

    if not found:
        return False

    step_num, step_name, step_state = found
    if status == "cancelled":
        step_state = "cancelled"

    changed = False
    step_states = task.setdefault("step_states", {})
    if not isinstance(step_states, dict):
        step_states = {}
        task["step_states"] = step_states
        changed = True

    step_key = str(step_num)
    if step_states.get(step_key) != step_state:
        step_states[step_key] = step_state
        changed = True
    if task.get("current_step") != step_num:
        task["current_step"] = step_num
        changed = True
    if task.get("current_step_name") != step_name:
        task["current_step_name"] = step_name
        changed = True
    if task.get("current_step_label") is not None:
        task["current_step_label"] = None
        changed = True

    return changed


def refresh_tasks_for_project_update(project_id: str, config: dict) -> int:
    """Propagate Studio config changes to active oneclick tasks linked to that preset."""
    _ensure_state_loaded()
    target_id = str(project_id or "").strip()
    if not target_id:
        return 0

    updated_config = dict(config or {})
    refreshed = 0
    changed = False

    db = SessionLocal()
    try:
        from sqlalchemy.orm.attributes import flag_modified

        for task in list(_TASKS.values()):
            if task.get("status") not in _LIVE_REFRESH_STATUSES:
                continue

            task_project_id = str(task.get("project_id") or "").strip()
            task_project = (
                db.query(Project).filter(Project.id == task_project_id).first()
                if task_project_id
                else None
            )
            task_config = (
                dict(task_project.config or {})
                if task_project and isinstance(task_project.config, dict)
                else {}
            )
            task_template_id = str(
                task.get("template_project_id")
                or task_config.get("template_project_id")
                or ""
            ).strip()

            direct_match = task_project_id == target_id
            template_match = task_template_id == target_id
            if not direct_match and not template_match:
                continue

            if direct_match:
                effective_config = updated_config
            else:
                effective_config = _merge_template_config(task_config, updated_config, target_id)
                task["template_project_id"] = target_id
                if task_project is not None:
                    task_project.config = effective_config
                    flag_modified(task_project, "config")

            changes = _apply_live_config_to_task(
                task,
                effective_config,
                update_channel=task.get("status") in ("prepared", "queued"),
            )
            if changes:
                _add_log(task, "ℹ Studio 설정 반영: " + "; ".join(changes))
                changed = True
            refreshed += 1

        db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        print(f"[oneclick] refresh tasks for project update failed: {e}")
    finally:
        db.close()

    if changed:
        _save_tasks_to_disk()
    return refreshed


def update_task_image_model(project_id: str, image_model_id: str) -> None:
    """v1.2.16: 이미지 스텝 실행 중 폴백(nano-banana-3 등)이 일어났을 때
    pipeline_tasks._step_image 에서 호출해 해당 project 의 실행 중 task
    의 models["image"] 를 갱신한다. project_id 로 task 를 역조회한다.

    pipeline_tasks 는 여러 실행 경로(스튜디오/oneclick) 에서 공유되므로
    일치하는 task 가 없으면 조용히 무시한다.
    """
    try:
        for t in _TASKS.values():
            if t.get("project_id") == project_id and t.get("status") in ("running", "prepared"):
                models = t.setdefault("models", {})
                if models.get("image") != image_model_id:
                    models["image"] = image_model_id
                    _add_log(t, f"ℹ 이미지 모델 → {image_model_id}")
                break
    except Exception:
        pass


def update_task_sub_status(project_id: str, text: Optional[str]) -> None:
    """v1.2.26: pipeline_tasks 의 서브단계에서 호출해 현재 "무슨 일을 하고
    있는지" 를 실시간 노출.

    text=None 이면 서브상태를 비운다. project_id 로 실행 중 task 를 역조회하며,
    일치하는 게 없으면 (Studio 경로 등) 조용히 무시한다. redis 가 아니라 in-memory
    dict 를 직접 쓰므로 같은 프로세스 안에서만 작동 — OneClick 워커는 모두 같은
    FastAPI 프로세스 안에 있어서 충분하다.
    """
    try:
        import re

        for t in _TASKS.values():
            if t.get("project_id") == project_id and t.get("status") in ("running", "prepared"):
                changed = False
                if t.get("sub_status") != text:
                    t["sub_status"] = text
                    changed = True
                if text:
                    cut_match = re.search(r"컷\s+(\d+)\s*/\s*(\d+)", str(text))
                    pct_match = re.search(r"\((\d+(?:\.\d+)?)%\)", str(text))
                    if cut_match:
                        active_cut = int(cut_match.group(1))
                        total_cuts = int(cut_match.group(2))
                        if t.get("current_step_active_cut") != active_cut:
                            t["current_step_active_cut"] = active_cut
                            changed = True
                        if t.get("current_step_total") != total_cuts:
                            t["current_step_total"] = total_cuts
                            changed = True
                        step = t.get("current_step")
                        if step in (3, 4, 5):
                            done_map = dict(t.get("completed_cuts_by_step") or {})
                            done = int(done_map.get(str(step)) or 0)
                            completed = max(0, min(total_cuts, max(done, active_cut - 1)))
                            if t.get("current_step_completed") != completed:
                                t["current_step_completed"] = completed
                                changed = True
                    if pct_match:
                        pct = float(pct_match.group(1))
                        if t.get("current_step_cut_progress_pct") != pct:
                            t["current_step_cut_progress_pct"] = pct
                            changed = True
                    if t.get("current_step_progress_text") != text:
                        t["current_step_progress_text"] = text
                        changed = True
                elif t.get("current_step_progress_text") is not None:
                    t["current_step_progress_text"] = None
                    t["current_step_active_cut"] = None
                    t["current_step_cut_progress_pct"] = None
                    changed = True
                if changed:
                    try:
                        _refresh_task_safety(t, force=False)
                    except Exception:
                        pass
                    _save_tasks_to_disk()
                break
    except Exception:
        pass


def append_task_log(project_id: str, msg: str, level: str = "info") -> None:
    """v1.2.26: pipeline_tasks 의 서브단계(특히 컷 시작 시점)에서 호출해
    task.logs 에 직접 한 줄 추가. project_id 역조회 방식은 sub_status 와 동일.

    stdout print 와 달리 이 함수로 쏜 로그는 프론트 Live 페이지의 "제작 로그"
    패널에 그대로 표시된다.
    """
    try:
        for t in _TASKS.values():
            if t.get("project_id") == project_id and t.get("status") in ("running", "prepared"):
                _add_log(t, msg, level)
                break
    except Exception:
        pass


def _run_sync_pipeline(task: dict, project_id: str, config: dict, resume_from) -> str:
    """Step 2~5 를 실행. v1.1.53: step 3(음성) + step 4(이미지)를 병렬 실행.

    대본(2) → 음성+이미지(3+4 병렬) → 영상(5)
    음성과 이미지는 서로 의존 관계가 없으므로 ThreadPoolExecutor 로 동시 실행한다.
    개별 step 내부는 여전히 단일 스레드 → 단일 이벤트 루프로 동작하여
    httpx transport, subprocess 핸들링 안정성은 유지된다.

    반환값: "ok" | "cancelled" | "failed:{에러메시지}"
    task dict 의 step_states/status 등은 이 함수 안에서 직접 갱신한다.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from app.tasks.pipeline_tasks import (
        _step_script,
        _step_voice,
        _step_image,
        _step_video,
        init_progress,
        run_async,
        PipelineCancelled,
    )
    # v1.2.26: 외부 API 서비스가 raise_if_cancelled() 로 올린 OperationCancelled
    # 도 PipelineCancelled 와 동일 취급. 한 클래스로 묶기 위해 튜플로 catch.
    try:
        from app.services.cancel_ctx import OperationCancelled
        _CancelTypes = (PipelineCancelled, OperationCancelled)
    except Exception:
        _CancelTypes = (PipelineCancelled,)

    # v1.2.16: 실행 시점의 fresh config 로 task["models"] 최신화.
    # prepare 시점 모델과 실행 시점 모델이 다를 수 있으므로 반드시 여기서
    # 한 번 덮어쓴다. (Live 페이지의 "실제 사용 모델" 표시 정확도 확보)
    _sync_task_models_from_config(task, config)

    def _is_recoverable_comfy_restart_error(exc: BaseException) -> bool:
        text = f"{type(exc).__name__}: {exc}".lower()
        if "comfyui" not in text and "comfy" not in text:
            return False
        recoverable_markers = (
            "connect",
            "connection",
            "refused",
            "reset",
            "timeout",
            "timed out",
            "temporarily",
            "unavailable",
            "server disconnected",
            "readerror",
            "remoteprotocolerror",
            "연결 실패",
        )
        return any(marker in text for marker in recoverable_markers)

    # 깨진 복구 프로젝트 보호:
    # step 3 이상부터 재개하려면 script.json 이 반드시 있어야 한다.
    # 없으면 폴더만 다시 만들고 외부 API 호출로 진입할 수 있으므로 즉시 중단한다.
    if resume_from is not None and int(resume_from) > 2:
        script_path = resolve_project_dir(project_id, config, create=False) / "script.json"
        script_missing_or_partial = not script_path.exists()
        if not script_missing_or_partial:
            try:
                script_data = json.loads(script_path.read_text(encoding="utf-8"))
                script_missing_or_partial = bool(script_data.get("_partial"))
            except Exception:
                script_missing_or_partial = True
        if script_missing_or_partial:
            msg = (
                f"완성된 script.json 이 없어 Step {resume_from}부터 이어서 할 수 없습니다. "
                "자동 재생성을 막기 위해 중단했습니다."
            )
            task["status"] = "failed"
            task["error"] = msg
            task["finished_at"] = _utcnow_iso()
            task["resume_from_step"] = 2
            _save_tasks_to_disk()
            return "failed:script.json missing"

    all_steps = [
        (2, _step_script, "대본 생성"),
        (3, _step_voice,  "음성 생성"),
        (4, _step_image,  "이미지 생성"),
        (5, _step_video,  "영상 생성"),
    ]

    def _should_skip(step_num):
        """resume 모드에서 이미 완료된 단계 건너뛰기"""
        if resume_from is not None and step_num < resume_from:
            return task["step_states"].get(str(step_num)) == "completed"
        return False

    def _check_cancel():
        if task.get("status") == "cancelled":
            return True
        try:
            from app.services.cancel_ctx import is_halted
            if is_halted(project_id):
                return True
        except Exception:
            pass
        try:
            if _redis_get(f"pipeline:cancel:{project_id}"):
                return True
        except Exception:
            pass
        return False

    def _run_single_step(step_num, func, label):
        """단일 스텝 실행. 예외는 그대로 raise."""
        task["current_step"] = step_num
        task["current_step_name"] = label
        task["step_states"][str(step_num)] = "running"
        # v1.2.26: 새 스텝 진입 시 이전 서브상태 텍스트 제거 — 이전 스텝이
        # 남긴 "컷 10/10" 같은 텍스트가 다음 스텝에 잔존하지 않도록.
        task["sub_status"] = None
        # v1.2.28: 각 스텝 시작 직전에 DB 에서 프로젝트 config 를 다시 읽어
        # 스냅샷을 덮어쓴다. 사용자가 "프로젝트 설정"(UI) 에서 모델을 바꾸면
        # 다음 스텝부터 즉시 반영된다 (실행 중이 아닌 스텝 한정).
        # 기존 버전은 태스크 시작 시점의 config 를 끝까지 고수해서, 사용자가
        # 2K → 4K 로 바꿔도 여전히 2K 로 돌아가는 문제가 있었다.
        try:
            _fresh_cfg = _effective_project_config(project_id, config)
            if _fresh_cfg:
                _fresh_cfg["auto_pause_after_step"] = False
                _changed = []
                for _k in ("story_model", "script_model", "tts_model", "tts_voice_id",
                            "image_model", "thumbnail_model", "video_model"):
                    _old = config.get(_k, "")
                    _new = _fresh_cfg.get(_k, "")
                    if _old != _new:
                        _changed.append((_k, _old, _new))
                if _changed:
                    for _k, _o, _n in _changed:
                        _add_log(task, f"ℹ 프리셋 현재 설정 반영: {_k} = {_o or '(없음)'} → {_n or '(없음)'}")
                    _persist_project_config_if_changed(project_id, _fresh_cfg)
                config.clear()
                config.update(_fresh_cfg)
        except Exception as _e:
            # config 재로드 실패해도 기존 스냅샷으로 계속 진행.
            _add_log(task, f"⚠ 설정 재로드 실패 ({type(_e).__name__}): 기존 설정 유지", "warn")
        _sync_task_models_from_config(task, config)
        try:
            from app.services.video.factory import DEFAULT_VIDEO_MODEL, resolve_video_model
            _log_video_model = resolve_video_model(config.get("video_model", DEFAULT_VIDEO_MODEL))
        except Exception:
            _log_video_model = config.get("video_model", "")
        # v2.1.2: 제작 로그 — 스텝 시작 시 사용 모델 기록
        _model_for_step = {
            2: ("script", config.get("script_model", "")),
            3: ("tts", f"{config.get('tts_model', '')} / {config.get('tts_voice_id', '')}"),
            4: ("image", config.get("image_model", "")),
            5: ("video", _log_video_model),
        }
        model_label = ""
        if step_num in _model_for_step:
            kind, mid = _model_for_step[step_num]
            model_label = f" [{mid}]" if mid else ""
        _add_log(task, f"▶ {label} 시작{model_label}")
        try:
            init_progress(project_id, step_num)
        except Exception:
            pass
        import time as _time
        _t0 = _time.monotonic()
        attempt = 0
        while True:
            try:
                func(project_id, config)
                break
            except _CancelTypes:
                raise
            except Exception as e:
                attempt += 1
                if step_num not in (4, 5) or not _is_recoverable_comfy_restart_error(e):
                    raise
                wait_sec = min(120, 15 * attempt)
                task["resume_from_step"] = step_num
                task["sub_status"] = f"ComfyUI 재연결 대기: {wait_sec}초 후 재시도"
                _add_log(
                    task,
                    f"↻ {label} ComfyUI 연결 끊김 — {wait_sec}초 후 재시도 ({type(e).__name__}: {e})",
                    "warn",
                )
                _save_tasks_to_disk()
                for _ in range(wait_sec):
                    if _check_cancel():
                        raise PipelineCancelled(f"{label} cancelled during ComfyUI reconnect wait")
                    _time.sleep(1)
                _add_log(task, f"▶ {label} 재시도", "info")
                _save_tasks_to_disk()
        _elapsed = _time.monotonic() - _t0
        _add_log(task, f"✓ {label} 완료 ({_elapsed:.1f}초)")
        task["step_states"][str(step_num)] = "completed"
        # v1.2.26: 스텝 종료 시점에 서브상태 초기화 — 다음 스텝이 자기 서브상태를
        # 덮어쓰기 전까지 "완료" 대신 이전 서브텍스트가 잠깐 남는 걸 방지.
        task["sub_status"] = None
        _save_tasks_to_disk()

    def _cleanup_cancel_key():
        """v1.1.53: 파이프라인 종료 시 cancel 키 정리"""
        try:
            _redis_delete(f"pipeline:cancel:{project_id}")
        except Exception:
            pass

    def _handle_cancel(step_num, label, e=None):
        msg = e or "사용자 취소"
        print(f"[oneclick] step {step_num} cancelled: {type(msg).__name__}: {ascii(msg)}")
        _add_log(task, f"⏹ {label} 취소: {msg}", "warn")
        task["step_states"][str(step_num)] = "cancelled"
        task["status"] = "cancelled"
        task["error"] = task.get("error") or "사용자 취소"
        task["finished_at"] = _utcnow_iso()
        _update_project_status(project_id, "cancelled")
        # v1.1.55: cancel 키를 여기서 삭제하지 않는다.
        # 병렬 실행 시 다른 스레드가 아직 돌고 있을 수 있으므로
        # cancel 키는 _run_sync_pipeline 의 최종 반환 직전에만 정리한다.
        return "cancelled"

    def _handle_fail(step_num, label, e):
        tb = traceback.format_exc()
        safe_tb = tb.encode("ascii", "backslashreplace").decode("ascii")
        print(f"[oneclick] step {step_num} failed: {type(e).__name__}: {ascii(e)}\n{safe_tb}")
        _add_log(task, f"✗ {label} 실패: {_human_readable_failure_reason(label, e)}", "error")
        task["step_states"][str(step_num)] = "failed"
        task["status"] = "failed"
        task["error"] = f"{label} 실패: {type(e).__name__}: {e}"
        task["finished_at"] = _utcnow_iso()
        _update_project_status(project_id, "failed")
        _save_tasks_to_disk()
        return f"failed:{task['error']}"

    # ── Step 2: 대본 (순차) ──
    step2 = all_steps[0]  # (2, _step_script, "대본 생성")
    if not _should_skip(2):
        if _check_cancel():
            _cleanup_cancel_key()
            return _handle_cancel(2, "대본 생성")
        try:
            _run_single_step(*step2)
        except _CancelTypes as e:
            _cleanup_cancel_key()
            return _handle_cancel(2, "대본 생성", e)
        except Exception as e:
            return _handle_fail(2, "대본 생성", e)

    # step 2 끝나면 total_cuts 결정 — task 에 반영
    fresh = _load_project(project_id)
    if fresh and fresh.total_cuts:
        task["total_cuts"] = int(fresh.total_cuts)

    # ── Step 3+4: 음성 + 이미지 (병렬) ──
    skip_3 = _should_skip(3)
    skip_4 = _should_skip(4)
    parallel_targets = []
    thumbnail_checked_after_voice = False

    def _ensure_thumbnail_after_voice_once() -> None:
        nonlocal thumbnail_checked_after_voice
        if thumbnail_checked_after_voice:
            return
        if task["step_states"].get("3") != "completed":
            return
        thumbnail_checked_after_voice = True
        _add_log(task, "▶ 음성 생성 완료 후 썸네일 생성 확인", "info")
        ok = _ensure_thumbnail_generated(project_id, config)
        if ok:
            _add_log(task, "✓ 음성 생성 완료 후 썸네일 생성 확인 완료", "info")
        else:
            _add_log(task, "⚠ 음성 생성 완료 후 썸네일 생성 실패 — 파이프라인 계속", "warn")
        _save_tasks_to_disk()

    if skip_3 and task["step_states"].get("3") == "completed":
        _ensure_thumbnail_after_voice_once()
    if not skip_3:
        parallel_targets.append(all_steps[1])  # (3, _step_voice, "음성 생성")
    if not skip_4:
        parallel_targets.append(all_steps[2])  # (4, _step_image, "이미지 생성")

    if parallel_targets:
        if _check_cancel():
            return _handle_cancel(3, "음성+이미지")

        if len(parallel_targets) == 2:
            # ★ 병렬 실행
            print(f"[oneclick] ★ 음성(3) + 이미지(4) 병렬 실행 시작")
            # v1.1.58: parallel 진입 시 current_step / current_step_name 을 갱신.
            # 이전에는 step 2 의 마지막 값("대본 생성")이 그대로 박혀 있어 UI 가
            # "현재 단계: 대본 생성 100%" 로만 보이고 음성/이미지 진행이 시각적으로
            # 묻혔다. (사용자 신고: "초기화 후 이어서 하기 반응 없다")
            task["current_step"] = 3
            task["current_step_name"] = "음성+이미지 생성 (병렬)"
            errors = {}

            def _thread_run(step_num, func, label):
                try:
                    task["step_states"][str(step_num)] = "running"
                    # v1.2.16: 병렬 스텝 시작 시에도 모델명 최신화
                    _sync_task_models_from_config(task, config)
                    try:
                        init_progress(project_id, step_num)
                    except Exception:
                        pass
                    func(project_id, config)
                    task["step_states"][str(step_num)] = "completed"
                    _save_tasks_to_disk()
                    print(f"[oneclick] ★ {label} 완료")
                except _CancelTypes:
                    raise
                except Exception:
                    raise

            # v1.1.55: cancel 키를 삭제하지 않고 유지하므로, 병렬 스레드들이
            # 각자 check_pause_or_cancel 에서 cancel 을 감지하고 종료한다.
            # wait=True 로 모든 스레드가 실제 종료될 때까지 대기한 후 반환.
            pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="step")
            cancel_result = None
            try:
                futures = {
                    pool.submit(_thread_run, sn, fn, lb): (sn, lb)
                    for sn, fn, lb in parallel_targets
                }
                for fut in as_completed(futures):
                    sn, lb = futures[fut]
                    try:
                        fut.result()
                    except _CancelTypes as e:
                        if not cancel_result:
                            cancel_result = _handle_cancel(sn, lb, e)
                        # break 하지 않고 나머지 future 도 수거한다.
                        # cancel 키가 살아있으므로 다른 스레드도 곧 종료된다.
                    except Exception as e:
                        if cancel_result:
                            pass  # cancel 중 발생한 부수 에러는 무시
                        else:
                            errors[sn] = (lb, e)
            finally:
                pool.shutdown(wait=True, cancel_futures=True)

            if cancel_result:
                _cleanup_cancel_key()
                return cancel_result

            if errors:
                first_sn = min(errors.keys())
                lb, e = errors[first_sn]
                return _handle_fail(first_sn, lb, e)
            _ensure_thumbnail_after_voice_once()
        else:
            # 하나만 실행 (resume 시 한쪽만 남은 경우)
            sn, fn, lb = parallel_targets[0]
            try:
                _run_single_step(sn, fn, lb)
            except _CancelTypes as e:
                _cleanup_cancel_key()
                return _handle_cancel(sn, lb, e)
            except Exception as e:
                return _handle_fail(sn, lb, e)
            _ensure_thumbnail_after_voice_once()

    if _task_requires_image_qa_hold(task, config):
        _cleanup_cancel_key()
        _mark_task_image_qa_hold(task, project_id)
        return "paused"

    # ── Step 5: 영상 (순차) ──
    if not _should_skip(5):
        if _check_cancel():
            _cleanup_cancel_key()
            return _handle_cancel(5, "영상 생성")
        try:
            _run_single_step(*all_steps[3])  # (5, _step_video, "영상 생성")
        except _CancelTypes as e:
            _cleanup_cancel_key()
            return _handle_cancel(5, "영상 생성", e)
        except Exception as e:
            return _handle_fail(5, "영상 생성", e)

    _cleanup_cancel_key()
    return "ok"


def _ensure_thumbnail_generated(project_id: str, config: dict) -> bool:
    """썸네일이 없으면 자동 생성한다.

    실패해도 렌더링은 계속 진행한다 (썸네일은 필수가 아님).
    """
    from app.tasks.pipeline_tasks import load_script, _generate_thumbnail_sync, _redis_set

    thumb_path = resolve_project_dir(project_id, config, create=True) / "output" / "thumbnail.png"
    if thumb_path.exists() and thumb_path.stat().st_size > 100:
        print(f"[oneclick] 썸네일 이미 존재 — 건너뜀: {thumb_path}")
        # v1.1.60: Redis 상태도 done 으로 동기화 — 안 그러면 UI 가 'waiting'
        # 으로 남아서 렌더 단계에서 미리보기가 안 뜬다 (resume 케이스).
        _redis_set(f"thumbnail:status:{project_id}", "done")
        return True

    print(f"[oneclick] 썸네일 없음 — 자동 생성 시작: {project_id}")
    try:
        script = load_script(project_id, config)
        if script:
            _generate_thumbnail_sync(project_id, config, script)
            ok = thumb_path.exists() and thumb_path.stat().st_size > 100
            print(f"[oneclick] 썸네일 자동 생성 완료: {project_id}" if ok else f"[oneclick] 썸네일 자동 생성 결과 파일 없음: {project_id}")
            return ok
        else:
            print(f"[oneclick] script.json 없음 — 썸네일 생성 불가")
            _redis_set(f"thumbnail:status:{project_id}", "failed:script.json 없음")
            return False
    except Exception as e:
        err_msg = f"{type(e).__name__}: {e}"
        print(f"[oneclick] 썸네일 자동 생성 실패 (파이프라인은 계속): {err_msg}")
        _redis_set(f"thumbnail:status:{project_id}", f"failed:{err_msg[:300]}")
        return False


def _schedule_oneclick_run(task_id: str) -> None:
    """v1.1.58: _run_oneclick_task 를 안전하게 스케줄한다.

    같은 task_id 의 이전 인스턴스가 아직 살아있으면 새 인스턴스를 띄우지 않는다.
    LLM 호출은 취소 신호와 실제 provider 연결 종료 사이에 시차가 있을 수 있으므로,
    여기서 재스케줄하면 같은 대본 호출이 중복 발생할 수 있다.
    """
    prev = _ACTIVE_RUNS.get(task_id)
    if prev is not None and not prev.done():
        task = _TASKS.get(task_id)
        if task is not None:
            _add_log(task, "ℹ 이미 실행 중인 작업 유지 — 중복 호출 차단", "muted")
            _save_tasks_to_disk()
        print(f"[oneclick] duplicate _run_oneclick_task({task_id}) blocked")
        return
    task = _TASKS.get(task_id)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        if task is not None:
            _add_log(task, "실행 루프가 없어 자동 시작을 보류했습니다", "warn")
            _save_tasks_to_disk()
        print(f"[oneclick] running event loop not found; cannot schedule task {task_id}")
        return

    async def _delayed_start():
        await _run_oneclick_task(task_id)

    new_task = loop.create_task(_delayed_start())
    _ACTIVE_RUNS[task_id] = new_task

    def _schedule_next_after_delay(finished_task_id: str) -> None:
        global _AUTO_NEXT_DISPATCH_NOT_BEFORE, _AUTO_NEXT_DISPATCH_TASK

        finished = _TASKS.get(finished_task_id) or {}
        if finished.get("status") not in ("completed", "failed", "uploading", "upload_pending", "upload_failed"):
            return
        if _emergency_stop_active():
            return
        if not _should_auto_dispatch_after_task(finished):
            _add_log(
                finished,
                "ℹ 스케줄 작업 완료: 다음 자동 생성은 설정된 실행 시간에만 시작합니다",
                "muted",
            )
            _save_tasks_to_disk()
            return

        if _AUTO_NEXT_DISPATCH_TASK is not None and not _AUTO_NEXT_DISPATCH_TASK.done():
            _AUTO_NEXT_DISPATCH_TASK.cancel()

        _AUTO_NEXT_DISPATCH_NOT_BEFORE = time.monotonic() + _AUTO_NEXT_DELAY_SECONDS

        async def _wait_and_dispatch() -> None:
            global _AUTO_NEXT_DISPATCH_NOT_BEFORE, _AUTO_NEXT_DISPATCH_TASK
            countdown_marks = [10, 5, 4, 3, 2, 1]
            last_logged: Optional[int] = _AUTO_NEXT_DELAY_SECONDS
            try:
                while True:
                    remaining = _auto_next_delay_remaining()
                    if remaining <= 0:
                        break
                    if remaining in countdown_marks and remaining != last_logged:
                        _add_log(finished, f"⏳ 다음 작업 {remaining}초 후 시작", "info")
                        _save_tasks_to_disk()
                        last_logged = remaining
                    await asyncio.sleep(1)

                _AUTO_NEXT_DISPATCH_NOT_BEFORE = 0.0
                if _emergency_stop_active():
                    return
                if _has_running_task(exclude_task_id=finished_task_id):
                    _add_log(finished, "ℹ 다음 작업 대기 종료: 이미 실행 중인 작업이 있어 자동 시작 생략", "muted")
                    _save_tasks_to_disk()
                    return

                next_task_id = _dispatch_next_queued_task(exclude_task_id=finished_task_id)
                if next_task_id:
                    _add_log(finished, "▶ 다음 대기 작업 시작", "info")
                    _save_tasks_to_disk()
                    return

                fired_ch = _dispatch_next_persisted_queue_item()
                if fired_ch:
                    _add_log(finished, f"▶ 다음 큐 작업 시작: CH{fired_ch}", "info")
                    _save_tasks_to_disk()
                else:
                    _add_log(finished, "ℹ 다음 작업 없음", "muted")
                    _save_tasks_to_disk()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"[oneclick] 다음 작업 지연 디스패치 실패: {e}")
            finally:
                if _AUTO_NEXT_DISPATCH_TASK is asyncio.current_task():
                    _AUTO_NEXT_DISPATCH_TASK = None

        _add_log(finished, f"⏳ 다음 작업 {_AUTO_NEXT_DELAY_SECONDS}초 후 시작", "info")
        _save_tasks_to_disk()
        _AUTO_NEXT_DISPATCH_TASK = loop.create_task(_wait_and_dispatch())

    def _cleanup(t):
        if _ACTIVE_RUNS.get(task_id) is t:
            _ACTIVE_RUNS.pop(task_id, None)
        try:
            if t.cancelled():
                return
            exc = t.exception()
            if exc is not None:
                finished = _TASKS.get(task_id) or {}
                if finished:
                    finished["status"] = "failed"
                    finished["error"] = f"실행 프로세스 오류: {type(exc).__name__}: {exc}"
                    finished["finished_at"] = _utcnow_iso()
                    _add_log(finished, finished["error"], "error")
                    _save_tasks_to_disk()
                print(f"[oneclick] _run_oneclick_task({task_id}) failed: {exc}")
                return
            finished = _TASKS.get(task_id) or {}
            if finished.get("status") == "cancelled" or _emergency_stop_active():
                return
            _schedule_next_after_delay(task_id)
        except Exception as e:
            print(f"[oneclick] 다음 queued 태스크 디스패치 실패: {e}")

    new_task.add_done_callback(_cleanup)


async def _run_oneclick_task(task_id: str) -> None:
    """단일 oneclick task 를 끝까지 실행. 실패/성공 모두 task 상태를 갱신.

    v1.1.51: Step 2~5 를 _run_sync_pipeline() 에서 **단일 스레드** 순차 직접
    호출로 변경. 스튜디오의 run_pipeline(Celery) 과 완전히 동일한 실행 환경을
    보장한다. 이전 버전의 개별 asyncio.to_thread 래핑이 TTS, FFmpeg 등 모든
    에러의 근본 원인이었다.
    """
    task = _TASKS.get(task_id)
    if not task:
        return

    project_id = task["project_id"]
    project = _load_project(project_id)
    if not project:
        task["status"] = "failed"
        task["error"] = "project not found (삭제되었거나 생성 실패)"
        task["finished_at"] = _utcnow_iso()
        return

    config = _effective_project_config(project_id, dict(project.config or {}))
    config["auto_pause_after_step"] = False
    if not config.get("template_project_id") and task.get("template_project_id"):
        config["template_project_id"] = task.get("template_project_id")

    async with _RUN_LOCK:
        if task.get("status") == "cancelled":
            return

        # v1.2.29: 이전 run 에서 남은 halt 플래그 해제. emergency_stop_all 또는
        # cancel_task 가 세워둔 전역 halt 집합에 이 project_id 가 남아 있으면,
        # 재실행해도 첫 컷이 바로 취소로 빠져버린다. 반드시 실행 시작 시점에 해제.
        try:
            from app.services.cancel_ctx import unmark_halted
            unmark_halted(project_id)
        except Exception:
            pass

        task["status"] = "running"
        if not task.get("started_at"):
            task["started_at"] = _utcnow_iso()
        _refresh_task_safety(task, force=True)

        if _reconcile_task_outputs(task, clear_terminal_cursor=True):
            _save_tasks_to_disk()
        resume_from = task.pop("resume_from_step", None)

        if resume_from is not None and resume_from > 2:
            fresh = _load_project(project_id)
            if fresh and fresh.total_cuts:
                task["total_cuts"] = int(fresh.total_cuts)

        # --- Step 2~5: V3 Studio-linked tasks call the actual Studio tab routes. ---
        # Step 6 is handled once by the shared final-render block below. Running it
        # here as well races on tmp_render/output files and corrupts shorts output.
        if _is_v3_studio_linked_project(project_id, config):
            result = await _run_studio_router_pipeline(task, project_id, resume_from)
            config = _sync_v3_run_project_from_source(task)
        else:
            result = await asyncio.to_thread(
                _run_sync_pipeline, task, project_id, config, resume_from
            )
        if result != "ok":
            return  # cancelled 또는 failed — _run_sync_pipeline 이 상태 갱신 완료

        # v1.1.48: 영상 단계 끝난 직후에도 cancel 확인 — 렌더링은 오래 걸리니
        # 중간 인터럽트는 불가능해도 진입 자체를 막을 수는 있다.
        if task.get("status") == "cancelled":
            task["step_states"]["6"] = "cancelled"
            task["error"] = task.get("error") or "사용자 취소"
            task["finished_at"] = task.get("finished_at") or _utcnow_iso()
            _update_project_status(project_id, "cancelled")
            return

        # --- Step 6: 최종 렌더링 (router handler 직접 호출) ---
        # v1.1.49: resume 모드에서 이미 완료된 6단계는 건너뛴다.
        if task["step_states"].get("6") == "completed" and task["step_states"].get("7") != "completed":
            render_ready, render_reason = await asyncio.to_thread(
                _render_outputs_ready_for_upload,
                project_id,
                config,
            )
            if not render_ready:
                task["step_states"]["6"] = "pending"
                task["step_states"]["7"] = "pending"
                task["resume_from_step"] = 6
                _mark_project_steps_pending(project_id, 6)
                _add_log(
                    task,
                    f"↻ 렌더 산출물 업로드 검증 실패 — Step 6 재생성: {render_reason}",
                    "warn",
                )
                _save_tasks_to_disk()

        if task["step_states"].get("6") == "completed":
            if task["step_states"].get("7") == "completed":
                task["current_step"] = None
                task["current_step_name"] = None
                task["status"] = "completed"
                task["finished_at"] = _utcnow_iso()
                _update_project_status(project_id, "completed")
                return
            _add_log(task, "↪ 최종 렌더링 완료 상태 확인: 유튜브 업로드 단계로 이동", "info")
        else:
            # v1.1.57: 렌더링 전 썸네일 없으면 자동 생성
            # _generate_thumbnail_sync 내부에서 run_async() 를 쓰므로
            # 이벤트 루프 충돌을 피하기 위해 별도 스레드에서 실행한다.
            await asyncio.to_thread(_ensure_thumbnail_generated, project_id, config)

            task["current_step"] = 6
            task["current_step_name"] = "최종 렌더링"
            task["step_states"]["6"] = "running"
            _add_log(task, "▶ 최종 렌더링 시작")
            try:
                import time as _time
                _t0 = _time.monotonic()
                def _render_in_worker_thread() -> None:
                    from app.routers.subtitle import render_video_with_subtitles

                    db = SessionLocal()
                    try:
                        run_async(render_video_with_subtitles(project_id, db=db))
                    finally:
                        db.close()

                await asyncio.to_thread(_render_in_worker_thread)
                _elapsed = _time.monotonic() - _t0
                _add_log(task, f"✓ 최종 렌더링 완료 ({_elapsed:.1f}초)")
            except Exception as e:
                tb = traceback.format_exc()
                print(f"[oneclick] step 최종 렌더링 FAILED: {e}\n{tb}")
                _add_log(task, f"✗ 최종 렌더링 실패: {type(e).__name__}: {e}", "error")
                task["step_states"]["6"] = "failed"
                task["status"] = "failed"
                task["error"] = f"최종 렌더링 실패: {type(e).__name__}: {e}"
                task["finished_at"] = _utcnow_iso()
                _update_project_status(project_id, "failed")
                return

            task["step_states"]["6"] = "completed"

        # --- Step 7: 업로드 대기 이관 ---
        # 최종 렌더링 이후에는 제작 runner 를 점유하지 않는다. 업로드는 별도
        # upload-pending worker 가 1회만 시도하고, 실패 시 실패로 남긴다.
        if task.get("status") == "cancelled":
            task["step_states"]["7"] = "cancelled"
            task["error"] = task.get("error") or "사용자 취소"
            task["finished_at"] = task.get("finished_at") or _utcnow_iso()
            _update_project_status(project_id, "cancelled")
            return

        if task["step_states"].get("7") == "completed":
            task["current_step"] = None
            task["current_step_name"] = None
            task["status"] = "completed"
            task["finished_at"] = _utcnow_iso()
            _update_project_status(project_id, "completed")
            return

        uploaded_project = _load_project(project_id)
        uploaded_url = str(getattr(uploaded_project, "youtube_url", "") or "").strip() if uploaded_project else ""
        if _youtube_video_id_from_url(uploaded_url) and _complete_task_from_existing_upload(
            task,
            project_id,
            dict(getattr(uploaded_project, "config", None) or config or {}),
        ):
            _save_tasks_to_disk()
            return

        _mark_task_upload_pending(task, project_id)
        _add_log(task, "✓ 최종 렌더링 완료 — 업로드 대기로 이관")
        _save_tasks_to_disk()
        _schedule_upload_pending_worker()
        return


def _update_project_status(project_id: str, status: str) -> None:
    db = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == project_id).first()
        if p:
            p.status = status
            db.commit()
    finally:
        db.close()


def _completed_project_step_states(
    existing_states: Optional[dict[str, Any]],
    task_states: Optional[dict[str, Any]],
) -> dict[str, Any]:
    states = dict(existing_states or {})
    for key, value in dict(task_states or {}).items():
        key_s = str(key)
        if key_s in {"story", "2", "3", "4", "5", "6", "7"} and value == "completed":
            states[key_s] = "completed"
    states["6"] = "completed"
    states["7"] = "completed"
    return states


def _mark_project_upload_completed(project_id: str, task_states: Optional[dict[str, Any]] = None) -> None:
    db = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == project_id).first()
        if not p:
            return
        p.status = "completed"
        p.current_step = 7
        p.step_states = _completed_project_step_states(p.step_states, task_states)
        try:
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(p, "step_states")
        except Exception:
            pass
        db.commit()
    finally:
        db.close()


def _update_project_upload_step_state(
    project_id: str,
    *,
    status: str,
    current_step: Optional[int],
    step7_state: str,
) -> None:
    db = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == project_id).first()
        if not p:
            return
        states = dict(p.step_states or {})
        states["6"] = "completed"
        states["7"] = step7_state
        p.status = status
        p.current_step = current_step
        p.step_states = states
        try:
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(p, "step_states")
        except Exception:
            pass
        db.commit()
    finally:
        db.close()


def _mark_task_upload_pending(task: dict[str, Any], project_id: str) -> None:
    states = dict(task.get("step_states") or {})
    states["6"] = "completed"
    states["7"] = "pending"
    task["step_states"] = states
    task["status"] = "upload_pending"
    task["current_step"] = None
    task["current_step_name"] = None
    task["current_step_label"] = None
    task["current_step_completed"] = 0
    task["current_step_total"] = 0
    task["current_step_progress_text"] = None
    task["current_step_cut_progress_pct"] = None
    task["current_step_active_cut"] = None
    task["sub_status"] = None
    task.pop("resume_from_step", None)
    task["error"] = None
    now = _utcnow_iso()
    task["finished_at"] = task.get("finished_at") or now
    task["upload_pending_at"] = task.get("upload_pending_at") or task["finished_at"]
    task.setdefault("youtube_upload_attempt_count", 0)
    task["progress_pct"] = _compute_progress_pct(task)
    _update_project_upload_step_state(
        project_id,
        status="upload_pending",
        current_step=6,
        step7_state="pending",
    )


def _reset_project_steps_for_resume(project_id: str, resume_step: int) -> None:
    db = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == project_id).first()
        if not p:
            return
        states = dict(p.step_states or {})
        for _slug, step_num, _label in STEP_ORDER:
            if step_num >= resume_step and states.get(str(step_num)) != "completed":
                states[str(step_num)] = "pending"
        p.step_states = states
        if p.status in ("failed", "cancelled"):
            p.status = "draft"
        try:
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(p, "step_states")
        except Exception:
            pass
        db.commit()
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Public API (routers/oneclick.py 에서 호출)
# --------------------------------------------------------------------------- #

def _mark_stale_inflight_tasks() -> bool:
    """Recover UI-visible in-flight state when no runner exists in this process."""
    changed = False
    dispatch_needed = False
    for task_id, task in list(_TASKS.items()):
        status = str(task.get("status") or "")
        if status not in ("running", "queued"):
            continue
        runner = _ACTIVE_RUNS.get(task_id)
        if runner is not None and not runner.done():
            continue
        if _is_externally_managed_task(task_id, task):
            continue
        if status == "queued":
            dispatch_needed = True
            continue
        if _has_running_task(exclude_task_id=task_id):
            continue
        if _prepare_inflight_task_for_restart(task):
            dispatch_needed = True
            changed = True

    if dispatch_needed and not _has_running_task():
        dispatched = _dispatch_next_queued_task(respect_auto_pause=False)
        if dispatched:
            changed = True
    return changed


def prepare_task(
    *,
    template_project_id: Optional[str],
    topic: str,
    title: Optional[str] = None,
    target_duration: Optional[int] = None,
    episode_openings: Optional[List[str]] = None,
    episode_endings: Optional[List[str]] = None,
    episode_core_content: Optional[str] = None,
    episode_number: Optional[int] = None,
    series: Optional[str] = None,
    episode_code: Optional[str] = None,
    next_episode_preview: Optional[str] = None,
    channel: Optional[int] = None,
) -> dict:
    """프로젝트 준비 + task 레코드 생성. 아직 실행은 안 함.

    v1.1.52: **기존 미완성 프로젝트 자동 감지** — 동일 주제로 이미 생성된
    프로젝트가 있고, 1개 이상의 스텝이 완료됐으면 새로 만들지 않고 재사용한다.
    완료된 스텝은 step_states 에 "completed" 로 표시해서 _run_sync_pipeline 이
    자동으로 건너뛴다. 실패해도 만들어진 생성물은 보존된다.

    v1.1.42: `target_duration` (초) 을 받아 clone 시 config 에 반영.
    """
    _ensure_state_loaded()
    source_project_id = _channel_studio_project_id(channel, template_project_id)
    if source_project_id:
        existing_project_id = _find_existing_project_for_queue_item(
            {
                "topic": topic,
                "template_project_id": source_project_id,
                "target_duration": target_duration or ONECLICK_MAIN_TARGET_DURATION,
                "target_cuts": ONECLICK_MAIN_CUT_COUNT,
                "channel": channel,
                "openings": episode_openings,
                "endings": episode_endings,
                "core_content": episode_core_content,
                "episode_number": episode_number,
                "series": series,
                "episode_code": episode_code,
                "next_episode_preview": next_episode_preview,
            }
        )
        if existing_project_id:
            task = recover_project(existing_project_id)
            try:
                ch_int = int(channel or task.get("channel") or 0)
                if 1 <= ch_int <= 4:
                    task["channel"] = ch_int
            except (TypeError, ValueError):
                pass
            if episode_number:
                task["episode_number"] = episode_number
            if episode_code:
                task["episode_code"] = str(episode_code).strip()
            task["source_project_id"] = source_project_id
            task["template_project_id"] = source_project_id
            _add_log(task, f"기존 에피소드 산출물 재사용: {existing_project_id}", "info")
            _save_tasks_to_disk()
            return task
        return _prepare_v3_studio_linked_task(
            source_project_id=source_project_id,
            topic=topic,
            title=title,
            episode_openings=episode_openings,
            episode_endings=episode_endings,
            episode_core_content=episode_core_content,
            episode_number=episode_number,
            series=series,
            episode_code=episode_code,
            next_episode_preview=next_episode_preview,
            channel=channel,
        )

    # ── 기존 미완성 프로젝트 재사용 시도 ──
    reusable = _find_reusable_project(template_project_id, topic, channel)
    if reusable:
        project, detected_states = reusable
        renamed_id = _rename_existing_oneclick_project_to_titleless(
            project.id,
            channel=channel,
            episode_number=episode_number,
        )
        if renamed_id != project.id:
            fresh_project = _load_project(renamed_id)
            if fresh_project:
                project = fresh_project
        _ensure_project_layout(project.id, project.config or {})
        detected_states, detected_counts, detected_total, removed = _cleanup_and_detect_completed_steps(project.id, project.config or {})

        # v1.1.57: 재사용 시 현재 프리셋(template) 의 config 로 갱신한다.
        # 이전에는 생성 당시의 옛 config (예: language=ko) 가 그대로 박혀
        # 있어서, 사용자가 프리셋을 English 로 바꾸고 재실행해도 한국어로
        # 대본이 나오는 버그가 있었다. 단, 이미 완료된 스텝의 결과물(스크립트
        # 파일 등)은 그대로 두고, 앞으로 실행될 스텝에만 새 config 가 적용된다.
        try:
            from app.routers.projects import DEFAULT_CONFIG
            db_refresh = SessionLocal()
            try:
                base = dict(DEFAULT_CONFIG)
                old_cfg = dict(project.config or {})
                if template_project_id:
                    tmpl = (
                        db_refresh.query(Project)
                        .filter(Project.id == template_project_id)
                        .first()
                    )
                    if tmpl and tmpl.config:
                        base.update(tmpl.config)
                    base["template_project_id"] = template_project_id
                elif old_cfg.get("template_project_id"):
                    base["template_project_id"] = old_cfg["template_project_id"]
                # __oneclick__ 마커 유지 + 기존 target_duration 보존
                base["__oneclick__"] = True
                base["auto_pause_after_step"] = False
                _force_oneclick_main_length(base, target_duration or old_cfg.get("target_duration"))

                # v1.2.9: 에피소드 상세 — 재사용 시에도 최신값으로 갱신.
                # None 이면 기존값 유지. 전달은 있지만 비어 있으면 제거.
                def _clean_list(xs):
                    return [x for x in [str(v or "").strip() for v in (xs or [])] if x]

                if episode_openings is not None:
                    filtered = _clean_list(episode_openings)
                    if filtered:
                        base["episode_openings"] = filtered
                    else:
                        base.pop("episode_openings", None)
                elif old_cfg.get("episode_openings"):
                    base["episode_openings"] = old_cfg["episode_openings"]

                if episode_endings is not None:
                    filtered = _clean_list(episode_endings)
                    if filtered:
                        base["episode_endings"] = filtered
                    else:
                        base.pop("episode_endings", None)
                elif old_cfg.get("episode_endings"):
                    base["episode_endings"] = old_cfg["episode_endings"]

                if episode_core_content is not None:
                    cc = str(episode_core_content or "").strip()
                    if cc:
                        base["episode_core_content"] = cc
                    else:
                        base.pop("episode_core_content", None)
                elif old_cfg.get("episode_core_content"):
                    base["episode_core_content"] = old_cfg["episode_core_content"]

                # v1.2.10: 시리즈 연속성 — episode_number / next_episode_preview
                if episode_number is not None:
                    try:
                        n = int(episode_number)
                        if n > 0:
                            base["episode_number"] = n
                        else:
                            base.pop("episode_number", None)
                    except (TypeError, ValueError):
                        base.pop("episode_number", None)
                elif old_cfg.get("episode_number"):
                    base["episode_number"] = old_cfg["episode_number"]

                if next_episode_preview is not None:
                    nep = str(next_episode_preview or "").strip()
                    if nep:
                        base["next_episode_preview"] = nep
                    else:
                        base.pop("next_episode_preview", None)
                elif old_cfg.get("next_episode_preview"):
                    base["next_episode_preview"] = old_cfg["next_episode_preview"]

                proj_in_db = (
                    db_refresh.query(Project)
                    .filter(Project.id == project.id)
                    .first()
                )
                if proj_in_db:
                    proj_in_db.config = base
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(proj_in_db, "config")
                    db_refresh.commit()
                    db_refresh.refresh(proj_in_db)
                    project = proj_in_db
            finally:
                db_refresh.close()
        except Exception as e:
            print(f"[oneclick] 재사용 프로젝트 config 갱신 실패: {e}")

        # 첫 번째 미완료 스텝 찾기
        first_pending = None
        for _slug, step_num, _label in STEP_ORDER:
            if detected_states.get(str(step_num)) != "completed":
                first_pending = step_num
                break

        task_id = str(uuid.uuid4())[:8]
        estimate = estimate_project(project.config or {})
        task = _make_task_record(
            task_id,
            template_project_id=template_project_id,
            project_id=project.id,
            topic=project.topic,
            title=project.title,
            estimate=estimate,
            config=project.config,
        )
        # 감지된 완료 상태 반영
        task["step_states"] = detected_states
        if first_pending:
            task["resume_from_step"] = first_pending
        else:
            task["status"] = "completed"
            task["finished_at"] = _utcnow_iso()

        # total_cuts 복원
        fresh = _load_project(project.id)
        if detected_total:
            task["total_cuts"] = int(detected_total)
        elif fresh and fresh.total_cuts:
            task["total_cuts"] = int(fresh.total_cuts)

        completed_labels = [
            label for _slug, sn, label in STEP_ORDER
            if detected_states.get(str(sn)) == "completed"
        ]
        print(
            f"[oneclick] 기존 프로젝트 재사용: {project.id} "
            f"(완료: {', '.join(completed_labels)}, "
            f"이어하기: Step {first_pending}부터)"
        )
        _TASKS[task_id] = task
        _save_tasks_to_disk()
        return task

    existing_project_id = _find_existing_unfinished_oneclick_project(
        topic,
        template_project_id=template_project_id,
        channel=channel,
    )
    if existing_project_id:
        existing_project_id = _rename_existing_oneclick_project_to_titleless(
            existing_project_id,
            channel=channel,
            episode_number=episode_number,
        )
        for existing_task in _TASKS.values():
            if existing_task.get("project_id") == existing_project_id:
                if _reconcile_task_outputs(existing_task, clear_terminal_cursor=True):
                    _save_tasks_to_disk()
                return existing_task

        project = _load_project(existing_project_id)
        if not project:
            raise ValueError(
                f"같은 채널/프리셋/토픽의 미완료 프로젝트({existing_project_id})가 있지만 DB에서 찾지 못했습니다."
            )

        _ensure_project_layout(existing_project_id, project.config or {})
        detected_states, detected_counts, detected_total, removed = _cleanup_and_detect_completed_steps(existing_project_id, project.config or {})
        first_pending = None
        for _slug, step_num, _label in STEP_ORDER:
            if detected_states.get(str(step_num)) != "completed":
                first_pending = step_num
                break

        task_id = str(uuid.uuid4())[:8]
        config = dict(project.config or {})
        try:
            from app.routers.projects import DEFAULT_CONFIG
            db_refresh = SessionLocal()
            try:
                refreshed = dict(DEFAULT_CONFIG)
                preset_id = template_project_id or config.get("template_project_id")
                if preset_id:
                    tmpl = (
                        db_refresh.query(Project)
                        .filter(Project.id == preset_id)
                        .first()
                    )
                    if tmpl and tmpl.config:
                        refreshed.update(tmpl.config)
                    refreshed["template_project_id"] = preset_id
                refreshed["__oneclick__"] = True
                refreshed["auto_pause_after_step"] = False
                _force_oneclick_main_length(refreshed)
                for key in (
                    "episode_openings",
                    "episode_endings",
                    "episode_core_content",
                    "episode_number",
                    "next_episode_preview",
                    "channel",
                ):
                    if key in config and key not in refreshed:
                        refreshed[key] = config[key]
                proj_in_db = (
                    db_refresh.query(Project)
                    .filter(Project.id == project.id)
                    .first()
                )
                if proj_in_db:
                    proj_in_db.config = refreshed
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(proj_in_db, "config")
                    db_refresh.commit()
                    db_refresh.refresh(proj_in_db)
                    project = proj_in_db
                    config = dict(project.config or {})
            finally:
                db_refresh.close()
        except Exception as e:
            print(f"[oneclick] 기존 미완성 프로젝트 config 갱신 실패: {e}")
        estimate = estimate_project(config)
        task = _make_task_record(
            task_id,
            template_project_id=template_project_id or config.get("template_project_id"),
            project_id=project.id,
            topic=project.topic,
            title=project.title,
            estimate=estimate,
            config=config,
        )
        task["step_states"] = detected_states
        task["completed_cuts_by_step"].update(detected_counts)
        task["status"] = "prepared"
        if first_pending:
            task["resume_from_step"] = first_pending
        else:
            task["status"] = "completed"
            task["finished_at"] = _utcnow_iso()
        if detected_total:
            task["total_cuts"] = int(detected_total)
        elif project.total_cuts:
            task["total_cuts"] = int(project.total_cuts)
        try:
            ch_int = int(channel or config.get("channel") or 0)
            if 1 <= ch_int <= 4:
                task["channel"] = ch_int
        except (TypeError, ValueError):
            pass
        task["logs"] = task.get("logs") or []
        _add_log(
            task,
            f"기존 미완료 프로젝트로 이어서 진행: {existing_project_id}",
            "info",
        )
        print(
            f"[oneclick] 기존 미완료 프로젝트 이어가기: {existing_project_id} "
            f"(이어하기: Step {first_pending or '모두완료'}부터)"
        )
        _TASKS[task_id] = task
        _save_tasks_to_disk()
        return task

    blocking_project_id = _find_blocking_broken_project(topic)
    if blocking_project_id:
        raise ValueError(
            f"기존 깨진 프로젝트({blocking_project_id})가 남아 있어 새 폴더를 만들지 않습니다. "
            "먼저 해당 태스크를 전체 초기화하거나 삭제해 주세요."
        )

    # ── 새 프로젝트 생성 ──
    project = _clone_project_from_template(
        template_project_id,
        topic,
        title,
        target_duration=target_duration,
        episode_openings=episode_openings,
        episode_endings=episode_endings,
        episode_core_content=episode_core_content,
        episode_number=episode_number,
        next_episode_preview=next_episode_preview,
        channel=channel,
    )
    task_id = str(uuid.uuid4())[:8]
    estimate = estimate_project(project.config or {})
    task = _make_task_record(
        task_id,
        template_project_id=template_project_id,
        project_id=project.id,
        topic=project.topic,
        title=project.title,
        estimate=estimate,
        config=project.config,
    )
    # v1.2.29: task 에도 channel 을 기록해 두면 UI / 디스크 저장에도 반영된다.
    try:
        if channel is not None:
            ch_int = int(channel)
            if 1 <= ch_int <= 4:
                task["channel"] = ch_int
    except (TypeError, ValueError):
        pass
    _TASKS[task_id] = task
    _save_tasks_to_disk()
    return task


def recover_project(project_id: str) -> dict:
    """v1.1.56: 프로젝트 ID 로 태스크를 복구한다.

    큐에서 사라졌거나, 서버 재시작으로 유실된 태스크를 디스크 파일 기반으로
    복구해서 이어서 하기 가능한 상태로 만든다.

    1. project_id 로 DB 에서 프로젝트를 찾는다.
    2. _detect_completed_steps 로 어디까지 완료됐는지 파악한다.
    3. 태스크 레코드를 _TASKS 에 등록한다 (status='failed' → 이어하기 가능).
    """
    _ensure_state_loaded()
    if _dedupe_tasks():
        _save_tasks_to_disk()

    # 이미 같은 project_id 의 태스크가 있으면 그대로 반환
    for t in _TASKS.values():
        if t.get("project_id") == project_id:
            return t

    project = _load_project(project_id)
    if not project:
        raise KeyError(f"프로젝트를 찾을 수 없습니다: {project_id}")

    config = dict(project.config or {})
    detected, detected_counts, detected_total, removed = _cleanup_and_detect_completed_steps(project_id, config)
    estimate = estimate_project(config)

    task_id = str(uuid.uuid4())[:8]
    task = _make_task_record(
        task_id,
        template_project_id=config.get("template_project_id"),
        project_id=project_id,
        topic=project.topic or "",
        title=project.title or "",
        estimate=estimate,
        config=config,
    )
    task["config"] = config
    if config.get("result_dir"):
        task["result_dir"] = str(config.get("result_dir"))
    task["step_states"] = detected
    task["completed_cuts_by_step"].update(detected_counts)

    # total_cuts 복원 — script.json 에서
    script_path = resolve_project_dir(project_id, config, create=False) / "script.json"
    if script_path.exists():
        try:
            script = json.loads(script_path.read_text(encoding="utf-8"))
            task["total_cuts"] = detected_total or len(script.get("cuts", []))
        except Exception:
            pass

    # 첫 번째 미완료 스텝
    first_pending = None
    for _slug, step_num, _label in STEP_ORDER:
        if detected.get(str(step_num)) != "completed":
            first_pending = step_num
            break

    if first_pending:
        task["resume_from_step"] = first_pending

    # 모든 스텝이 완료면 completed, 아니면 failed (이어하기 가능)
    all_done = all(v == "completed" for v in detected.values())
    task["status"] = "completed" if all_done else "failed"
    task["error"] = None if all_done else "태스크 복구됨 — 이어하기를 눌러주세요"
    task["finished_at"] = _utcnow_iso() if all_done else None

    completed_labels = [
        label for _slug, sn, label in STEP_ORDER
        if detected.get(str(sn)) == "completed"
    ]
    print(
        f"[oneclick] 프로젝트 복구: {project_id} "
        f"(완료: {', '.join(completed_labels) or '없음'}, "
        f"이어하기: Step {first_pending or '모두완료'}부터)"
    )
    _TASKS[task_id] = task
    _save_tasks_to_disk()
    return task


def start_task(task_id: str) -> dict:
    """prepared 상태의 task 를 실제로 실행. 백그라운드 asyncio.Task 등록."""
    _clear_emergency_stop_guard()
    _ensure_state_loaded()
    task = _TASKS.get(task_id)
    if not task:
        raise KeyError("task not found")
    task = _redirect_empty_v3_task_to_existing_episode(task_id, task)
    if task.get("status") == "queued":
        if not _has_running_task(exclude_task_id=task_id):
            _dispatch_next_queued_task(
                respect_auto_pause=False,
                respect_auto_delay=False,
            )
        return task
    if task["status"] not in ("prepared", "failed", "cancelled"):
        # 이미 running/completed 면 무시 (idempotent)
        return task
    task["status"] = "queued"
    task["error"] = None
    task["finished_at"] = None
    _refresh_task_from_current_preset(task)
    _add_log(task, "⏳ 실행 대기열 등록", "info")
    if _has_running_task(exclude_task_id=task_id):
        _save_tasks_to_disk()
        return task
    # v1.1.37 bugfix: get_event_loop() 는 worker thread 에서 에러. 반드시 async
    # 컨텍스트에서 호출되어야 하므로 get_running_loop() 로 의도를 명시. 라우터
    # oneclick.start 가 async def 로 선언되어 있어 여기서 running loop 가 보장됨.
    # v1.1.58: 중복 스케줄 방지 가드를 통한다.
    _dispatch_next_queued_task(
        respect_auto_pause=False,
        respect_auto_delay=False,
    )
    return task


def resume_task(task_id: str) -> dict:
    """실패/취소된 task 를 실패 지점부터 이어서 재실행.

    v1.1.49: 완료된 단계(step_states == "completed")는 건너뛰고,
    첫 번째 failed/pending/cancelled 단계부터 다시 실행한다.
    """
    _clear_emergency_stop_guard()
    _ensure_state_loaded()
    task = _TASKS.get(task_id)
    if not task:
        raise KeyError("task not found")
    if task["status"] not in ("failed", "cancelled", "paused", "completed", "queued"):
        raise ValueError(f"resume 불가: 현재 상태가 '{task['status']}'")
    task = _redirect_empty_v3_task_to_existing_episode(task_id, task)
    if task.get("status") == "completed":
        return task

    project_id = str(task.get("project_id") or "").strip()
    task_config = (
        task.get("config") if isinstance(task.get("config"), dict) else {}
    )
    task_config = _effective_project_config(project_id, task_config)
    project_dir = resolve_project_dir(project_id, task_config, create=False)
    script_path = project_dir / "script.json"
    has_db_script_cuts, db_cut_count = _project_has_db_script_cuts(project_id)
    if has_db_script_cuts:
        task.setdefault("step_states", {})["2"] = "completed"
        if db_cut_count:
            task["total_cuts"] = db_cut_count
    linked_audio_count, linked_audio_total = _link_existing_audio_files(project_id, project_dir)
    if linked_audio_total and linked_audio_count >= linked_audio_total:
        task.setdefault("step_states", {})["3"] = "completed"
        task.setdefault("completed_cuts_by_step", {})["3"] = linked_audio_count
    prior_error = str(task.get("error") or "")
    prior_logs = task.get("logs") or []
    prior_cuts = dict(task.get("completed_cuts_by_step") or {})
    has_downstream_outputs = False
    try:
        for sub in ("audio", "images", "videos", "output"):
            subdir = project_dir / sub
            if not subdir.exists():
                continue
            if sub == "output":
                blocking = [
                    p for p in subdir.iterdir()
                    if p.is_file() and not p.name.lower().startswith("thumbnail")
                ]
                if blocking:
                    has_downstream_outputs = True
                    break
            elif any(subdir.iterdir()):
                has_downstream_outputs = True
                break
    except Exception:
        has_downstream_outputs = False
    def _first_unfinished_step() -> int:
        for _slug, step_num, _label in STEP_ORDER:
            state = task.get("step_states", {}).get(str(step_num), "pending")
            if state != "completed":
                return step_num
        return 2

    try:
        intended_resume_step = int(task.get("resume_from_step") or _first_unfinished_step())
    except (TypeError, ValueError):
        intended_resume_step = _first_unfinished_step()
    downstream_progress = (
        any(int(prior_cuts.get(step_key) or 0) > 0 for step_key in ("3", "4", "5"))
        or has_downstream_outputs
    )
    can_regenerate_script = intended_resume_step <= 2 and not downstream_progress

    if not script_path.exists() and not has_db_script_cuts:
        if (
            not can_regenerate_script
            and (
                "script.json" in prior_error.lower()
                or any("script.json" in str(item.get("msg") or "").lower() for item in prior_logs if isinstance(item, dict))
                or downstream_progress
            )
        ):
            msg = (
                "script.json 이 없는 깨진 작업입니다. "
                "자동 재생성을 막기 위해 이어서 하기를 차단했습니다."
            )
            task["status"] = "failed"
            task["error"] = msg
            task["finished_at"] = _utcnow_iso()
            task["resume_from_step"] = 2
            _save_tasks_to_disk()
            raise ValueError(msg)

    previous_states = dict(task.get("step_states") or {})
    if _reconcile_task_outputs(task, clear_terminal_cursor=True):
        _save_tasks_to_disk()
    if has_db_script_cuts:
        task.setdefault("step_states", {})["2"] = "completed"
        if db_cut_count:
            task["total_cuts"] = db_cut_count
            task.setdefault("completed_cuts_by_step", {})["2"] = db_cut_count
    linked_audio_count, linked_audio_total = _link_existing_audio_files(project_id, project_dir)
    if linked_audio_total and linked_audio_count >= linked_audio_total:
        task.setdefault("step_states", {})["3"] = "completed"
        task.setdefault("completed_cuts_by_step", {})["3"] = linked_audio_count

    # 깨진 복구 프로젝트 보호:
    # 이전엔 step_states 가 오래된 completed 상태로 남아 있으면 script.json 이
    # 사라진 뒤에도 step 4부터 그대로 재개되어 이미지/영상 API를 다시 호출했다.
    # 핵심 파일이 없으면 자동 재생성으로 넘어가지 말고 즉시 중단한다.
    if any(previous_states.get(str(step_num)) == "completed" for _, step_num, _ in STEP_ORDER):
        current_states = task.get("step_states") or {}
        if current_states.get("2") != "completed" and not has_db_script_cuts:
            msg = (
                "script.json 이 없어 이어서 할 수 없습니다. "
                "자동 재생성을 막기 위해 중단했습니다."
            )
            task["status"] = "failed"
            task["error"] = msg
            task["finished_at"] = _utcnow_iso()
            task["resume_from_step"] = 2
            _save_tasks_to_disk()
            raise ValueError(msg)

    # 첫 번째 미완료 단계 찾기
    resume_step = None
    for _slug, step_num, _label in STEP_ORDER:
        state = task["step_states"].get(str(step_num), "pending")
        if state != "completed":
            resume_step = step_num
            break

    if resume_step is None:
        # 모든 단계가 completed — 사실상 완료 상태
        task["status"] = "completed"
        task["finished_at"] = _utcnow_iso()
        return task

    # 실패/취소된 단계와 이후 단계 상태를 pending 으로 리셋
    found = False
    for _slug, step_num, _label in STEP_ORDER:
        if step_num == resume_step:
            found = True
        if found:
            task["step_states"][str(step_num)] = "pending"

    # task 메타 리셋
    task["status"] = "queued"
    task["error"] = None
    task["finished_at"] = None
    task["resume_from_step"] = resume_step
    if project_id:
        _reset_project_steps_for_resume(project_id, resume_step)
    _add_log(task, f"↻ 이어서 하기 대기열 등록 (Step {resume_step})", "info")

    # Redis cancel 플래그 초기화
    try:
        from app.tasks.pipeline_tasks import _redis_set
        _redis_set(f"pipeline:cancel:{task['project_id']}", "")
    except Exception:
        pass

    if _has_running_task(exclude_task_id=task_id):
        _save_tasks_to_disk()
        return task

    # v1.1.58: 이전 인스턴스가 _RUN_LOCK 을 들고 있을 수 있으므로 가드로 정리 후 스케줄
    _dispatch_next_queued_task(
        respect_auto_pause=False,
        respect_auto_delay=False,
    )
    return task


def cancel_task(task_id: str) -> dict:
    """사용자 `중지` — 어떤 상태든 즉시 `cancelled` 로 표시한다.

    v1.1.48 이전에는 running 상태일 때 status 를 그대로 두고 Redis cancel 플래그
    에만 의존했다. 문제는:

    1. 사용자가 중지를 누른 직후에도 UI 가 여전히 `running` 으로 보여
       "중지가 안되네" 라고 느꼈다.
    2. 대본 생성(`_step_script`) 단계는 check_pause_or_cancel 호출이 전혀 없어
       LLM 이 끝날 때까지(30~60초) 플래그가 사실상 무시됐다.
    3. runner 가 PipelineCancelled 를 catch 하지 않아 취소가 `failed` 로 기록.

    v1.1.48 는 세 경로를 모두 수선한다:
    - 여기서 task status 를 즉시 `cancelled` + `finished_at` 로 마킹 → UI 즉시 반영.
    - `_run_oneclick_task` 가 매 단계 진입 전/후로 이 status 를 확인하고 빠진다.
    - `_step_script` 가 LLM 전후로 check_pause_or_cancel 을 돌아 중간 이탈 가능.
    - `_run_oneclick_task` 가 `PipelineCancelled` 를 별도로 잡아 cancelled 로 마감.

    즉 pipeline step 내부 루프(_step_voice/image/video)는 기존처럼 Redis 플래그로
    깨어나고, 대본 단계는 status 폴링 + 전후 체크로 빠지고, UI 는 즉시 업데이트된다.
    """
    _ensure_state_loaded()
    task = _TASKS.get(task_id)
    if not task:
        raise KeyError("task not found")

    pid = task.get("project_id")

    # v1.2.26: 사용자 피드백 우선 — 정리 작업 전에 UI 가 보는 status 부터 바꾼다.
    # 이전에는 redis/comfyui 호출이 슬로우 응답이면 cancel POST 응답이 5~10초
    # 지연돼 "버튼 안먹는다" 로 느껴졌다. 정리 작업은 그 다음에 fire-and-forget.
    if task["status"] not in ("completed", "failed", "cancelled"):
        task["status"] = "cancelled"
        task["error"] = task.get("error") or "사용자 취소"
        task["finished_at"] = task.get("finished_at") or _utcnow_iso()
        try:
            _add_log(task, "⏹ 사용자 중단 요청 — 모든 외부 API 호출 차단 시작", "warn")
        except Exception:
            pass

    # 1) Redis cancel 플래그 — 각 step 의 for-loop 에서 다음 iteration 진입 전,
    #    그리고 모든 외부 API 서비스(fal/openai/kling/elevenlabs/grok/flux/
    #    nano-banana/seedance/seedream/z-image) 의 raise_if_cancelled() 가
    #    이 플래그를 본다. 즉 set 만 되면 모든 in-flight polling 루프가 다음
    #    iteration 에서 OperationCancelled 로 이탈한다.
    if pid:
        try:
            from app.tasks.pipeline_tasks import _redis_set
            _redis_set(f"pipeline:cancel:{pid}", "1")
        except Exception as _e:
            print(f"[oneclick.cancel] redis flag set failed: {_e}")
        _cancel_studio_task_manager_steps(pid)
        # v1.2.29: 프로세스 halt 집합에도 마킹 — redis 장애시에도 보장되는 경로
        try:
            from app.services.cancel_ctx import mark_halted
            mark_halted(pid)
        except Exception:
            pass

    # 2) asyncio.Task 즉시 취소 — 취소 체크를 기다리지 않고 바로 깨운다.
    try:
        prev = _ACTIVE_RUNS.get(task_id)
        if prev is not None and not prev.done():
            prev.cancel()
        _ACTIVE_RUNS.pop(task_id, None)
    except Exception as e:
        print(f"[oneclick.cancel] asyncio task cancel skipped: {e}")

    try:
        task["progress_pct"] = _compute_progress_pct(task)
        _save_tasks_to_disk()
    except Exception:
        pass

    # 3) v1.2.23 [돈줄 차단 강화]: 이미 ComfyUI 에 제출된 프롬프트가 끝까지
    #    실행되는 문제를 막는다. cancel 은 "다음 컷 제출 금지" 만 하던 게 문제.
    #    사용자 보고: "큐에 작업 없는데 ComfyUI 가 SDXL 을 계속 돌린다."
    #    → 이미 제출된 프롬프트 interrupt + 대기 큐 clear 를 동시에 호출.
    #
    # v1.2.27: sync 라우터 경로에서 `asyncio.run(_kill_comfy())` 가 httpx timeout
    # 10s × 2 = 20s blocking 하던 문제. `cancel` 라우터가 sync def 라 FastAPI
    # threadpool 에서 돌지만, 이 스레드가 20s 막히면 `cancel()` API 응답이
    # 돌아오지 않아 프런트의 "중단 중..." 이 고착된다. 전체 상한을 3s 로 줄이고,
    # 시간 초과하면 조용히 포기한다 (redis flag + task status 는 위에서 이미 세팅됨).
    def _cancel_comfy_background() -> None:
        try:
            from app.services import comfyui_client

            async def _kill_comfy():
                await asyncio.gather(
                    comfyui_client.interrupt(),
                    comfyui_client.clear_queue(),
                    return_exceptions=True,
                )

            async def _kill_with_timeout():
                try:
                    await asyncio.wait_for(_kill_comfy(), timeout=3.0)
                except asyncio.TimeoutError:
                    print("[oneclick.cancel] comfyui interrupt 3s timeout — 응답 포기")
                except Exception as e:
                    print(f"[oneclick.cancel] comfyui interrupt err: {e}")

            asyncio.run(_kill_with_timeout())
        except Exception as e:
            print(f"[oneclick.cancel] comfyui interrupt skipped: {e}")

    try:
        threading.Thread(
            target=_cancel_comfy_background,
            name="oneclick-cancel-comfy",
            daemon=True,
        ).start()
    except Exception as e:
        print(f"[oneclick.cancel] comfyui background start skipped: {e}")

    return task


async def emergency_stop_all() -> dict:
    """v1.1.70 — 비상 정지. 서버에서 실행 중/대기 중인 모든 작업을 강제 중단.

    동기화되지 않은 ComfyUI 와 Python 간 불일치(서버에는 작업이 없는데
    ComfyUI 는 계속 이미지 생성) 문제를 해결하기 위한 풀 스택 중단.

    순서:
      1) 모든 running/queued 태스크에 대해 Redis cancel 플래그 설정
         → pipeline step 내부 루프(_step_voice/image/video)가 다음 컷
            진입 시 즉시 이탈 (돈줄 차단)
      2) `_ACTIVE_RUNS` 의 모든 asyncio.Task cancel
         → `_RUN_LOCK` 즉시 해제, runner coroutine 중단
      3) DB/메모리 태스크 상태 → cancelled
         → UI 가 즉시 최신 상태 반영
      4) ComfyUI `/interrupt` 호출 → 현재 실행 중인 prompt 중단
      5) ComfyUI `/queue` clear → 대기 큐 비움

    `delete_task` 와 달리 프로젝트 디렉토리(생성된 파일)는 보존한다.
    사용자가 "이어서 하기" 또는 "라이브러리 확인" 으로 복구할 수 있도록.

    반환값: 중단된 태스크 수 + ComfyUI 호출 결과 + 에러 목록.
    """
    from app.tasks.pipeline_tasks import _redis_set
    from app.services import comfyui_client
    from app.services.cancel_ctx import mark_halted

    _ensure_state_loaded()
    _set_emergency_stop_guard()

    stopped_ids: list[str] = []
    errors: list[str] = []

    # Prevent the daily scheduler from immediately starting a "missed" channel
    # after the user pressed "stop all". Queue items remain intact; only today's
    # already-due auto fire is marked as handled.
    try:
        now = datetime.now()
        today = _today_iso()
        lrd = dict(_QUEUE.get("last_run_dates") or {})
        for ch in CHANNELS:
            ch_key = str(ch)
            ct = (_QUEUE.get("channel_times") or {}).get(ch_key)
            if not ct:
                continue
            try:
                hh, mm = ct.split(":")
                due = (now.hour, now.minute) >= (int(hh), int(mm))
            except Exception:
                due = False
            if due and lrd.get(ch_key) != today:
                lrd[ch_key] = today
        _QUEUE["last_run_dates"] = lrd
        _save_queue_to_disk()
    except Exception as e:
        errors.append(f"queue auto-fire guard: {e}")

    # v1.2.29 긴급정지 사고 대응: 상태 필터에 걸리지 않는 '떠돌이 스레드' 도
    # 같은 project_id 로 돌고 있을 수 있으므로, _TASKS 안의 모든 project_id 를
    # 상태 무관하게 halt 집합에 넣는다. running/queued/paused 는 아래에서 asyncio
    # cancel + 상태 갱신까지 추가로 처리.
    for _pid in {t.get("project_id") for t in _TASKS.values() if t.get("project_id")}:
        try:
            mark_halted(_pid)
        except Exception as e:
            errors.append(f"mark_halted {_pid}: {e}")

    # 1~3) 모든 실행/대기 태스크 중단
    for task_id, task in list(_TASKS.items()):
        status = task.get("status")
        if status not in ("running", "queued", "paused", "prepared"):
            continue
        pid = task.get("project_id")

        # Redis cancel 플래그 + 프로세스 halt 집합 (이중 방어선)
        if pid:
            try:
                _redis_set(f"pipeline:cancel:{pid}", "1")
            except Exception as e:
                errors.append(f"redis cancel {task_id}: {e}")
            try:
                _cancel_studio_task_manager_steps(pid)
            except Exception as e:
                errors.append(f"studio task cancel {task_id}: {e}")
            try:
                mark_halted(pid)
            except Exception as e:
                errors.append(f"mark_halted {task_id}: {e}")

        # asyncio task cancel
        running_task = _ACTIVE_RUNS.get(task_id)
        if running_task is not None and not running_task.done():
            try:
                running_task.cancel()
            except Exception as e:
                errors.append(f"asyncio cancel {task_id}: {e}")
        _ACTIVE_RUNS.pop(task_id, None)

        # 태스크 상태 갱신
        task["status"] = "cancelled"
        task["error"] = task.get("error") or "비상 정지"
        task["finished_at"] = task.get("finished_at") or _utcnow_iso()
        try:
            task["progress_pct"] = _compute_progress_pct(task)
            _add_log(task, "⏹ 비상 정지 요청 — 모든 작업 중단", "warn")
        except Exception as e:
            errors.append(f"mark cancelled {task_id}: {e}")
        stopped_ids.append(task_id)

    if stopped_ids:
        try:
            _save_tasks_to_disk()
        except Exception as e:
            errors.append(f"save tasks: {e}")

    # 4~5) ComfyUI 서버 측 중단
    # 비상 정지 API 는 UI timeout 전에 즉시 돌아와야 한다. ComfyUI 응답 여부는
    # 기다리지 않고 백그라운드에서 best-effort 로 interrupt + queue clear 한다.
    comfy_interrupt_ok = False
    comfy_clear_ok = False

    try:
        loop = asyncio.get_running_loop()

        async def _stop_comfy_background():
            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        comfyui_client.interrupt(),
                        comfyui_client.clear_queue(),
                        return_exceptions=True,
                    ),
                    timeout=3.0,
                )
            except Exception as e:
                print(f"[oneclick] emergency stop comfyui background skipped: {e}")

        loop.create_task(_stop_comfy_background())
    except Exception as e:
        errors.append(f"comfyui fire-and-forget: {e}")

    print(
        f"[oneclick] EMERGENCY STOP — stopped={len(stopped_ids)} "
        f"comfy_interrupt={comfy_interrupt_ok} comfy_clear={comfy_clear_ok} "
        f"errors={len(errors)}"
    )

    return {
        "ok": True,
        "stopped_count": len(stopped_ids),
        "stopped_task_ids": stopped_ids,
        "comfyui_interrupt": comfy_interrupt_ok,
        "comfyui_queue_cleared": comfy_clear_ok,
        "errors": errors,
    }


def get_task(task_id: str) -> Optional[dict]:
    _ensure_state_loaded()
    _refresh_tasks_from_disk_if_newer()
    task = _TASKS.get(task_id)
    if not task:
        return None
    changed = False
    external_task = _is_externally_managed_task(task_id, task)
    if task.get("status") in _LIVE_REFRESH_STATUSES and not external_task:
        try:
            live_config = _effective_live_config_for_task(task)
            live_changes = _apply_live_config_to_task(
                task,
                live_config,
                update_channel=task.get("status") in ("prepared", "queued"),
            )
            if live_changes:
                changed = True
        except Exception:
            pass
    if task.get("status") in ("failed", "cancelled", "paused", "completed"):
        if _reconcile_task_outputs(task, clear_terminal_cursor=True):
            changed = True
    # 매 조회마다 진행률을 최신화
    task["progress_pct"] = _compute_progress_pct(task)
    if not external_task and _backfill_task_models_from_estimate(task):
        changed = True
    if not external_task and _refresh_task_safety(task, force=False):
        changed = True
    if not external_task and _sync_task_display_language(task):
        changed = True
    if not external_task and _normalize_failure_logs_for_readability(task):
        changed = True
    # v1.1.53: 썸네일 생성 상태 (waiting / generating / done / failed)
    # v1.1.55: failed:사유 형태인 경우 status 와 error 를 분리하여 전달
    # v1.1.58: 완료/실패 태스크는 실제 파일 존재 여부로 최종 판정 — Redis 고착 방지
    pid = task.get("project_id")
    if pid:
        raw = _redis_get(f"thumbnail:status:{pid}") or "waiting"
        # 태스크가 이미 끝났으면 Redis 대신 파일 체크로 확정
        if task["status"] in ("completed", "failed", "cancelled"):
            thumb_path = resolve_project_dir(
                pid,
                task.get("config") if isinstance(task.get("config"), dict) else {},
                create=False,
            ) / "output" / "thumbnail.png"
            if thumb_path.exists() and thumb_path.stat().st_size > 100:
                task["thumbnail_status"] = "done"
                task["thumbnail_error"] = None
            elif raw.startswith("failed:"):
                task["thumbnail_status"] = "failed"
                task["thumbnail_error"] = raw[len("failed:"):]
            else:
                # generating 이 고착됐거나 waiting 인데 태스크는 끝남 → 실패 처리
                task["thumbnail_status"] = "failed"
                task["thumbnail_error"] = "썸네일 파일이 생성되지 않았습니다."
        else:
            # v1.1.60: 실행 중인 태스크라도 썸네일 파일이 실제로 있으면 done 으로
            # 본다. Redis 가 'waiting' 으로 고착된 resume 케이스 등에서 미리보기가
            # 안 뜨는 문제를 막는다.
            thumb_path = resolve_project_dir(
                pid,
                task.get("config") if isinstance(task.get("config"), dict) else {},
                create=False,
            ) / "output" / "thumbnail.png"
            if thumb_path.exists() and thumb_path.stat().st_size > 100:
                task["thumbnail_status"] = "done"
                task["thumbnail_error"] = None
            elif raw.startswith("failed:"):
                task["thumbnail_status"] = "failed"
                task["thumbnail_error"] = raw[len("failed:"):]
            else:
                task["thumbnail_status"] = raw
                task["thumbnail_error"] = None
    else:
        task["thumbnail_status"] = "waiting"
        task["thumbnail_error"] = None
    if changed:
        _save_tasks_to_disk()
    return task


def get_running_task_info() -> Optional[dict]:
    """v1.1.58: 현재 실행 중(running/queued)인 태스크 정보 반환.

    없으면 None. 있으면 { task_id, topic, status, progress_pct,
    started_at, estimated_remaining_seconds } 를 반환.
    """
    _ensure_state_loaded()
    _refresh_tasks_from_disk_if_newer()
    if _mark_stale_inflight_tasks():
        _save_tasks_to_disk()
    active_tasks = [
        t for t in _TASKS.values()
        if t.get("status") in ("running", "queued", "prepared")
    ]
    active_tasks.sort(
        key=lambda t: (
            {"running": 0, "queued": 1, "prepared": 2}.get(str(t.get("status") or ""), 9),
            str(t.get("started_at") or ""),
        )
    )
    for t in active_tasks:
        if t["status"] in ("running", "queued", "prepared"):
            if not _is_externally_managed_task(str(t.get("task_id") or ""), t) and _sync_task_display_language(t):
                _save_tasks_to_disk()
            pct = _compute_progress_pct(t)
            remaining = None
            est = t.get("estimate") or {}
            est_total = est.get("estimated_seconds")
            if est_total and pct > 0:
                elapsed_ratio = pct / 100.0
                if elapsed_ratio > 0.01:
                    remaining = int(est_total * (1.0 - elapsed_ratio) / elapsed_ratio)
            elif est_total:
                remaining = est_total
            return {
                "task_id": t["task_id"],
                "project_id": t.get("project_id"),
                "topic": t.get("topic") or t.get("title") or "",
                "title": t.get("title") or "",
                "episode_number": t.get("episode_number"),
                "channel": t.get("channel"),
                "status": t["status"],
                "progress_pct": pct,
                "started_at": t.get("started_at"),
                "estimated_remaining_seconds": remaining,
            }
    return None


def list_tasks() -> list[dict]:
    _ensure_state_loaded()
    _refresh_tasks_from_disk_if_newer()
    changed = _dedupe_tasks()
    if _drop_tasks_without_project_rows():
        changed = True
    if _sync_completed_projects_into_tasks():
        changed = True
    if _mark_stale_inflight_tasks():
        changed = True
    # 최신순. 진행률도 갱신.
    for tid in list(_TASKS.keys()):
        if _TASKS[tid].get("status") in ("failed", "cancelled", "paused", "completed"):
            if _reconcile_task_outputs(
                _TASKS[tid],
                clear_terminal_cursor=True,
                cleanup_broken=False,
            ):
                changed = True
            if _restore_executed_models_from_logs(_TASKS[tid]):
                changed = True
        _TASKS[tid]["progress_pct"] = _compute_progress_pct(_TASKS[tid])
        external_task = _is_externally_managed_task(tid, _TASKS[tid])
        if not external_task and _refresh_task_safety(_TASKS[tid], force=False):
            changed = True
        if not external_task and _sync_task_display_language(_TASKS[tid]):
            changed = True
        if not external_task and _refresh_task_estimate(_TASKS[tid]):
            changed = True
        if not external_task and _backfill_task_models_from_estimate(_TASKS[tid]):
            changed = True
        if not external_task and _normalize_failure_logs_for_readability(_TASKS[tid]):
            changed = True
        # v1.2.17: episode_number 지연 백필 — 구버전에서 생성된 task 는
        # 이 필드가 없다. project.config 에서 한 번만 조회해 task 에 박아둔다.
        # 이후 호출부터는 dict 내 캐시로 DB 히트 없이 반환된다.
        t = _TASKS[tid]
        if t.get("status") in _LIVE_REFRESH_STATUSES and not external_task:
            try:
                live_config = _effective_live_config_for_task(t)
                live_changes = _apply_live_config_to_task(
                    t,
                    live_config,
                    update_channel=t.get("status") in ("prepared", "queued"),
                )
                if live_changes:
                    changed = True
            except Exception:
                pass
        if "episode_number" not in t and not external_task:
            _ep: Optional[int] = None
            pid = t.get("project_id")
            if pid:
                try:
                    proj = _load_project(pid)
                    if proj and proj.config:
                        raw = (proj.config or {}).get("episode_number")
                        if raw is not None:
                            try:
                                n = int(raw)
                                if n > 0:
                                    _ep = n
                            except (TypeError, ValueError):
                                _ep = None
                except Exception:
                    _ep = None
            t["episode_number"] = _ep
            changed = True
    if changed:
        _save_tasks_to_disk()
    return sorted(
        _TASKS.values(),
        key=lambda t: t.get("created_at") or "",
        reverse=True,
    )


def clear_step_outputs(task_id: str, step: int) -> dict:
    """v1.1.52: 특정 단계의 생성물을 디스크에서 삭제하고 step_state 를 pending 으로 되돌린다.

    지원 단계:
        3 — audio/*.mp3
        4 — images/*.png (커스텀 이미지 제외)
        5 — videos/*.mp4 + output/merged.mp4
    """
    task = _TASKS.get(task_id)
    if not task:
        raise KeyError(f"task {task_id} not found")
    if task["status"] in ("running", "queued"):
        raise ValueError("실행 중인 태스크는 초기화할 수 없습니다")

    project_id = task["project_id"]
    task_config = (
        task.get("config") if isinstance(task.get("config"), dict) else {}
    )
    task_config = _effective_project_config(project_id, task_config)
    project_dir = resolve_project_dir(project_id, task_config, create=False)

    STEP_LABELS = {
        2: "script",
        3: "audio",
        4: "images",
        5: "videos",
        6: "render",
    }
    if step not in STEP_LABELS:
        raise ValueError("초기화 가능한 단계: 2(대본), 3(음성), 4(이미지), 5(영상), 6(렌더)")

    def _delete_path(path: Path) -> int:
        if not path.exists():
            return 0
        try:
            if path.is_dir():
                count = sum(1 for p in path.rglob("*") if p.is_file())
                shutil.rmtree(path, ignore_errors=True)
                return count
            path.unlink()
            return 1
        except OSError:
            return 0

    label = STEP_LABELS[step]
    deleted = 0
    if step == 2:
        deleted += _delete_path(project_dir / "script.json")
    elif step == 3:
        deleted += _delete_path(project_dir / "audio")
        (project_dir / "audio").mkdir(parents=True, exist_ok=True)
    elif step == 4:
        deleted += _delete_path(project_dir / "images")
        (project_dir / "images").mkdir(parents=True, exist_ok=True)
    elif step == 5:
        deleted += _delete_path(project_dir / "videos")
        (project_dir / "videos").mkdir(parents=True, exist_ok=True)
    elif step == 6:
        deleted += _delete_path(project_dir / "subtitles")
        deleted += _delete_path(project_dir / "output")
        deleted += _delete_path(project_dir / "tmp_render")
        (project_dir / "subtitles").mkdir(parents=True, exist_ok=True)
        (project_dir / "output").mkdir(parents=True, exist_ok=True)

    # DB step_state 도 되돌린다
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if project:
            if step == 2:
                db.query(Cut).filter(Cut.project_id == project_id).delete(synchronize_session=False)
                project.total_cuts = 0
            elif step == 3:
                for cut in db.query(Cut).filter(Cut.project_id == project_id).all():
                    cut.audio_path = None
                    cut.audio_duration = None
                    cut.audio_original_duration = None
                    cut.status = "pending"
            elif step == 4:
                for cut in db.query(Cut).filter(Cut.project_id == project_id).all():
                    cut.image_path = None
                    cut.image_model = None
                    cut.status = "pending"
            elif step == 5:
                for cut in db.query(Cut).filter(Cut.project_id == project_id).all():
                    cut.video_path = None
                    cut.status = "pending"

            states = dict(project.step_states or {})
            states[str(step)] = "pending"
            # 이후 단계도 pending 으로 (예: 이미지 삭제 시 영상도 무효)
            for s in range(step + 1, 8):
                if str(s) in states:
                    states[str(s)] = "pending"
            project.step_states = states
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(project, "step_states")
            db.commit()
    finally:
        db.close()

    # 태스크 메모리에도 반영
    step_states = task.get("step_states", {})
    step_states[str(step)] = "pending"
    for s in range(step + 1, 8):
        if str(s) in step_states:
            step_states[str(s)] = "pending"
    task["step_states"] = step_states
    if step == 2:
        task["total_cuts"] = 0
    cuts_by_step = dict(task.get("completed_cuts_by_step") or {})
    for s in range(step, 6):
        cuts_by_step[str(s)] = 0
    task["completed_cuts_by_step"] = cuts_by_step
    _add_log(task, f"🧹 {label} 초기화 완료 ({deleted}개 파일 삭제)", "warn")
    _save_tasks_to_disk()

    return {"ok": True, "step": step, "label": label, "deleted_files": deleted}


def reset_task(task_id: str, from_step: int = 2) -> dict:
    """v1.1.55: 프로젝트 전체 초기화 — from_step 부터 모든 단계를 pending 으로 되돌린다.

    from_step=2 (기본값) → 대본부터 전부 초기화.
    from_step=3 → 음성부터 초기화 (대본은 유지).

    v1.1.55: 백그라운드 스레드가 아직 돌고 있을 수 있으므로 cancel 키를 설정해
    잔존 스레드가 다음 check_pause_or_cancel 에서 종료되도록 보장한다.
    """
    task = _TASKS.get(task_id)
    if not task:
        raise KeyError(f"task {task_id} not found")
    if task["status"] in ("running", "queued"):
        raise ValueError("실행 중인 태스크는 초기화할 수 없습니다")

    # v1.1.55: 취소 후에도 백그라운드 스레드가 살아있을 수 있다.
    # cancel 키를 (재)설정하여 잔존 스레드가 확실히 멈추게 한다.
    pid = task.get("project_id")
    if pid:
        try:
            from app.tasks.pipeline_tasks import _redis_set
            _redis_set(f"pipeline:cancel:{pid}", "1")
        except Exception:
            pass
        # 잔존 스레드가 종료될 시간을 약간 준다 (TTS 한 건 완료 대기)
        import time
        time.sleep(0.5)

    total_deleted = 0
    for step in range(from_step, 8):
        try:
            result = clear_step_outputs(task_id, step)
            total_deleted += result.get("deleted_files", 0)
        except (ValueError, KeyError):
            continue

    # cancel 키 정리 (다음 재실행 시 cancel 상태로 시작하지 않도록)
    if pid:
        try:
            from app.tasks.pipeline_tasks import _redis_delete
            _redis_delete(f"pipeline:cancel:{pid}")
        except Exception:
            pass

    # 상태를 paused 로 되돌림 (재실행 가능)
    task["status"] = "paused"
    task["error"] = None
    task["finished_at"] = None
    task["resume_from_step"] = from_step
    task["progress_pct"] = 0.0
    cuts_by_step = dict(task.get("completed_cuts_by_step") or {})
    for step_num in range(from_step, 6):
        cuts_by_step[str(step_num)] = 0
    task["completed_cuts_by_step"] = cuts_by_step
    task["current_step_completed"] = 0
    task["current_step_total"] = 0
    task["current_step_label"] = None
    task["sub_status"] = None
    task["current_step"] = None
    task["current_step_name"] = None
    _add_log(task, f"↺ Step {from_step}부터 전체 초기화 완료 ({total_deleted}개 파일 삭제)", "warn")
    _save_tasks_to_disk()

    return {"ok": True, "from_step": from_step, "deleted_files": total_deleted}


def delete_task(task_id: str) -> bool:
    """태스크 하나를 삭제한다. 디스크 파일도 정리.

    v1.1.58 [돈줄 차단 HOTFIX]: 이전엔 status 가 running/queued 면 거부했고,
    설령 cancelled 상태에서 삭제가 통과돼도 백그라운드 스레드(특히 이미지
    배치 호출)가 계속 살아있어 OpenAI 비용이 새는 사고가 났다.
    이제는:
      1) Redis cancel 플래그를 즉시 세워 다음 컷 호출을 차단
      2) _ACTIVE_RUNS 의 asyncio.Task 를 cancel 해서 _RUN_LOCK 즉시 해제
      3) task 메타 + 디스크 파일 정리
    실행 중이어도 강제 삭제를 허용한다.
    """
    task = _TASKS.get(task_id)
    if not task:
        return False

    pid = task.get("project_id")

    # 1) 백그라운드 스레드가 다음 컷에서 즉시 빠지도록 cancel 플래그 세팅
    if pid:
        try:
            from app.tasks.pipeline_tasks import _redis_set
            _redis_set(f"pipeline:cancel:{pid}", "1")
        except Exception as e:
            print(f"[oneclick] delete: cancel 플래그 설정 실패: {e}")
        _cancel_studio_task_manager_steps(pid)
        # v1.2.29: 프로세스 halt 집합에도 마킹 (redis 와 독립적인 최후 안전선)
        try:
            from app.services.cancel_ctx import mark_halted
            mark_halted(pid)
        except Exception:
            pass

    # 2) asyncio Task cancel
    prev = _ACTIVE_RUNS.get(task_id)
    if prev is not None and not prev.done():
        try:
            prev.cancel()
            print(f"[oneclick] delete: 실행 중인 _run_oneclick_task({task_id}) 강제 취소")
        except Exception as e:
            print(f"[oneclick] delete: asyncio task cancel 실패: {e}")
    _ACTIVE_RUNS.pop(task_id, None)

    # 3) 태스크 + 디스크 정리
    task["status"] = "cancelled"
    task["finished_at"] = task.get("finished_at") or _utcnow_iso()
    _cleanup_project_files(pid, task.get("config") if isinstance(task.get("config"), dict) else None)
    _delete_project_db_record(pid)
    _TASKS.pop(task_id, None)
    _save_tasks_to_disk()
    return True


def _project_cleanup_paths(project_id: str, config: dict | None = None) -> list[Path]:
    """Return every on-disk location that may contain this project."""
    pid = str(project_id or "").strip()
    if not pid:
        return []
    candidates: list[Path] = []
    try:
        candidates.append(resolve_project_dir(pid, config=config, create=False))
    except Exception:
        pass
    try:
        candidates.append(SYSTEM_DIR.parent / pid)
    except Exception:
        pass
    try:
        candidates.append(SYSTEM_DIR / "projects" / pid)
    except Exception:
        pass
    for ch in range(1, 5):
        try:
            candidates.append(get_channel_projects_root(ch) / pid)
        except Exception:
            pass

    seen: set[str] = set()
    out: list[Path] = []
    for p in candidates:
        try:
            key = str(Path(p).resolve()).lower()
        except Exception:
            key = str(p).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(Path(p))
    return out


def _delete_project_db_record(project_id: str | None) -> bool:
    """Remove a generated oneclick project from DB so orphan scans cannot revive it."""
    pid = str(project_id or "").strip()
    if not pid:
        return False
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == pid).first()
        if not project:
            return False
        cfg = dict(project.config or {})
        if not cfg.get("__oneclick__"):
            return False
        db.query(Cut).filter(Cut.project_id == pid).delete(synchronize_session=False)
        db.query(ApiLog).filter(ApiLog.project_id == pid).delete(synchronize_session=False)
        for row in db.query(ScheduledEpisode).filter(ScheduledEpisode.project_id == pid).all():
            row.project_id = None
            row.status = "failed" if row.status == "running" else row.status
        db.delete(project)
        db.commit()
        return True
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        print(f"[oneclick] project DB cleanup failed ({pid}): {e}")
        return False
    finally:
        db.close()


def _cleanup_project_files(project_id: str | None, config: dict | None = None) -> int:
    """프로젝트 디렉토리 삭제. 삭제한 바이트 수 반환."""
    if not project_id:
        return 0
    total = 0
    for project_dir in _project_cleanup_paths(str(project_id), config):
        if not project_dir.exists():
            continue
        try:
            total += _dir_size(project_dir)
            shutil.rmtree(project_dir, ignore_errors=True)
        except Exception as e:
            print(f"[oneclick] 디스크 정리 실패 ({project_id}): {e}")
    return total


def _archive_project_files(project_id: str | None, config: dict | None = None) -> tuple[int, str | None]:
    """완료 프로젝트 디렉토리를 삭제하지 않고 _system 백업 폴더로 이동한다."""
    if not project_id:
        return 0, None
    pid = str(project_id)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = SYSTEM_DIR / f"requeue_completed_backup_{stamp}"
    total = 0
    first_target: str | None = None
    moved = 0
    for project_dir in _project_cleanup_paths(pid, config):
        if not project_dir.exists():
            continue
        try:
            size = _dir_size(project_dir)
            backup_root.mkdir(parents=True, exist_ok=True)
            target = backup_root / project_dir.name
            if target.exists():
                moved += 1
                target = backup_root / f"{project_dir.name}_{moved}"
            shutil.move(str(project_dir), str(target))
            total += size
            first_target = first_target or str(target)
        except Exception as e:
            print(f"[oneclick] 완료 프로젝트 백업 이동 실패 ({project_id}): {e}")
    return total, first_target


def _dir_size(path) -> int:
    """디렉토리 전체 크기 (바이트)."""
    from pathlib import Path
    total = 0
    try:
        for f in Path(path).rglob("*"):
            if f.is_file():
                total += f.stat().st_size
    except Exception:
        pass
    return total


def _inspect_project_progress(
    project_id: str | None,
    total_cuts: int | None,
    config: Optional[dict] = None,
) -> dict[str, Any]:
    """프로젝트 폴더를 열어 생성된 산출물로 실제 진행률을 계산.

    v1.2.22: 실패/취소 태스크를 큐로 되돌릴 때 "실제로 얼마나 만들어졌는지"
    를 UI 에 알려주기 위한 함수. 태스크 메타의 progress_pct 는 스텝 단위
    가중 추정값이라 컷 일부가 실패로 빠진 경우 과장/과소가 생긴다.
    여기서는 디스크를 직접 관찰한다:
      - script.json        → 스크립트 생성 완료 여부
      - audio/*.mp3|wav    → 음성 파일 수
      - images/*.png       → 이미지 컷 수
      - videos/*.mp4       → 영상 컷 수
      - output/merged.mp4  → 최종 머지 완료 여부
      - output/thumbnail.png → 썸네일 완료 여부

    반환:
      {
        "has_script": bool,
        "audio_count": int,
        "image_count": int,
        "video_count": int,
        "has_merged": bool,
        "has_thumbnail": bool,
        "total_cuts": int,
        "progress_pct": float,   # 0~100. 대략적 가중 평균
        "disk_bytes": int,
      }
    """
    from pathlib import Path
    out: dict[str, Any] = {
        "has_script": False,
        "audio_count": 0,
        "image_count": 0,
        "video_count": 0,
        "has_merged": False,
        "has_thumbnail": False,
        "total_cuts": int(total_cuts or 0),
        "progress_pct": 0.0,
        "disk_bytes": 0,
    }
    if not project_id:
        return out
    pdir = resolve_project_dir(project_id, config or {}, create=False)
    if not pdir.exists():
        return out
    try:
        out["disk_bytes"] = _dir_size(pdir)
    except Exception:
        pass
    try:
        out["has_script"] = (pdir / "script.json").exists()
    except Exception:
        pass
    for sub, key, exts in [
        ("audio", "audio_count", (".mp3", ".wav", ".m4a", ".ogg")),
        ("images", "image_count", (".png", ".jpg", ".jpeg", ".webp")),
        ("videos", "video_count", (".mp4", ".mov", ".webm")),
    ]:
        try:
            d = pdir / sub
            if d.exists():
                out[key] = sum(1 for f in d.iterdir() if f.is_file() and f.suffix.lower() in exts)
        except Exception:
            pass
    try:
        out["has_merged"] = (pdir / "output" / "merged.mp4").exists()
        out["has_thumbnail"] = (pdir / "output" / "thumbnail.png").exists()
    except Exception:
        pass

    # progress 근사: 5단계 가중치 (스크립트 10 / 음성 20 / 이미지 30 / 영상 30 / 머지+썸네일 10).
    # 각 단계는 컷 수 대비 비율로 환산.
    total = max(1, out["total_cuts"])
    script_pct = 10.0 if out["has_script"] else 0.0
    audio_pct = 20.0 * min(1.0, out["audio_count"] / total) if out["audio_count"] else 0.0
    image_pct = 30.0 * min(1.0, out["image_count"] / total) if out["image_count"] else 0.0
    video_pct = 30.0 * min(1.0, out["video_count"] / total) if out["video_count"] else 0.0
    final_pct = (5.0 if out["has_merged"] else 0.0) + (5.0 if out["has_thumbnail"] else 0.0)
    out["progress_pct"] = round(script_pct + audio_pct + image_pct + video_pct + final_pct, 1)
    return out


def requeue_task(task_id: str) -> dict[str, Any]:
    """완료/실패/취소된 태스크를 "초기화 + 대기 큐 복귀" 로 되돌린다.

    v1.2.22 — 사용자가 실패 카드의 ⟳ 버튼을 눌렀을 때 호출.
    동작:
      1) 태스크 조회 — 없으면 KeyError
      2) 상태가 running 이면 거부 (ValueError)
      3) 프로젝트 폴더 진행률 관찰 (리포트용)
      4) Redis cancel 플래그 + asyncio Task cancel (혹시 살아있으면)
      5) 프로젝트 폴더 전체 삭제. completed 는 삭제 대신 _system 아래로 백업 이동
      6) _TASKS 에서 해당 태스크 제거
      7) topic / openings / endings / core_content / episode_number /
         template_project_id / channel / target_duration 을 보존한 새 큐
         아이템을 해당 채널의 맨 뒤에 append
      8) queue 저장

    반환: { ok, task_id, channel, progress, queue_item, deleted_bytes }
    """
    global _QUEUE
    task = _TASKS.get(task_id)
    if not task:
        raise KeyError(f"task not found: {task_id}")

    status = task.get("status") or ""
    if status == "running":
        # 실행 중 태스크는 먼저 취소해야 함 — 자동 cancel+requeue 는 위험.
        raise ValueError("실행 중 태스크는 먼저 중단하세요")

    pid = task.get("project_id")
    channel = int(task.get("channel") or 1)
    if channel not in (1, 2, 3, 4):
        channel = 1

    # 1) 진행률 관찰 — 삭제 전
    progress = _inspect_project_progress(
        pid,
        task.get("total_cuts"),
        task.get("config") if isinstance(task.get("config"), dict) else {},
    )

    # 2) 혹시 실행 중일 수 있으니 cancel 먼저
    if pid:
        try:
            from app.tasks.pipeline_tasks import _redis_set
            _redis_set(f"pipeline:cancel:{pid}", "1")
        except Exception as e:
            print(f"[oneclick.requeue] cancel flag fail ({pid}): {e}")
    prev = _ACTIVE_RUNS.get(task_id)
    if prev is not None and not prev.done():
        try:
            prev.cancel()
        except Exception:
            pass
    _ACTIVE_RUNS.pop(task_id, None)

    # 3) 에피소드 상세 추출 (프로젝트 config → 큐 아이템 으로 되돌림).
    project = _load_project(pid) if pid else None
    cfg = dict(project.config or {}) if project else {}
    openings = cfg.get("episode_openings") or []
    endings = cfg.get("episode_endings") or []
    core = cfg.get("episode_core_content") or ""
    ep_num = cfg.get("episode_number") or task.get("episode_number")
    ep_coerced = coerce_episode_number(ep_num)
    series = str(cfg.get("series") or task.get("series") or "").strip()
    raw_episode_code = str(
        cfg.get("episode_code")
        or cfg.get("episode_id")
        or task.get("episode_code")
        or task.get("episode_id")
        or ""
    ).strip()
    next_preview = cfg.get("next_episode_preview") or ""

    # 4) 디스크 정리. 완료 작업은 산출물을 바로 삭제하지 않고 백업으로 이동한다.
    cleanup_config = task.get("config") if isinstance(task.get("config"), dict) else None
    archived_path: str | None = None
    if status == "completed":
        deleted_bytes, archived_path = _archive_project_files(pid, cleanup_config)
    else:
        deleted_bytes = _cleanup_project_files(pid, cleanup_config)
    _delete_project_db_record(pid)

    new_item = {
        "id": uuid.uuid4().hex[:8],
        "topic": str(task.get("topic") or "").strip() or "(주제 없음)",
        "template_project_id": task.get("template_project_id") or cfg.get("template_project_id") or None,
        "target_duration": ONECLICK_MAIN_TARGET_DURATION,
        "target_cuts": ONECLICK_MAIN_CUT_COUNT,
        "channel": channel,
        "openings": openings if isinstance(openings, list) else [],
        "endings": endings if isinstance(endings, list) else [],
        "core_content": core if isinstance(core, str) else "",
        "episode_number": ep_coerced,
        "series": series,
        "episode_code": raw_episode_code,
        "episode_id": raw_episode_code,
        "next_episode_preview": str(next_preview or "").strip(),
        "queued_source": "requeue",
        "queued_at": _utcnow_iso(),
        "queued_note": "완료 태스크 큐 복귀" if status == "completed" else "실패/중단 태스크 복구",
        "requeued_from_task_id": task_id,
    }

    # 5) 큐 정규화 + 해당 채널의 **맨 앞**에 삽입.
    # v1.2.28: 이전 버전은 list 끝에 append 였으나, 큐가 60건 이상인 상황에선
    # 복구된 아이템이 마지막 페이지로 밀려 "사라진 것처럼" 보였다. 같은 채널의
    # 첫 항목 앞에 넣어서 사용자가 즉시 확인 + 다음 자동 실행에 바로 반영되게 한다.
    items = list(_QUEUE.get("items") or [])
    insert_at = 0
    while insert_at < len(items) and _is_immediate_queue_item(items[insert_at]):
        insert_at += 1
    items.insert(insert_at, new_item)
    _QUEUE["items"] = items
    _QUEUE = _queue_normalize(_QUEUE)
    _save_queue_to_disk()

    # 6) 태스크 메타 제거 (_cleanup_project_files 이후)
    _TASKS.pop(task_id, None)
    _save_tasks_to_disk()

    return {
        "ok": True,
        "task_id": task_id,
        "channel": channel,
        "progress": progress,
        "queue_item": new_item,
        "deleted_bytes": deleted_bytes,
        "archived_path": archived_path,
    }


def requeue_channel_failed(channel: int) -> dict[str, Any]:
    """해당 채널의 실패/취소 태스크 전체를 "초기화 + 큐 복귀" 한다.

    v1.2.22 — 사용자가 채널 상단의 '이 채널 실패 전부 복귀' 를 눌렀을 때.
    각 태스크마다 requeue_task 를 호출하고 결과를 누적. 개별 실패는
    무시하고 나머지를 계속 처리한다.
    """
    if channel not in (1, 2, 3, 4):
        raise ValueError(f"invalid channel: {channel}")

    # 대상 수집 — 반복 중 _TASKS 가 변하므로 먼저 id 만 스냅샷.
    targets: list[str] = []
    for t in list(_TASKS.values()):
        if int(t.get("channel") or 1) != channel:
            continue
        states = t.get("step_states") or {}
        upload_recoverable = states.get("6") in ("completed", "done") and states.get("7") not in ("completed", "done")
        if t.get("status") not in ("failed", "cancelled", "paused") and not upload_recoverable:
            continue
        targets.append(t["task_id"])

    results: list[dict[str, Any]] = []
    total_bytes = 0
    errors: list[dict[str, Any]] = []
    for tid in targets:
        try:
            r = requeue_task(tid)
            results.append(r)
            total_bytes += int(r.get("deleted_bytes") or 0)
        except Exception as e:
            errors.append({"task_id": tid, "error": f"{type(e).__name__}: {str(e)[:200]}"})

    return {
        "ok": True,
        "channel": channel,
        "requeued_count": len(results),
        "total_deleted_bytes": total_bytes,
        "items": results,
        "errors": errors,
    }


# --------------------------------------------------------------------------- #
# v1.2.28 — 고아 프로젝트 (_TASKS 에 없는 디스크 잔존 프로젝트) 관리
# --------------------------------------------------------------------------- #


def list_orphan_projects(channel: Optional[int] = None) -> list[dict]:
    """_TASKS 에 없지만 DB/디스크에 남은 딸깍 프로젝트를 전부 나열한다.

    v1.2.28 — 채널 편집 패널의 "고아 프로젝트" 섹션이 이걸 호출해서
    "폴더로만 남은 과거 에피소드" 를 사용자에게 보여준다.

    반환되는 각 dict:
      {
        "project_id": str,
        "topic": str,
        "title": str,
        "episode_number": int | None,
        "channel": int,           # config 에 저장된 값. 없으면 1.
        "openings": list[str],
        "endings": list[str],
        "core_content": str,
        "next_episode_preview": str,
        "target_duration": int | None,
        "template_project_id": str | None,
        "progress": dict,         # _inspect_project_progress 결과
        "created_at": str,        # ISO string — Project.created_at
      }

    `channel` 인수가 주어지면(1~4) 해당 채널만 반환. 없으면 모든 채널.
    """
    _ensure_state_loaded()
    if _dedupe_tasks():
        _save_tasks_to_disk()

    known_pids = {
        (t.get("project_id") or "").strip()
        for t in _TASKS.values()
    }
    known_pids.discard("")

    out: list[dict] = []
    db = SessionLocal()
    try:
        rows = (
            db.query(Project)
            .filter(Project.id.like("딸깍_%"))
            .order_by(Project.created_at.desc())
            .limit(500)
            .all()
        )
        for proj in rows:
            if proj.id in known_pids:
                continue
            cfg = dict(proj.config or {})
            # __oneclick__ 마커가 없는 행은 건너뜀 — 비-딸깍 레거시 프로젝트 보호.
            if not cfg.get("__oneclick__"):
                continue

            # 디스크가 실제로 존재해야 복구 의미가 있음.
            pdir = resolve_project_dir(proj.id, cfg)
            if not pdir.exists():
                continue

            # v1.2.29: 채널 귀속 판정 로직.
            # 1) project_id 가 "딸깍_CH{n}_..." 로 시작하면 그 채널이 우선.
            # 2) config["channel"] 에 기록된 값이 있으면 그 다음 우선.
            # 3) 둘 다 없으면 "미귀속(unattributed)" 상태. 필터링 시 이런
            #    프로젝트는 어떤 채널에서 열어도 보이도록 한다 (사용자가
            #    원하는 채널로 복구할 수 있게).
            ch: Optional[int] = None
            try:
                _m = re.match(r"^딸깍_CH(\d+)_", proj.id or "")
                if _m:
                    _c = int(_m.group(1))
                    if 1 <= _c <= 4:
                        ch = _c
            except Exception:
                ch = None
            if ch is None:
                ch_raw = cfg.get("channel")
                try:
                    if ch_raw is not None:
                        _c = int(ch_raw)
                        if 1 <= _c <= 4:
                            ch = _c
                except (TypeError, ValueError):
                    ch = None
            unattributed = ch is None
            if channel is not None:
                # 특정 채널을 요청한 경우 — 해당 채널에 귀속됐거나 미귀속 프로젝트 허용.
                if not unattributed and ch != int(channel):
                    continue
            # 표시용 채널 — 미귀속은 "1" 로 표기하지 말고 None 그대로 넘긴다.
            # 프론트 호환을 위해 수치가 필요하면 요청된 channel, 아니면 0.
            ch_display: int = (
                ch if ch is not None
                else (int(channel) if channel is not None else 0)
            )

            # 에피소드 번호
            _ep_raw = cfg.get("episode_number")
            try:
                ep_num: Optional[int] = int(_ep_raw) if _ep_raw is not None else None
                if ep_num is not None and ep_num <= 0:
                    ep_num = None
            except (TypeError, ValueError):
                ep_num = None

            td_val: Optional[int] = ONECLICK_MAIN_TARGET_DURATION

            # 디스크 진행률
            try:
                # total_cuts 는 script.json 을 _inspect_project_progress 내부가 못 구하니
                # 별도 제공. script.json 이 없으면 0.
                total_cuts = 0
                sp = pdir / "script.json"
                if sp.exists():
                    try:
                        total_cuts = len(json.loads(sp.read_text(encoding="utf-8")).get("cuts", []))
                    except Exception:
                        total_cuts = 0
                progress = _inspect_project_progress(proj.id, total_cuts, cfg)
            except Exception:
                progress = {
                    "has_script": False,
                    "audio_count": 0,
                    "image_count": 0,
                    "video_count": 0,
                    "has_merged": False,
                    "has_thumbnail": False,
                    "total_cuts": 0,
                    "progress_pct": 0.0,
                    "disk_bytes": 0,
                }

            created_at_iso = ""
            try:
                if proj.created_at:
                    created_at_iso = proj.created_at.isoformat()
            except Exception:
                pass

            openings = cfg.get("episode_openings") or []
            endings = cfg.get("episode_endings") or []
            core = cfg.get("episode_core_content") or ""
            preview = cfg.get("next_episode_preview") or ""

            out.append({
                "project_id": proj.id,
                "topic": (proj.topic or "").strip(),
                "title": (proj.title or "").strip(),
                "episode_number": ep_num,
                "channel": ch_display,
                # v1.2.29: 미귀속 플래그. 프론트가 "⚠ 채널 불명 — 이 채널로 복구됩니다"
                # 같은 안내를 보여줄 수 있도록 힌트 제공.
                "unattributed": unattributed,
                "openings": openings if isinstance(openings, list) else [],
                "endings": endings if isinstance(endings, list) else [],
                "core_content": core if isinstance(core, str) else "",
                "next_episode_preview": str(preview or "").strip(),
                "target_duration": td_val,
                "target_cuts": ONECLICK_MAIN_CUT_COUNT,
                "template_project_id": cfg.get("template_project_id") or None,
                "progress": progress,
                "created_at": created_at_iso,
            })
    finally:
        db.close()

    # 최근 생성 순으로 정렬 (created_at 내림차순)
    out.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return out


def requeue_orphan_projects(
    project_ids: list[str],
    *,
    target_channel: Optional[int] = None,
) -> dict[str, Any]:
    """선택한 고아 프로젝트들을 "폴더 삭제 + 큐 재등록" 한다.

    v1.2.28 — 고아 프로젝트 섹션의 '선택 N건 복구' 가 이 함수를 호출한다.

    동작:
      1) 각 project_id 에 대해 DB/config 를 읽어 큐 아이템으로 되돌릴 메타를 수집
      2) 프로젝트 디스크 폴더 삭제 (_cleanup_project_files)
      3) 새 큐 아이템 생성 — requeue_task 와 동일한 스키마
      4) target_channel 이 지정되면 그 채널로, 없으면 config.channel (fallback 1) 로
      5) 모든 아이템을 _QUEUE.items 에 append 하고 저장

    반환: {
      ok, requeued_count, total_deleted_bytes,
      items: [{project_id, queue_item, deleted_bytes}],
      errors: [{project_id, error}]
    }
    """
    global _QUEUE
    if not isinstance(project_ids, list) or not project_ids:
        return {
            "ok": True,
            "requeued_count": 0,
            "total_deleted_bytes": 0,
            "items": [],
            "errors": [],
        }

    # 대상 검증 — _TASKS 에 들어있으면 (이미 태스크로 관리중) 건너뜀.
    known_pids = {
        (t.get("project_id") or "").strip()
        for t in _TASKS.values()
    }
    known_pids.discard("")

    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    total_bytes = 0
    new_items: list[dict[str, Any]] = []

    for pid in project_ids:
        pid = (pid or "").strip()
        if not pid:
            errors.append({"project_id": pid, "error": "empty project_id"})
            continue
        if pid in known_pids:
            errors.append({"project_id": pid, "error": "태스크로 관리 중인 프로젝트입니다"})
            continue

        # 1) 메타 수집
        project = _load_project(pid)
        if not project:
            errors.append({"project_id": pid, "error": "DB 에 프로젝트 레코드가 없습니다"})
            continue
        cfg = dict(project.config or {})
        if not cfg.get("__oneclick__"):
            errors.append({"project_id": pid, "error": "딸깍 프로젝트가 아닙니다"})
            continue

        # v1.2.29: 채널 결정 우선순위
        #   1) target_channel (사용자가 이 채널로 복구 요청)
        #   2) project_id prefix "딸깍_CH{n}_" 에서 파싱
        #   3) config.channel
        #   4) fallback = 1
        ch = 1
        resolved = False
        if target_channel is not None:
            try:
                ch = int(target_channel)
                resolved = True
            except (TypeError, ValueError):
                ch = 1
                resolved = False
        if not resolved:
            try:
                _m = re.match(r"^딸깍_CH(\d+)_", pid or "")
                if _m:
                    _c = int(_m.group(1))
                    if 1 <= _c <= 4:
                        ch = _c
                        resolved = True
            except Exception:
                pass
        if not resolved:
            try:
                _c = int(cfg.get("channel") or 1)
                if 1 <= _c <= 4:
                    ch = _c
                    resolved = True
            except (TypeError, ValueError):
                pass
        if ch < 1 or ch > 4:
            ch = 1

        openings = cfg.get("episode_openings") or []
        endings = cfg.get("episode_endings") or []
        core = cfg.get("episode_core_content") or ""
        preview = cfg.get("next_episode_preview") or ""
        ep_raw = cfg.get("episode_number")
        try:
            ep_num: Optional[int] = int(ep_raw) if ep_raw is not None else None
            if ep_num is not None and ep_num <= 0:
                ep_num = None
        except (TypeError, ValueError):
            ep_num = None

        td_val: Optional[int] = ONECLICK_MAIN_TARGET_DURATION

        topic = (project.topic or "").strip() or "(주제 없음)"
        tpl = cfg.get("template_project_id") or None

        # 2) 디스크 정리
        deleted_bytes = 0
        try:
            deleted_bytes = _cleanup_project_files(pid, cfg)
        except Exception as e:
            errors.append({"project_id": pid, "error": f"폴더 삭제 실패: {e}"})
            # 삭제에 실패해도 큐 복귀는 진행 (새 project_id 가 할당되므로 안전)

        # 3) 새 큐 아이템
        new_item = {
            "id": uuid.uuid4().hex[:8],
            "topic": topic,
            "template_project_id": tpl,
            "target_duration": td_val,
            "target_cuts": ONECLICK_MAIN_CUT_COUNT,
            "channel": ch,
            "openings": openings if isinstance(openings, list) else [],
            "endings": endings if isinstance(endings, list) else [],
            "core_content": core if isinstance(core, str) else "",
            "episode_number": ep_num,
            "next_episode_preview": str(preview or "").strip(),
            "queued_source": "orphan",
            "queued_at": _utcnow_iso(),
            "queued_note": "고아 프로젝트 복구",
            "restored_from_project_id": pid,
        }
        new_items.append(new_item)
        total_bytes += int(deleted_bytes or 0)
        results.append({
            "project_id": pid,
            "queue_item": new_item,
            "deleted_bytes": deleted_bytes,
        })

    # 4) 큐에 삽입 — 채널별로 **맨 앞**에 집어넣는다.
    # v1.2.28: 사용자 요구 "대기큐로 복구할때는 대기 맨 앞으로 보내게 해".
    # 같은 채널의 첫 항목 위치를 찾아 그 앞에 삽입. new_items 는 넘겨받은
    # 선택 순서를 유지 (여러 건이면 첫 건이 가장 위로 온다 → 목록 순서 그대로
    # 맨 앞에 쌓임).
    if new_items:
        items = list(_QUEUE.get("items") or [])
        insert_at = 0
        while insert_at < len(items) and _is_immediate_queue_item(items[insert_at]):
            insert_at += 1
        for offset, ni in enumerate(new_items):
            items.insert(insert_at + offset, ni)
        _QUEUE["items"] = items
        _QUEUE = _queue_normalize(_QUEUE)
        _save_queue_to_disk()

    return {
        "ok": True,
        "requeued_count": len(results),
        "total_deleted_bytes": total_bytes,
        "items": results,
        "errors": errors,
    }


def prune_tasks(keep: int = 20) -> None:
    """완료/실패 태스크가 너무 쌓이면 오래된 것부터 정리."""
    finished = [
        t for t in _TASKS.values()
        if t["status"] in ("completed", "failed", "cancelled")
        and not _task_within_log_retention(t)
    ]
    finished.sort(key=lambda t: t.get("finished_at") or t.get("created_at") or "")
    excess = len(finished) - keep
    if excess > 0:
        for t in finished[:excess]:
            _TASKS.pop(t["task_id"], None)
        _save_tasks_to_disk()


# --------------------------------------------------------------------------- #
# v1.1.54 — 완성작 관리 (라이브러리)
# --------------------------------------------------------------------------- #


def get_task_detail(task_id: str) -> dict:
    """완성작 상세 정보 — 프로젝트 메타 + 디스크 용량 + 컷 목록."""
    task = _TASKS.get(task_id)
    if not task:
        raise KeyError("task not found")

    project_id = task.get("project_id")
    project = _load_project(project_id) if project_id else None
    project_dir = (
        resolve_project_dir(project_id, project.config if project else task.get("config"), create=False)
        if project_id
        else None
    )

    # 디스크 용량
    disk_bytes = _dir_size(project_dir) if project_dir and project_dir.exists() else 0

    # 파일 존재 여부
    has_final = False
    has_thumbnail = False
    final_path = ""
    thumbnail_path = ""
    cut_images = []
    if project_dir and project_dir.exists():
        output_dir = project_dir / "output"
        # 최종 영상
        for name in ("final_with_subtitles.mp4", "final.mp4", "merged.mp4"):
            f = output_dir / name
            if f.exists() and f.stat().st_size > 100:
                has_final = True
                final_path = f"output/{name}"
                break
        # 썸네일
        for ext in ("png", "jpg", "jpeg", "webp"):
            f = output_dir / f"thumbnail.{ext}"
            if f.exists():
                has_thumbnail = True
                thumbnail_path = f"output/thumbnail.{ext}"
                break
        # 컷 이미지 목록
        images_dir = project_dir / "images"
        if images_dir.exists():
            for img in sorted(images_dir.glob("cut_*.png")):
                cut_images.append(f"images/{img.name}")
            if not cut_images:
                for img in sorted(images_dir.glob("cut_*.jpg")):
                    cut_images.append(f"images/{img.name}")

    # 소요 시간
    elapsed_sec = None
    if task.get("started_at") and task.get("finished_at"):
        try:
            from datetime import datetime
            start = datetime.fromisoformat(task["started_at"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(task["finished_at"].replace("Z", "+00:00"))
            elapsed_sec = int((end - start).total_seconds())
        except Exception:
            pass

    return {
        "task_id": task_id,
        "project_id": project_id,
        "topic": task.get("topic"),
        "title": task.get("title"),
        "status": task.get("status"),
        "total_cuts": task.get("total_cuts", 0),
        "disk_bytes": disk_bytes,
        "disk_mb": round(disk_bytes / (1024 * 1024), 1),
        "has_final_video": has_final,
        "final_video_path": final_path,
        "has_thumbnail": has_thumbnail,
        "thumbnail_path": thumbnail_path,
        "cut_images": cut_images,
        "cut_image_count": len(cut_images),
        "models": task.get("models"),
        "estimate": task.get("estimate"),
        "elapsed_sec": elapsed_sec,
        "youtube_url": project.youtube_url if project else None,
        "started_at": task.get("started_at"),
        "finished_at": task.get("finished_at"),
        "created_at": task.get("created_at"),
        "error": task.get("error"),
    }


def _upload_attempt_count(task: dict[str, Any]) -> int:
    try:
        return max(0, int(task.get("youtube_upload_attempt_count") or 0))
    except (TypeError, ValueError):
        return 0


def _mark_task_upload_started(task: dict[str, Any], project_id: str, *, mode: str) -> None:
    states = dict(task.get("step_states") or {})
    states["6"] = "completed"
    states["7"] = "running"
    task["step_states"] = states
    task["status"] = "uploading"
    task["current_step"] = 7
    task["current_step_name"] = "유튜브 업로드"
    task["current_step_label"] = "유튜브 업로드"
    task["sub_status"] = "uploading"
    task["finished_at"] = None
    task.pop("resume_from_step", None)
    task["error"] = None
    task["youtube_upload_attempt_count"] = _upload_attempt_count(task) + 1
    now = _utcnow_iso()
    task.setdefault("youtube_upload_first_attempt_at", now)
    task["youtube_upload_last_attempt_at"] = now
    task["youtube_upload_mode"] = mode
    _update_project_upload_step_state(
        project_id,
        status="uploading",
        current_step=7,
        step7_state="running",
    )


def _mark_task_upload_failed(task: dict[str, Any], project_id: str, message: str) -> None:
    states = dict(task.get("step_states") or {})
    states["6"] = "completed"
    states["7"] = "failed"
    task["step_states"] = states
    task["status"] = "upload_failed"
    task["current_step"] = None
    task["current_step_name"] = None
    task["current_step_label"] = None
    task["current_step_completed"] = 0
    task["current_step_total"] = 0
    task["current_step_progress_text"] = None
    task["current_step_cut_progress_pct"] = None
    task["current_step_active_cut"] = None
    task["sub_status"] = None
    task.pop("resume_from_step", None)
    task["error"] = message
    task["youtube_upload_error"] = message
    task["youtube_upload_failed_at"] = _utcnow_iso()
    task["finished_at"] = task["youtube_upload_failed_at"]
    task["progress_pct"] = _compute_progress_pct(task)
    _update_project_upload_step_state(
        project_id,
        status="upload_failed",
        current_step=7,
        step7_state="failed",
    )


def _upload_attempt_already_used(task: dict[str, Any]) -> bool:
    if _upload_attempt_count(task) > 0:
        return True
    states = dict(task.get("step_states") or {})
    return (
        str(task.get("status") or "").strip().lower() == "upload_failed"
        or states.get("7") == "failed"
    )


def _restore_unattempted_upload_pending_tasks() -> bool:
    """Render-complete tasks with no upload attempt must stay upload_pending."""
    changed = False
    for task in list(_TASKS.values()):
        status = str(task.get("status") or "").strip().lower()
        if status not in ("completed", "failed"):
            continue
        states = dict(task.get("step_states") or {})
        if states.get("6") != "completed" or states.get("7") != "pending":
            continue
        if _upload_attempt_already_used(task):
            continue
        project_id = str(task.get("project_id") or "").strip()
        if not project_id:
            continue
        if _complete_task_from_existing_upload(
            task,
            project_id,
            task.get("config") if isinstance(task.get("config"), dict) else None,
            log_prefix="업로드 대기 복구 중 기존 YouTube URL 확인",
        ):
            changed = True
            continue
        if status == "failed" and "유튜브 본편 업로드 URL 미확인" not in str(task.get("error") or ""):
            continue
        _mark_task_upload_pending(task, project_id)
        task["youtube_upload_attempt_count"] = 0
        task["youtube_upload_error"] = None
        task["youtube_upload_failed_at"] = None
        _add_log(task, "↻ 미시도 업로드 대기 상태 복구", "warn")
        changed = True
    return changed


async def manual_youtube_upload(task_id: str, *, automatic: bool = False, force_retry: bool = False) -> dict:
    """완성작을 YouTube 에 1회만 업로드."""
    _ensure_state_loaded()
    task = _TASKS.get(task_id)
    if not task:
        raise KeyError("task not found")

    project_id = task["project_id"]
    project = _load_project(project_id)
    if not project:
        raise RuntimeError("프로젝트를 찾을 수 없습니다")

    config = dict(project.config or {})
    if _complete_task_from_existing_upload(
        task,
        project_id,
        config,
        log_prefix="수동 업로드 처리 중 기존 YouTube URL 확인",
    ):
        _save_tasks_to_disk()
        return {
            "ok": True,
            "status": "completed",
            "youtube_url": task.get("youtube_url"),
        }

    if _upload_attempt_already_used(task) and not force_retry:
        if _upload_attempt_count(task) <= 0:
            task["youtube_upload_attempt_count"] = 1
        if str(task.get("status") or "") != "upload_failed":
            _mark_task_upload_failed(
                task,
                project_id,
                "유튜브 업로드는 이미 1회 시도되어 재시도하지 않습니다.",
            )
        _save_tasks_to_disk()
        return {
            "ok": False,
            "status": "upload_failed",
            "message": task.get("error") or "유튜브 업로드는 이미 1회 시도되어 재시도하지 않습니다.",
            "youtube_url": task.get("youtube_url"),
        }

    if _UPLOAD_ACTIVE_TASK_IDS and task_id not in _UPLOAD_ACTIVE_TASK_IDS:
        return {
            "ok": False,
            "status": "upload_pending",
            "message": "다른 업로드가 진행 중입니다.",
            "youtube_url": task.get("youtube_url"),
        }

    if force_retry:
        states = dict(task.get("step_states") or {})
        states["6"] = "completed"
        states["7"] = "pending"
        task["step_states"] = states
        task["status"] = "completed"
        task["error"] = None
        task["youtube_upload_error"] = None
        task["youtube_upload_failed_at"] = None

    mode = "automatic" if automatic else ("manual-retry" if force_retry else "manual")
    _UPLOAD_ACTIVE_TASK_IDS.add(task_id)
    _mark_task_upload_started(task, project_id, mode=mode)
    _add_log(task, "▶ 업로드 대기 1회 업로드 시작" if automatic else "▶ 유튜브 수동 업로드 시작")
    _save_tasks_to_disk()

    try:
        upload_state = await _step_youtube_upload(project_id, config, channel=task.get("channel"), task_id=task_id)
    except Exception as e:
        if _complete_task_from_existing_upload(
            task,
            project_id,
            config,
            log_prefix="업로드 실패 응답 후 기존 본편 URL 확인",
        ):
            _save_tasks_to_disk()
            _UPLOAD_ACTIVE_TASK_IDS.discard(task_id)
            return {
                "ok": True,
                "status": "completed",
                "youtube_url": task.get("youtube_url"),
            }
        prefix = "유튜브 업로드 제한" if _is_youtube_upload_quota_error(e) else "유튜브 업로드 실패"
        message = f"{prefix}: {type(e).__name__}: {e}"
        _mark_task_upload_failed(task, project_id, message)
        _add_log(task, f"✗ {message}", "error")
        _save_tasks_to_disk()
        _UPLOAD_ACTIVE_TASK_IDS.discard(task_id)
        return {
            "ok": False,
            "status": "upload_failed",
            "message": message,
            "youtube_url": task.get("youtube_url"),
        }

    states = dict(task.get("step_states") or {})
    states["7"] = "completed"
    task["step_states"] = states
    if isinstance(upload_state, dict):
        main_video = next(
            (
                v for v in (upload_state.get("videos") or [])
                if isinstance(v, dict)
                and str(v.get("kind") or "") == "main"
                and str(v.get("url") or "").strip()
            ),
            None,
        )
        if main_video:
            task["youtube_url"] = str(main_video.get("url") or "").strip()
    _mark_task_completed(task, states)
    task["youtube_upload_completed_at"] = task.get("finished_at") or _utcnow_iso()
    _mark_project_upload_completed(project_id, states)
    _add_log(task, "✓ 유튜브 업로드 응답 완료 — 처리 모니터링 없이 완료 처리")
    _save_tasks_to_disk()

    project = _load_project(project_id)
    _UPLOAD_ACTIVE_TASK_IDS.discard(task_id)
    return {
        "ok": True,
        "status": "completed",
        "youtube_url": project.youtube_url if project else None,
    }


def _recover_stale_uploading_tasks() -> bool:
    changed = False
    for task in list(_TASKS.values()):
        task_id = str(task.get("task_id") or "").strip()
        if task_id in _UPLOAD_ACTIVE_TASK_IDS:
            continue
        if str(task.get("status") or "").strip().lower() != "uploading":
            continue
        project_id = str(task.get("project_id") or "").strip()
        if not project_id:
            continue
        _mark_task_upload_failed(
            task,
            project_id,
            "유튜브 업로드 1회 시도 중 서버가 중단되어 재시도하지 않습니다.",
        )
        _add_log(task, "✗ 업로드 1회 시도 중단 감지 — 재시도 없이 실패 처리", "error")
        changed = True
    return changed


def _pick_next_upload_pending_task_id() -> Optional[str]:
    candidates: list[tuple[str, str]] = []
    for task_id, task in _TASKS.items():
        status = str(task.get("status") or "").strip().lower()
        if status != "upload_pending":
            continue
        states = dict(task.get("step_states") or {})
        if states.get("6") != "completed" or states.get("7") != "pending":
            continue
        if _upload_attempt_already_used(task):
            continue
        ts = (
            str(task.get("upload_pending_at") or "")
            or str(task.get("finished_at") or "")
            or str(task.get("created_at") or "")
        )
        candidates.append((ts, task_id))
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1] if candidates else None


async def _upload_pending_worker_once() -> None:
    _ensure_state_loaded()
    changed = _recover_stale_uploading_tasks()
    if _restore_unattempted_upload_pending_tasks():
        changed = True
    task_id = _pick_next_upload_pending_task_id()
    if changed:
        _save_tasks_to_disk()
    if not task_id:
        return
    try:
        await manual_youtube_upload(task_id, automatic=True)
    except Exception as exc:
        task = _TASKS.get(task_id)
        project_id = str((task or {}).get("project_id") or "").strip()
        if task and project_id:
            _mark_task_upload_failed(
                task,
                project_id,
                f"유튜브 업로드 실패: {type(exc).__name__}: {exc}",
            )
            _add_log(task, f"✗ 유튜브 업로드 실패: {type(exc).__name__}: {exc}", "error")
            _save_tasks_to_disk()


def _schedule_upload_pending_worker() -> bool:
    global _UPLOAD_PENDING_RUN
    if _emergency_stop_active():
        return False
    if _UPLOAD_ACTIVE_TASK_IDS:
        return False
    if _UPLOAD_PENDING_RUN is not None and not _UPLOAD_PENDING_RUN.done():
        return False
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False

    async def _runner() -> None:
        global _UPLOAD_PENDING_RUN
        try:
            await _upload_pending_worker_once()
        finally:
            if _UPLOAD_PENDING_RUN is asyncio.current_task():
                _UPLOAD_PENDING_RUN = None

    _UPLOAD_PENDING_RUN = loop.create_task(_runner())
    return True

def bulk_delete_tasks(task_ids: list[str]) -> dict:
    """여러 태스크 일괄 삭제 + 디스크 정리."""
    deleted = 0
    freed_bytes = 0
    skipped = []
    for tid in task_ids:
        t = _TASKS.get(tid)
        if not t:
            skipped.append({"task_id": tid, "reason": "not found"})
            continue
        status = t.get("status") or ""
        if status in ("running", "queued"):
            skipped.append({"task_id": tid, "reason": f"status={status}"})
            continue
        pid = t.get("project_id")
        # cancel 플래그 + asyncio Task cancel (방어적)
        if pid:
            try:
                from app.tasks.pipeline_tasks import _redis_set
                _redis_set(f"pipeline:cancel:{pid}", "1")
            except Exception:
                pass
        prev = _ACTIVE_RUNS.get(tid)
        if prev is not None and not prev.done():
            try:
                prev.cancel()
            except Exception:
                pass
        _ACTIVE_RUNS.pop(tid, None)
        # 디스크 정리
        try:
            freed_bytes += _cleanup_project_files(pid, t.get("config") if isinstance(t.get("config"), dict) else None)
            _delete_project_db_record(pid)
        except Exception as e:
            print(f"[oneclick.bulk_delete] cleanup fail ({pid}): {e}")
        _TASKS.pop(tid, None)
        deleted += 1
    try:
        _save_tasks_to_disk()
    except Exception:
        pass
    return {
        "ok": True,
        "deleted": deleted,
        "freed_bytes": freed_bytes,
        "freed_mb": round(freed_bytes / (1024 * 1024), 1),
        "skipped": skipped,
    }


def get_library_stats() -> dict:
    """완성작 라이브러리 전체 통계.

    - total_completed: status == completed
    - total_failed:    status in (failed, cancelled)
    - uploaded:        youtube_url 있는 프로젝트 수
    - not_uploaded:    완료됐지만 아직 업로드 안 된 수
    - total_disk_bytes / total_disk_mb: 모든 oneclick 프로젝트 디렉토리 합
    """
    _ensure_state_loaded()
    if _sync_completed_projects_into_tasks():
        _save_tasks_to_disk()
    total_completed = 0
    total_failed = 0
    uploaded = 0
    not_uploaded = 0
    total_bytes = 0
    for t in list(_TASKS.values()):
        status = t.get("status") or ""
        if status == "completed":
            total_completed += 1
            pid = t.get("project_id")
            # 업로드 여부 판단
            has_url = False
            try:
                proj = _load_project(pid) if pid else None
                if _project_has_uploaded_video(proj):
                    has_url = True
            except Exception:
                pass
            if has_url:
                uploaded += 1
            else:
                not_uploaded += 1
            # 디스크 용량
            try:
                if pid:
                    proj = _load_project(pid)
                    d = resolve_project_dir(pid, proj.config if proj else t.get("config"), create=False)
                    if d.exists():
                        total_bytes += _dir_size(d)
            except Exception:
                pass
        elif status in ("failed", "cancelled"):
            total_failed += 1
    return {
        "total_completed": total_completed,
        "total_failed": total_failed,
        "uploaded": uploaded,
        "not_uploaded": not_uploaded,
        "total_disk_bytes": total_bytes,
        "total_disk_mb": round(total_bytes / (1024 * 1024), 1),
    }


# --------------------------------------------------------------------------- #
# v1.1.43 — 주제 큐 + 매일 HH:MM 스케줄러 (4채널 독립)
# --------------------------------------------------------------------------- #
# 1. 30 초 간격으로 `_queue_loop` 가 돈다.
# 2. 각 채널(1~4) 독립적으로 점검:
#    - channel_times[ch] 가 비어있으면 건너뜀
#    - 해당 채널의 items 가 없으면 건너뜀
#    - 오늘 HH:MM 시각을 지났고 last_run_dates[ch] 가 오늘이 아니면
#      해당 채널의 큐 맨 앞 1 건을 pop 해서 즉시 prepare + start.
# 3. 채널별로 last_run_dates[ch] 를 갱신해 같은 날 재발화 방지.

CHANNELS = [1, 2, 3, 4]

_QUEUE_FILE = SYSTEM_DIR / "oneclick_queue.json"

_QUEUE_DEFAULT: dict[str, Any] = {
    "channel_times": {"1": None, "2": None, "3": None, "4": None},
    "last_run_dates": {"1": None, "2": None, "3": None, "4": None},
    # v1.2.14: 채널별 기본 프리셋 — 아이템의 template_project_id 가 비면
    # 이 값으로 대체. None 이면 프리셋 없이 실행 (prepare_task 가 빈 템플릿 처리).
    "channel_presets": {"1": None, "2": None, "3": None, "4": None},
    "items": [],
}

# 프로세스 내 캐시. 파일을 정답으로 두고, 이 dict 는 읽기 가속용.
_QUEUE: dict[str, Any] = {
    "channel_times": {"1": None, "2": None, "3": None, "4": None},
    "last_run_dates": {"1": None, "2": None, "3": None, "4": None},
    "channel_presets": {"1": None, "2": None, "3": None, "4": None},
    "items": [],
}

# 스케줄러 asyncio.Task 핸들
_queue_task: Optional[asyncio.Task] = None

# 파일 I/O 직렬화용 락
_queue_io_lock = asyncio.Lock()

def _sort_queue_items_for_execution(
    items: list[dict[str, Any]],
    state: dict[str, Any],
    *,
    now: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    return sort_queue_items_for_execution(items, state, channels=CHANNELS, now=now)


def _sort_queue_state_in_place(state: dict[str, Any]) -> None:
    items = state.get("items")
    if not isinstance(items, list) or not items:
        return
    state["items"] = _sort_queue_items_for_execution(items, state)


def _queue_item_work_key(item: dict[str, Any]) -> Optional[tuple[int, int, str]]:
    """Return the logical episode key used to prevent duplicate queue rows."""
    try:
        ch = int(item.get("channel") or 1)
    except Exception:
        ch = 1
    try:
        ep = int(item.get("episode_number") or 0)
    except Exception:
        ep = 0
    episode_code = _normalize_episode_code(item.get("episode_code") or item.get("episode_id"))
    topic = re.sub(r"\s+", " ", str(item.get("topic") or "").strip().lower())
    identity = f"code:{episode_code}" if episode_code else f"topic:{topic}"
    if ep <= 0 or identity in ("code:", "topic:"):
        return None
    return (ch, ep, identity)


def _normalize_episode_code(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip()).casefold()


def _queue_item_keep_rank(item: dict[str, Any], index: int) -> tuple[int, int, int]:
    status = _normalized_queue_status(item.get("status"))
    status_rank = {
        "running": 100,
        "pending": 90,
        "paused": 40,
        "failed": 30,
        "cancelled": 20,
        "completed": 10,
    }.get(status, 0)
    has_task = 1 if str(item.get("task_id") or "").strip() else 0
    # For equal rows, keep the one already appearing earlier in the queue.
    return (status_rank, -has_task, -index)


def _dedupe_queue_state_in_place(state: dict[str, Any]) -> bool:
    items = state.get("items")
    if not isinstance(items, list) or len(items) < 2:
        return False
    keep_by_key: dict[tuple[int, int, str], tuple[int, tuple[int, int, int]]] = {}
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        key = _queue_item_work_key(item)
        if key is None:
            continue
        rank = _queue_item_keep_rank(item, idx)
        prev = keep_by_key.get(key)
        if prev is None or rank > prev[1]:
            keep_by_key[key] = (idx, rank)

    keep_indexes = {
        idx
        for idx, _rank in keep_by_key.values()
    }
    seen_keys: set[tuple[int, int, str]] = set()
    next_items: list[dict[str, Any]] = []
    changed = False
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            changed = True
            continue
        key = _queue_item_work_key(item)
        if key is None:
            next_items.append(item)
            continue
        if idx in keep_indexes and key not in seen_keys:
            next_items.append(item)
            seen_keys.add(key)
        else:
            changed = True
    if changed:
        state["items"] = next_items
        print(f"[oneclick.queue] removed duplicate queue rows: {len(items) - len(next_items)}")
    return changed


def _queue_item_identity_values(item: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for key in ("id", "task_id", "project_id", "result_dir"):
        value = str((item or {}).get(key) or "").strip()
        if value:
            values.add(f"{key}:{value}")
    work_key = _queue_item_work_key(item or {})
    if work_key is not None:
        values.add(f"work:{work_key[0]}:{work_key[1]}:{work_key[2]}")
    else:
        try:
            ch = int((item or {}).get("channel") or 1)
        except Exception:
            ch = 1
        topic = re.sub(r"\s+", " ", str((item or {}).get("topic") or "").strip().lower())
        preset = str((item or {}).get("template_project_id") or (item or {}).get("source_project_id") or "").strip()
        if topic:
            values.add(f"work-noep:{ch}:{preset}:{topic}")
    return values


def _queue_item_matches_identity(item: dict[str, Any], identities: set[str]) -> bool:
    return bool(_queue_item_identity_values(item) & identities)


def _queue_items_snapshot(items: Any) -> str:
    try:
        return json.dumps(items or [], ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        return repr(items)


def _normalize_queue_runtime_state(*, save: bool = True) -> bool:
    """Apply the live queue rules before scheduling or returning queue state."""
    if "_QUEUE" not in globals():
        return False
    before = _queue_items_snapshot((_QUEUE or {}).get("items") or [])
    changed = _sync_queue_items_from_tasks_for_save(save=save)
    _dedupe_queue_state_in_place(_QUEUE)
    after = _queue_items_snapshot((_QUEUE or {}).get("items") or [])
    if before != after:
        changed = True
    if changed and save:
        _save_queue_to_disk()
    return changed


def _queue_normalize(raw: Any) -> dict[str, Any]:
    """디스크/프론트 입력이 불완전해도 안전한 dict 로 강제.

    v1.1.57: 레거시 daily_time/last_run_date → channel_times/last_run_dates 마이그레이션.
    v1.2.9 : 큐 아이템에 에피소드 상세 필드 (openings/endings/core_content) 보존.
    v1.2.10: episode_number / next_episode_preview 보존.
    v1.2.14: channel_presets 필드 보존.
    """
    normalized = normalize_queue_state(
        raw,
        channels=CHANNELS,
        main_target_duration=ONECLICK_MAIN_TARGET_DURATION,
        main_cut_count=ONECLICK_MAIN_CUT_COUNT,
        load_project=_load_project,
    )
    _dedupe_queue_state_in_place(normalized)
    return normalized


def _load_queue_from_disk() -> None:
    global _QUEUE
    try:
        if _QUEUE_FILE.exists():
            raw = json.loads(_QUEUE_FILE.read_text(encoding="utf-8"))
            _QUEUE = _queue_normalize(raw)
            return
    except Exception as e:
        print(f"[oneclick.queue] load failed, falling back to default: {e}")
    _QUEUE = _queue_normalize(dict(_QUEUE_DEFAULT))


def _ensure_state_loaded() -> None:
    """딸깍 큐/태스크 영속 파일을 1회 로드한다."""
    global _STATE_LOADED
    if _STATE_LOADED:
        return
    _load_tasks_from_disk()
    _load_queue_from_disk()
    _reconcile_tasks_from_project_state()
    _STATE_LOADED = True


def _save_queue_to_disk() -> None:
    try:
        _dedupe_queue_state_in_place(_QUEUE)
        _QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _QUEUE_FILE.write_text(
            json.dumps(_QUEUE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"[oneclick.queue] save failed: {e}")


def _resolve_item_preset(item: dict) -> Optional[str]:
    """Return the Studio project linked to the item's channel.

    V3 작업대는 큐 아이템별 template_project_id 로 실행 원본을 바꾸지 않는다.
    채널 편집에 연결된 Studio 프로젝트가 실행 원본이다.
    """
    ch = item.get("channel") or 1
    try:
        ch = int(ch)
    except Exception:
        ch = 1
    if ch < 1 or ch > 4:
        ch = 1
    cp = (_QUEUE.get("channel_presets") or {}).get(str(ch))
    if cp:
        return str(cp)
    tpl = item.get("template_project_id")
    if tpl:
        return str(tpl)
    return None


def get_queue() -> dict[str, Any]:
    """현재 큐 상태 반환 (UI 조회용). 복사본을 돌려준다."""
    _ensure_state_loaded()
    _normalize_queue_runtime_state()
    return {
        "channel_times": dict(_QUEUE.get("channel_times") or {}),
        "last_run_dates": dict(_QUEUE.get("last_run_dates") or {}),
        "channel_presets": dict(_QUEUE.get("channel_presets") or {}),
        "items": list(_QUEUE.get("items") or []),
    }


def set_queue(new_state: dict[str, Any]) -> dict[str, Any]:
    """큐 전체를 교체. 프론트의 '저장' 버튼이 이 한 건만 호출한다."""
    global _QUEUE
    _ensure_state_loaded()
    _normalize_queue_runtime_state(save=False)
    locked_items = [
        dict(item or {})
        for item in (_QUEUE.get("items") or [])
        if _is_active_queue_status((item or {}).get("status"))
    ]
    locked_identities: set[str] = set()
    for item in locked_items:
        locked_identities.update(_queue_item_identity_values(item))

    normalized = _queue_normalize(new_state)
    if locked_items:
        incoming_items = [
            dict(item or {})
            for item in (normalized.get("items") or [])
            if not _queue_item_matches_identity(dict(item or {}), locked_identities)
        ]
        normalized["items"] = locked_items + incoming_items
        _dedupe_queue_state_in_place(normalized)
    # last_run_dates 는 사용자가 바꿀 값이 아니므로 기존 값 유지.
    if not isinstance(new_state.get("last_run_dates"), dict):
        normalized["last_run_dates"] = dict(_QUEUE.get("last_run_dates") or {})
    _QUEUE = normalized
    _save_queue_to_disk()
    _sync_windows_wake_timers(reason="queue-save")
    return get_queue()


def recover_existing_for_queue_item(item_id: str) -> dict[str, Any]:
    """큐 항목에 대응하는 기존 산출물이 있으면 태스크로 복구하고 큐에 연결한다."""
    global _QUEUE
    _ensure_state_loaded()
    item_id = str(item_id or "").strip()
    if not item_id:
        return {"ok": True, "task": None, "queue": get_queue()}

    with _QUEUE_RECOVER_LOCK:
        items = list(_QUEUE.get("items") or [])
        idx = next((i for i, item in enumerate(items) if str(item.get("id") or "") == item_id), -1)
        if idx < 0:
            return {"ok": True, "task": None, "queue": get_queue()}

        item = dict(items[idx] or {})
        project_id = _find_existing_project_for_queue_item(item, allow_implicit=False)
        if not project_id:
            return {"ok": True, "task": None, "queue": get_queue()}

        try:
            pdir = resolve_project_dir(project_id, create=False)
            if not pdir.exists():
                _restore_backup_for_queue_item(project_id, item)
        except Exception:
            _restore_backup_for_queue_item(project_id, item)

        task = recover_project(project_id)
        try:
            ch = int(item.get("channel") or 0)
            if 1 <= ch <= 4:
                task["channel"] = ch
        except (TypeError, ValueError):
            pass
        try:
            ep = int(item.get("episode_number") or 0)
            if ep > 0:
                task["episode_number"] = ep
        except (TypeError, ValueError):
            pass
        _add_log(task, f"작업대 큐에서 기존 자료 불러오기: {project_id}", "info")
        _reconcile_task_outputs(task, clear_terminal_cursor=True)
        task["progress_pct"] = _compute_progress_pct(task)

        linked_item = dict(items[idx] or {})
        linked_item["status"] = "running" if _task_has_live_runner(str(task.get("task_id") or ""), task) else "pending"
        linked_item["task_id"] = str(task.get("task_id") or "")
        linked_item["project_id"] = str(task.get("project_id") or "")
        linked_item["source_project_id"] = str(task.get("source_project_id") or task.get("template_project_id") or item.get("template_project_id") or "")
        linked_item["result_dir"] = str(task.get("result_dir") or "")
        linked_item["title"] = str(task.get("title") or "")
        if task.get("started_at"):
            linked_item["started_at"] = str(task.get("started_at") or "")
        linked_item["queued_note"] = "작업대 연결됨"
        items[idx] = linked_item
        _QUEUE["items"] = items
        _save_queue_to_disk()
        _save_tasks_to_disk()
        return {"ok": True, "task": task, "queue": get_queue()}


def _sync_windows_wake_timers(reason: str) -> dict[str, Any] | None:
    """Best-effort Windows wake timer sync for channel_times."""
    try:
        from app.services.wake_timer_service import sync_wake_timers

        result = sync_wake_timers(dict(_QUEUE.get("channel_times") or {}))
        if result.get("supported"):
            status = "ok" if result.get("ok") else "partial"
            print(f"[oneclick.wake] sync {status} ({reason}): {result.get('plan')}")
        return result
    except Exception as e:
        print(f"[oneclick.wake] sync failed ({reason}): {type(e).__name__}: {e}")
        return None


def sync_wake_timers_now() -> dict[str, Any] | None:
    """Public helper for API/manual sync."""
    _ensure_state_loaded()
    return _sync_windows_wake_timers(reason="manual")


def _today_iso() -> str:
    return datetime.now().date().isoformat()


def _should_fire_channel(now: datetime, ch: int) -> bool:
    """채널 ch 의 스케줄이 발화해야 하는지 판단."""
    ch_key = str(ch)
    ct = (_QUEUE.get("channel_times") or {}).get(ch_key)
    if not ct:
        return False
    try:
        hh, mm = ct.split(":")
        target_h = int(hh)
        target_m = int(mm)
    except Exception:
        return False
    today = now.date().isoformat()
    lrd = (_QUEUE.get("last_run_dates") or {}).get(ch_key)
    if lrd == today:
        return False
    return (now.hour, now.minute) >= (target_h, target_m)


def _queue_channel_schedule_minute(ch: int) -> int:
    ct = (_QUEUE.get("channel_times") or {}).get(str(ch))
    try:
        hh, mm = str(ct or "").split(":")
        return (int(hh) * 60) + int(mm)
    except Exception:
        return 24 * 60


def _scheduled_queue_channel_to_fire(now: datetime) -> int | None:
    """Return the due channel whose first pending queue row should run now."""
    candidates: list[tuple[int, int, int]] = []
    seen_channels: set[int] = set()
    for index, item in enumerate(list(_QUEUE.get("items") or [])):
        if not isinstance(item, dict):
            continue
        if _normalized_queue_status(item.get("status")) != "pending":
            continue
        if _is_immediate_queue_item(item):
            continue
        ch = _queue_item_channel(item)
        if ch in seen_channels:
            continue
        seen_channels.add(ch)
        if not _should_fire_channel(now, ch):
            continue
        candidates.append((_queue_channel_schedule_minute(ch), index, ch))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][2]


def _queue_item_channel(item: dict[str, Any] | None) -> int:
    return _helper_queue_item_channel(item, CHANNELS)


def _queue_running_task_for_channel(ch: int) -> dict[str, Any] | None:
    for item in list(_QUEUE.get("items") or []):
        if _queue_item_channel(item) != ch:
            continue
        if str(item.get("status") or "").lower() != "running":
            continue
        tid = str(item.get("task_id") or "").strip()
        if tid and tid in _TASKS and _task_has_live_runner(tid, _TASKS[tid]):
            return _TASKS[tid]
    return None


def _normalize_queue_work_topic(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def _task_project_metadata_config(task: dict[str, Any]) -> dict[str, Any]:
    cfg = task.get("config") if isinstance(task.get("config"), dict) else {}
    if cfg:
        return dict(cfg)
    project_id = str(task.get("project_id") or "").strip()
    if not project_id:
        return {}
    try:
        project = _load_project(project_id)
        return dict(project.config or {}) if project and isinstance(project.config, dict) else {}
    except Exception:
        return {}


def _task_episode_code(task: dict[str, Any]) -> str:
    cfg = _task_project_metadata_config(task)
    return _normalize_episode_code(
        task.get("episode_code")
        or task.get("episode_id")
        or cfg.get("episode_code")
        or cfg.get("episode_id")
    )


def _task_matches_queue_item(task: dict[str, Any], item: dict[str, Any], preset_id: str | None) -> bool:
    if not task or not item:
        return False
    if _normalize_queue_work_topic(task.get("topic") or task.get("title")) != _normalize_queue_work_topic(item.get("topic")):
        return False
    try:
        if int(task.get("channel") or 1) != _queue_item_channel(item):
            return False
    except Exception:
        return False
    item_ep = coerce_episode_number(item.get("episode_number"))
    if item_ep is not None and coerce_episode_number(task.get("episode_number")) != item_ep:
        return False
    item_episode_code = _normalize_episode_code(item.get("episode_code") or item.get("episode_id"))
    task_episode_code = _task_episode_code(task)
    if item_episode_code or task_episode_code:
        if item_episode_code != task_episode_code:
            return False
    if preset_id:
        task_preset = str(task.get("source_project_id") or task.get("template_project_id") or "").strip()
        if task_preset and task_preset != str(preset_id).strip():
            return False
    return True


def _task_has_uploaded_result(task: dict[str, Any]) -> bool:
    pid = str(task.get("project_id") or "").strip()
    if not pid:
        return False
    try:
        project = _load_project(pid)
        return _project_upload_step_complete(project, dict((project.config if project else None) or {}))
    except Exception:
        return False


def _task_has_rendered_upload_work(task: dict[str, Any]) -> bool:
    states = dict((task or {}).get("step_states") or {})
    return states.get("6") == "completed" and states.get("7") != "completed"


def _find_existing_task_for_queue_item(
    item: dict[str, Any],
    preset_id: str | None,
) -> tuple[str, dict[str, Any]] | None:
    active: list[dict[str, Any]] = []
    completed: list[dict[str, Any]] = []
    for task in _TASKS.values():
        if not _task_matches_queue_item(task, item, preset_id):
            continue
        status = str(task.get("status") or "").strip().lower()
        if status in ("running", "queued", "prepared"):
            active.append(task)
        elif status == "completed" and _task_has_uploaded_result(task):
            completed.append(task)
        elif status in ("completed", "upload_pending", "uploading", "upload_failed", "failed") and _task_has_rendered_upload_work(task):
            completed.append(task)
    if active:
        active.sort(key=lambda task: str(task.get("started_at") or task.get("created_at") or ""), reverse=True)
        return "active", active[0]
    if completed:
        completed.sort(key=lambda task: str(task.get("finished_at") or task.get("started_at") or ""), reverse=True)
        return "completed", completed[0]
    return None


def _mark_queue_item_running(index: int, task: dict[str, Any], source_project_id: str | None = None) -> None:
    items = list(_QUEUE.get("items") or [])
    if index < 0 or index >= len(items):
        return
    item = dict(items[index] or {})
    item["status"] = "running"
    item["task_id"] = str(task.get("task_id") or "")
    item["project_id"] = str(task.get("project_id") or "")
    item["source_project_id"] = str(source_project_id or task.get("source_project_id") or task.get("template_project_id") or "")
    item["result_dir"] = str(task.get("result_dir") or "")
    item["title"] = str(task.get("title") or "")
    item["started_at"] = str(task.get("started_at") or _utcnow_iso())
    item.pop("finished_at", None)
    item["queued_note"] = "실행 중"
    items[index] = item
    _QUEUE["items"] = items
    _save_queue_to_disk()


def _mark_queue_item_completed(index: int, task: dict[str, Any], source_project_id: str | None = None) -> None:
    items = list(_QUEUE.get("items") or [])
    if index < 0 or index >= len(items):
        return
    item = dict(items[index] or {})
    item["status"] = "completed"
    item["task_id"] = str(task.get("task_id") or "")
    item["project_id"] = str(task.get("project_id") or "")
    item["source_project_id"] = str(source_project_id or task.get("source_project_id") or task.get("template_project_id") or "")
    item["result_dir"] = str(task.get("result_dir") or "")
    item["title"] = str(task.get("title") or "")
    item["finished_at"] = str(task.get("finished_at") or _utcnow_iso())
    item["queued_note"] = "이미 완료됨"
    items[index] = item
    _QUEUE["items"] = items
    _save_queue_to_disk()


async def _fire_queue_for_channel(ch: int, triggered_by: str = "schedule") -> dict[str, Any] | None:
    """채널 ch 의 큐 맨 앞 1 건을 뽑아 즉시 실행.

    해당 채널에 items 가 없으면 아무것도 안 함.
    성공/실패 상관없이 pop-on-start.
    """
    if triggered_by != "manual":
        if _emergency_stop_active():
            print(f"[oneclick.queue] defer ch{ch}: emergency stop guard active")
            return None
        if _auto_production_paused():
            print(f"[oneclick.queue] defer ch{ch}: auto production paused")
            return None

    _normalize_queue_runtime_state()
    existing_running = _queue_running_task_for_channel(ch)
    if existing_running is not None:
        return existing_running

    if _has_inflight_task():
        print(f"[oneclick.queue] defer ch{ch}: 다른 작업이 이미 running/queued 상태")
        return None

    items = list(_QUEUE.get("items") or [])
    target_idx = None
    for i, it in enumerate(items):
        item_status = _normalized_queue_status(it.get("status"))
        if item_status != "pending":
            continue
        if (it.get("channel") or 1) == ch:
            target_idx = i
            break
    if target_idx is None:
        return None

    head = dict(items[target_idx] or {})

    preset_id = _resolve_item_preset(head)
    existing = _find_existing_task_for_queue_item(head, preset_id)
    if existing:
        existing_state, existing_task = existing
        if existing_state == "active":
            _mark_queue_item_running(target_idx, existing_task, preset_id)
            print(
                f"[oneclick.queue] skip duplicate ch{ch}: existing task "
                f"{existing_task.get('task_id')} status={existing_task.get('status')}"
            )
            return existing_task
        _mark_queue_item_completed(target_idx, existing_task, preset_id)
        print(
            f"[oneclick.queue] skip completed duplicate ch{ch}: existing task "
            f"{existing_task.get('task_id')}"
        )
        return existing_task

    existing_project_id = _find_existing_project_for_queue_item(head)
    if existing_project_id:
        try:
            task = recover_project(existing_project_id)
            try:
                ep = int(head.get("episode_number") or 0)
                if ep > 0:
                    task["episode_number"] = ep
            except (TypeError, ValueError):
                pass
            task["triggered_by"] = "schedule" if triggered_by == "schedule" else "manual"
            task["channel"] = ch
            if preset_id:
                task["source_project_id"] = preset_id
                task["template_project_id"] = preset_id
            _add_log(task, f"작업대 큐 기존 에피소드 산출물 재사용: {existing_project_id}", "info")
            _reconcile_task_outputs(task, clear_terminal_cursor=True)
            task["progress_pct"] = _compute_progress_pct(task)
            if str(task.get("status") or "").lower() == "completed":
                _mark_queue_item_completed(target_idx, task, preset_id)
                _save_tasks_to_disk()
                return task
            _mark_queue_item_running(target_idx, task, preset_id)
            _save_tasks_to_disk()
            start_task(task["task_id"])
            return task
        except Exception as e:
            print(f"[oneclick.queue] recover existing ch{ch} failed, queue item retained: {e}")
            return None

    print(
        f"[oneclick.queue] firing ch{ch} item: topic={head.get('topic')!r} "
        f"template={preset_id} cuts={ONECLICK_MAIN_CUT_COUNT}"
    )

    # v1.2.28: fire 실패 시 큐 아이템 손실 방지.
    # 기존: pop → prepare_task/start_task 예외 → print 만 찍고 아이템 증발.
    # 사용자 보고: "EP.1 복구해서 실행했는데 실패 떴더니 EP.1 이 어디갔냐?"
    # 수정: prepare_task 가 실패하면 head 를 큐 같은 자리에 되돌려 넣고
    #      ch 의 맨 앞에 재배치한다. start_task 가 실패하면 이미 _TASKS
    #      에 task 가 만들어져 있으니 status=failed 로 마킹해 실패/취소에
    #      보이도록 남긴다 (이미 _handle_fail 경로지만, start_task 자체가
    #      asyncio Task 등록 전에 raise 하는 경로는 놓칠 수 있어 방어).
    task = None
    try:
        task = prepare_task(
            template_project_id=preset_id,
            topic=head["topic"],
            title=None,
            target_duration=ONECLICK_MAIN_TARGET_DURATION,
            episode_openings=head.get("openings"),
            episode_endings=head.get("endings"),
            episode_core_content=head.get("core_content"),
            episode_number=head.get("episode_number"),
            series=head.get("series"),
            episode_code=head.get("episode_code") or head.get("episode_id"),
            next_episode_preview=head.get("next_episode_preview"),
            channel=ch,
        )
        task["triggered_by"] = "schedule" if triggered_by == "schedule" else "manual"
        task["channel"] = ch
        _mark_queue_item_running(target_idx, task, preset_id)
    except Exception as e:
        print(f"[oneclick.queue] prepare ch{ch} failed, queue item retained: {e}")
        return None

    try:
        start_task(task["task_id"])
    except Exception as e:
        print(f"[oneclick.queue] start ch{ch} task={task.get('task_id')} failed: {e}")
        task["status"] = "failed"
        task["error"] = f"start_task 실패: {type(e).__name__}: {e}"
        task["finished_at"] = _utcnow_iso()
        try:
            _save_tasks_to_disk()
        except Exception:
            pass
        return None

    return task


async def _queue_loop() -> None:
    """30 초 간격으로 채널별 큐 스케줄을 점검."""
    print("[oneclick.queue] scheduler loop started (4-channel mode)")
    try:
        while True:
            try:
                now = datetime.now()
                today = _today_iso()
                _normalize_queue_runtime_state()
                _schedule_upload_pending_worker()
                items = list(_QUEUE.get("items") or [])
                if _auto_production_paused():
                    await asyncio.sleep(min(30, max(1, _auto_production_pause_remaining())))
                    continue
                if items:
                    if _auto_next_delay_active():
                        await asyncio.sleep(min(5, max(1, _auto_next_delay_remaining())))
                        continue
                    if not _has_inflight_task():
                        head = items[0]
                        ch = _queue_item_channel(head)
                        if _is_immediate_queue_item(head):
                            await _fire_queue_for_channel(ch, "manual")
                        else:
                            due_ch = _scheduled_queue_channel_to_fire(now)
                            fired = await _fire_queue_for_channel(due_ch) if due_ch is not None else None
                            if fired:
                                if "last_run_dates" not in _QUEUE:
                                    _QUEUE["last_run_dates"] = {}
                                _QUEUE["last_run_dates"][str(due_ch)] = today
                                _save_queue_to_disk()
                    await asyncio.sleep(30)
                    continue
                for ch in CHANNELS:
                    if _should_fire_channel(now, ch):
                        ch_items = [
                            it for it in (_QUEUE.get("items") or [])
                            if (it.get("channel") or 1) == ch
                        ]
                        if not ch_items:
                            # 해당 채널 아이템이 모두 소진된 상태 — 스케줄만 기록하고 지나감.
                            continue
                        # v1.2.26 복구: 채널 큐 맨 앞 1건 즉시 실행.
                        fired = await _fire_queue_for_channel(ch)
                        if fired:
                            if "last_run_dates" not in _QUEUE:
                                _QUEUE["last_run_dates"] = {}
                            _QUEUE["last_run_dates"][str(ch)] = today
                            _save_queue_to_disk()
            except asyncio.CancelledError:
                raise
            except Exception as _loop_err:
                # 한 iteration 의 에러가 전체 루프를 죽이지 않도록 흡수.
                print(f"[oneclick.queue] loop iteration error: {_loop_err}")
            # 30초 간격으로 체크. sleep 도 취소 가능 지점이다.
            await asyncio.sleep(30)
    except asyncio.CancelledError:
        print("[oneclick.queue] scheduler loop cancelled")


# 모듈 전역 — asyncio Task 핸들.
_QUEUE_TASK: Optional[asyncio.Task] = None
_QUEUE_SCHEDULER_LOCK_HANDLE = None


def _acquire_queue_scheduler_lock() -> bool:
    """Only one backend process may run the oneclick queue scheduler."""
    global _QUEUE_SCHEDULER_LOCK_HANDLE
    if _QUEUE_SCHEDULER_LOCK_HANDLE is not None:
        return True
    try:
        SYSTEM_DIR.mkdir(parents=True, exist_ok=True)
        handle = open(SYSTEM_DIR / "oneclick_scheduler.lock", "a+b")
        if os.name == "nt":
            try:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                handle.close()
                return False
        _QUEUE_SCHEDULER_LOCK_HANDLE = handle
        return True
    except Exception as e:
        print(f"[oneclick.queue] scheduler lock failed: {type(e).__name__}: {e}")
        return False


def start_queue_scheduler() -> bool:
    """v1.1.43: FastAPI lifespan startup 훅에서 호출된다.

    _queue_loop 을 asyncio.Task 로 띄워 백그라운드에서 30 초마다 채널 스케줄
    을 감시한다. 이미 기동돼 있으면 중복 실행하지 않는다.
    """
    global _QUEUE_TASK
    _ensure_state_loaded()
    _sync_windows_wake_timers(reason="startup")
    if _QUEUE_TASK is not None and not _QUEUE_TASK.done():
        return True
    if not _acquire_queue_scheduler_lock():
        print("[oneclick.queue] scheduler skipped: another backend process holds the lock")
        return False
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    _QUEUE_TASK = loop.create_task(_queue_loop())
    _schedule_upload_pending_worker()
    return True


def stop_queue_scheduler() -> None:
    """v1.1.43: FastAPI lifespan shutdown 훅에서 호출."""
    global _QUEUE_TASK, _UPLOAD_PENDING_RUN
    if _QUEUE_TASK is not None:
        try:
            _QUEUE_TASK.cancel()
        except Exception as e:
            print(f"[oneclick.queue] cancel error: {e}")
    if _UPLOAD_PENDING_RUN is not None and not _UPLOAD_PENDING_RUN.done():
        try:
            _UPLOAD_PENDING_RUN.cancel()
        except Exception as e:
            print(f"[oneclick.upload] cancel error: {e}")
    _QUEUE_TASK = None
    _UPLOAD_PENDING_RUN = None

async def run_queue_top_now(channel=None):
    """v1.2.12: 큐 맨 위 1건을 즉시 실행. 큐가 비어 있으면 None 반환.

    async 이벤트 루프가 필요하므로 라우터에서 async 로 호출한다.
    channel 미지정 시 채널 1 로 간주.
    """
    _ensure_state_loaded()
    _clear_emergency_stop_guard()
    _normalize_queue_runtime_state()
    items = list(_QUEUE.get("items") or [])
    if not items:
        return None
    target_ch = _queue_item_channel(items[0])
    if channel is not None:
        try:
            requested_ch = int(channel)
        except (TypeError, ValueError):
            requested_ch = target_ch
        if requested_ch in CHANNELS:
            if not any(_queue_item_channel(it) == requested_ch for it in items):
                return None
            target_ch = requested_ch
    before_ids = set(_TASKS.keys())
    fired_task = await _fire_queue_for_channel(target_ch, "manual")
    if fired_task:
        return fired_task
    # 방금 생성된 task 반환. 즉시 실행(manual)과 스케줄 실행(schedule)을 구분한다.
    for t in reversed(list(_TASKS.values())):
        if t.get("task_id") not in before_ids and t.get("channel") == target_ch:
            return t
    for t in reversed(list(_TASKS.values())):
        if t.get("channel") == target_ch and t.get("status") in ("prepared", "queued", "running"):
            return t
    return None
