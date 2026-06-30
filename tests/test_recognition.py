from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path

import pytest
from fastapi import UploadFile
from PIL import Image

from electronic_recognition import api
from electronic_recognition.knowledge import ComponentKnowledgeBase
from electronic_recognition.config import Settings
from electronic_recognition.models import ComponentSample, ParsedDocument, ParsedPage
from electronic_recognition.pipeline import (
    RecognitionPipeline,
    _absorb_block_terminals,
    _build_page_views,
    _custom_symbol_shape_hint,
    _deduplicate_open_symbols,
    _exact_custom_symbol_correction,
    _group_open_symbols,
    _build_reference_panels,
    _remap_component_regions,
    normalize_components,
)


def test_component_knowledge_search_prefers_candidate_ids() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        payload = {
            "components": [
                {
                    "id": "fuse",
                    "label": "熔断器",
                    "image_path": "assets/fuse.png",
                    "aliases": ["FU"],
                },
                {
                    "id": "lamp",
                    "label": "指示灯",
                    "image_path": "assets/lamp.png",
                    "aliases": ["HL"],
                },
            ]
        }
        path = root / "components.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
        knowledge = ComponentKnowledgeBase.load(path)

        matches = knowledge.search("", 1, preferred_ids=["lamp"])

        assert matches[0].id == "lamp"


def test_exact_custom_symbol_correction_requires_strong_alias_match() -> None:
    candidates = [
        ComponentSample(
            id="user-symbol-gsd",
            label="GSD",
            image_path="gsd.png",
            component_type="图形标识",
            aliases=["GSD", "GSD图形标识"],
        )
    ]

    assert (
        _exact_custom_symbol_correction(
            {
                "raw_label": "端子",
                "code": "X01:1,X01:3",
                "component_type": "连接器件",
                "evidence": "右侧竖线中间端子符号",
            },
            candidates,
        )
        is None
    )
    corrected = _exact_custom_symbol_correction(
        {
            "raw_label": "GSD",
            "code": "",
            "component_type": "端子",
            "evidence": "开放识别为 GSD 图形标识",
        },
        candidates,
    )

    assert corrected is not None
    assert corrected["reference_id"] == "user-symbol-gsd"


def test_custom_symbol_shape_hint_targets_isolated_terminal_misread() -> None:
    assert "GSD" in _custom_symbol_shape_hint(
        {
            "raw_label": "端子排",
            "code": "",
            "component_type": "连接器件",
            "occurrence_count": 1,
            "evidence": "多端子连接器符号",
        }
    )
    assert (
        _custom_symbol_shape_hint(
            {
                "raw_label": "接线端子",
                "code": "X01:1",
                "component_type": "连接器件",
                "occurrence_count": 1,
                "evidence": "圆形端子符号，下方标注X01:1",
            }
        )
        == ""
    )


