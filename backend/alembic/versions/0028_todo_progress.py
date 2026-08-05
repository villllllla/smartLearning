"""Todo item progress (0-100).

Revision ID: 0028
Revises: 0027
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def _columns(bind, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    cols = _columns(bind, "todo_items")
    if "progress" not in cols:
        op.add_column(
            "todo_items",
            sa.Column("progress", sa.Integer, nullable=False, server_default="0"),
        )
        bind.execute(
            sa.text("UPDATE todo_items SET progress = 100 WHERE status = 'done'")
        )


def downgrade() -> None:
    cols = _columns(op.get_bind(), "todo_items")
    if "progress" in cols:
        op.drop_column("todo_items", "progress")
