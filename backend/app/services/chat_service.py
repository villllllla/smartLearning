"""Chat orchestration: persists messages and dispatches to LLMClient.

Both streaming and non-streaming entries share ``build_llm_messages`` so the
prompt assembly logic stays single-sourced.
"""
from __future__ import annotations

import asyncio
import base64
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Chat, Message, Model
from app.services.llm import LLMClient, LLMError, LLMMessage
from app.services.llm.types import LLMAttachment

log = logging.getLogger(__name__)


@dataclass
class StreamPersistResult:
    """Messages written to DB after a stream completes or is interrupted."""

    user_message_id: int | None = None
    assistant_message_id: int | None = None
    assistant_saved: bool = False
    interrupted: bool = False
    rag_sources: list[dict] = field(default_factory=list)


def _attachment_path(att_id: str) -> Path:
    return get_settings().attachments_dir / att_id


def _load_attachment(att_id: str, mime: str) -> LLMAttachment | None:
    p = _attachment_path(att_id)
    if not p.exists():
        return None
    data_url = f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"
    return LLMAttachment(data_url=data_url, mime=mime)


def build_llm_messages(
    db: Session, chat: Chat, *, system_prompt_text: str | None
) -> list[LLMMessage]:
    msgs: list[LLMMessage] = []
    if system_prompt_text:
        msgs.append(LLMMessage(role="system", content=system_prompt_text))
    for m in chat.messages:
        if m.role == "system":
            continue
        attachments: list[LLMAttachment] = []
        for raw in m.attachments_json or []:
            if not isinstance(raw, dict):
                continue
            att = _load_attachment(str(raw.get("id", "")), str(raw.get("mime", "image/png")))
            if att is not None:
                attachments.append(att)
        msgs.append(LLMMessage(role=m.role, content=m.content_text, attachments=attachments))
    return msgs


def _touch_chat(chat: Chat) -> None:
    chat.updated_at = datetime.now(timezone.utc)


def append_message(
    db: Session,
    chat: Chat,
    *,
    role: str,
    content: str,
    attachments_json: list[dict] | None = None,
    token_usage_json: dict | None = None,
) -> Message:
    now = datetime.now(timezone.utc)
    msg = Message(
        chat_id=chat.id,
        role=role,
        content_text=content,
        attachments_json=attachments_json or [],
        token_usage_json=token_usage_json,
    )
    msg.created_at = now
    msg.updated_at = now
    db.add(msg)
    _touch_chat(chat)
    db.flush()
    return msg


def vision_check(model: Model, attachments_json: list[dict] | None) -> None:
    if attachments_json and not model.supports_vision:
        raise LLMError(
            f"模型 '{model.name}' 不支持图片输入(supports_vision=false)。"
            "请到「设置 → 模型」启用 vision,或选用支持图片的模型。"
        )


def _compose_system_prompt(base: str, rag_suffix: str) -> str:
    if not rag_suffix:
        return base
    return (base or "").rstrip() + rag_suffix


