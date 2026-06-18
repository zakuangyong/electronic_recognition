from __future__ import annotations

import re
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol, Sequence

import fitz


TITLE_BLOCK_FIELDS = (
    "客户名称",
    "工程名称",
    "系统名称",
    "合同号",
    "版本号",
    "图纸名称",
    "原理图号",
)

RIGHT_SIDE_STOP_WORDS = {
    "客户名称",
    "工程名称",
    "系统名称",
    "合同号",
    "版本号",
    "图纸名称",
    "原理图号",
    "共",
    "第",
}

LEFT_TITLE_LABELS = {"客户名称", "工程名称", "系统名称"}
RIGHT_TITLE_LABELS = {"合同号", "版本号", "图纸名称", "原理图号"}


class OCRBackend(Protocol):
    def recognize(self, image_path: Path) -> str:
        """Return OCR text for a rendered title-block image."""


@dataclass(slots=True)
class TextWord:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass(slots=True)
class TitleBlockExtraction:
    page: int
    fields: dict[str, str]
    text_source: str = "pdf_text"
    region: tuple[float, float, float, float] | None = None
    missing_fields: list[str] = field(default_factory=list)

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
class _LabelOccurrence:
    label: str
    line: _Line
    start: int
    end: int
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


def extract_title_block(
    pdf_path: str | Path,
    page_number: int = 1,
    ocr_backend: OCRBackend | None = None,
) -> TitleBlockExtraction:
    """Extract drawing title-block fields from a PDF page.

    The extractor prefers the PDF text layer. If important fields are missing
    and an OCR backend is supplied, it renders the inferred title-block region
    and parses OCR text as a best-effort fallback.
    """

    path = Path(pdf_path)
    document = fitz.open(path)
    try:
        if page_number < 1 or page_number > len(document):
            raise ValueError(
                f"page_number must be between 1 and {len(document)}"
            )
        page = document[page_number - 1]
        words = _page_words(page)
        extraction = extract_title_block_from_words(
            words,
            page_number=page_number,
            page_width=float(page.rect.width),
            page_height=float(page.rect.height),
        )
        if ocr_backend and _needs_ocr(extraction):
            extraction = _merge_ocr_fallback(
                page,
                extraction,
                ocr_backend,
            )
        return extraction
    finally:
        document.close()


def extract_title_block_from_words(
    words: Sequence[TextWord | dict[str, object]],
    page_number: int = 1,
    page_width: float | None = None,
    page_height: float | None = None,
) -> TitleBlockExtraction:
    normalized_words = _normalize_words(words)
    lines = _group_lines(normalized_words)
    labels = _find_labels(lines, TITLE_BLOCK_FIELDS)
    region = _infer_region(labels, normalized_words, page_width, page_height)
    fields = {
        "客户名称": "",
        "工程名称": "",
        "系统名称": "",
        "公司名称": "",
        "公司英文名": "",
        "合同号": "",
        "版本号": "",
        "图纸名称": "",
        "总页数": "",
        "原理图号": "",
        "当前页": "",
    }

    for label in TITLE_BLOCK_FIELDS:
        occurrence = _first_label(labels, label)
        if occurrence:
            fields[label] = _value_for_label(
                occurrence,
                labels,
                lines,
                region,
            )

    fields["总页数"] = _extract_page_count(lines, "共", "页")
    fields["当前页"] = _extract_page_count(lines, "第", "页")
    company_name, english_name = _extract_company_names(lines, labels, region)
    fields["公司名称"] = company_name
    fields["公司英文名"] = english_name

    return TitleBlockExtraction(
        page=page_number,
        fields=fields,
        region=region,
        missing_fields=[
            name
            for name, value in fields.items()
            if name not in {"客户名称", "系统名称", "版本号"} and not value
        ],
    )


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
        if str(item[4]).strip()
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
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        normalized.append(
            TextWord(
                text=text,
                x0=float(item["x0"]),
                y0=float(item["y0"]),
                x1=float(item["x1"]),
                y1=float(item["y1"]),
            )
        )
    return normalized


