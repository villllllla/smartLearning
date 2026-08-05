"""Business facade for IM bots — hides answers when quizzing, reuses core services."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Chat, Question
from app.models.question import Tag
from app.schemas.practice import PracticeSetupRequest
from app.schemas.question import QuestionSummary
from app.services.chat_service import send_and_reply_nonstream
from app.services.practice_service import setup_questions


@dataclass
class QuestionPublic:
    id: int
    question_text: str
    difficulty: str
    qtype: str
    tags: list[str]
    source_wiki_title: str | None = None
    last_grade: str | None = None


@dataclass
class QuestionWithAnswer:
    id: int
    question_text: str
    answer_standard: str
    difficulty: str
    qtype: str
    tags: list[str]


def _tags_names(q: Question) -> list[str]:
    return [t.name for t in (q.tags or [])]


def strip_to_public(summary: QuestionSummary) -> QuestionPublic:
    return QuestionPublic(
        id=summary.id,
        question_text=summary.question_text,
        difficulty=summary.difficulty,
        qtype=summary.qtype,
        tags=[t.name for t in summary.tags],
        source_wiki_title=summary.source_wiki_title,
        last_grade=summary.last_grade,
    )


def draw_questions(
    db: Session,
    *,
    tenant_id: int = 1,
    limit: int = 5,
    mode: str = "random",
    difficulties: list[str] | None = None,
    qtypes: list[str] | None = None,
    tag_ids: list[int] | None = None,
    tag_mode: str = "or",
    collection_id: int | None = None,
    source_kinds: list[str] | None = None,
) -> list[QuestionPublic]:
    payload = PracticeSetupRequest(
        limit=limit,
        mode=mode,  # type: ignore[arg-type]
        difficulties=difficulties or [],  # type: ignore[arg-type]
        qtypes=qtypes or [],  # type: ignore[arg-type]
        tag_ids=tag_ids or [],
        tag_mode=tag_mode,  # type: ignore[arg-type]
        collection_id=collection_id,
        source_kinds=source_kinds or [],  # type: ignore[arg-type]
    )
    result = setup_questions(db, payload, tenant_id=tenant_id)
    return [strip_to_public(q) for q in result.questions]


def resolve_tag_ids_by_names(db: Session, names: list[str]) -> list[int]:
    if not names:
        return []
    rows = db.execute(select(Tag).where(Tag.name.in_(names))).scalars().all()
    found = {t.name.lower(): t.id for t in rows}
    ids: list[int] = []
    for n in names:
        tid = found.get(n.lower())
        if tid is not None:
            ids.append(tid)
    return ids


def get_answer(db: Session, question_id: int) -> QuestionWithAnswer | None:
    q = db.execute(
        select(Question)
        .where(Question.id == question_id, Question.deleted_at.is_(None))
        .options(selectinload(Question.tags))
    ).scalar_one_or_none()
    if q is None:
        return None
    return QuestionWithAnswer(
        id=q.id,
        question_text=q.question_text,
        answer_standard=q.answer_standard,
        difficulty=q.difficulty,
        qtype=q.qtype,
        tags=_tags_names(q),
    )


def get_question_public(db: Session, question_id: int) -> QuestionPublic | None:
    q = db.execute(
        select(Question)
        .where(Question.id == question_id, Question.deleted_at.is_(None))
        .options(selectinload(Question.tags))
    ).scalar_one_or_none()
    if q is None:
        return None
    return QuestionPublic(
        id=q.id,
        question_text=q.question_text,
        difficulty=q.difficulty,
        qtype=q.qtype,
        tags=_tags_names(q),
    )


async def chat_reply(
    db: Session,
    chat: Chat,
    user_text: str,
    *,
    use_rag: bool | None = None,
) -> str:
    _, assistant = await send_and_reply_nonstream(
        db, chat, user_text=user_text, user_attachments=None, use_rag=use_rag
    )
    db.commit()
    return assistant.content_text


def create_chat(db: Session, *, title: str = "飞书对话", tenant_id: int = 1) -> Chat:
    c = Chat(tenant_id=tenant_id, title=title)
    db.add(c)
    db.flush()
    return c
