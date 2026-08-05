"""AppSettings service: get/update the singleton row."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AppSettings


def get_settings_row(db: Session, tenant_id: int) -> AppSettings:
    s = db.execute(
        select(AppSettings).where(AppSettings.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if s is None:
        s = AppSettings(tenant_id=tenant_id)
        db.add(s)
        db.flush()
    return s
