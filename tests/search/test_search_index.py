from __future__ import annotations

import json
from pathlib import Path

from electronic_recognition.search.document_builder import DrawingDocumentBuilder
from electronic_recognition.search.search_service import DrawingSearchService
from electronic_recognition.search.sqlite_store import DrawingSearchStore


def test_search_exact_terms_match_identifier_aliases(tmp_path: Path) -> None:
    result_dir = _write_result(
        tmp_path,
        "result-1",
        {
            "document": "A17387_1706_fan.pdf",
            "title_block": {
                "fields": {
                    "原理图号": "A17387_1706",
                    "图纸名称": "Fan starter",
                    "工程名称": "Project A",
                    "版本号": "B",
                }
            },
            "detected_components": [
                {
                    "code": "KM1",
                    "label": "Contactor",
                    "component_type": "control",
                    "page": 1,
                }
            ],
            "detected_combinations": [],
            "preview_pages": [{"page": 1}],
            "meta": {"page_count": 1},
        },
    )
    store = DrawingSearchStore(tmp_path / "drawings.db")
    document = DrawingDocumentBuilder().build("result-1", result_dir, _read_result(result_dir))
    store.upsert_document(document)
    service = DrawingSearchService(store)

    by_drawing_number = service.search("A17387-1706")
    by_component = service.search("KM-1")

    assert by_drawing_number["items"][0]["result_id"] == "result-1"
    assert "exact" in by_drawing_number["items"][0]["match_sources"]
    assert by_component["items"][0]["matched_components"] == ["KM1"]


def test_search_bm25_returns_function_text(tmp_path: Path) -> None:
    result_dir = _write_result(
        tmp_path,
        "result-2",
        {
            "document": "fan-control.pdf",
            "title_block": {
                "fields": {
                    "图纸名称": "Fan control drawing",
                    "系统名称": "Ventilation",
                }
            },
            "detected_components": [
                {
                    "code": "FR1",
                    "label": "Thermal relay",
                    "component_type": "overload protection",
                    "page": 1,
                    "evidence": "fan start thermal overload protection",
                }
            ],
            "detected_combinations": [
                {
                    "name": "fan start thermal overload protection",
                    "pages": [1],
                    "members": [],
                    "evidence": ["thermal relay protects fan motor"],
                }
            ],
            "preview_pages": [{"page": 1}],
            "meta": {"page_count": 1},
        },
    )
    store = DrawingSearchStore(tmp_path / "drawings.db")
    document = DrawingDocumentBuilder().build("result-2", result_dir, _read_result(result_dir))
    store.upsert_document(document)
    service = DrawingSearchService(store)

    payload = service.search("thermal overload fan")

    assert payload["items"][0]["result_id"] == "result-2"
    assert "bm25" in payload["items"][0]["match_sources"]
    assert payload["degraded"] is False


def test_search_filters_ignore_empty_lists(tmp_path: Path) -> None:
    result_dir = _write_result(
        tmp_path,
        "result-3",
        {
            "document": "fan-control.pdf",
            "title_block": {
                "fields": {
                    "图纸名称": "Fan control drawing",
                }
            },
            "detected_components": [],
            "detected_combinations": [],
            "preview_pages": [{"page": 1}],
            "meta": {"page_count": 1},
        },
    )
    store = DrawingSearchStore(tmp_path / "drawings.db")
    document = DrawingDocumentBuilder().build("result-3", result_dir, _read_result(result_dir))
    store.upsert_document(document)
    service = DrawingSearchService(store)

    payload = service.search(
        "fan",
        filters={"revision": "", "project_name": [], "system_name": None},
    )

    assert payload["query"]["filters"] == {}
    assert payload["items"][0]["result_id"] == "result-3"


def test_search_applies_project_filter(tmp_path: Path) -> None:
    store = DrawingSearchStore(tmp_path / "drawings.db")
    builder = DrawingDocumentBuilder()
    for result_id, project_name in (
        ("result-a", "成都轨道交通"),
        ("result-b", "北京地铁"),
    ):
        result_dir = _write_result(
            tmp_path,
            result_id,
            {
                "document": f"{result_id}.pdf",
                "title_block": {
                    "fields": {
                        "图纸名称": "风机控制图",
                        "工程名称": project_name,
                    }
                },
                "detected_components": [],
                "detected_combinations": [],
            },
        )
        store.upsert_document(
            builder.build(result_id, result_dir, _read_result(result_dir))
        )
    service = DrawingSearchService(store)

    payload = service.search(
        "风机控制",
        filters={"project_name": "成都"},
    )

    assert [item["result_id"] for item in payload["items"]] == ["result-a"]


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
