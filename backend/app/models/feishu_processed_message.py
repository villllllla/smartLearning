"""Persist Feishu message_id dedup across process restarts."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FeishuProcessedMessage(Base):
    __tablename__ = "feishu_processed_messages"

    message_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    event_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    text_preview: Mapped[str | None] = mapped_column(String(200), nullable=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        nullable=False,
    )
