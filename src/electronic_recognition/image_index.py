from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageOps


def image_features(path: str | Path) -> tuple[str, list[float]]:
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        return _dhash(image), _color_histogram(image)


def image_similarity(
    left_hash: str,
    left_histogram: list[float],
    right_hash: str,
    right_histogram: list[float],
) -> float:
    return 0.72 * _hash_similarity(
        left_hash, right_hash
    ) + 0.28 * _cosine(left_histogram, right_histogram)


def _dhash(image: Image.Image, size: int = 8) -> str:
    grayscale = image.convert("L").resize(
        (size + 1, size), Image.Resampling.LANCZOS
    )
    pixels = list(grayscale.getdata())
    value = 0
    for row in range(size):
        offset = row * (size + 1)
        for column in range(size):
            value = (
                value << 1
                | int(
                    pixels[offset + column]
                    > pixels[offset + column + 1]
                )
            )
    return f"{value:0{size * size // 4}x}"


def _color_histogram(
    image: Image.Image, bins: int = 8
) -> list[float]:
    resized = image.resize((96, 96), Image.Resampling.BILINEAR)
    histogram = [0.0] * (bins * 3)
    for red, green, blue in resized.getdata():
        histogram[red * bins // 256] += 1
        histogram[bins + green * bins // 256] += 1
        histogram[bins * 2 + blue * bins // 256] += 1
    norm = math.sqrt(sum(value * value for value in histogram)) or 1.0
    return [round(value / norm, 8) for value in histogram]


def _hash_similarity(left: str, right: str) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    distance = (int(left, 16) ^ int(right, 16)).bit_count()
    return 1.0 - distance / (len(left) * 4)


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return max(0.0, min(1.0, numerator / (left_norm * right_norm)))
