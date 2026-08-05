"""Practice question pool resolution (shared by REST API and bot facade)."""
from __future__ import annotations

import random as _random

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.models import AnswerAttempt, Question, Wiki
from app.models.question import INTERVIEW_ANSWER_STATUS_PENDING, QuestionTag
from app.schemas.practice import PracticeSetupRequest, PracticeSetupResponse
from app.schemas.question import QuestionSummary


def build_pool_stmt(payload: PracticeSetupRequest, *, tenant_id: int):
    """Build a select returning only Question rows that satisfy filters."""
    stmt = select(Question).where(
        Question.deleted_at.is_(None), Question.tenant_id == tenant_id
    )
    # Skip interview questions still waiting for reference answers.
    stmt = stmt.where(
        (Question.interview_answer_status.is_(None))
        | (Question.interview_answer_status != INTERVIEW_ANSWER_STATUS_PENDING)
    )
    if payload.collection_id is not None:
        stmt = stmt.where(Question.collection_id == payload.collection_id)
    if payload.source_wiki_ids:
        stmt = stmt.where(Question.source_wiki_id.in_(payload.source_wiki_ids))
    if payload.difficulties:
        stmt = stmt.where(Question.difficulty.in_(payload.difficulties))
    if payload.qtypes:
        stmt = stmt.where(Question.qtype.in_(payload.qtypes))
    if payload.source_kinds:
        stmt = stmt.where(Question.source_kind.in_(payload.source_kinds))
    if payload.tag_ids:
        if payload.tag_mode == "and":
            for tid in payload.tag_ids:
                stmt = stmt.where(
                    Question.id.in_(
                        select(QuestionTag.question_id).where(QuestionTag.tag_id == tid)
                    )
                )
        else:
            stmt = stmt.where(
                Question.id.in_(
                    select(QuestionTag.question_id).where(
                        QuestionTag.tag_id.in_(payload.tag_ids)
                    )
                )
            )

    if payload.mode == "wrong":
        rn = (
            func.row_number()
            .over(
                partition_by=AnswerAttempt.question_id,
                order_by=desc(AnswerAttempt.created_at),
            )
            .label("rn")
        )
        inner = select(
            AnswerAttempt.question_id.label("question_id"),
            AnswerAttempt.grade.label("grade"),
            rn,
        ).subquery()
        latest = (
            select(inner.c.question_id)
            .where(inner.c.rn == 1, inner.c.grade == "C")
            .subquery()
        )
        stmt = stmt.where(Question.id.in_(select(latest.c.question_id)))
    return stmt


def setup_questions(
    db: Session, payload: PracticeSetupRequest, *, tenant_id: int
) -> PracticeSetupResponse:
    base = build_pool_stmt(payload, tenant_id=tenant_id)
    total = int(
        db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    )
    if total == 0:
        return PracticeSetupResponse(
            questions=[], time_limit_per_question=payload.time_limit_per_question, total_pool=0
        )

    if payload.mode == "random":
        ids = list(
            db.execute(select(Question.id).select_from(base.subquery())).scalars().all()
        )
        _random.shuffle(ids)
        ids = ids[: payload.limit]
        rows = db.execute(
            select(Question)
            .where(Question.id.in_(ids))
            .options(selectinload(Question.tags))
        ).scalars().unique().all()
        rows.sort(key=lambda x: ids.index(x.id))
    else:
        ordered = base.order_by(Question.created_at.asc()).limit(payload.limit)
        rows = (
            db.execute(
                select(Question)
                .where(Question.id.in_(ordered.with_only_columns(Question.id)))
                .options(selectinload(Question.tags))
                .order_by(Question.created_at.asc())
            )
            .scalars()
            .unique()
            .all()
        )

    summaries: list[QuestionSummary] = []
    for q in rows:
        item = QuestionSummary.model_validate(q)
        item.attempt_count = int(
            db.execute(
                select(func.count())
                .select_from(AnswerAttempt)
                .where(AnswerAttempt.question_id == q.id)
            ).scalar_one()
        )
        last = db.execute(
            select(AnswerAttempt)
            .where(AnswerAttempt.question_id == q.id)
            .order_by(AnswerAttempt.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if last is not None:
            item.last_grade = last.grade
            item.last_attempt_at = last.created_at
        if q.source_wiki_id is not None:
            item.source_wiki_title = db.execute(
                select(Wiki.title).where(Wiki.id == q.source_wiki_id)
            ).scalar_one_or_none()
        summaries.append(item)

    return PracticeSetupResponse(
        questions=summaries,
        time_limit_per_question=payload.time_limit_per_question,
        total_pool=total,
    )
