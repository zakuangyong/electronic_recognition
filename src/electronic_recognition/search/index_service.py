from __future__ import annotations

import json
import time
from pathlib import Path
from uuid import uuid4

from .embedding import DisabledEmbeddingBackend
from .document_builder import DrawingDocumentBuilder
from .sqlite_store import DrawingSearchStore


class DrawingIndexService:
    def __init__(
        self,
        store: DrawingSearchStore,
        builder: DrawingDocumentBuilder | None = None,
        *,
        embedding_backend: object | None = None,
        vector_store: object | None = None,
    ) -> None:
        self.store = store
        self.builder = builder or DrawingDocumentBuilder()
        self.embedding_backend = embedding_backend or DisabledEmbeddingBackend()
        self.vector_store = vector_store

    def index_result(
        self,
        result_id: str,
        result_dir: Path,
        *,
        mode: str = "all",
        force: bool = False,
    ) -> dict[str, object]:
        result_path = result_dir / "result.json"
        if not result_path.is_file():
            raise FileNotFoundError(result_path)
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("result.json must contain an object")
        document = self.builder.build(result_id, result_dir, payload)
        existing = self.store.result_status(result_id)
        unchanged = (
            existing.get("status") == "complete"
            and existing.get("content_hash") == document.content_hash
        )
        embedding_model = getattr(
            self.embedding_backend,
            "model_id",
            "disabled",
        )
        vector_current = (
            unchanged
            and existing.get("vector_status") == "complete"
            and existing.get("embedding_model") == embedding_model
            and existing.get("builder_version") == self.builder.version
        )
        if not force and (
            (mode == "bm25" and unchanged)
            or (mode == "vector" and vector_current)
            or (mode == "all" and unchanged and vector_current)
        ):
            return {
                "result_id": result_id,
                "drawing_id": document.drawing_id,
                "source_hash": document.source_hash,
                "status": "skipped",
                "chunks": len(document.chunks),
                "vectors": int(existing.get("vector_count", 0) or 0),
                "vector_status": str(
                    existing.get("vector_status", "complete")
                ),
                "vector_error": "",
                "embedding_model": embedding_model,
                "exact_terms": len(document.exact_terms),
            }
        if mode in {"all", "bm25"} and (force or not unchanged):
            self.store.upsert_document(document)
        vectors = 0
        vector_status = "disabled"
        vector_error = ""
        if mode in {"all", "vector"}:
            try:
                if self.vector_store is not None:
                    try:
                        self.vector_store.delete_result(result_id)
                    except Exception:
                        pass
                vectors = self._upsert_vectors(document)
                vector_status = "complete" if vectors else "disabled"
            except Exception as exc:
                vector_status = "vector_failed"
                vector_error = str(exc)
            self.store.update_vector_status(
                result_id,
                status=vector_status,
                vector_count=vectors,
                embedding_model=embedding_model,
                builder_version=self.builder.version,
                error=vector_error,
            )
        return {
            "result_id": result_id,
            "drawing_id": document.drawing_id,
            "source_hash": document.source_hash,
            "status": "complete",
            "chunks": len(document.chunks),
            "vectors": vectors,
            "vector_status": vector_status,
            "vector_error": vector_error,
            "embedding_model": embedding_model,
            "exact_terms": len(document.exact_terms),
        }

    def delete_result(self, result_id: str) -> dict[str, object]:
        deleted = self.store.delete_result(result_id)
        if self.vector_store is not None:
            try:
                self.vector_store.delete_result(result_id)
            except Exception:
                pass
        return {"result_id": result_id, "deleted": deleted}

    def rebuild(
        self,
        result_root: Path,
        *,
        force: bool = False,
        result_id: str = "",
        mode: str = "all",
    ) -> dict[str, object]:
        started = time.perf_counter()
        self.store.initialize()
        result_dirs = (
            [result_root / result_id]
            if result_id
            else [path for path in result_root.iterdir() if path.is_dir()]
        )
        indexed = 0
        skipped = 0
        chunks = 0
        vectors = 0
        source_hashes: set[str] = set()
        duplicates = 0
        failed: list[dict[str, str]] = []
        for result_dir in sorted(result_dirs):
            if not (result_dir / "result.json").is_file():
                skipped += 1
                continue
            try:
                payload = self.index_result(
                    result_dir.name,
                    result_dir,
                    mode=mode,
                    force=force,
                )
                if payload.get("status") == "skipped":
                    skipped += 1
                    continue
                indexed += 1
                chunks += int(payload.get("chunks", 0) or 0)
                vectors += int(payload.get("vectors", 0) or 0)
                source_hash = str(payload.get("source_hash", ""))
                if source_hash:
                    if source_hash in source_hashes:
                        duplicates += 1
                    source_hashes.add(source_hash)
            except Exception as exc:
                failed.append(
                    {"result_id": result_dir.name, "error": str(exc)}
                )
        return {
            "scanned": len(result_dirs),
            "indexed": indexed,
            "skipped": skipped,
            "failed": failed,
            "force": force,
            "mode": mode,
            "chunks": chunks,
            "vectors": vectors,
            "duplicates": duplicates,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "embedding_model": getattr(
                self.embedding_backend,
                "model_id",
                "disabled",
            ),
        }

    def create_job(
        self,
        result_id: str,
        status: str = "pending",
        stage: str = "created",
    ) -> str:
        job_id = uuid4().hex
        # Jobs are currently informational; indexing is synchronous in the
        # first implementation so recognition completion is not blocked by
        # a queue runner.
        return job_id

    def _upsert_vectors(self, document: object) -> int:
        if (
            self.vector_store is None
            or getattr(self.embedding_backend, "model_id", "disabled")
            == "disabled"
        ):
            return 0
        chunks = list(getattr(document, "chunks", []))
        if not chunks:
            return 0
        model_id = getattr(
            self.embedding_backend,
            "model_id",
            "disabled",
        )
        vectors: list[list[float] | None] = []
        missing_indexes: list[int] = []
        missing_texts: list[str] = []
        for index, chunk in enumerate(chunks):
            cached = self.store.get_cached_embedding(
                model_id=model_id,
                builder_version=self.builder.version,
                content_hash=chunk.content_hash,
            )
            vectors.append(cached)
            if cached is None:
                missing_indexes.append(index)
                missing_texts.append(chunk.text)
        if missing_texts:
            generated = self.embedding_backend.embed_documents(missing_texts)
            if len(generated) != len(missing_texts):
                return 0
            for index, vector in zip(missing_indexes, generated):
                vectors[index] = vector
                self.store.cache_embedding(
                    model_id=model_id,
                    builder_version=self.builder.version,
                    content_hash=chunks[index].content_hash,
                    vector=vector,
                )
        completed_vectors = [
            vector for vector in vectors if vector is not None
        ]
        if len(completed_vectors) != len(chunks):
            return 0
        return int(
            self.vector_store.upsert_chunks(
                result_id=document.result_id,
                drawing_id=document.drawing_id,
                chunks=chunks,
                vectors=completed_vectors,
                embedding_model=model_id,
                builder_version=self.builder.version,
            )
        )
