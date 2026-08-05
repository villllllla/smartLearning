"""User goal schemas (PRD §15.2)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

GoalStatus = Literal["active", "achieved", "archived"]


class JobRoleSkillOut(BaseModel):
    id: int
    skill_name: str
    tag_name: str
    weight: int
    expected_mastery: int


class JobRoleOut(BaseModel):
    id: int
    name: str
    family: str
    level: str
    description: str
    is_system: bool
    skills: list[JobRoleSkillOut] = Field(default_factory=list)


class JobRoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    family: str = Field(default="", max_length=80)
    level: str = Field(default="mid", max_length=16)
    description: str = Field(default="", max_length=2000)
    skills: list[dict] = Field(
        default_factory=list,
        description="[{skill_name, tag_name, weight?, expected_mastery?}]",
    )


class UserGoalOut(BaseModel):
    id: int
    job_role_id: int
    job_role_name: str
    target_date: date | None
    status: GoalStatus
    created_at: datetime


class UserGoalCreate(BaseModel):
    job_role_id: int
    target_date: date | None = None


class UserGoalUpdate(BaseModel):
    job_role_id: int | None = None
    target_date: date | None = None
    status: GoalStatus | None = None
    clear_target_date: bool = False


class SkillProgressOut(BaseModel):
    skill_name: str
    tag_name: str
    tag_id: int | None
    weight: int
    expected_mastery: int
    mastery: int
    question_total: int
    question_attempted: int
    coverage: float
    low_coverage: bool


class WeakTagOut(BaseModel):
    tag_name: str
    tag_id: int | None
    mastery: int
    expected_mastery: int
    gap: int


class ProgressTrendPoint(BaseModel):
    computed_at: datetime
    overall_mastery: int


class GoalProgressOut(BaseModel):
    goal: UserGoalOut
    overall_mastery: int
    skills: list[SkillProgressOut]
    weak_tags: list[WeakTagOut]
    trend: list[ProgressTrendPoint] = Field(default_factory=list)
    coverage_note: str | None = None
