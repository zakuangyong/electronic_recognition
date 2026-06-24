from __future__ import annotations

import json
from pathlib import Path

from electronic_recognition.search.document_builder import DrawingDocumentBuilder
from electronic_recognition.search.json_result_loader import JsonResultLoader


def test_loader_prefers_steps_for_final_components_and_combinations(
    tmp_path: Path,
) -> None:
    result_dir = _write_result_tree(
        tmp_path / "result-100",
        result_payload={
            "document": "demo.pdf",
            "detected_components": [{"code": "OLD1", "label": "旧元件", "page": 1}],
            "detected_combinations": [{"name": "旧组合", "pages": [1]}],
            "preview_pages": [{"page": 1}],
            "meta": {"page_count": 1},
        },
        step_payloads={
            "06-detected-components.json": [
                {
                    "code": "K1",
                    "label": "交流继电器线圈",
                    "component_type": "继电器",
                    "reference_id": "relay-coil",
                    "page": 1,
                }
            ],
            "06-detected-combinations.json": [
                {
                    "name": "继电器线圈与辅助触点组合",
                    "rule_id": "coil_contact_group",
                    "rule_layer": "builtin",
                    "group_code": "K1",
                    "pages": [1],
                    "members": [
                        {
                            "role": "线圈",
                            "codes": ["K1"],
                            "labels": ["交流继电器线圈"],
                        }
                    ],
                    "evidence": ["线圈与触点使用相同基础代号"],
                }
            ],
        },
    )

    loaded = JsonResultLoader().load(result_dir)

    assert loaded.payload["detected_components"][0]["code"] == "K1"
    assert loaded.payload["detected_combinations"][0]["name"] == "继电器线圈与辅助触点组合"
    assert {entry["path"] for entry in loaded.audit_files} >= {
        "result.json",
        "steps/06-detected-components.json",
        "steps/06-detected-combinations.json",
    }


def test_document_builder_adds_component_group_chunk_and_combination_metadata(
    tmp_path: Path,
) -> None:
    result_dir = _write_result_tree(
        tmp_path / "result-101",
        result_payload={
            "document": "fan-control.pdf",
            "title_block": {
                "fields": {
                    "drawing_title": "风阀控制原理图",
                    "drawing_number": "CDDT-6-DZ-.07",
                    "project_name": "成都轨道交通18号线工程",
                }
            },
            "preview_pages": [{"page": 1}],
            "meta": {"page_count": 1},
        },
        step_payloads={
            "05-rag-corrections.json": [
                {
                    "reference_id": "relay-coil",
                    "raw_label": "中间继电器",
                    "label": "交流继电器线圈",
                    "component_type": "继电器",
                    "correction_reason": "根据控制输出回路线圈符号修正",
                }
            ],
            "06-detected-components.json": [
                {
                    "code": "K1",
                    "label": "交流继电器线圈",
                    "component_type": "继电器",
                    "reference_id": "relay-coil",
                    "page": 1,
                    "occurrence_count": 3,
                },
                {
                    "code": "SA1",
                    "label": "选择开关",
                    "component_type": "开关",
                    "reference_id": "selector-switch",
                    "page": 1,
                },
            ],
            "06-detected-combinations.json": [
                {
                    "name": "继电器线圈与辅助触点组合",
                    "rule_id": "coil_contact_group",
                    "rule_layer": "builtin",
                    "group_code": "K1",
                    "pages": [1],
                    "members": [
                        {
                            "role": "线圈",
                            "codes": ["K1"],
                            "labels": ["交流继电器线圈"],
                        }
                    ],
                    "evidence": ["线圈与触点使用相同基础代号"],
                }
            ],
        },
    )
    loaded = JsonResultLoader().load(result_dir)

    document = DrawingDocumentBuilder().build("result-101", result_dir, loaded.payload)

    assert document.schema_version == 2
    assert document.control_signals == []
    component_group = next(
        chunk
        for chunk in document.chunks
        if chunk.chunk_type == "component_group"
        and chunk.metadata["component_type"] == "继电器"
    )
    combination = next(
        chunk for chunk in document.chunks if chunk.chunk_type == "combination"
    )

    assert "中间继电器" in component_group.text
    assert "根据控制输出回路线圈符号修正" in component_group.text
    assert component_group.metadata["component_type"] == "继电器"
    assert component_group.metadata["page"] == 1
    assert combination.metadata["rule_id"] == "coil_contact_group"
    assert combination.metadata["rule_layer"] == "builtin"
    assert combination.metadata["group_code"] == "K1"


def _write_result_tree(
    result_dir: Path,
    *,
    result_payload: dict[str, object],
    step_payloads: dict[str, object],
) -> Path:
    result_dir.mkdir(parents=True)
    (result_dir / "steps").mkdir()
    (result_dir / "result.json").write_text(
        json.dumps(result_payload, ensure_ascii=False),
        encoding="utf-8",
    )
    for name, payload in step_payloads.items():
        (result_dir / "steps" / name).write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
    return result_dir
