"""Tests for scheduled question push."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.push_schedule import QuestionPushSchedule
from app.models.tenant import Tenant
from app.services.push_schedule_service import is_due_now, parse_push_times


@pytest.fixture()
def db():
    """Empty tenant settings, so is_due_now falls back to Asia/Shanghai."""
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


def test_parse_push_times_ok():
    assert parse_push_times(["9:00", "18:30"]) == ["09:00", "18:30"]


def test_parse_push_times_rejects_invalid():
    with pytest.raises(ValueError, match="格式无效"):
        parse_push_times(["09:00", ".", ","])


def test_is_due_now_daily(db):
    row = QuestionPushSchedule(
        tenant_id=1,
        enabled=True,
        timezone="Asia/Shanghai",
        push_times=["09:00"],
        frequency="daily",
    )
    tz = ZoneInfo("Asia/Shanghai")
    at_nine = datetime(2026, 6, 2, 9, 0, tzinfo=tz)
    assert is_due_now(row, at_nine, db=db) == "2026-06-02T09:00"
    row.last_run_slot = "2026-06-02T09:00"
    assert is_due_now(row, at_nine, db=db) is None  # dedupe same slot
    at_ten = datetime(2026, 6, 2, 10, 0, tzinfo=tz)
    assert is_due_now(row, at_ten, db=db) is None


def test_is_due_now_weekdays_skips_saturday(db):
    row = QuestionPushSchedule(
        tenant_id=1,
        enabled=True,
        timezone="Asia/Shanghai",
        push_times=["09:00"],
        frequency="weekdays",
    )
    tz = ZoneInfo("Asia/Shanghai")
    sat = datetime(2026, 6, 6, 9, 0, tzinfo=tz)  # 2026-06-06 is Saturday
    assert is_due_now(row, sat, db=db) is None
