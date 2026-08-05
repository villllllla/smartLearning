"""bot_sessions for IM integrations.

Revision ID: 0004
Revises: 0003
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bot_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("platform", sa.String(32), nullable=False, server_default="feishu"),
        sa.Column("feishu_open_id", sa.String(128), nullable=False),
        sa.Column("feishu_chat_id", sa.String(128), nullable=True),
        sa.Column("question_queue_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("queue_cursor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_question_id", sa.Integer(), nullable=True),
        sa.Column("smartlearning_chat_id", sa.Integer(), nullable=True),
        sa.Column("last_event_id", sa.String(128), nullable=True),
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
        sa.ForeignKeyConstraint(["smartlearning_chat_id"], ["chats.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_bot_sessions_platform_open_id",
        "bot_sessions",
        ["platform", "feishu_open_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_bot_sessions_platform_open_id", table_name="bot_sessions")
    op.drop_table("bot_sessions")
