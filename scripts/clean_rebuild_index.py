from __future__ import annotations

import argparse
import shutil
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from electronic_recognition.config import Settings

QUARANTINE_DIRNAME = "_quarantine"


def _recover(name: str) -> str:
    if not name:
        return name
    try:
        return name.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


def _load_drawings(db_path: Path) -> list[dict]:
    if not db_path.is_file():
        return []
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT result_id, filename, drawing_number, source_hash, "
            "content_hash, page_count, indexed_at FROM drawings "
            "WHERE deleted_at IS NULL"
        ).fetchall()
    finally:
        con.close()
    return [dict(r) for r in rows]


def _vector_store_available(qdrant_dir: Path) -> bool:
    """Open and immediately close a throwaway client to confirm the embedded
    store is not locked by another process. Releases the lock before returning."""
    if not qdrant_dir.exists():
        return True
    try:
        from qdrant_client import QdrantClient
    except ImportError:
        return True
    try:
        client = QdrantClient(path=str(qdrant_dir))
    except Exception:
        return False
    close = getattr(client, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass
    return True


def _plan(result_root: Path, db_path: Path) -> dict:
    rows = _load_drawings(db_path)
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        key = row["source_hash"] or row["content_hash"] or row["result_id"]
        groups[key].append(row)

    keep: list[dict] = []
    drop_dup: list[dict] = []
    for items in groups.values():
        winner = max(
            items,
            key=lambda x: (
                (result_root / x["result_id"] / "result.json").is_file(),
                int(x["page_count"] or 0),
                str(x["indexed_at"] or ""),
            ),
        )
        keep.append(winner)
        drop_dup.extend(i for i in items if i["result_id"] != winner["result_id"])

    # result/ dirs with no result.json (failed runs / test inputs) — not indexed,
    # just clutter. Exclude the quarantine folder itself.
    junk: list[str] = []
    for path in sorted(result_root.iterdir()):
        if not path.is_dir() or path.name == QUARANTINE_DIRNAME:
            continue
        if not (path / "result.json").is_file():
            junk.append(path.name)

    return {"keep": keep, "drop_dup": drop_dup, "junk": junk}


def main() -> int:
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(
        description=(
            "Quarantine duplicate/test recognition results and rebuild a clean "
            "search index. Dry-run by default — pass --apply to execute."
        )
    )
    parser.add_argument("--result-root", default="result")
    parser.add_argument("--db", default=settings.search_sqlite_path)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually move dirs, back up + wipe the index, and rebuild.",
    )
    args = parser.parse_args()

    result_root = Path(args.result_root)
    db_path = Path(args.db)
    plan = _plan(result_root, db_path)

    keep, drop_dup, junk = plan["keep"], plan["drop_dup"], plan["junk"]

    print("=== 保留（每张图一份，共 %d 张）===" % len(keep))
    for row in sorted(keep, key=lambda x: x["result_id"]):
        print(f"  KEEP {row['result_id']}  ({_recover(row['filename'])})")
    print(f"\n=== 重复识别，将移入隔离区（共 {len(drop_dup)} 份）===")
    for row in sorted(drop_dup, key=lambda x: x["result_id"]):
        print(f"  DUP  {row['result_id']}  ({_recover(row['filename'])})")
    print(f"\n=== 无效/测试目录，将移入隔离区（共 {len(junk)} 个）===")
    for name in junk:
        print(f"  JUNK {name}")

    move_names = [r["result_id"] for r in drop_dup] + junk

    if not args.apply:
        print(
            f"\n[dry-run] 将移动 {len(move_names)} 个目录到 "
            f"{result_root / QUARANTINE_DIRNAME}/，备份并重建索引（保留 {len(keep)} 张）。"
            "\n确认无误后加 --apply 执行（执行前请先停止服务，避免抢占向量库锁）。"
        )
        return 0

    # 0) pre-flight: make sure the embedded vector store isn't locked by a
    # running server BEFORE we move/wipe anything, so a lock failure can't leave
    # a half-cleaned state.
    qdrant_dir = Path(settings.search_qdrant_path)
    if not _vector_store_available(qdrant_dir):
        print(
            "向量库 data/search/qdrant 被占用（很可能服务正在运行）。\n"
            "请先停止服务再执行本脚本——未做任何改动。"
        )
        return 2

    # 1) move duplicates + junk into the quarantine folder (reversible)
    quarantine = result_root / QUARANTINE_DIRNAME
    quarantine.mkdir(parents=True, exist_ok=True)
    for name in move_names:
        src = result_root / name
        if src.is_dir():
            shutil.move(str(src), str(quarantine / name))
    print(f"已移动 {len(move_names)} 个目录到 {quarantine}/")

    # 2) back up the current index, then wipe it for a clean rebuild
    search_dir = db_path.parent
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = search_dir / f"_backup-{stamp}"
    backup.mkdir(parents=True, exist_ok=True)
    if db_path.is_file():
        shutil.copy2(db_path, backup / db_path.name)
        db_path.unlink()
    if qdrant_dir.is_dir():
        shutil.copytree(qdrant_dir, backup / qdrant_dir.name)
        shutil.rmtree(qdrant_dir)
    print(f"已备份旧索引到 {backup}/，并清空 db 与向量库。")

    # 3) rebuild from the remaining (clean) result dirs
    try:
        from electronic_recognition.search.rebuild import _build_service

        service = _build_service(settings, db_path)
        payload = service.rebuild(result_root, force=True, mode="all")
    except Exception as exc:  # noqa: BLE001
        text = str(exc).lower()
        if "already accessed" in text or ".lock" in text or "storage folder" in text:
            print(
                "重建失败：向量库被占用。请先停止正在运行的服务再执行本脚本。\n"
                f"原始错误：{exc}"
            )
            return 2
        raise
    import json

    print("\n=== 重建完成 ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if payload.get("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
