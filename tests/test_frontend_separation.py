from __future__ import annotations

from fastapi.testclient import TestClient

from electronic_recognition.api import app


def test_backend_does_not_serve_legacy_static_frontend() -> None:
    client = TestClient(app)

    response = client.get("/static/index.html")

    assert response.status_code == 404

