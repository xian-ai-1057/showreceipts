"""Citation Marker 文法：Spec 106 §4.8.4 worked examples 依 #9 改寫後的表格，經由 postprocess 驗證。

每列是（例號, 原答, N, base, 最終答案, citations 的 Passage 編號, fabricated_markers）。
Passage 編號 k 指給定清單中的第 k 個（1-based），與 base 無關。例號是 Spec 106 的編號，
文字 id 的列是 #9 與開跑前裁決新增的行為（範圍符號、豁免區、刪除處的空白）。
重複 ID 的例 19、20、23 另成一表，例 20 經由 answer。
"""

import itertools
import time
from pathlib import Path

import pytest

from showreceipts import CitedAnswer, Passage, ShowReceiptsConfig, answer, postprocess

GOLDEN = Path(__file__).parent / "fixtures" / "golden"


def _run(raw: str, n: int, base: int):
    passages = [Passage(id=f"P{k}", text=f"text {k}", source="doc.md") for k in range(1, n + 1)]
    return postprocess(raw, passages, config=ShowReceiptsConfig(input_marker_base=base))


def _check(raw: str, n: int, base: int, expected: str, cited: list[int], fabricated: list[str]) -> None:
    result = _run(raw, n, base)
    assert result.answer == expected
    assert [c.passage.id for c in result.citations] == [f"P{k}" for k in cited]
    assert result.fabricated_markers == fabricated


