"""Chat / Message API schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .common import ORMBase


class AttachmentRef(BaseModel):
    """Frontend → backend reference to a previously uploaded file."""

    id: str = Field(..., description="服务端返回的附件 id")
    mime: str = "image/png"


class AttachmentInfo(BaseModel):
    id: str
    mime: str
    url: str


class MessageSummary(ORMBase):
    id: int
    chat_id: int
    role: str
    content_text: str
    attachments_json: list = Field(default_factory=list)
    token_usage_json: dict | None = None
    created_at: datetime


class ChatSummary(ORMBase):
    id: int
    title: str
    model_id: int | None
    prompt_template_id: int | None
    created_at: datetime
    updated_at: datetime


class ChatDetail(ChatSummary):
    messages: list[MessageSummary] = Field(default_factory=list)


class ChatCreate(BaseModel):
    title: str | None = None
    model_id: int | None = None
    prompt_template_id: int | None = None


class ChatUpdate(BaseModel):
    title: str | None = None
    model_id: int | None = None
    prompt_template_id: int | None = None


class SendMessageRequest(BaseModel):
    content: str
    attachments: list[AttachmentRef] = Field(default_factory=list)
    model_id: int | None = Field(
        None, description="若指定则仅本次使用,不修改 chat 默认绑定"
    )
    use_rag: bool | None = Field(
        None,
        description="是否检索 Wiki 知识库注入上下文；默认跟随 SL_RAG_DEFAULT_IN_CHAT",
    )


class SendMessageResponse(BaseModel):
    user_message: MessageSummary
    assistant_message: MessageSummary


class UploadResponse(BaseModel):
    id: str
    mime: str
    url: str
    size: int


class SaveToWikiRequest(BaseModel):
    title: str | None = Field(None, description="自定义 Wiki 标题；默认从内容或会话名推导")


class SaveToWikiResponse(BaseModel):
    wiki_id: int
    title: str
    url_path: str
