"""AI-news fetchers. Each source returns a list of NewsItem and never raises.

No third-party parsing deps: HN via JSON API, RSS via stdlib XML, GitHub
Trending via light regex. httpx honors system proxy env (trust_env=True), so
overseas sources go through the same proxy as other outbound calls.
"""
from __future__ import annotations

import asyncio
import html
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import httpx

log = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_TIMEOUT = httpx.Timeout(20.0, connect=10.0)

# Keyword gate for AI relevance. ASCII keywords are matched with word
# boundaries so short ones ("ai", "ml") don't hit substrings like "strAIning"
# or "HTML"; CJK keywords are matched as plain substrings.
_ASCII_KEYWORDS = (
    "ai", "llm", "llms", "gpt", "chatgpt", "gemini", "claude", "anthropic",
    "openai", "deepseek", "qwen", "mistral", "llama", "machine learning",
    "deep learning", "neural network", "transformer", "diffusion",
    "generative", "agent", "agents", "agentic", "rag", "embedding",
    "embeddings", "hugging face", "huggingface", "pytorch", "tensorflow",
    "fine-tuning", "fine-tune", "multimodal", "chatbot", "copilot",
    "gpu", "cuda",
)
_CJK_KEYWORDS = (
    "大模型", "人工智能", "机器学习", "深度学习", "神经网络", "智能体",
    "生成式", "算力", "大语言模型", "多模态", "训练模型",
)
_ASCII_RE = re.compile(
    r"(?<![a-z0-9])(?:" + "|".join(re.escape(k) for k in _ASCII_KEYWORDS) + r")(?![a-z0-9])",
    re.IGNORECASE,
)

# Default Chinese AI-media RSS feeds (overridable per-schedule). Add more in
# Settings; feeds that return non-XML (e.g. an SPA shell) are skipped safely.
DEFAULT_RSS_FEEDS: tuple[dict[str, str], ...] = (
    {"name": "量子位", "url": "https://www.qbitai.com/feed"},
)


@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    raw_score: float = 0.0
    published_at: datetime | None = None
    summary: str = ""
    extra: dict = field(default_factory=dict)


def _looks_ai_related(*texts: str) -> bool:
    blob = " ".join(t for t in texts if t)
    if any(k in blob for k in _CJK_KEYWORDS):
        return True
    return bool(_ASCII_RE.search(blob))


def _clean_text(s: str | None) -> str:
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", "", s)  # strip HTML tags
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


# --------------------------------------------------------------------------- #
# Hacker News (Algolia API) — has `points` as native heat.
# --------------------------------------------------------------------------- #
async def fetch_hackernews(client: httpx.AsyncClient, *, limit: int = 30) -> list[NewsItem]:
    items: dict[str, NewsItem] = {}
    endpoints = [
        "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=50",
        "https://hn.algolia.com/api/v1/search?query=AI%20OR%20LLM&tags=story&hitsPerPage=50",
    ]
    for url in endpoints:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            hits = resp.json().get("hits", [])
        except Exception as exc:  # noqa: BLE001
            log.warning("HN fetch failed (%s): %s", url, exc)
            continue
        for h in hits:
            title = h.get("title") or h.get("story_title") or ""
            link = h.get("url") or (
                f"https://news.ycombinator.com/item?id={h.get('objectID')}"
            )
            if not title or not _looks_ai_related(title):
                continue
            oid = str(h.get("objectID") or link)
            if oid in items:
                continue
            published = None
            if h.get("created_at_i"):
                published = datetime.fromtimestamp(h["created_at_i"], tz=timezone.utc)
            items[oid] = NewsItem(
                title=title.strip(),
                url=link,
                source="Hacker News",
                raw_score=float(h.get("points") or 0),
                published_at=published,
                summary="",
                extra={"comments": h.get("num_comments") or 0},
            )
    ranked = sorted(items.values(), key=lambda x: x.raw_score, reverse=True)
    return ranked[:limit]


