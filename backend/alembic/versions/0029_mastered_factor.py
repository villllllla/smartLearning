"""Mastered notes are de-prioritised, not silenced: interval factor + requeue.

Revision ID: 0029
Revises: 0028
"""
from __future__ import annotations

from datetime import datetime, timedelta

import sqlalchemy as sa

from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

DEFAULT_FACTOR = 3.0
FALLBACK_LONGEST_DAYS = 30

_schedules = sa.table(
    "learning_review_schedules",
    sa.column("tenant_id", sa.Integer),
    sa.column("intervals_days", sa.JSON),
)
_notes = sa.table(
    "learning_notes",
    sa.column("id", sa.Integer),
    sa.column("tenant_id", sa.Integer),
    sa.column("mastered", sa.Boolean),
    sa.column("next_review_at", sa.DateTime),
)


def _columns(bind, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def _longest_interval(raw) -> int:
    days = [int(d) for d in (raw or []) if str(d).lstrip("-").isdigit() and int(d) > 0]
    return max(days) if days else FALLBACK_LONGEST_DAYS


def upgrade() -> None:
    bind = op.get_bind()
    if "mastered_factor" not in _columns(bind, "learning_review_schedules"):
        op.add_column(
            "learning_review_schedules",
            sa.Column(
                "mastered_factor",
                sa.Float,
                nullable=False,
                server_default=str(DEFAULT_FACTOR),
            ),
        )

    # Notes mastered under the old rule had next_review_at cleared, which dropped
    # them from the queue forever. Requeue them at longest interval * factor.
    longest = {
        row.tenant_id: _longest_interval(row.intervals_days)
        for row in bind.execute(
            sa.select(_schedules.c.tenant_id, _schedules.c.intervals_days)
        )
    }
    stale = bind.execute(
        sa.select(_notes.c.id, _notes.c.tenant_id).where(
            _notes.c.mastered.is_(True), _notes.c.next_review_at.is_(None)
        )
    ).fetchall()
    now = datetime.utcnow()
    for note_id, tenant_id in stale:
        days = longest.get(tenant_id, FALLBACK_LONGEST_DAYS) * DEFAULT_FACTOR
        bind.execute(
            _notes.update()
            .where(_notes.c.id == note_id)
            .values(next_review_at=now + timedelta(days=days))
        )


def downgrade() -> None:
    if "mastered_factor" in _columns(op.get_bind(), "learning_review_schedules"):
        op.drop_column("learning_review_schedules", "mastered_factor")
