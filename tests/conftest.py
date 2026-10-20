"""共用測試工具：假 Generator，以及讓離線測試碰不到真模型端點的環境設定。"""

from dataclasses import dataclass, field

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
    monkeypatch.delenv("SHOWRECEIPTS_API_KEY", raising=False)
