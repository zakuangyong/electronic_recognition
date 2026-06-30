"""
M2: Render PDF pages to PNG images using PyMuPDF.

Usage:
    python render_pdf.py input/raw.pdf -o work/rendered/raw -d 300
"""

import argparse
import json
from pathlib import Path


def render_pdf_to_png(pdf_path: Path, output_prefix: Path, dpi: int = 300) -> list[dict]:
    """Render all PDF pages to PNG files.

    Returns list of page info dicts: {page, width_px, height_px, path}.
    """
    import fitz

    output_prefix.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(pdf_path))
    pages_info = []

    for i in range(len(doc)):
        page = doc[i]
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)

        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)

        page_num = i + 1
        out_path = output_prefix.parent / f"{output_prefix.name}_page_{page_num:03d}.png"
        pix.save(str(out_path))

        pages_info.append({
            "page": page_num,
            "width_px": pix.width,
            "height_px": pix.height,
            "path": str(out_path.resolve()),
        })

    doc.close()
    return pages_info


def get_pdf_page_count(pdf_path: Path) -> int:
    import fitz

    doc = fitz.open(str(pdf_path))
    count = len(doc)
    doc.close()
    return count


def main():
    parser = argparse.ArgumentParser(description="Render PDF to PNG pages")
    parser.add_argument("pdf", type=Path, help="Input PDF file")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Output PNG prefix")
    parser.add_argument("-d", "--dpi", type=int, default=300, help="Render DPI (default: 300)")
    parser.add_argument("--info", type=Path, default=None, help="Output page info JSON")
    args = parser.parse_args()

    if not args.pdf.exists():
        print(f"Error: PDF not found: {args.pdf}")
        return 1

    page_count = get_pdf_page_count(args.pdf)
    print(f"PDF has {page_count} page(s), rendering at {args.dpi} DPI...")

    pages_info = render_pdf_to_png(args.pdf, args.output, dpi=args.dpi)

    for info in pages_info:
        print(f"  Page {info['page']}: {info['width_px']}x{info['height_px']} -> {info['path']}")

    if args.info:
        args.info.parent.mkdir(parents=True, exist_ok=True)
        with open(args.info, "w", encoding="utf-8") as f:
            json.dump(pages_info, f, indent=2, ensure_ascii=False)
        print(f"Page info saved: {args.info}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
