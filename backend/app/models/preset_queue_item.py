"""PresetQueueItem — v2.1.0 신규.

딸깍폼 큐의 한 줄. 사용자는 별도 모달(/v2/queue) 에서 채널 드롭다운,
자동 할당된 EP.XX(read-only), 주제(멀티라인 자유 입력) 을 입력한다.

EP.XX 자동 번호 규칙 (기획 문서 §11.2):
    episode_no = 1 + (
        SELECT COUNT(*) FROM preset_tasks
        WHERE channel_id = :channel AND form_type = '딸깍폼'
    )

- **채널별 독립 카운터**.
- **딸깍폼만 카운트**. 테스트폼은 EP 없음(episode_no = NULL).
- 큐 추가 시점에 확정되며 이후 변경 금지 (수동 덮어쓰기 불가).
- 큐 순서가 바뀌어도 번호는 그대로.

topic_raw: 사용자 원문 (여러 줄)
topic_polished: 첫 줄(제목 부분)을 "의미 보존 다듬기"만 적용한 결과.
    과도한 요약/재해석 금지.
"""
from sqlalchemy import (
    Column,
    Integer,
    Text,
    DateTime,
    ForeignKey,
    Index,
    CheckConstraint,
)
from sqlalchemy.sql import func

from app.models.database import Base


QUEUE_STATUS = ("pending", "scheduled", "running", "done", "failed")


class PresetQueueItem(Base):
    __tablename__ = "preset_queue_items"

    id = Column(Integer, primary_key=True, autoincrement=True)

    preset_id = Column(
        Integer,
        ForeignKey("channel_presets.id", ondelete="CASCADE"),
        nullable=False,
    )

    channel_id = Column(Integer, nullable=False)  # 1~4

    # 딸깍폼 한정. 테스트폼은 NULL.
    episode_no = Column(Integer, nullable=True)

    # 사용자 자유 입력 원문 (멀티라인).
    topic_raw = Column(Text, nullable=False)

    # 의미 보존 다듬기 결과 (첫 줄 기준). NULL 이면 아직 정제 전.
    topic_polished = Column(Text, nullable=True)

    status = Column(Text, nullable=False, default="pending")

    # 스케줄러가 할당한 실행 예정 시각. 없으면 NULL.
    scheduled_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_preset_queue_items_channel_status", "channel_id", "status"),
        Index("ix_preset_queue_items_preset", "preset_id"),
        CheckConstraint(
            "status in ('pending','scheduled','running','done','failed')",
            name="ck_preset_queue_items_status",
        ),
        CheckConstraint(
            "channel_id >= 1 AND channel_id <= 4",
            name="ck_preset_queue_items_channel_range",
        ),
    )
