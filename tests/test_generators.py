"""OpenAICompatGenerator 的網路邊界：對 127.0.0.1 上的假端點驗證請求格式、重試與退避、錯誤包裝。"""

import time
import urllib.error

import pytest

from conftest import CLOSED_ENDPOINT, chat_reply
from showreceipts import GeneratorError, OpenAICompatGenerator


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    recorded: list[float] = []
    monkeypatch.setattr(time, "sleep", recorded.append)
    return recorded


def test_openai_compat_posts_chat_completions_request_and_returns_content(chat_server) -> None:
    chat_server.responses = [chat_reply("答案 [1]")]
    generator = OpenAICompatGenerator(base_url=chat_server.base_url + "/", model="qwen", api_key="secret")

    reply = generator("系統", "使用者")

    assert reply == "答案 [1]"
    [request] = chat_server.requests
    assert request["path"] == "/v1/chat/completions"
    assert request["headers"]["Content-Type"] == "application/json"
    assert request["headers"]["Authorization"] == "Bearer secret"
    assert request["body"] == {
        "model": "qwen",
        "messages": [{"role": "system", "content": "系統"}, {"role": "user", "content": "使用者"}],
        "temperature": 0.0,
        "stream": False,
    }


def test_openai_compat_without_api_key_sends_no_authorization(chat_server) -> None:
    OpenAICompatGenerator(base_url=chat_server.base_url, model="m")("s", "u")

    assert "Authorization" not in chat_server.requests[0]["headers"]


@pytest.mark.parametrize("status", [408, 409, 429, 500, 503])
def test_openai_compat_retryable_status_retried_with_backoff(chat_server, sleeps, status: int) -> None:
    chat_server.responses = [(status, {"error": "busy"}), (status, {"error": "busy"}), chat_reply("third time")]

    reply = OpenAICompatGenerator(base_url=chat_server.base_url, model="m")("s", "u")

    assert reply == "third time"
    assert len(chat_server.requests) == 3
    assert sleeps == [0.5, 1.0]


def test_openai_compat_dropped_connection_retried(chat_server, sleeps) -> None:
    chat_server.responses = ["drop", chat_reply("after drop")]

    reply = OpenAICompatGenerator(base_url=chat_server.base_url, model="m")("s", "u")

    assert reply == "after drop"
    assert sleeps == [0.5]


def test_openai_compat_retries_exhausted_raises_generator_error(chat_server, sleeps) -> None:
    chat_server.responses = [(500, {"error": "down"})] * 3

    with pytest.raises(GeneratorError) as excinfo:
        OpenAICompatGenerator(base_url=chat_server.base_url, model="m")("s", "u")

    assert isinstance(excinfo.value.__cause__, urllib.error.HTTPError)
    assert len(chat_server.requests) == 3
    assert sleeps == [0.5, 1.0]


def test_openai_compat_connection_refused_retried_then_generator_error(sleeps) -> None:
    with pytest.raises(GeneratorError) as excinfo:
        OpenAICompatGenerator(base_url=CLOSED_ENDPOINT, model="m")("s", "u")

    assert isinstance(excinfo.value.__cause__, urllib.error.URLError)
    assert sleeps == [0.5, 1.0]


def test_openai_compat_read_timeout_not_retried(chat_server, sleeps) -> None:
    chat_server.responses = [("delay", 1.0), chat_reply("in time")]

    with pytest.raises(GeneratorError) as excinfo:
        OpenAICompatGenerator(base_url=chat_server.base_url, model="m", timeout=0.2)("s", "u")

    assert isinstance(excinfo.value.__cause__, TimeoutError)
    assert len(chat_server.requests) == 1
    assert sleeps == []


@pytest.mark.parametrize(
    "response",
    [
        (400, {"error": "bad request"}),
        (401, {"error": "unauthorized"}),
        (200, b"not json"),
        (200, {"choices": []}),
        (200, {"result": "no choices"}),
        chat_reply(None),
        chat_reply(["not", "a", "string"]),
        (200, b"[" * 100_000 + b"]" * 100_000),
        ("raw", b"NOT HTTP\r\n\r\n"),
        ("raw", b"HTTP/1.1 200 OK\r\nX-Long: " + b"x" * 70_000 + b"\r\n\r\n"),
    ],
)
def test_openai_compat_non_retryable_failure_raises_generator_error_once(chat_server, sleeps, response) -> None:
    chat_server.responses = [response]

    with pytest.raises(GeneratorError):
        OpenAICompatGenerator(base_url=chat_server.base_url, model="m")("s", "u")

    assert len(chat_server.requests) == 1
    assert sleeps == []


@pytest.mark.parametrize(
    "base_url", ["", "localhost:11434/v1", "http://", "http://127.0.0.1:abc/v1", "http://exa mple.com/v1"]
)
def test_openai_compat_invalid_base_url_raises_generator_error_without_retry(sleeps, base_url: str) -> None:
    with pytest.raises(GeneratorError):
        OpenAICompatGenerator(base_url=base_url, model="m")("s", "u")

    assert sleeps == []
