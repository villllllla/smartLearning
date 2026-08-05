"""Todo REST API: list/create, calendar heatmap, snooze, daily-check schedule."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, get_auth_context
from app.db.session import get_db
from app.schemas.todo import (
    TodoCalendarDay,
    TodoCalendarResponse,
    TodoCreate,
    TodoDetail,
    TodoDirectCreate,
    TodoListResponse,
    TodoProgressRequest,
    TodoSnoozeRequest,
    TodoSummary,
    TodoUpdate,
)
from app.schemas.todo_check import (
    TodoCheckRead,
    TodoCheckTriggerResponse,
    TodoCheckUpdate,
)
from app.services import todo_check_service
from app.services.llm import LLMError
from app.services.todo_service import (
    calendar_counts,
    cancel_todo,
    create_todo_direct,
    delete_todo,
    get_todo,
    handle_todo_message,
    list_todos,
    mark_done,
    restore_todo,
    set_todo_progress,
    snooze_todo,
    unsnooze_todo,
    update_todo,
)

router = APIRouter()


@router.get("", response_model=TodoListResponse)
def list_todo_items(
    status: str | None = Query(None),
    day: date | None = Query(None, description="按计划日期(plan_date)过滤"),
    plan_id: int | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> TodoListResponse:
    statuses = [status] if status else None
    rows, total = list_todos(
        db,
        tenant_id=ctx.tenant_id,
        statuses=statuses,
        plan_date=day,
        plan_id=plan_id,
        limit=limit,
        offset=offset,
    )
    return TodoListResponse(
        items=[TodoSummary.model_validate(r) for r in rows], total=total
    )


@router.get("/calendar", response_model=TodoCalendarResponse)
def todo_calendar(
    start: date = Query(...),
    end: date = Query(...),
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> TodoCalendarResponse:
    if end < start:
        raise HTTPException(400, detail="end 不能早于 start")
    days = calendar_counts(db, tenant_id=ctx.tenant_id, start=start, end=end)
    return TodoCalendarResponse(
        days=[TodoCalendarDay(**d) for d in days],
        start=start.isoformat(),
        end=end.isoformat(),
    )


@router.get("/check", response_model=TodoCheckRead)
def get_check_schedule(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> TodoCheckRead:
    row = todo_check_service.get_or_create_schedule(db, tenant_id=ctx.tenant_id)
    db.commit()
    return TodoCheckRead.model_validate(row)


@router.put("/check", response_model=TodoCheckRead)
def update_check_schedule(
    payload: TodoCheckUpdate,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> TodoCheckRead:
    try:
        row = todo_check_service.update_schedule(
            db, tenant_id=ctx.tenant_id, **payload.model_dump(exclude_none=True)
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    db.refresh(row)
    return TodoCheckRead.model_validate(row)


@router.post("/check/trigger", response_model=TodoCheckTriggerResponse)
async def trigger_check_now(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> TodoCheckTriggerResponse:
    row = todo_check_service.get_or_create_schedule(db, tenant_id=ctx.tenant_id)
    try:
        msg, sent = await todo_check_service.execute_check(db, row, manual=True)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(400, detail=str(exc)) from exc
    return TodoCheckTriggerResponse(message=msg, recipients=sent)


@router.post("", response_model=TodoDetail)
def create_todo_item(
    payload: TodoDirectCreate,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> TodoDetail:
    """Structured form create (date + optional time + title), no LLM."""
    if payload.remind_time:
        import re

        if not re.match(r"^([01]?\d|2[0-3]):([0-5]\d)$", payload.remind_time.strip()):
            raise HTTPException(400, detail="提醒时间格式无效，请使用 HH:MM")
    item = create_todo_direct(
        db,
        tenant_id=ctx.tenant_id,
        title=payload.title,
        plan_date=payload.plan_date,
        remind_time=payload.remind_time,
        description=payload.description,
        channel="web",
    )
    db.commit()
    db.refresh(item)
    return TodoDetail.model_validate(item)


@router.post("/parse", response_model=TodoDetail)
async def parse_todo_item(
    payload: TodoCreate,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> TodoDetail:
    """Natural-language create via LLM intent parsing (quick add)."""
    try:
        result = await handle_todo_message(
            db,
            user_message=payload.raw_input,
            tenant_id=ctx.tenant_id,
            channel="web",
        )
        db.commit()
    except LLMError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    if result.todo is None:
        raise HTTPException(400, detail=result.texts[0] if result.texts else "创建失败")
    db.refresh(result.todo)
    return TodoDetail.model_validate(result.todo)


@router.put("/{todo_id}", response_model=TodoDetail)
def update_todo_item(
    todo_id: int,
    payload: TodoUpdate,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> TodoDetail:
    item = get_todo(db, todo_id, tenant_id=ctx.tenant_id)
    if item is None:
        raise HTTPException(404, detail="todo not found")
    try:
        fields = payload.model_dump(exclude_unset=True)
        update_todo(db, item, **fields)
        db.commit()
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    db.refresh(item)
    return TodoDetail.model_validate(item)


@router.get("/{todo_id}", response_model=TodoDetail)
def get_todo_item(
    todo_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> TodoDetail:
    item = get_todo(db, todo_id, tenant_id=ctx.tenant_id)
    if item is None:
        raise HTTPException(404, detail="todo not found")
    return TodoDetail.model_validate(item)


@router.post("/{todo_id}/progress", response_model=TodoDetail)
def update_todo_progress(
    todo_id: int,
    payload: TodoProgressRequest,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> TodoDetail:
    item = get_todo(db, todo_id, tenant_id=ctx.tenant_id)
    if item is None:
        raise HTTPException(404, detail="todo not found")
    try:
        set_todo_progress(db, item, payload.progress)
        db.commit()
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    db.refresh(item)
    return TodoDetail.model_validate(item)


@router.post("/{todo_id}/done", response_model=TodoDetail)
def complete_todo_item(
    todo_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> TodoDetail:
    item = get_todo(db, todo_id, tenant_id=ctx.tenant_id)
    if item is None:
        raise HTTPException(404, detail="todo not found")
    mark_done(db, item)
    db.commit()
    db.refresh(item)
    return TodoDetail.model_validate(item)


@router.post("/{todo_id}/cancel", response_model=TodoDetail)
def cancel_todo_item(
    todo_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> TodoDetail:
    item = get_todo(db, todo_id, tenant_id=ctx.tenant_id)
    if item is None:
        raise HTTPException(404, detail="todo not found")
    cancel_todo(db, item)
    db.commit()
    db.refresh(item)
    return TodoDetail.model_validate(item)


@router.post("/{todo_id}/restore", response_model=TodoDetail)
def restore_todo_item(
    todo_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> TodoDetail:
    item = get_todo(db, todo_id, tenant_id=ctx.tenant_id)
    if item is None:
        raise HTTPException(404, detail="todo not found")
    try:
        restore_todo(db, item)
        db.commit()
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    db.refresh(item)
    return TodoDetail.model_validate(item)


@router.delete("/{todo_id}", status_code=204)
def delete_todo_item(
    todo_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> None:
    item = get_todo(db, todo_id, tenant_id=ctx.tenant_id)
    if item is None:
        raise HTTPException(404, detail="todo not found")
    delete_todo(db, item)
    db.commit()


@router.post("/{todo_id}/snooze", response_model=TodoDetail)
def snooze_todo_item(
    todo_id: int,
    payload: TodoSnoozeRequest,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> TodoDetail:
    item = get_todo(db, todo_id, tenant_id=ctx.tenant_id)
    if item is None:
        raise HTTPException(404, detail="todo not found")
    snooze_todo(db, item, until=payload.until, note=payload.note)
    db.commit()
    db.refresh(item)
    return TodoDetail.model_validate(item)


@router.post("/{todo_id}/unsnooze", response_model=TodoDetail)
def unsnooze_todo_item(
    todo_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> TodoDetail:
    item = get_todo(db, todo_id, tenant_id=ctx.tenant_id)
    if item is None:
        raise HTTPException(404, detail="todo not found")
    unsnooze_todo(db, item)
    db.commit()
    db.refresh(item)
    return TodoDetail.model_validate(item)
