from __future__ import annotations

from electronic_recognition.search.models import SearchChunk
from electronic_recognition.search.qdrant_store import QdrantVectorStore


class _FakeQdrantClient:
    def __init__(self) -> None:
        self.collections: dict[str, dict[str, object]] = {}
        self.points: dict[str, list[dict[str, object]]] = {}

    def collection_exists(self, collection_name: str) -> bool:
        return collection_name in self.collections

    def create_collection(
        self,
        collection_name: str,
        vectors_config: object,
    ) -> None:
        self.collections[collection_name] = {"vectors_config": vectors_config}
        self.points.setdefault(collection_name, [])

    def upsert(
        self,
        collection_name: str,
        points: list[dict[str, object]],
        wait: bool = True,
    ) -> None:
        existing = {item["id"]: item for item in self.points.setdefault(collection_name, [])}
        for point in points:
            existing[point["id"]] = point
        self.points[collection_name] = list(existing.values())

    def delete(
        self,
        collection_name: str,
        points_selector: dict[str, object],
        wait: bool = True,
    ) -> None:
        must = points_selector["filter"]["must"]
        key = must[0]["key"]
        value = must[0]["match"]["value"]
        self.points[collection_name] = [
            item
            for item in self.points.get(collection_name, [])
            if item["payload"].get(key) != value
        ]

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int,
        with_payload: bool,
    ) -> list[object]:
        def score(vector: list[float]) -> float:
            return sum(a * b for a, b in zip(query_vector, vector))

        results = sorted(
            self.points.get(collection_name, []),
            key=lambda item: score(item["vector"]),
            reverse=True,
        )[:limit]
        return [
            type(
                "ScoredPoint",
                (),
                {
                    "id": item["id"],
                    "score": score(item["vector"]),
                    "payload": item["payload"],
                },
            )()
            for item in results
        ]

    def count(self, collection_name: str, exact: bool = True) -> object:
        return type("CountResult", (), {"count": len(self.points.get(collection_name, []))})()


def test_qdrant_store_upsert_search_and_delete() -> None:
    client = _FakeQdrantClient()
    store = QdrantVectorStore(
        collection_name="demo_v2",
        vector_size=2,
        client=client,
    )
    chunks = [
        SearchChunk(
            chunk_id="drawing-1:chunk-a",
            drawing_id="drawing-1",
            chunk_type="drawing",
            text="风阀控制图纸",
            title="风阀控制图纸",
            metadata={"page": 1},
        ),
        SearchChunk(
            chunk_id="drawing-2:chunk-b",
            drawing_id="drawing-2",
            chunk_type="combination",
            text="继电器线圈与辅助触点",
            title="继电器组合",
            page=1,
            metadata={"page": 1, "rule_id": "coil_contact_group"},
        ),
    ]
    vectors = [[0.9, 0.1], [0.1, 0.9]]

    upserted = store.upsert_chunks(
        result_id="result-1",
        drawing_id="drawing-1",
        chunks=chunks,
        vectors=vectors,
        embedding_model="fake-model",
        builder_version="2",
    )
    hits = store.search([0.0, 1.0], limit=2)
    store.delete_result("result-1")

    assert upserted == 2
    assert hits[0].source == "dense"
    assert hits[0].chunk_id == "drawing-2:chunk-b"
    assert hits[0].page == 1
    assert store.count() == 0


def test_qdrant_store_serializes_concurrent_ops() -> None:
    import threading

    client = _FakeQdrantClient()
    store = QdrantVectorStore(
        collection_name="demo_v2",
        vector_size=2,
        client=client,
        lock=threading.RLock(),
    )
    store.upsert_chunks(
        result_id="seed",
        drawing_id="d",
        chunks=[
            SearchChunk(
                chunk_id="seed:c",
                drawing_id="d",
                chunk_type="drawing",
                text="t",
                title="t",
                metadata={},
            )
        ],
        vectors=[[0.5, 0.5]],
        embedding_model="m",
        builder_version="2",
    )

    errors: list[Exception] = []

    def search_worker() -> None:
        try:
            for _ in range(100):
                store.search([0.0, 1.0], limit=2)
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(exc)

    def upsert_worker() -> None:
        try:
            for index in range(100):
                store.upsert_chunks(
                    result_id=f"r{index}",
                    drawing_id="d",
                    chunks=[
                        SearchChunk(
                            chunk_id=f"r{index}:c",
                            drawing_id="d",
                            chunk_type="drawing",
                            text="t",
                            title="t",
                            metadata={},
                        )
                    ],
                    vectors=[[0.5, 0.5]],
                    embedding_model="m",
                    builder_version="2",
                )
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(exc)

    threads = [
        threading.Thread(target=search_worker),
        threading.Thread(target=upsert_worker),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []


def test_qdrant_store_uses_stable_point_ids() -> None:
    store = QdrantVectorStore(
        collection_name="demo_v2",
        vector_size=2,
        client=_FakeQdrantClient(),
    )

    first = store.point_id_for_chunk("drawing-1:chunk-a")
    second = store.point_id_for_chunk("drawing-1:chunk-a")
    third = store.point_id_for_chunk("drawing-1:chunk-b")

    assert first == second
    assert first != third