def _group_lines(words: Sequence[TextWord]) -> list[_Line]:
    rows: list[list[TextWord]] = []
    for word in sorted(words, key=lambda item: (item.cy, item.x0)):
        if rows and abs(_row_center(rows[-1]) - word.cy) <= 5:
            rows[-1].append(word)
        else:
            rows.append([word])
    return [
        _Line(sorted(row, key=lambda item: item.x0))
        for row in rows
        if row
    ]


def _row_center(words: Sequence[TextWord]) -> float:
    return sum(word.cy for word in words) / len(words)


def _find_labels(
    lines: Sequence[_Line],
    labels: Sequence[str],
) -> list[_LabelOccurrence]:
    occurrences: list[_LabelOccurrence] = []
    for line in lines:
        for label in labels:
            occurrences.extend(_find_label_in_line(line, label))
    return occurrences


def _find_label_in_line(line: _Line, label: str) -> list[_LabelOccurrence]:
    found: list[_LabelOccurrence] = []
    words = line.words
    for start in range(len(words)):
        combined = ""
        for end in range(start, min(start + len(label) + 2, len(words))):
            if end > start and words[end].x0 - words[end - 1].x1 > 25:
                break
            combined += _compact(words[end].text)
            if combined == label:
                span = words[start : end + 1]
                found.append(
                    _LabelOccurrence(
                        label=label,
                        line=line,
                        start=start,
                        end=end,
                        x0=min(word.x0 for word in span),
                        y0=min(word.y0 for word in span),
                        x1=max(word.x1 for word in span),
                        y1=max(word.y1 for word in span),
                    )
                )
                break
            if not label.startswith(combined):
                break
    return found


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _first_label(
    labels: Sequence[_LabelOccurrence],
    label: str,
) -> _LabelOccurrence | None:
    matches = [item for item in labels if item.label == label]
    if not matches:
        return None
    return sorted(matches, key=lambda item: (item.y0, item.x0))[0]


def _value_for_label(
    occurrence: _LabelOccurrence,
    all_labels: Sequence[_LabelOccurrence],
    lines: Sequence[_Line],
    region: tuple[float, float, float, float] | None,
) -> str:
    if occurrence.label in LEFT_TITLE_LABELS:
        return _value_in_left_title_cell(
            occurrence,
            all_labels,
            lines,
            region,
        )
    return _value_after_label(occurrence, all_labels)


def _value_in_left_title_cell(
    occurrence: _LabelOccurrence,
    all_labels: Sequence[_LabelOccurrence],
    lines: Sequence[_Line],
    region: tuple[float, float, float, float] | None,
) -> str:
    y0, y1 = _label_row_bounds(occurrence, all_labels, region)
    x0 = occurrence.x1 - 1
    x1 = _left_value_stop_x(all_labels, region)
    value_words: list[TextWord] = []
    for line in lines:
        if not (y0 <= line.cy <= y1):
            continue
        for word in line.words:
            if word.x0 < x0 or word.x0 >= x1:
                continue
            if _compact(word.text) in RIGHT_SIDE_STOP_WORDS:
                continue
            value_words.append(word)
    return _join_words(sorted(value_words, key=lambda word: (word.cy, word.x0)))


