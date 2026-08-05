"""Study plans: LLM decomposition into daily tasks, preview, and persistence."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.todo import StudyPlan, TodoItem
from app.services.llm import LLMClient, LLMMessage

log = logging.getLogger(__name__)

_DECOMPOSE_SCHEMA: dict = {
    "type": "object",
    "required": ["tasks"],
    "properties": {
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["date", "title"],
                "properties": {
                    "date": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                },
            },
        }
    },
    "additionalProperties": True,
}

_MAX_TASKS = 120


@dataclass
class PlanTaskDraft:
    date: date
    title: str
    description: str = ""


@dataclass
class DecomposeResult:
    tasks: list[PlanTaskDraft] = field(default_factory=list)
    prompt_id: int | None = None
    model_id: int | None = None


def _parse_date(s: str) -> date | None:
    try:
        return date.fromisoformat(str(s).strip()[:10])
    except (ValueError, TypeError):
        return None


async def decompose_plan(
    db: Session,
    *,
    tenant_id: int,
    title: str,
    goal: str,
    start_date: date,
    end_date: date,
    timezone_name: str = "Asia/Shanghai",
) -> DecomposeResult:
    if end_date < start_date:
        raise ValueError("结束日期不能早于开始日期")

    client, prompt = LLMClient.for_scene(db, "plan_decomposition", tenant_id=tenant_id)
    rendered = (
        prompt.content.replace("{TITLE}", title)
        .replace("{GOAL}", goal or title)
        .replace("{START_DATE}", start_date.isoformat())
        .replace("{END_DATE}", end_date.isoformat())
        .replace("{TODAY}", date.today().isoformat())
        .replace("{TIMEZONE}", timezone_name)
    )
    data, _ = await client.chat_json(
        [LLMMessage(role="user", content=rendered)], schema=_DECOMPOSE_SCHEMA
    )

    tasks: list[PlanTaskDraft] = []
    for row in data.get("tasks", []):
        d = _parse_date(row.get("date"))
        t = str(row.get("title") or "").strip()[:200]
        if d is None or not t:
            continue
        if d < start_date or d > end_date:
            continue  # keep the model honest about the range
        tasks.append(
            PlanTaskDraft(
                date=d,
                title=t,
                description=str(row.get("description") or "").strip()[:400],
            )
        )
        if len(tasks) >= _MAX_TASKS:
            break
    tasks.sort(key=lambda x: (x.date, x.title))
    return DecomposeResult(tasks=tasks, prompt_id=prompt.id, model_id=client.model.id)


def create_plan(
    db: Session,
    *,
    tenant_id: int,
    title: str,
    goal: str | None,
    start_date: date,
    end_date: date,
    tasks: list[PlanTaskDraft],
    raw_input: str = "",
    channel: str = "web",
    feishu_open_id: str | None = None,
    prompt_id: int | None = None,
    model_id: int | None = None,
) -> StudyPlan:
    if not tasks:
        raise ValueError("计划没有任何任务，无法创建")
    from app.services.todo_service import _combine_plan_datetime, default_timezone

    tz_name = default_timezone(db, tenant_id=tenant_id)
    plan = StudyPlan(
        tenant_id=tenant_id,
        title=title.strip()[:200] or "学习计划",
        goal=(goal or "").strip() or None,
        start_date=start_date,
        end_date=end_date,
        status="active",
        raw_input=raw_input,
        structured_json={"task_count": len(tasks)},
        channel=channel,
        feishu_open_id=feishu_open_id,
        generated_by_prompt_id=prompt_id,
        generated_by_model_id=model_id,
    )
    db.add(plan)
    db.flush()

    for t in tasks:
        db.add(
            TodoItem(
                tenant_id=tenant_id,
                title=t.title,
                description=t.description or None,
                status="scheduled",
                plan_id=plan.id,
                plan_date=t.date,
                original_plan_date=t.date,
                defer_count=0,
                remind_at=_combine_plan_datetime(t.date, None, tz_name),
                timezone=tz_name,
                raw_input=t.title,
                structured_json={"from_plan": plan.id},
                channel=channel,
                feishu_open_id=feishu_open_id,
            )
        )
    db.flush()
    return plan


def list_plans(db: Session, *, tenant_id: int) -> list[StudyPlan]:
    return list(
        db.execute(
            select(StudyPlan)
            .where(StudyPlan.tenant_id == tenant_id, StudyPlan.deleted_at.is_(None))
            .order_by(StudyPlan.created_at.desc())
        ).scalars().all()
    )


def get_plan(db: Session, plan_id: int, *, tenant_id: int) -> StudyPlan | None:
    return db.execute(
        select(StudyPlan).where(
            StudyPlan.id == plan_id,
            StudyPlan.tenant_id == tenant_id,
            StudyPlan.deleted_at.is_(None),
        )
    ).scalar_one_or_none()


def plan_progress(db: Session, plan: StudyPlan) -> tuple[int, int]:
    """Return (done_count, total_count) for a plan's tasks."""
    rows = db.execute(
        select(TodoItem.status).where(
            TodoItem.plan_id == plan.id, TodoItem.deleted_at.is_(None)
        )
    ).scalars().all()
    total = len(rows)
    done = sum(1 for s in rows if s == "done")
    return done, total


def delete_plan(db: Session, plan: StudyPlan, *, drop_tasks: bool = True) -> None:
    """Soft-delete a plan. Optionally soft-delete its not-done tasks."""
    plan.deleted_at = datetime.utcnow()
    if drop_tasks:
        tasks = db.execute(
            select(TodoItem).where(
                TodoItem.plan_id == plan.id,
                TodoItem.deleted_at.is_(None),
                TodoItem.status != "done",
            )
        ).scalars().all()
        for t in tasks:
            t.deleted_at = datetime.utcnow()
    db.flush()
