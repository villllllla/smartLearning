"""Add arXiv/HuggingFace/Reddit source toggles to ai_news_schedules

Revision ID: 0018
Revises: 0017
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

_NEW_COLUMNS = ("enable_arxiv", "enable_huggingface", "enable_reddit")


def _columns(bind, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if "ai_news_schedules" not in set(sa.inspect(bind).get_table_names()):
        return
    existing = _columns(bind, "ai_news_schedules")
    for col in _NEW_COLUMNS:
        if col not in existing:
            op.add_column(
                "ai_news_schedules",
                sa.Column(col, sa.Boolean, nullable=False, server_default=sa.true()),
            )


def downgrade() -> None:
    bind = op.get_bind()
    if "ai_news_schedules" not in set(sa.inspect(bind).get_table_names()):
        return
    existing = _columns(bind, "ai_news_schedules")
    for col in _NEW_COLUMNS:
        if col in existing:
            op.drop_column("ai_news_schedules", col)
