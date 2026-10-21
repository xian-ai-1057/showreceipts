"""Demo 後端：HTTP 端點與 Python API 一一對應，輸入輸出是同一套 JSON。

啟動：`uv run --all-extras uvicorn demo.app:create_app --factory`；根路徑是 demo 頁面，API 文件頁在 `/docs`。
預設 Generator 讀 `SHOWRECEIPTS_BASE_URL`、`SHOWRECEIPTS_MODEL`、`SHOWRECEIPTS_API_KEY`，與 CLI 相同。
上傳的 Document 以 `{filename, data_base64}` 傳，檔名決定格式。base64 錯誤、不支援的格式、無法解碼的文字、
缺少 extra 都是輸入問題，回 422；GeneratorError 回 502。兩者的本文都是 `{"detail": 訊息}`。
"""

import base64
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from showreceipts import (
    CitedAnswer,
    Generator,
    GeneratorError,
    Passage,
    ShowReceiptsConfig,
    answer,
    postprocess,
    select,
    split,
)
from showreceipts.cli import default_generator

INDEX_HTML = Path(__file__).parent / "index.html"
RICHART_PASSAGES = Path(__file__).parents[1] / "data" / "richart_passages.json"
RICHART_MD = Path(__file__).parents[1] / "data" / "richart.md"


class PostprocessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer_text: str
    passages: list[Passage]
    config: ShowReceiptsConfig | None = None


class DocumentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str
    data_base64: str


class SplitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document: DocumentPayload
    target_chars: int = Field(default=500, ge=1)


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    passages: list[Passage] | None = None
    document: DocumentPayload | None = None
    budget: int = Field(default=12000, ge=0)
    config: ShowReceiptsConfig | None = None

    @model_validator(mode="after")
    def _exactly_one_source(self) -> "AnswerRequest":
        if (self.passages is None) == (self.document is None):
            raise ValueError("give exactly one of passages or document")
        return self


def _split_document(document: DocumentPayload, *, target_chars: int = 500) -> list[Passage]:
    try:
        data = base64.b64decode(document.data_base64, validate=True)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"data_base64 is not valid base64: {exc}") from exc
    try:
        return split((data, document.filename), target_chars=target_chars)
    except (ValueError, ImportError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def create_app(generator: Generator | None = None) -> FastAPI:
    app = FastAPI(title="showreceipts demo")
    if generator is None:
        generator = default_generator()

    @app.exception_handler(GeneratorError)
    async def generator_error_handler(request: Request, exc: GeneratorError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(INDEX_HTML, media_type="text/html")

    @app.get("/samples/richart_passages.json", include_in_schema=False)
    def richart_passages() -> FileResponse:
        return FileResponse(RICHART_PASSAGES, media_type="application/json")

    @app.get("/samples/richart.md", include_in_schema=False)
    def richart_markdown() -> FileResponse:
        return FileResponse(RICHART_MD, media_type="text/markdown; charset=utf-8")

    @app.post("/split")
    def split_endpoint(request: SplitRequest) -> list[Passage]:
        return _split_document(request.document, target_chars=request.target_chars)

    @app.post("/answer")
    def answer_endpoint(request: AnswerRequest) -> CitedAnswer:
        passages = _split_document(request.document) if request.document else request.passages
        selected = select(request.question, passages, request.budget)
        return answer(request.question, selected, generator, config=request.config)

    @app.post("/postprocess")
    def postprocess_endpoint(request: PostprocessRequest) -> CitedAnswer:
        return postprocess(request.answer_text, request.passages, config=request.config)

    return app
