"""IANA timezone reference list."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.timezone import TimezoneItem, TimezoneListResponse
from app.services.timezone_service import list_timezones, region_label_zh

router = APIRouter()


@router.get("", response_model=TimezoneListResponse)
def list_timezones_endpoint(db: Session = Depends(get_db)) -> TimezoneListResponse:
    rows = list_timezones(db)
    items = [
        TimezoneItem(
            iana_name=r.iana_name,
            label_zh=r.label_zh,
            region=r.region,
            region_label_zh=region_label_zh(r.region),
            utc_offset_label=r.utc_offset_label,
            display_label=f"{r.label_zh} ({r.utc_offset_label})",
        )
        for r in rows
    ]
    return TimezoneListResponse(items=items)
