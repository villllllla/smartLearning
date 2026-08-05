"""Spaced-review schedule: config, due detection, Feishu push (separate from quiz push)."""
from __future__ import annotations

import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import LearningReviewSchedule
from app.services.learning_note_service import (
    DEFAULT_INTERVALS_DAYS,
    MAX_MASTERED_FACTOR,
    due_notes,
    mark_reviewed,
)

log = logging.getLogger(__name__)

_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_VALID_FREQ = frozenset({"daily", "weekdays", "weekly"})


def get_or_create_schedule(db: Session, *, tenant_id: int) -> LearningReviewSchedule:
    row = db.execute(
        select(LearningReviewSchedule).where(
            LearningReviewSchedule.tenant_id == tenant_id
        )
    ).scalar_one_or_none()
    if row is None:
        row = LearningReviewSchedule(
            tenant_id=tenant_id,
            push_times=["08:00"],
            intervals_days=list(DEFAULT_INTERVALS_DAYS),
            weekdays=[],
        )
        db.add(row)
        db.flush()
    from app.services.app_timezone_service import apply_schedule_timezone

    apply_schedule_timezone(db, tenant_id=tenant_id, row=row)
    return row


def parse_push_times(times: list[str]) -> list[str]:
    if not times:
        raise ValueError("至少设置一个推送时间，格式 HH:MM（如 08:00）")
    out: list[str] = []
    bad: list[str] = []
    for raw in times:
        s = str(raw).strip()
        if not s:
            continue
        m = _TIME_RE.match(s)
        if not m:
            bad.append(s)
            continue
        out.append(f"{int(m.group(1)):02d}:{m.group(2)}")
    if bad:
        raise ValueError(f"推送时间格式无效: {', '.join(bad)}，请使用 HH:MM")
    if not out:
        raise ValueError("至少设置一个推送时间，格式 HH:MM")
    return sorted(set(out))


def _parse_intervals(values: list) -> list[int]:
    out: list[int] = []
    for v in values:
        try:
            n = int(v)
        except (TypeError, ValueError):
            continue
        if 1 <= n <= 365:
            out.append(n)
    if not out:
        raise ValueError("间隔天数无效，请输入 1-365 的正整数，如 1,3,7,15,30")
    return sorted(set(out))


def update_schedule(db: Session, *, tenant_id: int, **fields) -> LearningReviewSchedule:
    row = get_or_create_schedule(db, tenant_id=tenant_id)
    if fields.get("enabled") is not None:
        row.enabled = bool(fields["enabled"])
    if fields.get("push_times") is not None:
        row.push_times = parse_push_times(list(fields["push_times"]))
    if fields.get("frequency") is not None:
        freq = str(fields["frequency"]).lower()
        if freq not in _VALID_FREQ:
            raise ValueError("frequency 须为 daily / weekdays / weekly")
        row.frequency = freq
    if fields.get("weekdays") is not None:
        days = [int(d) for d in fields["weekdays"] if 0 <= int(d) <= 6]
        row.weekdays = sorted(set(days))
    if fields.get("intervals_days") is not None:
        row.intervals_days = _parse_intervals(list(fields["intervals_days"]))
    if fields.get("max_notes_per_push") is not None:
        row.max_notes_per_push = max(1, min(20, int(fields["max_notes_per_push"])))
    if fields.get("mastered_factor") is not None:
        try:
            factor = float(fields["mastered_factor"])
        except (TypeError, ValueError) as exc:
            raise ValueError("已掌握降权倍数须为 1-20 的数字") from exc
        row.mastered_factor = max(1.0, min(MAX_MASTERED_FACTOR, factor))
    if fields.get("recall_mode") is not None:
        row.recall_mode = bool(fields["recall_mode"])
    if fields.get("feishu_enabled") is not None:
        row.feishu_enabled = bool(fields["feishu_enabled"])
    from app.services.app_timezone_service import apply_schedule_timezone

    apply_schedule_timezone(db, tenant_id=tenant_id, row=row)
    db.flush()
    return row


def schedule_summary(row: LearningReviewSchedule) -> str:
    times = "、".join(row.push_times) if row.push_times else "未设置"
    freq_label = {"daily": "每天", "weekdays": "工作日", "weekly": "每周指定日"}.get(
        row.frequency, row.frequency
    )
    status = "已开启" if row.enabled else "已关闭"
    intervals = "/".join(str(d) for d in (row.intervals_days or DEFAULT_INTERVALS_DAYS))
    lines = [
        f"复习推送: {status}",
        f"时间: {times} ({row.timezone})",
        f"频率: {freq_label}",
        f"间隔(天): {intervals} · 每次最多 {row.max_notes_per_push} 条",
        f"已掌握降权: 间隔 ×{row.mastered_factor:g}，排在未掌握之后（仍会推送）",
        f"主动回忆: {'开' if row.recall_mode else '关'}",
        f"飞书推送: {'开' if row.feishu_enabled else '关'}",
    ]
    if row.last_run_at:
        lines.append(f"上次推送: {row.last_run_at.strftime('%Y-%m-%d %H:%M')}")
    if row.last_error:
        lines.append(f"上次错误: {row.last_error[:200]}")
    return "\n".join(lines)


def _local_now(db: Session, tenant_id: int) -> datetime:
    from app.services.app_timezone_service import get_app_timezone

    try:
        tz = ZoneInfo(get_app_timezone(db, tenant_id=tenant_id))
    except Exception:
        tz = ZoneInfo("Asia/Shanghai")
    return datetime.now(tz)


def _frequency_allows(row: LearningReviewSchedule, local: datetime) -> bool:
    wd = local.weekday()
    if row.frequency == "weekdays" and wd >= 5:
        return False
    if row.frequency == "weekly":
        allowed = row.weekdays or [0, 1, 2, 3, 4]
        if wd not in allowed:
            return False
    return True


