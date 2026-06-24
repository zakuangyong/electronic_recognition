from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any

from .embedding import DisabledEmbeddingBackend
from .fusion import reciprocal_rank_fusion
from .query_parser import QueryParser
from .sqlite_store import DrawingSearchStore


class DrawingSearchService:
    def __init__(
        self,
        store: DrawingSearchStore,
        parser: QueryParser | None = None,
        *,
        embedding_backend: Any | None = None,
        vector_store: Any | None = None,
        bm25_limit: int = 50,
        vector_limit: int = 50,
        rrf_k: int = 60,
        default_limit: int = 20,
        mode: str = "bm25",
        deduplicate: bool = True,
    ) -> None:
        self.store = store
        self.parser = parser or QueryParser()
        self.embedding_backend = embedding_backend or DisabledEmbeddingBackend()
        self.vector_store = vector_store
        self.bm25_limit = bm25_limit
        self.vector_limit = vector_limit
        self.rrf_k = rrf_k
        self.default_limit = default_limit
        self.mode = mode
        self.deduplicate = deduplicate

    def search(
        self,
        query: str,
        *,
        limit: int | None = None,
        offset: int = 0,
        filters: dict[str, object] | None = None,
        debug: bool = False,
        retrieval_mode: str | None = None,
    ) -> dict[str, object]:
        started = time.perf_counter()
        normalized_started = time.perf_counter()
        parsed = self.parser.parse(query, filters)
        normalize_ms = _elapsed_ms(normalized_started)
        mode = _allowed_retrieval_mode(
            retrieval_mode or self.mode,
            self.mode,
        )

        exact_started = time.perf_counter()
        exact_hits = (
            self.store.exact_search(parsed.exact_terms)
            if mode in {"bm25", "hybrid"}
            else []
        )
        exact_ms = _elapsed_ms(exact_started)

        bm25_started = time.perf_counter()
        sparse_query = " ".join(
            [parsed.normalized_query, *parsed.expanded_terms]
        ).strip()
        bm25_hits = (
            self.store.bm25_search(sparse_query, self.bm25_limit)
            if mode in {"bm25", "hybrid"}
            else []
        )
        bm25_ms = _elapsed_ms(bm25_started)

        dense_started = time.perf_counter()
        dense_hits: list[Any] = []
        degraded_reason = ""
        if mode in {"vector", "hybrid"}:
            dense_hits, degraded_reason = self._dense_hits(parsed.normalized_query)
        dense_ms = _elapsed_ms(dense_started)

        fallback_mode = ""
        if mode == "vector" and degraded_reason:
            fallback_mode = "bm25"
            exact_hits = self.store.exact_search(parsed.exact_terms)
            bm25_hits = self.store.bm25_search(
                sparse_query,
                self.bm25_limit,
            )

        fused_started = time.perf_counter()
        fused_hits = (
            dense_hits
            if mode == "vector" and not degraded_reason
            else reciprocal_rank_fusion(
                [exact_hits, bm25_hits, dense_hits],
                k=self.rrf_k,
            )
        )
        result_limit = limit or self.default_limit
        items = self.store.aggregate_drawings(
            fused_hits,
            limit=result_limit,
            offset=offset,
            debug=debug,
            deduplicate=self.deduplicate,
            filters=parsed.filters,
        )
        fusion_ms = _elapsed_ms(fused_started)
        degraded = bool(degraded_reason)
        return {
            "query": {
                "raw": parsed.raw_query,
                "normalized": parsed.normalized_query,
                "exact_terms": [asdict(term) for term in parsed.exact_terms],
                "filters": parsed.filters,
                "expanded_terms": parsed.expanded_terms,
            },
            "retrieval_mode": mode,
            "effective_mode": fallback_mode or mode,
            "total": len(items),
            "items": [asdict(item) for item in items],
            "degraded": degraded,
            "degraded_reason": degraded_reason,
            "match_counts": {
                "exact": len(exact_hits),
                "bm25": len(bm25_hits),
                "dense": len(dense_hits),
            },
            "timing_ms": {
                "normalize": normalize_ms,
                "exact": exact_ms,
                "bm25": bm25_ms,
                "dense": dense_ms,
                "fusion": fusion_ms,
                "total": _elapsed_ms(started),
            },
        }

    def health(self) -> dict[str, object]:
        status = self.store.status()
        vector_health = (
            self.vector_store.health()
            if self.vector_store is not None
            else {"available": False, "collection": "", "points": 0}
        )
        availability_check = getattr(
            self.embedding_backend,
            "is_available",
            None,
        )
        embedding_available = (
            bool(availability_check())
            if callable(availability_check)
            else getattr(self.embedding_backend, "model_id", "disabled")
            != "disabled"
        )
        status.update(
            {
                "qdrant_available": bool(vector_health.get("available", False)),
                "embedding_backend_available": embedding_available,
                "collection": str(vector_health.get("collection", "")),
                "vector_points": int(vector_health.get("points", 0) or 0),
                "degraded": not (
                    status.get("sqlite_available", False)
                    and status.get("fts5_available", False)
                    and (
                        self.mode in {"bm25", "disabled"}
                        or (
                            embedding_available
                            and bool(vector_health.get("available", False))
                        )
                    )
                ),
                "mode": self.mode,
            }
        )
        return status

    def _dense_hits(self, query: str) -> tuple[list[Any], str]:
        if getattr(self.embedding_backend, "model_id", "disabled") == "disabled":
            return [], "向量检索未启用，已降级为 Exact + BM25。"
        if self.vector_store is None:
            return [], "向量存储未配置，已降级为 Exact + BM25。"
        try:
            query_vector = self.embedding_backend.embed_query(query)
            if not query_vector:
                return [], "向量查询结果为空，已降级为 Exact + BM25。"
            return self.vector_store.search(query_vector, self.vector_limit), ""
        except Exception as exc:
            return [], str(exc)


def _elapsed_ms(started: float) -> int:
    return int(round((time.perf_counter() - started) * 1000))


def _retrieval_mode(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    if normalized in {"bm25", "vector", "hybrid", "disabled"}:
        return normalized
    return "bm25"


def _allowed_retrieval_mode(
    requested: str,
    configured: str,
) -> str:
    server_mode = _retrieval_mode(configured)
    request_mode = _retrieval_mode(requested)
    if server_mode == "hybrid":
        return request_mode
    if server_mode == "vector":
        return request_mode if request_mode in {"vector", "bm25"} else "vector"
    return "bm25"
