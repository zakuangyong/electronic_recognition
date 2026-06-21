from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Settings:
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = ""
    render_dpi: int = 220
    max_pages: int = 12
    request_timeout: int = 180
    http_retries: int = 4
    response_cache_dir: str = "data/cache/model"
    catalog_candidate_limit: int = 20
    reference_batch_size: int = 12
    tile_grid: int = 2
    tile_overlap: float = 0.15
    open_recognition_concurrency: int = 2
    correction_batch_size: int = 12
    correction_candidate_limit: int = 8
    recognition_mode: str = "hybrid"

    @classmethod
    def from_env(
        cls, dotenv_path: str | Path | None = None
    ) -> "Settings":
        load_dotenv(dotenv_path)
        return cls(
            base_url=os.getenv(
                "ER_LLM_BASE_URL", "https://api.openai.com/v1"
            ),
            api_key=os.getenv("ER_LLM_API_KEY", ""),
            model=os.getenv("ER_LLM_MODEL", ""),
            render_dpi=int(os.getenv("ER_RENDER_DPI", "220")),
            max_pages=int(os.getenv("ER_MAX_PAGES", "12")),
            request_timeout=int(
                os.getenv("ER_REQUEST_TIMEOUT", "180")
            ),
            http_retries=int(os.getenv("ER_HTTP_RETRIES", "4")),
            response_cache_dir=os.getenv(
                "ER_RESPONSE_CACHE_DIR", "data/cache/model"
            ),
            catalog_candidate_limit=int(
                os.getenv("ER_CATALOG_CANDIDATE_LIMIT", "20")
            ),
            reference_batch_size=max(
                1,
                int(
                    os.getenv(
                        "ER_REFERENCE_BATCH_SIZE",
                        os.getenv("ER_REFERENCE_LIMIT", "12"),
                    )
                ),
            ),
            tile_grid=min(
                3,
                max(1, int(os.getenv("ER_TILE_GRID", "2"))),
            ),
            tile_overlap=max(
                0.0,
                min(0.45, float(os.getenv("ER_TILE_OVERLAP", "0.15"))),
            ),
            open_recognition_concurrency=max(
                1,
                min(
                    4,
                    int(
                        os.getenv(
                            "ER_OPEN_RECOGNITION_CONCURRENCY",
                            "2",
                        )
                    ),
                ),
            ),
            correction_batch_size=max(
                1,
                int(os.getenv("ER_CORRECTION_BATCH_SIZE", "12")),
            ),
            correction_candidate_limit=max(
                1,
                int(
                    os.getenv(
                        "ER_CORRECTION_CANDIDATE_LIMIT",
                        "8",
                    )
                ),
            ),
            recognition_mode=_recognition_mode(
                os.getenv("ER_RECOGNITION_MODE", "hybrid")
            ),
        )


def load_dotenv(path: str | Path | None = None) -> Path | None:
    target = _resolve_dotenv(path)
    if target is None:
        return None
    for raw_line in target.read_text(
        encoding="utf-8-sig"
    ).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {"'", '"'}
        ):
            value = value[1:-1]
        comment = value.find(" #")
        if comment >= 0:
            value = value[:comment]
        os.environ.setdefault(key.strip(), value.strip())
    return target


def _resolve_dotenv(path: str | Path | None) -> Path | None:
    if path:
        target = Path(path).expanduser().resolve()
        if not target.is_file():
            raise FileNotFoundError(target)
        return target
    for directory in (Path.cwd().resolve(), *Path.cwd().resolve().parents):
        candidate = directory / ".env"
        if candidate.is_file():
            return candidate
    return None


def _recognition_mode(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    return normalized if normalized in {
        "hybrid",
        "rag_first",
        "vision_first",
    } else "hybrid"
