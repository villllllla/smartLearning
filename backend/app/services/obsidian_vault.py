"""Import / update a single Markdown file from an Obsidian vault folder."""
from __future__ import annotations

import logging
import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Wiki, WikiCommit
from app.services.branch_service import commit_on_branch, ensure_main_branch
from app.services.markdown_parser import parse_markdown
from app.services.wiki_import import (
    _HTML_IMG,
    _IMG_INLINE,
    _LINK_INLINE,
    _REF_DEF,
    _looks_local,
    _safe_join,
    _strip_angle,
)
from app.services.wiki_service import create_wiki_from_markdown

log = logging.getLogger(__name__)

_MD_EXT = {".md", ".markdown"}
_ASSET_SENTINEL = "__SL_ASSET__"


@dataclass
class VaultImportResult:
    rel_path: str
    wiki_id: int | None
    created: bool
    updated: bool
    skipped: bool
    assets_written: int = 0
    missing_refs: list[str] = field(default_factory=list)
    error: str | None = None


def is_markdown_path(path: Path) -> bool:
    return path.suffix.lower() in _MD_EXT


def vault_rel_path(vault_root: Path, file_path: Path) -> str:
    rel = file_path.resolve().relative_to(vault_root.resolve())
    return rel.as_posix()


def _vault_file_exists(vault_root: Path, posix_path: str) -> bool:
    parts = posix_path.split("/")
    candidate = vault_root.joinpath(*parts)
    try:
        candidate.resolve().relative_to(vault_root.resolve())
    except ValueError:
        return False
    return candidate.is_file()


def _rewrite_vault_refs(
    md_text: str,
    vault_root: Path,
    base_dir: str,
) -> tuple[str, set[str], list[str]]:
    used: set[str] = set()
    missing: list[str] = []

    def _process(url_raw: str) -> str | None:
        inner, was_angled = _strip_angle(url_raw)
        if not _looks_local(inner):
            return None
        resolved = _safe_join(base_dir, inner)
        if resolved is None:
            missing.append(inner.strip())
            return None
        if not _vault_file_exists(vault_root, resolved):
            missing.append(resolved)
            return None
        used.add(resolved)
        rewritten_path = resolved.replace(" ", "%20")
        new_url = f"{_ASSET_SENTINEL}/{rewritten_path}"
        return f"<{new_url}>" if was_angled else new_url

    def _sub_inline(match: re.Match) -> str:
        new = _process(match.group("url"))
        if new is None:
            return match.group(0)
        if "bang" in match.groupdict():
            return (
                f"{match.group('bang')}[{match.group('alt')}]"
                f"({match.group('lead')}{new}{match.group('rest')})"
            )
        return (
            f"[{match.group('text')}]"
            f"({match.group('lead')}{new}{match.group('rest')})"
        )

    def _sub_ref(match: re.Match) -> str:
        new = _process(match.group("url"))
        if new is None:
            return match.group(0)
        return f"{match.group('prefix')}{new}{match.group('rest')}"

    def _sub_html(match: re.Match) -> str:
        new = _process(match.group("url"))
        if new is None:
            return match.group(0)
        if new.startswith("<") and new.endswith(">"):
            new = new[1:-1]
        return f"{match.group(1)}{match.group('quote')}{new}{match.group('quote')}"

    rewritten = _IMG_INLINE.sub(_sub_inline, md_text)
    rewritten = _LINK_INLINE.sub(_sub_inline, rewritten)
    rewritten = _REF_DEF.sub(_sub_ref, rewritten)
    rewritten = _HTML_IMG.sub(_sub_html, rewritten)
    return rewritten, used, missing


def _copy_assets(vault_root: Path, wiki_id: int, asset_paths: set[str]) -> int:
    settings = get_settings()
    asset_root = settings.wikis_dir / str(wiki_id) / "_assets"
    asset_root.mkdir(parents=True, exist_ok=True)
    written = 0
    for rel in asset_paths:
        src = vault_root.joinpath(*rel.split("/"))
        if not src.is_file():
            continue
        target = asset_root.joinpath(*rel.split("/"))
        try:
            target_resolved = target.resolve()
            root_resolved = asset_root.resolve()
            if root_resolved not in target_resolved.parents and target_resolved != root_resolved:
                continue
        except OSError:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(src.read_bytes())
        written += 1
    return written