def _label_row_bounds(
    occurrence: _LabelOccurrence,
    all_labels: Sequence[_LabelOccurrence],
    region: tuple[float, float, float, float] | None,
) -> tuple[float, float]:
    left_labels = sorted(
        [item for item in all_labels if item.label in LEFT_TITLE_LABELS],
        key=lambda item: item.cy,
    )
    if occurrence not in left_labels:
        return occurrence.y0 - 8, occurrence.y1 + 8
    index = left_labels.index(occurrence)
    if index > 0:
        y0 = (left_labels[index - 1].cy + occurrence.cy) / 2
    else:
        next_height = (
            left_labels[index + 1].cy - occurrence.cy
            if len(left_labels) > 1
            else occurrence.y1 - occurrence.y0
        )
        y0 = occurrence.cy - next_height / 2
    if index + 1 < len(left_labels):
        y1 = (occurrence.cy + left_labels[index + 1].cy) / 2
    else:
        previous_height = (
            occurrence.cy - left_labels[index - 1].cy
            if index > 0
            else occurrence.y1 - occurrence.y0
        )
        y1 = occurrence.cy + previous_height / 2
    if region:
        y0 = max(region[1], y0)
        y1 = min(region[3], y1)
    return y0, y1


def _left_value_stop_x(
    labels: Sequence[_LabelOccurrence],
    region: tuple[float, float, float, float] | None,
) -> float:
    left_edge = max(
        (item.x1 for item in labels if item.label in LEFT_TITLE_LABELS),
        default=region[0] if region else 0.0,
    )
    right_edge = min(
        (item.x0 for item in labels if item.label in RIGHT_TITLE_LABELS),
        default=region[2] if region else float("inf"),
    )
    if right_edge == float("inf"):
        return right_edge
    return left_edge + (right_edge - left_edge) * 0.45


def _value_after_label(
    occurrence: _LabelOccurrence,
    all_labels: Sequence[_LabelOccurrence],
) -> str:
    words = occurrence.line.words
    stop_x = _next_stop_x(occurrence, all_labels)
    value_words: list[TextWord] = []
    for index, word in enumerate(words):
        if index <= occurrence.end:
            continue
        if word.x0 < occurrence.x1 - 1 or word.x0 >= stop_x:
            continue
        if _compact(word.text) in RIGHT_SIDE_STOP_WORDS:
            continue
        if (
            value_words
            and word.x0 - value_words[-1].x1 > 90
            and occurrence.label in {"客户名称", "工程名称", "系统名称"}
        ):
            break
        value_words.append(word)
    return _join_words(value_words)


def _next_stop_x(
    occurrence: _LabelOccurrence,
    all_labels: Sequence[_LabelOccurrence],
) -> float:
    candidates = [
        item.x0
        for item in all_labels
        if item.line is occurrence.line and item.x0 > occurrence.x1
    ]
    candidates.extend(
        word.x0
        for word in occurrence.line.words
        if word.x0 > occurrence.x1
        and _compact(word.text) in RIGHT_SIDE_STOP_WORDS
    )
    return min(candidates) if candidates else float("inf")


def _join_words(words: Sequence[TextWord]) -> str:
    if not words:
        return ""
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


def _extract_page_count(
    lines: Sequence[_Line],
    start_marker: str,
    end_marker: str,
) -> str:
    pattern = re.compile(
        rf"{re.escape(start_marker)}\s*([0-9]+)\s*{re.escape(end_marker)}"
    )
    for line in lines:
        compact = _compact(_join_words(line.words))
        match = pattern.search(compact)
        if match:
            return match.group(1)
    return ""


def _extract_company_names(
    lines: Sequence[_Line],
    labels: Sequence[_LabelOccurrence],
    region: tuple[float, float, float, float] | None,
) -> tuple[str, str]:
    if not region:
        return "", ""
    left_limit = _left_value_stop_x(labels, region)
    right_limit = min(
        (item.x0 for item in labels if item.label in RIGHT_TITLE_LABELS),
        default=region[2],
    )
    y_limit = _company_bottom_limit(labels, region)
    candidates: list[str] = []
    for line in lines:
        line_words = [
            word
            for word in line.words
            if left_limit < word.cx < right_limit
            and region[1] <= word.cy <= y_limit
        ]
        text = _join_words(line_words)
        if text:
            candidates.append(text)

    chinese_candidates = [
        _strip_logo_prefix(item)
        for item in candidates
        if re.search(r"[\u4e00-\u9fff]", item)
        and not any(label in item for label in TITLE_BLOCK_FIELDS)
        and not _looks_like_detail_table_text(item)
    ]
    english_candidates = [
        item
        for item in candidates
        if re.search(r"[A-Za-z]", item)
        and not re.search(r"[\u4e00-\u9fff]", item)
        and not _looks_like_detail_table_text(item)
    ]
    chinese = max(chinese_candidates, key=len, default="")
    english = max(english_candidates, key=len, default="")
    return chinese, english


