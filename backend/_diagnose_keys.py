"""Diagnose stored provider API keys: are they still decryptable with the
current secret? Also offer to wipe undecryptable ciphertexts so subsequent
PATCH calls behave predictably.

Run:
  python _diagnose_keys.py            # read-only report
  python _diagnose_keys.py --wipe     # wipe undecryptable rows (irreversible)
"""
from __future__ import annotations

import sys

from sqlalchemy import select

from app.core.security import decrypt_secret
from app.db.session import SessionLocal
from app.models import ModelProvider


def main(wipe: bool) -> int:
    db = SessionLocal()
    try:
        rows = db.execute(
            select(ModelProvider).order_by(ModelProvider.id.asc())
        ).scalars().all()
        if not rows:
            print("(no providers in DB)")
            return 0

        undecryptable: list[ModelProvider] = []
        for p in rows:
            if p.api_key_encrypted is None:
                status = "EMPTY"
            else:
                plain = decrypt_secret(p.api_key_encrypted)
                if plain is None:
                    status = "UNDECRYPTABLE (orphaned ciphertext)"
                    undecryptable.append(p)
                else:
                    masked = plain[:4] + "*" * max(0, len(plain) - 8) + plain[-4:]
                    status = f"OK ({masked})"
            print(f"  [{p.id}] {p.name!r} type={p.type} -> {status}")

        if undecryptable and wipe:
            for p in undecryptable:
                p.api_key_encrypted = None
            db.commit()
            print(
                f"\nWiped {len(undecryptable)} undecryptable ciphertext(s). "
                f"Re-enter API keys in the UI."
            )
        elif undecryptable:
            print(
                f"\nFound {len(undecryptable)} undecryptable ciphertext(s). "
                f"Re-run with --wipe to clear them, OR set SL_SECRET_KEY to "
                f"the value you had previously."
            )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main(wipe="--wipe" in sys.argv))
