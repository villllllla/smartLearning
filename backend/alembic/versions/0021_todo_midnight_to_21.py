"""Set 21:00 local for historical todos stuck at midnight (00:00) placeholder.

Revision ID: 0021
Revises: 0020
"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import sqlalchemy as sa

from alembic import op

revision = "0021"
down_revision = "0020"
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
            SELECT id, plan_date, remind_at, timezone
            FROM todo_items
            WHERE deleted_at IS NULL AND remind_at IS NOT NULL
            """
        )
    ).fetchall()
    for row in rows:
        rid, plan_date, remind_at, tz_name = row[0], row[1], row[2], row[3]
        if isinstance(remind_at, str):
            remind_at = datetime.fromisoformat(remind_at.replace("Z", "+00:00"))
        try:
            tz = ZoneInfo(tz_name or "Asia/Shanghai")
        except Exception:
            tz = ZoneInfo("Asia/Shanghai")
        local = remind_at.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
        if local.hour != 0 or local.minute != 0:
            continue
        target_date = _parse_date(plan_date) if plan_date else local.date()
        new_ra = _to_utc_naive(target_date, tz_name)
        bind.execute(
            sa.text(
                """
                UPDATE todo_items
                SET remind_at = :ra, updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """
            ),
            {"ra": new_ra, "id": rid},
        )


def downgrade() -> None:
    pass
