"""Question stem similarity (PRD §6.3.2 — string-based MVP, no embeddings)."""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher


def normalize_question_text(text: str) -> str:
    """Lowercase, strip noise so near-duplicate stems score high."""
    t = (text or "").strip()
    if not t:
        return ""
    t = unicodedata.normalize("NFKC", t)
    t = t.lower()
    t = re.sub(r"[^\w\u4e00-\u9fff]", "", t)
    t = re.sub(r"[\s\u3000]+", "", t)
    return t


def question_similarity(a: str, b: str) -> float:
    """0..1 ratio on normalized stems."""
    na, nb = normalize_question_text(a), normalize_question_text(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def cluster_indices(n: int, pairs: list[tuple[int, int]]) -> list[list[int]]:
    """Union-find clusters from undirected duplicate pairs."""
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    for i, j in pairs:
        union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return [sorted(g) for g in groups.values() if len(g) > 1]
