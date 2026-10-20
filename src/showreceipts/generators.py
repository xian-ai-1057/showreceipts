"""Generator 型別與預設的 OpenAI 相容實作（只用 stdlib）。

呼叫端自己的 Generator 拋出的例外原樣往上傳；`OpenAICompatGenerator` 的失敗則在
重試用完或遇到不可重試的錯誤時一律包成 `GeneratorError`，以 `__cause__` 保留原因。
"""

import http.client
import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

Generator = Callable[[str, str], str]

_RETRYABLE_STATUS = frozenset({408, 409, 429})

log = logging.getLogger(__name__)


class GeneratorError(RuntimeError):
    pass


class OpenAICompatGenerator:
    """呼叫 `{base_url}/chat/completions` 的 Generator，例如本機 Ollama 的 OpenAI 相容端點。"""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        temperature: float = 0.0,
        timeout: float = 600.0,
        max_retries: int = 2,
    ) -> None:
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        self.timeout = timeout
        self.max_retries = max_retries

    def __call__(self, system_prompt: str, user_prompt: str) -> str:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
            "stream": False,
        }
        response = self._post(json.dumps(body).encode("utf-8"))
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as err:
            raise GeneratorError(f"unexpected response shape from {self.url}") from err
        if not isinstance(content, str):
            raise GeneratorError(f"response content is {type(content).__name__}, expected str")
        return content

    def _post(self, data: bytes) -> Any:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        attempt = 0
        while True:
            try:
                request = urllib.request.Request(self.url, data=data, headers=headers, method="POST")
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except (OSError, http.client.HTTPException, ValueError) as err:
                if attempt >= self.max_retries or not _is_retryable(err):
                    raise GeneratorError(f"request to {self.url} failed: {err}") from err
                delay = min(0.5 * 2**attempt, 8.0)
                log.warning("request to %s failed (%s); retrying in %.1fs", self.url, err, delay)
            time.sleep(delay)
            attempt += 1


def _is_retryable(err: Exception) -> bool:
    if isinstance(err, urllib.error.HTTPError):
        return err.code in _RETRYABLE_STATUS or err.code >= 500
    # 等待回應逾時拋 TimeoutError、連線被中斷拋 RemoteDisconnected，兩者都不是 URLError。
    return isinstance(err, urllib.error.URLError | ConnectionError | TimeoutError | http.client.HTTPException)
