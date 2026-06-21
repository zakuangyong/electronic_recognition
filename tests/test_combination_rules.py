from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from electronic_recognition import api
from electronic_recognition.combination_rules import detect_combinations
from electronic_recognition.custom_rules import CustomRuleKnowledgeBase


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


def test_custom_rules_are_loaded_and_applied_after_component_detection() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        rules_path = root / "custom_rules.json"
        rules_path.write_text(
            json.dumps(
                {
                    "rules": [
                        {
                            "id": "custom-status",
                            "name": "自定义状态组合",
                            "scope": "same_page",
                            "members": [
                                {
                                    "role": "辅助触点",
                                    "min_quantity": 3,
                                    "code_patterns": ["^QF$"],
                                },
                                {
                                    "role": "红灯",
                                    "code_patterns": ["^HR$"],
                                },
                                {
                                    "role": "黄灯",
                                    "code_patterns": ["^HY$"],
                                },
                                {
                                    "role": "绿灯",
                                    "code_patterns": ["^HG$"],
                                },
                            ],
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        rules = CustomRuleKnowledgeBase.load(rules_path)

        combinations = detect_combinations(
            [
                {
                    "label": "断路器辅助触点",
                    "code": "QF",
                    "page": 1,
                    "occurrence_count": 3,
                },
                {
                    "label": "指示灯",
                    "code": "HR,HY,HG",
                    "page": 1,
                    "occurrence_count": 3,
                },
            ],
            custom_rules=rules,
        )

        result = next(
            item
            for item in combinations
            if item["rule_id"] == "custom-status"
        )
        assert result["rule_layer"] == "custom"
        assert result["pages"] == [1]
        assert result["group_code"] == "QF,HR,HY,HG"
        assert [member["quantity"] for member in result["members"]] == [
            3,
            1,
            1,
            1,
        ]


def test_custom_same_page_rule_does_not_join_components_across_pages() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        rules_path = root / "custom_rules.json"
        rules_path.write_text(
            json.dumps(
                {
                    "rules": [
                        {
                            "id": "same-page",
                            "name": "同页规则",
                            "members": [
                                {
                                    "role": "A",
                                    "code_patterns": ["^A$"],
                                },
                                {
                                    "role": "B",
                                    "code_patterns": ["^B$"],
                                },
                            ],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        combinations = detect_combinations(
            [
                {"label": "A", "code": "A", "page": 1},
                {"label": "B", "code": "B", "page": 2},
            ],
            custom_rules=CustomRuleKnowledgeBase.load(rules_path),
        )

        assert not any(
            item["rule_id"] == "same-page"
            for item in combinations
        )


def test_component_and_custom_rule_apis_use_separate_catalogs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        image = root / "rule.png"
        image.write_bytes(b"png")
        components_path = root / "components.json"
        components_path.write_text(
            json.dumps(
                {
                    "components": [
                        {
                            "id": "lamp",
                            "label": "指示灯",
                            "image_path": "lamp.png",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        rules_path = root / "custom_rules.json"
        rules_path.write_text(
            json.dumps(
                {
                    "rules": [
                        {
                            "id": "custom-rule",
                            "name": "自定义组合",
                            "image_path": "rule.png",
                            "members": [
                                {
                                    "role": "指示灯",
                                    "code_patterns": ["^HL$"],
                                }
                            ],
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(api, "KNOWLEDGE_PATH", components_path)
        monkeypatch.setattr(api, "CUSTOM_RULES_PATH", rules_path)

        components = api.knowledge_items()
        rules = api.custom_rule_items()
        config = api.config()

        assert components["count"] == 1
        assert components["items"][0]["id"] == "lamp"
        assert rules["count"] == 1
        assert rules["items"][0]["id"] == "custom-rule"
        assert config["component_count"] == 1
        assert config["custom_rule_count"] == 1


def test_project_rule_catalog_contains_three_builtin_and_one_custom() -> None:
    root = Path(__file__).resolve().parents[1]
    rules = CustomRuleKnowledgeBase.load(
        root / "data" / "index" / "custom_rules.json"
    )

    assert len(rules.rules) == 4
    assert {
        rule.id
        for rule in rules.rules
        if rule.engine == "builtin"
    } == {
        "coil_contact_group",
        "motor_start_protection",
        "start_stop_indicator",
    }
    assert rules.by_id["user-custom-combination-1"].engine == "declarative"
    assert all(
        rules.image_path(rule).is_file()
        for rule in rules.rules
    )


def test_disabled_builtin_rule_is_not_evaluated() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        rules_path = root / "custom_rules.json"
        rules_path.write_text(
            json.dumps(
                {
                    "rules": [
                        {
                            "id": "coil_contact_group",
                            "name": "线圈触点组合",
                            "engine": "builtin",
                            "enabled": False,
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        combinations = detect_combinations(
            [],
            open_symbols=[
                {"raw_label": "继电器线圈", "code": "K1", "page": 1},
                {"raw_label": "继电器辅助触点", "code": "K1", "page": 1},
            ],
            custom_rules=CustomRuleKnowledgeBase.load(rules_path),
        )

        assert not combinations
