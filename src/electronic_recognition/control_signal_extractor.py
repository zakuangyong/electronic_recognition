from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from statistics import median
from typing import Sequence

import fitz

from .title_block_extractor import TextWord


ANCHORS = ("信号输入", "控制方式")
ACTION_WORDS = ("开阀", "关阀", "开", "关", "启动", "停止")


@dataclass(slots=True)
class ControlMode:
    controller: str
    action: str
    raw: str


@dataclass(slots=True)
class SignalInputGroup:
    category: str
    items: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ControlSignalPage:
    page: int
    signal_inputs: list[SignalInputGroup] = field(default_factory=list)
    control_modes: list[ControlMode] = field(default_factory=list)
    raw_signal_inputs: list[str] = field(default_factory=list)
    raw_control_modes: list[str] = field(default_factory=list)
    regions: dict[str, tuple[float, float, float, float]] = field(
        default_factory=dict
    )


@dataclass(slots=True)
class ControlSignalExtraction:
    pages: list[ControlSignalPage] = field(default_factory=list)
    signal_inputs: list[SignalInputGroup] = field(default_factory=list)
    control_modes: list[ControlMode] = field(default_factory=list)
    text_source: str = "pdf_text"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def extract_control_signal_configuration(
    pdf_path: str | Path,
) -> ControlSignalExtraction:
    document = fitz.open(Path(pdf_path))
    try:
        page_results: list[ControlSignalPage] = []
        for index, page in enumerate(document):
            result = extract_control_signal_from_words(
                _page_words(page),
                page_number=index + 1,
                page_width=float(page.rect.width),
                page_height=float(page.rect.height),
            )
            if result.raw_signal_inputs or result.raw_control_modes:
                page_results.append(result)
        return ControlSignalExtraction(
            pages=page_results,
            signal_inputs=_merge_signal_groups(page_results),
            control_modes=_merge_control_modes(page_results),
        )
    finally:
        document.close()


def extract_control_signal_from_words(
    words: Sequence[TextWord | dict[str, object]],
    page_number: int = 1,
    page_width: float | None = None,
    page_height: float | None = None,
) -> ControlSignalPage:
    normalized = _normalize_words(words)
    anchors = {
        label: _find_anchor(normalized, label) for label in ANCHORS
    }
    result = ControlSignalPage(page=page_number)
    for label, anchor in anchors.items():
        if anchor is None:
            continue
        cells = _extract_cells_below_anchor(
            normalized,
            anchor,
            [item for item in anchors.values() if item is not None],
            page_width,
        )
        region = _region_for_words(
            [anchor, *[word for cell in cells for word in cell]],
            page_width,
            page_height,
        )
        values = [
            _clean_value("".join(word.text for word in cell))
            for cell in cells
        ]
        values = [
            value
            for value in values
            if value and _compact(value) not in {_compact(item) for item in ANCHORS}
        ]
        if label == "信号输入":
            result.raw_signal_inputs = _unique(values)
            result.signal_inputs = _classify_signal_inputs(values)
            if region:
                result.regions["signal_inputs"] = region
        else:
            result.raw_control_modes = _unique(values)
            result.control_modes = [
                mode
                for value in values
                for mode in [_parse_control_mode(value)]
                if mode is not None
            ]
            if region:
                result.regions["control_modes"] = region
    return result


def _page_words(page: fitz.Page) -> list[TextWord]:
    return [
        TextWord(
            text=str(item[4]).strip(),
            x0=float(item[0]),
            y0=float(item[1]),
            x1=float(item[2]),
            y1=float(item[3]),
        )
        for item in page.get_text("words")
        if len(item) >= 5 and str(item[4]).strip()
    ]


