from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .json_result_loader import JsonResultLoader, LoadedRecognitionResult
from .models import SCHEMA_VERSION, DrawingDocument, ExactTerm, SearchChunk
from .normalizer import SearchNormalizer


class DrawingDocumentBuilder:
    version = "2"

    def __init__(
        self,
        normalizer: SearchNormalizer | None = None,
        loader: JsonResultLoader | None = None,
    ) -> None:
        self.normalizer = normalizer or SearchNormalizer()
        self.loader = loader or JsonResultLoader()

    def build(
        self,
        result_id: str,
        result_dir: Path,
        payload: dict[str, Any] | LoadedRecognitionResult,
    ) -> DrawingDocument:
        loaded = (
            payload
            if isinstance(payload, LoadedRecognitionResult)
            else self.loader.load(result_dir, payload)
        )
        data = loaded.payload
        filename = str(data.get("document") or result_id)
        title_fields = _dict(_dict(data.get("title_block")).get("fields"))
        components = _dict_list(data.get("detected_components"))
        combinations = _dict_list(data.get("detected_combinations"))
        page_layouts = _dict_list(data.get("page_layouts"))
        preview_pages = _dict_list(data.get("preview_pages"))
        component_table = _dict(data.get("component_table"))
        rag_corrections = _dict_list(data.get("rag_corrections"))
        control_signals = _control_signal_terms(
            _dict(data.get("control_signal_configuration"))
        )
        page_count = _page_count(data, preview_pages, components)
        source_hash = _source_hash(result_dir, data)
        drawing_id = "sha256:" + _hash_text(
            f"{result_id}\n{source_hash}\n{filename}"
        )

        drawing_number = _field(
            title_fields,
            "drawing_number",
            "drawing no",
            "number",
            "原理图号",
            "图号",
            "鍘熺悊鍥惧彿",
        )
        drawing_title = _field(
            title_fields,
            "drawing_title",
            "title",
            "图纸名称",
            "图纸名",
            "鍥剧焊鍚嶇О",
        )
        project_name = _field(
            title_fields,
            "project_name",
            "project",
            "工程名称",
            "项目名称",
            "宸ョ▼鍚嶇О",
        )
        system_name = _field(
            title_fields,
            "system_name",
            "system",
            "系统名称",
            "绯荤粺鍚嶇О",
        )
        contract_number = _field(
            title_fields,
            "contract_number",
            "contract",
            "合同号",
            "鍚堝悓鍙",
        )
        revision = _field(
            title_fields,
            "revision",
            "rev",
            "版本号",
            "鍚堝悓鍙",
            "鐗堟湰鍙",
        )
        component_codes = _unique(
            _split_codes(component.get("code", "")) for component in components
        )
        component_labels = _unique(
            str(component.get("label", "")).strip()
            for component in components
        )
        component_types = _unique(
            str(component.get("component_type", "")).strip()
            for component in components
        )
        component_models = _unique(
            str(row.get(key, "")).strip()
            for row in _component_rows(component_table)
            for key in ("规格型号", "model", "瑙勬牸鍨嬪彿")
            if str(row.get(key, "")).strip()
        )
        combination_names = _unique(
            str(item.get("name", "")).strip()
            for item in combinations
        )
        parent_text = _join_lines(
            [
                f"图纸文件：{filename}",
                f"工程名称：{project_name}",
                f"系统名称：{system_name}",
                f"图纸名称：{drawing_title}",
                f"图号：{drawing_number}",
                f"合同号：{contract_number}",
                f"版本：{revision}",
                f"页数：{page_count}",
                f"元件：{'；'.join(component_codes + component_labels)}",
                f"规格型号：{'；'.join(component_models)}",
                f"组合功能：{'；'.join(combination_names)}",
                f"控制方式：{'；'.join(control_signals)}",
            ]
        )
        document = DrawingDocument(
            drawing_id=drawing_id,
            result_id=result_id,
            filename=filename,
            drawing_number=drawing_number,
            drawing_title=drawing_title,
            project_name=project_name,
            system_name=system_name,
            contract_number=contract_number,
            revision=revision,
            page_count=page_count,
            source_hash=source_hash,
            content_hash=_hash_json(data),
            schema_version=SCHEMA_VERSION,
            component_codes=component_codes,
            component_labels=component_labels,
            component_types=component_types,
            component_models=component_models,
            combination_names=combination_names,
            control_signals=control_signals,
            search_text=parent_text,
        )
        document.chunks = self._chunks(
            document=document,
            payload=data,
            parent_text=parent_text,
            components=components,
            combinations=combinations,
            component_table=component_table,
            page_layouts=page_layouts,
            page_count=page_count,
            rag_corrections=rag_corrections,
            audit_files=loaded.audit_files,
        )
        document.exact_terms = self._exact_terms(document)
        return document

    def _chunks(
        self,
        *,
        document: DrawingDocument,
        payload: dict[str, Any],
        parent_text: str,
        components: list[dict[str, Any]],
        combinations: list[dict[str, Any]],
        component_table: dict[str, Any],
        page_layouts: list[dict[str, Any]],
        page_count: int,
        rag_corrections: list[dict[str, Any]],
        audit_files: list[dict[str, str]],
    ) -> list[SearchChunk]:
        base_metadata = {
            "drawing_id": document.drawing_id,
            "result_id": document.result_id,
            "schema_version": document.schema_version,
            "builder_version": self.version,
            "source_hash": document.source_hash,
            "audit_files": audit_files,
        }
        chunks: list[SearchChunk] = [
            SearchChunk(
                chunk_id=f"{document.drawing_id}:drawing",
                drawing_id=document.drawing_id,
                chunk_type="drawing",
                title=document.drawing_title or document.filename,
                text=parent_text,
                content_hash=_hash_text(parent_text),
                metadata=dict(base_metadata),
            )
        ]

        grouped_components = defaultdict(list)
        corrections = _correction_index(rag_corrections)
        for component in components:
            grouped_components[int(component.get("page") or 0) or 1].append(
                component
            )

        for page in range(1, page_count + 1):
            page_components = grouped_components.get(page, [])
            page_combinations = [
                item for item in combinations if page in _pages(item.get("pages"))
            ]
            page_text = _join_lines(
                [
                    f"第{page}页。",
                    "元件："
                    + "；".join(
                        _component_summary(component)
                        for component in page_components
                    ),
                    "组合功能："
                    + "；".join(
                        str(item.get("name", "")).strip()
                        for item in page_combinations
                    ),
                    "控制信号："
                    + "；".join(_page_control_signals(payload, page)),
                ]
            )
            chunks.append(
                SearchChunk(
                    chunk_id=f"{document.drawing_id}:page:{page}",
                    drawing_id=document.drawing_id,
                    chunk_type="page",
                    page=page,
                    title=f"第{page}页",
                    text=page_text,
                    content_hash=_hash_text(page_text),
                    metadata={**base_metadata, "page": page},
                )
            )

        for page, component_type, items in _component_groups(components):
            text = _component_group_text(
                page=page,
                component_type=component_type,
                components=items,
                corrections=corrections,
            )
            chunks.append(
                SearchChunk(
                    chunk_id=f"{document.drawing_id}:component-group:{page}:{_slug(component_type)}",
                    drawing_id=document.drawing_id,
                    chunk_type="component_group",
                    page=page,
                    title=f"第{page}页{component_type}",
                    text=text,
                    content_hash=_hash_text(text),
                    metadata={
                        **base_metadata,
                        "page": page,
                        "component_type": component_type,
                        "component_codes": _unique(
                            _split_codes(item.get("code", ""))
                            for item in items
                        ),
                    },
                )
            )

        rows = _component_rows(component_table)
        if rows:
            table_text = _join_lines(
                ["元件表。", *[_component_row_text(row) for row in rows]]
            )
            chunks.append(
                SearchChunk(
                    chunk_id=f"{document.drawing_id}:component-table",
                    drawing_id=document.drawing_id,
                    chunk_type="component_table",
                    title="元件表",
                    text=table_text,
                    content_hash=_hash_text(table_text),
                    metadata=dict(base_metadata),
                )
            )

        for index, combination in enumerate(combinations, start=1):
            text = _combination_text(combination)
            page = _first_page(combination.get("pages"))
            chunks.append(
                SearchChunk(
                    chunk_id=f"{document.drawing_id}:combination:{index}",
                    drawing_id=document.drawing_id,
                    chunk_type="combination",
                    page=page,
                    title=str(combination.get("name") or "组合规则"),
                    text=text,
                    content_hash=_hash_text(text),
                    metadata={
                        **base_metadata,
                        "page": page,
                        "rule_id": str(
                            combination.get("rule_id", "")
                        ).strip(),
                        "rule_layer": str(
                            combination.get("rule_layer", "")
                        ).strip(),
                        "group_code": str(
                            combination.get("group_code", "")
                        ).strip(),
                    },
                )
            )

        for layout in page_layouts:
            layout_page = int(layout.get("page") or 0) or None
            for region in _dict_list(layout.get("regions")):
                if region.get("route") != "component":
                    continue
                page = int(region.get("page") or layout_page or 0) or None
                text = _join_lines(
                    [
                        f"功能区域：{region.get('region_type', '')}",
                        f"页码：{region.get('page', layout_page or '')}",
                        f"来源：{region.get('source', '')}",
                    ]
                )
                chunks.append(
                    SearchChunk(
                        chunk_id=f"{document.drawing_id}:region:{region.get('id', len(chunks))}",
                        drawing_id=document.drawing_id,
                        chunk_type="region",
                        page=page,
                        region_id=str(region.get("id", "")),
                        region_type=str(region.get("region_type", "")),
                        bounds=list(region.get("bounds", [])),
                        title=str(region.get("region_type", "region")),
                        text=text,
                        content_hash=_hash_text(text),
                        metadata={
                            **base_metadata,
                            "page": page,
                            "region_type": str(
                                region.get("region_type", "")
                            ),
                        },
                    )
                )
        return chunks

    def _exact_terms(self, document: DrawingDocument) -> list[ExactTerm]:
        terms: list[ExactTerm] = []
        for term_type, value in (
            ("filename", document.filename),
            ("drawing_number", document.drawing_number),
            ("contract_number", document.contract_number),
            ("revision", document.revision),
            ("drawing_title", document.drawing_title),
            ("project_name", document.project_name),
            ("system_name", document.system_name),
        ):
            self._append_identifier_terms(terms, document, term_type, value)
        for code in document.component_codes:
            for alias in self.normalizer.aliases_for_component_code(code):
                terms.append(
                    ExactTerm(
                        drawing_id=document.drawing_id,
                        term_type="component_code",
                        raw_value=code,
                        normalized_value=self.normalizer.compact_identifier(
                            alias
                        ),
                    )
                )
        for model in document.component_models:
            self._append_identifier_terms(
                terms,
                document,
                "component_model",
                model,
            )
        return _deduplicate_exact_terms(terms)

    def _append_identifier_terms(
        self,
        terms: list[ExactTerm],
        document: DrawingDocument,
        term_type: str,
        value: str,
    ) -> None:
        if not value:
            return
        for alias in self.normalizer.aliases_for_identifier(value):
            terms.append(
                ExactTerm(
                    drawing_id=document.drawing_id,
                    term_type=term_type,
                    raw_value=value,
                    normalized_value=self.normalizer.compact_identifier(alias),
                )
            )


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _component_rows(component_table: dict[str, Any]) -> list[dict[str, Any]]:
    return _dict_list(component_table.get("rows"))


