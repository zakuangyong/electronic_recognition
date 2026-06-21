from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


def detect_combinations(
    detected_components: list[dict[str, Any]],
    *,
    open_symbols: list[dict[str, Any]] | None = None,
    component_table: dict[str, Any] | None = None,
    title_block: dict[str, Any] | None = None,
    control_signal_configuration: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Apply deterministic electrical combination rules."""
    symbols = [
        item for item in (open_symbols or []) if isinstance(item, dict)
    ]
    components = [
        item for item in detected_components if isinstance(item, dict)
    ]
    table_rows = _table_rows(component_table)
    context = _context_text(
        components,
        symbols,
        table_rows,
        title_block,
        control_signal_configuration,
    )

    combinations: list[dict[str, Any]] = []
    combinations.extend(_coil_contact_combinations(symbols or components))

    motor = _motor_start_combination(
        components,
        symbols,
        table_rows,
        context,
    )
    if motor is not None:
        combinations.append(motor)

    start_stop = _start_stop_combination(
        components,
        symbols,
        table_rows,
        context,
    )
    if start_stop is not None:
        combinations.append(start_stop)

    return sorted(
        combinations,
        key=lambda item: (
            str(item.get("rule_id", "")),
            str(item.get("group_code", "")),
        ),
    )


def _coil_contact_combinations(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: {"coil": [], "contact": []}
    )
    for record in records:
        text = _record_text(record)
        role = ""
        if "线圈" in text or "coil" in text.casefold():
            role = "coil"
        elif "触点" in text or "contact" in text.casefold():
            role = "contact"
        if not role:
            continue
        for code in _codes(record.get("code")):
            if _is_device_code(code):
                grouped[code][role].append(record)

    results: list[dict[str, Any]] = []
    for code, roles in grouped.items():
        if not roles["coil"] or not roles["contact"]:
            continue
        is_contactor = code.startswith("KM") or any(
            "接触器线圈" in _record_text(item)
            for item in roles["coil"]
        )
        pages = _pages(roles["coil"] + roles["contact"])
        results.append(
            {
                "rule_id": "coil_contact_group",
                "name": (
                    "接触器线圈与辅助触点组合"
                    if is_contactor
                    else "继电器线圈与辅助触点组合"
                ),
                "group_code": code,
                "confidence": 0.98,
                "physical_quantity": 1,
                "pages": pages,
                "members": [
                    _member(
                        "线圈",
                        [code],
                        roles["coil"],
                        quantity=len(roles["coil"]),
                    ),
                    _member(
                        "辅助触点",
                        [code],
                        roles["contact"],
                        quantity=sum(
                            _record_quantity(item)
                            for item in roles["contact"]
                        ),
                    ),
                ],
                "evidence": [
                    f"线圈与触点使用相同基础代号 {code}",
                    (
                        f"识别到 {len(roles['coil'])} 条线圈记录、"
                        f"{sum(_record_quantity(item) for item in roles['contact'])}"
                        " 个触点实例"
                    ),
                ],
            }
        )
    return results


def _motor_start_combination(
    components: list[dict[str, Any]],
    symbols: list[dict[str, Any]],
    table_rows: list[dict[str, Any]],
    context: str,
) -> dict[str, Any] | None:
    records = components + symbols
    breaker = _matching_codes(records, table_rows, ("QF",), ("断路器",))
    contactor = _matching_codes(
        records,
        table_rows,
        ("KM",),
        ("接触器",),
    )
    overload = _matching_codes(
        records,
        table_rows,
        ("FR", "F"),
        ("热继电器", "过载保护"),
    )
    load = _matching_codes(
        records,
        table_rows,
        ("M", "P"),
        ("电动机", "风机", "水泵"),
    )
    load_context = any(
        word in context for word in ("电动机", "电机", "风机", "水泵")
    )
    if not breaker or not contactor or not overload:
        return None
    if not load and not load_context:
        return None

    members = [
        _role_member("短路保护", breaker, records, table_rows),
        _role_member("接触器控制", contactor, records, table_rows),
        _role_member("过载保护", overload, records, table_rows),
    ]
    if load:
        members.append(
            _role_member("电动机或风机负载", load, records, table_rows)
        )
    else:
        members.append(
            {
                "role": "电动机或风机负载",
                "codes": [],
                "quantity": 1,
                "pages": [],
                "labels": ["由图纸名称或控制信号推断的风机/电机负载"],
            }
        )
    pages = sorted(
        {
            page
            for member in members
            for page in member.get("pages", [])
        }
    )
    return {
        "rule_id": "motor_start_protection",
        "name": "电动机启动与保护组合",
        "group_code": ",".join(
            _unique(breaker + contactor + overload + load)
        ),
        "confidence": 0.96 if load else 0.88,
        "physical_quantity": 1,
        "pages": pages,
        "members": members,
        "evidence": [
            "同时识别到断路器、接触器和热继电器/过载保护",
            (
                "识别到电动机/风机负载代号"
                if load
                else "图纸标题或控制信号包含风机/电机负载语义"
            ),
        ],
    }


def _start_stop_combination(
    components: list[dict[str, Any]],
    symbols: list[dict[str, Any]],
    table_rows: list[dict[str, Any]],
    context: str,
) -> dict[str, Any] | None:
    records = components + symbols
    start = _table_role_codes(
        table_rows,
        ("启动", "开机"),
        command_only=True,
    )
    stop = _table_role_codes(
        table_rows,
        ("停止", "停机"),
        command_only=True,
    )
    indicators = _matching_codes(
        records,
        table_rows,
        ("HL", "G", "R", "Y"),
        ("指示灯",),
    )
    relays = _relay_codes(records, table_rows)
    if not start or not stop or not indicators or not relays:
        return None
    if not any(
        word in context
        for word in ("启动", "停止", "启停", "开机", "停机")
    ):
        return None

    members = [
        _role_member("启动命令", start, records, table_rows),
        _role_member("停止命令", stop, records, table_rows),
        _role_member("继电控制", relays, records, table_rows),
        _role_member("状态反馈", indicators, records, table_rows),
    ]
    pages = sorted(
        {
            page
            for member in members
            for page in member.get("pages", [])
        }
    )
    return {
        "rule_id": "start_stop_indicator",
        "name": "启停控制及状态指示组合",
        "group_code": ",".join(
            _unique(start + stop + relays + indicators)
        ),
        "confidence": 0.94,
        "physical_quantity": 1,
        "pages": pages,
        "members": members,
        "evidence": [
            "图纸标签中同时存在明确的启动和停止命令",
            "同一图纸中存在继电控制元件及运行/故障状态指示灯",
        ],
    }


def _role_member(
    role: str,
    codes: list[str],
    records: list[dict[str, Any]],
    table_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    code_set = set(codes)
    matched_records = [
        item
        for item in records
        if code_set.intersection(_codes(item.get("code")))
    ]
    labels = [
        str(item.get("label") or item.get("raw_label") or "").strip()
        for item in matched_records
        if str(item.get("label") or item.get("raw_label") or "").strip()
    ]
    for row in table_rows:
        if code_set.intersection(_codes(row.get("代号"))):
            label = str(row.get("元件名称", "")).strip()
            note = str(row.get("备注", "")).strip()
            if label:
                labels.append(label)
            if note:
                labels.append(note)
    return {
        "role": role,
        "codes": _unique(codes),
        "quantity": max(1, len(_unique(codes))),
        "pages": _pages(matched_records),
        "labels": _unique(labels),
    }


def _member(
    role: str,
    codes: list[str],
    records: list[dict[str, Any]],
    *,
    quantity: int,
) -> dict[str, Any]:
    return {
        "role": role,
        "codes": _unique(codes),
        "quantity": max(1, quantity),
        "pages": _pages(records),
        "labels": _unique(
            [
                str(
                    item.get("label")
                    or item.get("raw_label")
                    or item.get("component_type")
                    or ""
                ).strip()
                for item in records
                if str(
                    item.get("label")
                    or item.get("raw_label")
                    or item.get("component_type")
                    or ""
                ).strip()
            ]
        ),
    }


def _matching_codes(
    records: list[dict[str, Any]],
    table_rows: list[dict[str, Any]],
    prefixes: tuple[str, ...],
    keywords: tuple[str, ...],
) -> list[str]:
    found: list[str] = []
    for record in records:
        text = _record_text(record)
        codes = _codes(record.get("code"))
        if any(keyword in text for keyword in keywords):
            found.extend(codes)
            continue
        found.extend(
            code
            for code in codes
            if _matches_prefix(code, prefixes)
        )
    for row in table_rows:
        text = " ".join(
            str(row.get(key, ""))
            for key in ("代号", "元件名称", "规格型号", "备注")
        )
        codes = _codes(row.get("代号"))
        if any(keyword in text for keyword in keywords):
            found.extend(codes)
            continue
        found.extend(
            code
            for code in codes
            if _matches_prefix(code, prefixes)
        )
    return _unique(found)


def _table_role_codes(
    table_rows: list[dict[str, Any]],
    keywords: tuple[str, ...],
    *,
    command_only: bool = False,
) -> list[str]:
    codes: list[str] = []
    for row in table_rows:
        name = str(row.get("元件名称", ""))
        text = " ".join(
            str(row.get(key, ""))
            for key in ("元件名称", "备注")
        )
        if command_only and not any(
            keyword in name for keyword in ("按钮", "开关", "触点")
        ):
            continue
        if any(keyword in text for keyword in keywords):
            codes.extend(_codes(row.get("代号")))
    return _unique(codes)


def _relay_codes(
    records: list[dict[str, Any]],
    table_rows: list[dict[str, Any]],
) -> list[str]:
    codes: list[str] = []
    for row in table_rows:
        if "中间继电器" in str(row.get("元件名称", "")):
            codes.extend(_codes(row.get("代号")))
    if codes:
        return _unique(codes)
    for record in records:
        text = _record_text(record)
        if "继电器线圈" in text or "中间继电器" in text:
            codes.extend(_codes(record.get("code")))
    return _unique(codes)


def _table_rows(component_table: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(component_table, dict):
        return []
    rows = component_table.get("rows")
    return [item for item in rows if isinstance(item, dict)] if isinstance(
        rows, list
    ) else []


def _context_text(
    components: list[dict[str, Any]],
    symbols: list[dict[str, Any]],
    table_rows: list[dict[str, Any]],
    title_block: dict[str, Any] | None,
    control_signal_configuration: dict[str, Any] | None,
) -> str:
    values: list[str] = []
    values.extend(_record_text(item) for item in components + symbols)
    values.extend(
        " ".join(str(value) for value in row.values())
        for row in table_rows
    )
    if isinstance(title_block, dict):
        values.append(str(title_block.get("fields", title_block)))
    if isinstance(control_signal_configuration, dict):
        values.append(str(control_signal_configuration))
    return " ".join(values)


def _record_text(record: dict[str, Any]) -> str:
    return " ".join(
        str(record.get(key, ""))
        for key in (
            "label",
            "raw_label",
            "component_type",
            "code",
            "evidence",
        )
    )


def _codes(value: object) -> list[str]:
    values = re.split(r"[,，;；、\s]+", str(value or ""))
    return _unique(
        normalized
        for item in values
        if (normalized := _normalize_code(item))
    )


def _normalize_code(value: str) -> str:
    code = value.strip().upper().lstrip("-")
    code = re.sub(r"[:./-](A1|A2|NO|NC|\d+)$", "", code)
    return code


def _is_device_code(code: str) -> bool:
    return bool(
        re.fullmatch(r"(?:\d+)?K(?:A|C|M)?\d*", code)
    )


def _matches_prefix(code: str, prefixes: tuple[str, ...]) -> bool:
    return any(
        re.fullmatch(rf"(?:\d+)?{re.escape(prefix)}\d*", code)
        for prefix in prefixes
    )


def _record_quantity(record: dict[str, Any]) -> int:
    try:
        return max(1, int(record.get("occurrence_count", 1)))
    except (TypeError, ValueError):
        return 1


def _pages(records: list[dict[str, Any]]) -> list[int]:
    pages: set[int] = set()
    for item in records:
        try:
            page = int(item.get("page", 0))
        except (TypeError, ValueError):
            continue
        if page > 0:
            pages.add(page)
    return sorted(pages)


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
