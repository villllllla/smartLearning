"""Interview question group key + job question_groups for packed queue batches.

Revision ID: 0025
Revises: 0024
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    q_cols = {c["name"] for c in insp.get_columns("questions")}
    if "interview_group_key" not in q_cols:
        op.add_column(
            "questions",
            sa.Column("interview_group_key", sa.String(128), nullable=True),
        )

    j_cols = {c["name"] for c in insp.get_columns("interview_answer_jobs")}
    if "question_groups" not in j_cols:
        op.add_column(
            "interview_answer_jobs",
            sa.Column("question_groups", sa.JSON, nullable=False, server_default="[]"),
        )

    _refresh_interview_answer_prompt(bind)


def _refresh_interview_answer_prompt(bind) -> None:
    from app.prompts import defaults as d

    content = d.INTERVIEW_ANSWER_V1
    if "{GROUP_LABEL}" not in content:
        return
    tenant_ids = [row[0] for row in bind.execute(sa.text("SELECT id FROM tenants")).fetchall()]
    for tid in tenant_ids:
        row = bind.execute(
            sa.text(
                "SELECT id, content FROM prompt_templates "
                "WHERE tenant_id=:tid AND scene=:scene AND is_current=1 LIMIT 1"
            ),
            {"tid": tid, "scene": "interview_answer_generation"},
        ).fetchone()
        if row is None:
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
                    "notes": "默认 v1,0025 迁移写入",
                },
            )
            continue
        if "{GROUP_LABEL}" in (row[1] or ""):
            continue
        bind.execute(
            sa.text(
                "UPDATE prompt_templates SET content=:content, updated_at=CURRENT_TIMESTAMP "
                "WHERE id=:id"
            ),
            {"id": row[0], "content": content},
        )


def downgrade() -> None:
    op.drop_column("interview_answer_jobs", "question_groups")
    op.drop_column("questions", "interview_group_key")
