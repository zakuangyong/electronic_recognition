from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ComponentSample:
    id: str
    label: str
    image_path: str
    variant_images: list[str] = field(default_factory=list)
    component_type: str = ""
    model: str = ""
    definition: str = ""
    standards: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    notes: str = ""
    source: str = ""
    dhash: str = ""
    color_histogram: list[float] = field(default_factory=list)
    enabled: bool = True
    created_at: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class ParsedPage:
    number: int
    text: str
    image_path: str
    width: int = 0
    height: int = 0
    text_length: int = 0
    has_text_layer: bool = False


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
    detected_combinations: list[dict[str, Any]] = field(
        default_factory=list
    )
    title_block: dict[str, Any] = field(default_factory=dict)
    control_signal_configuration: dict[str, Any] = field(
        default_factory=dict
    )
    component_table: dict[str, Any] = field(default_factory=dict)
    page_layouts: list[dict[str, Any]] = field(default_factory=list)
    recognition_steps: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
