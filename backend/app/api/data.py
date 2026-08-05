"""Data export + clear endpoints (PRD §6.5).

Export:
  GET /api/data/export/bank?format=json     → questions + tags + collections JSON
  GET /api/data/export/bank?format=csv      → flat questions CSV (UTF-8 with BOM)
  GET /api/data/export/wikis                → zip with each wiki as <slug>-<id>.md
                                              + manifest.json (titles + commit metadata)

Clear:
  POST /api/data/clear  body: { scope: "chats"|"attempts"|"candidates"|"questions"|"all" }
  - "all" never touches: app_settings, model_providers, models, prompt_templates,
    function_bindings, wikis (those have separate UI to manage; preserves the user's
    setup when they want to wipe trial data).
"""
from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import AuthContext, get_auth_context
from app.db.session import get_db
from app.models import (
    AnswerAttempt,
    Chat,
    Message,
    Question,
    QuestionBankCollection,
    QuestionCandidate,
    Tag,
    Wiki,
    WikiBranch,
    WikiCommit,
)
from app.models.question import QuestionTag

router = APIRouter()


# ---------------------------------------------------------------------------
# Export: bank
# ---------------------------------------------------------------------------


def _slugify(text: str, fallback: str = "untitled") -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text or "", flags=re.UNICODE).strip("-")
    return s or fallback


@router.get("/export/bank")
def export_bank(
    format: Literal["json", "csv"] = Query("json"),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
):
    questions = (
        db.execute(
            select(Question)
            .where(Question.deleted_at.is_(None), Question.tenant_id == ctx.tenant_id)
            .options(selectinload(Question.tags))
            .order_by(Question.id.asc())
        )
        .scalars()
        .unique()
        .all()
    )
    today = datetime.utcnow().strftime("%Y%m%d")

    if format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "id",
                "collection_id",
                "question_text",
                "answer_standard",
                "difficulty",
                "qtype",
                "tags",
                "source_wiki_id",
                "source_commit_id",
                "generated_by_prompt_id",
                "generated_by_model_id",
                "created_at",
                "updated_at",
            ]
        )
        for q in questions:
            writer.writerow(
                [
                    q.id,
                    q.collection_id or "",
                    q.question_text,
                    q.answer_standard,
                    q.difficulty,
                    q.qtype,
                    "|".join(t.name for t in q.tags),
                    q.source_wiki_id or "",
                    q.source_commit_id or "",
                    q.generated_by_prompt_id or "",
                    q.generated_by_model_id or "",
                    q.created_at.isoformat(),
                    q.updated_at.isoformat(),
                ]
            )
        # UTF-8 with BOM so Excel opens it cleanly
        body = "\ufeff" + buf.getvalue()
        return Response(
            content=body,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="bank-{today}.csv"',
            },
        )

    # JSON: full export
    collections = db.execute(
        select(QuestionBankCollection)
        .where(QuestionBankCollection.tenant_id == ctx.tenant_id)
        .order_by(QuestionBankCollection.id.asc())
    ).scalars().all()
    tags = db.execute(
        select(Tag).where(Tag.tenant_id == ctx.tenant_id).order_by(Tag.id.asc())
    ).scalars().all()

    payload = {
        "exported_at": datetime.utcnow().isoformat(),
        "version": 1,
        "collections": [
            {
                "id": c.id,
                "name": c.name,
                "parent_id": c.parent_id,
            }
            for c in collections
        ],
        "tags": [{"id": t.id, "name": t.name, "kind": t.kind} for t in tags],
        "questions": [
            {
                "id": q.id,
                "collection_id": q.collection_id,
                "question_text": q.question_text,
                "answer_standard": q.answer_standard,
                "difficulty": q.difficulty,
                "qtype": q.qtype,
                "tags": [t.name for t in q.tags],
                "source_wiki_id": q.source_wiki_id,
                "source_commit_id": q.source_commit_id,
                "generated_by_prompt_id": q.generated_by_prompt_id,
                "generated_by_model_id": q.generated_by_model_id,
                "created_at": q.created_at.isoformat(),
                "updated_at": q.updated_at.isoformat(),
            }
            for q in questions
        ],
    }
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    return Response(
        content=body,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="bank-{today}.json"'},
    )


# ---------------------------------------------------------------------------
# Export: wikis as zip
# ---------------------------------------------------------------------------


