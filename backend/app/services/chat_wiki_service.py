"""Persist chat messages into the wiki knowledge base."""
from __future__ import annotations

import logging
import re
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import Chat, Message
from app.services.wiki_service import create_wiki_from_markdown

log = logging.getLogger(__name__)


def _safe_slug(text: str, fallback: str = "chat") -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", (text or "").strip(), flags=re.UNICODE).strip(
        "-"
    )
    return (s[:48] or fallback)


def _maybe_reindex_wiki(db: Session, wiki_id: int, settings: Settings) -> None:
    if not settings.rag_enabled or not settings.rag_auto_index:
        return
    try:
        from app.services.rag.index_service import index_wiki

        index_wiki(db, wiki_id, settings)
    except Exception as exc:  # noqa: BLE001
        log.warning("RAG auto-index after save-to-wiki failed wiki_id=%s: %s", wiki_id, exc)


def format_conversation_md(chat: Chat, messages: list[Message], *, title: str | None = None) -> str:
    heading = title or chat.title or "对话摘录"
    lines = [f"# {heading}", ""]
    for m in messages:
        if m.role == "system":
            continue
        label = "用户" if m.role == "user" else "助手"
        ts = m.created_at.strftime("%Y-%m-%d %H:%M") if m.created_at else ""
        lines.append(f"## {label}" + (f" ({ts})" if ts else ""))
        lines.append("")
        lines.append((m.content_text or "").strip())
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def save_message_to_wiki(
    db: Session,
    chat: Chat,
    message: Message,
    *,
    title: str | None = None,
    tenant_id: int,
) -> tuple[int, str]:
    """Create a new wiki from one chat message."""
    if message.chat_id != chat.id:
        raise ValueError("message does not belong to chat")
    if not (message.content_text or "").strip():
        raise ValueError("message is empty")

    base_title = title or _derive_title(chat, message)
    body = (message.content_text or "").strip()
    if not body.lstrip().startswith("#"):
        content_md = f"# {base_title}\n\n{body}\n"
    else:
        content_md = body if body.endswith("\n") else body + "\n"

    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M")
    filename = f"{_safe_slug(base_title)}-{stamp}.md"
    wiki = create_wiki_from_markdown(
        db, tenant_id=tenant_id, filename=filename, content_md=content_md
    )
    db.flush()
    _maybe_reindex_wiki(db, wiki.id, get_settings())
    return wiki.id, wiki.title


def save_conversation_to_wiki(
    db: Session,
    chat: Chat,
    messages: list[Message],
    *,
    title: str | None = None,
    tenant_id: int,
) -> tuple[int, str]:
    """Create a new wiki containing the full user/assistant conversation."""
    visible = [m for m in messages if m.role in ("user", "assistant")]
    if not visible:
        raise ValueError("no messages to save")

    base_title = title or chat.title or "对话摘录"
    content_md = format_conversation_md(chat, visible, title=base_title)
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M")
    filename = f"{_safe_slug(base_title)}-{stamp}.md"
    wiki = create_wiki_from_markdown(
        db, tenant_id=tenant_id, filename=filename, content_md=content_md
    )
    db.flush()
    _maybe_reindex_wiki(db, wiki.id, get_settings())
    return wiki.id, wiki.title


def _derive_title(chat: Chat, message: Message) -> str:
    first_line = (message.content_text or "").strip().splitlines()[0][:60]
    first_line = re.sub(r"^#+\s*", "", first_line).strip()
    if first_line:
        return first_line
    return f"{chat.title or '对话'}-摘录"
