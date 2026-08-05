"""Scheduled question push: config, due detection, execution."""
from __future__ import annotations

import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import BotSession, QuestionPushSchedule, Tag
from app.services import bot_facade

log = logging.getLogger(__name__)

_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_VALID_FREQ = frozenset({"daily", "weekdays", "weekly"})
_VALID_MODES = frozenset({"random", "sequential", "wrong"})


def get_or_create_schedule(db: Session, *, tenant_id: int) -> QuestionPushSchedule:
    row = db.execute(
        select(QuestionPushSchedule).where(QuestionPushSchedule.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if row is None:
        row = QuestionPushSchedule(tenant_id=tenant_id, push_times=["09:00"])
        db.add(row)
        db.flush()
    from app.services.app_timezone_service import apply_schedule_timezone

    apply_schedule_timezone(db, tenant_id=tenant_id, row=row)
    return row


def parse_push_times(times: list[str]) -> list[str]:
    """Parse and normalize push times; reject any invalid token."""
    if not times:
        raise ValueError("至少设置一个推送时间，格式 HH:MM（如 09:00）")
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
        raise ValueError(
            f"推送时间格式无效: {', '.join(bad)}，请使用 HH:MM（如 09:00、18:30）"
        )
    if not out:
        raise ValueError("至少设置一个推送时间，格式 HH:MM（如 09:00）")
    return sorted(set(out))


def update_schedule(
    db: Session,
    *,
    tenant_id: int,
    **fields,
) -> QuestionPushSchedule:
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
    if fields.get("limit") is not None:
        row.limit = max(1, min(20, int(fields["limit"])))
    if fields.get("mode") is not None:
        mode = str(fields["mode"]).lower()
        if mode not in _VALID_MODES:
            raise ValueError("mode 须为 random / sequential / wrong")
        row.mode = mode
    if fields.get("difficulties") is not None:
        row.difficulties = list(fields["difficulties"])
    if fields.get("qtypes") is not None:
        row.qtypes = list(fields["qtypes"])
    if fields.get("tag_ids") is not None:
        row.tag_ids = list(fields["tag_ids"])
    if fields.get("tag_mode") is not None:
        row.tag_mode = str(fields["tag_mode"]).lower()
    if fields.get("source_kinds") is not None:
        kinds = [str(k) for k in fields["source_kinds"] if str(k) in ("simulated", "interview")]
        row.source_kinds = kinds
    if fields.get("feishu_enabled") is not None:
        row.feishu_enabled = bool(fields["feishu_enabled"])
    from app.services.app_timezone_service import apply_schedule_timezone

    apply_schedule_timezone(db, tenant_id=tenant_id, row=row)
    db.flush()
    return row


def schedule_summary(row: QuestionPushSchedule) -> str:
    times = "、".join(row.push_times) if row.push_times else "未设置"
    freq_label = {"daily": "每天", "weekdays": "工作日", "weekly": "每周指定日"}.get(
        row.frequency, row.frequency
    )
    diff = ",".join(row.difficulties) if row.difficulties else "不限"
    qt = ",".join(row.qtypes) if row.qtypes else "不限"
    sk = ",".join(row.source_kinds) if getattr(row, "source_kinds", None) else "不限"
    status = "已开启" if row.enabled else "已关闭"
    lines = [
        f"定时推题: {status}",
        f"时间: {times} ({row.timezone})",
        f"频率: {freq_label}",
        f"每次 {row.limit} 题 · 模式 {row.mode} · 难度 {diff} · 类型 {qt} · 来源 {sk}",
        f"飞书推送: {'开' if row.feishu_enabled else '关'}",
    ]
    if row.frequency == "weekly" and row.weekdays:
        day_names = "一二三四五六日"
        days = "".join(day_names[d] for d in sorted(row.weekdays) if 0 <= d <= 6)
        lines.append(f"推送日: 周{days}")
    if row.last_run_at:
        lines.append(f"上次推送: {row.last_run_at.strftime('%Y-%m-%d %H:%M')}")
    if row.last_error:
        lines.append(f"上次错误: {row.last_error[:200]}")
    return "\n".join(lines)


def _weekday_index(dt: datetime) -> int:
    """Monday=0 .. Sunday=6."""
    return dt.weekday()


def is_due_now(
    row: QuestionPushSchedule, now: datetime | None = None, *, db: Session
) -> str | None:
    """Return slot key if push should run now, else None."""
    if not row.enabled or not row.push_times:
        return None
    from app.services.app_timezone_service import get_app_timezone

    try:
        tz = ZoneInfo(get_app_timezone(db, tenant_id=row.tenant_id))
    except Exception:
        tz = ZoneInfo("Asia/Shanghai")
    local = (now or datetime.now(tz)).astimezone(tz)
    wd = _weekday_index(local)
    if row.frequency == "weekdays" and wd >= 5:
        return None
    if row.frequency == "weekly":
        allowed = row.weekdays or [0, 1, 2, 3, 4]
        if wd not in allowed:
            return None
    hhmm = local.strftime("%H:%M")
    if hhmm not in row.push_times:
        return None
    slot = f"{local.strftime('%Y-%m-%d')}T{hhmm}"
    if row.last_run_slot == slot:
        return None
    return slot


def _resolve_tag_ids(db: Session, *, tenant_id: int, tag_ids: list[int]) -> list[int]:
    if not tag_ids:
        return []
    rows = db.execute(
        select(Tag.id).where(Tag.tenant_id == tenant_id, Tag.id.in_(tag_ids))
    ).scalars().all()
    return list(rows)


def _feishu_recipients(db: Session, settings: Settings) -> list[BotSession]:
    allowed = set(settings.feishu_allowed_open_ids_list)
    if not allowed:
        return []
    rows = db.execute(
        select(BotSession).where(
            BotSession.platform == "feishu",
            BotSession.feishu_open_id.in_(allowed),
            BotSession.feishu_chat_id.isnot(None),
        )
    ).scalars().all()
    return [r for r in rows if r.feishu_chat_id]


async def execute_push(
    db: Session,
    row: QuestionPushSchedule,
    *,
    settings: Settings | None = None,
    slot: str | None = None,
    manual: bool = False,
) -> tuple[int, int, str]:
    """Draw questions and send to Feishu. Returns (question_count, recipient_count, message)."""
    from app.integrations.feishu import client as feishu_client
    from app.integrations.feishu import formatters

    settings = settings or get_settings()
    if row.feishu_enabled and not settings.feishu_bot_enabled:
        raise RuntimeError("飞书 Bot 未启用 (SL_FEISHU_BOT_ENABLED)")

    tag_ids = _resolve_tag_ids(db, tenant_id=row.tenant_id, tag_ids=row.tag_ids or [])
    questions = bot_facade.draw_questions(
        db,
        tenant_id=row.tenant_id,
        limit=row.limit,
        mode=row.mode,
        difficulties=row.difficulties or None,
        qtypes=row.qtypes or None,
        tag_ids=tag_ids or None,
        tag_mode=row.tag_mode or "or",
        source_kinds=getattr(row, "source_kinds", None) or None,
    )
    if not questions:
        msg = "题库为空或筛选无题，未推送"
        row.last_error = msg
        if slot:
            row.last_run_slot = slot
        row.last_run_at = datetime.utcnow()
        db.flush()
        return 0, 0, msg

    hint = " [定时推送]" if not manual else " [立即推送]"
    texts = formatters.format_questions_batch(questions, pool_hint=hint)
    if texts:
        texts[0] = "📅 SmartLearning 面试题推送\n\n" + texts[0]

    sent = 0
    if row.feishu_enabled:
        recipients = _feishu_recipients(db, settings)
        if not recipients:
            raise RuntimeError(
                "没有可推送的飞书会话。请先在飞书私聊机器人发一条消息，并配置 SL_FEISHU_ALLOWED_OPEN_IDS"
            )
        for session in recipients:
            try:
                for chunk in texts:
                    await feishu_client.send_text_to_chat(
                        session.feishu_chat_id, chunk, settings=settings
                    )
                sent += 1
            except Exception as exc:
                log.warning("push to %s failed: %s", session.feishu_open_id, exc)

    row.last_error = None
    if slot:
        row.last_run_slot = slot
    row.last_run_at = datetime.utcnow()
    db.flush()
    msg = f"已推送 {len(questions)} 道题到 {sent} 个飞书用户"
    return len(questions), sent, msg


async def run_due_pushes(db: Session) -> None:
    settings = get_settings()
    if not settings.feishu_bot_enabled:
        return
    rows = db.execute(
        select(QuestionPushSchedule).where(
            QuestionPushSchedule.enabled.is_(True),
            QuestionPushSchedule.feishu_enabled.is_(True),
        )
    ).scalars().all()
    for row in rows:
        slot = is_due_now(row, db=db)
        if slot is None:
            continue
        try:
            await execute_push(db, row, settings=settings, slot=slot)
            db.commit()
            log.info("scheduled push ok tenant=%s slot=%s", row.tenant_id, slot)
        except Exception as exc:
            row.last_error = str(exc)[:500]
            row.last_run_slot = slot
            row.last_run_at = datetime.utcnow()
            db.commit()
            log.warning("scheduled push failed tenant=%s: %s", row.tenant_id, exc)
