"""PromptTemplate / FunctionBinding (PRD §6.2.3)."""
from __future__ import annotations

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

# Allowed scenes — kept as plain strings for flexibility (vs SQL ENUM in SQLite)
SCENES = (
    "chat_general",
    "wiki_to_questions",
    "answer_scoring",
    "wiki_summary",
    "learning_note_structuring",
    "todo_intent_parsing",
    "ai_news_curation",
    "plan_decomposition",
    "todo_motivation",
    "interview_answer_generation",
)


class PromptTemplate(Base, TimestampMixin):
    __tablename__ = "prompt_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    scene: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_prompts_scene_version", "scene", "version_no"),
        UniqueConstraint("tenant_id", "scene", "version_no", name="uq_prompt_tenant_scene_version"),
    )


class FunctionBinding(Base, TimestampMixin):
    """One-to-one binding from a scene to its currently active prompt + model."""

    __tablename__ = "function_bindings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scene: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("prompt_templates.id", ondelete="SET NULL"), nullable=True
    )
    model_id: Mapped[int | None] = mapped_column(
        ForeignKey("models.id", ondelete="SET NULL"), nullable=True
    )
    # Used when primary model fails after retries (429/503/connection errors).
    fallback_model_id: Mapped[int | None] = mapped_column(
        ForeignKey("models.id", ondelete="SET NULL"), nullable=True
    )
    params_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    fallback_params_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    prompt_template: Mapped["PromptTemplate | None"] = relationship()

    __table_args__ = (UniqueConstraint("tenant_id", "scene", name="uq_binding_tenant_scene"),)
