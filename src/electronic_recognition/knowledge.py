from __future__ import annotations

import json
import re
from pathlib import Path

from .models import ComponentSample


class ComponentKnowledgeBase:
    def __init__(
        self,
        components: list[ComponentSample],
        root_dir: str | Path,
    ) -> None:
        self.components = components
        self.root_dir = Path(root_dir).resolve()
        self.by_id = {component.id: component for component in components}

    @classmethod
    def load(cls, path: str | Path) -> "ComponentKnowledgeBase":
        source = Path(path).resolve()
        payload = json.loads(source.read_text(encoding="utf-8"))
        components = [
            ComponentSample(**item)
            for item in payload.get("components", [])
        ]
        return cls(components, source.parent)

    def image_path(self, sample: ComponentSample) -> Path:
        path = Path(sample.image_path)
        return path if path.is_absolute() else self.root_dir / path

    def image_paths(self, sample: ComponentSample) -> list[Path]:
        paths = [sample.image_path, *sample.variant_images]
        return [
            path if path.is_absolute() else self.root_dir / path
            for value in paths
            if value
            for path in [Path(value)]
        ]

    def catalog(
        self, components: list[ComponentSample] | None = None
    ) -> list[dict[str, object]]:
        return [
            {
                "id": sample.id,
                "label": sample.label,
                "component_type": sample.component_type,
                "model": sample.model,
                "aliases": sample.aliases[:4],
                "variant_count": len(sample.variant_images),
            }
            for sample in (
                [
                    item
                    for item in (
                        self.components if components is None else components
                    )
                    if item.enabled
                ]
            )
        ]

    def search(
        self,
        query: str,
        limit: int,
        preferred_ids: list[str] | None = None,
        components: list[ComponentSample] | None = None,
    ) -> list[ComponentSample]:
        preferred = {
            value.casefold() for value in preferred_ids or [] if value
        }
        query_tokens = set(_tokens(query))
        ranked: list[tuple[float, ComponentSample]] = []
        for sample in (
            [
                item
                for item in (
                    self.components if components is None else components
                )
                if item.enabled
            ]
        ):
            searchable = " ".join(
                [
                    sample.id,
                    sample.label,
                    sample.component_type,
                    sample.model,
                    sample.definition,
                    *sample.standards,
                    *sample.aliases,
                ]
            )
            score = float(
                len(query_tokens & set(_tokens(searchable)))
            )
            if sample.id.casefold() in preferred:
                score += 100
            if sample.label and sample.label.casefold() in query.casefold():
                score += 8
            if sample.model and sample.model.casefold() in query.casefold():
                score += 10
            ranked.append((score, sample))
        ranked.sort(key=lambda item: (-item[0], item[1].label, item[1].id))
        return [sample for _score, sample in ranked[:limit]]


def _tokens(text: str) -> list[str]:
    lowered = text.casefold()
    latin = re.findall(r"[a-z0-9_-]+", lowered)
    chinese = [
        lowered[index : index + 2]
        for index in range(max(0, len(lowered) - 1))
        if "\u4e00" <= lowered[index] <= "\u9fff"
    ]
    return latin + chinese
