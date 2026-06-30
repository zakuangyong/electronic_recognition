from __future__ import annotations

from electronic_recognition.config import Settings


def test_search_vector_min_score_loads_from_env_file(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("ER_SEARCH_VECTOR_MIN_SCORE", raising=False)
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "ER_SEARCH_VECTOR_MIN_SCORE=0.72\n",
        encoding="utf-8",
    )

    settings = Settings.from_env(dotenv_path)

    assert settings.search_vector_min_score == 0.72
