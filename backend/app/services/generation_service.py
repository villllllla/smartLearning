"""Question generation pipeline (PRD §6.3).

Flow:
  1. Resolve scene "wiki_to_questions" → (prompt, model, provider).
  2. Render prompt with N / TITLE / MARKDOWN substitutions.
  3. Call ``LLMClient.chat_json`` with strict schema; one self-repair retry.
  4. Persist each item as a ``QuestionCandidate`` row sharing a batch_id, with
     frozen ``generated_by_prompt_id`` / ``generated_by_model_id`` / source.
  5. Caller hands off batch_id to the user for preview.

Commit step:
  - For every candidate marked ``picked=True``, materialise a ``Question``
    with the same frozen IDs. Tags are upserted into ``Tag`` and linked.
  - Picked candidates are then deleted from ``question_candidates`` (we still
    keep batch traceability via the new Question rows).
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Question,
    QuestionBankCollection,
    QuestionCandidate,
    Tag,
    Wiki,
)
from app.models.question import SOURCE_KIND_SIMULATED, QuestionTag
from app.services.llm import LLMClient, LLMMessage
from app.services.question_dedupe_service import find_bank_duplicate
from app.services.wiki_generation_service import clear_wiki_generated_content

log = logging.getLogger(__name__)


CANDIDATE_SCHEMA: dict = {
    "type": "array",
    "items": {
        "type": "object",
        "required": ["question", "tag", "answer", "difficulty", "type", "origin"],
        "properties": {
            "question": {"type": "string", "minLength": 4},
            "tag": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 6,
            },
            "answer": {"type": "string", "minLength": 10},
            "difficulty": {"enum": ["easy", "medium", "hard"]},
            "type": {"enum": ["concept", "scenario"]},
            "origin": {"type": "string"},
        },
        "additionalProperties": False,
    },
}


def _count_directive(n: int | None, max_n: int) -> str:
    """Build the natural-language instruction that controls how many items
    the model emits. Two modes:

    - ``n is None`` → auto: the model decides based on content density, with
      a soft floor of 3 and a hard ceiling of ``max_n``. Prevents runaway
      output on large wikis while staying honest on short ones.
    - ``n is int``  → fixed: model must emit exactly ``n`` items.
    """
    if n is None:
        return (
            f"请根据文档实质内容自行决定题量;信息密度高就多出、低就少出;"
            f"下限 3 条,上限 {max_n} 条;宁可少出也不要凑数。"
        )
    return f"必须恰好为 {n} 条。"


def _render_prompt(
    template: str,
    *,
    n: int | None,
    max_n: int,
    title: str,
    markdown: str,
) -> str:
    """Tolerant substitution: works for the new template (uses
    ``{COUNT_DIRECTIVE}``) AND legacy templates (use ``{N}``).

    For legacy templates: when ``n is None`` we substitute ``{N}`` with the
    auto directive sentence so the surrounding Chinese still reads clean
    (the original v1 said ``数组长度 = {N}(默认 12)``).
    """
    directive = _count_directive(n, max_n)
    n_token = str(n) if n is not None else directive
    out = template
    for placeholder, value in (
        ("{COUNT_DIRECTIVE}", directive),
        ("{N}", n_token),
        ("{MAX}", str(max_n)),
        ("{TITLE}", title),
        ("{MARKDOWN}", markdown),
    ):
        out = out.replace(placeholder, value)
    return out


@dataclass
class GenerationResult:
    batch_id: str
    candidates: list[QuestionCandidate]
    raw_count: int
    replaced_bank_questions: int = 0
    replaced_candidates: int = 0


async def generate_for_wiki(
    db: Session,
    wiki: Wiki,
    *,
    n: int | None = None,
    max_n: int = 30,
    override_model_id: int | None = None,
    replace_existing: bool = False,
) -> GenerationResult:
    """Run the wiki→candidates pipeline.

    ``n=None`` (default) lets the model size the batch based on the wiki's
    actual content, capped at ``max_n``. Passing an explicit ``n`` forces an
    exact count (legacy behavior). The pipeline never throws when the model
    returns fewer items than ``max_n`` — the wiki's information density gets
    the final say.
    """
    if wiki.current_main_commit is None:
        raise RuntimeError(f"wiki {wiki.id} has no main commit yet")

    replaced_bank = 0
    replaced_cand = 0
    if replace_existing:
        replaced_bank, replaced_cand = clear_wiki_generated_content(db, wiki.id)

    content_md = wiki.current_main_commit.content_md

    client, prompt = LLMClient.for_scene(
        db,
        "wiki_to_questions",
        tenant_id=wiki.tenant_id,
        override_model_id=override_model_id,
    )
    rendered = _render_prompt(
        prompt.content, n=n, max_n=max_n, title=wiki.title, markdown=content_md
    )
    messages = [LLMMessage(role="user", content=rendered)]

    items, _ = await client.chat_json(messages, schema=CANDIDATE_SCHEMA)
    if not isinstance(items, list):
        raise RuntimeError("expected JSON array from model")
    # Defensive cap: if the model ignored the upper bound and returned a flood
    # of items, trim. Keeps DB rows and UI predictable.
    if len(items) > max_n:
        log.warning(
            "generation: model returned %d items, trimming to max_n=%d",
            len(items),
            max_n,
        )
        items = items[:max_n]

    batch_id = uuid.uuid4().hex
    candidates: list[QuestionCandidate] = []
    for item in items:
        cand = QuestionCandidate(
            tenant_id=wiki.tenant_id,
            batch_id=batch_id,
            payload_json=item,
            picked=False,
            edited=False,
            source_wiki_id=wiki.id,
            source_commit_id=wiki.current_main_commit_id,
            generated_by_prompt_id=prompt.id,
            generated_by_model_id=client.model.id,
        )
        db.add(cand)
        candidates.append(cand)
    db.flush()
    return GenerationResult(
        batch_id=batch_id,
        candidates=candidates,
        raw_count=len(items),
        replaced_bank_questions=replaced_bank,
        replaced_candidates=replaced_cand,
    )


# ---------------------------------------------------------------------------
# Commit (preview-list → persisted Questions)
# ---------------------------------------------------------------------------


def _ensure_default_collection(db: Session, *, tenant_id: int) -> QuestionBankCollection:
    coll = db.execute(
        select(QuestionBankCollection)
        .where(QuestionBankCollection.tenant_id == tenant_id)
        .order_by(QuestionBankCollection.id.asc())
        .limit(1)
    ).scalar_one_or_none()
    if coll is not None:
        return coll
    coll = QuestionBankCollection(tenant_id=tenant_id, name="默认题库")
    db.add(coll)
    db.flush()
    return coll


def _upsert_tag(db: Session, name: str, *, tenant_id: int) -> Tag:
    name = name.strip()
    existing = db.execute(
        select(Tag).where(Tag.tenant_id == tenant_id, Tag.name == name)
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    t = Tag(tenant_id=tenant_id, name=name, kind="user")
    db.add(t)
    db.flush()
    return t


def commit_batch(
    db: Session,
    batch_id: str,
    *,
    tenant_id: int,
    target_collection_id: int | None = None,
    pick_all: bool = False,
) -> tuple[int, int]:
    """Materialise picked candidates as Questions. Returns (saved, discarded_remaining)."""
    rows = db.execute(
        select(QuestionCandidate).where(
            QuestionCandidate.batch_id == batch_id,
            QuestionCandidate.tenant_id == tenant_id,
        )
    ).scalars().all()
    if not rows:
        return 0, 0

    if pick_all:
        for cand in rows:
            cand.picked = True

    if target_collection_id is None:
        coll = _ensure_default_collection(db, tenant_id=tenant_id)
        target_collection_id = coll.id
    elif db.get(QuestionBankCollection, target_collection_id) is None:
        raise ValueError("target collection not found")

    saved = 0
    remaining = 0
    for cand in rows:
        if not cand.picked:
            remaining += 1
            continue
        payload = cand.payload_json or {}
        stem = str(payload.get("question", "")).strip()
        if find_bank_duplicate(
            db,
            stem,
            tenant_id=tenant_id,
            collection_id=target_collection_id,
        ):
            db.delete(cand)
            continue
        q = Question(
            tenant_id=tenant_id,
            collection_id=target_collection_id,
            question_text=stem,
            answer_standard=str(payload.get("answer", "")).strip(),
            difficulty=str(payload.get("difficulty", "medium")),
            qtype=str(payload.get("type", "concept")),
            source_kind=SOURCE_KIND_SIMULATED,
            source_wiki_id=cand.source_wiki_id,
            source_commit_id=cand.source_commit_id,
            generated_by_prompt_id=cand.generated_by_prompt_id,
            generated_by_model_id=cand.generated_by_model_id,
        )
        db.add(q)
        db.flush()
        for tag_name in payload.get("tag") or []:
            tag = _upsert_tag(db, tag_name, tenant_id=tenant_id)
            db.add(QuestionTag(question_id=q.id, tag_id=tag.id))
        try:
            from app.services.question_embedding_service import ensure_question_embedding

            ensure_question_embedding(db, q)
        except Exception as exc:
            log.warning("question %s embedding skipped: %s", q.id, exc)
        saved += 1
        db.delete(cand)

    db.flush()
    return saved, remaining


def bulk_commit_batches(
    db: Session,
    batch_ids: list[str],
    *,
    tenant_id: int,
    target_collection_id: int | None = None,
    pick_all: bool = True,
) -> list[tuple[str, int, int]]:
    """Commit multiple batches; returns [(batch_id, saved, remaining), ...]."""
    out: list[tuple[str, int, int]] = []
    for batch_id in batch_ids:
        saved, remaining = commit_batch(
            db,
            batch_id,
            tenant_id=tenant_id,
            target_collection_id=target_collection_id,
            pick_all=pick_all,
        )
        out.append((batch_id, saved, remaining))
    return out


def list_candidates(
    db: Session, batch_id: str, *, tenant_id: int
) -> list[QuestionCandidate]:
    return list(
        db.execute(
            select(QuestionCandidate)
            .where(
                QuestionCandidate.batch_id == batch_id,
                QuestionCandidate.tenant_id == tenant_id,
            )
            .order_by(QuestionCandidate.id.asc())
        ).scalars().all()
    )


def update_candidate(
    db: Session,
    cand_id: int,
    *,
    tenant_id: int,
    payload_json: dict | None = None,
    picked: bool | None = None,
) -> QuestionCandidate | None:
    cand = db.get(QuestionCandidate, cand_id)
    if cand is None or cand.tenant_id != tenant_id:
        return None
    if payload_json is not None:
        cand.payload_json = payload_json
        cand.edited = True
    if picked is not None:
        cand.picked = picked
    db.flush()
    return cand


def discard_candidate(db: Session, cand_id: int, *, tenant_id: int) -> bool:
    cand = db.get(QuestionCandidate, cand_id)
    if cand is None or cand.tenant_id != tenant_id:
        return False
    db.delete(cand)
    db.flush()
    return True
