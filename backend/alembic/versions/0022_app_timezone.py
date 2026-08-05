"""App-wide timezone on app_settings + realign todos/schedules.

Revision ID: 0022
Revises: 0021
"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import sqlalchemy as sa

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

_DEFAULT_TIME = "21:00"
_FALLBACK = "Asia/Shanghai"


def _detect_tz(bind, tenant_id: int) -> str:
    for table in (
        "question_push_schedules",
        "learning_review_schedules",
        "todo_check_schedules",
        "ai_news_schedules",
    ):
        row = bind.execute(
            sa.text(f"SELECT timezone FROM {table} WHERE tenant_id = :tid LIMIT 1"),
            {"tid": tenant_id},
        ).scalar()
        if row:
            return str(row)
    return _FALLBACK


def _to_utc_naive(plan_date, tz_name: str, hhmm: str = _DEFAULT_TIME) -> datetime:
    if isinstance(plan_date, str):
        plan_date = date.fromisoformat(plan_date[:10])
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo(_FALLBACK)
    hh, mm = (int(x) for x in hhmm.split(":"))
    local = datetime(plan_date.year, plan_date.month, plan_date.day, hh, mm, tzinfo=tz)
    return local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("app_settings")}
    if "timezone" not in cols:
        op.add_column(
            "app_settings",
            sa.Column("timezone", sa.String(64), nullable=False, server_default=_FALLBACK),
        )

    tenant_ids = [r[0] for r in bind.execute(sa.text("SELECT id FROM tenants")).fetchall()]
    for tid in tenant_ids:
        tz = _detect_tz(bind, tid)
        bind.execute(
            sa.text("UPDATE app_settings SET timezone = :tz WHERE tenant_id = :tid"),
            {"tz": tz, "tid": tid},
        )
        for table in (
            "question_push_schedules",
            "learning_review_schedules",
            "todo_check_schedules",
            "ai_news_schedules",
        ):
            bind.execute(
                sa.text(f"UPDATE {table} SET timezone = :tz WHERE tenant_id = :tid"),
                {"tz": tz, "tid": tid},
            )

        rows = bind.execute(
            sa.text(
                """
                SELECT id, plan_date, remind_at
                FROM todo_items
                WHERE tenant_id = :tid AND deleted_at IS NULL
                  AND status IN ('scheduled', 'reminded', 'snoozed')
                  AND plan_date IS NOT NULL
                """
            ),
            {"tid": tid},
        ).fetchall()
        for rid, plan_date, _ in rows:
            ra = _to_utc_naive(plan_date, tz, _DEFAULT_TIME)
            bind.execute(
                sa.text(
                    """
                    UPDATE todo_items
                    SET timezone = :tz, remind_at = :ra, updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                    """
                ),
                {"tz": tz, "ra": ra, "id": rid},
            )


def downgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("app_settings")}
    if "timezone" in cols:
        op.drop_column("app_settings", "timezone")
