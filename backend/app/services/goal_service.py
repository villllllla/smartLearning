"""Job roles, user goals, and progress computation (PRD §15.2)."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import desc, func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.models import AnswerAttempt, JobRole, JobRoleSkill, Question, Tag, UserGoal
from app.models.goal import GoalProgressSnapshot
from app.models.question import QuestionTag
from app.schemas.goal import (
    GoalProgressOut,
    JobRoleOut,
    JobRoleSkillOut,
    SkillProgressOut,
    UserGoalOut,
    WeakTagOut,
)
from app.schemas.practice import PracticeSetupRequest, PracticeSetupResponse

_LOW_COVERAGE_THRESHOLD = 0.2
_WEAK_GAP = 10


def list_job_roles(
    db: Session, *, tenant_id: int, q: str | None = None
) -> list[JobRole]:
    stmt = (
        select(JobRole)
        .where(or_(JobRole.is_system.is_(True), JobRole.tenant_id == tenant_id))
        .options(selectinload(JobRole.skills))
        .order_by(JobRole.is_system.desc(), JobRole.name.asc())
    )
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(JobRole.name.ilike(like), JobRole.family.ilike(like))
        )
    return list(db.execute(stmt).scalars().unique().all())


def get_job_role(db: Session, role_id: int, *, tenant_id: int) -> JobRole | None:
    return db.execute(
        select(JobRole)
        .where(
            JobRole.id == role_id,
            or_(JobRole.is_system.is_(True), JobRole.tenant_id == tenant_id),
        )
        .options(selectinload(JobRole.skills))
    ).scalar_one_or_none()


def create_custom_job_role(
    db: Session,
    *,
    tenant_id: int,
    name: str,
    family: str,
    level: str,
    description: str,
    skills: list[dict],
) -> JobRole:
    existing = db.execute(
        select(JobRole.id).where(JobRole.tenant_id == tenant_id, JobRole.name == name)
    ).scalar_one_or_none()
    if existing:
        raise ValueError("同名岗位已存在")
    role = JobRole(
        tenant_id=tenant_id,
        name=name.strip(),
        family=family.strip(),
        level=level.strip() or "mid",
        description=description.strip(),
        is_system=False,
    )
    db.add(role)
    db.flush()
    for raw in skills:
        sn = str(raw.get("skill_name") or raw.get("tag_name") or "").strip()
        tn = str(raw.get("tag_name") or sn).strip()
        if not tn:
            continue
        db.add(
            JobRoleSkill(
                job_role_id=role.id,
                skill_name=sn or tn,
                tag_name=tn,
                weight=int(raw.get("weight") or 100),
                expected_mastery=int(raw.get("expected_mastery") or 70),
            )
        )
    db.flush()
    return role


def job_role_to_out(role: JobRole) -> JobRoleOut:
    return JobRoleOut(
        id=role.id,
        name=role.name,
        family=role.family,
        level=role.level,
        description=role.description,
        is_system=role.is_system,
        skills=[
            JobRoleSkillOut(
                id=s.id,
                skill_name=s.skill_name,
                tag_name=s.tag_name,
                weight=s.weight,
                expected_mastery=s.expected_mastery,
            )
            for s in role.skills
        ],
    )


def goal_to_out(goal: UserGoal) -> UserGoalOut:
    return UserGoalOut(
        id=goal.id,
        job_role_id=goal.job_role_id,
        job_role_name=goal.job_role.name if goal.job_role else "",
        target_date=goal.target_date,
        status=goal.status,  # type: ignore[arg-type]
        created_at=goal.created_at,
    )


def list_user_goals(
    db: Session, *, tenant_id: int, user_id: int, status: str | None = None
) -> list[UserGoal]:
    stmt = (
        select(UserGoal)
        .where(UserGoal.tenant_id == tenant_id, UserGoal.user_id == user_id)
        .options(selectinload(UserGoal.job_role))
        .order_by(UserGoal.created_at.desc())
    )
    if status:
        stmt = stmt.where(UserGoal.status == status)
    return list(db.execute(stmt).scalars().unique().all())


def get_active_goal(db: Session, *, tenant_id: int, user_id: int) -> UserGoal | None:
    return db.execute(
        select(UserGoal)
        .where(
            UserGoal.tenant_id == tenant_id,
            UserGoal.user_id == user_id,
            UserGoal.status == "active",
        )
        .options(selectinload(UserGoal.job_role).selectinload(JobRole.skills))
        .order_by(UserGoal.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _archive_other_active_goals(
    db: Session, *, tenant_id: int, user_id: int, except_goal_id: int | None = None
) -> None:
    stmt = (
        update(UserGoal)
        .where(
            UserGoal.tenant_id == tenant_id,
            UserGoal.user_id == user_id,
            UserGoal.status == "active",
        )
        .values(status="archived")
    )
    if except_goal_id is not None:
        stmt = stmt.where(UserGoal.id != except_goal_id)
    db.execute(stmt)


def create_user_goal(
    db: Session,
    *,
    tenant_id: int,
    user_id: int,
    job_role_id: int,
    target_date: date | None,
) -> UserGoal:
    role = get_job_role(db, job_role_id, tenant_id=tenant_id)
    if role is None:
        raise ValueError("岗位不存在")
    _archive_other_active_goals(db, tenant_id=tenant_id, user_id=user_id)
    goal = UserGoal(
        tenant_id=tenant_id,
        user_id=user_id,
        job_role_id=job_role_id,
        target_date=target_date,
        status="active",
    )
    db.add(goal)
    db.flush()
    goal.job_role = role
    return goal


def get_user_goal(
    db: Session, goal_id: int, *, tenant_id: int, user_id: int
) -> UserGoal | None:
    return db.execute(
        select(UserGoal)
        .where(
            UserGoal.id == goal_id,
            UserGoal.tenant_id == tenant_id,
            UserGoal.user_id == user_id,
        )
        .options(selectinload(UserGoal.job_role).selectinload(JobRole.skills))
    ).scalar_one_or_none()


def update_user_goal(
    db: Session,
    goal: UserGoal,
    *,
    tenant_id: int,
    job_role_id: int | None = None,
    target_date: date | None = None,
    status: str | None = None,
    clear_target_date: bool = False,
) -> UserGoal:
    if job_role_id is not None and job_role_id != goal.job_role_id:
        role = get_job_role(db, job_role_id, tenant_id=tenant_id)
        if role is None:
            raise ValueError("岗位不存在")
        goal.job_role_id = job_role_id
        goal.job_role = role
    if clear_target_date:
        goal.target_date = None
    elif target_date is not None:
        goal.target_date = target_date
    if status is not None and status != goal.status:
        if status == "active":
            _archive_other_active_goals(
                db,
                tenant_id=tenant_id,
                user_id=goal.user_id,
                except_goal_id=goal.id,
            )
        goal.status = status
    db.flush()
    return goal


def delete_user_goal(db: Session, goal: UserGoal) -> None:
    db.delete(goal)
    db.flush()


def _resolve_tag(db: Session, *, tenant_id: int, tag_name: str) -> Tag | None:
    return db.execute(
        select(Tag).where(
            Tag.tenant_id == tenant_id,
            func.lower(Tag.name) == tag_name.lower(),
        )
    ).scalar_one_or_none()


def _question_ids_for_tag(db: Session, *, tenant_id: int, tag_id: int) -> list[int]:
    return list(
        db.execute(
            select(Question.id)
            .join(QuestionTag, QuestionTag.question_id == Question.id)
            .where(
                QuestionTag.tag_id == tag_id,
                Question.tenant_id == tenant_id,
                Question.deleted_at.is_(None),
            )
        ).scalars().all()
    )


def _latest_attempt_scores(
    db: Session, question_ids: list[int]
) -> dict[int, tuple[int, int, int, int]]:
    if not question_ids:
        return {}
    rn = (
        func.row_number()
        .over(partition_by=AnswerAttempt.question_id, order_by=desc(AnswerAttempt.created_at))
        .label("rn")
    )
    inner = (
        select(
            AnswerAttempt.question_id,
            AnswerAttempt.score_correctness,
            AnswerAttempt.score_completeness,
            AnswerAttempt.score_structure,
            AnswerAttempt.score_depth,
            rn,
        )
        .where(AnswerAttempt.question_id.in_(question_ids))
        .subquery()
    )
    rows = db.execute(select(inner).where(inner.c.rn == 1)).all()
    out: dict[int, tuple[int, int, int, int]] = {}
    for row in rows:
        out[row.question_id] = (
            row.score_correctness,
            row.score_completeness,
            row.score_structure,
            row.score_depth,
        )
    return out


def _mastery_from_scores(c: int, comp: int, struct: int, depth: int) -> int:
    return int(round((c + comp + struct + depth) / 4))


def compute_skill_progress(
    db: Session, *, tenant_id: int, skill: JobRoleSkill
) -> SkillProgressOut:
    tag = _resolve_tag(db, tenant_id=tenant_id, tag_name=skill.tag_name)
    if tag is None:
        return SkillProgressOut(
            skill_name=skill.skill_name,
            tag_name=skill.tag_name,
            tag_id=None,
            weight=skill.weight,
            expected_mastery=skill.expected_mastery,
            mastery=0,
            question_total=0,
            question_attempted=0,
            coverage=0.0,
            low_coverage=True,
        )
    qids = _question_ids_for_tag(db, tenant_id=tenant_id, tag_id=tag.id)
    total = len(qids)
    if total == 0:
        return SkillProgressOut(
            skill_name=skill.skill_name,
            tag_name=skill.tag_name,
            tag_id=tag.id,
            weight=skill.weight,
            expected_mastery=skill.expected_mastery,
            mastery=0,
            question_total=0,
            question_attempted=0,
            coverage=0.0,
            low_coverage=True,
        )
    scores = _latest_attempt_scores(db, qids)
    attempted = len(scores)
    if attempted == 0:
        mastery = 0
    else:
        mastery = int(
            round(
                sum(_mastery_from_scores(*s) for s in scores.values()) / attempted
            )
        )
    coverage = attempted / total
    return SkillProgressOut(
        skill_name=skill.skill_name,
        tag_name=skill.tag_name,
        tag_id=tag.id,
        weight=skill.weight,
        expected_mastery=skill.expected_mastery,
        mastery=mastery,
        question_total=total,
        question_attempted=attempted,
        coverage=round(coverage, 3),
        low_coverage=coverage < _LOW_COVERAGE_THRESHOLD and total > 0,
    )


def compute_goal_progress(
    db: Session, goal: UserGoal, *, save_snapshot: bool = True
) -> GoalProgressOut:
    role = goal.job_role
    if role is None:
        raise ValueError("目标岗位不存在")
    skills: list[SkillProgressOut] = []
    weighted_sum = 0
    weight_total = 0
    low_coverage_count = 0
    for skill in role.skills:
        sp = compute_skill_progress(db, tenant_id=goal.tenant_id, skill=skill)
        skills.append(sp)
        if sp.weight > 0:
            weighted_sum += sp.mastery * sp.weight
            weight_total += sp.weight
        if sp.low_coverage:
            low_coverage_count += 1
    overall = int(round(weighted_sum / weight_total)) if weight_total else 0

    weak: list[WeakTagOut] = []
    for sp in skills:
        gap = sp.expected_mastery - sp.mastery
        if gap >= _WEAK_GAP or sp.mastery < sp.expected_mastery:
            weak.append(
                WeakTagOut(
                    tag_name=sp.tag_name,
                    tag_id=sp.tag_id,
                    mastery=sp.mastery,
                    expected_mastery=sp.expected_mastery,
                    gap=max(0, gap),
                )
            )
    weak.sort(key=lambda x: (-x.gap, x.mastery))

    coverage_note = None
    if low_coverage_count > 0:
        coverage_note = (
            f"有 {low_coverage_count} 个能力点题目覆盖不足（作答率 < "
            f"{int(_LOW_COVERAGE_THRESHOLD * 100)}%），掌握度仅供参考。"
        )

    now = datetime.utcnow()
    if save_snapshot:
        snap = GoalProgressSnapshot(
            user_goal_id=goal.id,
            overall_mastery=overall,
            skill_breakdown_json=[s.model_dump() for s in skills],
            weak_tags_json=[w.model_dump() for w in weak[:10]],
            computed_at=now,
        )
        db.add(snap)
        db.flush()

    trend_rows = db.execute(
        select(GoalProgressSnapshot)
        .where(GoalProgressSnapshot.user_goal_id == goal.id)
        .order_by(GoalProgressSnapshot.computed_at.desc())
        .limit(14)
    ).scalars().all()
    trend = [
        {"computed_at": r.computed_at, "overall_mastery": r.overall_mastery}
        for r in reversed(trend_rows)
    ]

    return GoalProgressOut(
        goal=goal_to_out(goal),
        overall_mastery=overall,
        skills=skills,
        weak_tags=weak[:8],
        trend=trend,
        coverage_note=coverage_note,
    )


def recommend_practice_for_goal(
    db: Session, goal: UserGoal, *, limit: int = 10
) -> PracticeSetupResponse:
    progress = compute_goal_progress(db, goal, save_snapshot=False)
    weak_tag_ids = [w.tag_id for w in progress.weak_tags if w.tag_id is not None][:3]
    if not weak_tag_ids:
        weak_tag_ids = [
            s.tag_id for s in progress.skills if s.tag_id and s.mastery < s.expected_mastery
        ][:3]
    payload = PracticeSetupRequest(
        tag_ids=weak_tag_ids,
        tag_mode="or",
        mode="random",
        limit=min(limit, 20),
    )
    from app.services.practice_service import setup_questions

    return setup_questions(db, payload, tenant_id=goal.tenant_id)
