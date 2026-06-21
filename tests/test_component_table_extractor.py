from __future__ import annotations

from electronic_recognition.component_table_extractor import (
    extract_component_table_from_words,
)
from electronic_recognition.title_block_extractor import TextWord


def test_extract_component_table_from_pdf_words() -> None:
    words = [
        *_row(100, ["8", "TA_附件", "端子（附件）", "D-TB4/10 附：E/UK（2）+ UZB6横 1-10（1）", "1", ""]),
        *_row(130, ["7", "TA", "二次端子", "TB4I", "16", ""]),
        TextWord("AD16-22D/y31S 黄色 AC220V 附：A22-RAS-X(1)", 360, 148, 690, 160),
        *_row(160, ["6", "3LT", "指示灯", "", "1", "故障指示"]),
        TextWord("+ 有机玻璃 1.0 *26mm*8mm无背胶(1)", 360, 178, 610, 190),
        *_row(210, ["5", "1LT", "指示灯", "AD16-22D/r31S 红色 AC220V 附：A22-RAS-X(1)", "1", "运行指示"]),
        *_row(240, ["4", "FUN1,FUP1", "低压熔断器", "NRT14-20 6A 附：NRT14-20 690V（1）", "2", ""]),
        TextWord("CR-WX230AC4 附：CR-M4SS10095969(1) +", 360, 258, 690, 270),
        *_row(270, ["3", "1KA", "继电器", "", "1", ""]),
        TextWord("CR-MH1(2)", 360, 280, 430, 292),
        *_row(320, ["2", "51GD", "H火灾监控", "详见一次系统图", "1", ""]),
        *_row(350, ["1", "52A", "S 塑壳断路器", "详见一次系统图", "1", ""]),
        *_row(380, ["序号", "代号", "元件名称", "规格型号", "数量", "备注"]),
    ]

    extraction = extract_component_table_from_words(
        words,
        page_number=3,
        page_width=1000,
        page_height=420,
    )

    assert len(extraction.rows) == 8
    assert extraction.rows[0]["page"] == 3
    assert extraction.rows[0]["序号"] == "8"
    assert extraction.rows[0]["代号"] == "TA_附件"
    assert extraction.rows[0]["元件名称"] == "端子（附件）"
    assert extraction.rows[1]["数量"] == "16"
    assert extraction.rows[2]["规格型号"] == (
        "AD16-22D/y31S 黄色 AC220V 附：A22-RAS-X(1) "
        "+ 有机玻璃 1.0 *26mm*8mm无背胶(1)"
    )
    assert extraction.rows[2]["备注"] == "故障指示"
    assert extraction.rows[5]["规格型号"].endswith(
        "CR-M4SS10095969(1) + CR-MH1(2)"
    )
    assert extraction.region is not None


def test_extractor_returns_empty_without_header() -> None:
    extraction = extract_component_table_from_words(
        [
            TextWord("普通说明文字", 10, 10, 80, 24),
            TextWord("FU1", 120, 10, 145, 24),
        ],
        page_width=300,
        page_height=200,
    )

    assert extraction.rows == []
    assert extraction.region is None


def _row(y: float, values: list[str]) -> list[TextWord]:
    xs = [20, 92, 250, 360, 790, 835]
    widths = [30, 100, 80, 330, 28, 110]
    return [
        TextWord(value, x, y, x + width, y + 12)
        for value, x, width in zip(values, xs, widths)
        if value
    ]