# --------------------------------------------------------------------------- #
# RSS / Atom feeds — no native heat; ranked later by LLM + recency.
# --------------------------------------------------------------------------- #
def _parse_rss(xml_text: str, source: str, limit: int) -> list[NewsItem]:
    out: list[NewsItem] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        log.warning("RSS parse error (%s): %s", source, exc)
        return out

    # RSS 2.0: channel/item ; Atom: feed/entry
    items = root.findall(".//item")
    if items:
        for it in items[:limit]:
            title = _clean_text(it.findtext("title"))
            link = (it.findtext("link") or "").strip()
            desc = _clean_text(it.findtext("description"))
            pub = it.findtext("pubDate")
            published = None
            if pub:
                try:
                    published = parsedate_to_datetime(pub)
                except (TypeError, ValueError):
                    published = None
            if title and link:
                out.append(
                    NewsItem(
                        title=title, url=link, source=source, raw_score=0.0,
                        published_at=published, summary=desc[:200],
                    )
                )
        return out

    # Atom
    ns = "{http://www.w3.org/2005/Atom}"
    for entry in root.findall(f".//{ns}entry")[:limit]:
        title = _clean_text(entry.findtext(f"{ns}title"))
        link_el = entry.find(f"{ns}link")
        link = (link_el.get("href") if link_el is not None else "") or ""
        desc = _clean_text(entry.findtext(f"{ns}summary"))
        pub = entry.findtext(f"{ns}updated") or entry.findtext(f"{ns}published")
        published = None
        if pub:
            try:
                published = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            except ValueError:
                published = None
        if title and link:
            out.append(
                NewsItem(
                    title=title, url=link.strip(), source=source, raw_score=0.0,
                    published_at=published, summary=desc[:200],
                )
            )
    return out


async def fetch_rss_feed(
    client: httpx.AsyncClient, *, name: str, url: str, limit: int = 15
) -> list[NewsItem]:
    try:
        resp = await client.get(url, headers={"Accept": "application/rss+xml, application/xml, text/xml"})
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        log.warning("RSS fetch failed (%s %s): %s", name, url, exc)
        return []
    items = _parse_rss(resp.text, name, limit)
    # Keep AI-related only (Chinese media also covers non-AI topics sometimes).
    return [i for i in items if _looks_ai_related(i.title, i.summary)]


# --------------------------------------------------------------------------- #
# GitHub Trending (HTML) — `stars today` as native heat.
# --------------------------------------------------------------------------- #
_GH_ROW_RE = re.compile(r'<article class="Box-row">(.*?)</article>', re.S)
# The star button links to /login?return_to=%2Fowner%2Frepo — reliable across
# markup changes to the repo heading anchor.
_GH_REPO_RE = re.compile(r"return_to=%2F([^%\"]+)%2F([^%\"&?]+)")
_GH_DESC_RE = re.compile(r'<p class="col-9[^"]*"[^>]*>(.*?)</p>', re.S)
_GH_STARS_RE = re.compile(r"([\d,]+)\s+stars today")


async def fetch_github_trending(
    client: httpx.AsyncClient, *, limit: int = 15
) -> list[NewsItem]:
    try:
        resp = await client.get(
            "https://github.com/trending?since=daily",
            headers={"Accept": "text/html"},
        )
        resp.raise_for_status()
        html = resp.text
    except Exception as exc:  # noqa: BLE001
        log.warning("GitHub trending fetch failed: %s", exc)
        return []

    out: list[NewsItem] = []
    for block in _GH_ROW_RE.findall(html):
        repo_m = _GH_REPO_RE.search(block)
        if not repo_m:
            continue
        repo = f"{repo_m.group(1)}/{repo_m.group(2)}".strip().rstrip("/")
        desc_m = _GH_DESC_RE.search(block)
        desc = _clean_text(desc_m.group(1)) if desc_m else ""
        stars_m = _GH_STARS_RE.search(block)
        stars = float(stars_m.group(1).replace(",", "")) if stars_m else 0.0
        if not _looks_ai_related(repo, desc):
            continue
        out.append(
            NewsItem(
                title=f"{repo} — {desc}" if desc else repo,
                url=f"https://github.com/{repo}",
                source="GitHub Trending",
                raw_score=stars,
                published_at=datetime.now(timezone.utc),
                summary=desc[:200],
            )
        )
    out.sort(key=lambda x: x.raw_score, reverse=True)
    return out[:limit]


# --------------------------------------------------------------------------- #
# arXiv (Atom API) — no native heat; ranked by recency + LLM. Category IS the
# filter, so no keyword gate.
# --------------------------------------------------------------------------- #
_ARXIV_URL = (
    "http://export.arxiv.org/api/query?search_query="
    "cat:cs.AI+OR+cat:cs.LG+OR+cat:cs.CL+OR+cat:cs.CV"
    "&sortBy=submittedDate&sortOrder=descending&start=0&max_results={n}"
)


