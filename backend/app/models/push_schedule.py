"""Scheduled interview question push (Feishu + future channels)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class QuestionPushSchedule(Base, TimestampMixin):
    __tablename__ = "question_push_schedules"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_push_schedule_tenant"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Shanghai")
    # ["09:00", "18:30"] local times in `timezone`
    push_times: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # daily | weekdays | weekly
    frequency: Mapped[str] = mapped_column(String(16), nullable=False, default="daily")
    # For weekly: 0=Mon .. 6=Sun (ISO weekday - 1)
    weekdays: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    limit: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="random")
    difficulties: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    qtypes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    tag_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    tag_mode: Mapped[str] = mapped_column(String(8), nullable=False, default="or")
    # [] = all kinds; otherwise subset of simulated / interview
    source_kinds: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    feishu_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Dedupe key e.g. "2026-06-01T09:00"
    last_run_slot: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
