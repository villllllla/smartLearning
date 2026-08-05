"""Feishu message_id dedup across restarts."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.integrations.feishu.dedup import try_claim_message
from app.models.feishu_processed_message import FeishuProcessedMessage  # noqa: F401


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


def test_claim_once(db):
    assert try_claim_message(
        db, message_id="om_test_1", event_id="evt_1", text="帮助"
    ) is False
    assert try_claim_message(
        db, message_id="om_test_1", event_id="evt_2", text="帮助"
    ) is True


def test_different_messages(db):
    assert try_claim_message(
        db, message_id="om_a", event_id="evt_a", text="a"
    ) is False
    assert try_claim_message(
        db, message_id="om_b", event_id="evt_b", text="b"
    ) is False
