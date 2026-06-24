from __future__ import annotations

import json
import hashlib
import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import DrawingDocument, DrawingSearchResult, SearchHit
from .normalizer import SearchNormalizer


FTS_COLUMNS = {
    "chunk_id",
    "drawing_id",
    "drawing_number",
    "component_codes",
    "title",
    "project_system",
    "combinations",
    "component_text",
    "full_text",
}

TABLE_COLUMN_UPGRADES = {
    "drawings": {
        "contract_number": "TEXT",
        "revision": "TEXT",
        "page_count": "INTEGER NOT NULL DEFAULT 1",
        "source_hash": "TEXT NOT NULL DEFAULT ''",
        "content_hash": "TEXT NOT NULL DEFAULT ''",
        "schema_version": "INTEGER NOT NULL DEFAULT 1",
        "indexed_at": "TEXT NOT NULL DEFAULT ''",
        "updated_at": "TEXT NOT NULL DEFAULT ''",
        "deleted_at": "TEXT",
        "bm25_status": "TEXT NOT NULL DEFAULT 'complete'",
        "vector_status": "TEXT NOT NULL DEFAULT 'pending'",
        "vector_count": "INTEGER NOT NULL DEFAULT 0",
        "embedding_model": "TEXT NOT NULL DEFAULT ''",
        "builder_version": "TEXT NOT NULL DEFAULT ''",
        "vector_indexed_at": "TEXT NOT NULL DEFAULT ''",
        "last_error": "TEXT NOT NULL DEFAULT ''",
    },
    "drawing_payloads": {
        "component_codes_json": "TEXT NOT NULL DEFAULT '[]'",
        "component_labels_json": "TEXT NOT NULL DEFAULT '[]'",
        "component_types_json": "TEXT NOT NULL DEFAULT '[]'",
        "component_models_json": "TEXT NOT NULL DEFAULT '[]'",
        "combination_names_json": "TEXT NOT NULL DEFAULT '[]'",
        "control_signals_json": "TEXT NOT NULL DEFAULT '[]'",
        "search_text": "TEXT NOT NULL DEFAULT ''",
    },
    "search_chunks": {
        "page": "INTEGER",
        "region_id": "TEXT",
        "region_type": "TEXT",
        "bounds_json": "TEXT",
        "title": "TEXT",
        "metadata_json": "TEXT NOT NULL DEFAULT '{}'",
    },
    "exact_terms": {
        "page": "INTEGER",
        "chunk_id": "TEXT NOT NULL DEFAULT ''",
    },
    "index_jobs": {
        "drawing_id": "TEXT",
        "stage": "TEXT NOT NULL DEFAULT ''",
        "attempt": "INTEGER NOT NULL DEFAULT 0",
        "error": "TEXT",
    },
}


