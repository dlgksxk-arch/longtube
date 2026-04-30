"""Event — v2.1.0 신규.

실시간 현황 페이지(/v2/live) 의 SSE 스트림, 실패 분석, 최근 이벤트
10건 표시에 사용된다. 기획 §3.5 / §12.3.

scope 값:
    'task'   : scope_id = preset_tasks.id
    'queue'  : scope_id = preset_queue_items.id
    'system' : scope_id = NULL

level:
    'info' / 'warn' / 'error'

code 예:
    TASK_STEP_STARTED, TASK_STEP_COMPLETED, TASK_STEP_FAILED,
    TASK_DELAYED_OVER_120S, QUEUE_ITEM_ADDED, QUEUE_ITEM_POLISHED,
    SYSTEM_BOOT, API_KEY_ENCRYPTED, API_PING_OK, API_PING_FAIL,
    STORAGE_PATH_CHANGED, ...
"""
from sqlalchemy import (
    Column,
    Integer,
    Text,
    DateTime,
    JSON,
    Index,
    CheckConstraint,
)
from sqlalchemy.sql import func

from app.models.database import Base


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)

    scope = Column(Text, nullable=False)  # task / queue / system
    scope_id = Column(Integer, nullable=True)

    level = Column(Text, nullable=False, default="info")  # info/warn/error

    code = Column(Text, nullable=False)
    message = Column(Text, nullable=False, default="")

    payload = Column(JSON, nullable=True)

    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_events_scope_time", "scope", "scope_id", "created_at"),
        Index("ix_events_level_time", "level", "created_at"),
        CheckConstraint(
            "scope in ('task','queue','system')", name="ck_events_scope"
        ),
        CheckConstraint(
            "level in ('info','warn','error')", name="ck_events_level"
        ),
    )