GRAMMAR = [
    ("1", "句A [2]. 句B [4][2][99].", 5, 1, "句A [1]. 句B [2][1].", [2, 4], ["[99]"]),
    ("2", "年費 NT$4,500 [1-3]。", 5, 1, "年費 NT$4,500 [1][2][3]。", [1, 2, 3], []),
    ("3", "回饋 3.8% [1, 2]。", 5, 1, "回饋 3.8% [1][2]。", [1, 2], []),
    ("4", "回饋 3.8% [2，1]。", 5, 1, "回饋 3.8% [1][2]。", [2, 1], []),
    ("5", "保費 1.3% [1、3]。", 5, 1, "保費 1.3% [1][2]。", [1, 3], []),
    ("6", "甲 [3, 1-2]。", 5, 1, "甲 [1][2][3]。", [3, 1, 2], []),
    ("7", "乙 [4-7]。", 5, 1, "乙 [1][2]。", [4, 5], ["[4-7]"]),
    ("8", "丙 [3-1] 丁 [2]。", 5, 1, "丙 丁 [1]。", [2], ["[3-1]"]),
    ("9", "戊 [8, 9] 結束。", 5, 1, "戊 結束。", [], ["[8, 9]"]),
    ("10", "己 [0][1]。", 3, 1, "己 [1]。", [1], ["[0]"]),
    ("11", "己 [0][1]。", 3, 0, "己 [1][2]。", [1, 2], []),
    ("12", "庚 [3] 辛 [2]。", 3, 0, "庚 辛 [1]。", [3], ["[3]"]),
    ("15", "甲 [2][2] 乙 [1, 1]。", 3, 1, "甲 [1][1] 乙 [2][2]。", [2, 1], []),
    ("16", "甲 [ 1 , 2 ] 乙 [1 - 2]。", 3, 1, "甲 [1][2] 乙 [1][2]。", [1, 2], []),
    ("17", "甲 [1-99999999]。", 3, 1, "甲 [1][2][3]。", [1, 2, 3], ["[1-99999999]"]),
    ("18", "陣列 [a] 與 [1.5] 與 【1】 與 [1–2]。", 3, 1, "陣列 [a] 與 [1.5] 與 【1】 與 [1][2]。", [1, 2], []),
    ("21", "甲 [0-2]。", 3, 0, "甲 [1][2][3]。", [1, 2, 3], []),
    ("22", "甲 [1-3]。", 3, 0, "甲 [1][2]。", [2, 3], ["[1-3]"]),
    ("24", "甲 [1,,2]。", 3, 1, "甲 [1][2]。", [1, 2], []),
    ("25", "甲 [1,2,]。", 3, 1, "甲 [1][2]。", [1, 2], []),
    ("26", "甲 [1-] 乙 [2]。", 3, 1, "甲 乙 [1]。", [2], ["[1-]"]),
    ("27", "甲 [1-2-3] 乙 [1 2] 丙 [3]。", 3, 1, "甲 乙 丙 [1]。", [3], ["[1-2-3]", "[1 2]"]),
    ("28", "甲 [3] 乙 [1,,2]。", 3, 1, "甲 [1] 乙 [2][3]。", [3, 1, 2], []),
    ("29", "甲 [1,\n2]。", 3, 1, "甲 [1,\n2]。", [], []),
    ("30", "超商 [7-11] 消費。", 6, 1, "超商 消費。", [], ["[7-11]"]),
    ("31", "超商 [7-11] 消費。", 12, 1, "超商 [1][2][3][4][5] 消費。", [7, 8, 9, 10, 11], []),
    ("33", "回答 [2]。\n\n[1] 來源: a.md（第 1 頁）\n[2] 來源: b.md", 3, 1,
     "回答 [1]。\n\n[2] 來源: a.md（第 1 頁）\n[1] 來源: b.md", [2, 1], []),
    ("43", "甲 [１][2]。", 3, 1, "甲 [1][2]。", [1, 2], []),
    ("44", "甲 ［1］。", 3, 1, "甲 ［1］。", [], []),
    ("45", "甲 [01]。", 3, 1, "甲 [1]。", [1], []),
    ("46", "甲 [00]。", 3, 0, "甲 [1]。", [1], []),
    ("50", "甲 [" + "1" * 5000 + "]。", 3, 1, "甲。", [], ["[" + "1" * 5000 + "]"]),
    ("51", "甲 [1-" + "9" * 5000 + "]。", 3, 1, "甲 [1][2][3]。", [1, 2, 3], ["[1-" + "9" * 5000 + "]"]),
    ("52", "[9][8]", 3, 1, "", [], ["[9]", "[8]"]),
    ("53", "", 3, 1, "", [], []),
    ("tilde", "甲 [1~3]。", 5, 1, "甲 [1][2][3]。", [1, 2, 3], []),
    ("fullwidth-tilde", "甲 [1～3]。", 5, 1, "甲 [1][2][3]。", [1, 2, 3], []),
    ("en-dash", "甲 [1–3]。", 5, 1, "甲 [1][2][3]。", [1, 2, 3], []),
    ("mixed-en-dash", "甲 [3, 1–2]。", 5, 1, "甲 [1][2][3]。", [3, 1, 2], []),
    ("reverse-tilde", "甲 [3~1] 乙 [2]。", 5, 1, "甲 乙 [1]。", [2], ["[3~1]"]),
    ("reverse-kept-item", "甲 [3-1, 2]。", 5, 1, "甲 [1]。", [2], ["[3-1, 2]"]),
    ("huge-range-no-passage", "甲 [100000000-999999999]。", 3, 1, "甲。", [], ["[100000000-999999999]"]),
    ("other-dashes", "甲 [1〜2] [1—2] [1－2]。", 3, 1, "甲 [1〜2] [1—2] [1－2]。", [], []),
    ("tabs-inside-group", "甲 [1\t,\t2] 乙 [\t3\t]。", 3, 1, "甲 [1][2] 乙 [3]。", [1, 2, 3], []),
    ("tabs-around-range-sign", "甲 [1\t~\t3]。", 3, 1, "甲 [1][2][3]。", [1, 2, 3], []),
    ("leading-zeros-beyond-nine-digits", "甲 [0000000001]。", 3, 1, "甲 [1]。", [1], []),
    ("fullwidth-leading-zeros", "甲 [０００００００００２]。", 3, 1, "甲 [1]。", [2], []),
    ("leading-zeros-in-range", "甲 [00000000002-00000000003]。", 3, 1, "甲 [1][2]。", [2, 3], []),
]


@pytest.mark.parametrize(
    ("example", "raw", "n", "base", "expected", "cited", "fabricated"), GRAMMAR, ids=[r[0] for r in GRAMMAR]
)
def test_markers_grammar_worked_example_normalized(
    example: str, raw: str, n: int, base: int, expected: str, cited: list[int], fabricated: list[str]
) -> None:
    _check(raw, n, base, expected, cited, fabricated)


