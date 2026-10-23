"""demo/index.html 裡的 Python 規則複本：用 node 跑頁面上的 regex，結果要和 Python 一致。

`ANSWER_TOKEN_RE` 是 markers.py 豁免規則的近似複本，頁面靠它在處理後的答案裡找出 `[n]` 按鈕的位置；
這裡拿 test_markers.py 的表格，比對它找到的位置與 `markers.resolve` 回傳的 `marker_spans`。
改了 markers.py 的豁免規則、這個測試紅了，就同步改 index.html。
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from test_markers import DELETION, EXEMPTION, GRAMMAR

from showreceipts import Passage, ShowReceiptsConfig, postprocess
from showreceipts.markers import resolve

INDEX = Path(__file__).parents[1] / "demo" / "index.html"
NODE = shutil.which("node")
# 頁面註解寫明的近似：收尾 fence 不比對引言層數。
APPROXIMATED = {"quoted-fence-line-does-not-close-unquoted-block"}

# 把頁面上的 regex 定義原樣取出，在 node 裡建立；和頁面一樣只留對得到 Citation 的 [n]，位置以 code point 計。
_SCRIPT = """
const ANSWER_TOKEN_RE = %s;
const cp = (s, i) => Array.from(s.slice(0, i)).length;
const answers = JSON.parse(require("fs").readFileSync(0, "utf8"));
console.log(JSON.stringify(answers.map(([text, cited]) => [...text.matchAll(ANSWER_TOKEN_RE)]
  .filter((m) => m.groups.n !== undefined && Number(m.groups.n) >= 1 && Number(m.groups.n) <= cited)
  .map((m) => [cp(text, m.index), cp(text, m.index + m[0].length)]))));
"""


def _page_regex() -> str:
    found = re.search(
        r"const ANSWER_TOKEN_RE = (new RegExp\(\[.*?\]\.join\(\"\|\"\), \"gmu\"\));",
        INDEX.read_text(encoding="utf-8"),
        re.S,
    )
    assert found, "ANSWER_TOKEN_RE definition not found in demo/index.html"
    return found.group(1)


def test_demo_page_never_assigns_inner_html() -> None:
    # 答案與 Passage 內容來自模型與上傳檔，一律以文字節點放入（`el()`）。
    assert "innerHTML" not in INDEX.read_text(encoding="utf-8")


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_demo_page_answer_token_re_finds_same_markers_as_python() -> None:
    rows = [row for row in GRAMMAR + DELETION + EXEMPTION if row[0] not in APPROXIMATED]
    answers, expected = [], []
    for example, raw, n, base, *_ in rows:
        passages = [Passage(id=f"P{k}", text=f"text {k}", source="doc.md") for k in range(1, n + 1)]
        cited = postprocess(raw, passages, config=ShowReceiptsConfig(input_marker_base=base))
        answers.append([cited.answer, len(cited.citations)])
        resolved = resolve(cited.answer, dict(enumerate(passages, start=1)))
        expected.append((example, [list(span) for span in resolved.marker_spans]))

    run = subprocess.run(
        [NODE, "-e", _SCRIPT % _page_regex()], input=json.dumps(answers), capture_output=True, text=True, check=True
    )

    found = json.loads(run.stdout)
    assert [(ex, spans) for (ex, _), spans in zip(expected, found, strict=True)] == expected
