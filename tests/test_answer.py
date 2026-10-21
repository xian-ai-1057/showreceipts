"""answer：問題 + Passage + Generator → Cited Answer；prompt 經假 Generator 觀察。"""

import json
from pathlib import Path

import pytest

from showreceipts import Passage, ShowReceiptsConfig, answer, postprocess

GOLDEN = Path(__file__).parent / "fixtures" / "golden"


def test_answer_same_raw_answer_matches_postprocess(fake_generator) -> None:
    golden = json.loads((GOLDEN / "cited_answer.json").read_text(encoding="utf-8"))
    passages = [Passage.model_validate(p) for p in golden["passages"]]
    fake_generator.reply = golden["raw_answer"]

    cited = answer("Richart 卡的回饋是多少？", passages, fake_generator)

    assert cited == postprocess(golden["raw_answer"], passages)
    assert cited.raw_answer == golden["raw_answer"]
    assert len(fake_generator.calls) == 1


DEFAULT_SYSTEM_PROMPT = """你是一個嚴謹的問答助理。你會收到使用者問題與多段【參考資料】，每段以 [n] 編號標示。

【作答規則】
1. 只能使用提供的參考資料；不得編造資訊。
2. 每段論述結尾必須標註來源編號，例如 [1] 或 [2][3]。
3. 若同一句話綜合多段資料，依重要性排序列出所有編號。
4. 若參考資料不足以回答問題，明確說「依現有資料無法回答」並指出缺什麼。
5. 使用繁體中文回答。
6. 不要在回答尾端加入「參考資料」、「來源清單」等清單 — 介面下方會另行顯示。"""


def test_answer_default_prompts_number_blocks_and_omit_empty_locator(fake_generator) -> None:
    passages = [
        Passage(id="a", text="年費 4,500 元", source="richart.md", locator="三、年費"),
        Passage(id="b", text="回饋 0.3%", source="notes.txt"),
    ]

    answer("年費多少？", passages, fake_generator)

    system, user = fake_generator.calls[0]
    assert system == DEFAULT_SYSTEM_PROMPT
    assert user == (
        "【參考資料】\n"
        "[1] 來源: richart.md（三、年費）\n年費 4,500 元\n"
        "\n"
        "[2] 來源: notes.txt\n回饋 0.3%\n"
        "\n\n"
        "【使用者問題】\n年費多少？\n\n【回答】"
    )


def test_answer_language_only_changes_answer_language_rule(fake_generator) -> None:
    answer("q", [Passage(id="a", text="t", source="s")], fake_generator, config=ShowReceiptsConfig(language="English"))

    system, _ = fake_generator.calls[0]
    assert system == DEFAULT_SYSTEM_PROMPT.replace("5. 使用繁體中文回答。", "5. 使用English回答。")


def test_answer_numbers_passages_in_given_order_after_dedupe_ignoring_score(fake_generator) -> None:
    passages = [
        Passage(id="low", text="first", source="s", score=0.1),
        Passage(id="high", text="second", source="s", score=0.9),
        Passage(id="low", text="duplicate", source="other", score=1.0),
    ]
    fake_generator.reply = "甲 [2]，乙 [1]。"

    cited = answer("q", passages, fake_generator)

    _, user = fake_generator.calls[0]
    assert "[1] 來源: s\nfirst\n" in user
    assert "[2] 來源: s\nsecond\n" in user
    assert "duplicate" not in user
    assert [p.id for p in cited.passages] == ["low", "high"]
    assert [(c.n, c.passage.id) for c in cited.citations] == [(1, "high"), (2, "low")]
    assert cited.answer == "甲 [1]，乙 [2]。"


def test_answer_duplicate_id_dropped_from_prompt_without_numbering_gap(fake_generator) -> None:
    passages = [
        Passage(id="x", text="one", source="s"),
        Passage(id="x", text="dup", source="s"),
        Passage(id="y", text="two", source="s"),
    ]

    answer("q", passages, fake_generator)

    _, user = fake_generator.calls[0]
    assert "[1] 來源: s\none\n" in user
    assert "[2] 來源: s\ntwo\n" in user
    assert "dup" not in user
    assert "[3]" not in user


