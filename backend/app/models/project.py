"""Project DB model"""
from sqlalchemy import Column, Text, Integer, Float, DateTime, JSON
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.sql import func
from app.models.database import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(Text, primary_key=True)
    title = Column(Text, nullable=False, default="Untitled")
    topic = Column(Text, nullable=False)
    # v1.1.29: config/step_states 는 dict 내부 mutation 을 SQLAlchemy 가 감지할 수 있도록
    # MutableDict 로 감싼다. 이렇게 하지 않으면 image reference/character/logo 업로드처럼
    # `project.config["key"] = value` 후 `db.commit()` 해도 DB 에 반영되지 않는 치명적 버그가 발생한다.
    config = Column(MutableDict.as_mutable(JSON), nullable=False, default=dict)
    status = Column(Text, default="draft")  # draft, processing, paused, completed, failed
    current_step = Column(Integer, default=0)
    step_states = Column(MutableDict.as_mutable(JSON), default=dict)  # {"2":"completed","3":"paused",...}
    total_cuts = Column(Integer, default=0)
    youtube_url = Column(Text, nullable=True)
    api_cost = Column(Float, default=0.0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
