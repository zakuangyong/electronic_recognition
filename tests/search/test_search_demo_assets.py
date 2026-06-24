from __future__ import annotations

import json
from pathlib import Path


def test_demo_queries_file_exists_and_covers_demo_modes() -> None:
    data = json.loads(
        Path("data/search/demo_queries.json").read_text(encoding="utf-8")
    )

    assert isinstance(data, dict)
    assert set(data) >= {"exact", "keyword", "semantic", "constraint"}
    assert any(item["query"] == "A17387" for item in data["exact"])
    assert any(item["query"] == "排烟风机" for item in data["keyword"])
    assert any(
        item["query"] == "可以手动自动切换的风阀控制回路"
        for item in data["semantic"]
    )
    assert any(
        item["query"] == "同时包含K1 K2 K3的控制原理图"
        for item in data["constraint"]
    )
    for group in data.values():
        assert isinstance(group, list)
        assert group
        for item in group:
            assert set(item) >= {
                "query",
                "type",
                "expected_result_ids",
                "notes",
            }
