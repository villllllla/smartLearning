"""Wiki API schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .common import ORMBase


class WikiSummary(ORMBase):
    id: int
    title: str
    collection_id: int | None = None
    current_main_commit_id: int | None = None
    word_count: int = 0
    excerpt: str | None = None
    updated_at: datetime
    created_at: datetime
    bank_question_count: int = 0
    pending_candidate_count: int = 0  # 最新一批，与候选预览页一致
    pending_candidate_total: int = 0  # 该文档全部未入库候选
    pending_batch_count: int = 0
    pending_batch_id: str | None = None

    @property
    def has_generated_questions(self) -> bool:
        return (
            self.bank_question_count > 0
            or self.pending_candidate_total > 0
            or self.pending_candidate_count > 0
        )


class TocItem(ORMBase):
    level: int
    text: str
    anchor: str


class CommitSummary(ORMBase):
    id: int
    branch_id: int
    parent_commit_id: int | None
    message: str
    content_hash: str
    created_at: datetime


class BranchSummary(ORMBase):
    id: int
    name: str
    head_commit_id: int | None
    created_at: datetime


class WikiDetail(WikiSummary):
    current_main_commit_id: int | None = None
    content_md: str = Field(default="", description="Main 分支 head commit 的内容")
    toc: list[TocItem] = Field(default_factory=list)
    branches: list[BranchSummary] = Field(default_factory=list)


class UploadResultItem(ORMBase):
    filename: str
    success: bool
    wiki_id: int | None = None
    title: str | None = None
    error: str | None = None


class UploadResponse(ORMBase):
    created: int
    failed: int
    results: list[UploadResultItem]


# ─── Branching (PRD §6.1.2) ────────────────────────────────────────────────


class BranchContent(BaseModel):
    """A branch + its current HEAD content for the editor view."""

    branch: BranchSummary
    head_commit_id: int | None
    content_md: str
    is_main: bool


class CreateBranchRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    base_branch_id: int | None = None


class CommitRequest(BaseModel):
    content_md: str
    message: str = ""
    expected_parent_commit_id: int | None = Field(
        ...,
        description="客户端编辑时记录的 HEAD commit id；用于乐观并发控制",
    )


HunkKind = Literal["clean", "conflict"]


class HunkSchema(BaseModel):
    id: int
    kind: HunkKind
    base_start: int
    base_end: int
    base_text: str
    ours_text: str
    theirs_text: str
    resolved: str | None


class MergePreview(BaseModel):
    source_branch_id: int
    source_branch_name: str
    target_branch_id: int
    target_branch_name: str
    base_commit_id: int | None
    main_head_commit_id: int | None
    source_head_commit_id: int | None
    base_text: str
    ours_text: str
    theirs_text: str
    hunks: list[HunkSchema]
    auto_merged: str | None
    has_conflict: bool
    conflict_count: int


class MergeRequest(BaseModel):
    expected_main_head_id: int | None
    message: str = ""
    # Map hunk_id → user-chosen text (only required when has_conflict=True)
    resolutions: dict[int, str] | None = None

