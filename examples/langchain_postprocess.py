"""LangChain 範例：LangChain 產生的 0-based 答案交給 showreceipts 後處理。

LangChain 的 QA 範例常以 `[0]`、`[1]` 從 0 開始替資料編號。這裡把 arrkb 樣本轉成 LangChain Document
（模擬 retriever 的輸出），用 LangChain 的鏈產生答案，再以 `from_langchain` 把同一批文件轉成 Passage，
經 `postprocess(..., input_marker_base=0)` 轉成從 1 連號的 `[n]`，並刪掉對不到任何文件的編號。
showreceipts 本身不需要安裝 LangChain。

    uv run python examples/langchain_postprocess.py "切換 Pay 著刷最高回饋多少？"

聊天模型由 showreceipts 的預設 Generator 充當，所以只裝 langchain-core 就能執行；實際專案換成 ChatOpenAI、
ChatOllama 等任何 LangChain 聊天模型即可。模型端點與 CLI 相同，讀 SHOWRECEIPTS_BASE_URL、SHOWRECEIPTS_MODEL、
SHOWRECEIPTS_API_KEY（預設本機 Ollama）；連本機模型時把 localhost 加入 NO_PROXY。
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompt_values import ChatPromptValue
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableLambda

from showreceipts import CitedAnswer, GeneratorError, ShowReceiptsConfig, postprocess
from showreceipts.adapters import from_langchain
from showreceipts.cli import default_generator

SAMPLE_PATH = Path(__file__).parent.parent / "data" / "sample_reranked.json"

PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "只根據下列資料，以繁體中文回答問題。每個用到資料的句子後面標上資料編號，例如 [0]；"
                "資料不足時回答「依現有資料無法回答」。\n\n{context}"
            ),
        ),
        ("human", "{question}"),
    ]
)


def build_documents(sample_path: Path) -> list[Document]:
    records = json.loads(Path(sample_path).read_text(encoding="utf-8"))["data"]
    return [
        Document(
            id=str(record["context_id"]),
            page_content=record["content"],
            metadata={"source": record["filename"], "page": record["page"]},
        )
        for record in records
    ]


def run(question: str, llm: Runnable[Any, Any], docs: list[Document]) -> CitedAnswer:
    context = "\n\n".join(f"[{i}] {doc.metadata['source']}\n{doc.page_content}" for i, doc in enumerate(docs))
    raw_answer = (PROMPT | llm | StrOutputParser()).invoke({"context": context, "question": question})
    return postprocess(raw_answer, from_langchain(docs), config=ShowReceiptsConfig(input_marker_base=0))


def main(argv: list[str] | None = None, *, llm: Runnable[Any, Any] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question")
    parser.add_argument("--sample", type=Path, default=SAMPLE_PATH, help="arrkb 樣本 JSON")
    args = parser.parse_args(argv)

    try:
        cited = run(args.question, llm or _chat_model_from_env(), build_documents(args.sample))
    except GeneratorError as exc:
        print(f"模型呼叫失敗：{exc}", file=sys.stderr)
        return 1

    print(f"原始答案（0-based）：\n{cited.raw_answer}\n")
    print(f"處理後（1-based）：\n{cited.answer}\n")
    print("引用：")
    for citation in cited.citations:
        p = citation.passage
        locator = f"（{p.locator}）" if p.locator else ""
        print(f"[{citation.n}] {p.source}{locator} id={p.id}")
    if cited.fabricated_markers:
        print(f"刪除的 Fabricated Marker：{'、'.join(cited.fabricated_markers)}")
    return 0


def _chat_model_from_env() -> Runnable[Any, str]:
    generator = default_generator()

    def chat(prompt: ChatPromptValue) -> str:
        system, human = prompt.to_messages()
        return generator(system.content, human.content)

    return RunnableLambda(chat)


if __name__ == "__main__":
    raise SystemExit(main())
