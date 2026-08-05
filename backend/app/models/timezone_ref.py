"""Reference table: IANA timezones for UI dropdowns."""
from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TimezoneRef(Base):
    __tablename__ = "timezone_refs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    iana_name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    label_zh: Mapped[str] = mapped_column(String(120), nullable=False)
    region: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    utc_offset_label: Mapped[str] = mapped_column(String(16), nullable=False)
    utc_offset_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
