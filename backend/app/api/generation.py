"""Question generation + candidate preview + commit (PRD §6.3)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, get_auth_context
from app.db.session import get_db
from app.models import Wiki
from app.schemas.question import (
    BulkCommitItemResult,
    BulkCommitRequest,
    BulkCommitResponse,
    BulkGenerateItemResult,
    BulkGenerateRequest,
    BulkGenerateResponse,
    CandidateBatchSummary,
    CandidateSummary,
    CandidateUpdate,
    CommitRequest,
    CommitResponse,
    GenerateRequest,
    GenerateResponse,
)
from app.services.generation_service import (
    bulk_commit_batches,
    commit_batch,
    discard_candidate,
    generate_for_wiki,
    list_candidates,
    update_candidate,
)
from app.services.llm import LLMError

log = logging.getLogger(__name__)

router = APIRouter()


# Must be registered before ``/wiki/{wiki_id}/...`` or ``bulk`` is parsed as wiki_id.
@router.post("/wiki/bulk/generate-questions", response_model=BulkGenerateResponse)
async def bulk_generate_for_wikis(
    payload: BulkGenerateRequest,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> BulkGenerateResponse:
    """Generate interview questions for multiple wikis sequentially."""
    results: list[BulkGenerateItemResult] = []
    success = 0
    for wiki_id in payload.wiki_ids:
        wiki = db.get(Wiki, wiki_id)
        if (
            wiki is None
            or wiki.deleted_at is not None
            or wiki.tenant_id != ctx.tenant_id
        ):
            results.append(
                BulkGenerateItemResult(
                    wiki_id=wiki_id,
                    wiki_title="(未找到)",
                    success=False,
                    error="wiki not found",
                )
            )
            continue
        try:
            result = await generate_for_wiki(
                db,
                wiki,
                n=payload.n,
                max_n=payload.max_n,
                override_model_id=payload.model_id,
                replace_existing=payload.replace_existing,
            )
            db.commit()
            success += 1
            results.append(
                BulkGenerateItemResult(
                    wiki_id=wiki.id,
                    wiki_title=wiki.title,
                    success=True,
                    batch_id=result.batch_id,
                    raw_count=result.raw_count,
                    replaced_bank_questions=result.replaced_bank_questions,
                    replaced_candidates=result.replaced_candidates,
                )
            )
        except (LLMError, RuntimeError) as exc:
            db.rollback()
            err = str(exc)
            log.warning(
                "bulk generate failed wiki_id=%s title=%r: %s",
                wiki.id,
                wiki.title,
                err,
            )
            results.append(
                BulkGenerateItemResult(
                    wiki_id=wiki.id,
                    wiki_title=wiki.title,
                    success=False,
                    error=err,
                )
            )
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            err = f"internal error: {exc}"
            log.exception(
                "bulk generate internal error wiki_id=%s title=%r",
                wiki.id,
                wiki.title,
            )
            results.append(
                BulkGenerateItemResult(
                    wiki_id=wiki.id,
                    wiki_title=wiki.title,
                    success=False,
                    error=err,
                )
            )
    return BulkGenerateResponse(
        results=results,
        success_count=success,
        fail_count=len(results) - success,
    )


@router.post("/wiki/{wiki_id}/generate-questions", response_model=GenerateResponse)
async def generate_for_wiki_endpoint(
    wiki_id: int,
    payload: GenerateRequest,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> GenerateResponse:
    wiki = db.get(Wiki, wiki_id)
    if (
        wiki is None
        or wiki.deleted_at is not None
        or wiki.tenant_id != ctx.tenant_id
    ):
        raise HTTPException(404, detail="wiki not found")
    try:
        result = await generate_for_wiki(
            db,
            wiki,
            n=payload.n,
            max_n=payload.max_n,
            override_model_id=payload.model_id,
            replace_existing=payload.replace_existing,
        )
    except LLMError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    db.commit()
    return GenerateResponse(
        batch_id=result.batch_id,
        raw_count=result.raw_count,
        candidates=[CandidateSummary.model_validate(c) for c in result.candidates],
        replaced_bank_questions=result.replaced_bank_questions,
        replaced_candidates=result.replaced_candidates,
    )


@router.get("/candidates/batches", response_model=list[CandidateBatchSummary])
def list_candidate_batches_endpoint(
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
    limit: int = 100,
) -> list[CandidateBatchSummary]:
    from app.services.wiki_generation_service import list_candidate_batches

    rows = list_candidate_batches(db, tenant_id=ctx.tenant_id, limit=min(limit, 200))
    return [CandidateBatchSummary.model_validate(r) for r in rows]


@router.post("/candidates/batches/bulk-commit", response_model=BulkCommitResponse)
def bulk_commit_batches_endpoint(
    payload: BulkCommitRequest,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> BulkCommitResponse:
    try:
        rows = bulk_commit_batches(
            db,
            payload.batch_ids,
            tenant_id=ctx.tenant_id,
            target_collection_id=payload.target_collection_id,
            pick_all=payload.pick_all,
        )
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    db.commit()
    results = [
        BulkCommitItemResult(batch_id=bid, saved=s, remaining=r) for bid, s, r in rows
    ]
    return BulkCommitResponse(
        total_saved=sum(r.saved for r in results),
        total_remaining=sum(r.remaining for r in results),
        batches_done=len(results),
        results=results,
    )


@router.get("/candidates/{batch_id}", response_model=list[CandidateSummary])
def list_candidates_endpoint(
    batch_id: str,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> list[CandidateSummary]:
    rows = list_candidates(db, batch_id, tenant_id=ctx.tenant_id)
    return [CandidateSummary.model_validate(r) for r in rows]


@router.patch("/candidates/{cand_id}", response_model=CandidateSummary)
def update_candidate_endpoint(
    cand_id: int,
    payload: CandidateUpdate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> CandidateSummary:
    cand = update_candidate(
        db,
        cand_id,
        tenant_id=ctx.tenant_id,
        payload_json=payload.payload_json,
        picked=payload.picked,
    )
    if cand is None:
        raise HTTPException(404, detail="candidate not found")
    db.commit()
    return CandidateSummary.model_validate(cand)


@router.delete("/candidates/{cand_id}", status_code=status.HTTP_204_NO_CONTENT)
def discard_candidate_endpoint(
    cand_id: int,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> None:
    if not discard_candidate(db, cand_id, tenant_id=ctx.tenant_id):
        raise HTTPException(404, detail="candidate not found")
    db.commit()


@router.post("/candidates/{batch_id}/commit", response_model=CommitResponse)
def commit_batch_endpoint(
    batch_id: str,
    payload: CommitRequest,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> CommitResponse:
    try:
        saved, remaining = commit_batch(
            db,
            batch_id,
            tenant_id=ctx.tenant_id,
            target_collection_id=payload.target_collection_id,
            pick_all=payload.pick_all,
        )
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    db.commit()
    return CommitResponse(saved=saved, remaining=remaining)
