from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

from .knowledge import ComponentKnowledgeBase
from .models import ComponentSample


ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_WRITE_LOCK = threading.Lock()
_ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


class KnowledgeStoreError(Exception):
    pass


class ComponentAlreadyExistsError(KnowledgeStoreError):
    pass


class ComponentNotFoundError(KnowledgeStoreError):
    pass


class InvalidComponentPayloadError(KnowledgeStoreError):
    pass


class InvalidImageError(KnowledgeStoreError):
    pass


class KnowledgeStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self.root_dir = self.path.parent
        self.asset_dir = self.root_dir / "assets" / "components"
        self.asset_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> ComponentKnowledgeBase:
        if not self.path.is_file():
            self._write_payload({"version": 2, "components": []})
        return ComponentKnowledgeBase.load(self.path)

    def get_component(self, component_id: str) -> ComponentSample:
        sample = self.load().by_id.get(component_id)
        if sample is None:
            raise ComponentNotFoundError(component_id)
        return sample

    def list_components(self) -> list[ComponentSample]:
        return self.load().components

    def create_component(
        self,
        payload: dict[str, object],
    ) -> ComponentSample:
        data = self._normalize_component_payload(payload, creating=True)
        with _WRITE_LOCK:
            current = self._read_payload()
            components = list(current.get("components", []))
            if any(
                str(item.get("id", "")).casefold()
                == data["id"].casefold()
                for item in components
                if isinstance(item, dict)
            ):
                raise ComponentAlreadyExistsError(data["id"])
            components.append(data)
            current["version"] = max(2, int(current.get("version", 2) or 2))
            current["components"] = components
            self._write_payload(current)
        return self.get_component(data["id"])

    def update_component(
        self,
        component_id: str,
        payload: dict[str, object],
    ) -> ComponentSample:
        with _WRITE_LOCK:
            current = self._read_payload()
            components = []
            found = False
            for item in current.get("components", []):
                if not isinstance(item, dict):
                    continue
                if str(item.get("id", "")).casefold() == component_id.casefold():
                    merged = dict(item)
                    merged.update(payload)
                    merged["id"] = component_id
                    data = self._normalize_component_payload(
                        merged, creating=False
                    )
                    components.append(data)
                    found = True
                else:
                    components.append(item)
            if not found:
                raise ComponentNotFoundError(component_id)
            current["version"] = max(2, int(current.get("version", 2) or 2))
            current["components"] = components
            self._write_payload(current)
        return self.get_component(component_id)

    def delete_component(self, component_id: str) -> None:
        with _WRITE_LOCK:
            current = self._read_payload()
            before = len(current.get("components", []))
            components = [
                item
                for item in current.get("components", [])
                if not (
                    isinstance(item, dict)
                    and str(item.get("id", "")).casefold()
                    == component_id.casefold()
                )
            ]
            if len(components) == before:
                raise ComponentNotFoundError(component_id)
            current["components"] = components
            self._write_payload(current)

    def add_component_image(
        self,
        component_id: str,
        content: bytes,
        filename: str,
        *,
        kind: str = "variant",
    ) -> ComponentSample:
        relative_path = self._save_image(component_id, content, filename)
        with _WRITE_LOCK:
            current = self._read_payload()
            components = []
            found = False
            for item in current.get("components", []):
                if not isinstance(item, dict):
                    continue
                if str(item.get("id", "")).casefold() == component_id.casefold():
                    updated = dict(item)
                    if kind == "primary":
                        updated["image_path"] = relative_path
                    else:
                        variants = _unique_strings(updated.get("variant_images", []))
                        variants.append(relative_path)
                        updated["variant_images"] = _unique_strings(variants)
                    updated = self._normalize_component_payload(
                        updated, creating=False
                    )
                    components.append(updated)
                    found = True
                else:
                    components.append(item)
            if not found:
                raise ComponentNotFoundError(component_id)
            current["components"] = components
            self._write_payload(current)
        return self.get_component(component_id)

    def remove_component_image(
        self,
        component_id: str,
        image_id: str,
    ) -> ComponentSample:
        with _WRITE_LOCK:
            current = self._read_payload()
            components = []
            found = False
            for item in current.get("components", []):
                if not isinstance(item, dict):
                    continue
                if str(item.get("id", "")).casefold() == component_id.casefold():
                    updated = dict(item)
                    if image_id == "primary":
                        updated["image_path"] = ""
                    else:
                        variants = _unique_strings(updated.get("variant_images", []))
                        try:
                            index = int(image_id)
                        except ValueError as exc:
                            raise InvalidComponentPayloadError("非法图片标识。") from exc
                        if index < 0 or index >= len(variants):
                            raise InvalidComponentPayloadError("图片不存在。")
                        variants.pop(index)
                        updated["variant_images"] = variants
                    updated = self._normalize_component_payload(
                        updated, creating=False
                    )
                    components.append(updated)
                    found = True
                else:
                    components.append(item)
            if not found:
                raise ComponentNotFoundError(component_id)
            current["components"] = components
            self._write_payload(current)
        return self.get_component(component_id)

    def _normalize_component_payload(
        self,
        payload: dict[str, object],
        *,
        creating: bool,
    ) -> dict[str, object]:
        component_id = str(payload.get("id", "")).strip()
        if not component_id or not ID_PATTERN.fullmatch(component_id):
            raise InvalidComponentPayloadError("组件 ID 不合法。")
        label = str(payload.get("label", "")).strip()
        if not label:
            raise InvalidComponentPayloadError("组件名称不能为空。")
        timestamp = _utc_now()
        created_at = str(payload.get("created_at", "")).strip()
        image_path = _normalize_asset_path(
            payload.get("image_path", ""),
            "assets/components",
        )
        return {
            "id": component_id,
            "label": label,
            "image_path": image_path,
            "variant_images": _normalize_asset_list(
                payload.get("variant_images", []),
                "assets/components",
            ),
            "component_type": str(payload.get("component_type", "")).strip(),
            "model": str(payload.get("model", "")).strip(),
            "definition": str(payload.get("definition", "")).strip(),
            "standards": _unique_strings(payload.get("standards", [])),
            "aliases": _unique_strings(payload.get("aliases", [])),
            "notes": str(payload.get("notes", "")).strip(),
            "source": str(payload.get("source", "")).strip(),
            "dhash": str(payload.get("dhash", "")).strip(),
            "color_histogram": list(payload.get("color_histogram", [])),
            "enabled": bool(payload.get("enabled", True)),
            "created_at": created_at if created_at else (timestamp if creating else ""),
            "updated_at": timestamp,
        }

    def _save_image(
        self,
        component_id: str,
        content: bytes,
        filename: str,
    ) -> str:
        suffix = Path(filename).suffix.lower() or ".png"
        if suffix not in _ALLOWED_SUFFIXES:
            raise InvalidImageError("仅支持 PNG/JPEG/WebP 图片。")
        target = self.asset_dir / f"{component_id}-{uuid4().hex[:8]}{suffix}"
        temp_path = _bytes_to_path(content, suffix)
        try:
            with Image.open(temp_path) as image:
                converted = image.convert("RGB")
                converted.save(target)
        except (UnidentifiedImageError, OSError) as exc:
            raise InvalidImageError("图片内容无效。") from exc
        finally:
            temp_path.unlink(missing_ok=True)
        return target.relative_to(self.root_dir).as_posix()

    def _read_payload(self) -> dict[str, object]:
        if not self.path.is_file():
            return {"version": 2, "components": []}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write_payload(self, payload: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            backup = self.path.with_suffix(
                f".{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.bak"
            )
            if not backup.exists():
                backup.write_text(
                    self.path.read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self.path.parent,
            delete=False,
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)
        temp_path.replace(self.path)


def _unique_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        normalized = str(item).strip()
        key = normalized.casefold()
        if normalized and key not in seen:
            result.append(normalized)
            seen.add(key)
    return result


def _bytes_to_path(content: bytes, suffix: str) -> Path:
    temp = NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        temp.write(content)
        temp.flush()
        return Path(temp.name)
    finally:
        temp.close()


def _utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _normalize_asset_path(value: object, prefix: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    path = Path(raw)
    if path.is_absolute():
        raise InvalidComponentPayloadError("图片路径必须位于知识库资产目录内。")
    normalized = Path(raw.replace("\\", "/")).as_posix()
    if normalized.startswith("../") or "/../" in normalized or normalized == "..":
        raise InvalidComponentPayloadError("图片路径必须位于知识库资产目录内。")
    if not (normalized == prefix or normalized.startswith(f"{prefix}/")):
        raise InvalidComponentPayloadError("图片路径必须位于知识库资产目录内。")
    return normalized


def _normalize_asset_list(value: object, prefix: str) -> list[str]:
    if not isinstance(value, list):
        return []
    return _unique_strings([
        _normalize_asset_path(item, prefix)
        for item in value
    ])
