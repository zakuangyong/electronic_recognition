from __future__ import annotations

import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageDraw, ImageOps

from .config import Settings
from .component_table_extractor import extract_component_table
from .combination_rules import detect_combinations
from .control_signal_extractor import (
    extract_control_signal_configuration,
)
from .custom_rules import CustomRuleKnowledgeBase
from .document import parse_document
from .knowledge import ComponentKnowledgeBase
from .layout_models import PageLayout
from .layout_router import LayoutRouter, summarize_layouts
from .llm import VisionModel
from .models import ComponentSample, RecognitionResult
from .prompts import (
    SYSTEM_PROMPT,
    batch_correction_prompt,
    catalog_prompt,
    open_recognition_prompt,
    recognition_prompt,
)
from .title_block_extractor import extract_title_block
from .region_images import crop_region_image


class RecognitionPipeline:
    def __init__(
        self,
        knowledge_base: ComponentKnowledgeBase,
        settings: Settings | None = None,
        model: VisionModel | None = None,
        custom_rule_base: CustomRuleKnowledgeBase | None = None,
    ) -> None:
        self.knowledge_base = knowledge_base
        self.settings = settings or Settings.from_env()
        self.model = model or VisionModel(self.settings)
        self.custom_rule_base = (
            custom_rule_base or CustomRuleKnowledgeBase.empty()
        )
        self.layout_router = LayoutRouter(self.settings)

    def analyze(
        self,
        input_path: str | Path,
        work_dir: str | Path,
        progress: Callable[[str, object], None] | None = None,
    ) -> tuple[RecognitionResult, Path]:
        started = time.perf_counter()
        directory = Path(work_dir)
        directory.mkdir(parents=True, exist_ok=True)
        document = parse_document(
            input_path,
            directory,
            render_dpi=self.settings.render_dpi,
            max_pages=self.settings.max_pages,
        )
        _emit(
            progress,
            "document",
            {
                "filename": document.filename,
                "pages": [
                    {
                        "page": page.number,
                        "image_path": page.image_path,
                        "text_length": len(page.text),
                    }
                    for page in document.pages
                ],
            },
        )
        title_block: dict[str, Any] = {}
        title_block_warning = ""
        control_signal_configuration: dict[str, Any] = {}
        control_signal_warning = ""
        component_table: dict[str, Any] = {}
        component_table_warning = ""
        if Path(input_path).suffix.lower() == ".pdf":
            try:
                title_block = extract_title_block(input_path).to_dict()
            except Exception as exc:
                title_block_warning = f"图签信息提取失败：{exc}"
            _emit(progress, "title_block", title_block)
            try:
                control_signal_configuration = (
                    extract_control_signal_configuration(
                        input_path
                    ).to_dict()
                )
            except Exception as exc:
                control_signal_warning = (
                    f"控制与信号配置提取失败：{exc}"
                )
            _emit(
                progress,
                "control_signal_configuration",
                control_signal_configuration,
            )
            try:
                component_table = extract_component_table(
                    input_path
                ).to_dict()
            except Exception as exc:
                component_table_warning = f"图纸表格提取失败：{exc}"
            _emit(progress, "component_table", component_table)
        try:
            page_layouts = self.layout_router.route(
                document,
                input_path,
                title_block=title_block,
                component_table=component_table,
            )
            layout_warning = ""
        except Exception as exc:
            page_layouts = []
            layout_warning = f"Layout routing failed; using grid fallback: {exc}"
        page_quality_steps = [layout.quality for layout in page_layouts]
        layout_region_steps = [
            layout.to_dict() for layout in page_layouts
        ]
        structured_region_steps = [
            region.to_dict()
            for layout in page_layouts
            for region in layout.regions
            if region.route == "structured"
        ]
        _emit(progress, "page_quality", page_quality_steps)
        _emit(progress, "layout_regions", layout_region_steps)
        _emit(
            progress,
            "structured_region_extraction",
            structured_region_steps,
        )
        catalog_components = [
            sample
            for sample in self.knowledge_base.components
            if sample.enabled
        ]
        recognition = self._recognize_components(
            document,
            directory,
            catalog_components,
            progress,
            page_layouts,
        )
        recognition["steps"]["page_quality"] = page_quality_steps
        recognition["steps"]["layout_regions"] = layout_region_steps
        recognition["steps"][
            "structured_region_extraction"
        ] = structured_region_steps
        components = recognition["components"]
        combinations = detect_combinations(
            components,
            open_symbols=recognition["steps"].get("open_symbols", []),
            component_table=component_table,
            title_block=title_block,
            control_signal_configuration=control_signal_configuration,
            custom_rules=self.custom_rule_base,
        )
        references = recognition["references"]
        reference_images = recognition["reference_images"]
        reference_batches = recognition["reference_batches"]
        candidate_ids = recognition["candidate_ids"]
        page_view_counts = recognition["page_view_counts"]
        recognition_warnings = recognition["warnings"]
        warnings = recognition_warnings
        if title_block_warning:
            warnings.append(title_block_warning)
        if control_signal_warning:
            warnings.append(control_signal_warning)
        if component_table_warning:
            warnings.append(component_table_warning)
        if layout_warning:
            warnings.append(layout_warning)
        warnings = list(dict.fromkeys(warnings))
        layout_summary = summarize_layouts(page_layouts)
        meta = {
            "elapsed_seconds": round(
                time.perf_counter() - started, 2
            ),
            "model": self.settings.model,
            "model_requests": self.model.model_requests,
            "cache_hits": self.model.cache_hits,
            "page_count": len(document.pages),
            "knowledge_components": len(
                self.knowledge_base.components
            ),
            "custom_rules": len(self.custom_rule_base.rules),
            "catalog_components_presented": len(catalog_components),
            "local_catalog_recall_enabled": False,
            "recognition_mode": self.settings.recognition_mode,
            "recognition_strategy": recognition["strategy"],
            "layout_routing_enabled": (
                self.settings.layout_routing_enabled
            ),
            "layout_router_mode": self.settings.layout_router_mode,
            "layout_fallback_to_grid": (
                self.settings.layout_fallback_to_grid
            ),
            **layout_summary,
            "avoided_component_model_requests": max(
                0,
                recognition.get("legacy_page_view_count", 0)
                - recognition.get("routed_component_view_count", 0),
            ),
            "open_symbol_count": recognition["open_symbol_count"],
            "open_category_count": recognition.get(
                "open_category_count", 0
            ),
            "open_instance_count": recognition.get(
                "open_instance_count", 0
            ),
            "rag_correction_count": recognition["rag_correction_count"],
            "rag_corrected_instance_count": recognition.get(
                "rag_corrected_instance_count", 0
            ),
            "candidate_ids": candidate_ids,
            "reference_ids": [
                sample.id for sample in references
            ],
            "reference_panels": len(reference_images),
            "reference_batch_size": (
                self.settings.reference_batch_size
            ),
            "reference_batch_count": len(reference_batches),
            "page_view_counts": page_view_counts,
            "tile_grid": self.settings.tile_grid,
            "tile_overlap": self.settings.tile_overlap,
            "open_recognition_concurrency": (
                self.settings.open_recognition_concurrency
            ),
            "correction_batch_size": (
                self.settings.correction_batch_size
            ),
            "correction_candidate_limit": (
                self.settings.correction_candidate_limit
            ),
            "open_view_success_count": recognition.get(
                "open_view_success_count", 0
            ),
            "open_view_failure_count": recognition.get(
                "open_view_failure_count", 0
            ),
            "combination_count": len(combinations),
            "combination_rule_counts": {
                rule_id: sum(
                    1
                    for item in combinations
                    if item.get("rule_id") == rule_id
                )
                for rule_id in {
                    str(item.get("rule_id", ""))
                    for item in combinations
                }
                if rule_id
            },
        }
        _emit(progress, "detected_components", components)
        _emit(progress, "detected_combinations", combinations)
        _emit(progress, "warnings", warnings)
        _emit(progress, "meta", meta)
        result = RecognitionResult(
            document=document.filename,
            detected_components=components,
            detected_combinations=combinations,
            title_block=title_block,
            control_signal_configuration=(
                control_signal_configuration
            ),
            component_table=component_table,
            page_layouts=layout_region_steps,
            recognition_steps=recognition["steps"],
            warnings=warnings,
            meta=meta,
        )
        return result, directory / "pages"

    def _recognize_components(
        self,
        document: Any,
        directory: Path,
        catalog_components: list[ComponentSample],
        progress: Callable[[str, object], None] | None = None,
        page_layouts: list[PageLayout] | None = None,
    ) -> dict[str, Any]:
        mode = self.settings.recognition_mode
        if mode in {"hybrid", "vision_first"}:
            recognition = self._analyze_vision_first(
                document,
                directory,
                progress,
                page_layouts,
            )
            if recognition["components"] or mode == "vision_first":
                recognition["strategy"] = "vision_first"
                return recognition
        recognition = self._analyze_rag_first(
            document,
            directory,
            catalog_components,
            progress,
            page_layouts,
        )
        recognition["strategy"] = (
            "rag_first_fallback" if mode == "hybrid" else "rag_first"
        )
        return recognition

    def _analyze_rag_first(
        self,
        document: Any,
        directory: Path,
        catalog_components: list[ComponentSample],
        progress: Callable[[str, object], None] | None = None,
        page_layouts: list[PageLayout] | None = None,
    ) -> dict[str, Any]:
        _emit(progress, "open_symbols", [])
        _emit(progress, "rag_corrections", [])
        drawing_images = [
            Path(page.image_path) for page in document.pages
        ]
        shortlist = self.model.complete_json(
            SYSTEM_PROMPT,
            catalog_prompt(
                document.text,
                self.knowledge_base.catalog(catalog_components),
                self.settings.catalog_candidate_limit,
            ),
            drawing_images,
        )
        candidate_ids = _valid_reference_ids(
            shortlist.get("candidate_ids", []),
            self.knowledge_base,
        )
        if not candidate_ids:
            raise RuntimeError(
                "候选选择模型未从知识库目录中返回有效候选元件。"
            )
        references = [
            self.knowledge_base.by_id[item]
            for item in candidate_ids
            if self.knowledge_base.by_id[item].enabled
        ]
        if not references:
            raise RuntimeError("组件知识库中没有可用参考图片。")
        reference_images = _build_reference_panels(
            self.knowledge_base,
            references,
            directory / "reference-panels",
        )
        raw_components: list[object] = []
        warnings: list[str] = []
        page_view_counts: list[int] = []
        legacy_page_view_count = 0
        routed_component_view_count = 0
        reference_batches = list(
            _batches(references, self.settings.reference_batch_size)
        )
        layouts_by_page = _layouts_by_page(page_layouts)
        for page in document.pages:
            legacy_views = _build_page_views(
                Path(page.image_path),
                directory / "page-tiles",
                page.number,
                self.settings.tile_grid,
                self.settings.tile_overlap,
            )
            legacy_page_view_count += len(legacy_views)
            page_views = _build_routed_page_views(
                Path(page.image_path),
                directory / "page-tiles",
                page.number,
                self.settings,
                layouts_by_page.get(page.number),
                legacy_views,
            )
            page_view_counts.append(len(page_views))
            routed_component_view_count += len(
                [view for view in page_views if _is_component_view(view)]
            )
            view_metadata = _view_metadata(page_views)
            page_images = [
                Path(str(view["path"])) for view in page_views
            ]
            reference_offset = 0
            for reference_batch in reference_batches:
                batch_size = len(reference_batch)
                batch_images = reference_images[
                    reference_offset : reference_offset + batch_size
                ]
                reference_offset += batch_size
                response = self.model.complete_json(
                    SYSTEM_PROMPT,
                    recognition_prompt(
                        page.text,
                        reference_batch,
                        view_metadata,
                        page.number,
                    ),
                    page_images + batch_images,
                )
                raw_components.extend(
                    _remap_component_regions(
                        response.get("detected_components", []),
                        page_views,
                        page.number,
                    )
                )
                warnings.extend(_warnings(response))
        components = normalize_components(
            raw_components,
            references,
            len(document.pages),
        )
        return {
            "components": components,
            "references": references,
            "reference_images": reference_images,
            "reference_batches": reference_batches,
            "candidate_ids": candidate_ids,
            "page_view_counts": page_view_counts,
            "warnings": warnings,
            "steps": {
                "open_symbols": [],
                "open_recognition_tiles": [],
                "open_categories": [],
                "rag_corrections": [],
            },
            "open_symbol_count": 0,
            "open_category_count": 0,
            "open_instance_count": 0,
            "rag_correction_count": 0,
            "rag_corrected_instance_count": 0,
            "legacy_page_view_count": legacy_page_view_count,
            "routed_component_view_count": routed_component_view_count,
            "strategy": "rag_first",
        }

    def _analyze_vision_first(
        self,
        document: Any,
        directory: Path,
        progress: Callable[[str, object], None] | None = None,
        page_layouts: list[PageLayout] | None = None,
    ) -> dict[str, Any]:
        raw_symbols: list[dict[str, Any]] = []
        warnings: list[str] = []
        page_view_counts: list[int] = []
        tile_statuses: list[dict[str, Any]] = []
        successful_views = 0
        failed_views = 0
        legacy_page_view_count = 0
        routed_component_view_count = 0
        layouts_by_page = _layouts_by_page(page_layouts)
        _emit(progress, "open_symbols", raw_symbols)
        _emit(progress, "open_recognition_tiles", tile_statuses)
        for page in document.pages:
            legacy_views = _build_page_views(
                Path(page.image_path),
                directory / "page-tiles",
                page.number,
                self.settings.tile_grid,
                self.settings.tile_overlap,
            )
            legacy_page_view_count += len(legacy_views)
            page_views = _build_routed_page_views(
                Path(page.image_path),
                directory / "page-tiles",
                page.number,
                self.settings,
                layouts_by_page.get(page.number),
                legacy_views,
            )
            page_view_counts.append(len(page_views))
            recognition_views = [
                view
                for view in page_views
                if _is_component_view(view)
            ] or page_views
            routed_component_view_count += len(recognition_views)
            workers = min(
                len(recognition_views),
                self.settings.open_recognition_concurrency,
            )
            results: dict[
                int, tuple[dict[str, Any] | None, float, Exception | None]
            ] = {}
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures: dict[Any, int] = {}
                future_started: dict[Any, float] = {}
                for index, view in enumerate(recognition_views):
                    future = executor.submit(
                        self._recognize_open_view,
                        page.text,
                        page.number,
                        view,
                    )
                    futures[future] = index
                    future_started[future] = time.perf_counter()
                for future in as_completed(futures):
                    index = futures[future]
                    try:
                        response, elapsed = future.result()
                        results[index] = (response, elapsed, None)
                    except Exception as exc:
                        results[index] = (
                            None,
                            time.perf_counter()
                            - future_started[future],
                            exc,
                        )
            for index, view in enumerate(recognition_views):
                response, elapsed, error = results[index]
                tile_name = str(view["tile"])
                if error is not None:
                    failed_views += 1
                    message = (
                        f"第 {page.number} 页切片 {tile_name} "
                        f"开放识别失败：{error}"
                    )
                    warnings.append(message)
                    tile_statuses.append(
                        {
                            "page": page.number,
                            "tile": tile_name,
                            "status": "failed",
                            "elapsed_seconds": round(elapsed, 2),
                            "error": str(error),
                        }
                    )
                    _emit(
                        progress,
                        "open_recognition_tiles",
                        tile_statuses,
                    )
                    continue
                assert response is not None
                successful_views += 1
                remapped = _remap_component_regions(
                    response.get("detected_symbols", []),
                    [view],
                    page.number,
                )
                raw_symbols.extend(remapped)
                raw_symbols = _deduplicate_open_symbols(raw_symbols)
                status = "truncated" if response.get("truncated") else "complete"
                tile_statuses.append(
                    {
                        "page": page.number,
                        "tile": tile_name,
                        "status": status,
                        "elapsed_seconds": round(elapsed, 2),
                        "symbol_count": len(remapped),
                    }
                )
                if response.get("truncated"):
                    warnings.append(
                        f"第 {page.number} 页切片 {tile_name} "
                        "返回结果达到单次上限，可能存在漏识别。"
                    )
                warnings.extend(_warnings(response))
                _emit(progress, "open_symbols", raw_symbols)
                _emit(
                    progress,
                    "open_recognition_tiles",
                    tile_statuses,
                )
        corrected: list[dict[str, Any]] = []
        rag_corrections: list[dict[str, Any]] = []
        open_categories = _group_open_symbols(raw_symbols)
        category_summaries = [
            category["summary"] for category in open_categories
        ]
        _emit(progress, "open_categories", category_summaries)
        _emit(progress, "rag_corrections", rag_corrections)
        references_by_id: dict[str, ComponentSample] = {}
        corrections = 0
        corrected_instances = 0
        candidate_sets = [
            self._candidates_for_symbol(summary)
            for summary in category_summaries
        ]
        batch_size = self.settings.correction_batch_size
        for offset in range(0, len(open_categories), batch_size):
            categories = open_categories[offset : offset + batch_size]
            summaries = [
                category["summary"] for category in categories
            ]
            candidates_batch = candidate_sets[
                offset : offset + batch_size
            ]
            try:
                correction_batch = self._correct_symbols(
                    summaries,
                    candidates_batch,
                )
            except Exception as exc:
                warnings.append(
                    "RAG 批量修正失败，已保留开放识别结果："
                    f"{exc}"
                )
                correction_batch = [{} for _ in summaries]
            for category, candidates, correction in zip(
                categories,
                candidates_batch,
                correction_batch,
            ):
                summary = category["summary"]
                members = category["members"]
                reference_id = str(
                    correction.get("reference_id", "")
                ).strip()
                sample = self.knowledge_base.by_id.get(reference_id)
                if sample is not None:
                    references_by_id[sample.id] = sample
                    corrections += 1
                    corrected_instances += int(
                        summary["occurrence_count"]
                    )
                components = [
                    _symbol_to_component(
                        symbol, correction, sample
                    )
                    for symbol in members
                ]
                corrected.extend(components)
                rag_corrections.append(
                    {
                        "symbol": summary,
                        "open_category": summary,
                        "candidates": [
                            _sample_summary(candidate)
                            for candidate in candidates
                        ],
                        "correction": correction,
                        "component": components[0] if components else {},
                        "components": components,
                    }
                )
            _emit(progress, "rag_corrections", rag_corrections)
        references = list(references_by_id.values())
        reference_images = (
            _build_reference_panels(
                self.knowledge_base,
                references,
                directory / "reference-panels",
            )
            if references
            else []
        )
        components = normalize_components(
            corrected,
            references,
            len(document.pages),
        )
        candidate_ids = [sample.id for sample in references]
        return {
            "components": components,
            "references": references,
            "reference_images": reference_images,
            "reference_batches": list(
                _batches(references, self.settings.reference_batch_size)
            ),
            "candidate_ids": candidate_ids,
            "page_view_counts": page_view_counts,
            "warnings": warnings,
            "steps": {
                "open_symbols": raw_symbols,
                "open_recognition_tiles": tile_statuses,
                "open_categories": category_summaries,
                "rag_corrections": rag_corrections,
            },
            "open_symbol_count": len(raw_symbols),
            "open_category_count": len(open_categories),
            "open_instance_count": sum(
                int(summary["occurrence_count"])
                for summary in category_summaries
            ),
            "rag_correction_count": corrections,
            "rag_corrected_instance_count": corrected_instances,
            "open_view_success_count": successful_views,
            "open_view_failure_count": failed_views,
            "legacy_page_view_count": legacy_page_view_count,
            "routed_component_view_count": routed_component_view_count,
            "strategy": "vision_first",
        }

    def _recognize_open_view(
        self,
        page_text: str,
        page_number: int,
        view: dict[str, object],
    ) -> tuple[dict[str, Any], float]:
        started = time.perf_counter()
        response = self.model.complete_json(
            SYSTEM_PROMPT,
            open_recognition_prompt(
                page_text,
                _view_metadata([view]),
                page_number,
            ),
            [Path(str(view["path"]))],
        )
        return response, time.perf_counter() - started

    def _candidates_for_symbol(
        self,
        symbol: dict[str, Any],
    ) -> list[ComponentSample]:
        query = " ".join(
            str(symbol.get(key, ""))
            for key in (
                "raw_label",
                "label",
                "component_type",
                "code",
                "evidence",
            )
        )
        preferred_ids = _preferred_ids_for_code(
            str(symbol.get("code", "")),
            self.knowledge_base.components,
        )
        return self.knowledge_base.search(
            query,
            self.settings.correction_candidate_limit,
            preferred_ids=preferred_ids,
        )

    def _correct_symbols(
        self,
        symbols: list[dict[str, Any]],
        candidate_sets: list[list[ComponentSample]],
    ) -> list[dict[str, Any]]:
        if not symbols:
            return []
        items = list(zip(symbols, candidate_sets))
        if not any(candidate_sets):
            return [{} for _ in symbols]
        response = self.model.complete_json(
            SYSTEM_PROMPT,
            batch_correction_prompt(items),
            [],
        )
        raw_corrections = response.get("corrections")
        if not isinstance(raw_corrections, list):
            if len(symbols) == 1:
                raw_corrections = [response]
            else:
                return [{} for _ in symbols]
        by_index: dict[int, dict[str, Any]] = {}
        for fallback_index, raw in enumerate(raw_corrections):
            if not isinstance(raw, dict):
                continue
            index = _bounded_int(
                raw.get("index"),
                0,
                len(symbols) - 1,
                fallback_index,
            )
            correction = dict(raw)
            valid_ids = {
                sample.id for sample in candidate_sets[index]
            }
            reference_id = str(
                correction.get("reference_id", "")
            ).strip()
            if (
                reference_id not in valid_ids
                or _confidence(correction.get("confidence")) < 0.45
            ):
                correction["reference_id"] = ""
            by_index[index] = correction
        return [
            by_index.get(index, {})
            for index in range(len(symbols))
        ]