def _field(fields: dict[str, Any], *names: str) -> str:
    lowered_names = [name.casefold() for name in names]
    for name in names:
        value = str(fields.get(name, "")).strip()
        if value:
            return value
    for key, value in fields.items():
        key_text = str(key).strip()
        lowered_key = key_text.casefold()
        if any(name in lowered_key for name in lowered_names):
            value_text = str(value).strip()
            if value_text:
                return value_text
    return ""


def _page_count(
    payload: dict[str, Any],
    preview_pages: list[dict[str, Any]],
    components: list[dict[str, Any]],
) -> int:
    meta = _dict(payload.get("meta"))
    candidates = [
        int(meta.get("page_count") or 0),
        len(preview_pages),
        *[int(component.get("page") or 0) for component in components],
    ]
    return max(1, *candidates)


def _source_hash(result_dir: Path, payload: dict[str, Any]) -> str:
    files = _dict(payload.get("result_files"))
    input_file = str(files.get("input", "")).strip()
    candidates = [result_dir / input_file] if input_file else []
    input_dir = result_dir / "input"
    if input_dir.is_dir():
        candidates.extend(
            path for path in input_dir.iterdir() if path.is_file()
        )
    for path in candidates:
        if path.is_file():
            return _hash_bytes(path.read_bytes())
    return _hash_json(payload)


