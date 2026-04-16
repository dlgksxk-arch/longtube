"""Pipeline control router (run, pause, resume, cancel, reset)"""
import time
import redis
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.models.database import get_db
from app.models.project import Project
from app.config import REDIS_URL

router = APIRouter()

# Redis: graceful fallback when unavailable
try:
    redis_client = redis.from_url(REDIS_URL)
    redis_client.ping()
except Exception:
    redis_client = None


def _redis_set(key: str, value: str):
    if redis_client:
        redis_client.set(key, value)

def _redis_get(key: str):
    if redis_client:
        return redis_client.get(key)
    return None

def _redis_delete(*keys: str):
    if redis_client:
        redis_client.delete(*keys)


# ── Average time per cut by step (seconds) ──
# Used for ETA calculation
STEP_AVG_SECONDS_PER_CUT = {
    2: 3.0,    # Script: ~3s per cut (LLM generation)
    3: 4.0,    # Voice TTS: ~4s per cut
    4: 8.0,    # Image gen: ~8s per cut
    5: 30.0,   # Video gen: ~30s per cut (FFmpeg=fast, AI=slow)
}

STEP_NAMES = {
    1: "settings", 2: "script", 3: "voice",
    4: "image", 5: "video",
}


class RunRequest(BaseModel):
    start_step: Optional[int] = 2
    end_step: Optional[int] = 5


@router.post("/{project_id}/run-all")
def run_all(project_id: str, body: RunRequest = RunRequest(), db: Session = Depends(get_db)):
    """전체 파이프라인 실행"""
    project = _get_project(project_id, db)

    _redis_delete(f"pipeline:pause:{project_id}", f"pipeline:cancel:{project_id}")

    project.status = "processing"
    db.commit()

    try:
        from app.tasks.pipeline_tasks import run_pipeline
        run_pipeline.delay(project_id, body.start_step, body.end_step)
    except Exception:
        pass

    return {"status": "started", "from_step": body.start_step, "to_step": body.end_step}


@router.post("/{project_id}/step/{step}")
def run_step(project_id: str, step: int, db: Session = Depends(get_db)):
    """특정 단계만 실행"""
    project = _get_project(project_id, db)
    _redis_delete(f"pipeline:pause:{project_id}")

    # Mark step as running
    states = dict(project.step_states or {})
    states[str(step)] = "running"
    project.step_states = states
    project.current_step = step
    project.status = "processing"
    db.commit()

    # Track start time
    _redis_set(f"pipeline:step_start:{project_id}:{step}", str(time.time()))
    _redis_set(f"pipeline:step_progress:{project_id}:{step}", "0")

    try:
        from app.tasks.pipeline_tasks import run_pipeline
        run_pipeline.delay(project_id, step, step)
    except Exception:
        pass

    return {"status": "started", "step": step}


@router.post("/{project_id}/pause")
def pause(project_id: str, db: Session = Depends(get_db)):
    """일시중지"""
    _redis_set(f"pipeline:pause:{project_id}", "1")

    project = _get_project(project_id, db)
    step = project.current_step
    if step:
        states = dict(project.step_states or {})
        states[str(step)] = "paused"
        project.step_states = states
        project.status = "paused"
        db.commit()

    return {"status": "pausing", "message": "현재 컷 처리 완료 후 일시중지됩니다"}


@router.post("/{project_id}/pause-step/{step}")
def pause_step(project_id: str, step: int, db: Session = Depends(get_db)):
    """특정 단계 일시중지"""
    _redis_set(f"pipeline:pause:{project_id}", "1")

    project = _get_project(project_id, db)
    states = dict(project.step_states or {})
    states[str(step)] = "paused"
    project.step_states = states
    project.status = "paused"
    db.commit()

    return {"status": "paused", "step": step}


@router.post("/{project_id}/resume")
def resume(project_id: str, db: Session = Depends(get_db)):
    """재시작"""
    _redis_delete(f"pipeline:pause:{project_id}")

    project = _get_project(project_id, db)
    step = project.current_step
    if step:
        states = dict(project.step_states or {})
        if states.get(str(step)) == "paused":
            states[str(step)] = "running"
            project.step_states = states
            project.status = "processing"
            db.commit()

    return {"status": "resumed"}


