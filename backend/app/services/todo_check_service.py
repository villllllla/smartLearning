"""Daily todo check: roll over overdue tasks, then nudge if today has no plan
(or push today's plan list). One card, clearly titled, to the single Feishu chat."""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.todo import TodoCheckSchedule
from app.services import todo_service

log = logging.getLogger(__name__)

_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_DEFER_MOTIVATE_THRESHOLD = 3  # days overdue before we attach LLM encouragement


def get_or_create_schedule(db: Session, *, tenant_id: int) -> TodoCheckSchedule:
    row = db.execute(
        select(TodoCheckSchedule).where(TodoCheckSchedule.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if row is None:
        row = TodoCheckSchedule(tenant_id=tenant_id)
        db.add(row)
        db.flush()
    from app.services.app_timezone_service import apply_schedule_timezone

    apply_schedule_timezone(db, tenant_id=tenant_id, row=row)
    return row


def _parse_time(value: str) -> str:
    s = str(value or "").strip()
    m = _TIME_RE.match(s)
    if not m:
        raise ValueError("检测时间格式无效，请使用 HH:MM（如 08:00）")
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def update_schedule(db: Session, *, tenant_id: int, **fields) -> TodoCheckSchedule:
    row = get_or_create_schedule(db, tenant_id=tenant_id)
    if fields.get("enabled") is not None:
        row.enabled = bool(fields["enabled"])
    if fields.get("check_time") is not None:
        row.check_time = _parse_time(fields["check_time"])
    if fields.get("push_today_plan") is not None:
        row.push_today_plan = bool(fields["push_today_plan"])
    if fields.get("feishu_enabled") is not None:
        row.feishu_enabled = bool(fields["feishu_enabled"])
    from app.services.app_timezone_service import apply_schedule_timezone

    apply_schedule_timezone(db, tenant_id=tenant_id, row=row)
    db.flush()
    return row


def _local_today(db: Session, row: TodoCheckSchedule) -> date:
    from app.services.app_timezone_service import get_app_timezone

    try:
        tz = ZoneInfo(get_app_timezone(db, tenant_id=row.tenant_id))
    except Exception:
        tz = ZoneInfo("Asia/Shanghai")
    return datetime.now(tz).date()


def is_due_now(row: TodoCheckSchedule, now: datetime | None = None, *, db: Session) -> str | None:
    if not row.enabled or not row.check_time:
        return None
    from app.services.app_timezone_service import get_app_timezone

    try:
        tz = ZoneInfo(get_app_timezone(db, tenant_id=row.tenant_id))
    except Exception:
        tz = ZoneInfo("Asia/Shanghai")
    local = (now or datetime.now(tz)).astimezone(tz)
    if local.strftime("%H:%M") != row.check_time:
        return None
    slot = f"{local.strftime('%Y-%m-%d')}T{row.check_time}"
    if row.last_run_slot == slot:
        return None
    return slot


async def execute_check(
    db: Session,
    row: TodoCheckSchedule,
    *,
    settings: Settings | None = None,
    slot: str | None = None,
    manual: bool = False,
) -> tuple[str, int]:
    """Defer overdue tasks, then push today's plan (or a no-plan nudge).

    Returns (human message, recipients pushed to).
    """
    from app.integrations.feishu import client as feishu_client
    from app.integrations.feishu import formatters
    from app.services.push_schedule_service import _feishu_recipients

    settings = settings or get_settings()
    today = _local_today(db, row)

    deferred = todo_service.run_deferrals(db, tenant_id=row.tenant_id, today=today)
    tasks = todo_service.open_tasks_for_date(db, tenant_id=row.tenant_id, day=today)

    # Enrich long-overdue tasks with an LLM motivation line.
    motivations: dict[int, str] = {}
    for t in tasks:
        if (t.defer_count or 0) >= _DEFER_MOTIVATE_THRESHOLD:
            line = await todo_service.motivation_line(
                db,
                tenant_id=row.tenant_id,
                task_title=t.title,
                defer_days=int(t.defer_count or 0),
            )
            if line:
                motivations[t.id] = line

    sent = 0
    push_feishu = row.feishu_enabled and settings.feishu_bot_enabled
    if push_feishu:
        recipients = _feishu_recipients(db, settings)
        if not recipients:
            raise RuntimeError(
                "没有可推送的飞书会话。请先在飞书私聊机器人发一条消息，并配置 SL_FEISHU_ALLOWED_OPEN_IDS"
            )
        if not tasks:
            card = formatters.todo_no_plan_card(today)
        elif row.push_today_plan:
            card = formatters.todo_today_plan_card(today, tasks, motivations)
        else:
            card = None
        if card is not None:
            for session in recipients:
                try:
                    await feishu_client.send_interactive_card_to_chat(
                        session.feishu_chat_id, card, settings=settings
                    )
                    sent += 1
                except Exception as exc:
                    log.warning(
                        "todo-check push to %s failed: %s", session.feishu_open_id, exc
                    )

    row.last_error = None
    if slot:
        row.last_run_slot = slot
    row.last_run_at = datetime.utcnow()
    db.flush()

    if not tasks:
        msg = f"今日({today})暂无计划，已提醒 {sent} 个飞书用户；顺延处理 {deferred} 项"
    else:
        msg = (
            f"今日({today})共 {len(tasks)} 项计划，已推送 {sent} 个飞书用户；"
            f"顺延处理 {deferred} 项"
        )
    return msg, sent


async def run_due_todo_check(db: Session) -> None:
    settings = get_settings()
    rows = db.execute(
        select(TodoCheckSchedule).where(TodoCheckSchedule.enabled.is_(True))
    ).scalars().all()
    for row in rows:
        slot = is_due_now(row, db=db)
        if slot is None:
            continue
        try:
            await execute_check(db, row, settings=settings, slot=slot)
            db.commit()
            log.info("todo-check ok tenant=%s slot=%s", row.tenant_id, slot)
        except Exception as exc:
            row.last_error = str(exc)[:500]
            row.last_run_slot = slot
            row.last_run_at = datetime.utcnow()
            db.commit()
            log.warning("todo-check failed tenant=%s: %s", row.tenant_id, exc)
