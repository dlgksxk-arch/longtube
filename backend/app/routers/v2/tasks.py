"""/api/v2/tasks — 실행 기록 조회.

v2.1.0 은 조회만 연다. 실제 실행 파이프라인은 v2.2.0 task_runner 에서 붙인다.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.preset_task import PresetTask


router = APIRouter()


class TaskOut(BaseModel):
    id: int
    channel_id: int
    form_type: str
    episode_no: Optional[int]
    status: str
    step_states: dict
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    estimated_sec: Optional[int]
    actual_sec: Optional[int]
    output_dir: Optional[str]

    model_config = {"from_attributes": True}


@router.get("/", response_model=list[TaskOut])
def list_tasks(
    channel_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(PresetTask)
    if channel_id is not None:
        q = q.filter(PresetTask.channel_id == channel_id)
    if status is not None:
        q = q.filter(PresetTask.status == status)
    return q.order_by(PresetTask.id.desc()).limit(200).all()


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: int, db: Session = Depends(get_db)):
    row = db.query(PresetTask).filter(PresetTask.id == task_id).first()
    if row is None:
        raise HTTPException(404, "task not found")
    return row
