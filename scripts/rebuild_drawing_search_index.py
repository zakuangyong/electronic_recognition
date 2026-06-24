from __future__ import annotations

import argparse
import json
from pathlib import Path

from electronic_recognition.config import Settings
from electronic_recognition.search.rebuild import _build_service


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild the drawing search index from saved result.json files."
    )
    parser.add_argument(
        "--result-root",
        default="result",
        help="Directory containing saved recognition result folders.",
    )
    parser.add_argument(
        "--db",
        default="",
        help="SQLite database path. Defaults to ER_SEARCH_SQLITE_PATH.",
    )
    parser.add_argument("--result-id", default="", help="Only rebuild one result id.")
    parser.add_argument(
        "--mode",
        default="all",
        choices=("all", "bm25", "vector"),
        help="Index mode: all, bm25, or vector.",
    )
    parser.add_argument("--force", action="store_true", help="Rebuild unchanged results too.")
    args = parser.parse_args()

    settings = Settings.from_env()
    db_path = Path(args.db or settings.search_sqlite_path)
    service = _build_service(settings, db_path)
    payload = service.rebuild(
        Path(args.result_root),
        force=args.force,
        result_id=args.result_id,
        mode=args.mode,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if payload.get("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
