"""Wiki domain service: create from upload, list, fetch, soft-delete.

Branching/merge operations live in a dedicated service in a follow-up iteration.
A single .md upload always creates:
  - one Wiki row
  - one ``main`` WikiBranch
  - one initial WikiCommit on that branch
  - back-links current_main_commit_id and head_commit_id
"""
from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import Wiki, WikiBranch, WikiCommit
from app.services.markdown_parser import parse_markdown


def create_wiki_from_markdown(
    db: Session,
    *,
    tenant_id: int,
    filename: str,
    content_md: str,
    collection_id: int | None = None,
) -> Wiki:
    """Create Wiki + main branch + initial commit in one transaction."""
    fallback_title = filename.rsplit(".", 1)[0]
    meta = parse_markdown(content_md, fallback_title=fallback_title)

    wiki = Wiki(
        tenant_id=tenant_id,
        title=meta.title,
        collection_id=collection_id,
        word_count=meta.word_count,
        excerpt=meta.excerpt,
    )
    db.add(wiki)
    db.flush()  # need wiki.id

    branch = WikiBranch(wiki_id=wiki.id, name="main")
    db.add(branch)
    db.flush()

    commit = WikiCommit(
        wiki_id=wiki.id,
        branch_id=branch.id,
        parent_commit_id=None,
        message=f"initial commit from {filename}",
        content_md=content_md,
        content_hash=meta.content_hash,
    )
    db.add(commit)
    db.flush()

    branch.head_commit_id = commit.id
    wiki.current_main_commit_id = commit.id
    db.flush()

    return wiki


def list_wikis(
    db: Session,
    *,
    tenant_id: int,
    q: str | None = None,
    collection_id: int | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Wiki], int]:
    stmt = select(Wiki).where(Wiki.deleted_at.is_(None), Wiki.tenant_id == tenant_id)
    if collection_id is not None:
        stmt = stmt.where(Wiki.collection_id == collection_id)
    if q:
        like = f"%{q}%"
        # Search title or commit content of current main commit
        stmt = stmt.outerjoin(WikiCommit, Wiki.current_main_commit_id == WikiCommit.id).where(
            or_(Wiki.title.ilike(like), WikiCommit.content_md.ilike(like))
        )
    stmt = stmt.order_by(Wiki.updated_at.desc())

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_count = db.execute(count_stmt).scalar_one()

    rows = db.execute(stmt.limit(limit).offset(offset)).scalars().unique().all()
    return list(rows), int(total_count)


def get_wiki(db: Session, wiki_id: int, *, tenant_id: int) -> Wiki | None:
    stmt = (
        select(Wiki)
        .where(Wiki.id == wiki_id, Wiki.deleted_at.is_(None), Wiki.tenant_id == tenant_id)
        .options(selectinload(Wiki.current_main_commit), selectinload(Wiki.branches))
    )
    return db.execute(stmt).scalar_one_or_none()


def soft_delete_wiki(db: Session, wiki_id: int, *, tenant_id: int) -> bool:
    wiki = get_wiki(db, wiki_id, tenant_id=tenant_id)
    if wiki is None:
        return False
    from datetime import datetime

    wiki.deleted_at = datetime.utcnow()
    db.flush()
    return True


def bulk_create_from_uploads(
    db: Session, files: Iterable[tuple[str, str]], *, tenant_id: int
) -> list[dict]:
    """Per-file outcome list, preserving input order.

    Each item: ``{"filename": str, "wiki": Wiki | None, "error": str | None}``.
    """
    out: list[dict] = []
    for filename, content in files:
        try:
            wiki = create_wiki_from_markdown(
                db, tenant_id=tenant_id, filename=filename, content_md=content
            )
            out.append({"filename": filename, "wiki": wiki, "error": None})
        except Exception as exc:  # noqa: BLE001
            out.append({"filename": filename, "wiki": None, "error": str(exc)})
    return out
