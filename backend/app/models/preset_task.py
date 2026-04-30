"""PresetTask — v2.1.0 신규.

큐 한 줄(preset_queue_items) 이 실제 실행될 때 생성되는 실행 기록.

단계별 진행 상태는 `step_states` JSON 한 곳에 모인다.
    예) {"script":"completed","image":"running","bgm":"pending",
         "video":"pending","thumbnail":"pending","upload":"pending"}

output_dir 규약 (기획 §4.2):
    f"{DATA_DIR}/tasks/{task_id}/"
    하위에 script/, audio/, images/, subtitle/, video/, thumbnail/,
    upload/ 가 생긴다.

form_type 컬럼은 "EP.XX 카운트용" 플래그다. 딸깍폼만 episode_no
를 가지며, COUNT(*) WHERE form_type='딸깍폼' 으로 다음 번호를 계산한다
(기획 §11.2).
"""
from sqlalchemy import (
    Column,
    Integer,
    Text,
    DateTime,
    JSON,
    ForeignKey,
    Index,
    CheckConstraint,
)
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.sql import func

from app.models.database import Base


TASK_STATUS = (
    "queued",
    "running",
    "paused",
    "completed",
    "failed",
    "cancelled",
)


class PresetTask(Base):
    __tablename__ = "preset_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)

    queue_item_id = Column(
        Integer,
        ForeignKey("preset_queue_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    preset_id = Column(
        Integer,
        ForeignKey("channel_presets.id", ondelete="SET NULL"),
        nullable=True,
    )

    # 카운트/필터용으로 중복 저장 (큐/프리셋이 지워져도 보존).
    channel_id = Column(Integer, nullable=False)
    form_type = Column(Text, nullable=False)  # '딸깍폼' / '테스트폼'
    episode_no = Column(Integer, nullable=True)  # 딸깍폼만 사용

    status = Column(Text, nullable=False, default="queued")

    # 단계별 상태 dict. MutableDict 로 in-place mutation 감지.
    step_states = Column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )

    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)

    # 예산 시간(초) — 로그 카드에 항상 표시 (기획 §12.2).
    estimated_sec = Column(Integer, nullable=True)
    # 실제 소요 시간(초) — 완료 시각 기준.
    actual_sec = Column(Integer, nullable=True)

    output_dir = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        # 채널별 EP 카운트 쿼리 최적화 (기획 §11.2).
        Index(
            "ix_preset_tasks_channel_form_ep",
            "channel_id",
            "form_type",
            "episode_no",
        ),
        Index("ix_preset_tasks_status", "status"),
        CheckConstraint(
            "status in ('queued','running','paused','completed','failed','cancelled')",
            name="ck_preset_tasks_status",
        ),
        CheckConstraint(
            "channel_id >= 1 AND channel_id <= 4",
            name="ck_preset_tasks_channel_range",
        ),
        CheckConstraint(
            "form_type in ('딸깍폼','테스트폼')",
            name="ck_preset_tasks_form_type",
        ),
    )
