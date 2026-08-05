"""Add interview answer generation queue + question answer status.

Revision ID: 0024
Revises: 0023
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    q_cols = {c["name"] for c in insp.get_columns("questions")}
    if "interview_answer_status" not in q_cols:
        op.add_column(
            "questions",
            sa.Column("interview_answer_status", sa.String(16), nullable=True),
        )

    if "interview_answer_jobs" not in set(insp.get_table_names()):
        op.create_table(
            "interview_answer_jobs",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column(
                "tenant_id",
                sa.Integer,
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("job_id", sa.String(64), nullable=False),
            sa.Column("doc_name", sa.String(200), nullable=False, server_default=""),
            sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
            sa.Column("context_md", sa.Text, nullable=False, server_default=""),
            sa.Column("question_ids", sa.JSON, nullable=False),
            sa.Column("cursor", sa.Integer, nullable=False, server_default="0"),
            sa.Column("completed_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("failed_count", sa.Integer, nullable=False, server_default="0"),
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
            sa.UniqueConstraint("job_id", name="uq_interview_answer_job_id"),
        )
        op.create_index(
            "ix_interview_answer_jobs_tenant_status",
            "interview_answer_jobs",
            ["tenant_id", "status"],
        )
    _seed_prompt(bind)


def _seed_prompt(bind) -> None:
    from app.prompts import defaults as d

    tenant_ids = [row[0] for row in bind.execute(sa.text("SELECT id FROM tenants")).fetchall()]
    content = d.INTERVIEW_ANSWER_V1
    for tid in tenant_ids:
        exists = bind.execute(
            sa.text(
                "SELECT id FROM prompt_templates "
                "WHERE tenant_id=:tid AND scene=:scene AND is_current=1 LIMIT 1"
            ),
            {"tid": tid, "scene": "interview_answer_generation"},
        ).scalar()
        if exists:
            continue
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
                "scene": "interview_answer_generation",
                "content": content,
                "notes": "默认 v1,0024 迁移写入",
            },
        )


def downgrade() -> None:
    op.drop_index("ix_interview_answer_jobs_tenant_status", table_name="interview_answer_jobs")
    op.drop_table("interview_answer_jobs")
    op.drop_column("questions", "interview_answer_status")
