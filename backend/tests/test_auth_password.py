"""Tests for password change."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.auth_tokens import verify_password
from app.db.base import Base
from app.models import Tenant, User
from app.services.auth_service import change_password, login


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_change_password_success():
    db = _session()
    tenant = Tenant(name="t", slug="t")
    db.add(tenant)
    db.flush()
    from app.core.auth_tokens import hash_password

    user = User(
        tenant_id=tenant.id,
        email="u@local",
        password_hash=hash_password("oldpass123"),
        display_name="u",
        role="admin",
    )
    db.add(user)
    db.commit()

    change_password(
        db,
        user=user,
        current_password="oldpass123",
        new_password="newpass456",
    )
    db.commit()
    db.refresh(user)
    assert verify_password("newpass456", user.password_hash)
    assert not verify_password("oldpass123", user.password_hash)


def test_change_password_wrong_current():
    db = _session()
    tenant = Tenant(name="t", slug="t")
    db.add(tenant)
    db.flush()
    from app.core.auth_tokens import hash_password

    user = User(
        tenant_id=tenant.id,
        email="u@local",
        password_hash=hash_password("oldpass123"),
        display_name="u",
        role="admin",
    )
    db.add(user)
    db.commit()

    try:
        change_password(
            db,
            user=user,
            current_password="wrong",
            new_password="newpass456",
        )
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "当前密码不正确" in str(exc)


def test_login_after_change_password():
    db = _session()
    tenant = Tenant(name="t", slug="t")
    db.add(tenant)
    db.flush()
    from app.core.auth_tokens import hash_password

    user = User(
        tenant_id=tenant.id,
        email="u@local",
        password_hash=hash_password("oldpass123"),
        display_name="u",
        role="admin",
    )
    db.add(user)
    db.commit()

    change_password(
        db,
        user=user,
        current_password="oldpass123",
        new_password="newpass456",
    )
    db.commit()

    result = login(db, email="u@local", password="newpass456")
    assert result.user_id == user.id
