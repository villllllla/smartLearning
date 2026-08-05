"""Build / rebuild wiki chunk embeddings."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings, get_settings
from app.models import Wiki
from app.models.rag_chunk import RagChunk
from app.services.rag.chunking import chunk_markdown
from app.services.rag.embedder import RagEmbedderError, embed_texts, embedding_to_json
from app.services.rag.retrieve import chunk_count, delete_wiki_chunks

log = logging.getLogger(__name__)


@dataclass
class RagIndexSummary:
    wikis_processed: int = 0
    chunks_written: int = 0
    wikis_skipped: int = 0
    errors: list[str] | None = None


def _wiki_markdown(wiki: Wiki) -> tuple[str, int | None, str]:
    commit = wiki.current_main_commit
    if commit is None:
        return "", None, ""
    return commit.content_md or "", commit.id, commit.content_hash or ""


def index_wiki(db: Session, wiki_id: int, settings: Settings | None = None) -> int:
    """Re-embed one wiki; returns chunk count."""
    settings = settings or get_settings()
    wiki = db.execute(
        select(Wiki)
        .where(Wiki.id == wiki_id, Wiki.deleted_at.is_(None))
        .options(selectinload(Wiki.current_main_commit))
    ).scalar_one_or_none()
    if wiki is None:
        raise ValueError(f"wiki {wiki_id} not found")

    content_md, commit_id, content_hash = _wiki_markdown(wiki)
    delete_wiki_chunks(db, wiki_id)
    if not content_md.strip():
        db.flush()
        return 0

    chunks = chunk_markdown(
        content_md,
        max_chars=settings.rag_chunk_max_chars,
        overlap=settings.rag_chunk_overlap,
    )
    if not chunks:
        db.flush()
        return 0

    texts = [c.text for c in chunks]
    vectors = embed_texts(texts)
    now = datetime.now(timezone.utc)
    for i, (ch, vec) in enumerate(zip(chunks, vectors, strict=False)):
        row = RagChunk(
            wiki_id=wiki.id,
            wiki_title=wiki.title,
            chunk_index=i,
            heading=ch.heading,
            text=ch.text,
            source_commit_id=commit_id,
            content_hash=content_hash,
            embedding_json=embedding_to_json(vec),
        )
        row.created_at = now
        row.updated_at = now
        db.add(row)
    db.flush()
    return len(chunks)


def rebuild_index(
    db: Session,
    settings: Settings | None = None,
    *,
    wiki_id: int | None = None,
) -> RagIndexSummary:
    settings = settings or get_settings()
    summary = RagIndexSummary(errors=[])

    if wiki_id is not None:
        try:
            n = index_wiki(db, wiki_id, settings)
            summary.wikis_processed = 1
            summary.chunks_written = n
        except (RagEmbedderError, ValueError) as exc:
            summary.errors.append(str(exc))
        except Exception as exc:  # noqa: BLE001
            log.exception("rag index wiki %s failed", wiki_id)
            summary.errors.append(f"wiki {wiki_id}: {exc}")
        db.commit()
        return summary

    wikis = db.execute(
        select(Wiki).where(Wiki.deleted_at.is_(None)).order_by(Wiki.id.asc())
    ).scalars().all()
    for wiki in wikis:
        try:
            n = index_wiki(db, wiki.id, settings)
            summary.wikis_processed += 1
            summary.chunks_written += n
        except RagEmbedderError:
            raise
        except Exception as exc:  # noqa: BLE001
            summary.wikis_skipped += 1
            summary.errors.append(f"wiki {wiki.id} ({wiki.title}): {exc}")
            log.exception("rag index failed wiki=%s", wiki.id)
    db.commit()
    return summary


def get_index_status(db: Session, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    total_chunks = chunk_count(db)
    distinct_wikis = int(
        db.execute(select(func.count(func.distinct(RagChunk.wiki_id)))).scalar_one()
    )
    return {
        "enabled": settings.rag_enabled,
        "embedding_model": settings.rag_embedding_model,
        "chunk_count": total_chunks,
        "wiki_count_indexed": distinct_wikis,
        "top_k": settings.rag_top_k,
        "min_score": settings.rag_min_score,
        "chunk_max_chars": settings.rag_chunk_max_chars,
    }
