"""Demo 後端：HTTP 端點與 Python API 一一對應，輸入輸出是同一套 JSON。

啟動：`uv run --all-extras uvicorn demo.app:create_app --factory`，API 文件頁在 `/docs`。
"""

from collections.abc import Callable

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

from showreceipts import CitedAnswer, Passage, ShowReceiptsConfig, postprocess


class PostprocessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer_text: str
    passages: list[Passage]
    config: ShowReceiptsConfig | None = None


def create_app(generator: Callable[[str, str], str] | None = None) -> FastAPI:
    app = FastAPI(title="showreceipts demo")

    @app.post("/postprocess")
    def postprocess_endpoint(request: PostprocessRequest) -> CitedAnswer:
        return postprocess(request.answer_text, request.passages, config=request.config)

    return app
