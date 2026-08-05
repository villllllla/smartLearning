"""Timezone reference API schemas."""
from __future__ import annotations

from pydantic import BaseModel


class TimezoneItem(BaseModel):
    iana_name: str
    label_zh: str
    region: str
    region_label_zh: str
    utc_offset_label: str
    display_label: str


class TimezoneListResponse(BaseModel):
    items: list[TimezoneItem]