def normalize_components(
    raw_components: object,
    references: list[ComponentSample],
    page_count: int,
) -> list[dict[str, Any]]:
    reference_by_id = {sample.id: sample for sample in references}
    merged: dict[tuple[str, str, int], dict[str, Any]] = {}
    if not isinstance(raw_components, list):
        return []
    for raw in raw_components:
        if not isinstance(raw, dict):
            continue
        reference_id = str(raw.get("reference_id", "")).strip()
        sample = reference_by_id.get(reference_id)
        label = str(
            raw.get("label") or (sample.label if sample else "")
        ).strip()
        if not label:
            continue
        code = str(raw.get("code", "")).strip()
        page = _bounded_int(raw.get("page"), 1, page_count, 1)
        regions = _normalize_regions(raw.get("regions"))
        count = max(
            _bounded_int(
                raw.get("occurrence_count"), 1, 10000, 1
            ),
            len(regions),
        )
        key = (
            reference_id.casefold(),
            label.casefold(),
            page,
        )
        item = merged.setdefault(
            key,
            {
                "reference_id": reference_id,
                "label": label,
                "code": code,
                "component_type": str(
                    raw.get("component_type")
                    or (sample.component_type if sample else "")
                ).strip(),
                "page": page,
                "occurrence_count": count,
                "confidence": _confidence(raw.get("confidence")),
                "regions": [],
                "region_id": str(raw.get("region_id", "")).strip(),
                "region_type": str(raw.get("region_type", "")).strip(),
                "evidence": str(raw.get("evidence", "")).strip(),
            },
        )
        item["occurrence_count"] = max(
            int(item["occurrence_count"]), count
        )
        item["confidence"] = max(
            float(item["confidence"]), _confidence(raw.get("confidence"))
        )
        item["code"] = _merge_codes(str(item["code"]), code)
        if not str(item.get("region_id", "")).strip():
            item["region_id"] = str(raw.get("region_id", "")).strip()
        if not str(item.get("region_type", "")).strip():
            item["region_type"] = str(raw.get("region_type", "")).strip()
        existing = {tuple(region) for region in item["regions"]}
        for region in regions:
            if tuple(region) not in existing:
                item["regions"].append(region)
                existing.add(tuple(region))
    for item in merged.values():
        item["regions"] = _deduplicate_regions(item["regions"])
        if item["regions"]:
            item["occurrence_count"] = len(item["regions"])
    return sorted(
        merged.values(),
        key=lambda item: (
            int(item["page"]),
            str(item["label"]),
            str(item["code"]),
        ),
    )


