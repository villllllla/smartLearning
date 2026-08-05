"""Todo intent parsing and clarification flow."""
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.tenant import Tenant
from app.models.todo import TodoItem
from app.services.todo_service import (
    _format_todo_list,
    can_edit_todo,
    due_todos,
    get_clarifying_todo,
    handle_todo_message,
    is_todo_cancel,
    list_todos,
    open_tasks_for_date,
    run_deferrals,
    update_todo,
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


def test_is_todo_cancel():
    assert is_todo_cancel("取消")
    assert not is_todo_cancel("明天下午三点")


@pytest.mark.asyncio
async def test_handle_todo_needs_clarification(db):
    fake = (
        {
            "intent": "create_todo",
            "title": "交周报",
            "needs_clarification": True,
            "clarification_question": "请问希望在什么时间提醒你?",
            "missing_fields": ["remind_at"],
            "remind_at_iso": None,
        },
        1,
        1,
    )
    with patch(
        "app.services.todo_service.parse_todo_intent",
        new_callable=AsyncMock,
        return_value=fake,
    ):
        result = await handle_todo_message(
            db,
            user_message="待办 提醒我交周报",
            tenant_id=1,
            feishu_open_id="ou_todo",
        )
        db.commit()
    assert result.todo is not None
    assert result.todo.status == "clarifying"
    assert "什么时间" in result.texts[0]
    assert get_clarifying_todo(db, feishu_open_id="ou_todo") is not None


@pytest.mark.asyncio
async def test_handle_todo_scheduled(db):
    remind = (datetime.utcnow() + timedelta(days=1)).replace(microsecond=0)
    iso = remind.isoformat() + "+00:00"
    fake = (
        {
            "intent": "create_todo",
            "title": "交周报",
            "needs_clarification": False,
            "clarification_question": "",
            "missing_fields": [],
            "remind_at_iso": iso,
        },
        1,
        1,
    )
    with patch(
        "app.services.todo_service.parse_todo_intent",
        new_callable=AsyncMock,
        return_value=fake,
    ):
        result = await handle_todo_message(
            db,
            user_message="明天提醒我交周报",
            tenant_id=1,
            feishu_open_id="ou_todo2",
        )
        db.commit()
    assert result.todo is not None
    assert result.todo.status == "scheduled"
    assert result.todo.remind_at is not None
    assert "待办已记录" in result.texts[0]


@pytest.mark.asyncio
async def test_clarification_continuation(db):
    draft = TodoItem(
        tenant_id=1,
        title="交周报",
        status="clarifying",
        raw_input="待办 交周报",
        timezone="Asia/Shanghai",
        feishu_open_id="ou_cont",
        clarification_question="几点提醒?",
        clarification_context_json=[{"role": "user", "content": "待办 交周报"}],
        structured_json={},
    )
    db.add(draft)
    db.flush()

    remind = (datetime.utcnow() + timedelta(hours=2)).replace(microsecond=0)
    fake = (
        {
            "intent": "create_todo",
            "title": "交周报",
            "needs_clarification": False,
            "clarification_question": "",
            "missing_fields": [],
            "remind_at_iso": remind.isoformat() + "+00:00",
        },
        1,
        1,
    )
    with patch(
        "app.services.todo_service.parse_todo_intent",
        new_callable=AsyncMock,
        return_value=fake,
    ):
        result = await handle_todo_message(
            db,
            user_message="下午3点",
            tenant_id=1,
            feishu_open_id="ou_cont",
            existing=draft,
        )
        db.commit()
    assert result.todo.status == "scheduled"
    assert get_clarifying_todo(db, feishu_open_id="ou_cont") is None


def test_due_todos(db):
    past = TodoItem(
        tenant_id=1,
        title="t",
        status="scheduled",
        raw_input="x",
        remind_at=datetime.utcnow() - timedelta(minutes=5),
        timezone="Asia/Shanghai",
        structured_json={},
        clarification_context_json=[],
    )
    future = TodoItem(
        tenant_id=1,
        title="f",
        status="scheduled",
        raw_input="y",
        remind_at=datetime.utcnow() + timedelta(days=1),
        timezone="Asia/Shanghai",
        structured_json={},
        clarification_context_json=[],
    )
    db.add_all([past, future])
    db.flush()
    due = due_todos(db, tenant_id=1)
    assert len(due) == 1
    assert due[0].title == "t"


def test_run_deferrals_rolls_plan_tasks_to_today(db):
    yesterday = date.today() - timedelta(days=1)
    item = TodoItem(
        tenant_id=1,
        title="未完成计划项",
        status="scheduled",
        raw_input="x",
        plan_id=1,
        plan_date=yesterday,
        original_plan_date=yesterday,
        timezone="Asia/Shanghai",
        structured_json={},
        clarification_context_json=[],
    )
    db.add(item)
    db.flush()
    run_deferrals(db, tenant_id=1, today=date.today())
    db.refresh(item)
    assert item.plan_date == date.today()
    assert item.defer_count == 1
    assert open_tasks_for_date(db, tenant_id=1, day=date.today())


def test_list_todos_keeps_deferred_incomplete_on_original_day(db):
    yesterday = date.today() - timedelta(days=1)
    item = TodoItem(
        tenant_id=1,
        title="顺延前待办",
        status="scheduled",
        raw_input="x",
        plan_id=1,
        plan_date=date.today(),
        original_plan_date=yesterday,
        defer_count=1,
        timezone="Asia/Shanghai",
        structured_json={},
        clarification_context_json=[],
    )
    db.add(item)
    db.flush()
    rows_today, total_today = list_todos(db, tenant_id=1, plan_date=date.today())
    rows_yesterday, total_yesterday = list_todos(db, tenant_id=1, plan_date=yesterday)
    assert total_today == 1
    assert total_yesterday == 1
    assert rows_today[0].id == item.id
    assert rows_yesterday[0].id == item.id


def test_can_edit_done_todo(db):
    yesterday = date.today() - timedelta(days=1)
    item = TodoItem(
        tenant_id=1,
        title="已完成",
        status="done",
        progress=100,
        raw_input="x",
        plan_date=yesterday,
        timezone="Asia/Shanghai",
        structured_json={},
        clarification_context_json=[],
    )
    db.add(item)
    db.flush()
    assert can_edit_todo(item)
    update_todo(db, item, title="修订标题", description="补充说明")
    assert item.title == "修订标题"
    assert item.description == "补充说明"
    assert item.status == "done"


def test_set_todo_progress_marks_done_at_100(db):
    item = TodoItem(
        tenant_id=1,
        title="部分完成",
        status="scheduled",
        raw_input="x",
        plan_date=date.today(),
        timezone="Asia/Shanghai",
        structured_json={},
        clarification_context_json=[],
    )
    db.add(item)
    db.flush()
    from app.services.todo_service import set_todo_progress, snap_progress

    assert snap_progress(37) == 25
    assert snap_progress(88) == 100
    set_todo_progress(db, item, 50)
    assert item.progress == 50
    assert item.status == "scheduled"
    set_todo_progress(db, item, 100)
    assert item.progress == 100
    assert item.status == "done"
    set_todo_progress(db, item, 75)
    assert item.progress == 75
    assert item.status == "scheduled"
    assert item.completed_at is None


def test_set_todo_progress_reopen_reminded_when_reminded(db):
    item = TodoItem(
        tenant_id=1,
        title="已提醒任务",
        status="done",
        progress=100,
        raw_input="x",
        plan_date=date.today(),
        timezone="Asia/Shanghai",
        reminded_at=datetime.utcnow(),
        structured_json={},
        clarification_context_json=[],
    )
    db.add(item)
    db.flush()
    from app.services.todo_service import set_todo_progress

    set_todo_progress(db, item, 50)
    assert item.progress == 50
    assert item.status == "reminded"
    assert item.completed_at is None


def test_format_todo_list_shows_tenant_today_not_only_feishu(db):
    today = date.today()
    web_task = TodoItem(
        tenant_id=1,
        title="网页计划任务",
        status="scheduled",
        raw_input="x",
        plan_id=2,
        plan_date=today,
        original_plan_date=today,
        feishu_open_id=None,
        timezone="Asia/Shanghai",
        structured_json={},
        clarification_context_json=[],
    )
    feishu_old = TodoItem(
        tenant_id=1,
        title="飞书旧待办",
        status="scheduled",
        raw_input="y",
        plan_date=today - timedelta(days=30),
        feishu_open_id="ou_x",
        timezone="Asia/Shanghai",
        structured_json={},
        clarification_context_json=[],
    )
    db.add_all([web_task, feishu_old])
    db.flush()
    text = _format_todo_list(db, tenant_id=1, feishu_open_id="ou_x")
    assert "网页计划任务" in text
    assert "飞书旧待办" not in text
    assert "今日待办" in text
