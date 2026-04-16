"""Cut (scene) DB model"""
from sqlalchemy import Column, Text, Integer, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.models.database import Base


class Cut(Base):
    __tablename__ = "cuts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Text, ForeignKey("projects.id"), nullable=False)
    cut_number = Column(Integer, nullable=False)
    narration = Column(Text)
    image_prompt = Column(Text)
    scene_type = Column(Text)  # title, narration, transition, ending
    audio_path = Column(Text)
    audio_duration = Column(Float)
    image_path = Column(Text)
    image_model = Column(Text)
    video_path = Column(Text)
    video_model = Column(Text)
    status = Column(Text, default="pending")  # pending, generating, completed, failed
    is_custom_image = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
