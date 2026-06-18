from __future__ import annotations

from electronic_recognition.control_signal_extractor import (
    extract_control_signal_from_words,
)
from electronic_recognition.title_block_extractor import TextWord


def test_extract_signal_inputs_and_control_modes_from_pdf_words() -> None:
    words = [
        TextWord("信号输入", 180, 20, 240, 34),
        TextWord("公共端", 20, 42, 70, 56),
        TextWord("自动", 100, 42, 130, 56),
        TextWord("开阀", 165, 42, 195, 56),
        TextWord("关阀", 230, 42, 260, 56),
        TextWord("就地/手动开关阀", 290, 42, 410, 56),
        TextWord("控制方式", 720, 20, 780, 34),
        TextWord("PLC", 600, 42, 628, 56),
        TextWord("（关阀）", 630, 42, 680, 56),
        TextWord("环控（关阀）", 700, 42, 775, 56),
        TextWord("PLC", 795, 42, 823, 56),
        TextWord("（开阀）", 825, 42, 875, 56),
        TextWord("环控（开阀）", 895, 42, 970, 56),
        TextWord("无关说明", 450, 200, 510, 214),
    ]

    extraction = extract_control_signal_from_words(
        words,
        page_number=1,
        page_width=1000,
        page_height=300,
    )

    assert extraction.raw_signal_inputs == [
        "公共端",
        "自动",
        "开阀",
        "关阀",
        "就地/手动开关阀",
    ]
    groups = {
        group.category: group.items for group in extraction.signal_inputs
    }
    assert groups["公共信号"] == ["公共端"]
    assert groups["运行模式"] == ["自动", "就地/手动开关阀"]
    assert groups["控制指令"] == ["开阀", "关阀"]
    assert [
        (mode.controller, mode.action)
        for mode in extraction.control_modes
    ] == [
        ("PLC", "关阀"),
        ("环控", "关阀"),
        ("PLC", "开阀"),
        ("环控", "开阀"),
    ]
    assert "signal_inputs" in extraction.regions
    assert "control_modes" in extraction.regions


def test_extractor_returns_empty_when_anchors_are_absent() -> None:
    extraction = extract_control_signal_from_words(
        [TextWord("普通说明文字", 10, 10, 100, 25)],
        page_number=2,
        page_width=500,
        page_height=300,
    )

    assert extraction.signal_inputs == []
    assert extraction.control_modes == []
    assert extraction.regions == {}


def test_extractor_accepts_split_header_words() -> None:
    extraction = extract_control_signal_from_words(
        [
            TextWord("信号", 100, 10, 125, 24),
            TextWord("输入", 126, 10, 151, 24),
            TextWord("自动", 105, 34, 135, 48),
        ],
        page_width=400,
        page_height=200,
    )

    assert extraction.raw_signal_inputs == ["自动"]
