"""Authentication endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import AuthContext, get_auth_context, get_current_user
from app.db.session import get_db
from app.models import Tenant, User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    MeResponse,
    RegisterRequest,
)
from app.services.auth_service import change_password, login, register_tenant

router = APIRouter()


def _user_out(user: User, tenant: Tenant) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name or user.email,
        "role": user.role,
        "tenant_id": tenant.id,
        "tenant_name": tenant.name,
    }


@router.post("/login", response_model=LoginResponse)
def auth_login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    try:
        result = login(db, email=payload.email, password=payload.password)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    db.commit()
    user = db.get(User, result.user_id)
    tenant = db.get(Tenant, result.tenant_id)
    assert user and tenant
    return LoginResponse(
        access_token=result.access_token,
        token_type=result.token_type,
        user=_user_out(user, tenant),
    )


@router.post("/register", response_model=LoginResponse)
def auth_register(payload: RegisterRequest, db: Session = Depends(get_db)) -> LoginResponse:
    settings = get_settings()
    if not settings.auth_allow_register:
        raise HTTPException(403, detail="注册已关闭")
    try:
        result = register_tenant(
            db,
            tenant_name=payload.tenant_name,
            email=payload.email,
            password=payload.password,
            display_name=payload.display_name,
        )
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    db.commit()
    user = db.get(User, result.user_id)
    tenant = db.get(Tenant, result.tenant_id)
    assert user and tenant
    return LoginResponse(
        access_token=result.access_token,
        token_type=result.token_type,
        user=_user_out(user, tenant),
    )


@router.get("/me", response_model=MeResponse)
def auth_me(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
) -> MeResponse:
    settings = get_settings()
    if user is None:
        tenant = db.get(Tenant, ctx.tenant_id)
        if tenant is None:
            raise HTTPException(401, detail="租户不存在")
        return MeResponse(
            auth_enabled=settings.auth_enabled,
            user={
                "id": 0,
                "email": "service@local",
                "display_name": "服务令牌",
                "role": "service",
                "tenant_id": tenant.id,
                "tenant_name": tenant.name,
            },
        )
    tenant = db.get(Tenant, user.tenant_id)
    if tenant is None:
        raise HTTPException(401, detail="租户不存在")
    return MeResponse(
        auth_enabled=settings.auth_enabled,
        user=_user_out(user, tenant),
    )


@router.post("/change-password", status_code=204)
def auth_change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
) -> None:
    if user is None:
        raise HTTPException(401, detail="请先登录后再修改密码")
    try:
        change_password(
            db,
            user=user,
            current_password=payload.current_password,
            new_password=payload.new_password,
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
