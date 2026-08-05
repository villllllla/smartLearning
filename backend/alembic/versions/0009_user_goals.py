"""Job roles and user goals (PRD §15.2).

Revision ID: 0009
Revises: 0008
"""
from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

_SYSTEM_ROLES = (
    {
        "name": "后端开发 · Java · 中级",
        "family": "后端",
        "level": "mid",
        "description": "Java/Spring 后端岗位常见考点",
        "skills": (
            ("Java 基础", "Java", 120, 75),
            ("Spring 框架", "Spring", 100, 70),
            ("数据库", "MySQL", 90, 70),
            ("缓存", "Redis", 80, 70),
            ("系统设计", "系统设计", 70, 65),
        ),
    },
    {
        "name": "前端开发 · 中级",
        "family": "前端",
        "level": "mid",
        "description": "Web 前端工程与框架",
        "skills": (
            ("JavaScript", "JavaScript", 120, 75),
            ("React", "React", 100, 70),
            ("浏览器原理", "浏览器", 80, 65),
            ("工程化", "工程化", 70, 65),
        ),
    },
    {
        "name": "算法工程师 · 中级",
        "family": "算法",
        "level": "mid",
        "description": "算法与机器学习基础",
        "skills": (
            ("数据结构", "数据结构", 100, 75),
            ("算法", "算法", 120, 75),
            ("机器学习", "机器学习", 90, 70),
        ),
    },
)


def upgrade() -> None:
    op.create_table(
        "job_roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("family", sa.String(80), nullable=False, server_default=""),
        sa.Column("level", sa.String(16), nullable=False, server_default="mid"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="0"),
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
        sa.UniqueConstraint("tenant_id", "name", name="uq_job_roles_tenant_name"),
    )
    op.create_index("ix_job_roles_tenant_id", "job_roles", ["tenant_id"])

    op.create_table(
        "job_role_skills",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_role_id", sa.Integer(), sa.ForeignKey("job_roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("skill_name", sa.String(80), nullable=False),
        sa.Column("tag_name", sa.String(80), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("expected_mastery", sa.Integer(), nullable=False, server_default="70"),
    )
    op.create_index("ix_job_role_skills_role", "job_role_skills", ["job_role_id"])

    op.create_table(
        "user_goals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_role_id", sa.Integer(), sa.ForeignKey("job_roles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
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
    op.create_index("ix_user_goals_tenant_id", "user_goals", ["tenant_id"])
    op.create_index("ix_user_goals_user_id", "user_goals", ["user_id"])
    op.create_index("ix_user_goals_tenant_user_status", "user_goals", ["tenant_id", "user_id", "status"])

    op.create_table(
        "goal_progress_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_goal_id", sa.Integer(), sa.ForeignKey("user_goals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("overall_mastery", sa.Integer(), nullable=False),
        sa.Column("skill_breakdown_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("weak_tags_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("computed_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_goal_progress_snapshots_goal", "goal_progress_snapshots", ["user_goal_id"])

    bind = op.get_bind()
    now = datetime.utcnow()
    for role in _SYSTEM_ROLES:
        result = bind.execute(
            sa.text(
                """INSERT INTO job_roles (tenant_id, name, family, level, description, is_system, created_at, updated_at)
                   VALUES (NULL, :name, :family, :level, :desc, 1, :now, :now)"""
            ),
            {
                "name": role["name"],
                "family": role["family"],
                "level": role["level"],
                "desc": role["description"],
                "now": now,
            },
        )
        role_id = result.lastrowid
        for skill_name, tag_name, weight, expected in role["skills"]:
            bind.execute(
                sa.text(
                    """INSERT INTO job_role_skills (job_role_id, skill_name, tag_name, weight, expected_mastery)
                       VALUES (:rid, :sn, :tn, :w, :exp)"""
                ),
                {"rid": role_id, "sn": skill_name, "tn": tag_name, "w": weight, "exp": expected},
            )


def downgrade() -> None:
    op.drop_table("goal_progress_snapshots")
    op.drop_table("user_goals")
    op.drop_table("job_role_skills")
    op.drop_table("job_roles")
