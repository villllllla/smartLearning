"""Long-term todos: create daily tasks over a date range with cascade sync."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.todo import LongTermTodo, TodoItem
from app.services.todo_service import _combine_plan_datetime, default_timezone

log = logging.getLogger(__name__)

_MAX_DAYS = 366


def _validate_range(start_date: date, end_date: date) -> None:
    if end_date < start_date:
        raise ValueError("结束日期不能早于开始日期")
    if (end_date - start_date).days + 1 > _MAX_DAYS:
        raise ValueError(f"日期跨度不能超过 {_MAX_DAYS} 天")


def iter_schedule_dates(
    start_date: date,
    end_date: date,
    *,
    schedule_mode: str = "daily",
) -> list[date]:
    out: list[date] = []
    cur = start_date
    while cur <= end_date:
        if schedule_mode == "weekdays" and cur.weekday() >= 5:
            cur += timedelta(days=1)
            continue
        out.append(cur)
        cur += timedelta(days=1)
    return out


def _spawn_daily_todos(
    db: Session,
    *,
    lt: LongTermTodo,
    dates: list[date],
    tz_name: str,
    channel: str = "web",
) -> int:
    created = 0
    for d in dates:
        db.add(
            TodoItem(
                tenant_id=lt.tenant_id,
                title=lt.title,
                description=lt.description,
                status="scheduled",
                long_term_id=lt.id,
                plan_date=d,
                original_plan_date=d,
                defer_count=0,
                remind_at=_combine_plan_datetime(d, lt.remind_time, tz_name),
                timezone=tz_name,
                raw_input=lt.title,
                structured_json={"from_long_term": lt.id},
                channel=channel,
            )
        )
        created += 1
    if created:
        db.flush()
    return created


def create_long_term(
    db: Session,
    *,
    tenant_id: int,
    title: str,
    start_date: date,
    end_date: date,
    description: str | None = None,
    remind_time: str = "21:00",
    schedule_mode: str = "daily",
    channel: str = "web",
) -> LongTermTodo:
    _validate_range(start_date, end_date)
    if schedule_mode not in ("daily", "weekdays"):
        raise ValueError("无效的重复模式")
    dates = iter_schedule_dates(start_date, end_date, schedule_mode=schedule_mode)
    if not dates:
        raise ValueError("日期区间内没有可排期的日子")

    tz_name = default_timezone(db, tenant_id=tenant_id)
    lt = LongTermTodo(
        tenant_id=tenant_id,
        title=title.strip()[:200],
        description=(description or "").strip() or None,
        start_date=start_date,
        end_date=end_date,
        remind_time=(remind_time or "21:00").strip()[:8] or "21:00",
        schedule_mode=schedule_mode,
        status="active",
    )
    db.add(lt)
    db.flush()
    _spawn_daily_todos(db, lt=lt, dates=dates, tz_name=tz_name, channel=channel)
    return lt


def list_long_term(db: Session, *, tenant_id: int) -> list[LongTermTodo]:
    return list(
        db.execute(
            select(LongTermTodo)
            .where(LongTermTodo.tenant_id == tenant_id, LongTermTodo.deleted_at.is_(None))
            .order_by(LongTermTodo.created_at.desc())
        ).scalars().all()
    )


def get_long_term(
    db: Session, long_term_id: int, *, tenant_id: int
) -> LongTermTodo | None:
    return db.execute(
        select(LongTermTodo).where(
            LongTermTodo.id == long_term_id,
            LongTermTodo.tenant_id == tenant_id,
            LongTermTodo.deleted_at.is_(None),
        )
    ).scalar_one_or_none()


def long_term_progress(db: Session, lt: LongTermTodo) -> tuple[int, int]:
    rows = db.execute(
        select(TodoItem.status).where(
            TodoItem.long_term_id == lt.id, TodoItem.deleted_at.is_(None)
        )
    ).scalars().all()
    total = len(rows)
    done = sum(1 for s in rows if s == "done")
    return done, total


def _active_children(db: Session, lt: LongTermTodo) -> list[TodoItem]:
    return list(
        db.execute(
            select(TodoItem).where(
                TodoItem.long_term_id == lt.id,
                TodoItem.deleted_at.is_(None),
            )
        ).scalars().all()
    )


def _soft_delete_child(item: TodoItem) -> None:
    item.deleted_at = datetime.utcnow()


def sync_long_term_children(
    db: Session,
    lt: LongTermTodo,
    *,
    today: date | None = None,
) -> None:
    """Align daily todos with the long-term definition (after update)."""
    if lt.status != "active":
        return
    today = today or date.today()
    tz_name = default_timezone(db, tenant_id=lt.tenant_id)
    target_dates = set(
        iter_schedule_dates(lt.start_date, lt.end_date, schedule_mode=lt.schedule_mode)
    )
    by_date: dict[date, TodoItem] = {}
    for item in _active_children(db, lt):
        if item.plan_date is None:
            continue
        by_date[item.plan_date] = item

    for d, item in list(by_date.items()):
        if d in target_dates:
            if item.status != "done":
                item.title = lt.title
                item.description = lt.description
                item.remind_at = _combine_plan_datetime(d, lt.remind_time, tz_name)
            continue
        if item.status == "done":
            continue
        _soft_delete_child(item)
        by_date.pop(d, None)

    missing = sorted(d for d in target_dates if d not in by_date)
    if missing:
        _spawn_daily_todos(db, lt=lt, dates=missing, tz_name=tz_name)


def update_long_term(
    db: Session,
    lt: LongTermTodo,
    *,
    title: str | None = None,
    description: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    remind_time: str | None = None,
    schedule_mode: str | None = None,
    status: str | None = None,
) -> LongTermTodo:
    new_start = start_date if start_date is not None else lt.start_date
    new_end = end_date if end_date is not None else lt.end_date
    _validate_range(new_start, new_end)

    if title is not None:
        lt.title = title.strip()[:200]
    if description is not None:
        lt.description = description.strip() or None
    if remind_time is not None:
        lt.remind_time = remind_time.strip()[:8] or lt.remind_time
    if schedule_mode is not None:
        if schedule_mode not in ("daily", "weekdays"):
            raise ValueError("无效的重复模式")
        lt.schedule_mode = schedule_mode
    if status is not None:
        if status not in ("active", "paused", "done", "archived"):
            raise ValueError("无效的状态")
        lt.status = status

    lt.start_date = new_start
    lt.end_date = new_end
    db.flush()

    if lt.status == "active":
        sync_long_term_children(db, lt)
    elif lt.status in ("paused", "archived", "done"):
        for item in _active_children(db, lt):
            if item.status != "done":
                _soft_delete_child(item)
    db.flush()
    return lt


def delete_long_term(db: Session, lt: LongTermTodo, *, drop_tasks: bool = True) -> None:
    """Soft-delete parent and optionally soft-delete unfinished daily todos."""
    lt.deleted_at = datetime.utcnow()
    if drop_tasks:
        for item in _active_children(db, lt):
            if item.status != "done":
                _soft_delete_child(item)
    db.flush()
