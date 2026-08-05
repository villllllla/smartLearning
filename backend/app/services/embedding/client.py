"""Embedding providers: local sentence-transformers or OpenAI-compatible APIs."""
from __future__ import annotations

import logging

import httpx

from app.core.config import get_settings
from app.services.embedding.vector_math import normalize
from app.services.rag.embedder import (
    RagEmbedderError,
    embedding_from_json,
    embedding_to_json,
)
from app.services.rag.embedder import (
    embed_texts as embed_texts_local,
)

log = logging.getLogger(__name__)


class EmbeddingClientError(RuntimeError):
    pass


def embedding_configured() -> bool:
    settings = get_settings()
    if settings.dedupe_use_embedding:
        if settings.embedding_provider == "openai_compatible":
            return bool((settings.embedding_api_key or "").strip())
        return True
    return False


def embed_stems(texts: list[str]) -> list[list[float]]:
    """Embed question stems for deduplication (normalized vectors)."""
    if not texts:
        return []
    settings = get_settings()
    provider = (settings.embedding_provider or "local").strip().lower()
    if provider == "openai_compatible":
        return _embed_openai_compatible(texts)
    try:
        vecs = embed_texts_local(texts)
    except RagEmbedderError as exc:
        raise EmbeddingClientError(str(exc)) from exc
    return [normalize(v) for v in vecs]


def _embed_openai_compatible(texts: list[str]) -> list[list[float]]:
    settings = get_settings()
    api_key = (settings.embedding_api_key or "").strip()
    if not api_key:
        raise EmbeddingClientError(
            "未配置 Embedding API Key，请在 backend/.env 设置 SL_EMBEDDING_API_KEY"
        )
    base = (settings.embedding_api_base or "").rstrip("/")
    url = f"{base}/embeddings"
    body: dict = {
        "model": settings.embedding_model,
        "input": texts,
        "encoding_format": settings.embedding_encoding_format,
    }
    if settings.embedding_dimensions > 0:
        body["dimensions"] = settings.embedding_dimensions
    try:
        resp = httpx.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json=body,
            timeout=settings.model_request_timeout_seconds,
        )
        resp.raise_for_status()
        payload = resp.json()
    except httpx.HTTPError as exc:
        raise EmbeddingClientError(f"Embedding API 请求失败: {exc}") from exc

    data = payload.get("data")
    if not isinstance(data, list) or len(data) != len(texts):
        raise EmbeddingClientError("Embedding API 返回格式异常")
    ordered = sorted(data, key=lambda item: int(item.get("index", 0)))
    vecs: list[list[float]] = []
    for item in ordered:
        vec = item.get("embedding")
        if not isinstance(vec, list):
            raise EmbeddingClientError("Embedding API 缺少 embedding 字段")
        vecs.append(normalize([float(x) for x in vec]))
    return vecs


__all__ = [
    "EmbeddingClientError",
    "embed_stems",
    "embedding_configured",
    "embedding_from_json",
    "embedding_to_json",
]
