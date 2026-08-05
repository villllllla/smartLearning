"""Queue + LLM batch generation of standard answers for interview questions."""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.question import (
    INTERVIEW_ANSWER_PLACEHOLDER,
    INTERVIEW_ANSWER_STATUS_FAILED,
    INTERVIEW_ANSWER_STATUS_PENDING,
    INTERVIEW_ANSWER_STATUS_READY,
    SOURCE_KIND_INTERVIEW,
    InterviewAnswerJob,
    Question,
    QuestionTag,
)
from app.services.generation_service import _upsert_tag
from app.services.llm import LLMClient, LLMError, LLMMessage

log = logging.getLogger(__name__)

# Legacy flat slice when question_groups is empty
BATCH_SIZE = 6
# Max questions per LLM call within one project/round pack
MAX_GROUP_PACK = 12
MAX_CONTEXT_CHARS = 24_000

ANSWER_SCHEMA: dict = {
    "type": "array",
    "items": {
        "type": "object",
        "required": ["index", "answer", "difficulty", "type", "tag"],
        "properties": {
            "index": {"type": "integer", "minimum": 0},
            "answer": {"type": "string", "minLength": 20},
            "difficulty": {"enum": ["easy", "medium", "hard"]},
            "type": {"enum": ["concept", "scenario"]},
            "tag": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 6,
            },
        },
        "additionalProperties": False,
    },
}


@dataclass
class EnqueueResult:
    job_id: str
    queued: int
    pack_count: int = 0


def _truncate_context(text: str) -> str:
    text = (text or "").strip()
    if len(text) <= MAX_CONTEXT_CHARS:
        return text
    head = text[: int(MAX_CONTEXT_CHARS * 0.7)]
    tail = text[-int(MAX_CONTEXT_CHARS * 0.25) :]
    return f"{head}\n\n…(中间省略)…\n\n{tail}"


def build_question_groups(
    ordered_ids: list[int],
    group_keys: dict[int, str],
    *,
    max_per_pack: int = MAX_GROUP_PACK,
) -> list[list[int]]:
    """Pack questions by project/round group; never mix unrelated groups in one batch."""
    groups_order: list[str] = []
    by_group: dict[str, list[int]] = {}
    for qid in ordered_ids:
        gk = (group_keys.get(qid) or "default").strip() or "default"
        if gk not in by_group:
            by_group[gk] = []
            groups_order.append(gk)
        by_group[gk].append(qid)
    packs: list[list[int]] = []
    for gk in groups_order:
        ids = by_group[gk]
        for i in range(0, len(ids), max_per_pack):
            packs.append(ids[i : i + max_per_pack])
    return packs


def _group_label(questions: list[Question]) -> str:
    if not questions:
        return "未分组"
    q0 = questions[0]
    if q0.interview_group_key:
        return q0.interview_group_key.replace("::", " / ")
    if q0.source_anchor:
        return q0.source_anchor
    return "实战面经题目组"


def enqueue_answer_job(
    db: Session,
    *,
    tenant_id: int,
    question_ids: list[int],
    context_md: str,
    doc_name: str = "",
    group_keys: dict[int, str] | None = None,
) -> EnqueueResult | None:
    ids = [int(i) for i in question_ids if i]
    if not ids:
        return None
    gkeys = group_keys or {}
    if not gkeys:
        rows = db.execute(
            select(Question.id, Question.interview_group_key).where(
                Question.id.in_(ids), Question.tenant_id == tenant_id
            )
        ).all()
        gkeys = {int(r[0]): (r[1] or "default") for r in rows}
    packs = build_question_groups(ids, gkeys)
    job = InterviewAnswerJob(
        tenant_id=tenant_id,
        job_id=uuid.uuid4().hex,
        doc_name=(doc_name or "")[:200],
        status="queued",
        context_md=_truncate_context(context_md),
        question_ids=ids,
        question_groups=packs,
        cursor=0,
        completed_count=0,
        failed_count=0,
    )
    db.add(job)
    db.flush()
    return EnqueueResult(job_id=job.job_id, queued=len(ids), pack_count=len(packs))


