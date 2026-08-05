"""Question push schedule table.

Revision ID: 0008
Revises: 0007
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "question_push_schedules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Shanghai"),
        sa.Column("push_times", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("frequency", sa.String(16), nullable=False, server_default="daily"),
        sa.Column("weekdays", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("limit", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("mode", sa.String(16), nullable=False, server_default="random"),
        sa.Column("difficulties", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("qtypes", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("tag_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("tag_mode", sa.String(8), nullable=False, server_default="or"),
        sa.Column("feishu_enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("last_run_slot", sa.String(32), nullable=True),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.UniqueConstraint("tenant_id", name="uq_push_schedule_tenant"),
    )


def downgrade() -> None:
    op.drop_table("question_push_schedules")
