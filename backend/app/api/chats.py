"""Chat endpoints — list/create/update, message send, SSE stream (PRD §6.2)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.deps import AuthContext, get_auth_context
from app.db.session import SessionLocal, get_db
from app.models import Chat, Message
from app.schemas.chat import (
    ChatCreate,
    ChatDetail,
    ChatSummary,
    ChatUpdate,
    MessageSummary,
    SaveToWikiRequest,
    SaveToWikiResponse,
    SendMessageRequest,
    SendMessageResponse,
    UploadResponse,
)
from app.services.chat_service import (
    send_and_reply_nonstream,
    stream_reply,
)
from app.services.chat_wiki_service import (
    save_conversation_to_wiki,
    save_message_to_wiki,
)
from app.services.llm import LLMError

router = APIRouter()


# ---- Chat CRUD -------------------------------------------------------------


@router.get("", response_model=list[ChatSummary])
def list_chats(
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> list[ChatSummary]:
    rows = db.execute(
        select(Chat)
        .where(Chat.tenant_id == ctx.tenant_id)
        .order_by(Chat.updated_at.desc())
    ).scalars().all()
    return [ChatSummary.model_validate(c) for c in rows]


@router.post("", response_model=ChatDetail, status_code=status.HTTP_201_CREATED)
def create_chat(
    payload: ChatCreate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> ChatDetail:
    c = Chat(
        tenant_id=ctx.tenant_id,
        title=payload.title or "新对话",
        model_id=payload.model_id,
        prompt_template_id=payload.prompt_template_id,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return ChatDetail(
        id=c.id,
        title=c.title,
        model_id=c.model_id,
        prompt_template_id=c.prompt_template_id,
        created_at=c.created_at,
        updated_at=c.updated_at,
        messages=[],
    )


@router.get("/{chat_id}", response_model=ChatDetail)
def get_chat(
    chat_id: int,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> ChatDetail:
    chat = db.execute(
        select(Chat)
        .where(Chat.id == chat_id, Chat.tenant_id == ctx.tenant_id)
        .options(selectinload(Chat.messages))
    ).scalar_one_or_none()
    if chat is None:
        raise HTTPException(404, detail="chat not found")
    return ChatDetail(
        id=chat.id,
        title=chat.title,
        model_id=chat.model_id,
        prompt_template_id=chat.prompt_template_id,
        created_at=chat.created_at,
        updated_at=chat.updated_at,
        messages=[MessageSummary.model_validate(m) for m in chat.messages],
    )


@router.patch("/{chat_id}", response_model=ChatSummary)
def update_chat(
    chat_id: int,
    payload: ChatUpdate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> ChatSummary:
    chat = db.get(Chat, chat_id)
    if chat is None or chat.tenant_id != ctx.tenant_id:
        raise HTTPException(404, detail="chat not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(chat, k, v)
    db.commit()
    db.refresh(chat)
    return ChatSummary.model_validate(chat)


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat(
    chat_id: int,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> None:
    chat = db.get(Chat, chat_id)
    if chat is None or chat.tenant_id != ctx.tenant_id:
        raise HTTPException(404, detail="chat not found")
    db.delete(chat)
    db.commit()


# ---- Save to wiki (knowledge base) -----------------------------------------


@router.post("/{chat_id}/save-to-wiki", response_model=SaveToWikiResponse)
def save_chat_to_wiki(
    chat_id: int,
    payload: SaveToWikiRequest,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> SaveToWikiResponse:
    chat = db.execute(
        select(Chat)
        .where(Chat.id == chat_id, Chat.tenant_id == ctx.tenant_id)
        .options(selectinload(Chat.messages))
    ).scalar_one_or_none()
    if chat is None:
        raise HTTPException(404, detail="chat not found")
    try:
        wiki_id, title = save_conversation_to_wiki(
            db, chat, list(chat.messages), title=payload.title, tenant_id=ctx.tenant_id
        )
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    db.commit()
    return SaveToWikiResponse(wiki_id=wiki_id, title=title, url_path=f"/wiki/{wiki_id}")


@router.post(
    "/{chat_id}/messages/{message_id}/save-to-wiki",
    response_model=SaveToWikiResponse,
)
def save_message_to_wiki_endpoint(
    chat_id: int,
    message_id: int,
    payload: SaveToWikiRequest,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> SaveToWikiResponse:
    chat = db.get(Chat, chat_id)
    if chat is None or chat.tenant_id != ctx.tenant_id:
        raise HTTPException(404, detail="chat not found")
    message = db.get(Message, message_id)
    if message is None or message.chat_id != chat_id:
        raise HTTPException(404, detail="message not found")
    try:
        wiki_id, title = save_message_to_wiki(
            db, chat, message, title=payload.title, tenant_id=ctx.tenant_id
        )
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    db.commit()
    return SaveToWikiResponse(wiki_id=wiki_id, title=title, url_path=f"/wiki/{wiki_id}")


# ---- Send messages ---------------------------------------------------------


def _attachments_to_persist(req: SendMessageRequest) -> list[dict]:
    return [{"id": a.id, "mime": a.mime} for a in req.attachments]


@router.post("/{chat_id}/messages", response_model=SendMessageResponse)
async def send_message(
    chat_id: int,
    payload: SendMessageRequest,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> SendMessageResponse:
    chat = db.execute(
        select(Chat)
        .where(Chat.id == chat_id, Chat.tenant_id == ctx.tenant_id)
        .options(selectinload(Chat.messages))
    ).scalar_one_or_none()
    if chat is None:
        raise HTTPException(404, detail="chat not found")
    try:
        user_msg, assistant_msg = await send_and_reply_nonstream(
            db,
            chat,
            user_text=payload.content,
            user_attachments=_attachments_to_persist(payload),
            override_model_id=payload.model_id,
            use_rag=payload.use_rag,
        )
    except LLMError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    db.commit()
    return SendMessageResponse(
        user_message=MessageSummary.model_validate(user_msg),
        assistant_message=MessageSummary.model_validate(assistant_msg),
    )


@router.post("/{chat_id}/stream")
async def stream_message(
    chat_id: int,
    payload: SendMessageRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """SSE stream. We open our own session per request so the response can
    keep yielding even after the request handler returns."""
    tenant_id = ctx.tenant_id

    async def event_source():
        db = SessionLocal()
        try:
            chat = db.execute(
                select(Chat)
                .where(Chat.id == chat_id, Chat.tenant_id == tenant_id)
                .options(selectinload(Chat.messages))
            ).scalar_one_or_none()
            if chat is None:
                yield _sse("error", {"message": "chat not found"})
                return
            try:
                stream_gen, persist = await stream_reply(
                    db,
                    chat,
                    user_text=payload.content,
                    user_attachments=_attachments_to_persist(payload),
                    override_model_id=payload.model_id,
                    use_rag=payload.use_rag,
                )
                async for delta in stream_gen:
                    yield _sse("delta", {"text": delta})
                yield _sse(
                    "done",
                    {
                        "chat_id": chat.id,
                        "user_message_id": persist.user_message_id,
                        "assistant_message_id": persist.assistant_message_id,
                        "assistant_saved": persist.assistant_saved,
                        "interrupted": persist.interrupted,
                        "rag_sources": persist.rag_sources,
                    },
                )
            except LLMError as exc:
                yield _sse("error", {"message": str(exc)})
            except Exception as exc:  # noqa: BLE001
                yield _sse("error", {"message": f"internal error: {exc}"})
        finally:
            db.close()

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ---- Attachments -----------------------------------------------------------

attachments_router = APIRouter()

_ALLOWED_IMAGE_MIME = {"image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp"}


@attachments_router.post("", response_model=UploadResponse)
async def upload_attachment(
    file: UploadFile = File(...),
) -> UploadResponse:
    mime = (file.content_type or "").lower()
    if mime not in _ALLOWED_IMAGE_MIME:
        raise HTTPException(400, detail=f"不支持的图片类型: {mime or '未知'}")
    raw = await file.read()
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(400, detail="图片过大,限制 8MB")
    settings = get_settings()
    settings.attachments_dir.mkdir(parents=True, exist_ok=True)
    att_id = f"{datetime.utcnow():%Y%m%d}-{uuid.uuid4().hex[:12]}"
    path = settings.attachments_dir / att_id
    path.write_bytes(raw)
    return UploadResponse(
        id=att_id, mime=mime, url=f"/api/attachments/{att_id}", size=len(raw)
    )


@attachments_router.get("/{att_id}")
def get_attachment(att_id: str):
    settings = get_settings()
    p = settings.attachments_dir / att_id
    if not p.exists() or not p.is_file():
        raise HTTPException(404, detail="attachment not found")
    return FileResponse(p)
