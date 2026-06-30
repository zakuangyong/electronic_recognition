from __future__ import annotations

from electronic_recognition import api


def test_result_id_strips_extension() -> None:
    assert api._result_id_for_filename("A17387_1706_项目原理图_24-3.pdf") == "A17387_1706_项目原理图_24-3"


def test_result_id_keeps_inner_dots_but_strips_last_suffix() -> None:
    assert api._result_id_for_filename("archive.v1.tar.gz") == "archive.v1.tar"

