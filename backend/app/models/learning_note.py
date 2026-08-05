"""Daily learning notes: raw input + LLM-validated structured content + spaced review."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin


class LearningNote(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "learning_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Original user input, stored verbatim.
    raw_input: Mapped[str] = mapped_column(Text, nullable=False)

    # LLM-structured fields
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    key_points_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # Full raw structured payload from the model (forward-compatible).
    structured_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # Validation / "检验": {"issues": [...], "corrections": [...], "suggestions": [...]}
    review_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    quality_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Spaced repetition state
    mastered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    interval_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_review_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_pushed_slot: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Provenance
    channel: Mapped[str | None] = mapped_column(String(16), nullable=True)  # feishu / web
    feishu_open_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    feishu_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    generated_by_prompt_id: Mapped[int | None] = mapped_column(
        ForeignKey("prompt_templates.id", ondelete="SET NULL"), nullable=True
    )
    generated_by_model_id: Mapped[int | None] = mapped_column(
        ForeignKey("models.id", ondelete="SET NULL"), nullable=True
    )

    tags: Mapped[list["Tag"]] = relationship(  # noqa: F821
        secondary="learning_note_tags",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_learning_notes_tenant_next_review", "tenant_id", "next_review_at"),
        Index("ix_learning_notes_tenant_created", "tenant_id", "created_at"),
    )


class LearningNoteTag(Base):
    __tablename__ = "learning_note_tags"

    note_id: Mapped[int] = mapped_column(
        ForeignKey("learning_notes.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )


class LearningReviewSchedule(Base, TimestampMixin):
    """When to check for due learning notes and push them for review (Feishu)."""

    __tablename__ = "learning_review_schedules"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_learning_review_schedule_tenant"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="Asia/Shanghai"
    )
    # ["08:00"] local times in `timezone`
    push_times: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # daily | weekdays | weekly
    frequency: Mapped[str] = mapped_column(String(16), nullable=False, default="daily")
    weekdays: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Spaced repetition intervals in days; index advances each successful review.
    intervals_days: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    max_notes_per_push: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    # "已掌握" de-prioritises instead of stopping: its interval is multiplied by
    # this factor and it queues behind still-learning notes.
    mastered_factor: Mapped[float] = mapped_column(Float, nullable=False, default=3.0)
    # active recall: push title/question first, reveal key points on demand
    recall_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    feishu_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_run_slot: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
