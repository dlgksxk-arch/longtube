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
5. **서버 재시작 시 tasks 손실 허용**: oneclick 태스크는 단건 수명이 짧고, 복구
   로직을 넣으면 복잡도가 폭발한다. 재시작 시 in-flight 태스크는 "중단됨"
   으로 간주하고 사용자에게 다시 누르게 한다.

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
- 상태 영속화: `DATA_DIR / oneclick_queue.json`. 프로세스 재시작에도 복원.
- 중복 발화 방지: `last_run_date` (YYYY-MM-DD) 를 저장해 같은 날 두 번
  안 돌게 한다. 서버가 09:00 에 죽었다가 09:30 에 올라와도 오늘 아직 안
  돌았으면 catch-up 으로 즉시 발화.
- 즉시 실행 팝업(v1.1.42) 은 제거. 모달은 이제 큐 편집기 역할만 한다.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
import traceback
import threading
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

from app.config import DATA_DIR, SYSTEM_DIR, resolve_project_dir, get_channel_projects_root
from app.models.database import SessionLocal
from app.models.api_log import ApiLog
from app.models.cut import Cut
from app.models.project import Project
from app.models.scheduled_episode import ScheduledEpisode
from app.services.estimation_service import estimate_project
from app.services.title_utils import coerce_episode_number, with_episode_prefix

# v1.1.52: pipeline_tasks 의 _redis_get 을 사용 — 인메모리 fallback 포함이라
# Redis 없어도 같은 프로세스 내에서 진행률을 정확히 읽는다.
from app.tasks.pipeline_tasks import _redis_get, _redis_delete, run_async


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


def _project_storage_exists(project_id: str, config: Optional[dict] = None) -> bool:
    """현재 저장소 기준으로 프로젝트 폴더가 실제 존재하는지 확인한다."""
    pid = str(project_id or "").strip()
    if not pid:
        return False
    try:
        if resolve_project_dir(pid, config=config, create=False).exists():
            return True
    except Exception:
        pass
    try:
        db = SessionLocal()
        try:
            return db.query(Project.id).filter(Project.id == pid).first() is not None
        finally:
            db.close()
    except Exception:
        return False


