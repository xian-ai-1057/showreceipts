"""共用測試工具：假 Generator、本機假 chat completions 端點，以及讓離線測試碰不到真模型端點的環境設定。"""

import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

CLOSED_ENDPOINT = "http://127.0.0.1:9/v1"


@dataclass
class FakeGenerator:
    reply: str = ""
    calls: list[tuple[str, str]] = field(default_factory=list)

    def __call__(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self.reply


@pytest.fixture
def fake_generator() -> FakeGenerator:
    return FakeGenerator()


@pytest.fixture(autouse=True)
def _offline_generator_endpoint(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.node.get_closest_marker("requires_ollama"):
        return
    monkeypatch.setenv("SHOWRECEIPTS_BASE_URL", CLOSED_ENDPOINT)
    monkeypatch.delenv("SHOWRECEIPTS_MODEL", raising=False)
    monkeypatch.delenv("SHOWRECEIPTS_API_KEY", raising=False)
    # urllib 會讀 HTTP(S)_PROXY；離線測試的請求一律直連、不送進 proxy。小寫的 no_proxy 優先，兩者都設。
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.setenv(name, "*")


def chat_reply(content: Any) -> tuple[int, dict[str, Any]]:
    return 200, {"choices": [{"index": 0, "message": {"role": "assistant", "content": content}}]}


@dataclass
class ChatServer:
    """127.0.0.1 上的假 OpenAI 相容端點。

    `responses` 依序取用：`(status, dict | bytes)`、`"drop"`（不回應直接斷線）、
    `("delay", 秒數)`（等待後回 `chat_reply("late")`）或 `("raw", bytes)`（原樣寫出、不是合法的 HTTP 回應）；
    取完後一律回 `chat_reply("ok")`。
    """

    base_url: str
    responses: list[Any] = field(default_factory=list)
    requests: list[dict[str, Any]] = field(default_factory=list)


@pytest.fixture
def chat_server() -> Iterator[ChatServer]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ChatHandler)
    state = ChatServer(base_url=f"http://127.0.0.1:{server.server_port}/v1")
    server.state = state  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    yield state
    server.shutdown()
    server.server_close()


class _ChatHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        try:
            self._respond()
        except (BrokenPipeError, ConnectionResetError):
            pass  # 逾時與格式錯誤的測試裡，client 會在回應寫完前斷線

    def _respond(self) -> None:
        state: ChatServer = self.server.state  # type: ignore[attr-defined]
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        state.requests.append({"path": self.path, "headers": dict(self.headers), "body": json.loads(body)})
        response = state.responses.pop(0) if state.responses else chat_reply("ok")
        if response == "drop":
            self.close_connection = True
            return
        if response[0] == "raw":
            self.wfile.write(response[1])
            self.close_connection = True
            return
        if response[0] == "delay":
            threading.Event().wait(response[1])
            response = chat_reply("late")
        status, payload = response
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        pass
