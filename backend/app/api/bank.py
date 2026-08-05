"""Question bank read endpoints (PRD §6.3.5).

Filters:
  collection_id, source_wiki_id (legacy / single)
  source_wiki_ids (multi)
  tag_ids + tag_mode=and|or
  difficulties (multi)
  qtypes (multi)
  wrong_only=bool      # latest attempt grade == 'C'
  q                    # title search

Each row is enriched with: tags, source_wiki_title, last_grade,
last_attempt_at, attempt_count.
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import AuthContext, get_auth_context
from app.db.session import get_db
from app.models import (
    AnswerAttempt,
    Question,
    QuestionBankCollection,
    Tag,
    Wiki,
)
from app.models.question import QuestionTag
from app.schemas.common import Page
from app.schemas.dedupe import (
    DedupeClusterOut,
    DedupeMemberOut,
    DedupeMergeOut,
    DedupeMergeRequest,
    DedupePreviewOut,
)
from app.schemas.question import (
    AttemptSummary,
    BankCollectionSummary,
    InterviewAnswerJobRead,
    InterviewImportResponse,
    QuestionSummary,
    TagSummary,
)
from app.services.interview_answer_service import (
    enqueue_backfill_pending,
    get_job,
    list_recent_jobs,
)
from app.services.interview_import_service import import_interview_markdown
from app.services.question_dedupe_service import (
    backfill_question_embeddings,
    merge_duplicates,
    preview_dedupe,
)

router = APIRouter()


# ---- Collections / tags helpers --------------------------------------------


@router.get("/collections", response_model=list[BankCollectionSummary])
def list_collections(
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> list[BankCollectionSummary]:
    rows = db.execute(
        select(QuestionBankCollection)
        .where(QuestionBankCollection.tenant_id == ctx.tenant_id)
        .order_by(QuestionBankCollection.id.asc())
    ).scalars().all()
    return [BankCollectionSummary.model_validate(c) for c in rows]


@router.get("/tags", response_model=list[TagSummary])
def list_tags(
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> list[TagSummary]:
    rows = db.execute(
        select(Tag).where(Tag.tenant_id == ctx.tenant_id).order_by(Tag.name.asc())
    ).scalars().all()
    return [TagSummary.model_validate(t) for t in rows]


# ---- Question listing with filters ----------------------------------------


def _parse_csv_int(value: str | None) -> list[int]:
    if not value:
        return []
    out: list[int] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            continue
    return out


def _parse_csv_str(value: str | None) -> list[str]:
    if not value:
        return []
    return [p.strip() for p in value.split(",") if p.strip()]


def _latest_attempt_subq(db: Session):
    """Subquery returning (question_id, grade, created_at, count) for each question."""
    rn = (
        func.row_number()
        .over(partition_by=AnswerAttempt.question_id, order_by=desc(AnswerAttempt.created_at))
        .label("rn")
    )
    inner = select(
        AnswerAttempt.question_id.label("question_id"),
        AnswerAttempt.grade.label("grade"),
        AnswerAttempt.created_at.label("created_at"),
        rn,
    ).subquery()
    latest = (
        select(inner.c.question_id, inner.c.grade, inner.c.created_at)
        .where(inner.c.rn == 1)
        .subquery()
    )
    counts = (
        select(
            AnswerAttempt.question_id.label("question_id"),
            func.count().label("attempt_count"),
        )
        .group_by(AnswerAttempt.question_id)
        .subquery()
    )
    return latest, counts


@router.get("/questions", response_model=Page[QuestionSummary])
def list_questions(
    collection_id: int | None = Query(None),
    source_wiki_id: int | None = Query(None),
    source_wiki_ids: str | None = Query(None, description="逗号分隔多个 wiki id"),
    tag_ids: str | None = Query(None, description="逗号分隔标签 id"),
    tag_mode: str = Query("or", pattern="^(and|or)$"),
    difficulties: str | None = Query(None, description="easy,medium,hard 任意子集"),
    qtypes: str | None = Query(None, description="concept,scenario 任意子集"),
    source_kinds: str | None = Query(
        None, description="simulated,interview 任意子集；simulated=模拟题 interview=实战面经"
    ),
    wrong_only: bool = Query(False, description="仅展示最近一次评级为 C 的题"),
    q: str | None = Query(None, description="题干模糊搜索"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> Page[QuestionSummary]:
    latest_sub, count_sub = _latest_attempt_subq(db)

    stmt = (
        select(
            Question,
            Wiki.title.label("source_wiki_title"),
            latest_sub.c.grade.label("last_grade"),
            latest_sub.c.created_at.label("last_attempt_at"),
            func.coalesce(count_sub.c.attempt_count, 0).label("attempt_count"),
        )
        .where(Question.deleted_at.is_(None), Question.tenant_id == ctx.tenant_id)
        .outerjoin(Wiki, Wiki.id == Question.source_wiki_id)
        .outerjoin(latest_sub, latest_sub.c.question_id == Question.id)
        .outerjoin(count_sub, count_sub.c.question_id == Question.id)
        .options(selectinload(Question.tags))
    )

    if collection_id is not None:
        stmt = stmt.where(Question.collection_id == collection_id)

    wiki_ids = _parse_csv_int(source_wiki_ids)
    if source_wiki_id is not None:
        wiki_ids = list({source_wiki_id, *wiki_ids})
    if wiki_ids:
        stmt = stmt.where(Question.source_wiki_id.in_(wiki_ids))

    diffs = _parse_csv_str(difficulties)
    if diffs:
        stmt = stmt.where(Question.difficulty.in_(diffs))
    types = _parse_csv_str(qtypes)
    if types:
        stmt = stmt.where(Question.qtype.in_(types))
    kinds = _parse_csv_str(source_kinds)
    if kinds:
        stmt = stmt.where(Question.source_kind.in_(kinds))

    tids = _parse_csv_int(tag_ids)
    if tids:
        if tag_mode == "and":
            for tid in tids:
                stmt = stmt.where(
                    Question.id.in_(
                        select(QuestionTag.question_id).where(QuestionTag.tag_id == tid)
                    )
                )
        else:
            stmt = stmt.where(
                Question.id.in_(
                    select(QuestionTag.question_id).where(QuestionTag.tag_id.in_(tids))
                )
            )

    if wrong_only:
        stmt = stmt.where(latest_sub.c.grade == "C")

    if q:
        stmt = stmt.where(Question.question_text.ilike(f"%{q}%"))

    stmt = stmt.order_by(Question.created_at.desc())

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = int(db.execute(count_stmt).scalar_one())

    rows = db.execute(stmt.limit(limit).offset(offset)).unique().all()

    items: list[QuestionSummary] = []
    for question, wiki_title, last_grade, last_at, attempt_count in rows:
        item = QuestionSummary.model_validate(question)
        item.source_wiki_title = wiki_title
        item.last_grade = last_grade
        item.last_attempt_at = last_at
        item.attempt_count = int(attempt_count or 0)
        items.append(item)

    return Page[QuestionSummary](items=items, total=total, limit=limit, offset=offset)


@router.post("/import/interview-notes", response_model=InterviewImportResponse)
async def import_interview_notes(
    files: list[UploadFile] = File(..., description="面经 Markdown 文件 (.md)"),
    collection_id: int | None = Query(None),
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> InterviewImportResponse:
    if not files:
        raise HTTPException(400, detail="请上传至少一个 .md 文件")
    total_parsed = 0
    total_imported = 0
    total_skipped = 0
    total_queued = 0
    last_job_id: str | None = None
    names: list[str] = []
    try:
        for f in files:
            name = (f.filename or "面经.md").strip()
            if not name.lower().endswith(".md"):
                raise ValueError(f"仅支持 Markdown 文件: {name}")
            raw = await f.read()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("utf-8-sig")
            doc_name = name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
            if doc_name.lower().endswith(".md"):
                doc_name = doc_name[:-3]
            result = import_interview_markdown(
                db,
                tenant_id=ctx.tenant_id,
                content=text,
                doc_name=doc_name,
                target_collection_id=collection_id,
            )
            total_parsed += result.parsed
            total_imported += result.imported
            total_skipped += result.skipped_duplicates
            if result.answer_job_id:
                last_job_id = result.answer_job_id
                total_queued += result.answers_queued
            names.append(doc_name)
        db.commit()
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    label = "、".join(names[:3])
    if len(names) > 3:
        label += f" 等 {len(names)} 个文件"
    msg = f"从 {label} 识别 {total_parsed} 题，入库 {total_imported} 题"
    if total_skipped:
        msg += f"，跳过重复 {total_skipped} 题"
    if total_skipped:
        msg += f"，跳过重复 {total_skipped} 题"
    if total_queued:
        msg += f"；已排队生成 {total_queued} 道题的参考答案"
    return InterviewImportResponse(
        parsed=total_parsed,
        imported=total_imported,
        skipped_duplicates=total_skipped,
        doc_name=label,
        message=msg,
        answer_job_id=last_job_id,
        answers_queued=total_queued,
    )


def _job_to_read(job) -> InterviewAnswerJobRead:
    ids = list(job.question_ids or [])
    packs = list(getattr(job, "question_groups", None) or [])
    return InterviewAnswerJobRead(
        job_id=job.job_id,
        doc_name=job.doc_name,
        status=job.status,
        total=len(ids),
        pack_count=len(packs) if packs else max(1, (len(ids) + 5) // 6),
        completed_count=job.completed_count,
        failed_count=job.failed_count,
        cursor=job.cursor,
        last_error=job.last_error,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get("/interview-answer-jobs", response_model=list[InterviewAnswerJobRead])
def list_interview_answer_jobs(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[InterviewAnswerJobRead]:
    rows = list_recent_jobs(db, tenant_id=ctx.tenant_id, limit=10)
    return [_job_to_read(r) for r in rows]


@router.get("/interview-answer-jobs/{job_id}", response_model=InterviewAnswerJobRead)
def get_interview_answer_job(
    job_id: str,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> InterviewAnswerJobRead:
    job = get_job(db, job_id, tenant_id=ctx.tenant_id)
    if job is None:
        raise HTTPException(404, detail="任务不存在")
    return _job_to_read(job)


@router.post("/interview-answer-jobs/backfill", response_model=InterviewAnswerJobRead)
def backfill_interview_answers(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> InterviewAnswerJobRead:
    enq = enqueue_backfill_pending(db, tenant_id=ctx.tenant_id)
    if enq is None:
        raise HTTPException(400, detail="没有待生成参考答案的实战面经题")
    db.commit()
    job = get_job(db, enq.job_id, tenant_id=ctx.tenant_id)
    assert job is not None
    return _job_to_read(job)


@router.get("/questions/{q_id}", response_model=QuestionSummary)
def get_question(
    q_id: int,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> QuestionSummary:
    q = db.execute(
        select(Question)
        .where(
            Question.id == q_id,
            Question.deleted_at.is_(None),
            Question.tenant_id == ctx.tenant_id,
        )
        .options(selectinload(Question.tags))
    ).scalar_one_or_none()
    if q is None:
        raise HTTPException(404, detail="question not found")

    wiki_title: str | None = None
    if q.source_wiki_id is not None:
        wiki_title = db.execute(
            select(Wiki.title).where(Wiki.id == q.source_wiki_id)
        ).scalar_one_or_none()

    last_attempt = db.execute(
        select(AnswerAttempt)
        .where(AnswerAttempt.question_id == q_id)
        .order_by(AnswerAttempt.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    attempt_count = int(
        db.execute(
            select(func.count())
            .select_from(AnswerAttempt)
            .where(AnswerAttempt.question_id == q_id)
        ).scalar_one()
    )

    item = QuestionSummary.model_validate(q)
    item.source_wiki_title = wiki_title
    item.last_grade = last_attempt.grade if last_attempt else None
    item.last_attempt_at = last_attempt.created_at if last_attempt else None
    item.attempt_count = attempt_count
    return item


@router.get(
    "/questions/{q_id}/attempts", response_model=list[AttemptSummary]
)
def list_attempts(
    q_id: int,
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> list[AttemptSummary]:
    rows = db.execute(
        select(AnswerAttempt)
        .where(AnswerAttempt.question_id == q_id)
        .order_by(AnswerAttempt.created_at.desc())
        .limit(limit)
    ).scalars().all()
    return [AttemptSummary.model_validate(r) for r in rows]


@router.delete("/questions/{q_id}", status_code=status.HTTP_204_NO_CONTENT)
def soft_delete_question(
    q_id: int,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> None:
    q = db.get(Question, q_id)
    if q is None or q.deleted_at is not None or q.tenant_id != ctx.tenant_id:
        raise HTTPException(404, detail="question not found")
    q.deleted_at = datetime.utcnow()
    db.commit()


def _ids_to_name_set(items: Iterable[Tag]) -> set[str]:
    return {t.name for t in items}


def _preview_to_schema(preview) -> DedupePreviewOut:
    return DedupePreviewOut(
        threshold=preview.threshold,
        method=preview.method,
        total_questions=preview.total_questions,
        cluster_count=preview.cluster_count,
        duplicate_question_count=preview.duplicate_question_count,
        clusters=[
            DedupeClusterOut(
                canonical_id=c.canonical_id,
                canonical_text=c.canonical_text,
                members=[
                    DedupeMemberOut(
                        id=m.id,
                        question_text=m.question_text,
                        attempt_count=m.attempt_count,
                        similarity_to_canonical=m.similarity_to_canonical,
                    )
                    for m in c.members
                ],
            )
            for c in preview.clusters
        ],
    )


@router.get("/dedupe/preview", response_model=DedupePreviewOut)
def dedupe_preview(
    threshold: float | None = Query(None, ge=0.5, le=1.0),
    collection_id: int | None = Query(None),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> DedupePreviewOut:
    """Scan the bank for near-duplicate stems (no writes)."""
    return _preview_to_schema(
        preview_dedupe(
            db,
            threshold=threshold,
            collection_id=collection_id,
            tenant_id=ctx.tenant_id,
        )
    )


@router.post("/dedupe/merge", response_model=DedupeMergeOut)
def dedupe_merge(
    payload: DedupeMergeRequest,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> DedupeMergeOut:
    """Merge clusters: keep canonical (most attempts), reassign history, soft-delete dupes."""
    result = merge_duplicates(
        db,
        threshold=payload.threshold,
        collection_id=payload.collection_id,
        dry_run=payload.dry_run,
        tenant_id=ctx.tenant_id,
    )
    return DedupeMergeOut(
        threshold=result.threshold,
        method=result.method,
        dry_run=result.dry_run,
        clusters_merged=result.clusters_merged,
        questions_removed=result.questions_removed,
        attempts_reassigned=result.attempts_reassigned,
    )


@router.post("/dedupe/backfill-embeddings")
def dedupe_backfill_embeddings(
    collection_id: int | None = Query(None),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> dict:
    """Compute/store stem embeddings for all active questions (semantic dedupe)."""
    from app.core.config import get_settings

    if not get_settings().dedupe_use_embedding:
        raise HTTPException(400, detail="未启用 embedding 去重 (SL_DEDUPE_USE_EMBEDDING=false)")
    total, embedded = backfill_question_embeddings(
        db,
        tenant_id=ctx.tenant_id,
        collection_id=collection_id,
    )
    db.commit()
    return {"total_questions": total, "newly_embedded": embedded}
