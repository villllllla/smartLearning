"""Wiki ↔ question generation helpers (counts, replace-before-regenerate)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import Question, QuestionCandidate


def wiki_generation_stats(

    db: Session, wiki_ids: list[int]

) -> dict[int, dict[str, int | str | None]]:

    """Per-wiki counts: bank questions + pending candidates.



    ``pending_candidate_count`` is the count in the **latest batch only** so it

    matches the candidate preview page (``/bank/candidates/{pending_batch_id}``).

    ``pending_candidate_total`` sums all batches for that wiki.

    """

    if not wiki_ids:

        return {}

    out: dict[int, dict[str, int | str | None]] = {

        wid: {

            "bank_question_count": 0,

            "pending_candidate_count": 0,

            "pending_candidate_total": 0,

            "pending_batch_count": 0,

            "pending_batch_id": None,

        }

        for wid in wiki_ids

    }



    for wiki_id, cnt in db.execute(

        select(Question.source_wiki_id, func.count(Question.id))

        .where(

            Question.source_wiki_id.in_(wiki_ids),

            Question.deleted_at.is_(None),

        )

        .group_by(Question.source_wiki_id)

    ).all():

        if wiki_id is not None:

            out[wiki_id]["bank_question_count"] = int(cnt)



    batch_rows = db.execute(

        select(

            QuestionCandidate.source_wiki_id,

            QuestionCandidate.batch_id,

            func.count(QuestionCandidate.id).label("cnt"),

            func.max(QuestionCandidate.created_at).label("latest_at"),

        )

        .where(QuestionCandidate.source_wiki_id.in_(wiki_ids))

        .group_by(QuestionCandidate.source_wiki_id, QuestionCandidate.batch_id)

    ).all()



    batches_by_wiki: dict[int, list[tuple[str, int, datetime]]] = {}

    for wiki_id, batch_id, cnt, latest_at in batch_rows:

        if wiki_id is None:

            continue

        batches_by_wiki.setdefault(wiki_id, []).append(

            (batch_id, int(cnt), latest_at)

        )



    for wiki_id, batches in batches_by_wiki.items():

        batches.sort(key=lambda x: x[2], reverse=True)

        latest_batch_id, latest_count, _ = batches[0]

        total = sum(b[1] for b in batches)

        out[wiki_id]["pending_batch_id"] = latest_batch_id

        out[wiki_id]["pending_candidate_count"] = latest_count

        out[wiki_id]["pending_candidate_total"] = total

        out[wiki_id]["pending_batch_count"] = len(batches)



    return out





def clear_wiki_generated_content(db: Session, wiki_id: int) -> tuple[int, int]:

    """Remove prior questions (soft) and preview candidates (hard) for one wiki.



    Returns ``(bank_questions_removed, candidates_removed)``.

    """

    now = datetime.utcnow()

    questions = (

        db.execute(

            select(Question).where(

                Question.source_wiki_id == wiki_id,

                Question.deleted_at.is_(None),

            )

        )

        .scalars()

        .all()

    )

    for q in questions:

        q.deleted_at = now



    cand_result = db.execute(

        delete(QuestionCandidate).where(QuestionCandidate.source_wiki_id == wiki_id)

    )

    db.flush()

    return len(questions), int(cand_result.rowcount or 0)





def list_candidate_batches(

    db: Session, *, tenant_id: int, limit: int = 100

) -> list[dict]:

    """All candidate batches (including orphaned rows with null source_wiki_id)."""

    from app.models import Wiki



    rows = db.execute(

        select(

            QuestionCandidate.batch_id,

            func.count(QuestionCandidate.id).label("cnt"),

            func.max(QuestionCandidate.created_at).label("latest_at"),

            func.min(QuestionCandidate.source_wiki_id).label("wiki_id"),

        )

        .where(QuestionCandidate.tenant_id == tenant_id)

        .group_by(QuestionCandidate.batch_id)

        .order_by(func.max(QuestionCandidate.created_at).desc())

        .limit(limit)

    ).all()



    out: list[dict] = []

    for batch_id, cnt, latest_at, wiki_id in rows:

        title = None

        if wiki_id is not None:

            wiki = db.get(Wiki, wiki_id)

            if wiki is not None and wiki.deleted_at is None:

                title = wiki.title

        out.append(

            {

                "batch_id": batch_id,

                "count": int(cnt),

                "created_at": latest_at,

                "source_wiki_id": wiki_id,

                "source_wiki_title": title,

            }

        )

    return out


