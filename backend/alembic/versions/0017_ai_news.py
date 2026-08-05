"""AI news digests/items/schedule + ai_news_curation prompt + feishu trigger

Revision ID: 0017
Revises: 0016
"""
from __future__ import annotations

import json

import sqlalchemy as sa

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

_SCENE = "ai_news_curation"
_TRIGGER = {
    "action": "fetch_ai_news",
    "title": "AI 资讯",
    "description": "立即抓取多源 AI 资讯并推送今日热点 Top5",
    "match_mode": "exact",
    "prefixes": ["资讯", "AI资讯", "ai资讯", "热点", "今日热点", "ai news"],
    "extra_args_json": {},
    "priority": 82,
}


def _table_names(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    existing = _table_names(bind)

    if "ai_news_digests" not in existing:
        op.create_table(
            "ai_news_digests",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column(
                "tenant_id", sa.Integer,
                sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column("run_slot", sa.String(32), nullable=True),
            sa.Column("item_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("total_candidates", sa.Integer, nullable=False, server_default="0"),
            sa.Column("used_llm", sa.Boolean, nullable=False, server_default=sa.false()),
            sa.Column("channel", sa.String(16), nullable=True),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
        )
        op.create_index(
            "ix_ai_news_digests_tenant_created", "ai_news_digests", ["tenant_id", "created_at"]
        )

    if "ai_news_items" not in existing:
        op.create_table(
            "ai_news_items",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column(
                "digest_id", sa.Integer,
                sa.ForeignKey("ai_news_digests.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column(
                "tenant_id", sa.Integer,
                sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column("rank", sa.Integer, nullable=False, server_default="0"),
            sa.Column("title", sa.String(300), nullable=False, server_default=""),
            sa.Column("original_title", sa.String(300), nullable=False, server_default=""),
            sa.Column("url", sa.Text, nullable=False, server_default=""),
            sa.Column("source", sa.String(64), nullable=False, server_default=""),
            sa.Column("summary", sa.Text, nullable=False, server_default=""),
            sa.Column("heat_score", sa.Integer, nullable=False, server_default="0"),
            sa.Column("why", sa.String(200), nullable=True),
            sa.Column("raw_score", sa.Float, nullable=False, server_default="0"),
            sa.Column("published_at", sa.DateTime, nullable=True),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
        )
        op.create_index("ix_ai_news_items_digest", "ai_news_items", ["digest_id"])
        op.create_index("ix_ai_news_items_tenant_url", "ai_news_items", ["tenant_id", "url"])

    if "ai_news_schedules" not in existing:
        op.create_table(
            "ai_news_schedules",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column(
                "tenant_id", sa.Integer,
                sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.false()),
            sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Shanghai"),
            sa.Column("push_times", sa.JSON, nullable=False),
            sa.Column("frequency", sa.String(16), nullable=False, server_default="daily"),
            sa.Column("weekdays", sa.JSON, nullable=False),
            sa.Column("top_n", sa.Integer, nullable=False, server_default="5"),
            sa.Column("enable_hackernews", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("enable_github", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("rss_feeds", sa.JSON, nullable=False),
            sa.Column("dedup_days", sa.Integer, nullable=False, server_default="7"),
            sa.Column("feishu_enabled", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("last_run_slot", sa.String(32), nullable=True),
            sa.Column("last_run_at", sa.DateTime, nullable=True),
            sa.Column("last_error", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
            sa.UniqueConstraint("tenant_id", name="uq_ai_news_schedule_tenant"),
        )

    _seed_prompt(bind)
    _seed_trigger(bind)


def _seed_prompt(bind) -> None:
    from app.prompts.defaults import AI_NEWS_CURATION_V1

    tenant_ids = [row[0] for row in bind.execute(sa.text("SELECT id FROM tenants")).fetchall()]
    for tid in tenant_ids:
        exists = bind.execute(
            sa.text(
                "SELECT id FROM prompt_templates "
                "WHERE tenant_id = :tid AND scene = :scene AND is_current = 1"
            ),
            {"tid": tid, "scene": _SCENE},
        ).scalar()
        if exists is None:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO prompt_templates
                      (tenant_id, name, scene, content, version_no, is_current, notes,
                       created_at, updated_at)
                    VALUES
                      (:tid, :name, :scene, :content, 1, 1, :notes, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """
                ),
                {
                    "tid": tid,
                    "name": "AI 资讯精选 v1",
                    "scene": _SCENE,
                    "content": AI_NEWS_CURATION_V1,
                    "notes": "默认 v1,0017 迁移写入",
                },
            )
        prompt_id = bind.execute(
            sa.text(
                "SELECT id FROM prompt_templates "
                "WHERE tenant_id = :tid AND scene = :scene AND is_current = 1"
            ),
            {"tid": tid, "scene": _SCENE},
        ).scalar()
        binding_exists = bind.execute(
            sa.text(
                "SELECT id FROM function_bindings WHERE tenant_id = :tid AND scene = :scene"
            ),
            {"tid": tid, "scene": _SCENE},
        ).scalar()
        if binding_exists is None:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO function_bindings
                      (tenant_id, scene, prompt_template_id, model_id, params_json,
                       created_at, updated_at)
                    VALUES (:tid, :scene, :prompt_id, NULL, '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """
                ),
                {"tid": tid, "scene": _SCENE, "prompt_id": prompt_id},
            )


def _seed_trigger(bind) -> None:
    tenant_ids = [row[0] for row in bind.execute(sa.text("SELECT id FROM tenants")).fetchall()]
    for tid in tenant_ids:
        exists = bind.execute(
            sa.text(
                "SELECT id FROM feishu_trigger_rules WHERE tenant_id = :tid AND action = :action"
            ),
            {"tid": tid, "action": _TRIGGER["action"]},
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
                   :extra_args_json, 1, :priority, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            ),
            {
                "tid": tid,
                "action": _TRIGGER["action"],
                "title": _TRIGGER["title"],
                "description": _TRIGGER["description"],
                "match_mode": _TRIGGER["match_mode"],
                "prefixes": json.dumps(list(_TRIGGER["prefixes"]), ensure_ascii=False),
                "extra_args_json": json.dumps(_TRIGGER["extra_args_json"], ensure_ascii=False),
                "priority": int(_TRIGGER["priority"]),
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM feishu_trigger_rules WHERE action = :action"),
        {"action": _TRIGGER["action"]},
    )
    bind.execute(sa.text("DELETE FROM function_bindings WHERE scene = :scene"), {"scene": _SCENE})
    bind.execute(sa.text("DELETE FROM prompt_templates WHERE scene = :scene"), {"scene": _SCENE})
    op.drop_table("ai_news_items")
    op.drop_table("ai_news_schedules")
    op.drop_table("ai_news_digests")
