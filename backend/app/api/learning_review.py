"""Spaced-review schedule configuration API (separate from question push)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, get_auth_context
from app.db.session import get_db
from app.schemas.learning_note import (
    ReviewScheduleRead,
    ReviewScheduleUpdate,
    ReviewTriggerResponse,
)
from app.services.learning_review_service import (
    execute_review_push,
    get_or_create_schedule,
    update_schedule,
)

router = APIRouter()


def _to_read(row) -> ReviewScheduleRead:
    return ReviewScheduleRead(
        enabled=row.enabled,
        timezone=row.timezone,
        push_times=list(row.push_times or []),
        frequency=row.frequency,
        weekdays=list(row.weekdays or []),
        intervals_days=list(row.intervals_days or []),
        max_notes_per_push=row.max_notes_per_push,
        recall_mode=row.recall_mode,
        feishu_enabled=row.feishu_enabled,
        last_run_slot=row.last_run_slot,
        last_run_at=row.last_run_at,
        last_error=row.last_error,
    )


@router.get("", response_model=ReviewScheduleRead)
def get_review_schedule(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ReviewScheduleRead:
    row = get_or_create_schedule(db, tenant_id=ctx.tenant_id)
    db.commit()
    return _to_read(row)


@router.put("", response_model=ReviewScheduleRead)
def put_review_schedule(
    payload: ReviewScheduleUpdate,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ReviewScheduleRead:
    try:
        row = update_schedule(
            db,
            tenant_id=ctx.tenant_id,
            **payload.model_dump(exclude_unset=True),
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    return _to_read(row)


@router.post("/trigger", response_model=ReviewTriggerResponse)
async def trigger_review_now(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ReviewTriggerResponse:
    row = get_or_create_schedule(db, tenant_id=ctx.tenant_id)
    try:
        n_count, r_count, msg = await execute_review_push(db, row, manual=True)
        db.commit()
    except RuntimeError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, detail=str(exc)) from exc
    return ReviewTriggerResponse(
        ok=True, message=msg, note_count=n_count, recipient_count=r_count
    )
