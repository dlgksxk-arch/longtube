"""PresetUsageRecord — v2.1.0 신규.

프리셋 카드의 "총 비용 / 총 제작 건수 / 예정 제작 건수" 집계용.

하나의 태스크 실행 중 여러 프로바이더 호출이 있을 수 있으므로
(대본 Anthropic, TTS ElevenLabs, 이미지 fal, 썸네일 Gemini, BGM
ElevenLabs Music, 보조 OpenAI/xAI) 호출 단위로 1 행씩 적재한다.

기존 `api_logs` 테이블은 프로젝트 단위이므로 그대로 두고, v2 에서는
프리셋/태스크 단위로 별도 기록한다.
"""
from sqlalchemy import (
    Column,
    Integer,
    Text,
    Float,
    DateTime,
    ForeignKey,
    Index,
)
from sqlalchemy.sql import func

from app.models.database import Base


class PresetUsageRecord(Base):
    __tablename__ = "preset_usage_records"

    id = Column(Integer, primary_key=True, autoincrement=True)

    preset_id = Column(
        Integer,
        ForeignKey("channel_presets.id", ondelete="SET NULL"),
        nullable=True,
    )
    task_id = Column(
        Integer,
        ForeignKey("preset_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )

    # anthropic / openai / elevenlabs / fal / xai / gemini / elevenlabs_music ...
    provider = Column(Text, nullable=False)

    cost_usd = Column(Float, nullable=False, default=0.0)

    tokens_in = Column(Integer, nullable=True)
    tokens_out = Column(Integer, nullable=True)
    # 음성 초, 이미지 장, 음악 초 등 단가 환산치.
    units = Column(Float, nullable=True)

    recorded_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_preset_usage_preset", "preset_id"),
        Index("ix_preset_usage_task", "task_id"),
        Index("ix_preset_usage_provider_time", "provider", "recorded_at"),
    )
