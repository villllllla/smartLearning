"""Tests for question stem similarity and clustering."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models import Question, QuestionBankCollection, Tenant
from app.services.question_dedupe_service import merge_duplicates, preview_dedupe
from app.services.question_similarity import (
    cluster_indices,
    normalize_question_text,
    question_similarity,
)


def test_normalize_strips_punctuation():
    assert normalize_question_text("  Redis 是什么？ ") == normalize_question_text("redis是什么")


def test_similarity_high_for_near_duplicates():
    a = "请解释 Redis 的单线程模型"
    b = "请解释Redis的单线程模型?"
    assert question_similarity(a, b) >= 0.85


def test_cluster_indices():
    pairs = [(0, 1), (1, 2)]
    clusters = cluster_indices(4, pairs)
    assert clusters == [[0, 1, 2]]


def test_merge_duplicates_reassigns_attempts():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        db.add(Tenant(id=1, name="t", slug="t"))
        db.flush()
        coll = QuestionBankCollection(tenant_id=1, name="默认题库")
        db.add(coll)
        db.flush()
        q1 = Question(
            tenant_id=1,
            collection_id=coll.id,
            question_text="什么是 CAP 定理",
            answer_standard="a1",
            difficulty="medium",
            qtype="concept",
        )
        q2 = Question(
            tenant_id=1,
            collection_id=coll.id,
            question_text="什么是CAP定理?",
            answer_standard="a2",
            difficulty="medium",
            qtype="concept",
        )
        db.add_all([q1, q2])
        db.commit()

        preview = preview_dedupe(db, tenant_id=1, threshold=0.85)
        assert preview.duplicate_question_count == 1
        assert preview.cluster_count == 1

        result = merge_duplicates(db, tenant_id=1, threshold=0.85)
        assert result.questions_removed == 1
        db.refresh(q1)
        assert q2.deleted_at is not None
    finally:
        db.close()