def get_job(db: Session, job_id: str, *, tenant_id: int) -> InterviewAnswerJob | None:
    return db.execute(
        select(InterviewAnswerJob).where(
            InterviewAnswerJob.job_id == job_id,
            InterviewAnswerJob.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()


def list_recent_jobs(
    db: Session, *, tenant_id: int, limit: int = 10
) -> list[InterviewAnswerJob]:
    return list(
        db.execute(
            select(InterviewAnswerJob)
            .where(InterviewAnswerJob.tenant_id == tenant_id)
            .order_by(InterviewAnswerJob.created_at.desc())
            .limit(limit)
        ).scalars().all()
    )


def _pick_active_job(db: Session) -> InterviewAnswerJob | None:
    return db.execute(
        select(InterviewAnswerJob)
        .where(InterviewAnswerJob.status.in_(("queued", "running")))
        .order_by(InterviewAnswerJob.created_at.asc())
        .limit(1)
    ).scalar_one_or_none()


def _next_batch_ids(job: InterviewAnswerJob) -> list[int]:
    packs: list[list[int]] = list(job.question_groups or [])
    if packs:
        if job.cursor >= len(packs):
            return []
        return [int(i) for i in packs[job.cursor]]
    ids: list[int] = list(job.question_ids or [])
    if job.cursor >= len(ids):
        return []
    return ids[job.cursor : job.cursor + BATCH_SIZE]


def _advance_cursor(job: InterviewAnswerJob, batch_len: int) -> None:
    packs: list[list[int]] = list(job.question_groups or [])
    if packs:
        job.cursor += 1
        if job.cursor >= len(packs):
            job.status = "completed"
        return
    job.cursor += batch_len
    if job.cursor >= len(job.question_ids or []):
        job.status = "completed"


async def process_next_batch(db: Session) -> bool:
    """Process one pack from the oldest active job. Returns True if work was done."""
    job = _pick_active_job(db)
    if job is None:
        return False

    batch_ids = _next_batch_ids(job)
    if not batch_ids:
        job.status = "completed"
        db.flush()
        return True

    job.status = "running"
    questions = db.execute(
        select(Question).where(
            Question.id.in_(batch_ids),
            Question.tenant_id == job.tenant_id,
            Question.source_kind == SOURCE_KIND_INTERVIEW,
            Question.deleted_at.is_(None),
        )
    ).scalars().all()
    by_id = {q.id: q for q in questions}
    ordered = [by_id[i] for i in batch_ids if i in by_id]
    if not ordered:
        _advance_cursor(job, len(batch_ids))
        db.flush()
        return True

    group_label = _group_label(ordered)
    payload = [
        {"index": i, "question": q.question_text}
        for i, q in enumerate(ordered)
    ]
    try:
        client, prompt = LLMClient.for_scene(
            db, "interview_answer_generation", tenant_id=job.tenant_id
        )
        rendered = (
            prompt.content.replace("{CONTEXT}", job.context_md)
            .replace("{GROUP_LABEL}", group_label)
            .replace("{QUESTIONS_JSON}", json.dumps(payload, ensure_ascii=False, indent=2))
        )
        items, _resp = await client.chat_json(
            [LLMMessage(role="user", content=rendered)],
            schema=ANSWER_SCHEMA,
        )
        if not isinstance(items, list):
            raise LLMError("模型返回格式无效")
        by_index = {
            int(it.get("index")): it
            for it in items
            if isinstance(it, dict) and it.get("index") is not None
        }
        for i, q in enumerate(ordered):
            data = by_index.get(i)
            if not data:
                q.interview_answer_status = INTERVIEW_ANSWER_STATUS_FAILED
                job.failed_count += 1
                continue
            answer = str(data.get("answer", "")).strip()
            if len(answer) < 20:
                q.interview_answer_status = INTERVIEW_ANSWER_STATUS_FAILED
                job.failed_count += 1
                continue
            q.answer_standard = answer
            q.difficulty = str(data.get("difficulty", q.difficulty))
            q.qtype = str(data.get("type", q.qtype))
            q.interview_answer_status = INTERVIEW_ANSWER_STATUS_READY
            q.generated_by_prompt_id = prompt.id
            q.generated_by_model_id = client.model.id
            for tag_name in data.get("tag") or []:
                tag = _upsert_tag(db, str(tag_name), tenant_id=job.tenant_id)
                exists = db.execute(
                    select(QuestionTag).where(
                        QuestionTag.question_id == q.id,
                        QuestionTag.tag_id == tag.id,
                    )
                ).scalar_one_or_none()
                if exists is None:
                    db.add(QuestionTag(question_id=q.id, tag_id=tag.id))
            job.completed_count += 1
            try:
                from app.services.question_embedding_service import ensure_question_embedding

                ensure_question_embedding(db, q)
            except Exception as exc:
                log.warning("embedding refresh q=%s: %s", q.id, exc)
        _advance_cursor(job, len(batch_ids))
        job.last_error = None
    except LLMError as exc:
        job.last_error = str(exc)[:500]
        for q in ordered:
            if q.interview_answer_status == INTERVIEW_ANSWER_STATUS_PENDING:
                q.interview_answer_status = INTERVIEW_ANSWER_STATUS_FAILED
                job.failed_count += 1
        _advance_cursor(job, len(batch_ids))
        if job.status != "completed":
            job.status = "failed" if job.completed_count == 0 else "completed"
        log.warning("interview answer batch failed job=%s: %s", job.job_id, exc)
    except Exception as exc:
        job.last_error = str(exc)[:500]
        job.status = "failed"
        log.exception("interview answer job %s crashed", job.job_id)

    db.flush()
    return True


def enqueue_backfill_pending(
    db: Session,
    *,
    tenant_id: int,
    doc_name: str = "待补全",
    context_md: str = "",
) -> EnqueueResult | None:
    """Queue answer generation for interview questions still on placeholder."""
    rows = list(
        db.execute(
            select(Question).where(
                Question.tenant_id == tenant_id,
                Question.source_kind == SOURCE_KIND_INTERVIEW,
                Question.deleted_at.is_(None),
                Question.interview_answer_status.in_(
                    [INTERVIEW_ANSWER_STATUS_PENDING, INTERVIEW_ANSWER_STATUS_FAILED]
                ),
            )
        ).scalars().all()
    )
    if not rows:
        rows = list(
            db.execute(
                select(Question).where(
                    Question.tenant_id == tenant_id,
                    Question.source_kind == SOURCE_KIND_INTERVIEW,
                    Question.deleted_at.is_(None),
                    Question.answer_standard == INTERVIEW_ANSWER_PLACEHOLDER,
                )
            ).scalars().all()
        )
    if not rows:
        return None
    rows.sort(key=lambda q: (q.interview_group_key or q.source_anchor or "", q.id))
    for q in rows:
        q.interview_answer_status = INTERVIEW_ANSWER_STATUS_PENDING
        q.answer_standard = INTERVIEW_ANSWER_PLACEHOLDER
    ctx = context_md or (
        "（无原始面经全文，请根据题干本身撰写通用但高质量的技术面试参考答案。）"
    )
    group_keys = {
        q.id: (q.interview_group_key or q.source_anchor or "default") for q in rows
    }
    return enqueue_answer_job(
        db,
        tenant_id=tenant_id,
        question_ids=[q.id for q in rows],
        context_md=ctx,
        doc_name=doc_name,
        group_keys=group_keys,
    )
