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
    layout_routing_enabled: bool = True
    layout_router_mode: str = "rules"
    layout_model_path: str = ""
    layout_min_confidence: float = 0.45
    layout_fallback_to_grid: bool = True
    layout_save_region_images: bool = False
    scan_text_threshold: int = 40
    region_ocr_enabled: bool = True
    region_vlm_fallback_enabled: bool = True
    region_max_area_ratio: float = 0.65
    region_tile_overlap: float = 0.12
    search_enabled: bool = True
    search_sqlite_path: str = "data/search/drawings.db"
    search_qdrant_mode: str = "local"
    search_qdrant_path: str = "data/search/qdrant"
    search_qdrant_url: str = "http://127.0.0.1:6333"
    search_qdrant_api_key: str = ""
    search_collection: str = "electronic_drawing_chunks_demo_v2"
    search_embedding_backend: str = "sentence_transformers"
    search_embedding_model: str = "BAAI/bge-small-zh-v1.5"
    search_embedding_model_path: str = ""
    search_embedding_device: str = "cpu"
    search_embedding_batch_size: int = 8
    search_embedding_normalize: bool = True
    search_bm25_limit: int = 50
    search_vector_limit: int = 50
    search_rrf_k: int = 60
    search_result_limit: int = 20
    search_auto_index: bool = True
    search_deduplicate: bool = True
    search_exact_boost_config: str = "data/index/search_weights.json"
    search_synonyms_config: str = "data/index/search_synonyms.json"
    search_mode: str = "hybrid"

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
            layout_routing_enabled=_bool_env(
                "ER_LAYOUT_ROUTING_ENABLED", True
            ),
            layout_router_mode=_layout_router_mode(
                os.getenv("ER_LAYOUT_ROUTER_MODE", "rules")
            ),
            layout_model_path=os.getenv("ER_LAYOUT_MODEL_PATH", ""),
            layout_min_confidence=max(
                0.0,
                min(
                    1.0,
                    float(os.getenv("ER_LAYOUT_MIN_CONFIDENCE", "0.45")),
                ),
            ),
            layout_fallback_to_grid=_bool_env(
                "ER_LAYOUT_FALLBACK_TO_GRID", True
            ),
            layout_save_region_images=_bool_env(
                "ER_LAYOUT_SAVE_REGION_IMAGES", False
            ),
            scan_text_threshold=max(
                0,
                int(os.getenv("ER_SCAN_TEXT_THRESHOLD", "40")),
            ),
            region_ocr_enabled=_bool_env("ER_REGION_OCR_ENABLED", True),
            region_vlm_fallback_enabled=_bool_env(
                "ER_REGION_VLM_FALLBACK_ENABLED", True
            ),
            region_max_area_ratio=max(
                0.05,
                min(
                    1.0,
                    float(os.getenv("ER_REGION_MAX_AREA_RATIO", "0.65")),
                ),
            ),
            region_tile_overlap=max(
                0.0,
                min(
                    0.45,
                    float(os.getenv("ER_REGION_TILE_OVERLAP", "0.12")),
                ),
            ),
            search_enabled=_bool_env("ER_SEARCH_ENABLED", True),
            search_sqlite_path=os.getenv(
                "ER_SEARCH_SQLITE_PATH", "data/search/drawings.db"
            ),
            search_qdrant_mode=os.getenv(
                "ER_SEARCH_QDRANT_MODE", "local"
            ).strip().lower(),
            search_qdrant_path=os.getenv(
                "ER_SEARCH_QDRANT_PATH", "data/search/qdrant"
            ),
            search_qdrant_url=os.getenv(
                "ER_SEARCH_QDRANT_URL", "http://127.0.0.1:6333"
            ),
            search_qdrant_api_key=os.getenv("ER_SEARCH_QDRANT_API_KEY", ""),
            search_collection=os.getenv(
                "ER_SEARCH_COLLECTION",
                "electronic_drawing_chunks_demo_v2",
            ),
            search_embedding_backend=os.getenv(
                "ER_SEARCH_EMBEDDING_BACKEND", "sentence_transformers"
            ).strip().lower(),
            search_embedding_model=os.getenv(
                "ER_SEARCH_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5"
            ),
            search_embedding_model_path=os.getenv(
                "ER_SEARCH_EMBEDDING_MODEL_PATH", ""
            ),
            search_embedding_device=os.getenv(
                "ER_SEARCH_EMBEDDING_DEVICE", "cpu"
            ),
            search_embedding_batch_size=max(
                1,
                int(os.getenv("ER_SEARCH_EMBEDDING_BATCH_SIZE", "8")),
            ),
            search_embedding_normalize=_bool_env(
                "ER_SEARCH_EMBEDDING_NORMALIZE", True
            ),
            search_bm25_limit=max(
                1, int(os.getenv("ER_SEARCH_BM25_LIMIT", "50"))
            ),
            search_vector_limit=max(
                1, int(os.getenv("ER_SEARCH_VECTOR_LIMIT", "50"))
            ),
            search_rrf_k=max(
                1, int(os.getenv("ER_SEARCH_RRF_K", "60"))
            ),
            search_result_limit=max(
                1, int(os.getenv("ER_SEARCH_RESULT_LIMIT", "20"))
            ),
            search_auto_index=_bool_env("ER_SEARCH_AUTO_INDEX", True),
            search_deduplicate=_bool_env("ER_SEARCH_DEDUPLICATE", True),
            search_exact_boost_config=os.getenv(
                "ER_SEARCH_EXACT_BOOST_CONFIG",
                "data/index/search_weights.json",
            ),
            search_synonyms_config=os.getenv(
                "ER_SEARCH_SYNONYMS_CONFIG",
                "data/index/search_synonyms.json",
            ),
            search_mode=_search_mode(os.getenv("ER_SEARCH_MODE", "hybrid")),
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


def _layout_router_mode(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    return normalized if normalized in {
        "rules",
        "detector",
        "hybrid",
        "disabled",
    } else "rules"


def _search_mode(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    return normalized if normalized in {
        "bm25",
        "vector",
        "hybrid",
        "disabled",
    } else "bm25"


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
