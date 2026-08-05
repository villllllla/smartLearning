"""Job roles, user goals, and progress snapshots (PRD §15.2)."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class JobRole(Base, TimestampMixin):
    __tablename__ = "job_roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    family: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="mid")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_system: Mapped[bool] = mapped_column(default=False, nullable=False)

    skills: Mapped[list["JobRoleSkill"]] = relationship(
        back_populates="job_role", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_job_roles_tenant_name"),
    )


class JobRoleSkill(Base):
    __tablename__ = "job_role_skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_role_id: Mapped[int] = mapped_column(
        ForeignKey("job_roles.id", ondelete="CASCADE"), nullable=False
    )
    skill_name: Mapped[str] = mapped_column(String(80), nullable=False)
    tag_name: Mapped[str] = mapped_column(String(80), nullable=False)
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    expected_mastery: Mapped[int] = mapped_column(Integer, nullable=False, default=70)

    job_role: Mapped[JobRole] = relationship(back_populates="skills")

    __table_args__ = (Index("ix_job_role_skills_role", "job_role_id"),)


class UserGoal(Base, TimestampMixin):
    __tablename__ = "user_goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_role_id: Mapped[int] = mapped_column(
        ForeignKey("job_roles.id", ondelete="RESTRICT"), nullable=False
    )
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")

    job_role: Mapped[JobRole] = relationship()
    snapshots: Mapped[list["GoalProgressSnapshot"]] = relationship(
        back_populates="user_goal", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_user_goals_tenant_user_status", "tenant_id", "user_id", "status"),
    )


class GoalProgressSnapshot(Base):
    __tablename__ = "goal_progress_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_goal_id: Mapped[int] = mapped_column(
        ForeignKey("user_goals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    overall_mastery: Mapped[int] = mapped_column(Integer, nullable=False)
    skill_breakdown_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    weak_tags_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    computed_at: Mapped[datetime] = mapped_column(nullable=False)

    user_goal: Mapped[UserGoal] = relationship(back_populates="snapshots")
