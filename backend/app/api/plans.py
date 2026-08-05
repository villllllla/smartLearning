"""Study plan REST API: LLM decomposition preview, confirm, list."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, get_auth_context
from app.db.session import get_db
from app.schemas.plan import (
    PlanCreateRequest,
    PlanListResponse,
    PlanPreviewRequest,
    PlanPreviewResponse,
    PlanSummary,
    PlanTaskDraftSchema,
)
from app.services import plan_service
from app.services.llm import LLMError
from app.services.plan_service import PlanTaskDraft
from app.services.todo_service import default_timezone

router = APIRouter()


def _to_summary(db: Session, plan) -> PlanSummary:
    done, total = plan_service.plan_progress(db, plan)
    return PlanSummary(
        id=plan.id,
        title=plan.title,
        goal=plan.goal,
        start_date=plan.start_date,
        end_date=plan.end_date,
        status=plan.status,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
        done_count=done,
        total_count=total,
    )


@router.get("", response_model=PlanListResponse)
def list_plans(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> PlanListResponse:
    rows = plan_service.list_plans(db, tenant_id=ctx.tenant_id)
    return PlanListResponse(
        items=[_to_summary(db, p) for p in rows], total=len(rows)
    )


@router.post("/preview", response_model=PlanPreviewResponse)
async def preview_plan(
    payload: PlanPreviewRequest,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> PlanPreviewResponse:
    if payload.end_date < payload.start_date:
        raise HTTPException(400, detail="结束日期不能早于开始日期")
    tz = default_timezone(db, tenant_id=ctx.tenant_id)
    try:
        result = await plan_service.decompose_plan(
            db,
            tenant_id=ctx.tenant_id,
            title=payload.title,
            goal=payload.goal,
            start_date=payload.start_date,
            end_date=payload.end_date,
            timezone_name=tz,
        )
        db.commit()
    except (LLMError, ValueError) as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    if not result.tasks:
        raise HTTPException(
            400, detail="模型未能分解出任务，请调整目标描述或日期区间后重试"
        )
    return PlanPreviewResponse(
        title=payload.title,
        goal=payload.goal,
        start_date=payload.start_date,
        end_date=payload.end_date,
        tasks=[
            PlanTaskDraftSchema(date=t.date, title=t.title, description=t.description)
            for t in result.tasks
        ],
        prompt_id=result.prompt_id,
        model_id=result.model_id,
    )


@router.post("", response_model=PlanSummary)
def create_plan(
    payload: PlanCreateRequest,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> PlanSummary:
    if payload.end_date < payload.start_date:
        raise HTTPException(400, detail="结束日期不能早于开始日期")
    tasks = [
        PlanTaskDraft(date=t.date, title=t.title, description=t.description)
        for t in payload.tasks
        if payload.start_date <= t.date <= payload.end_date
    ]
    if not tasks:
        raise HTTPException(400, detail="没有落在日期区间内的任务")
    try:
        plan = plan_service.create_plan(
            db,
            tenant_id=ctx.tenant_id,
            title=payload.title,
            goal=payload.goal,
            start_date=payload.start_date,
            end_date=payload.end_date,
            tasks=tasks,
            raw_input=payload.goal or payload.title,
            channel="web",
            prompt_id=payload.prompt_id,
            model_id=payload.model_id,
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    db.refresh(plan)
    return _to_summary(db, plan)


@router.delete("/{plan_id}")
def delete_plan(
    plan_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict:
    plan = plan_service.get_plan(db, plan_id, tenant_id=ctx.tenant_id)
    if plan is None:
        raise HTTPException(404, detail="plan not found")
    plan_service.delete_plan(db, plan, drop_tasks=True)
    db.commit()
    return {"ok": True}
