"""GET / PUT /api/settings (PRD §6.5)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, get_auth_context
from app.db.session import get_db
from app.schemas.settings import AppSettingsRead, AppSettingsUpdate
from app.services.settings_service import get_settings_row

router = APIRouter()





@router.get("", response_model=AppSettingsRead)

def get_settings(

    db: Session = Depends(get_db),

    ctx: AuthContext = Depends(get_auth_context),

) -> AppSettingsRead:

    return AppSettingsRead.model_validate(get_settings_row(db, ctx.tenant_id))





@router.put("", response_model=AppSettingsRead)

def update_settings(

    payload: AppSettingsUpdate,

    db: Session = Depends(get_db),

    ctx: AuthContext = Depends(get_auth_context),

) -> AppSettingsRead:

    s = get_settings_row(db, ctx.tenant_id)

    data = payload.model_dump(exclude_unset=True, exclude={"clear_time_limit", "clear_llm_fallback_model"})
    tz_update = data.pop("timezone", None)

    for k, v in data.items():
        setattr(s, k, v)

    if tz_update is not None:
        from app.services.app_timezone_service import set_app_timezone

        set_app_timezone(db, tenant_id=ctx.tenant_id, timezone=tz_update)

    if payload.clear_time_limit:

        s.practice_time_limit_per_question = None

    if payload.clear_llm_fallback_model:
        s.llm_fallback_model_id = None

    db.commit()

    db.refresh(s)

    return AppSettingsRead.model_validate(s)