DELETION = [
    ("13", "甲 [99] 乙  丙 [1]。", 3, 1, "甲 乙  丙 [1]。", [1], ["[99]"]),
    ("14", "甲 [99]。", 3, 1, "甲。", [], ["[99]"]),
    ("32", "答案如下：\n[1] 年費 4,500\n[2] 回饋 3.8%", 1, 1, "答案如下：\n[1] 年費 4,500\n 回饋 3.8%", [1], ["[2]"]),
    ("34", "甲（[9]）乙", 3, 1, "甲（）乙", [], ["[9]"]),
    ("35", "甲 ([9]) 乙", 3, 1, "甲 () 乙", [], ["[9]"]),
    ("36", "[9] 甲", 3, 1, " 甲", [], ["[9]"]),
    ("37", "甲 [9]\n乙", 3, 1, "甲 \n乙", [], ["[9]"]),
    ("38", "甲　[9]　乙", 3, 1, "甲　　乙", [], ["[9]"]),
    ("39", "甲 [9]，乙", 3, 1, "甲，乙", [], ["[9]"]),
    ("47", "甲 [[9]1]。", 3, 1, "甲。", [], ["[9]", "[1]"]),
    ("48", "甲 [1-[9]2]。", 3, 1, "甲。", [], ["[9]", "[1-2]"]),
    ("49", "甲 [1] 乙 [[9]1]。", 3, 1, "甲 [1] 乙。", [1], ["[9]", "[1]"]),
    ("tab-before-punctuation", "甲\t[9]。", 3, 1, "甲。", [], ["[9]"]),
    ("no-marker-double-space", "甲  乙", 3, 1, "甲  乙", [], []),
    ("mixed-run-keeps-first-char", "甲\t [9]  乙", 3, 1, "甲\t乙", [], ["[9]"]),
    ("joined-run-collapsed-whole", "甲  [9] 乙", 3, 1, "甲 乙", [], ["[9]"]),
    ("untouched-run-beside-deletion", "甲  [9]乙", 3, 1, "甲  乙", [], ["[9]"]),
    ("two-sided-run-before-punctuation", "甲 [9] 。", 3, 1, "甲。", [], ["[9]"]),
    ("two-sided-tab-run-before-punctuation", "甲 [9]\t，乙", 3, 1, "甲，乙", [], ["[9]"]),
    ("run-after-deletion-before-punctuation", "甲[9]  。", 3, 1, "甲。", [], ["[9]"]),
    ("kept-marker-then-run-before-punctuation", "甲 [1] [9] 。", 3, 1, "甲 [1]。", [1], ["[9]"]),
    ("nested-splice", "甲 [[[9]1]2] 乙", 3, 1, "甲 乙", [], ["[9]", "[1]", "[2]"]),
    ("private-use-chars-in-input-kept", "姓名：王\ue000明 [1]，甲 \ue001[2]\ue002 乙 [9]。", 3, 1,
     "姓名：王\ue000明 [1]，甲 \ue001[2]\ue002 乙。", [1, 2], ["[9]"]),
]


@pytest.mark.parametrize(
    ("example", "raw", "n", "base", "expected", "cited", "fabricated"), DELETION, ids=[r[0] for r in DELETION]
)
def test_markers_deletion_worked_example_cleaned_locally(
    example: str, raw: str, n: int, base: int, expected: str, cited: list[int], fabricated: list[str]
) -> None:
    _check(raw, n, base, expected, cited, fabricated)


