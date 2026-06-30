"""
M3: Extract text from diff regions using PyMuPDF text layer.

Converts pixel bbox coordinates back to PDF page coordinates
and extracts text blocks that intersect with the region.

Usage:
    python extract_text.py input.pdf work/regions_page_001.json -d 300 -o work/text_page_001.json
"""

import argparse
import json
from pathlib import Path


def bbox_px_to_pdf(bbox_px: list[int], page_width_px: int, page_height_px: int,
                   pdf_width_pt: float, pdf_height_pt: float) -> tuple[float, float, float, float]:
    """Convert pixel bbox (x0, y0, x1, y1) to PDF point coordinates (x0, y0, x1, y1).

    PDF coordinate origin is bottom-left; image origin is top-left.
    """
    px_to_pt_x = pdf_width_pt / page_width_px
    px_to_pt_y = pdf_height_pt / page_height_px

    x0_px, y0_px, x1_px, y1_px = bbox_px

    x0_pt = x0_px * px_to_pt_x
    x1_pt = x1_px * px_to_pt_x

    y0_pt = pdf_height_pt - y1_px * px_to_pt_y
    y1_pt = pdf_height_pt - y0_px * px_to_pt_y

    return (x0_pt, y0_pt, x1_pt, y1_pt)


def extract_text_from_region(page, bbox_pt: tuple[float, float, float, float]) -> str:
    """Extract text blocks from a PDF page that intersect with the given bbox (PDF coords)."""
    x0, y0, x1, y1 = bbox_pt
    margin = 2
    x0 -= margin
    y0 -= margin
    x1 += margin
    y1 += margin

    blocks = page.get_text("blocks")
    lines = []
    for block in blocks:
        bx0, by0, bx1, by1, text, block_type, _ = block
        if block_type != 0:
            continue
        if bx1 < x0 or bx0 > x1 or by1 < y0 or by0 > y1:
            continue
        text = text.strip()
        if text:
            lines.append(text)
    return "\n".join(lines)


def extract_all_regions(
    pdf_path: Path,
    regions: list[dict],
    page_num: int,
    page_width_px: int,
    page_height_px: int,
    offset_px: tuple[int, int] = (0, 0),
    text_key: str = "text_extracted",
    source_key: str = "text_source",
) -> list[dict]:
    """Extract text for all diff regions on a page.

    ``bbox_px`` is expressed in the aligned/padded coordinate space produced by
    ``align_pages`` (max of both page sizes, new image shifted by the alignment
    offset). ``offset_px`` maps that bbox back into *this* PDF's own pixel frame
    before scaling to PDF points:

      - old PDF: offset (0, 0)              — old image sits unshifted at top-left
      - new PDF: offset (-dx, -dy)          — undo the alignment shift (dx, dy)

    ``page_width_px``/``page_height_px`` must be the rendered pixel size of *this*
    PDF's page, and ``text_key``/``source_key`` let the caller store old/new text
    into separate fields.
    """
    import fitz

    doc = fitz.open(str(pdf_path))
    page = doc[page_num - 1]
    pdf_rect = page.rect
    pdf_w = pdf_rect.width
    pdf_h = pdf_rect.height

    ox, oy = offset_px

    for region in regions:
        x0, y0, x1, y1 = region["bbox_px"]
        x0 += ox
        x1 += ox
        y0 += oy
        y1 += oy

        # Clip to this page's pixel bounds; a region fully outside yields no text.
        x0 = max(0, min(x0, page_width_px))
        x1 = max(0, min(x1, page_width_px))
        y0 = max(0, min(y0, page_height_px))
        y1 = max(0, min(y1, page_height_px))

        bbox_pt = bbox_px_to_pdf(
            [x0, y0, x1, y1], page_width_px, page_height_px, pdf_w, pdf_h
        )
        text = extract_text_from_region(page, bbox_pt)

        region[text_key] = text or ""
        region[source_key] = "pdf_layer" if text else "none"

    doc.close()
    return regions


def main():
    parser = argparse.ArgumentParser(description="Extract text from PDF for diff regions")
    parser.add_argument("pdf", type=Path, help="PDF file")
    parser.add_argument("regions", type=Path, help="Regions JSON from diff detection")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Output JSON with text")
    parser.add_argument("--page", type=int, default=1, help="Page number")
    parser.add_argument("--width", type=int, required=True, help="Page image width in pixels")
    parser.add_argument("--height", type=int, required=True, help="Page image height in pixels")
    args = parser.parse_args()

    if not args.pdf.exists():
        print(f"Error: PDF not found: {args.pdf}")
        return 1
    if not args.regions.exists():
        print(f"Error: regions JSON not found: {args.regions}")
        return 1

    with open(args.regions, "r", encoding="utf-8") as f:
        data = json.load(f)

    regions = data if isinstance(data, list) else data.get("regions", [])

    regions = extract_all_regions(
        args.pdf, regions, args.page, args.width, args.height
    )

    text_count = sum(1 for r in regions if r["text_extracted"])
    print(f"  Page {args.page}: text extracted from {text_count}/{len(regions)} region(s)")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(regions, f, indent=2, ensure_ascii=False)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