@router.get("/export/wikis")
def export_wikis(
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
):
    wikis = (
        db.execute(
            select(Wiki)
            .where(Wiki.deleted_at.is_(None), Wiki.tenant_id == ctx.tenant_id)
            .options(selectinload(Wiki.current_main_commit))
        )
        .scalars()
        .unique()
        .all()
    )

    today = datetime.utcnow().strftime("%Y%m%d")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        manifest: list[dict] = []
        for w in wikis:
            slug = _slugify(w.title)
            md_name = f"{slug}-{w.id}.md"
            md_content = w.current_main_commit.content_md if w.current_main_commit else ""
            zf.writestr(md_name, md_content)

            # Per-wiki commit history (small, helpful for re-import / audit)
            commits = (
                db.execute(
                    select(WikiCommit)
                    .where(WikiCommit.wiki_id == w.id)
                    .order_by(WikiCommit.id.asc())
                )
                .scalars()
                .all()
            )
            branches = (
                db.execute(
                    select(WikiBranch).where(WikiBranch.wiki_id == w.id)
                )
                .scalars()
                .all()
            )
            manifest.append(
                {
                    "id": w.id,
                    "title": w.title,
                    "filename": md_name,
                    "current_main_commit_id": w.current_main_commit_id,
                    "created_at": w.created_at.isoformat(),
                    "updated_at": w.updated_at.isoformat(),
                    "branches": [
                        {"id": b.id, "name": b.name, "head_commit_id": b.head_commit_id}
                        for b in branches
                    ],
                    "commits": [
                        {
                            "id": c.id,
                            "branch_id": c.branch_id,
                            "parent_commit_id": c.parent_commit_id,
                            "message": c.message,
                            "content_hash": c.content_hash,
                            "created_at": c.created_at.isoformat(),
                        }
                        for c in commits
                    ],
                }
            )
        zf.writestr(
            "manifest.json",
            json.dumps(
                {"exported_at": datetime.utcnow().isoformat(), "wikis": manifest},
                ensure_ascii=False,
                indent=2,
            ),
        )

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="wikis-{today}.zip"',
        },
    )


# ---------------------------------------------------------------------------
# Clear
# ---------------------------------------------------------------------------


class ClearRequest(BaseModel):
    scope: Literal["chats", "attempts", "candidates", "questions", "all"]


class ClearResponse(BaseModel):
    deleted: dict[str, int]


@router.post("/clear", response_model=ClearResponse)
def clear_data(
    payload: ClearRequest,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> ClearResponse:
    deleted: dict[str, int] = {}
    valid = {"chats", "attempts", "candidates", "questions", "all"}
    if payload.scope not in valid:
        raise HTTPException(400, detail=f"unknown scope: {payload.scope}")

    tid = ctx.tenant_id

    def wipe_tenant(model, key: str, tenant_col) -> None:
        cnt = int(
            db.execute(
                select(func.count()).select_from(model).where(tenant_col == tid)
            ).scalar_one()
        )
        db.execute(delete(model).where(tenant_col == tid))
        deleted[key] = cnt

    def wipe_questions_via_tenant() -> None:
        q_ids = select(Question.id).where(Question.tenant_id == tid)
        cnt_qt = int(
            db.execute(
                select(func.count())
                .select_from(QuestionTag)
                .where(QuestionTag.question_id.in_(q_ids))
            ).scalar_one()
        )
        db.execute(delete(QuestionTag).where(QuestionTag.question_id.in_(q_ids)))
        deleted["question_tags"] = cnt_qt
        cnt_q = int(
            db.execute(
                select(func.count()).select_from(Question).where(Question.tenant_id == tid)
            ).scalar_one()
        )
        db.execute(delete(Question).where(Question.tenant_id == tid))
        deleted["questions"] = cnt_q

    def wipe_attempts_for_tenant() -> None:
        q_ids = select(Question.id).where(Question.tenant_id == tid)
        cnt = int(
            db.execute(
                select(func.count())
                .select_from(AnswerAttempt)
                .where(AnswerAttempt.question_id.in_(q_ids))
            ).scalar_one()
        )
        db.execute(delete(AnswerAttempt).where(AnswerAttempt.question_id.in_(q_ids)))
        deleted["answer_attempts"] = cnt

    scope = payload.scope
    if scope in ("chats", "all"):
        chat_ids = select(Chat.id).where(Chat.tenant_id == tid)
        cnt_msg = int(
            db.execute(
                select(func.count()).select_from(Message).where(Message.chat_id.in_(chat_ids))
            ).scalar_one()
        )
        db.execute(delete(Message).where(Message.chat_id.in_(chat_ids)))
        deleted["messages"] = cnt_msg
        wipe_tenant(Chat, "chats", Chat.tenant_id)
    if scope in ("attempts", "all"):
        wipe_attempts_for_tenant()
    if scope in ("candidates", "all"):
        wipe_tenant(QuestionCandidate, "question_candidates", QuestionCandidate.tenant_id)
    if scope in ("questions", "all"):
        wipe_attempts_for_tenant()
        wipe_questions_via_tenant()
        wipe_tenant(Tag, "tags", Tag.tenant_id)
        # bank collections survive — typically there's only "默认题库" the user wants

    db.commit()
    return ClearResponse(deleted=deleted)
