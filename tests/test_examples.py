"""examples/langchain_postprocess.py：LangChain 產生的 0-based 答案經 postprocess 轉成 1-based。"""

import importlib.util
import json
import time
from pathlib import Path
from types import ModuleType

import pytest
from conftest import ChatServer, chat_reply
from langchain_core.language_models import FakeListChatModel
from langchain_core.runnables import RunnableLambda

ROOT = Path(__file__).parent.parent
SAMPLE_PATH = ROOT / "data" / "sample_reranked.json"
IDS = [record["context_id"] for record in json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))["data"]]
RAW = "最高回饋 3.8% [0]，超商 LINE Pay 也有回饋 [2, 1]，保費 10% [7]。"


@pytest.fixture(scope="module")
def example() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "langchain_postprocess", ROOT / "examples" / "langchain_postprocess.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_examples_langchain_zero_based_answer_renumbered_and_fabricated_removed(example: ModuleType) -> None:
    llm = FakeListChatModel(responses=[RAW])

    cited = example.run("切換 Pay 著刷最高回饋多少？", llm, example.build_documents(SAMPLE_PATH))

    assert cited.raw_answer == RAW
    assert cited.answer == "最高回饋 3.8% [1]，超商 LINE Pay 也有回饋 [2][3]，保費 10%。"
    assert [(c.n, c.passage.id) for c in cited.citations] == [(1, IDS[0]), (2, IDS[2]), (3, IDS[1])]
    assert cited.fabricated_markers == ["[7]"]


def test_examples_langchain_context_numbered_from_zero_in_document_order(example: ModuleType) -> None:
    prompts: list[str] = []

    def llm(prompt: object) -> str:
        prompts.append(prompt.to_string())  # type: ignore[attr-defined]
        return "最後一段 [5]。"

    docs = example.build_documents(SAMPLE_PATH)
    cited = example.run("問題", RunnableLambda(llm), docs)

    starts = [prompts[0].find(f"[{i}] ") for i in range(len(docs))]
    assert -1 not in starts
    assert starts == sorted(starts)
    assert f"[{len(docs)}] " not in prompts[0]
    assert [(c.n, c.passage.id) for c in cited.citations] == [(1, IDS[5])]


def test_examples_langchain_main_prints_raw_and_processed_answer(
    example: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    code = example.main(["切換 Pay 著刷最高回饋多少？"], llm=FakeListChatModel(responses=[RAW]))

    out = capsys.readouterr().out
    assert code == 0
    assert RAW in out
    assert "最高回饋 3.8% [1]，超商 LINE Pay 也有回饋 [2][3]，保費 10%。" in out
    assert f"[3] 20260312【信用卡】115年上半年台新Richart卡權益 .docx.txt（第 1 頁） id={IDS[1]}" in out
    assert "刪除的 Fabricated Marker：[7]" in out


def test_examples_langchain_main_default_model_uses_showreceipts_endpoint(
    example: ModuleType, chat_server: ChatServer, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SHOWRECEIPTS_BASE_URL", chat_server.base_url)
    chat_server.responses = [chat_reply(RAW)]

    code = example.main(["切換 Pay 著刷最高回饋多少？"])

    [request] = chat_server.requests
    assert [m["role"] for m in request["body"]["messages"]] == ["system", "user"]
    assert request["body"]["messages"][1]["content"] == "切換 Pay 著刷最高回饋多少？"
    assert code == 0
    assert "最高回饋 3.8% [1]，超商 LINE Pay 也有回饋 [2][3]，保費 10%。" in capsys.readouterr().out


def test_examples_langchain_main_endpoint_down_exits_1(
    example: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(time, "sleep", lambda seconds: None)

    code = example.main(["問題"])

    assert code == 1
    assert "模型呼叫失敗" in capsys.readouterr().err
