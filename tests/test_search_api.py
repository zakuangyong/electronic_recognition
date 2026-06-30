from __future__ import annotations

import json
import sys
import tempfile
import types
from pathlib import Path


def _import_api():
    if "fitz" not in sys.modules:
        sys.modules["fitz"] = types.ModuleType("fitz")
    if "pypdf" not in sys.modules:
        pypdf = types.ModuleType("pypdf")
        pypdf.PdfReader = object
        sys.modules["pypdf"] = pypdf
    from electronic_recognition import api

    return api


def test_search_demo_queries_api_reads_demo_file(monkeypatch) -> None:
    api = _import_api()
    with tempfile.TemporaryDirectory() as temp:
        demo_path = Path(temp) / "demo_queries.json"
        demo_path.write_text(
            json.dumps(
                {
                    "exact": [
                        {
                            "query": "A17387",
                            "type": "exact",
                            "expected_result_ids": ["result-1"],
                            "notes": "demo",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(api, "SEARCH_DEMO_QUERIES_PATH", demo_path)

        payload = api.search_demo_queries()

        assert "exact" in payload
        assert payload["exact"][0]["query"] == "A17387"


def test_result_preview_file_returns_original_input_file(
    monkeypatch,
    tmp_path: Path,
) -> None:
    api = _import_api()
    result_dir = tmp_path / "result-1"
    input_dir = result_dir / "input"
    input_dir.mkdir(parents=True)
    preview_file = input_dir / "drawing.pdf"
    preview_file.write_bytes(b"%PDF-1.4 demo")
    (result_dir / "manifest.json").write_text(
        json.dumps(
            {
                "result_id": "result-1",
                "document": "drawing.pdf",
                "input_file": "input/drawing.pdf",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(api, "RESULT_DIR", tmp_path)

    response = api.result_preview_file("result-1")

    assert Path(response.path) == preview_file


def test_result_preview_file_falls_back_to_first_rendered_page(
    monkeypatch,
    tmp_path: Path,
) -> None:
    api = _import_api()
    result_dir = tmp_path / "result-1"
    pages_dir = result_dir / "pages"
    pages_dir.mkdir(parents=True)
    second_page = pages_dir / "page-2.png"
    first_page = pages_dir / "page-1.png"
    second_page.write_bytes(b"page 2")
    first_page.write_bytes(b"page 1")
    (result_dir / "manifest.json").write_text(
        json.dumps({"result_id": "result-1"}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(api, "RESULT_DIR", tmp_path)

    response = api.result_preview_file("result-1")

    assert Path(response.path) == first_page


def test_result_preview_page_returns_requested_rendered_page(
    monkeypatch,
    tmp_path: Path,
) -> None:
    api = _import_api()
    result_dir = tmp_path / "result-1"
    pages_dir = result_dir / "pages"
    pages_dir.mkdir(parents=True)
    requested_page = pages_dir / "page-2.png"
    requested_page.write_bytes(b"page 2")
    monkeypatch.setattr(api, "RESULT_DIR", tmp_path)

    response = api.result_preview_page("result-1", 2)

    assert Path(response.path) == requested_page
