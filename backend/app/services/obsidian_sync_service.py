"""Obsidian vault folder → SmartLearning Wiki sync."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.services.branch_service import repair_wikis_missing_main_branch
from app.services.obsidian_vault import (
    VaultImportResult,
    import_or_update_from_vault,
    is_markdown_path,
    vault_rel_path,
)
from app.services.question_dedupe_service import merge_duplicates
from app.services.wiki_dedupe_service import (
    backfill_obsidian_rel_paths_from_commits,
    backfill_obsidian_rel_paths_from_state,
    bind_obsidian_paths_from_vault_files,
    dedupe_wikis,
    rebuild_sync_mappings_from_db,
)

log = logging.getLogger(__name__)

_DEFAULT_IGNORE = frozenset(
    {".obsidian", ".trash", ".git", "node_modules", ".cursor", ".smartlearning"}
)


@dataclass
class MappingEntry:
    wiki_id: int
    last_mtime: float | None = None
    last_content_hash: str | None = None


@dataclass
class SyncState:
    vault_path: str
    mappings: dict[str, MappingEntry] = field(default_factory=dict)
    last_full_scan_at: str | None = None
    last_file_sync_at: str | None = None
    recent_events: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "vault_path": self.vault_path,
            "mappings": {
                k: {
                    "wiki_id": v.wiki_id,
                    "last_mtime": v.last_mtime,
                    "last_content_hash": v.last_content_hash,
                }
                for k, v in self.mappings.items()
            },
            "last_full_scan_at": self.last_full_scan_at,
            "last_file_sync_at": self.last_file_sync_at,
            "recent_events": self.recent_events[-50:],
        }

    @classmethod
    def from_json(cls, data: dict) -> SyncState:
        mappings: dict[str, MappingEntry] = {}
        for k, v in (data.get("mappings") or {}).items():
            if isinstance(v, dict) and "wiki_id" in v:
                mappings[k] = MappingEntry(
                    wiki_id=int(v["wiki_id"]),
                    last_mtime=v.get("last_mtime"),
                    last_content_hash=v.get("last_content_hash"),
                )
        return cls(
            vault_path=str(data.get("vault_path") or ""),
            mappings=mappings,
            last_full_scan_at=data.get("last_full_scan_at"),
            last_file_sync_at=data.get("last_file_sync_at"),
            recent_events=list(data.get("recent_events") or []),
        )


@dataclass
class SyncRunSummary:
    scanned: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    wikis_deduped: int = 0
    wikis_repaired: int = 0
    errors: list[str] = field(default_factory=list)


def _state_path(settings: Settings) -> Path:
    d = settings.data_dir / "obsidian_sync"
    d.mkdir(parents=True, exist_ok=True)
    return d / "state.json"


def load_state(settings: Settings | None = None) -> SyncState:
    settings = settings or get_settings()
    path = _state_path(settings)
    if not path.exists():
        return SyncState(vault_path=str(settings.obsidian_vault_path or ""))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return SyncState.from_json(data)
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("obsidian sync state corrupt: %s", exc)
        return SyncState(vault_path=str(settings.obsidian_vault_path or ""))


def save_state(state: SyncState, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    path = _state_path(settings)
    path.write_text(json.dumps(state.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")


def _log_event(state: SyncState, msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    state.recent_events.append(f"[{ts}] {msg}")
    state.recent_events = state.recent_events[-50:]


def _should_ignore(path: Path, ignore_dirs: frozenset[str]) -> bool:
    parts = path.parts
    for p in parts:
        if p in ignore_dirs:
            return True
        if p.startswith(".") and p not in (".", ".."):
            return True
    return False


def iter_markdown_files(vault_root: Path, ignore_dirs: frozenset[str]) -> list[Path]:
    vault_root = vault_root.resolve()
    out: list[Path] = []
    for pattern in ("**/*.md", "**/*.markdown"):
        for p in vault_root.glob(pattern):
            if not p.is_file():
                continue
            if _should_ignore(p.relative_to(vault_root), ignore_dirs):
                continue
            out.append(p)
    return sorted(out, key=lambda x: x.as_posix())


def _content_hash(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def sync_markdown_file(
    db: Session,
    *,
    vault_root: Path,
    md_path: Path,
    state: SyncState,
    force: bool = False,
) -> VaultImportResult:
    """Sync one file; update ``state.mappings`` on success."""
    rel = vault_rel_path(vault_root, md_path)
    try:
        mtime = md_path.stat().st_mtime
        raw = md_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw = md_path.read_text(encoding="gbk")
        mtime = md_path.stat().st_mtime
    except OSError as exc:
        return VaultImportResult(
            rel_path=rel,
            wiki_id=None,
            created=False,
            updated=False,
            skipped=False,
            error=str(exc),
        )

    ch = _content_hash(raw)
    entry = state.mappings.get(rel)
    if (
        not force
        and entry is not None
        and entry.last_mtime == mtime
        and entry.last_content_hash == ch
    ):
        return VaultImportResult(
            rel_path=rel,
            wiki_id=entry.wiki_id,
            created=False,
            updated=False,
            skipped=True,
        )

    wiki_id = entry.wiki_id if entry else None
    result = import_or_update_from_vault(
        db, vault_root=vault_root, md_path=md_path, wiki_id=wiki_id, tenant_id=1
    )
    if result.error:
        return result
    if result.wiki_id is None:
        return result

    settings = get_settings()
    if settings.rag_enabled and settings.rag_auto_index:
        try:
            from app.services.rag.index_service import index_wiki

            index_wiki(db, result.wiki_id, settings)
            db.commit()
        except Exception:
            log.warning("rag auto-index failed for wiki %s", result.wiki_id, exc_info=True)

    state.mappings[rel] = MappingEntry(
        wiki_id=result.wiki_id,
        last_mtime=mtime,
        last_content_hash=ch,
    )
    state.last_file_sync_at = datetime.now(timezone.utc).isoformat()
    return result


def run_full_scan(
    db: Session,
    settings: Settings | None = None,
    *,
    force: bool = False,
) -> SyncRunSummary:
    settings = settings or get_settings()
    if not settings.obsidian_sync_enabled:
        raise ValueError("Obsidian sync is disabled (SL_OBSIDIAN_SYNC_ENABLED=false)")
    vault = settings.obsidian_vault_path_resolved
    if vault is None:
        raise ValueError("SL_OBSIDIAN_VAULT_PATH is not set or does not exist")

    ignore = settings.obsidian_ignore_dir_set | _DEFAULT_IGNORE
    state = load_state(settings)
    state.vault_path = str(vault)
    summary = SyncRunSummary()

    md_files = iter_markdown_files(vault, ignore)

    backfill_obsidian_rel_paths_from_state(db, state.mappings)
    backfill_obsidian_rel_paths_from_commits(db)
    bind_obsidian_paths_from_vault_files(db, vault_root=vault, markdown_paths=md_files)
    summary.wikis_repaired = repair_wikis_missing_main_branch(db)
    if summary.wikis_repaired:
        _log_event(state, f"repaired {summary.wikis_repaired} wikis missing main branch")
    db.commit()
    for rel, wiki_id in rebuild_sync_mappings_from_db(db).items():
        entry = state.mappings.get(rel)
        if entry is None or entry.wiki_id != wiki_id:
            state.mappings[rel] = MappingEntry(wiki_id=wiki_id)

    for md_path in md_files:
        if not is_markdown_path(md_path):
            continue
        summary.scanned += 1
        try:
            result = sync_markdown_file(
                db, vault_root=vault, md_path=md_path, state=state, force=force
            )
        except Exception as exc:
            summary.failed += 1
            summary.errors.append(f"{md_path.name}: {exc}")
            log.exception("obsidian sync failed for %s", md_path)
            continue

        if result.error:
            summary.failed += 1
            summary.errors.append(f"{result.rel_path}: {result.error}")
        elif result.skipped:
            summary.skipped += 1
        elif result.created:
            summary.created += 1
            _log_event(state, f"created wiki#{result.wiki_id} ← {result.rel_path}")
        elif result.updated:
            summary.updated += 1
            _log_event(state, f"updated wiki#{result.wiki_id} ← {result.rel_path}")

    state.last_full_scan_at = datetime.now(timezone.utc).isoformat()

    dedupe_result = dedupe_wikis(db, dry_run=False)
    if dedupe_result.wikis_removed:
        summary.wikis_deduped = dedupe_result.wikis_removed
        db.commit()
        _log_event(
            state,
            f"wiki dedupe: removed {dedupe_result.wikis_removed} duplicates "
            f"({dedupe_result.groups_merged} groups)",
        )
        for rel, wiki_id in rebuild_sync_mappings_from_db(db).items():
            prev = state.mappings.get(rel)
            state.mappings[rel] = MappingEntry(
                wiki_id=wiki_id,
                last_mtime=prev.last_mtime if prev else None,
                last_content_hash=prev.last_content_hash if prev else None,
            )

    save_state(state, settings)

    if settings.obsidian_sync_dedupe_after:
        merge_duplicates(db, tenant_id=1, dry_run=False)
        _log_event(state, "ran question dedupe after sync")
        save_state(state, settings)

    _log_event(
        state,
        f"full scan: {summary.created} created, {summary.updated} updated, "
        f"{summary.skipped} skipped, {summary.failed} failed, "
        f"{summary.wikis_repaired} wikis repaired, "
        f"{summary.wikis_deduped} wiki duplicates removed",
    )
    save_state(state, settings)
    return summary


def get_status(settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    state = load_state(settings)
    vault = settings.obsidian_vault_path_resolved
    return {
        "enabled": settings.obsidian_sync_enabled,
        "vault_path": str(settings.obsidian_vault_path or ""),
        "vault_exists": vault is not None and vault.is_dir(),
        "debounce_seconds": settings.obsidian_sync_debounce_seconds,
        "dedupe_after_sync": settings.obsidian_sync_dedupe_after,
        "mapped_files": len(state.mappings),
        "last_full_scan_at": state.last_full_scan_at,
        "last_file_sync_at": state.last_file_sync_at,
        "recent_events": state.recent_events[-15:],
    }
