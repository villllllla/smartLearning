"""Regression guard for the agent's deterministic rule routing.

The full accuracy report (incl. LLM intent routing) lives in ``eval/run_eval.py``.
Here we only assert the *rule fast path* stays at 100%, so a change to trigger
prefixes / answer parsing can't silently misroute a known utterance. The
adversarial cases are asserted to still misroute — they document a known
prefix-routing limitation; if a fix lands, this test flags it so the dataset
gets updated.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.integrations.feishu import agent as agent_module
from app.integrations.feishu.commands import CommandResult
from app.services.feishu_trigger_service import seed_default_rules
from eval.routing_cases import ADVERSARIAL_CASES, RULE_CASES


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    seed_default_rules(session, tenant_id=1)
    session.commit()
    try:
        yield session
    finally:
        session.close()


async def _route(db, text, idx):
    captured = {}

    async def _recorder(db_, session_, tool, args, *, user_text=None):
        captured["tool"] = tool
        return CommandResult(texts=["[recorded]"])

    original = agent_module.execute_tool
    agent_module.execute_tool = _recorder
    try:
        await agent_module.handle_incoming_text(
            db, get_settings(), open_id=f"ou_t_{idx}", chat_id=f"oc_t_{idx}", text=text
        )
    finally:
        agent_module.execute_tool = original
    return captured.get("tool")


@pytest.mark.asyncio
@pytest.mark.parametrize("case", RULE_CASES, ids=[c.text for c in RULE_CASES])
async def test_rule_routing_is_exact(db, case):
    got = await _route(db, case.text, id(case))
    assert got == case.expected_tool, f"{case.text!r}: expected {case.expected_tool}, got {got}"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case", ADVERSARIAL_CASES, ids=[c.text for c in ADVERSARIAL_CASES]
)
async def test_adversarial_cases_document_known_gaps(db, case):
    """These SHOULD misroute today. When one starts passing, update the dataset."""
    got = await _route(db, case.text, id(case))
    # Not asserting a specific wrong tool — only that the rule layer does not
    # already produce the correct answer (which would need the LLM router).
    if got is not None and got == case.expected_tool:
        pytest.fail(
            f"Adversarial case {case.text!r} now routes correctly at the rule "
            f"layer — move it out of ADVERSARIAL_CASES."
        )
