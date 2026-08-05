"""Embed and persist question stems for semantic dedupe."""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Question
from app.services.embedding.client import (
    EmbeddingClientError,
    embed_stems,
    embedding_from_json,
    embedding_to_json,
)
from app.services.embedding.milvus_store import (
    delete_question_vector,
    milvus_enabled,
    upsert_question_vector,
)
from app.services.embedding.vector_math import cosine_similarity

log = logging.getLogger(__name__)


def ensure_question_embedding(db: Session, question: Question) -> list[float] | None:
    settings = get_settings()
    if not settings.dedupe_use_embedding:
        return None
    if question.stem_embedding_json:
        try:
            return embedding_from_json(question.stem_embedding_json)
        except (TypeError, ValueError):
            question.stem_embedding_json = None

    try:
        vec = embed_stems([question.question_text])[0]
    except EmbeddingClientError as exc:
        log.warning("embed question %s failed: %s", question.id, exc)
        raise

    question.stem_embedding_json = embedding_to_json(vec)
    question.embedding_model = settings.embedding_model
    db.flush()

    if milvus_enabled(settings):
        try:
            upsert_question_vector(
                question_id=question.id,
                tenant_id=question.tenant_id,
                collection_id=question.collection_id,
                vector=vec,
            )
        except Exception as exc:
            log.warning("milvus upsert question %s failed: %s", question.id, exc)
    return vec


def ensure_embeddings_for_questions(db: Session, questions: list[Question]) -> None:
    missing = [q for q in questions if not q.stem_embedding_json]
    if not missing:
        return
    settings = get_settings()
    try:
        vecs = embed_stems([q.question_text for q in missing])
    except EmbeddingClientError:
        raise
    for q, vec in zip(missing, vecs, strict=False):
        q.stem_embedding_json = embedding_to_json(vec)
        q.embedding_model = settings.embedding_model
        if milvus_enabled(settings):
            try:
                upsert_question_vector(
                    question_id=q.id,
                    tenant_id=q.tenant_id,
                    collection_id=q.collection_id,
                    vector=vec,
                )
            except Exception as exc:
                log.warning("milvus upsert question %s failed: %s", q.id, exc)
    db.flush()


def load_question_vector(question: Question) -> list[float] | None:
    if not question.stem_embedding_json:
        return None
    try:
        return embedding_from_json(question.stem_embedding_json)
    except (TypeError, ValueError):
        return None


def embedding_similarity(text_a: str, text_b: str, vec_a: list[float] | None, vec_b: list[float] | None) -> float:
    if vec_a and vec_b:
        return cosine_similarity(vec_a, vec_b)
    if vec_a or vec_b:
        return 0.0
    from app.services.question_similarity import question_similarity

    return question_similarity(text_a, text_b)


def find_similar_question_ids(
    db: Session,
    *,
    query_vector: list[float],
    tenant_id: int,
    threshold: float,
    collection_id: int | None = None,
    exclude_question_id: int | None = None,
) -> list[tuple[int, float]]:
    settings = get_settings()
    if milvus_enabled(settings):
        from app.services.embedding.milvus_store import search_similar_questions

        hits = search_similar_questions(
            vector=query_vector,
            tenant_id=tenant_id,
            top_k=20,
        )
        out: list[tuple[int, float]] = []
        for qid, sim in hits:
            if sim < threshold:
                continue
            if exclude_question_id is not None and qid == exclude_question_id:
                continue
            q = db.get(Question, qid)
            if q is None or q.deleted_at is not None:
                continue
            if collection_id is not None and q.collection_id != collection_id:
                continue
            out.append((qid, sim))
        return out

    stmt = select(Question).where(
        Question.deleted_at.is_(None),
        Question.tenant_id == tenant_id,
        Question.stem_embedding_json.is_not(None),
    )
    if collection_id is not None:
        stmt = stmt.where(Question.collection_id == collection_id)
    if exclude_question_id is not None:
        stmt = stmt.where(Question.id != exclude_question_id)
    out = []
    for q in db.execute(stmt).scalars().all():
        vec = load_question_vector(q)
        if not vec:
            continue
        sim = cosine_similarity(query_vector, vec)
        if sim >= threshold:
            out.append((q.id, sim))
    out.sort(key=lambda x: x[1], reverse=True)
    return out


def remove_question_embedding(db: Session, question: Question) -> None:
    question.stem_embedding_json = None
    question.embedding_model = None
    if milvus_enabled():
        try:
            delete_question_vector(question_id=question.id)
        except Exception as exc:
            log.warning("milvus delete question %s failed: %s", question.id, exc)
