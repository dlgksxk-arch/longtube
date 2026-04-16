"""API usage log model"""
from sqlalchemy import Column, Text, Integer, Float, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.models.database import Base


class ApiLog(Base):
    __tablename__ = "api_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Text, ForeignKey("projects.id"), nullable=True)
    service = Column(Text, nullable=False)  # claude, gpt, elevenlabs, flux, kling, youtube
    model = Column(Text)
    endpoint = Column(Text)
    cost_usd = Column(Float, default=0.0)
    tokens_used = Column(Integer)
    duration_ms = Column(Integer)
    status = Column(Text)  # success, failed
    created_at = Column(DateTime, server_default=func.now())
