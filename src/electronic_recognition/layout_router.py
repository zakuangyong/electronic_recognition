from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz

from .config import Settings
from .layout_detector import LayoutDetector
from .layout_models import LayoutRegion, PageLayout
from .page_quality import PageQualityAnalyzer


class LayoutRouter:
    def __init__(
        self,
        settings: Settings,
        detector: LayoutDetector | None = None,
    ) -> None:
        self.settings = settings
        self.detector = detector
        self.quality_analyzer = PageQualityAnalyzer(
            settings.scan_text_threshold
        )

    def route(
        self,
        document: object,
        source_path: str | Path,
        title_block: dict[str, Any] | None = None,
        component_table: dict[str, Any] | None = None,
    ) -> list[PageLayout]:
        pages = list(getattr(document, "pages", []))
        pdf_sizes = _pdf_page_sizes(source_path)
        layouts: list[PageLayout] = []
        for page in pages:
            page_number = int(getattr(page, "number", 1) or 1)
            quality = self.quality_analyzer.analyze(page)
            regions: list[LayoutRegion] = []
            if self.settings.layout_routing_enabled:
                regions.extend(
                    self._structured_regions(
                        page_number,
                        pdf_sizes.get(page_number),
                        title_block or {},
                        component_table or {},
                    )
                )
                regions.extend(
                    self._detector_regions(page, page_number)
                )
                regions = _merge_regions(regions)
                regions.extend(
                    self._component_regions(page_number, regions)
                )
                if quality.edge_density < 0.003 and quality.text_length == 0:
                    regions.append(
                        LayoutRegion(
                            id=f"page-{page_number}-blank-1",
                            page=page_number,
                            region_type="blank",
                            bounds=[0.0, 0.0, 1000.0, 1000.0],
                            confidence=0.7,
                            source="heuristic",
                            route="skip",
                            hints={"reason": "low_edge_density"},
                        )
                    )
            component_count = sum(
                1 for region in regions if region.route == "component"
            )
            fallback_required = (
                not self.settings.layout_routing_enabled
                or self.settings.layout_router_mode == "disabled"
                or component_count == 0
            )
            layouts.append(
                PageLayout(
                    page=page_number,
                    width=quality.width,
                    height=quality.height,
                    scan_likelihood=quality.scan_likelihood,
                    text_coverage=quality.text_coverage,
                    regions=regions,
                    fallback_required=fallback_required,
                    quality=quality.to_dict(),
                )
            )
        return layouts

    def _structured_regions(
        self,
        page_number: int,
        pdf_size: tuple[float, float] | None,
        title_block: dict[str, Any],
        component_table: dict[str, Any],
    ) -> list[LayoutRegion]:
        regions: list[LayoutRegion] = []
        if page_number == int(title_block.get("page") or 1):
            bounds = _normalized_pdf_region(
                title_block.get("region"), pdf_size
            )
            if bounds:
                regions.append(
                    LayoutRegion(
                        id=f"page-{page_number}-title-block-1",
                        page=page_number,
                        region_type="title_block",
                        bounds=bounds,
                        confidence=0.88,
                        source="pdf_text",
                        route="structured",
                        hints={
                            "missing_fields": title_block.get(
                                "missing_fields", []
                            ),
                            "text_source": title_block.get(
                                "text_source", "pdf_text"
                            ),
                        },
                    )
                )
        for index, table_page in enumerate(
            _component_table_pages(component_table, page_number),
            start=1,
        ):
            bounds = _normalized_pdf_region(
                table_page.get("region"), pdf_size
            )
            if not bounds:
                continue
            region_type = (
                "terminal_table"
                if _looks_like_terminal_table(table_page)
                else "component_table"
            )
            regions.append(
                LayoutRegion(
                    id=f"page-{page_number}-{region_type}-{index}",
                    page=page_number,
                    region_type=region_type,
                    bounds=bounds,
                    confidence=0.9,
                    source="pdf_text",
                    route="structured",
                    hints={
                        "row_count": len(table_page.get("rows", [])),
                        "text_source": component_table.get(
                            "text_source", "pdf_text"
                        ),
                    },
                )
            )
        return regions

    def _detector_regions(
        self,
        page: object,
        page_number: int,
    ) -> list[LayoutRegion]:
        if (
            self.settings.layout_router_mode not in {"detector", "hybrid"}
            or self.detector is None
        ):
            return []
        try:
            regions = self.detector.detect(
                Path(str(getattr(page, "image_path", ""))),
                page_number,
            )
        except Exception:
            return []
        return [
            region
            for region in regions
            if region.confidence >= self.settings.layout_min_confidence
        ]

    def _component_regions(
        self,
        page_number: int,
        existing: list[LayoutRegion],
    ) -> list[LayoutRegion]:
        skip_regions = [
            region.bounds
            for region in existing
            if region.route in {"structured", "text", "skip"}
            and region.confidence >= self.settings.layout_min_confidence
        ]
        bounds_list = _grid_bounds(
            self.settings.tile_grid,
            self.settings.region_tile_overlap,
        )
        component_regions: list[LayoutRegion] = []
        for index, bounds in enumerate(bounds_list, start=1):
            if any(
                _intersection_area(bounds, skip) / max(1.0, _area(bounds))
                > 0.35
                for skip in skip_regions
            ):
                continue
            component_regions.append(
                LayoutRegion(
                    id=f"page-{page_number}-circuit-{index}",
                    page=page_number,
                    region_type="circuit_unknown",
                    bounds=bounds,
                    confidence=0.62,
                    source="heuristic",
                    route="component",
                    hints={"grid": self.settings.tile_grid},
                )
            )
        return component_regions


