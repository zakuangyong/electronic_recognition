from __future__ import annotations

import re

from .models import ParsedQuery, QueryTerm
from .normalizer import SearchNormalizer


class QueryParser:
    def __init__(
        self,
        normalizer: SearchNormalizer | None = None,
        synonyms: dict[str, list[str]] | None = None,
    ) -> None:
        self.normalizer = normalizer or SearchNormalizer()
        self.synonyms = synonyms or {}

    def parse(
        self,
        query: str,
        filters: dict[str, object] | None = None,
    ) -> ParsedQuery:
        normalized = self.normalizer.normalize_text(query)
        exact_terms: list[QueryTerm] = []
        for identifier in self.normalizer.extract_identifiers(normalized):
            exact_terms.append(
                QueryTerm(
                    type="identifier",
                    value=identifier,
                    normalized=self.normalizer.compact_identifier(identifier),
                )
            )
        for code in self.normalizer.extract_component_codes(normalized):
            exact_terms.append(
                QueryTerm(
                    type="component_code",
                    value=code,
                    normalized=self.normalizer.compact_identifier(code),
                )
            )
        revision = _extract_revision(normalized)
        parsed_filters = {
            key: value
            for key, value in (filters or {}).items()
            if not _is_empty_filter_value(value)
        }
        if revision:
            parsed_filters.setdefault("revision", revision)
            exact_terms.append(
                QueryTerm(
                    type="revision",
                    value=revision,
                    normalized=self.normalizer.normalize_text(revision),
                )
            )
        keywords = [
            token
            for token in re.split(r"[\s,;:]+", normalized)
            if token and len(token) > 1
        ]
        expanded_terms = self._expanded_terms(normalized)
        return ParsedQuery(
            raw_query=query,
            normalized_query=normalized,
            exact_terms=_deduplicate_terms(exact_terms),
            keywords=keywords,
            filters=parsed_filters,
            expanded_terms=expanded_terms,
        )

    def _expanded_terms(self, normalized_query: str) -> list[str]:
        expanded: list[str] = []
        for source, aliases in self.synonyms.items():
            normalized_source = self.normalizer.normalize_text(source)
            if normalized_source and normalized_source in normalized_query:
                expanded.extend(
                    self.normalizer.normalize_text(alias)
                    for alias in aliases
                    if str(alias).strip()
                )
        return _unique(expanded)


def _extract_revision(value: str) -> str:
    match = re.search(r"(?:REV|VERSION|版本|版次|版)[\s:：-]*([A-Z0-9]+)", value)
    return match.group(1) if match else ""


def _is_empty_filter_value(value: object) -> bool:
    return value is None or value == "" or value == []


def _deduplicate_terms(terms: list[QueryTerm]) -> list[QueryTerm]:
    seen: set[tuple[str, str]] = set()
    result: list[QueryTerm] = []
    for term in terms:
        key = (term.type, term.normalized)
        if key in seen:
            continue
        seen.add(key)
        result.append(term)
    return result


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
