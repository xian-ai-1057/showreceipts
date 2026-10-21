"""Adapters：arrkb 結果與 LangChain 文件物件 → Passage。"""

import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document

from showreceipts.adapters import from_arrkb, from_langchain

ROOT = Path(__file__).parent.parent
SAMPLE = json.loads((ROOT / "data" / "sample_reranked.json").read_text(encoding="utf-8"))
GOLDEN_PASSAGE = json.loads((ROOT / "tests" / "fixtures" / "golden" / "passage_arrkb.json").read_text(encoding="utf-8"))


def _record(context_id: str, *, score: float | None = None, **fields: object) -> dict[str, object]:
    record: dict[str, object] = {"context_id": context_id, "content": f"text of {context_id}", "filename": "doc.md"}
    if score is not None:
        record["kwargs"] = {"relevance_score": score}
    return record | fields


def test_adapters_arrkb_sample_first_item_matches_golden_passage() -> None:
    passages = from_arrkb(SAMPLE)

    assert passages[0].model_dump(mode="json") == GOLDEN_PASSAGE


def test_adapters_arrkb_envelope_list_and_single_record_accepted() -> None:
    records = SAMPLE["data"]

    from_envelope = from_arrkb(SAMPLE)
    from_list = from_arrkb(records)
    from_single = from_arrkb(records[2])

    assert from_list == from_envelope
    assert from_single == [from_envelope[2]]


def test_adapters_arrkb_order_kept_not_sorted_by_score() -> None:
    records = [_record("low", score=0.1), _record("high", score=0.9), _record("mid", score=0.5)]

    passages = from_arrkb(records)

    assert [p.id for p in passages] == ["low", "high", "mid"]
    assert [p.score for p in passages] == [0.1, 0.9, 0.5]


@pytest.mark.parametrize("key", ["context_id", "content"])
def test_adapters_arrkb_missing_required_field_raises_value_error(key: str) -> None:
    broken = _record("b")
    del broken[key]

    with pytest.raises(ValueError, match=f"arrkb item 1: missing '{key}'"):
        from_arrkb([_record("a"), broken])


def test_adapters_arrkb_optional_fields_missing_fall_back() -> None:
    passage = from_arrkb({"context_id": 42, "content": "內文", "kb_name": "kb", "rerank": {"rank": 3}})[0]

    assert passage.model_dump(mode="json") == {
        "id": "42",
        "text": "內文",
        "source": "?",
        "locator": "",
        "score": None,
        "metadata": {"kb_name": "kb", "rerank": {"rank": 3}},
    }


@pytest.mark.parametrize(
    ("page", "locator"),
    [("1", "第 1 頁"), (" 7 ", "第 7 頁"), (0, "第 0 頁"), ("", ""), ("  ", ""), (None, "")],
)
def test_adapters_arrkb_page_becomes_locator(page: object, locator: str) -> None:
    passage = from_arrkb(_record("a", page=page))[0]

    assert passage.locator == locator
    assert passage.metadata["page"] == page


def test_adapters_langchain_duck_typed_object_converted() -> None:
    doc = SimpleNamespace(id="d1", page_content="年費 NT$4,500", metadata={"source": "card.pdf", "page": 2, "x": 1})

    passages = from_langchain([doc])

    assert [p.model_dump(mode="json") for p in passages] == [
        {
            "id": "d1",
            "text": "年費 NT$4,500",
            "source": "card.pdf",
            "locator": "第 2 頁",
            "score": None,
            "metadata": {"source": "card.pdf", "page": 2, "x": 1},
        }
    ]


def test_adapters_langchain_id_and_source_keys_read_from_metadata() -> None:
    doc = SimpleNamespace(page_content="內文", metadata={"context_id": 465150, "filename": "a.docx", "source": "x"})

    passage = from_langchain([doc], id_key="context_id", source_key="filename")[0]

    assert (passage.id, passage.source) == ("465150", "a.docx")


def test_adapters_langchain_object_id_wins_over_metadata_id() -> None:
    doc = SimpleNamespace(id="obj", page_content="內文", metadata={"id": "meta"})

    assert from_langchain([doc])[0].id == "obj"


def test_adapters_langchain_missing_id_hashes_source_and_text_with_one_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    docs = [
        SimpleNamespace(page_content="年費 NT$4,500", metadata={"source": "card.pdf"}),
        SimpleNamespace(id="keep", page_content="內文", metadata={}),
        SimpleNamespace(id="", page_content="回饋 0.3%", metadata={"id": None}),
    ]

    first = from_langchain(docs)
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="showreceipts.adapters"):
        again = from_langchain(docs)

    assert [p.id for p in first] == ["6133e8a81912", "keep", "87cc927e9c86"]
    assert again == first
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "[0, 2]" in warnings[0].getMessage()


def test_adapters_langchain_locator_fn_overrides_page_locator() -> None:
    doc = SimpleNamespace(id="d1", page_content="內文", metadata={"page": 0, "section": "三、年費"})

    passage = from_langchain([doc], locator_fn=lambda m: f"第 {m['page'] + 1} 頁 · {m['section']}")[0]

    assert passage.locator == "第 1 頁 · 三、年費"


def test_adapters_langchain_score_pairs_set_score_and_keep_order() -> None:
    low = SimpleNamespace(id="low", page_content="a", metadata={})
    high = SimpleNamespace(id="high", page_content="b", metadata={})

    passages = from_langchain([(low, 0.25), [high, 0.75]])

    assert [(p.id, p.score) for p in passages] == [("low", 0.25), ("high", 0.75)]


@pytest.mark.parametrize(
    "bad",
    [
        "年費 NT$4,500",
        {"page_content": "內文", "metadata": {}},
        SimpleNamespace(page_content="內文"),
        SimpleNamespace(page_content=None, metadata={}),
        SimpleNamespace(page_content="內文", metadata=[("page", 1)]),
        ("not a document", 0.5),
    ],
)
def test_adapters_langchain_non_document_raises_type_error(bad: object) -> None:
    good = SimpleNamespace(id="ok", page_content="內文", metadata={})

    with pytest.raises(TypeError, match=r"docs\[1\]: expected an object with page_content and metadata"):
        from_langchain([good, bad])


def test_adapters_langchain_real_document_matches_duck_typed_object() -> None:
    metadata = {"source": "card.pdf", "page": 3}
    real = Document(id="d1", page_content="回饋 0.3%", metadata=metadata)
    duck = SimpleNamespace(id="d1", page_content="回饋 0.3%", metadata=metadata)
    real_without_id = Document(page_content="回饋 0.3%", metadata=metadata)
    duck_without_id = SimpleNamespace(page_content="回饋 0.3%", metadata=metadata)

    converted = from_langchain([(real, 0.5), real_without_id])

    assert converted == from_langchain([(duck, 0.5), duck_without_id])
    assert [(p.id, p.score) for p in converted] == [("d1", 0.5), ("bd8c4ff744f5", None)]
