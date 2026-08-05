"""LLM per-scene fallback model chain."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models import AppSettings, FunctionBinding, Model, ModelProvider, PromptTemplate
from app.models.tenant import Tenant
from app.services.llm.adapters import LLMHttpError
from app.services.llm.client import FallbackLLMClient, LLMClient, LLMError, resolve_for_scene
from app.services.llm.types import LLMMessage, LLMResponse


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(Tenant(id=1, name="t", slug="t"))
    prov = ModelProvider(
        id=1, tenant_id=1, name="p1", type="openai_compatible", base_url="http://x", enabled=True
    )
    prov2 = ModelProvider(
        id=2, tenant_id=1, name="p2", type="openai_compatible", base_url="http://y", enabled=True
    )
    big = Model(
        id=1, provider_id=1, name="big-model", enabled=True, is_default=True, context_window=8192
    )
    small = Model(
        id=2, provider_id=2, name="small-model", enabled=True, is_default=False, context_window=4096
    )
    global_fb = Model(
        id=3, provider_id=1, name="global-fb", enabled=True, is_default=False, context_window=4096
    )
    prompt = PromptTemplate(
        id=1,
        tenant_id=1,
        name="todo v1",
        scene="todo_intent_parsing",
        content="parse {USER_MESSAGE}",
        version_no=1,
        is_current=True,
    )
    binding = FunctionBinding(
        tenant_id=1,
        scene="todo_intent_parsing",
        prompt_template_id=1,
        model_id=1,
        fallback_model_id=2,
        params_json={"temperature": 0.2},
        fallback_params_json={"temperature": 0.1},
    )
    settings = AppSettings(tenant_id=1, llm_fallback_model_id=3)
    session.add_all([prov, prov2, big, small, global_fb, prompt, binding, settings])
    session.flush()
    try:
        yield session
    finally:
        session.close()


def test_resolve_for_scene_builds_fallback_chain(db):
    scn = resolve_for_scene(db, "todo_intent_parsing", tenant_id=1)
    assert scn.model.id == 1
    assert len(scn.fallback_specs) == 2
    assert scn.fallback_specs[0].model.id == 2
    assert scn.fallback_specs[1].model.id == 3


@pytest.mark.asyncio
async def test_fallback_client_switches_on_transient_error():
    primary = MagicMock(spec=LLMClient)
    primary.model = MagicMock(name="big-model")
    primary.provider = MagicMock()
    primary.params = {}
    primary._adapter = MagicMock()
    try:
        raise LLMHttpError(429, "rate")
    except LLMHttpError as http_err:
        llm_err = LLMError("busy")
        llm_err.__cause__ = http_err
    primary.chat = AsyncMock(side_effect=llm_err)

    backup = MagicMock(spec=LLMClient)
    backup.model = MagicMock(name="small-model")
    backup.chat = AsyncMock(return_value=LLMResponse(text="ok"))

    client = FallbackLLMClient(primary, [backup])
    resp = await client.chat([LLMMessage(role="user", content="hi")])
    assert resp.text == "ok"
    backup.chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_fallback_client_does_not_switch_on_non_transient():
    primary = MagicMock(spec=LLMClient)
    primary.model = MagicMock(name="big-model")
    primary.provider = MagicMock()
    primary.params = {}
    primary._adapter = MagicMock()
    primary.chat = AsyncMock(side_effect=LLMError("bad request"))

    backup = MagicMock(spec=LLMClient)
    backup.chat = AsyncMock(return_value=LLMResponse(text="ok"))

    client = FallbackLLMClient(primary, [backup])
    with pytest.raises(LLMError, match="bad request"):
        await client.chat([LLMMessage(role="user", content="hi")])
    backup.chat.assert_not_awaited()
