"""Provider & Model API schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .common import ORMBase

PROVIDER_TYPES = ("openai_compatible", "ollama", "anthropic", "custom")


class ModelSummary(ORMBase):
    id: int
    provider_id: int
    name: str
    supports_vision: bool
    supports_streaming: bool
    context_window: int
    is_default: bool
    enabled: bool
    created_at: datetime


class ModelCreate(BaseModel):
    name: str
    supports_vision: bool = False
    supports_streaming: bool = True
    context_window: int = 8192
    is_default: bool = False
    enabled: bool = True


class ModelUpdate(BaseModel):
    name: str | None = None
    supports_vision: bool | None = None
    supports_streaming: bool | None = None
    context_window: int | None = None
    is_default: bool | None = None
    enabled: bool | None = None


class ProviderSummary(ORMBase):
    id: int
    name: str
    type: str
    base_url: str
    enabled: bool
    has_api_key: bool = Field(False, description="是否已配置 API Key (不返回明文)")
    masked_api_key: str = ""
    created_at: datetime
    models: list[ModelSummary] = []


class ProviderCreate(BaseModel):
    name: str
    type: str
    base_url: str = ""
    api_key: str | None = None
    enabled: bool = False


class ProviderUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    base_url: str | None = None
    api_key: str | None = Field(
        None,
        description='传入空字符串 "" 视为「保留原 Key 不变」;传入 null 表示「清除」;传入新值表示「替换」',
    )
    enabled: bool | None = None


class ConnectivityResult(BaseModel):
    ok: bool
    elapsed_ms: int
    detail: str = ""
    discovered_models: list[str] = []
    chat_probe_ok: bool | None = Field(
        None,
        description="None=未探测；True/False=最小 chat 补全是否成功",
    )
    chat_probe_elapsed_ms: int | None = None
    chat_probe_detail: str = ""
    request_timeout_seconds: int = Field(
        0,
        description="当前 SL_MODEL_REQUEST_TIMEOUT_SECONDS，供生成类调用参考",
    )
