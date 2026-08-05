"""Wiki branching + commits + 3-way merge orchestration (PRD §6.1.2).

This service is purposely thin — the heavy lifting (line-based diff, conflict
detection) lives in ``merge.py`` so it can be unit-tested without DB.

Concurrency model: single-user MVP, all writes serialize on the SQLite file.
We still defend against stale clients by *requiring* the caller to send the
parent commit id when committing on a branch — if the branch HEAD has moved
since the client loaded the page, the API surfaces a 409 and the user must
refresh.
"""
from __future__ import annotations

import hashlib
import logging
import re
from collections import deque

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Wiki, WikiBranch, WikiCommit
from app.services import merge as merge_mod
from app.services.markdown_parser import parse_markdown

log = logging.getLogger(__name__)

_BRANCH_NAME_RE = re.compile(r"^[A-Za-z0-9_\-./]{1,120}$")


class BranchError(Exception):
    """Domain error → mapped to HTTP 4xx by the router."""

    def __init__(self, message: str, *, code: str = "branch_error", http_status: int = 400):
        super().__init__(message)
        self.code = code
        self.http_status = http_status


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------


def list_branches(db: Session, wiki_id: int) -> list[WikiBranch]:
    return list(
        db.execute(
            select(WikiBranch)
            .where(WikiBranch.wiki_id == wiki_id)
            .order_by(WikiBranch.id.asc())
        )
        .scalars()
        .all()
    )


def get_main_branch(db: Session, wiki_id: int) -> WikiBranch | None:
    return db.execute(
        select(WikiBranch).where(WikiBranch.wiki_id == wiki_id, WikiBranch.name == "main")
    ).scalar_one_or_none()


def ensure_main_branch(db: Session, wiki: Wiki) -> WikiBranch:
    """Ensure wiki has a ``main`` branch (empty HEAD allowed). Used after legacy imports."""
    branch = get_main_branch(db, wiki.id)
    if branch is not None:
        return branch
    branch = WikiBranch(wiki_id=wiki.id, name="main", head_commit_id=None)
    db.add(branch)
    db.flush()
    log.warning("created missing main branch for wiki #%s (%s)", wiki.id, wiki.title)
    return branch


def repair_wikis_missing_main_branch(db: Session, *, tenant_id: int | None = None) -> int:
    """Create ``main`` for wikis that exist without any branch. Returns repair count."""
    q = select(Wiki).where(Wiki.deleted_at.is_(None))
    if tenant_id is not None:
        q = q.where(Wiki.tenant_id == tenant_id)
    repaired = 0
    for wiki in db.execute(q).scalars().all():
        if get_main_branch(db, wiki.id) is not None:
            continue
        ensure_main_branch(db, wiki)
        repaired += 1
    if repaired:
        db.flush()
    return repaired


def get_branch(db: Session, branch_id: int) -> WikiBranch:
    b = db.get(WikiBranch, branch_id)
    if b is None:
        raise BranchError("branch not found", code="not_found", http_status=404)
    return b


def get_commit(db: Session, commit_id: int) -> WikiCommit:
    c = db.get(WikiCommit, commit_id)
    if c is None:
        raise BranchError("commit not found", code="not_found", http_status=404)
    return c


def list_commits(db: Session, branch_id: int, *, limit: int = 50) -> list[WikiCommit]:
    """Walk the commit chain backwards from branch HEAD up to ``limit`` entries.

    We return parents-first along a single chain (we don't model merges with
    multiple parents in the MVP — a merge writes a single new commit whose
    parent is the previous branch HEAD).
    """
    branch = get_branch(db, branch_id)
    out: list[WikiCommit] = []
    cur_id = branch.head_commit_id
    seen: set[int] = set()
    while cur_id is not None and len(out) < limit:
        if cur_id in seen:
            break
        seen.add(cur_id)
        c = db.get(WikiCommit, cur_id)
        if c is None:
            break
        out.append(c)
        cur_id = c.parent_commit_id
    return out