def test_normalize_components_merges_duplicate_regions() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        image = root / "fuse.png"
        Image.new("RGB", (20, 20), "white").save(image)
        path = root / "components.json"
        path.write_text(
            json.dumps(
                {
                    "components": [
                        {
                            "id": "fuse",
                            "label": "熔断器",
                            "image_path": str(image),
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        references = [ComponentKnowledgeBase.load(path).components[0]]
        result = normalize_components(
            [
                {
                    "reference_id": "fuse",
                    "label": "熔断器",
                    "code": "FU1",
                    "page": 1,
                    "occurrence_count": 2,
                    "regions": [
                        [100, 100, 200, 200],
                        [300, 100, 400, 200],
                    ],
                    "confidence": 0.9,
                },
                {
                    "reference_id": "fuse",
                    "label": "熔断器",
                    "code": "FU1",
                    "page": 1,
                    "occurrence_count": 1,
                    "regions": [[100, 100, 200, 200]],
                    "confidence": 0.8,
                },
            ],
            references,
            page_count=1,
        )

        assert len(result) == 1
        assert result[0]["occurrence_count"] == 2
        assert len(result[0]["regions"]) == 2


def test_reference_panel_contains_rotations_and_manual_variants() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        primary = root / "primary.png"
        variant = root / "variant.png"
        Image.new("RGB", (80, 40), "white").save(primary)
        Image.new("RGB", (40, 80), "white").save(variant)
        knowledge_path = root / "components.json"
        knowledge_path.write_text(
            json.dumps(
                {
                    "components": [
                        {
                            "id": "switch",
                            "label": "开关",
                            "image_path": str(primary),
                            "variant_images": [str(variant)],
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        knowledge = ComponentKnowledgeBase.load(knowledge_path)

        panels = _build_reference_panels(
            knowledge,
            knowledge.components,
            root / "panels",
        )

        assert len(panels) == 1
        assert panels[0].is_file()
        with Image.open(panels[0]) as panel:
            assert panel.width == 840
            assert panel.height == 1362


def test_page_views_ignore_grid_and_use_full_page() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        page = root / "page.png"
        Image.new("RGB", (100, 100), "white").save(page)
        views = _build_page_views(
            page,
            root / "tiles",
            page_number=1,
            grid=2,
            overlap=0.2,
        )
        remapped = _remap_component_regions(
            [
                {
                    "reference_id": "switch",
                    "label": "开关",
                    "code": "SA1",
                    "source_image_index": 1,
                    "regions": [[270, 270, 340, 340]],
                },
                {
                    "reference_id": "switch",
                    "label": "开关",
                    "code": "SA1",
                    "source_image_index": 1,
                    "regions": [[270, 270, 340, 340]],
                },
            ],
            views,
            page_number=1,
        )
        sample_path = root / "components.json"
        sample_path.write_text(
            json.dumps(
                {
                    "components": [
                        {
                            "id": "switch",
                            "label": "开关",
                            "image_path": str(page),
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        references = ComponentKnowledgeBase.load(
            sample_path
        ).components

        result = normalize_components(remapped, references, page_count=1)

        assert len(views) == 1
        assert views[0]["kind"] == "full_page"
        assert views[0]["tile"] == "full"
        assert not any((root / "tiles").glob("*.png"))
        assert len(result) == 1
        assert result[0]["occurrence_count"] == 1
        assert len(result[0]["regions"]) == 1


def test_pipeline_parses_retrieves_and_recognizes() -> None:
    class FakeModel:
        def __init__(self) -> None:
            self.model_requests = 0
            self.cache_hits = 0
            self.calls: list[list[Path]] = []
            self.prompts: list[str] = []

        def complete_json(
            self,
            _system_prompt: str,
            _user_prompt: str,
            images: list[Path],
        ) -> dict:
            self.model_requests += 1
            self.prompts.append(_user_prompt)
            self.calls.append(images)
            if self.model_requests == 1:
                return {"candidate_ids": ["fuse", "unused"]}
            if '"id": "unused"' in _user_prompt:
                return {"detected_components": []}
            return {
                "detected_components": [
                    {
                        "id": "fuse",
                        "reference_id": "fuse",
                        "label": "熔断器",
                        "code": "FU1",
                        "page": 1,
                        "occurrence_count": 1,
                        "confidence": 0.95,
                        "regions": [[100, 100, 220, 260]],
                    }
                ]
            }

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        drawing = root / "drawing.png"
        reference = root / "reference.png"
        image = Image.new("RGB", (200, 120), "white")
        image.info["Description"] = "FU1"
        image.save(drawing)
        Image.new("RGB", (40, 40), "white").save(reference)
        knowledge_path = root / "components.json"
        knowledge_path.write_text(
            json.dumps(
                {
                    "components": [
                        {
                            "id": "fuse",
                            "label": "熔断器",
                            "image_path": str(reference),
                            "aliases": ["FU1"],
                        },
                        {
                            "id": "unused",
                            "label": "unused component",
                            "image_path": str(reference),
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        model = FakeModel()
        result, page_dir = RecognitionPipeline(
            ComponentKnowledgeBase.load(knowledge_path),
            Settings(
                api_key="test",
                model="test",
                catalog_candidate_limit=5,
                reference_batch_size=1,
                recognition_mode="rag_first",
            ),
            model=model,
        ).analyze(drawing, root / "work")

        assert model.model_requests == 3
        assert len(model.calls[0]) == 1
        assert len(model.calls[1]) == 2
        assert len(model.calls[2]) == 2
        assert "unused component" in model.prompts[0]
        assert '"id": "fuse"' in model.prompts[1]
        assert '"id": "unused"' in model.prompts[2]
        assert result.detected_components[0]["code"] == "FU1"
        assert result.title_block == {}
        assert result.component_table == {}
        assert result.meta["reference_ids"] == ["fuse", "unused"]
        assert result.meta["reference_batch_size"] == 1
        assert result.meta["reference_batch_count"] == 2
        assert result.meta["catalog_components_presented"] == 2
        assert result.meta["local_catalog_recall_enabled"] is False
        assert result.meta["page_view_counts"] == [1]
        assert (page_dir / "page-1.png").is_file()


def test_hybrid_pipeline_recognizes_then_corrects_with_rag() -> None:
    class FakeModel:
        def __init__(self) -> None:
            self.model_requests = 0
            self.cache_hits = 0
            self.calls: list[list[Path]] = []
            self.prompts: list[str] = []

        def complete_json(
            self,
            _system_prompt: str,
            user_prompt: str,
            images: list[Path],
        ) -> dict:
            self.model_requests += 1
            self.prompts.append(user_prompt)
            self.calls.append(images)
            if images and images[0].name == "page-1.png":
                return {
                    "detected_symbols": [
                        {
                            "raw_label": "raw fuse symbol",
                            "code": "FU1",
                            "component_type": "protection",
                            "page": 1,
                            "source_image_index": 1,
                            "occurrence_count": 1,
                            "confidence": 0.7,
                            "regions": [[100, 100, 220, 260]],
                            "evidence": "FU1",
                        },
                        {
                            "raw_label": "raw fuse symbol",
                            "code": "FU2",
                            "component_type": "protection",
                            "page": 1,
                            "source_image_index": 1,
                            "occurrence_count": 1,
                            "confidence": 0.75,
                            "regions": [[700, 700, 820, 860]],
                            "evidence": "FU2",
                        }
                    ]
                }
            if images:
                return {"detected_symbols": []}
            return {
                "corrections": [
                    {
                        "index": 0,
                        "reference_id": "fuse",
                        "label": "Fuse",
                        "component_type": "protection",
                        "confidence": 0.92,
                        "reason": "alias FU1",
                    }
                ]
            }

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        drawing = root / "drawing.png"
        reference = root / "reference.png"
        Image.new("RGB", (200, 120), "white").save(drawing)
        Image.new("RGB", (40, 40), "white").save(reference)
        knowledge_path = root / "components.json"
        knowledge_path.write_text(
            json.dumps(
                {
                    "components": [
                        {
                            "id": "fuse",
                            "label": "Fuse",
                            "image_path": str(reference),
                            "component_type": "protection",
                            "aliases": ["FU1", "fuse"],
                        },
                        {
                            "id": "lamp",
                            "label": "Lamp",
                            "image_path": str(reference),
                            "component_type": "indicator",
                        },
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        model = FakeModel()

        result, page_dir = RecognitionPipeline(
            ComponentKnowledgeBase.load(knowledge_path),
            Settings(
                api_key="test",
                model="test",
                catalog_candidate_limit=2,
                recognition_mode="hybrid",
                layout_routing_enabled=False,
                tile_grid=1,
            ),
            model=model,
        ).analyze(drawing, root / "work")

        assert model.model_requests == 2
        assert sum(bool(call) for call in model.calls) == 1
        assert all(len(call) == 1 for call in model.calls if call)
        assert sum(not call for call in model.calls) == 1
        assert any("raw fuse symbol" in prompt for prompt in model.prompts)
        assert result.detected_components[0]["reference_id"] == "fuse"
        assert result.detected_components[0]["label"] == "Fuse"
        assert result.detected_components[0]["code"] == "FU1,FU2"
        assert result.detected_components[0]["occurrence_count"] == 2
        assert result.recognition_steps["open_symbols"][0]["raw_label"] == (
            "raw fuse symbol"
        )
        assert len(result.recognition_steps["open_symbols"]) == 2
        categories = result.recognition_steps["open_categories"]
        assert len(categories) == 1
        assert categories[0]["occurrence_count"] == 2
        assert categories[0]["expression"] == (
            "[FU1,FU2]:[raw fuse symbol]:[2]"
        )
        correction = result.recognition_steps["rag_corrections"][0]
        assert correction["symbol"]["code"] == "FU1,FU2"
        assert len(correction["components"]) == 2
        assert correction["candidates"][0]["id"] == "fuse"
        assert correction["correction"]["reference_id"] == "fuse"
        assert correction["component"]["label"] == "Fuse"
        assert result.meta["recognition_mode"] == "hybrid"
        assert result.meta["recognition_strategy"] == "vision_first"
        assert result.meta["open_symbol_count"] == 2
        assert result.meta["open_category_count"] == 1
        assert result.meta["open_instance_count"] == 2
        assert result.meta["rag_correction_count"] == 1
        assert result.meta["rag_corrected_instance_count"] == 2
        assert result.meta["page_view_counts"] == [1]
        assert result.meta["open_view_success_count"] == 1
        assert result.meta["open_view_failure_count"] == 0
        assert result.meta["candidate_ids"] == ["fuse"]
        assert (page_dir / "page-1.png").is_file()


def test_hybrid_pipeline_prefers_exact_custom_symbol_alias_during_rag() -> None:
    class FakeModel:
        def __init__(self) -> None:
            self.model_requests = 0
            self.cache_hits = 0

        def complete_json(
            self,
            _system_prompt: str,
            _user_prompt: str,
            images: list[Path],
        ) -> dict:
            self.model_requests += 1
            if images:
                return {
                    "detected_symbols": [
                        {
                            "raw_label": "GSD",
                            "code": "",
                            "component_type": "端子",
                            "page": 1,
                            "source_image_index": 1,
                            "occurrence_count": 1,
                            "confidence": 0.88,
                            "regions": [[300, 300, 360, 340]],
                            "evidence": "开放识别为 GSD 图形标识",
                        }
                    ]
                }
            return {
                "corrections": [
                    {
                        "index": 0,
                        "reference_id": "terminal",
                        "label": "接线端子",
                        "component_type": "接线端子",
                        "confidence": 0.96,
                        "reason": "粗分类为端子",
                    }
                ]
            }

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        drawing = root / "drawing.png"
        reference = root / "reference.png"
        Image.new("RGB", (200, 120), "white").save(drawing)
        Image.new("RGB", (40, 40), "white").save(reference)
        knowledge_path = root / "components.json"
        knowledge_path.write_text(
            json.dumps(
                {
                    "components": [
                        {
                            "id": "terminal",
                            "label": "接线端子",
                            "image_path": str(reference),
                            "component_type": "接线端子",
                            "aliases": ["端子"],
                        },
                        {
                            "id": "user-symbol-gsd",
                            "label": "GSD",
                            "image_path": str(reference),
                            "component_type": "图形标识",
                            "aliases": ["GSD", "GSD图形标识"],
                        },
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result, _page_dir = RecognitionPipeline(
            ComponentKnowledgeBase.load(knowledge_path),
            Settings(
                api_key="test",
                model="test",
                catalog_candidate_limit=2,
                correction_candidate_limit=2,
                recognition_mode="hybrid",
                layout_routing_enabled=False,
                tile_grid=1,
            ),
            model=FakeModel(),
        ).analyze(drawing, root / "work")

        component = result.detected_components[0]
        assert component["reference_id"] == "user-symbol-gsd"
        assert component["label"] == "GSD"
        assert component["component_type"] == "图形标识"
        correction = result.recognition_steps["rag_corrections"][0]
        assert correction["correction"]["reference_id"] == "user-symbol-gsd"
        assert "自定义图形标识" in correction["correction"]["reason"]


def test_hybrid_pipeline_corrects_isolated_terminal_misread_to_gsd() -> None:
    class FakeModel:
        def __init__(self) -> None:
            self.model_requests = 0
            self.cache_hits = 0

        def complete_json(
            self,
            _system_prompt: str,
            _user_prompt: str,
            images: list[Path],
        ) -> dict:
            self.model_requests += 1
            if images:
                return {
                    "detected_symbols": [
                        {
                            "raw_label": "端子排",
                            "code": "",
                            "component_type": "连接器件",
                            "page": 1,
                            "source_image_index": 1,
                            "occurrence_count": 1,
                            "confidence": 0.88,
                            "regions": [[675, 545, 705, 590]],
                            "evidence": "多端子连接器符号",
                        },
                        {
                            "raw_label": "接线端子",
                            "code": "X01:1",
                            "component_type": "连接器件",
                            "page": 1,
                            "source_image_index": 1,
                            "occurrence_count": 1,
                            "confidence": 0.91,
                            "regions": [[285, 840, 310, 865]],
                            "evidence": "圆形端子符号，下方标注X01:1",
                        },
                    ]
                }
            return {
                "corrections": [
                    {
                        "index": 0,
                        "reference_id": "terminal",
                        "label": "接线端子（端子排）",
                        "component_type": "接线端子",
                        "confidence": 0.94,
                        "reason": "模型仍按端子排修正",
                    },
                    {
                        "index": 1,
                        "reference_id": "terminal",
                        "label": "接线端子（端子排）",
                        "component_type": "接线端子",
                        "confidence": 0.95,
                        "reason": "X01:1 端子编号明确",
                    },
                ]
            }

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        drawing = root / "drawing.png"
        reference = root / "reference.png"
        Image.new("RGB", (200, 120), "white").save(drawing)
        Image.new("RGB", (40, 40), "white").save(reference)
        knowledge_path = root / "components.json"
        knowledge_path.write_text(
            json.dumps(
                {
                    "components": [
                        {
                            "id": "terminal",
                            "label": "接线端子（端子排）",
                            "image_path": str(reference),
                            "component_type": "接线端子",
                            "aliases": ["端子排", "接线端子"],
                        },
                        {
                            "id": "user-symbol-gsd",
                            "label": "GSD",
                            "image_path": str(reference),
                            "component_type": "图形标识",
                            "aliases": [
                                "GSD",
                                "GSD图形标识",
                                "小矩形带三角齿",
                            ],
                        },
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result, _page_dir = RecognitionPipeline(
            ComponentKnowledgeBase.load(knowledge_path),
            Settings(
                api_key="test",
                model="test",
                catalog_candidate_limit=2,
                correction_candidate_limit=2,
                recognition_mode="hybrid",
                layout_routing_enabled=False,
                tile_grid=1,
            ),
            model=FakeModel(),
        ).analyze(drawing, root / "work")

        ids = {component["reference_id"] for component in result.detected_components}
        assert ids == {"terminal", "user-symbol-gsd"}
        by_id = {
            component["reference_id"]: component
            for component in result.detected_components
        }
        assert by_id["user-symbol-gsd"]["label"] == "GSD"
        assert by_id["user-symbol-gsd"]["code"] == ""
        assert by_id["terminal"]["code"] == "X01:1"
        corrections = result.recognition_steps["rag_corrections"]
        assert corrections[0]["correction"]["reference_id"] == "user-symbol-gsd"
        assert corrections[1]["correction"]["reference_id"] == "terminal"


def test_deduplicate_open_symbols_merges_same_code_across_views() -> None:
    # 同一熔断器被整页视图和分块视图各检测一次，重映射后的边框互不重叠，
    # 但代号同为 FU，应合并为一个实例而非计数两次。
    symbols = [
        {
            "raw_label": "低压熔断器",
            "code": "FU",
            "component_type": "熔断器",
            "page": 1,
            "occurrence_count": 1,
            "confidence": 0.95,
            "regions": [[192, 192, 208, 230]],
        },
        {
            "raw_label": "熔断器",
            "code": "FU",
            "component_type": "熔断器",
            "page": 1,
            "occurrence_count": 1,
            "confidence": 0.9,
            "regions": [[168, 191, 179, 230]],
        },
    ]

    result = _deduplicate_open_symbols(symbols)

    assert len(result) == 1
    assert result[0]["occurrence_count"] == 1
    assert len(result[0]["regions"]) == 1


def test_deduplicate_open_symbols_keeps_distinct_codes() -> None:
    # 不同代号(G1、G2)即使外形相似且不重叠，也是不同实例，不得合并。
    symbols = [
        {
            "raw_label": "端子",
            "code": "G1",
            "component_type": "端子",
            "page": 1,
            "occurrence_count": 1,
            "confidence": 0.9,
            "regions": [[195, 293, 218, 310]],
        },
        {
            "raw_label": "端子",
            "code": "G2",
            "component_type": "端子",
            "page": 1,
            "occurrence_count": 1,
            "confidence": 0.9,
            "regions": [[350, 344, 368, 379]],
        },
    ]

    result = _deduplicate_open_symbols(symbols)

    assert len(result) == 2
    assert {str(item["code"]) for item in result} == {"G1", "G2"}


def test_deduplicate_open_symbols_preserves_multi_terminal_count() -> None:
    # 端子排 X01 在整页视图中占 3 个端子，分块视图重报同一代号；
    # 合并时应保留占用数更高的一次(3)，不被单端子重报压低或翻倍。
    symbols = [
        {
            "raw_label": "端子",
            "code": "X01",
            "component_type": "端子",
            "page": 1,
            "occurrence_count": 3,
            "confidence": 0.95,
            "regions": [
                [192, 520, 208, 535],
                [335, 520, 350, 535],
                [365, 520, 380, 535],
            ],
        },
        {
            "raw_label": "端子",
            "code": "X01",
            "component_type": "端子",
            "page": 1,
            "occurrence_count": 1,
            "confidence": 0.9,
            "regions": [[173, 506, 184, 523]],
        },
    ]

    result = _deduplicate_open_symbols(symbols)

    assert len(result) == 1
    assert result[0]["occurrence_count"] == 3


def test_group_open_symbols_splits_mislabeled_designators() -> None:
    # 开放识别把电感 G1/G2 误标成与端子 X01 相同的粗 label "端子"；
    # 按代号拆分后它们应进入不同类别，避免一个 reference_id 被强加到混杂代号上。
    symbols = [
        {
            "raw_label": "端子",
            "code": "G1",
            "component_type": "端子",
            "page": 1,
            "occurrence_count": 1,
            "confidence": 0.9,
            "regions": [[195, 293, 218, 310]],
        },
        {
            "raw_label": "端子",
            "code": "X01:1",
            "component_type": "端子",
            "page": 1,
            "occurrence_count": 1,
            "confidence": 0.9,
            "regions": [[172, 506, 184, 523]],
        },
    ]

    categories = _group_open_symbols(symbols)

    codes = {category["summary"]["code"] for category in categories}
    assert codes == {"G1", "X01:1"}
    assert len(categories) == 2


def test_absorb_block_terminals_drops_redundant_block() -> None:
    # 端子排块 X01(占 3 个端子)与其子端子 X01:1/3/5 指向同一组端子；
    # 子端子数量不少于块时，应丢弃裸块、保留更具体的子端子，避免层级重复计数。
    symbols = [
        {"code": "X01", "page": 1, "occurrence_count": 3, "confidence": 0.95,
         "regions": [[192, 520, 208, 535], [335, 520, 350, 535], [365, 520, 380, 535]]},
        {"code": "X01:1", "page": 1, "occurrence_count": 1, "confidence": 0.9,
         "regions": [[173, 506, 184, 523]]},
        {"code": "X01:3", "page": 1, "occurrence_count": 1, "confidence": 0.9,
         "regions": [[322, 506, 333, 523]]},
        {"code": "X01:5", "page": 1, "occurrence_count": 1, "confidence": 0.9,
         "regions": [[356, 506, 368, 523]]},
    ]

    result = _absorb_block_terminals(symbols)

    codes = {str(item["code"]) for item in result}
    assert codes == {"X01:1", "X01:3", "X01:5"}
    assert sum(int(item["occurrence_count"]) for item in result) == 3


def test_absorb_block_terminals_keeps_block_when_more_terminals() -> None:
    # 块统计到 5 个端子但只单独标注了 2 个子端子时，保留块以免漏数，
    # 并把子端子代号并入块的 code。
    symbols = [
        {"code": "X01", "page": 1, "occurrence_count": 5, "confidence": 0.95,
         "regions": [[10, 10, 20, 20]]},
        {"code": "X01:1", "page": 1, "occurrence_count": 1, "confidence": 0.9,
         "regions": [[10, 10, 14, 20]]},
        {"code": "X01:2", "page": 1, "occurrence_count": 1, "confidence": 0.9,
         "regions": [[14, 10, 18, 20]]},
    ]

    result = _absorb_block_terminals(symbols)

    assert len(result) == 1
    block = result[0]
    assert int(block["occurrence_count"]) == 5
    assert set(str(block["code"]).split(",")) == {"X01", "X01:1", "X01:2"}


def test_absorb_block_terminals_noop_without_block() -> None:
    # 只有子端子、没有裸块代号时，不做任何吸收。
    symbols = [
        {"code": "X01:1", "page": 1, "occurrence_count": 1, "regions": [[10, 10, 14, 20]]},
        {"code": "X01:3", "page": 1, "occurrence_count": 1, "regions": [[14, 10, 18, 20]]},
    ]

    result = _absorb_block_terminals(symbols)

    assert len(result) == 2


def test_vision_first_tiles_recover_symbol_missed_on_full_page() -> None:
    # 整页视图只看到大符号 FU、漏掉小电感 G1；分块视图(放大)补识别出 G1，
    # 并再次看到 FU。两遍结果按代号合并：FU 跨视图只计一次，G1 作为新实例补入。
    class FakeModel:
        def __init__(self) -> None:
            self.model_requests = 0
            self.cache_hits = 0

        def complete_json(
            self,
            _system_prompt: str,
            _user_prompt: str,
            images: list[Path],
        ) -> dict:
            self.model_requests += 1
            if not images:
                return {"corrections": []}
            if images[0].name == "page-1.png":
                return {
                    "detected_symbols": [
                        {
                            "raw_label": "熔断器",
                            "code": "FU",
                            "component_type": "熔断器",
                            "page": 1,
                            "source_image_index": 1,
                            "occurrence_count": 1,
                            "confidence": 0.9,
                            "regions": [[100, 100, 200, 300]],
                            "evidence": "FU",
                        }
                    ]
                }
            return {
                "detected_symbols": [
                    {
                        "raw_label": "熔断器",
                        "code": "FU",
                        "component_type": "熔断器",
                        "page": 1,
                        "source_image_index": 1,
                        "occurrence_count": 1,
                        "confidence": 0.85,
                        "regions": [[120, 120, 360, 520]],
                        "evidence": "FU",
                    },
                    {
                        "raw_label": "电感",
                        "code": "G1",
                        "component_type": "电感",
                        "page": 1,
                        "source_image_index": 1,
                        "occurrence_count": 1,
                        "confidence": 0.7,
                        "regions": [[400, 400, 520, 560]],
                        "evidence": "G1 小线圈",
                    },
                ]
            }

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        drawing = root / "drawing.png"
        reference = root / "reference.png"
        Image.new("RGB", (240, 160), "white").save(drawing)
        Image.new("RGB", (40, 40), "white").save(reference)
        knowledge_path = root / "components.json"
        knowledge_path.write_text(
            json.dumps(
                {
                    "components": [
                        {
                            "id": "fuse",
                            "label": "熔断器",
                            "image_path": str(reference),
                            "component_type": "熔断器",
                            "aliases": ["FU"],
                        },
                        {
                            "id": "inductor",
                            "label": "电感",
                            "image_path": str(reference),
                            "component_type": "电感",
                            "aliases": ["G"],
                        },
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result, _page_dir = RecognitionPipeline(
            ComponentKnowledgeBase.load(knowledge_path),
            Settings(
                api_key="test",
                model="test",
                catalog_candidate_limit=2,
                recognition_mode="vision_first",
                layout_routing_enabled=False,
                tile_grid=2,
            ),
            model=FakeModel(),
        ).analyze(drawing, root / "work")

        by_code = {
            component["code"]: component
            for component in result.detected_components
        }
        # 分块召回成功：整页漏掉的 G1 被补回
        assert "G1" in by_code
        # 跨整页+分块视图，同代号 FU 未被重复计数
        assert by_code["FU"]["occurrence_count"] == 1
        assert result.meta["page_view_mode"] == "full_page+tiles"
        assert result.meta["page_view_counts"][0] > 1


def test_persist_result_writes_intermediate_step_files() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        work_dir = root / "work"
        page_dir = work_dir / "pages"
        page_dir.mkdir(parents=True)
        Image.new("RGB", (20, 12), "white").save(page_dir / "page-1.png")
        input_path = root / "drawing.png"
        input_path.write_bytes(b"test")
        result_dir = root / "result"
        payload = {
            "document": "drawing.png",
            "detected_components": [{"label": "Fuse"}],
            "recognition_steps": {
                "open_symbols": [{"raw_label": "raw fuse"}],
                "rag_corrections": [{"correction": {"reference_id": "fuse"}}],
            },
            "warnings": [],
            "meta": {},
        }

        saved = api._persist_result(
            result_id="test-result",
            result_dir=result_dir,
            input_path=input_path,
            work_dir=work_dir,
            page_dir=page_dir,
            payload=payload,
        )

        assert saved["recognition_steps"]["open_symbols"][0]["raw_label"] == (
            "raw fuse"
        )
        assert (
            json.loads(
                (result_dir / "steps" / "04-open-symbols.json").read_text(
                    encoding="utf-8"
                )
            )[0]["raw_label"]
            == "raw fuse"
        )
        assert (
            json.loads(
                (
                    result_dir / "steps" / "05-rag-corrections.json"
                ).read_text(encoding="utf-8")
            )[0]["correction"]["reference_id"]
            == "fuse"
        )
        assert (result_dir / "steps" / "06-detected-components.json").is_file()
        assert (
            result_dir / "steps" / "06-detected-combinations.json"
        ).is_file()
        assert (result_dir / "steps" / "04-detected-components.json").is_file()


def test_progress_writer_records_readable_recognition_logs() -> None:
    with tempfile.TemporaryDirectory() as temp:
        result_dir = Path(temp)
        progress = api._result_progress_writer(result_dir)

        progress(
            "open_recognition_tiles",
            [
                {
                    "page": 1,
                    "tile": "full",
                    "view": "full",
                    "status": "complete",
                    "symbol_count": 3,
                }
            ],
        )
        progress(
            "open_categories",
            [{"raw_label": "A", "occurrence_count": 3}],
        )
        progress("job_completed", {})

        logs = json.loads(
            (
                result_dir
                / "steps"
                / "00-recognition-log.json"
            ).read_text(encoding="utf-8")
        )

        assert logs[0]["stage"] == "job_started"
        assert "full" in logs[1]["message"]
        assert "3" in logs[1]["message"]
        assert "共 1 种" in logs[2]["message"]
        assert logs[-1]["stage"] == "job_completed"


def test_analyze_returns_running_job_before_background_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started: list[dict[str, object]] = []

    class FakeThread:
        def __init__(self, **kwargs: object) -> None:
            started.append(kwargs)

        def start(self) -> None:
            started[-1]["started"] = True

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        knowledge_path = root / "components.json"
        knowledge_path.write_text(
            json.dumps({"components": []}),
            encoding="utf-8",
        )
        monkeypatch.setattr(api, "RESULT_DIR", root / "result")
        monkeypatch.setattr(api, "KNOWLEDGE_PATH", knowledge_path)
        monkeypatch.setattr(api.threading, "Thread", FakeThread)
        drawing = UploadFile(
            filename="drawing.png",
            file=io.BytesIO(b"png"),
        )

        response = api.analyze(drawing)
        try:
            assert response["status"] == "running"
            assert response["result_id"]
            assert response["steps_url"].endswith("/steps")
            assert started[0]["started"] is True
            result_dir = root / "result" / str(response["result_id"])
            assert (result_dir / "input" / "drawing.png").is_file()
            manifest = json.loads(
                (result_dir / "manifest.json").read_text(encoding="utf-8")
            )
            assert manifest["status"] == "running"
        finally:
            api._release_result_id(str(response["result_id"]))


def test_result_directory_uses_filename_and_replaces_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        monkeypatch.setattr(api, "RESULT_DIR", root / "result")
        result_id, result_dir = api._create_result_dir("drawing.png")
        (result_dir / "old-result.json").write_text("old", encoding="utf-8")

        next_id, next_dir = api._create_result_dir("drawing.png")

        assert result_id == "drawing"
        assert next_id == result_id
        assert next_dir == result_dir
        assert not (next_dir / "old-result.json").exists()


def test_analyze_rejects_concurrent_upload_for_same_filename(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        knowledge_path = root / "components.json"
        knowledge_path.write_text(
            json.dumps({"components": []}),
            encoding="utf-8",
        )
        monkeypatch.setattr(api, "RESULT_DIR", root / "result")
        monkeypatch.setattr(api, "KNOWLEDGE_PATH", knowledge_path)
        result_id = api._result_id_for_filename("drawing.png")
        api._reserve_result_id(result_id)
        try:
            with pytest.raises(api.HTTPException) as exc_info:
                api.analyze(
                    UploadFile(
                        filename="drawing.png",
                        file=io.BytesIO(b"png"),
                    )
                )
        finally:
            api._release_result_id(result_id)

        assert exc_info.value.status_code == 409


def test_failed_pages_keep_partial_recognition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class PartiallyFailingModel:
        def __init__(self) -> None:
            self.model_requests = 0
            self.cache_hits = 0
            self.calls: list[list[str]] = []

        def complete_json(
            self,
            _system_prompt: str,
            _user_prompt: str,
            images: list[Path],
        ) -> dict:
            self.model_requests += 1
            if not images:
                return {
                    "corrections": [
                        {
                            "index": 0,
                            "reference_id": "fuse",
                            "label": "Fuse",
                            "component_type": "protection",
                            "confidence": 0.9,
                            "reason": "FU1",
                        }
                    ]
                }
            self.calls.append([image.name for image in images])
            if images[0].name == "page-1.png":
                return {
                    "detected_symbols": [
                        {
                            "raw_label": "Fuse",
                            "code": "FU1",
                            "component_type": "protection",
                            "source_image_index": 1,
                            "occurrence_count": 1,
                            "confidence": 0.8,
                            "regions": [[100, 100, 220, 260]],
                            "evidence": "FU1",
                        }
                    ]
                }
            raise RuntimeError(
                "Remote end closed connection without response"
            )

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        result_id = "failed-result"
        result_dir = root / "result" / result_id
        result_dir.mkdir(parents=True)
        drawing = result_dir / "input" / "A17387_1706_项目原理图_05.png"
        drawing.parent.mkdir()
        Image.new("RGB", (200, 120), "white").save(drawing)
        model_page_dir = result_dir / "pages"
        page_1 = model_page_dir / "page-1.png"
        page_2 = model_page_dir / "page-2.png"
        model_page_dir.mkdir(parents=True)
        Image.new("RGB", (200, 120), "white").save(page_1)
        Image.new("RGB", (200, 120), "white").save(page_2)
        reference = root / "reference.png"
        Image.new("RGB", (40, 40), "white").save(reference)
        knowledge_path = root / "components.json"
        knowledge_path.write_text(
            json.dumps(
                {
                    "components": [
                        {
                            "id": "fuse",
                            "label": "Fuse",
                            "image_path": str(reference),
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        api._write_initial_manifest(
            result_id=result_id,
            result_dir=result_dir,
            input_path=drawing,
            status="running",
        )
        def fake_parse_document(
            input_path: str | Path,
            work_dir: str | Path,
            render_dpi: int = 220,
            max_pages: int = 12,
        ) -> ParsedDocument:
            return ParsedDocument(
                filename=Path(input_path).name,
                pages=[
                    ParsedPage(
                        1,
                        "",
                        str(page_1),
                        width=200,
                        height=120,
                    ),
                    ParsedPage(
                        2,
                        "",
                        str(page_2),
                        width=200,
                        height=120,
                    ),
                ],
            )

        monkeypatch.setattr(
            "electronic_recognition.pipeline.parse_document",
            fake_parse_document,
        )
        progress = api._result_progress_writer(result_dir)
        model = PartiallyFailingModel()
        pipeline = RecognitionPipeline(
            ComponentKnowledgeBase.load(knowledge_path),
            Settings(
                api_key="test",
                model="test",
                recognition_mode="vision_first",
                layout_routing_enabled=False,
                tile_grid=1,
            ),
            model=model,
        )

        result, page_dir = pipeline.analyze(
            drawing,
            result_dir,
            progress=progress,
        )
        api._persist_result(
            result_id=result_id,
            result_dir=result_dir,
            input_path=drawing,
            work_dir=result_dir,
            page_dir=page_dir,
            payload=result.to_dict(),
        )
        monkeypatch.setattr(api, "RESULT_DIR", root / "result")
        saved = api.saved_result(result_id)
        steps = api.result_steps(result_id)

        assert saved["detected_components"][0]["reference_id"] == "fuse"
        assert saved["meta"]["open_view_success_count"] == 1
        assert saved["meta"]["open_view_failure_count"] == 1
        assert saved["meta"]["page_view_counts"] == [1, 1]
        assert model.calls == [["page-1.png"], ["page-2.png"]]
        assert any(
            "Remote end closed connection without response" in warning
            for warning in saved["warnings"]
        )
        assert "document" in steps["steps"]
        assert len(steps["steps"]["open_symbols"]) == 1
        page_steps = steps["steps"]["open_recognition_tiles"]
        assert len(page_steps) == 2
        assert [item["tile"] for item in page_steps] == ["full", "full"]
        assert sum(item["status"] == "failed" for item in page_steps) == 1
        assert (result_dir / "input" / drawing.name).is_file()
        assert (result_dir / "pages" / "page-1.png").is_file()
        assert (result_dir / "pages" / "page-2.png").is_file()
        assert (result_dir / "steps" / "00-document.json").is_file()
        assert (result_dir / "steps" / "04-open-symbols.json").is_file()
        assert (
            result_dir
            / "steps"
            / "04-open-recognition-tiles.json"
        ).is_file()
        assert (result_dir / "result.json").is_file()
        manifest = json.loads(
            (result_dir / "manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["status"] == "complete"
        assert manifest["page_files"] == [
            {"page": 1, "file": "pages/page-1.png"},
            {"page": 2, "file": "pages/page-2.png"},
        ]
