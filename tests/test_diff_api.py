from __future__ import annotations

import io
import json
from pathlib import Path

from fastapi import UploadFile

from electronic_recognition import api


class _FakeDiffService:
    calls: list[dict[str, object]] = []

    def run_compare(self, **kwargs: object) -> None:
        self.calls.append(kwargs)
        job = kwargs["job"]
        output_dir = job.output_dir
        work_dir = job.work_dir
        diff_dir = work_dir / "diff"
        crops_dir = diff_dir / "crops"
        crops_dir.mkdir(parents=True)
        (diff_dir / "page_001_annotated.png").write_bytes(b"png")
        crop = crops_dir / "page_001_region_001_new.png"
        crop.write_bytes(b"crop")
        summary = {
            "total_pages": 1,
            "total_regions": 1,
            "pages": [
                {
                    "page": 1,
                    "regions": [
                        {
                            "region_id": 1,
                            "bbox_px": [1, 2, 3, 4],
                            "change_type": "visual_change",
                            "old_text": "",
                            "new_text": "KM1",
                            "new_crop": str(crop),
                        }
                    ],
                }
            ],
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "summary.json").write_text(
            json.dumps(summary),
            encoding="utf-8",
        )
        (output_dir / "source_files.json").write_text(
            json.dumps(
                {
                    "old_filename": Path(str(kwargs["old_source"])).name,
                    "new_filename": Path(str(kwargs["new_source"])).name,
                    "file_type": kwargs["file_type"],
                }
            ),
            encoding="utf-8",
        )
        (output_dir / "diff_report.xlsx").write_bytes(b"xlsx")


def test_diff_compare_api_builds_result(monkeypatch, tmp_path: Path) -> None:
    _FakeDiffService.calls.clear()
    monkeypatch.setattr(api, "DIFF_JOB_DIR", tmp_path / "jobs")
    monkeypatch.setattr(api, "_diff_service", lambda: _FakeDiffService())

    payload = _run_async(
        api.compare_drawings(
            old_file=_upload("old.CATDrawing"),
            new_file=_upload("new.CATDrawing"),
            file_type="catdrawing",
            dpi=200,
            threshold=30,
        )
    )

    assert payload["success"] is True
    assert payload["job_id"]
    assert payload["data"]["summary"]["total_diff_count"] == 1
    assert payload["data"]["diff_items"][0]["new_text"] == "KM1"
    assert payload["data"]["downloads"]["excel_report_url"].startswith(
        "/api/diff/files/"
    )
    assert _FakeDiffService.calls[0]["file_type"] == "catdrawing"


def test_diff_compare_api_accepts_pdf_uploads(monkeypatch, tmp_path: Path) -> None:
    _FakeDiffService.calls.clear()
    monkeypatch.setattr(api, "DIFF_JOB_DIR", tmp_path / "jobs")
    monkeypatch.setattr(api, "_diff_service", lambda: _FakeDiffService())

    payload = _run_async(
        api.compare_drawings(
            old_file=_upload("old.pdf"),
            new_file=_upload("new.pdf"),
            file_type="pdf",
            dpi=200,
            threshold=30,
        )
    )

    assert payload["success"] is True
    assert payload["data"]["summary"]["old_filename"] == "old.pdf"
    assert payload["data"]["summary"]["new_filename"] == "new.pdf"
    assert _FakeDiffService.calls[0]["file_type"] == "pdf"


def test_diff_compare_rejects_mismatched_extensions(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(api, "DIFF_JOB_DIR", tmp_path / "jobs")

    payload = _run_async(
        api.compare_drawings(
            old_file=_upload("old.CATDrawing"),
            new_file=_upload("new.dwg"),
            file_type="catdrawing",
            dpi=200,
            threshold=30,
        )
    )

    assert payload["success"] is False
    assert payload["error_code"] == "validation_error"


def _upload(filename: str) -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(b"demo"))


def _run_async(awaitable):
    import asyncio

    return asyncio.run(awaitable)
