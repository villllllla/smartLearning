"""Todo items + todo_intent prompt + Feishu trigger rules

Revision ID: 0016
Revises: 0015
"""
from __future__ import annotations

import json

import sqlalchemy as sa

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

_SCENE = "todo_intent_parsing"
_NEW_TRIGGERS = (
    {
        "action": "submit_todo",
        "title": "创建待办",
        "description": "前缀 + 正文：意图识别、拆解并设置提醒(可追问补全)",
        "match_mode": "prefix",
        "prefixes": ["待办", "提醒", "todo", "remind"],
        "extra_args_json": {"min_body_len": 4},
        "priority": 15,
    },
    {
        "action": "list_todos",
        "title": "待办列表",
        "description": "查看未完成待办",
        "match_mode": "exact",
        "prefixes": ["待办列表", "我的待办", "todo list"],
        "extra_args_json": {},
        "priority": 84,
    },
)


def _table_names(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    existing = _table_names(bind)

    if "todo_items" not in existing:
        op.create_table(
            "todo_items",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column(
                "tenant_id",
                sa.Integer,
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("title", sa.String(200), nullable=False, server_default=""),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column(
                "status", sa.String(16), nullable=False, server_default="clarifying"
            ),
            sa.Column("remind_at", sa.DateTime, nullable=True),
            sa.Column(
                "timezone", sa.String(64), nullable=False, server_default="Asia/Shanghai"
            ),
            sa.Column("reminded_at", sa.DateTime, nullable=True),
            sa.Column("completed_at", sa.DateTime, nullable=True),
            sa.Column("raw_input", sa.Text, nullable=False, server_default=""),
            sa.Column("structured_json", sa.JSON, nullable=False),
            sa.Column("clarification_question", sa.Text, nullable=True),
            sa.Column("clarification_context_json", sa.JSON, nullable=False),
            sa.Column("channel", sa.String(16), nullable=True),
            sa.Column("feishu_open_id", sa.String(128), nullable=True),
            sa.Column("feishu_message_id", sa.String(128), nullable=True),
            sa.Column(
                "generated_by_prompt_id",
                sa.Integer,
                sa.ForeignKey("prompt_templates.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "generated_by_model_id",
                sa.Integer,
                sa.ForeignKey("models.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("deleted_at", sa.DateTime, nullable=True),
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
        )
        op.create_index(
            "ix_todo_items_tenant_remind", "todo_items", ["tenant_id", "remind_at"]
        )
        op.create_index(
            "ix_todo_items_feishu_status", "todo_items", ["feishu_open_id", "status"]
        )

    _seed_prompt(bind)
    _seed_triggers(bind)


def _seed_prompt(bind) -> None:
    from app.prompts.defaults import TODO_INTENT_V1

    tenant_ids = [
        row[0] for row in bind.execute(sa.text("SELECT id FROM tenants")).fetchall()
    ]
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
                    "name": "待办意图解析 v1",
                    "scene": _SCENE,
                    "content": TODO_INTENT_V1,
                    "notes": "默认 v1,0016 迁移写入",
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
                "SELECT id FROM function_bindings "
                "WHERE tenant_id = :tid AND scene = :scene"
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


def _seed_triggers(bind) -> None:
    tenant_ids = [
        row[0] for row in bind.execute(sa.text("SELECT id FROM tenants")).fetchall()
    ]
    for tid in tenant_ids:
        for spec in _NEW_TRIGGERS:
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
                       :extra_args_json, 1, :priority, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
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
    bind = op.get_bind()
    for spec in _NEW_TRIGGERS:
        bind.execute(
            sa.text("DELETE FROM feishu_trigger_rules WHERE action = :action"),
            {"action": spec["action"]},
        )
    bind.execute(
        sa.text("DELETE FROM function_bindings WHERE scene = :scene"), {"scene": _SCENE}
    )
    bind.execute(
        sa.text("DELETE FROM prompt_templates WHERE scene = :scene"), {"scene": _SCENE}
    )
    op.drop_index("ix_todo_items_feishu_status", table_name="todo_items")
    op.drop_index("ix_todo_items_tenant_remind", table_name="todo_items")
    op.drop_table("todo_items")
