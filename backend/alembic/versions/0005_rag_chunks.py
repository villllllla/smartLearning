"""rag_chunks table for wiki RAG

Revision ID: 0005
Revises: 0004
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rag_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("wiki_id", sa.Integer(), sa.ForeignKey("wikis.id", ondelete="CASCADE"), nullable=False),
        sa.Column("wiki_title", sa.String(300), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("heading", sa.String(500), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "source_commit_id",
            sa.Integer(),
            sa.ForeignKey("wiki_commits.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("content_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("embedding_json", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
    )
    op.create_index("ix_rag_chunks_wiki", "rag_chunks", ["wiki_id"])
    op.create_index("ix_rag_chunks_wiki_idx", "rag_chunks", ["wiki_id", "chunk_index"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_rag_chunks_wiki_idx", table_name="rag_chunks")
    op.drop_index("ix_rag_chunks_wiki", table_name="rag_chunks")
    op.drop_table("rag_chunks")
