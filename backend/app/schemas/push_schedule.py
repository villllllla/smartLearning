"""Scheduled question push schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .settings import Difficulty, QType

PushFrequency = Literal["daily", "weekdays", "weekly"]
PushMode = Literal["random", "sequential", "wrong"]
QuestionSourceKind = Literal["simulated", "interview"]


class PushScheduleRead(BaseModel):
    enabled: bool
    timezone: str
    push_times: list[str]
    frequency: PushFrequency
    weekdays: list[int] = Field(description="0=Mon .. 6=Sun")
    limit: int
    mode: PushMode
    difficulties: list[Difficulty]
    qtypes: list[QType]
    tag_ids: list[int]
    tag_mode: Literal["and", "or"]
    source_kinds: list[QuestionSourceKind] = Field(
        default_factory=list,
        description="空=不限；simulated=模拟题 interview=实战面经",
    )
    feishu_enabled: bool
    last_run_slot: str | None = None
    last_run_at: datetime | None = None
    last_error: str | None = None


class PushScheduleUpdate(BaseModel):
    enabled: bool | None = None
    timezone: str | None = None
    push_times: list[str] | None = None
    frequency: PushFrequency | None = None
    weekdays: list[int] | None = None
    limit: int | None = Field(None, ge=1, le=20)
    mode: PushMode | None = None
    difficulties: list[Difficulty] | None = None
    qtypes: list[QType] | None = None
    tag_ids: list[int] | None = None
    tag_mode: Literal["and", "or"] | None = None
    source_kinds: list[QuestionSourceKind] | None = None
    feishu_enabled: bool | None = None


class PushTriggerResponse(BaseModel):
    ok: bool
    message: str
    question_count: int = 0
    recipient_count: int = 0
