"""Feishu event webhook endpoint."""
from __future__ import annotations

import json
import logging
import time
from collections import OrderedDict

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import SessionLocal, get_db
from app.integrations.feishu import agent, client, commands, verify
from app.integrations.feishu.dedup import try_claim_message
from app.services.bot_session_service import get_or_create_session

log = logging.getLogger(__name__)

router = APIRouter()

# In-memory dedup caches (event_id / message_id -> True), max 2000 entries each.
# Cleared on process restart; paired with immediate HTTP 200 to avoid Feishu retries.
_seen_events: OrderedDict[str, bool] = OrderedDict()
_seen_messages: OrderedDict[str, bool] = OrderedDict()
_DEDUP_MAX = 2000


def _remember_key(key: str, cache: OrderedDict[str, bool]) -> bool:
    """Return True if this key was already seen."""
    if not key:
        return False
    if key in cache:
        return True
    cache[key] = True
    while len(cache) > _DEDUP_MAX:
        cache.popitem(last=False)
    return False


def _is_duplicate(event_id: str, message_id: str) -> bool:
    if _remember_key(event_id, _seen_events):
        return True
    if _remember_key(message_id, _seen_messages):
        return True
    return False


_CARD_TOAST_BY_CMD = {
    "复习要点": "已展开要点 👇",
    "复习掌握": "已标记为已掌握,复习频率降低",
    "复习加强": "好的,会尽快再次推送",
    "todo_done": "已标记完成",
    "todo_snooze": "好的,稍后再提醒",
    "todo_hold": "已挂起 3 天",
}


def _extract_card_action(payload: dict) -> dict | None:
    """Normalize a Feishu card button callback (v2 event or legacy) → action info.

    Returns dict with keys: value(dict), open_id, message_id, chat_id — or None.
    """
    header = payload.get("header") or {}
    event_type = header.get("event_type", "")
    # Card callback 2.0: delivered as `card.action.trigger` event.
    if event_type == "card.action.trigger":
        event = payload.get("event") or {}
        action = event.get("action") or {}
        operator = event.get("operator") or {}
        context = event.get("context") or {}
        return {
            "value": action.get("value") or {},
            "open_id": operator.get("open_id") or operator.get("user_id") or "",
            "message_id": context.get("open_message_id") or "",
            "chat_id": context.get("open_chat_id") or "",
        }
    # Legacy interactive card callback: top-level `action`.
    if "action" in payload and isinstance(payload.get("action"), dict):
        action = payload["action"]
        return {
            "value": action.get("value") or {},
            "open_id": payload.get("open_id") or payload.get("user_id") or "",
            "message_id": payload.get("open_message_id") or "",
            "chat_id": payload.get("open_chat_id") or "",
        }
    return None


async def _process_card_action(
    *,
    open_id: str,
    chat_id: str,
    message_id: str,
    value_text: str,
) -> None:
    """Run the card button's tool after the callback has returned its toast."""
    settings = get_settings()
    db = SessionLocal()
    try:
        result = await agent.handle_incoming_text(
            db,
            settings,
            open_id=open_id,
            chat_id=chat_id,
            text=value_text,
            message_id=message_id or None,
        )
        db.commit()
        if not message_id:
            return
        for chunk in result.texts:
            try:
                await client.reply_text(message_id, chunk, settings=settings)
            except Exception:
                log.warning("card action reply failed", exc_info=True)
        if result.card:
            try:
                await client.reply_interactive_card(message_id, result.card, settings=settings)
            except Exception:
                log.warning("card action card reply failed", exc_info=True)
    except Exception:
        log.exception("card action processing failed")
    finally:
        db.close()


def _check_open_id_allowed(settings: Settings, open_id: str) -> None:
    allowed = settings.feishu_allowed_open_ids_list
    if not allowed:
        raise HTTPException(
            503,
            detail="SL_FEISHU_ALLOWED_OPEN_IDS is not configured",
        )
    if open_id not in allowed:
        raise HTTPException(403, detail="feishu user not in allowlist")


