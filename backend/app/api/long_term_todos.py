"""Long-term todo REST API: CRUD with daily todo cascade."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, get_auth_context
from app.db.session import get_db
from app.schemas.long_term_todo import (
    LongTermTodoCreate,
    LongTermTodoListResponse,
    LongTermTodoSummary,
    LongTermTodoUpdate,
)
from app.services import long_term_todo_service

router = APIRouter()


def _to_summary(db: Session, lt) -> LongTermTodoSummary:
    done, total = long_term_todo_service.long_term_progress(db, lt)
    return LongTermTodoSummary(
        id=lt.id,
        title=lt.title,
        description=lt.description,
        start_date=lt.start_date,
        end_date=lt.end_date,
        remind_time=lt.remind_time,
        schedule_mode=lt.schedule_mode,
        status=lt.status,
        created_at=lt.created_at,
        updated_at=lt.updated_at,
        done_count=done,
        total_count=total,
    )


@router.get("", response_model=LongTermTodoListResponse)
def list_long_term(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> LongTermTodoListResponse:
    rows = long_term_todo_service.list_long_term(db, tenant_id=ctx.tenant_id)
    return LongTermTodoListResponse(
        items=[_to_summary(db, r) for r in rows], total=len(rows)
    )


@router.get("/{long_term_id}", response_model=LongTermTodoSummary)
def get_long_term(
    long_term_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> LongTermTodoSummary:
    lt = long_term_todo_service.get_long_term(
        db, long_term_id, tenant_id=ctx.tenant_id
    )
    if lt is None:
        raise HTTPException(404, detail="长期任务不存在")
    return _to_summary(db, lt)


@router.post("", response_model=LongTermTodoSummary)
def create_long_term(
    payload: LongTermTodoCreate,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> LongTermTodoSummary:
    try:
        lt = long_term_todo_service.create_long_term(
            db,
            tenant_id=ctx.tenant_id,
            title=payload.title,
            description=payload.description,
            start_date=payload.start_date,
            end_date=payload.end_date,
            remind_time=payload.remind_time,
            schedule_mode=payload.schedule_mode,
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    db.refresh(lt)
    return _to_summary(db, lt)


@router.put("/{long_term_id}", response_model=LongTermTodoSummary)
def update_long_term(
    long_term_id: int,
    payload: LongTermTodoUpdate,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> LongTermTodoSummary:
    lt = long_term_todo_service.get_long_term(
        db, long_term_id, tenant_id=ctx.tenant_id
    )
    if lt is None:
        raise HTTPException(404, detail="长期任务不存在")
    try:
        lt = long_term_todo_service.update_long_term(
            db,
            lt,
            title=payload.title,
            description=payload.description,
            start_date=payload.start_date,
            end_date=payload.end_date,
            remind_time=payload.remind_time,
            schedule_mode=payload.schedule_mode,
            status=payload.status,
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    db.refresh(lt)
    return _to_summary(db, lt)


@router.delete("/{long_term_id}")
def delete_long_term(
    long_term_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict:
    lt = long_term_todo_service.get_long_term(
        db, long_term_id, tenant_id=ctx.tenant_id
    )
    if lt is None:
        raise HTTPException(404, detail="长期任务不存在")
    long_term_todo_service.delete_long_term(db, lt, drop_tasks=True)
    db.commit()
    return {"ok": True}
