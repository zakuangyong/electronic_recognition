from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .config import Settings
from .document import parse_document
from .knowledge import ComponentKnowledgeBase
from .llm import VisionModel
from .models import ComponentSample, RecognitionResult
from .prompts import SYSTEM_PROMPT, catalog_prompt, recognition_prompt
from .title_block_extractor import extract_title_block


class RecognitionPipeline:
    def __init__(
        self,
        knowledge_base: ComponentKnowledgeBase,
        settings: Settings | None = None,
        model: VisionModel | None = None,
    ) -> None:
        self.knowledge_base = knowledge_base
        self.settings = settings or Settings.from_env()
        self.model = model or VisionModel(self.settings)

    def analyze(
        self,
        input_path: str | Path,
        work_dir: str | Path,
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
        title_block: dict[str, Any] = {}
        title_block_warning = ""
        if Path(input_path).suffix.lower() == ".pdf":
            try:
                title_block = extract_title_block(input_path).to_dict()
            except Exception as exc:
                title_block_warning = f"图签信息提取失败：{exc}"
        drawing_images = [
            Path(page.image_path) for page in document.pages
        ]
        catalog_pool = self.knowledge_base.search(
            document.text,
            limit=max(1, self.settings.catalog_pool_limit),
        )
        shortlist = self.model.complete_json(
            SYSTEM_PROMPT,
            catalog_prompt(
                document.text,
                self.knowledge_base.catalog(catalog_pool),
                self.settings.catalog_candidate_limit,
            ),
            drawing_images,
        )
        candidate_ids = [
            str(item)
            for item in shortlist.get("candidate_ids", [])
            if str(item) in self.knowledge_base.by_id
        ]
        if candidate_ids:
            references = [
                self.knowledge_base.by_id[item]
                for item in candidate_ids[: self.settings.reference_limit]
            ]
        else:
            references = self.knowledge_base.search(
                document.text,
                limit=min(self.settings.reference_limit, len(catalog_pool)),
                components=catalog_pool,
            )
        if not references:
            raise RuntimeError("组件知识库中没有可用参考图片。")
        reference_images = [
            self.knowledge_base.image_path(sample)
            for sample in references
        ]
        response = self.model.complete_json(
            SYSTEM_PROMPT,
            recognition_prompt(
                document.text,
                references,
                len(drawing_images),
            ),
            drawing_images + reference_images,
        )
        components = normalize_components(
            response.get("detected_components", []),
            references,
            len(document.pages),
        )
        warnings = [
            str(item)
            for item in response.get("warnings", [])
            if str(item).strip()
        ]
        if title_block_warning:
            warnings.append(title_block_warning)
        result = RecognitionResult(
            document=document.filename,
            detected_components=components,
            title_block=title_block,
            warnings=list(dict.fromkeys(warnings)),
            meta={
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
                "catalog_pool_components": len(catalog_pool),
                "candidate_ids": candidate_ids,
                "reference_ids": [
                    sample.id for sample in references
                ],
            },
        )
        return result, directory / "pages"


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
        key = (code.casefold(), label.casefold(), page)
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
                "evidence": str(raw.get("evidence", "")).strip(),
            },
        )
        item["occurrence_count"] = max(
            int(item["occurrence_count"]), count
        )
        item["confidence"] = max(
            float(item["confidence"]), _confidence(raw.get("confidence"))
        )
        existing = {tuple(region) for region in item["regions"]}
        for region in regions:
            if tuple(region) not in existing:
                item["regions"].append(region)
                existing.add(tuple(region))
    return sorted(
        merged.values(),
        key=lambda item: (
            int(item["page"]),
            str(item["label"]),
            str(item["code"]),
        ),
    )


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
