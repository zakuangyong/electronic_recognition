from __future__ import annotations

import threading
from contextlib import AbstractContextManager, nullcontext
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable
from uuid import NAMESPACE_URL, uuid5

from .models import SearchChunk, SearchHit


class QdrantVectorStore:
    def __init__(
        self,
        *,
        collection_name: str,
        vector_size: int = 0,
        client: Any | None = None,
        client_factory: Callable[[], Any] | None = None,
        lock: "threading.Lock | threading.RLock | None" = None,
    ) -> None:
        self.collection_name = collection_name
        self.vector_size = vector_size
        self._client = client
        self._client_factory = client_factory
        # Embedded Qdrant (QdrantLocal) is not safe for concurrent access. The
        # api layer shares one client process-wide, so all operations must be
        # serialized through this lock to keep the background auto-index thread
        # and request threads from racing on the same local store.
        self._lock = lock
        self._ready = False

    def _guard(self) -> AbstractContextManager[Any]:
        return self._lock if self._lock is not None else nullcontext()

    def point_id_for_chunk(self, chunk_id: str) -> str:
        return str(uuid5(NAMESPACE_URL, chunk_id))

    def ensure_collection(self) -> None:
        if self._ready:
            return
        with self._guard():
            self._ensure_collection_locked()

    def _ensure_collection_locked(self) -> None:
        if self._ready:
            return
        client = self._get_client()
        if client.collection_exists(self.collection_name):
            self._ready = True
            return
        if self.vector_size <= 0:
            raise RuntimeError("向量维度未初始化，无法创建 Qdrant collection。")
        if not client.collection_exists(self.collection_name):
            vectors_config: object = {
                "size": self.vector_size,
                "distance": "Cosine",
            }
            if self._uses_native_models(client):
                from qdrant_client.models import Distance, VectorParams

                vectors_config = VectorParams(
                    size=self.vector_size,
                    distance=Distance.COSINE,
                )
            client.create_collection(
                collection_name=self.collection_name,
                vectors_config=vectors_config,
            )
        self._ready = True

    def upsert_chunks(
        self,
        *,
        result_id: str,
        drawing_id: str,
        chunks: list[SearchChunk],
        vectors: list[list[float]],
        embedding_model: str,
        builder_version: str,
    ) -> int:
        if not chunks:
            return 0
        if len(chunks) != len(vectors):
            raise ValueError("chunks 与 vectors 数量不一致")
        with self._guard():
            if self.vector_size <= 0 and vectors:
                self.vector_size = len(vectors[0])
            self._ensure_collection_locked()
            return self._upsert_locked(
                result_id=result_id,
                drawing_id=drawing_id,
                chunks=chunks,
                vectors=vectors,
                embedding_model=embedding_model,
                builder_version=builder_version,
            )

    def _upsert_locked(
        self,
        *,
        result_id: str,
        drawing_id: str,
        chunks: list[SearchChunk],
        vectors: list[list[float]],
        embedding_model: str,
        builder_version: str,
    ) -> int:
        client = self._get_client()
        points = []
        for chunk, vector in zip(chunks, vectors):
            point = {
                "id": self.point_id_for_chunk(chunk.chunk_id),
                "vector": vector,
                "payload": {
                    "chunk_id": chunk.chunk_id,
                    "drawing_id": chunk.drawing_id,
                    "result_id": result_id,
                    "chunk_type": chunk.chunk_type,
                    "page": chunk.page,
                    "region_type": chunk.region_type,
                    "content_hash": chunk.content_hash,
                    "schema_version": chunk.metadata.get(
                        "schema_version", 2
                    ),
                    "builder_version": builder_version,
                    "embedding_model": embedding_model,
                },
            }
            if self._uses_native_models(client):
                from qdrant_client.models import PointStruct

                points.append(PointStruct(**point))
            else:
                points.append(point)
        client.upsert(
            collection_name=self.collection_name,
            points=points,
            wait=True,
        )
        return len(points)

    def delete_result(self, result_id: str) -> None:
        with self._guard():
            self._ensure_collection_locked()
            self._delete_by_field("result_id", result_id)

    def delete_drawing(self, drawing_id: str) -> None:
        with self._guard():
            self._ensure_collection_locked()
            self._delete_by_field("drawing_id", drawing_id)

    def search(self, query_vector: list[float], limit: int) -> list[SearchHit]:
        if not query_vector:
            return []
        with self._guard():
            self._ensure_collection_locked()
            return self._search_locked(query_vector, limit)

    def _search_locked(
        self, query_vector: list[float], limit: int
    ) -> list[SearchHit]:
        client = self._get_client()
        if hasattr(client, "query_points"):
            response = client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=limit,
                with_payload=True,
            )
            results = list(getattr(response, "points", []) or [])
        else:
            results = client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=limit,
                with_payload=True,
            )
        hits: list[SearchHit] = []
        for rank, item in enumerate(results, start=1):
            payload = dict(getattr(item, "payload", {}) or {})
            hits.append(
                SearchHit(
                    chunk_id=str(payload.get("chunk_id", "")),
                    drawing_id=str(payload.get("drawing_id", "")),
                    score=float(getattr(item, "score", 0.0) or 0.0),
                    source="dense",
                    rank=rank,
                    page=payload.get("page"),
                    chunk_type=str(payload.get("chunk_type", "")),
                    source_ranks={"dense": rank},
                    source_scores={
                        "dense": float(getattr(item, "score", 0.0) or 0.0)
                    },
                )
            )
        return hits

    def ping(self) -> bool:
        """Open the client and report whether the collection exists.

        Used by startup warmup to surface real client/lock errors (e.g. a stale
        embedded-Qdrant ``.lock``) early, without forcing collection creation on
        a fresh deployment that has no vectors yet.
        """
        with self._guard():
            client = self._get_client()
            return bool(client.collection_exists(self.collection_name))

    def count(self) -> int:
        with self._guard():
            self._ensure_collection_locked()
            return int(
                getattr(
                    self._get_client().count(
                        collection_name=self.collection_name,
                        exact=True,
                    ),
                    "count",
                    0,
                )
            )

    def health(self) -> dict[str, object]:
        try:
            return {
                "available": True,
                "collection": self.collection_name,
                "points": self.count(),
            }
        except Exception as exc:  # pragma: no cover
            return {
                "available": False,
                "collection": self.collection_name,
                "points": 0,
                "error": str(exc),
            }

    def _delete_by_field(self, field_name: str, field_value: str) -> None:
        client = self._get_client()
        points_selector: object = {
            "filter": {
                "must": [
                    {"key": field_name, "match": {"value": field_value}}
                ]
            }
        }
        if self._uses_native_models(client):
            from qdrant_client.models import (
                FieldCondition,
                Filter,
                FilterSelector,
                MatchValue,
            )

            points_selector = FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(
                            key=field_name,
                            match=MatchValue(value=field_value),
                        )
                    ]
                )
            )
        client.delete(
            collection_name=self.collection_name,
            points_selector=points_selector,
            wait=True,
        )

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if self._client_factory is not None:
            self._client = self._client_factory()
            return self._client
        try:
            from qdrant_client import QdrantClient
        except ImportError as exc:
            raise RuntimeError("qdrant-client 未安装，无法启用向量检索。") from exc
        self._client = QdrantClient(path="data/search/qdrant")
        return self._client

    @staticmethod
    def _uses_native_models(client: Any) -> bool:
        return client.__class__.__module__.startswith("qdrant_client")
