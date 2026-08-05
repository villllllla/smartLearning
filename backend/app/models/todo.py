"""User todos with LLM-parsed intent, clarification flow, and Feishu reminders.

Also hosts StudyPlan (a big goal decomposed into daily todo tasks) and
TodoCheckSchedule (daily "did you plan today?" nudge).
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin

# clarifying | scheduled | reminded | snoozed | done | cancelled
TODO_STATUSES = frozenset(
    {"clarifying", "scheduled", "reminded", "snoozed", "done", "cancelled"}
)
# draft | active | done | archived
PLAN_STATUSES = frozenset({"draft", "active", "done", "archived"})
# active | paused | done | archived
LONG_TERM_STATUSES = frozenset({"active", "paused", "done", "archived"})
# daily | weekdays
LONG_TERM_SCHEDULE_MODES = frozenset({"daily", "weekdays"})


class TodoItem(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "todo_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="clarifying")
    # 0-100; 100 means done (status=done). Partial progress is web-only, not synced to Feishu.
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    remind_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Shanghai")
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Calendar / plan scheduling
    plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("study_plans.id", ondelete="SET NULL"), nullable=True, index=True
    )
    long_term_id: Mapped[int | None] = mapped_column(
        ForeignKey("long_term_todos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # The local day this task is scheduled for (drives the calendar heatmap).
    plan_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    # First scheduled day, preserved across deferrals.
    original_plan_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    defer_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Snooze / hold
    snooze_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    snooze_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    raw_input: Mapped[str] = mapped_column(Text, nullable=False, default="")
    structured_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    clarification_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    # [{role, content}] multi-turn clarification history
    clarification_context_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    channel: Mapped[str | None] = mapped_column(String(16), nullable=True)
    feishu_open_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    feishu_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    generated_by_prompt_id: Mapped[int | None] = mapped_column(
        ForeignKey("prompt_templates.id", ondelete="SET NULL"), nullable=True
    )
    generated_by_model_id: Mapped[int | None] = mapped_column(
        ForeignKey("models.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        Index("ix_todo_items_tenant_remind", "tenant_id", "remind_at"),
        Index("ix_todo_items_feishu_status", "feishu_open_id", "status"),
        Index("ix_todo_items_tenant_plan_date", "tenant_id", "plan_date"),
    )


class StudyPlan(Base, TimestampMixin, SoftDeleteMixin):
    """A big learning/work goal decomposed into dated todo tasks."""

    __tablename__ = "study_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")

    raw_input: Mapped[str] = mapped_column(Text, nullable=False, default="")
    structured_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    channel: Mapped[str | None] = mapped_column(String(16), nullable=True)
    feishu_open_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    generated_by_prompt_id: Mapped[int | None] = mapped_column(
        ForeignKey("prompt_templates.id", ondelete="SET NULL"), nullable=True
    )
    generated_by_model_id: Mapped[int | None] = mapped_column(
        ForeignKey("models.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        Index("ix_study_plans_tenant_status", "tenant_id", "status"),
    )


class LongTermTodo(Base, TimestampMixin, SoftDeleteMixin):
    """A recurring daily task over a date range (e.g. one LeetCode problem per day)."""

    __tablename__ = "long_term_todos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    remind_time: Mapped[str] = mapped_column(String(8), nullable=False, default="21:00")
    # daily = every day in range; weekdays = Mon–Fri only
    schedule_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="daily")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")

    __table_args__ = (
        Index("ix_long_term_todos_tenant_status", "tenant_id", "status"),
    )


class TodoCheckSchedule(Base, TimestampMixin):
    """Daily 'did you plan for today?' nudge + today's plan push (Feishu)."""

    __tablename__ = "todo_check_schedules"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_todo_check_schedule_tenant"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="Asia/Shanghai"
    )
    check_time: Mapped[str] = mapped_column(String(8), nullable=False, default="08:00")
    # Also push today's plan list (not just the empty-day nudge).
    push_today_plan: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    feishu_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_run_slot: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
