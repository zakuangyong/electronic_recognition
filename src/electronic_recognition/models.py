from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ComponentSample:
    id: str
    label: str
    image_path: str
    component_type: str = ""
    model: str = ""
    definition: str = ""
    standards: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    notes: str = ""
    source: str = ""
    dhash: str = ""
    color_histogram: list[float] = field(default_factory=list)


@dataclass(slots=True)
class ParsedPage:
    number: int
    text: str
    image_path: str


@dataclass(slots=True)
class ParsedDocument:
    filename: str
    pages: list[ParsedPage]

    @property
    def text(self) -> str:
        return "\n\n".join(
            f"===== PAGE {page.number} =====\n{page.text}"
            for page in self.pages
        )


@dataclass(slots=True)
class RecognitionResult:
    document: str
    detected_components: list[dict[str, Any]]
    title_block: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
