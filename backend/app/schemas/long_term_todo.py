"""Long-term todo API schemas."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from .common import ORMBase


class LongTermTodoCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    start_date: date
    end_date: date
    remind_time: str = Field("21:00", max_length=8)
    schedule_mode: Literal["daily", "weekdays"] = "daily"


class LongTermTodoUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    start_date: date | None = None
    end_date: date | None = None
    remind_time: str | None = Field(None, max_length=8)
    schedule_mode: Literal["daily", "weekdays"] | None = None
    status: Literal["active", "paused", "done", "archived"] | None = None


class LongTermTodoSummary(ORMBase):
    id: int
    title: str
    description: str | None = None
    start_date: date
    end_date: date
    remind_time: str
    schedule_mode: str
    status: str
    created_at: datetime
    updated_at: datetime
    done_count: int = 0
    total_count: int = 0


class LongTermTodoListResponse(BaseModel):
    items: list[LongTermTodoSummary]
    total: int