def _save_tasks_to_disk() -> None:
    """_TASKS 를 JSON 으로 영속화. running 태스크 중단 감지를 위해 상태 보존."""
    try:
        with _TASKS_SAVE_LOCK:
            _TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
            # 최근 50건만 보존 (오래된 completed 태스크는 버린다)
            recent = dict(list(_TASKS.items())[-50:])
            _TASKS_FILE.write_text(
                json.dumps(recent, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
    except Exception as e:
        print(f"[oneclick] tasks save failed: {e}")


def _load_tasks_from_disk() -> None:
    """서버 시작 시 이전 태스크 복원. running 상태였던 건 interrupted 로 표시."""
    global _TASKS
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
            # running/queued 상태였으면 서버가 중간에 죽은 것 — failed 로 전환
            if task.get("status") in ("running", "queued"):
                task["status"] = "failed"
                task["error"] = "서버 재시작으로 중단됨"
                task["finished_at"] = task.get("finished_at") or _utcnow_iso()
                _reconcile_task_outputs(task, clear_terminal_cursor=True)
            elif task.get("status") in ("failed", "cancelled", "paused", "completed"):
                _reconcile_task_outputs(task, clear_terminal_cursor=True)
            _TASKS[tid] = task
        print(f"[oneclick] restored tasks: {len(_TASKS)}")
        if skipped_missing:
            print(f"[oneclick] dropped missing-storage tasks: {skipped_missing}")
            _save_tasks_to_disk()
        # 고아 프로젝트는 조회 화면 진입만으로 태스크를 되살리지 않는다.
        # 사용자가 복구 버튼/고아 프로젝트 API 를 명시적으로 눌렀을 때만 처리한다.
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
            cfg = proj.config or {}
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
            detected = _detect_completed_steps(proj.id)

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
    if not project or not str(project.youtube_url or "").strip():
        return False
    states = project.step_states or {}
    return states.get("7") == "completed"


def _mark_project_uploaded(db, project: Project) -> bool:
    """업로드 단계가 실제 완료로 기록된 프로젝트만 완료 상태로 맞춘다."""
    if not _project_has_uploaded_video(project):
        return False

    changed = False
    states = dict(project.step_states or {})
    if project.status != "completed":
        project.status = "completed"
        changed = True
    if (project.current_step or 0) < 7:
        project.current_step = 7
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
            if task.get("status") in ("running", "queued", "prepared"):
                continue
            pid = str(task.get("project_id") or "").strip()
            if not pid:
                continue
            project = projects_by_id.get(pid)
            if not _project_has_uploaded_video(project):
                continue

            detected = _detect_completed_steps(pid)
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
_EMERGENCY_STOP_UNTIL = 0.0


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


def _has_running_task(*, exclude_task_id: Optional[str] = None) -> bool:
    """지금 실제 실행 중인 작업이 있는지 확인."""
    if _has_live_runner(exclude_task_id=exclude_task_id):
        return True
    for tid, task in _TASKS.items():
        if exclude_task_id is not None and tid == exclude_task_id:
            continue
        if task.get("status") == "running":
            return True
    return False


def _has_inflight_task(*, exclude_task_id: Optional[str] = None) -> bool:
    """running/queued 태스크가 이미 있으면 새 작업을 끼워 넣지 않는다."""
    if _has_running_task(exclude_task_id=exclude_task_id):
        return True
    for tid, task in _TASKS.items():
        if exclude_task_id is not None and tid == exclude_task_id:
            continue
        if task.get("status") == "queued":
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


def _dispatch_next_queued_task(*, exclude_task_id: Optional[str] = None) -> Optional[str]:
    """현재 실행이 비었을 때 queued 1건만 다음 순서로 시작."""
    if _emergency_stop_active():
        return None
    if _has_running_task(exclude_task_id=exclude_task_id):
        return None
    next_task_id = _pick_next_queued_task_id(exclude_task_id=exclude_task_id)
    if not next_task_id:
        return None
    _schedule_oneclick_run(next_task_id)
    return next_task_id


def _dispatch_next_persisted_queue_item() -> Optional[int]:
    """현재 실행이 비었을 때 저장된 제작 큐의 다음 1건을 시작한다."""
    if _emergency_stop_active():
        return None
    if _has_inflight_task():
        return None
    items = list(_QUEUE.get("items") or [])
    if not items:
        return None
    try:
        ch = int(items[0].get("channel") or 1)
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
ONECLICK_MAIN_CUT_COUNT = 120
ONECLICK_SECONDS_PER_CUT = 5
ONECLICK_MAIN_TARGET_DURATION = ONECLICK_MAIN_CUT_COUNT * ONECLICK_SECONDS_PER_CUT


def _force_oneclick_main_length(config: dict) -> dict:
    """OneClick main videos are fixed by clip count, not a free duration field."""
    config["target_cuts"] = ONECLICK_MAIN_CUT_COUNT
    # Keep this legacy field in sync because older render/subtitle/estimate code reads it.
    config["target_duration"] = ONECLICK_MAIN_TARGET_DURATION
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
    return {
        "task_id": task_id,
        "template_project_id": effective_template_project_id,
        "project_id": project_id,
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
        # 각 항목: {"ts": "HH:MM:SS", "level": "info"|"warn"|"error", "msg": "..."}
        "logs": [],
    }


# --------------------------------------------------------------------------- #
# v2.1.2: 제작 로그 헬퍼
# --------------------------------------------------------------------------- #

def _add_log(task: dict, msg: str, level: str = "info") -> None:
    """task["logs"] 에 한 줄 추가. 최대 200 줄 유지."""
    from datetime import datetime as _dt
    logs = task.setdefault("logs", [])
    logs.append({
        "ts": _dt.now().strftime("%H:%M:%S"),
        "level": level,
        "msg": msg,
    })
    # 너무 길어지면 앞쪽 잘라내기
    if len(logs) > 200:
        task["logs"] = logs[-200:]
    _save_tasks_to_disk()


# --------------------------------------------------------------------------- #
# 공용 DB 헬퍼
# --------------------------------------------------------------------------- #

def _load_project(project_id: str) -> Optional[Project]:
    db = SessionLocal()
    try:
        return db.query(Project).filter(Project.id == project_id).first()
    finally:
        db.close()


def _detect_completed_steps(project_id: str) -> dict[str, str]:
    """v1.1.52: 프로젝트 디렉토리와 DB 를 스캔해서 실제 완료된 스텝을 감지한다.

    실패/중단된 프로젝트를 재사용할 때, 이미 만들어진 생성물이 있으면
    해당 스텝을 "completed" 로 표시해서 _run_sync_pipeline 이 건너뛸 수 있게 한다.

    반환: { "2": "completed", "3": "completed", "4": "pending", ... }
    """
    from app.models.cut import Cut

    project_dir = resolve_project_dir(project_id)
    states: dict[str, str] = {}

    # Step 2 (대본): script.json 존재 + cuts 배열 비어있지 않으면 완료
    script_path = project_dir / "script.json"
    script_ok = False
    total_cuts = 0
    if script_path.exists():
        try:
            script = json.loads(script_path.read_text(encoding="utf-8"))
            cuts = script.get("cuts", [])
            if cuts:
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
        states["7"] = "completed" if (
            proj and proj.youtube_url and proj_states.get("7") == "completed"
        ) else "pending"
    finally:
        db.close()

    return states


def _reconcile_task_outputs(task: dict[str, Any], *, clear_terminal_cursor: bool = False) -> bool:
    """디스크 실물 기준으로 task step 상태를 보정한다.

    서버 재시작이나 강제 종료 뒤에는 step_states/current_step 이 중간 상태로
    남을 수 있다. 이 함수는 실제 생성물 개수를 기준으로 완료된 step 을 다시
    맞추고, 필요하면 이어서 시작할 step 번호를 갱신한다.
    """
    project_id = str(task.get("project_id") or "").strip()
    if not project_id:
        return False

    detected = _detect_completed_steps(project_id)
    step_states = dict(task.get("step_states") or {})
    changed = False

    for step_key, state in detected.items():
        if step_states.get(step_key) != state:
            step_states[step_key] = state
            changed = True

    if task.get("step_states") != step_states:
        task["step_states"] = step_states
        changed = True

    completed_cuts = dict(task.get("completed_cuts_by_step") or {})
    for step_key in ("2", "3", "4", "5"):
        if step_states.get(step_key) != "completed" and completed_cuts.get(step_key):
            completed_cuts[step_key] = 0
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
    elif task.get("resume_from_step") != first_pending:
        task["resume_from_step"] = first_pending
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

    return changed


def _find_reusable_project(
    template_project_id: Optional[str],
    topic: str,
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
                Project.status != "completed",
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
            detected = _detect_completed_steps(proj.id)
            completed_count = sum(1 for v in detected.values() if v == "completed")
            if completed_count > 0:
                return (proj, detected)
        return None
    finally:
        db.close()


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
    # 공백 → 언더스코어
    text = text.strip().replace(" ", "_")
    # 허용 문자만 남김 (한글, 영문, 숫자, 하이픈, 언더스코어)
    text = re.sub(r'[^\w가-힣-]', '', text, flags=re.UNICODE)
    return text[:max_len] or "Untitled"


def _generate_oneclick_project_id(topic: str, db, channel: Optional[int] = None) -> str:
    """v1.1.52: 딸깍_주제_YYMMDD-N 형식의 project_id 를 생성한다.

    v1.2.29: channel 이 주어지면 딸깍_CH{ch}_주제_YYMMDD-N 로 채널 번호를
    prefix 에 박아 생성. 사용자 요구: "앞으로 결과물 생성할 때 파일명에
    채널 번호도 표기 해 — 딸깍_CH1_뭐뭐_날짜_순번 이렇게". 채널이 None 이면
    (미지정 호출 경로) 기존 포맷 유지 — 모든 채널에서 접근 가능한 레거시로 취급.

    같은 날짜/채널에 이미 생성된 딸깍 프로젝트 수를 세서 순번(N)을 매긴다.
    예:
      채널 지정: 딸깍_CH1_AI로봇_260413-1, 딸깍_CH1_AI로봇_260413-2
      채널 미지정 (레거시): 딸깍_AI로봇_260413-1
    """
    safe_topic = _sanitize_for_filename(topic)
    date_str = datetime.now().strftime("%y%m%d")
    if channel is not None:
        try:
            ch_int = int(channel)
            if 1 <= ch_int <= 4:
                prefix = f"딸깍_CH{ch_int}_{safe_topic}_{date_str}"
            else:
                prefix = f"딸깍_{safe_topic}_{date_str}"
        except (TypeError, ValueError):
            prefix = f"딸깍_{safe_topic}_{date_str}"
    else:
        prefix = f"딸깍_{safe_topic}_{date_str}"

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


def _copy_template_assets(tmpl_dir: Path, dest_dir: Path, config: dict):
    """템플릿 프로젝트의 에셋 파일(레퍼런스/캐릭터/로고/간지/BGM)을 새 프로젝트 디렉토리에 복사.

    v1.1.52: config 에 상대 경로로 기록된 에셋 파일이 새 project_id
    디렉토리에도 물리적으로 존재해야 collect_reference_images /
    collect_character_images 가 제대로 동작한다.
    """
    import shutil

    # 1) config 에 기록된 상대 경로 기반 에셋 복사
    for key in ("reference_images", "character_images", "logo_images"):
        for rel in config.get(key, []) or []:
            src = tmpl_dir / rel
            dst = dest_dir / rel
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(str(src), str(dst))
                except Exception as e:
                    print(f"[oneclick] 에셋 복사 실패 {rel}: {e}")

    bgm_rel = str(config.get("bgm_path") or "").strip()
    if bgm_rel:
        src = tmpl_dir / bgm_rel
        dst = dest_dir / bgm_rel
        if src.exists() and src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(str(src), str(dst))
            except Exception as e:
                print(f"[oneclick] BGM 복사 실패 {bgm_rel}: {e}")

    # 2) 간지(interlude)/BGM 디렉토리가 있으면 통째로 복사
    for dirname, label in (("interlude", "간지"), ("bgm", "BGM")):
        tmpl_interlude = tmpl_dir / dirname
        if not tmpl_interlude.is_dir():
            continue
        dest_interlude = dest_dir / dirname
        try:
            shutil.copytree(str(tmpl_interlude), str(dest_interlude), dirs_exist_ok=True)
        except Exception as e:
            print(f"[oneclick] {label} 복사 실패: {e}")

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


def _ensure_project_layout(project_id: str) -> Path:
    project_dir = resolve_project_dir(project_id, create=True)
    project_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("audio", "images", "videos", "subtitles", "output"):
        (project_dir / sub).mkdir(parents=True, exist_ok=True)
    return project_dir


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
        _force_oneclick_main_length(base_config)

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
        project_id = _generate_oneclick_project_id(clean_topic, db, channel=channel)

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
        image_dir = resolve_project_dir(project_id) / "images"
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
            if step_num == 6:
                # 렌더링은 컷 단위 카운터가 없음 — 단계 라벨만 노출
                running_labels.append(label)
                task["current_step_completed"] = 0
                task["current_step_total"] = 0
                continue
            if step_num == 2:
                # v1.1.53: 대본은 단건 LLM 호출이라 컷 단위 진행이 없음
                # running 중이면 가중치의 50% 부여 (생성 중 표시)
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

async def _step_youtube_upload(
    project_id: str,
    config: dict,
    channel: Optional[int] = None,
) -> None:
    """썸네일을 자동 생성하고 YouTube 에 업로드한다.

    channel (1~4) 가 지정되면 채널별 OAuth 토큰을 우선 사용한다.
    채널 토큰이 없으면 프로젝트 토큰 → 전역 토큰 순으로 폴백.
    """
    from app.services.thumbnail_service import generate_ai_thumbnail
    from app.services.youtube_service import YouTubeUploader, YouTubeAuthError, YouTubeUploadError
    from pathlib import Path

    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise RuntimeError("project not found")

        # 1) 썸네일 자동 생성 (AI overlay 모드)
        # v1.1.55: script.json 에서 LLM 이 생성한 title 을 우선 사용
        script_path_t = resolve_project_dir(project_id) / "script.json"
        script_title = ""
        if script_path_t.exists():
            try:
                with open(script_path_t, "r", encoding="utf-8") as f:
                    _sd = json.load(f)
                script_title = (_sd.get("title") or "").strip()
            except Exception:
                pass
        title = with_episode_prefix(
            script_title or (project.title or project.topic or "Untitled").strip(),
            config.get("episode_number") or (project.config or {}).get("episode_number"),
        )

        thumb_dir = resolve_project_dir(project_id) / "output"
        thumb_path = thumb_dir / "thumbnail.png"

        if not thumb_path.exists():
            try:
                from app.services.image.factory import resolve_image_model

                image_model = resolve_image_model(
                    config.get("thumbnail_model") or config.get("image_model")
                )
                # script.json 에서 thumbnail_prompt 를 가져온다
                thumb_prompt = "YouTube thumbnail: " + title
                if script_path_t.exists():
                    try:
                        with open(script_path_t, "r", encoding="utf-8") as f:
                            script_data = json.load(f)
                        tp = script_data.get("thumbnail_prompt") or ""
                        if tp.strip():
                            thumb_prompt = tp.strip()
                    except Exception:
                        pass

                result = await generate_ai_thumbnail(
                    project_id=project_id,
                    image_prompt=thumb_prompt,
                    image_model_id=image_model,
                    overlay_title_text=title,
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
        template_project_id = (
            config.get("template_project_id")
            or (project.config or {}).get("template_project_id")
            or None
        )
        if template_project_id:
            template_uploader = YouTubeUploader(project_id=str(template_project_id))
            if template_uploader.is_authenticated():
                uploader = template_uploader
                print(f"[oneclick] using preset-bound YouTube token ({template_project_id})")

        if uploader is None:
            project_uploader = YouTubeUploader(project_id=project_id)
            if project_uploader.is_authenticated():
                uploader = project_uploader
                print(f"[oneclick] using project-bound YouTube token ({project_id})")

        if uploader is None and ch_int is not None:
            ch_uploader = YouTubeUploader(channel_id=ch_int)
            if ch_uploader.is_authenticated():
                uploader = ch_uploader
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
        script_path = resolve_project_dir(project_id) / "script.json"
        if script_path.exists():
            try:
                with open(script_path, "r", encoding="utf-8") as f:
                    script_data = json.load(f)
                script_description = (script_data.get("description") or "").strip()
                raw_tags = script_data.get("tags") or []
                if isinstance(raw_tags, list):
                    script_tags = [t.strip() for t in raw_tags if isinstance(t, str) and t.strip()]
            except Exception:
                pass

        # 우선순위: config(프리셋) > script.json(LLM생성) > project.topic(폴백)
        description = (
            (config.get("youtube_description") or "").strip()
            or script_description
            or (project.topic or "").strip()
        )
        config_tags = [t.strip() for t in (config.get("youtube_tags") or "").split(",") if t.strip()] if config.get("youtube_tags") else []
        tags = config_tags if config_tags else script_tags
        privacy = config.get("youtube_privacy") or "private"
        print(f"[oneclick] YouTube upload: privacy={privacy}, desc_len={len(description)}, tags={len(tags)}, thumb={thumb_path.exists()}")

        use_thumb = thumb_path.exists()
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
            None,   # progress_callback
        )

        video_url = result.get("url")
        if video_url:
            project.youtube_url = video_url
            db.commit()
            print(f"[oneclick] YouTube uploaded: {video_url}")
        else:
            raise RuntimeError(f"업로드 성공했으나 URL 이 비어있습니다: {result!r}")

        # 3) Shorts 자동 업로드
        # 최종 렌더 단계(render_video_with_subtitles)가 output/shorts/short_*.mp4 를
        # 생성한다. 딸깍 업로드는 본편만 올리고 끝나면 사용자가 기대한 자동화와 다르므로,
        # 같은 채널/프라이버시로 숏츠도 이어서 업로드한다.
        shorts_enabled = bool(config.get("shorts_enabled", True))
        shorts_dir = thumb_dir / "shorts"
        shorts_files = sorted(shorts_dir.glob("short_*.mp4")) if shorts_enabled and shorts_dir.exists() else []
        if shorts_files:
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
            for idx, short_path in enumerate(shorts_files, start=1):
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
                short_title_base = with_episode_prefix(
                    short_title_base,
                    config.get("episode_number") or (project.config or {}).get("episode_number"),
                )
                suffix = " #Shorts" if len(shorts_files) == 1 else f" #{idx} #Shorts"
                max_base_len = max(1, 100 - len(suffix))
                short_title = (short_title_base[:max_base_len].rstrip() + suffix).strip()
                short_description = (description or project.topic or "").strip()
                if short_description:
                    short_description = f"{short_description}\n\n#Shorts"
                else:
                    short_description = "#Shorts"
                short_tags = list(dict.fromkeys([*(tags or []), "Shorts", "쇼츠"]))

                print(f"[oneclick] YouTube Shorts upload: {key}, title={short_title!r}")
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
                    None,   # progress_callback
                )
                short_url = short_result.get("url")
                if not short_url:
                    raise RuntimeError(f"숏츠 업로드 성공했으나 URL 이 비어있습니다: {short_result!r}")
                item = {
                    "file": key,
                    "title": short_title,
                    "url": short_url,
                    "video_id": short_result.get("video_id"),
                }
                shorts_uploads[key] = item
                uploaded_items.append(item)
                shorts_uploads_path.write_text(
                    json.dumps(shorts_uploads, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                print(f"[oneclick] YouTube Shorts uploaded: {short_url}")

            cfg = dict(project.config or {})
            cfg["youtube_shorts_urls"] = [
                item.get("url") for item in uploaded_items
                if isinstance(item, dict) and item.get("url")
            ]
            project.config = cfg
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(project, "config")
            db.commit()
            print(f"[oneclick] YouTube Shorts uploaded count: {len(uploaded_items)}")

        ss = dict(project.step_states or {})
        ss["7"] = "completed"
        project.step_states = ss
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(project, "step_states")
        db.commit()
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


_LIVE_REFRESH_STATUSES = {"prepared", "queued", "running", "paused", "failed", "cancelled"}
_LIVE_MODEL_KEYS = ("script", "tts", "tts_voice", "image", "video", "thumbnail")
_ONECLICK_CLONE_PRESERVE_KEYS = (
    "__oneclick__",
    "template_project_id",
    "topic",
    "episode_number",
    "episode_openings",
    "episode_endings",
    "episode_core_content",
    "next_episode_preview",
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
    return _merge_template_config(project_config, template_config, str(template_project_id))


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
        for t in _TASKS.values():
            if t.get("project_id") == project_id and t.get("status") in ("running", "prepared"):
                if t.get("sub_status") != text:
                    t["sub_status"] = text
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

    # 깨진 복구 프로젝트 보호:
    # step 3 이상부터 재개하려면 script.json 이 반드시 있어야 한다.
    # 없으면 폴더만 다시 만들고 외부 API 호출로 진입할 수 있으므로 즉시 중단한다.
    if resume_from is not None and int(resume_from) > 2:
        script_path = resolve_project_dir(project_id) / "script.json"
        if not script_path.exists():
            msg = (
                f"script.json 이 없어 Step {resume_from}부터 이어서 할 수 없습니다. "
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
            _fresh_proj = _load_project(project_id)
            if _fresh_proj and isinstance(_fresh_proj.config, dict):
                _fresh_cfg = dict(_fresh_proj.config)
                _fresh_cfg["auto_pause_after_step"] = False
                # 변경 감지 → 로그 남김 (UI 에서 "왜 바뀌었는지" 추적 가능하게)
                _changed = []
                for _k in ("script_model", "tts_model", "tts_voice_id",
                            "image_model", "thumbnail_model", "video_model"):
                    _old = config.get(_k, "")
                    _new = _fresh_cfg.get(_k, "")
                    if _old != _new:
                        _changed.append((_k, _old, _new))
                if _changed:
                    for _k, _o, _n in _changed:
                        _add_log(task, f"ℹ 설정 변경 감지: {_k} = {_o or '(없음)'} → {_n or '(없음)'}")
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
        func(project_id, config)
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
        _add_log(task, f"✗ {label} 실패: {type(e).__name__}: {e}", "error")
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


def _ensure_thumbnail_before_render(project_id: str, config: dict):
    """v1.1.57: 렌더링(Step 6) 전에 썸네일이 없으면 자동 생성.

    resume 등으로 Step 6 부터 시작할 때 썸네일이 누락된 경우를 방지한다.
    실패해도 렌더링은 계속 진행한다 (썸네일은 필수가 아님).
    """
    from app.tasks.pipeline_tasks import load_script, _generate_thumbnail_sync, _redis_set

    thumb_path = DATA_DIR / project_id / "output" / "thumbnail.png"
    if thumb_path.exists() and thumb_path.stat().st_size > 100:
        print(f"[oneclick] 썸네일 이미 존재 — 건너뜀: {thumb_path}")
        # v1.1.60: Redis 상태도 done 으로 동기화 — 안 그러면 UI 가 'waiting'
        # 으로 남아서 렌더 단계에서 미리보기가 안 뜬다 (resume 케이스).
        _redis_set(f"thumbnail:status:{project_id}", "done")
        return

    print(f"[oneclick] 썸네일 없음 — 렌더링 전에 자동 생성 시작: {project_id}")
    try:
        script = load_script(project_id)
        if script:
            _generate_thumbnail_sync(project_id, config, script)
            print(f"[oneclick] 썸네일 자동 생성 완료: {project_id}")
        else:
            print(f"[oneclick] script.json 없음 — 썸네일 생성 불가")
            _redis_set(f"thumbnail:status:{project_id}", "failed:script.json 없음")
    except Exception as e:
        err_msg = f"{type(e).__name__}: {e}"
        print(f"[oneclick] 썸네일 자동 생성 실패 (렌더링은 계속): {err_msg}")
        _redis_set(f"thumbnail:status:{project_id}", f"failed:{err_msg[:300]}")


def _schedule_oneclick_run(task_id: str) -> None:
    """v1.1.58: _run_oneclick_task 를 안전하게 스케줄한다.

    같은 task_id 의 이전 인스턴스가 아직 살아있으면(예: 사용자가 중지를 눌렀지만
    내부 LLM/TTS 호출이 끝나지 않아 _RUN_LOCK 을 들고 있는 경우), 그것을 cancel
    하고 새 인스턴스를 띄운다. 이 가드가 없으면 새 _run_oneclick_task 가 _RUN_LOCK
    에서 영원히 대기해 UI 가 "queued" 로 멎는다.
    """
    prev = _ACTIVE_RUNS.get(task_id)
    if prev is not None and not prev.done():
        # 1) 백그라운드 스레드(_run_sync_pipeline) 가 다음 체크포인트에서 종료되도록
        #    Redis cancel 플래그를 세운다. asyncio Task 만 cancel 하면 thread 는
        #    살아남아 새 인스턴스와 동시에 같은 프로젝트를 건드릴 수 있다.
        task = _TASKS.get(task_id)
        pid = task.get("project_id") if task else None
        if pid:
            try:
                from app.tasks.pipeline_tasks import _redis_set
                _redis_set(f"pipeline:cancel:{pid}", "1")
            except Exception:
                pass
        # 2) 코루틴을 cancel — `async with _RUN_LOCK` 블록이 풀리며 락이 즉시 반환된다.
        try:
            prev.cancel()
            print(f"[oneclick] 이전 _run_oneclick_task({task_id}) 를 취소합니다 — 새 실행 스케줄")
        except Exception as e:
            print(f"[oneclick] 이전 task 취소 실패: {e}")
    loop = asyncio.get_running_loop()

    async def _delayed_start():
        # 3) 잠깐 대기 후 cancel 플래그를 비우고 본 작업 시작 — 잔존 스레드가
        #    새 작업의 cancel 플래그를 자기 것으로 오인하지 않게 한다.
        if prev is not None:
            try:
                await asyncio.sleep(1.0)
            except Exception:
                pass
            task = _TASKS.get(task_id)
            pid = task.get("project_id") if task else None
            if pid:
                try:
                    from app.tasks.pipeline_tasks import _redis_set
                    _redis_set(f"pipeline:cancel:{pid}", "")
                except Exception:
                    pass
        await _run_oneclick_task(task_id)

    new_task = loop.create_task(_delayed_start())
    _ACTIVE_RUNS[task_id] = new_task

    def _cleanup(t):
        if _ACTIVE_RUNS.get(task_id) is t:
            _ACTIVE_RUNS.pop(task_id, None)
        try:
            finished = _TASKS.get(task_id) or {}
            if finished.get("status") == "cancelled" or _emergency_stop_active():
                return
            next_task_id = _dispatch_next_queued_task(exclude_task_id=task_id)
            if not next_task_id:
                _dispatch_next_persisted_queue_item()
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

    config = dict(project.config or {})
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

        resume_from = task.pop("resume_from_step", None)

        if resume_from is not None and resume_from > 2:
            fresh = _load_project(project_id)
            if fresh and fresh.total_cuts:
                task["total_cuts"] = int(fresh.total_cuts)

        # --- Step 2~5: 단일 스레드에서 직접 호출 (run_pipeline 과 동일) ---
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
        if task["step_states"].get("6") == "completed":
            task["current_step"] = None
            task["current_step_name"] = None
            task["status"] = "completed"
            task["finished_at"] = _utcnow_iso()
            _update_project_status(project_id, "completed")
            return

        # v1.1.57: 렌더링 전 썸네일 없으면 자동 생성
        # _generate_thumbnail_sync 내부에서 run_async() 를 쓰므로
        # 이벤트 루프 충돌을 피하기 위해 별도 스레드에서 실행한다.
        await asyncio.to_thread(_ensure_thumbnail_before_render, project_id, config)

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

        # --- Step 7: 썸네일 생성 + 유튜브 업로드 ---
        # v1.1.49: resume 모드에서 이미 완료된 7단계는 건너뛴다.
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

        task["current_step"] = 7
        task["current_step_name"] = "유튜브 업로드"
        task["step_states"]["7"] = "running"
        _ch = task.get("channel") or 1
        _privacy = config.get("youtube_privacy", "private")
        _add_log(task, f"▶ 유튜브 업로드 시작 [CH{_ch}, {_privacy}]")
        try:
            await asyncio.to_thread(
                lambda: run_async(_step_youtube_upload(project_id, config, channel=task.get("channel")))
            )
            _add_log(task, "✓ 유튜브 업로드 완료")
        except PipelineCancelled as e:
            print(f"[oneclick] step 유튜브 업로드 CANCELLED by user: {e}")
            _add_log(task, f"⏹ 유튜브 업로드 취소: {e}", "warn")
            task["step_states"]["7"] = "cancelled"
            task["status"] = "cancelled"
            task["error"] = task.get("error") or "사용자 취소"
            task["finished_at"] = _utcnow_iso()
            _update_project_status(project_id, "cancelled")
            return
        except Exception as e:
            tb = traceback.format_exc()
            print(f"[oneclick] step 유튜브 업로드 FAILED: {e}\n{tb}")
            _add_log(task, f"✗ 유튜브 업로드 실패: {type(e).__name__}: {e}", "error")
            task["step_states"]["7"] = "failed"
            task["status"] = "failed"
            task["error"] = f"유튜브 업로드 실패: {type(e).__name__}: {e}"
            task["finished_at"] = _utcnow_iso()
            _update_project_status(project_id, "failed")
            return

        task["step_states"]["7"] = "completed"
        task["current_step"] = None
        task["current_step_name"] = None
        task["status"] = "completed"
        task["finished_at"] = _utcnow_iso()
        # v2.1.2: 전체 소요시간 계산
        try:
            from datetime import datetime as _dt
            _started = _dt.fromisoformat(task.get("started_at", ""))
            _finished = _dt.fromisoformat(task["finished_at"])
            _total_sec = (_finished - _started).total_seconds()
            _add_log(task, f"🎉 제작 완료! 총 {_total_sec/60:.1f}분 소요")
        except Exception:
            _add_log(task, "🎉 제작 완료!")
        _update_project_status(project_id, "completed")
        _save_tasks_to_disk()


def _update_project_status(project_id: str, status: str) -> None:
    db = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == project_id).first()
        if p:
            p.status = status
            db.commit()
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Public API (routers/oneclick.py 에서 호출)
# --------------------------------------------------------------------------- #

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
    # ── 기존 미완성 프로젝트 재사용 시도 ──
    reusable = _find_reusable_project(template_project_id, topic)
    if reusable:
        project, detected_states = reusable
        _ensure_project_layout(project.id)

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
                old_cfg = dict(project.config or {})
                _force_oneclick_main_length(base)

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

        # total_cuts 복원
        fresh = _load_project(project.id)
        if fresh and fresh.total_cuts:
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
    # 이미 같은 project_id 의 태스크가 있으면 그대로 반환
    for t in _TASKS.values():
        if t.get("project_id") == project_id:
            return t

    project = _load_project(project_id)
    if not project:
        raise KeyError(f"프로젝트를 찾을 수 없습니다: {project_id}")

    detected = _detect_completed_steps(project_id)
    config = project.config or {}
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
    task["step_states"] = detected

    # total_cuts 복원 — script.json 에서
    script_path = resolve_project_dir(project_id) / "script.json"
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
    if task["status"] not in ("prepared", "failed", "cancelled"):
        # 이미 running/completed 면 무시 (idempotent)
        return task
    task["status"] = "queued"
    task["error"] = None
    task["finished_at"] = None
    _add_log(task, "⏳ 실행 대기열 등록", "info")
    if _has_running_task(exclude_task_id=task_id):
        _save_tasks_to_disk()
        return task
    # v1.1.37 bugfix: get_event_loop() 는 worker thread 에서 에러. 반드시 async
    # 컨텍스트에서 호출되어야 하므로 get_running_loop() 로 의도를 명시. 라우터
    # oneclick.start 가 async def 로 선언되어 있어 여기서 running loop 가 보장됨.
    # v1.1.58: 중복 스케줄 방지 가드를 통한다.
    _dispatch_next_queued_task()
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

    project_id = str(task.get("project_id") or "").strip()
    project_dir = resolve_project_dir(project_id)
    script_path = project_dir / "script.json"
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

    if not script_path.exists():
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

    # 깨진 복구 프로젝트 보호:
    # 이전엔 step_states 가 오래된 completed 상태로 남아 있으면 script.json 이
    # 사라진 뒤에도 step 4부터 그대로 재개되어 이미지/영상 API를 다시 호출했다.
    # 핵심 파일이 없으면 자동 재생성으로 넘어가지 말고 즉시 중단한다.
    if any(previous_states.get(str(step_num)) == "completed" for _, step_num, _ in STEP_ORDER):
        current_states = task.get("step_states") or {}
        if current_states.get("2") != "completed":
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
    _dispatch_next_queued_task()
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
        # v1.2.29: 프로세스 halt 집합에도 마킹 — redis 장애시에도 보장되는 경로
        try:
            from app.services.cancel_ctx import mark_halted
            mark_halted(pid)
        except Exception:
            pass

    # 2) v1.2.23 [돈줄 차단 강화]: 이미 ComfyUI 에 제출된 프롬프트가 끝까지
    #    실행되는 문제를 막는다. cancel 은 "다음 컷 제출 금지" 만 하던 게 문제.
    #    사용자 보고: "큐에 작업 없는데 ComfyUI 가 SDXL 을 계속 돌린다."
    #    → 이미 제출된 프롬프트 interrupt + 대기 큐 clear 를 동시에 호출.
    #
    # v1.2.27: sync 라우터 경로에서 `asyncio.run(_kill_comfy())` 가 httpx timeout
    # 10s × 2 = 20s blocking 하던 문제. `cancel` 라우터가 sync def 라 FastAPI
    # threadpool 에서 돌지만, 이 스레드가 20s 막히면 `cancel()` API 응답이
    # 돌아오지 않아 프런트의 "중단 중..." 이 고착된다. 전체 상한을 3s 로 줄이고,
    # 시간 초과하면 조용히 포기한다 (redis flag + task status 는 위에서 이미 세팅됨).
    try:
        from app.services import comfyui_client
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            # 이벤트 루프가 있을 때: fire-and-forget 으로 async interrupt.
            loop.create_task(comfyui_client.interrupt())
            loop.create_task(comfyui_client.clear_queue())
        else:
            # 이벤트 루프가 없을 때 (sync 라우터에서 호출된 일반 케이스):
            # 임시 루프를 열어 3초 안에 끝내도록 강제.
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
            try:
                asyncio.run(_kill_with_timeout())
            except Exception:
                pass
    except Exception as e:
        print(f"[oneclick.cancel] comfyui interrupt skipped: {e}")

    # 3) asyncio.Task 즉시 취소 — 취소 체크를 기다리지 않고 바로 깨운다.
    try:
        prev = _ACTIVE_RUNS.get(task_id)
        if prev is not None and not prev.done():
            prev.cancel()
        _ACTIVE_RUNS.pop(task_id, None)
    except Exception as e:
        print(f"[oneclick.cancel] asyncio task cancel skipped: {e}")

    try:
        _normalize_interrupted_task(task)
        _reconcile_task_outputs(task, clear_terminal_cursor=True)
        task["progress_pct"] = _compute_progress_pct(task)
    except Exception as e:
        print(f"[oneclick.cancel] normalize skipped: {e}")

    try:
        _save_tasks_to_disk()
    except Exception:
        pass
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
        if status not in ("running", "queued", "paused"):
            continue
        pid = task.get("project_id")

        # Redis cancel 플래그 + 프로세스 halt 집합 (이중 방어선)
        if pid:
            try:
                _redis_set(f"pipeline:cancel:{pid}", "1")
            except Exception as e:
                errors.append(f"redis cancel {task_id}: {e}")
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
            _normalize_interrupted_task(task)
            _reconcile_task_outputs(task, clear_terminal_cursor=True)
            task["progress_pct"] = _compute_progress_pct(task)
        except Exception as e:
            errors.append(f"normalize {task_id}: {e}")
        stopped_ids.append(task_id)

    if stopped_ids:
        try:
            _save_tasks_to_disk()
        except Exception as e:
            errors.append(f"save tasks: {e}")

    # 4~5) ComfyUI 서버 측 중단
    #
    # v1.2.27: "중단 중..." 버튼이 고착되던 문제 해결.
    # 이전엔 `await comfyui_client.interrupt()` (httpx timeout 10s) +
    # `await comfyui_client.clear_queue()` (10s) 를 순차 await 했다.
    # ComfyUI 서버(원격 GPU PC)가 응답 못 주면 HTTP 응답이 최대 20초 지연되고,
    # 프런트 `setEmergencyStopping(true)` 상태가 그 동안 풀리지 않아 "중단 중..."
    # 로 고착. 사용자는 버튼이 안 먹는 줄 알게 된다.
    #
    # 수정: 두 호출을 병렬 `asyncio.gather` 로 묶고 전체 상한 3초. 시간 초과하면
    # 결과값은 False 로 두고 fire-and-forget 으로 뒤에서 계속 시도. cancel 플래그·
    # redis 는 위에서 이미 세팅돼 있어서 파이프라인은 이미 이탈 중이고, ComfyUI
    # `/interrupt` 는 best-effort 라 지연 응답을 기다릴 이유가 없다.
    comfy_interrupt_ok = False
    comfy_clear_ok = False

    async def _both_comfy():
        return await asyncio.gather(
            comfyui_client.interrupt(),
            comfyui_client.clear_queue(),
            return_exceptions=True,
        )

    try:
        results = await asyncio.wait_for(_both_comfy(), timeout=3.0)
        r_int, r_clr = results
        if isinstance(r_int, Exception):
            errors.append(f"comfyui interrupt: {r_int}")
        else:
            comfy_interrupt_ok = bool(r_int)
        if isinstance(r_clr, Exception):
            errors.append(f"comfyui clear_queue: {r_clr}")
        else:
            comfy_clear_ok = bool(r_clr)
    except asyncio.TimeoutError:
        errors.append("comfyui interrupt/clear_queue timeout 3s — 백그라운드로 전환")
        # 3초 안에 안 돌아오면 fire-and-forget 로 뒤에서 계속 시도 (응답은 즉시 반환).
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(comfyui_client.interrupt())
            loop.create_task(comfyui_client.clear_queue())
        except Exception as e:
            errors.append(f"comfyui fire-and-forget: {e}")
    except Exception as e:
        errors.append(f"comfyui gather: {e}")

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
    task = _TASKS.get(task_id)
    if not task:
        return None
    changed = False
    if task.get("status") in _LIVE_REFRESH_STATUSES:
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
    # v1.1.53: 썸네일 생성 상태 (waiting / generating / done / failed)
    # v1.1.55: failed:사유 형태인 경우 status 와 error 를 분리하여 전달
    # v1.1.58: 완료/실패 태스크는 실제 파일 존재 여부로 최종 판정 — Redis 고착 방지
    pid = task.get("project_id")
    if pid:
        raw = _redis_get(f"thumbnail:status:{pid}") or "waiting"
        # 태스크가 이미 끝났으면 Redis 대신 파일 체크로 확정
        if task["status"] in ("completed", "failed", "cancelled"):
            thumb_path = DATA_DIR / pid / "output" / "thumbnail.png"
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
            thumb_path = DATA_DIR / pid / "output" / "thumbnail.png"
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
    for t in _TASKS.values():
        if t["status"] in ("running", "queued", "prepared"):
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
    # 최신순. 진행률도 갱신.
    changed = False
    for tid in list(_TASKS.keys()):
        if _TASKS[tid].get("status") in ("failed", "cancelled", "paused", "completed"):
            if _reconcile_task_outputs(_TASKS[tid], clear_terminal_cursor=True):
                changed = True
        _TASKS[tid]["progress_pct"] = _compute_progress_pct(_TASKS[tid])
        # v1.2.17: episode_number 지연 백필 — 구버전에서 생성된 task 는
        # 이 필드가 없다. project.config 에서 한 번만 조회해 task 에 박아둔다.
        # 이후 호출부터는 dict 내 캐시로 DB 히트 없이 반환된다.
        t = _TASKS[tid]
        if t.get("status") in _LIVE_REFRESH_STATUSES:
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
        if "episode_number" not in t:
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
    import glob as _glob

    task = _TASKS.get(task_id)
    if not task:
        raise KeyError(f"task {task_id} not found")
    if task["status"] in ("running", "queued"):
        raise ValueError("실행 중인 태스크는 초기화할 수 없습니다")

    project_id = task["project_id"]
    project_dir = resolve_project_dir(project_id)

    STEP_MAP = {
        2: ("script", ["script.json", "output/thumbnail*.png", "output/thumbnail*.jpg", "output/thumbnail*.jpeg", "output/thumbnail*.webp"]),
        3: ("audio", ["audio/*.mp3"]),
        4: ("images", ["images/*.png"]),
        5: ("videos", ["videos/*.mp4", "output/merged.mp4"]),
        6: ("render", ["output/final.mp4", "output/merged.mp4"]),
    }
    if step not in STEP_MAP:
        raise ValueError(f"초기화 가능한 단계: 2(대본), 3(음성), 4(이미지), 5(영상), 6(렌더)")

    label, patterns = STEP_MAP[step]
    deleted = 0
    for pattern in patterns:
        for fp in _glob.glob(str(project_dir / pattern)):
            try:
                os.remove(fp)
                deleted += 1
            except OSError:
                pass

    # DB step_state 도 되돌린다
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if project:
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
        candidates.append(DATA_DIR / pid)
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
    import shutil
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


def _inspect_project_progress(project_id: str | None, total_cuts: int | None) -> dict[str, Any]:
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
    pdir = resolve_project_dir(project_id)
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
    """실패/취소된 태스크를 "초기화 + 대기 큐 복귀" 로 되돌린다.

    v1.2.22 — 사용자가 실패 카드의 ⟳ 버튼을 눌렀을 때 호출.
    동작:
      1) 태스크 조회 — 없으면 KeyError
      2) 상태가 completed / running 이면 거부 (ValueError)
      3) 프로젝트 폴더 진행률 관찰 (리포트용)
      4) Redis cancel 플래그 + asyncio Task cancel (혹시 살아있으면)
      5) 프로젝트 폴더 전체 삭제
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
    if status == "completed":
        # 완성작은 라이브러리 관리 대상. 복귀 의미가 없어 거부.
        raise ValueError("완성된 태스크는 복귀할 수 없습니다")
    if status == "running":
        # 실행 중 태스크는 먼저 취소해야 함 — 자동 cancel+requeue 는 위험.
        raise ValueError("실행 중 태스크는 먼저 중단하세요")

    pid = task.get("project_id")
    channel = int(task.get("channel") or 1)
    if channel not in (1, 2, 3, 4):
        channel = 1

    # 1) 진행률 관찰 — 삭제 전
    progress = _inspect_project_progress(pid, task.get("total_cuts"))

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

    # 3) 디스크 정리
    deleted_bytes = _cleanup_project_files(pid, task.get("config") if isinstance(task.get("config"), dict) else None)

    # 4) 에피소드 상세 추출 (프로젝트 config → 큐 아이템 으로 되돌림).
    project = _load_project(pid) if pid else None
    cfg = dict(project.config or {}) if project else {}
    openings = cfg.get("episode_openings") or []
    endings = cfg.get("episode_endings") or []
    core = cfg.get("episode_core_content") or ""
    ep_num = cfg.get("episode_number") or task.get("episode_number")
    next_preview = cfg.get("next_episode_preview") or ""
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
        "episode_number": (int(ep_num) if isinstance(ep_num, (int, float)) and int(ep_num) > 0 else None),
        "next_episode_preview": str(next_preview or "").strip(),
        "queued_source": "requeue",
        "queued_at": _utcnow_iso(),
        "queued_note": "실패/중단 태스크 복구",
        "requeued_from_task_id": task_id,
    }

    # 5) 큐 정규화 + 해당 채널의 **맨 앞**에 삽입.
    # v1.2.28: 이전 버전은 list 끝에 append 였으나, 큐가 60건 이상인 상황에선
    # 복구된 아이템이 마지막 페이지로 밀려 "사라진 것처럼" 보였다. 같은 채널의
    # 첫 항목 앞에 넣어서 사용자가 즉시 확인 + 다음 자동 실행에 바로 반영되게 한다.
    items = list(_QUEUE.get("items") or [])
    insert_at = len(items)
    for _i, _it in enumerate(items):
        if int(_it.get("channel") or 1) == channel:
            insert_at = _i
            break
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
        if t.get("status") not in ("failed", "cancelled"):
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
                progress = _inspect_project_progress(proj.id, total_cuts)
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
        # 채널별로 그룹화하여 맨 앞에 삽입.
        by_channel: dict[int, list[dict]] = {}
        for ni in new_items:
            by_channel.setdefault(int(ni.get("channel") or 1), []).append(ni)
        for ch_key, group in by_channel.items():
            insert_at = len(items)
            for _i, _it in enumerate(items):
                if int(_it.get("channel") or 1) == ch_key:
                    insert_at = _i
                    break
            # group 을 역순으로 하나씩 insert 하면 최종 순서가 유지된다.
            for ni in reversed(group):
                items.insert(insert_at, ni)
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
    ]
    finished.sort(key=lambda t: t.get("finished_at") or t.get("created_at") or "")
    excess = len(finished) - keep
    if excess > 0:
        for t in finished[:excess]:
            _TASKS.pop(t["task_id"], None)


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
    project_dir = DATA_DIR / project_id if project_id else None

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


async def manual_youtube_upload(task_id: str) -> dict:
    """완성작을 수동으로 YouTube 에 업로드."""
    task = _TASKS.get(task_id)
    if not task:
        raise KeyError("task not found")

    project_id = task["project_id"]
    project = _load_project(project_id)
    if not project:
        raise RuntimeError("프로젝트를 찾을 수 없습니다")

    config = dict(project.config or {})
    states = dict(task.get("step_states") or {})
    states["7"] = "running"
    task["step_states"] = states
    task["current_step"] = 7
    task["current_step_name"] = "유튜브 업로드"
    task["error"] = None
    _add_log(task, "▶ 유튜브 수동 업로드 시작")
    _save_tasks_to_disk()

    try:
        await _step_youtube_upload(project_id, config, channel=task.get("channel"))
    except Exception as e:
        states = dict(task.get("step_states") or {})
        states["7"] = "failed"
        task["step_states"] = states
        task["current_step"] = None
        task["current_step_name"] = None
        task["error"] = f"유튜브 업로드 실패: {type(e).__name__}: {e}"
        _add_log(task, f"✗ 유튜브 수동 업로드 실패: {type(e).__name__}: {e}", "error")
        _save_tasks_to_disk()
        raise

    # 업로드 후 URL 다시 읽기
    project = _load_project(project_id)
    states = dict(task.get("step_states") or {})
    states["7"] = "completed"
    task["step_states"] = states
    task["current_step"] = None
    task["current_step_name"] = None
    task["error"] = None
    _add_log(task, "✓ 유튜브 수동 업로드 완료")
    _save_tasks_to_disk()
    return {
        "ok": True,
        "youtube_url": project.youtube_url if project else None,
    }


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
                if proj and getattr(proj, "youtube_url", None):
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
                    d = DATA_DIR / pid
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


def _queue_normalize(raw: Any) -> dict[str, Any]:
    """디스크/프론트 입력이 불완전해도 안전한 dict 로 강제.

    v1.1.57: 레거시 daily_time/last_run_date → channel_times/last_run_dates 마이그레이션.
    v1.2.9 : 큐 아이템에 에피소드 상세 필드 (openings/endings/core_content) 보존.
    v1.2.10: episode_number / next_episode_preview 보존.
    v1.2.14: channel_presets 필드 보존.
    """
    if not isinstance(raw, dict):
        return {
            "channel_times": {"1": None, "2": None, "3": None, "4": None},
            "last_run_dates": {"1": None, "2": None, "3": None, "4": None},
            "channel_presets": {"1": None, "2": None, "3": None, "4": None},
            "items": [],
        }
    out: dict[str, Any] = {
        "channel_times": {"1": None, "2": None, "3": None, "4": None},
        "last_run_dates": {"1": None, "2": None, "3": None, "4": None},
        "channel_presets": {"1": None, "2": None, "3": None, "4": None},
        "items": [],
    }

    # --- channel_times ---
    ct = raw.get("channel_times")
    if isinstance(ct, dict):
        for ch in CHANNELS:
            v = ct.get(str(ch))
            if isinstance(v, str) and len(v) == 5 and v[2] == ":":
                out["channel_times"][str(ch)] = v
    # 레거시 마이그레이션: daily_time → channel_times["1"]
    legacy_dt = raw.get("daily_time")
    if isinstance(legacy_dt, str) and len(legacy_dt) == 5 and legacy_dt[2] == ":":
        if not out["channel_times"]["1"]:
            out["channel_times"]["1"] = legacy_dt

    # --- last_run_dates ---
    lrd = raw.get("last_run_dates")
    if isinstance(lrd, dict):
        for ch in CHANNELS:
            v = lrd.get(str(ch))
            if isinstance(v, str) and len(v) == 10:
                out["last_run_dates"][str(ch)] = v
    # 레거시
    legacy_lrd = raw.get("last_run_date")
    if isinstance(legacy_lrd, str) and len(legacy_lrd) == 10:
        if not out["last_run_dates"]["1"]:
            out["last_run_dates"]["1"] = legacy_lrd

    # --- channel_presets ---
    cp = raw.get("channel_presets")
    if isinstance(cp, dict):
        for ch in CHANNELS:
            v = cp.get(str(ch))
            if v is None or v == "":
                out["channel_presets"][str(ch)] = None
            else:
                out["channel_presets"][str(ch)] = str(v)

    # --- items ---
    items = raw.get("items")
    if isinstance(items, list):
        clean: list[dict] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            topic = str(it.get("topic") or "").strip()
            if not topic:
                continue
            # channel: 1~4. 명시값 → 프리셋 youtube_channel → 1.
            ch_raw = it.get("channel")
            ch: Optional[int] = None
            try:
                if ch_raw is not None and str(ch_raw).strip() != "":
                    ch = int(ch_raw)
            except (TypeError, ValueError):
                ch = None
            if ch is None:
                tpl_id = it.get("template_project_id")
                if tpl_id:
                    try:
                        tpl = _load_project(str(tpl_id))
                        cfg_ch = (tpl.config or {}).get("youtube_channel") if tpl else None
                        if cfg_ch is not None and str(cfg_ch).strip() != "":
                            ch = int(cfg_ch)
                    except Exception:
                        ch = None
            if ch is None:
                ch = 1
            if ch < 1 or ch > 4:
                ch = 1

            # OneClick main videos are always 120 clips. Keep the legacy
            # duration field normalized so stale 30s queue rows cannot leak in.
            td_val: Optional[int] = ONECLICK_MAIN_TARGET_DURATION

            # openings / endings — list[str]
            def _clean_list_of_str(xs):
                if not isinstance(xs, list):
                    return []
                return [str(x) for x in xs]

            openings = _clean_list_of_str(it.get("openings"))
            endings = _clean_list_of_str(it.get("endings"))
            core_content = str(it.get("core_content") or "")

            # episode_number
            ep_num: Optional[int] = None
            try:
                ep_raw = it.get("episode_number")
                if isinstance(ep_raw, (int, float)) and int(ep_raw) > 0:
                    ep_num = int(ep_raw)
            except Exception:
                ep_num = None

            next_preview = str(it.get("next_episode_preview") or "")
            queued_source = str(it.get("queued_source") or "manual").strip().lower()
            if queued_source not in ("manual", "import", "requeue", "orphan", "schedule", "system"):
                queued_source = "manual"
            queued_at = str(it.get("queued_at") or "").strip() or None
            queued_note = str(it.get("queued_note") or "").strip()
            requeued_from_task_id = str(it.get("requeued_from_task_id") or "").strip()
            restored_from_project_id = str(it.get("restored_from_project_id") or "").strip()

            clean.append({
                "id": str(it.get("id") or uuid.uuid4().hex[:8]),
                "topic": topic,
                "template_project_id": (it.get("template_project_id") or None),
                "target_duration": td_val,
                "target_cuts": ONECLICK_MAIN_CUT_COUNT,
                "channel": ch,
                "openings": openings,
                "endings": endings,
                "core_content": core_content,
                "episode_number": ep_num,
                "next_episode_preview": next_preview,
                "queued_source": queued_source,
                "queued_at": queued_at,
                "queued_note": queued_note,
                "requeued_from_task_id": requeued_from_task_id,
                "restored_from_project_id": restored_from_project_id,
            })
        out["items"] = clean
    return out


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
        _QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _QUEUE_FILE.write_text(
            json.dumps(_QUEUE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"[oneclick.queue] save failed: {e}")


def _resolve_item_preset(item: dict) -> Optional[str]:
    """아이템의 template_project_id 가 비어 있으면 채널별 기본 프리셋을 사용.

    v1.2.14: `channel_presets[str(ch)]` 를 fallback 으로. 둘 다 없으면 None
    → prepare_task 가 빈 템플릿으로 DEFAULT_CONFIG 만으로 돌린다.
    """
    tpl = item.get("template_project_id")
    if tpl:
        return str(tpl)
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
    return None


def get_queue() -> dict[str, Any]:
    """현재 큐 상태 반환 (UI 조회용). 복사본을 돌려준다."""
    _ensure_state_loaded()
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
    normalized = _queue_normalize(new_state)
    # last_run_dates 는 사용자가 바꿀 값이 아니므로 기존 값 유지.
    if not isinstance(new_state.get("last_run_dates"), dict):
        normalized["last_run_dates"] = dict(_QUEUE.get("last_run_dates") or {})
    _QUEUE = normalized
    _save_queue_to_disk()
    _sync_windows_wake_timers(reason="queue-save")
    return get_queue()


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


async def _fire_queue_for_channel(ch: int, triggered_by: str = "schedule") -> bool:
    """채널 ch 의 큐 맨 앞 1 건을 뽑아 즉시 실행.

    해당 채널에 items 가 없으면 아무것도 안 함.
    성공/실패 상관없이 pop-on-start.
    """
    if triggered_by != "manual" and _emergency_stop_active():
        print(f"[oneclick.queue] defer ch{ch}: emergency stop guard active")
        return False

    if _has_inflight_task():
        print(f"[oneclick.queue] defer ch{ch}: 다른 작업이 이미 running/queued 상태")
        return False

    items = list(_QUEUE.get("items") or [])
    target_idx = None
    for i, it in enumerate(items):
        if (it.get("channel") or 1) == ch:
            target_idx = i
            break
    if target_idx is None:
        return False

    head = items.pop(target_idx)
    _QUEUE["items"] = items
    _save_queue_to_disk()

    preset_id = _resolve_item_preset(head)
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
            next_episode_preview=head.get("next_episode_preview"),
            channel=ch,
        )
        task["triggered_by"] = "schedule" if triggered_by == "schedule" else "manual"
        task["channel"] = ch
    except Exception as e:
        # prepare_task 실패 → 아이템 자체를 큐에 되돌려 넣음 (해당 채널 맨 앞).
        print(f"[oneclick.queue] prepare ch{ch} failed, restoring queue item: {e}")
        try:
            restore_items = list(_QUEUE.get("items") or [])
            restore_at = len(restore_items)
            for _ri, _rit in enumerate(restore_items):
                if int(_rit.get("channel") or 1) == ch:
                    restore_at = _ri
                    break
            restore_items.insert(restore_at, head)
            _QUEUE["items"] = restore_items
            _save_queue_to_disk()
        except Exception as _re:
            print(f"[oneclick.queue] restore fail ch{ch}: {_re}")
        return False

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
        return False

    return True


async def _queue_loop() -> None:
    """30 초 간격으로 채널별 큐 스케줄을 점검."""
    print("[oneclick.queue] scheduler loop started (4-channel mode)")
    try:
        while True:
            try:
                now = datetime.now()
                today = _today_iso()
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


def start_queue_scheduler() -> None:
    """v1.1.43: FastAPI lifespan startup 훅에서 호출된다.

    _queue_loop 을 asyncio.Task 로 띄워 백그라운드에서 30 초마다 채널 스케줄
    을 감시한다. 이미 기동돼 있으면 중복 실행하지 않는다.
    """
    global _QUEUE_TASK
    _ensure_state_loaded()
    _sync_windows_wake_timers(reason="startup")
    if _QUEUE_TASK is not None and not _QUEUE_TASK.done():
        return
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    _QUEUE_TASK = loop.create_task(_queue_loop())


def stop_queue_scheduler() -> None:
    """v1.1.43: FastAPI lifespan shutdown 훅에서 호출."""
    global _QUEUE_TASK
    if _QUEUE_TASK is None:
        return
    try:
        _QUEUE_TASK.cancel()
    except Exception as e:
        print(f"[oneclick.queue] cancel error: {e}")
    _QUEUE_TASK = None

def run_queue_top_now(channel=None):
    """v1.2.12: 큐 맨 위 1건을 즉시 실행. 큐가 비어 있으면 None 반환.

    async 이벤트 루프가 필요하므로 라우터에서 async 로 호출한다.
    channel 미지정 시 채널 1 로 간주.
    """
    _clear_emergency_stop_guard()
    target_ch = int(channel) if channel else 1
    ch_items = [
        it for it in (_QUEUE.get("items") or [])
        if int(it.get("channel") or 1) == target_ch
    ]
    if not ch_items:
        return None
    before_ids = set(_TASKS.keys())
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_fire_queue_for_channel(target_ch, "manual"))
        else:
            loop.run_until_complete(_fire_queue_for_channel(target_ch, "manual"))
    except RuntimeError:
        new_loop = asyncio.new_event_loop()
        try:
            new_loop.run_until_complete(_fire_queue_for_channel(target_ch, "manual"))
        finally:
            new_loop.close()
    # 방금 생성된 task 반환. 즉시 실행(manual)과 스케줄 실행(schedule)을 구분한다.
    for t in reversed(list(_TASKS.values())):
        if t.get("task_id") not in before_ids and t.get("channel") == target_ch:
            return t
    for t in reversed(list(_TASKS.values())):
        if t.get("channel") == target_ch:
            return t
    return None
