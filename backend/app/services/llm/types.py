"""Common transit types for LLM calls."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Role = Literal["system", "user", "assistant"]


@dataclass
class LLMAttachment:
    """An image attachment relayed to vision-capable models.

    ``data_url`` is preferred; if absent ``url`` is used. ``mime`` is required
    when ``data_url`` is built from raw bytes by the caller.
    """

    data_url: str | None = None
    url: str | None = None
    mime: str = "image/png"


@dataclass
class LLMMessage:
    role: Role
    content: str
    attachments: list[LLMAttachment] = field(default_factory=list)


@dataclass
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class LLMResponse:
    text: str
    usage: LLMUsage = field(default_factory=LLMUsage)
    finish_reason: str | None = None