def _emit(
    progress: Callable[[str, object], None] | None,
    name: str,
    payload: object,
) -> None:
    if progress is not None:
        progress(name, payload)


def _valid_reference_ids(
    values: object,
    knowledge_base: ComponentKnowledgeBase,
) -> list[str]:
    if not isinstance(values, list):
        return []
    return list(
        dict.fromkeys(
            str(item)
            for item in values
            if str(item) in knowledge_base.by_id
        )
    )


def _view_metadata(
    page_views: list[dict[str, object]],
) -> list[dict[str, object]]:
    return [
        {
            "input_image_index": index + 1,
            "kind": view["kind"],
            "tile": view["tile"],
            "bounds_in_page": view["bounds"],
            "region_id": view.get("region_id", ""),
            "region_type": view.get("region_type", ""),
        }
        for index, view in enumerate(page_views)
    ]


def _warnings(response: dict[str, Any]) -> list[str]:
    return [
        str(item)
        for item in response.get("warnings", [])
        if str(item).strip()
    ]


def _preferred_ids_for_code(
    code: str,
    components: list[ComponentSample],
) -> list[str]:
    tokens = [
        item.casefold()
        for item in code.replace("，", ",").split(",")
        if item.strip()
    ]
    if not tokens:
        return []
    preferred: list[str] = []
    for sample in components:
        searchable = " ".join(
            [
                sample.id,
                sample.label,
                sample.component_type,
                sample.model,
                *sample.aliases,
            ]
        ).casefold()
        if any(token in searchable or searchable in token for token in tokens):
            preferred.append(sample.id)
    return preferred


