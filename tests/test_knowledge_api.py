from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image

from electronic_recognition import api


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (24, 24), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_component_crud_flow(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        components_path = root / "components.json"
        rules_path = root / "custom_rules.json"
        assets = root / "assets" / "components"
        assets.mkdir(parents=True)
        components_path.write_text(
            json.dumps({"version": 2, "components": []}, ensure_ascii=False),
            encoding="utf-8",
        )
        rules_path.write_text(
            json.dumps({"version": 1, "rules": []}, ensure_ascii=False),
            encoding="utf-8",
        )
        monkeypatch.setattr(api, "KNOWLEDGE_PATH", components_path)
        monkeypatch.setattr(api, "CUSTOM_RULES_PATH", rules_path)

        created = api.create_knowledge_item(
            {
                "id": "lamp",
                "label": "指示灯",
                "image_path": "assets/components/lamp.png",
                "component_type": "指示灯",
            }
        )
        assert created["id"] == "lamp"

        upload = UploadFile(
            filename="lamp.png",
            file=io.BytesIO(_png_bytes()),
        )
        uploaded = api.upload_knowledge_image(
            "lamp",
            file=upload,
            kind="primary",
        )
        assert uploaded["image_url"].endswith("/api/knowledge/lamp/image")

        listed = api.knowledge_items()
        assert listed["count"] == 1


def test_rule_api_blocks_deleting_referenced_component(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        components_path = root / "components.json"
        rules_path = root / "custom_rules.json"
        components_path.write_text(
            json.dumps(
                {
                    "version": 2,
                    "components": [
                        {
                            "id": "lamp",
                            "label": "指示灯",
                            "image_path": "assets/components/lamp.png",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        rules_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "rules": [
                        {
                            "id": "user-rule",
                            "name": "自定义规则",
                            "engine": "declarative",
                            "members": [
                                {
                                    "role": "主灯",
                                    "component_ids": ["lamp"],
                                }
                            ],
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(api, "KNOWLEDGE_PATH", components_path)
        monkeypatch.setattr(api, "CUSTOM_RULES_PATH", rules_path)

        with pytest.raises(HTTPException) as exc:
            api.delete_knowledge_item("lamp")

        assert exc.value.status_code == 409
        payload = {"detail": exc.value.detail}
        assert payload["detail"]["code"] == "component_referenced"
        assert payload["detail"]["references"] == ["user-rule"]
