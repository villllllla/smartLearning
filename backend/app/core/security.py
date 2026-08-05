"""Symmetric encryption helpers for sensitive fields (e.g. provider API keys).

Derives a Fernet key deterministically from ``settings.secret_key`` so the same
secret key can decrypt previously stored ciphertexts.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings


def _fernet() -> Fernet:
    secret = get_settings().secret_key.encode("utf-8")
    digest = hashlib.sha256(secret).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(plaintext: str | None) -> str | None:
    if not plaintext:
        return None
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str | None) -> str | None:
    if not ciphertext:
        return None
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None


def mask_key(plaintext: str | None) -> str:
    """Return a masked representation safe to send to the frontend."""
    if not plaintext:
        return ""
    if len(plaintext) <= 8:
        return "*" * len(plaintext)
    return f"{plaintext[:4]}{'*' * (len(plaintext) - 8)}{plaintext[-4:]}"
