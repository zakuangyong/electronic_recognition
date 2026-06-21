from __future__ import annotations

import base64
import io
import json
import re
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

from .config import Settings
from .combination_rules import detect_combinations
from .custom_rules import CustomRuleKnowledgeBase
from .knowledge import ComponentKnowledgeBase
from .pipeline import RecognitionPipeline


app = FastAPI(title="Electronic Recognition", version="0.1.0")
PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parents[1]
STATIC_DIR = PACKAGE_DIR / "static"
KNOWLEDGE_PATH = PROJECT_ROOT / "data" / "index" / "components.json"
CUSTOM_RULES_PATH = PROJECT_ROOT / "data" / "index" / "custom_rules.json"
RESULT_DIR = PROJECT_ROOT / "result"
RESULT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.\-\u4e00-\u9fff]+$")
STEP_FILES = {
    "recognition_log": "steps/00-recognition-log.json",
    "title_block": "steps/01-title-block.json",
    "control_signal_configuration": (
        "steps/02-control-signal-configuration.json"
    ),
    "component_table": "steps/03-component-table.json",
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
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/knowledge", include_in_schema=False)
def knowledge_page() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "knowledge.html",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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


@app.get("/api/knowledge")
def knowledge_items() -> dict[str, object]:
    if not KNOWLEDGE_PATH.is_file():
        raise HTTPException(500, "组件知识库不存在。")
    knowledge = ComponentKnowledgeBase.load(KNOWLEDGE_PATH)
    return {
        "count": len(knowledge.components),
        "items": [
            {
                "id": sample.id,
                "label": sample.label,
                "component_type": sample.component_type,
                "image_url": f"/api/knowledge/{sample.id}/image",
            }
            for sample in knowledge.components
        ],
    }


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


@app.post("/analyze")
def analyze(
    drawing: UploadFile = File(...),
) -> dict[str, object]:
    filename = drawing.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in {".pdf", ".png"}:
        raise HTTPException(400, "仅支持 PDF 或 PNG 格式。")
    if not KNOWLEDGE_PATH.is_file():
        raise HTTPException(500, "组件知识库不存在。")

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
    return {
        "result_id": result_id,
        "status": "running",
        "result_url": f"/api/results/{result_id}",
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
        raise HTTPException(404, "Recognition result does not exist.")
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(500, "Recognition result is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(500, "Recognition result must be an object.")
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
    stem = Path(filename or "drawing").stem or "drawing"
    safe_stem = re.sub(
        r"[^A-Za-z0-9_.\-\u4e00-\u9fff]+",
        "_",
        stem,
    ).strip("._-")
    safe_stem = safe_stem[:40] or "drawing"
    for _ in range(100):
        result_id = (
            f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-"
            f"{uuid4().hex[:8]}-{safe_stem}"
        )
        result_dir = RESULT_DIR / result_id
        try:
            result_dir.mkdir()
        except FileExistsError:
            continue
        return result_id, result_dir
    raise HTTPException(500, "Unable to create result directory.")


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
                "page-tiles": "page-tiles",
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
    except Exception as exc:
        progress("job_failed", {"error": str(exc)})
        _persist_error(
            result_id=result_id,
            result_dir=result_dir,
            input_path=input_path,
            error=exc,
        )


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
            message = "已生成图纸切片，准备调用视觉模型。"
        else:
            latest = payload[-1] if isinstance(payload[-1], dict) else {}
            status = str(latest.get("status", "complete"))
            tile = str(latest.get("tile", ""))
            page = latest.get("page", "")
            if status == "failed":
                level = "warning"
                message = f"第 {page} 页切片 {tile} 识别失败，继续处理其他切片。"
            else:
                symbol_count = latest.get("symbol_count", 0)
                message = (
                    f"第 {page} 页切片 {tile} 识别完成，"
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
    for name in ("pages", "reference-panels", "page-tiles"):
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


def _result_path(result_id: str) -> Path:
    if not RESULT_ID_PATTERN.fullmatch(result_id):
        raise HTTPException(400, "Invalid result id.")
    result_path = (RESULT_DIR / result_id).resolve()
    root = RESULT_DIR.resolve()
    if result_path != root and root not in result_path.parents:
        raise HTTPException(403, "Invalid result path.")
    return result_path


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
