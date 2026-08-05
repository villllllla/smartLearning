"""Feishu Open API client (tenant token + send message)."""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from app.core.config import Settings, get_settings

log = logging.getLogger(__name__)

_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
_MSG_REPLY_URL = "https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply"
_MSG_CREATE_URL = "https://open.feishu.cn/open-apis/im/v1/messages"

_token_cache: dict[str, Any] = {"token": "", "expires_at": 0.0}


async def get_tenant_access_token(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    now = time.time()
    if _token_cache["token"] and _token_cache["expires_at"] > now + 60:
        return _token_cache["token"]

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            _TOKEN_URL,
            json={"app_id": settings.feishu_app_id, "app_secret": settings.feishu_app_secret},
        )
        resp.raise_for_status()
        data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Feishu token error: {data.get('msg', data)}")
    token = data["tenant_access_token"]
    expire = int(data.get("expire", 7200))
    _token_cache["token"] = token
    _token_cache["expires_at"] = now + expire
    return token


async def reply_text(
    message_id: str,
    text: str,
    *,
    settings: Settings | None = None,
) -> None:
    """Reply in thread to an incoming message."""
    settings = settings or get_settings()
    token = await get_tenant_access_token(settings)
    body = {
        "msg_type": "text",
        "content": json.dumps({"text": text}, ensure_ascii=False),
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            _MSG_REPLY_URL.format(message_id=message_id),
            headers={"Authorization": f"Bearer {token}"},
            json=body,
        )
        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if resp.status_code >= 400 or data.get("code") not in (0, None):
            log.warning(
                "Feishu reply failed http=%s code=%s msg=%s",
                resp.status_code,
                data.get("code"),
                data.get("msg", resp.text[:300]),
            )
            return


async def send_text_to_chat(
    chat_id: str,
    text: str,
    *,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    token = await get_tenant_access_token(settings)
    body = {
        "receive_id": chat_id,
        "msg_type": "text",
        "content": json.dumps({"text": text}, ensure_ascii=False),
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            _MSG_CREATE_URL,
            params={"receive_id_type": "chat_id"},
            headers={"Authorization": f"Bearer {token}"},
            json=body,
        )
        if resp.status_code >= 400:
            log.warning("Feishu send failed %s: %s", resp.status_code, resp.text)
            resp.raise_for_status()
        data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Feishu send error: {data.get('msg', data)}")


async def send_interactive_card_to_chat(
    chat_id: str,
    card: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    token = await get_tenant_access_token(settings)
    body = {
        "receive_id": chat_id,
        "msg_type": "interactive",
        "content": json.dumps(card, ensure_ascii=False),
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            _MSG_CREATE_URL,
            params={"receive_id_type": "chat_id"},
            headers={"Authorization": f"Bearer {token}"},
            json=body,
        )
        if resp.status_code >= 400:
            log.warning("Feishu card send failed %s: %s", resp.status_code, resp.text)
            resp.raise_for_status()
        data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Feishu card send error: {data.get('msg', data)}")


async def reply_interactive_card(
    message_id: str,
    card: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    token = await get_tenant_access_token(settings)
    body = {
        "msg_type": "interactive",
        "content": json.dumps(card, ensure_ascii=False),
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            _MSG_REPLY_URL.format(message_id=message_id),
            headers={"Authorization": f"Bearer {token}"},
            json=body,
        )
        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if resp.status_code >= 400 or data.get("code") not in (0, None):
            log.warning(
                "Feishu card reply failed http=%s code=%s msg=%s",
                resp.status_code,
                data.get("code"),
                data.get("msg", resp.text[:300]),
            )
