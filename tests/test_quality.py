"""Quality Report：經 postprocess／answer 觀察，不直接呼叫 quality 模組。"""

import json
import logging
import time
from pathlib import Path

import pytest

from showreceipts import (
    EntityFlag,
    EntityKind,
    Passage,
    QualityReport,
    SentenceSupport,
    ShowReceiptsConfig,
    UncitedSentence,
    answer,
    postprocess,
)

GOLDEN = Path(__file__).parent / "fixtures" / "golden"

FEE = Passage(id="fee", text="年費 4,500 元。", source="doc.md")
REWARD = Passage(id="reward", text="回饋 0.3%。", source="doc.md")


def _passage(pid: str, text: str) -> Passage:
    return Passage(id=pid, text=text, source="doc.md")


def _fully_supported(sentence: str, passage: Passage) -> SentenceSupport:
    return SentenceSupport(sentence=sentence, supported=True, best_match_passage_id=passage.id, overlap_score=1.0)


def test_quality_empty_answer_on_by_default_scores_one() -> None:
    cited = postprocess("", [_passage("a", "年費 4,500 元")])

    assert cited.quality_report == QualityReport(quality_score=1.0)


def test_quality_disabled_returns_none_and_same_answer() -> None:
    passages = [_passage("a", "年費 4,500 元"), _passage("b", "回饋 0.3%")]
    raw = "年費 4,500 元 [2][9]。回饋 0.3% [1]。"

    enabled = postprocess(raw, passages)
    disabled = postprocess(raw, passages, config=ShowReceiptsConfig(enable_quality_report=False))

    assert disabled.quality_report is None
    assert enabled.quality_report is not None
    assert disabled == enabled.model_copy(update={"quality_report": None})


def test_quality_no_answer_reply_has_no_report(fake_generator) -> None:
    assert postprocess("年費 4,500 元 [1]。", []).quality_report is None
    assert answer("年費？", [], fake_generator).quality_report is None


def test_quality_golden_cited_answer_reproduced(fake_generator) -> None:
    golden = json.loads((GOLDEN / "cited_answer.json").read_text(encoding="utf-8"))
    passages = [Passage.model_validate(p) for p in golden["passages"]]
    fake_generator.reply = golden["raw_answer"]

    via_postprocess = postprocess(golden["raw_answer"], passages)
    via_answer = answer("Richart 卡的回饋是多少？", passages, fake_generator)

    assert via_postprocess.model_dump(mode="json") == golden
    assert via_answer == via_postprocess
    expected_report = json.loads((GOLDEN / "quality_report_uncited.json").read_text(encoding="utf-8"))
    assert via_postprocess.quality_report.model_dump(mode="json") == expected_report


def test_quality_worked_example_low_overlap_and_missing_number_flagged() -> None:
    passages = [_passage("a", "台新銀行 2024 年發卡 300 萬張。")]

    cited = postprocess("台新銀行 2024 年發卡 300 萬張 [1]。同年營收達 100 億元 [1]。", passages)

    # 句 0 去掉 marker 後 20 個 3-gram 有 18 個在 Passage 裡；句 1 的 12 個只有「00 」在。
    assert cited.quality_report == QualityReport(
        quality_score=0.5,
        sentence_supports=[
            SentenceSupport(
                sentence="台新銀行 2024 年發卡 300 萬張 [1]。",
                supported=True,
                best_match_passage_id="a",
                overlap_score=0.9,
            ),
            SentenceSupport(sentence="同年營收達 100 億元 [1]。", supported=False, overlap_score=0.0833),
        ],
        unsupported_entities=[EntityFlag(entity="100 億", kind=EntityKind.NUM, reason="not found in any passage text")],
    )


def test_quality_entities_num_before_date_each_in_order_of_appearance() -> None:
    passages = [_passage("a", "申辦說明")]
    raw = "2025-01-02 起 [1]，3 月 5 日前申辦回饋 5% [1]，2026 年 Q1 2027 加碼 1.5 萬 [1]，民國115年1月1日截止 [1]，5% 不變。"

    cited = postprocess(raw, passages)

    assert [(e.entity, e.kind) for e in cited.quality_report.unsupported_entities] == [
        ("5%", EntityKind.NUM),
        ("1.5 萬", EntityKind.NUM),
        ("2025-01-02", EntityKind.DATE),
        ("3 月 5 日", EntityKind.DATE),
        ("2026 年", EntityKind.DATE),
        ("Q1 2027", EntityKind.DATE),
        ("民國115年1月1日", EntityKind.DATE),
    ]


def test_quality_num_entity_with_thousands_separator_kept_whole() -> None:
    passages = [_passage("a", "信用額度上限 2,500萬，年費 4,500 元。")]

    cited = postprocess("額度 1,500萬 [1]，另一張 2,500萬 [1]，年費 4,500 元 [1]。", passages)

    assert [e.entity for e in cited.quality_report.unsupported_entities] == ["1,500萬"]


def test_quality_entity_found_in_any_passage_not_flagged() -> None:
    passages = [_passage("a", "年費說明"), _passage("b", "民國115年起回饋 3.8%")]

    cited = postprocess("回饋 3.8% [1]，民國115年起適用 [1]。", passages)

    assert cited.quality_report.unsupported_entities == []


@pytest.mark.parametrize(("passage_text", "supported", "score"), [("abcde", True, 0.15), ("abcd", False, 0.1)])
def test_quality_overlap_threshold_inclusive_at_015(passage_text: str, supported: bool, score: float) -> None:
    # 去掉 marker 後 22 個字元、20 個 3-gram；"abcde" 含其中 3 個，"abcd" 含 2 個。
    report = postprocess("abcdefghijklmnopqrstuv [1]", [_passage("a", passage_text)]).quality_report

    assert report.sentence_supports == [
        SentenceSupport(
            sentence="abcdefghijklmnopqrstuv [1]",
            supported=supported,
            best_match_passage_id="a" if supported else None,
            overlap_score=score,
        )
    ]
    assert report.quality_score == (1.0 if supported else 0.0)


