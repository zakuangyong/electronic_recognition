from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class LoadedRecognitionResult:
    payload: dict[str, Any]
    audit_files: list[dict[str, str]] = field(default_factory=list)


class JsonResultLoader:
    _STEP_FIELD_MAP: tuple[tuple[str, str], ...] = (
        ("01-title-block.json", "title_block"),
        ("02-control-signal-configuration.json", "control_signal_configuration"),
        ("03-component-table.json", "component_table"),
        ("04-open-symbols.json", "open_symbols"),
        ("05-rag-corrections.json", "rag_corrections"),
        ("06-detected-components.json", "detected_components"),
        ("06-detected-combinations.json", "detected_combinations"),
        ("09-meta.json", "meta"),
    )

    def load(
        self,
        result_dir: Path,
        base_payload: dict[str, Any] | None = None,
    ) -> LoadedRecognitionResult:
        payload = base_payload if isinstance(base_payload, dict) else self._read_json(
            result_dir / "result.json"
        )
        normalized = dict(payload)
        audit_files: list[dict[str, str]] = []
        self._audit_file(result_dir / "result.json", "result.json", audit_files)

        for file_name, field_name in self._STEP_FIELD_MAP:
            path = result_dir / "steps" / file_name
            if not path.is_file():
                continue
            step_payload = self._read_json(path)
            self._audit_file(path, f"steps/{file_name}", audit_files)
            if field_name in {"detected_components", "detected_combinations"}:
                normalized[field_name] = self._normalize_list_payload(step_payload)
            elif field_name in {"open_symbols", "rag_corrections"}:
                normalized[field_name] = self._normalize_list_payload(step_payload)
            elif field_name == "meta":
                if isinstance(step_payload, dict):
                    merged_meta = dict(normalized.get("meta", {}))
                    merged_meta.update(step_payload)
                    normalized["meta"] = merged_meta
            elif field_name not in normalized or not normalized.get(field_name):
                normalized[field_name] = step_payload

        normalized.setdefault("detected_components", [])
        normalized.setdefault("detected_combinations", [])
        normalized.setdefault("open_symbols", [])
        normalized.setdefault("rag_corrections", [])
        normalized.setdefault("meta", {})
        normalized["loader_audit_files"] = list(audit_files)
        return LoadedRecognitionResult(payload=normalized, audit_files=audit_files)

    def _read_json(self, path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))

    def _normalize_list_payload(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("items", "rows", "components", "combinations", "results"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        return []

    def _audit_file(
        self,
        path: Path,
        relative_path: str,
        audit_files: list[dict[str, str]],
    ) -> None:
        if not path.is_file():
            return
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        audit_files.append(
            {
                "path": relative_path.replace("\\", "/"),
                "sha256": digest,
            }
        )
