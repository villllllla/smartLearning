"""Backfill remind_at=21:00 local for todos without a specific reminder time.

Revision ID: 0020
Revises: 0019
"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import sqlalchemy as sa

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

_DEFAULT_TIME = "21:00"


def _parse_date(val) -> date:
    if isinstance(val, date):
        return val
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, str):
        return date.fromisoformat(val[:10])
    return date.today()


def _to_utc_naive(plan_date: date, tz_name: str) -> datetime:
    plan_date = _parse_date(plan_date)
    try:
        tz = ZoneInfo(tz_name or "Asia/Shanghai")
    except Exception:
        tz = ZoneInfo("Asia/Shanghai")
    hh, mm = (int(x) for x in _DEFAULT_TIME.split(":"))
    local = datetime(plan_date.year, plan_date.month, plan_date.day, hh, mm, tzinfo=tz)
    return local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT id, plan_date, timezone, created_at
            FROM todo_items
            WHERE deleted_at IS NULL AND remind_at IS NULL
            """
        )
    ).fetchall()
    for row in rows:
        rid, plan_date, tz_name, created_at = row[0], row[1], row[2], row[3]
        if plan_date is None:
            if isinstance(created_at, str):
                plan_date = date.fromisoformat(created_at[:10])
            elif isinstance(created_at, datetime):
                plan_date = created_at.date()
            else:
                plan_date = date.today()
        remind_at = _to_utc_naive(plan_date, tz_name)
        bind.execute(
            sa.text(
                """
                UPDATE todo_items
                SET remind_at = :ra,
                    plan_date = COALESCE(plan_date, :pd),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """
            ),
            {"ra": remind_at, "pd": plan_date, "id": rid},
        )


def downgrade() -> None:
    # Cannot reliably distinguish backfilled 21:00 from user-chosen times.
    pass
