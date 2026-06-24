from __future__ import annotations

import json

from electronic_recognition.search import rebuild as rebuild_module


class _FakeSettings:
    search_sqlite_path = "fake.db"


class _FakeService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def rebuild(
        self,
        result_root,
        *,
        force: bool = False,
        result_id: str = "",
        mode: str = "all",
    ) -> dict[str, object]:
        self.calls.append(
            {
                "result_root": str(result_root),
                "force": force,
                "result_id": result_id,
                "mode": mode,
            }
        )
        return {
            "indexed": 1,
            "skipped": 0,
            "failed": [],
            "mode": mode,
        }


def test_rebuild_cli_accepts_mode_argument(
    monkeypatch,
    capsys,
) -> None:
    service = _FakeService()

    monkeypatch.setattr(
        rebuild_module.Settings,
        "from_env",
        classmethod(lambda cls: _FakeSettings()),
    )
    monkeypatch.setattr(
        rebuild_module,
        "DrawingSearchStore",
        lambda path: object(),
    )
    monkeypatch.setattr(
        rebuild_module,
        "DrawingIndexService",
        lambda store: service,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "rebuild",
            "--result-root",
            "custom-result",
            "--result-id",
            "result-7",
            "--mode",
            "vector",
            "--force",
        ],
    )

    exit_code = rebuild_module.main()

    assert exit_code == 0
    assert service.calls == [
        {
            "result_root": "custom-result",
            "force": True,
            "result_id": "result-7",
            "mode": "vector",
        }
    ]
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "vector"
