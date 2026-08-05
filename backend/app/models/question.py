"""Question / QuestionBankCollection / Tag / QuestionCandidate (PRD §6.3.4)."""
from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin

# simulated = LLM-generated from wiki docs; interview = parsed real interview notes
QUESTION_SOURCE_KINDS = frozenset({"simulated", "interview"})
SOURCE_KIND_SIMULATED = "simulated"
SOURCE_KIND_INTERVIEW = "interview"

INTERVIEW_ANSWER_PLACEHOLDER = (
    "（参考答案生成中，请稍候…）"
)

INTERVIEW_ANSWER_STATUS_PENDING = "pending"
INTERVIEW_ANSWER_STATUS_READY = "ready"
INTERVIEW_ANSWER_STATUS_FAILED = "failed"


class QuestionBankCollection(Base, TimestampMixin):
    __tablename__ = "question_bank_collections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("question_bank_collections.id", ondelete="SET NULL"), nullable=True
    )
    owner_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # phase-2
    visibility: Mapped[str] = mapped_column(String(16), default="private", nullable=False)

    questions: Mapped[list["Question"]] = relationship(back_populates="collection")


class Tag(Base, TimestampMixin):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), default="user", nullable=False)

    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_tags_tenant_name"),)


class Question(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    collection_id: Mapped[int | None] = mapped_column(
        ForeignKey("question_bank_collections.id", ondelete="SET NULL"), nullable=True
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_standard: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)
    qtype: Mapped[str] = mapped_column(String(16), default="concept", nullable=False)
    # simulated | interview
    source_kind: Mapped[str] = mapped_column(
        String(16), default=SOURCE_KIND_SIMULATED, nullable=False
    )
    # pending | ready | failed — only for interview questions awaiting LLM answers
    interview_answer_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Pack key: doc::company::round::topic — questions in same group are batched together
    interview_group_key: Mapped[str | None] = mapped_column(String(128), nullable=True)

    source_wiki_id: Mapped[int | None] = mapped_column(
        ForeignKey("wikis.id", ondelete="SET NULL"), nullable=True
    )
    source_commit_id: Mapped[int | None] = mapped_column(
        ForeignKey("wiki_commits.id", ondelete="SET NULL"), nullable=True
    )
    source_anchor: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Frozen at generation time for reproducibility (PRD §6.2.3)
    generated_by_prompt_id: Mapped[int | None] = mapped_column(
        ForeignKey("prompt_templates.id", ondelete="SET NULL"), nullable=True
    )
    generated_by_model_id: Mapped[int | None] = mapped_column(
        ForeignKey("models.id", ondelete="SET NULL"), nullable=True
    )

    stem_embedding_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(120), nullable=True)

    collection: Mapped[QuestionBankCollection | None] = relationship(back_populates="questions")
    tags: Mapped[list[Tag]] = relationship(secondary="question_tags")
    attempts: Mapped[list["AnswerAttempt"]] = relationship(  # noqa: F821
        back_populates="question",
    )

    __table_args__ = (
        Index("ix_questions_collection", "collection_id"),
        Index("ix_questions_source_wiki", "source_wiki_id"),
        Index("ix_questions_difficulty", "difficulty"),
        Index("ix_questions_source_kind", "source_kind"),
    )


class QuestionTag(Base):
    __tablename__ = "question_tags"

    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )


class QuestionCandidate(Base, TimestampMixin):
    """Preview-panel temporary table for the generation flow (PRD §6.3.3)."""

    __tablename__ = "question_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    picked: Mapped[bool] = mapped_column(default=False, nullable=False)
    edited: Mapped[bool] = mapped_column(default=False, nullable=False)

    source_wiki_id: Mapped[int | None] = mapped_column(
        ForeignKey("wikis.id", ondelete="SET NULL"), nullable=True
    )
    source_commit_id: Mapped[int | None] = mapped_column(
        ForeignKey("wiki_commits.id", ondelete="SET NULL"), nullable=True
    )
    generated_by_prompt_id: Mapped[int | None] = mapped_column(
        ForeignKey("prompt_templates.id", ondelete="SET NULL"), nullable=True
    )
    generated_by_model_id: Mapped[int | None] = mapped_column(
        ForeignKey("models.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        Index("ix_question_candidates_batch", "batch_id"),
        UniqueConstraint("batch_id", "id", name="uq_candidate_batch_id"),
    )


class InterviewAnswerJob(Base, TimestampMixin):
    """Queue: batch-generate standard answers for imported interview questions."""

    __tablename__ = "interview_answer_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    doc_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    context_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    question_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    # Each inner list = one related project/round pack sent to LLM together
    question_groups: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    cursor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_interview_answer_jobs_tenant_status", "tenant_id", "status"),
    )
