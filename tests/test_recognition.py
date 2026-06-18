from __future__ import annotations

import json
import tempfile
from pathlib import Path

from PIL import Image

from electronic_recognition.knowledge import ComponentKnowledgeBase
from electronic_recognition.config import Settings
from electronic_recognition.pipeline import (
    RecognitionPipeline,
    _build_page_views,
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


def test_tile_regions_are_remapped_and_deduplicated() -> None:
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
                    "source_image_index": 2,
                    "regions": [[500, 500, 600, 600]],
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

        assert len(views) == 5
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
            ),
            model=model,
        ).analyze(drawing, root / "work")

        assert model.model_requests == 3
        assert len(model.calls[0]) == 1
        assert len(model.calls[1]) == 6
        assert len(model.calls[2]) == 6
        assert "unused component" in model.prompts[0]
        assert '"id": "fuse"' in model.prompts[1]
        assert '"id": "unused"' in model.prompts[2]
        assert result.detected_components[0]["code"] == "FU1"
        assert result.title_block == {}
        assert result.meta["reference_ids"] == ["fuse", "unused"]
        assert result.meta["reference_batch_size"] == 1
        assert result.meta["reference_batch_count"] == 2
        assert result.meta["catalog_components_presented"] == 2
        assert result.meta["local_catalog_recall_enabled"] is False
        assert result.meta["page_view_counts"] == [5]
        assert (page_dir / "page-1.png").is_file()
