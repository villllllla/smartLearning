"""Feishu quiz answer routing and submit_answer tool."""
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.integrations.feishu.answer_routing import (
    parse_answer_submission,
    should_submit_as_answer,
)
from app.integrations.feishu.tools import execute_tool
from app.models.bot_session import BotSession
from app.models.practice import AnswerAttempt
from app.models.question import Question
from app.models.tenant import Tenant
from app.services.bot_session_service import set_question_queue


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


def test_parse_answer_submission_requires_question_id():
    assert parse_answer_submission("Kv cache爆了怎么处理") is None
    assert not should_submit_as_answer("Kv cache爆了怎么处理", has_current_question=True)
    assert not should_submit_as_answer("答案 12", has_current_question=True)

    parsed = parse_answer_submission(
        "15 Redis 使用单线程处理命令，主要因为避免锁开销并保证简单性。"
    )
    assert parsed == (
        15,
        "Redis 使用单线程处理命令，主要因为避免锁开销并保证简单性。",
    )

    assert parse_answer_submission("作答 15 通过限制工具调用深度来避免死循环") == (
        15,
        "通过限制工具调用深度来避免死循环",
    )
    assert parse_answer_submission("题号15 同上所述的处理方式") == (
        15,
        "同上所述的处理方式",
    )


@pytest.mark.asyncio
async def test_submit_answer_records_attempt(db):
    tenant = Tenant(id=1, name="t", slug="t")
    db.add(tenant)
    q = Question(
        tenant_id=1,
        question_text="什么是 CAP？",
        answer_standard="一致性、可用性、分区容忍",
        difficulty="medium",
        qtype="concept",
    )
    db.add(q)
    db.flush()

    session = BotSession(platform="feishu", feishu_open_id="ou_answer_test")
    db.add(session)
    db.flush()
    set_question_queue(session, [q.id])

    attempt = AnswerAttempt(
        question_id=q.id,
        user_answer_text="我的作答",
        grade="B",
        score_correctness=70,
        score_completeness=65,
        score_structure=60,
        score_depth=55,
        feedback_text="不错",
        channel="feishu",
        feishu_open_id="ou_answer_test",
        feishu_message_id="om_test_msg",
        bot_session_id=session.id,
    )

    with patch(
        "app.integrations.feishu.tools.score_answer",
        new_callable=AsyncMock,
        return_value=attempt,
    ):
        res = await execute_tool(
            db,
            session,
            "submit_answer",
            {
                "question_id": q.id,
                "user_answer": "我的作答内容比较长一些",
                "feishu_message_id": "om_test_msg",
            },
            user_text="我的作答内容比较长一些",
        )

    assert "作答已记录" in res.texts[0]
    assert "attempt_id=" in res.texts[0]
    assert "等级 B" in res.texts[0]


@pytest.mark.asyncio
async def test_submit_answer_without_question_id_rejected(db):
    session = BotSession(platform="feishu", feishu_open_id="ou_reject")
    db.add(session)
    db.flush()
    set_question_queue(session, [99])

    res = await execute_tool(
        db,
        session,
        "submit_answer",
        {"user_answer": "只有作答没有题号的内容足够长"},
        user_text="只有作答没有题号的内容足够长",
    )
    assert "须带题号" in res.texts[0]
