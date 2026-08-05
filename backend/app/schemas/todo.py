"""Todo API schemas."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from .common import ORMBase


class TodoSummary(ORMBase):
    id: int
    title: str
    description: str | None = None
    status: str
    progress: int = 0
    remind_at: datetime | None = None
    timezone: str
    reminded_at: datetime | None = None
    completed_at: datetime | None = None
    plan_id: int | None = None
    long_term_id: int | None = None
    plan_date: date | None = None
    original_plan_date: date | None = None
    defer_count: int = 0
    snooze_until: date | None = None
    snooze_note: str | None = None
    channel: str | None = None
    feishu_open_id: str | None = None
    clarification_question: str | None = None
    created_at: datetime
    updated_at: datetime


class TodoDetail(TodoSummary):
    raw_input: str
    structured: dict = Field(default_factory=dict, alias="structured_json")
    clarification_context: list = Field(
        default_factory=list, alias="clarification_context_json"
    )


class TodoCreate(BaseModel):
    """Natural-language create (LLM intent parsing)."""
    raw_input: str = Field(..., min_length=1, max_length=2000)


class TodoDirectCreate(BaseModel):
    """Structured web form: date + optional time + title — no LLM."""
    title: str = Field(..., min_length=1, max_length=200)
    plan_date: date
    remind_time: str | None = Field(
        None,
        max_length=8,
        description="HH:MM local reminder; defaults to 21:00 when omitted",
    )
    description: str | None = Field(None, max_length=2000)


class TodoListResponse(BaseModel):
    items: list[TodoSummary]
    total: int


class TodoCalendarDay(BaseModel):
    date: str
    total: int
    done: int


class TodoCalendarResponse(BaseModel):
    days: list[TodoCalendarDay]
    start: str
    end: str


class TodoSnoozeRequest(BaseModel):
    until: date
    note: str | None = Field(None, max_length=500)


class TodoProgressRequest(BaseModel):
    progress: int = Field(..., ge=0, le=100)


class TodoUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    plan_date: date | None = None
    remind_time: str | None = Field(None, max_length=8)
    description: str | None = Field(None, max_length=2000)
