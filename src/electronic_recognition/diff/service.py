from __future__ import annotations

import json
import shutil
from pathlib import Path

from .storage import DiffJobPaths


class DrawingDiffService:
    def run_compare(
        self,
        *,
        job: DiffJobPaths,
        old_source: Path,
        new_source: Path,
        file_type: str,
        dpi: int = 300,
        threshold: int = 25,
        min_area: int = 200,
        dilate_kernel: int = 5,
        merge_distance: int = 30,
    ) -> None:
        normalized_file_type = file_type.strip().lower()
        self._validate_file_type(normalized_file_type, old_source, new_source)

        old_pdf = job.input_dir / "old.pdf"
        new_pdf = job.input_dir / "new.pdf"
        _write_json(
            job.output_dir / "source_files.json",
            {
                "old_filename": old_source.name,
                "new_filename": new_source.name,
                "file_type": normalized_file_type,
            },
        )

        self._prepare_pdf(normalized_file_type, old_source, old_pdf)
        self._prepare_pdf(normalized_file_type, new_source, new_pdf)
        self._run_pdf_diff(
            job=job,
            old_pdf=old_pdf,
            new_pdf=new_pdf,
            dpi=dpi,
            threshold=threshold,
            min_area=min_area,
            dilate_kernel=dilate_kernel,
            merge_distance=merge_distance,
        )

    def _prepare_pdf(
        self,
        file_type: str,
        source: Path,
        output: Path,
    ) -> None:
        if file_type == "pdf":
            log = self._copy_pdf_input(source, output)
            _write_json(output.with_suffix(".export_log.json"), log)
            if not log.get("success"):
                raise RuntimeError(str(log.get("error") or "pdf copy failed"))
            return
        self._export_to_pdf(file_type, source, output)

    def _copy_pdf_input(
        self,
        source: Path,
        output: Path,
    ) -> dict[str, object]:
        log = {
            "source": str(source.resolve()),
            "output": str(output.resolve()),
            "tool": "direct_pdf",
            "success": False,
            "error": None,
        }
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            if source.resolve(strict=False) != output.resolve(strict=False):
                shutil.copyfile(source, output)
            if output.exists() and output.stat().st_size > 0:
                log["success"] = True
            else:
                log["error"] = "PDF input is missing or empty."
        except Exception as exc:
            log["error"] = str(exc)
        return log

    def _export_to_pdf(
        self,
        file_type: str,
        source: Path,
        output: Path,
    ) -> None:
        from .export import export_catdrawing_pycatia, export_dwg_autocad

        output.parent.mkdir(parents=True, exist_ok=True)
        if file_type == "catdrawing":
            log = export_catdrawing_pycatia(source, output)
        elif file_type == "dwg":
            log = export_dwg_autocad(source, output)
        else:
            raise ValueError("unsupported file_type")

        _write_json(output.with_suffix(".export_log.json"), log)
        if not log.get("success"):
            raise RuntimeError(str(log.get("error") or "export failed"))

    def _run_pdf_diff(
        self,
        *,
        job: DiffJobPaths,
        old_pdf: Path,
        new_pdf: Path,
        dpi: int,
        threshold: int,
        min_area: int,
        dilate_kernel: int,
        merge_distance: int,
    ) -> None:
        from .detect import diff_page
        from .render import get_pdf_page_count, render_pdf_to_png
        from .report import build_summary, write_excel_report
        from .text import extract_all_regions

        old_page_count = get_pdf_page_count(old_pdf)
        new_page_count = get_pdf_page_count(new_pdf)
        page_count = min(old_page_count, new_page_count)

        old_pages = render_pdf_to_png(
            old_pdf,
            job.work_dir / "rendered" / "old",
            dpi=dpi,
        )
        new_pages = render_pdf_to_png(
            new_pdf,
            job.work_dir / "rendered" / "new",
            dpi=dpi,
        )

        diff_output_dir = job.work_dir / "diff"
        diff_output_dir.mkdir(parents=True, exist_ok=True)
        job.output_dir.mkdir(parents=True, exist_ok=True)
        all_pages_data: list[dict[str, object]] = []

        for index in range(page_count):
            page_number = index + 1
            old_page = old_pages[index]
            new_page = new_pages[index]
            regions, offset = diff_page(
                Path(str(old_page["path"])),
                Path(str(new_page["path"])),
                diff_output_dir,
                page_number,
                min_area=min_area,
                dilate_kernel=dilate_kernel,
                threshold=threshold,
                merge_distance=merge_distance,
            )
            if regions:
                old_w = int(old_page["width_px"])
                old_h = int(old_page["height_px"])
                new_w = int(new_page["width_px"])
                new_h = int(new_page["height_px"])
                dx, dy = offset
                regions = extract_all_regions(
                    old_pdf,
                    regions,
                    page_number,
                    old_w,
                    old_h,
                    offset_px=(0, 0),
                    text_key="old_text",
                    source_key="old_text_source",
                )
                regions = extract_all_regions(
                    new_pdf,
                    regions,
                    page_number,
                    new_w,
                    new_h,
                    offset_px=(-dx, -dy),
                    text_key="new_text",
                    source_key="new_text_source",
                )
            all_pages_data.append(
                {
                    "page": page_number,
                    "offset_px": list(offset),
                    "width_px": int(old_page["width_px"]),
                    "height_px": int(old_page["height_px"]),
                    "regions": regions,
                }
            )

        regions_path = job.work_dir / "all_regions.json"
        _write_json(regions_path, all_pages_data)
        summary = build_summary(
            old_pdf.name,
            new_pdf.name,
            old_pdf.name,
            new_pdf.name,
            all_pages_data,
        )
        _write_json(job.output_dir / "summary.json", summary)
        write_excel_report(summary, job.output_dir / "diff_report.xlsx")

    def _validate_file_type(
        self,
        file_type: str,
        old_source: Path,
        new_source: Path,
    ) -> None:
        expected = {
            "catdrawing": ".catdrawing",
            "dwg": ".dwg",
            "pdf": ".pdf",
        }.get(file_type)
        if expected is None:
            raise ValueError("unsupported file_type")
        if old_source.suffix.lower() != expected:
            raise ValueError("old file suffix does not match file_type")
        if new_source.suffix.lower() != expected:
            raise ValueError("new file suffix does not match file_type")


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
