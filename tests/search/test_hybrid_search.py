from __future__ import annotations

import json
from pathlib import Path

from electronic_recognition.search.document_builder import DrawingDocumentBuilder
from electronic_recognition.search.models import SearchHit
from electronic_recognition.search.search_service import DrawingSearchService
from electronic_recognition.search.sqlite_store import DrawingSearchStore


class _FakeEmbeddingBackend:
    model_id = "fake-embedding"
    dimension = 2

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.0, 1.0]


class _FakeVectorStore:
    def __init__(self, hit: SearchHit) -> None:
        self.hit = hit

    def search(self, query_vector: list[float], limit: int) -> list[SearchHit]:
        return [self.hit]

    def health(self) -> dict[str, object]:
        return {"available": True, "collection": "demo_v2", "points": 1}


def test_hybrid_search_returns_dense_matches(tmp_path: Path) -> None:
    result_dir = _write_result(
        tmp_path,
        "result-hybrid",
        {
            "document": "fan-control.pdf",
            "title_block": {
                "fields": {"drawing_title": "组合式风阀控制图"}
            },
            "detected_components": [
                {
                    "code": "K1",
                    "label": "交流继电器线圈",
                    "component_type": "继电器",
                    "page": 1,
                }
            ],
            "detected_combinations": [
                {
                    "name": "继电器线圈与辅助触点组合",
                    "rule_id": "coil_contact_group",
                    "rule_layer": "builtin",
                    "pages": [1],
                }
            ],
            "preview_pages": [{"page": 1}],
            "meta": {"page_count": 1},
        },
    )
    store = DrawingSearchStore(tmp_path / "drawings.db")
    document = DrawingDocumentBuilder().build(
        "result-hybrid",
        result_dir,
        _read_result(result_dir),
    )
    store.upsert_document(document)
    drawing_hit = SearchHit(
        chunk_id=f"{document.drawing_id}:drawing",
        drawing_id=document.drawing_id,
        score=0.95,
        source="dense",
        rank=1,
    )
    service = DrawingSearchService(
        store,
        embedding_backend=_FakeEmbeddingBackend(),
        vector_store=_FakeVectorStore(drawing_hit),
        mode="hybrid",
    )

    payload = service.search("可以手动自动切换的风阀控制回路")

    assert payload["degraded"] is False
    assert payload["match_counts"]["dense"] == 1
    assert "dense" in payload["items"][0]["match_sources"]


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
