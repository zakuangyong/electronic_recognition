from __future__ import annotations

import re
import unicodedata


DEVICE_CODE_RE = re.compile(
    r"\b[A-Z]{1,4}[-_\s]*[0-9]{0,4}(?:/[A-Z0-9]+)?\b",
    re.IGNORECASE,
)
IDENTIFIER_RE = re.compile(
    r"\b[A-Z][A-Z0-9]{1,12}[-_][A-Z0-9][A-Z0-9_-]{1,18}\b",
    re.IGNORECASE,
)
GENERIC_IDENTIFIER_RE = re.compile(
    r"\b(?=[A-Z0-9_.\-/]*[A-Z])(?=[A-Z0-9_.\-/]*\d)"
    r"[A-Z0-9][A-Z0-9_.\-/]{1,30}\b",
    re.IGNORECASE,
)


class SearchNormalizer:
    version = "1"

    def normalize_text(self, value: object) -> str:
        text = unicodedata.normalize("NFKC", str(value or ""))
        text = text.replace("，", ",").replace("；", ";").replace("：", ":")
        text = text.replace("（", "(").replace("）", ")")
        text = text.replace("—", "-").replace("–", "-")
        text = re.sub(r"\s+", " ", text).strip()
        return text.upper()

    def compact_identifier(self, value: object) -> str:
        text = self.normalize_text(value)
        return re.sub(r"[\s_\-./:;]+", "", text)

    def aliases_for_identifier(self, value: object) -> list[str]:
        normalized = self.normalize_text(value)
        compact = self.compact_identifier(normalized)
        aliases = [normalized, compact]
        if "_" in normalized:
            aliases.append(normalized.replace("_", "-"))
        if "-" in normalized:
            aliases.append(normalized.replace("-", "_"))
        aliases.append(re.sub(r"[\s_\-]+", "", normalized))
        return _unique(item for item in aliases if item)

    def aliases_for_component_code(self, value: object) -> list[str]:
        normalized = self.normalize_text(value)
        compact = self.compact_identifier(normalized)
        aliases = [normalized, compact]
        match = re.match(r"^([A-Z]+)([0-9]+)(/[A-Z0-9]+)?$", compact)
        if match:
            prefix, number, suffix = match.groups()
            suffix = suffix or ""
            aliases.extend(
                [
                    f"{prefix}-{number}{suffix}",
                    f"{prefix} {number}{suffix}",
                    f"{prefix}_{number}{suffix}",
                ]
            )
        return _unique(item for item in aliases if item)

    def extract_component_codes(self, value: object) -> list[str]:
        text = self.normalize_text(value)
        codes: list[str] = []
        for match in DEVICE_CODE_RE.finditer(text):
            token = match.group(0).strip(" ,;:()")
            compact = self.compact_identifier(token)
            if len(compact) < 2:
                continue
            if re.fullmatch(r"[A-Z]+", compact) and len(compact) > 3:
                continue
            if re.search(r"\d", compact) or compact in {
                "KA",
                "KM",
                "FU",
                "FR",
                "QF",
                "SB",
                "HL",
                "PLC",
            }:
                codes.append(token)
        return _unique(codes)

    def extract_identifiers(self, value: object) -> list[str]:
        text = self.normalize_text(value)
        return _unique(
            [
                *(
                    match.group(0).strip(" ,;:()")
                    for match in IDENTIFIER_RE.finditer(text)
                ),
                *(
                    match.group(0).strip(" ,;:()")
                    for match in GENERIC_IDENTIFIER_RE.finditer(text)
                ),
            ]
        )


def _unique(values: object) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []
    for value in values:
        text = str(value).strip()
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        results.append(text)
    return results
