"""CLI 包裝層：每個子指令的輸出與直接呼叫 Python API 完全相同。"""

import io
import json
from pathlib import Path

import pytest

from showreceipts import Passage, ShowReceiptsConfig, postprocess
from showreceipts.cli import main

PASSAGES = [
    Passage(id="A", text="first A", source="doc.md", locator="第 1 頁", score=0.9, metadata={"k": 1}),
    Passage(id="B", text="B", source="doc.md"),
    Passage(id="A", text="second A", source="other.md"),
]
ANSWER = "x [2] y [0] z [3] w [9]。"


@pytest.mark.parametrize("answer_from", ["stdin", "file"])
def test_cli_postprocess_matches_python_api(
    answer_from: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    passages_file = tmp_path / "passages.json"
    passages_file.write_text(json.dumps([p.model_dump(mode="json") for p in PASSAGES]), encoding="utf-8")
    argv = ["postprocess", "--passages", str(passages_file), "--input-marker-base", "0"]
    if answer_from == "file":
        answer_file = tmp_path / "answer.txt"
        answer_file.write_text(ANSWER, encoding="utf-8")
        argv += ["--answer-file", str(answer_file)]
    else:
        monkeypatch.setattr("sys.stdin", io.StringIO(ANSWER))

    code = main(argv)

    expected = postprocess(ANSWER, PASSAGES, config=ShowReceiptsConfig(input_marker_base=0))
    assert code == 0
    assert json.loads(capsys.readouterr().out) == expected.model_dump(mode="json")
