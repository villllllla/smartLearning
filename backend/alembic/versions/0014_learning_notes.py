"""Learning notes + spaced review schedule + structuring prompt scene

Revision ID: 0014
Revises: 0013
"""
from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

_SCENE = "learning_note_structuring"


def _table_names(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    existing = _table_names(bind)

    if "learning_notes" not in existing:
        op.create_table(
            "learning_notes",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column(
                "tenant_id",
                sa.Integer,
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("raw_input", sa.Text, nullable=False),
            sa.Column("title", sa.String(200), nullable=False, server_default=""),
            sa.Column("summary", sa.Text, nullable=False, server_default=""),
            sa.Column("key_points_json", sa.JSON, nullable=False),
            sa.Column("category", sa.String(80), nullable=True),
            sa.Column("structured_json", sa.JSON, nullable=False),
            sa.Column("review_json", sa.JSON, nullable=False),
            sa.Column("quality_score", sa.Integer, nullable=True),
            sa.Column("mastered", sa.Boolean, nullable=False, server_default=sa.text("0")),
            sa.Column("interval_index", sa.Integer, nullable=False, server_default="0"),
            sa.Column("review_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("next_review_at", sa.DateTime, nullable=True),
            sa.Column("last_reviewed_at", sa.DateTime, nullable=True),
            sa.Column("last_pushed_slot", sa.String(32), nullable=True),
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
            "ix_learning_notes_tenant_next_review",
            "learning_notes",
            ["tenant_id", "next_review_at"],
        )
        op.create_index(
            "ix_learning_notes_tenant_created",
            "learning_notes",
            ["tenant_id", "created_at"],
        )

    if "learning_note_tags" not in existing:
        op.create_table(
            "learning_note_tags",
            sa.Column(
                "note_id",
                sa.Integer,
                sa.ForeignKey("learning_notes.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column(
                "tag_id",
                sa.Integer,
                sa.ForeignKey("tags.id", ondelete="CASCADE"),
                primary_key=True,
            ),
        )

    if "learning_review_schedules" not in existing:
        op.create_table(
            "learning_review_schedules",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column(
                "tenant_id",
                sa.Integer,
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("0")),
            sa.Column(
                "timezone", sa.String(64), nullable=False, server_default="Asia/Shanghai"
            ),
            sa.Column("push_times", sa.JSON, nullable=False),
            sa.Column(
                "frequency", sa.String(16), nullable=False, server_default="daily"
            ),
            sa.Column("weekdays", sa.JSON, nullable=False),
            sa.Column("intervals_days", sa.JSON, nullable=False),
            sa.Column(
                "max_notes_per_push", sa.Integer, nullable=False, server_default="5"
            ),
            sa.Column(
                "recall_mode", sa.Boolean, nullable=False, server_default=sa.text("1")
            ),
            sa.Column(
                "feishu_enabled", sa.Boolean, nullable=False, server_default=sa.text("1")
            ),
            sa.Column("last_run_slot", sa.String(32), nullable=True),
            sa.Column("last_run_at", sa.DateTime, nullable=True),
            sa.Column("last_error", sa.Text, nullable=True),
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
                "tenant_id", name="uq_learning_review_schedule_tenant"
            ),
        )

    _seed_prompt_scene(bind)


def _seed_prompt_scene(bind) -> None:
    """Seed the structuring prompt + binding for every existing tenant (idempotent)."""
    from app.prompts.defaults import LEARNING_NOTE_STRUCTURING_V1

    now = datetime.utcnow()
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
                      (:tid, :name, :scene, :content, 1, 1, :notes, :now, :now)
                    """
                ),
                {
                    "tid": tid,
                    "name": "学习总结结构化 v1",
                    "scene": _SCENE,
                    "content": LEARNING_NOTE_STRUCTURING_V1,
                    "notes": "默认 v1,0014 迁移写入",
                    "now": now,
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
                    VALUES (:tid, :scene, :prompt_id, NULL, '{}', :now, :now)
                    """
                ),
                {"tid": tid, "scene": _SCENE, "prompt_id": prompt_id, "now": now},
            )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM function_bindings WHERE scene = :scene"), {"scene": _SCENE}
    )
    bind.execute(
        sa.text("DELETE FROM prompt_templates WHERE scene = :scene"), {"scene": _SCENE}
    )
    op.drop_table("learning_note_tags")
    op.drop_table("learning_review_schedules")
    op.drop_index(
        "ix_learning_notes_tenant_created", table_name="learning_notes"
    )
    op.drop_index(
        "ix_learning_notes_tenant_next_review", table_name="learning_notes"
    )
    op.drop_table("learning_notes")