@pytest.mark.parametrize(
    ("raw", "sentences"),
    [
        ("年費 4,500 元。[1] 回饋 0.3%。[2]", ["年費 4,500 元。[1]", "回饋 0.3%。[2]"]),
        ("年費 4,500 元。 [1][2]\t回饋 0.3%。[2]", ["年費 4,500 元。 [1][2]", "回饋 0.3%。[2]"]),
        ("年費 4,500 元。\n[1]\n回饋 0.3%。\n\n[2] [1]", ["年費 4,500 元。\n[1]", "回饋 0.3%。\n\n[2] [1]"]),
        ("[1] 年費 4,500 元。\n[2] 回饋 0.3%。", ["[1] 年費 4,500 元。", "[2] 回饋 0.3%。"]),
    ],
)
def test_quality_marker_at_sentence_start_merged_into_previous_sentence(raw: str, sentences: list[str]) -> None:
    report = postprocess(raw, [FEE, REWARD]).quality_report

    assert report.model_dump()["sentence_supports"] == [
        _fully_supported(sentences[0], FEE).model_dump(),
        _fully_supported(sentences[1], REWARD).model_dump(),
    ]
    assert report.uncited_sentences == []
    assert report.quality_score == 1.0


def test_quality_lone_enumerator_merged_into_next_sentence() -> None:
    report = postprocess("2. 注意事項\n2. 年費 4,500 元", [FEE]).quality_report

    assert [s.sentence for s in report.sentence_supports] == ["2. 注意事項", "2. 年費 4,500 元"]
    assert report.uncited_sentences == [
        UncitedSentence(sentence="2. 年費 4,500 元", sentence_index=1, numbers=["4,500"])
    ]


@pytest.mark.parametrize(
    ("sentence", "numbers"),
    [
        ("一般消費回饋為 0.3%。", ["0.3"]),
        ("1.年費 4,500 元。", ["4,500"]),
        ("（1）年費 NT$4,500。", ["4,500"]),
        ("3、年費 4,500 元", ["4,500"]),
        ("- 年費 4,500 元", ["4,500"]),
        ("3.8% 回饋。", ["3.8"]),
        ("方案 (2) 年費 4,500 元。", ["2", "4,500"]),
        ("年費４，５００元。", ["４", "５００"]),
        ("Q1：年費多少", ["1"]),
        ("`list[1]` 有 3 個元素。", ["1", "3"]),
        ("(1) 假日刷：", None),
        ("依現有資料無法回答。", None),
        ("年費 4,500 元 [1]。", None),
    ],
)
def test_quality_uncited_sentence_numbers_after_enumerator(sentence: str, numbers: list[str] | None) -> None:
    report = postprocess(sentence, [FEE]).quality_report

    expected = [UncitedSentence(sentence=sentence, sentence_index=0, numbers=numbers)] if numbers else []
    assert report.uncited_sentences == expected


def test_quality_build_failure_logs_warning_and_answer_still_returned(caplog: pytest.LogCaptureFixture) -> None:
    # 跳過驗證建出的 Passage（text=None）讓報告建構失敗；答案與引用不受影響。
    broken = Passage.model_construct(id="a", text=None, source="doc.md", locator="", score=None, metadata={})

    with caplog.at_level(logging.WARNING, logger="showreceipts"):
        cited = postprocess("年費 4,500 元 [1][9]。", [broken])

    assert cited.quality_report is None
    assert cited.answer == "年費 4,500 元 [1]。"
    assert [c.passage.id for c in cited.citations] == ["a"]
    assert cited.fabricated_markers == ["[9]"]
    assert [r.levelno for r in caplog.records] == [logging.WARNING]


def test_quality_sentences_are_verbatim_and_found_in_order() -> None:
    raw = "```py\nx = a[1]\n```\n1. 年費 4,500 元。[1] 回饋 0.3% [2][7]。\n2. 詳見 https://x.com/a[2] 共 2 頁。\n[1]"

    cited = postprocess(raw, [FEE, REWARD])

    pos = 0
    for support in cited.quality_report.sentence_supports:
        pos = cited.answer.index(support.sentence, pos) + len(support.sentence)
    assert cited.answer[pos:] == ""
    for uncited in cited.quality_report.uncited_sentences:
        assert cited.quality_report.sentence_supports[uncited.sentence_index].sentence == uncited.sentence


def _long_input() -> tuple[str, list[Passage]]:
    passages = [
        _passage(f"p{i}", (f"第 {i} 段：年費 4,500 元，回饋 {i}.5%，2024 年 3 月 1 日起適用。" * 10)[:300])
        for i in range(5)
    ]
    paragraph = "".join(f"第 {i} 段說明年費 4,500 元 [{i + 1}]，回饋 {i}.5% 與 100 億 [{i + 1}][9]。" for i in range(5))
    return "\n\n".join([(paragraph * 3)[:300]] * 5), passages


def test_quality_repeated_runs_identical() -> None:
    raw, passages = _long_input()

    dumps = [postprocess(raw, passages).model_dump(mode="json") for _ in range(5)]

    assert dumps[0]["quality_report"]["sentence_supports"]
    assert all(d == dumps[0] for d in dumps)


def test_quality_five_paragraphs_of_300_chars_under_500ms() -> None:
    raw, passages = _long_input()

    started = time.perf_counter()
    cited = postprocess(raw, passages)
    elapsed = time.perf_counter() - started

    assert cited.quality_report is not None
    assert elapsed < 0.5
