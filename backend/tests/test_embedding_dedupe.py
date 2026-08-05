"""Tests for embedding-based question dedupe."""
from __future__ import annotations

from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.models import Question, QuestionBankCollection, Tenant
from app.services.question_dedupe_service import find_bank_duplicate, preview_dedupe


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _fake_embed(texts: list[str]) -> list[list[float]]:
    vec = [0.9, 0.1, 0.1, 0.2]
    return [vec for _ in texts]


def test_embedding_dedupe_finds_paraphrase(monkeypatch):
    monkeypatch.setenv("SL_DEDUPE_USE_EMBEDDING", "true")
    get_settings.cache_clear()
    db = _session()
    tenant = Tenant(name="t", slug="t")
    db.add(tenant)
    db.flush()
    coll = QuestionBankCollection(tenant_id=tenant.id, name="c")
    db.add(coll)
    db.flush()
    q1 = Question(
        tenant_id=tenant.id,
        collection_id=coll.id,
        question_text="请解释 Redis 的单线程模型",
        answer_standard="a1",
        difficulty="medium",
        qtype="concept",
        stem_embedding_json='[0.9,0.1,0.1,0.2]',
        embedding_model="test",
    )
    db.add(q1)
    db.commit()

    with patch("app.services.question_dedupe_service.embed_stems", side_effect=_fake_embed):
        dup = find_bank_duplicate(
            db,
            "Redis 为什么采用单线程架构？",
            tenant_id=tenant.id,
            collection_id=coll.id,
            threshold=0.5,
        )
    assert dup is not None
    assert dup.id == q1.id
    get_settings.cache_clear()


def test_preview_dedupe_uses_embedding_method(monkeypatch):
    monkeypatch.setenv("SL_DEDUPE_USE_EMBEDDING", "true")
    get_settings.cache_clear()
    db = _session()
    tenant = Tenant(name="t", slug="t")
    db.add(tenant)
    db.flush()
    coll = QuestionBankCollection(tenant_id=tenant.id, name="c")
    db.add(coll)
    db.flush()
    db.add_all(
        [
            Question(
                tenant_id=tenant.id,
                collection_id=coll.id,
                question_text="题 A",
                answer_standard="a",
                difficulty="medium",
                qtype="concept",
                stem_embedding_json="[1.0,0.0,0.0,0.0]",
                embedding_model="test",
            ),
            Question(
                tenant_id=tenant.id,
                collection_id=coll.id,
                question_text="题 B",
                answer_standard="b",
                difficulty="medium",
                qtype="concept",
                stem_embedding_json="[0.99,0.01,0.0,0.0]",
                embedding_model="test",
            ),
        ]
    )
    db.commit()

    preview = preview_dedupe(db, tenant_id=tenant.id, threshold=0.9)
    assert preview.method == "embedding"
    assert preview.duplicate_question_count == 1
    get_settings.cache_clear()
