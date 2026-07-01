from __future__ import annotations

import atexit
import base64
import io
import json
import re
import shutil
import threading
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image

from .config import Settings
from .combination_rules import detect_combinations
from .custom_rules import CustomRuleKnowledgeBase
from .knowledge import ComponentKnowledgeBase
from .custom_rule_store import (
    BuiltinRuleReadonlyError,
    ComponentReferencedError,
    CustomRuleStore,
    InvalidRulePayloadError,
    RuleAlreadyExistsError,
    RuleNotFoundError,
)
from .knowledge_store import (
    ComponentAlreadyExistsError,
    ComponentNotFoundError,
    InvalidComponentPayloadError,
    InvalidImageError,
    KnowledgeStore,
)
from .pipeline import RecognitionPipeline
from .search.embedding import (
    DisabledEmbeddingBackend,
    SentenceTransformerEmbeddingBackend,
)
from .search.index_service import DrawingIndexService
from .search.qdrant_store import QdrantVectorStore
from .search.query_parser import QueryParser
from .search.search_service import DrawingSearchService
from .search.sqlite_store import DrawingSearchStore
from .diff.response import build_diff_result_payload
from .diff.service import DrawingDiffService
from .diff.storage import DiffJobStorage
from .runtime import project_root, web_dist_dir


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # Warm up the search stack off the event loop so a slow model load / offline
    # retry never blocks startup; health reports degraded until it finishes.
    threading.Thread(
        target=_run_search_warmup,
        name="search-warmup",
        daemon=True,
    ).start()
    yield


app = FastAPI(
    title="Electronic Recognition",
    version="0.1.0",
    lifespan=_lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = project_root()
KNOWLEDGE_PATH = PROJECT_ROOT / "data" / "index" / "components.json"
CUSTOM_RULES_PATH = PROJECT_ROOT / "data" / "index" / "custom_rules.json"
SEARCH_DEMO_QUERIES_PATH = PROJECT_ROOT / "data" / "search" / "demo_queries.json"
RESULT_DIR = PROJECT_ROOT / "result"
DIFF_JOB_DIR = PROJECT_ROOT / "data" / "diff" / "jobs"
RESULT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.\-\u4e00-\u9fff]+$")
ACTIVE_RESULT_IDS: set[str] = set()
ACTIVE_RESULT_IDS_LOCK = threading.Lock()
SEARCH_RUNTIME_LOCK = threading.RLock()
EMBEDDING_BACKENDS: dict[tuple[object, ...], object] = {}
QDRANT_CLIENTS: dict[tuple[object, ...], object] = {}
# Serializes every operation on the shared embedded-Qdrant client. QdrantLocal
# is not concurrency-safe, so the background auto-index thread and request
# threads must take turns. Reentrant so a single op can ensure_collection then
# upsert/search without self-deadlock.
QDRANT_OP_LOCK = threading.RLock()
# Set by the startup warmup when search cannot be brought up (model download,
# stale Qdrant lock, etc.). Surfaced via /api/search/health so the UI degrades
# instead of the whole app failing.
SEARCH_WARMUP_ERROR = ""
STEP_FILES = {
    "recognition_log": "steps/00-recognition-log.json",
    "title_block": "steps/01-title-block.json",
    "control_signal_configuration": (
        "steps/02-control-signal-configuration.json"
    ),
    "component_table": "steps/03-component-table.json",
    "page_quality": "steps/01-page-quality.json",
    "layout_regions": "steps/02-layout-regions.json",
    "structured_region_extraction": "steps/03-structured-regions.json",
    "open_symbols": "steps/04-open-symbols.json",
    "open_recognition_tiles": "steps/04-open-recognition-tiles.json",
    "open_categories": "steps/04-open-categories.json",
    "rag_corrections": "steps/05-rag-corrections.json",
    "detected_components": "steps/06-detected-components.json",
    "detected_combinations": "steps/06-detected-combinations.json",
    "preview_pages": "steps/07-preview-pages.json",
    "warnings": "steps/08-warnings.json",
    "meta": "steps/09-meta.json",
    "document": "steps/00-document.json",
    "legacy_detected_components": "steps/04-detected-components.json",
}


def _close_search_clients() -> None:
    with SEARCH_RUNTIME_LOCK:
        clients = list(QDRANT_CLIENTS.values())
        QDRANT_CLIENTS.clear()
    for client in clients:
        close = getattr(client, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass


atexit.register(_close_search_clients)


def _run_search_warmup() -> None:
    """Eagerly bring up the search stack so the first query is fast and so
    startup problems (model download, stale embedded-Qdrant lock) surface via
    health instead of failing the app. Runs in a daemon thread; never raises.
    """
    global SEARCH_WARMUP_ERROR
    try:
        settings = Settings.from_env()
    except Exception as exc:  # pragma: no cover - defensive
        SEARCH_WARMUP_ERROR = f"settings: {exc}"
        return
    if not settings.search_enabled or settings.search_mode == "disabled":
        return
    try:
        _search_store(settings).initialize()
    except Exception as exc:
        SEARCH_WARMUP_ERROR = f"sqlite: {exc}"
        return
    try:
        backend = _embedding_backend(settings)
        if getattr(backend, "model_id", "") not in ("", "disabled"):
            backend.embed_query("warmup")
    except Exception as exc:
        SEARCH_WARMUP_ERROR = f"embedding: {exc}"
        return
    try:
        vector_store = _vector_store(settings)
        if vector_store is not None:
            vector_store.ping()
    except Exception as exc:
        SEARCH_WARMUP_ERROR = (
            f"qdrant: {exc} —— 可能是 data/search/qdrant 被其他进程占用或存在"
            " 残留 .lock，请确认仅有一个服务进程后清理锁文件。"
        )
        return
    SEARCH_WARMUP_ERROR = ""


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/search")
def search_drawings(payload: dict[str, Any]) -> dict[str, object]:
    settings = Settings.from_env()
    if not settings.search_enabled or settings.search_mode == "disabled":
        raise HTTPException(
            503,
            _error_detail("search_disabled", "Search is disabled."),
        )
    query = str(payload.get("query", "")).strip()
    if not query:
        raise HTTPException(
            400,
            _error_detail("empty_query", "Search query is required."),
        )
    try:
        limit = int(payload.get("limit") or settings.search_result_limit)
        offset = int(payload.get("offset") or 0)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            400,
            _error_detail("invalid_pagination", "Invalid search pagination."),
        ) from exc
    filters = payload.get("filters", {})
    if not isinstance(filters, dict):
        filters = {}
    try:
        return _search_service(settings).search(
            query,
            limit=max(1, min(100, limit)),
            offset=max(0, offset),
            filters=filters,
            debug=bool(payload.get("debug", False)),
            retrieval_mode=str(payload.get("retrieval_mode", "")).strip() or None,
        )
    except Exception as exc:
        raise HTTPException(
            500,
            _error_detail("search_failed", str(exc)),
        ) from exc


@app.get("/api/search/health")
def search_health() -> dict[str, object]:
    settings = Settings.from_env()
    if not settings.search_enabled or settings.search_mode == "disabled":
        return {"enabled": False, "degraded": True, "status": "disabled"}
    try:
        status = _search_service(settings).health()
    except Exception as exc:
        raise HTTPException(
            500,
            _error_detail("search_health_failed", str(exc)),
        ) from exc
    status["enabled"] = True
    # Fold the startup warmup outcome in: if warmup failed (model download,
    # stale embedded-Qdrant lock, ...) report degraded with the reason even
    # when the lazy health probe happened to succeed.
    if SEARCH_WARMUP_ERROR:
        status["degraded"] = True
        status["warmup_error"] = SEARCH_WARMUP_ERROR
    return status