def test_answer_no_passages_returns_no_answer_reply_without_calling_generator(fake_generator) -> None:
    golden = json.loads((GOLDEN / "cited_answer_no_answer.json").read_text(encoding="utf-8"))

    cited = answer("q", [], fake_generator)

    assert fake_generator.calls == []
    assert cited.model_dump(mode="json") == golden


def test_answer_ignores_input_marker_base_zero() -> None:
    a, b = Passage(id="a", text="ta", source="s"), Passage(id="b", text="tb", source="s")
    config = ShowReceiptsConfig(input_marker_base=0)

    cited = answer("q", [a, b], lambda system, user: "x [1] y [0] z [2]", config=config)

    assert cited.answer == "x [1] y z [2]"
    assert [c.passage.id for c in cited.citations] == ["a", "b"]
    assert cited.fabricated_markers == ["[0]"]


def test_answer_no_passages_custom_no_answer_reply_used(fake_generator) -> None:
    cited = answer("q", [], fake_generator, config=ShowReceiptsConfig(no_answer_reply="無資料"))

    assert cited.answer == "無資料"
    assert cited.raw_answer == ""
    assert fake_generator.calls == []


def test_answer_non_str_generator_reply_raises_type_error() -> None:
    with pytest.raises(TypeError):
        answer("q", [Passage(id="a", text="t", source="s")], lambda system, user: None)


@pytest.mark.parametrize("passages", [[], [Passage(id="a", text="t", source="s")]])
def test_answer_non_callable_generator_raises_type_error(passages: list[Passage]) -> None:
    with pytest.raises(TypeError):
        answer("q", passages, "not a generator")


@pytest.mark.parametrize("element", [{"id": "a", "text": "t", "source": "s"}, "just a string", None])
def test_answer_non_passage_element_raises_type_error_naming_index(fake_generator, element) -> None:
    with pytest.raises(TypeError, match=r"passages\[1\]"):
        answer("q", [Passage(id="a", text="t", source="s"), element], fake_generator)

    assert fake_generator.calls == []


def test_answer_generator_exception_propagates_unchanged() -> None:
    error = ConnectionResetError("boom")
    calls = []

    def failing(system: str, user: str) -> str:
        calls.append(1)
        raise error

    with pytest.raises(ConnectionResetError) as excinfo:
        answer("q", [Passage(id="a", text="t", source="s")], failing)

    assert excinfo.value is error
    assert calls == [1]


def test_answer_overridden_templates_substitute_once_and_keep_other_braces(fake_generator) -> None:
    config = ShowReceiptsConfig(
        system_prompt="Answer in {language}.",
        language="English",
        user_prompt_template='{"format": "json"}\nQ: {question}\n{context_blocks}',
        passage_block_template="<{n}|{source}|{locator}> {text}",
    )
    passages = [
        Passage(id="a", text="mentions {question} and {n}", source="a.md", locator="p1"),
        Passage(id="b", text="plain", source="b.md"),
    ]

    answer("what is {context_blocks}?", passages, fake_generator, config=config)

    system, user = fake_generator.calls[0]
    assert system == "Answer in {language}."
    assert user == (
        '{"format": "json"}\n'
        "Q: what is {context_blocks}?\n"
        "<1|a.md|p1> mentions {question} and {n}\n"
        "<2|b.md|> plain"
    )


def test_answer_templates_missing_placeholders_warn_without_raising(fake_generator, caplog) -> None:
    config = ShowReceiptsConfig(user_prompt_template="no placeholders", passage_block_template="")

    with caplog.at_level("WARNING", logger="showreceipts"):
        answer("q", [Passage(id="a", text="t", source="s")], fake_generator, config=config)

    assert fake_generator.calls[0][1] == "no placeholders"
    warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    for placeholder in ("{context_blocks}", "{question}", "{n}", "{text}"):
        assert any(placeholder in message for message in warnings)
