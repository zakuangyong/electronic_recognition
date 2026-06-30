"""
M2: Global diff detection between two rendered PDF page images.

Pipeline:
  grayscale -> alignment (phase correlation) -> absdiff -> threshold ->
  morphological close/dilate -> connected components -> filter & merge -> annotated output

Usage:
    python detect_diff.py old.png new.png -o output_dir/ --dpi 300
"""

import argparse
import json
from pathlib import Path
from typing import Optional

import cv2
import numpy as np


def imread_unicode(path, flags: int = cv2.IMREAD_COLOR) -> np.ndarray:
    """Read image with Unicode path support (path can be str or Path)."""
    path = Path(path)
    data = np.fromfile(str(path), dtype=np.uint8)
    img = cv2.imdecode(data, flags)
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {path}")
    return img


def imwrite_unicode(path, img: np.ndarray, params=None) -> bool:
    """Write image with Unicode path support (path can be str or Path)."""
    path = Path(path)
    ext = path.suffix
    success, buf = cv2.imencode(ext, img, params or [])
    if not success:
        return False
    buf.tofile(str(path))
    return True


def load_grayscale(path: Path) -> np.ndarray:
    return imread_unicode(path, cv2.IMREAD_GRAYSCALE)


def align_pages(old_gray: np.ndarray, new_gray: np.ndarray) -> tuple[np.ndarray, np.ndarray, tuple[int, int]]:
    """Align two page images using phase correlation for translation.

    Returns (aligned_old, aligned_new, offset_xy).
    """
    h_old, w_old = old_gray.shape
    h_new, w_new = new_gray.shape
    h_max = max(h_old, h_new)
    w_max = max(w_old, w_new)

    old_pad = np.ones((h_max, w_max), dtype=np.uint8) * 255
    new_pad = np.ones((h_max, w_max), dtype=np.uint8) * 255
    old_pad[:h_old, :w_old] = old_gray
    new_pad[:h_new, :w_new] = new_gray

    hann = cv2.createHanningWindow((w_max, h_max), cv2.CV_64F)
    shift, _ = cv2.phaseCorrelate(
        old_pad.astype(np.float64) * hann,
        new_pad.astype(np.float64) * hann,
    )

    dx = int(round(shift[0]))
    dy = int(round(shift[1]))
    offset = (int(dx), int(dy))

    M = np.float32([[1, 0, dx], [0, 1, dy]])
    aligned_new = cv2.warpAffine(new_pad, M, (w_max, h_max), borderValue=255)

    return old_pad, aligned_new, offset


