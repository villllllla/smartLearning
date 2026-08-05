"""RAG API schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field


class RagSourceOut(BaseModel):
    wiki_id: int
    wiki_title: str
    heading: str | None
    chunk_index: int
    score: float
    url_path: str
    excerpt: str


class RagStatusOut(BaseModel):
    enabled: bool
    embedding_model: str
    chunk_count: int
    wiki_count_indexed: int
    top_k: int
    min_score: float
    chunk_max_chars: int


class RagRebuildRequest(BaseModel):
    wiki_id: int | None = None


class RagRebuildResponse(BaseModel):
    wikis_processed: int
    chunks_written: int
    wikis_skipped: int
    errors: list[str] = Field(default_factory=list)


class RagQueryRequest(BaseModel):
    query: str
    top_k: int | None = Field(None, ge=1, le=20)


class RagQueryResponse(BaseModel):
    hits: list[RagSourceOut]


class RagChunkOut(BaseModel):
    id: int
    wiki_id: int
    wiki_title: str
    chunk_index: int
    heading: str | None
    text: str
    source_commit_id: int | None
    content_hash: str
    text_length: int
    created_at: str | None = None

