"""Scheduled question push configuration API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, get_auth_context
from app.db.session import get_db
from app.schemas.push_schedule import PushScheduleRead, PushScheduleUpdate, PushTriggerResponse
from app.services.push_schedule_service import (
    execute_push,
    get_or_create_schedule,
    update_schedule,
)

router = APIRouter()


def _to_read(row) -> PushScheduleRead:
    return PushScheduleRead(
        enabled=row.enabled,
        timezone=row.timezone,
        push_times=list(row.push_times or []),
        frequency=row.frequency,
        weekdays=list(row.weekdays or []),
        limit=row.limit,
        mode=row.mode,
        difficulties=list(row.difficulties or []),
        qtypes=list(row.qtypes or []),
        tag_ids=list(row.tag_ids or []),
        tag_mode=row.tag_mode,
        source_kinds=list(getattr(row, "source_kinds", None) or []),
        feishu_enabled=row.feishu_enabled,
        last_run_slot=row.last_run_slot,
        last_run_at=row.last_run_at,
        last_error=row.last_error,
    )


@router.get("", response_model=PushScheduleRead)
def get_push_schedule(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> PushScheduleRead:
    row = get_or_create_schedule(db, tenant_id=ctx.tenant_id)
    return _to_read(row)


@router.put("", response_model=PushScheduleRead)
def put_push_schedule(
    payload: PushScheduleUpdate,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> PushScheduleRead:
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


@router.post("/trigger", response_model=PushTriggerResponse)
async def trigger_push_now(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> PushTriggerResponse:
    row = get_or_create_schedule(db, tenant_id=ctx.tenant_id)
    try:
        q_count, r_count, msg = await execute_push(db, row, manual=True)
        db.commit()
    except RuntimeError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, detail=str(exc)) from exc
    return PushTriggerResponse(
        ok=True, message=msg, question_count=q_count, recipient_count=r_count
    )
