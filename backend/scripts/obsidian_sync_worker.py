#!/usr/bin/env python3
"""Watch an Obsidian vault and sync .md files into SmartLearning wikis.

Usage (from backend/, with venv active):

    python scripts/obsidian_sync_worker.py

Requires in ``backend/.env``:

    SL_OBSIDIAN_SYNC_ENABLED=true
    SL_OBSIDIAN_VAULT_PATH=D:/Obsidian/MyVault
    SL_OBSIDIAN_SYNC_DEBOUNCE_SECONDS=5

Optional: ``SL_OBSIDIAN_SYNC_ON_START=true`` runs a full scan when the worker starts.
"""
from __future__ import annotations

import logging
import sys
import threading
import time
from pathlib import Path

# Allow ``python scripts/obsidian_sync_worker.py`` from backend/
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.obsidian_sync_service import (
    _DEFAULT_IGNORE,
    load_state,
    run_full_scan,
    save_state,
    sync_markdown_file,
)
from app.services.obsidian_vault import is_markdown_path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("obsidian_sync_worker")


class _DebouncedVaultHandler(FileSystemEventHandler):
    def __init__(self, vault_root: Path, debounce_sec: float, ignore_dirs: frozenset[str]) -> None:
        super().__init__()
        self.vault_root = vault_root
        self.debounce_sec = debounce_sec
        self.ignore_dirs = ignore_dirs | _DEFAULT_IGNORE
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def _schedule(self, path: Path) -> None:
        if not is_markdown_path(path):
            return
        try:
            path.resolve().relative_to(self.vault_root)
        except ValueError:
            return
        rel = path.relative_to(self.vault_root)
        if any(part in self.ignore_dirs or part.startswith(".") for part in rel.parts):
            return

        key = path.as_posix()

        def _run() -> None:
            settings = get_settings()
            state = load_state(settings)
            db = SessionLocal()
            try:
                result = sync_markdown_file(
                    db,
                    vault_root=self.vault_root,
                    md_path=path,
                    state=state,
                    force=False,
                )
                save_state(state, settings)
                if result.error:
                    log.error("sync %s: %s", rel, result.error)
                elif result.skipped:
                    log.debug("skip unchanged %s", rel)
                elif result.created:
                    log.info("created wiki#%s ← %s", result.wiki_id, rel)
                elif result.updated:
                    log.info("updated wiki#%s ← %s", result.wiki_id, rel)
            except Exception:
                log.exception("sync failed for %s", rel)
            finally:
                db.close()

        with self._lock:
            old = self._timers.pop(key, None)
            if old is not None:
                old.cancel()
            timer = threading.Timer(self.debounce_sec, _run)
            self._timers[key] = timer
            timer.daemon = True
            timer.start()

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._schedule(Path(event.src_path))

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._schedule(Path(event.src_path))

    def on_moved(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._schedule(Path(event.dest_path))


def main() -> None:
    settings = get_settings()
    if not settings.obsidian_sync_enabled:
        log.error("Set SL_OBSIDIAN_SYNC_ENABLED=true in backend/.env")
        sys.exit(1)
    vault = settings.obsidian_vault_path_resolved
    if vault is None:
        log.error("SL_OBSIDIAN_VAULT_PATH must point to an existing Obsidian vault folder")
        sys.exit(1)

    log.info("Watching vault: %s", vault)

    if settings.obsidian_sync_on_start:
        db = SessionLocal()
        try:
            summary = run_full_scan(db, settings, force=False)
            log.info(
                "Initial scan: %s created, %s updated, %s skipped, %s failed",
                summary.created,
                summary.updated,
                summary.skipped,
                summary.failed,
            )
        finally:
            db.close()

    handler = _DebouncedVaultHandler(
        vault,
        settings.obsidian_sync_debounce_seconds,
        settings.obsidian_ignore_dir_set,
    )
    observer = Observer()
    observer.schedule(handler, str(vault), recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Stopping observer…")
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