EXEMPTION = [
    ("40", "用 `list[0]` 取值 [1]", 3, 0, "用 `list[0]` 取值 [1]", [2], []),
    ("41", "見 https://x.com/a[2]/b 甲 [1]。", 3, 1, "見 https://x.com/a[2]/b 甲 [1]。", [1], []),
    ("42", "[1](http://x) 甲", 3, 1, "[1](http://x) 甲", [1], []),
    ("url-ends-at-fullwidth-punctuation", "見 https://x.com/a，[2] 與 http://y[9]", 3, 1,
     "見 https://x.com/a，[1] 與 http://y[9]", [2], []),
    ("url-ends-at-chinese-quote", "見“https://x.com”[2] 乙", 3, 1, "見“https://x.com”[1] 乙", [2], []),
    ("url-ends-at-ellipsis", "見 https://x.com…[2]", 3, 1, "見 https://x.com…[1]", [2], []),
    ("url-ends-at-em-dash", "見 https://x.com—[2]", 3, 1, "見 https://x.com—[1]", [2], []),
    ("url-ends-at-fullwidth-tilde", "https://x.com/～[2] 乙", 3, 1, "https://x.com/～[1] 乙", [2], []),
    ("url-continues-past-western-punctuation", "見 https://x.org/A–B·C•D[2] 甲 [1]", 3, 1,
     "見 https://x.org/A–B·C•D[2] 甲 [1]", [1], []),
    ("url-ends-at-newline","見 https://x.com/[9]\n甲 [2]", 3, 1, "見 https://x.com/[9]\n甲 [1]", [2], []),
    ("markdown-link-url-ends-at-paren", "詳見[官網](https://x.com)[1]，另見 [2]。", 3, 1,
     "詳見[官網](https://x.com)[1]，另見 [2]。", [1, 2], []),
    ("markdown-link-url-keeps-balanced-parens", "見[維基](https://x.org/A_(b)/c[2])[1]", 3, 1,
     "見[維基](https://x.org/A_(b)/c[2])[1]", [1], []),
    ("markdown-link-url-ends-before-title", '見[官網](https://x.com/[2] "標題")[3]', 3, 1,
     '見[官網](https://x.com/[2] "標題")[1]', [3], []),
    ("autolink-url-ends-at-angle-bracket", "見 <https://x.com/a[2]>[3]", 3, 1, "見 <https://x.com/a[2]>[1]", [3], []),
    ("group-straddling-url-end","見 https://x.com/a[2，3] 甲", 3, 1, "見 https://x.com/a[2，3] 甲", [], []),
    ("fenced-backticks", "說明 [2]\n```python\nx = a[1]  # [9]\n```\n結論 [1]", 3, 1,
     "說明 [1]\n```python\nx = a[1]  # [9]\n```\n結論 [2]", [2, 1], []),
    ("fenced-tildes", "~~~\na[9]\n~~~\n甲 [1]", 3, 1, "~~~\na[9]\n~~~\n甲 [1]", [1], []),
    ("fenced-indentation-kept", "```\n    x  =  a[1]\n\tb [9]\n```\n甲 [9]。", 3, 1,
     "```\n    x  =  a[1]\n\tb [9]\n```\n甲。", [], ["[9]"]),
    ("fenced-longer-closing", "````\n```\na[1]\n`````\n甲 [2]", 3, 1, "````\n```\na[1]\n`````\n甲 [1]", [2], []),
    ("fenced-unclosed-to-end", "甲 [2]\n```\na[9] [1]", 3, 1, "甲 [1]\n```\na[9] [1]", [2], []),
    ("fenced-in-numbered-list-item", "1. ```bash\n   pip install a[1]\n   ```\n2. 年費 [2]。\n3. 回饋 [3]。", 3, 1,
     "1. ```bash\n   pip install a[1]\n   ```\n2. 年費 [1]。\n3. 回饋 [2]。", [2, 3], []),
    ("fenced-in-list-item-unindented-closing", "1. ```bash\npip install x[1]\n```\n2. 年費 [2]。", 3, 1,
     "1. ```bash\npip install x[1]\n```\n2. 年費 [1]。", [2], []),
    ("fenced-in-bullet-item", "- ```\n  x[1]\n  ```\n甲 [9]。", 3, 1, "- ```\n  x[1]\n  ```\n甲。", [], ["[9]"]),
    ("fenced-in-blockquote", "> ```python\n> x = a[1]\n> ```\n> 結論 [2]", 3, 1,
     "> ```python\n> x = a[1]\n> ```\n> 結論 [1]", [2], []),
    ("fenced-in-blockquoted-list-item", ">  1. ~~~\n>     a[1]\n>     ~~~\n> 甲 [2]", 3, 1,
     ">  1. ~~~\n>     a[1]\n>     ~~~\n> 甲 [1]", [2], []),
    ("quoted-fence-line-does-not-close-unquoted-block", "```\n> ```\nx = a[1]\n```\n甲 [2]。", 3, 1,
     "```\n> ```\nx = a[1]\n```\n甲 [1]。", [2], []),
    ("fenced-in-blockquote-longer-closing", "> ```\n> a[1]\n> ````\n甲 [2]。", 3, 1,
     "> ```\n> a[1]\n> ````\n甲 [1]。", [2], []),
    ("backticks-in-info-string-not-fence","```x``` 與 [2]", 3, 1, "```x``` 與 [1]", [2], []),
    ("inline-double-backticks", "``a`[1]`` 甲 [2]", 3, 1, "``a`[1]`` 甲 [1]", [2], []),
    ("unmatched-backtick-literal", "甲 ` [2] 乙 [1]", 3, 1, "甲 ` [1] 乙 [2]", [2, 1], []),
    ("escaped-backtick-not-inline-code", "使用 \\` 符號 [2] 與 `code` [1]", 3, 1,
     "使用 \\` 符號 [1] 與 `code` [2]", [2, 1], []),
    ("inline-code-spans-single-newline", "甲 `a\n[1]` 乙 [2]", 3, 1, "甲 `a\n[1]` 乙 [1]", [2], []),
    ("inline-code-stops-at-blank-line", "第一段 ` 符號 [1]。\n\n第二段 `code` [2]。", 3, 1,
     "第一段 ` 符號 [1]。\n\n第二段 `code` [2]。", [1, 2], []),
    ("inline-code-stops-at-whitespace-line", "甲 ` [1]\n \t\r\n乙 ` [2]", 3, 1, "甲 ` [1]\n \t\r\n乙 ` [2]", [1, 2], []),
]


