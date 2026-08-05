"""User goals and job roles API (PRD §15.2)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, get_auth_context, get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.goal import (
    GoalProgressOut,
    JobRoleCreate,
    JobRoleOut,
    UserGoalCreate,
    UserGoalOut,
    UserGoalUpdate,
)
from app.schemas.practice import PracticeSetupResponse
from app.services import goal_service

router = APIRouter()


def _require_user(user: User | None = Depends(get_current_user)) -> User:
    if user is None:
        raise HTTPException(401, detail="请先登录后再使用求职目标")
    return user


@router.get("/job-roles", response_model=list[JobRoleOut])
def list_job_roles(
    q: str | None = Query(None),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> list[JobRoleOut]:
    rows = goal_service.list_job_roles(db, tenant_id=ctx.tenant_id, q=q)
    return [goal_service.job_role_to_out(r) for r in rows]


@router.post("/job-roles", response_model=JobRoleOut)
def create_job_role(
    payload: JobRoleCreate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> JobRoleOut:
    try:
        role = goal_service.create_custom_job_role(
            db,
            tenant_id=ctx.tenant_id,
            name=payload.name,
            family=payload.family,
            level=payload.level,
            description=payload.description,
            skills=payload.skills,
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    db.refresh(role)
    role = goal_service.get_job_role(db, role.id, tenant_id=ctx.tenant_id)
    assert role
    return goal_service.job_role_to_out(role)


@router.get("", response_model=list[UserGoalOut])
def list_goals(
    status: str | None = Query(None),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
    user: User = Depends(_require_user),
) -> list[UserGoalOut]:
    rows = goal_service.list_user_goals(
        db, tenant_id=ctx.tenant_id, user_id=user.id, status=status
    )
    return [goal_service.goal_to_out(g) for g in rows]


@router.get("/active", response_model=UserGoalOut | None)
def get_active_goal(
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
    user: User = Depends(_require_user),
) -> UserGoalOut | None:
    goal = goal_service.get_active_goal(db, tenant_id=ctx.tenant_id, user_id=user.id)
    if goal is None:
        return None
    return goal_service.goal_to_out(goal)


@router.post("", response_model=UserGoalOut)
def create_goal(
    payload: UserGoalCreate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
    user: User = Depends(_require_user),
) -> UserGoalOut:
    try:
        goal = goal_service.create_user_goal(
            db,
            tenant_id=ctx.tenant_id,
            user_id=user.id,
            job_role_id=payload.job_role_id,
            target_date=payload.target_date,
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    return goal_service.goal_to_out(goal)


@router.get("/{goal_id}", response_model=UserGoalOut)
def get_goal(
    goal_id: int,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
    user: User = Depends(_require_user),
) -> UserGoalOut:
    goal = goal_service.get_user_goal(
        db, goal_id, tenant_id=ctx.tenant_id, user_id=user.id
    )
    if goal is None:
        raise HTTPException(404, detail="目标不存在")
    return goal_service.goal_to_out(goal)


@router.patch("/{goal_id}", response_model=UserGoalOut)
def update_goal(
    goal_id: int,
    payload: UserGoalUpdate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
    user: User = Depends(_require_user),
) -> UserGoalOut:
    goal = goal_service.get_user_goal(
        db, goal_id, tenant_id=ctx.tenant_id, user_id=user.id
    )
    if goal is None:
        raise HTTPException(404, detail="目标不存在")
    data = payload.model_dump(exclude_unset=True)
    clear_target_date = data.pop("clear_target_date", False)
    try:
        goal_service.update_user_goal(
            db,
            goal,
            tenant_id=ctx.tenant_id,
            clear_target_date=clear_target_date,
            **data,
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    db.refresh(goal)
    goal = goal_service.get_user_goal(
        db, goal_id, tenant_id=ctx.tenant_id, user_id=user.id
    )
    assert goal
    return goal_service.goal_to_out(goal)


@router.delete("/{goal_id}", status_code=204)
def delete_goal(
    goal_id: int,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
    user: User = Depends(_require_user),
) -> None:
    goal = goal_service.get_user_goal(
        db, goal_id, tenant_id=ctx.tenant_id, user_id=user.id
    )
    if goal is None:
        raise HTTPException(404, detail="目标不存在")
    goal_service.delete_user_goal(db, goal)
    db.commit()


@router.get("/{goal_id}/progress", response_model=GoalProgressOut)
def get_goal_progress(
    goal_id: int,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
    user: User = Depends(_require_user),
) -> GoalProgressOut:
    goal = goal_service.get_user_goal(
        db, goal_id, tenant_id=ctx.tenant_id, user_id=user.id
    )
    if goal is None:
        raise HTTPException(404, detail="目标不存在")
    progress = goal_service.compute_goal_progress(db, goal)
    db.commit()
    return progress


@router.post("/{goal_id}/recommend-practice", response_model=PracticeSetupResponse)
def recommend_practice(
    goal_id: int,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
    user: User = Depends(_require_user),
) -> PracticeSetupResponse:
    goal = goal_service.get_user_goal(
        db, goal_id, tenant_id=ctx.tenant_id, user_id=user.id
    )
    if goal is None:
        raise HTTPException(404, detail="目标不存在")
    return goal_service.recommend_practice_for_goal(db, goal)
