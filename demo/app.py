"""Demo 後端：HTTP 端點與 Python API 一一對應，輸入輸出是同一套 JSON。

啟動：`uv run --all-extras uvicorn demo.app:create_app --factory`，API 文件頁在 `/docs`。
預設 Generator 讀 `SHOWRECEIPTS_BASE_URL`、`SHOWRECEIPTS_MODEL`、`SHOWRECEIPTS_API_KEY`，與 CLI 相同。
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, model_validator

from showreceipts import CitedAnswer, Generator, GeneratorError, Passage, ShowReceiptsConfig, answer, postprocess
from showreceipts.cli import default_generator


class PostprocessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer_text: str
    passages: list[Passage]
    config: ShowReceiptsConfig | None = None


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    passages: list[Passage] | None = None
    config: ShowReceiptsConfig | None = None

    @model_validator(mode="after")
    def _require_passages(self) -> "AnswerRequest":
        # passages 設成選填，是為了日後與 document 二擇一；目前只有這個來源，所以必填。
        if self.passages is None:
            raise ValueError("passages is required")
        return self


def create_app(generator: Generator | None = None) -> FastAPI:
    app = FastAPI(title="showreceipts demo")
    if generator is None:
        generator = default_generator()

    @app.exception_handler(GeneratorError)
    async def generator_error_handler(request: Request, exc: GeneratorError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    @app.post("/answer")
    def answer_endpoint(request: AnswerRequest) -> CitedAnswer:
        return answer(request.question, request.passages, generator, config=request.config)

    @app.post("/postprocess")
    def postprocess_endpoint(request: PostprocessRequest) -> CitedAnswer:
        return postprocess(request.answer_text, request.passages, config=request.config)

    return app