@router.post("/{project_id}/resume-step/{step}")
def resume_step(project_id: str, step: int, db: Session = Depends(get_db)):
    """특정 단계 이어하기"""
    _redis_delete(f"pipeline:pause:{project_id}", f"pipeline:cancel:{project_id}")

    project = _get_project(project_id, db)
    states = dict(project.step_states or {})
    states[str(step)] = "running"
    project.step_states = states
    project.current_step = step
    project.status = "processing"
    db.commit()

    _redis_set(f"pipeline:step_start:{project_id}:{step}", str(time.time()))

    try:
        from app.tasks.pipeline_tasks import run_pipeline
        run_pipeline.delay(project_id, step, step)
    except Exception:
        pass

    return {"status": "resumed", "step": step}


@router.post("/{project_id}/reset-step/{step}")
def reset_step(project_id: str, step: int, db: Session = Depends(get_db)):
    """특정 단계 초기화 (생성된 데이터 제거)"""
    project = _get_project(project_id, db)

    # Cancel any running task
    _redis_set(f"pipeline:cancel:{project_id}", "1")
    _redis_delete(
        f"pipeline:pause:{project_id}",
        f"pipeline:step_start:{project_id}:{step}",
        f"pipeline:step_progress:{project_id}:{step}",
    )

    # Clear step state
    states = dict(project.step_states or {})
    states[str(step)] = "pending"
    project.step_states = states
    if project.current_step == step:
        project.status = "draft"
    db.commit()

    # Clear generated data based on step type
    from app.config import DATA_DIR
    import os, glob
    project_dir = DATA_DIR / project_id

    if step == 2:  # Script — clear cuts from DB
        pass  # Cuts are regenerated by script.generate
    elif step == 3:  # Voice — clear audio files
        audio_dir = project_dir / "audio"
        if audio_dir.exists():
            for f in audio_dir.iterdir():
                try:
                    f.unlink()
                except:
                    pass
    elif step == 4:  # Image — clear image files (v1.1.29 이후 4번, 이전 5번)
        img_dir = project_dir / "images"
        if img_dir.exists():
            for f in img_dir.iterdir():
                try:
                    f.unlink()
                except:
                    pass
    elif step == 5:  # Video — clear video files (v1.1.29 이후 5번, 이전 6번)
        vid_dir = project_dir / "videos"
        if vid_dir.exists():
            for f in vid_dir.iterdir():
                try:
                    f.unlink()
                except:
                    pass
    elif step == 6:  # Render — clear subtitles/output (수동 렌더링 단계)
        for sub in ["subtitles", "output"]:
            d = project_dir / sub
            if d.exists():
                for f in d.iterdir():
                    try:
                        f.unlink()
                    except:
                        pass

    _redis_delete(f"pipeline:cancel:{project_id}")
    return {"status": "reset", "step": step}


@router.post("/{project_id}/resume-from/{step}")
def resume_from_step(project_id: str, step: int):
    """특정 단계부터 재시작"""
    _redis_delete(f"pipeline:pause:{project_id}", f"pipeline:cancel:{project_id}")

    try:
        from app.tasks.pipeline_tasks import run_pipeline
        run_pipeline.delay(project_id, step)
    except Exception:
        pass

    return {"status": "restarted", "from_step": step}


@router.post("/{project_id}/cancel")
def cancel(project_id: str, db: Session = Depends(get_db)):
    """파이프라인 취소"""
    _redis_set(f"pipeline:cancel:{project_id}", "1")
    _redis_delete(f"pipeline:pause:{project_id}")

    project = _get_project(project_id, db)
    project.status = "draft"
    states = dict(project.step_states or {})
    for k, v in states.items():
        if v == "running":
            states[k] = "failed"
    project.step_states = states
    db.commit()

    return {"status": "cancelling"}


