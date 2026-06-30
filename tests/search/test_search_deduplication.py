from __future__ import annotations

import json
from pathlib import Path

from electronic_recognition.search.document_builder import DrawingDocumentBuilder
from electronic_recognition.search.search_service import DrawingSearchService
from electronic_recognition.search.sqlite_store import DrawingSearchStore


def test_search_collapses_history_versions_by_source_hash(tmp_path: Path) -> None:
    payload = {
        "document": "fan-control.pdf",
        "title_block": {
            "fields": {
                "drawing_number": "A17387_1706",
                "drawing_title": "风阀控制图",
            }
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
    }
    older_dir = _write_result(tmp_path, "result-old", payload)
    newer_dir = _write_result(tmp_path, "result-new", payload)
    builder = DrawingDocumentBuilder()
    store = DrawingSearchStore(tmp_path / "drawings.db")
    store.upsert_document(builder.build("result-old", older_dir, _read_result(older_dir)))
    store.upsert_document(builder.build("result-new", newer_dir, _read_result(newer_dir)))
    service = DrawingSearchService(store, mode="bm25", deduplicate=True)

    payload = service.search("A17387")

    assert len(payload["items"]) == 1
    assert payload["items"][0]["result_id"] == "result-new"
    assert payload["items"][0]["collapsed_versions"] == 1
    assert payload["items"][0]["preview_url"] == "/api/results/result-new/preview-file#page-1"
    assert payload["items"][0]["history_versions"] == [
        {"result_id": "result-old"}
    ]


def test_search_debug_keeps_history_versions_expanded(tmp_path: Path) -> None:
    payload = {
        "document": "fan-control.pdf",
        "title_block": {
            "fields": {
                "drawing_number": "A17387_1706",
                "drawing_title": "风阀控制图",
            }
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
    }
    older_dir = _write_result(tmp_path, "result-old", payload)
    newer_dir = _write_result(tmp_path, "result-new", payload)
    builder = DrawingDocumentBuilder()
    store = DrawingSearchStore(tmp_path / "drawings.db")
    store.upsert_document(builder.build("result-old", older_dir, _read_result(older_dir)))
    store.upsert_document(builder.build("result-new", newer_dir, _read_result(newer_dir)))
    service = DrawingSearchService(store, mode="bm25", deduplicate=True)

    result = service.search("A17387", debug=True)

    assert [item["result_id"] for item in result["items"]] == [
        "result-new",
        "result-old",
    ]


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
