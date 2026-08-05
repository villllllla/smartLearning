"""Local embeddings via sentence-transformers (bge-small-zh)."""
from __future__ import annotations

import json
import logging
from functools import lru_cache

from app.core.config import get_settings

log = logging.getLogger(__name__)

_MODEL = None


class RagEmbedderError(RuntimeError):
    pass


def _require_sentence_transformers():
    try:
        import sentence_transformers  # noqa: F401
    except ImportError as exc:
        raise RagEmbedderError(
            "未安装 RAG 依赖。请在 backend 目录执行: pip install -e \".[rag]\""
        ) from exc


@lru_cache(maxsize=1)
def _get_model():
    _require_sentence_transformers()
    from sentence_transformers import SentenceTransformer

    settings = get_settings()
    model_name = settings.rag_embedding_model
    log.info("Loading embedding model: %s", model_name)
    return SentenceTransformer(model_name)


def embed_texts(texts: list[str], *, batch_size: int = 32) -> list[list[float]]:
    if not texts:
        return []
    model = _get_model()
    # bge 官方建议检索时对 query 加指令；对文档块用原文
    vecs = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return [v.tolist() for v in vecs]


def embed_query(query: str) -> list[float]:
    settings = get_settings()
    prefix = settings.rag_query_prefix
    text = f"{prefix}{query}" if prefix else query
    return embed_texts([text])[0]


def embedding_to_json(vec: list[float]) -> str:
    return json.dumps(vec, separators=(",", ":"))


def embedding_from_json(raw: str) -> list[float]:
    return json.loads(raw)
