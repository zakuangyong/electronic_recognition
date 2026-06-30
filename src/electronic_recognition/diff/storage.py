from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True)
class DiffJobPaths:
    job_id: str
    root: Path
    input_dir: Path
    work_dir: Path
    output_dir: Path


class DiffJobStorage:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)

    def create_job(self) -> DiffJobPaths:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        while True:
            job_id = uuid4().hex
            root = self.base_dir / job_id
            if not root.exists():
                break
        input_dir = root / "input"
        work_dir = root / "work"
        output_dir = root / "output"
        input_dir.mkdir(parents=True, exist_ok=False)
        work_dir.mkdir(parents=True, exist_ok=False)
        output_dir.mkdir(parents=True, exist_ok=False)
        return DiffJobPaths(
            job_id=job_id,
            root=root,
            input_dir=input_dir,
            work_dir=work_dir,
            output_dir=output_dir,
        )

    def save_uploads(
        self,
        job: DiffJobPaths,
        old_filename: str,
        old_bytes: bytes,
        new_filename: str,
        new_bytes: bytes,
    ) -> tuple[Path, Path]:
        safe_old_name = self._sanitize_filename(old_filename)
        safe_new_name = self._sanitize_filename(new_filename)
        if safe_old_name.lower() == safe_new_name.lower():
            safe_old_name = f"old_{safe_old_name}"
            safe_new_name = f"new_{safe_new_name}"
        return (
            self._write_bytes(job.input_dir, safe_old_name, old_bytes),
            self._write_bytes(job.input_dir, safe_new_name, new_bytes),
        )

    def get_existing_job(self, job_id: str) -> DiffJobPaths | None:
        root = self._resolve_existing_job_root(job_id)
        if root is None:
            return None
        input_dir = root / "input"
        work_dir = root / "work"
        output_dir = root / "output"
        if not root.is_dir():
            return None
        if (
            not input_dir.is_dir()
            or not work_dir.is_dir()
            or not output_dir.is_dir()
        ):
            return None
        return DiffJobPaths(
            job_id=job_id,
            root=root,
            input_dir=input_dir,
            work_dir=work_dir,
            output_dir=output_dir,
        )

    def resolve_file(self, job: DiffJobPaths, relative_path: str) -> Path | None:
        job_root = job.root.resolve(strict=False)
        path = (job.root / relative_path).resolve(strict=False)
        try:
            path.relative_to(job_root)
        except ValueError:
            return None
        if not path.is_file():
            return None
        return path

    def _write_bytes(
        self,
        directory: Path,
        filename: str,
        content: bytes,
    ) -> Path:
        destination = directory / self._sanitize_filename(filename)
        destination.write_bytes(content)
        return destination

    def _sanitize_filename(self, filename: str) -> str:
        return Path(filename).name or "upload.bin"

    def _resolve_existing_job_root(self, job_id: str) -> Path | None:
        if not self._is_safe_job_id(job_id):
            return None
        base_dir = self.base_dir.resolve(strict=False)
        root = (base_dir / job_id).resolve(strict=False)
        try:
            root.relative_to(base_dir)
        except ValueError:
            return None
        return root

    def _is_safe_job_id(self, job_id: str) -> bool:
        if not job_id or job_id in {".", ".."}:
            return False
        return not any(char in job_id for char in {"/", "\\", ":"})