def detect_diff_regions(
    old_img: np.ndarray,
    new_img: np.ndarray,
    min_area: int = 200,
    dilate_kernel: int = 5,
    threshold: int = 30,
    merge_distance: int = 20,
) -> tuple[list[dict], np.ndarray]:
    """Detect difference regions between two aligned grayscale images.

    Returns list of region dicts and the annotated image (BGR).
    """
    diff = cv2.absdiff(old_img.astype(np.int16), new_img.astype(np.int16))
    diff = np.clip(diff, 0, 255).astype(np.uint8)

    _, binary = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate_kernel, dilate_kernel))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    binary = cv2.morphologyEx(binary, cv2.MORPH_DILATE, kernel)

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)

    raw_boxes = []
    for i in range(1, num_labels):
        x = stats[i, cv2.CC_STAT_LEFT]
        y = stats[i, cv2.CC_STAT_TOP]
        w = stats[i, cv2.CC_STAT_WIDTH]
        h = stats[i, cv2.CC_STAT_HEIGHT]
        area = stats[i, cv2.CC_STAT_AREA]

        if area < min_area:
            continue

        raw_boxes.append([x, y, x + w, y + h, area])

    merged_boxes = merge_boxes(raw_boxes, merge_distance)

    annotated = cv2.cvtColor(new_img, cv2.COLOR_GRAY2BGR)

    regions = []
    for idx, (x0, y0, x1, y1, _) in enumerate(merged_boxes, start=1):
        x0 = max(0, x0 - 2)
        y0 = max(0, y0 - 2)
        x1 = min(new_img.shape[1], x1 + 2)
        y1 = min(new_img.shape[0], y1 + 2)

        region = {
            "region_id": idx,
            "bbox_px": [int(x0), int(y0), int(x1), int(y1)],
        }
        regions.append(region)

        cv2.rectangle(annotated, (x0, y0), (x1, y1), (0, 0, 255), 2)
        label = str(idx)
        cv2.putText(annotated, label, (x0, max(y0 - 5, 15)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 1)

    return regions, annotated


def merge_boxes(boxes: list[list[int]], distance: int) -> list[list[int]]:
    """Merge overlapping and nearby bounding boxes."""
    if not boxes:
        return []

    boxes = sorted(boxes, key=lambda b: (b[1], b[0]))

    def overlap_or_near(a, b, d):
        ax0, ay0, ax1, ay1, _ = a
        bx0, by0, bx1, by1, _ = b
        if ax0 > bx1 + d or bx0 > ax1 + d:
            return False
        if ay0 > by1 + d or by0 > ay1 + d:
            return False
        return True

    merged = []
    used = set()
    for i, box in enumerate(boxes):
        if i in used:
            continue
        current = list(box)
        changed = True
        while changed:
            changed = False
            for j, other in enumerate(boxes):
                if j in used or j == i:
                    continue
                if overlap_or_near(current, other, distance):
                    current[0] = min(current[0], other[0])
                    current[1] = min(current[1], other[1])
                    current[2] = max(current[2], other[2])
                    current[3] = max(current[3], other[3])
                    current[4] = current[4] + other[4]
                    used.add(j)
                    changed = True
        merged.append(current)

    return merged


def crop_region(img: np.ndarray, bbox: list[int], margin: int = 4) -> np.ndarray:
    x0, y0, x1, y1 = bbox
    h, w = img.shape[:2]
    x0 = max(0, x0 - margin)
    y0 = max(0, y0 - margin)
    x1 = min(w, x1 + margin)
    y1 = min(h, y1 + margin)
    return img[y0:y1, x0:x1]


def save_crops_and_annotated(
    old_img: np.ndarray,
    new_img: np.ndarray,
    annotated_img: np.ndarray,
    regions: list[dict],
    output_dir: Path,
    page_num: int,
) -> list[dict]:
    """Save crop images and annotated image. Update regions with crop paths."""
    crops_dir = output_dir / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)

    annotated_path = output_dir / f"page_{page_num:03d}_annotated.png"
    imwrite_unicode(str(annotated_path), annotated_img)

    for region in regions:
        rid = region["region_id"]
        bbox = region["bbox_px"]

        old_crop = crop_region(old_img, bbox)
        new_crop = crop_region(new_img, bbox)

        old_path = crops_dir / f"page_{page_num:03d}_region_{rid:03d}_old.png"
        new_path = crops_dir / f"page_{page_num:03d}_region_{rid:03d}_new.png"

        imwrite_unicode(str(old_path), old_crop)
        imwrite_unicode(str(new_path), new_crop)

        region["old_crop"] = str(old_path.resolve())
        region["new_crop"] = str(new_path.resolve())

    return regions


def diff_page(
    old_png: Path,
    new_png: Path,
    output_dir: Path,
    page_num: int,
    min_area: int = 200,
    dilate_kernel: int = 5,
    threshold: int = 30,
    merge_distance: int = 30,
) -> tuple[list[dict], tuple[int, int]]:
    """Run diff detection on a single page pair.

    Returns (regions, offset_xy).
    """
    old_gray = load_grayscale(old_png)
    new_gray = load_grayscale(new_png)

    old_aligned, new_aligned, offset = align_pages(old_gray, new_gray)

    regions, annotated = detect_diff_regions(
        old_aligned, new_aligned,
        min_area=min_area,
        dilate_kernel=dilate_kernel,
        threshold=threshold,
        merge_distance=merge_distance,
    )

    regions = save_crops_and_annotated(
        old_aligned, new_aligned, annotated, regions, output_dir, page_num,
    )

    print(f"  Page {page_num}: {len(regions)} diff region(s), offset={offset}")
    return regions, offset


def main():
    parser = argparse.ArgumentParser(description="Detect differences between two page images")
    parser.add_argument("old", type=Path, help="Old version page PNG")
    parser.add_argument("new", type=Path, help="New version page PNG")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Output directory")
    parser.add_argument("--page", type=int, default=1, help="Page number for naming")
    parser.add_argument("--min-area", type=int, default=200, help="Minimum diff area in pixels")
    parser.add_argument("--dilate", type=int, default=5, help="Dilation kernel size")
    parser.add_argument("--threshold", type=int, default=30, help="Diff threshold (0-255)")
    parser.add_argument("--merge", type=int, default=30, help="Merge distance for nearby boxes")
    parser.add_argument("--json", type=Path, default=None, help="Output regions JSON")
    args = parser.parse_args()

    if not args.old.exists() or not args.new.exists():
        print("Error: input images not found")
        return 1

    args.output.mkdir(parents=True, exist_ok=True)

    regions, offset = diff_page(
        args.old, args.new, args.output, args.page,
        min_area=args.min_area,
        dilate_kernel=args.dilate,
        threshold=args.threshold,
        merge_distance=args.merge,
    )

    if args.json:
        data = {
            "page": args.page,
            "offset_px": list(offset),
            "old_file": str(args.old.resolve()),
            "new_file": str(args.new.resolve()),
            "regions": regions,
        }
        args.json.parent.mkdir(parents=True, exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
