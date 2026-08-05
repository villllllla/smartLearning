"""Detect and merge near-duplicate questions in the bank."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.models import AnswerAttempt, Question, Tag
from app.models.question import QuestionTag
from app.prompts.defaults import GenerationDefaults
from app.services.embedding.client import embed_stems
from app.services.embedding.vector_math import cosine_similarity
from app.services.question_embedding_service import (
    ensure_embeddings_for_questions,
    find_similar_question_ids,
    load_question_vector,
)
from app.services.question_similarity import cluster_indices, question_similarity


@dataclass
class DuplicateMember:
    id: int
    question_text: str
    attempt_count: int
    similarity_to_canonical: float


@dataclass
class DuplicateCluster:
    canonical_id: int
    canonical_text: str
    members: list[DuplicateMember]


@dataclass
class DedupePreview:
    threshold: float
    method: str
    total_questions: int
    clusters: list[DuplicateCluster]
    duplicate_question_count: int

    @property
    def cluster_count(self) -> int:
        return len(self.clusters)


@dataclass
class DedupeMergeResult:
    threshold: float
    method: str
    dry_run: bool
    clusters_merged: int
    questions_removed: int
    attempts_reassigned: int


def _dedupe_method() -> str:
    return "embedding" if get_settings().dedupe_use_embedding else "string"


def _default_threshold() -> float:
    settings = get_settings()
    if settings.dedupe_use_embedding:
        return settings.dedupe_embedding_threshold
    return GenerationDefaults().similarity_threshold


def _load_active_questions(
    db: Session, *, tenant_id: int, collection_id: int | None = None
) -> list[Question]:
    stmt = (
        select(Question)
        .where(Question.deleted_at.is_(None), Question.tenant_id == tenant_id)
        .options(selectinload(Question.tags))
        .order_by(Question.id.asc())
    )
    if collection_id is not None:
        stmt = stmt.where(Question.collection_id == collection_id)
    return list(db.execute(stmt).scalars().all())


def _attempt_counts(db: Session, question_ids: list[int]) -> dict[int, int]:
    if not question_ids:
        return {}
    rows = db.execute(
        select(AnswerAttempt.question_id, func.count())
        .where(AnswerAttempt.question_id.in_(question_ids))
        .group_by(AnswerAttempt.question_id)
    ).all()
    return {int(qid): int(cnt) for qid, cnt in rows}


def _pick_canonical(
    questions: list[Question], attempt_counts: dict[int, int]
) -> Question:
    return max(
        questions,
        key=lambda q: (attempt_counts.get(q.id, 0), -q.id),
    )


def _pair_similarity(
    left: Question,
    right: Question,
    *,
    use_embedding: bool,
    vectors: dict[int, list[float]] | None = None,
) -> float:
    if use_embedding and vectors is not None:
        va = vectors.get(left.id)
        vb = vectors.get(right.id)
        if va and vb:
            return cosine_similarity(va, vb)
    return question_similarity(left.question_text, right.question_text)


def find_duplicate_clusters(
    db: Session,
    questions: list[Question],
    *,
    threshold: float,
    attempt_counts: dict[int, int] | None = None,
    use_embedding: bool = False,
) -> list[DuplicateCluster]:
    """Pairwise O(n²) clustering — fine for local single-user banks (< few k)."""
    if len(questions) < 2:
        return []

    vectors: dict[int, list[float]] | None = None
    if use_embedding:
        ensure_embeddings_for_questions(db, questions)
        vectors = {}
        for q in questions:
            vec = load_question_vector(q)
            if vec:
                vectors[q.id] = vec

    pairs: list[tuple[int, int]] = []
    for i in range(len(questions)):
        for j in range(i + 1, len(questions)):
            if (
                _pair_similarity(
                    questions[i],
                    questions[j],
                    use_embedding=use_embedding,
                    vectors=vectors,
                )
                >= threshold
            ):
                pairs.append((i, j))

    clusters: list[DuplicateCluster] = []
    for idxs in cluster_indices(len(questions), pairs):
        group = [questions[i] for i in idxs]
        counts = attempt_counts or {}
        canonical = _pick_canonical(group, counts)
        members: list[DuplicateMember] = []
        for q in sorted(group, key=lambda x: x.id):
            sim = _pair_similarity(
                canonical,
                q,
                use_embedding=use_embedding,
                vectors=vectors,
            )
            members.append(
                DuplicateMember(
                    id=q.id,
                    question_text=q.question_text,
                    attempt_count=counts.get(q.id, 0),
                    similarity_to_canonical=round(sim, 4),
                )
            )
        clusters.append(
            DuplicateCluster(
                canonical_id=canonical.id,
                canonical_text=canonical.question_text,
                members=members,
            )
        )
    return clusters


def preview_dedupe(
    db: Session,
    *,
    tenant_id: int,
    threshold: float | None = None,
    collection_id: int | None = None,
) -> DedupePreview:
    method = _dedupe_method()
    th = threshold if threshold is not None else _default_threshold()
    questions = _load_active_questions(db, tenant_id=tenant_id, collection_id=collection_id)
    ids = [q.id for q in questions]
    counts = _attempt_counts(db, ids)
    clusters = find_duplicate_clusters(
        db,
        questions,
        threshold=th,
        attempt_counts=counts,
        use_embedding=method == "embedding",
    )
    dup_count = sum(len(c.members) - 1 for c in clusters)
    return DedupePreview(
        threshold=th,
        method=method,
        total_questions=len(questions),
        clusters=clusters,
        duplicate_question_count=dup_count,
    )


def merge_duplicates(
    db: Session,
    *,
    tenant_id: int,
    threshold: float | None = None,
    collection_id: int | None = None,
    dry_run: bool = False,
) -> DedupeMergeResult:
    preview = preview_dedupe(
        db, tenant_id=tenant_id, threshold=threshold, collection_id=collection_id
    )
    if dry_run or not preview.clusters:
        return DedupeMergeResult(
            threshold=preview.threshold,
            method=preview.method,
            dry_run=dry_run,
            clusters_merged=0,
            questions_removed=0,
            attempts_reassigned=0,
        )

    removed = 0
    reassigned = 0
    for cluster in preview.clusters:
        canonical_id = cluster.canonical_id
        canonical = db.get(Question, canonical_id)
        if canonical is None or canonical.deleted_at is not None:
            continue
        tag_names = {t.name for t in (canonical.tags or [])}

        for member in cluster.members:
            if member.id == canonical_id:
                continue
            dup = db.get(Question, member.id)
            if dup is None or dup.deleted_at is not None:
                continue

            attempts = db.execute(
                select(AnswerAttempt).where(AnswerAttempt.question_id == dup.id)
            ).scalars().all()
            for att in attempts:
                att.question_id = canonical_id
                reassigned += 1

            if canonical.source_wiki_id is None and dup.source_wiki_id is not None:
                canonical.source_wiki_id = dup.source_wiki_id
                canonical.source_commit_id = dup.source_commit_id

            dup_tags = db.execute(
                select(Tag)
                .join(QuestionTag, QuestionTag.tag_id == Tag.id)
                .where(QuestionTag.question_id == dup.id)
            ).scalars().all()
            for tag in dup_tags:
                if tag.name not in tag_names:
                    db.add(QuestionTag(question_id=canonical_id, tag_id=tag.id))
                    tag_names.add(tag.name)

            dup.deleted_at = datetime.utcnow()
            removed += 1

    if not dry_run:
        db.commit()

    return DedupeMergeResult(
        threshold=preview.threshold,
        method=preview.method,
        dry_run=False,
        clusters_merged=preview.cluster_count,
        questions_removed=removed,
        attempts_reassigned=reassigned,
    )


def find_bank_duplicate(
    db: Session,
    question_text: str,
    *,
    tenant_id: int,
    collection_id: int | None = None,
    threshold: float | None = None,
    exclude_question_id: int | None = None,
) -> Question | None:
    """Return an existing question if stem is similar enough (for commit-time skip)."""
    settings = get_settings()
    th = threshold if threshold is not None else _default_threshold()

    if settings.dedupe_use_embedding:
        try:
            query_vec = embed_stems([question_text])[0]
        except Exception:
            query_vec = None
        if query_vec:
            hits = find_similar_question_ids(
                db,
                query_vector=query_vec,
                tenant_id=tenant_id,
                threshold=th,
                collection_id=collection_id,
                exclude_question_id=exclude_question_id,
            )
            if hits:
                q = db.get(Question, hits[0][0])
                if q is not None and q.deleted_at is None:
                    return q

    stmt = select(Question).where(
        Question.deleted_at.is_(None), Question.tenant_id == tenant_id
    )
    if collection_id is not None:
        stmt = stmt.where(Question.collection_id == collection_id)
    if exclude_question_id is not None:
        stmt = stmt.where(Question.id != exclude_question_id)
    for q in db.execute(stmt).scalars().all():
        if question_similarity(question_text, q.question_text) >= th:
            return q
    return None


def backfill_question_embeddings(
    db: Session,
    *,
    tenant_id: int,
    collection_id: int | None = None,
) -> tuple[int, int]:
    """Ensure all active questions have stem embeddings. Returns (total, newly_embedded)."""
    questions = _load_active_questions(db, tenant_id=tenant_id, collection_id=collection_id)
    missing = [q for q in questions if not q.stem_embedding_json]
    if missing:
        ensure_embeddings_for_questions(db, missing)
    return len(questions), len(missing)
