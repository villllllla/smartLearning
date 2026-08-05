"""Todo daily-check schedule schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .common import ORMBase


class TodoCheckRead(ORMBase):
    enabled: bool
    timezone: str
    check_time: str
    push_today_plan: bool
    feishu_enabled: bool
    last_run_at: datetime | None = None
    last_error: str | None = None


class TodoCheckUpdate(BaseModel):
    enabled: bool | None = None
    timezone: str | None = Field(None, max_length=64)
    check_time: str | None = Field(None, max_length=8)
    push_today_plan: bool | None = None
    feishu_enabled: bool | None = None


class TodoCheckTriggerResponse(BaseModel):
    message: str
    recipients: int