@app.get("/api/search/demo-queries")
def search_demo_queries() -> dict[str, object]:
    if not SEARCH_DEMO_QUERIES_PATH.is_file():
        return {}
    payload = json.loads(SEARCH_DEMO_QUERIES_PATH.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


@app.post("/api/search/index/{result_id}")
def index_search_result(result_id: str) -> dict[str, object]:
    settings = Settings.from_env()
    if not settings.search_enabled:
        raise HTTPException(503, "Search is disabled.")
    result_dir = _result_path(result_id)
    try:
        payload = _index_service(settings).index_result(
            result_id,
            result_dir,
            mode="all",
        )
    except FileNotFoundError as exc:
        raise HTTPException(404, "Recognition result does not exist.") from exc
    except Exception as exc:
        _set_manifest_index_status(result_dir, "failed", str(exc))
        raise HTTPException(500, str(exc)) from exc
    _set_manifest_index_status(result_dir, "complete", "")
    return payload


@app.delete("/api/search/index/{result_id}")
def delete_search_result_index(result_id: str) -> dict[str, object]:
    settings = Settings.from_env()
    payload = _index_service(settings).delete_result(result_id)
    result_dir = _result_path(result_id)
    if result_dir.is_dir():
        _set_manifest_index_status(result_dir, "deleted", "")
    return payload


@app.post("/api/search/rebuild")
def rebuild_search_index(payload: dict[str, Any] | None = None) -> dict[str, object]:
    settings = Settings.from_env()
    if not settings.search_enabled:
        raise HTTPException(
            503,
            _error_detail("search_disabled", "Search is disabled."),
        )
    payload = payload or {}
    try:
        return _index_service(settings).rebuild(
            RESULT_DIR,
            force=bool(payload.get("force", False)),
            result_id=str(payload.get("result_id", "")).strip(),
            mode=str(payload.get("mode", "all")).strip() or "all",
        )
    except Exception as exc:
        raise HTTPException(
            500,
            _error_detail("search_rebuild_failed", str(exc)),
        ) from exc


@app.get("/api/search/index-status")
def search_index_status() -> dict[str, object]:
    settings = Settings.from_env()
    return _search_store(settings).status()


@app.get("/api/search/index-status/{result_id}")
def search_result_index_status(result_id: str) -> dict[str, object]:
    settings = Settings.from_env()
    return _search_store(settings).result_status(result_id)


@app.post("/api/diff/compare")
async def compare_drawings(
    old_file: UploadFile = File(...),
    new_file: UploadFile = File(...),
    file_type: str = Form(...),
    dpi: int = Form(300),
    threshold: int = Form(25),
) -> dict[str, object]:
    normalized_type = _normalize_diff_file_type(file_type)
    old_name = old_file.filename or "old_file"
    new_name = new_file.filename or "new_file"
    if normalized_type is None:
        return _diff_error_response(
            "validation",
            "invalid file_type",
            status=False,
        )
    if Path(old_name).suffix.lower() != Path(new_name).suffix.lower():
        return _diff_error_response(
            "validation",
            "file extensions must match",
            status=False,
        )
    if not _diff_extension_matches(normalized_type, old_name):
        return _diff_error_response(
            "validation",
            "file extension does not match file_type",
            status=False,
        )

    job = _diff_storage().create_job()
    old_path, new_path = _diff_storage().save_uploads(
        job,
        old_name,
        await old_file.read(),
        new_name,
        await new_file.read(),
    )
    try:
        _diff_service().run_compare(
            job=job,
            old_source=old_path,
            new_source=new_path,
            file_type=normalized_type,
            dpi=max(72, min(1200, int(dpi))),
            threshold=max(0, min(255, int(threshold))),
        )
    except Exception as exc:
        return _diff_error_response(
            "pipeline",
            str(exc),
            job_id=job.job_id,
            status=False,
        )
    return _diff_success_response(job.job_id, build_diff_result_payload(job))


@app.get("/api/diff/results/{job_id}")
def get_diff_result(job_id: str) -> dict[str, object]:
    job = _diff_storage().get_existing_job(job_id)
    if job is None:
        raise HTTPException(
            404,
            _error_detail("diff_job_not_found", "Diff job not found."),
        )
    try:
        payload = build_diff_result_payload(job)
    except FileNotFoundError as exc:
        raise HTTPException(
            404,
            _error_detail("diff_result_not_found", "Diff result not found."),
        ) from exc
    return _diff_success_response(job.job_id, payload)


@app.get("/api/diff/files/{job_id}/{filename:path}")
def get_diff_file(job_id: str, filename: str) -> FileResponse:
    job = _diff_storage().get_existing_job(job_id)
    if job is None:
        raise HTTPException(
            404,
            _error_detail("diff_job_not_found", "Diff job not found."),
        )
    path = _diff_storage().resolve_file(job, filename)
    if path is None:
        raise HTTPException(
            404,
            _error_detail("diff_file_not_found", "Diff file not found."),
        )
    return FileResponse(path)


@app.get("/api/config")
def config() -> dict[str, object]:
    settings = Settings.from_env()
    count = 0
    custom_rule_count = 0
    if KNOWLEDGE_PATH.is_file():
        count = len(ComponentKnowledgeBase.load(KNOWLEDGE_PATH).components)
    if CUSTOM_RULES_PATH.is_file():
        custom_rule_count = len(
            CustomRuleKnowledgeBase.load(CUSTOM_RULES_PATH).rules
        )
    return {
        "model": settings.model,
        "api_key_configured": bool(settings.api_key),
        "knowledge_path": str(KNOWLEDGE_PATH),
        "component_count": count,
        "custom_rules_path": str(CUSTOM_RULES_PATH),
        "custom_rule_count": custom_rule_count,
        "reference_batch_size": settings.reference_batch_size,
        "recognition_mode": settings.recognition_mode,
        "layout_routing_enabled": settings.layout_routing_enabled,
        "layout_router_mode": settings.layout_router_mode,
        "search_enabled": settings.search_enabled,
        "search_mode": settings.search_mode,
        "search_auto_index": settings.search_auto_index,
        "open_recognition_concurrency": (
            settings.open_recognition_concurrency
        ),
        "correction_batch_size": settings.correction_batch_size,
        "correction_candidate_limit": (
            settings.correction_candidate_limit
        ),
    }


@app.get("/api/custom-rules")
def custom_rule_items() -> dict[str, object]:
    if not CUSTOM_RULES_PATH.is_file():
        return {"count": 0, "items": []}
    rule_base = CustomRuleKnowledgeBase.load(CUSTOM_RULES_PATH)
    return {
        "count": len(rule_base.rules),
        "items": [
            {
                "id": rule.id,
                "name": rule.name,
                "description": rule.description,
                "engine": rule.engine,
                "enabled": rule.enabled,
                "scope": rule.scope,
                "member_count": len(rule.members),
                "image_url": (
                    f"/api/custom-rules/{rule.id}/image"
                    if rule.image_path
                    else ""
                ),
            }
            for rule in rule_base.rules
        ],
    }


@app.get("/api/custom-rules/{rule_id}")
def custom_rule_detail(rule_id: str) -> dict[str, object]:
    store = CustomRuleStore(CUSTOM_RULES_PATH)
    try:
        rule = store.get_rule(rule_id)
    except RuleNotFoundError as exc:
        raise HTTPException(404, _error_detail("not_found", "组合元件不存在。")) from exc
    return _serialize_rule(rule, store.load().root_dir)


@app.get("/api/custom-rules/{rule_id}/image")
def custom_rule_image(rule_id: str) -> FileResponse:
    if not CUSTOM_RULES_PATH.is_file():
        raise HTTPException(404, "自定义规则库不存在。")
    rule_base = CustomRuleKnowledgeBase.load(CUSTOM_RULES_PATH)
    rule = rule_base.by_id.get(rule_id)
    if not rule:
        raise HTTPException(404, "自定义规则不存在。")
    image_path = rule_base.image_path(rule).resolve()
    root = rule_base.root_dir.resolve()
    if root not in image_path.parents:
        raise HTTPException(403, "自定义规则图片路径不合法。")
    if not image_path.is_file():
        raise HTTPException(404, "自定义规则图片不存在。")
    return FileResponse(image_path)


@app.post("/api/custom-rules")
def create_custom_rule(payload: dict[str, Any]) -> dict[str, object]:
    store = CustomRuleStore(CUSTOM_RULES_PATH)
    try:
        rule = store.create_rule(payload)
    except RuleAlreadyExistsError as exc:
        raise HTTPException(409, _error_detail("duplicate_id", "组合元件 ID 已存在。")) from exc
    except InvalidRulePayloadError as exc:
        raise HTTPException(400, _error_detail("invalid_payload", str(exc))) from exc
    return _serialize_rule(rule, store.load().root_dir)


@app.put("/api/custom-rules/{rule_id}")
def update_custom_rule(
    rule_id: str,
    payload: dict[str, Any],
) -> dict[str, object]:
    store = CustomRuleStore(CUSTOM_RULES_PATH)
    try:
        rule = store.update_rule(rule_id, payload)
    except RuleNotFoundError as exc:
        raise HTTPException(404, _error_detail("not_found", "组合元件不存在。")) from exc
    except BuiltinRuleReadonlyError as exc:
        raise HTTPException(403, _error_detail("builtin_rule_readonly", "内置组合元件不允许修改。")) from exc
    except InvalidRulePayloadError as exc:
        raise HTTPException(400, _error_detail("invalid_payload", str(exc))) from exc
    return _serialize_rule(rule, store.load().root_dir)


@app.patch("/api/custom-rules/{rule_id}/enabled")
def patch_custom_rule_enabled(
    rule_id: str,
    payload: dict[str, Any],
) -> dict[str, object]:
    store = CustomRuleStore(CUSTOM_RULES_PATH)
    try:
        rule = store.set_rule_enabled(rule_id, bool(payload.get("enabled", True)))
    except RuleNotFoundError as exc:
        raise HTTPException(404, _error_detail("not_found", "组合元件不存在。")) from exc
    return _serialize_rule(rule, store.load().root_dir)


@app.delete("/api/custom-rules/{rule_id}")
def delete_custom_rule(rule_id: str) -> dict[str, object]:
    store = CustomRuleStore(CUSTOM_RULES_PATH)
    try:
        store.delete_rule(rule_id)
    except RuleNotFoundError as exc:
        raise HTTPException(404, _error_detail("not_found", "组合元件不存在。")) from exc
    except BuiltinRuleReadonlyError as exc:
        raise HTTPException(403, _error_detail("builtin_rule_readonly", "内置组合元件不允许删除。")) from exc
    return {"ok": True}


@app.post("/api/custom-rules/{rule_id}/image")
def upload_custom_rule_image(
    rule_id: str,
    file: UploadFile = File(...),
) -> dict[str, object]:
    store = CustomRuleStore(CUSTOM_RULES_PATH)
    try:
        rule = store.update_rule_image(
            rule_id,
            file.file.read(),
            file.filename or "rule.png",
        )
    except RuleNotFoundError as exc:
        raise HTTPException(404, _error_detail("not_found", "组合元件不存在。")) from exc
    except BuiltinRuleReadonlyError as exc:
        raise HTTPException(403, _error_detail("builtin_rule_readonly", "内置组合元件不允许上传图片。")) from exc
    except InvalidRulePayloadError as exc:
        raise HTTPException(400, _error_detail("invalid_image", str(exc))) from exc
    return _serialize_rule(rule, store.load().root_dir)


@app.post("/api/custom-rules/validate")
def validate_custom_rule(payload: dict[str, Any]) -> dict[str, object]:
    store = CustomRuleStore(CUSTOM_RULES_PATH)
    try:
        return store.validate_rule(payload)
    except InvalidRulePayloadError as exc:
        raise HTTPException(400, _error_detail("invalid_payload", str(exc))) from exc


@app.post("/api/custom-rules/test")
def test_custom_rule(payload: dict[str, Any]) -> dict[str, object]:
    store = CustomRuleStore(CUSTOM_RULES_PATH)
    try:
        return store.test_rule(
            payload.get("rule", payload),
            detected_components=list(payload.get("detected_components", [])),
            open_symbols=list(payload.get("open_symbols", [])),
        )
    except InvalidRulePayloadError as exc:
        raise HTTPException(400, _error_detail("invalid_payload", str(exc))) from exc


@app.get("/api/knowledge")
def knowledge_items() -> dict[str, object]:
    if not KNOWLEDGE_PATH.is_file():
        raise HTTPException(500, "组件知识库不存在。")
    knowledge = ComponentKnowledgeBase.load(KNOWLEDGE_PATH)
    return {
        "count": len(knowledge.components),
        "items": [
            _serialize_component(sample, knowledge.root_dir)
            for sample in knowledge.components
        ],
    }

@app.get("/api/knowledge/{component_id}")
def knowledge_detail(component_id: str) -> dict[str, object]:
    store = KnowledgeStore(KNOWLEDGE_PATH)
    try:
        sample = store.get_component(component_id)
    except ComponentNotFoundError as exc:
        raise HTTPException(404, _error_detail("not_found", "组件不存在。")) from exc
    return _serialize_component(sample, store.root_dir)



@app.get("/api/knowledge/{component_id}/image")
def knowledge_image(component_id: str) -> FileResponse:
    if not KNOWLEDGE_PATH.is_file():
        raise HTTPException(500, "组件知识库不存在。")
    knowledge = ComponentKnowledgeBase.load(KNOWLEDGE_PATH)
    sample = knowledge.by_id.get(component_id)
    if not sample:
        raise HTTPException(404, "组件不存在。")
    image_path = knowledge.image_path(sample).resolve()
    root = knowledge.root_dir.resolve()
    if root not in image_path.parents:
        raise HTTPException(403, "组件图片路径不合法。")
    if not image_path.is_file():
        raise HTTPException(404, "组件图片不存在。")
    return FileResponse(image_path)


@app.get("/api/knowledge/{component_id}/images/{image_id}")
def knowledge_variant_image(
    component_id: str,
    image_id: str,
) -> FileResponse:
    store = KnowledgeStore(KNOWLEDGE_PATH)
    try:
        sample = store.get_component(component_id)
    except ComponentNotFoundError as exc:
        raise HTTPException(404, _error_detail("not_found", "组件不存在。")) from exc
    try:
        index = int(image_id)
    except ValueError as exc:
        raise HTTPException(404, _error_detail("not_found", "组件图片不存在。")) from exc
    if index < 0 or index >= len(sample.variant_images):
        raise HTTPException(404, _error_detail("not_found", "组件图片不存在。"))
    image_path = (store.root_dir / sample.variant_images[index]).resolve()
    root = store.root_dir.resolve()
    if root not in image_path.parents:
        raise HTTPException(403, _error_detail("invalid_image", "组件图片路径不合法。"))
    if not image_path.is_file():
        raise HTTPException(404, _error_detail("not_found", "组件图片不存在。"))
    return FileResponse(image_path)


@app.post("/api/knowledge")
def create_knowledge_item(payload: dict[str, Any]) -> dict[str, object]:
    store = KnowledgeStore(KNOWLEDGE_PATH)
    try:
        sample = store.create_component(payload)
    except ComponentAlreadyExistsError as exc:
        raise HTTPException(409, _error_detail("duplicate_id", "组件 ID 已存在。")) from exc
    except InvalidComponentPayloadError as exc:
        raise HTTPException(400, _error_detail("invalid_payload", str(exc))) from exc
    return _serialize_component(sample, store.root_dir)


@app.put("/api/knowledge/{component_id}")
def update_knowledge_item(
    component_id: str,
    payload: dict[str, Any],
) -> dict[str, object]:
    store = KnowledgeStore(KNOWLEDGE_PATH)
    try:
        sample = store.update_component(component_id, payload)
    except ComponentNotFoundError as exc:
        raise HTTPException(404, _error_detail("not_found", "组件不存在。")) from exc
    except InvalidComponentPayloadError as exc:
        raise HTTPException(400, _error_detail("invalid_payload", str(exc))) from exc
    return _serialize_component(sample, store.root_dir)


@app.delete("/api/knowledge/{component_id}")
def delete_knowledge_item(component_id: str) -> dict[str, object]:
    rule_store = CustomRuleStore(CUSTOM_RULES_PATH)
    component_store = KnowledgeStore(KNOWLEDGE_PATH)
    try:
        rule_store.assert_component_not_referenced(component_id)
        component_store.delete_component(component_id)
    except ComponentReferencedError as exc:
        raise HTTPException(
            409,
            _error_detail(
                "component_referenced",
                "该单元件已被组合元件引用，无法删除。",
                references=exc.references,
            ),
        ) from exc
    except ComponentNotFoundError as exc:
        raise HTTPException(404, _error_detail("not_found", "组件不存在。")) from exc
    return {"ok": True}


@app.post("/api/knowledge/{component_id}/images")
def upload_knowledge_image(
    component_id: str,
    file: UploadFile = File(...),
    kind: str = Form("variant"),
) -> dict[str, object]:
    store = KnowledgeStore(KNOWLEDGE_PATH)
    try:
        sample = store.add_component_image(
            component_id,
            file.file.read(),
            file.filename or "image.png",
            kind=kind,
        )
    except ComponentNotFoundError as exc:
        raise HTTPException(404, _error_detail("not_found", "组件不存在。")) from exc
    except (InvalidComponentPayloadError, InvalidImageError) as exc:
        raise HTTPException(400, _error_detail("invalid_image", str(exc))) from exc
    return _serialize_component(sample, store.root_dir)


@app.delete("/api/knowledge/{component_id}/images/{image_id}")
def delete_knowledge_image(
    component_id: str,
    image_id: str,
) -> dict[str, object]:
    store = KnowledgeStore(KNOWLEDGE_PATH)
    try:
        sample = store.remove_component_image(component_id, image_id)
    except ComponentNotFoundError as exc:
        raise HTTPException(404, _error_detail("not_found", "组件不存在。")) from exc
    except InvalidComponentPayloadError as exc:
        raise HTTPException(400, _error_detail("invalid_payload", str(exc))) from exc
    return _serialize_component(sample, store.root_dir)


@app.post("/analyze")
def analyze(
    drawing: UploadFile = File(...),
) -> dict[str, object]:
    filename = _safe_filename(drawing.filename or "")
    suffix = Path(filename).suffix.lower()
    if suffix not in {".pdf", ".png"}:
        raise HTTPException(400, "仅支持 PDF 或 PNG 格式。")
    if not KNOWLEDGE_PATH.is_file():
        raise HTTPException(500, "组件知识库不存在。")

    result_id = _result_id_for_filename(filename)
    _reserve_result_id(result_id)
    try:
        settings = Settings.from_env()
        _remove_existing_search_index(result_id, settings)
        result_id, result_dir = _create_result_dir(filename)
        input_path = _persist_input(drawing, filename, result_dir)
        work_dir = result_dir
        _write_initial_manifest(
            result_id=result_id,
            result_dir=result_dir,
            input_path=input_path,
            status="running",
        )
        worker = threading.Thread(
            target=_run_analysis_job,
            kwargs={
                "result_id": result_id,
                "result_dir": result_dir,
                "input_path": input_path,
                "work_dir": work_dir,
            },
            name=f"recognition-{result_id}",
            daemon=True,
        )
        worker.start()
    except Exception:
        _release_result_id(result_id)
        raise
    return {
        "task_id": result_id,
        "result_id": result_id,
        "status": "running",
        "result_url": f"/results/{result_id}",
        "steps_url": f"/api/results/{result_id}/steps",
    }


@app.get("/api/results/{result_id}")
def saved_result(result_id: str) -> dict[str, object]:
    result_dir = _result_path(result_id)
    result_path = result_dir / "result.json"
    if not result_path.is_file() and (result_dir / "error.json").is_file():
        error_payload = json.loads(
            (result_dir / "error.json").read_text(encoding="utf-8")
        )
        manifest_payload = (
            json.loads(
                (result_dir / "manifest.json").read_text(encoding="utf-8")
            )
            if (result_dir / "manifest.json").is_file()
            else {}
        )
        message = ""
        if isinstance(error_payload.get("error"), dict):
            message = str(error_payload["error"].get("message", ""))
        return {
            "result_id": result_id,
            "document": (
                error_payload.get("document")
                or manifest_payload.get("document")
                or result_id
            ),
            "status": "failed",
            "detected_components": [],
            "detected_combinations": [],
            "title_block": {},
            "control_signal_configuration": {},
            "component_table": {},
            "recognition_steps": {},
            "warnings": [message] if message else [],
            "meta": {},
            "error": error_payload,
            "manifest": manifest_payload,
        }
    if not result_path.is_file():
        # The result has not been produced yet. If the analysis job is still
        # running (the initial manifest exists), report its running status with
        # HTTP 200 so clients can keep polling instead of treating the
        # in-progress window as a fatal error.
        manifest_path = result_dir / "manifest.json"
        if manifest_path.is_file():
            try:
                manifest_payload = json.loads(
                    manifest_path.read_text(encoding="utf-8")
                )
            except json.JSONDecodeError:
                manifest_payload = {}
            if isinstance(manifest_payload, dict):
                status = str(manifest_payload.get("status", "running"))
                if status not in {"complete", "failed"}:
                    return {
                        "result_id": result_id,
                        "document": (
                            manifest_payload.get("document") or result_id
                        ),
                        "status": status,
                        "detected_components": [],
                        "detected_combinations": [],
                        "title_block": {},
                        "control_signal_configuration": {},
                        "component_table": {},
                        "recognition_steps": {},
                        "warnings": [],
                        "meta": {},
                        "manifest": manifest_payload,
                    }
        raise HTTPException(404, "Recognition result does not exist.")
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(500, "Recognition result is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(500, "Recognition result must be an object.")
    # A persisted result.json only exists on success, so surface the terminal
    # "complete" status the frontend polls for (it is not part of the
    # RecognitionResult payload itself).
    payload.setdefault("status", "complete")
    if "detected_combinations" not in payload:
        steps = payload.get("recognition_steps", {})
        payload["detected_combinations"] = detect_combinations(
            payload.get("detected_components", []),
            open_symbols=(
                steps.get("open_symbols", [])
                if isinstance(steps, dict)
                else []
            ),
            component_table=payload.get("component_table", {}),
            title_block=payload.get("title_block", {}),
            control_signal_configuration=payload.get(
                "control_signal_configuration", {}
            ),
            custom_rules=(
                CustomRuleKnowledgeBase.load(CUSTOM_RULES_PATH)
                if CUSTOM_RULES_PATH.is_file()
                else None
            ),
        )
    return payload


@app.get("/api/results/{result_id}/manifest")
def result_manifest(result_id: str) -> dict[str, object]:
    manifest_path = _result_path(result_id) / "manifest.json"
    if not manifest_path.is_file():
        raise HTTPException(404, "Recognition result manifest does not exist.")
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(500, "Recognition manifest is not valid JSON.") from exc


@app.get("/api/results/{result_id}/preview-file")
def result_preview_file(result_id: str) -> FileResponse:
    result_dir = _result_path(result_id)
    preview_path = _resolve_result_preview_file(result_dir)
    if preview_path is None:
        raise HTTPException(404, "Recognition preview file does not exist.")
    return FileResponse(preview_path)


@app.get("/api/results/{result_id}/preview-page/{page}")
def result_preview_page(result_id: str, page: int) -> FileResponse:
    result_dir = _result_path(result_id)
    preview_path = _resolve_result_preview_page(result_dir, page)
    if preview_path is None:
        raise HTTPException(404, "Recognition preview page does not exist.")
    return FileResponse(preview_path)


@app.get("/api/results/{result_id}/steps")
def result_steps(result_id: str) -> dict[str, object]:
    result_dir = _result_path(result_id)
    if not result_dir.is_dir():
        raise HTTPException(404, "Recognition result does not exist.")
    manifest_path = result_dir / "manifest.json"
    manifest: dict[str, object] = {}
    if manifest_path.is_file():
        try:
            loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                manifest = loaded
        except json.JSONDecodeError as exc:
            raise HTTPException(
                500, "Recognition manifest is not valid JSON."
            ) from exc
    steps, files, missing = _read_step_payloads(result_dir, manifest)
    return {
        "result_id": result_id,
        "status": manifest.get("status", "unknown"),
        "steps": steps,
        "files": files,
        "missing": missing,
    }


@app.get("/api/results/{result_id}/error")
def result_error(result_id: str) -> dict[str, object]:
    error_path = _result_path(result_id) / "error.json"
    if not error_path.is_file():
        raise HTTPException(404, "Recognition error does not exist.")
    try:
        return json.loads(error_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(500, "Recognition error is not valid JSON.") from exc


def _create_result_dir(filename: str) -> tuple[str, Path]:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    result_id = _result_id_for_filename(filename)
    result_dir = (RESULT_DIR / result_id).resolve()
    root = RESULT_DIR.resolve()
    if result_dir.parent != root:
        raise HTTPException(403, "Invalid result path.")
    if result_dir.exists():
        shutil.rmtree(result_dir)
    result_dir.mkdir()
    return result_id, result_dir


def _safe_filename(name: str) -> str:
    """Recover the real UTF-8 filename from an upload.

    Starlette decodes multipart filenames as latin-1, so a UTF-8 (e.g. Chinese)
    filename arrives mojibake'd. If re-encoding latin-1 -> utf-8 yields valid
    text, use it; otherwise keep the original. Idempotent for plain-ASCII names.
    """
    if not name:
        return name
    try:
        recovered = name.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name
    if recovered == name:
        return name
    # Prefer the recovered form only when it actually changes pure-latin1 bytes
    # into multibyte UTF-8 text (i.e. the original was mangled non-ASCII).
    return recovered


def _result_id_for_filename(filename: str) -> str:
    source_name = Path(filename or "drawing").name or "drawing"
    source_name = Path(source_name).stem or source_name
    safe_name = re.sub(
        r"[^A-Za-z0-9_.\-\u4e00-\u9fff]+",
        "_",
        source_name,
    ).strip("._-")
    return safe_name[:120] or "drawing"


def _reserve_result_id(result_id: str) -> None:
    with ACTIVE_RESULT_IDS_LOCK:
        if result_id in ACTIVE_RESULT_IDS:
            raise HTTPException(
                409,
                "同名图纸正在识别，请等待当前任务完成后再重新上传。",
            )
        ACTIVE_RESULT_IDS.add(result_id)


def _release_result_id(result_id: str) -> None:
    with ACTIVE_RESULT_IDS_LOCK:
        ACTIVE_RESULT_IDS.discard(result_id)


def _persist_input(
    drawing: UploadFile,
    filename: str,
    result_dir: Path,
) -> Path:
    input_dir = result_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    input_path = input_dir / Path(filename).name
    with input_path.open("wb") as output:
        shutil.copyfileobj(drawing.file, output)
    return input_path


def _write_initial_manifest(
    *,
    result_id: str,
    result_dir: Path,
    input_path: Path,
    status: str,
) -> None:
    now = datetime.now().astimezone().isoformat()
    _write_json(
        result_dir / "manifest.json",
        {
            "result_id": result_id,
            "created_at": now,
            "updated_at": now,
            "status": status,
            "document": input_path.name,
            "input_file": f"input/{input_path.name}",
            "result_file": "result.json",
            "error_file": "error.json",
            "step_files": STEP_FILES,
            "artifacts": {
                "pages": "pages",
                "reference-panels": "reference-panels",
            },
            "page_files": [],
        },
    )


def _result_progress_writer(
    result_dir: Path,
) -> Callable[[str, object], None]:
    log_entries: list[dict[str, object]] = []

    def write_step(name: str, payload: object) -> None:
        entry = _progress_log_entry(name, payload)
        if entry is not None:
            log_entries.append(entry)
            _write_json(
                result_dir / STEP_FILES["recognition_log"],
                log_entries,
            )
        relative = STEP_FILES.get(name)
        if not relative:
            return
        _write_json(result_dir / relative, payload)

    write_step("job_started", {})
    return write_step


def _run_analysis_job(
    *,
    result_id: str,
    result_dir: Path,
    input_path: Path,
    work_dir: Path,
) -> None:
    progress = _result_progress_writer(result_dir)
    try:
        settings = Settings.from_env()
        knowledge = ComponentKnowledgeBase.load(KNOWLEDGE_PATH)
        custom_rules = (
            CustomRuleKnowledgeBase.load(CUSTOM_RULES_PATH)
            if CUSTOM_RULES_PATH.is_file()
            else CustomRuleKnowledgeBase.empty()
        )
        result, page_dir = RecognitionPipeline(
            knowledge,
            settings,
            custom_rule_base=custom_rules,
        ).analyze(input_path, work_dir=work_dir, progress=progress)
        progress("job_completed", result.meta)
        _persist_result(
            result_id=result_id,
            result_dir=result_dir,
            input_path=input_path,
            work_dir=work_dir,
            page_dir=page_dir,
            payload=result.to_dict(),
        )
        _try_auto_index_result(result_id, result_dir, settings)
    except Exception as exc:
        progress("job_failed", {"error": str(exc)})
        _persist_error(
            result_id=result_id,
            result_dir=result_dir,
            input_path=input_path,
            error=exc,
        )
    finally:
        _release_result_id(result_id)


def _progress_log_entry(
    name: str,
    payload: object,
) -> dict[str, object] | None:
    count = len(payload) if isinstance(payload, (list, dict)) else 0
    level = "info"
    messages = {
        "job_started": "识别任务已创建，正在准备图纸。",
        "document": "图纸解析完成，开始提取页面与文本。",
        "title_block": "图签信息提取完成。",
        "control_signal_configuration": "控制与信号配置提取完成。",
        "component_table": "图纸标签表提取完成。",
        "open_categories": f"开放识别类别已聚合，共 {count} 种。",
        "detected_components": f"元器件识别完成，共形成 {count} 条结果。",
        "detected_combinations": f"组合规则判断完成，共识别 {count} 个组合。",
        "warnings": f"识别过程产生 {count} 条提示。",
        "job_completed": "全部识别步骤已完成，正在生成结果。",
    }
    message = messages.get(name)
    if name == "open_symbols" and isinstance(payload, list):
        message = f"开放识别已发现 {len(payload)} 条元器件记录。"
    elif name == "rag_corrections" and isinstance(payload, list):
        message = f"知识库名称修正已处理 {len(payload)} 种元器件。"
    elif name == "open_recognition_tiles" and isinstance(payload, list):
        if not payload:
            message = "已准备图纸整页图，准备调用视觉模型。"
        else:
            latest = payload[-1] if isinstance(payload[-1], dict) else {}
            status = str(latest.get("status", "complete"))
            view = str(latest.get("tile", "full"))
            page = latest.get("page", "")
            if status == "failed":
                level = "warning"
                message = f"第 {page} 页整页图 {view} 识别失败，继续处理后续页面。"
            else:
                symbol_count = latest.get("symbol_count", 0)
                message = (
                    f"第 {page} 页整页图 {view} 识别完成，"
                    f"发现 {symbol_count} 条记录。"
                )
    elif name == "job_failed":
        level = "error"
        error = payload.get("error", "") if isinstance(payload, dict) else ""
        message = f"识别任务失败：{error}"
    if not message:
        return None
    return {
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "stage": name,
        "level": level,
        "message": message,
    }


def _persist_error(
    *,
    result_id: str,
    result_dir: Path,
    input_path: Path,
    error: Exception,
) -> None:
    page_dir = result_dir / "pages"
    page_files = _page_artifacts(page_dir)
    failed_at = datetime.now().astimezone().isoformat()
    manifest_path = result_dir / "manifest.json"
    created_at = ""
    if manifest_path.is_file():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                created_at = str(existing.get("created_at", ""))
        except json.JSONDecodeError:
            created_at = ""
    payload = {
        "result_id": result_id,
        "document": input_path.name,
        "status": "failed",
        "failed_at": failed_at,
        "error": {
            "type": type(error).__name__,
            "message": str(error),
        },
        "step_files": STEP_FILES,
        "page_files": page_files,
    }
    _write_json(result_dir / "error.json", payload)
    _write_initial_manifest(
        result_id=result_id,
        result_dir=result_dir,
        input_path=input_path,
        status="failed",
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if created_at:
        manifest["created_at"] = created_at
    manifest["error_file"] = "error.json"
    manifest["page_files"] = page_files
    manifest["updated_at"] = failed_at
    _write_json(manifest_path, manifest)


def _persist_result(
    *,
    result_id: str,
    result_dir: Path,
    input_path: Path,
    work_dir: Path,
    page_dir: Path,
    payload: dict[str, object],
) -> dict[str, object]:
    input_dir = result_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    target_input = input_dir / input_path.name
    if input_path.resolve() != target_input.resolve():
        shutil.copy2(input_path, target_input)

    artifacts: dict[str, str] = {}
    for name in ("pages", "reference-panels"):
        source = work_dir / name
        if not source.exists():
            continue
        target = result_dir / name
        if source.resolve() == target.resolve():
            artifacts[name] = name
            continue
        if source.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(source, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        artifacts[name] = name

    persisted_page_dir = result_dir / "pages"
    preview_pages = _preview_pages(
        persisted_page_dir if persisted_page_dir.is_dir() else page_dir
    )
    page_files = _page_artifacts(persisted_page_dir)
    saved_payload = dict(payload)
    saved_payload["result_id"] = result_id
    saved_payload["preview_pages"] = preview_pages
    saved_payload["result_files"] = {
        "root": str(result_dir),
        "input": f"input/{input_path.name}",
        "manifest": "manifest.json",
        "steps": "steps",
        "artifacts": artifacts,
    }

    steps_dir = result_dir / "steps"
    steps_dir.mkdir(parents=True, exist_ok=True)
    step_files = STEP_FILES
    recognition_steps = saved_payload.get("recognition_steps", {})
    if not isinstance(recognition_steps, dict):
        recognition_steps = {}
    _write_json(
        result_dir / step_files["title_block"],
        saved_payload.get("title_block", {}),
    )
    _write_json(
        result_dir / step_files["control_signal_configuration"],
        saved_payload.get("control_signal_configuration", {}),
    )
    _write_json(
        result_dir / step_files["component_table"],
        saved_payload.get("component_table", {}),
    )
    _write_json(
        result_dir / step_files["page_quality"],
        recognition_steps.get("page_quality", []),
    )
    _write_json(
        result_dir / step_files["layout_regions"],
        saved_payload.get("page_layouts", []),
    )
    _write_json(
        result_dir / step_files["structured_region_extraction"],
        recognition_steps.get("structured_region_extraction", []),
    )
    _write_json(
        result_dir / step_files["open_symbols"],
        recognition_steps.get("open_symbols", []),
    )
    _write_json(
        result_dir / step_files["open_recognition_tiles"],
        recognition_steps.get("open_recognition_tiles", []),
    )
    _write_json(
        result_dir / step_files["open_categories"],
        recognition_steps.get("open_categories", []),
    )
    _write_json(
        result_dir / step_files["rag_corrections"],
        recognition_steps.get("rag_corrections", []),
    )
    _write_json(
        result_dir / step_files["detected_components"],
        saved_payload.get("detected_components", []),
    )
    _write_json(
        result_dir / step_files["detected_combinations"],
        saved_payload.get("detected_combinations", []),
    )
    _write_json(
        result_dir / step_files["legacy_detected_components"],
        saved_payload.get("detected_components", []),
    )
    _write_json(
        result_dir / step_files["preview_pages"],
        {
            "pages": page_files,
            "previews": [
                {
                    key: value
                    for key, value in page.items()
                    if key != "data_url"
                }
                for page in preview_pages
            ],
        },
    )
    _write_json(
        result_dir / step_files["warnings"],
        saved_payload.get("warnings", []),
    )
    _write_json(result_dir / step_files["meta"], saved_payload.get("meta", {}))

    manifest = {
        "result_id": result_id,
        "created_at": datetime.now().astimezone().isoformat(),
        "updated_at": datetime.now().astimezone().isoformat(),
        "status": "complete",
        "document": saved_payload.get("document", input_path.name),
        "input_file": f"input/{input_path.name}",
        "result_file": "result.json",
        "error_file": "error.json",
        "step_files": step_files,
        "artifacts": artifacts,
        "page_files": page_files,
    }
    _write_json(result_dir / "result.json", saved_payload)
    _write_json(result_dir / "manifest.json", manifest)
    return saved_payload


def _search_store(settings: Settings) -> DrawingSearchStore:
    return DrawingSearchStore(
        PROJECT_ROOT / settings.search_sqlite_path,
        score_weights=_read_search_mapping(
            PROJECT_ROOT / settings.search_exact_boost_config
        ),
    )


def _index_service(settings: Settings) -> DrawingIndexService:
    return DrawingIndexService(
        _search_store(settings),
        embedding_backend=_embedding_backend(settings),
        vector_store=_vector_store(settings),
    )


def _search_service(settings: Settings) -> DrawingSearchService:
    return DrawingSearchService(
        _search_store(settings),
        parser=QueryParser(
            synonyms=_read_search_synonyms(
                PROJECT_ROOT / settings.search_synonyms_config
            )
        ),
        embedding_backend=_embedding_backend(settings),
        vector_store=_vector_store(settings),
        bm25_limit=settings.search_bm25_limit,
        vector_limit=settings.search_vector_limit,
        vector_min_score=settings.search_vector_min_score,
        rrf_k=settings.search_rrf_k,
        default_limit=settings.search_result_limit,
        mode=settings.search_mode,
        deduplicate=settings.search_deduplicate,
    )


def _diff_storage() -> DiffJobStorage:
    return DiffJobStorage(DIFF_JOB_DIR)


def _diff_service() -> DrawingDiffService:
    return DrawingDiffService()


def enable_production_frontend(
    dist_dir: str | Path | None = None,
    api_app: FastAPI | None = None,
) -> Path:
    """Serve the built Vue SPA from the API app for packaged runs.

    This is intentionally opt-in so the development API keeps returning 404
    for frontend routes while Vite handles the UI.
    """
    root = Path(dist_dir).resolve() if dist_dir else web_dist_dir()
    index_path = root / "index.html"
    if not index_path.is_file():
        raise FileNotFoundError(index_path)
    target_app = api_app or app

    @target_app.get("/", include_in_schema=False)
    def _frontend_index() -> FileResponse:
        return FileResponse(index_path)

    @target_app.get("/{full_path:path}", include_in_schema=False)
    def _frontend_asset_or_route(full_path: str) -> FileResponse:
        if _is_backend_path(full_path):
            raise HTTPException(404, "Not Found")
        candidate = (root / full_path).resolve(strict=False)
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise HTTPException(404, "Not Found") from exc
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index_path)

    return root


def _is_backend_path(path_value: str) -> bool:
    first = path_value.strip("/").split("/", 1)[0]
    return first in {"api", "analyze", "health", "docs", "redoc", "openapi.json"}


def _read_search_mapping(path: Path) -> dict[str, float]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    result: dict[str, float] = {}
    for key, value in payload.items():
        try:
            result[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return result


def _read_search_synonyms(path: Path) -> dict[str, list[str]]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        str(key): [
            str(item)
            for item in value
            if str(item).strip()
        ]
        for key, value in payload.items()
        if isinstance(value, list)
    }


def _embedding_backend(settings: Settings) -> object:
    if settings.search_embedding_backend != "sentence_transformers":
        return DisabledEmbeddingBackend("disabled")
    key = (
        settings.search_embedding_backend,
        settings.search_embedding_model,
        settings.search_embedding_model_path,
        settings.search_embedding_device,
        settings.search_embedding_batch_size,
        settings.search_embedding_normalize,
    )
    with SEARCH_RUNTIME_LOCK:
        backend = EMBEDDING_BACKENDS.get(key)
        if backend is None:
            backend = SentenceTransformerEmbeddingBackend(
                model_id=settings.search_embedding_model,
                batch_size=settings.search_embedding_batch_size,
                normalize=settings.search_embedding_normalize,
                device=settings.search_embedding_device,
                model_path=settings.search_embedding_model_path,
            )
            EMBEDDING_BACKENDS[key] = backend
        return backend


def _vector_store(settings: Settings) -> object | None:
    if settings.search_embedding_backend == "disabled":
        return None

    def _client_factory() -> object:
        key = (
            settings.search_qdrant_mode,
            settings.search_qdrant_url,
            settings.search_qdrant_path,
            settings.search_qdrant_api_key,
        )
        with SEARCH_RUNTIME_LOCK:
            client = QDRANT_CLIENTS.get(key)
            if client is not None:
                return client
            try:
                from qdrant_client import QdrantClient
            except ImportError as exc:
                raise RuntimeError(
                    "qdrant-client 未安装，无法启用向量检索。"
                ) from exc
            if settings.search_qdrant_mode == "remote":
                client = QdrantClient(
                    url=settings.search_qdrant_url,
                    api_key=settings.search_qdrant_api_key or None,
                )
            else:
                client = QdrantClient(
                    path=str(PROJECT_ROOT / settings.search_qdrant_path)
                )
            QDRANT_CLIENTS[key] = client
            return client

    return QdrantVectorStore(
        collection_name=settings.search_collection,
        client_factory=_client_factory,
        lock=QDRANT_OP_LOCK,
    )


def _try_auto_index_result(
    result_id: str,
    result_dir: Path,
    settings: Settings,
) -> None:
    if (
        not settings.search_enabled
        or not settings.search_auto_index
        or settings.search_mode == "disabled"
    ):
        _set_manifest_index_status(result_dir, "disabled", "")
        return
    try:
        _index_service(settings).index_result(result_id, result_dir)
    except Exception as exc:
        _set_manifest_index_status(result_dir, "failed", str(exc))
        return
    _set_manifest_index_status(result_dir, "complete", "")


def _remove_existing_search_index(
    result_id: str,
    settings: Settings,
) -> None:
    if not settings.search_enabled:
        return
    try:
        _index_service(settings).delete_result(result_id)
    except Exception:
        # A stale search index must not prevent a new recognition run.
        pass


def _set_manifest_index_status(
    result_dir: Path,
    status: str,
    error: str,
) -> None:
    manifest_path = result_dir / "manifest.json"
    if not manifest_path.is_file():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    if not isinstance(manifest, dict):
        return
    manifest["index_status"] = status
    manifest["index_error"] = error
    manifest["updated_at"] = datetime.now().astimezone().isoformat()
    _write_json(manifest_path, manifest)


def _serialize_component(
    sample: object,
    root_dir: Path,
) -> dict[str, object]:
    image_url = (
        f"/api/knowledge/{sample.id}/image"
        if getattr(sample, "image_path", "")
        else ""
    )
    return {
        "id": sample.id,
        "label": sample.label,
        "image_path": getattr(sample, "image_path", ""),
        "image_url": image_url,
        "variant_images": list(getattr(sample, "variant_images", [])),
        "variant_image_urls": [
            f"/api/knowledge/{sample.id}/images/{index}"
            for index, _value in enumerate(
                getattr(sample, "variant_images", [])
            )
        ],
        "component_type": getattr(sample, "component_type", ""),
        "model": getattr(sample, "model", ""),
        "definition": getattr(sample, "definition", ""),
        "standards": list(getattr(sample, "standards", [])),
        "aliases": list(getattr(sample, "aliases", [])),
        "notes": getattr(sample, "notes", ""),
        "source": getattr(sample, "source", ""),
        "enabled": bool(getattr(sample, "enabled", True)),
        "created_at": getattr(sample, "created_at", ""),
        "updated_at": getattr(sample, "updated_at", ""),
    }


def _serialize_rule(rule: object, root_dir: Path) -> dict[str, object]:
    image_url = (
        f"/api/custom-rules/{rule.id}/image"
        if getattr(rule, "image_path", "")
        else ""
    )
    return {
        "id": rule.id,
        "name": rule.name,
        "description": getattr(rule, "description", ""),
        "image_path": getattr(rule, "image_path", ""),
        "image_url": image_url,
        "engine": getattr(rule, "engine", "declarative"),
        "enabled": bool(getattr(rule, "enabled", True)),
        "scope": getattr(rule, "scope", "same_page"),
        "confidence": float(getattr(rule, "confidence", 0.95)),
        "aliases": list(getattr(rule, "aliases", [])),
        "notes": getattr(rule, "notes", ""),
        "source": getattr(rule, "source", ""),
        "member_count": len(getattr(rule, "members", [])),
        "members": [
            {
                "role": member.role,
                "min_quantity": member.min_quantity,
                "component_ids": list(getattr(member, "component_ids", [])),
                "code_patterns": list(getattr(member, "code_patterns", [])),
                "label_keywords": list(getattr(member, "label_keywords", [])),
            }
            for member in getattr(rule, "members", [])
        ],
        "created_at": getattr(rule, "created_at", ""),
        "updated_at": getattr(rule, "updated_at", ""),
    }


def _error_detail(
    code: str,
    message: str,
    *,
    fields: dict[str, object] | None = None,
    references: list[str] | None = None,
) -> dict[str, object]:
    return {
        "code": code,
        "message": message,
        "fields": fields or {},
        "references": references or [],
    }


def _normalize_diff_file_type(value: str) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"catdrawing", "dwg", "pdf"}:
        return normalized
    return None


def _diff_extension_matches(file_type: str, filename: str) -> bool:
    suffix = Path(filename).suffix.lower()
    return (
        (file_type == "catdrawing" and suffix == ".catdrawing")
        or (file_type == "dwg" and suffix == ".dwg")
        or (file_type == "pdf" and suffix == ".pdf")
    )


def _diff_success_response(
    job_id: str,
    data: dict[str, object],
) -> dict[str, object]:
    return {
        "success": True,
        "message": "compare completed",
        "stage": "completed",
        "job_id": job_id,
        "data": data,
        "error_code": "",
    }


def _diff_error_response(
    stage: str,
    message: str,
    *,
    job_id: str | None = None,
    status: bool = False,
) -> dict[str, object]:
    return {
        "success": status,
        "message": message,
        "stage": stage,
        "job_id": job_id,
        "data": None,
        "error_code": f"{stage}_error",
    }


def _result_path(result_id: str) -> Path:
    if not RESULT_ID_PATTERN.fullmatch(result_id):
        raise HTTPException(400, "Invalid result id.")
    result_path = (RESULT_DIR / result_id).resolve()
    root = RESULT_DIR.resolve()
    if result_path != root and root not in result_path.parents:
        raise HTTPException(403, "Invalid result path.")
    return result_path


def _is_result_child(path: Path, result_dir: Path) -> bool:
    result_root = result_dir.resolve()
    return path == result_root or result_root in path.parents


def _resolve_result_preview_file(result_dir: Path) -> Path | None:
    manifest_path = result_dir / "manifest.json"
    manifest: dict[str, object] = {}
    if manifest_path.is_file():
        try:
            loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(500, "Recognition manifest is not valid JSON.") from exc
        if isinstance(loaded, dict):
            manifest = loaded

    input_file = str(manifest.get("input_file", "")).strip()
    if input_file:
        candidate = (result_dir / input_file).resolve()
        if _is_result_child(candidate, result_dir) and candidate.is_file():
            return candidate

    input_dir = result_dir / "input"
    if input_dir.is_dir():
        files = sorted(path for path in input_dir.iterdir() if path.is_file())
        for suffix in (".pdf", ".png", ".jpg", ".jpeg", ".webp"):
            for path in files:
                if path.suffix.lower() == suffix:
                    return path
        if files:
            return files[0]
    first_page = _resolve_first_result_preview_page(result_dir)
    if first_page is not None:
        return first_page
    return None


def _resolve_result_preview_page(result_dir: Path, page: int) -> Path | None:
    if page < 1:
        return None
    pages_dir = result_dir / "pages"
    if not pages_dir.is_dir():
        return None
    for suffix in (".png", ".jpg", ".jpeg", ".webp"):
        candidate = (pages_dir / f"page-{page}{suffix}").resolve()
        if _is_result_child(candidate, result_dir) and candidate.is_file():
            return candidate
    return None


def _resolve_first_result_preview_page(result_dir: Path) -> Path | None:
    pages_dir = result_dir / "pages"
    if not pages_dir.is_dir():
        return None
    files = [
        path
        for path in pages_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    ]
    for path in sorted(files, key=_preview_page_sort_key):
        candidate = path.resolve()
        if _is_result_child(candidate, result_dir):
            return candidate
    return None


def _preview_page_sort_key(path: Path) -> tuple[int, str]:
    try:
        return (int(path.stem.rsplit("-", 1)[-1]), path.name)
    except ValueError:
        return (sys.maxsize, path.name)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _page_artifacts(page_dir: Path) -> list[dict[str, object]]:
    if not page_dir.is_dir():
        return []
    pages: list[dict[str, object]] = []
    for path in _sorted_page_files(page_dir):
        pages.append(
            {
                "page": int(path.stem.rsplit("-", 1)[-1]),
                "file": f"pages/{path.name}",
            }
        )
    return pages


def _read_step_payloads(
    result_dir: Path,
    manifest: dict[str, object],
) -> tuple[dict[str, object], dict[str, str], list[str]]:
    step_files = manifest.get("step_files")
    if not isinstance(step_files, dict):
        step_files = STEP_FILES
    steps: dict[str, object] = {}
    files: dict[str, str] = {}
    missing: list[str] = []
    for name, relative in step_files.items():
        if not isinstance(name, str) or not isinstance(relative, str):
            continue
        path = (result_dir / relative).resolve()
        if result_dir.resolve() not in path.parents:
            continue
        if not path.is_file():
            missing.append(name)
            continue
        try:
            steps[name] = json.loads(path.read_text(encoding="utf-8"))
            files[name] = relative
        except json.JSONDecodeError:
            steps[name] = {
                "error": "step file is not valid JSON",
                "file": relative,
            }
            files[name] = relative
    return steps, files, missing


def _preview_pages(page_dir: Path) -> list[dict[str, object]]:
    previews: list[dict[str, object]] = []
    for path in _sorted_page_files(page_dir):
        with Image.open(path) as source:
            image = source.convert("RGB")
            image.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            image.save(buffer, "JPEG", quality=82, optimize=True)
        previews.append(
            {
                "page": int(path.stem.rsplit("-", 1)[-1]),
                "width": image.width,
                "height": image.height,
                "data_url": (
                    "data:image/jpeg;base64,"
                    + base64.b64encode(buffer.getvalue()).decode("ascii")
                ),
            }
        )
    return previews


def _sorted_page_files(page_dir: Path) -> list[Path]:
    return sorted(
        page_dir.glob("page-*.png"),
        key=lambda item: int(item.stem.rsplit("-", 1)[-1]),
    )
