"""Obsidian vault sync API schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ObsidianSyncStatus(BaseModel):
    enabled: bool
    vault_path: str
    vault_exists: bool
    debounce_seconds: float
    dedupe_after_sync: bool
    mapped_files: int
    last_full_scan_at: str | None
    last_file_sync_at: str | None
    recent_events: list[str]


class ObsidianSyncRunRequest(BaseModel):
    force: bool = Field(
        False,
        description="Re-import even when file mtime/hash unchanged",
    )


class ObsidianSyncRunResponse(BaseModel):
    scanned: int
    created: int
    updated: int
    skipped: int
    failed: int
    wikis_deduped: int = 0
    wikis_repaired: int = 0
    errors: list[str]


class ObsidianWikiDedupeResponse(BaseModel):
    groups_merged: int
    wikis_removed: int
    reassigned_questions: int
    reassigned_candidates: int
    details: list[str] = Field(default_factory=list)
