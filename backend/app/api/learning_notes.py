"""Learning notes API: submit (LLM structure), list, edit, review, master."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, get_auth_context
from app.db.session import get_db
from app.schemas.learning_note import (
    LearningNoteCreate,
    LearningNoteDetail,
    LearningNoteListResponse,
    LearningNoteSummary,
    LearningNoteUpdate,
)
from app.services.learning_note_service import (
    create_note,
    delete_note,
    get_note,
    list_notes,
    mark_mastered,
    mark_reviewed,
    update_note,
)
from app.services.llm import LLMError

log = logging.getLogger(__name__)

router = APIRouter()


@router.post("", response_model=LearningNoteDetail)
async def create_learning_note(
    payload: LearningNoteCreate,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> LearningNoteDetail:
    try:
        note = await create_note(
            db,
            raw_input=payload.raw_input,
            tenant_id=ctx.tenant_id,
            channel="web",
            extra_tags=payload.extra_tags,
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    db.refresh(note)
    return LearningNoteDetail.model_validate(note)


@router.get("", response_model=LearningNoteListResponse)
def list_learning_notes(
    only_due: bool = Query(False),
    include_mastered: bool = Query(True),
    tag_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> LearningNoteListResponse:
    rows, total, due_today = list_notes(
        db,
        tenant_id=ctx.tenant_id,
        only_due=only_due,
        include_mastered=include_mastered,
        tag_id=tag_id,
        limit=limit,
        offset=offset,
    )
    return LearningNoteListResponse(
        items=[LearningNoteSummary.model_validate(r) for r in rows],
        total=total,
        due_today=due_today,
    )


@router.get("/{note_id}", response_model=LearningNoteDetail)
def get_learning_note(
    note_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> LearningNoteDetail:
    note = get_note(db, note_id, tenant_id=ctx.tenant_id)
    if note is None:
        raise HTTPException(404, detail="learning note not found")
    return LearningNoteDetail.model_validate(note)


@router.patch("/{note_id}", response_model=LearningNoteDetail)
def update_learning_note(
    note_id: int,
    payload: LearningNoteUpdate,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> LearningNoteDetail:
    note = get_note(db, note_id, tenant_id=ctx.tenant_id)
    if note is None:
        raise HTTPException(404, detail="learning note not found")
    update_note(
        db,
        note,
        tenant_id=ctx.tenant_id,
        **payload.model_dump(exclude_unset=True),
    )
    db.commit()
    db.refresh(note)
    return LearningNoteDetail.model_validate(note)


@router.delete("/{note_id}", status_code=204)
def delete_learning_note(
    note_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> None:
    note = get_note(db, note_id, tenant_id=ctx.tenant_id)
    if note is None:
        raise HTTPException(404, detail="learning note not found")
    delete_note(db, note)
    db.commit()


@router.post("/{note_id}/reviewed", response_model=LearningNoteDetail)
def review_learning_note(
    note_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> LearningNoteDetail:
    note = get_note(db, note_id, tenant_id=ctx.tenant_id)
    if note is None:
        raise HTTPException(404, detail="learning note not found")
    mark_reviewed(db, note)
    db.commit()
    db.refresh(note)
    return LearningNoteDetail.model_validate(note)


@router.post("/{note_id}/master", response_model=LearningNoteDetail)
def master_learning_note(
    note_id: int,
    mastered: bool = Query(True),
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> LearningNoteDetail:
    note = get_note(db, note_id, tenant_id=ctx.tenant_id)
    if note is None:
        raise HTTPException(404, detail="learning note not found")
    mark_mastered(db, note, mastered)
    db.commit()
    db.refresh(note)
    return LearningNoteDetail.model_validate(note)
