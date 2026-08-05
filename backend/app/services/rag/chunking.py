"""Split wiki markdown into retrieval chunks."""
from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


@dataclass
class TextChunk:
    heading: str | None
    text: str


def chunk_markdown(content_md: str, *, max_chars: int = 500, overlap: int = 80) -> list[TextChunk]:
    """Split by headings; merge small sections; sliding overlap on long bodies."""
    content_md = (content_md or "").strip()
    if not content_md:
        return []

    sections: list[tuple[str | None, str]] = []
    matches = list(_HEADING_RE.finditer(content_md))
    if not matches:
        sections.append((None, content_md))
    else:
        if matches[0].start() > 0:
            pre = content_md[: matches[0].start()].strip()
            if pre:
                sections.append((None, pre))
        for i, m in enumerate(matches):
            title = m.group(2).strip()
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content_md)
            body = content_md[start:end].strip()
            sections.append((title, body if body else title))

    merged: list[TextChunk] = []
    buf_heading: str | None = None
    buf_parts: list[str] = []

    def flush() -> None:
        nonlocal buf_heading, buf_parts
        if not buf_parts:
            return
        text = "\n\n".join(buf_parts).strip()
        if text:
            merged.append(TextChunk(heading=buf_heading, text=text))
        buf_heading = None
        buf_parts = []

    for heading, body in sections:
        piece = f"## {heading}\n{body}" if heading else body
        if not buf_parts:
            buf_heading = heading
            buf_parts = [piece]
        elif sum(len(p) for p in buf_parts) + len(piece) <= max_chars:
            buf_parts.append(piece)
        else:
            flush()
            buf_heading = heading
            buf_parts = [piece]
    flush()

    out: list[TextChunk] = []
    for ch in merged:
        if len(ch.text) <= max_chars:
            out.append(ch)
            continue
        start = 0
        while start < len(ch.text):
            end = min(len(ch.text), start + max_chars)
            slice_text = ch.text[start:end].strip()
            if slice_text:
                out.append(TextChunk(heading=ch.heading, text=slice_text))
            if end >= len(ch.text):
                break
            start = max(0, end - overlap)
    return out
