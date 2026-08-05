"""Learning notes: LLM validation + structuring, CRUD, spaced repetition."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import LearningNote, LearningNoteTag, Tag
from app.services.llm import LLMClient, LLMMessage

log = logging.getLogger(__name__)

DEFAULT_INTERVALS_DAYS = [1, 3, 7, 15, 30]
# "已掌握" is a de-prioritisation, not a stop: the note keeps its place in the
# queue but its interval is stretched by this factor and it yields the per-push
# quota to notes that are still being learned.
DEFAULT_MASTERED_FACTOR = 3.0
MAX_MASTERED_FACTOR = 20.0

STRUCTURE_SCHEMA: dict = {
    "type": "object",
    "required": ["title", "summary", "key_points", "tags"],
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "tags": {"type": "array", "items": {"type": "string"}},
        "category": {"type": "string"},
        "issues": {"type": "array", "items": {"type": "string"}},
        "corrections": {"type": "array", "items": {"type": "string"}},
        "suggestions": {"type": "array", "items": {"type": "string"}},
        "quality_score": {"type": "integer", "minimum": 0, "maximum": 100},
    },
    "additionalProperties": True,
}


def _upsert_tag(db: Session, name: str, *, tenant_id: int) -> Tag | None:
    name = (name or "").strip()
    if not name:
        return None
    existing = db.execute(
        select(Tag).where(Tag.tenant_id == tenant_id, Tag.name == name)
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    t = Tag(tenant_id=tenant_id, name=name, kind="user")
    db.add(t)
    db.flush()
    return t


def _schedule_row(db: Session, *, tenant_id: int):
    from app.models import LearningReviewSchedule

    return db.execute(
        select(LearningReviewSchedule).where(
            LearningReviewSchedule.tenant_id == tenant_id
        )
    ).scalar_one_or_none()


def get_review_intervals(db: Session, *, tenant_id: int) -> list[int]:
    row = _schedule_row(db, tenant_id=tenant_id)
    if row and row.intervals_days:
        return [int(d) for d in row.intervals_days if int(d) > 0] or list(
            DEFAULT_INTERVALS_DAYS
        )
    return list(DEFAULT_INTERVALS_DAYS)


def get_mastered_factor(db: Session, *, tenant_id: int) -> float:
    """Interval multiplier applied to notes marked 已掌握 (1.0 = no de-prioritisation)."""
    row = _schedule_row(db, tenant_id=tenant_id)
    raw = getattr(row, "mastered_factor", None) if row else None
    try:
        factor = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_MASTERED_FACTOR
    if factor < 1.0:
        return 1.0
    return min(factor, MAX_MASTERED_FACTOR)


def _next_review_delay(
    intervals: list[int], index: int, *, mastered: bool, factor: float
) -> timedelta:
    idx = max(0, min(index, len(intervals) - 1))
    days = intervals[idx] * (factor if mastered else 1.0)
    return timedelta(days=days)


async def structure_note(
    db: Session,
    *,
    raw_input: str,
    tenant_id: int,
    override_model_id: int | None = None,
) -> tuple[dict, int, int]:
    """Call the structuring scene. Returns (data, prompt_id, model_id)."""
    client, prompt = LLMClient.for_scene(
        db,
        "learning_note_structuring",
        tenant_id=tenant_id,
        override_model_id=override_model_id,
    )
    rendered = prompt.content.replace("{RAW_INPUT}", raw_input)
    messages = [LLMMessage(role="user", content=rendered)]
    data, _ = await client.chat_json(messages, schema=STRUCTURE_SCHEMA)
    return data, prompt.id, client.model.id


async def create_note(
    db: Session,
    *,
    raw_input: str,
    tenant_id: int,
    channel: str = "web",
    feishu_open_id: str | None = None,
    feishu_message_id: str | None = None,
    extra_tags: list[str] | None = None,
    override_model_id: int | None = None,
) -> LearningNote:
    raw_input = (raw_input or "").strip()
    if not raw_input:
        raise ValueError("学习总结内容不能为空")

    data, prompt_id, model_id = await structure_note(
        db,
        raw_input=raw_input,
        tenant_id=tenant_id,
        override_model_id=override_model_id,
    )

    title = str(data.get("title") or "").strip()[:200] or raw_input[:24]
    summary = str(data.get("summary") or "").strip()
    key_points = [str(x).strip() for x in (data.get("key_points") or []) if str(x).strip()]
    category = (str(data.get("category")).strip() or None) if data.get("category") else None
    review = {
        "issues": [str(x) for x in (data.get("issues") or [])],
        "corrections": [str(x) for x in (data.get("corrections") or [])],
        "suggestions": [str(x) for x in (data.get("suggestions") or [])],
    }
    quality = data.get("quality_score")
    quality = int(quality) if isinstance(quality, (int, float)) else None

    intervals = get_review_intervals(db, tenant_id=tenant_id)
    now = datetime.utcnow()
    next_review = now + timedelta(days=intervals[0])

    note = LearningNote(
        tenant_id=tenant_id,
        raw_input=raw_input,
        title=title,
        summary=summary,
        key_points_json=key_points,
        category=category,
        structured_json=data,
        review_json=review,
        quality_score=quality,
        interval_index=0,
        review_count=0,
        next_review_at=next_review,
        channel=channel,
        feishu_open_id=feishu_open_id,
        feishu_message_id=feishu_message_id,
        generated_by_prompt_id=prompt_id,
        generated_by_model_id=model_id,
    )
    db.add(note)
    db.flush()

    tag_names = list(data.get("tags") or []) + list(extra_tags or [])
    _set_note_tags(db, note, tag_names, tenant_id=tenant_id)
    db.flush()
    return note


def _set_note_tags(
    db: Session, note: LearningNote, names: list[str], *, tenant_id: int
) -> None:
    db.execute(
        LearningNoteTag.__table__.delete().where(
            LearningNoteTag.note_id == note.id
        )
    )
    seen: set[str] = set()
    for name in names:
        key = (name or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        tag = _upsert_tag(db, name, tenant_id=tenant_id)
        if tag is not None:
            db.add(LearningNoteTag(note_id=note.id, tag_id=tag.id))


def list_notes(
    db: Session,
    *,
    tenant_id: int,
    only_due: bool = False,
    include_mastered: bool = True,
    tag_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[LearningNote], int, int]:
    base = select(LearningNote).where(
        LearningNote.tenant_id == tenant_id,
        LearningNote.deleted_at.is_(None),
    )
    if not include_mastered:
        base = base.where(LearningNote.mastered.is_(False))
    if tag_id is not None:
        base = base.join(
            LearningNoteTag, LearningNoteTag.note_id == LearningNote.id
        ).where(LearningNoteTag.tag_id == tag_id)
    now = datetime.utcnow()
    if only_due:
        base = base.where(
            LearningNote.next_review_at.isnot(None),
            LearningNote.next_review_at <= now,
        )

    total = db.execute(
        select(func.count()).select_from(base.subquery())
    ).scalar_one()

    # Mirrors the push queue (`due_notes`): mastered notes are de-prioritised,
    # not excluded, so they count towards the backlog too.
    due_today = db.execute(
        select(func.count())
        .select_from(LearningNote)
        .where(
            LearningNote.tenant_id == tenant_id,
            LearningNote.deleted_at.is_(None),
            LearningNote.next_review_at.isnot(None),
            LearningNote.next_review_at <= now,
        )
    ).scalar_one()

    rows = db.execute(
        base.order_by(LearningNote.created_at.desc()).limit(limit).offset(offset)
    ).scalars().all()
    return list(rows), int(total), int(due_today)


def get_note(db: Session, note_id: int, *, tenant_id: int) -> LearningNote | None:
    return db.execute(
        select(LearningNote).where(
            LearningNote.id == note_id,
            LearningNote.tenant_id == tenant_id,
            LearningNote.deleted_at.is_(None),
        )
    ).scalar_one_or_none()


def update_note(
    db: Session,
    note: LearningNote,
    *,
    tenant_id: int,
    title: str | None = None,
    summary: str | None = None,
    key_points: list[str] | None = None,
    category: str | None = None,
    tags: list[str] | None = None,
    mastered: bool | None = None,
) -> LearningNote:
    if title is not None:
        note.title = title.strip()[:200]
    if summary is not None:
        note.summary = summary.strip()
    if key_points is not None:
        note.key_points_json = [str(x).strip() for x in key_points if str(x).strip()]
    if category is not None:
        note.category = category.strip() or None
    if mastered is not None:
        note.mastered = bool(mastered)
    if tags is not None:
        _set_note_tags(db, note, tags, tenant_id=tenant_id)
    db.flush()
    return note


def delete_note(db: Session, note: LearningNote) -> None:
    note.deleted_at = datetime.utcnow()
    db.flush()


def mark_reviewed(
    db: Session,
    note: LearningNote,
    *,
    intervals: list[int] | None = None,
    factor: float | None = None,
) -> LearningNote:
    """Advance the spaced-repetition interval after a successful review."""
    intervals = intervals or get_review_intervals(db, tenant_id=note.tenant_id)
    if factor is None:
        factor = get_mastered_factor(db, tenant_id=note.tenant_id)
    now = datetime.utcnow()
    note.review_count += 1
    note.last_reviewed_at = now
    note.interval_index = min(note.interval_index + 1, len(intervals) - 1)
    note.next_review_at = now + _next_review_delay(
        intervals, note.interval_index, mastered=note.mastered, factor=factor
    )
    db.flush()
    return note


def mark_mastered(db: Session, note: LearningNote, mastered: bool = True) -> LearningNote:
    """Toggle 已掌握. Mastered notes are de-prioritised, never permanently silenced."""
    intervals = get_review_intervals(db, tenant_id=note.tenant_id)
    factor = get_mastered_factor(db, tenant_id=note.tenant_id)
    note.mastered = mastered
    if mastered:
        # Jump to the longest interval and stretch it, so the note resurfaces
        # occasionally instead of disappearing from the queue for good.
        note.interval_index = len(intervals) - 1
    idx = min(note.interval_index, len(intervals) - 1)
    note.next_review_at = datetime.utcnow() + _next_review_delay(
        intervals, idx, mastered=mastered, factor=factor
    )
    db.flush()
    return note


def reset_review(db: Session, note: LearningNote) -> LearningNote:
    """User asked to reinforce: restart from the first interval (review again soon)."""
    from datetime import timedelta as _td

    intervals = get_review_intervals(db, tenant_id=note.tenant_id)
    note.mastered = False
    note.interval_index = 0
    note.next_review_at = datetime.utcnow() + _td(days=intervals[0])
    db.flush()
    return note


def due_notes(
    db: Session, *, tenant_id: int, now: datetime | None = None, limit: int = 5
) -> list[LearningNote]:
    """Notes whose next_review_at has passed, mastered ones last (lower weight)."""
    now = now or datetime.utcnow()
    return list(
        db.execute(
            select(LearningNote)
            .where(
                LearningNote.tenant_id == tenant_id,
                LearningNote.deleted_at.is_(None),
                LearningNote.next_review_at.isnot(None),
                LearningNote.next_review_at <= now,
            )
            # Mastered notes only get a slot once the still-learning backlog fits.
            .order_by(
                LearningNote.mastered.asc(), LearningNote.next_review_at.asc()
            )
            .limit(limit)
        ).scalars().all()
    )