async def send_and_reply_nonstream(
    db: Session,
    chat: Chat,
    *,
    user_text: str,
    user_attachments: list[dict] | None = None,
    override_model_id: int | None = None,
    use_rag: bool | None = None,
) -> tuple[Message, Message]:
    """Persist user msg → call LLM (non-stream) → persist assistant msg."""
    client, prompt = LLMClient.for_scene(
        db,
        "chat_general",
        tenant_id=chat.tenant_id,
        override_model_id=override_model_id or chat.model_id,
    )
    vision_check(client.model, user_attachments)

    user_msg = append_message(
        db,
        chat,
        role="user",
        content=user_text,
        attachments_json=user_attachments,
    )
    db.flush()

    from app.core.config import get_settings
    from app.services.rag.context import build_rag_context
    from app.services.rag.embedder import RagEmbedderError

    settings = get_settings()
    do_rag = settings.rag_enabled and (
        use_rag if use_rag is not None else settings.rag_default_in_chat
    )
    rag_sources: list[dict] = []
    rag_suffix = ""
    if do_rag:
        try:
            rag_suffix, rag_sources = build_rag_context(db, user_text)
        except RagEmbedderError as exc:
            log.warning("RAG unavailable, continuing without retrieval: %s", exc)
            do_rag = False

    llm_messages = build_llm_messages(
        db, chat, system_prompt_text=_compose_system_prompt(prompt.content, rag_suffix)
    )
    response = await client.chat(llm_messages)
    usage: dict = {
        "prompt": response.usage.prompt_tokens,
        "completion": response.usage.completion_tokens,
        "total": response.usage.total_tokens,
        "model": client.model.name,
        "use_rag": do_rag,
        "interrupted": False,
    }
    if rag_sources:
        usage["rag_sources"] = rag_sources
    assistant_msg = append_message(
        db,
        chat,
        role="assistant",
        content=response.text,
        token_usage_json=usage,
    )
    if not chat.title or chat.title == "新对话":
        chat.title = (user_text or "").strip().splitlines()[0][:30] or "新对话"
    db.flush()
    return user_msg, assistant_msg


async def stream_reply(
    db: Session,
    chat: Chat,
    *,
    user_text: str,
    user_attachments: list[dict] | None = None,
    override_model_id: int | None = None,
    use_rag: bool | None = None,
) -> tuple[AsyncIterator[str], StreamPersistResult]:
    """Stream LLM deltas; always persist assistant text in ``finally`` (incl. stop/disconnect)."""
    client, prompt = LLMClient.for_scene(
        db,
        "chat_general",
        tenant_id=chat.tenant_id,
        override_model_id=override_model_id or chat.model_id,
    )
    vision_check(client.model, user_attachments)

    from app.core.config import get_settings
    from app.services.rag.context import build_rag_context
    from app.services.rag.embedder import RagEmbedderError

    settings = get_settings()
    do_rag = settings.rag_enabled and (
        use_rag if use_rag is not None else settings.rag_default_in_chat
    )
    rag_sources: list[dict] = []
    rag_suffix = ""
    if do_rag:
        try:
            rag_suffix, rag_sources = build_rag_context(db, user_text)
        except RagEmbedderError as exc:
            log.warning("RAG unavailable, continuing without retrieval: %s", exc)
            do_rag = False

    user_msg = append_message(
        db,
        chat,
        role="user",
        content=user_text,
        attachments_json=user_attachments,
    )
    db.commit()
    db.refresh(chat)
    db.refresh(user_msg)

    persist = StreamPersistResult(
        user_message_id=user_msg.id,
        rag_sources=rag_sources,
    )

    llm_messages = build_llm_messages(
        db, chat, system_prompt_text=_compose_system_prompt(prompt.content, rag_suffix)
    )

    async def _gen() -> AsyncIterator[str]:
        parts: list[str] = []
        interrupted = False
        try:
            async for delta in client.chat_stream(llm_messages):
                parts.append(delta)
                yield delta
        except (asyncio.CancelledError, GeneratorExit):
            interrupted = True
            raise
        except Exception:
            interrupted = True
            raise
        finally:
            # No early `return` in here: that would swallow whatever exception is
            # propagating (a failed stream would look like a clean finish).
            full_text = "".join(parts)
            if full_text.strip():
                usage: dict = {
                    "model": client.model.name,
                    "use_rag": do_rag,
                    "interrupted": interrupted,
                }
                if rag_sources:
                    usage["rag_sources"] = rag_sources
                try:
                    asst = append_message(
                        db,
                        chat,
                        role="assistant",
                        content=full_text,
                        token_usage_json=usage,
                    )
                    if not chat.title or chat.title == "新对话":
                        chat.title = (user_text or "").strip().splitlines()[0][:30] or "新对话"
                    db.commit()
                    persist.assistant_message_id = asst.id
                    persist.assistant_saved = True
                    persist.interrupted = interrupted
                except Exception:
                    log.exception("failed to persist assistant message chat_id=%s", chat.id)
                    db.rollback()

    return _gen(), persist
