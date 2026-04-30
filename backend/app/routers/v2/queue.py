"""/api/v2/queue — 딸깍/테스트폼 큐.

기획 §11 대응. Option A 자유 입력 멀티라인 textarea 를 그대로 저장한다.
EP.XX 자동 번호 규칙(§11.2):
    episode_no = 1 + COUNT(preset_tasks WHERE channel_id=:ch AND form_type='딸깍폼')
 - 큐 추가 시점에 확정. 수동 덮어쓰기 불가.
 - 딸깍폼만 카운트. 테스트폼은 episode_no NULL.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.channel_preset import (
    ChannelPreset,
    FORM_TYPE_DDALKKAK,
)
from app.models.preset_queue_item import PresetQueueItem
from app.models.preset_task import PresetTask


router = APIRouter()


class QueueItemOut(BaseModel):
    id: int
    preset_id: int
    channel_id: int
    episode_no: Optional[int]
    topic_raw: str
    topic_polished: Optional[str]
    status: str
    scheduled_at: Optional[datetime]
    created_at: Optional[datetime]

    model_config = {"from_attributes": True}


class QueueAddBody(BaseModel):
    preset_id: int
    topic_raw: str = Field(min_length=1, max_length=20000)


class QueueScheduleBody(BaseModel):
    """미래 실행 시각을 지정/해제한다.

    - `scheduled_at` 이 주어지면 해당 시각으로 설정하고 status 가
      'pending' 이면 'scheduled' 로 승격.
    - `scheduled_at=None` 이면 예약 해제. status 가 'scheduled' 였으면
      'pending' 으로 환원. 그 외 상태('running', 'done', 'failed') 는
      그대로 둔다.
    """

    scheduled_at: Optional[datetime] = None


class EpisodePreviewOut(BaseModel):
    channel_id: int
    next_episode_no: int


def _next_episode_no(db: Session, channel_id: int) -> int:
    count = (
        db.query(PresetTask)
        .filter(
            PresetTask.channel_id == channel_id,
            PresetTask.form_type == FORM_TYPE_DDALKKAK,
        )
        .count()
    )
    return count + 1


@router.get("/preview-episode/{channel_id}", response_model=EpisodePreviewOut)
def preview_episode(channel_id: int, db: Session = Depends(get_db)):
    """UI 모달이 채널 드롭다운 선택 직후 read-only 표시용으로 호출."""
    if channel_id < 1 or channel_id > 4:
        raise HTTPException(400, "channel_id out of range")
    return EpisodePreviewOut(
        channel_id=channel_id, next_episode_no=_next_episode_no(db, channel_id)
    )


@router.get("/", response_model=list[QueueItemOut])
def list_queue(
    channel_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(PresetQueueItem)
    if channel_id is not None:
        q = q.filter(PresetQueueItem.channel_id == channel_id)
    if status is not None:
        q = q.filter(PresetQueueItem.status == status)
    return q.order_by(PresetQueueItem.created_at.asc()).all()


@router.post("/", response_model=QueueItemOut, status_code=201)
def add_to_queue(body: QueueAddBody, db: Session = Depends(get_db)):
    preset = (
        db.query(ChannelPreset).filter(ChannelPreset.id == body.preset_id).first()
    )
    if preset is None:
        raise HTTPException(404, "preset not found")

    episode_no: Optional[int] = None
    if preset.form_type == FORM_TYPE_DDALKKAK:
        episode_no = _next_episode_no(db, preset.channel_id)

    row = PresetQueueItem(
        preset_id=preset.id,
        channel_id=preset.channel_id,
        episode_no=episode_no,
        topic_raw=body.topic_raw,
        status="pending",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/{item_id}/schedule", response_model=QueueItemOut)
def set_schedule(
    item_id: int, body: QueueScheduleBody, db: Session = Depends(get_db)
):
    """큐 항목의 `scheduled_at` 을 설정하거나 해제한다.

    실행 중/완료/실패 항목은 예약 변경을 거부한다 — 의미가 없기 때문.
    """
    row = db.query(PresetQueueItem).filter(PresetQueueItem.id == item_id).first()
    if row is None:
        raise HTTPException(404, "queue item not found")
    if row.status in ("running", "done", "failed"):
        raise HTTPException(
            409,
            f"queue item in status '{row.status}' cannot be rescheduled",
        )
    row.scheduled_at = body.scheduled_at
    if body.scheduled_at is not None and row.status == "pending":
        row.status = "scheduled"
    elif body.scheduled_at is None and row.status == "scheduled":
        row.status = "pending"
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{item_id}", status_code=204)
def remove_from_queue(item_id: int, db: Session = Depends(get_db)):
    row = db.query(PresetQueueItem).filter(PresetQueueItem.id == item_id).first()
    if row is None:
        raise HTTPException(404, "queue item not found")
    db.delete(row)
    db.commit()
    return None
