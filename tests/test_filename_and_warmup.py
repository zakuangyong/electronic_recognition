from __future__ import annotations

from electronic_recognition import api


def test_safe_filename_recovers_mojibake_utf8() -> None:
    original = "原理图_05.pdf"
    # Simulate Starlette decoding UTF-8 bytes as latin-1 (the upload mojibake).
    mojibake = original.encode("utf-8").decode("latin-1")
    assert mojibake != original
    assert api._safe_filename(mojibake) == original


def test_safe_filename_keeps_plain_ascii() -> None:
    assert api._safe_filename("A17387_06.pdf") == "A17387_06.pdf"


def test_safe_filename_keeps_already_correct_unicode() -> None:
    # A correct UTF-8 string that cannot be latin-1 encoded is returned as-is.
    assert api._safe_filename("原理图.pdf") == "原理图.pdf"


def test_run_search_warmup_sets_error_on_qdrant_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        api.Settings,
        "from_env",
        staticmethod(
            lambda *a, **k: api.Settings(
                search_enabled=True, search_mode="hybrid"
            )
        ),
    )

    class _Store:
        def initialize(self) -> None:
            return None

    class _Vector:
        def ping(self) -> bool:
            raise RuntimeError("Storage folder data/search/qdrant is already accessed")

    monkeypatch.setattr(api, "_search_store", lambda settings: _Store())
    monkeypatch.setattr(
        api, "_embedding_backend", lambda settings: api.DisabledEmbeddingBackend()
    )
    monkeypatch.setattr(api, "_vector_store", lambda settings: _Vector())
    monkeypatch.setattr(api, "SEARCH_WARMUP_ERROR", "")

    api._run_search_warmup()

    assert "qdrant" in api.SEARCH_WARMUP_ERROR


def test_search_health_reports_warmup_error(monkeypatch) -> None:
    monkeypatch.setattr(
        api.Settings,
        "from_env",
        staticmethod(
            lambda *a, **k: api.Settings(
                search_enabled=True, search_mode="hybrid"
            )
        ),
    )

    class _Service:
        def health(self) -> dict:
            return {"degraded": False, "status": "ok"}

    monkeypatch.setattr(api, "_search_service", lambda settings: _Service())
    monkeypatch.setattr(api, "SEARCH_WARMUP_ERROR", "qdrant: stale lock")

    status = api.search_health()

    assert status["enabled"] is True
    assert status["degraded"] is True
    assert status["warmup_error"] == "qdrant: stale lock"
