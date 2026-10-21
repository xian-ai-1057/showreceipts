"""命令列入口 `showreceipts`：子指令對應 Python API 的操作，結果以 JSON 輸出到 stdout。"""

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import TypeAdapter

from .config import ShowReceiptsConfig
from .generators import Generator, GeneratorError, OpenAICompatGenerator
from .models import Passage
from .pipeline import answer, postprocess
from .selector import select
from .splitter import split

_PASSAGE_LIST = TypeAdapter(list[Passage])


def main(argv: Sequence[str] | None = None, *, generator: Generator | None = None) -> int:
    args = _parser().parse_args(argv)
    args.generator = generator
    try:
        output = args.run(args)
    except (OSError, ValueError, ImportError, GeneratorError) as exc:
        print(f"showreceipts: {exc}", file=sys.stderr)
        return 1
    sys.stdout.write(output + "\n")
    return 0


def default_generator(
    *, base_url: str | None = None, model: str | None = None, api_key: str | None = None
) -> OpenAICompatGenerator:
    """CLI 與 demo 後端共用的預設 Generator：參數優先，其次是環境變數，最後指向本機 Ollama。"""
    if base_url is None:
        base_url = os.environ.get("SHOWRECEIPTS_BASE_URL", "http://localhost:11434/v1")
    if model is None:
        model = os.environ.get("SHOWRECEIPTS_MODEL", "qwen3.5:4b-mlx")
    if api_key is None:
        api_key = os.environ.get("SHOWRECEIPTS_API_KEY", "ollama")
    return OpenAICompatGenerator(base_url=base_url, model=model, api_key=api_key)


def _split(args: argparse.Namespace) -> str:
    passages = split(args.document, target_chars=args.target_chars, source=args.source)
    return _PASSAGE_LIST.dump_json(passages, indent=2).decode()


def _answer(args: argparse.Namespace) -> str:
    if args.document:
        passages = split(args.document)
    else:
        passages = _PASSAGE_LIST.validate_json(Path(args.passages).read_bytes())
    selected = select(args.question, passages, args.budget)
    generator = args.generator
    if generator is None:
        generator = default_generator(base_url=args.base_url, model=args.model, api_key=args.api_key)
    return answer(args.question, selected, generator).model_dump_json(indent=2)


def _postprocess(args: argparse.Namespace) -> str:
    passages = _PASSAGE_LIST.validate_json(Path(args.passages).read_bytes())
    answer_text = Path(args.answer_file).read_text(encoding="utf-8") if args.answer_file else sys.stdin.read()
    config = ShowReceiptsConfig(input_marker_base=args.input_marker_base)
    return postprocess(answer_text, passages, config=config).model_dump_json(indent=2)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="showreceipts", description="不綁定 RAG 框架的引用層")
    commands = parser.add_subparsers(dest="command", required=True)

    spl = commands.add_parser("split", help="Document 檔案 → Passage JSON")
    spl.add_argument("document", help="Document 檔案；格式由副檔名決定")
    spl.add_argument("--target-chars", type=int, default=500, help="每段目標字數")
    spl.add_argument("--source", help="Passage 的 Source；預設為檔名")
    spl.set_defaults(run=_split)

    ans = commands.add_parser(
        "answer", help="問題 + Document 檔案或 Passage JSON → split → select → 呼叫 Generator → Cited Answer JSON"
    )
    ans.add_argument("--question", "-q", required=True, help="問題文字")
    source = ans.add_mutually_exclusive_group(required=True)
    source.add_argument("document", nargs="?", help="Document 檔案；先 split 再 select")
    source.add_argument("--passages", help="Passage JSON 清單檔；直接 select")
    ans.add_argument("--budget", type=int, default=12000, help="送進 prompt 的 Passage 總字數上限")
    ans.add_argument("--base-url", help="OpenAI 相容端點；預設讀 SHOWRECEIPTS_BASE_URL，再預設本機 Ollama")
    ans.add_argument("--model", help="模型名稱；預設讀 SHOWRECEIPTS_MODEL")
    ans.add_argument("--api-key", help="API key；預設讀 SHOWRECEIPTS_API_KEY")
    ans.set_defaults(run=_answer)

    post = commands.add_parser("postprocess", help="外部答案 + Passage JSON → Cited Answer JSON")
    post.add_argument("--passages", required=True, help="Passage JSON 清單檔")
    post.add_argument("--answer-file", help="答案文字檔；省略時從 stdin 讀入")
    post.add_argument("--input-marker-base", type=int, choices=(0, 1), default=1, help="答案編號的起點")
    post.set_defaults(run=_postprocess)
    return parser
