"""Request auth context for multi-tenant APIs."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import User


@dataclass(frozen=True)
class AuthContext:
    tenant_id: int
    user_id: int | None
    email: str | None
    is_service_token: bool = False


def get_auth_context(request: Request) -> AuthContext:
    tid = getattr(request.state, "tenant_id", None)
    if tid is None:
        raise HTTPException(401, detail="未登录或登录已过期")
    return AuthContext(
        tenant_id=int(tid),
        user_id=getattr(request.state, "user_id", None),
        email=getattr(request.state, "user_email", None),
        is_service_token=bool(getattr(request.state, "is_service_token", False)),
    )


def get_current_user(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> User | None:
    if ctx.user_id is None:
        return None
    user = db.get(User, ctx.user_id)
    if user is None or user.tenant_id != ctx.tenant_id:
        raise HTTPException(401, detail="用户不存在或无权访问")
    return user
