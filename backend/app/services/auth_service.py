"""Login / register / bootstrap admin."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth_tokens import create_access_token, hash_password, verify_password
from app.core.config import (
    DEFAULT_BOOTSTRAP_PASSWORD,
    Settings,
    get_settings,
)
from app.models import AppSettings, FunctionBinding, PromptTemplate, Tenant, User
from app.prompts.defaults import DEFAULT_PROMPTS
from app.services.prompt_service import repair_bindings_for_tenant

log = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")


@dataclass
class AuthResult:
    access_token: str
    token_type: str
    user_id: int
    tenant_id: int
    tenant_name: str
    email: str
    display_name: str


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if len(s) < 2:
        s = "tenant"
    return s[:62]


def ensure_bootstrap_tenant(db: Session, settings: Settings | None = None) -> None:
    """Create default tenant + admin if DB is empty."""
    settings = settings or get_settings()
    tenant = db.get(Tenant, 1)
    if tenant is None:
        tenant = Tenant(id=1, name="默认租户", slug="default")
        db.add(tenant)
        db.flush()

    user = db.execute(select(User).where(User.tenant_id == 1).limit(1)).scalar_one_or_none()

    if user is not None and settings.auth_enabled:
        # Turning auth on for a database that was created with auth off: the
        # admin may still carry the placeholder password from the repo, and the
        # branch below never runs because the user already exists. Only touches
        # an account whose stored hash matches the known default — a real
        # password can't be clobbered by this.
        if verify_password(DEFAULT_BOOTSTRAP_PASSWORD, user.password_hash):
            replacement = (settings.auth_bootstrap_admin_password or "").strip()
            if not replacement or replacement == DEFAULT_BOOTSTRAP_PASSWORD:
                raise RuntimeError(
                    f"管理员 {user.email} 仍在使用仓库里的默认口令。请设置 "
                    "SL_AUTH_BOOTSTRAP_ADMIN_PASSWORD 为一个新口令后再启动，"
                    "启动时会自动替换。"
                )
            user.password_hash = hash_password(replacement)
            db.flush()
            log.warning(
                "Admin %s still had the default password; replaced it with "
                "SL_AUTH_BOOTSTRAP_ADMIN_PASSWORD.",
                user.email,
            )

    if user is None:
        email = (settings.auth_bootstrap_admin_email or "admin@local").strip().lower()
        password = (
            settings.auth_bootstrap_admin_password or DEFAULT_BOOTSTRAP_PASSWORD
        ).strip()
        # Refuse to create a reachable admin with the password that ships in
        # this repo. Only enforced when auth is on: with auth off every endpoint
        # is already open, so the password isn't what's protecting anything, and
        # local single-user runs shouldn't be forced to configure credentials.
        if settings.auth_enabled and password == DEFAULT_BOOTSTRAP_PASSWORD:
            raise RuntimeError(
                "拒绝以默认口令创建管理员账号。请设置 SL_AUTH_BOOTSTRAP_ADMIN_PASSWORD "
                "（以及 SL_AUTH_BOOTSTRAP_ADMIN_EMAIL）后再启动——默认口令写在仓库里，"
                "公网部署等同于无密码。"
            )
        user = User(
            tenant_id=1,
            email=email,
            password_hash=hash_password(password),
            display_name="管理员",
            role="admin",
        )
        db.add(user)

        if (
            db.execute(select(AppSettings).where(AppSettings.tenant_id == 1).limit(1))
            .scalar_one_or_none()
            is None
        ):
            db.add(AppSettings(tenant_id=1))

        _seed_prompts_for_tenant(db, tenant_id=1)
        db.flush()
        log.warning(
            "Bootstrap admin created: email=%s (change password after first login)",
            email,
        )

    repair_bindings_for_tenant(db, tenant_id=1)
    db.flush()


def _seed_prompts_for_tenant(db: Session, *, tenant_id: int) -> None:
    existing = db.execute(
        select(PromptTemplate.id).where(PromptTemplate.tenant_id == tenant_id).limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        return
    for pdef in DEFAULT_PROMPTS:
        pt = PromptTemplate(
            tenant_id=tenant_id,
            name=pdef.name,
            scene=pdef.scene,
            content=pdef.content,
            version_no=1,
            is_current=True,
        )
        db.add(pt)
        db.flush()
        binding = db.execute(
            select(FunctionBinding).where(
                FunctionBinding.tenant_id == tenant_id,
                FunctionBinding.scene == pdef.scene,
            )
        ).scalar_one_or_none()
        if binding is None:
            db.add(
                FunctionBinding(
                    tenant_id=tenant_id,
                    scene=pdef.scene,
                    prompt_template_id=pt.id,
                    params_json={},
                )
            )


def login(db: Session, *, email: str, password: str) -> AuthResult:
    settings = get_settings()
    email = email.strip().lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        raise ValueError("邮箱或密码错误")
    tenant = db.get(Tenant, user.tenant_id)
    if tenant is None:
        raise ValueError("租户不存在")
    token = create_access_token(
        secret=settings.secret_key,
        user_id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        expire_hours=settings.auth_token_expire_hours,
    )
    return AuthResult(
        access_token=token,
        token_type="bearer",
        user_id=user.id,
        tenant_id=user.tenant_id,
        tenant_name=tenant.name,
        email=user.email,
        display_name=user.display_name or user.email,
    )


def change_password(
    db: Session,
    *,
    user: User,
    current_password: str,
    new_password: str,
) -> None:
    if not verify_password(current_password, user.password_hash):
        raise ValueError("当前密码不正确")
    if len(new_password) < 8:
        raise ValueError("新密码至少 8 位")
    if current_password == new_password:
        raise ValueError("新密码不能与当前密码相同")
    user.password_hash = hash_password(new_password)
    db.flush()


def register_tenant(
    db: Session,
    *,
    tenant_name: str,
    email: str,
    password: str,
    display_name: str = "",
) -> AuthResult:
    settings = get_settings()
    if not settings.auth_allow_register:
        raise ValueError("注册已关闭，请联系管理员")
    email = email.strip().lower()
    if len(password) < 8:
        raise ValueError("密码至少 8 位")
    if db.execute(select(User.id).where(User.email == email)).scalar_one_or_none():
        raise ValueError("该邮箱已被使用")

    base_slug = _slugify(tenant_name)
    slug = base_slug
    n = 1
    while db.execute(select(Tenant.id).where(Tenant.slug == slug)).scalar_one_or_none():
        n += 1
        slug = f"{base_slug}-{n}"

    tenant = Tenant(name=tenant_name.strip(), slug=slug)
    db.add(tenant)
    db.flush()

    user = User(
        tenant_id=tenant.id,
        email=email,
        password_hash=hash_password(password),
        display_name=display_name.strip() or email.split("@")[0],
        role="admin",
    )
    db.add(user)
    db.add(AppSettings(tenant_id=tenant.id))
    _seed_prompts_for_tenant(db, tenant_id=tenant.id)
    repair_bindings_for_tenant(db, tenant_id=tenant.id)
    from app.services.feishu_trigger_service import get_rules

    get_rules(db, tenant_id=tenant.id)
    db.flush()

    token = create_access_token(
        secret=settings.secret_key,
        user_id=user.id,
        tenant_id=tenant.id,
        email=user.email,
        expire_hours=settings.auth_token_expire_hours,
    )
    return AuthResult(
        access_token=token,
        token_type="bearer",
        user_id=user.id,
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        email=user.email,
        display_name=user.display_name,
    )
