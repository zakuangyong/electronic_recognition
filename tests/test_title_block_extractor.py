from __future__ import annotations

from electronic_recognition.title_block_extractor import (
    TextWord,
    extract_title_block_from_words,
)


def test_extract_title_block_from_pdf_words() -> None:
    words = [
        TextWord("客户名称", 342.8, 748.0, 382.3, 762.1),
        TextWord("合同号", 930.5, 744.2, 970.0, 758.4),
        TextWord("A17387", 1027.1, 744.1, 1056.7, 758.2),
        TextWord("镇江默勒电器有限公司", 725.1, 762.1, 902.5, 784.3),
        TextWord("版本号", 930.5, 765.4, 970.0, 779.5),
        TextWord("工程名称", 342.8, 776.0, 382.3, 790.1),
        TextWord("成都地铁轨道交通18号线", 437.8, 776.2, 546.5, 790.3),
        TextWord("图纸名称", 929.9, 786.9, 969.5, 801.0),
        TextWord("双电源进线", 1021.0, 786.6, 1070.4, 800.7),
        TextWord("共", 1114.2, 786.4, 1124.1, 800.5),
        TextWord("2", 1136.2, 786.6, 1141.1, 800.7),
        TextWord("页", 1153.7, 786.4, 1163.6, 800.5),
        TextWord("Zhenjiang", 726.7, 789.9, 784.8, 806.0),
        TextWord("Klockner-Moeller", 791.2, 789.9, 894.4, 806.0),
        TextWord("系统名称", 342.8, 804.4, 382.3, 818.5),
        TextWord("原理图号", 930.4, 807.9, 969.9, 822.0),
        TextWord("CDDT-6-DZ-.01", 1013.6, 807.8, 1077.8, 821.9),
        TextWord("第", 1114.2, 808.1, 1124.0, 822.2),
        TextWord("1", 1136.2, 807.7, 1141.1, 821.8),
        TextWord("页", 1153.7, 808.1, 1163.5, 822.2),
    ]

    extraction = extract_title_block_from_words(
        words,
        page_number=1,
        page_width=1190.5512,
        page_height=841.8898,
    )

    assert extraction.fields["客户名称"] == ""
    assert extraction.fields["工程名称"] == "成都地铁轨道交通18号线"
    assert extraction.fields["系统名称"] == ""
    assert extraction.fields["公司名称"] == "镇江默勒电器有限公司"
    assert extraction.fields["公司英文名"] == "Zhenjiang Klockner-Moeller"
    assert extraction.fields["合同号"] == "A17387"
    assert extraction.fields["版本号"] == ""
    assert extraction.fields["图纸名称"] == "双电源进线"
    assert extraction.fields["总页数"] == "2"
    assert extraction.fields["原理图号"] == "CDDT-6-DZ-.01"
    assert extraction.fields["当前页"] == "1"


def test_extract_title_block_keeps_multiline_project_name() -> None:
    words = [
        TextWord("客户名称", 180, 40, 220, 54),
        TextWord("工程名称", 180, 70, 220, 84),
        TextWord("上海核工程研究设计院股份有限公司（广东廉", 250, 61, 455, 75),
        TextWord("江核电项目一期工程循环水泵房、海水取水泵", 250, 77, 465, 91),
        TextWord("系统名称", 180, 102, 220, 116),
        TextWord("Z", 515, 56, 524, 70),
        TextWord("M", 515, 73, 524, 87),
        TextWord("镇江默勒电器有限公司", 565, 58, 700, 78),
        TextWord("Zhenjiang", 565, 83, 625, 97),
        TextWord("Klockner-Moeller", 630, 83, 735, 97),
        TextWord("合同号", 780, 40, 820, 54),
        TextWord("A18523/0406", 875, 40, 935, 54),
        TextWord("版本号", 780, 70, 820, 84),
        TextWord("图纸名称", 780, 100, 820, 114),
        TextWord("馈电", 900, 100, 925, 114),
        TextWord("共", 950, 100, 960, 114),
        TextWord("页", 1000, 100, 1010, 114),
        TextWord("原理图号", 780, 130, 820, 144),
        TextWord("MCLE104-G", 875, 130, 925, 144),
        TextWord("第", 950, 130, 960, 144),
        TextWord("页", 1000, 130, 1010, 144),
        TextWord("序号代号元件名称规格型号", 550, 190, 720, 204),
    ]

    extraction = extract_title_block_from_words(
        words,
        page_number=1,
        page_width=1100,
        page_height=220,
    )

    assert extraction.fields["工程名称"] == (
        "上海核工程研究设计院股份有限公司（广东廉"
        "江核电项目一期工程循环水泵房、海水取水泵"
    )
    assert extraction.fields["公司名称"] == "镇江默勒电器有限公司"
    assert extraction.fields["公司英文名"] == "Zhenjiang Klockner-Moeller"
    assert extraction.fields["合同号"] == "A18523/0406"
    assert extraction.fields["图纸名称"] == "馈电"
    assert extraction.fields["原理图号"] == "MCLE104-G"
    assert extraction.fields["总页数"] == ""
    assert extraction.fields["当前页"] == ""
