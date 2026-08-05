"""Branch / commit / merge endpoints (PRD §6.1.2).

Mounted under ``/api/wiki`` so URLs read naturally:
  POST   /api/wiki/{wiki_id}/branches             create branch
  GET    /api/wiki/{wiki_id}/branches             list branches (with content shortcut)
  GET    /api/wiki/branches/{branch_id}           branch + HEAD content
  PUT    /api/wiki/branches/{branch_id}/commit    new commit on branch
  GET    /api/wiki/branches/{branch_id}/commits   recent commit chain
  DELETE /api/wiki/branches/{branch_id}           delete branch (not 'main')
  GET    /api/wiki/branches/{branch_id}/merge-preview     3-way plan vs main
  POST   /api/wiki/branches/{branch_id}/merge             execute merge

We deliberately keep merge orchestration on the source branch's URL — the
target is always ``main`` in the MVP.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.wiki import (
    BranchContent,
    BranchSummary,
    CommitRequest,
    CommitSummary,
    CreateBranchRequest,
    HunkSchema,
    MergePreview,
    MergeRequest,
)
from app.services import branch_service
from app.services.branch_service import BranchError

router = APIRouter()


def _content(db: Session, branch) -> BranchContent:
    return BranchContent(
        branch=BranchSummary.model_validate(branch),
        head_commit_id=branch.head_commit_id,
        content_md=branch_service.head_content(branch, db),
        is_main=branch.name == "main",
    )


# --- Branch CRUD ----------------------------------------------------------


@router.post("/{wiki_id}/branches", response_model=BranchContent, status_code=201)
def create_branch_endpoint(
    wiki_id: int, payload: CreateBranchRequest, db: Session = Depends(get_db)
) -> BranchContent:
    try:
        b = branch_service.create_branch(
            db, wiki_id, name=payload.name, base_branch_id=payload.base_branch_id
        )
    except BranchError as exc:
        raise HTTPException(exc.http_status, detail=str(exc)) from exc
    db.commit()
    return _content(db, b)


@router.get("/{wiki_id}/branches", response_model=list[BranchSummary])
def list_branches_endpoint(
    wiki_id: int, db: Session = Depends(get_db)
) -> list[BranchSummary]:
    return [
        BranchSummary.model_validate(b) for b in branch_service.list_branches(db, wiki_id)
    ]


@router.get("/branches/{branch_id}", response_model=BranchContent)
def get_branch_endpoint(
    branch_id: int, db: Session = Depends(get_db)
) -> BranchContent:
    try:
        b = branch_service.get_branch(db, branch_id)
    except BranchError as exc:
        raise HTTPException(exc.http_status, detail=str(exc)) from exc
    return _content(db, b)


@router.delete("/branches/{branch_id}", status_code=204)
def delete_branch_endpoint(
    branch_id: int, db: Session = Depends(get_db)
) -> None:
    try:
        branch_service.delete_branch(db, branch_id)
    except BranchError as exc:
        raise HTTPException(exc.http_status, detail=str(exc)) from exc
    db.commit()


# --- Commits --------------------------------------------------------------


@router.put("/branches/{branch_id}/commit", response_model=BranchContent)
def commit_branch_endpoint(
    branch_id: int, payload: CommitRequest, db: Session = Depends(get_db)
) -> BranchContent:
    try:
        branch_service.commit_on_branch(
            db,
            branch_id,
            content_md=payload.content_md,
            message=payload.message,
            expected_parent_commit_id=payload.expected_parent_commit_id,
        )
    except BranchError as exc:
        raise HTTPException(exc.http_status, detail=str(exc)) from exc
    db.commit()
    branch = branch_service.get_branch(db, branch_id)
    return _content(db, branch)


@router.get("/branches/{branch_id}/commits", response_model=list[CommitSummary])
def list_commits_endpoint(
    branch_id: int, limit: int = 50, db: Session = Depends(get_db)
) -> list[CommitSummary]:
    try:
        commits = branch_service.list_commits(db, branch_id, limit=max(1, min(200, limit)))
    except BranchError as exc:
        raise HTTPException(exc.http_status, detail=str(exc)) from exc
    return [CommitSummary.model_validate(c) for c in commits]


# --- Merge ----------------------------------------------------------------


@router.get("/branches/{branch_id}/merge-preview", response_model=MergePreview)
def merge_preview_endpoint(
    branch_id: int, db: Session = Depends(get_db)
) -> MergePreview:
    try:
        plan, main, src, lca_id = branch_service.diff_against_main(db, branch_id)
    except BranchError as exc:
        raise HTTPException(exc.http_status, detail=str(exc)) from exc
    return MergePreview(
        source_branch_id=src.id,
        source_branch_name=src.name,
        target_branch_id=main.id,
        target_branch_name=main.name,
        base_commit_id=lca_id,
        main_head_commit_id=main.head_commit_id,
        source_head_commit_id=src.head_commit_id,
        base_text=plan.base,
        ours_text=plan.ours,
        theirs_text=plan.theirs,
        hunks=[
            HunkSchema(
                id=h.id,
                kind=h.kind,
                base_start=h.base_start,
                base_end=h.base_end,
                base_text=h.base_text,
                ours_text=h.ours_text,
                theirs_text=h.theirs_text,
                resolved=h.resolved,
            )
            for h in plan.hunks
        ],
        auto_merged=plan.auto_merged,
        has_conflict=plan.has_conflict,
        conflict_count=plan.conflict_count,
    )


@router.post("/branches/{branch_id}/merge", response_model=BranchContent)
def merge_branch_endpoint(
    branch_id: int, payload: MergeRequest, db: Session = Depends(get_db)
) -> BranchContent:
    try:
        branch_service.merge_into_main(
            db,
            branch_id,
            resolutions=payload.resolutions,
            expected_main_head_id=payload.expected_main_head_id,
            message=payload.message,
        )
    except BranchError as exc:
        raise HTTPException(exc.http_status, detail=str(exc)) from exc
    db.commit()
    # Return the *main* branch state (consumer wants the merged content)
    main = next(
        b
        for b in branch_service.list_branches(
            db, branch_service.get_branch(db, branch_id).wiki_id
        )
        if b.name == "main"
    )
    return _content(db, main)