def _control_signal_terms(configuration: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    for group in _dict_list(configuration.get("signal_inputs")):
        items = group.get("items", [])
        if isinstance(items, list):
            terms.extend(
                str(item).strip() for item in items if str(item).strip()
            )
    for mode in _dict_list(configuration.get("control_modes")):
        for key in ("controller", "action", "mode"):
            value = str(mode.get(key, "")).strip()
            if value:
                terms.append(value)
    return _unique(terms)


def _page_control_signals(payload: dict[str, Any], page: int) -> list[str]:
    config = _dict(payload.get("control_signal_configuration"))
    page_terms: list[str] = []
    for group in _dict_list(config.get("signal_inputs")):
        if int(group.get("page") or page) != page:
            continue
        items = group.get("items", [])
        if isinstance(items, list):
            page_terms.extend(
                str(item).strip() for item in items if str(item).strip()
            )
    if page_terms:
        return _unique(page_terms)
    return _control_signal_terms(config)


def _component_summary(component: dict[str, Any]) -> str:
    return _join_values(
        component.get("code"),
        component.get("label"),
        component.get("component_type"),
        component.get("evidence"),
    )


def _component_groups(
    components: list[dict[str, Any]],
) -> list[tuple[int, str, list[dict[str, Any]]]]:
    grouped: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for component in components:
        page = int(component.get("page") or 0) or 1
        component_type = (
            str(component.get("component_type", "")).strip()
            or "未分类元件"
        )
        grouped[(page, component_type)].append(component)
    return [
        (page, component_type, grouped[(page, component_type)])
        for page, component_type in sorted(grouped)
    ]


def _component_group_text(
    *,
    page: int,
    component_type: str,
    components: list[dict[str, Any]],
    corrections: dict[str, dict[str, str]],
) -> str:
    items = []
    correction_lines = []
    for component in components:
        codes = ",".join(_split_codes(component.get("code", "")))
        label = str(component.get("label", "")).strip()
        count = int(component.get("occurrence_count") or 1)
        items.append(f"{codes} {label}，共{count}个。".strip())
        reference_id = str(component.get("reference_id", "")).strip()
        correction = corrections.get(reference_id)
        if correction:
            correction_lines.append(
                _join_values(
                    f"原始叫法：{correction.get('raw_label', '')}",
                    f"最终名称：{correction.get('label', label)}",
                    f"修正原因：{correction.get('correction_reason', '')}",
                )
            )
    return _join_lines(
        [
            f"第{page}页{component_type}。",
            "元件：" + "；".join(items),
            "修正语义：" + "；".join(correction_lines),
        ]
    )


def _component_row_text(row: dict[str, Any]) -> str:
    return _join_values(
        row.get("code") or row.get("代号") or row.get("浠ｅ彿"),
        row.get("label") or row.get("元件名称") or row.get("鍏冧欢鍚嶇О"),
        row.get("model") or row.get("规格型号") or row.get("瑙勬牸鍨嬪彿"),
        row.get("quantity") or row.get("数量"),
        row.get("note") or row.get("备注"),
    )


def _combination_text(combination: dict[str, Any]) -> str:
    members = []
    for member in _dict_list(combination.get("members")):
        members.append(
            _join_values(
                member.get("role", ""),
                ",".join(_string_list(member.get("codes"))),
                ",".join(_string_list(member.get("labels"))),
            )
        )
    return _join_lines(
        [
            f"组合功能：{combination.get('name', '')}",
            f"规则：{combination.get('rule_id', '')}",
            f"层级：{combination.get('rule_layer', '')}",
            f"组号：{combination.get('group_code', '')}",
            "成员：" + "；".join(members),
            "证据：" + "；".join(
                _string_list(combination.get("evidence"))
            ),
        ]
    )


def _pages(value: object) -> list[int]:
    pages: list[int] = []
    if isinstance(value, list):
        for item in value:
            try:
                pages.append(int(item))
            except (TypeError, ValueError):
                continue
    return pages


def _first_page(value: object) -> int | None:
    pages = _pages(value)
    return pages[0] if pages else None


def _split_codes(value: object) -> list[str]:
    return [
        item.strip()
        for item in str(value or "")
        .replace("，", ",")
        .replace(";", ",")
        .split(",")
        if item.strip()
    ]


def _join_values(*values: object) -> str:
    return " ".join(
        str(value).strip()
        for value in values
        if str(value or "").strip()
    )


def _join_lines(values: list[str]) -> str:
    return "\n".join(value for value in values if value.strip())


def _unique(values: object) -> list[str]:
    flattened: list[str] = []
    for value in values:
        if isinstance(value, list):
            flattened.extend(str(item) for item in value)
        else:
            flattened.append(str(value))
    seen: set[str] = set()
    result: list[str] = []
    for value in flattened:
        text = value.strip()
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _slug(value: str) -> str:
    return value.replace(" ", "-").replace("/", "-").lower()


def _correction_index(
    rag_corrections: list[dict[str, Any]],
) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for item in rag_corrections:
        reference_id = str(item.get("reference_id", "")).strip()
        if reference_id:
            index[reference_id] = {
                "raw_label": str(item.get("raw_label", "")).strip(),
                "label": str(item.get("label", "")).strip(),
                "correction_reason": str(
                    item.get("correction_reason", "")
                ).strip(),
            }
    return index


def _deduplicate_exact_terms(terms: list[ExactTerm]) -> list[ExactTerm]:
    seen: set[tuple[str, str, str, int | None, str]] = set()
    result: list[ExactTerm] = []
    for term in terms:
        key = (
            term.drawing_id,
            term.term_type,
            term.normalized_value,
            term.page,
            term.chunk_id,
        )
        if key in seen or not term.normalized_value:
            continue
        seen.add(key)
        result.append(term)
    return result


def _hash_json(payload: object) -> str:
    return _hash_text(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
