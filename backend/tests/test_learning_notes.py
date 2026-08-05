"""Learning notes: routing, structuring, spaced repetition, review schedule."""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.integrations.feishu.agent import _parse_review_card
from app.integrations.feishu.answer_routing import parse_learning_note
from app.models import LearningReviewSchedule, Tenant
from app.services import learning_note_service
from app.services.learning_review_service import is_due_now, review_catch_up_slot


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


def test_parse_learning_note_prefixes():
    assert parse_learning_note("总结 今天学习了 Redis 持久化机制") == "今天学习了 Redis 持久化机制"
    assert parse_learning_note("学习总结：复习了 TCP 三次握手与四次挥手") == (
        "复习了 TCP 三次握手与四次挥手"
    )
    assert parse_learning_note("笔记 操作系统的进程与线程区别整理") == (
        "操作系统的进程与线程区别整理"
    )
    # too short body -> None
    assert parse_learning_note("总结 好") is None
    # no prefix -> None (treated as chat/question)
    assert parse_learning_note("什么是 CAP 定理") is None
    # card callback json -> None
    assert parse_learning_note('{"cmd":"复习要点","nid":"3"}') is None


def test_parse_review_card():
    assert _parse_review_card('{"cmd":"复习要点","nid":"7"}') == ("note_reveal", 7)
    assert _parse_review_card('{"cmd":"复习掌握","nid":"7"}') == ("note_master", 7)
    assert _parse_review_card('{"cmd":"复习加强","nid":"7"}') == ("note_reinforce", 7)
    assert _parse_review_card('{"cmd":"答案","qid":"1"}') is None
    assert _parse_review_card("总结 今天学了很多东西") is None


@pytest.mark.asyncio
async def test_create_note_structures_and_schedules(db):
    fake = (
        {
            "title": "Redis 持久化",
            "summary": "RDB 快照 + AOF 日志",
            "key_points": ["RDB 是快照", "AOF 是追加日志"],
            "tags": ["Redis", "存储"],
            "category": "后端",
            "issues": ["AOF 默认每秒刷盘，不是每次"],
            "corrections": ["appendfsync 默认 everysec"],
            "suggestions": ["了解混合持久化"],
            "quality_score": 82,
        },
        1,
        1,
    )
    with patch(
        "app.services.learning_note_service.structure_note",
        new_callable=AsyncMock,
        return_value=fake,
    ):
        note = await learning_note_service.create_note(
            db,
            raw_input="今天学了 Redis 的 RDB 和 AOF",
            tenant_id=1,
            channel="feishu",
            feishu_open_id="ou_x",
            extra_tags=["面试"],
        )
        db.commit()

    assert note.title == "Redis 持久化"
    assert note.key_points_json == ["RDB 是快照", "AOF 是追加日志"]
    assert note.quality_score == 82
    assert note.review_json["issues"]
    assert note.raw_input == "今天学了 Redis 的 RDB 和 AOF"
    tag_names = {t.name for t in note.tags}
    assert {"Redis", "存储", "面试"}.issubset(tag_names)
    # scheduled for the first interval (1 day) from now
    assert note.next_review_at is not None
    assert note.interval_index == 0


def _make_note(db):
    from app.models import LearningNote

    note = LearningNote(
        tenant_id=1,
        raw_input="x" * 20,
        title="t",
        key_points_json=[],
        structured_json={},
        review_json={},
        interval_index=0,
        review_count=0,
        next_review_at=datetime.utcnow(),
    )
    db.add(note)
    db.flush()
    return note


def test_mark_reviewed_advances_interval(db):
    note = _make_note(db)
    learning_note_service.mark_reviewed(db, note, intervals=[1, 3, 7])
    assert note.interval_index == 1
    assert note.review_count == 1
    delta = note.next_review_at - datetime.utcnow()
    assert timedelta(days=2, hours=23) < delta < timedelta(days=3, hours=1)

    learning_note_service.mark_reviewed(db, note, intervals=[1, 3, 7])
    learning_note_service.mark_reviewed(db, note, intervals=[1, 3, 7])
    # clamps at last index
    assert note.interval_index == 2


def test_reset_review(db):
    note = _make_note(db)
    note.interval_index = 3
    note.mastered = True
    learning_note_service.reset_review(db, note)
    assert note.interval_index == 0
    assert note.mastered is False
    assert note.next_review_at is not None


def test_due_notes_excludes_future_but_keeps_mastered_last(db):

    # Mastered is a de-prioritisation, not a mute: it still surfaces, but only
    # after every still-learning note that is due.
    mastered = _make_note(db)
    mastered.next_review_at = datetime.utcnow() - timedelta(days=10)
    mastered.mastered = True
    due = _make_note(db)
    due.next_review_at = datetime.utcnow() - timedelta(hours=1)
    future = _make_note(db)
    future.next_review_at = datetime.utcnow() + timedelta(days=5)
    db.flush()

    rows = learning_note_service.due_notes(db, tenant_id=1, limit=10)
    ids = [r.id for r in rows]
    assert ids == [due.id, mastered.id]
    assert future.id not in ids


