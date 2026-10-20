"""CLI 包裝層：每個子指令的輸出與直接呼叫 Python API 完全相同。"""

import io
import json
import time
from pathlib import Path

import pytest

from conftest import CLOSED_ENDPOINT, chat_reply
from showreceipts import Passage, ShowReceiptsConfig, answer, postprocess
from showreceipts.cli import default_generator, main

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


def test_cli_answer_matches_python_api(fake_generator, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    passages_file = tmp_path / "passages.json"
    passages_file.write_text(json.dumps([p.model_dump(mode="json") for p in PASSAGES]), encoding="utf-8")
    fake_generator.reply = ANSWER

    code = main(["answer", "--question", "A 是什麼？", "--passages", str(passages_file)], generator=fake_generator)

    expected = answer("A 是什麼？", PASSAGES, fake_generator)
    assert code == 0
    assert json.loads(capsys.readouterr().out) == expected.model_dump(mode="json")
    assert fake_generator.calls[0] == fake_generator.calls[1]


def test_cli_answer_flags_override_env_for_default_generator(
    chat_server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    passages_file = tmp_path / "passages.json"
    passages_file.write_text(json.dumps([p.model_dump(mode="json") for p in PASSAGES]), encoding="utf-8")
    monkeypatch.setenv("SHOWRECEIPTS_MODEL", "env-model")
    monkeypatch.setenv("SHOWRECEIPTS_API_KEY", "env-key")
    chat_server.responses = [chat_reply(ANSWER)]
    argv = ["answer", "-q", "A 是什麼？", "--passages", str(passages_file)]

    code = main(argv + ["--base-url", chat_server.base_url, "--model", "flag-model", "--api-key", "flag-key"])

    [request] = chat_server.requests
    assert code == 0
    assert request["path"] == "/v1/chat/completions"
    assert request["body"]["model"] == "flag-model"
    assert request["headers"]["Authorization"] == "Bearer flag-key"
    expected = answer("A 是什麼？", PASSAGES, lambda system, user: ANSWER)
    assert json.loads(capsys.readouterr().out) == expected.model_dump(mode="json")


def test_cli_answer_generator_error_exits_nonzero_with_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    passages_file = tmp_path / "passages.json"
    passages_file.write_text(json.dumps([p.model_dump(mode="json") for p in PASSAGES]), encoding="utf-8")
    monkeypatch.setattr(time, "sleep", lambda seconds: None)

    code = main(["answer", "-q", "A 是什麼？", "--passages", str(passages_file)])

    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert captured.err.startswith("showreceipts: ")
    assert CLOSED_ENDPOINT in captured.err


def test_default_generator_without_env_points_at_local_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SHOWRECEIPTS_BASE_URL")

    generator = default_generator()

    assert generator.url == "http://localhost:11434/v1/chat/completions"
    assert generator.model == "qwen3.5:4b-mlx"
    assert generator.api_key == "ollama"


def test_default_generator_args_override_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHOWRECEIPTS_BASE_URL", "http://env-host/v1")
    monkeypatch.setenv("SHOWRECEIPTS_MODEL", "env-model")
    monkeypatch.setenv("SHOWRECEIPTS_API_KEY", "env-key")

    from_env = default_generator()
    from_args = default_generator(base_url="http://arg-host/v1", model="arg-model", api_key="arg-key")

    assert (from_env.url, from_env.model, from_env.api_key) == (
        "http://env-host/v1/chat/completions",
        "env-model",
        "env-key",
    )
    assert (from_args.url, from_args.model, from_args.api_key) == (
        "http://arg-host/v1/chat/completions",
        "arg-model",
        "arg-key",
    )
