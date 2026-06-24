from __future__ import annotations

from pathlib import Path

import fitz
from PIL import Image, ImageOps
from pypdf import PdfReader

from .models import ParsedDocument, ParsedPage


def parse_document(
    input_path: str | Path,
    work_dir: str | Path,
    render_dpi: int = 220,
    max_pages: int = 12,
) -> ParsedDocument:
    source = Path(input_path)
    suffix = source.suffix.lower()
    output_dir = Path(work_dir) / "pages"
    output_dir.mkdir(parents=True, exist_ok=True)
    if suffix == ".png":
        output = output_dir / "page-1.png"
        with Image.open(source) as image:
            rendered = ImageOps.exif_transpose(image).convert("RGB")
            width, height = rendered.size
            rendered.save(output)
        return ParsedDocument(
            filename=source.name,
            pages=[
                ParsedPage(
                    1,
                    "",
                    str(output),
                    width=width,
                    height=height,
                    text_length=0,
                    has_text_layer=False,
                )
            ],
        )
    if suffix != ".pdf":
        raise ValueError("仅支持 PDF 或 PNG 格式。")

    reader = PdfReader(source)
    count = min(len(reader.pages), max_pages)
    document = fitz.open(source)
    matrix = fitz.Matrix(render_dpi / 72, render_dpi / 72)
    pages: list[ParsedPage] = []
    for index in range(count):
        output = output_dir / f"page-{index + 1}.png"
        pixmap = document[index].get_pixmap(
            matrix=matrix, alpha=False
        )
        pixmap.save(output)
        text = reader.pages[index].extract_text() or ""
        pages.append(
            ParsedPage(
                index + 1,
                text,
                str(output),
                width=int(pixmap.width),
                height=int(pixmap.height),
                text_length=len(text),
                has_text_layer=bool(text.strip()),
            )
        )
    return ParsedDocument(source.name, pages)
