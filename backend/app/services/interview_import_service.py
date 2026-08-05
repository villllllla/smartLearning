"""Import real interview notes (面经) into the question bank."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Question, QuestionBankCollection
from app.models.question import (
    INTERVIEW_ANSWER_PLACEHOLDER,
    INTERVIEW_ANSWER_STATUS_PENDING,
    SOURCE_KIND_INTERVIEW,
    QuestionTag,
)
from app.services.generation_service import _ensure_default_collection, _upsert_tag
from app.services.interview_answer_service import enqueue_answer_job
from app.services.interview_note_parser import parse_interview_markdown
from app.services.question_dedupe_service import find_bank_duplicate

log = logging.getLogger(__name__)


@dataclass
class InterviewImportResult:
    parsed: int
    imported: int
    skipped_duplicates: int
    doc_name: str
    answer_job_id: str | None = None
    answers_queued: int = 0


def import_interview_markdown(
    db: Session,
    *,
    tenant_id: int,
    content: str,
    doc_name: str = "",
    target_collection_id: int | None = None,
) -> InterviewImportResult:
    items = parse_interview_markdown(content, doc_name=doc_name)
    if not items:
        raise ValueError("未从文档中识别到面经题目（请以问句结尾，如「…？」）")

    if target_collection_id is None:
        coll = _ensure_default_collection(db, tenant_id=tenant_id)
        target_collection_id = coll.id
    elif db.get(QuestionBankCollection, target_collection_id) is None:
        raise ValueError("目标题库不存在")

    doc_tag = _upsert_tag(db, "实战面经", tenant_id=tenant_id)
    if doc_name:
        doc_tag_name = f"面经:{doc_name[:60]}"
        _upsert_tag(db, doc_tag_name, tenant_id=tenant_id)

    imported = 0
    skipped = 0
    imported_ids: list[int] = []
    group_keys: dict[int, str] = {}
    for item in items:
        stem = item.question_text.strip()
        if find_bank_duplicate(
            db, stem, tenant_id=tenant_id, collection_id=target_collection_id
        ):
            skipped += 1
            continue
        q = Question(
            tenant_id=tenant_id,
            collection_id=target_collection_id,
            question_text=stem,
            answer_standard=INTERVIEW_ANSWER_PLACEHOLDER,
            difficulty="medium",
            qtype="scenario",
            source_kind=SOURCE_KIND_INTERVIEW,
            source_anchor=(item.source_anchor or doc_name or "")[:64] or None,
            interview_group_key=(item.group_key or "")[:128] or None,
            interview_answer_status=INTERVIEW_ANSWER_STATUS_PENDING,
        )
        db.add(q)
        db.flush()
        tag_ids = {doc_tag.id}
        db.add(QuestionTag(question_id=q.id, tag_id=doc_tag.id))
        if item.company:
            ct = _upsert_tag(db, item.company[:80], tenant_id=tenant_id)
            if ct.id not in tag_ids:
                db.add(QuestionTag(question_id=q.id, tag_id=ct.id))
                tag_ids.add(ct.id)
        if item.round_label:
            rt = _upsert_tag(db, item.round_label[:80], tenant_id=tenant_id)
            if rt.id not in tag_ids:
                db.add(QuestionTag(question_id=q.id, tag_id=rt.id))
        if doc_name:
            dt = _upsert_tag(db, f"面经:{doc_name[:60]}", tenant_id=tenant_id)
            if dt.id not in tag_ids:
                db.add(QuestionTag(question_id=q.id, tag_id=dt.id))
        try:
            from app.services.question_embedding_service import ensure_question_embedding

            ensure_question_embedding(db, q)
        except Exception as exc:
            log.warning("interview question %s embedding skipped: %s", q.id, exc)
        imported += 1
        imported_ids.append(q.id)
        group_keys[q.id] = item.group_key or doc_name

    answer_job_id: str | None = None
    answers_queued = 0
    if imported_ids:
        enq = enqueue_answer_job(
            db,
            tenant_id=tenant_id,
            question_ids=imported_ids,
            context_md=content,
            doc_name=doc_name,
            group_keys=group_keys,
        )
        if enq:
            answer_job_id = enq.job_id
            answers_queued = enq.queued

    db.flush()
    return InterviewImportResult(
        parsed=len(items),
        imported=imported,
        skipped_duplicates=skipped,
        doc_name=doc_name,
        answer_job_id=answer_job_id,
        answers_queued=answers_queued,
    )
