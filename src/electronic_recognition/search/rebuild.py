from __future__ import annotations

import argparse
import json
from pathlib import Path

from electronic_recognition.config import Settings
from electronic_recognition.search.index_service import DrawingIndexService
from electronic_recognition.search.sqlite_store import DrawingSearchStore


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild the drawing search index from saved results."
    )
    parser.add_argument("--result-root", default="result")
    parser.add_argument("--db", default="")
    parser.add_argument("--result-id", default="")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--mode",
        default="all",
        choices=("all", "bm25", "vector"),
    )
    args = parser.parse_args()

    settings = Settings.from_env()
    service = _build_service(
        settings,
        Path(args.db or settings.search_sqlite_path),
    )
    payload = service.rebuild(
        Path(args.result_root),
        force=args.force,
        result_id=args.result_id,
        mode=args.mode,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if payload.get("failed") else 0


def _build_service(
    settings: Settings,
    db_path: Path,
) -> DrawingIndexService:
    try:
        from electronic_recognition.api import (
            PROJECT_ROOT,
            _embedding_backend,
            _index_service,
            _read_search_mapping,
            _vector_store,
        )

        configured_db = (
            PROJECT_ROOT / settings.search_sqlite_path
        ).resolve()
        if db_path.resolve() == configured_db:
            return _index_service(settings)
        return DrawingIndexService(
            DrawingSearchStore(
                db_path,
                score_weights=_read_search_mapping(
                    PROJECT_ROOT / settings.search_exact_boost_config
                ),
            ),
            embedding_backend=_embedding_backend(settings),
            vector_store=_vector_store(settings),
        )
    except AttributeError:
        return DrawingIndexService(DrawingSearchStore(db_path))


if __name__ == "__main__":
    raise SystemExit(main())
