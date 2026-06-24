from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

from .combination_rules import detect_combinations
from .custom_rules import (
    CustomRule,
    CustomRuleKnowledgeBase,
    RuleMember,
    validate_rule_payload,
)


ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_WRITE_LOCK = threading.Lock()
_ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


class CustomRuleStoreError(Exception):
    pass


class RuleAlreadyExistsError(CustomRuleStoreError):
    pass


class RuleNotFoundError(CustomRuleStoreError):
    pass


class BuiltinRuleReadonlyError(CustomRuleStoreError):
    pass


class InvalidRulePayloadError(CustomRuleStoreError):
    pass


class ComponentReferencedError(CustomRuleStoreError):
    def __init__(self, component_id: str, references: list[str]) -> None:
        super().__init__(component_id)
        self.component_id = component_id
        self.references = references


class CustomRuleStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self.root_dir = self.path.parent
        self.asset_dir = self.root_dir / "assets" / "rules"
        self.asset_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> CustomRuleKnowledgeBase:
        if not self.path.is_file():
            self._write_payload({"version": 2, "rules": []})
        return CustomRuleKnowledgeBase.load(self.path)

    def get_rule(self, rule_id: str) -> CustomRule:
        rule = self.load().by_id.get(rule_id)
        if rule is None:
            raise RuleNotFoundError(rule_id)
        return rule

    def create_rule(self, payload: dict[str, Any]) -> CustomRule:
        data = self._normalize_rule_payload(payload, creating=True)
        if data["engine"] != "declarative":
            raise InvalidRulePayloadError("仅允许创建声明式组合规则。")
        with _WRITE_LOCK:
            current = self._read_payload()
            rules = list(current.get("rules", []))
            if any(
                isinstance(item, dict)
                and str(item.get("id", "")).casefold() == data["id"].casefold()
                for item in rules
            ):
                raise RuleAlreadyExistsError(data["id"])
            rules.append(data)
            current["version"] = max(2, int(current.get("version", 1) or 1))
            current["rules"] = rules
            self._write_payload(current)
        return self.get_rule(data["id"])

    def update_rule(
        self,
        rule_id: str,
        payload: dict[str, Any],
    ) -> CustomRule:
        with _WRITE_LOCK:
            current = self._read_payload()
            rules = []
            found = False
            for item in current.get("rules", []):
                if not isinstance(item, dict):
                    continue
                if str(item.get("id", "")).casefold() == rule_id.casefold():
                    if str(item.get("engine", "declarative")) == "builtin":
                        raise BuiltinRuleReadonlyError(rule_id)
                    merged = dict(item)
                    merged.update(payload)
                    merged["id"] = rule_id
                    data = self._normalize_rule_payload(
                        merged, creating=False
                    )
                    rules.append(data)
                    found = True
                else:
                    rules.append(item)
            if not found:
                raise RuleNotFoundError(rule_id)
            current["version"] = max(2, int(current.get("version", 1) or 1))
            current["rules"] = rules
            self._write_payload(current)
        return self.get_rule(rule_id)

    def delete_rule(self, rule_id: str) -> None:
        with _WRITE_LOCK:
            current = self._read_payload()
            filtered = []
            found = False
            for item in current.get("rules", []):
                if not isinstance(item, dict):
                    continue
                if str(item.get("id", "")).casefold() == rule_id.casefold():
                    found = True
                    if str(item.get("engine", "declarative")) == "builtin":
                        raise BuiltinRuleReadonlyError(rule_id)
                    continue
                filtered.append(item)
            if not found:
                raise RuleNotFoundError(rule_id)
            current["rules"] = filtered
            self._write_payload(current)

    def set_rule_enabled(self, rule_id: str, enabled: bool) -> CustomRule:
        rule = self.get_rule(rule_id)
        payload = asdict(rule)
        payload["enabled"] = bool(enabled)
        if rule.engine == "builtin":
            payload["members"] = [asdict(member) for member in rule.members]
            with _WRITE_LOCK:
                current = self._read_payload()
                rules = []
                for item in current.get("rules", []):
                    if not isinstance(item, dict):
                        continue
                    if str(item.get("id", "")).casefold() == rule_id.casefold():
                        item = dict(item)
                        item["enabled"] = bool(enabled)
                    rules.append(item)
                current["rules"] = rules
                current["version"] = max(
                    2, int(current.get("version", 1) or 1)
                )
                self._write_payload(current)
            return self.get_rule(rule_id)
        return self.update_rule(rule_id, payload)

    def update_rule_image(
        self,
        rule_id: str,
        content: bytes,
        filename: str,
    ) -> CustomRule:
        relative = self._save_image(rule_id, content, filename)
        with _WRITE_LOCK:
            current = self._read_payload()
            rules = []
            found = False
            for item in current.get("rules", []):
                if not isinstance(item, dict):
                    continue
                if str(item.get("id", "")).casefold() == rule_id.casefold():
                    if str(item.get("engine", "declarative")) == "builtin":
                        raise BuiltinRuleReadonlyError(rule_id)
                    updated = dict(item)
                    updated["image_path"] = relative
                    updated = self._normalize_rule_payload(
                        updated, creating=False
                    )
                    rules.append(updated)
                    found = True
                else:
                    rules.append(item)
            if not found:
                raise RuleNotFoundError(rule_id)
            current["rules"] = rules
            self._write_payload(current)
        return self.get_rule(rule_id)

    def assert_component_not_referenced(self, component_id: str) -> None:
        references = []
        for rule in self.load().rules:
            for member in rule.members:
                if component_id in member.component_ids:
                    references.append(rule.id)
                    break
        if references:
            raise ComponentReferencedError(component_id, references)

    def validate_rule(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_rule_payload(payload, creating=False)
        members = normalized["members"]
        return {
            "valid": True,
            "summary": {
                "member_count": len(members),
                "min_quantity_total": sum(
                    int(member.get("min_quantity", 1)) for member in members
                ),
            },
            "warnings": [],
        }

    def test_rule(
        self,
        payload: dict[str, Any],
        *,
        detected_components: list[dict[str, Any]] | None = None,
        open_symbols: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        rule = CustomRule(
            **self._normalize_rule_payload(payload, creating=False)
        )
        matches = detect_combinations(
            detected_components or [],
            open_symbols=open_symbols or [],
            custom_rules=CustomRuleKnowledgeBase([rule], self.root_dir),
        )
        return {"matches": matches}

    def _normalize_rule_payload(
        self,
        payload: dict[str, Any],
        *,
        creating: bool,
    ) -> dict[str, Any]:
        rule_id = str(payload.get("id", "")).strip()
        if not rule_id or not ID_PATTERN.fullmatch(rule_id):
            raise InvalidRulePayloadError("组合元件 ID 不合法。")
        name = str(payload.get("name", "")).strip()
        if not name:
            raise InvalidRulePayloadError("组合元件名称不能为空。")
        engine = str(payload.get("engine", "declarative")).strip() or "declarative"
        scope = str(payload.get("scope", "same_page")).strip() or "same_page"
        if scope not in {"same_page", "document"}:
            raise InvalidRulePayloadError("组合元件作用域不合法。")
        members_payload = payload.get("members", [])
        if not isinstance(members_payload, list):
            raise InvalidRulePayloadError("组合元件成员格式不合法。")
        members = []
        for item in members_payload:
            if isinstance(item, RuleMember):
                values = asdict(item)
            elif isinstance(item, dict):
                values = dict(item)
            else:
                raise InvalidRulePayloadError("组合元件成员格式不合法。")
            members.append(validate_rule_payload(values))
        timestamp = _utc_now()
        created_at = str(payload.get("created_at", "")).strip()
        return {
            "id": rule_id,
            "name": name,
            "description": str(payload.get("description", "")).strip(),
            "image_path": _normalize_asset_path(
                payload.get("image_path", ""),
                "assets/rules",
            ),
            "engine": engine,
            "enabled": bool(payload.get("enabled", True)),
            "scope": scope,
            "confidence": max(
                0.0,
                min(1.0, float(payload.get("confidence", 0.95) or 0.95)),
            ),
            "members": members,
            "aliases": _unique_strings(payload.get("aliases", [])),
            "notes": str(payload.get("notes", "")).strip(),
            "source": str(payload.get("source", "")).strip(),
            "created_at": created_at if created_at else (timestamp if creating else ""),
            "updated_at": timestamp,
        }

    def _save_image(self, rule_id: str, content: bytes, filename: str) -> str:
        suffix = Path(filename).suffix.lower() or ".png"
        if suffix not in _ALLOWED_SUFFIXES:
            raise InvalidRulePayloadError("仅支持 PNG/JPEG/WebP 图片。")
        target = self.asset_dir / f"{rule_id}-{uuid4().hex[:8]}{suffix}"
        temp = NamedTemporaryFile(delete=False, suffix=suffix)
        try:
            temp.write(content)
            temp.flush()
            temp.close()
            with Image.open(temp.name) as image:
                image.convert("RGB").save(target)
        except (UnidentifiedImageError, OSError) as exc:
            raise InvalidRulePayloadError("图片内容无效。") from exc
        finally:
            try:
                Path(temp.name).unlink(missing_ok=True)
            except OSError:
                pass
        return target.relative_to(self.root_dir).as_posix()

    def _read_payload(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"version": 2, "rules": []}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write_payload(self, payload: dict[str, Any]) -> None:
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


def _utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _normalize_asset_path(value: object, prefix: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    path = Path(raw)
    if path.is_absolute():
        raise InvalidRulePayloadError("图片路径必须位于知识库资产目录内。")
    normalized = Path(raw.replace("\\", "/")).as_posix()
    if normalized.startswith("../") or "/../" in normalized or normalized == "..":
        raise InvalidRulePayloadError("图片路径必须位于知识库资产目录内。")
    if not (normalized == prefix or normalized.startswith(f"{prefix}/")):
        raise InvalidRulePayloadError("图片路径必须位于知识库资产目录内。")
    return normalized
