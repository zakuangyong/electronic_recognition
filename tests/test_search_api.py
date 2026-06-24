from __future__ import annotations

import json
import tempfile
from pathlib import Path

from electronic_recognition import api


def test_search_demo_queries_api_reads_demo_file(monkeypatch) -> None:
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
