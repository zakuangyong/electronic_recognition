from __future__ import annotations

from .models import SearchHit


def reciprocal_rank_fusion(
    sources: list[list[SearchHit]],
    k: int = 60,
) -> list[SearchHit]:
    by_chunk: dict[str, SearchHit] = {}
    scores: dict[str, float] = {}
    source_names: dict[str, list[str]] = {}
    source_ranks: dict[str, dict[str, int]] = {}
    source_scores: dict[str, dict[str, float]] = {}
    for hits in sources:
        for rank, hit in enumerate(hits, start=1):
            key = hit.chunk_id
            if key not in by_chunk:
                by_chunk[key] = hit
                scores[key] = 0.0
                source_names[key] = []
                source_ranks[key] = {}
                source_scores[key] = {}
            scores[key] += 1.0 / (k + rank)
            if hit.source not in source_names[key]:
                source_names[key].append(hit.source)
            source_ranks[key][hit.source] = rank
            source_scores[key][hit.source] = hit.score
            if not by_chunk[key].snippet and hit.snippet:
                by_chunk[key] = hit
    fused: list[SearchHit] = []
    for key, hit in by_chunk.items():
        fused_hit = SearchHit(
            chunk_id=hit.chunk_id,
            drawing_id=hit.drawing_id,
            score=scores[key],
            source="+".join(source_names[key]),
            rank=hit.rank,
            page=hit.page,
            snippet=hit.snippet,
            chunk_type=hit.chunk_type,
            fields=list(hit.fields),
            exact_term_types=list(hit.exact_term_types),
            source_ranks=source_ranks[key],
            source_scores=source_scores[key],
        )
        fused.append(fused_hit)
    return sorted(fused, key=lambda item: item.score, reverse=True)