def _symbol_to_component(
    symbol: dict[str, Any],
    correction: dict[str, Any],
    sample: ComponentSample | None,
) -> dict[str, Any]:
    label = str(
        correction.get("label")
        or symbol.get("label")
        or symbol.get("raw_label")
        or (sample.label if sample else "")
    ).strip()
    return {
        "reference_id": str(
            correction.get("reference_id")
            or (sample.id if sample else "")
        ).strip(),
        "label": label,
        "code": str(symbol.get("code", "")).strip(),
        "component_type": str(
            correction.get("component_type")
            or symbol.get("component_type")
            or (sample.component_type if sample else "")
        ).strip(),
        "page": symbol.get("page"),
        "occurrence_count": symbol.get("occurrence_count"),
        "confidence": max(
            _confidence(symbol.get("confidence")),
            _confidence(correction.get("confidence")),
        ),
        "regions": symbol.get("regions"),
        "evidence": str(symbol.get("evidence", "")).strip(),
        "raw_label": str(symbol.get("raw_label", "")).strip(),
        "correction_reason": str(correction.get("reason", "")).strip(),
    }


def _sample_summary(sample: ComponentSample) -> dict[str, object]:
    return {
        "id": sample.id,
        "label": sample.label,
        "component_type": sample.component_type,
        "model": sample.model,
        "aliases": sample.aliases,
        "standards": sample.standards,
    }


