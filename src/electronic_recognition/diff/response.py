from __future__ import annotations

import json
import re
from pathlib import Path

from .storage import DiffJobPaths


def build_diff_result_payload(job: DiffJobPaths) -> dict[str, object]:
    summary_path = job.output_dir / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    old_filename, new_filename = _resolve_source_filenames(job, summary)
    return {
        "summary": {
            "old_filename": old_filename,
            "new_filename": new_filename,
            "page_count": summary.get(
                "total_pages",
                len(summary.get("pages", [])),
            ),
            "total_diff_count": summary.get("total_regions", 0),
            "status": "completed",
            "duration_ms": None,
        },
        "annotated_images": _build_annotated_images(job),
        "diff_items": _build_diff_items(job, summary),
        "downloads": {
            "summary_json_url": _file_url(job, summary_path),
            "excel_report_url": _optional_file_url(
                job,
                job.output_dir / "diff_report.xlsx",
            ),
        },
        "artifacts": _build_artifacts(job, summary_path),
    }


def _build_annotated_images(job: DiffJobPaths) -> list[dict[str, object]]:
    diff_dir = job.work_dir / "diff"
    if not diff_dir.is_dir():
        return []
    images: list[dict[str, object]] = []
    for image_path in sorted(diff_dir.glob("page_*_annotated.png")):
        page = _extract_page_number(image_path)
        if page is None:
            continue
        images.append({"page": page, "image_url": _file_url(job, image_path)})
    return images


def _build_diff_items(
    job: DiffJobPaths,
    summary: dict[str, object],
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for page in summary.get("pages", []):
        if not isinstance(page, dict):
            continue
        page_number = int(page.get("page", 0) or 0)
        for region in page.get("regions", []):
            if not isinstance(region, dict):
                continue
            region_id = int(region.get("region_id", 0) or 0)
            crop_path = str(
                region.get("new_crop") or region.get("old_crop") or ""
            )
            items.append(
                {
                    "id": f"region_{region_id:03d}",
                    "page": page_number,
                    "bbox": list(region.get("bbox_px", [])),
                    "crop_image_url": _path_to_url(job, crop_path),
                    "old_text": region.get("old_text", ""),
                    "new_text": region.get("new_text", ""),
                    "changed_type": region.get(
                        "change_type",
                        "graphic_or_text",
                    ),
                }
            )
    return items


def _build_artifacts(
    job: DiffJobPaths,
    summary_path: Path,
) -> dict[str, str]:
    artifacts = {"raw_summary_url": _file_url(job, summary_path)}
    all_regions_url = _optional_file_url(job, job.work_dir / "all_regions.json")
    if all_regions_url:
        artifacts["all_regions_url"] = all_regions_url
    return artifacts


def _resolve_source_filenames(
    job: DiffJobPaths,
    summary: dict[str, object],
) -> tuple[str, str]:
    metadata_path = job.output_dir / "source_files.json"
    if metadata_path.is_file():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        old_filename = str(metadata.get("old_filename", ""))
        new_filename = str(metadata.get("new_filename", ""))
        if old_filename and new_filename:
            return old_filename, new_filename

    old_source = Path(str(summary.get("old_source", ""))).name
    new_source = Path(str(summary.get("new_source", ""))).name
    if (
        not _looks_like_generated_pdf_name(old_source)
        and not _looks_like_generated_pdf_name(new_source)
    ):
        return old_source, new_source

    input_files = [
        path
        for path in sorted(job.input_dir.iterdir())
        if path.is_file() and path.name.lower() not in {"old.pdf", "new.pdf"}
    ]
    if len(input_files) >= 2:
        old_candidate = _match_source_file(input_files, "old")
        new_candidate = _match_source_file(input_files, "new")
        if old_candidate is not None and new_candidate is not None:
            return old_candidate.name, new_candidate.name
        return input_files[0].name, input_files[1].name
    return old_source, new_source


def _optional_file_url(job: DiffJobPaths, path: Path) -> str:
    if not path.is_file():
        return ""
    return _file_url(job, path)


def _path_to_url(job: DiffJobPaths, path_value: str) -> str:
    if not path_value:
        return ""
    return _file_url(job, Path(path_value))


def _file_url(job: DiffJobPaths, path: Path) -> str:
    relative = Path(path).resolve(strict=False).relative_to(
        job.root.resolve(strict=False)
    )
    return f"/api/diff/files/{job.job_id}/{relative.as_posix()}"


def _extract_page_number(path: Path) -> int | None:
    match = re.search(r"page_(\d+)_annotated\.png$", path.name)
    return int(match.group(1)) if match else None


def _looks_like_generated_pdf_name(filename: str) -> bool:
    return filename.lower() in {"old.pdf", "new.pdf"}


def _match_source_file(paths: list[Path], keyword: str) -> Path | None:
    keyword_lower = keyword.lower()
    for path in paths:
        if keyword_lower in path.stem.lower():
            return path
    return None
