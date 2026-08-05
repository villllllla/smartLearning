"""LLM client abstraction.

Public surface: ``LLMClient`` plus message/usage dataclasses.
Adapters live in ``adapters.py`` and are dispatched by ``provider.type``.
"""
from .client import LLMClient, LLMError, resolve_for_scene
from .types import LLMAttachment, LLMMessage, LLMResponse, LLMUsage

__all__ = [
    "LLMClient",
    "LLMError",
    "LLMMessage",
    "LLMResponse",
    "LLMUsage",
    "LLMAttachment",
    "resolve_for_scene",
]