@router.get("/{project_id}/status")
def get_status(project_id: str, db: Session = Depends(get_db)):
    """현재 파이프라인 상태 + 진행률 + 예상시간

    v1.1.49: task_manager 의 인메모리 상태도 병합하여 사이드바와
    GenerationTimer 게이지가 일치하도록 한다. step 2(대본), 6(렌더링)은
    Redis 가 아닌 task_manager 에서만 추적된다.
    """
    from app.services.task_manager import get_task as _get_tm_task

    project = _get_project(project_id, db)
    is_paused = _redis_get(f"pipeline:pause:{project_id}") is not None
    total_cuts = project.total_cuts or 0

    # step_num → task_manager step name 매핑
    TM_STEP_MAP = {2: "script", 3: "voice", 4: "image", 5: "video", 6: "render"}

    # Build per-step progress info (파이프라인 스텝 2~6)
    step_progress = {}
    for step_num in range(2, 7):
        step_key = str(step_num)
        state = (project.step_states or {}).get(step_key, "pending")

        # --- 1) task_manager 인메모리 상태 확인 (우선) ---
        tm_step = TM_STEP_MAP.get(step_num)
        tm = _get_tm_task(project_id, tm_step) if tm_step else None

        if tm and tm.status == "running":
            # task_manager 에 running 태스크가 있으면 그 진행률 사용
            step_progress[step_key] = {
                "state": "running",
                "completed_cuts": tm.completed,
                "total_cuts": tm.total,
                "progress_pct": tm.progress_pct,
                "eta_seconds": tm.eta_seconds,
            }
            continue

        # --- 1b) 서버 재시작 복구: DB는 running 인데 task_manager에 task 없음 ---
        # 백엔드 서버가 재시작되면 인메모리 태스크가 사라지지만 DB step_states는
        # 여전히 "running". 이 경우 자동으로 "failed"로 마킹해서 재시도 가능하게.
        if state == "running" and (tm is None or tm.status != "running"):
            from sqlalchemy.orm.attributes import flag_modified
            ss = dict(project.step_states or {})
            ss[step_key] = "failed"
            project.step_states = ss
            flag_modified(project, "step_states")
            db.commit()
            state = "failed"
            print(f"[pipeline/status] reconciled step {step_key} ({tm_step}): "
                  f"DB was 'running' but no active task → set to 'failed'")

        # --- 2) Redis pipeline progress (기존 방식, step 2~5) ---
        progress_raw = _redis_get(f"pipeline:step_progress:{project_id}:{step_num}")
        completed_cuts = int(progress_raw) if progress_raw else 0

        start_raw = _redis_get(f"pipeline:step_start:{project_id}:{step_num}")
        start_time = float(start_raw) if start_raw else 0

        # Calculate progress percentage
        if state == "completed":
            pct = 100.0
            eta_seconds = 0
        elif state == "running" and total_cuts > 0:
            pct = round((completed_cuts / total_cuts) * 100, 1)
            remaining = total_cuts - completed_cuts
            avg_per_cut = STEP_AVG_SECONDS_PER_CUT.get(step_num, 5.0)

            if start_time > 0 and completed_cuts > 0:
                elapsed = time.time() - start_time
                actual_avg = elapsed / completed_cuts
                eta_seconds = int(remaining * actual_avg)
            else:
                eta_seconds = int(remaining * avg_per_cut)
        else:
            pct = 0.0
            avg_per_cut = STEP_AVG_SECONDS_PER_CUT.get(step_num, 5.0)
            eta_seconds = int(total_cuts * avg_per_cut) if total_cuts > 0 else 0

        step_progress[step_key] = {
            "state": state,
            "completed_cuts": completed_cuts,
            "total_cuts": total_cuts,
            "progress_pct": pct,
            "eta_seconds": eta_seconds,
        }

    return {
        "status": project.status,
        "current_step": project.current_step,
        "step_states": project.step_states,
        "step_progress": step_progress,
        "is_paused": is_paused,
        "total_cuts": total_cuts,
    }


def _get_project(project_id: str, db: Session) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    return project
