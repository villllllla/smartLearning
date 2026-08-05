"""Todos: LLM intent parsing, clarification, scheduling, Feishu reminders."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.todo import TodoItem
from app.services.llm import LLMClient, LLMError, LLMMessage

log = logging.getLogger(__name__)

DEFAULT_REMIND_TIME = "21:00"

_ACTIVE_TODO_STATUSES = ("scheduled", "reminded", "snoozed", "clarifying")


def _todo_belongs_to_day(item: TodoItem, day: date) -> bool:
    """Match items shown in the day list, including deferred-but-incomplete on origin day."""
    if item.deleted_at is not None or item.status == "cancelled":
        return False
    if item.plan_date == day:
        return True
    return (
        item.original_plan_date == day
        and item.status in _ACTIVE_TODO_STATUSES
    )

TODO_INTENT_SCHEMA: dict = {
    "type": "object",
    "required": ["intent", "needs_clarification"],
    "properties": {
        "intent": {
            "type": "string",
            "enum": [
                "create_todo",
                "list_todos",
                "complete_todo",
                "cancel_draft",
                "unknown",
            ],
        },
        "title": {"type": "string"},
        "description": {"type": "string"},
        "remind_at_iso": {"type": ["string", "null"]},
        "remind_at_text": {"type": "string"},
        "needs_clarification": {"type": "boolean"},
        "clarification_question": {"type": "string"},
        "missing_fields": {"type": "array", "items": {"type": "string"}},
        "todo_id": {"type": ["integer", "null"]},
        "confidence": {"type": "integer"},
    },
    "additionalProperties": True,
}

_CANCEL_PHRASES = frozenset({"取消", "算了", "不建了", "不要了", "取消待办"})


@dataclass
class TodoHandleResult:
    texts: list[str]
    card: dict | None = None
    todo: TodoItem | None = None


def default_timezone(db: Session, *, tenant_id: int) -> str:
    from app.services.app_timezone_service import get_app_timezone

    return get_app_timezone(db, tenant_id=tenant_id)


def get_clarifying_todo(
    db: Session, *, feishu_open_id: str, tenant_id: int = 1
) -> TodoItem | None:
    return db.execute(
        select(TodoItem).where(
            TodoItem.tenant_id == tenant_id,
            TodoItem.feishu_open_id == feishu_open_id,
            TodoItem.status == "clarifying",
            TodoItem.deleted_at.is_(None),
        )
    ).scalar_one_or_none()


def is_todo_cancel(text: str) -> bool:
    t = (text or "").strip()
    return t in _CANCEL_PHRASES or t.lower() in {"cancel", "cancel todo"}


async def parse_todo_intent(
    db: Session,
    *,
    user_message: str,
    tenant_id: int,
    timezone_name: str | None = None,
    context: list[dict] | None = None,
    override_model_id: int | None = None,
) -> tuple[dict, int, int]:
    tz_name = timezone_name or default_timezone(db, tenant_id=tenant_id)
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Asia/Shanghai")
        tz_name = "Asia/Shanghai"
    now_local = datetime.now(tz).strftime("%Y-%m-%d %H:%M %A")

    client, prompt = LLMClient.for_scene(
        db,
        "todo_intent_parsing",
        tenant_id=tenant_id,
        override_model_id=override_model_id,
    )
    rendered = (
        prompt.content.replace("{TIMEZONE}", tz_name)
        .replace("{NOW_LOCAL}", now_local)
        .replace("{CONTEXT_JSON}", json.dumps(context or [], ensure_ascii=False))
        .replace("{USER_MESSAGE}", user_message)
    )
    data, _ = await client.chat_json(
        [LLMMessage(role="user", content=rendered)],
        schema=TODO_INTENT_SCHEMA,
    )
    return data, prompt.id, client.model.id


def _parse_remind_at(iso_str: str | None, tz_name: str) -> datetime | None:
    if not iso_str or not str(iso_str).strip():
        return None
    raw = str(iso_str).strip()
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        try:
            dt = dt.replace(tzinfo=ZoneInfo(tz_name))
        except Exception:
            dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _local_date(remind_at: datetime | None, tz_name: str) -> date:
    """Local calendar day for a UTC-naive remind_at (or today if none)."""
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Asia/Shanghai")
    if remind_at is None:
        return datetime.now(tz).date()
    return remind_at.replace(tzinfo=timezone.utc).astimezone(tz).date()


def _format_remind_local(remind_at: datetime | None, tz_name: str) -> str:
    if remind_at is None:
        return "未设置"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Asia/Shanghai")
    local = remind_at.replace(tzinfo=timezone.utc).astimezone(tz)
    return local.strftime("%Y-%m-%d %H:%M")


def _combine_plan_datetime(
    plan_date: date,
    remind_time: str | None,
    tz_name: str,
    *,
    use_default: bool = True,
) -> datetime | None:
    """Combine local plan_date + HH:MM into UTC-naive remind_at.

    When remind_time is empty and use_default=True, falls back to DEFAULT_REMIND_TIME.
    """
    raw = (str(remind_time).strip() if remind_time else "") or (
        DEFAULT_REMIND_TIME if use_default else ""
    )
    if not raw:
        return None
    parts = raw.split(":")
    if len(parts) != 2:
        return None
    try:
        hh, mm = int(parts[0]), int(parts[1])
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            return None
    except ValueError:
        return None
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Asia/Shanghai")
    local = datetime(plan_date.year, plan_date.month, plan_date.day, hh, mm, tzinfo=tz)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def create_todo_direct(
    db: Session,
    *,
    tenant_id: int,
    title: str,
    plan_date: date,
    remind_time: str | None = None,
    description: str | None = None,
    channel: str = "web",
) -> TodoItem:
    """Create a todo from structured form fields (no LLM)."""
    tz_name = default_timezone(db, tenant_id=tenant_id)
    remind_at = _combine_plan_datetime(plan_date, remind_time, tz_name)
    item = TodoItem(
        tenant_id=tenant_id,
        title=title.strip()[:200],
        description=(description or "").strip()[:2000] or None,
        status="scheduled",
        remind_at=remind_at,
        timezone=tz_name,
        plan_date=plan_date,
        original_plan_date=plan_date,
        defer_count=0,
        raw_input=title.strip(),
        structured_json={"source": "web_form", "plan_date": plan_date.isoformat()},
        channel=channel,
    )
    db.add(item)
    db.flush()
    return item


async def handle_todo_message(
    db: Session,
    *,
    user_message: str,
    tenant_id: int = 1,
    feishu_open_id: str | None = None,
    feishu_message_id: str | None = None,
    channel: str = "feishu",
    existing: TodoItem | None = None,
) -> TodoHandleResult:
    user_message = (user_message or "").strip()
    if not user_message:
        return TodoHandleResult(texts=["请描述待办内容,例如:明天下午3点提醒我交周报"])

    tz_name = default_timezone(db, tenant_id=tenant_id)
    context: list[dict] = []
    if existing is not None:
        context = list(existing.clarification_context_json or [])
        context.append({"role": "assistant", "content": existing.clarification_question or ""})
    context.append({"role": "user", "content": user_message})

    data, prompt_id, model_id = await parse_todo_intent(
        db,
        user_message=user_message,
        tenant_id=tenant_id,
        timezone_name=tz_name,
        context=context[:-1] if existing else None,
    )

    intent = str(data.get("intent") or "unknown")
    if intent == "unknown" and existing is not None:
        intent = "create_todo"

    if intent == "cancel_draft" or (existing and is_todo_cancel(user_message)):
        if existing is not None:
            existing.status = "cancelled"
            db.flush()
        return TodoHandleResult(texts=["已取消,未创建待办。"])

    if intent == "list_todos":
        return TodoHandleResult(texts=[_format_todo_list(db, tenant_id=tenant_id, feishu_open_id=feishu_open_id)])

    if intent == "complete_todo":
        tid = data.get("todo_id")
        if tid is not None:
            item = get_todo(db, int(tid), tenant_id=tenant_id)
            if item is not None:
                mark_done(db, item)
                db.flush()
                return TodoHandleResult(texts=[f"✅ 待办 #{item.id}「{item.title}」已标记完成。"])
        return TodoHandleResult(texts=["请说明要完成哪条待办,例如:完成待办 3"])

    if intent not in ("create_todo", "unknown"):
        return TodoHandleResult(texts=["未能理解待办意图,请换种说法或发送「待办列表」查看。"])

    question = str(data.get("clarification_question") or "").strip()
    title = str(data.get("title") or "").strip()[:200]
    description = (str(data.get("description")).strip()[:2000] or None) if data.get("description") else None
    remind_at = _parse_remind_at(data.get("remind_at_iso"), tz_name)
    needs_clarification = bool(data.get("needs_clarification"))

    # Clarify when the title is missing or the model still needs more info.
    if not title or needs_clarification:
        draft = existing or TodoItem(
            tenant_id=tenant_id,
            title=title or "待办",
            status="clarifying",
            raw_input=user_message if existing is None else existing.raw_input,
            timezone=tz_name,
            channel=channel,
            feishu_open_id=feishu_open_id,
            feishu_message_id=feishu_message_id,
        )
        if existing is None:
            db.add(draft)
        draft.title = title or draft.title
        draft.description = description
        draft.structured_json = data
        draft.clarification_question = question or (
            "请问待办事项是什么?" if not title else "请补充待办的日期或提醒时间。"
        )
        draft.clarification_context_json = context
        draft.generated_by_prompt_id = prompt_id
        draft.generated_by_model_id = model_id
        db.flush()
        return TodoHandleResult(
            texts=[f"❓ {draft.clarification_question}\n(回复补充信息,或发送「取消」放弃)"],
            todo=draft,
        )

    if existing is not None:
        item = existing
    else:
        item = TodoItem(
            tenant_id=tenant_id,
            raw_input=user_message,
            channel=channel,
            feishu_open_id=feishu_open_id,
            feishu_message_id=feishu_message_id,
        )
        db.add(item)

    item.title = title
    item.description = description
    item.timezone = tz_name
    item.status = "scheduled"
    if remind_at is None:
        pdate = _local_date(None, tz_name)
        remind_at = _combine_plan_datetime(pdate, None, tz_name)
    else:
        pdate = _local_date(remind_at, tz_name)
    item.remind_at = remind_at
    item.plan_date = pdate
    if item.original_plan_date is None:
        item.original_plan_date = pdate
    item.structured_json = data
    item.clarification_question = None
    item.clarification_context_json = context
    item.generated_by_prompt_id = prompt_id
    item.generated_by_model_id = model_id
    db.flush()

    if remind_at is not None:
        when = _format_remind_local(remind_at, tz_name)
        tail = f"提醒: {when} ({tz_name})\n到点将通过飞书推送提醒。"
    else:
        tail = f"计划日期: {pdate.isoformat()}\n可在网页「待办」日历里查看或调整。"
    return TodoHandleResult(
        texts=[f"✅ 待办已记录 · ID={item.id}\n事项: {item.title}\n{tail}"],
        todo=item,
    )


def _format_todo_list(
    db: Session, *, tenant_id: int, feishu_open_id: str | None = None
) -> str:
    """Today's open tasks for the tenant (matches web calendar), plus clarifying drafts."""
    tz = default_timezone(db, tenant_id=tenant_id)
    today = _local_date(None, tz)
    run_deferrals(db, tenant_id=tenant_id, today=today)

    rows = open_tasks_for_date(db, tenant_id=tenant_id, day=today)
    if feishu_open_id:
        extra, _ = list_todos(
            db,
            tenant_id=tenant_id,
            feishu_open_id=feishu_open_id,
            statuses=["clarifying"],
            limit=10,
        )
        seen = {t.id for t in rows}
        for t in extra:
            if t.id not in seen:
                rows.append(t)

    if not rows:
        return f"📋 今日({today})暂无待办。发送「待办 明天3点提醒我…」或在网页日历添加。"
    lines = [f"📋 今日待办 ({today}):"]
    for t in rows:
        st = {"clarifying": "待补充", "scheduled": "待办", "reminded": "已提醒"}.get(
            t.status, t.status
        )
        when = _format_remind_local(t.remind_at, t.timezone) if t.remind_at else "-"
        tags: list[str] = []
        if (t.defer_count or 0) > 0 and t.original_plan_date:
            tags.append(f"顺延自{t.original_plan_date}")
        if t.plan_id:
            tags.append("计划")
        if t.long_term_id:
            tags.append("长期")
        tag_s = f" ({' · '.join(tags)})" if tags else ""
        lines.append(f"· #{t.id} [{st}] {t.title} — {when}{tag_s}")
    lines.append("\n完成某条: 发送「完成待办 ID」")
    return "\n".join(lines)


