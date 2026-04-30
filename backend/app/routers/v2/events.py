"""/api/v2/events — 이벤트 피드.

기획 §12.3 의 SSE 스트림은 v2.3.0 에서 추가된다. v2.1.0 은 최근 10건
폴링 조회만 제공.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.event import Event


router = APIRouter()


class EventOut(BaseModel):
    id: int
    scope: str
    scope_id: Optional[int]
    level: str
    code: str
    message: str
    payload: Optional[dict]
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/", response_model=list[EventOut])
def list_events(
    scope: Optional[str] = None,
    level: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    q = db.query(Event)
    if scope is not None:
        q = q.filter(Event.scope == scope)
    if level is not None:
        q = q.filter(Event.level == level)
    limit = max(1, min(limit, 500))
    return q.order_by(Event.id.desc()).limit(limit).all()
