"""Tests for Feishu agent tool execution (no LLM)."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.integrations.feishu.tools import execute_tool
from app.models.bot_session import BotSession


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.mark.asyncio
async def test_help_tool(db):
    session = BotSession(platform="feishu", feishu_open_id="ou_test")
    db.add(session)
    db.flush()
    res = await execute_tool(db, session, "help", {})
    assert res.texts
    assert "自然语言" in res.texts[0] or "SmartLearning" in res.texts[0]


@pytest.mark.asyncio
async def test_draw_questions_empty_bank(db):
    session = BotSession(platform="feishu", feishu_open_id="ou_test2")
    db.add(session)
    db.flush()
    res = await execute_tool(
        db,
        session,
        "draw_questions",
        {"limit": 5, "mode": "random"},
    )
    assert "题库为空" in res.texts[0]


@pytest.mark.asyncio
async def test_next_question_without_queue(db):
    session = BotSession(platform="feishu", feishu_open_id="ou_test3")
    db.add(session)
    db.flush()
    res = await execute_tool(db, session, "next_question", {})
    assert "没有题单" in res.texts[0]
