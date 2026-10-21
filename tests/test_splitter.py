"""split：Document → Passage；Markdown 的 Locator 是標題路徑，純文字為空，Passage ID 由內容雜湊與段落序號組成。"""

from pathlib import Path

import pytest

from showreceipts import Passage, split

DOCS = Path(__file__).parent / "fixtures" / "docs"
RICHART_MD = Path(__file__).parents[1] / "data" / "richart.md"


def test_split_markdown_locator_is_heading_path() -> None:
    passages = split(DOCS / "tiny.md")

    assert passages == [
        Passage(
            id="23af2738f40b:0",
            text=(
                "Tag RAG 是一個具備段落級引用功能的本地 RAG 系統，使用 ChromaDB 作為向量資料庫，"
                "並透過 Ollama 本地模型進行推理。每個 chunk 均帶有穩定的 chunk_id，格式為 `{doc_id}:{chunk_index}`。"
            ),
            source="tiny.md",
            locator="測試文件：Tag RAG 系統簡介 > 系統架構",
        ),
        Passage(
            id="23af2738f40b:1",
            text=(
                "當 LLM 生成答案時，系統會自動追蹤每個 `[n]` 標記的使用情況，並依首次出現的順序重新編號。"
                "若 LLM 引用了不存在的編號，該標記會從答案中刪除，確保引用的正確性與完整性。"
            ),
            source="tiny.md",
            locator="測試文件：Tag RAG 系統簡介 > 引用機制",
        ),
    ]


def test_split_plain_text_locator_is_empty() -> None:
    passages = split(DOCS / "tiny.txt")

    assert passages == [
        Passage(
            id="7e573c76f601:0",
            text=(DOCS / "tiny.txt").read_text(encoding="utf-8").strip(),
            source="tiny.txt",
            locator="",
        )
    ]


def test_split_bytes_with_filename_matches_path() -> None:
    path = DOCS / "tiny.md"

    from_bytes = split((path.read_bytes(), "tiny.md"))

    assert from_bytes == split(path) == split(str(path))


def test_split_same_document_twice_gives_identical_ids() -> None:
    data = (DOCS / "tiny.md").read_bytes()

    first = split((data, "tiny.md"))
    again = split((data, "renamed.md"))

    assert [p.id for p in again] == [p.id for p in first] == ["23af2738f40b:0", "23af2738f40b:1"]


def test_split_source_defaults_to_basename_and_can_be_overridden() -> None:
    data = (DOCS / "tiny.txt").read_bytes()

    default = split((data, "uploads/2026/說明.txt"))
    overridden = split(DOCS / "tiny.txt", source="Tag RAG 說明")

    assert [p.source for p in default] == ["說明.txt"]
    assert [p.source for p in overridden] == ["Tag RAG 說明"]


def test_split_packs_paragraphs_up_to_target_chars() -> None:
    paragraphs = [c * 200 for c in "甲乙丙丁"]
    document = "\n\n".join(paragraphs).encode()

    passages = split((document, "notes.txt"), target_chars=500)

    assert [p.text for p in passages] == [
        paragraphs[0] + "\n\n" + paragraphs[1],
        paragraphs[2] + "\n\n" + paragraphs[3],
    ]


def test_split_long_paragraph_breaks_at_sentence_ends() -> None:
    sentences = [f"第{i:02d}句" + "內容" * 20 + "。" for i in range(30)]  # 每句 45 字
    document = "".join(sentences).encode()

    passages = split((document, "long.txt"), target_chars=500)

    assert [p.text for p in passages] == ["".join(sentences[:11]), "".join(sentences[11:22]), "".join(sentences[22:])]


def test_split_text_without_any_boundary_is_cut_at_target_chars() -> None:
    document = ("字" * 1200).encode()

    passages = split((document, "dense.txt"), target_chars=500)

    assert [len(p.text) for p in passages] == [500, 500, 200]


def test_split_markdown_heading_path_follows_heading_levels() -> None:
    document = "前言\n\n# 一、介紹\n## 卡片\n卡片說明\n### 卡面\n卡面說明\n## 平臺\n平臺說明\n# 二、費用\n年費說明\n".encode()

    passages = split((document, "card.md"))

    assert [(p.locator, p.text) for p in passages] == [
        ("", "前言"),
        ("一、介紹 > 卡片", "卡片說明"),
        ("一、介紹 > 卡片 > 卡面", "卡面說明"),
        ("一、介紹 > 平臺", "平臺說明"),
        ("二、費用", "年費說明"),
    ]


def test_split_markdown_hash_lines_in_code_fence_are_not_headings() -> None:
    document = "# 安裝\n\n```bash\n# 建立環境\nuv sync\n```\n\n完成。\n".encode()

    passages = split((document, "install.md"))

    assert [(p.locator, p.text) for p in passages] == [("安裝", "```bash\n# 建立環境\nuv sync\n```\n\n完成。")]


def test_split_windows_line_endings_split_like_unix() -> None:
    unix = "# 一、介紹\n\n第一段。\n\n第二段。\n"

    windows = split((unix.replace("\n", "\r\n").encode(), "card.md"))

    assert [(p.locator, p.text) for p in windows] == [("一、介紹", "第一段。\n\n第二段。")]


@pytest.mark.parametrize("filename", ["fees.xlsx", "page.html", "README"])
def test_split_unsupported_format_raises_clear_error(filename: str) -> None:
    with pytest.raises(ValueError, match=r"unsupported document format .*supported: .*\.md.*\.txt") as raised:
        split((b"irrelevant", filename))

    assert filename in str(raised.value)


def test_split_unsupported_path_is_rejected_before_reading_the_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsupported document format"):
        split(tmp_path / "missing.xlsx")


def test_split_text_that_is_not_utf8_raises_clear_error() -> None:
    with pytest.raises(ValueError, match=r"big5\.txt is not UTF-8 text"):
        split(("臺新".encode("big5"), "big5.txt"))


def test_split_empty_document_gives_no_passages() -> None:
    assert split((b"\n\n  \n", "empty.md")) == []


def test_split_target_chars_below_one_raises() -> None:
    with pytest.raises(ValueError, match="target_chars"):
        split(DOCS / "tiny.txt", target_chars=0)


def test_split_richart_sample_gives_several_passages_located_by_heading_path() -> None:
    passages = split(RICHART_MD)

    assert len(passages) >= 6
    assert all(0 < len(p.text) <= 500 for p in passages)
    assert all(p.source == "richart.md" for p in passages)
    assert "三、切換刷方案 > 假日刷" in {p.locator for p in passages}
