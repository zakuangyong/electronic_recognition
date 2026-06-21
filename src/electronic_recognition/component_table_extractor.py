from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from statistics import median
from typing import Sequence

import fitz

from .title_block_extractor import TextWord


COMPONENT_TABLE_COLUMNS = (
    "序号",
    "代号",
    "元件名称",
    "规格型号",
    "数量",
    "备注",
)

_EXPECTED_COLUMN_CENTERS = (0.026, 0.143, 0.326, 0.591, 0.789, 0.909)


@dataclass(slots=True)
class ComponentTablePage:
    page: int
    columns: list[str] = field(
        default_factory=lambda: list(COMPONENT_TABLE_COLUMNS)
    )
    rows: list[dict[str, object]] = field(default_factory=list)
    region: tuple[float, float, float, float] | None = None


@dataclass(slots=True)
class ComponentTableExtraction:
    columns: list[str] = field(
        default_factory=lambda: list(COMPONENT_TABLE_COLUMNS)
    )
    rows: list[dict[str, object]] = field(default_factory=list)
    pages: list[ComponentTablePage] = field(default_factory=list)
    text_source: str = "pdf_text"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class _Line:
    words: list[TextWord]

    @property
    def y0(self) -> float:
        return min(word.y0 for word in self.words)

    @property
    def y1(self) -> float:
        return max(word.y1 for word in self.words)

    @property
    def cy(self) -> float:
        return sum(word.cy for word in self.words) / len(self.words)


@dataclass(slots=True)
class _Column:
    name: str
    left: float
    right: float

    @property
    def center(self) -> float:
        return (self.left + self.right) / 2


def extract_component_table(
    pdf_path: str | Path,
) -> ComponentTableExtraction:
    document = fitz.open(Path(pdf_path))
    try:
        pages: list[ComponentTablePage] = []
        rows: list[dict[str, object]] = []
        for index, page in enumerate(document):
            result = extract_component_table_from_words(
                _page_words(page),
                page_number=index + 1,
                page_width=float(page.rect.width),
                page_height=float(page.rect.height),
            )
            if result.rows:
                pages.append(result)
                rows.extend(result.rows)
        return ComponentTableExtraction(rows=rows, pages=pages)
    finally:
        document.close()


def extract_component_table_from_words(
    words: Sequence[TextWord | dict[str, object]],
    page_number: int = 1,
    page_width: float | None = None,
    page_height: float | None = None,
) -> ComponentTablePage:
    normalized = _normalize_words(words)
    lines = _group_rows(normalized)
    candidates: list[ComponentTablePage] = []
    for header in lines:
        if not _looks_like_header(header):
            continue
        columns = _build_columns(header, lines, page_width)
        body_lines = _select_body_lines(lines, header, columns, page_height)
        rows, used_lines = _parse_body_lines(body_lines, columns, page_number)
        if not rows:
            continue
        candidates.append(
            ComponentTablePage(
                page=page_number,
                rows=rows,
                region=_region_for_lines(
                    [header, *used_lines],
                    page_width,
                    page_height,
                ),
            )
        )
    if not candidates:
        return ComponentTablePage(page=page_number)
    return max(candidates, key=lambda item: len(item.rows))


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


def _group_rows(words: Sequence[TextWord]) -> list[_Line]:
    if not words:
        return []
    heights = [max(1.0, word.y1 - word.y0) for word in words]
    tolerance = max(4.0, median(heights) * 0.55)
    rows: list[list[TextWord]] = []
    for word in sorted(words, key=lambda item: (item.cy, item.x0)):
        row = next(
            (
                current
                for current in rows
                if abs(word.cy - _row_center(current)) <= tolerance
            ),
            None,
        )
        if row is None:
            rows.append([word])
        else:
            row.append(word)
    return [_Line(sorted(row, key=lambda item: item.x0)) for row in rows]


def _row_center(words: Sequence[TextWord]) -> float:
    return sum(word.cy for word in words) / len(words)


def _looks_like_header(line: _Line) -> bool:
    compact = _compact(_join_words(line.words))
    matches = [
        column for column in COMPONENT_TABLE_COLUMNS if column in compact
    ]
    return (
        len(matches) >= 4
        and "代号" in compact
        and "元件名称" in compact
        and ("规格型号" in compact or "数量" in compact)
    )


