"""Optional Milvus vector store for question stem search."""
from __future__ import annotations

import logging
from typing import Any

from app.core.config import Settings, get_settings

log = logging.getLogger(__name__)

_COLLECTION_READY = False


class MilvusStoreError(RuntimeError):
    pass


def milvus_enabled(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return bool(settings.milvus_enabled and (settings.milvus_host or "").strip())


def _require_pymilvus():
    try:
        from pymilvus import (
            Collection,
            CollectionSchema,
            DataType,
            FieldSchema,
            connections,
            utility,
        )
    except ImportError as exc:
        raise MilvusStoreError(
            '未安装 Milvus 依赖。请执行: pip install -e ".[milvus]"'
        ) from exc
    return Collection, CollectionSchema, DataType, FieldSchema, connections, utility


def _connect(settings: Settings):
    parts = _require_pymilvus()
    Collection, CollectionSchema, DataType, FieldSchema, connections, utility = parts
    alias = "sl_default"
    try:
        connections.connect(
            alias=alias,
            host=settings.milvus_host,
            port=str(settings.milvus_port),
        )
    except Exception:
        if not connections.has_connection(alias):
            raise
    return Collection, CollectionSchema, DataType, FieldSchema, utility, alias


def _distance_to_similarity(distance: float, metric: str) -> float:
    metric = metric.upper()
    if metric == "L2":
        return max(0.0, 1.0 - (distance * distance) / 2.0)
    if metric == "COSINE":
        return max(0.0, 1.0 - distance)
    if metric == "IP":
        return float(distance)
    return max(0.0, 1.0 - distance)


def _ensure_collection(settings: Settings):
    global _COLLECTION_READY
    if _COLLECTION_READY:
        return
    Collection, CollectionSchema, DataType, FieldSchema, utility, alias = _connect(settings)
    name = settings.milvus_collection
    dim = settings.embedding_dimensions
    metric = settings.milvus_metric.upper()
    if not utility.has_collection(name, using=alias):
        fields = [
            FieldSchema(name="question_id", dtype=DataType.INT64, is_primary=True, auto_id=False),
            FieldSchema(name="tenant_id", dtype=DataType.INT64),
            FieldSchema(name="collection_id", dtype=DataType.INT64),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dim),
        ]
        schema = CollectionSchema(fields, description="SmartLearning question stems")
        col = Collection(name, schema, using=alias)
        index_params = settings.milvus_index_params or {"nlist": 128}
        col.create_index(
            field_name="embedding",
            index_params={
                "index_type": settings.milvus_index,
                "metric_type": metric,
                "params": index_params,
            },
        )
        log.info("Created Milvus collection %s (dim=%s, metric=%s)", name, dim, metric)
    _COLLECTION_READY = True


def upsert_question_vector(
    *,
    question_id: int,
    tenant_id: int,
    collection_id: int | None,
    vector: list[float],
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    if not milvus_enabled(settings):
        return
    _ensure_collection(settings)
    Collection, *_rest = _connect(settings)
    alias = _rest[5]
    col = Collection(settings.milvus_collection, using=alias)
    col.load()
    col.delete(expr=f"question_id == {question_id}")
    col.insert(
        [
            [question_id],
            [tenant_id],
            [collection_id or 0],
            [vector],
        ]
    )
    col.flush()


def delete_question_vector(*, question_id: int, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    if not milvus_enabled(settings):
        return
    _ensure_collection(settings)
    Collection, *_rest = _connect(settings)
    alias = _rest[5]
    col = Collection(settings.milvus_collection, using=alias)
    col.delete(expr=f"question_id == {question_id}")


def search_similar_questions(
    *,
    vector: list[float],
    tenant_id: int,
    top_k: int = 10,
    settings: Settings | None = None,
) -> list[tuple[int, float]]:
    settings = settings or get_settings()
    if not milvus_enabled(settings):
        return []
    _ensure_collection(settings)
    Collection, *_rest = _connect(settings)
    alias = _rest[5]
    col = Collection(settings.milvus_collection, using=alias)
    col.load()
    metric = settings.milvus_metric.upper()
    search_params: dict[str, Any] = settings.milvus_search_params or {"nprobe": 10}
    results = col.search(
        data=[vector],
        anns_field="embedding",
        param=search_params,
        limit=top_k,
        expr=f"tenant_id == {tenant_id}",
        output_fields=["question_id"],
    )
    hits: list[tuple[int, float]] = []
    for hit in results[0]:
        qid = int(hit.id)
        sim = _distance_to_similarity(float(hit.distance), metric)
        hits.append((qid, sim))
    return hits
