"""Study plan API schemas."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from .common import ORMBase


class PlanTaskDraftSchema(BaseModel):
    date: date
    title: str = Field(..., min_length=1, max_length=200)
    description: str = ""


# Practical cap for the plan goal / imported document. Kept high so users can
# paste a full plan document; the LLM's own context limit is the real ceiling.
GOAL_MAX_CHARS = 100_000


class PlanPreviewRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    goal: str = Field("", max_length=GOAL_MAX_CHARS)
    start_date: date
    end_date: date


class PlanPreviewResponse(BaseModel):
    title: str
    goal: str
    start_date: date
    end_date: date
    tasks: list[PlanTaskDraftSchema]
    prompt_id: int | None = None
    model_id: int | None = None


class PlanCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    goal: str = Field("", max_length=GOAL_MAX_CHARS)
    start_date: date
    end_date: date
    tasks: list[PlanTaskDraftSchema] = Field(..., min_length=1)
    prompt_id: int | None = None
    model_id: int | None = None


class PlanSummary(ORMBase):
    id: int
    title: str
    goal: str | None = None
    start_date: date
    end_date: date
    status: str
    created_at: datetime
    updated_at: datetime
    done_count: int = 0
    total_count: int = 0


class PlanListResponse(BaseModel):
    items: list[PlanSummary]
    total: int
