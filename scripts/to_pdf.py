from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SUPPORTED_SUFFIXES = {".dwg", ".catdrawing"}


def _detect_type(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix == ".dwg":
        return "dwg"
    if suffix == ".catdrawing":
        return "catdrawing"
    return None


def _iter_sources(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    if input_path.is_dir():
        return [
            p
            for p in sorted(input_path.rglob("*"))
            if p.is_file() and p.suffix.lower() in _SUPPORTED_SUFFIXES
        ]
    raise ValueError(f"input 不是文件或目录：{input_path}")


def _is_output_directory(input_path: Path, output_path: Path) -> bool:
    if input_path.is_dir():
        return True
    if output_path.exists():
        return output_path.is_dir()
    return output_path.suffix.lower() != ".pdf"


def _resolve_output_pdf(
    *,
    source: Path,
    input_root: Path,
    output: Path,
) -> Path:
    if input_root.is_file():
        if _is_output_directory(input_root, output):
            return output / f"{source.stem}.pdf"
        return output
    rel = source.relative_to(input_root)
    return output / rel.with_suffix(".pdf")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _export_one(*, source: Path, output_pdf: Path, file_type: str) -> dict:
    from electronic_recognition.diff.export import export_catdrawing_pycatia, export_dwg_autocad

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    normalized = str(file_type or "").strip().lower()
    if normalized == "catdrawing":
        log = export_catdrawing_pycatia(source, output_pdf)
    elif normalized == "dwg":
        log = export_dwg_autocad(source, output_pdf)
    else:
        log = {
            "source": str(source.resolve()),
            "output": str(output_pdf.resolve()),
            "tool": None,
            "tool_version": None,
            "export_time": None,
            "success": False,
            "error": f"unsupported file_type: {file_type}",
            "pages": 0,
            "page_size": None,
            "orientation": None,
        }

    _write_json(output_pdf.with_suffix(".export_log.json"), log)
    return log


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert DWG / CATDrawing to PDF. Recurses directories and preserves structure."
    )
    parser.add_argument("--input", required=True, help="输入文件或目录（递归）")
    parser.add_argument("--output", required=True, help="输出 PDF 文件或输出目录")
    parser.add_argument(
        "--type",
        default="auto",
        choices=("auto", "dwg", "catdrawing"),
        help="输入类型（默认 auto 按扩展名识别）",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    if not input_path.exists():
        print(f"输入不存在：{input_path}", file=sys.stderr)
        return 1

    try:
        sources = _iter_sources(input_path)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if input_path.is_dir():
        if output_path.suffix.lower() == ".pdf":
            print("当 input 是目录时，output 必须是目录路径，而不是 .pdf 文件。", file=sys.stderr)
            return 1
        output_path.mkdir(parents=True, exist_ok=True)
    else:
        if _is_output_directory(input_path, output_path):
            output_path.mkdir(parents=True, exist_ok=True)
        else:
            output_path.parent.mkdir(parents=True, exist_ok=True)

    failed: list[tuple[Path, str]] = []
    success_count = 0

    for source in sources:
        if args.type == "auto":
            detected = _detect_type(source)
            if detected is None:
                failed.append((source, f"不支持的扩展名：{source.suffix}"))
                continue
            file_type = detected
        else:
            file_type = args.type

        out_pdf = _resolve_output_pdf(
            source=source,
            input_root=input_path,
            output=output_path,
        )
        log = _export_one(source=source, output_pdf=out_pdf, file_type=file_type)
        if log.get("success"):
            success_count += 1
            print(f"OK  {source} -> {out_pdf}")
        else:
            failed.append((source, str(log.get("error") or "export failed")))
            print(f"FAIL {source} -> {out_pdf}  ({failed[-1][1]})", file=sys.stderr)

    if input_path.is_dir():
        print(f"完成：成功 {success_count} / 总计 {len(sources)}")
    if failed:
        print("\n失败列表：", file=sys.stderr)
        for path, reason in failed:
            print(f"- {path}  ({reason})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
