"""Central app timezone: single source of truth for all schedules and todos."""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import (
    AiNewsSchedule,
    LearningReviewSchedule,
    QuestionPushSchedule,
    TodoItem,
)
from app.models.todo import TodoCheckSchedule
from app.services.settings_service import get_settings_row
from app.services.timezone_service import is_valid_timezone

_FALLBACK_TZ = "Asia/Shanghai"
_DEFAULT_REMIND_TIME = "21:00"


def get_app_timezone(db: Session, *, tenant_id: int) -> str:
    row = get_settings_row(db, tenant_id)
    tz = (getattr(row, "timezone", None) or "").strip()
    if tz and is_valid_timezone(db, tz):
        return tz
    # Legacy fallback before settings row has timezone
    for model in (QuestionPushSchedule, LearningReviewSchedule, TodoCheckSchedule, AiNewsSchedule):
        sched = db.execute(
            select(model).where(model.tenant_id == tenant_id)  # type: ignore[arg-type]
        ).scalar_one_or_none()
        if sched and getattr(sched, "timezone", None):
            return str(sched.timezone)
    return _FALLBACK_TZ


def _to_utc_naive(plan_date: date, tz_name: str, hhmm: str = _DEFAULT_REMIND_TIME) -> datetime:
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo(_FALLBACK_TZ)
    hh, mm = (int(x) for x in hhmm.split(":"))
    local = datetime(plan_date.year, plan_date.month, plan_date.day, hh, mm, tzinfo=tz)
    return local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def _local_hhmm(remind_at: datetime, tz_name: str) -> str:
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo(_FALLBACK_TZ)
    local = remind_at.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
    return local.strftime("%H:%M")


def local_hhmm_from_remind_at(remind_at: datetime, tz_name: str) -> str:
    """Public helper: UTC-naive remind_at → HH:MM in the given IANA timezone."""
    return _local_hhmm(remind_at, tz_name)


def apply_schedule_timezone(db: Session, *, tenant_id: int, row) -> str:
    """Keep schedule row timezone aligned with the global app setting."""
    tz = get_app_timezone(db, tenant_id=tenant_id)
    row.timezone = tz
    return tz


def sync_schedule_timezones(db: Session, *, tenant_id: int, timezone: str) -> None:
    """Push global timezone to all per-feature schedule rows."""
    for model in (
        QuestionPushSchedule,
        LearningReviewSchedule,
        TodoCheckSchedule,
        AiNewsSchedule,
    ):
        db.execute(
            update(model).where(model.tenant_id == tenant_id).values(timezone=timezone)  # type: ignore[arg-type]
        )
    db.flush()


def realign_todo_reminders(
    db: Session,
    *,
    tenant_id: int,
    timezone: str,
    from_date: date | None = None,
) -> int:
    """Set timezone + 21:00 remind_at on active todos from from_date onward."""
    from_date = from_date or date.today()
    rows = db.execute(
        select(TodoItem).where(
            TodoItem.tenant_id == tenant_id,
            TodoItem.deleted_at.is_(None),
            TodoItem.status.in_(["scheduled", "reminded", "snoozed"]),
            TodoItem.plan_date.isnot(None),
            TodoItem.plan_date >= from_date,
        )
    ).scalars().all()
    for item in rows:
        item.timezone = timezone
        hhmm = (
            _local_hhmm(item.remind_at, item.timezone)
            if item.remind_at is not None
            else _DEFAULT_REMIND_TIME
        )
        if hhmm == "00:00":
            hhmm = _DEFAULT_REMIND_TIME
        item.remind_at = _to_utc_naive(item.plan_date, timezone, hhmm)
    if rows:
        db.flush()
    return len(rows)


def set_app_timezone(db: Session, *, tenant_id: int, timezone: str) -> str:
    tz = (timezone or "").strip() or _FALLBACK_TZ
    if not is_valid_timezone(db, tz):
        raise ValueError(f"无效时区: {tz}")
    row = get_settings_row(db, tenant_id)
    row.timezone = tz
    sync_schedule_timezones(db, tenant_id=tenant_id, timezone=tz)
    realign_todo_reminders(db, tenant_id=tenant_id, timezone=tz, from_date=date.today())
    db.flush()
    return tz
