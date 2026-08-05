"""Merge duplicate wikis (Obsidian resync / corrupt state) — keep the newest row."""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models import Question, QuestionCandidate, Wiki, WikiCommit
from app.models.rag_chunk import RagChunk

log = logging.getLogger(__name__)


@dataclass
class WikiDedupeResult:
    groups_merged: int = 0
    wikis_removed: int = 0
    reassigned_questions: int = 0
    reassigned_candidates: int = 0
    rag_chunks_deleted: int = 0
    details: list[str] = field(default_factory=list)


def _active_wikis(db: Session) -> list[Wiki]:
    return list(
        db.execute(
            select(Wiki)
            .where(Wiki.deleted_at.is_(None))
            .order_by(Wiki.updated_at.desc(), Wiki.id.desc())
        ).scalars().all()
    )


def _duplicate_groups(wikis: list[Wiki]) -> list[list[Wiki]]:
    """Build merge groups by vault path, then by exact title (skip already grouped)."""
    groups: list[list[Wiki]] = []
    assigned: set[int] = set()

    by_path: dict[str, list[Wiki]] = defaultdict(list)
    for w in wikis:
        path = (w.obsidian_rel_path or "").strip()
        if path:
            by_path[path].append(w)

    for bucket in by_path.values():
        if len(bucket) < 2:
            continue
        ordered = sorted(bucket, key=lambda x: (x.updated_at, x.id), reverse=True)
        groups.append(ordered)
        assigned.update(w.id for w in ordered)

    by_title: dict[str, list[Wiki]] = defaultdict(list)
    for w in wikis:
        if w.id in assigned:
            continue
        by_title[w.title.strip()].append(w)

    for bucket in by_title.values():
        if len(bucket) < 2:
            continue
        ordered = sorted(bucket, key=lambda x: (x.updated_at, x.id), reverse=True)
        groups.append(ordered)

    return groups


def _reassign_wiki_id(db: Session, old_id: int, new_id: int) -> tuple[int, int, int]:
    q_res = db.execute(
        update(Question)
        .where(Question.source_wiki_id == old_id)
        .values(source_wiki_id=new_id)
    )
    c_res = db.execute(
        update(QuestionCandidate)
        .where(QuestionCandidate.source_wiki_id == old_id)
        .values(source_wiki_id=new_id)
    )
    rag_res = db.execute(delete(RagChunk).where(RagChunk.wiki_id == old_id))
    db.flush()
    return (
        int(q_res.rowcount or 0),
        int(c_res.rowcount or 0),
        int(rag_res.rowcount or 0),
    )


def dedupe_wikis(db: Session, *, dry_run: bool = False) -> WikiDedupeResult:
    """Soft-delete older duplicate wikis; reassign bank/candidate links to the keeper."""
    result = WikiDedupeResult()
    wikis = _active_wikis(db)

    for group in _duplicate_groups(wikis):
        keeper, *dupes = group
        result.groups_merged += 1
        for dup in dupes:
            qn, cn, rn = _reassign_wiki_id(db, dup.id, keeper.id)
            result.reassigned_questions += qn
            result.reassigned_candidates += cn
            result.rag_chunks_deleted += rn
            if not dry_run:
                dup.deleted_at = datetime.utcnow()
                if keeper.obsidian_rel_path and not dup.obsidian_rel_path:
                    pass
                elif dup.obsidian_rel_path and not keeper.obsidian_rel_path:
                    keeper.obsidian_rel_path = dup.obsidian_rel_path
            result.wikis_removed += 1
            result.details.append(
                f"merged wiki#{dup.id} → #{keeper.id} ({keeper.title!r})"
            )
            log.info(
                "wiki dedupe: removed #%s, kept #%s (%s)",
                dup.id,
                keeper.id,
                keeper.title,
            )

    if not dry_run:
        db.flush()
    return result


def backfill_obsidian_rel_paths_from_state(db: Session, mappings: dict) -> int:
    """Apply rel_path from sync state onto wiki rows (recovery after corrupt state)."""
    updated = 0
    for rel, entry in mappings.items():
        rel = rel.strip()
        if not rel:
            continue
        wiki = db.get(Wiki, entry.wiki_id)
        if wiki is None or wiki.deleted_at is not None:
            continue
        if wiki.obsidian_rel_path != rel:
            wiki.obsidian_rel_path = rel
            updated += 1
    if updated:
        db.flush()
    return updated


def infer_obsidian_rel_path_from_commits(db: Session, wiki: Wiki) -> str | None:
    prefix = "obsidian sync: "
    msg = db.execute(
        select(WikiCommit.message)
        .where(
            WikiCommit.wiki_id == wiki.id,
            WikiCommit.message.like("obsidian sync:%"),
        )
        .order_by(WikiCommit.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if msg and msg.startswith(prefix):
        return msg[len(prefix) :].strip()
    return None


def backfill_obsidian_rel_paths_from_commits(db: Session) -> int:
    """Fill missing paths from commit messages (post-migration one-time helper)."""
    updated = 0
    for wiki in _active_wikis(db):
        if wiki.obsidian_rel_path:
            continue
        rel = infer_obsidian_rel_path_from_commits(db, wiki)
        if rel:
            wiki.obsidian_rel_path = rel
            updated += 1
    if updated:
        db.flush()
    return updated


def bind_obsidian_paths_from_vault_files(
    db: Session,
    *,
    vault_root: Path,
    markdown_paths: list[Path],
) -> int:
    """Match vault files to wikis by parsed title when ``obsidian_rel_path`` is missing."""
    from app.services.markdown_parser import parse_markdown
    from app.services.obsidian_vault import find_wiki_by_obsidian_rel_path, vault_rel_path

    vault_root = vault_root.resolve()
    updated = 0
    for md_path in markdown_paths:
        rel = vault_rel_path(vault_root, md_path)
        if find_wiki_by_obsidian_rel_path(db, rel) is not None:
            continue
        try:
            raw = md_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raw = md_path.read_text(encoding="gbk")
        meta = parse_markdown(raw, fallback_title=md_path.stem)
        title = (meta.title or md_path.stem).strip()
        rows = list(
            db.execute(
                select(Wiki)
                .where(Wiki.deleted_at.is_(None), Wiki.title == title)
                .order_by(Wiki.updated_at.desc(), Wiki.id.desc())
            ).scalars().all()
        )
        if len(rows) != 1:
            continue
        wiki = rows[0]
        if wiki.obsidian_rel_path and wiki.obsidian_rel_path != rel:
            continue
        wiki.obsidian_rel_path = rel
        updated += 1
    if updated:
        db.flush()
    return updated


def rebuild_sync_mappings_from_db(db: Session) -> dict[str, int]:
    """wiki_id keyed by rel_path for all active wikis with a stored path."""
    out: dict[str, int] = {}
    for wiki in _active_wikis(db):
        path = (wiki.obsidian_rel_path or "").strip()
        if path:
            out[path] = wiki.id
    return out
