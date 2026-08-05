"""Daily AI-news digests: fetched + LLM-curated top-N, plus push schedule."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class AiNewsDigest(Base, TimestampMixin):
    """One curated batch (top-N) produced by a fetch run."""

    __tablename__ = "ai_news_digests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_slot: Mapped[str | None] = mapped_column(String(32), nullable=True)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_candidates: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    used_llm: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    channel: Mapped[str | None] = mapped_column(String(16), nullable=True)

    items: Mapped[list["AiNewsItem"]] = relationship(
        back_populates="digest",
        cascade="all, delete-orphan",
        order_by="AiNewsItem.rank",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_ai_news_digests_tenant_created", "tenant_id", "created_at"),
    )


class AiNewsItem(Base, TimestampMixin):
    __tablename__ = "ai_news_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    digest_id: Mapped[int] = mapped_column(
        ForeignKey("ai_news_digests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )

    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    title: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    original_title: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    heat_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    why: Mapped[str | None] = mapped_column(String(200), nullable=True)
    raw_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    digest: Mapped["AiNewsDigest"] = relationship(back_populates="items")

    __table_args__ = (
        Index("ix_ai_news_items_tenant_url", "tenant_id", "url"),
    )


class AiNewsSchedule(Base, TimestampMixin):
    """When to fetch + curate + push daily AI news (Feishu)."""

    __tablename__ = "ai_news_schedules"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_ai_news_schedule_tenant"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="Asia/Shanghai"
    )
    push_times: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    frequency: Mapped[str] = mapped_column(String(16), nullable=False, default="daily")
    weekdays: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    top_n: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    enable_hackernews: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enable_github: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enable_arxiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enable_huggingface: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    enable_reddit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # [{"name": "...", "url": "..."}]; empty list means "use defaults".
    rss_feeds: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # Skip items whose URL was pushed within this many days.
    dedup_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)

    feishu_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_run_slot: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
