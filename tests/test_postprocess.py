"""postprocess：外部答案 + Passage → Cited Answer（這一階段只處理單一 `[n]`）。"""

import pytest

from showreceipts import DEFAULT_NO_ANSWER_REPLY, Passage, ShowReceiptsConfig, postprocess


def _passages(*ids: str) -> list[Passage]:
    return [Passage(id=pid, text=f"text of {pid}", source="doc.md") for pid in ids]


def test_postprocess_markers_renumbered_by_first_appearance() -> None:
    p1, p2, p3 = _passages("p1", "p2", "p3")

    cited = postprocess("甲 [3]，乙 [1]，丙 [3]。", [p1, p2, p3])

    assert cited.answer == "甲 [1]，乙 [2]，丙 [1]。"
    assert [(c.n, c.passage.id) for c in cited.citations] == [(1, "p3"), (2, "p1")]
    assert cited.passages == [p1, p2, p3]
    assert cited.raw_answer == "甲 [3]，乙 [1]，丙 [3]。"
    assert cited.fabricated_markers == []
    assert cited.quality_report is None


def test_postprocess_unmatched_markers_removed_and_recorded_once() -> None:
    passages = _passages("p1", "p2")

    cited = postprocess("甲[9]乙[2]丙[0]丁[9]戊[1]", passages)

    assert cited.answer == "甲乙[1]丙丁戊[2]"
    assert [c.passage.id for c in cited.citations] == ["p2", "p1"]
    assert cited.fabricated_markers == ["[9]", "[0]"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("甲 [9]。", "甲。"),
        ("甲 [9]，乙", "甲，乙"),
        ("甲 [1] [9])", "甲 [1])"),
        ("甲 [9] 乙", "甲 乙"),
        ("甲\t[9] 乙", "甲\t乙"),
        ("甲 [9][8] 乙", "甲 乙"),
        ("甲 [8] [9]！", "甲！"),
        ("甲  乙 [9] 丙 ，丁", "甲  乙 丙 ，丁"),
        ("    code  x\n甲 [9]。", "    code  x\n甲。"),
        ("甲 [9]\n乙", "甲 \n乙"),
        ("甲　[9]　乙", "甲　　乙"),
    ],
)
def test_postprocess_whitespace_cleaned_only_at_deletion(raw: str, expected: str) -> None:
    assert postprocess(raw, _passages("p1")).answer == expected


def test_postprocess_duplicate_ids_map_by_position_to_first_occurrence() -> None:
    a = Passage(id="A", text="first A", source="doc.md")
    b = Passage(id="B", text="B", source="doc.md")
    a_again = Passage(id="A", text="second A", source="other.md")

    cited = postprocess("x [3] y [2] z [1]。", [a, b, a_again])

    assert cited.answer == "x [1] y [2] z [1]。"
    assert [(c.n, c.passage) for c in cited.citations] == [(1, a), (2, b)]
    assert cited.passages == [a, b]


def test_postprocess_zero_marker_base_points_zero_at_first_passage() -> None:
    passages = _passages("p1", "p2")

    cited = postprocess("甲 [1] 乙 [0] 丙 [2]。", passages, config=ShowReceiptsConfig(input_marker_base=0))

    assert cited.answer == "甲 [1] 乙 [2] 丙。"
    assert [c.passage.id for c in cited.citations] == ["p2", "p1"]
    assert cited.fabricated_markers == ["[2]"]


def test_postprocess_no_passages_returns_no_answer_reply_keeping_raw() -> None:
    cited = postprocess("甲 [1]。", [])

    assert cited.model_dump(mode="json") == {
        "answer": DEFAULT_NO_ANSWER_REPLY,
        "raw_answer": "甲 [1]。",
        "citations": [],
        "passages": [],
        "fabricated_markers": [],
        "quality_report": None,
    }


def test_postprocess_no_passages_custom_reply_used() -> None:
    cited = postprocess("甲", [], config=ShowReceiptsConfig(no_answer_reply="查無資料"))

    assert cited.answer == "查無資料"


def test_postprocess_only_fabricated_markers_returns_empty_string() -> None:
    cited = postprocess(" [9] \t[8]  ", _passages("p1"))

    assert cited.answer == ""
    assert cited.passages == _passages("p1")
    assert cited.fabricated_markers == ["[9]", "[8]"]


def test_postprocess_non_passage_element_raises_type_error_naming_index() -> None:
    with pytest.raises(TypeError, match=r"passages\[0\]"):
        postprocess("甲 [1]", [{"id": "a", "text": "t", "source": "s"}])