def _build_columns(
    header: _Line,
    lines: Sequence[_Line],
    page_width: float | None,
) -> list[_Column]:
    centers = [_label_center(header, column) for column in COMPONENT_TABLE_COLUMNS]
    known = [
        (index, center)
        for index, center in enumerate(centers)
        if center is not None
    ]
    header_min = min(word.x0 for word in header.words)
    header_max = max(word.x1 for word in header.words)
    table_x0 = header_min
    table_x1 = header_max
    if len(known) >= 2:
        first_index, first_center = known[0]
        last_index, last_center = known[-1]
        rel_width = (
            _EXPECTED_COLUMN_CENTERS[last_index]
            - _EXPECTED_COLUMN_CENTERS[first_index]
        )
        if rel_width > 0:
            width = (last_center - first_center) / rel_width
            table_x0 = first_center - (
                _EXPECTED_COLUMN_CENTERS[first_index] * width
            )
            table_x1 = table_x0 + width
    table_x0, table_x1 = _expand_table_bounds(
        table_x0,
        table_x1,
        header,
        lines,
        page_width,
    )
    width = max(1.0, table_x1 - table_x0)
    filled_centers = [
        center
        if center is not None
        else table_x0 + _EXPECTED_COLUMN_CENTERS[index] * width
        for index, center in enumerate(centers)
    ]
    boundaries = [table_x0]
    boundaries.extend(
        (left + right) / 2
        for left, right in zip(filled_centers, filled_centers[1:])
    )
    boundaries.append(table_x1)
    quantity_center = filled_centers[4]
    note_center = filled_centers[5]
    if note_center > quantity_center:
        half_width = max(10.0, min(24.0, (note_center - quantity_center) * 0.65))
        boundaries[4] = max(boundaries[3] + 8.0, quantity_center - half_width)
        boundaries[5] = min(boundaries[6] - 8.0, quantity_center + half_width)
    return [
        _Column(name, boundaries[index], boundaries[index + 1])
        for index, name in enumerate(COMPONENT_TABLE_COLUMNS)
    ]


def _label_center(line: _Line, label: str) -> float | None:
    compact_label = _compact(label)
    for word in line.words:
        compact_word = _compact(word.text)
        if compact_label in compact_word:
            start = compact_word.find(compact_label)
            unit = (word.x1 - word.x0) / max(1, len(compact_word))
            return word.x0 + unit * (start + len(compact_label) / 2)
    for start in range(len(line.words)):
        combined = ""
        selected: list[TextWord] = []
        for word in line.words[start : start + len(label) + 1]:
            combined += _compact(word.text)
            selected.append(word)
            if combined == compact_label:
                return (
                    min(item.x0 for item in selected)
                    + max(item.x1 for item in selected)
                ) / 2
            if not compact_label.startswith(combined):
                break
    return None


def _expand_table_bounds(
    table_x0: float,
    table_x1: float,
    header: _Line,
    lines: Sequence[_Line],
    page_width: float | None,
) -> tuple[float, float]:
    max_distance = 260.0
    nearby_words = [
        word
        for line in lines
        if abs(line.cy - header.cy) <= max_distance
        for word in line.words
        if table_x0 - 80 <= word.cx <= table_x1 + 80
        and not _looks_like_margin_grid_label(word.text)
    ]
    if nearby_words:
        table_x0 = min(table_x0, min(word.x0 for word in nearby_words))
        table_x1 = max(table_x1, max(word.x1 for word in nearby_words))
    if page_width is not None:
        table_x0 = max(0.0, table_x0)
        table_x1 = min(page_width, table_x1)
    if table_x1 <= table_x0:
        table_x1 = table_x0 + 1.0
    return table_x0, table_x1


def _select_body_lines(
    lines: Sequence[_Line],
    header: _Line,
    columns: Sequence[_Column],
    page_height: float | None,
) -> list[_Line]:
    above = _near_header_sequence_block(
        _side_body_lines(lines, header, columns, page_height, above=True),
        columns,
        above=True,
    )
    below = _near_header_sequence_block(
        _side_body_lines(lines, header, columns, page_height, above=False),
        columns,
        above=False,
    )
    above_rows = _sequence_line_count(above, columns)
    below_rows = _sequence_line_count(below, columns)
    if above_rows >= below_rows and above_rows > 0:
        return sorted(above, key=lambda line: line.cy)
    if below_rows > 0:
        return sorted(below, key=lambda line: line.cy)
    return []


