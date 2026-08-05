"""Learning note + spaced review schedule schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .common import ORMBase
from .question import TagSummary

ReviewFrequency = Literal["daily", "weekdays", "weekly"]


class LearningNoteCreate(BaseModel):
    raw_input: str = Field(..., min_length=1, max_length=20000)
    # Optional manual tags to merge with model-suggested ones.
    extra_tags: list[str] = Field(default_factory=list)


class LearningNoteUpdate(BaseModel):
    title: str | None = None
    summary: str | None = None
    key_points: list[str] | None = None
    category: str | None = None
    tags: list[str] | None = None
    mastered: bool | None = None


class LearningNoteReview(ORMBase):
    """Validation result block from the model."""

    issues: list[str] = Field(default_factory=list)
    corrections: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class LearningNoteSummary(ORMBase):
    id: int
    title: str
    summary: str
    key_points: list[str] = Field(default_factory=list, validation_alias="key_points_json")
    category: str | None = None
    quality_score: int | None = None
    mastered: bool
    review_count: int
    interval_index: int
    next_review_at: datetime | None = None
    last_reviewed_at: datetime | None = None
    channel: str | None = None
    created_at: datetime
    updated_at: datetime
    tags: list[TagSummary] = Field(default_factory=list)

    model_config = {"populate_by_name": True, "from_attributes": True}


class LearningNoteDetail(LearningNoteSummary):
    raw_input: str
    review: dict = Field(default_factory=dict, validation_alias="review_json")
    structured: dict = Field(default_factory=dict, validation_alias="structured_json")


class LearningNoteListResponse(BaseModel):
    items: list[LearningNoteSummary]
    total: int
    due_today: int


# ---- Review schedule -------------------------------------------------------


class ReviewScheduleRead(BaseModel):
    enabled: bool
    timezone: str
    push_times: list[str]
    frequency: ReviewFrequency
    weekdays: list[int] = Field(description="0=Mon .. 6=Sun")
    intervals_days: list[int]
    max_notes_per_push: int
    mastered_factor: float = Field(
        description="已掌握后的间隔倍数（1 = 不降权，仍会推送，只是更稀疏）"
    )
    recall_mode: bool
    feishu_enabled: bool
    last_run_slot: str | None = None
    last_run_at: datetime | None = None
    last_error: str | None = None


class ReviewScheduleUpdate(BaseModel):
    enabled: bool | None = None
    timezone: str | None = None
    push_times: list[str] | None = None
    frequency: ReviewFrequency | None = None
    weekdays: list[int] | None = None
    intervals_days: list[int] | None = None
    max_notes_per_push: int | None = Field(None, ge=1, le=20)
    mastered_factor: float | None = Field(None, ge=1.0, le=20.0)
    recall_mode: bool | None = None
    feishu_enabled: bool | None = None


class ReviewTriggerResponse(BaseModel):
    ok: bool
    message: str
    note_count: int = 0
    recipient_count: int = 0
