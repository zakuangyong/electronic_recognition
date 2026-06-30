from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
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
    parser.add_argument(
        "--via-api",
        action="store_true",
        help=(
            "Rebuild through the running server's HTTP API instead of opening "
            "the store directly. Use this whenever the server is running — the "
            "embedded Qdrant store only allows one process at a time."
        ),
    )
    parser.add_argument(
        "--api-url",
        default="http://127.0.0.1:8892",
        help="Base URL of the running server when using --via-api.",
    )
    args = parser.parse_args()

    if args.via_api:
        payload = _rebuild_via_api(
            args.api_url,
            force=args.force,
            result_id=args.result_id,
            mode=args.mode,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1 if payload.get("failed") else 0

    settings = Settings.from_env()
    try:
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
    except Exception as exc:  # noqa: BLE001 - surfaced to the operator
        if _looks_like_qdrant_lock(exc):
            print(
                "无法打开本地向量库 data/search/qdrant：很可能服务正在运行并已"
                "占用该目录（嵌入式 Qdrant 同一时刻只允许一个进程）。\n"
                "请改用：python -m electronic_recognition.search.rebuild --via-api\n"
                f"原始错误：{exc}"
            )
            return 2
        raise
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if payload.get("failed") else 0


def _rebuild_via_api(
    api_url: str,
    *,
    force: bool,
    result_id: str,
    mode: str,
) -> dict[str, object]:
    url = api_url.rstrip("/") + "/api/search/rebuild"
    body = json.dumps(
        {"force": force, "result_id": result_id, "mode": mode}
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        return {
            "failed": [str(getattr(exc, "reason", exc))],
            "error": f"无法连接到服务 {url}，请确认服务已启动。",
        }


def _looks_like_qdrant_lock(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "already accessed" in text
        or "storage folder" in text
        or ".lock" in text
    )


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
