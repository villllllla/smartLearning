"""Build RAG prompt context and citation list for the LLM."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.rag.embedder import RagEmbedderError
from app.services.rag.retrieve import RagHit, retrieve


def hits_to_sources(hits: list[RagHit]) -> list[dict]:
    return [
        {
            "wiki_id": h.wiki_id,
            "wiki_title": h.wiki_title,
            "heading": h.heading,
            "chunk_index": h.chunk_index,
            "score": h.score,
            "url_path": h.url_path,
            "excerpt": h.text[:240] + ("…" if len(h.text) > 240 else ""),
        }
        for h in hits
    ]


def build_rag_context(db: Session, user_query: str) -> tuple[str, list[dict]]:
    """Return (system_suffix, sources) for injection into chat system prompt."""
    settings = get_settings()
    if not settings.rag_enabled:
        return "", []

    try:
        hits = retrieve(
            db,
            user_query,
            top_k=settings.rag_top_k,
            min_score=settings.rag_min_score,
        )
    except RagEmbedderError:
        raise
    except Exception:
        return "", []

    if not hits:
        return "", []

    blocks: list[str] = []
    for i, h in enumerate(hits, start=1):
        blocks.append(
            f"[{i}] 标题: {h.wiki_title}\n"
            f"    链接: {h.url_path}\n"
            f"    章节: {h.heading or '(正文)'}\n"
            f"    摘录:\n{h.text}\n"
        )

    suffix = (
        "\n\n---\n"
        "【知识库检索结果】以下摘录来自用户本地 Wiki，回答时请优先依据这些内容；"
        "若与常识冲突以摘录为准。回答末尾用「参考文档」列出所用条目的链接（使用上面的 url_path，"
        "前端会渲染为可点击的 /wiki/<id>）。\n\n"
        + "\n".join(blocks)
    )
    return suffix, hits_to_sources(hits)