def _group_open_symbols(
    symbols: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for index, symbol in enumerate(symbols):
        raw_label = str(
            symbol.get("raw_label")
            or symbol.get("label")
            or "未知元件"
        ).strip()
        component_type = str(
            symbol.get("component_type", "")
        ).strip()
        normalized_label = _normalize_category_text(raw_label)
        normalized_type = _normalize_category_text(component_type)
        if normalized_label in {"", "未知元件", "未知", "unknown"}:
            key = (
                f"{normalized_label or '未知元件'}#{index}",
                normalized_type,
            )
        else:
            key = (normalized_label, normalized_type)
        category = grouped.setdefault(
            key,
            {
                "raw_label": raw_label,
                "component_type": component_type,
                "members": [],
                "codes": "",
                "evidence": [],
                "pages": set(),
                "occurrence_count": 0,
                "confidence": 0.0,
            },
        )
        category["members"].append(symbol)
        category["codes"] = _merge_codes(
            str(category["codes"]),
            str(symbol.get("code", "")),
        )
        evidence = str(symbol.get("evidence", "")).strip()
        if evidence and evidence not in category["evidence"]:
            category["evidence"].append(evidence)
        category["pages"].add(
            _bounded_int(symbol.get("page"), 1, 10000, 1)
        )
        regions = _normalize_regions(symbol.get("regions"))
        category["occurrence_count"] += max(
            _bounded_int(
                symbol.get("occurrence_count"),
                1,
                10000,
                1,
            ),
            len(regions),
        )
        category["confidence"] = max(
            float(category["confidence"]),
            _confidence(symbol.get("confidence")),
        )
    results: list[dict[str, Any]] = []
    for category_index, category in enumerate(grouped.values(), start=1):
        codes = str(category["codes"])
        summary = {
            "category_id": f"open-category-{category_index}",
            "expression": (
                f"[{codes or '-'}]:"
                f"[{category['raw_label']}]:"
                f"[{category['occurrence_count']}]"
            ),
            "raw_label": category["raw_label"],
            "component_type": category["component_type"],
            "code": codes,
            "codes": [
                value.strip()
                for value in codes.split(",")
                if value.strip()
            ],
            "pages": sorted(category["pages"]),
            "occurrence_count": category["occurrence_count"],
            "confidence": category["confidence"],
            "evidence": "；".join(category["evidence"][:8]),
        }
        results.append(
            {
                "summary": summary,
                "members": category["members"],
            }
        )
    return results


def _normalize_category_text(value: str) -> str:
    return "".join(value.casefold().split())


def _deduplicate_open_symbols(
    symbols: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for symbol in symbols:
        item = dict(symbol)
        item["regions"] = _normalize_regions(item.get("regions"))
        duplicate: dict[str, Any] | None = None
        for existing in kept:
            if int(existing.get("page", 0)) != int(item.get("page", 0)):
                continue
            if not _same_symbol_identity(existing, item):
                continue
            existing_regions = _normalize_regions(
                existing.get("regions")
            )
            item_regions = _normalize_regions(item.get("regions"))
            if not any(
                _same_instance(left, right)
                for left in existing_regions
                for right in item_regions
            ):
                continue
            duplicate = existing
            break
        if duplicate is None:
            kept.append(item)
            continue
        merged_regions = _deduplicate_regions(
            _normalize_regions(duplicate.get("regions"))
            + _normalize_regions(item.get("regions"))
        )
        duplicate["regions"] = merged_regions
        duplicate["occurrence_count"] = max(1, len(merged_regions))
        duplicate["confidence"] = max(
            _confidence(duplicate.get("confidence")),
            _confidence(item.get("confidence")),
        )
        duplicate["code"] = _merge_codes(
            str(duplicate.get("code", "")),
            str(item.get("code", "")),
        )
        if not str(duplicate.get("evidence", "")).strip():
            duplicate["evidence"] = item.get("evidence", "")
    return kept


def _same_symbol_identity(
    left: dict[str, Any],
    right: dict[str, Any],
) -> bool:
    left_codes = {
        value.strip().casefold()
        for value in str(left.get("code", "")).replace("，", ",").split(",")
        if value.strip()
    }
    right_codes = {
        value.strip().casefold()
        for value in str(right.get("code", "")).replace("，", ",").split(",")
        if value.strip()
    }
    if left_codes and right_codes and left_codes & right_codes:
        return True
    left_label = str(
        left.get("raw_label") or left.get("label") or ""
    ).strip().casefold()
    right_label = str(
        right.get("raw_label") or right.get("label") or ""
    ).strip().casefold()
    if left_label and right_label and left_label == right_label:
        return True
    left_type = str(left.get("component_type", "")).strip().casefold()
    right_type = str(right.get("component_type", "")).strip().casefold()
    return bool(left_type and left_type == right_type)


def _normalize_regions(value: object) -> list[list[float]]:
    if not isinstance(value, list):
        return []
    candidates = (
        [value]
        if len(value) == 4
        and all(isinstance(item, (int, float, str)) for item in value)
        else value
    )
    regions: list[list[float]] = []
    for region in candidates:
        if not isinstance(region, (list, tuple)) or len(region) != 4:
            continue
        try:
            values = [
                max(0.0, min(1000.0, float(item))) for item in region
            ]
        except (TypeError, ValueError):
            continue
        if values[2] > values[0] and values[3] > values[1]:
            regions.append(values)
    return regions


def _bounded_int(
    value: object, minimum: int, maximum: int, default: int
) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _confidence(value: object) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _batches(
    values: list[ComponentSample],
    batch_size: int,
) -> list[list[ComponentSample]]:
    size = max(1, batch_size)
    return [
        values[index : index + size]
        for index in range(0, len(values), size)
    ]


def _build_reference_panels(
    knowledge_base: ComponentKnowledgeBase,
    references: list[ComponentSample],
    output_dir: Path,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    panels: list[Path] = []
    for sample in references:
        source_paths = knowledge_base.image_paths(sample)
        if not source_paths or not source_paths[0].is_file():
            raise FileNotFoundError(
                source_paths[0] if source_paths else sample.image_path
            )
        images: list[tuple[str, Image.Image]] = []
        with Image.open(source_paths[0]) as source:
            primary = _as_rgb(source)
            for angle in (0, 90, 180, 270):
                rotated = primary.rotate(
                    angle,
                    expand=True,
                    fillcolor="white",
                )
                images.append((f"{angle} deg", _trim_white(rotated)))
        for index, path in enumerate(source_paths[1:], start=1):
            if not path.is_file():
                continue
            with Image.open(path) as source:
                variant = _as_rgb(source)
                images.append(
                    (f"sample-{index}", _trim_white(variant))
                )
        panel = _make_contact_sheet(images)
        target = output_dir / f"{sample.id}.png"
        panel.save(target)
        panels.append(target)
    return panels


def _make_contact_sheet(
    images: list[tuple[str, Image.Image]],
    cell_size: int = 420,
) -> Image.Image:
    columns = 2
    rows = math.ceil(len(images) / columns)
    label_height = 34
    panel = Image.new(
        "RGB",
        (columns * cell_size, rows * (cell_size + label_height)),
        "white",
    )
    draw = ImageDraw.Draw(panel)
    for index, (label, source) in enumerate(images):
        row, column = divmod(index, columns)
        image = source.copy()
        image.thumbnail(
            (cell_size - 32, cell_size - 32),
            Image.Resampling.LANCZOS,
        )
        left = column * cell_size + (cell_size - image.width) // 2
        top = row * (cell_size + label_height) + (
            cell_size - image.height
        ) // 2
        panel.paste(image, (left, top))
        draw.text(
            (column * cell_size + 12, top + image.height + 4),
            label,
            fill="black",
        )
    return panel


def _trim_white(image: Image.Image, padding: int = 12) -> Image.Image:
    grayscale = ImageOps.grayscale(image)
    foreground = ImageOps.invert(grayscale).point(
        lambda value: 255 if value > 18 else 0
    )
    bounds = foreground.getbbox()
    if not bounds:
        return image.copy()
    left = max(0, bounds[0] - padding)
    top = max(0, bounds[1] - padding)
    right = min(image.width, bounds[2] + padding)
    bottom = min(image.height, bounds[3] + padding)
    return image.crop((left, top, right, bottom))


def _as_rgb(source: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(source)
    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, "white")
        return Image.alpha_composite(background, rgba).convert("RGB")
    return image.convert("RGB")


def _layouts_by_page(
    layouts: list[PageLayout] | None,
) -> dict[int, PageLayout]:
    return {layout.page: layout for layout in layouts or []}


def _is_component_view(view: dict[str, object]) -> bool:
    if view.get("route") == "component":
        return True
    return view.get("kind") == "tile"


def _build_routed_page_views(
    page_path: Path,
    output_dir: Path,
    page_number: int,
    settings: Settings,
    layout: PageLayout | None,
    fallback_views: list[dict[str, object]],
) -> list[dict[str, object]]:
    if (
        not settings.layout_routing_enabled
        or settings.layout_router_mode == "disabled"
        or layout is None
        or layout.fallback_required
    ):
        return fallback_views
    component_regions = [
        region
        for region in layout.regions
        if region.route == "component"
        and region.confidence >= settings.layout_min_confidence
    ]
    if not component_regions:
        return fallback_views if settings.layout_fallback_to_grid else []
    region_dir = output_dir / "layout-regions"
    views: list[dict[str, object]] = [
        {
            "path": page_path,
            "kind": "full_page",
            "tile": "full",
            "bounds": [0.0, 0.0, 1000.0, 1000.0],
            "route": "context",
        }
    ]
    for index, region in enumerate(component_regions, start=1):
        if _region_area(region.bounds) / 1_000_000.0 > settings.region_max_area_ratio:
            nested = _build_region_tiles(
                page_path,
                region_dir,
                region,
                page_number,
                index,
                settings.tile_grid,
                settings.region_tile_overlap,
            )
            views.extend(nested)
            continue
        crop_path = crop_region_image(page_path, region_dir, region)
        views.append(
            {
                "path": crop_path,
                "kind": "layout_region",
                "tile": region.id,
                "bounds": region.bounds,
                "route": region.route,
                "region_id": region.id,
                "region_type": region.region_type,
                "confidence": region.confidence,
            }
        )
    return views


def _build_region_tiles(
    page_path: Path,
    output_dir: Path,
    region: Any,
    page_number: int,
    region_index: int,
    grid: int,
    overlap: float,
) -> list[dict[str, object]]:
    crop_path = crop_region_image(page_path, output_dir, region)
    local_views = _build_page_views(
        crop_path,
        output_dir / f"{region.id}-tiles",
        page_number,
        max(1, grid),
        overlap,
    )
    tiled = [view for view in local_views if view["kind"] == "tile"]
    results: list[dict[str, object]] = []
    for index, view in enumerate(tiled, start=1):
        local_bounds = view["bounds"]
        assert isinstance(local_bounds, list)
        bounds = [
            round(
                float(region.bounds[0])
                + float(local_bounds[0])
                / 1000
                * (float(region.bounds[2]) - float(region.bounds[0])),
                4,
            ),
            round(
                float(region.bounds[1])
                + float(local_bounds[1])
                / 1000
                * (float(region.bounds[3]) - float(region.bounds[1])),
                4,
            ),
            round(
                float(region.bounds[0])
                + float(local_bounds[2])
                / 1000
                * (float(region.bounds[2]) - float(region.bounds[0])),
                4,
            ),
            round(
                float(region.bounds[1])
                + float(local_bounds[3])
                / 1000
                * (float(region.bounds[3]) - float(region.bounds[1])),
                4,
            ),
        ]
        results.append(
            {
                "path": view["path"],
                "kind": "layout_region_tile",
                "tile": f"{region.id}-{region_index}-{index}",
                "bounds": bounds,
                "route": "component",
                "region_id": region.id,
                "region_type": region.region_type,
                "confidence": region.confidence,
            }
        )
    return results or [
        {
            "path": crop_path,
            "kind": "layout_region",
            "tile": region.id,
            "bounds": region.bounds,
            "route": "component",
            "region_id": region.id,
            "region_type": region.region_type,
            "confidence": region.confidence,
        }
    ]


def _build_page_views(
    page_path: Path,
    output_dir: Path,
    page_number: int,
    grid: int,
    overlap: float,
) -> list[dict[str, object]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    views: list[dict[str, object]] = [
        {
            "path": page_path,
            "kind": "full_page",
            "tile": "full",
            "bounds": [0.0, 0.0, 1000.0, 1000.0],
        }
    ]
    if grid <= 1:
        return views
    with Image.open(page_path) as source:
        image = _as_rgb(source)
        x_ranges = _tile_ranges(image.width, grid, overlap)
        y_ranges = _tile_ranges(image.height, grid, overlap)
        for row, (top, bottom) in enumerate(y_ranges):
            for column, (left, right) in enumerate(x_ranges):
                target = (
                    output_dir
                    / f"page-{page_number}-tile-{row + 1}-{column + 1}.png"
                )
                image.crop((left, top, right, bottom)).save(target)
                views.append(
                    {
                        "path": target,
                        "kind": "tile",
                        "tile": f"{row + 1}-{column + 1}",
                        "bounds": [
                            round(left / image.width * 1000, 4),
                            round(top / image.height * 1000, 4),
                            round(right / image.width * 1000, 4),
                            round(bottom / image.height * 1000, 4),
                        ],
                    }
                )
    return views


def _tile_ranges(
    length: int,
    grid: int,
    overlap: float,
) -> list[tuple[int, int]]:
    tile_length = min(
        length,
        math.ceil(length / (grid - overlap * (grid - 1))),
    )
    if grid == 1:
        return [(0, length)]
    maximum_start = max(0, length - tile_length)
    starts = [
        round(index * maximum_start / (grid - 1))
        for index in range(grid)
    ]
    return [
        (start, min(length, start + tile_length))
        for start in starts
    ]


def _remap_component_regions(
    raw_components: object,
    page_views: list[dict[str, object]],
    page_number: int,
) -> list[dict[str, Any]]:
    if not isinstance(raw_components, list):
        return []
    remapped: list[dict[str, Any]] = []
    for raw in raw_components:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        source_index = _bounded_int(
            item.get("source_image_index"),
            1,
            len(page_views),
            1,
        )
        bounds = page_views[source_index - 1]["bounds"]
        assert isinstance(bounds, list)
        local_regions = _normalize_regions(item.get("regions"))
        item["regions"] = [
            [
                round(
                    float(bounds[0])
                    + region[0]
                    / 1000
                    * (float(bounds[2]) - float(bounds[0])),
                    4,
                ),
                round(
                    float(bounds[1])
                    + region[1]
                    / 1000
                    * (float(bounds[3]) - float(bounds[1])),
                    4,
                ),
                round(
                    float(bounds[0])
                    + region[2]
                    / 1000
                    * (float(bounds[2]) - float(bounds[0])),
                    4,
                ),
                round(
                    float(bounds[1])
                    + region[3]
                    / 1000
                    * (float(bounds[3]) - float(bounds[1])),
                    4,
                ),
            ]
            for region in local_regions
        ]
        item["page"] = page_number
        if "region_id" in page_views[source_index - 1]:
            item["region_id"] = page_views[source_index - 1].get(
                "region_id", ""
            )
        if "region_type" in page_views[source_index - 1]:
            item["region_type"] = page_views[source_index - 1].get(
                "region_type", ""
            )
        remapped.append(item)
    return remapped


def _merge_codes(left: str, right: str) -> str:
    values: list[str] = []
    for source in (left, right):
        for value in source.replace("，", ",").split(","):
            normalized = value.strip()
            if normalized and normalized.casefold() not in {
                item.casefold() for item in values
            }:
                values.append(normalized)
    return ",".join(values)


def _deduplicate_regions(
    regions: list[list[float]],
) -> list[list[float]]:
    kept: list[list[float]] = []
    for region in sorted(regions, key=_region_area):
        if any(_same_instance(region, existing) for existing in kept):
            continue
        kept.append(region)
    return sorted(kept, key=lambda item: (item[1], item[0]))


def _same_instance(
    left: list[float],
    right: list[float],
) -> bool:
    intersection = _intersection_area(left, right)
    if intersection <= 0:
        return False
    left_area = _region_area(left)
    right_area = _region_area(right)
    union = left_area + right_area - intersection
    iou = intersection / union if union else 0.0
    containment = intersection / min(left_area, right_area)
    return iou >= 0.35 or containment >= 0.7


def _intersection_area(
    left: list[float],
    right: list[float],
) -> float:
    width = max(0.0, min(left[2], right[2]) - max(left[0], right[0]))
    height = max(0.0, min(left[3], right[3]) - max(left[1], right[1]))
    return width * height


def _region_area(region: list[float]) -> float:
    return max(0.0, region[2] - region[0]) * max(
        0.0, region[3] - region[1]
    )
