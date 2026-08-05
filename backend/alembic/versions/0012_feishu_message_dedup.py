"""feishu_processed_messages for cross-restart webhook dedup

Revision ID: 0012
Revises: 0011
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feishu_processed_messages",
        sa.Column("message_id", sa.String(128), primary_key=True),
        sa.Column("event_id", sa.String(128), nullable=True),
        sa.Column("text_preview", sa.String(200), nullable=True),
        sa.Column(
            "processed_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("feishu_processed_messages")
