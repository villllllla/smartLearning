"""Tests for goal progress computation."""
from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models import (
    AnswerAttempt,
    JobRole,
    JobRoleSkill,
    Question,
    QuestionBankCollection,
    Tag,
    Tenant,
    User,
    UserGoal,
)
from app.models.question import QuestionTag
from app.services import goal_service


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_compute_goal_progress_weighted():
    db = _session()
    tenant = Tenant(name="t", slug="t")
    db.add(tenant)
    db.flush()
    user = User(
        tenant_id=tenant.id,
        email="u@local",
        password_hash="x",
        display_name="u",
        role="admin",
    )
    db.add(user)
    coll = QuestionBankCollection(tenant_id=tenant.id, name="c")
    db.add(coll)
    tag_java = Tag(tenant_id=tenant.id, name="Java", kind="user")
    tag_redis = Tag(tenant_id=tenant.id, name="Redis", kind="user")
    db.add_all([tag_java, tag_redis])
    db.flush()

    role = JobRole(
        tenant_id=None,
        name="Test Role",
        family="后端",
        level="mid",
        is_system=True,
    )
    db.add(role)
    db.flush()
    db.add_all(
        [
            JobRoleSkill(
                job_role_id=role.id,
                skill_name="Java",
                tag_name="Java",
                weight=100,
                expected_mastery=70,
            ),
            JobRoleSkill(
                job_role_id=role.id,
                skill_name="Redis",
                tag_name="Redis",
                weight=50,
                expected_mastery=70,
            ),
        ]
    )

    q1 = Question(
        tenant_id=tenant.id,
        collection_id=coll.id,
        question_text="q1",
        answer_standard="a1",
        difficulty="medium",
        qtype="concept",
    )
    q2 = Question(
        tenant_id=tenant.id,
        collection_id=coll.id,
        question_text="q2",
        answer_standard="a2",
        difficulty="medium",
        qtype="concept",
    )
    db.add_all([q1, q2])
    db.flush()
    db.add_all(
        [
            QuestionTag(question_id=q1.id, tag_id=tag_java.id),
            QuestionTag(question_id=q2.id, tag_id=tag_redis.id),
        ]
    )
    db.add(
        AnswerAttempt(
            question_id=q1.id,
            user_answer_text="ans",
            grade="A",
            score_correctness=85,
            score_completeness=80,
            score_structure=75,
            score_depth=70,
            feedback_text="ok",
        )
    )
    db.flush()

    goal = UserGoal(
        tenant_id=tenant.id,
        user_id=user.id,
        job_role_id=role.id,
        status="active",
    )
    db.add(goal)
    db.flush()
    goal.job_role = role

    progress = goal_service.compute_goal_progress(db, goal, save_snapshot=False)
    java_skill = next(s for s in progress.skills if s.tag_name == "Java")
    assert java_skill.mastery == 78  # (85+80+75+70)/4 = 77.5 -> 78
    assert java_skill.question_attempted == 1
    assert progress.overall_mastery > 0
    assert any(w.tag_name == "Redis" for w in progress.weak_tags)


def test_update_user_goal_archives_other_active():
    db = _session()
    tenant = Tenant(name="t", slug="t")
    db.add(tenant)
    db.flush()
    user = User(
        tenant_id=tenant.id,
        email="u@local",
        password_hash="x",
        display_name="u",
        role="admin",
    )
    db.add(user)
    role_a = JobRole(tenant_id=None, name="Role A", family="后端", level="mid", is_system=True)
    role_b = JobRole(tenant_id=None, name="Role B", family="后端", level="mid", is_system=True)
    db.add_all([role_a, role_b])
    db.flush()
    goal_a = UserGoal(
        tenant_id=tenant.id, user_id=user.id, job_role_id=role_a.id, status="active"
    )
    goal_b = UserGoal(
        tenant_id=tenant.id, user_id=user.id, job_role_id=role_b.id, status="archived"
    )
    db.add_all([goal_a, goal_b])
    db.flush()

    goal_service.update_user_goal(db, goal_b, tenant_id=tenant.id, status="active")
    db.refresh(goal_a)
    db.refresh(goal_b)
    assert goal_a.status == "archived"
    assert goal_b.status == "active"


def test_update_user_goal_change_role_and_clear_date():
    db = _session()
    tenant = Tenant(name="t", slug="t")
    db.add(tenant)
    db.flush()
    user = User(
        tenant_id=tenant.id,
        email="u@local",
        password_hash="x",
        display_name="u",
        role="admin",
    )
    db.add(user)
    role_a = JobRole(tenant_id=None, name="Role A", family="后端", level="mid", is_system=True)
    role_b = JobRole(tenant_id=None, name="Role B", family="后端", level="mid", is_system=True)
    db.add_all([role_a, role_b])
    db.flush()
    goal = UserGoal(
        tenant_id=tenant.id,
        user_id=user.id,
        job_role_id=role_a.id,
        status="active",
        target_date=date(2026, 12, 31),
    )
    db.add(goal)
    db.flush()
    goal.job_role = role_a

    goal_service.update_user_goal(
        db,
        goal,
        tenant_id=tenant.id,
        job_role_id=role_b.id,
        clear_target_date=True,
    )
    assert goal.job_role_id == role_b.id
    assert goal.target_date is None


def test_delete_user_goal():
    db = _session()
    tenant = Tenant(name="t", slug="t")
    db.add(tenant)
    db.flush()
    user = User(
        tenant_id=tenant.id,
        email="u@local",
        password_hash="x",
        display_name="u",
        role="admin",
    )
    db.add(user)
    role = JobRole(tenant_id=None, name="Role", family="后端", level="mid", is_system=True)
    db.add(role)
    db.flush()
    goal = UserGoal(
        tenant_id=tenant.id, user_id=user.id, job_role_id=role.id, status="active"
    )
    db.add(goal)
    db.flush()
    goal_id = goal.id

    goal_service.delete_user_goal(db, goal)
    assert db.get(UserGoal, goal_id) is None
