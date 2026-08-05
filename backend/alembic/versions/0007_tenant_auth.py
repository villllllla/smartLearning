"""Multi-tenant auth: tenants, users, tenant_id columns.

Revision ID: 0007
Revises: 0006
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime

import sqlalchemy as sa

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

_TENANT_TABLES = (
    "wiki_collections",
    "wikis",
    "question_bank_collections",
    "tags",
    "questions",
    "question_candidates",
    "chats",
    "model_providers",
    "prompt_templates",
    "function_bindings",
)


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 600_000
    )
    return f"pbkdf2_sha256${salt}${digest.hex()}"


def _sqlite_replace_global_unique(table: str, old_cols: list[str], new_name: str, new_cols: list[str]) -> None:
    """Replace SQLite unnamed UNIQUE with a named per-tenant constraint."""
    tmp = f"_uq_{table}_legacy_tmp"
    with op.batch_alter_table(table) as batch:
        batch.create_unique_constraint(tmp, old_cols)
    with op.batch_alter_table(table) as batch:
        batch.drop_constraint(tmp, type_="unique")
    with op.batch_alter_table(table) as batch:
        batch.create_unique_constraint(new_name, new_cols)


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing = set(insp.get_table_names())

    if "tenants" not in existing:
        op.create_table(
            "tenants",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("slug", sa.String(80), nullable=False, unique=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.func.current_timestamp(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.func.current_timestamp(),
                nullable=False,
            ),
        )
    if "users" not in existing:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("email", sa.String(320), nullable=False),
            sa.Column("password_hash", sa.String(255), nullable=False),
            sa.Column("display_name", sa.String(120), nullable=False, server_default=""),
            sa.Column("role", sa.String(16), nullable=False, server_default="admin"),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.func.current_timestamp(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.func.current_timestamp(),
                nullable=False,
            ),
            sa.UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
        )
        op.create_index("ix_users_email", "users", ["email"])

    now = datetime.utcnow()
    if bind.execute(sa.text("SELECT COUNT(*) FROM tenants")).scalar_one() == 0:
        bind.execute(
            sa.text("INSERT INTO tenants (id, name, slug, created_at, updated_at) VALUES (1, :n, 'default', :now, :now)"),
            {"n": "默认租户", "now": now},
        )
    if bind.execute(sa.text("SELECT COUNT(*) FROM users")).scalar_one() == 0:
        pw = _hash_password("changeme123")
        bind.execute(
            sa.text(
                """INSERT INTO users (tenant_id, email, password_hash, display_name, role, created_at, updated_at)
                   VALUES (1, 'admin@local', :pw, '管理员', 'admin', :now, :now)"""
            ),
            {"pw": pw, "now": now},
        )

    for table in _TENANT_TABLES:
        cols = {c["name"] for c in insp.get_columns(table)}
        if "tenant_id" in cols:
            continue
        with op.batch_alter_table(table) as batch:
            batch.add_column(
                sa.Column("tenant_id", sa.Integer(), nullable=False, server_default="1")
            )
            batch.create_foreign_key(
                f"fk_{table}_tenant_id",
                "tenants",
                ["tenant_id"],
                ["id"],
                ondelete="CASCADE",
            )
            batch.create_index(f"ix_{table}_tenant_id", ["tenant_id"])

    app_cols = {c["name"] for c in insp.get_columns("app_settings")}
    if "tenant_id" not in app_cols:
        with op.batch_alter_table("app_settings") as batch:
            batch.add_column(
                sa.Column("tenant_id", sa.Integer(), nullable=False, server_default="1")
            )
            batch.create_foreign_key(
                "fk_app_settings_tenant_id",
                "tenants",
                ["tenant_id"],
                ["id"],
                ondelete="CASCADE",
            )
            batch.create_unique_constraint("uq_app_settings_tenant_id", ["tenant_id"])

    # Drop old global uniques; add per-tenant uniques
    tag_uqs = {c["name"] for c in insp.get_unique_constraints("tags")}
    if "uq_tags_tenant_name" not in tag_uqs:
        _sqlite_replace_global_unique("tags", ["name"], "uq_tags_tenant_name", ["tenant_id", "name"])

    mp_uqs = {c["name"] for c in insp.get_unique_constraints("model_providers")}
    if "uq_provider_tenant_name" not in mp_uqs:
        _sqlite_replace_global_unique(
            "model_providers", ["name"], "uq_provider_tenant_name", ["tenant_id", "name"]
        )

    pt_uqs = {c["name"] for c in insp.get_unique_constraints("prompt_templates")}
    if "uq_prompt_tenant_scene_version" not in pt_uqs:
        with op.batch_alter_table("prompt_templates") as batch:
            batch.drop_constraint("uq_prompt_scene_version", type_="unique")
            batch.create_unique_constraint(
                "uq_prompt_tenant_scene_version", ["tenant_id", "scene", "version_no"]
            )

    fb_uqs = {c["name"] for c in insp.get_unique_constraints("function_bindings")}
    if "uq_binding_tenant_scene" not in fb_uqs:
        _sqlite_replace_global_unique(
            "function_bindings", ["scene"], "uq_binding_tenant_scene", ["tenant_id", "scene"]
        )

    bind.execute(sa.text("UPDATE app_settings SET tenant_id = 1 WHERE tenant_id IS NULL OR tenant_id = 0"))


def downgrade() -> None:
    op.drop_table("users")
    op.drop_table("tenants")
    for table in reversed(_TENANT_TABLES):
        with op.batch_alter_table(table) as batch:
            batch.drop_index(f"ix_{table}_tenant_id")
            batch.drop_constraint(f"fk_{table}_tenant_id", type_="foreignkey")
            batch.drop_column("tenant_id")
    with op.batch_alter_table("app_settings") as batch:
        batch.drop_constraint("uq_app_settings_tenant_id", type_="unique")
        batch.drop_constraint("fk_app_settings_tenant_id", type_="foreignkey")
        batch.drop_column("tenant_id")
