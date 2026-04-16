"""스케줄 CRUD + 실행 제어 라우터.

엔드포인트:
- GET    /api/schedule               전체 목록
- POST   /api/schedule                한 건 생성/업서트 (episode_number 기준)
- PUT    /api/schedule/{id}           한 건 수정
- DELETE /api/schedule/{id}           한 건 삭제
- POST   /api/schedule/bulk           17행 한 번에 저장 (UI 에서 일괄 저장)
- POST   /api/schedule/{id}/run       지금 실행
- POST   /api/schedule/{id}/reset     실패/완료 상태 → pending 으로 되돌림
- GET    /api/schedule/status         스케줄러 루프 동작 여부
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.scheduled_episode import ScheduledEpisode
from app.services import scheduler_service

router = APIRouter()


_HHMM_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _validate_hhmm(v: str) -> str:
    v = (v or "").strip()
    if not _HHMM_RE.match(v):
        raise ValueError("scheduled_time 은 HH:MM (24h) 포맷이어야 합니다.")
    return v


# ─── Pydantic 스키마 ────────────────────────────────────────────


class ScheduleItemIn(BaseModel):
    episode_number: int = Field(..., ge=1, le=999)
    topic: str = ""
    scheduled_time: str = "09:00"   # HH:MM (24h, 로컬 시간)
    template_project_id: Optional[str] = None
    privacy: str = "private"
    enabled: bool = True

    @field_validator("scheduled_time")
    @classmethod
    def _check_time(cls, v: str) -> str:
        return _validate_hhmm(v)


class ScheduleItemUpdate(BaseModel):
    topic: Optional[str] = None
    scheduled_time: Optional[str] = None
    template_project_id: Optional[str] = None
    privacy: Optional[str] = None
    enabled: Optional[bool] = None
    status: Optional[str] = None  # 수동으로 pending 으로 되돌릴 때 등

    @field_validator("scheduled_time")
    @classmethod
    def _check_time(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _validate_hhmm(v)


class ScheduleBulkIn(BaseModel):
    items: list[ScheduleItemIn]
    # True 면 기존 데이터 전부 지우고 이걸로 교체. False 면 upsert.
    replace_all: bool = False


def _to_dict(ep: ScheduledEpisode) -> dict:
    return {
        "id": ep.id,
        "episode_number": ep.episode_number,
        "topic": ep.topic or "",
        "scheduled_time": ep.scheduled_time or "09:00",
        "template_project_id": ep.template_project_id,
        "privacy": ep.privacy,
        "enabled": bool(ep.enabled),
        "status": ep.status,
        "project_id": ep.project_id,
        "video_url": ep.video_url,
        "final_title": ep.final_title,
        "error_message": ep.error_message,
        "started_at": ep.started_at.isoformat() if ep.started_at else None,
        "finished_at": ep.finished_at.isoformat() if ep.finished_at else None,
        "created_at": str(ep.created_at) if ep.created_at else None,
        "updated_at": str(ep.updated_at) if ep.updated_at else None,
    }


# ─── 조회 ──────────────────────────────────────────────────────


@router.get("")
def list_schedule(db: Session = Depends(get_db)):
    items = (
        db.query(ScheduledEpisode)
        .order_by(ScheduledEpisode.episode_number.asc())
        .all()
    )
    return [_to_dict(it) for it in items]


@router.get("/status")
def scheduler_status():
    return {
        "running": scheduler_service.is_running(),
        "poll_interval_seconds": scheduler_service.POLL_INTERVAL,
    }


@router.get("/{episode_id}")
def get_episode(episode_id: str, db: Session = Depends(get_db)):
    ep = db.query(ScheduledEpisode).filter(ScheduledEpisode.id == episode_id).first()
    if not ep:
        raise HTTPException(404, "스케줄 항목을 찾을 수 없습니다.")
    return _to_dict(ep)


# ─── 생성 / 수정 / 삭제 ──────────────────────────────────────────


def _validate_privacy(p: str) -> str:
    p = (p or "private").strip().lower()
    if p not in {"private", "unlisted", "public"}:
        raise HTTPException(422, "privacy 는 private/unlisted/public 중 하나여야 합니다.")
    return p


@router.post("")
def create_episode(body: ScheduleItemIn, db: Session = Depends(get_db)):
    privacy = _validate_privacy(body.privacy)

    # episode_number 가 이미 있으면 덮어쓴다 (upsert).
    existing = (
        db.query(ScheduledEpisode)
        .filter(ScheduledEpisode.episode_number == body.episode_number)
        .first()
    )
    if existing:
        existing.topic = body.topic or ""
        existing.scheduled_time = body.scheduled_time
        existing.template_project_id = body.template_project_id
        existing.privacy = privacy
        existing.enabled = body.enabled
        # 사용자가 다시 저장하면 상태 리셋 (완료/실패 → pending)
        if existing.status in ("failed", "uploaded", "skipped"):
            existing.status = "pending"
            existing.error_message = None
        db.commit()
        return _to_dict(existing)

    ep = ScheduledEpisode(
        id=str(uuid.uuid4())[:12],
        episode_number=body.episode_number,
        topic=body.topic or "",
        scheduled_time=body.scheduled_time,
        template_project_id=body.template_project_id,
        privacy=privacy,
        enabled=body.enabled,
        status="pending",
    )
    db.add(ep)
    db.commit()
    return _to_dict(ep)


@router.put("/{episode_id}")
def update_episode(
    episode_id: str,
    body: ScheduleItemUpdate,
    db: Session = Depends(get_db),
):
    ep = db.query(ScheduledEpisode).filter(ScheduledEpisode.id == episode_id).first()
    if not ep:
        raise HTTPException(404, "스케줄 항목을 찾을 수 없습니다.")

    if body.topic is not None:
        ep.topic = body.topic
    if body.scheduled_time is not None:
        ep.scheduled_time = body.scheduled_time
    if body.template_project_id is not None:
        ep.template_project_id = body.template_project_id or None
    if body.privacy is not None:
        ep.privacy = _validate_privacy(body.privacy)
    if body.enabled is not None:
        ep.enabled = body.enabled
    if body.status is not None:
        if body.status not in ("pending", "skipped"):
            raise HTTPException(
                422,
                "status 는 pending/skipped 로만 수동 변경할 수 있습니다.",
            )
        ep.status = body.status
        if body.status == "pending":
            ep.error_message = None

    db.commit()
    return _to_dict(ep)


@router.delete("/{episode_id}")
def delete_episode(episode_id: str, db: Session = Depends(get_db)):
    ep = db.query(ScheduledEpisode).filter(ScheduledEpisode.id == episode_id).first()
    if not ep:
        raise HTTPException(404, "스케줄 항목을 찾을 수 없습니다.")
    db.delete(ep)
    db.commit()
    return {"status": "deleted", "id": episode_id}


@router.post("/bulk")
def bulk_upsert(body: ScheduleBulkIn, db: Session = Depends(get_db)):
    """17행짜리 테이블을 통째로 저장. episode_number 가 동일한 행은 덮어쓴다."""
    if body.replace_all:
        db.query(ScheduledEpisode).delete()
        db.commit()

    out: list[dict] = []
    for item in body.items:
        privacy = _validate_privacy(item.privacy)
        existing = (
            db.query(ScheduledEpisode)
            .filter(ScheduledEpisode.episode_number == item.episode_number)
            .first()
        )
        if existing:
            existing.topic = item.topic or ""
            existing.scheduled_time = item.scheduled_time
            existing.template_project_id = item.template_project_id
            existing.privacy = privacy
            existing.enabled = item.enabled
            if existing.status in ("failed", "uploaded", "skipped"):
                existing.status = "pending"
                existing.error_message = None
            out.append(_to_dict(existing))
        else:
            ep = ScheduledEpisode(
                id=str(uuid.uuid4())[:12],
                episode_number=item.episode_number,
                topic=item.topic or "",
                scheduled_time=item.scheduled_time,
                template_project_id=item.template_project_id,
                privacy=privacy,
                enabled=item.enabled,
                status="pending",
            )
            db.add(ep)
            out.append(_to_dict(ep))
    db.commit()
    return {"items": out, "count": len(out)}


# ─── 실행 제어 ──────────────────────────────────────────────────


@router.post("/{episode_id}/run")
async def run_now(episode_id: str, background: BackgroundTasks, db: Session = Depends(get_db)):
    """수동 트리거. 파이프라인이 오래 걸리므로 BackgroundTasks 로 던지고
    바로 202 성격의 응답을 돌려준다.
    """
    ep = db.query(ScheduledEpisode).filter(ScheduledEpisode.id == episode_id).first()
    if not ep:
        raise HTTPException(404, "스케줄 항목을 찾을 수 없습니다.")
    if ep.status == "running":
        raise HTTPException(409, "이미 실행 중입니다.")

    # BackgroundTasks 는 sync/async 둘 다 받지만 coroutine 을 직접 던지면
    # anyio 가 알아서 await 해준다.
    background.add_task(scheduler_service.run_episode_now, episode_id)

    return {"status": "queued", "id": episode_id}


@router.post("/{episode_id}/reset")
def reset_episode(episode_id: str, db: Session = Depends(get_db)):
    """failed/uploaded 상태를 pending 으로 되돌려 재시도할 수 있게 한다."""
    ep = db.query(ScheduledEpisode).filter(ScheduledEpisode.id == episode_id).first()
    if not ep:
        raise HTTPException(404, "스케줄 항목을 찾을 수 없습니다.")
    if ep.status == "running":
        raise HTTPException(409, "실행 중에는 리셋할 수 없습니다.")
    ep.status = "pending"
    ep.error_message = None
    ep.started_at = None
    ep.finished_at = None
    db.commit()
    return _to_dict(ep)