def _apply_asset_prefix(wiki: Wiki, content_md: str) -> str:
    prefix = f"/api/wiki/{wiki.id}/assets"
    return content_md.replace(_ASSET_SENTINEL, prefix)


def find_wiki_by_obsidian_rel_path(db: Session, rel_path: str) -> Wiki | None:
    """Resolve an existing wiki for a vault file (newest if multiple)."""
    rel_path = rel_path.strip()
    if not rel_path:
        return None
    rows = (
        db.execute(
            select(Wiki)
            .where(Wiki.deleted_at.is_(None), Wiki.obsidian_rel_path == rel_path)
            .order_by(Wiki.updated_at.desc(), Wiki.id.desc())
        )
        .scalars()
        .all()
    )
    return rows[0] if rows else None


def import_or_update_from_vault(
    db: Session,
    *,
    vault_root: Path,
    md_path: Path,
    wiki_id: int | None = None,
    tenant_id: int = 1,
) -> VaultImportResult:
    """Create or commit-update a wiki from one vault markdown file."""
    vault_root = vault_root.resolve()
    md_path = md_path.resolve()
    rel = vault_rel_path(vault_root, md_path)
    base_dir = posixpath.dirname(rel)

    try:
        raw = md_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            raw = md_path.read_text(encoding="gbk")
        except OSError as exc:
            return VaultImportResult(rel_path=rel, wiki_id=None, created=False, updated=False, skipped=False, error=str(exc))

    rewritten, used_assets, missing = _rewrite_vault_refs(raw, vault_root, base_dir)
    display_name = md_path.name

    if wiki_id is None:
        existing = find_wiki_by_obsidian_rel_path(db, rel)
        if existing is not None:
            wiki_id = existing.id
        else:
            wiki = create_wiki_from_markdown(
                db, tenant_id=tenant_id, filename=display_name, content_md=rewritten
            )
            wiki.obsidian_rel_path = rel
            final_md = _apply_asset_prefix(wiki, wiki.current_main_commit.content_md)
            if final_md != wiki.current_main_commit.content_md:
                wiki.current_main_commit.content_md = final_md
                meta = parse_markdown(final_md, fallback_title=wiki.title)
                wiki.title = meta.title or wiki.title
                wiki.word_count = meta.word_count
                wiki.excerpt = meta.excerpt
                wiki.current_main_commit.content_hash = meta.content_hash
                db.flush()
            assets_written = _copy_assets(vault_root, wiki.id, used_assets)
            db.commit()
            return VaultImportResult(
                rel_path=rel,
                wiki_id=wiki.id,
                created=True,
                updated=False,
                skipped=False,
                assets_written=assets_written,
                missing_refs=missing,
            )

    wiki = db.get(Wiki, wiki_id)
    if wiki is None or wiki.deleted_at is not None:
        return VaultImportResult(
            rel_path=rel,
            wiki_id=wiki_id,
            created=False,
            updated=False,
            skipped=False,
            error="mapped wiki not found",
        )

    wiki.obsidian_rel_path = rel

    branch = ensure_main_branch(db, wiki)

    final_md = rewritten.replace(_ASSET_SENTINEL, f"/api/wiki/{wiki.id}/assets")
    head_id = branch.head_commit_id
    head_commit = db.get(WikiCommit, head_id) if head_id else None
    if head_commit is not None and head_commit.content_md == final_md:
        db.commit()
        return VaultImportResult(
            rel_path=rel,
            wiki_id=wiki.id,
            created=False,
            updated=False,
            skipped=True,
            missing_refs=missing,
        )

    commit_on_branch(
        db,
        branch.id,
        content_md=final_md,
        message=f"obsidian sync: {rel}",
        expected_parent_commit_id=head_id,
    )
    assets_written = _copy_assets(vault_root, wiki.id, used_assets)
    db.commit()
    return VaultImportResult(
        rel_path=rel,
        wiki_id=wiki.id,
        created=False,
        updated=True,
        skipped=False,
        assets_written=assets_written,
        missing_refs=missing,
    )