def _side_body_lines(
    lines: Sequence[_Line],
    header: _Line,
    columns: Sequence[_Column],
    page_height: float | None,
    above: bool,
) -> list[_Line]:
    max_distance = max(320.0, (page_height or 0.0) * 0.6)
    selected: list[_Line] = []
    for line in lines:
        if line is header:
            continue
        distance = header.cy - line.cy if above else line.cy - header.cy
        if distance <= 0 or distance > max_distance:
            continue
        if not _line_overlaps_table(line, columns):
            continue
        cells, _cell_words = _line_to_cells(line, columns)
        if _is_sequence(cells["序号"]) or _could_be_continuation(cells):
            selected.append(line)
    return selected


def _near_header_sequence_block(
    lines: Sequence[_Line],
    columns: Sequence[_Column],
    above: bool,
) -> list[_Line]:
    sequence_lines = [
        line
        for line in lines
        if _is_sequence(_line_to_cells(line, columns)[0]["序号"])
    ]
    if not sequence_lines:
        return []
    ordered = sorted(sequence_lines, key=lambda line: line.cy, reverse=above)
    cluster = [ordered[0]]
    gaps = [
        abs(right.cy - left.cy)
        for left, right in zip(
            sorted(sequence_lines, key=lambda line: line.cy),
            sorted(sequence_lines, key=lambda line: line.cy)[1:],
        )
        if abs(right.cy - left.cy) > 0
    ]
    typical_gap = median(gaps) if gaps else 24.0
    max_gap = max(36.0, min(70.0, typical_gap * 2.6))
    previous = ordered[0]
    for line in ordered[1:]:
        gap = abs(previous.cy - line.cy)
        if gap > max_gap:
            break
        cluster.append(line)
        previous = line
    top = min(line.cy for line in cluster)
    bottom = max(line.cy for line in cluster)
    padding = max(14.0, min(32.0, typical_gap * 0.65))
    return [
        line
        for line in lines
        if top - padding <= line.cy <= bottom + padding
    ]


def _sequence_line_count(
    lines: Sequence[_Line],
    columns: Sequence[_Column],
) -> int:
    count = 0
    for line in lines:
        cells, _cell_words = _line_to_cells(line, columns)
        if _is_sequence(cells["序号"]):
            count += 1
    return count


def _line_overlaps_table(line: _Line, columns: Sequence[_Column]) -> bool:
    left = columns[0].left - 8
    right = columns[-1].right + 8
    return any(left <= word.cx <= right for word in line.words)


def _parse_body_lines(
    lines: Sequence[_Line],
    columns: Sequence[_Column],
    page_number: int,
) -> tuple[list[dict[str, object]], list[_Line]]:
    line_infos = [
        (line, _line_to_cells(line, columns)[0]) for line in lines
    ]
    sequence_infos = [
        (line, cells)
        for line, cells in line_infos
        if _is_sequence(cells["序号"])
    ]
    if not sequence_infos:
        return [], []
    sequence_infos.sort(key=lambda item: item[0].cy)
    typical_gap = _typical_sequence_gap([line for line, _cells in sequence_infos])
    grouped: dict[int, list[tuple[_Line, dict[str, str], bool]]] = {}
    for index, (line, cells) in enumerate(sequence_infos):
        grouped[index] = [(line, cells, True)]
    used = {id(line) for line, _cells in sequence_infos}

    for line, cells in line_infos:
        if id(line) in used or not _could_be_continuation(cells):
            continue
        nearest_index, nearest_distance = min(
            (
                (index, abs(line.cy - sequence_line.cy))
                for index, (sequence_line, _cells) in enumerate(sequence_infos)
            ),
            key=lambda item: item[1],
        )
        if nearest_distance > max(18.0, typical_gap * 0.65):
            continue
        grouped[nearest_index].append((line, cells, False))
        used.add(id(line))

    rows: list[dict[str, object]] = []
    used_lines: list[_Line] = []
    for index, (_sequence_line, sequence_cells) in enumerate(sequence_infos):
        row: dict[str, object] = {
            "page": page_number,
            **{column: "" for column in COMPONENT_TABLE_COLUMNS},
        }
        for line, cells, is_sequence in sorted(
            grouped[index], key=lambda item: item[0].cy
        ):
            _append_cells(row, cells, is_sequence)
            used_lines.append(line)
        row["序号"] = sequence_cells["序号"].strip()
        rows.append(row)
    return rows, used_lines


