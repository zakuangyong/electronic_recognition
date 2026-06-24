from __future__ import annotations

import math
import importlib.util
from typing import Any, Callable, Protocol


class EmbeddingBackend(Protocol):
    @property
    def model_id(self) -> str:
        ...

    @property
    def dimension(self) -> int:
        ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_query(self, text: str) -> list[float]:
        ...


class DisabledEmbeddingBackend:
    def __init__(self, reason: str = "disabled") -> None:
        self.reason = reason

    @property
    def model_id(self) -> str:
        return "disabled"

    @property
    def dimension(self) -> int:
        return 0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return []

    def embed_query(self, text: str) -> list[float]:
        return []

    def is_available(self) -> bool:
        return False


class SentenceTransformerEmbeddingBackend:
    def __init__(
        self,
        *,
        model_id: str,
        batch_size: int = 8,
        normalize: bool = True,
        device: str = "cpu",
        model_path: str = "",
        model_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._model_id = model_id
        self.batch_size = batch_size
        self.normalize = normalize
        self.device = device
        self.model_path = model_path
        self.model_factory = model_factory
        self._model: Any | None = None
        self._dimension = 0

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._encode(texts)
        self._dimension = len(vectors[0]) if vectors else self._dimension
        return vectors

    def embed_query(self, text: str) -> list[float]:
        if not text.strip():
            return []
        vectors = self._encode([text])
        self._dimension = len(vectors[0]) if vectors else self._dimension
        return vectors[0] if vectors else []

    def is_available(self) -> bool:
        return (
            self.model_factory is not None
            or importlib.util.find_spec("sentence_transformers") is not None
        )

    def _encode(self, texts: list[str]) -> list[list[float]]:
        model = self._get_model()
        vectors = model.encode(
            texts,
            normalize_embeddings=False,
            batch_size=self.batch_size,
            show_progress_bar=False,
        )
        result = [
            [float(value) for value in vector]
            for vector in list(vectors)
        ]
        if self.normalize:
            return [_normalize(vector) for vector in result]
        return result

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model
        if self.model_factory is not None:
            self._model = self.model_factory()
            return self._model
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers 未安装，无法启用向量检索。"
            ) from exc
        model_source = self.model_path or self._model_id
        try:
            self._model = SentenceTransformer(
                model_source,
                device=self.device,
            )
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                f"Embedding 模型加载失败: {model_source}"
            ) from exc
        return self._model


def _normalize(vector: list[float]) -> list[float]:
    length = math.sqrt(sum(value * value for value in vector))
    if length <= 0:
        return [0.0 for _ in vector]
    return [value / length for value in vector]
