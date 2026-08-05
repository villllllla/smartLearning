"""question stem embeddings for semantic dedupe

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-02
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("questions") as batch_op:
        batch_op.add_column(sa.Column("stem_embedding_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("embedding_model", sa.String(120), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("questions") as batch_op:
        batch_op.drop_column("embedding_model")
        batch_op.drop_column("stem_embedding_json")