def test_due_notes_quota_goes_to_unmastered_first(db):
    mastered = _make_note(db)
    mastered.next_review_at = datetime.utcnow() - timedelta(days=30)
    mastered.mastered = True
    active = _make_note(db)
    active.next_review_at = datetime.utcnow() - timedelta(hours=1)
    db.flush()

    rows = learning_note_service.due_notes(db, tenant_id=1, limit=1)
    assert [r.id for r in rows] == [active.id]


def test_mark_mastered_stretches_interval_instead_of_stopping(db):
    note = _make_note(db)
    learning_note_service.mark_mastered(db, note, True)

    assert note.mastered is True
    # longest configured interval (30d) * default factor (3) = ~90 days
    assert note.next_review_at is not None
    delta = note.next_review_at - datetime.utcnow()
    assert timedelta(days=89) < delta < timedelta(days=91)


def test_mastered_review_keeps_stretched_interval(db):
    note = _make_note(db)
    note.mastered = True
    learning_note_service.mark_reviewed(db, note, intervals=[1, 3, 7], factor=3.0)
    # index 1 -> 3 days, stretched to 9
    delta = note.next_review_at - datetime.utcnow()
    assert timedelta(days=8, hours=23) < delta < timedelta(days=9, hours=1)


def test_mastered_factor_one_disables_deprioritisation(db):
    from app.services import learning_review_service

    learning_review_service.update_schedule(db, tenant_id=1, mastered_factor=1)
    note = _make_note(db)
    learning_note_service.mark_mastered(db, note, True)
    delta = note.next_review_at - datetime.utcnow()
    assert timedelta(days=29) < delta < timedelta(days=31)


def test_is_due_now_matches_slot(db):
    tz = ZoneInfo("Asia/Shanghai")
    now = datetime(2026, 6, 23, 8, 0, tzinfo=tz)
    row = LearningReviewSchedule(
        tenant_id=1,
        enabled=True,
        timezone="Asia/Shanghai",
        push_times=["08:00"],
        frequency="daily",
        weekdays=[],
        intervals_days=[1, 3, 7],
    )
    slot = is_due_now(row, now, db=db)
    assert slot == "2026-06-23T08:00"

    # already ran this slot
    row.last_run_slot = slot
    assert is_due_now(row, now, db=db) is None

    # disabled
    row.last_run_slot = None
    row.enabled = False
    assert is_due_now(row, now, db=db) is None

    # wrong time
    row.enabled = True
    assert is_due_now(row, datetime(2026, 6, 23, 9, 1, tzinfo=tz), db=db) is None


def test_review_catch_up_when_backlog_after_scheduled_slot(db):
    from app.models import LearningNote

    tz = ZoneInfo("Asia/Shanghai")
    row = LearningReviewSchedule(
        tenant_id=1,
        enabled=True,
        timezone="Asia/Shanghai",
        push_times=["08:00"],
        frequency="daily",
        weekdays=[],
        intervals_days=[1, 3, 7],
        max_notes_per_push=5,
        last_run_slot="2026-06-22T08:00",
    )
    db.add(row)
    note = LearningNote(
        tenant_id=1,
        raw_input="x",
        title="due note",
        summary="s",
        key_points_json=[],
        structured_json={},
        review_json={},
        next_review_at=datetime.utcnow() - timedelta(hours=2),
    )
    db.add(note)
    db.flush()

    now = datetime(2026, 6, 23, 10, 0, tzinfo=tz)
    assert is_due_now(row, now, db=db) is None
    assert review_catch_up_slot(row, db=db, now=now) == "2026-06-23T08:00"

    row.last_run_slot = "2026-06-23T08:00"
    row.last_run_at = datetime.utcnow() - timedelta(hours=1)
    assert review_catch_up_slot(row, db=db, now=now) == "2026-06-23Tbacklog"


@pytest.mark.asyncio
async def test_execute_review_push_leaves_slot_open_when_batch_partial(db):
    from app.models import LearningNote
    from app.services.learning_review_service import execute_review_push, get_or_create_schedule

    row = get_or_create_schedule(db, tenant_id=1)
    row.max_notes_per_push = 1
    row.feishu_enabled = False
    for i in range(2):
        db.add(
            LearningNote(
                tenant_id=1,
                raw_input=f"x{i}",
                title=f"note {i}",
                summary="s",
                key_points_json=[],
                structured_json={},
                review_json={},
                next_review_at=datetime.utcnow() - timedelta(hours=1),
            )
        )
    db.flush()

    n, _, _ = await execute_review_push(
        db, row, slot="2026-06-23T08:00", manual=False
    )
    assert n == 1
    assert row.last_run_slot is None
    assert learning_note_service.due_notes(db, tenant_id=1, limit=5)
