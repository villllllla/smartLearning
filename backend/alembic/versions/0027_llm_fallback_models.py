"""Per-scene fallback models + global LLM fallback model.

Revision ID: 0027
Revises: 0026
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def _tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _columns(bind, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    b_cols = _columns(bind, "function_bindings")
    if "fallback_model_id" not in b_cols:
        op.add_column(
            "function_bindings",
            sa.Column("fallback_model_id", sa.Integer, nullable=True),
        )
    if "fallback_params_json" not in b_cols:
        op.add_column(
            "function_bindings",
            sa.Column(
                "fallback_params_json",
                sa.JSON,
                nullable=False,
                server_default="{}",
            ),
        )

    if "app_settings" in _tables(bind):
        s_cols = _columns(bind, "app_settings")
        if "llm_fallback_model_id" not in s_cols:
            op.add_column(
                "app_settings",
                sa.Column("llm_fallback_model_id", sa.Integer, nullable=True),
            )

    _backfill_interview_bindings(bind)


def _backfill_interview_bindings(bind) -> None:
    from app.prompts import defaults as d

    scene = "interview_answer_generation"
    tenant_ids = [row[0] for row in bind.execute(sa.text("SELECT id FROM tenants")).fetchall()]
    content = d.INTERVIEW_ANSWER_V1
    for tid in tenant_ids:
        binding = bind.execute(
            sa.text(
                "SELECT id, prompt_template_id FROM function_bindings "
                "WHERE tenant_id=:tid AND scene=:scene LIMIT 1"
            ),
            {"tid": tid, "scene": scene},
        ).fetchone()
        if binding is None:
            bind.execute(
                sa.text(
                    "INSERT INTO function_bindings "
                    "(tenant_id, scene, prompt_template_id, params_json, fallback_params_json, "
                    " created_at, updated_at) "
                    "VALUES (:tid, :scene, NULL, '{}', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"tid": tid, "scene": scene},
            )
            binding = bind.execute(
                sa.text(
                    "SELECT id, prompt_template_id FROM function_bindings "
                    "WHERE tenant_id=:tid AND scene=:scene LIMIT 1"
                ),
                {"tid": tid, "scene": scene},
            ).fetchone()
        if binding and binding[1] is not None:
            continue
        prompt_id = bind.execute(
            sa.text(
                "SELECT id FROM prompt_templates "
                "WHERE tenant_id=:tid AND scene=:scene AND is_current=1 LIMIT 1"
            ),
            {"tid": tid, "scene": scene},
        ).scalar()
        if prompt_id is None:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO prompt_templates
                      (tenant_id, name, scene, content, version_no, is_current, notes,
                       created_at, updated_at)
                    VALUES
                      (:tid, :name, :scene, :content, 1, 1, :notes,
                       CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """
                ),
                {
                    "tid": tid,
                    "name": "面经参考答案 v1",
                    "scene": scene,
                    "content": content,
                    "notes": "默认 v1,0027 迁移写入",
                },
            )
            prompt_id = bind.execute(
                sa.text(
                    "SELECT id FROM prompt_templates "
                    "WHERE tenant_id=:tid AND scene=:scene AND is_current=1 LIMIT 1"
                ),
                {"tid": tid, "scene": scene},
            ).scalar()
        if prompt_id and binding:
            bind.execute(
                sa.text(
                    "UPDATE function_bindings SET prompt_template_id=:pid, "
                    "updated_at=CURRENT_TIMESTAMP WHERE id=:id"
                ),
                {"pid": prompt_id, "id": binding[0]},
            )


def downgrade() -> None:
    if "app_settings" in _tables(op.get_bind()):
        cols = _columns(op.get_bind(), "app_settings")
        if "llm_fallback_model_id" in cols:
            op.drop_column("app_settings", "llm_fallback_model_id")
    cols = _columns(op.get_bind(), "function_bindings")
    if "fallback_params_json" in cols:
        op.drop_column("function_bindings", "fallback_params_json")
    if "fallback_model_id" in cols:
        op.drop_column("function_bindings", "fallback_model_id")