def list_todos(
    db: Session,
    *,
    tenant_id: int,
    feishu_open_id: str | None = None,
    statuses: list[str] | None = None,
    plan_date: date | None = None,
    plan_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[TodoItem], int]:
    base = select(TodoItem).where(
        TodoItem.tenant_id == tenant_id,
        TodoItem.deleted_at.is_(None),
    )
    if feishu_open_id:
        base = base.where(TodoItem.feishu_open_id == feishu_open_id)
    if statuses:
        base = base.where(TodoItem.status.in_(statuses))
    if plan_date is not None:
        base = base.where(
            or_(
                TodoItem.plan_date == plan_date,
                and_(
                    TodoItem.original_plan_date == plan_date,
                    TodoItem.status.in_(_ACTIVE_TODO_STATUSES),
                ),
            )
        )
    if plan_id is not None:
        base = base.where(TodoItem.plan_id == plan_id)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(
        base.order_by(
            TodoItem.plan_date.asc().nulls_last(),
            TodoItem.remind_at.asc().nulls_last(),
            TodoItem.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    ).scalars().all()
    return list(rows), int(total)


def calendar_counts(
    db: Session, *, tenant_id: int, start: date, end: date
) -> list[dict]:
    """Per-day task counts in [start, end] for the calendar heatmap."""
    rows = db.execute(
        select(TodoItem).where(
            TodoItem.tenant_id == tenant_id,
            TodoItem.deleted_at.is_(None),
            TodoItem.status != "cancelled",
            or_(
                and_(
                    TodoItem.plan_date.isnot(None),
                    TodoItem.plan_date >= start,
                    TodoItem.plan_date <= end,
                ),
                and_(
                    TodoItem.original_plan_date.isnot(None),
                    TodoItem.original_plan_date >= start,
                    TodoItem.original_plan_date <= end,
                ),
            ),
        )
    ).scalars().all()
    span = (end - start).days
    counts: dict[str, dict[str, int]] = {
        (start + timedelta(days=i)).isoformat(): {"total": 0, "done": 0}
        for i in range(span + 1)
    }
    for item in rows:
        for i in range(span + 1):
            day = start + timedelta(days=i)
            if not _todo_belongs_to_day(item, day):
                continue
            bucket = counts[day.isoformat()]
            bucket["total"] += 1
            if item.status == "done":
                bucket["done"] += 1
    return [{"date": d, **counts[d]} for d in sorted(counts)]


def snooze_todo(
    db: Session, item: TodoItem, *, until: date, note: str | None = None
) -> TodoItem:
    item.status = "snoozed"
    item.snooze_until = until
    item.snooze_note = (note or "").strip() or None
    db.flush()
    return item


def unsnooze_todo(db: Session, item: TodoItem, *, today: date | None = None) -> TodoItem:
    today = today or date.today()
    item.status = "scheduled"
    item.plan_date = item.snooze_until or today
    item.remind_at = _combine_plan_datetime(
        item.plan_date, None, item.timezone or default_timezone(db, tenant_id=item.tenant_id)
    )
    if item.original_plan_date is None:
        item.original_plan_date = item.plan_date
    item.snooze_until = None
    item.snooze_note = None
    db.flush()
    return item


def can_edit_todo(item: TodoItem, *, today: date | None = None) -> bool:
    if item.deleted_at is not None or item.status == "cancelled":
        return False
    if item.status in ("done", "clarifying"):
        return True
    if item.plan_date is None:
        return False
    return item.plan_date >= (today or date.today())


def update_todo(
    db: Session,
    item: TodoItem,
    *,
    title: str | None = None,
    plan_date: date | None = None,
    remind_time: str | None = None,
    description: str | None = None,
) -> TodoItem:
    if not can_edit_todo(item):
        raise ValueError("仅可编辑今天及以后的待办")
    tz_name = item.timezone or default_timezone(db, tenant_id=item.tenant_id)
    if title is not None:
        item.title = title.strip()[:200]
    if description is not None:
        item.description = description.strip()[:2000] or None
    if plan_date is not None:
        item.plan_date = plan_date
    pdate = item.plan_date or date.today()
    if remind_time is not None:
        import re

        if not re.match(r"^([01]?\d|2[0-3]):([0-5]\d)$", str(remind_time).strip()):
            raise ValueError("提醒时间格式无效，请使用 HH:MM")
        item.remind_at = _combine_plan_datetime(pdate, remind_time, tz_name)
    elif plan_date is not None and item.remind_at is not None:
        from app.services.app_timezone_service import local_hhmm_from_remind_at

        hhmm = local_hhmm_from_remind_at(item.remind_at, tz_name)
        item.remind_at = _combine_plan_datetime(pdate, hhmm, tz_name)
    elif item.remind_at is None and item.plan_date is not None:
        item.remind_at = _combine_plan_datetime(pdate, remind_time or DEFAULT_REMIND_TIME, tz_name)
    if item.status == "clarifying" and item.title.strip() and item.plan_date:
        item.status = "scheduled"
        item.clarification_question = None
        item.clarification_context_json = []
    db.flush()
    return item


def run_deferrals(
    db: Session, *, tenant_id: int | None = None, today: date | None = None
) -> int:
    """Roll overdue, unfinished tasks forward to today; wake due snoozed tasks.

    Returns number of tasks affected. defer_count is derived from the gap between
    original_plan_date and today so it is correct regardless of run cadence.
    """
    if today is None and tenant_id is not None:
        today = _local_date(None, default_timezone(db, tenant_id=tenant_id))
    today = today or date.today()
    affected = 0

    wake_q = select(TodoItem).where(
        TodoItem.deleted_at.is_(None),
        TodoItem.status == "snoozed",
        TodoItem.snooze_until.isnot(None),
        TodoItem.snooze_until <= today,
    )
    if tenant_id is not None:
        wake_q = wake_q.where(TodoItem.tenant_id == tenant_id)
    for item in db.execute(wake_q).scalars().all():
        item.status = "scheduled"
        item.plan_date = item.snooze_until or today
        item.remind_at = _combine_plan_datetime(
            item.plan_date, None, item.timezone or "Asia/Shanghai"
        )
        item.snooze_until = None
        item.snooze_note = None
        affected += 1

    # Only plan-decomposed tasks roll over; ad-hoc timed reminders keep their
    # own remind_at semantics and are not disturbed here.
    overdue_q = select(TodoItem).where(
        TodoItem.deleted_at.is_(None),
        TodoItem.status.in_(["scheduled", "reminded"]),
        or_(TodoItem.plan_id.isnot(None), TodoItem.long_term_id.isnot(None)),
        TodoItem.plan_date.isnot(None),
        TodoItem.plan_date < today,
    )
    if tenant_id is not None:
        overdue_q = overdue_q.where(TodoItem.tenant_id == tenant_id)
    for item in db.execute(overdue_q).scalars().all():
        if item.original_plan_date is None:
            item.original_plan_date = item.plan_date
        item.plan_date = today
        item.remind_at = _combine_plan_datetime(
            today, None, item.timezone or "Asia/Shanghai"
        )
        item.status = "scheduled"
        item.defer_count = max(0, (today - item.original_plan_date).days)
        affected += 1

    if affected:
        db.flush()
    return affected


def run_deferrals_all_tenants(db: Session) -> int:
    """Roll overdue plan/long-term tasks for every tenant (app timezone)."""
    from app.models.tenant import Tenant

    total = 0
    for tid in db.execute(select(Tenant.id)).scalars().all():
        total += run_deferrals(db, tenant_id=int(tid))
    return total


def open_tasks_for_date(
    db: Session, *, tenant_id: int, day: date
) -> list[TodoItem]:
    """Not-done, not-cancelled tasks scheduled for a given day."""
    return list(
        db.execute(
            select(TodoItem)
            .where(
                TodoItem.tenant_id == tenant_id,
                TodoItem.deleted_at.is_(None),
                TodoItem.plan_date == day,
                TodoItem.status.in_(["scheduled", "reminded"]),
            )
            .order_by(TodoItem.defer_count.desc(), TodoItem.id.asc())
        ).scalars().all()
    )


async def motivation_line(
    db: Session, *, tenant_id: int, task_title: str, defer_days: int
) -> str:
    """One-line LLM encouragement for a long-overdue task (best-effort)."""
    try:
        client, prompt = LLMClient.for_scene(db, "todo_motivation", tenant_id=tenant_id)
        rendered = prompt.content.replace("{TASK_TITLE}", task_title).replace(
            "{DEFER_DAYS}", str(defer_days)
        )
        resp = await client.chat([LLMMessage(role="user", content=rendered)])
        return (resp.text or "").strip().strip('"').replace("\n", " ")[:60]
    except LLMError as exc:
        log.warning("motivation LLM failed: %s", exc)
        return ""


def get_todo(db: Session, todo_id: int, *, tenant_id: int) -> TodoItem | None:
    return db.execute(
        select(TodoItem).where(
            TodoItem.id == todo_id,
            TodoItem.tenant_id == tenant_id,
            TodoItem.deleted_at.is_(None),
        )
    ).scalar_one_or_none()


def mark_done(db: Session, item: TodoItem) -> TodoItem:
    item.status = "done"
    item.progress = 100
    item.completed_at = datetime.utcnow()
    db.flush()
    return item


def snap_progress(progress: int) -> int:
    """Snap to 5-step slider: 0, 25, 50, 75, 100."""
    p = max(0, min(100, int(progress)))
    return int(round(p / 25) * 25)


def set_todo_progress(db: Session, item: TodoItem, progress: int) -> TodoItem:
    """Update progress on web. 100% marks done; lowering from 100% reopens the todo."""
    if item.status in ("cancelled", "clarifying", "snoozed"):
        raise ValueError("当前状态不可更新进度")
    p = snap_progress(progress)
    item.progress = p
    if p >= 100:
        item.status = "done"
        item.completed_at = datetime.utcnow()
    elif item.status == "done":
        item.status = "reminded" if item.reminded_at else "scheduled"
        item.completed_at = None
    db.flush()
    return item


def cancel_todo(db: Session, item: TodoItem) -> TodoItem:
    item.status = "cancelled"
    db.flush()
    return item


def restore_todo(db: Session, item: TodoItem) -> TodoItem:
    if item.status != "cancelled":
        raise ValueError("仅已取消的待办可撤销")
    item.status = "scheduled"
    item.progress = 0
    db.flush()
    return item


def delete_todo(db: Session, item: TodoItem) -> None:
    item.deleted_at = datetime.utcnow()
    db.flush()


def due_todos(db: Session, *, tenant_id: int | None = None, now: datetime | None = None) -> list[TodoItem]:
    now = now or datetime.utcnow()
    q = select(TodoItem).where(
        TodoItem.deleted_at.is_(None),
        TodoItem.status == "scheduled",
        TodoItem.remind_at.isnot(None),
        TodoItem.remind_at <= now,
    )
    if tenant_id is not None:
        q = q.where(TodoItem.tenant_id == tenant_id)
    return list(db.execute(q.order_by(TodoItem.remind_at.asc())).scalars().all())


async def run_due_todo_reminders(db: Session) -> None:
    from app.core.config import get_settings
    from app.integrations.feishu import client as feishu_client
    from app.integrations.feishu import formatters
    from app.services.push_schedule_service import _feishu_recipients

    settings = get_settings()
    if not settings.feishu_bot_enabled:
        return

    items = due_todos(db)
    if not items:
        return

    recipients_by_open_id = {
        s.feishu_open_id: s
        for s in _feishu_recipients(db, settings)
    }
    broadcast_sessions = list(recipients_by_open_id.values())

    for item in items:
        if item.plan_id or item.long_term_id:
            targets = broadcast_sessions
        elif item.feishu_open_id:
            session = recipients_by_open_id.get(item.feishu_open_id)
            targets = [session] if session else []
        else:
            targets = []

        if not targets:
            item.status = "reminded"
            item.reminded_at = datetime.utcnow()
            log.warning(
                "todo #%s: no feishu recipient (open_id=%s plan=%s long_term=%s)",
                item.id,
                item.feishu_open_id,
                item.plan_id,
                item.long_term_id,
            )
            continue
        card = formatters.todo_reminder_card(item)
        sent_any = False
        for session in targets:
            try:
                await feishu_client.send_interactive_card_to_chat(
                    session.feishu_chat_id, card, settings=settings
                )
                sent_any = True
            except Exception as exc:
                log.warning(
                    "todo reminder failed id=%s chat=%s: %s",
                    item.id,
                    session.feishu_chat_id,
                    exc,
                )
        if sent_any:
            item.status = "reminded"
            item.reminded_at = datetime.utcnow()
            log.info("todo reminder sent id=%s targets=%s", item.id, len(targets))

    db.flush()
