from __future__ import annotations

import base64
import io
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

from .config import Settings
from .knowledge import ComponentKnowledgeBase
from .pipeline import RecognitionPipeline


app = FastAPI(title="Electronic Recognition", version="0.1.0")
PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parents[1]
STATIC_DIR = PACKAGE_DIR / "static"
KNOWLEDGE_PATH = PROJECT_ROOT / "data" / "index" / "components.json"
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
    if KNOWLEDGE_PATH.is_file():
        count = len(ComponentKnowledgeBase.load(KNOWLEDGE_PATH).components)
    return {
        "model": settings.model,
        "api_key_configured": bool(settings.api_key),
        "knowledge_path": str(KNOWLEDGE_PATH),
        "component_count": count,
        "reference_limit": settings.reference_limit,
    }


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

    with tempfile.TemporaryDirectory(
        prefix="electronic-recognition-api-"
    ) as temp:
        temp_dir = Path(temp)
        input_path = temp_dir / Path(filename).name
        with input_path.open("wb") as output:
            shutil.copyfileobj(drawing.file, output)
        try:
            settings = Settings.from_env()
            knowledge = ComponentKnowledgeBase.load(KNOWLEDGE_PATH)
            result, page_dir = RecognitionPipeline(
                knowledge, settings
            ).analyze(input_path, work_dir=temp_dir / "work")
        except Exception as exc:
            raise HTTPException(502, str(exc)) from exc
        payload = result.to_dict()
        payload["preview_pages"] = _preview_pages(page_dir)
        return payload


def _preview_pages(page_dir: Path) -> list[dict[str, object]]:
    previews: list[dict[str, object]] = []
    for path in sorted(
        page_dir.glob("page-*.png"),
        key=lambda item: int(item.stem.rsplit("-", 1)[-1]),
    ):
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