def _company_bottom_limit(
    labels: Sequence[_LabelOccurrence],
    region: tuple[float, float, float, float],
) -> float:
    left_labels = [item for item in labels if item.label in LEFT_TITLE_LABELS]
    if len(left_labels) >= 3:
        return max(item.cy for item in left_labels) + 25
    return region[1] + (region[3] - region[1]) * 0.72


def _looks_like_detail_table_text(value: str) -> bool:
    compact = _compact(value)
    noise_tokens = ("序号", "代号", "元件名称", "规格型号", "数量", "备注")
    return any(token in compact for token in noise_tokens)


def _strip_logo_prefix(value: str) -> str:
    match = re.search(r"[\u4e00-\u9fff].*", value)
    return match.group(0) if match else value


def _infer_region(
    labels: Sequence[_LabelOccurrence],
    words: Sequence[TextWord],
    page_width: float | None,
    page_height: float | None,
) -> tuple[float, float, float, float] | None:
    if labels:
        x0 = min(item.x0 for item in labels)
        y0 = min(item.y0 for item in labels)
        x1 = max(item.x1 for item in labels)
        y1 = max(item.y1 for item in labels)
    elif words:
        x0 = min(word.x0 for word in words)
        y0 = min(word.y0 for word in words)
        x1 = max(word.x1 for word in words)
        y1 = max(word.y1 for word in words)
    else:
        return None

    return (
        max(0.0, x0 - 20),
        max(0.0, y0 - 20),
        min(page_width or x1 + 20, x1 + 260),
        min(page_height or y1 + 20, y1 + 40),
    )


def _needs_ocr(extraction: TitleBlockExtraction) -> bool:
    important = {"工程名称", "公司名称", "合同号", "图纸名称", "原理图号"}
    return any(not extraction.fields.get(name) for name in important)


def _merge_ocr_fallback(
    page: fitz.Page,
    extraction: TitleBlockExtraction,
    ocr_backend: OCRBackend,
) -> TitleBlockExtraction:
    region = extraction.region or tuple(page.rect)
    with tempfile.TemporaryDirectory(prefix="title-block-ocr-") as temp:
        image_path = Path(temp) / "title-block.png"
        clip = fitz.Rect(region)
        page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=clip, alpha=False).save(
            image_path
        )
        ocr_text = ocr_backend.recognize(image_path)
    fallback = _parse_ocr_text(ocr_text)
    fields = dict(extraction.fields)
    for key, value in fallback.items():
        if value and not fields.get(key):
            fields[key] = value
    return TitleBlockExtraction(
        page=extraction.page,
        fields=fields,
        text_source="pdf_text+ocr",
        region=extraction.region,
        missing_fields=[
            name
            for name, value in fields.items()
            if name not in {"客户名称", "系统名称", "版本号"} and not value
        ],
    )


def _parse_ocr_text(text: str) -> dict[str, str]:
    compact = _compact(text)
    fields: dict[str, str] = {}
    for label in TITLE_BLOCK_FIELDS:
        match = re.search(
            rf"{re.escape(label)}(.+?)(?={'|'.join(TITLE_BLOCK_FIELDS)}|$)",
            compact,
        )
        if match:
            fields[label] = match.group(1)
    total = re.search(r"共([0-9]+)页", compact)
    current = re.search(r"第([0-9]+)页", compact)
    if total:
        fields["总页数"] = total.group(1)
    if current:
        fields["当前页"] = current.group(1)
    return fields