def head_content(branch: WikiBranch, db: Session) -> str:
    if branch.head_commit_id is None:
        return ""
    c = db.get(WikiCommit, branch.head_commit_id)
    return c.content_md if c else ""


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def create_branch(
    db: Session, wiki_id: int, *, name: str, base_branch_id: int | None
) -> WikiBranch:
    """Create a new branch starting at ``base_branch_id`` HEAD (or main HEAD).

    The new branch's HEAD points at the same commit as the base — there is no
    duplicated commit (consistent with how git creates a "ref"). The first
    edit on the new branch creates a commit whose parent is that shared commit.
    """
    wiki = db.get(Wiki, wiki_id)
    if wiki is None or wiki.deleted_at is not None:
        raise BranchError("wiki not found", code="not_found", http_status=404)
    if not _BRANCH_NAME_RE.match(name):
        raise BranchError(
            "branch name must match [A-Za-z0-9_-./], length 1..120",
            code="invalid_name",
        )
    if name == "main":
        raise BranchError("cannot create another 'main' branch", code="reserved_name")
    existing = db.execute(
        select(WikiBranch).where(
            WikiBranch.wiki_id == wiki_id, WikiBranch.name == name
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise BranchError(f"branch '{name}' already exists", code="duplicate", http_status=409)

    base: WikiBranch
    if base_branch_id is None:
        main = db.execute(
            select(WikiBranch).where(
                WikiBranch.wiki_id == wiki_id, WikiBranch.name == "main"
            )
        ).scalar_one_or_none()
        if main is None:
            raise BranchError("main branch missing", code="invalid_state", http_status=500)
        base = main
    else:
        base = get_branch(db, base_branch_id)
        if base.wiki_id != wiki_id:
            raise BranchError("base branch belongs to a different wiki", code="cross_wiki")

    branch = WikiBranch(
        wiki_id=wiki_id, name=name, head_commit_id=base.head_commit_id
    )
    db.add(branch)
    db.flush()
    return branch


def commit_on_branch(
    db: Session,
    branch_id: int,
    *,
    content_md: str,
    message: str,
    expected_parent_commit_id: int | None,
) -> WikiCommit:
    """Append a new commit to ``branch_id`` and update HEAD.

    ``expected_parent_commit_id`` is the commit id the client believed was
    HEAD when it started editing. If HEAD has advanced (someone else
    committed; mostly relevant in concurrent tabs), we raise a 409.
    No-op if content is identical to current HEAD content.
    """
    branch = get_branch(db, branch_id)
    if branch.head_commit_id != expected_parent_commit_id:
        raise BranchError(
            f"branch HEAD has moved to commit#{branch.head_commit_id}; "
            "请刷新后再提交",
            code="stale_parent",
            http_status=409,
        )
    current = (
        db.get(WikiCommit, branch.head_commit_id)
        if branch.head_commit_id is not None
        else None
    )
    if current is not None and current.content_md == content_md:
        # Idempotent — return the existing HEAD instead of creating a noop.
        return current

    commit = WikiCommit(
        wiki_id=branch.wiki_id,
        branch_id=branch.id,
        parent_commit_id=branch.head_commit_id,
        message=message or "edit",
        content_md=content_md,
        content_hash=_hash(content_md),
    )
    db.add(commit)
    db.flush()
    branch.head_commit_id = commit.id

    # If this is the main branch, also update Wiki cached pointers + meta
    if branch.name == "main":
        wiki = db.get(Wiki, branch.wiki_id)
        if wiki is not None:
            wiki.current_main_commit_id = commit.id
            meta = parse_markdown(content_md, fallback_title=wiki.title)
            wiki.title = meta.title or wiki.title
            wiki.word_count = meta.word_count
            wiki.excerpt = meta.excerpt
    db.flush()
    return commit


def delete_branch(db: Session, branch_id: int) -> None:
    branch = get_branch(db, branch_id)
    if branch.name == "main":
        raise BranchError("cannot delete main branch", code="protected")
    db.delete(branch)
    db.flush()


# ---------------------------------------------------------------------------
# History helpers (common ancestor)
# ---------------------------------------------------------------------------


def _ancestors(db: Session, commit_id: int | None) -> list[int]:
    out: list[int] = []
    cur = commit_id
    seen: set[int] = set()
    while cur is not None and cur not in seen:
        seen.add(cur)
        out.append(cur)
        c = db.get(WikiCommit, cur)
        if c is None:
            break
        cur = c.parent_commit_id
    return out


def common_ancestor(db: Session, a_commit_id: int | None, b_commit_id: int | None) -> int | None:
    """Lowest common ancestor along single-parent chains (BFS over both)."""
    if a_commit_id is None or b_commit_id is None:
        return None
    a_set = set(_ancestors(db, a_commit_id))
    queue = deque([b_commit_id])
    seen: set[int] = set()
    while queue:
        cur = queue.popleft()
        if cur in seen:
            continue
        seen.add(cur)
        if cur in a_set:
            return cur
        c = db.get(WikiCommit, cur)
        if c is not None and c.parent_commit_id is not None:
            queue.append(c.parent_commit_id)
    return None


# ---------------------------------------------------------------------------
# Diff & merge
# ---------------------------------------------------------------------------


def diff_against_main(
    db: Session, branch_id: int
) -> tuple[merge_mod.MergePlan, WikiBranch, WikiBranch, int | None]:
    """Compute a 3-way plan: base = LCA(main HEAD, branch HEAD)."""
    src = get_branch(db, branch_id)
    main = db.execute(
        select(WikiBranch).where(
            WikiBranch.wiki_id == src.wiki_id, WikiBranch.name == "main"
        )
    ).scalar_one_or_none()
    if main is None:
        raise BranchError("main branch missing", code="invalid_state", http_status=500)
    if src.id == main.id:
        raise BranchError("cannot diff main against itself", code="invalid_target")

    lca_id = common_ancestor(db, main.head_commit_id, src.head_commit_id)
    base_text = (
        db.get(WikiCommit, lca_id).content_md
        if lca_id is not None
        else ""
    )
    main_text = head_content(main, db)
    src_text = head_content(src, db)

    plan = merge_mod.merge_three_way(base=base_text, ours=main_text, theirs=src_text)
    return plan, main, src, lca_id


def merge_into_main(
    db: Session,
    branch_id: int,
    *,
    resolutions: dict[int, str] | None,
    expected_main_head_id: int | None,
    message: str,
) -> WikiCommit:
    """Merge ``branch_id`` into main.

    Strategy:
      1. Compute the merge plan.
      2. If clean / fast-forward, persist a single new main commit (or
         reuse the source HEAD if main is an ancestor of source).
      3. If conflicts: caller MUST supply ``resolutions`` keyed by hunk id.
         We re-compute the plan and apply resolutions deterministically.
      4. CAS guard: ``expected_main_head_id`` must match current main HEAD.
    """
    plan, main, src, _lca = diff_against_main(db, branch_id)
    if main.head_commit_id != expected_main_head_id:
        raise BranchError(
            f"main HEAD moved to commit#{main.head_commit_id}; 请刷新合并预览",
            code="stale_main",
            http_status=409,
        )

    if plan.has_conflict:
        if resolutions is None:
            raise BranchError(
                "merge has conflicts; supply 'resolutions' for each conflict hunk",
                code="needs_resolution",
                http_status=409,
            )
        try:
            merged_text = merge_mod.apply_resolutions(plan, resolutions)
        except ValueError as exc:
            raise BranchError(str(exc), code="needs_resolution", http_status=409) from exc
    else:
        merged_text = plan.auto_merged or plan.theirs  # plan ensures one is set

    # Idempotent: if merge result equals current main, no new commit is created.
    cur_main = (
        db.get(WikiCommit, main.head_commit_id)
        if main.head_commit_id is not None
        else None
    )
    if cur_main is not None and cur_main.content_md == merged_text:
        return cur_main

    return commit_on_branch(
        db,
        main.id,
        content_md=merged_text,
        message=message or f"merge branch '{src.name}' into main",
        expected_parent_commit_id=main.head_commit_id,
    )