def _normalize_words(
    words: Sequence[TextWord | dict[str, object]],
) -> list[TextWord]:
    normalized: list[TextWord] = []
    for item in words:
        if isinstance(item, TextWord):
            if item.text.strip():
                normalized.append(item)
            continue
        try:
            word = TextWord(
                text=str(item["text"]).strip(),
                x0=float(item["x0"]),
                y0=float(item["y0"]),
                x1=float(item["x1"]),
                y1=float(item["y1"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
        if word.text:
            normalized.append(word)
    return normalized


def _find_anchor(
    words: list[TextWord],
    label: str,
) -> TextWord | None:
    exact = [
        word for word in words if _compact(word.text) == _compact(label)
    ]
    if exact:
        return sorted(exact, key=lambda word: (word.y0, word.x0))[0]
    containing = [
        word for word in words if _compact(label) in _compact(word.text)
    ]
    if containing:
        return sorted(containing, key=lambda word: (word.y0, word.x0))[0]
    for row in _group_rows(words, tolerance=5.0):
        for start in range(len(row)):
            text = ""
            selected: list[TextWord] = []
            for word in row[start : start + len(label) + 1]:
                text += _compact(word.text)
                selected.append(word)
                if text == _compact(label):
                    return TextWord(
                        text=label,
                        x0=min(item.x0 for item in selected),
                        y0=min(item.y0 for item in selected),
                        x1=max(item.x1 for item in selected),
                        y1=max(item.y1 for item in selected),
                    )
                if not _compact(label).startswith(text):
                    break
    return None


def _extract_cells_below_anchor(
    words: list[TextWord],
    anchor: TextWord,
    anchors: list[TextWord],
    page_width: float | None,
) -> list[list[TextWord]]:
    anchor_height = max(4.0, anchor.y1 - anchor.y0)
    minimum_y = anchor.cy + anchor_height * 0.35
    maximum_y = anchor.y1 + anchor_height * 3.2
    nearest_other_distance = min(
        (
            abs(item.cx - anchor.cx)
            for item in anchors
            if item is not anchor
        ),
        default=(page_width or anchor.x1 * 2) * 0.7,
    )
    horizontal_radius = min(
        (page_width or anchor.x1 * 2) * 0.38,
        max(anchor_height * 22, nearest_other_distance * 0.48),
    )
    candidates = [
        word
        for word in words
        if word is not anchor
        and minimum_y <= word.cy <= maximum_y
        and abs(word.cx - anchor.cx) <= horizontal_radius
        and all(
            abs(word.cx - anchor.cx) <= abs(word.cx - other.cx)
            for other in anchors
            if other is not anchor
        )
    ]
    if not candidates:
        return []
    rows = _group_rows(candidates, tolerance=anchor_height * 0.75)
    cells: list[list[TextWord]] = []
    for row in rows[:2]:
        cells.extend(_split_row_cells(row))
    return cells


def _group_rows(
    words: list[TextWord],
    tolerance: float,
) -> list[list[TextWord]]:
    rows: list[list[TextWord]] = []
    for word in sorted(words, key=lambda item: (item.cy, item.x0)):
        row = next(
            (
                current
                for current in rows
                if abs(
                    word.cy
                    - sum(item.cy for item in current) / len(current)
                )
                <= tolerance
            ),
            None,
        )
        if row is None:
            rows.append([word])
        else:
            row.append(word)
    return [sorted(row, key=lambda word: word.x0) for row in rows]


def _split_row_cells(words: list[TextWord]) -> list[list[TextWord]]:
    if not words:
        return []
    heights = [max(1.0, word.y1 - word.y0) for word in words]
    merge_gap = max(2.0, median(heights) * 0.65)
    cells: list[list[TextWord]] = [[words[0]]]
    for word in words[1:]:
        previous = cells[-1][-1]
        gap = word.x0 - previous.x1
        if gap <= merge_gap or _needs_join(previous.text, word.text):
            cells[-1].append(word)
        else:
            cells.append([word])
    return cells


def _needs_join(left: str, right: str) -> bool:
    return bool(
        left.endswith(("/", "(", "（", "-", "+"))
        or right.startswith((")", "）", "/", "-", "+"))
        or left.upper() in {"PLC", "DCS"}
    )


def _classify_signal_inputs(
    values: list[str],
) -> list[SignalInputGroup]:
    groups: dict[str, list[str]] = {
        "公共信号": [],
        "运行模式": [],
        "控制指令": [],
        "其他": [],
    }
    for value in values:
        compact = _compact(value)
        if "公共" in compact or "共用" in compact:
            category = "公共信号"
        elif any(
            keyword in compact
            for keyword in ("自动", "手动", "就地", "远程", "本地")
        ):
            category = "运行模式"
        elif any(keyword in compact for keyword in ACTION_WORDS):
            category = "控制指令"
        else:
            category = "其他"
        groups[category].append(value)
    return [
        SignalInputGroup(category=category, items=_unique(items))
        for category, items in groups.items()
        if items
    ]


def _parse_control_mode(value: str) -> ControlMode | None:
    compact = _compact(value)
    match = re.match(
        r"(?P<controller>.+?)[（(](?P<action>开阀|关阀|开|关|启动|停止)[）)]$",
        compact,
    )
    if not match:
        for action in ACTION_WORDS:
            if compact.endswith(action) and len(compact) > len(action):
                controller = compact[: -len(action)].strip("（）()/-")
                if controller:
                    return ControlMode(controller, action, value)
        return None
    return ControlMode(
        controller=match.group("controller"),
        action=match.group("action"),
        raw=value,
    )


def _merge_signal_groups(
    pages: list[ControlSignalPage],
) -> list[SignalInputGroup]:
    merged: dict[str, list[str]] = {}
    for page in pages:
        for group in page.signal_inputs:
            merged.setdefault(group.category, []).extend(group.items)
    return [
        SignalInputGroup(category, _unique(items))
        for category, items in merged.items()
    ]


def _merge_control_modes(
    pages: list[ControlSignalPage],
) -> list[ControlMode]:
    seen: set[tuple[str, str]] = set()
    modes: list[ControlMode] = []
    for page in pages:
        for mode in page.control_modes:
            key = (mode.controller.casefold(), mode.action.casefold())
            if key not in seen:
                seen.add(key)
                modes.append(mode)
    return modes


def _region_for_words(
    words: list[TextWord],
    page_width: float | None,
    page_height: float | None,
) -> tuple[float, float, float, float] | None:
    if not words:
        return None
    padding = max(
        2.0,
        median(max(1.0, word.y1 - word.y0) for word in words) * 0.6,
    )
    return (
        max(0.0, min(word.x0 for word in words) - padding),
        max(0.0, min(word.y0 for word in words) - padding),
        min(
            page_width or max(word.x1 for word in words) + padding,
            max(word.x1 for word in words) + padding,
        ),
        min(
            page_height or max(word.y1 for word in words) + padding,
            max(word.y1 for word in words) + padding,
        ),
    )


def _clean_value(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" |")


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value).strip()


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = _compact(value).casefold()
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result