def _typical_sequence_gap(lines: Sequence[_Line]) -> float:
    centers = sorted(line.cy for line in lines)
    gaps = [
        right - left
        for left, right in zip(centers, centers[1:])
        if right > left
    ]
    return median(gaps) if gaps else 16.0


def _line_to_cells(
    line: _Line,
    columns: Sequence[_Column],
) -> tuple[dict[str, str], dict[str, list[TextWord]]]:
    cell_words: dict[str, list[TextWord]] = {
        column.name: [] for column in columns
    }
    for word in line.words:
        column = _column_for_word(word, columns)
        if column:
            cell_words[column.name].append(word)
    cells = {
        name: _join_words(sorted(words, key=lambda word: word.x0))
        for name, words in cell_words.items()
    }
    return cells, cell_words


def _column_for_word(
    word: TextWord,
    columns: Sequence[_Column],
) -> _Column | None:
    for column in columns:
        if column.left <= word.cx < column.right:
            return column
    if columns and abs(word.cx - columns[-1].right) <= 2:
        return columns[-1]
    return None


def _is_sequence(value: str) -> bool:
    stripped = value.strip().strip(".、")
    return bool(re.fullmatch(r"\d{1,3}", stripped))


def _could_be_continuation(cells: dict[str, str]) -> bool:
    if _compact(cells.get("序号", "")):
        return False
    compact_text = _compact("".join(cells.values()))
    if not compact_text:
        return False
    if len(compact_text) <= 1:
        return False
    if any(column in compact_text for column in COMPONENT_TABLE_COLUMNS):
        return False
    return any(
        _compact(cells.get(column, ""))
        for column in ("代号", "元件名称", "规格型号", "备注")
    )


def _append_cells(
    row: dict[str, object],
    cells: dict[str, str],
    is_sequence: bool,
) -> None:
    cells = dict(cells)
    if not is_sequence:
        cells = _normalize_continuation_cells(cells, str(row.get("规格型号", "")))
    for column in COMPONENT_TABLE_COLUMNS:
        value = cells.get(column, "").strip()
        if not value:
            continue
        if column == "序号":
            if is_sequence:
                row[column] = value
            continue
        current = str(row.get(column, "")).strip()
        row[column] = _merge_text(current, value)


def _normalize_continuation_cells(
    cells: dict[str, str],
    previous_model: str,
) -> dict[str, str]:
    cells = dict(cells)
    if (
        not _compact(cells.get("规格型号", ""))
        and _looks_like_model_continuation(
            cells.get("元件名称", ""),
            previous_model,
        )
    ):
        cells["规格型号"] = cells.get("元件名称", "")
        cells["元件名称"] = ""
    if (
        _looks_like_model_continuation(
            cells.get("数量", ""),
            _merge_text(previous_model, cells.get("规格型号", "")),
        )
        and not _compact(cells.get("备注", ""))
    ):
        cells["规格型号"] = _merge_text(
            cells.get("规格型号", ""),
            cells.get("数量", ""),
        )
        cells["数量"] = ""
    return cells


def _looks_like_model_continuation(value: str, previous_model: str) -> bool:
    text = value.strip()
    if not text:
        return False
    if previous_model.rstrip().endswith(("+", "/", "-", "(", "（")):
        return True
    return bool(
        re.search(r"[A-Za-z0-9]", text)
        and re.search(r"[-+/()（）]", text)
    )


def _looks_like_margin_grid_label(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z]", _compact(value)))


def _merge_text(left: str, right: str) -> str:
    if not left:
        return right
    if not right:
        return left
    return f"{left} {right}".strip()


def _region_for_lines(
    lines: Sequence[_Line],
    page_width: float | None,
    page_height: float | None,
) -> tuple[float, float, float, float] | None:
    words = [word for line in lines for word in line.words]
    if not words:
        return None
    padding = max(2.0, median(max(1.0, word.y1 - word.y0) for word in words) * 0.6)
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


def _join_words(words: Sequence[TextWord]) -> str:
    text = ""
    previous: TextWord | None = None
    for word in words:
        if previous and _needs_space(previous.text, word.text):
            text += " "
        text += word.text
        previous = word
    return text.strip()


def _needs_space(left: str, right: str) -> bool:
    return bool(
        re.search(r"[A-Za-z0-9]$", left)
        and re.search(r"^[A-Za-z0-9]", right)
    )


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value)
