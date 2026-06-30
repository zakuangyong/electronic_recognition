from __future__ import annotations

import argparse
from pathlib import Path

from electronic_recognition.config import Settings


def main() -> int:
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(
        description=(
            "One-time online prefetch of the search embedding model into a "
            "local directory, so the app can run fully offline afterwards. "
            "Point ER_SEARCH_EMBEDDING_MODEL_PATH at the --target directory."
        )
    )
    parser.add_argument(
        "--model",
        default=settings.search_embedding_model,
        help="HuggingFace model id to download (default: ER_SEARCH_EMBEDDING_MODEL).",
    )
    parser.add_argument(
        "--target",
        default="",
        help=(
            "Local directory to save the self-contained model into. "
            "Defaults to data/models/<model-basename>."
        ),
    )
    parser.add_argument("--device", default=settings.search_embedding_device)
    args = parser.parse_args()

    target = Path(args.target) if args.target else (
        Path("data/models") / args.model.split("/")[-1]
    )
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("sentence-transformers 未安装，无法预取模型。请先安装依赖。")
        return 1

    print(f"下载并保存模型: {args.model} -> {target}")
    model = SentenceTransformer(args.model, device=args.device)
    model.save(str(target))
    print("完成。请在 .env 中设置：")
    print(f"  ER_SEARCH_EMBEDDING_MODEL_PATH={target.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
