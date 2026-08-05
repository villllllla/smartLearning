"""Feishu webhook message dedup (survives uvicorn --reload)."""
from __future__ import annotations

import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.feishu_processed_message import FeishuProcessedMessage

log = logging.getLogger(__name__)


def try_claim_message(
    db: Session,
    *,
    message_id: str,
    event_id: str,
    text: str,
) -> bool:
    """
    Claim a Feishu user message for processing.

    Returns True if this message_id was already processed (caller should skip).
    Returns False if newly claimed and processing should proceed.
    """
    if not message_id:
        return False

    existing = db.get(FeishuProcessedMessage, message_id)
    if existing is not None:
        log.info(
            "feishu skip already processed message_id=%s event_id=%s preview=%r",
            message_id,
            existing.event_id,
            existing.text_preview,
        )
        return True

    preview = (text or "")[:200] or None
    db.add(
        FeishuProcessedMessage(
            message_id=message_id,
            event_id=event_id or None,
            text_preview=preview,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        log.info("feishu skip race duplicate message_id=%s", message_id)
        return True
    return False
