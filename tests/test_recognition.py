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
                recognition_mode="rag_first",
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
        assert result.component_table == {}
        assert result.meta["reference_ids"] == ["fuse", "unused"]
        assert result.meta["reference_batch_size"] == 1
        assert result.meta["reference_batch_count"] == 2
        assert result.meta["catalog_components_presented"] == 2
        assert result.meta["local_catalog_recall_enabled"] is False
        assert result.meta["page_view_counts"] == [5]
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
            if images and images[0].name.endswith("tile-1-1.png"):
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
                        }
                    ]
                }
            if images and images[0].name.endswith("tile-2-2.png"):
                return {
                    "detected_symbols": [
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
            ),
            model=model,
        ).analyze(drawing, root / "work")

        assert model.model_requests == 5
        assert sum(bool(call) for call in model.calls) == 4
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
        assert result.meta["open_view_success_count"] == 4
        assert result.meta["open_view_failure_count"] == 0
        assert result.meta["candidate_ids"] == ["fuse"]
        assert (page_dir / "page-1.png").is_file()


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
                    "tile": "1-1",
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
        assert "切片 1-1" in logs[1]["message"]
        assert "3 条记录" in logs[1]["message"]
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

        assert result_id == "drawing.png"
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


def test_failed_tiles_keep_partial_recognition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class PartiallyFailingModel:
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
            if images[0].name.endswith("tile-1-1.png"):
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
        progress = api._result_progress_writer(result_dir)
        pipeline = RecognitionPipeline(
            ComponentKnowledgeBase.load(knowledge_path),
            Settings(
                api_key="test",
                model="test",
                recognition_mode="vision_first",
                layout_routing_enabled=False,
            ),
            model=PartiallyFailingModel(),
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
        assert saved["meta"]["open_view_failure_count"] == 3
        assert any(
            "Remote end closed connection without response" in warning
            for warning in saved["warnings"]
        )
        assert "document" in steps["steps"]
        assert len(steps["steps"]["open_symbols"]) == 1
        tile_steps = steps["steps"]["open_recognition_tiles"]
        assert len(tile_steps) == 4
        assert sum(item["status"] == "failed" for item in tile_steps) == 3
        assert (result_dir / "input" / drawing.name).is_file()
        assert (result_dir / "pages" / "page-1.png").is_file()
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
            {"page": 1, "file": "pages/page-1.png"}
        ]
