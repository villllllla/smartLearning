"""AppSettings: a single-row table for user preferences (PRD §6.5).

Why singleton-row instead of EAV: this is local single-user MVP; one row keeps
the access pattern trivial and migrations explicit. The well-known id=1 is
seeded by the 0002 migration so the API never needs to special-case absence.
"""
from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AppSettings(Base, TimestampMixin):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    # Practice defaults (PRD §6.4.1, §6.4.3)
    practice_default_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10
    )
    practice_time_limit_per_question: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # null = 不限
    practice_default_difficulties: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    practice_default_qtypes: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    practice_history_keep_n: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10
    )

    # Appearance
    appearance_theme: Mapped[str] = mapped_column(
        String(16), nullable=False, default="system"
    )  # light | dark | system
    appearance_locale: Mapped[str] = mapped_column(
        String(16), nullable=False, default="zh-CN"
    )

    # Global IANA timezone for todos, schedules, and display
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="Asia/Shanghai"
    )
    # Global LLM fallback when per-scene primary / scene-fallback both fail
    llm_fallback_model_id: Mapped[int | None] = mapped_column(
        ForeignKey("models.id", ondelete="SET NULL"), nullable=True
    )
