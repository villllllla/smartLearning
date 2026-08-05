"""Configurable Feishu bot trigger phrases (prefix / exact match → tool)."""
from __future__ import annotations

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class FeishuTriggerRule(Base, TimestampMixin):
    __tablename__ = "feishu_trigger_rules"
    __table_args__ = (
        UniqueConstraint("tenant_id", "action", name="uq_feishu_trigger_tenant_action"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Tool name executed by agent/tools.py, e.g. submit_learning_note, push_now
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # prefix: message starts with phrase + body; exact: message equals phrase
    match_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="exact")
    prefixes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    extra_args_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
