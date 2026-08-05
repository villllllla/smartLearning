"""AnswerAttempt (PRD §6.4.4)."""
from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class AnswerAttempt(Base, TimestampMixin):
    __tablename__ = "answer_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # phase-2

    # Provenance: web practice vs Feishu bot (null = legacy / unspecified web)
    channel: Mapped[str | None] = mapped_column(String(16), nullable=True)
    feishu_open_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    feishu_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    bot_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("bot_sessions.id", ondelete="SET NULL"), nullable=True
    )

    user_answer_text: Mapped[str] = mapped_column(Text, nullable=False)

    grade: Mapped[str] = mapped_column(String(2), nullable=False)  # S/A/B/C
    score_correctness: Mapped[int] = mapped_column(Integer, nullable=False)
    score_completeness: Mapped[int] = mapped_column(Integer, nullable=False)
    score_structure: Mapped[int] = mapped_column(Integer, nullable=False)
    score_depth: Mapped[int] = mapped_column(Integer, nullable=False)

    feedback_text: Mapped[str] = mapped_column(Text, nullable=False, default="")

    model_id: Mapped[int | None] = mapped_column(
        ForeignKey("models.id", ondelete="SET NULL"), nullable=True
    )
    prompt_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("prompt_templates.id", ondelete="SET NULL"), nullable=True
    )

    question: Mapped["Question"] = relationship(back_populates="attempts")  # noqa: F821

    __table_args__ = (
        Index("ix_attempts_question_created", "question_id", "created_at"),
        Index("ix_attempts_feishu_open_id", "feishu_open_id", "created_at"),
    )
