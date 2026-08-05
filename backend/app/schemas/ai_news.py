"""AI news digest + schedule API schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .common import ORMBase

NewsFrequency = Literal["daily", "weekdays", "weekly"]


class RssFeed(BaseModel):
    name: str
    url: str


class AiNewsItemRead(ORMBase):
    id: int
    rank: int
    title: str
    original_title: str
    url: str
    source: str
    summary: str
    heat_score: int
    why: str | None = None
    raw_score: float
    published_at: datetime | None = None


class AiNewsDigestRead(ORMBase):
    id: int
    run_slot: str | None = None
    item_count: int
    total_candidates: int
    used_llm: bool
    channel: str | None = None
    created_at: datetime
    items: list[AiNewsItemRead] = Field(default_factory=list)


class AiNewsListResponse(BaseModel):
    items: list[AiNewsDigestRead]
    total: int


class AiNewsScheduleRead(BaseModel):
    enabled: bool
    timezone: str
    push_times: list[str]
    frequency: NewsFrequency
    weekdays: list[int] = Field(description="0=Mon .. 6=Sun")
    top_n: int
    enable_hackernews: bool
    enable_github: bool
    enable_arxiv: bool
    enable_huggingface: bool
    enable_reddit: bool
    rss_feeds: list[RssFeed]
    dedup_days: int
    feishu_enabled: bool
    last_run_slot: str | None = None
    last_run_at: datetime | None = None
    last_error: str | None = None


class AiNewsScheduleUpdate(BaseModel):
    enabled: bool | None = None
    timezone: str | None = None
    push_times: list[str] | None = None
    frequency: NewsFrequency | None = None
    weekdays: list[int] | None = None
    top_n: int | None = Field(None, ge=1, le=15)
    enable_hackernews: bool | None = None
    enable_github: bool | None = None
    enable_arxiv: bool | None = None
    enable_huggingface: bool | None = None
    enable_reddit: bool | None = None
    rss_feeds: list[RssFeed] | None = None
    dedup_days: int | None = Field(None, ge=0, le=90)
    feishu_enabled: bool | None = None


class AiNewsTriggerResponse(BaseModel):
    ok: bool
    message: str
    item_count: int = 0
    recipient_count: int = 0
    digest_id: int | None = None
