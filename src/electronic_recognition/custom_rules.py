from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class RuleMember:
    role: str
    min_quantity: int = 1
    code_patterns: list[str] = field(default_factory=list)
    label_keywords: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CustomRule:
    id: str
    name: str
    description: str = ""
    image_path: str = ""
    engine: str = "declarative"
    enabled: bool = True
    scope: str = "same_page"
    confidence: float = 0.95
    members: list[RuleMember] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    notes: str = ""
    source: str = ""


class CustomRuleKnowledgeBase:
    def __init__(
        self,
        rules: list[CustomRule],
        root_dir: str | Path,
    ) -> None:
        self.rules = rules
        self.root_dir = Path(root_dir).resolve()
        self.by_id = {rule.id: rule for rule in rules}

    @classmethod
    def empty(cls, root_dir: str | Path = ".") -> "CustomRuleKnowledgeBase":
        return cls([], root_dir)

    @classmethod
    def load(cls, path: str | Path) -> "CustomRuleKnowledgeBase":
        source = Path(path).resolve()
        payload = json.loads(source.read_text(encoding="utf-8"))
        rules: list[CustomRule] = []
        for item in payload.get("rules", []):
            if not isinstance(item, dict):
                continue
            members = [
                RuleMember(**member)
                for member in item.get("members", [])
                if isinstance(member, dict)
            ]
            rule_values = dict(item)
            rule_values["members"] = members
            rules.append(CustomRule(**rule_values))
        return cls(rules, source.parent)

    def image_path(self, rule: CustomRule) -> Path:
        path = Path(rule.image_path)
        return path if path.is_absolute() else self.root_dir / path


def evaluate_custom_rules(
    rule_base: CustomRuleKnowledgeBase,
    detected_components: list[dict[str, Any]],
    *,
    open_symbols: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    records = [
        item
        for item in (open_symbols or detected_components)
        if isinstance(item, dict)
    ]
    results: list[dict[str, Any]] = []
    for rule in rule_base.rules:
        if (
            not rule.enabled
            or rule.engine != "declarative"
            or not rule.members
        ):
            continue
        if rule.scope == "same_page":
            pages = sorted(
                {
                    page
                    for record in records
                    if (page := _page(record)) is not None
                }
            )
            for page in pages:
                match = _match_rule(
                    rule,
                    [
                        record
                        for record in records
                        if _page(record) == page
                    ],
                )
                if match is not None:
                    match["pages"] = [page]
                    results.append(match)
        else:
            match = _match_rule(rule, records)
            if match is not None:
                match["pages"] = sorted(
                    {
                        page
                        for record in records
                        if (page := _page(record)) is not None
                    }
                )
                results.append(match)
    return results


def _match_rule(
    rule: CustomRule,
    records: list[dict[str, Any]],
) -> dict[str, Any] | None:
    members: list[dict[str, Any]] = []
    all_codes: list[str] = []
    for requirement in rule.members:
        matched = [
            _match_record(requirement, record)
            for record in records
        ]
        matched = [item for item in matched if item is not None]
        quantity = sum(int(item["quantity"]) for item in matched)
        if quantity < max(1, requirement.min_quantity):
            return None
        codes = _unique(
            code
            for item in matched
            for code in item["codes"]
        )
        labels = _unique(
            str(item["label"])
            for item in matched
            if str(item["label"]).strip()
        )
        all_codes.extend(codes)
        members.append(
            {
                "role": requirement.role,
                "codes": codes,
                "quantity": quantity,
                "pages": sorted(
                    {
                        int(page)
                        for item in matched
                        for page in item["pages"]
                    }
                ),
                "labels": labels,
            }
        )
    return {
        "rule_id": rule.id,
        "rule_layer": "custom",
        "name": rule.name,
        "description": rule.description,
        "group_code": ",".join(_unique(all_codes)),
        "confidence": max(0.0, min(1.0, rule.confidence)),
        "physical_quantity": 1,
        "members": members,
        "evidence": [
            (
                f"自定义规则要求的 {len(rule.members)} 个成员条件"
                "均由单元件识别结果满足"
            )
        ],
    }


def _match_record(
    requirement: RuleMember,
    record: dict[str, Any],
) -> dict[str, Any] | None:
    codes = _codes(record.get("code"))
    matched_codes = [
        code
        for code in codes
        if any(
            re.fullmatch(pattern, code, flags=re.IGNORECASE)
            for pattern in requirement.code_patterns
        )
    ]
    text = " ".join(
        str(record.get(key, ""))
        for key in (
            "label",
            "raw_label",
            "component_type",
            "evidence",
        )
    )
    keyword_match = any(
        keyword.casefold() in text.casefold()
        for keyword in requirement.label_keywords
    )
    criteria_configured = bool(
        requirement.code_patterns or requirement.label_keywords
    )
    if not criteria_configured:
        return None
    if not matched_codes and not keyword_match:
        return None
    record_quantity = _quantity(record)
    quantity = (
        len(matched_codes)
        if matched_codes and len(codes) > 1
        else record_quantity
    )
    return {
        "codes": matched_codes or codes,
        "quantity": quantity,
        "pages": [_page(record)] if _page(record) is not None else [],
        "label": str(
            record.get("label")
            or record.get("raw_label")
            or record.get("component_type")
            or ""
        ).strip(),
    }


def _codes(value: object) -> list[str]:
    return _unique(
        item.strip().upper()
        for item in re.split(r"[,，;；、\s]+", str(value or ""))
        if item.strip()
    )


def _quantity(record: dict[str, Any]) -> int:
    try:
        return max(1, int(record.get("occurrence_count", 1)))
    except (TypeError, ValueError):
        return 1


def _page(record: dict[str, Any]) -> int | None:
    try:
        page = int(record.get("page", 0))
    except (TypeError, ValueError):
        return None
    return page if page > 0 else None


def _unique(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value).strip()
        key = normalized.casefold()
        if normalized and key not in seen:
            result.append(normalized)
            seen.add(key)
    return result
