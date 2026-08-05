"""Lightweight Markdown analysis used by the Wiki module (PRD §6.1.3).

We do *not* re-render or rewrite source Markdown — the frontend renders it.
Here we only extract metadata.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

_H1_RE = re.compile(r"^\s*#\s+(.+?)\s*$", re.MULTILINE)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_CODE_INLINE_RE = re.compile(r"`[^`]*`")
_PUNCT_OR_WS_RE = re.compile(r"[\s\u3000\.,;:!\?\-_=+*~`<>\[\]\(\){}|/\\\"']+")


def _count_fence_run(s: str, ch: str) -> int:
    """Count consecutive ``ch`` at the start of ``s`` (``s`` already left-stripped)."""
    i = 0
    while i < len(s) and s[i] == ch:
        i += 1
    return i


def _fence_opener(line: str) -> tuple[str, int] | None:
    """If ``line`` opens a fenced code block, return (``'`'`` or ``'~'``, run_length)."""
    s = line.lstrip(" \t")
    if s.startswith("```"):
        n = _count_fence_run(s, "`")
        return ("`", n) if n >= 3 else None
    if s.startswith("~~~"):
        n = _count_fence_run(s, "~")
        return ("~", n) if n >= 3 else None
    return None


def _is_fence_closer(line: str, ch: str, need_len: int) -> bool:
    s = line.lstrip(" \t")
    n = _count_fence_run(s, ch)
    if n < need_len:
        return False
    return not s[n:].strip()


def _strip_fenced_code_blocks(md: str) -> str:
    """Remove CommonMark-style fenced regions so ``#`` inside code is ignored."""
    out: list[str] = []
    fence_ch: str | None = None
    fence_len = 0
    for line in md.splitlines(keepends=True):
        if fence_len == 0:
            op = _fence_opener(line)
            if op is not None:
                fence_ch, fence_len = op
                continue
            out.append(line)
        else:
            if fence_ch is not None and _is_fence_closer(line, fence_ch, fence_len):
                fence_len = 0
                fence_ch = None
            # else: drop line (inside fence)
    return "".join(out)


def _strip_front_matter(md: str) -> str:
    """If the doc starts with YAML front matter (``---`` … ``---``), strip it.

    If there is no closing ``---`` on its own line, return ``md`` unchanged so a
    leading thematic-break ``---`` is not mistaken for front matter.
    """
    raw = md.lstrip("\ufeff")
    lines = raw.splitlines()
    if not lines or lines[0].strip() != "---":
        return md
    for j in range(1, len(lines)):
        if lines[j].strip() == "---":
            return "\n".join(lines[j + 1 :]).lstrip("\n")
    return md


def _body_for_title_scan(content_md: str) -> str:
    """Strip regions where a ``#`` line is not a real document heading."""
    s = _strip_front_matter(content_md)
    return _strip_fenced_code_blocks(s)


def _extract_document_title(content_md: str, fallback_title: str) -> str:
    """First ATX H1 in prose (not inside fenced code / not in YAML front matter)."""
    scan = _body_for_title_scan(content_md)
    m = _H1_RE.search(scan)
    return m.group(1).strip() if m else fallback_title


@dataclass
class MdMetadata:
    title: str
    word_count: int
    excerpt: str
    toc: list[dict]  # [{level, text, anchor}]
    images: list[str]
    content_hash: str


def _slug(text: str) -> str:
    """Very small heading→anchor slug, intentionally CJK-friendly."""
    s = text.strip().lower()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^\w\u4e00-\u9fff\-]", "", s)
    return s or hashlib.md5(text.encode("utf-8")).hexdigest()[:8]


def _strip_markdown_for_count(md: str) -> str:
    s = _FENCE_RE.sub(" ", md)
    s = _CODE_INLINE_RE.sub(" ", s)
    return s


def _word_count(md: str) -> int:
    """Mixed CN/EN word count: each CJK char = 1, English words split by space."""
    s = _strip_markdown_for_count(md)
    cjk = len(re.findall(r"[\u4e00-\u9fff]", s))
    s_no_cjk = re.sub(r"[\u4e00-\u9fff]", " ", s)
    en = len([w for w in re.split(r"\s+", s_no_cjk) if w.strip()])
    return cjk + en


def _excerpt(md: str, limit: int = 160) -> str:
    s = _strip_markdown_for_count(md)
    s = re.sub(r"^#+\s+.*$", "", s, flags=re.MULTILINE)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit]


def parse_markdown(content_md: str, fallback_title: str) -> MdMetadata:
    title = _extract_document_title(content_md, fallback_title)

    toc: list[dict] = []
    seen: dict[str, int] = {}
    for m in _HEADING_RE.finditer(content_md):
        level = len(m.group(1))
        text = m.group(2).strip()
        anchor = _slug(text)
        if anchor in seen:
            seen[anchor] += 1
            anchor = f"{anchor}-{seen[anchor]}"
        else:
            seen[anchor] = 0
        toc.append({"level": level, "text": text, "anchor": anchor})

    images = list({m.group(1) for m in _IMAGE_RE.finditer(content_md)})

    return MdMetadata(
        title=title,
        word_count=_word_count(content_md),
        excerpt=_excerpt(content_md),
        toc=toc,
        images=images,
        content_hash=hashlib.sha256(content_md.encode("utf-8")).hexdigest(),
    )
