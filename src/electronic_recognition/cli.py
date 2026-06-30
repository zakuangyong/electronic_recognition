from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(prog="electronic-recognition")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8892)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    # NOTE: run single-process only. The default search backend uses an embedded
    # Qdrant store (data/search/qdrant) that allows just one process at a time,
    # so no `--workers` option is exposed here. For multi-worker deployments,
    # switch to a standalone Qdrant server (ER_SEARCH_QDRANT_MODE=remote).
    uvicorn.run(
        "electronic_recognition.api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
