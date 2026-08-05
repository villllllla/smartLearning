"""AI news API: recent digests, schedule config, manual trigger."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, get_auth_context
from app.db.session import get_db
from app.models import AiNewsDigest
from app.schemas.ai_news import (
    AiNewsDigestRead,
    AiNewsListResponse,
    AiNewsScheduleRead,
    AiNewsScheduleUpdate,
    AiNewsTriggerResponse,
)
from app.services import ai_news_service

log = logging.getLogger(__name__)

router = APIRouter()


def _to_schedule_read(row) -> AiNewsScheduleRead:
    return AiNewsScheduleRead(
        enabled=row.enabled,
        timezone=row.timezone,
        push_times=list(row.push_times or []),
        frequency=row.frequency,
        weekdays=list(row.weekdays or []),
        top_n=row.top_n,
        enable_hackernews=row.enable_hackernews,
        enable_github=row.enable_github,
        enable_arxiv=row.enable_arxiv,
        enable_huggingface=row.enable_huggingface,
        enable_reddit=row.enable_reddit,
        rss_feeds=list(row.rss_feeds or []),
        dedup_days=row.dedup_days,
        feishu_enabled=row.feishu_enabled,
        last_run_slot=row.last_run_slot,
        last_run_at=row.last_run_at,
        last_error=row.last_error,
    )


@router.get("", response_model=AiNewsListResponse)
def list_digests(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> AiNewsListResponse:
    total = db.execute(
        select(func.count(AiNewsDigest.id)).where(
            AiNewsDigest.tenant_id == ctx.tenant_id
        )
    ).scalar_one()
    rows = db.execute(
        select(AiNewsDigest)
        .where(AiNewsDigest.tenant_id == ctx.tenant_id)
        .order_by(AiNewsDigest.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).scalars().all()
    return AiNewsListResponse(
        items=[AiNewsDigestRead.model_validate(r) for r in rows], total=total
    )


@router.get("/schedule", response_model=AiNewsScheduleRead)
def get_schedule(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> AiNewsScheduleRead:
    row = ai_news_service.get_or_create_schedule(db, tenant_id=ctx.tenant_id)
    db.commit()
    return _to_schedule_read(row)


@router.put("/schedule", response_model=AiNewsScheduleRead)
def put_schedule(
    payload: AiNewsScheduleUpdate,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> AiNewsScheduleRead:
    try:
        row = ai_news_service.update_schedule(
            db, tenant_id=ctx.tenant_id, **payload.model_dump(exclude_unset=True)
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    return _to_schedule_read(row)


@router.post("/trigger", response_model=AiNewsTriggerResponse)
async def trigger_now(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> AiNewsTriggerResponse:
    row = ai_news_service.get_or_create_schedule(db, tenant_id=ctx.tenant_id)
    try:
        count, recipients, msg, digest_id = await ai_news_service.execute_news_push(
            db, row, manual=True
        )
        db.commit()
    except RuntimeError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log.warning("ai_news manual trigger failed: %s", exc)
        raise HTTPException(500, detail=str(exc)) from exc
    return AiNewsTriggerResponse(
        ok=True,
        message=msg,
        item_count=count,
        recipient_count=recipients,
        digest_id=digest_id,
    )
