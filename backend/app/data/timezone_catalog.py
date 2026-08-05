"""Curated IANA timezones for push scheduling (seeded into ``timezone_refs``).

Built from ``zoneinfo``-valid names; offsets are computed at seed time for sorting.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class TimezoneCatalogEntry:
    iana_name: str
    label_zh: str
    region: str
    sort_order: int


# region keys match UI optgroup labels (see REGION_LABEL_ZH)
TIMEZONE_CATALOG: tuple[TimezoneCatalogEntry, ...] = (
    # UTC
    TimezoneCatalogEntry("UTC", "协调世界时", "UTC", 0),
    # Asia
    TimezoneCatalogEntry("Asia/Shanghai", "北京 / 上海", "Asia", 10),
    TimezoneCatalogEntry("Asia/Hong_Kong", "香港", "Asia", 11),
    TimezoneCatalogEntry("Asia/Taipei", "台北", "Asia", 12),
    TimezoneCatalogEntry("Asia/Tokyo", "东京", "Asia", 20),
    TimezoneCatalogEntry("Asia/Seoul", "首尔", "Asia", 21),
    TimezoneCatalogEntry("Asia/Singapore", "新加坡", "Asia", 30),
    TimezoneCatalogEntry("Asia/Bangkok", "曼谷", "Asia", 31),
    TimezoneCatalogEntry("Asia/Jakarta", "雅加达", "Asia", 32),
    TimezoneCatalogEntry("Asia/Kuala_Lumpur", "吉隆坡", "Asia", 33),
    TimezoneCatalogEntry("Asia/Manila", "马尼拉", "Asia", 34),
    TimezoneCatalogEntry("Asia/Ho_Chi_Minh", "胡志明市", "Asia", 35),
    TimezoneCatalogEntry("Asia/Kolkata", "新德里 / 孟买", "Asia", 40),
    TimezoneCatalogEntry("Asia/Dubai", "迪拜", "Asia", 50),
    TimezoneCatalogEntry("Asia/Riyadh", "利雅得", "Asia", 51),
    TimezoneCatalogEntry("Asia/Jerusalem", "耶路撒冷", "Asia", 52),
    TimezoneCatalogEntry("Asia/Tehran", "德黑兰", "Asia", 53),
    # Europe
    TimezoneCatalogEntry("Europe/London", "伦敦", "Europe", 100),
    TimezoneCatalogEntry("Europe/Dublin", "都柏林", "Europe", 101),
    TimezoneCatalogEntry("Europe/Paris", "巴黎 / 中欧", "Europe", 110),
    TimezoneCatalogEntry("Europe/Berlin", "柏林", "Europe", 111),
    TimezoneCatalogEntry("Europe/Amsterdam", "阿姆斯特丹", "Europe", 112),
    TimezoneCatalogEntry("Europe/Rome", "罗马", "Europe", 113),
    TimezoneCatalogEntry("Europe/Madrid", "马德里", "Europe", 114),
    TimezoneCatalogEntry("Europe/Zurich", "苏黎世", "Europe", 115),
    TimezoneCatalogEntry("Europe/Stockholm", "斯德哥尔摩", "Europe", 116),
    TimezoneCatalogEntry("Europe/Warsaw", "华沙", "Europe", 117),
    TimezoneCatalogEntry("Europe/Athens", "雅典", "Europe", 120),
    TimezoneCatalogEntry("Europe/Helsinki", "赫尔辛基", "Europe", 121),
    TimezoneCatalogEntry("Europe/Bucharest", "布加勒斯特", "Europe", 122),
    TimezoneCatalogEntry("Europe/Istanbul", "伊斯坦布尔", "Europe", 123),
    TimezoneCatalogEntry("Europe/Moscow", "莫斯科", "Europe", 130),
    # America
    TimezoneCatalogEntry("America/New_York", "纽约 (美东)", "America", 200),
    TimezoneCatalogEntry("America/Chicago", "芝加哥 (美中)", "America", 201),
    TimezoneCatalogEntry("America/Denver", "丹佛 (美山)", "America", 202),
    TimezoneCatalogEntry("America/Los_Angeles", "洛杉矶 (美西)", "America", 203),
    TimezoneCatalogEntry("America/Phoenix", "凤凰城", "America", 204),
    TimezoneCatalogEntry("America/Toronto", "多伦多", "America", 210),
    TimezoneCatalogEntry("America/Vancouver", "温哥华", "America", 211),
    TimezoneCatalogEntry("America/Mexico_City", "墨西哥城", "America", 220),
    TimezoneCatalogEntry("America/Sao_Paulo", "圣保罗", "America", 230),
    TimezoneCatalogEntry("America/Buenos_Aires", "布宜诺斯艾利斯", "America", 231),
    TimezoneCatalogEntry("America/Bogota", "波哥大", "America", 232),
    TimezoneCatalogEntry("America/Lima", "利马", "America", 233),
    # Pacific / Australia
    TimezoneCatalogEntry("Australia/Sydney", "悉尼", "Australia", 300),
    TimezoneCatalogEntry("Australia/Melbourne", "墨尔本", "Australia", 301),
    TimezoneCatalogEntry("Australia/Brisbane", "布里斯班", "Australia", 302),
    TimezoneCatalogEntry("Australia/Perth", "珀斯", "Australia", 303),
    TimezoneCatalogEntry("Pacific/Auckland", "奥克兰", "Pacific", 310),
    TimezoneCatalogEntry("Pacific/Fiji", "斐济", "Pacific", 311),
    TimezoneCatalogEntry("Pacific/Honolulu", "檀香山", "Pacific", 320),
    # Africa
    TimezoneCatalogEntry("Africa/Cairo", "开罗", "Africa", 400),
    TimezoneCatalogEntry("Africa/Johannesburg", "约翰内斯堡", "Africa", 401),
    TimezoneCatalogEntry("Africa/Lagos", "拉各斯", "Africa", 402),
    TimezoneCatalogEntry("Africa/Nairobi", "内罗毕", "Africa", 403),
    # Indian
    TimezoneCatalogEntry("Indian/Mauritius", "毛里求斯", "Indian", 500),
)

REGION_LABEL_ZH: dict[str, str] = {
    "UTC": "协调世界时",
    "Asia": "亚洲",
    "Europe": "欧洲",
    "America": "美洲",
    "Australia": "澳大利亚",
    "Pacific": "太平洋",
    "Africa": "非洲",
    "Indian": "印度洋",
}


def utc_offset_label(iana_name: str, *, at: datetime | None = None) -> str:
    """Human-readable offset e.g. ``UTC+8`` (uses current DST rules)."""
    at = at or datetime.now(ZoneInfo(iana_name))
    off = at.utcoffset()
    if off is None:
        return "UTC"
    total = int(off.total_seconds() // 60)
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    h, m = divmod(total, 60)
    if m:
        return f"UTC{sign}{h}:{m:02d}"
    return f"UTC{sign}{h}"


def utc_offset_minutes(iana_name: str, *, at: datetime | None = None) -> int:
    at = at or datetime.now(ZoneInfo(iana_name))
    off = at.utcoffset()
    if off is None:
        return 0
    return int(off.total_seconds() // 60)


def catalog_rows_for_seed() -> list[dict]:
    """Rows for Alembic / service bootstrap."""
    rows: list[dict] = []
    for entry in TIMEZONE_CATALOG:
        ZoneInfo(entry.iana_name)  # validate
        rows.append(
            {
                "iana_name": entry.iana_name,
                "label_zh": entry.label_zh,
                "region": entry.region,
                "utc_offset_label": utc_offset_label(entry.iana_name),
                "utc_offset_minutes": utc_offset_minutes(entry.iana_name),
                "sort_order": entry.sort_order,
            }
        )
    return rows
