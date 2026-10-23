"""demo/index.html 裡的 Python 規則複本：用 node 跑頁面上 `<markers-port>` 那段 JS，結果要和 Python 一致。

`marker_spans` 不在 JSON 裡，頁面以移植的 `citationMarkers` 在處理後的答案裡找出 `[n]` 按鈕的位置。這裡拿
test_markers.py 的表格與隨機產生的答案，比對它在處理後答案上找到的位置，與 `markers.resolve` 對同一份答案的判定。
刪除 marker 偶爾會讓豁免區改變（例如 ` [9]```` 刪掉後變成行首的 fence），這時頁面與原始答案上的判定不同，
這是只拿得到處理後答案的限制，不在這裡比。改了 markers.py 的豁免規則、這個測試紅了，就同步改 index.html。
"""

import json
import random
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest
from test_markers import DELETION, EXEMPTION, GRAMMAR

from showreceipts import Passage, ShowReceiptsConfig, postprocess
from showreceipts.markers import _ends_url, resolve

INDEX = Path(__file__).parents[1] / "demo" / "index.html"
NODE = shutil.which("node")
TOKENS = [
    "`", "``", "```", "~~~", "\n", "\n\n", "\r", "\u2028", "> ", "1. ", "١. ", "- ", "    ", "\\", "\x1c", "\ufeff",
    "http://x.com/a", "https://y.org", "](https://z.com/", "<https://w.com/", "(", ")", "<", ">", "，", "。", "“",
    "–", "·", "＄", "｡", "\U00016fe2", "王", "甲", "\ue000", "\U000f0000", " ", " [1]", " [2]", "[3]", " [1-2]", " [9]",
]  # fmt: skip

# 頁面上的移植原樣放進 node；和頁面一樣只留對得到 Citation 的 [n]，位置以 code point 計。
_SCRIPT = """
%s
const cp = (s, i) => Array.from(s.slice(0, i)).length;
const answers = JSON.parse(require("fs").readFileSync(0, "utf8"));
console.log(JSON.stringify(answers.map(([text, cited]) => citationMarkers(text)
  .filter(({ n }) => n >= 1 && n <= cited)
  .map(({ start, end }) => [cp(text, start), cp(text, end)]))));
"""

# 每個 code point 丟給頁面的 URL_END_RE，列出純網址會停下的字元。
_URL_END_SCRIPT = """
const ends = [];
for (let c = 0; c <= 0x10ffff; c++) if ((c < 0xd800 || c > 0xdfff) && URL_END_RE.test(String.fromCodePoint(c))) ends.push(c);
console.log(JSON.stringify(ends));
"""


def _port() -> str:
    found = re.search(r"// <markers-port>\n(.*?)// </markers-port>", INDEX.read_text(encoding="utf-8"), re.S)
    assert found, "<markers-port> block not found in demo/index.html"
    return found.group(1)


def _node(script: str, payload: object) -> object:
    run = subprocess.run([NODE, "-e", script], input=json.dumps(payload), capture_output=True, text=True, check=True)
    return json.loads(run.stdout)


def test_demo_page_never_assigns_inner_html() -> None:
    # 答案與 Passage 內容來自模型與上傳檔，一律以文字節點放入（`el()`）。
    assert "innerHTML" not in INDEX.read_text(encoding="utf-8")


def _cases() -> list[tuple[str, str, int, int]]:
    tables = [(example, raw, n, base) for example, raw, n, base, *_ in GRAMMAR + DELETION + EXEMPTION]
    rng = random.Random(0)
    generated = ["".join(rng.choices(TOKENS, k=rng.randint(1, 25))) for _ in range(3000)]
    return tables + [(f"random-{i}", raw, 3, 1) for i, raw in enumerate(generated)]


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_demo_page_citation_markers_found_where_python_wrote_them() -> None:
    answers, expected = [], []
    for example, raw, n, base in _cases():
        passages = [Passage(id=f"P{k}", text=f"text {k}", source="doc.md") for k in range(1, n + 1)]
        cited = postprocess(raw, passages, config=ShowReceiptsConfig(input_marker_base=base))
        # 處理後的 [n] 已依首次出現排成 1..K，以 n 對到第 n 段重掃時位置不變。
        rescanned = resolve(cited.answer, dict(enumerate(passages, start=1)))
        answers.append([cited.answer, len(cited.citations)])
        expected.append((example, cited.answer, [list(span) for span in rescanned.marker_spans]))

    found = _node(_SCRIPT % _port(), answers)

    mismatches = [
        (ex, text, spans, got) for (ex, text, spans), got in zip(expected, found, strict=True) if spans != got
    ]
    assert mismatches == []


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_demo_page_bare_url_ends_at_same_characters_as_python() -> None:
    # 只比 Python 這版 Unicode 已指派的字元；node 的 Unicode 可能較新。
    assigned = {c for c in range(sys.maxunicode + 1) if unicodedata.category(chr(c)) != "Cn"}
    python_ends = {c for c in assigned if _ends_url(chr(c))}

    node_ends = set(_node(_port() + _URL_END_SCRIPT, None)) & assigned

    assert sorted(node_ends ^ python_ends) == []