async def _process_feishu_message(
    *,
    event_id: str,
    message_id: str,
    open_id: str,
    chat_id: str,
    text: str,
) -> None:
    """Handle one user message after the webhook has already returned 200."""
    settings = get_settings()
    db = SessionLocal()
    log.info(
        "feishu processing message_id=%s event_id=%s text=%r",
        message_id,
        event_id,
        (text or "")[:80],
    )
    try:
        session = get_or_create_session(
            db, platform="feishu", feishu_open_id=open_id, feishu_chat_id=chat_id
        )
        session.last_event_id = event_id
        db.commit()

        try:
            await client.reply_text(message_id, "思考中…", settings=settings)
        except Exception:
            log.debug("could not send thinking indicator", exc_info=True)

        try:
            result = await agent.handle_incoming_text(
                db,
                settings,
                open_id=open_id,
                chat_id=chat_id,
                text=text,
                message_id=message_id,
            )
        except Exception as exc:
            log.exception("command handler failed")
            await client.reply_text(message_id, f"处理失败: {exc}", settings=settings)
            return

        for chunk in result.texts:
            await client.reply_text(message_id, chunk, settings=settings)

        if result.card and message_id:
            try:
                await client.reply_interactive_card(message_id, result.card, settings=settings)
            except Exception:
                log.warning("interactive card send failed", exc_info=True)
    finally:
        db.close()


@router.post("/events")
async def feishu_events(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    if not settings.feishu_bot_enabled:
        raise HTTPException(503, detail="Feishu bot is disabled (SL_FEISHU_BOT_ENABLED)")

    t0 = time.perf_counter()
    raw = await request.body()
    try:
        payload = verify.parse_incoming_body(settings, raw)
    except Exception as exc:
        log.warning("feishu payload parse failed: %s", exc)
        raise HTTPException(400, detail="invalid feishu payload") from exc

    if verify.is_url_verification(payload):
        challenge = payload.get("challenge", "")
        return JSONResponse({"challenge": challenge})

    if not verify.verify_event_token(settings, payload):
        raise HTTPException(403, detail="invalid feishu verification token")

    # Interactive card button callback (review / todo cards). Handled separately
    # from im.message.receive_v1 so buttons like 查看要点/已掌握/需加强 work.
    card_action = _extract_card_action(payload)
    if card_action is not None:
        value = card_action["value"]
        open_id = card_action["open_id"]
        if open_id:
            try:
                _check_open_id_allowed(settings, open_id)
            except HTTPException:
                return JSONResponse(
                    {"toast": {"type": "error", "content": "无权操作"}}
                )
        value_text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        cmd = value.get("cmd", "") if isinstance(value, dict) else ""
        background_tasks.add_task(
            _process_card_action,
            open_id=open_id,
            chat_id=card_action["chat_id"],
            message_id=card_action["message_id"],
            value_text=value_text,
        )
        log.info(
            "feishu card action ack %.1fms cmd=%s open_id=%s",
            (time.perf_counter() - t0) * 1000,
            cmd,
            open_id,
        )
        toast = _CARD_TOAST_BY_CMD.get(cmd, "已处理")
        return JSONResponse({"toast": {"type": "info", "content": toast}})

    header = payload.get("header") or {}
    event_id = str(header.get("event_id", ""))
    event_type = header.get("event_type", "")
    if event_type != "im.message.receive_v1":
        return JSONResponse({"ok": True})

    event = payload.get("event") or {}
    message = event.get("message") or {}
    sender = event.get("sender") or {}
    sender_id = sender.get("sender_id") or {}
    open_id = sender_id.get("open_id") or ""
    if not open_id:
        return JSONResponse({"ok": True})

    # Ignore messages from the bot itself
    if sender.get("sender_type") == "app":
        return JSONResponse({"ok": True})

    _check_open_id_allowed(settings, open_id)

    message_id = message.get("message_id", "")
    chat_id = message.get("chat_id", "")
    message_type = message.get("message_type", "text")
    text = commands.extract_message_text(message.get("content") or "{}", message_type)
    if not text:
        return JSONResponse({"ok": True})

    if _is_duplicate(event_id, message_id):
        log.debug("feishu duplicate skipped event_id=%s message_id=%s", event_id, message_id)
        return JSONResponse({"ok": True})

    if try_claim_message(db, message_id=message_id, event_id=event_id, text=text):
        log.info(
            "feishu webhook ack skipped-duplicate %.1fms message_id=%s event_id=%s",
            (time.perf_counter() - t0) * 1000,
            message_id,
            event_id,
        )
        return JSONResponse({"ok": True})

    background_tasks.add_task(
        _process_feishu_message,
        event_id=event_id,
        message_id=message_id,
        open_id=open_id,
        chat_id=chat_id,
        text=text,
    )
    log.info(
        "feishu webhook ack queued-background %.1fms message_id=%s event_id=%s text=%r",
        (time.perf_counter() - t0) * 1000,
        message_id,
        event_id,
        (text or "")[:40],
    )
    return JSONResponse({"ok": True})
