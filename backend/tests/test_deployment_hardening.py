"""Guards for the public-deployment hardening.

These pin the *defaults*, because every finding they cover came from the same
failure mode: a deployment that simply didn't set a variable. A default that
silently opens the app is the bug, so the defaults are what's asserted.
"""
import time

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.core.config import DEFAULT_BOOTSTRAP_PASSWORD, Settings
from app.core.rate_limit import RateLimitMiddleware, _SlidingWindow, client_ip
from app.db.base import Base
from app.services.auth_service import ensure_bootstrap_tenant


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


# --- defaults --------------------------------------------------------------


def test_api_docs_are_off_by_default():
    """Publishing the schema must require an explicit opt-in."""
    assert Settings(_env_file=None).api_docs_enabled is False


def test_proxy_headers_are_not_trusted_by_default():
    """Trusting X-Forwarded-For without a proxy in front makes limits spoofable."""
    assert Settings(_env_file=None).trust_proxy_headers is False


def test_rate_limiting_is_on_by_default():
    assert Settings(_env_file=None).rate_limit_enabled is True


def test_registration_is_closed_by_default():
    assert Settings(_env_file=None).auth_allow_register is False


# --- bootstrap credentials -------------------------------------------------


def test_bootstrap_refuses_default_password_when_auth_enabled(db):
    settings = Settings(_env_file=None, auth_enabled=True)
    assert settings.auth_bootstrap_admin_password == DEFAULT_BOOTSTRAP_PASSWORD
    with pytest.raises(RuntimeError, match="默认口令"):
        ensure_bootstrap_tenant(db, settings)


def test_bootstrap_allows_default_password_when_auth_disabled(db):
    """Local single-user runs shouldn't be forced to configure credentials."""
    ensure_bootstrap_tenant(db, Settings(_env_file=None, auth_enabled=False))


def test_existing_admin_with_default_password_is_rotated(db):
    """Turning auth on for a DB created with auth off must not leave the
    placeholder password live — the create-branch never runs for it."""
    from app.core.auth_tokens import verify_password
    from app.models import User

    ensure_bootstrap_tenant(db, Settings(_env_file=None, auth_enabled=False))
    db.flush()
    admin = db.execute(select(User).where(User.tenant_id == 1)).scalar_one()
    assert verify_password(DEFAULT_BOOTSTRAP_PASSWORD, admin.password_hash)

    ensure_bootstrap_tenant(
        db,
        Settings(
            _env_file=None,
            auth_enabled=True,
            auth_bootstrap_admin_password="a-real-password",
        ),
    )
    db.flush()
    assert not verify_password(DEFAULT_BOOTSTRAP_PASSWORD, admin.password_hash)
    assert verify_password("a-real-password", admin.password_hash)


def test_existing_admin_with_default_password_blocks_start_without_replacement(db):
    ensure_bootstrap_tenant(db, Settings(_env_file=None, auth_enabled=False))
    db.flush()
    with pytest.raises(RuntimeError, match="默认口令"):
        ensure_bootstrap_tenant(db, Settings(_env_file=None, auth_enabled=True))


def test_a_real_password_is_never_clobbered(db):
    """The rotation must only fire on the known-default hash."""
    from app.core.auth_tokens import hash_password, verify_password
    from app.models import User

    ensure_bootstrap_tenant(db, Settings(_env_file=None, auth_enabled=False))
    db.flush()
    admin = db.execute(select(User).where(User.tenant_id == 1)).scalar_one()
    admin.password_hash = hash_password("chosen-by-the-user")
    db.flush()

    ensure_bootstrap_tenant(
        db,
        Settings(
            _env_file=None,
            auth_enabled=True,
            auth_bootstrap_admin_password="something-else-entirely",
        ),
    )
    db.flush()
    assert verify_password("chosen-by-the-user", admin.password_hash)


def test_bootstrap_accepts_a_configured_password(db):
    ensure_bootstrap_tenant(
        db,
        Settings(
            _env_file=None,
            auth_enabled=True,
            auth_bootstrap_admin_password="a-real-password",
        ),
    )


