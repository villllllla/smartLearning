"""Vector helpers for embedding similarity."""
from __future__ import annotations

import math


def normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm <= 0:
        return vec
    return [x / norm for x in vec]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=True))  # lengths checked above


def l2_distance(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return float("inf")
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b, strict=True)))  # lengths checked above


def l2_similarity(a: list[float], b: list[float]) -> float:
    """Map L2 distance on unit vectors to a 0..1 similarity score."""
    dist = l2_distance(a, b)
    return max(0.0, 1.0 - (dist * dist) / 2.0)
