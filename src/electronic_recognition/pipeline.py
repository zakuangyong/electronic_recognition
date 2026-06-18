from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageOps

from .config import Settings
from .control_signal_extractor import (
    extract_control_signal_configuration,
)
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
        control_signal_configuration: dict[str, Any] = {}
        control_signal_warning = ""
        if Path(input_path).suffix.lower() == ".pdf":
            try:
                title_block = extract_title_block(input_path).to_dict()
            except Exception as exc:
                title_block_warning = f"图签信息提取失败：{exc}"
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
        drawing_images = [
            Path(page.image_path) for page in document.pages
        ]
        catalog_components = self.knowledge_base.components
        shortlist = self.model.complete_json(
            SYSTEM_PROMPT,
            catalog_prompt(
                document.text,
                self.knowledge_base.catalog(catalog_components),
                self.settings.catalog_candidate_limit,
            ),
            drawing_images,
        )
        candidate_ids = [
            str(item)
            for item in shortlist.get("candidate_ids", [])
            if str(item) in self.knowledge_base.by_id
        ]
        candidate_ids = list(dict.fromkeys(candidate_ids))
        if not candidate_ids:
            raise RuntimeError(
                "候选选择模型未从完整知识库目录中返回候选元件。"
            )
        references = [
            self.knowledge_base.by_id[item] for item in candidate_ids
        ]
        if not references:
            raise RuntimeError("组件知识库中没有可用参考图片。")
        reference_images = _build_reference_panels(
            self.knowledge_base,
            references,
            directory / "reference-panels",
        )
        raw_components: list[object] = []
        recognition_warnings: list[str] = []
        page_view_counts: list[int] = []
        reference_batches = list(
            _batches(references, self.settings.reference_batch_size)
        )
        for page in document.pages:
            page_views = _build_page_views(
                Path(page.image_path),
                directory / "page-tiles",
                page.number,
                self.settings.tile_grid,
                self.settings.tile_overlap,
            )
            page_view_counts.append(len(page_views))
            view_metadata = [
                {
                    "input_image_index": index + 1,
                    "kind": view["kind"],
                    "tile": view["tile"],
                    "bounds_in_page": view["bounds"],
                }
                for index, view in enumerate(page_views)
            ]
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
                recognition_warnings.extend(
                    str(item)
                    for item in response.get("warnings", [])
                    if str(item).strip()
                )
        components = normalize_components(
            raw_components,
            references,
            len(document.pages),
        )
        warnings = recognition_warnings
        if title_block_warning:
            warnings.append(title_block_warning)
        if control_signal_warning:
            warnings.append(control_signal_warning)
        result = RecognitionResult(
            document=document.filename,
            detected_components=components,
            title_block=title_block,
            control_signal_configuration=(
                control_signal_configuration
            ),
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
                "catalog_components_presented": len(catalog_components),
                "local_catalog_recall_enabled": False,
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
