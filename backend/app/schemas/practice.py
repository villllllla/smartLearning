"""Practice setup + answer schemas (PRD §6.4)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .question import QuestionSummary


class PracticeSetupRequest(BaseModel):
    collection_id: int | None = None
    source_wiki_ids: list[int] = Field(default_factory=list)
    tag_ids: list[int] = Field(default_factory=list)
    tag_mode: Literal["and", "or"] = "or"
    difficulties: list[Literal["easy", "medium", "hard"]] = Field(default_factory=list)
    qtypes: list[Literal["concept", "scenario"]] = Field(default_factory=list)
    source_kinds: list[Literal["simulated", "interview"]] = Field(
        default_factory=list,
        description="空=不限；simulated=模拟题 interview=实战面经",
    )
    mode: Literal["sequential", "random", "wrong"] = "sequential"
    limit: int = Field(default=10, ge=1, le=50)
    time_limit_per_question: int | None = Field(
        default=None,
        description="每题秒数 (PRD §6.4.1: 不限/30/60/120);仅用作客户端提示",
    )


class PracticeSetupResponse(BaseModel):
    questions: list[QuestionSummary]
    time_limit_per_question: int | None = None
    total_pool: int = Field(
        default=0, description="符合筛选条件的题目总数(便于 UI 提示)"
    )


class PracticeAnswerRequest(BaseModel):
    question_id: int
    user_answer_text: str
    override_model_id: int | None = None


class PracticeAnswerResponse(BaseModel):
    attempt_id: int
    question_id: int
    grade: Literal["S", "A", "B", "C"]
    score_correctness: int
    score_completeness: int
    score_structure: int
    score_depth: int
    feedback_text: str
