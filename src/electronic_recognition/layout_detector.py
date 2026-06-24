from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .layout_models import LayoutRegion


class LayoutDetector(Protocol):
    def detect(self, image_path: Path, page: int) -> list[LayoutRegion]:
        ...


class NullLayoutDetector:
    def detect(self, image_path: Path, page: int) -> list[LayoutRegion]:
        return []
