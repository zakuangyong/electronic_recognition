from __future__ import annotations

import math
import sys
import types

from electronic_recognition.search.embedding import (
    DisabledEmbeddingBackend,
    SentenceTransformerEmbeddingBackend,
)


def _install_fake_sentence_transformers(monkeypatch) -> dict:
    captured: dict = {}

    class _FakeST:
        def __init__(self, source, **kwargs) -> None:
            captured["source"] = source
            captured["kwargs"] = kwargs

        def encode(self, texts, **_kwargs):
            return [[1.0, 0.0] for _ in texts]

    module = types.ModuleType("sentence_transformers")
    module.SentenceTransformer = _FakeST
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    return captured


def test_embedding_model_path_loads_offline(monkeypatch) -> None:
    captured = _install_fake_sentence_transformers(monkeypatch)
    backend = SentenceTransformerEmbeddingBackend(
        model_id="BAAI/bge-small-zh-v1.5",
        model_path="data/models/bge-small-zh-v1.5",
    )

    backend.embed_query("hi")

    assert captured["source"] == "data/models/bge-small-zh-v1.5"
    assert captured["kwargs"].get("local_files_only") is True


def test_embedding_without_model_path_allows_network(monkeypatch) -> None:
    captured = _install_fake_sentence_transformers(monkeypatch)
    backend = SentenceTransformerEmbeddingBackend(
        model_id="BAAI/bge-small-zh-v1.5",
    )

    backend.embed_query("hi")

    assert captured["source"] == "BAAI/bge-small-zh-v1.5"
    assert "local_files_only" not in captured["kwargs"]


class _FakeSentenceTransformerModel:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def encode(
        self,
        texts: list[str],
        *,
        normalize_embeddings: bool,
        batch_size: int,
        show_progress_bar: bool,
    ) -> list[list[float]]:
        self.calls.append(list(texts))
        if len(texts) == 1 and texts[0] == "query":
            return [[3.0, 4.0]]
        return [[1.0, 2.0], [0.0, 5.0]]


def test_disabled_embedding_backend_returns_empty_vectors() -> None:
    backend = DisabledEmbeddingBackend(reason="not configured")

    assert backend.model_id == "disabled"
    assert backend.dimension == 0
    assert backend.embed_documents(["a", "b"]) == []
    assert backend.embed_query("query") == []


def test_sentence_transformer_backend_normalizes_vectors() -> None:
    fake_model = _FakeSentenceTransformerModel()
    backend = SentenceTransformerEmbeddingBackend(
        model_id="fake-model",
        batch_size=4,
        normalize=True,
        model_factory=lambda: fake_model,
    )

    documents = backend.embed_documents(["doc-a", "doc-b"])
    query = backend.embed_query("query")

    assert fake_model.calls == [["doc-a", "doc-b"], ["query"]]
    assert backend.dimension == 2
    assert math.isclose(documents[0][0], 1 / math.sqrt(5), rel_tol=1e-6)
    assert math.isclose(documents[0][1], 2 / math.sqrt(5), rel_tol=1e-6)
    assert math.isclose(query[0], 0.6, rel_tol=1e-6)
    assert math.isclose(query[1], 0.8, rel_tol=1e-6)