async def fetch_arxiv(client: httpx.AsyncClient, *, limit: int = 15) -> list[NewsItem]:
    try:
        resp = await client.get(_ARXIV_URL.format(n=limit))
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        log.warning("arXiv fetch failed: %s", exc)
        return []
    return _parse_rss(resp.text, "arXiv", limit)


# --------------------------------------------------------------------------- #
# HuggingFace Daily Papers (JSON) — `upvotes` as native heat.
# --------------------------------------------------------------------------- #
async def fetch_huggingface(
    client: httpx.AsyncClient, *, limit: int = 15
) -> list[NewsItem]:
    try:
        resp = await client.get("https://huggingface.co/api/daily_papers")
        resp.raise_for_status()
        rows = resp.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("HuggingFace fetch failed: %s", exc)
        return []
    out: list[NewsItem] = []
    for row in rows if isinstance(rows, list) else []:
        paper = row.get("paper") or {}
        pid = str(paper.get("id") or "").strip()
        title = _clean_text(paper.get("title") or row.get("title"))
        if not pid or not title:
            continue
        published = None
        pub = row.get("publishedAt") or paper.get("publishedAt")
        if pub:
            try:
                published = datetime.fromisoformat(str(pub).replace("Z", "+00:00"))
            except ValueError:
                published = None
        out.append(
            NewsItem(
                title=title,
                url=f"https://huggingface.co/papers/{pid}",
                source="HuggingFace",
                raw_score=float(paper.get("upvotes") or 0),
                published_at=published,
                summary=_clean_text(paper.get("summary"))[:200],
            )
        )
    out.sort(key=lambda x: x.raw_score, reverse=True)
    return out[:limit]


# --------------------------------------------------------------------------- #
# Reddit — the JSON API 403s unauthenticated requests, but the public top .rss
# (Atom) works with a browser UA. No native heat, so ranked by recency + LLM.
# AI-focused subreddits, no keyword gate.
# --------------------------------------------------------------------------- #
DEFAULT_SUBREDDITS: tuple[str, ...] = ("LocalLLaMA", "MachineLearning")


async def fetch_reddit(
    client: httpx.AsyncClient,
    *,
    subreddits: tuple[str, ...] = DEFAULT_SUBREDDITS,
    limit: int = 15,
) -> list[NewsItem]:
    out: list[NewsItem] = []
    for idx, sub in enumerate(subreddits):
        if idx:
            await asyncio.sleep(1.0)  # be polite; Reddit 429s on rapid requests
        url = f"https://www.reddit.com/r/{sub}/top/.rss?t=day"
        try:
            resp = await client.get(url, headers={"Accept": "application/atom+xml"})
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            log.warning("Reddit fetch failed (r/%s): %s", sub, exc)
            continue
        for item in _parse_rss(resp.text, f"Reddit r/{sub}", limit):
            out.append(item)
    return out[:limit]


async def fetch_all_candidates(
    *,
    enable_hackernews: bool = True,
    enable_github: bool = True,
    enable_arxiv: bool = True,
    enable_huggingface: bool = True,
    enable_reddit: bool = True,
    rss_feeds: list[dict] | None = None,
    per_source_limit: int = 20,
) -> list[NewsItem]:
    """Fetch every enabled source concurrently. Failures degrade gracefully."""
    feeds = rss_feeds if rss_feeds is not None else list(DEFAULT_RSS_FEEDS)
    async with httpx.AsyncClient(
        timeout=_TIMEOUT, headers={"User-Agent": _UA}, follow_redirects=True, trust_env=True
    ) as client:
        tasks: list = []
        if enable_hackernews:
            tasks.append(fetch_hackernews(client, limit=per_source_limit))
        if enable_github:
            tasks.append(fetch_github_trending(client, limit=per_source_limit))
        if enable_arxiv:
            tasks.append(fetch_arxiv(client, limit=per_source_limit))
        if enable_huggingface:
            tasks.append(fetch_huggingface(client, limit=per_source_limit))
        if enable_reddit:
            tasks.append(fetch_reddit(client, limit=per_source_limit))
        for feed in feeds:
            url = (feed or {}).get("url")
            name = (feed or {}).get("name") or url
            if url:
                tasks.append(
                    fetch_rss_feed(client, name=name, url=url, limit=per_source_limit)
                )
        results = await asyncio.gather(*tasks, return_exceptions=True)

    candidates: list[NewsItem] = []
    for res in results:
        if isinstance(res, Exception):
            log.warning("a news source raised: %s", res)
            continue
        candidates.extend(res)
    return candidates
