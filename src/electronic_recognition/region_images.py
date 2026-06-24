from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps

from .layout_models import LayoutRegion


def normalized_to_pixels(
    bounds: list[float],
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = [max(0.0, min(1000.0, float(value))) for value in bounds]
    left = int(round(x0 / 1000.0 * width))
    top = int(round(y0 / 1000.0 * height))
    right = int(round(x1 / 1000.0 * width))
    bottom = int(round(y1 / 1000.0 * height))
    return (
        max(0, min(width - 1, left)),
        max(0, min(height - 1, top)),
        max(1, min(width, right)),
        max(1, min(height, bottom)),
    )


def crop_region_image(
    page_path: Path,
    output_dir: Path,
    region: LayoutRegion,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(page_path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        left, top, right, bottom = normalized_to_pixels(
            region.bounds,
            image.width,
            image.height,
        )
        if right <= left:
            right = min(image.width, left + 1)
        if bottom <= top:
            bottom = min(image.height, top + 1)
        target = output_dir / f"{region.id}.png"
        image.crop((left, top, right, bottom)).save(target)
        return target