@pytest.mark.parametrize(
    ("example", "raw", "n", "base", "expected", "cited", "fabricated"), EXEMPTION, ids=[r[0] for r in EXEMPTION]
)
def test_markers_exempt_region_left_untouched(
    example: str, raw: str, n: int, base: int, expected: str, cited: list[int], fabricated: list[str]
) -> None:
    _check(raw, n, base, expected, cited, fabricated)


def test_markers_golden_cited_answer_reproduced() -> None:
    golden = CitedAnswer.model_validate_json((GOLDEN / "cited_answer.json").read_text(encoding="utf-8"))

    result = postprocess(golden.raw_answer, golden.passages)

    assert result.answer == golden.answer
    assert result.citations == golden.citations
    assert result.fabricated_markers == golden.fabricated_markers


def test_markers_answer_with_every_bmp_private_use_char_resolved() -> None:
    private_use = "".join(map(chr, range(0xE000, 0xF900)))

    result = _run(private_use + " 甲 [2]", 3, 1)

    assert result.answer == private_use + " 甲 [1]"
    assert [c.passage.id for c in result.citations] == ["P2"]
    assert result.quality_report is not None


def test_markers_answer_with_every_private_use_char_raises_value_error() -> None:
    every = itertools.chain(range(0xE000, 0xF900), range(0xF0000, 0x110000))

    with pytest.raises(ValueError, match="private-use"):
        _run("".join(map(chr, every)) + " 甲 [2]", 3, 1)


def test_markers_huge_range_not_expanded_completes_fast() -> None:
    started = time.perf_counter()
    result = _run("甲 [1-999999999] 乙 [999999999~1]。", 3, 1)
    elapsed = time.perf_counter() - started

    assert result.answer == "甲 [1][2][3] 乙。"
    assert result.fabricated_markers == ["[1-999999999]", "[999999999~1]"]
    assert elapsed < 0.5


# Spec 106 的重複 ID 表：Passage 清單是 A、B、A′（與 A 同 ID、內文不同），postprocess 用 base 1。
# 每列是（例號, 入口, 原答, 最終答案, citations 依 n 的 Passage ID）。
DUPLICATE_IDS = [
    ("19", "postprocess", "x [3] y [2] z [1]。", "x [1] y [2] z [1]。", ["A", "B"]),
    ("20", "answer", "y [2] x [1]。", "y [1] x [2]。", ["B", "A"]),
    ("23", "postprocess", "x [1-3]。", "x [1][2][1]。", ["A", "B"]),
]


@pytest.mark.parametrize(
    ("example", "entry", "raw", "expected", "cited"), DUPLICATE_IDS, ids=[r[0] for r in DUPLICATE_IDS]
)
def test_markers_duplicate_ids_worked_example_point_to_first_occurrence(
    example: str, entry: str, raw: str, expected: str, cited: list[str], fake_generator
) -> None:
    a = Passage(id="A", text="first A", source="doc.md")
    b = Passage(id="B", text="B", source="doc.md")
    a_again = Passage(id="A", text="second A", source="other.md")
    fake_generator.reply = raw

    result = answer("q", [a, b, a_again], fake_generator) if entry == "answer" else postprocess(raw, [a, b, a_again])

    assert result.answer == expected
    assert [(c.n, c.passage) for c in result.citations] == [(n, {"A": a, "B": b}[i]) for n, i in enumerate(cited, 1)]
    assert result.passages == [a, b]
    assert result.fabricated_markers == []
