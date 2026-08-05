"""Long-term todo CRUD and daily todo cascade."""
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.tenant import Tenant
from app.models.todo import LongTermTodo, TodoItem
from app.services.long_term_todo_service import (
    create_long_term,
    delete_long_term,
    iter_schedule_dates,
    update_long_term,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(Tenant(id=1, name="t", slug="t"))
    session.flush()
    try:
        yield session
    finally:
        session.close()


def test_iter_schedule_dates_weekdays():
    # 2026-07-06 is Monday
    start = date(2026, 7, 6)
    end = date(2026, 7, 12)
    days = iter_schedule_dates(start, end, schedule_mode="weekdays")
    assert len(days) == 5
    assert all(d.weekday() < 5 for d in days)


def test_create_spawns_daily_todos(db):
    start = date.today()
    end = start + timedelta(days=2)
    lt = create_long_term(
        db,
        tenant_id=1,
        title="LeetCode #42",
        start_date=start,
        end_date=end,
        schedule_mode="daily",
    )
    db.commit()
    children = db.execute(
        select(TodoItem).where(TodoItem.long_term_id == lt.id)
    ).scalars().all()
    assert len(children) == 3
    assert all(c.title == "LeetCode #42" for c in children)
    assert all(c.plan_date is not None for c in children)


def test_update_syncs_future_children(db):
    start = date.today()
    end = start + timedelta(days=4)
    lt = create_long_term(
        db,
        tenant_id=1,
        title="旧标题",
        start_date=start,
        end_date=end,
    )
    db.commit()
    new_end = start + timedelta(days=2)
    update_long_term(
        db,
        lt,
        title="新标题",
        end_date=new_end,
    )
    db.commit()
    children = db.execute(
        select(TodoItem).where(
            TodoItem.long_term_id == lt.id,
            TodoItem.deleted_at.is_(None),
        )
    ).scalars().all()
    assert len(children) == 3
    assert all(c.title == "新标题" for c in children)


def test_delete_cascades_open_daily_todos(db):
    start = date.today()
    end = start + timedelta(days=2)
    lt = create_long_term(
        db,
        tenant_id=1,
        title="待删",
        start_date=start,
        end_date=end,
    )
    db.commit()
    child = db.execute(
        select(TodoItem).where(TodoItem.long_term_id == lt.id).limit(1)
    ).scalar_one()
    child.status = "done"
    db.commit()

    delete_long_term(db, lt, drop_tasks=True)
    db.commit()

    assert db.get(LongTermTodo, lt.id).deleted_at is not None
    rows = db.execute(select(TodoItem).where(TodoItem.long_term_id == lt.id)).scalars().all()
    open_rows = [r for r in rows if r.deleted_at is None]
    done_rows = [r for r in rows if r.status == "done" and r.deleted_at is None]
    assert len(open_rows) == 1
    assert len(done_rows) == 1


def test_pause_removes_open_children(db):
    start = date.today()
    end = start + timedelta(days=2)
    lt = create_long_term(
        db,
        tenant_id=1,
        title="暂停测试",
        start_date=start,
        end_date=end,
    )
    db.commit()
    update_long_term(db, lt, status="paused")
    db.commit()
    open_children = db.execute(
        select(TodoItem).where(
            TodoItem.long_term_id == lt.id,
            TodoItem.deleted_at.is_(None),
            TodoItem.status != "done",
        )
    ).scalars().all()
    assert open_children == []
