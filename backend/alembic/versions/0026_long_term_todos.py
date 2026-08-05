"""Long-term todo tasks: daily | weekdays over a date range.

Revision ID: 0026
Revises: 0025
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def _tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _columns(bind, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)

    if "long_term_todos" not in tables:
        op.create_table(
            "long_term_todos",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column(
                "tenant_id",
                sa.Integer,
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("title", sa.String(200), nullable=False, server_default=""),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("start_date", sa.Date, nullable=False),
            sa.Column("end_date", sa.Date, nullable=False),
            sa.Column("remind_time", sa.String(8), nullable=False, server_default="21:00"),
            sa.Column("schedule_mode", sa.String(16), nullable=False, server_default="daily"),
            sa.Column("status", sa.String(16), nullable=False, server_default="active"),
            sa.Column("deleted_at", sa.DateTime, nullable=True),
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
        op.create_index(
            "ix_long_term_todos_tenant_status",
            "long_term_todos",
            ["tenant_id", "status"],
        )

    t_cols = _columns(bind, "todo_items")
    if "long_term_id" not in t_cols:
        op.add_column(
            "todo_items",
            sa.Column("long_term_id", sa.Integer, nullable=True),
        )
        op.create_index("ix_todo_items_long_term_id", "todo_items", ["long_term_id"])


def downgrade() -> None:
    op.drop_index("ix_todo_items_long_term_id", table_name="todo_items")
    op.drop_column("todo_items", "long_term_id")
    op.drop_index("ix_long_term_todos_tenant_status", table_name="long_term_todos")
    op.drop_table("long_term_todos")
