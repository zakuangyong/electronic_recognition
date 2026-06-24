from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


REGION_TYPES = {
    "title_block",
    "component_table",
    "terminal_table",
    "revision_block",
    "main_circuit",
    "control_circuit",
    "circuit_unknown",
    "notes",
    "frame_or_margin",
    "blank",
}

ROUTES = {"component", "structured", "text", "skip"}


@dataclass(slots=True)
class LayoutRegion:
    id: str
    page: int
    region_type: str
    bounds: list[float]
    confidence: float
    source: str
    route: str
    hints: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PageLayout:
    page: int
    width: int
    height: int
    scan_likelihood: float
    text_coverage: float
    regions: list[LayoutRegion]
    fallback_required: bool = False
    quality: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
