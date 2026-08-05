"""Feishu bot trigger prefix configuration API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, get_auth_context
from app.db.session import get_db
from app.schemas.feishu_trigger import (
    FeishuTriggerBulkUpdate,
    FeishuTriggerListResponse,
    FeishuTriggerRuleRead,
)
from app.services.feishu_trigger_service import (
    get_rules,
    reset_rules_to_defaults,
    update_rules,
)

router = APIRouter()


@router.get("", response_model=FeishuTriggerListResponse)
def list_feishu_triggers(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> FeishuTriggerListResponse:
    rows = get_rules(db, tenant_id=ctx.tenant_id)
    db.commit()
    return FeishuTriggerListResponse(
        items=[FeishuTriggerRuleRead.model_validate(r) for r in rows]
    )


@router.put("", response_model=FeishuTriggerListResponse)
def update_feishu_triggers(
    payload: FeishuTriggerBulkUpdate,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> FeishuTriggerListResponse:
    try:
        rows = update_rules(
            db,
            tenant_id=ctx.tenant_id,
            updates=[item.model_dump(exclude_unset=True) for item in payload.items],
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    return FeishuTriggerListResponse(
        items=[FeishuTriggerRuleRead.model_validate(r) for r in rows]
    )


@router.post("/reset", response_model=FeishuTriggerListResponse)
def reset_feishu_triggers(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> FeishuTriggerListResponse:
    rows = reset_rules_to_defaults(db, tenant_id=ctx.tenant_id)
    db.commit()
    return FeishuTriggerListResponse(
        items=[FeishuTriggerRuleRead.model_validate(r) for r in rows]
    )