# --- client ip extraction --------------------------------------------------


def _request(headers: dict[str, str], peer: str = "10.0.0.1") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/x",
            "headers": Headers(headers).raw,
            "client": (peer, 12345),
        }
    )


def test_forwarded_headers_ignored_when_proxy_not_trusted():
    req = _request({"x-forwarded-for": "1.2.3.4", "cf-connecting-ip": "5.6.7.8"})
    assert client_ip(req, trust_proxy=False) == "10.0.0.1"


def test_uses_last_forwarded_entry_not_the_first():
    """Earlier XFF entries are client-supplied; only the last hop is our proxy's."""
    req = _request({"x-forwarded-for": "9.9.9.9, 203.0.113.7"})
    assert client_ip(req, trust_proxy=True) == "203.0.113.7"


def test_cf_connecting_ip_wins_when_trusted():
    req = _request({"x-forwarded-for": "9.9.9.9, 127.0.0.1", "cf-connecting-ip": "203.0.113.7"})
    assert client_ip(req, trust_proxy=True) == "203.0.113.7"


# --- sliding window --------------------------------------------------------


def test_window_blocks_past_the_limit_and_reports_retry_after():
    w = _SlidingWindow(limit=3, window_seconds=60)
    now = time.monotonic()
    assert all(w.check("ip", now) is None for _ in range(3))
    retry = w.check("ip", now)
    assert retry is not None and retry > 0


def test_window_is_per_key():
    w = _SlidingWindow(limit=1, window_seconds=60)
    now = time.monotonic()
    assert w.check("a", now) is None
    assert w.check("b", now) is None
    assert w.check("a", now) is not None


def test_window_frees_slots_once_hits_age_out():
    w = _SlidingWindow(limit=2, window_seconds=10)
    now = time.monotonic()
    w.check("ip", now)
    w.check("ip", now)
    assert w.check("ip", now) is not None
    assert w.check("ip", now + 11) is None


# --- middleware dispatch ---------------------------------------------------


def _limited_client(**overrides) -> TestClient:
    async def ok(request):  # noqa: ANN001, ANN202
        return PlainTextResponse("ok")

    kwargs = {
        "auth_limit": 2,
        "auth_window_seconds": 900,
        "write_limit": 3,
        "write_window_seconds": 300,
        "trust_proxy": False,
    }
    kwargs.update(overrides)
    app = Starlette(
        routes=[
            Route("/api/auth/login", ok, methods=["POST"]),
            Route("/api/todos", ok, methods=["GET", "POST"]),
            Route("/api/integrations/feishu/events", ok, methods=["POST"]),
            Route("/healthz", ok, methods=["GET"]),
        ]
    )
    app.add_middleware(RateLimitMiddleware, **kwargs)
    return TestClient(app)


def test_login_uses_the_strict_bucket():
    c = _limited_client()
    assert [c.post("/api/auth/login").status_code for _ in range(2)] == [200, 200]
    resp = c.post("/api/auth/login")
    assert resp.status_code == 429
    assert int(resp.headers["Retry-After"]) > 0


def test_reads_are_not_limited():
    c = _limited_client()
    assert all(c.get("/api/todos").status_code == 200 for _ in range(20))


def test_writes_use_the_looser_bucket():
    c = _limited_client()
    assert [c.post("/api/todos").status_code for _ in range(3)] == [200, 200, 200]
    assert c.post("/api/todos").status_code == 429


def test_login_and_write_buckets_are_independent():
    """Exhausting login must not lock the user out of the rest of the API."""
    c = _limited_client()
    for _ in range(3):
        c.post("/api/auth/login")
    assert c.post("/api/todos").status_code == 200


def test_feishu_webhook_is_exempt():
    """Feishu retries deliveries; it has its own token + fail-closed allowlist."""
    c = _limited_client()
    assert all(
        c.post("/api/integrations/feishu/events").status_code == 200 for _ in range(10)
    )


def test_non_api_paths_are_untouched():
    c = _limited_client()
    assert all(c.get("/healthz").status_code == 200 for _ in range(20))
