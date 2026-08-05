"""Aggregate multi-source candidates → prefilter → LLM curation → top-N.

Links/sources always come from real fetched items; the LLM only selects a
candidate `id` and writes Chinese title/summary/heat. Any id it invents is
dropped (anti-hallucination).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.services.ai_news.sources import NewsItem, fetch_all_candidates
from app.services.llm import LLMClient, LLMError, LLMMessage

log = logging.getLogger(__name__)

_CURATION_SCHEMA: dict = {
    "type": "object",
    "required": ["items"],
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "title_cn", "summary_cn", "heat_score"],
                "properties": {
                    "id": {"type": "integer"},
                    "title_cn": {"type": "string"},
                    "summary_cn": {"type": "string"},
                    "heat_score": {"type": "integer", "minimum": 0, "maximum": 100},
                    "why": {"type": "string"},
                },
            },
        }
    },
    "additionalProperties": True,
}


@dataclass
class CuratedItem:
    title: str          # Chinese (or original if not translated)
    original_title: str
    url: str
    source: str
    summary: str
    heat_score: int
    why: str = ""
    raw_score: float = 0.0
    published_at: datetime | None = None


@dataclass
class CurationResult:
    items: list[CuratedItem] = field(default_factory=list)
    total_candidates: int = 0
    used_llm: bool = False


def _norm_url(url: str) -> str:
    u = (url or "").strip().rstrip("/")
    for pfx in ("https://", "http://"):
        if u.startswith(pfx):
            u = u[len(pfx):]
    if u.startswith("www."):
        u = u[4:]
    return u.lower()


def _dedup(cands: list[NewsItem]) -> list[NewsItem]:
    seen: set[str] = set()
    out: list[NewsItem] = []
    for c in cands:
        key = _norm_url(c.url)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def _prefilter(cands: list[NewsItem], *, keep: int) -> list[NewsItem]:
    """Rank by per-source min-max normalized native score, then recency."""
    by_source: dict[str, list[NewsItem]] = {}
    for c in cands:
        by_source.setdefault(c.source, []).append(c)

    scored: list[tuple[float, NewsItem]] = []
    now = datetime.now(timezone.utc)
    for group in by_source.values():
        scores = [g.raw_score for g in group]
        lo, hi = (min(scores), max(scores)) if scores else (0.0, 0.0)
        span = (hi - lo) or 1.0
        for g in group:
            norm = (g.raw_score - lo) / span if hi > lo else 0.5
            # recency bonus (0..0.3) within last 3 days
            rec = 0.0
            if g.published_at is not None:
                pub = g.published_at
                if pub.tzinfo is None:
                    pub = pub.replace(tzinfo=timezone.utc)
                age_h = max(0.0, (now - pub).total_seconds() / 3600.0)
                rec = max(0.0, 0.3 * (1 - age_h / 72.0))
            scored.append((norm + rec, g))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:keep]]


def _fallback_rank(cands: list[NewsItem], *, top_n: int) -> list[CuratedItem]:
    ranked = _prefilter(cands, keep=top_n)
    out: list[CuratedItem] = []
    for i, c in enumerate(ranked):
        out.append(
            CuratedItem(
                title=c.title,
                original_title=c.title,
                url=c.url,
                source=c.source,
                summary=c.summary,
                heat_score=max(1, 90 - i * 10),
                why="",
                raw_score=c.raw_score,
                published_at=c.published_at,
            )
        )
    return out


async def curate_ai_news(
    db: Session,
    *,
    tenant_id: int,
    top_n: int = 5,
    enable_hackernews: bool = True,
    enable_github: bool = True,
    enable_arxiv: bool = True,
    enable_huggingface: bool = True,
    enable_reddit: bool = True,
    rss_feeds: list[dict] | None = None,
    candidate_pool: int = 40,
    exclude_urls: set[str] | None = None,
) -> CurationResult:
    raw = await fetch_all_candidates(
        enable_hackernews=enable_hackernews,
        enable_github=enable_github,
        enable_arxiv=enable_arxiv,
        enable_huggingface=enable_huggingface,
        enable_reddit=enable_reddit,
        rss_feeds=rss_feeds,
    )
    cands = _dedup(raw)
    if exclude_urls:
        cands = [c for c in cands if _norm_url(c.url) not in exclude_urls]
    total = len(cands)
    if not cands:
        return CurationResult(items=[], total_candidates=0, used_llm=False)

    pool = _prefilter(cands, keep=candidate_pool)
    by_id: dict[int, NewsItem] = {i: c for i, c in enumerate(pool)}

    payload = [
        {
            "id": i,
            "title": c.title[:200],
            "source": c.source,
            "url": c.url,
            "score": round(c.raw_score, 1),
            "published_at": c.published_at.isoformat() if c.published_at else None,
            "summary": c.summary[:200],
        }
        for i, c in by_id.items()
    ]

    try:
        client, prompt = LLMClient.for_scene(
            db, "ai_news_curation", tenant_id=tenant_id
        )
        rendered = prompt.content.replace("{TOP_N}", str(top_n)).replace(
            "{CANDIDATES_JSON}", json.dumps(payload, ensure_ascii=False)
        )
        data, _ = await client.chat_json(
            [LLMMessage(role="user", content=rendered)], schema=_CURATION_SCHEMA
        )
    except LLMError as exc:
        log.warning("ai_news LLM curation failed, using fallback rank: %s", exc)
        return CurationResult(
            items=_fallback_rank(cands, top_n=top_n),
            total_candidates=total,
            used_llm=False,
        )

    curated: list[CuratedItem] = []
    seen_ids: set[int] = set()
    for row in data.get("items", []):
        try:
            cid = int(row.get("id"))
        except (TypeError, ValueError):
            continue
        if cid not in by_id or cid in seen_ids:
            continue  # anti-hallucination: id must be a real candidate
        seen_ids.add(cid)
        src = by_id[cid]
        curated.append(
            CuratedItem(
                title=str(row.get("title_cn") or src.title).strip()[:200],
                original_title=src.title,
                url=src.url,
                source=src.source,
                summary=str(row.get("summary_cn") or src.summary).strip()[:300],
                heat_score=int(row.get("heat_score") or 0),
                why=str(row.get("why") or "").strip()[:120],
                raw_score=src.raw_score,
                published_at=src.published_at,
            )
        )
        if len(curated) >= top_n:
            break

    if not curated:
        return CurationResult(
            items=_fallback_rank(cands, top_n=top_n),
            total_candidates=total,
            used_llm=False,
        )
    curated.sort(key=lambda x: x.heat_score, reverse=True)
    return CurationResult(items=curated, total_candidates=total, used_llm=True)
