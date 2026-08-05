"""Tests for Obsidian vault → wiki sync."""
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.services.obsidian_sync_service import (
    SyncState,
    run_full_scan,
    save_state,
    sync_markdown_file,
)


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


def test_sync_creates_and_updates_wiki(db, tmp_path: Path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "redis.md"
    note.write_text("# Redis\n\n![pic](assets/p.png)\n", encoding="utf-8")
    assets = vault / "assets"
    assets.mkdir()
    (assets / "p.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    monkeypatch.setenv("SL_OBSIDIAN_SYNC_ENABLED", "true")
    monkeypatch.setenv("SL_OBSIDIAN_VAULT_PATH", str(vault))
    get_settings.cache_clear()
    settings = get_settings()

    state = SyncState(vault_path=str(vault))
    r1 = sync_markdown_file(db, vault_root=vault, md_path=note, state=state)
    assert r1.created and r1.wiki_id
    save_state(state, settings)

    note.write_text("# Redis\n\nUpdated body.\n", encoding="utf-8")
    r2 = sync_markdown_file(db, vault_root=vault, md_path=note, state=state, force=True)
    assert r2.updated and r2.wiki_id == r1.wiki_id

    summary = run_full_scan(db, settings, force=False)
    assert summary.scanned >= 1
