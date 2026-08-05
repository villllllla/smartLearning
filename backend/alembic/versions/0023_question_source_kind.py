"""Add question source_kind + push schedule source_kinds filter.

Revision ID: 0023
Revises: 0022
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "questions",
        sa.Column(
            "source_kind",
            sa.String(16),
            nullable=False,
            server_default="simulated",
        ),
    )
    op.create_index("ix_questions_source_kind", "questions", ["source_kind"])

    op.add_column(
        "question_push_schedules",
        sa.Column(
            "source_kinds",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("question_push_schedules", "source_kinds")
    op.drop_index("ix_questions_source_kind", table_name="questions")
    op.drop_column("questions", "source_kind")
