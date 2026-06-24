from __future__ import annotations

import json
from pathlib import Path

from electronic_recognition.search.document_builder import DrawingDocumentBuilder
from electronic_recognition.search.search_service import DrawingSearchService
from electronic_recognition.search.sqlite_store import DrawingSearchStore


class _BrokenEmbeddingBackend:
    model_id = "broken"
    dimension = 2

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return []

    def embed_query(self, text: str) -> list[float]:
        raise RuntimeError("embedding backend offline")


class _UnusedVectorStore:
    def search(self, query_vector: list[float], limit: int) -> list[object]:
        raise AssertionError("降级时不应调用向量检索")

    def health(self) -> dict[str, object]:
        return {"available": False, "collection": "demo_v2", "points": 0}


def test_search_degrades_to_exact_and_bm25_when_embedding_fails(
    tmp_path: Path,
) -> None:
    result_dir = _write_result(
        tmp_path,
        "result-degraded",
        {
            "document": "fan-control.pdf",
            "title_block": {
                "fields": {"drawing_title": "Fan control drawing"}
            },
            "detected_components": [
                {
                    "code": "K1",
                    "label": "Contactor coil",
                    "component_type": "relay",
                    "page": 1,
                }
            ],
            "detected_combinations": [],
            "preview_pages": [{"page": 1}],
            "meta": {"page_count": 1},
        },
    )
    store = DrawingSearchStore(tmp_path / "drawings.db")
    document = DrawingDocumentBuilder().build(
        "result-degraded",
        result_dir,
        _read_result(result_dir),
    )
    store.upsert_document(document)
    service = DrawingSearchService(
        store,
        embedding_backend=_BrokenEmbeddingBackend(),
        vector_store=_UnusedVectorStore(),
        mode="hybrid",
    )

    payload = service.search("K1")

    assert payload["degraded"] is True
    assert "embedding backend offline" in payload["degraded_reason"]
    assert payload["items"][0]["result_id"] == "result-degraded"


def test_vector_mode_degrades_to_sparse_results(
    tmp_path: Path,
) -> None:
    result_dir = _write_result(
        tmp_path,
        "result-vector-fallback",
        {
            "document": "fan-control.pdf",
            "detected_components": [
                {
                    "code": "K1",
                    "label": "交流继电器线圈",
                    "component_type": "继电器",
                    "page": 1,
                }
            ],
        },
    )
    store = DrawingSearchStore(tmp_path / "drawings.db")
    store.upsert_document(
        DrawingDocumentBuilder().build(
            "result-vector-fallback",
            result_dir,
            _read_result(result_dir),
        )
    )
    service = DrawingSearchService(
        store,
        embedding_backend=_BrokenEmbeddingBackend(),
        vector_store=_UnusedVectorStore(),
        mode="hybrid",
    )

    payload = service.search("K1", retrieval_mode="vector")

    assert payload["degraded"] is True
    assert payload["effective_mode"] == "bm25"
    assert payload["items"][0]["result_id"] == "result-vector-fallback"


def _write_result(
    root: Path,
    result_id: str,
    payload: dict[str, object],
) -> Path:
    result_dir = root / result_id
    result_dir.mkdir()
    (result_dir / "result.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    return result_dir


def _read_result(result_dir: Path) -> dict[str, object]:
    return json.loads((result_dir / "result.json").read_text(encoding="utf-8"))