class DrawingSearchStore:
    def __init__(
        self,
        db_path: str | Path,
        normalizer: SearchNormalizer | None = None,
        score_weights: dict[str, float] | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.normalizer = normalizer or SearchNormalizer()
        self.score_weights = {
            "drawing_number_exact": 0.25,
            "contract_number_exact": 0.2,
            "component_code_exact": 0.12,
            "component_model_exact": 0.1,
            "drawing_title_phrase": 0.08,
            "project_system_match": 0.05,
            "revision_exact": 0.05,
            **(score_weights or {}),
        }

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS drawings (
                    drawing_id TEXT PRIMARY KEY,
                    result_id TEXT NOT NULL UNIQUE,
                    filename TEXT NOT NULL,
                    drawing_number TEXT,
                    drawing_title TEXT,
                    project_name TEXT,
                    system_name TEXT,
                    contract_number TEXT,
                    revision TEXT,
                    page_count INTEGER NOT NULL DEFAULT 1,
                    source_hash TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    schema_version INTEGER NOT NULL,
                    indexed_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted_at TEXT,
                    bm25_status TEXT NOT NULL DEFAULT 'complete',
                    vector_status TEXT NOT NULL DEFAULT 'pending',
                    vector_count INTEGER NOT NULL DEFAULT 0,
                    embedding_model TEXT NOT NULL DEFAULT '',
                    builder_version TEXT NOT NULL DEFAULT '',
                    vector_indexed_at TEXT NOT NULL DEFAULT '',
                    last_error TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS drawing_payloads (
                    drawing_id TEXT PRIMARY KEY,
                    component_codes_json TEXT NOT NULL,
                    component_labels_json TEXT NOT NULL,
                    component_types_json TEXT NOT NULL,
                    component_models_json TEXT NOT NULL,
                    combination_names_json TEXT NOT NULL,
                    control_signals_json TEXT NOT NULL,
                    search_text TEXT NOT NULL,
                    FOREIGN KEY (drawing_id) REFERENCES drawings(drawing_id)
                );

                CREATE TABLE IF NOT EXISTS search_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    drawing_id TEXT NOT NULL,
                    chunk_type TEXT NOT NULL,
                    page INTEGER,
                    region_id TEXT,
                    region_type TEXT,
                    bounds_json TEXT,
                    title TEXT,
                    text TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY (drawing_id) REFERENCES drawings(drawing_id)
                );

                CREATE TABLE IF NOT EXISTS exact_terms (
                    drawing_id TEXT NOT NULL,
                    term_type TEXT NOT NULL,
                    raw_value TEXT NOT NULL,
                    normalized_value TEXT NOT NULL,
                    page INTEGER,
                    chunk_id TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (
                        drawing_id,
                        term_type,
                        normalized_value,
                        page,
                        chunk_id
                    ),
                    FOREIGN KEY (drawing_id) REFERENCES drawings(drawing_id)
                );

                CREATE INDEX IF NOT EXISTS idx_exact_terms_lookup
                ON exact_terms(term_type, normalized_value);

                CREATE TABLE IF NOT EXISTS index_jobs (
                    job_id TEXT PRIMARY KEY,
                    result_id TEXT NOT NULL,
                    drawing_id TEXT,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    attempt INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS embedding_cache (
                    cache_key TEXT PRIMARY KEY,
                    model_id TEXT NOT NULL,
                    builder_version TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    dimension INTEGER NOT NULL,
                    vector_blob BLOB NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            self._ensure_columns(connection)
            self._ensure_fts(connection)

    def upsert_document(self, document: DrawingDocument) -> None:
        now = datetime.now().astimezone().isoformat()
        self.initialize()
        with self._connect() as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN")
            existing = connection.execute(
                "SELECT drawing_id FROM drawings WHERE result_id = ?",
                (document.result_id,),
            ).fetchone()
            if existing and str(existing["drawing_id"]) != document.drawing_id:
                self._delete_drawing(connection, str(existing["drawing_id"]))
            self._delete_drawing(connection, document.drawing_id)
            connection.execute(
                """
                INSERT INTO drawings (
                    drawing_id, result_id, filename, drawing_number,
                    drawing_title, project_name, system_name,
                    contract_number, revision, page_count, source_hash,
                    content_hash, schema_version, indexed_at, updated_at,
                    deleted_at, bm25_status, vector_status,
                    vector_count, embedding_model, builder_version,
                    vector_indexed_at, last_error
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL,
                    'complete', 'pending', 0, '', ?, '', ''
                )
                """,
                (
                    document.drawing_id,
                    document.result_id,
                    document.filename,
                    document.drawing_number,
                    document.drawing_title,
                    document.project_name,
                    document.system_name,
                    document.contract_number,
                    document.revision,
                    document.page_count,
                    document.source_hash,
                    document.content_hash,
                    document.schema_version,
                    now,
                    now,
                    str(document.schema_version),
                ),
            )
            connection.execute(
                """
                INSERT INTO drawing_payloads (
                    drawing_id, component_codes_json,
                    component_labels_json, component_types_json,
                    component_models_json, combination_names_json,
                    control_signals_json, search_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document.drawing_id,
                    json.dumps(document.component_codes, ensure_ascii=False),
                    json.dumps(document.component_labels, ensure_ascii=False),
                    json.dumps(document.component_types, ensure_ascii=False),
                    json.dumps(document.component_models, ensure_ascii=False),
                    json.dumps(document.combination_names, ensure_ascii=False),
                    json.dumps(document.control_signals, ensure_ascii=False),
                    document.search_text,
                ),
            )
            for chunk in document.chunks:
                connection.execute(
                    """
                    INSERT INTO search_chunks (
                        chunk_id, drawing_id, chunk_type, page,
                        region_id, region_type, bounds_json, title,
                        text, content_hash, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk.chunk_id,
                        chunk.drawing_id,
                        chunk.chunk_type,
                        chunk.page,
                        chunk.region_id,
                        chunk.region_type,
                        json.dumps(chunk.bounds, ensure_ascii=False),
                        chunk.title,
                        chunk.text,
                        chunk.content_hash,
                        json.dumps(chunk.metadata, ensure_ascii=False),
                    ),
                )
                self._insert_fts_row(connection, document, chunk)
            for term in document.exact_terms:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO exact_terms (
                        drawing_id, term_type, raw_value,
                        normalized_value, page, chunk_id
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        term.drawing_id,
                        term.term_type,
                        term.raw_value,
                        term.normalized_value,
                        term.page,
                        term.chunk_id,
                    ),
                )
            connection.commit()

    def delete_result(self, result_id: str) -> bool:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT drawing_id FROM drawings WHERE result_id = ?",
                (result_id,),
            ).fetchone()
            if row is None:
                return False
            self._delete_drawing(connection, str(row["drawing_id"]))
            connection.commit()
            return True

    def exact_search(
        self,
        terms: list[object],
        limit: int = 100,
    ) -> list[SearchHit]:
        if not terms:
            return []
        self.initialize()
        hits: list[SearchHit] = []
        with self._connect() as connection:
            rank = 1
            seen: set[tuple[str, str]] = set()
            for term in terms:
                term_type = str(getattr(term, "type", ""))
                normalized = str(getattr(term, "normalized", ""))
                if term_type == "identifier":
                    rows = connection.execute(
                        """
                        SELECT e.*, c.chunk_type, c.text, c.title
                        FROM exact_terms e
                        LEFT JOIN search_chunks c ON c.chunk_id = e.chunk_id
                        JOIN drawings d ON d.drawing_id = e.drawing_id
                        WHERE d.deleted_at IS NULL
                          AND e.normalized_value = ?
                        LIMIT ?
                        """,
                        (normalized, limit),
                    ).fetchall()
                else:
                    rows = connection.execute(
                        """
                        SELECT e.*, c.chunk_type, c.text, c.title
                        FROM exact_terms e
                        LEFT JOIN search_chunks c ON c.chunk_id = e.chunk_id
                        JOIN drawings d ON d.drawing_id = e.drawing_id
                        WHERE d.deleted_at IS NULL
                          AND e.term_type = ?
                          AND e.normalized_value = ?
                        LIMIT ?
                        """,
                        (term_type, normalized, limit),
                    ).fetchall()
                for row in rows:
                    chunk_id = str(row["chunk_id"] or f"{row['drawing_id']}:drawing")
                    key = (str(row["drawing_id"]), chunk_id)
                    if key in seen:
                        continue
                    seen.add(key)
                    hits.append(
                        SearchHit(
                            chunk_id=chunk_id,
                            drawing_id=str(row["drawing_id"]),
                            score=1.0 / rank,
                            source="exact",
                            rank=rank,
                            page=row["page"],
                            snippet=_snippet(
                                str(row["text"] or row["raw_value"])
                            ),
                            chunk_type=str(row["chunk_type"] or ""),
                            fields=[str(row["term_type"])],
                            exact_term_types=[str(row["term_type"])],
                            source_ranks={"exact": rank},
                            source_scores={"exact": 1.0 / rank},
                        )
                    )
                    rank += 1
        return hits

    def bm25_search(
        self,
        query: str,
        limit: int,
    ) -> list[SearchHit]:
        self.initialize()
        fts_query = _fts_query(query)
        if not fts_query:
            return []
        with self._connect() as connection:
            try:
                rows = connection.execute(
                    """
                    SELECT
                        f.chunk_id,
                        f.drawing_id,
                        c.page,
                        c.chunk_type,
                        c.text,
                        bm25(drawing_fts) AS score
                    FROM drawing_fts f
                    JOIN search_chunks c ON c.chunk_id = f.chunk_id
                    JOIN drawings d ON d.drawing_id = f.drawing_id
                    WHERE drawing_fts MATCH ?
                      AND d.deleted_at IS NULL
                    ORDER BY score
                    LIMIT ?
                    """,
                    (fts_query, limit),
                ).fetchall()
            except sqlite3.OperationalError:
                try:
                    rows = connection.execute(
                        """
                        SELECT
                            f.chunk_id,
                            f.drawing_id,
                            c.page,
                            c.chunk_type,
                            c.text,
                            bm25(drawing_fts) AS score
                        FROM drawing_fts f
                        JOIN search_chunks c ON c.chunk_id = f.chunk_id
                        JOIN drawings d ON d.drawing_id = f.drawing_id
                        WHERE drawing_fts MATCH ?
                          AND d.deleted_at IS NULL
                        ORDER BY score
                        LIMIT ?
                        """,
                        (_quote_fts_query(query), limit),
                    ).fetchall()
                except sqlite3.OperationalError:
                    return []
        hits: list[SearchHit] = []
        for rank, row in enumerate(rows, start=1):
            score = float(row["score"] or 0.0)
            hits.append(
                SearchHit(
                    chunk_id=str(row["chunk_id"]),
                    drawing_id=str(row["drawing_id"]),
                    score=1.0 / (rank + max(0.0, score)),
                    source="bm25",
                    rank=rank,
                    page=row["page"],
                    snippet=_snippet(str(row["text"] or "")),
                    chunk_type=str(row["chunk_type"] or ""),
                    source_ranks={"bm25": rank},
                    source_scores={"bm25": 1.0 / (rank + max(0.0, score))},
                )
            )
        return hits

    def aggregate_drawings(
        self,
        hits: list[SearchHit],
        limit: int,
        offset: int = 0,
        debug: bool = False,
        deduplicate: bool = True,
        filters: dict[str, object] | None = None,
    ) -> list[DrawingSearchResult]:
        if not hits:
            return []
        by_drawing: dict[str, list[SearchHit]] = {}
        for hit in hits:
            by_drawing.setdefault(hit.drawing_id, []).append(hit)
        with self._connect() as connection:
            ranked_results: list[tuple[DrawingSearchResult, str, int]] = []
            for drawing_id, drawing_hits in by_drawing.items():
                row = connection.execute(
                    """
                    SELECT d.rowid AS storage_order,
                           d.*, p.component_codes_json,
                           p.combination_names_json
                    FROM drawings d
                    LEFT JOIN drawing_payloads p
                      ON p.drawing_id = d.drawing_id
                    WHERE d.drawing_id = ? AND d.deleted_at IS NULL
                    """,
                    (drawing_id,),
                ).fetchone()
                if row is None:
                    continue
                if not self._matches_filters(row, filters or {}):
                    continue
                ordered_hits = sorted(
                    drawing_hits,
                    key=lambda item: item.score,
                    reverse=True,
                )
                score = _aggregate_score(ordered_hits, self.score_weights)
                matched_pages = sorted(
                    {
                        int(hit.page)
                        for hit in ordered_hits
                        if hit.page is not None
                    }
                )
                sources = _unique(
                    source
                    for hit in ordered_hits
                    for source in str(hit.source).split("+")
                    if source
                )
                chunk_types = _unique(
                    hit.chunk_type for hit in ordered_hits if hit.chunk_type
                )
                components = _json_list(row["component_codes_json"])
                combinations = _json_list(row["combination_names_json"])
                best = ordered_hits[0]
                ranked_results.append(
                    (
                        DrawingSearchResult(
                            drawing_id=drawing_id,
                            result_id=str(row["result_id"]),
                            filename=str(row["filename"]),
                            drawing_number=str(row["drawing_number"] or ""),
                            drawing_title=str(row["drawing_title"] or ""),
                            revision=str(row["revision"] or ""),
                            project_name=str(row["project_name"] or ""),
                            system_name=str(row["system_name"] or ""),
                            score=round(score, 6),
                            matched_pages=matched_pages,
                            matched_components=components[:10],
                            matched_combinations=combinations[:8],
                            matched_chunk_types=chunk_types,
                            snippet=best.snippet,
                            match_sources=sources,
                            preview_url=(
                                f"/?result_id={row['result_id']}"
                                if not matched_pages
                                else (
                                    f"/?result_id={row['result_id']}"
                                    f"#page-{matched_pages[0]}"
                                )
                            ),
                            source_hash=str(row["source_hash"] or ""),
                            debug={
                                "hits": [asdict(hit) for hit in ordered_hits[:5]]
                            }
                            if debug
                            else {},
                        ),
                        str(row["updated_at"] or row["indexed_at"] or ""),
                        int(row["storage_order"] or 0),
                    )
                )
        if deduplicate:
            results = self._order_history_results(ranked_results)
        else:
            ordered = sorted(
                ranked_results,
                key=lambda item: (
                    item[0].score,
                    item[1],
                    item[2],
                ),
                reverse=True,
            )
            results = [item for item, _updated_at, _storage_order in ordered]
        if deduplicate and not debug:
            results = self._collapse_history_versions(results)
        return results[offset : offset + limit]

    def _matches_filters(
        self,
        row: sqlite3.Row,
        filters: dict[str, object],
    ) -> bool:
        for key, raw_value in filters.items():
            values = (
                [str(item) for item in raw_value]
                if isinstance(raw_value, list)
                else [str(raw_value)]
            )
            values = [item.strip() for item in values if item.strip()]
            if not values:
                continue
            if key in {
                "drawing_number",
                "contract_number",
                "revision",
                "filename",
            }:
                actual = self.normalizer.compact_identifier(row[key] or "")
                if not any(
                    self.normalizer.compact_identifier(value) == actual
                    for value in values
                ):
                    return False
                continue
            if key in {
                "project_name",
                "system_name",
                "drawing_title",
            }:
                actual = self.normalizer.normalize_text(row[key] or "")
                if not any(
                    self.normalizer.normalize_text(value) in actual
                    for value in values
                ):
                    return False
        return True

    def status(self) -> dict[str, object]:
        self.initialize()
        with self._connect() as connection:
            drawing_count = connection.execute(
                "SELECT COUNT(*) FROM drawings WHERE deleted_at IS NULL"
            ).fetchone()[0]
            chunk_count = connection.execute(
                "SELECT COUNT(*) FROM search_chunks"
            ).fetchone()[0]
            failed_jobs = connection.execute(
                "SELECT COUNT(*) FROM index_jobs WHERE status = 'failed'"
            ).fetchone()[0]
            vector_count = connection.execute(
                "SELECT COALESCE(SUM(vector_count), 0) FROM drawings"
            ).fetchone()[0]
            vector_failed = connection.execute(
                """
                SELECT COUNT(*) FROM drawings
                WHERE vector_status = 'vector_failed'
                """
            ).fetchone()[0]
        return {
            "sqlite_available": True,
            "fts5_available": True,
            "indexed_drawings": drawing_count,
            "indexed_chunks": chunk_count,
            "failed_jobs": failed_jobs,
            "indexed_vectors": vector_count,
            "vector_failed_drawings": vector_failed,
            "database": str(self.db_path),
        }

    def _collapse_history_versions(
        self,
        results: list[DrawingSearchResult],
    ) -> list[DrawingSearchResult]:
        groups: dict[str, list[DrawingSearchResult]] = {}
        for item in results:
            groups.setdefault(self._history_group_key(item), []).append(item)
        collapsed: list[DrawingSearchResult] = []
        for group_items in groups.values():
            primary = group_items[0]
            if len(group_items) > 1:
                primary.history_versions = [
                    {"result_id": item.result_id}
                    for item in group_items[1:]
                ]
                primary.collapsed_versions = len(group_items) - 1
            collapsed.append(primary)
        return collapsed

    def _order_history_results(
        self,
        ranked_results: list[tuple[DrawingSearchResult, str, int]],
    ) -> list[DrawingSearchResult]:
        groups: dict[str, list[tuple[DrawingSearchResult, str, int]]] = {}
        for item in ranked_results:
            groups.setdefault(self._history_group_key(item[0]), []).append(item)
        ordered_groups = sorted(
            groups.values(),
            key=lambda group: (
                max(item[0].score for item in group),
                max(item[1] for item in group),
                max(item[2] for item in group),
            ),
            reverse=True,
        )
        ordered_results: list[DrawingSearchResult] = []
        for group in ordered_groups:
            ordered_group = sorted(
                group,
                key=lambda item: (item[1], item[2], item[0].result_id),
                reverse=True,
            )
            ordered_results.extend(
                item for item, _updated_at, _storage_order in ordered_group
            )
        return ordered_results

    def _history_group_key(self, item: DrawingSearchResult) -> str:
        if item.source_hash:
            return f"source_hash:{item.source_hash}"
        drawing_number = self.normalizer.normalize_text(item.drawing_number)
        filename = self.normalizer.normalize_text(item.filename)
        return f"fallback:{drawing_number}|{filename}"

    def result_status(self, result_id: str) -> dict[str, object]:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT drawing_id, result_id, filename, updated_at,
                       content_hash, deleted_at, bm25_status,
                       vector_status, vector_count, embedding_model,
                       builder_version, vector_indexed_at, last_error
                FROM drawings
                WHERE result_id = ?
                """,
                (result_id,),
            ).fetchone()
        if row is None:
            return {"result_id": result_id, "status": "missing"}
        return {
            "result_id": result_id,
            "drawing_id": row["drawing_id"],
            "filename": row["filename"],
            "status": "deleted" if row["deleted_at"] else "complete",
            "updated_at": row["updated_at"],
            "content_hash": row["content_hash"],
            "bm25_status": row["bm25_status"],
            "vector_status": row["vector_status"],
            "vector_count": row["vector_count"],
            "embedding_model": row["embedding_model"],
            "builder_version": row["builder_version"],
            "vector_indexed_at": row["vector_indexed_at"],
            "last_error": row["last_error"],
        }

    def update_vector_status(
        self,
        result_id: str,
        *,
        status: str,
        vector_count: int = 0,
        embedding_model: str = "",
        builder_version: str = "",
        error: str = "",
    ) -> None:
        self.initialize()
        now = datetime.now().astimezone().isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE drawings
                SET vector_status = ?, vector_count = ?,
                    embedding_model = ?, builder_version = ?,
                    vector_indexed_at = ?, last_error = ?,
                    updated_at = ?
                WHERE result_id = ?
                """,
                (
                    status,
                    max(0, int(vector_count)),
                    embedding_model,
                    builder_version,
                    now if status == "complete" else "",
                    error,
                    now,
                    result_id,
                ),
            )
            connection.commit()

    def get_cached_embedding(
        self,
        *,
        model_id: str,
        builder_version: str,
        content_hash: str,
    ) -> list[float] | None:
        self.initialize()
        cache_key = _embedding_cache_key(
            model_id,
            builder_version,
            content_hash,
        )
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT vector_blob FROM embedding_cache
                WHERE cache_key = ?
                """,
                (cache_key,),
            ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(bytes(row["vector_blob"]).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
            return None
        return (
            [float(value) for value in payload]
            if isinstance(payload, list)
            else None
        )

    def cache_embedding(
        self,
        *,
        model_id: str,
        builder_version: str,
        content_hash: str,
        vector: list[float],
    ) -> None:
        self.initialize()
        cache_key = _embedding_cache_key(
            model_id,
            builder_version,
            content_hash,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO embedding_cache (
                    cache_key, model_id, builder_version,
                    content_hash, dimension, vector_blob, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cache_key,
                    model_id,
                    builder_version,
                    content_hash,
                    len(vector),
                    json.dumps(vector).encode("utf-8"),
                    datetime.now().astimezone().isoformat(),
                ),
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_columns(self, connection: sqlite3.Connection) -> None:
        for table, columns in TABLE_COLUMN_UPGRADES.items():
            existing = self._table_columns(connection, table)
            if not existing:
                continue
            for name, column_type in columns.items():
                if name in existing:
                    continue
                connection.execute(
                    f"ALTER TABLE {table} ADD COLUMN {name} {column_type}"
                )

    def _table_columns(
        self,
        connection: sqlite3.Connection,
        table: str,
    ) -> set[str]:
        rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
        return {str(row["name"]) for row in rows}

    def _ensure_fts(self, connection: sqlite3.Connection) -> None:
        row = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name = 'drawing_fts'
            """
        ).fetchone()
        rebuild = False
        if row is not None and FTS_COLUMNS.issubset(
            self._table_columns(connection, "drawing_fts")
        ):
            return
        if row is not None:
            connection.execute("DROP TABLE drawing_fts")
            rebuild = True
        try:
            connection.execute(
                """
                CREATE VIRTUAL TABLE drawing_fts USING fts5(
                    chunk_id UNINDEXED,
                    drawing_id UNINDEXED,
                    drawing_number,
                    component_codes,
                    title,
                    project_system,
                    combinations,
                    component_text,
                    full_text,
                    tokenize='trigram'
                )
                """
            )
        except sqlite3.OperationalError:
            connection.execute(
                """
                CREATE VIRTUAL TABLE drawing_fts USING fts5(
                    chunk_id UNINDEXED,
                    drawing_id UNINDEXED,
                    drawing_number,
                    component_codes,
                    title,
                    project_system,
                    combinations,
                    component_text,
                    full_text,
                    tokenize='unicode61'
                )
                """
            )
        if rebuild:
            self._populate_fts_from_chunks(connection)

    def _populate_fts_from_chunks(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            """
            SELECT
                c.chunk_id,
                c.drawing_id,
                c.title,
                c.text,
                d.drawing_number,
                d.drawing_title,
                d.project_name,
                d.system_name,
                p.component_codes_json,
                p.component_labels_json,
                p.component_types_json,
                p.component_models_json,
                p.combination_names_json
            FROM search_chunks c
            JOIN drawings d ON d.drawing_id = c.drawing_id
            LEFT JOIN drawing_payloads p ON p.drawing_id = c.drawing_id
            WHERE d.deleted_at IS NULL
            """
        ).fetchall()
        for row in rows:
            component_text = " ".join(
                [
                    *_json_list(row["component_labels_json"]),
                    *_json_list(row["component_types_json"]),
                    *_json_list(row["component_models_json"]),
                ]
            )
            connection.execute(
                """
                INSERT INTO drawing_fts (
                    chunk_id, drawing_id, drawing_number, component_codes,
                    title, project_system, combinations, component_text,
                    full_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["chunk_id"],
                    row["drawing_id"],
                    row["drawing_number"] or "",
                    " ".join(_json_list(row["component_codes_json"])),
                    row["title"] or row["drawing_title"] or "",
                    " ".join(
                        item
                        for item in (row["project_name"], row["system_name"])
                        if item
                    ),
                    " ".join(_json_list(row["combination_names_json"])),
                    component_text,
                    row["text"] or "",
                ),
            )

    def _delete_drawing(
        self,
        connection: sqlite3.Connection,
        drawing_id: str,
    ) -> None:
        connection.execute(
            "DELETE FROM drawing_fts WHERE drawing_id = ?",
            (drawing_id,),
        )
        connection.execute(
            "DELETE FROM exact_terms WHERE drawing_id = ?",
            (drawing_id,),
        )
        connection.execute(
            "DELETE FROM search_chunks WHERE drawing_id = ?",
            (drawing_id,),
        )
        connection.execute(
            "DELETE FROM drawing_payloads WHERE drawing_id = ?",
            (drawing_id,),
        )
        connection.execute(
            "DELETE FROM drawings WHERE drawing_id = ?",
            (drawing_id,),
        )

    def _insert_fts_row(
        self,
        connection: sqlite3.Connection,
        document: DrawingDocument,
        chunk: object,
    ) -> None:
        connection.execute(
            """
            INSERT INTO drawing_fts (
                chunk_id, drawing_id, drawing_number, component_codes,
                title, project_system, combinations, component_text,
                full_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chunk.chunk_id,
                document.drawing_id,
                document.drawing_number,
                " ".join(document.component_codes),
                chunk.title or document.drawing_title,
                " ".join(
                    item
                    for item in (document.project_name, document.system_name)
                    if item
                ),
                " ".join(document.combination_names),
                " ".join(
                    [
                        *document.component_labels,
                        *document.component_types,
                        *document.component_models,
                    ]
                ),
                chunk.text,
            ),
        )


