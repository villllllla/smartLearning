"""Per-user state for IM bot integrations (Feishu, etc.)."""
from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class BotSession(Base, TimestampMixin):
    __tablename__ = "bot_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, default="feishu")
    feishu_open_id: Mapped[str] = mapped_column(String(128), nullable=False)
    feishu_chat_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # JSON list[int] — question ids in current quiz queue
    question_queue_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    queue_cursor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_question_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    smartlearning_chat_id: Mapped[int | None] = mapped_column(
        ForeignKey("chats.id", ondelete="SET NULL"), nullable=True
    )

    last_event_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    __table_args__ = (
        Index("ix_bot_sessions_platform_open_id", "platform", "feishu_open_id", unique=True),
    )
