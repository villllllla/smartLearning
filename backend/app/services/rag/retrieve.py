"""Cosine retrieval over stored rag chunks."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.models.rag_chunk import RagChunk
from app.services.rag.embedder import embed_query, embedding_from_json


@dataclass
class RagHit:
    wiki_id: int
    wiki_title: str
    chunk_index: int
    heading: str | None
    text: str
    score: float
    url_path: str

    @property
    def link_label(self) -> str:
        h = f" · {self.heading}" if self.heading else ""
        return f"《{self.wiki_title}》{h} (#{self.chunk_index})"


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))  # lengths checked above
    return dot  # vectors already L2-normalized by embedder


def retrieve(
    db: Session,
    query: str,
    *,
    top_k: int = 5,
    min_score: float = 0.35,
) -> list[RagHit]:
    q_vec = embed_query(query)
    rows = db.execute(select(RagChunk)).scalars().all()
    scored: list[RagHit] = []
    for row in rows:
        vec = embedding_from_json(row.embedding_json)
        score = _cosine(q_vec, vec)
        if score < min_score:
            continue
        scored.append(
            RagHit(
                wiki_id=row.wiki_id,
                wiki_title=row.wiki_title,
                chunk_index=row.chunk_index,
                heading=row.heading,
                text=row.text,
                score=round(score, 4),
                url_path=f"/wiki/{row.wiki_id}",
            )
        )
    scored.sort(key=lambda h: h.score, reverse=True)
    return scored[:top_k]


def chunk_count(db: Session, wiki_id: int | None = None) -> int:
    stmt = select(func.count()).select_from(RagChunk)
    if wiki_id is not None:
        stmt = stmt.where(RagChunk.wiki_id == wiki_id)
    return int(db.execute(stmt).scalar_one())


def delete_wiki_chunks(db: Session, wiki_id: int) -> None:
    db.execute(delete(RagChunk).where(RagChunk.wiki_id == wiki_id))


def list_chunks(
    db: Session,
    *,
    wiki_id: int | None = None,
    q: str | None = None,
    limit: int = 30,
    offset: int = 0,
) -> tuple[list[RagChunk], int]:
    """List stored chunks for inspection (no embedding vectors)."""
    stmt = select(RagChunk)
    if wiki_id is not None:
        stmt = stmt.where(RagChunk.wiki_id == wiki_id)
    if q and q.strip():
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(RagChunk.text.ilike(needle), RagChunk.heading.ilike(needle))
        )
    count_stmt = select(func.count(RagChunk.id))
    if wiki_id is not None:
        count_stmt = count_stmt.where(RagChunk.wiki_id == wiki_id)
    if q and q.strip():
        needle = f"%{q.strip()}%"
        count_stmt = count_stmt.where(
            or_(RagChunk.text.ilike(needle), RagChunk.heading.ilike(needle))
        )
    total = int(db.execute(count_stmt).scalar_one())
    rows = (
        db.execute(
            stmt.order_by(RagChunk.wiki_id.asc(), RagChunk.chunk_index.asc())
            .offset(offset)
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return rows, total
