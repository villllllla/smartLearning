"""Feishu event subscription verification and optional payload decryption."""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

from app.core.config import Settings


def decrypt_event_body(encrypt_key: str, cipher_text_b64: str) -> dict[str, Any]:
    """Decrypt Feishu encrypted event callback body."""
    key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()
    raw = base64.b64decode(cipher_text_b64)
    if len(raw) < 16:
        raise ValueError("ciphertext too short")
    iv, data = raw[:16], raw[16:]
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded = decryptor.update(data) + decryptor.finalize()
    unpadder = PKCS7(128).unpadder()
    plain = unpadder.update(padded) + unpadder.finalize()
    return json.loads(plain.decode("utf-8"))


def parse_incoming_body(settings: Settings, raw_body: bytes) -> dict[str, Any]:
    data = json.loads(raw_body.decode("utf-8"))
    if "encrypt" in data and settings.feishu_encrypt_key:
        return decrypt_event_body(settings.feishu_encrypt_key, data["encrypt"])
    return data


def verify_event_token(settings: Settings, payload: dict[str, Any]) -> bool:
    """Schema 2.0: header.token must match verification token when configured."""
    expected = (settings.feishu_verification_token or "").strip()
    if not expected:
        return True
    header = payload.get("header") or {}
    token = (header.get("token") or "").strip()
    # URL verification uses top-level token
    if not token:
        token = (payload.get("token") or "").strip()
    return token == expected


def is_url_verification(payload: dict[str, Any]) -> bool:
    if payload.get("type") == "url_verification":
        return True
    return (payload.get("header") or {}).get("event_type") == "url_verification"
