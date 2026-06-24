from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SCHEMA_VERSION = 2


@dataclass(slots=True)
class SearchChunk:
    chunk_id: str
    drawing_id: str
    chunk_type: str
    text: str
    page: int | None = None
    region_id: str = ""
    region_type: str = ""
    bounds: list[float] = field(default_factory=list)
    title: str = ""
    content_hash: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExactTerm:
    drawing_id: str
    term_type: str
    raw_value: str
    normalized_value: str
    page: int | None = None
    chunk_id: str = ""


@dataclass(slots=True)
class DrawingDocument:
    drawing_id: str
    result_id: str
    filename: str
    drawing_number: str = ""
    drawing_title: str = ""
    project_name: str = ""
    system_name: str = ""
    contract_number: str = ""
    revision: str = ""
    page_count: int = 1
    source_hash: str = ""
    content_hash: str = ""
    schema_version: int = SCHEMA_VERSION
    component_codes: list[str] = field(default_factory=list)
    component_labels: list[str] = field(default_factory=list)
    component_types: list[str] = field(default_factory=list)
    component_models: list[str] = field(default_factory=list)
    combination_names: list[str] = field(default_factory=list)
    control_signals: list[str] = field(default_factory=list)
    search_text: str = ""
    chunks: list[SearchChunk] = field(default_factory=list)
    exact_terms: list[ExactTerm] = field(default_factory=list)


@dataclass(slots=True)
class QueryTerm:
    type: str
    value: str
    normalized: str


@dataclass(slots=True)
class ParsedQuery:
    raw_query: str
    normalized_query: str
    exact_terms: list[QueryTerm] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    filters: dict[str, Any] = field(default_factory=dict)
    expanded_terms: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SearchHit:
    chunk_id: str
    drawing_id: str
    score: float
    source: str
    rank: int
    page: int | None = None
    snippet: str = ""
    chunk_type: str = ""
    fields: list[str] = field(default_factory=list)
    exact_term_types: list[str] = field(default_factory=list)
    source_ranks: dict[str, int] = field(default_factory=dict)
    source_scores: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class DrawingSearchResult:
    drawing_id: str
    result_id: str
    filename: str
    drawing_number: str
    drawing_title: str
    revision: str
    project_name: str
    system_name: str
    score: float
    matched_pages: list[int] = field(default_factory=list)
    matched_components: list[str] = field(default_factory=list)
    matched_combinations: list[str] = field(default_factory=list)
    matched_chunk_types: list[str] = field(default_factory=list)
    snippet: str = ""
    match_sources: list[str] = field(default_factory=list)
    preview_url: str = ""
    source_hash: str = ""
    collapsed_versions: int = 0
    history_versions: list[dict[str, Any]] = field(default_factory=list)
    debug: dict[str, Any] = field(default_factory=dict)