def summarize_layouts(layouts: list[PageLayout]) -> dict[str, int | float]:
    region_count = sum(len(layout.regions) for layout in layouts)
    component_count = sum(
        1
        for layout in layouts
        for region in layout.regions
        if region.route == "component"
    )
    structured_count = sum(
        1
        for layout in layouts
        for region in layout.regions
        if region.route == "structured"
    )
    skipped_count = sum(
        1
        for layout in layouts
        for region in layout.regions
        if region.route == "skip"
    )
    fallback_count = sum(1 for layout in layouts if layout.fallback_required)
    scan_count = sum(
        1 for layout in layouts if layout.scan_likelihood >= 0.6
    )
    return {
        "layout_region_count": region_count,
        "component_region_count": component_count,
        "structured_region_count": structured_count,
        "skipped_region_count": skipped_count,
        "layout_fallback_page_count": fallback_count,
        "scan_page_count": scan_count,
    }


def _component_table_pages(
    component_table: dict[str, Any],
    page_number: int,
) -> list[dict[str, Any]]:
    pages = component_table.get("pages", [])
    if not isinstance(pages, list):
        return []
    return [
        page
        for page in pages
        if isinstance(page, dict)
        and int(page.get("page") or 0) == page_number
    ]


def _looks_like_terminal_table(table_page: dict[str, Any]) -> bool:
    text = " ".join(
        " ".join(str(value) for value in row.values())
        for row in table_page.get("rows", [])
        if isinstance(row, dict)
    )
    keywords = ("terminal", "TB", "端子", "接线", "线号")
    return any(keyword.lower() in text.lower() for keyword in keywords)


def _pdf_page_sizes(source_path: str | Path) -> dict[int, tuple[float, float]]:
    path = Path(source_path)
    if path.suffix.lower() != ".pdf" or not path.is_file():
        return {}
    sizes: dict[int, tuple[float, float]] = {}
    document = fitz.open(path)
    try:
        for index, page in enumerate(document, start=1):
            sizes[index] = (float(page.rect.width), float(page.rect.height))
    finally:
        document.close()
    return sizes


def _normalized_pdf_region(
    value: object,
    pdf_size: tuple[float, float] | None,
) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        x0, y0, x1, y1 = [float(item) for item in value]
    except (TypeError, ValueError):
        return None
    if x1 <= x0 or y1 <= y0:
        return None
    if pdf_size:
        width, height = pdf_size
        if width > 0 and height > 0:
            return _clamp_bounds(
                [
                    x0 / width * 1000.0,
                    y0 / height * 1000.0,
                    x1 / width * 1000.0,
                    y1 / height * 1000.0,
                ]
            )
    return _clamp_bounds([x0, y0, x1, y1])


def _grid_bounds(grid: int, overlap: float) -> list[list[float]]:
    grid = max(1, grid)
    if grid == 1:
        return [[0.0, 0.0, 1000.0, 1000.0]]
    ranges = _tile_ranges(1000.0, grid, overlap)
    return [
        [left, top, right, bottom]
        for top, bottom in ranges
        for left, right in ranges
    ]


def _tile_ranges(
    length: float,
    grid: int,
    overlap: float,
) -> list[tuple[float, float]]:
    tile_length = min(
        length,
        length / (grid - overlap * (grid - 1)),
    )
    maximum_start = max(0.0, length - tile_length)
    starts = [
        index * maximum_start / (grid - 1)
        for index in range(grid)
    ]
    return [
        (round(start, 4), round(min(length, start + tile_length), 4))
        for start in starts
    ]


def _merge_regions(regions: list[LayoutRegion]) -> list[LayoutRegion]:
    kept: list[LayoutRegion] = []
    for region in sorted(
        regions,
        key=lambda item: (
            0 if item.route == "structured" else 1,
            -item.confidence,
            _area(item.bounds),
        ),
    ):
        duplicate = next(
            (
                existing
                for existing in kept
                if existing.page == region.page
                and existing.region_type == region.region_type
                and _intersection_area(existing.bounds, region.bounds)
                / max(1.0, min(_area(existing.bounds), _area(region.bounds)))
                > 0.78
            ),
            None,
        )
        if duplicate is None:
            kept.append(region)
    return sorted(kept, key=lambda item: (item.page, item.bounds[1], item.bounds[0]))


def _clamp_bounds(bounds: list[float]) -> list[float]:
    values = [round(max(0.0, min(1000.0, float(value))), 4) for value in bounds]
    if values[2] <= values[0] or values[3] <= values[1]:
        return [0.0, 0.0, 1000.0, 1000.0]
    return values


def _area(bounds: list[float]) -> float:
    return max(0.0, bounds[2] - bounds[0]) * max(0.0, bounds[3] - bounds[1])


def _intersection_area(left: list[float], right: list[float]) -> float:
    width = max(0.0, min(left[2], right[2]) - max(left[0], right[0]))
    height = max(0.0, min(left[3], right[3]) - max(left[1], right[1]))
    return width * height
