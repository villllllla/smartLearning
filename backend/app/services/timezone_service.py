"""Timezone reference list (DB-backed)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.timezone_catalog import REGION_LABEL_ZH, catalog_rows_for_seed
from app.models.timezone_ref import TimezoneRef


def seed_timezone_refs(db: Session) -> int:
    """Insert catalog rows if table is empty. Returns rows inserted."""
    existing = db.execute(select(TimezoneRef.id).limit(1)).scalar_one_or_none()
    if existing is not None:
        return 0
    for row in catalog_rows_for_seed():
        db.add(TimezoneRef(**row))
    db.flush()
    return len(catalog_rows_for_seed())


def list_timezones(db: Session) -> list[TimezoneRef]:
    seed_timezone_refs(db)
    return list(
        db.execute(
            select(TimezoneRef).order_by(
                TimezoneRef.utc_offset_minutes.asc(),
                TimezoneRef.sort_order.asc(),
                TimezoneRef.iana_name.asc(),
            )
        ).scalars().all()
    )


def is_valid_timezone(db: Session, iana_name: str) -> bool:
    seed_timezone_refs(db)
    name = (iana_name or "").strip()
    if not name:
        return False
    hit = db.execute(
        select(TimezoneRef.id).where(TimezoneRef.iana_name == name).limit(1)
    ).scalar_one_or_none()
    return hit is not None


def region_label_zh(region: str) -> str:
    return REGION_LABEL_ZH.get(region, region)
