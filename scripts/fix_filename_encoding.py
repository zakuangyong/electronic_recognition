from __future__ import annotations

import argparse
import json
from pathlib import Path


def _recover(name: str) -> str:
    """latin-1 -> utf-8 recovery for mojibake'd filenames (see api._safe_filename)."""
    if not name:
        return name
    try:
        recovered = name.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name
    return recovered if recovered != name else name


# JSON fields that may carry a user-facing (potentially mojibake'd) filename.
_FIELDS = ("document", "filename")


def _fix_file(path: Path, dry_run: bool) -> list[tuple[str, str, str]]:
    changes: list[tuple[str, str, str]] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return changes
    if not isinstance(payload, dict):
        return changes
    dirty = False
    for field in _FIELDS:
        value = payload.get(field)
        if isinstance(value, str):
            recovered = _recover(value)
            if recovered != value:
                changes.append((str(path), value, recovered))
                payload[field] = recovered
                dirty = True
    if dirty and not dry_run:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Recover mojibake'd (GBK/latin-1) Chinese filenames in saved "
            "result.json / manifest.json metadata, in place."
        )
    )
    parser.add_argument("--result-root", default="result")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report what would change; do not write.",
    )
    args = parser.parse_args()

    root = Path(args.result_root)
    if not root.is_dir():
        print(f"结果目录不存在：{root}")
        return 1

    all_changes: list[tuple[str, str, str]] = []
    for name in ("result.json", "manifest.json"):
        for path in root.glob(f"*/{name}"):
            all_changes.extend(_fix_file(path, args.dry_run))

    for file_path, before, after in all_changes:
        print(f"{file_path}\n  - {before}\n  + {after}")

    print(
        f"\n{'将修改' if args.dry_run else '已修改'} {len(all_changes)} 处文件名字段。"
    )
    if all_changes and not args.dry_run:
        print(
            "下一步：重建索引以更新库内元数据。\n"
            "  服务运行中：python -m electronic_recognition.search.rebuild --via-api --force\n"
            "  服务已停止：python -m electronic_recognition.search.rebuild --force"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
