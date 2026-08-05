"""Question / Candidate / Bank API schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .common import ORMBase

QuestionSourceKind = Literal["simulated", "interview"]


# ---- Bank collection -------------------------------------------------------


class BankCollectionSummary(ORMBase):
    id: int
    name: str
    parent_id: int | None
    created_at: datetime


# ---- Candidate -------------------------------------------------------------


class CandidatePayload(BaseModel):
    """Free-form per-question payload (matches generation schema)."""

    question: str
    answer: str
    tag: list[str] = Field(default_factory=list)
    difficulty: str = "medium"
    type: str = "concept"
    origin: str = ""


class CandidateSummary(ORMBase):
    id: int
    batch_id: str
    payload_json: dict
    picked: bool
    edited: bool
    source_wiki_id: int | None
    source_commit_id: int | None
    generated_by_prompt_id: int | None
    generated_by_model_id: int | None
    created_at: datetime


class CandidateUpdate(BaseModel):
    payload_json: dict | None = None
    picked: bool | None = None


# ---- Generate request/response --------------------------------------------


class GenerateRequest(BaseModel):
    # n=None → 自动:由模型按内容决定题量(下限 3 ，上限 max_n)
    n: int | None = Field(default=None, ge=1, le=50)
    # 自动模式下的硬上限保护;固定模式时仅作为提示展示,不会改变 n
    max_n: int = Field(default=30, ge=3, le=50)
    model_id: int | None = None
    replace_existing: bool = Field(
        default=False,
        description="为 true 时先删除该 Wiki 已入库题目与未提交候选,再重新生成",
    )


class CandidateBatchSummary(BaseModel):
    batch_id: str
    count: int
    created_at: datetime
    source_wiki_id: int | None = None
    source_wiki_title: str | None = None


class GenerateResponse(BaseModel):
    batch_id: str
    raw_count: int
    candidates: list[CandidateSummary]
    replaced_bank_questions: int = 0
    replaced_candidates: int = 0


class BulkGenerateRequest(BaseModel):
    wiki_ids: list[int] = Field(..., min_length=1, max_length=5)
    n: int | None = Field(default=None, ge=1, le=50)
    max_n: int = Field(default=30, ge=3, le=50)
    model_id: int | None = None
    replace_existing: bool = Field(
        default=True,
        description="批量生成时默认先清理各 Wiki 已有题目/候选",
    )


class BulkGenerateItemResult(BaseModel):
    wiki_id: int
    wiki_title: str
    success: bool
    batch_id: str | None = None
    raw_count: int = 0
    replaced_bank_questions: int = 0
    replaced_candidates: int = 0
    error: str | None = None


class BulkGenerateResponse(BaseModel):
    results: list[BulkGenerateItemResult]
    success_count: int
    fail_count: int


class CommitRequest(BaseModel):
    target_collection_id: int | None = None
    pick_all: bool = Field(
        default=False,
        description="为 true 时将该批次全部候选视为已勾选再入库(避免前端逐条勾选竞态)",
    )


class CommitResponse(BaseModel):
    saved: int
    remaining: int


class BulkCommitRequest(BaseModel):
    batch_ids: list[str] = Field(..., min_length=1, max_length=100)
    target_collection_id: int | None = None
    pick_all: bool = True


class BulkCommitItemResult(BaseModel):
    batch_id: str
    saved: int
    remaining: int


class BulkCommitResponse(BaseModel):
    total_saved: int
    total_remaining: int
    batches_done: int
    results: list[BulkCommitItemResult]


# ---- Question (bank list) --------------------------------------------------


class TagSummary(ORMBase):
    id: int
    name: str


class QuestionSummary(ORMBase):
    id: int
    collection_id: int | None
    question_text: str
    answer_standard: str
    difficulty: str
    qtype: str
    source_kind: QuestionSourceKind = "simulated"
    interview_answer_status: str | None = None
    source_wiki_id: int | None
    source_wiki_title: str | None = None
    source_commit_id: int | None
    source_anchor: str | None = None
    generated_by_prompt_id: int | None
    generated_by_model_id: int | None
    created_at: datetime
    updated_at: datetime
    tags: list[TagSummary] = Field(default_factory=list)
    last_grade: str | None = None
    last_attempt_at: datetime | None = None
    attempt_count: int = 0


class InterviewImportResponse(BaseModel):
    parsed: int
    imported: int
    skipped_duplicates: int
    doc_name: str
    message: str
    answer_job_id: str | None = None
    answers_queued: int = 0


class InterviewAnswerJobRead(BaseModel):
    job_id: str
    doc_name: str
    status: str
    total: int
    pack_count: int = 0
    completed_count: int
    failed_count: int
    cursor: int
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class AttemptSummary(ORMBase):
    id: int
    question_id: int
    user_answer_text: str
    grade: str
    score_correctness: int
    score_completeness: int
    score_structure: int
    score_depth: int
    feedback_text: str
    model_id: int | None
    prompt_template_id: int | None
    channel: str | None = None
    feishu_open_id: str | None = None
    created_at: datetime
