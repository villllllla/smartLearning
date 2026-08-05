"""Feishu trigger prefix configuration schemas."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .common import ORMBase

MatchMode = Literal["prefix", "exact"]


class FeishuTriggerRuleRead(ORMBase):
    id: int
    action: str
    title: str
    description: str | None = None
    match_mode: MatchMode
    prefixes: list[str]
    enabled: bool
    priority: int
    is_system: bool


class FeishuTriggerRuleUpdate(BaseModel):
    action: str
    prefixes: list[str] | None = None
    match_mode: MatchMode | None = None
    enabled: bool | None = None


class FeishuTriggerListResponse(BaseModel):
    items: list[FeishuTriggerRuleRead]


class FeishuTriggerBulkUpdate(BaseModel):
    items: list[FeishuTriggerRuleUpdate] = Field(..., min_length=1)