def _fts_query(query: str) -> str:
    tokens = [
        token.replace('"', "")
        for token in str(query or "").split()
        if token.strip()
    ]
    return " OR ".join(f'"{token}"' for token in tokens[:12])


def _quote_fts_query(query: str) -> str:
    return '"' + str(query or "").replace('"', " ").strip() + '"'


def _snippet(text: str, limit: int = 220) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _aggregate_score(
    hits: list[SearchHit],
    weights: dict[str, float],
) -> float:
    ordered = sorted(hits, key=lambda item: item.score, reverse=True)
    score = ordered[0].score
    if len(ordered) > 1:
        score += 0.35 * ordered[1].score
    if len(ordered) > 2:
        score += 0.15 * ordered[2].score
    exact_types = {
        term_type
        for hit in ordered
        for term_type in hit.exact_term_types
    }
    for term_type in exact_types:
        score += float(weights.get(f"{term_type}_exact", 0.0))
    return score


def _json_list(value: object) -> list[str]:
    try:
        loaded = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    return [str(item) for item in loaded] if isinstance(loaded, list) else []


def _unique(values: object) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value)
        if text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _embedding_cache_key(
    model_id: str,
    builder_version: str,
    content_hash: str,
) -> str:
    payload = f"{model_id}\n{builder_version}\n{content_hash}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