def review_catch_up_slot(
    row: LearningReviewSchedule, *, db: Session, now: datetime | None = None
) -> str | None:
    """Push overdue backlog after scheduled time if earlier run did not clear the queue."""
    if not row.enabled or not row.push_times:
        return None
    if not due_notes(db, tenant_id=row.tenant_id, limit=1):
        return None
    from app.services.app_timezone_service import get_app_timezone

    try:
        tz = ZoneInfo(get_app_timezone(db, tenant_id=row.tenant_id))
    except Exception:
        tz = ZoneInfo("Asia/Shanghai")
    local = (
        now.astimezone(tz)
        if now is not None and now.tzinfo
        else (now.replace(tzinfo=tz) if now is not None else datetime.now(tz))
    )
    if not _frequency_allows(row, local):
        return None
    hhmm = local.strftime("%H:%M")
    day = local.strftime("%Y-%m-%d")
    passed = [t for t in row.push_times if t <= hhmm]
    if not passed:
        return None
    for pt in sorted(passed):
        slot = f"{day}T{pt}"
        if row.last_run_slot != slot:
            return slot
    # Scheduled slot marked complete but backlog remains (partial push / legacy state).
    if row.last_run_at and (datetime.utcnow() - row.last_run_at).total_seconds() < 300:
        return None
    return f"{day}Tbacklog"


def is_due_now(
    row: LearningReviewSchedule, now: datetime | None = None, *, db: Session
) -> str | None:
    if not row.enabled or not row.push_times:
        return None
    from app.services.app_timezone_service import get_app_timezone

    try:
        tz = ZoneInfo(get_app_timezone(db, tenant_id=row.tenant_id))
    except Exception:
        tz = ZoneInfo("Asia/Shanghai")
    if now is not None:
        local = now.astimezone(tz) if now.tzinfo else now.replace(tzinfo=tz)
    else:
        local = datetime.now(tz)
    if not _frequency_allows(row, local):
        return None
    hhmm = local.strftime("%H:%M")
    if hhmm not in row.push_times:
        return None
    slot = f"{local.strftime('%Y-%m-%d')}T{hhmm}"
    if row.last_run_slot == slot:
        return None
    return slot


async def execute_review_push(
    db: Session,
    row: LearningReviewSchedule,
    *,
    settings: Settings | None = None,
    slot: str | None = None,
    manual: bool = False,
) -> tuple[int, int, str]:
    """Push due learning notes to Feishu for review. Returns (note_count, recipients, msg)."""
    from app.integrations.feishu import client as feishu_client
    from app.integrations.feishu import formatters
    from app.services.push_schedule_service import _feishu_recipients

    settings = settings or get_settings()
    if row.feishu_enabled and not settings.feishu_bot_enabled:
        raise RuntimeError("飞书 Bot 未启用 (SL_FEISHU_BOT_ENABLED)")

    notes = due_notes(
        db, tenant_id=row.tenant_id, limit=row.max_notes_per_push
    )
    if not notes:
        msg = "今天没有待复习的学习总结"
        row.last_error = None
        if slot:
            row.last_run_slot = slot
        row.last_run_at = datetime.utcnow()
        db.flush()
        return 0, 0, msg

    sent = 0
    if row.feishu_enabled:
        recipients = _feishu_recipients(db, settings)
        if not recipients:
            raise RuntimeError(
                "没有可推送的飞书会话。请先在飞书私聊机器人发一条消息，并配置 SL_FEISHU_ALLOWED_OPEN_IDS"
            )
        intro = formatters.review_push_intro(len(notes), manual=manual)
        for session in recipients:
            try:
                await feishu_client.send_text_to_chat(
                    session.feishu_chat_id, intro, settings=settings
                )
                for note in notes:
                    card = formatters.note_review_card(note, recall_mode=row.recall_mode)
                    await feishu_client.send_interactive_card_to_chat(
                        session.feishu_chat_id, card, settings=settings
                    )
                sent += 1
            except Exception as exc:
                log.warning(
                    "review push to %s failed: %s", session.feishu_open_id, exc
                )
        if not sent:
            raise RuntimeError("飞书推送失败，未能送达任何用户")

    # Advance spaced interval only after a successful Feishu delivery (or web-only).
    for note in notes:
        note.last_pushed_slot = slot
        mark_reviewed(db, note)

    remaining = due_notes(db, tenant_id=row.tenant_id, limit=1)
    row.last_error = None
    if slot and not remaining:
        row.last_run_slot = slot
    row.last_run_at = datetime.utcnow()
    db.flush()
    extra = "，仍有待复习条目" if remaining else ""
    msg = f"已推送 {len(notes)} 条待复习总结到 {sent} 个飞书用户{extra}"
    return len(notes), sent, msg


async def run_due_learning_reviews(db: Session) -> None:
    settings = get_settings()
    if not settings.feishu_bot_enabled:
        return
    rows = db.execute(
        select(LearningReviewSchedule).where(
            LearningReviewSchedule.enabled.is_(True),
            LearningReviewSchedule.feishu_enabled.is_(True),
        )
    ).scalars().all()
    for row in rows:
        slot = is_due_now(row, db=db) or review_catch_up_slot(row, db=db)
        if slot is None:
            continue
        try:
            await execute_review_push(db, row, settings=settings, slot=slot)
            db.commit()
            log.info("scheduled review ok tenant=%s slot=%s", row.tenant_id, slot)
        except Exception as exc:
            row.last_error = str(exc)[:500]
            row.last_run_at = datetime.utcnow()
            db.commit()
            log.warning("scheduled review failed tenant=%s: %s", row.tenant_id, exc)
