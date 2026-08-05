"""Add Feishu provenance columns on answer_attempts

Revision ID: 0013
Revises: 0012
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

_COLUMNS: tuple[tuple[str, sa.types.TypeEngine], ...] = (
    ("channel", sa.String(16)),
    ("feishu_open_id", sa.String(128)),
    ("feishu_message_id", sa.String(128)),
    ("bot_session_id", sa.Integer()),
)


def _existing_columns() -> set[str]:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return {c["name"] for c in insp.get_columns("answer_attempts")}


def _index_exists(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return any(ix["name"] == name for ix in insp.get_indexes("answer_attempts"))


def upgrade() -> None:
    existing = _existing_columns()
    to_add = [(name, col_type) for name, col_type in _COLUMNS if name not in existing]
    if to_add:
        with op.batch_alter_table("answer_attempts", schema=None) as batch_op:
            for name, col_type in to_add:
                batch_op.add_column(sa.Column(name, col_type, nullable=True))
    if not _index_exists("ix_attempts_feishu_open_id"):
        op.create_index(
            "ix_attempts_feishu_open_id",
            "answer_attempts",
            ["feishu_open_id", "created_at"],
        )


def downgrade() -> None:
    if _index_exists("ix_attempts_feishu_open_id"):
        op.drop_index("ix_attempts_feishu_open_id", table_name="answer_attempts")
    existing = _existing_columns()
    to_drop = [name for name, _ in _COLUMNS if name in existing]
    if to_drop:
        with op.batch_alter_table("answer_attempts", schema=None) as batch_op:
            for name in reversed(to_drop):
                batch_op.drop_column(name)
