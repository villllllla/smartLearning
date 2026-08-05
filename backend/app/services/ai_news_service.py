"""AI-news schedule: config, due detection, fetch+curate+persist+Feishu push."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import AiNewsDigest, AiNewsItem, AiNewsSchedule
from app.services.ai_news.aggregator import CurationResult, _norm_url, curate_ai_news

log = logging.getLogger(__name__)

_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_VALID_FREQ = frozenset({"daily", "weekdays", "weekly"})


def get_or_create_schedule(db: Session, *, tenant_id: int) -> AiNewsSchedule:
    row = db.execute(
        select(AiNewsSchedule).where(AiNewsSchedule.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if row is None:
        row = AiNewsSchedule(
            tenant_id=tenant_id, push_times=["09:00"], weekdays=[], rss_feeds=[]
        )
        db.add(row)
        db.flush()
    from app.services.app_timezone_service import apply_schedule_timezone

    apply_schedule_timezone(db, tenant_id=tenant_id, row=row)
    return row


def parse_push_times(times: list[str]) -> list[str]:
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
        raise ValueError(f"推送时间格式无效: {', '.join(bad)}，请使用 HH:MM")
    if not out:
        raise ValueError("至少设置一个推送时间，格式 HH:MM")
    return sorted(set(out))


def _clean_feeds(feeds: list) -> list[dict]:
    out: list[dict] = []
    for f in feeds or []:
        if hasattr(f, "model_dump"):
            f = f.model_dump()
        url = str((f or {}).get("url") or "").strip()
        name = str((f or {}).get("name") or "").strip() or url
        if url.startswith("http"):
            out.append({"name": name, "url": url})
    return out


def update_schedule(db: Session, *, tenant_id: int, **fields) -> AiNewsSchedule:
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
    if fields.get("top_n") is not None:
        row.top_n = max(1, min(15, int(fields["top_n"])))
    if fields.get("enable_hackernews") is not None:
        row.enable_hackernews = bool(fields["enable_hackernews"])
    if fields.get("enable_github") is not None:
        row.enable_github = bool(fields["enable_github"])
    if fields.get("enable_arxiv") is not None:
        row.enable_arxiv = bool(fields["enable_arxiv"])
    if fields.get("enable_huggingface") is not None:
        row.enable_huggingface = bool(fields["enable_huggingface"])
    if fields.get("enable_reddit") is not None:
        row.enable_reddit = bool(fields["enable_reddit"])
    if fields.get("rss_feeds") is not None:
        row.rss_feeds = _clean_feeds(list(fields["rss_feeds"]))
    if fields.get("dedup_days") is not None:
        row.dedup_days = max(0, min(90, int(fields["dedup_days"])))
    if fields.get("feishu_enabled") is not None:
        row.feishu_enabled = bool(fields["feishu_enabled"])
    from app.services.app_timezone_service import apply_schedule_timezone

    apply_schedule_timezone(db, tenant_id=tenant_id, row=row)
    db.flush()
    return row


def schedule_summary(row: AiNewsSchedule) -> str:
    times = "、".join(row.push_times) if row.push_times else "未设置"
    freq_label = {"daily": "每天", "weekdays": "工作日", "weekly": "每周指定日"}.get(
        row.frequency, row.frequency
    )
    status = "已开启" if row.enabled else "已关闭"
    sources = []
    if row.enable_hackernews:
        sources.append("HackerNews")
    if row.enable_github:
        sources.append("GitHub Trending")
    if row.enable_arxiv:
        sources.append("arXiv")
    if row.enable_huggingface:
        sources.append("HuggingFace")
    if row.enable_reddit:
        sources.append("Reddit")
    n_feeds = len(row.rss_feeds or [])
    sources.append(f"RSS×{n_feeds if n_feeds else '默认'}")
    lines = [
        f"AI 资讯推送: {status}",
        f"时间: {times} ({row.timezone})",
        f"频率: {freq_label} · 每次 Top{row.top_n}",
        f"来源: {'、'.join(sources)}",
        f"飞书推送: {'开' if row.feishu_enabled else '关'}",
    ]
    if row.last_run_at:
        lines.append(f"上次推送: {row.last_run_at.strftime('%Y-%m-%d %H:%M')}")
    if row.last_error:
        lines.append(f"上次错误: {row.last_error[:200]}")
    return "\n".join(lines)


def is_due_now(row: AiNewsSchedule, now: datetime | None = None, *, db: Session) -> str | None:
    if not row.enabled or not row.push_times:
        return None
    from app.services.app_timezone_service import get_app_timezone

    try:
        tz = ZoneInfo(get_app_timezone(db, tenant_id=row.tenant_id))
    except Exception:
        tz = ZoneInfo("Asia/Shanghai")
    local = (now or datetime.now(tz)).astimezone(tz)
    wd = local.weekday()
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


def _recent_pushed_urls(db: Session, *, tenant_id: int, days: int) -> set[str]:
    if days <= 0:
        return set()
    since = datetime.utcnow() - timedelta(days=days)
    rows = db.execute(
        select(AiNewsItem.url).where(
            AiNewsItem.tenant_id == tenant_id,
            AiNewsItem.created_at >= since,
        )
    ).scalars().all()
    return {_norm_url(u) for u in rows if u}


def _persist_digest(
    db: Session,
    *,
    tenant_id: int,
    result: CurationResult,
    channel: str,
    slot: str | None,
) -> AiNewsDigest:
    digest = AiNewsDigest(
        tenant_id=tenant_id,
        run_slot=slot,
        item_count=len(result.items),
        total_candidates=result.total_candidates,
        used_llm=result.used_llm,
        channel=channel,
    )
    db.add(digest)
    db.flush()
    for i, it in enumerate(result.items):
        db.add(
            AiNewsItem(
                digest_id=digest.id,
                tenant_id=tenant_id,
                rank=i + 1,
                title=it.title,
                original_title=it.original_title,
                url=it.url,
                source=it.source,
                summary=it.summary,
                heat_score=it.heat_score,
                why=it.why or None,
                raw_score=it.raw_score,
                published_at=it.published_at,
            )
        )
    db.flush()
    db.refresh(digest)
    return digest


async def execute_news_push(
    db: Session,
    row: AiNewsSchedule,
    *,
    settings: Settings | None = None,
    slot: str | None = None,
    manual: bool = False,
) -> tuple[int, int, str, int | None]:
    """Fetch + curate + persist, then push to Feishu. Returns (items, recipients, msg, digest_id)."""
    from app.integrations.feishu import client as feishu_client
    from app.integrations.feishu import formatters
    from app.services.push_schedule_service import _feishu_recipients

    settings = settings or get_settings()
    if row.feishu_enabled and not settings.feishu_bot_enabled:
        raise RuntimeError("飞书 Bot 未启用 (SL_FEISHU_BOT_ENABLED)")

    exclude = _recent_pushed_urls(db, tenant_id=row.tenant_id, days=row.dedup_days)
    result = await curate_ai_news(
        db,
        tenant_id=row.tenant_id,
        top_n=row.top_n,
        enable_hackernews=row.enable_hackernews,
        enable_github=row.enable_github,
        enable_arxiv=row.enable_arxiv,
        enable_huggingface=row.enable_huggingface,
        enable_reddit=row.enable_reddit,
        rss_feeds=list(row.rss_feeds or []) or None,
        exclude_urls=exclude,
    )

    if not result.items:
        msg = "未抓到新的 AI 资讯（可能是来源不可达或已全部推送过）"
        row.last_error = None
        if slot:
            row.last_run_slot = slot
        row.last_run_at = datetime.utcnow()
        db.flush()
        return 0, 0, msg, None

    digest = _persist_digest(
        db,
        tenant_id=row.tenant_id,
        result=result,
        channel="feishu" if row.feishu_enabled else ("manual" if manual else "web"),
        slot=slot,
    )

    sent = 0
    if row.feishu_enabled:
        recipients = _feishu_recipients(db, settings)
        if not recipients:
            raise RuntimeError(
                "没有可推送的飞书会话。请先在飞书私聊机器人发一条消息，并配置 SL_FEISHU_ALLOWED_OPEN_IDS"
            )
        card = formatters.ai_news_card(digest, manual=manual)
        for session in recipients:
            try:
                await feishu_client.send_interactive_card_to_chat(
                    session.feishu_chat_id, card, settings=settings
                )
                sent += 1
            except Exception as exc:
                log.warning("ai_news push to %s failed: %s", session.feishu_open_id, exc)

    row.last_error = None
    if slot:
        row.last_run_slot = slot
    row.last_run_at = datetime.utcnow()
    db.flush()
    src_note = "（模型精选）" if result.used_llm else "（按热度排序）"
    msg = f"已推送 {len(result.items)} 条 AI 资讯到 {sent} 个飞书用户{src_note}"
    return len(result.items), sent, msg, digest.id


async def run_due_ai_news(db: Session) -> None:
    settings = get_settings()
    if not settings.feishu_bot_enabled:
        return
    rows = db.execute(
        select(AiNewsSchedule).where(
            AiNewsSchedule.enabled.is_(True),
            AiNewsSchedule.feishu_enabled.is_(True),
        )
    ).scalars().all()
    for row in rows:
        slot = is_due_now(row, db=db)
        if slot is None:
            continue
        try:
            await execute_news_push(db, row, settings=settings, slot=slot)
            db.commit()
            log.info("scheduled ai_news ok tenant=%s slot=%s", row.tenant_id, slot)
        except Exception as exc:
            row.last_error = str(exc)[:500]
            row.last_run_slot = slot
            row.last_run_at = datetime.utcnow()
            db.commit()
            log.warning("scheduled ai_news failed tenant=%s: %s", row.tenant_id, exc)
