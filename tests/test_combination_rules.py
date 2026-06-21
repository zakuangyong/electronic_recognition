from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from electronic_recognition import api
from electronic_recognition.combination_rules import detect_combinations


def test_detects_coil_and_contacts_by_exact_code() -> None:
    combinations = detect_combinations(
        [],
        open_symbols=[
            {
                "raw_label": "接触器线圈",
                "component_type": "线圈",
                "code": "KM1",
                "page": 1,
            },
            {
                "raw_label": "接触器辅助触点",
                "component_type": "触点",
                "code": "KM1",
                "page": 2,
                "occurrence_count": 2,
            },
            {
                "raw_label": "继电器辅助触点",
                "component_type": "触点",
                "code": "K2",
                "page": 1,
            },
        ],
    )

    assert len(combinations) == 1
    result = combinations[0]
    assert result["rule_id"] == "coil_contact_group"
    assert result["group_code"] == "KM1"
    assert result["physical_quantity"] == 1
    assert result["members"][1]["quantity"] == 2


def test_detects_motor_start_and_start_stop_indicator_rules() -> None:
    combinations = detect_combinations(
        [
            {"label": "三极断路器", "code": "QF1", "page": 1},
            {"label": "接触器线圈", "code": "KM1", "page": 1},
            {"label": "热继电器/过载保护器", "code": "F1", "page": 1},
            {"label": "指示灯", "code": "G1,R1,Y1", "page": 1},
            {"label": "中间继电器", "code": "KA1", "page": 1},
        ],
        open_symbols=[
            {"raw_label": "接触器线圈", "code": "KM1", "page": 1},
            {"raw_label": "接触器辅助触点", "code": "KM1", "page": 1},
        ],
        component_table={
            "rows": [
                {"代号": "QF1,KM1,F1,P1", "元件名称": ""},
                {"代号": "SF1", "元件名称": "按钮", "备注": "启动"},
                {"代号": "SS1", "元件名称": "按钮", "备注": "停止"},
                {"代号": "G1", "元件名称": "指示灯", "备注": "停机指示"},
                {"代号": "R1", "元件名称": "指示灯", "备注": "开机指示"},
                {"代号": "Y1", "元件名称": "指示灯", "备注": "故障指示"},
                {"代号": "KA1", "元件名称": "中间继电器"},
            ]
        },
        title_block={"fields": {"图纸名称": "排烟风机控制原理"}},
        control_signal_configuration={
            "raw_control_modes": ["FAS启停"],
            "raw_signal_inputs": ["风机", "运行", "故障"],
        },
    )

    rule_ids = {item["rule_id"] for item in combinations}
    assert rule_ids == {
        "coil_contact_group",
        "motor_start_protection",
        "start_stop_indicator",
    }
    motor = next(
        item
        for item in combinations
        if item["rule_id"] == "motor_start_protection"
    )
    assert "P1" in motor["group_code"]
    start_stop = next(
        item
        for item in combinations
        if item["rule_id"] == "start_stop_indicator"
    )
    assert any(
        member["role"] == "启动命令"
        and member["codes"] == ["SF1"]
        for member in start_stop["members"]
    )


def test_does_not_infer_start_stop_without_explicit_roles() -> None:
    combinations = detect_combinations(
        [{"label": "指示灯", "code": "G1", "page": 1}],
        component_table={
            "rows": [
                {"代号": "SA1", "元件名称": "按钮", "备注": "自动/手动"},
                {"代号": "G1", "元件名称": "指示灯"},
                {"代号": "K1", "元件名称": "中间继电器"},
            ]
        },
    )

    assert not any(
        item["rule_id"] == "start_stop_indicator"
        for item in combinations
    )


def test_saved_legacy_result_is_hydrated_with_combinations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        result_dir = root / "legacy"
        result_dir.mkdir()
        (result_dir / "result.json").write_text(
            json.dumps(
                {
                    "document": "legacy.pdf",
                    "detected_components": [],
                    "recognition_steps": {
                        "open_symbols": [
                            {
                                "raw_label": "继电器线圈",
                                "code": "K1",
                                "page": 1,
                            },
                            {
                                "raw_label": "继电器辅助触点",
                                "code": "K1",
                                "page": 1,
                            },
                        ]
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(api, "RESULT_DIR", root)

        result = api.saved_result("legacy")

        assert result["detected_combinations"][0]["group_code"] == "K1"
