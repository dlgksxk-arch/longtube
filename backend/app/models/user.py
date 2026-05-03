"""Application users for local LongTube access control."""
from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, String, func

from app.models.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String, unique=True, index=True, nullable=False)
    display_name = Column(String, nullable=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="user")  # master | admin | user
    status = Column(String, nullable=False, default="pending")  # pending | approved | rejected | disabled
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
