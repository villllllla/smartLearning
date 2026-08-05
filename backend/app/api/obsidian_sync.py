"""Obsidian vault sync control API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.obsidian_sync import (
    ObsidianSyncRunRequest,
    ObsidianSyncRunResponse,
    ObsidianSyncStatus,
    ObsidianWikiDedupeResponse,
)
from app.services.obsidian_sync_service import get_status, run_full_scan
from app.services.wiki_dedupe_service import (
    backfill_obsidian_rel_paths_from_commits,
    dedupe_wikis,
)

router = APIRouter()


@router.get("/status", response_model=ObsidianSyncStatus)
def obsidian_sync_status(
    settings: Settings = Depends(get_settings),
) -> ObsidianSyncStatus:
    return ObsidianSyncStatus.model_validate(get_status(settings))


@router.post("/scan", response_model=ObsidianSyncRunResponse)
def obsidian_sync_scan(
    payload: ObsidianSyncRunRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ObsidianSyncRunResponse:
    try:
        summary = run_full_scan(db, settings, force=payload.force)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    db.commit()
    return ObsidianSyncRunResponse(
        scanned=summary.scanned,
        created=summary.created,
        updated=summary.updated,
        skipped=summary.skipped,
        failed=summary.failed,
        wikis_deduped=summary.wikis_deduped,
        wikis_repaired=summary.wikis_repaired,
        errors=summary.errors[:20],
    )


@router.post("/dedupe-wikis", response_model=ObsidianWikiDedupeResponse)
def obsidian_dedupe_wikis(db: Session = Depends(get_db)) -> ObsidianWikiDedupeResponse:
    """Merge duplicate wikis (same title / vault path), keeping the newest."""
    backfill_obsidian_rel_paths_from_commits(db)
    result = dedupe_wikis(db, dry_run=False)
    db.commit()
    return ObsidianWikiDedupeResponse(
        groups_merged=result.groups_merged,
        wikis_removed=result.wikis_removed,
        reassigned_questions=result.reassigned_questions,
        reassigned_candidates=result.reassigned_candidates,
        details=result.details[:30],
    )
