"""Wiki / WikiCollection / WikiBranch / WikiCommit (PRD §6.1.4)."""
from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin


class WikiCollection(Base, TimestampMixin):
    __tablename__ = "wiki_collections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("wiki_collections.id", ondelete="SET NULL"), nullable=True
    )
    owner_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # phase-2 reserved
    visibility: Mapped[str] = mapped_column(String(16), default="private", nullable=False)

    wikis: Mapped[list["Wiki"]] = relationship(back_populates="collection")


class Wiki(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "wikis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    collection_id: Mapped[int | None] = mapped_column(
        ForeignKey("wiki_collections.id", ondelete="SET NULL"), nullable=True
    )
    owner_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # phase-2 reserved

    # The WikiCommit currently representing the head of the main branch.
    # Nullable because the row exists *before* its first commit is created
    # (we create them in the same transaction but the FK direction matters).
    current_main_commit_id: Mapped[int | None] = mapped_column(
        ForeignKey("wiki_commits.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )

    # Cached metadata for list views (cheap to denormalize)
    word_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Vault-relative path (posix), used to avoid duplicate wikis after sync-state loss.
    obsidian_rel_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    collection: Mapped[WikiCollection | None] = relationship(back_populates="wikis")
    branches: Mapped[list["WikiBranch"]] = relationship(
        back_populates="wiki", cascade="all, delete-orphan", foreign_keys="WikiBranch.wiki_id"
    )
    commits: Mapped[list["WikiCommit"]] = relationship(
        back_populates="wiki",
        cascade="all, delete-orphan",
        foreign_keys="WikiCommit.wiki_id",
    )
    current_main_commit: Mapped["WikiCommit | None"] = relationship(
        foreign_keys=[current_main_commit_id], post_update=True
    )

    __table_args__ = (
        Index("ix_wikis_title", "title"),
        Index("ix_wikis_deleted", "deleted_at"),
        Index("ix_wikis_obsidian_rel_path", "obsidian_rel_path"),
    )


class WikiBranch(Base, TimestampMixin):
    __tablename__ = "wiki_branches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    wiki_id: Mapped[int] = mapped_column(ForeignKey("wikis.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    head_commit_id: Mapped[int | None] = mapped_column(
        ForeignKey("wiki_commits.id", ondelete="SET NULL", use_alter=True), nullable=True
    )

    wiki: Mapped[Wiki] = relationship(back_populates="branches", foreign_keys=[wiki_id])
    head_commit: Mapped["WikiCommit | None"] = relationship(
        foreign_keys=[head_commit_id], post_update=True
    )

    __table_args__ = (Index("ix_wiki_branches_wiki_name", "wiki_id", "name", unique=True),)


class WikiCommit(Base, TimestampMixin):
    __tablename__ = "wiki_commits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    wiki_id: Mapped[int] = mapped_column(ForeignKey("wikis.id", ondelete="CASCADE"), nullable=False)
    branch_id: Mapped[int] = mapped_column(
        ForeignKey("wiki_branches.id", ondelete="CASCADE"), nullable=False
    )
    parent_commit_id: Mapped[int | None] = mapped_column(
        ForeignKey("wiki_commits.id", ondelete="SET NULL"), nullable=True
    )
    author_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # phase-2 reserved
    message: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    wiki: Mapped[Wiki] = relationship(back_populates="commits", foreign_keys=[wiki_id])
    branch: Mapped[WikiBranch] = relationship(foreign_keys=[branch_id])

    __table_args__ = (
        Index("ix_wiki_commits_wiki", "wiki_id"),
        Index("ix_wiki_commits_branch", "branch_id"),
    )
