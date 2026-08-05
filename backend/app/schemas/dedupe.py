"""Schemas for question deduplication / merge APIs."""
from __future__ import annotations

from pydantic import BaseModel, Field


class DedupeMemberOut(BaseModel):
    id: int
    question_text: str
    attempt_count: int
    similarity_to_canonical: float


class DedupeClusterOut(BaseModel):
    canonical_id: int
    canonical_text: str
    members: list[DedupeMemberOut]


class DedupePreviewOut(BaseModel):
    threshold: float
    method: str = "string"
    total_questions: int
    cluster_count: int
    duplicate_question_count: int
    clusters: list[DedupeClusterOut]


class DedupeMergeRequest(BaseModel):
    threshold: float | None = Field(
        None,
        ge=0.5,
        le=1.0,
        description="题干相似度阈值,默认 0.85",
    )
    collection_id: int | None = None
    dry_run: bool = False


class DedupeMergeOut(BaseModel):
    threshold: float
    method: str = "string"
    dry_run: bool
    clusters_merged: int
    questions_removed: int
    attempts_reassigned: int
