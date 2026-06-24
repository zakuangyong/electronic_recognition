from __future__ import annotations

import json
from pathlib import Path

from electronic_recognition.search.document_builder import DrawingDocumentBuilder
from electronic_recognition.search.index_service import DrawingIndexService
from electronic_recognition.search.sqlite_store import DrawingSearchStore


class _FakeEmbeddingBackend:
    model_id = "fake-embedding"
    dimension = 2

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0]


class _FakeVectorStore:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def upsert_chunks(self, **payload: object) -> int:
        self.calls.append(payload)
        chunks = payload["chunks"]
        return len(chunks)

    def delete_result(self, result_id: str) -> None:
        return None


def test_index_service_indexes_bm25_and_vectors(tmp_path: Path) -> None:
    result_dir = tmp_path / "result-200"
    result_dir.mkdir()
    (result_dir / "result.json").write_text(
        json.dumps(
            {
                "document": "fan-control.pdf",
                "title_block": {
                    "fields": {"drawing_title": "风阀控制图"}
                },
                "detected_components": [
                    {
                        "code": "K1",
                        "label": "交流继电器线圈",
                        "component_type": "继电器",
                        "page": 1,
                    }
                ],
                "preview_pages": [{"page": 1}],
                "meta": {"page_count": 1},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    vector_store = _FakeVectorStore()
    service = DrawingIndexService(
        DrawingSearchStore(tmp_path / "drawings.db"),
        builder=DrawingDocumentBuilder(),
        embedding_backend=_FakeEmbeddingBackend(),
        vector_store=vector_store,
    )

    payload = service.index_result("result-200", result_dir, mode="all")

    assert payload["status"] == "complete"
    assert payload["chunks"] >= 2
    assert payload["vectors"] == payload["chunks"]
    assert payload["embedding_model"] == "fake-embedding"
    assert len(vector_store.calls) == 1
