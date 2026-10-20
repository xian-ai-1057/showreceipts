"""Demo HTTP 包裝層：每個端點的輸出與直接呼叫 Python API 完全相同。"""

import time

import pytest
from fastapi.testclient import TestClient

from conftest import CLOSED_ENDPOINT, chat_reply
from demo.app import create_app
from showreceipts import Passage, ShowReceiptsConfig, answer, postprocess

PASSAGES = [
    Passage(id="A", text="first A", source="doc.md", locator="第 1 頁", score=0.9, metadata={"k": 1}),
    Passage(id="B", text="B", source="doc.md"),
    Passage(id="A", text="second A", source="other.md"),
]
ANSWER = "x [2] y [0] z [3] w [9]。"


def test_demo_postprocess_matches_python_api() -> None:
    client = TestClient(create_app())
    config = ShowReceiptsConfig(input_marker_base=0)

    response = client.post(
        "/postprocess",
        json={
            "answer_text": ANSWER,
            "passages": [p.model_dump(mode="json") for p in PASSAGES],
            "config": config.model_dump(mode="json"),
        },
    )

    assert response.status_code == 200
    assert response.json() == postprocess(ANSWER, PASSAGES, config=config).model_dump(mode="json")


def test_demo_answer_matches_python_api(fake_generator) -> None:
    client = TestClient(create_app(generator=fake_generator))
    config = ShowReceiptsConfig(language="English")
    fake_generator.reply = ANSWER

    response = client.post(
        "/answer",
        json={
            "question": "A 是什麼？",
            "passages": [p.model_dump(mode="json") for p in PASSAGES],
            "config": config.model_dump(mode="json"),
        },
    )

    expected = answer("A 是什麼？", PASSAGES, fake_generator, config=config)
    assert response.status_code == 200
    assert response.json() == expected.model_dump(mode="json")
    assert fake_generator.calls[0] == fake_generator.calls[1]


def test_demo_answer_default_generator_reads_env(chat_server, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHOWRECEIPTS_BASE_URL", chat_server.base_url)
    monkeypatch.setenv("SHOWRECEIPTS_MODEL", "env-model")
    chat_server.responses = [chat_reply(ANSWER)]
    client = TestClient(create_app())

    response = client.post("/answer", json={"question": "q", "passages": [p.model_dump(mode="json") for p in PASSAGES]})

    [request] = chat_server.requests
    assert request["body"]["model"] == "env-model"
    assert request["headers"]["Authorization"] == "Bearer ollama"
    expected = answer("q", PASSAGES, lambda system, user: ANSWER)
    assert response.json() == expected.model_dump(mode="json")


def test_demo_answer_generator_error_returns_502(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    client = TestClient(create_app())

    response = client.post("/answer", json={"question": "q", "passages": [p.model_dump(mode="json") for p in PASSAGES]})

    assert response.status_code == 502
    assert CLOSED_ENDPOINT in response.json()["detail"]


def test_demo_answer_without_passages_returns_422(fake_generator) -> None:
    client = TestClient(create_app(generator=fake_generator))

    response = client.post("/answer", json={"question": "q"})

    assert response.status_code == 422
    assert "detail" in response.json()
    assert fake_generator.calls == []
