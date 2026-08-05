"""CRUD for IM bot per-user session state."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.bot_session import BotSession


def get_or_create_session(
    db: Session, *, platform: str, feishu_open_id: str, feishu_chat_id: str | None
) -> BotSession:
    row = db.execute(
        select(BotSession).where(
            BotSession.platform == platform,
            BotSession.feishu_open_id == feishu_open_id,
        )
    ).scalar_one_or_none()
    if row is None:
        row = BotSession(
            platform=platform,
            feishu_open_id=feishu_open_id,
            feishu_chat_id=feishu_chat_id,
            question_queue_json=[],
            queue_cursor=0,
        )
        db.add(row)
        db.flush()
    elif feishu_chat_id and row.feishu_chat_id != feishu_chat_id:
        row.feishu_chat_id = feishu_chat_id
    return row


def set_question_queue(session: BotSession, question_ids: list[int]) -> None:
    session.question_queue_json = question_ids
    session.queue_cursor = 0
    session.current_question_id = question_ids[0] if question_ids else None


def advance_queue(session: BotSession) -> int | None:
    """Move cursor to next question; return its id or None."""
    ids = list(session.question_queue_json or [])
    if not ids:
        session.current_question_id = None
        return None
    session.queue_cursor = min(session.queue_cursor + 1, len(ids) - 1)
    qid = ids[session.queue_cursor]
    session.current_question_id = qid
    return qid


def current_question_id(session: BotSession) -> int | None:
    ids = list(session.question_queue_json or [])
    if not ids:
        return None
    idx = min(session.queue_cursor, len(ids) - 1)
    return int(ids[idx])
