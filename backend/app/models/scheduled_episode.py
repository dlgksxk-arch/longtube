"""ScheduledEpisode DB model — represents one automated upload slot"""
from sqlalchemy import Column, Text, Integer, DateTime, Boolean
from sqlalchemy.sql import func
from app.models.database import Base


class ScheduledEpisode(Base):
    """One row per queued episode in the daily automation queue.

    v1.1.25 변경: 날짜는 더 이상 저장하지 않는다. 대신 `scheduled_time`
    (HH:MM) 만 저장하고, 스케줄러는 "하루에 한 편"씩 episode_number
    오름차순으로 꺼내 실행한다. 즉 오늘 이미 한 편이라도 업로드됐으면
    오늘은 더 돌리지 않고, 다음날 해당 시각이 지나면 다음 pending
    에피소드를 꺼낸다. 사용자가 날짜를 매일 밀어줄 필요가 없다.
    """

    __tablename__ = "scheduled_episodes"

    id = Column(Text, primary_key=True)
    episode_number = Column(Integer, nullable=False)
    topic = Column(Text, nullable=False, default="")
    # 하루 중 실행 시각 (HH:MM, 24h). 로컬 타임존 기준.
    scheduled_time = Column(Text, nullable=False, default="09:00")

    # Template project whose config (style, voice, model choices, etc.)
    # will be copied into the generated project.
    template_project_id = Column(Text, nullable=True)

    # YouTube privacy for the resulting upload
    privacy = Column(Text, nullable=False, default="private")

    # User can toggle off without deleting
    enabled = Column(Boolean, nullable=False, default=True)

    # pending, running, uploaded, failed, skipped
    status = Column(Text, nullable=False, default="pending")

    # Populated after execution
    project_id = Column(Text, nullable=True)
    video_url = Column(Text, nullable=True)
    final_title = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
