"""Wiki RAG index and debug retrieval API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.common import Page
from app.schemas.rag import (
    RagChunkOut,
    RagQueryRequest,
    RagQueryResponse,
    RagRebuildRequest,
    RagRebuildResponse,
    RagSourceOut,
    RagStatusOut,
)
from app.services.rag.context import hits_to_sources
from app.services.rag.embedder import RagEmbedderError
from app.services.rag.index_service import get_index_status, rebuild_index
from app.services.rag.retrieve import list_chunks, retrieve

router = APIRouter()


@router.get("/status", response_model=RagStatusOut)
def rag_status(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RagStatusOut:
    return RagStatusOut.model_validate(get_index_status(db, settings))


@router.post("/rebuild", response_model=RagRebuildResponse)
def rag_rebuild(
    payload: RagRebuildRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RagRebuildResponse:
    if not settings.rag_enabled:
        raise HTTPException(400, detail="RAG 未启用 (SL_RAG_ENABLED=false)")
    try:
        summary = rebuild_index(db, settings, wiki_id=payload.wiki_id)
    except RagEmbedderError as exc:
        raise HTTPException(503, detail=str(exc)) from exc
    return RagRebuildResponse(
        wikis_processed=summary.wikis_processed,
        chunks_written=summary.chunks_written,
        wikis_skipped=summary.wikis_skipped,
        errors=summary.errors or [],
    )


@router.get("/chunks", response_model=Page[RagChunkOut])
def rag_list_chunks(
    wiki_id: int | None = Query(None, description="仅查看某篇 Wiki 的片段"),
    q: str | None = Query(None, description="在片段正文/标题中模糊搜索"),
    limit: int = Query(30, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Page[RagChunkOut]:
    rows, total = list_chunks(db, wiki_id=wiki_id, q=q, limit=limit, offset=offset)
    items = [
        RagChunkOut(
            id=r.id,
            wiki_id=r.wiki_id,
            wiki_title=r.wiki_title,
            chunk_index=r.chunk_index,
            heading=r.heading,
            text=r.text,
            source_commit_id=r.source_commit_id,
            content_hash=r.content_hash,
            text_length=len(r.text or ""),
            created_at=r.created_at.isoformat() if r.created_at else None,
        )
        for r in rows
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("/query", response_model=RagQueryResponse)
def rag_query(
    payload: RagQueryRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RagQueryResponse:
    if not settings.rag_enabled:
        raise HTTPException(400, detail="RAG 未启用")
    top_k = payload.top_k or settings.rag_top_k
    try:
        hits = retrieve(
            db,
            payload.query,
            top_k=top_k,
            min_score=settings.rag_min_score,
        )
    except RagEmbedderError as exc:
        raise HTTPException(503, detail=str(exc)) from exc
    sources = hits_to_sources(hits)
    return RagQueryResponse(hits=[RagSourceOut.model_validate(s) for s in sources])
