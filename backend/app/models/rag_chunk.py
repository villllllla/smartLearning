"""Vector chunks for wiki RAG retrieval."""
from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class RagChunk(Base, TimestampMixin):
    __tablename__ = "rag_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    wiki_id: Mapped[int] = mapped_column(
        ForeignKey("wikis.id", ondelete="CASCADE"), nullable=False
    )
    wiki_title: Mapped[str] = mapped_column(String(300), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    heading: Mapped[str | None] = mapped_column(String(500), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source_commit_id: Mapped[int | None] = mapped_column(
        ForeignKey("wiki_commits.id", ondelete="SET NULL"), nullable=True
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    # JSON-serialized float list from bge-small-zh
    embedding_json: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("ix_rag_chunks_wiki", "wiki_id"),
        Index("ix_rag_chunks_wiki_idx", "wiki_id", "chunk_index", unique=True),
    )
