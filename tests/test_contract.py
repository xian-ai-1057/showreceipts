"""資料模型契約：golden fixture、JSON 往返、CitedAnswer 不變式與設定驗證。"""

import json
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from showreceipts import (
    Citation,
    CitedAnswer,
    Passage,
    QualityReport,
    SentenceSupport,
    ShowReceiptsConfig,
    UncitedSentence,
)

GOLDEN = Path(__file__).parent / "fixtures" / "golden"


def _load(name: str) -> dict:
    return json.loads((GOLDEN / name).read_text(encoding="utf-8"))


def _passage(pid: str) -> Passage:
    return Passage(id=pid, text=f"text of {pid}", source="doc.md")


@pytest.mark.parametrize(
    ("fixture", "model"),
    [
        ("passage_arrkb.json", Passage),
        ("cited_answer.json", CitedAnswer),
        ("cited_answer_no_answer.json", CitedAnswer),
        ("quality_report_uncited.json", QualityReport),
        ("config_default.json", ShowReceiptsConfig),
    ],
)
def test_contract_golden_fixture_validates_and_round_trips(fixture: str, model: type[BaseModel]) -> None:
    data = _load(fixture)
    parsed = model.model_validate(data)
    assert parsed.model_dump(mode="json") == data
    assert model.model_validate_json(parsed.model_dump_json()) == parsed


def test_config_defaults_match_golden_fixture() -> None:
    assert ShowReceiptsConfig().model_dump(mode="json") == _load("config_default.json")


def test_passage_optional_fields_default_to_empty() -> None:
    p = Passage(id="p1", text="t", source="s")
    assert (p.locator, p.score, p.metadata) == ("", None, {})


@pytest.mark.parametrize(
    "kwargs",
    [
        {"id": "", "text": "t", "source": "s"},
        {"id": "p1", "text": "t", "source": "s", "unknown": 1},
        {"text": "t", "source": "s"},
    ],
)
def test_passage_invalid_input_rejected(kwargs: dict) -> None:
    with pytest.raises(ValidationError):
        Passage(**kwargs)


def test_cited_answer_valid_citations_accepted() -> None:
    a, b = _passage("a"), _passage("b")
    cited = CitedAnswer(
        answer="x [1][2]",
        raw_answer="x [2][1]",
        citations=[Citation(n=1, passage=b), Citation(n=2, passage=a)],
        passages=[a, b],
    )
    assert [c.passage.id for c in cited.citations] == ["b", "a"]


def test_cited_answer_non_contiguous_n_rejected() -> None:
    a, b = _passage("a"), _passage("b")
    with pytest.raises(ValidationError, match="1..2 in order"):
        CitedAnswer(
            answer="",
            raw_answer="",
            citations=[Citation(n=1, passage=a), Citation(n=3, passage=b)],
            passages=[a, b],
        )


def test_cited_answer_out_of_order_n_rejected() -> None:
    a, b = _passage("a"), _passage("b")
    with pytest.raises(ValidationError, match="1..2 in order"):
        CitedAnswer(
            answer="",
            raw_answer="",
            citations=[Citation(n=2, passage=a), Citation(n=1, passage=b)],
            passages=[a, b],
        )


def test_cited_answer_duplicate_passage_ids_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        CitedAnswer(answer="", raw_answer="", passages=[_passage("a"), _passage("a")])


def test_cited_answer_passage_cited_twice_rejected() -> None:
    a = _passage("a")
    with pytest.raises(ValidationError, match="at most once"):
        CitedAnswer(
            answer="",
            raw_answer="",
            citations=[Citation(n=1, passage=a), Citation(n=2, passage=a)],
            passages=[a],
        )


def test_cited_answer_citation_outside_passages_rejected() -> None:
    with pytest.raises(ValidationError, match="not in passages"):
        CitedAnswer(
            answer="",
            raw_answer="",
            citations=[Citation(n=1, passage=_passage("ghost"))],
            passages=[_passage("a")],
        )


@pytest.mark.parametrize(
    "build",
    [
        lambda: Citation(n=0, passage=_passage("a")),
        lambda: SentenceSupport(sentence="s", supported=True, overlap_score=1.5),
        lambda: UncitedSentence(sentence="s", sentence_index=0, numbers=[]),
        lambda: UncitedSentence(sentence="s", sentence_index=-1, numbers=["1"]),
        lambda: QualityReport(quality_score=1.1),
    ],
)
def test_quality_and_citation_out_of_range_values_rejected(build) -> None:
    with pytest.raises(ValidationError):
        build()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"input_marker_base": 2},
        {"language": ""},
        {"no_answer_reply": ""},
        {"unknown": True},
    ],
)
def test_config_invalid_values_rejected(kwargs: dict) -> None:
    with pytest.raises(ValidationError):
        ShowReceiptsConfig(**kwargs)


def test_config_is_frozen() -> None:
    config = ShowReceiptsConfig()
    with pytest.raises(ValidationError):
        config.language = "English"


def test_config_template_without_placeholders_accepted() -> None:
    config = ShowReceiptsConfig(user_prompt_template="no placeholders", passage_block_template="")
    assert config.user_prompt_template == "no placeholders"
