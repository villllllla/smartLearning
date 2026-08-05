"""Feishu trigger rules + seed defaults

Revision ID: 0015
Revises: 0014
"""
from __future__ import annotations

import json

import sqlalchemy as sa

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def _table_names(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    if "feishu_trigger_rules" in _table_names(bind):
        return

    op.create_table(
        "feishu_trigger_rules",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Integer,
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("title", sa.String(64), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "match_mode", sa.String(16), nullable=False, server_default="exact"
        ),
        sa.Column("prefixes", sa.JSON, nullable=False),
        sa.Column("extra_args_json", sa.JSON, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "is_system", sa.Boolean, nullable=False, server_default=sa.text("1")
        ),
        sa.Column(
            "created_at",
            sa.DateTime,
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime,
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "tenant_id", "action", name="uq_feishu_trigger_tenant_action"
        ),
    )
    op.create_index(
        "ix_feishu_trigger_rules_tenant_id",
        "feishu_trigger_rules",
        ["tenant_id"],
    )

    from app.services.feishu_trigger_service import DEFAULT_FEISHU_TRIGGER_RULES

    tenant_ids = [
        row[0] for row in bind.execute(sa.text("SELECT id FROM tenants")).fetchall()
    ]
    for tid in tenant_ids:
        for spec in DEFAULT_FEISHU_TRIGGER_RULES:
            exists = bind.execute(
                sa.text(
                    "SELECT id FROM feishu_trigger_rules "
                    "WHERE tenant_id = :tid AND action = :action"
                ),
                {"tid": tid, "action": spec["action"]},
            ).scalar()
            if exists is not None:
                continue
            bind.execute(
                sa.text(
                    """
                    INSERT INTO feishu_trigger_rules
                      (tenant_id, action, title, description, match_mode, prefixes,
                       extra_args_json, enabled, priority, is_system, created_at, updated_at)
                    VALUES
                      (:tid, :action, :title, :description, :match_mode, :prefixes,
                       :extra_args_json, 1, :priority, 1,
                       CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """
                ),
                {
                    "tid": tid,
                    "action": spec["action"],
                    "title": spec["title"],
                    "description": spec.get("description"),
                    "match_mode": spec["match_mode"],
                    "prefixes": json.dumps(list(spec["prefixes"]), ensure_ascii=False),
                    "extra_args_json": json.dumps(
                        spec.get("extra_args_json") or {}, ensure_ascii=False
                    ),
                    "priority": int(spec.get("priority") or 0),
                },
            )


def downgrade() -> None:
    op.drop_index("ix_feishu_trigger_rules_tenant_id", table_name="feishu_trigger_rules")
    op.drop_table("feishu_trigger_rules")
