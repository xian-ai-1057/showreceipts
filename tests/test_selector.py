"""select：總字數沒超過預算就原樣回傳；超過時以字元 bigram BM25 挑段，回傳時恢復原本順序。"""

import pytest

from showreceipts import Passage, select

FEE = Passage(id="fee", text="年費每年新臺幣四千五百元整。", source="richart.md")
INSURANCE = Passage(id="insurance", text="保費一次付清可享回饋。", source="richart.md")
HOLIDAY = Passage(id="holiday", text="假日刷不限通路可享回饋。", source="richart.md")
SWITCH = Passage(id="switch", text="保費回饋：切換假日刷最高。", source="richart.md")


def _passage(pid: str, text: str) -> Passage:
    return Passage(id=pid, text=text, source="richart.md")


def test_select_within_budget_returns_passages_unchanged() -> None:
    passages = [_passage("b", "年費每年 NT$4,500。"), _passage("a", "保費享 1.3% 回饋。"), _passage("b", "重複的 ID。")]

    selected = select("保費回饋多少？", passages, sum(len(p.text) for p in passages))

    assert selected == passages


def test_select_over_budget_keeps_most_relevant_in_original_order() -> None:
    passages = [FEE, INSURANCE, HOLIDAY, SWITCH]

    selected = select("保費回饋多少？", passages, len(INSURANCE.text) + len(SWITCH.text))

    assert selected == [INSURANCE, SWITCH]


def test_select_skips_passage_too_long_for_budget_and_tries_next() -> None:
    long_switch = SWITCH.model_copy(update={"text": SWITCH.text * 4})
    passages = [FEE, INSURANCE, HOLIDAY, long_switch]

    selected = select("保費回饋多少？", passages, 24)

    assert selected == [INSURANCE, HOLIDAY]


def test_select_equal_scores_keep_earlier_passage_every_time() -> None:
    twins = [_passage(f"p{i}", "切換假日刷可享回饋。") for i in range(4)]

    results = [select("假日刷回饋", twins, len(twins[0].text) * 2) for _ in range(3)]

    assert results == [twins[:2]] * 3


FIRST = _passage("a", "年費四千五。")
OTHER = _passage("b", "保費回饋說明。")
LATER_DUPLICATE = _passage("a", "保費回饋保費回饋。")


def test_select_duplicate_id_counted_once_toward_budget_returns_passages_unchanged() -> None:
    passages = [FIRST, OTHER, LATER_DUPLICATE]

    assert select("保費回饋", passages, len(FIRST.text) + len(OTHER.text)) == passages


def test_select_over_budget_only_first_occurrence_of_duplicate_id_competes() -> None:
    selected = select("保費回饋", [FIRST, OTHER, LATER_DUPLICATE], len(OTHER.text))

    assert selected == [OTHER]


def test_select_over_budget_keeps_later_duplicates_of_chosen_id_like_unchanged_path() -> None:
    selected = select("年費", [FIRST, OTHER, LATER_DUPLICATE], len(FIRST.text))

    assert selected == [FIRST, LATER_DUPLICATE]


def test_select_negative_budget_raises() -> None:
    with pytest.raises(ValueError, match="budget"):
        select("保費", [FEE], -1)
