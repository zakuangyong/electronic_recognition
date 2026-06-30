from __future__ import annotations

from pathlib import Path

import pytest

from electronic_recognition.diff.service import DrawingDiffService
from electronic_recognition.diff.storage import DiffJobStorage


def test_diff_service_uses_pdf_inputs_directly(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    job = DiffJobStorage(tmp_path / "jobs").create_job()
    old_source = job.input_dir / "before.pdf"
    new_source = job.input_dir / "after.pdf"
    old_source.write_bytes(b"%PDF-old")
    new_source.write_bytes(b"%PDF-new")
    captured: dict[str, object] = {}

    def fail_export(*args: object, **kwargs: object) -> None:
        raise AssertionError("PDF inputs should not use CAD export")

    def fake_run_pdf_diff(self: DrawingDiffService, **kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(DrawingDiffService, "_export_to_pdf", fail_export)
    monkeypatch.setattr(DrawingDiffService, "_run_pdf_diff", fake_run_pdf_diff)

    DrawingDiffService().run_compare(
        job=job,
        old_source=old_source,
        new_source=new_source,
        file_type="pdf",
        dpi=200,
        threshold=30,
    )

    assert captured["old_pdf"] == job.input_dir / "old.pdf"
    assert captured["new_pdf"] == job.input_dir / "new.pdf"
    assert (job.input_dir / "old.pdf").read_bytes() == b"%PDF-old"
    assert (job.input_dir / "new.pdf").read_bytes() == b"%PDF-new"
    assert (job.input_dir / "old.export_log.json").is_file()
    assert (job.input_dir / "new.export_log.json").is_file()
