from __future__ import annotations

import importlib
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from electronic_recognition import runtime
from electronic_recognition.api import enable_production_frontend


def test_runtime_project_root_uses_env_override(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ER_PROJECT_ROOT", str(tmp_path))

    assert runtime.project_root() == tmp_path.resolve()


def test_runtime_project_root_uses_executable_dir_when_frozen(
    monkeypatch,
    tmp_path: Path,
) -> None:
    executable = tmp_path / "ElectronicRecognition.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.delenv("ER_PROJECT_ROOT", raising=False)

    assert runtime.project_root() == tmp_path.resolve()


def test_api_paths_follow_project_root_env(monkeypatch, tmp_path: Path) -> None:
    from electronic_recognition import api

    with monkeypatch.context() as scoped:
        scoped.setenv("ER_PROJECT_ROOT", str(tmp_path))
        reloaded = importlib.reload(api)

        assert reloaded.PROJECT_ROOT == tmp_path.resolve()
        assert reloaded.RESULT_DIR == tmp_path.resolve() / "result"
        assert reloaded.DIFF_JOB_DIR == tmp_path.resolve() / "data" / "diff" / "jobs"

    importlib.reload(api)


def test_production_frontend_serves_spa_without_capturing_api(tmp_path: Path) -> None:
    dist_dir = tmp_path / "web_dist"
    asset_dir = dist_dir / "assets"
    asset_dir.mkdir(parents=True)
    (dist_dir / "index.html").write_text("<main>app shell</main>", encoding="utf-8")
    (asset_dir / "app.js").write_text("console.log('ok')", encoding="utf-8")

    app = FastAPI()
    enable_production_frontend(dist_dir, api_app=app)
    client = TestClient(app)

    assert client.get("/").text == "<main>app shell</main>"
    assert client.get("/workbench").text == "<main>app shell</main>"
    assert "console.log" in client.get("/assets/app.js").text
    assert client.get("/api/missing").status_code == 404
