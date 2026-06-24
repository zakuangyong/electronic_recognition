from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps, ImageStat


@dataclass(slots=True)
class PageQuality:
    page: int
    width: int
    height: int
    text_length: int
    has_text_layer: bool
    text_coverage: float
    white_ratio: float
    edge_density: float
    sharpness: float
    scan_likelihood: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class PageQualityAnalyzer:
    def __init__(self, scan_text_threshold: int = 40) -> None:
        self.scan_text_threshold = max(0, scan_text_threshold)

    def analyze(self, page: object) -> PageQuality:
        image_path = Path(str(getattr(page, "image_path", "")))
        width = int(getattr(page, "width", 0) or 0)
        height = int(getattr(page, "height", 0) or 0)
        text = str(getattr(page, "text", "") or "")
        text_length = int(getattr(page, "text_length", len(text)) or len(text))
        has_text_layer = bool(
            getattr(page, "has_text_layer", False) or text.strip()
        )
        white_ratio = 1.0
        edge_density = 0.0
        sharpness = 0.0
        if image_path.is_file():
            with Image.open(image_path) as source:
                image = ImageOps.exif_transpose(source).convert("L")
                width, height = image.size
                image.thumbnail((900, 900), Image.Resampling.BILINEAR)
                histogram = image.histogram()
                total = max(1, image.width * image.height)
                white_ratio = sum(histogram[245:]) / total
                edges = image.filter(ImageFilter.FIND_EDGES)
                edge_histogram = edges.histogram()
                edge_density = sum(edge_histogram[36:]) / total
                sharpness = float(ImageStat.Stat(edges).stddev[0]) / 255.0
        page_area = max(1, width * height)
        text_coverage = min(1.0, text_length / max(300.0, page_area / 6000.0))
        low_text = text_length < self.scan_text_threshold
        scan_likelihood = 0.0
        if low_text:
            scan_likelihood += 0.45
        if edge_density > 0.045:
            scan_likelihood += 0.3
        if white_ratio < 0.985:
            scan_likelihood += 0.15
        if sharpness > 0.03:
            scan_likelihood += 0.1
        return PageQuality(
            page=int(getattr(page, "number", 1) or 1),
            width=width,
            height=height,
            text_length=text_length,
            has_text_layer=has_text_layer,
            text_coverage=round(text_coverage, 4),
            white_ratio=round(white_ratio, 4),
            edge_density=round(edge_density, 4),
            sharpness=round(sharpness, 4),
            scan_likelihood=round(min(1.0, scan_likelihood), 4),
        )
