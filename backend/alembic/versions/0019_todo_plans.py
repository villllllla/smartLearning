"""Study plans + todo plan/defer/snooze columns + daily check schedule
+ plan_decomposition / todo_motivation prompts

Revision ID: 0019
Revises: 0018
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

_SCENES = (
    ("plan_decomposition", "计划分解 v1", "PLAN_DECOMPOSITION_V1"),
    ("todo_motivation", "待办激励 v1", "TODO_MOTIVATION_V1"),
)


def _tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _columns(bind, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)

    if "study_plans" not in tables:
        op.create_table(
            "study_plans",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column(
                "tenant_id", sa.Integer,
                sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column("title", sa.String(200), nullable=False, server_default=""),
            sa.Column("goal", sa.Text, nullable=True),
            sa.Column("start_date", sa.Date, nullable=False),
            sa.Column("end_date", sa.Date, nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default="active"),
            sa.Column("raw_input", sa.Text, nullable=False, server_default=""),
            sa.Column("structured_json", sa.JSON, nullable=False),
            sa.Column("channel", sa.String(16), nullable=True),
            sa.Column("feishu_open_id", sa.String(128), nullable=True),
            sa.Column(
                "generated_by_prompt_id", sa.Integer,
                sa.ForeignKey("prompt_templates.id", ondelete="SET NULL"), nullable=True,
            ),
            sa.Column(
                "generated_by_model_id", sa.Integer,
                sa.ForeignKey("models.id", ondelete="SET NULL"), nullable=True,
            ),
            sa.Column("deleted_at", sa.DateTime, nullable=True),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
        )
        op.create_index("ix_study_plans_tenant_status", "study_plans", ["tenant_id", "status"])

    if "todo_check_schedules" not in tables:
        op.create_table(
            "todo_check_schedules",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column(
                "tenant_id", sa.Integer,
                sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.false()),
            sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Shanghai"),
            sa.Column("check_time", sa.String(8), nullable=False, server_default="08:00"),
            sa.Column("push_today_plan", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("feishu_enabled", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("last_run_slot", sa.String(32), nullable=True),
            sa.Column("last_run_at", sa.DateTime, nullable=True),
            sa.Column("last_error", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
            sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp(), nullable=False),
            sa.UniqueConstraint("tenant_id", name="uq_todo_check_schedule_tenant"),
        )

    if "todo_items" in tables:
        cols = _columns(bind, "todo_items")
        adds = [
            ("plan_id", sa.Column("plan_id", sa.Integer, nullable=True)),
            ("plan_date", sa.Column("plan_date", sa.Date, nullable=True)),
            ("original_plan_date", sa.Column("original_plan_date", sa.Date, nullable=True)),
            ("defer_count", sa.Column("defer_count", sa.Integer, nullable=False, server_default="0")),
            ("snooze_until", sa.Column("snooze_until", sa.Date, nullable=True)),
            ("snooze_note", sa.Column("snooze_note", sa.Text, nullable=True)),
        ]
        for name, col in adds:
            if name not in cols:
                op.add_column("todo_items", col)
        op.create_index(
            "ix_todo_items_tenant_plan_date", "todo_items", ["tenant_id", "plan_date"]
        )
        # Backfill plan_date for existing todos from remind_at (or created_at).
        bind.execute(
            sa.text(
                "UPDATE todo_items SET plan_date = date(COALESCE(remind_at, created_at)) "
                "WHERE plan_date IS NULL"
            )
        )

    _seed_prompts(bind)


def _seed_prompts(bind) -> None:
    from app.prompts import defaults as d

    tenant_ids = [row[0] for row in bind.execute(sa.text("SELECT id FROM tenants")).fetchall()]
    for tid in tenant_ids:
        for scene, name, const in _SCENES:
            content = getattr(d, const)
            exists = bind.execute(
                sa.text(
                    "SELECT id FROM prompt_templates "
                    "WHERE tenant_id = :tid AND scene = :scene AND is_current = 1"
                ),
                {"tid": tid, "scene": scene},
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
                    {"tid": tid, "name": name, "scene": scene, "content": content,
                     "notes": "默认 v1,0019 迁移写入"},
                )
            prompt_id = bind.execute(
                sa.text(
                    "SELECT id FROM prompt_templates "
                    "WHERE tenant_id = :tid AND scene = :scene AND is_current = 1"
                ),
                {"tid": tid, "scene": scene},
            ).scalar()
            binding_exists = bind.execute(
                sa.text(
                    "SELECT id FROM function_bindings WHERE tenant_id = :tid AND scene = :scene"
                ),
                {"tid": tid, "scene": scene},
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
                    {"tid": tid, "scene": scene, "prompt_id": prompt_id},
                )


def downgrade() -> None:
    bind = op.get_bind()
    for scene, _, _ in _SCENES:
        bind.execute(sa.text("DELETE FROM function_bindings WHERE scene = :s"), {"s": scene})
        bind.execute(sa.text("DELETE FROM prompt_templates WHERE scene = :s"), {"s": scene})
    if "todo_items" in _tables(bind):
        cols = _columns(bind, "todo_items")
        for name in ("snooze_note", "snooze_until", "defer_count", "original_plan_date", "plan_date", "plan_id"):
            if name in cols:
                op.drop_column("todo_items", name)
    op.drop_table("todo_check_schedules")
    op.drop_table("study_plans")
