"""Local smoke test for Feishu webhook (reads .env via app settings)."""
from __future__ import annotations

import json
import sys

import httpx

from app.core.config import get_settings


def main() -> int:
    base = "http://127.0.0.1:8000"
    get_settings.cache_clear()
    s = get_settings()
    errors: list[str] = []

    print("=== Config (masked) ===")
    print(f"  feishu_bot_enabled: {s.feishu_bot_enabled}")
    print(f"  feishu_app_id: {s.feishu_app_id[:8]}..." if s.feishu_app_id else "  feishu_app_id: (empty)")
    print(f"  verification_token set: {bool(s.feishu_verification_token)}")
    print(f"  encrypt_key set: {bool(s.feishu_encrypt_key)}")
    print(f"  allowed_open_ids: {len(s.feishu_allowed_open_ids_list)} id(s)")
    print(f"  bot_api_token set: {bool(s.bot_api_token)}")

    # 1) Health (public)
    try:
        r = httpx.get(f"{base}/api/health", timeout=5.0)
        print(f"\n[1] GET /api/health -> {r.status_code} {r.text[:80]}")
        if r.status_code != 200:
            errors.append("health failed")
    except httpx.ConnectError:
        print("\n[1] GET /api/health -> CONNECTION REFUSED (is uvicorn running?)")
        return 1

    # 2) URL verification (Feishu save-URL handshake)
    body = {
        "challenge": "sl-test-challenge-001",
        "token": s.feishu_verification_token,
        "type": "url_verification",
    }
    r = httpx.post(f"{base}/api/integrations/feishu/events", json=body, timeout=10.0)
    print(f"\n[2] POST url_verification -> {r.status_code}")
    try:
        data = r.json()
        print(f"     body: {data}")
        if r.status_code != 200 or data.get("challenge") != body["challenge"]:
            errors.append("url_verification challenge mismatch")
    except Exception:
        print(f"     raw: {r.text[:200]}")
        errors.append("url_verification not json")

    # 3) Simulated message: 帮助 (allowed open_id)
    if not s.feishu_allowed_open_ids_list:
        print("\n[3] SKIP message test (no SL_FEISHU_ALLOWED_OPEN_IDS)")
    else:
        open_id = s.feishu_allowed_open_ids_list[0]
        msg_body = {
            "schema": "2.0",
            "header": {
                "event_id": "sl_local_test_evt_001",
                "event_type": "im.message.receive_v1",
                "token": s.feishu_verification_token,
                "create_time": "1710000000",
            },
            "event": {
                "message": {
                    "message_id": "om_sl_local_test",
                    "chat_id": "oc_sl_local_test",
                    "message_type": "text",
                    "content": json.dumps({"text": "帮助"}, ensure_ascii=False),
                },
                "sender": {
                    "sender_id": {"open_id": open_id},
                    "sender_type": "user",
                },
            },
        }
        r = httpx.post(
            f"{base}/api/integrations/feishu/events",
            json=msg_body,
            timeout=60.0,
        )
        print(f"\n[3] POST im.message.receive_v1 (帮助) -> {r.status_code} {r.text[:120]}")
        if r.status_code != 200:
            errors.append(f"message handler returned {r.status_code}")
        else:
            print("     (If Feishu credentials OK, bot may have tried reply_text to Feishu API)")

    # 4) Wrong open_id -> expect 403
    bad_body = {
        "schema": "2.0",
        "header": {
            "event_id": "sl_local_test_evt_002",
            "event_type": "im.message.receive_v1",
            "token": s.feishu_verification_token,
            "create_time": "1710000000",
        },
        "event": {
            "message": {
                "message_id": "om_bad",
                "chat_id": "oc_bad",
                "message_type": "text",
                "content": json.dumps({"text": "帮助"}),
            },
            "sender": {
                "sender_id": {"open_id": "ou_not_in_allowlist"},
                "sender_type": "user",
            },
        },
    }
    r = httpx.post(f"{base}/api/integrations/feishu/events", json=bad_body, timeout=10.0)
    print(f"\n[4] POST wrong open_id -> {r.status_code} (expect 403)")
    if r.status_code != 403:
        errors.append(f"expected 403 for bad open_id, got {r.status_code}")

    print("\n=== Summary ===")
    if errors:
        print("FAILED:", "; ".join(errors))
        return 1
    print("All local checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
