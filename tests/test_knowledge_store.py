from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from PIL import Image

from electronic_recognition.custom_rule_store import (
    BuiltinRuleReadonlyError,
    ComponentReferencedError,
    CustomRuleStore,
)
from electronic_recognition.knowledge_store import (
    ComponentAlreadyExistsError,
    InvalidComponentPayloadError,
    KnowledgeStore,
)


def _write_components(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "version": 2,
                "components": [
                    {
                        "id": "lamp",
                        "label": "指示灯",
                        "image_path": "assets/components/lamp.png",
                        "component_type": "指示灯",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_rules(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "rules": [
                    {
                        "id": "builtin-rule",
                        "name": "内置规则",
                        "engine": "builtin",
                        "members": [],
                    },
                    {
                        "id": "user-rule",
                        "name": "用户规则",
                        "engine": "declarative",
                        "members": [
                            {
                                "role": "主指示",
                                "component_ids": ["lamp"],
                            }
                        ],
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_knowledge_store_creates_component_and_normalizes_fields() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        path = root / "components.json"
        _write_components(path)
        store = KnowledgeStore(path)

        component = store.create_component(
            {
                "id": "motor-protect",
                "label": "电机保护器",
                "image_path": "assets/components/motor-protect.png",
                "component_type": "保护器件",
                "aliases": [" MP ", "mp", ""],
                "standards": [" GB ", "GB"],
            }
        )

        assert component.id == "motor-protect"
        assert component.aliases == ["MP"]
        assert component.standards == ["GB"]
        reloaded = json.loads(path.read_text(encoding="utf-8"))
        assert any(
            item["id"] == "motor-protect"
            for item in reloaded["components"]
        )


def test_knowledge_store_rejects_duplicate_component_id() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        path = root / "components.json"
        _write_components(path)
        store = KnowledgeStore(path)

        with pytest.raises(ComponentAlreadyExistsError):
            store.create_component(
                {
                    "id": "lamp",
                    "label": "重复指示灯",
                    "image_path": "assets/components/lamp-2.png",
                }
            )


def test_custom_rule_store_blocks_deleting_referenced_component() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        components_path = root / "components.json"
        rules_path = root / "custom_rules.json"
        _write_components(components_path)
        _write_rules(rules_path)
        store = CustomRuleStore(rules_path)

        with pytest.raises(ComponentReferencedError) as exc:
            store.assert_component_not_referenced("lamp")

        assert exc.value.references == ["user-rule"]


def test_custom_rule_store_rejects_updating_builtin_rule() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        rules_path = root / "custom_rules.json"
        _write_rules(rules_path)
        store = CustomRuleStore(rules_path)

        with pytest.raises(BuiltinRuleReadonlyError):
            store.update_rule(
                "builtin-rule",
                {
                    "name": "内置规则-修改",
                    "members": [],
                },
            )


def test_knowledge_store_can_attach_variant_image() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        path = root / "components.json"
        _write_components(path)
        store = KnowledgeStore(path)
        image = root / "variant.png"
        Image.new("RGB", (24, 24), "white").save(image)

        updated = store.add_component_image("lamp", image.read_bytes(), "variant.png")

        assert len(updated.variant_images) == 1
        saved_path = root / updated.variant_images[0]
        assert saved_path.is_file()


def test_knowledge_store_rejects_unmanaged_image_paths() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        path = root / "components.json"
        _write_components(path)
        store = KnowledgeStore(path)

        with pytest.raises(InvalidComponentPayloadError):
            store.update_component(
                "lamp",
                {
                    "label": "指示灯",
                    "image_path": "../../secret.txt",
                },
            )
