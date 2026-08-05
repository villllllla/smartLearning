"""Add app_settings singleton table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-12
"""
from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("practice_default_limit", sa.Integer, nullable=False, server_default="10"),
        sa.Column("practice_time_limit_per_question", sa.Integer, nullable=True),
        sa.Column("practice_default_difficulties", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("practice_default_qtypes", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("practice_history_keep_n", sa.Integer, nullable=False, server_default="10"),
        sa.Column("appearance_theme", sa.String(16), nullable=False, server_default="system"),
        sa.Column("appearance_locale", sa.String(16), nullable=False, server_default="zh-CN"),
        sa.Column(
            "created_at",
            sa.DateTime,
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime,
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
    )

    # Seed singleton row (id = 1)
    now = datetime.utcnow()
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """INSERT INTO app_settings (
                id,
                practice_default_limit,
                practice_time_limit_per_question,
                practice_default_difficulties,
                practice_default_qtypes,
                practice_history_keep_n,
                appearance_theme,
                appearance_locale,
                created_at,
                updated_at
            ) VALUES (
                1, 10, NULL, '[]', '[]', 10, 'system', 'zh-CN', :now, :now
            )"""
        ),
        {"now": now},
    )


def downgrade() -> None:
    op.drop_table("app_settings")
