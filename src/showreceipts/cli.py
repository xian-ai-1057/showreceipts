"""命令列入口 `showreceipts`：子指令對應 Python API 的操作，結果以 JSON 輸出到 stdout。"""

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from pydantic import TypeAdapter

from .config import ShowReceiptsConfig
from .models import Passage
from .pipeline import postprocess

_PASSAGE_LIST = TypeAdapter(list[Passage])


def main(argv: Sequence[str] | None = None, *, generator: Callable[[str, str], str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        output = args.run(args)
    except (OSError, ValueError) as exc:
        print(f"showreceipts: {exc}", file=sys.stderr)
        return 1
    sys.stdout.write(output + "\n")
    return 0


def _postprocess(args: argparse.Namespace) -> str:
    passages = _PASSAGE_LIST.validate_json(Path(args.passages).read_bytes())
    answer_text = Path(args.answer_file).read_text(encoding="utf-8") if args.answer_file else sys.stdin.read()
    config = ShowReceiptsConfig(input_marker_base=args.input_marker_base)
    return postprocess(answer_text, passages, config=config).model_dump_json(indent=2)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="showreceipts", description="不綁定 RAG 框架的引用層")
    commands = parser.add_subparsers(dest="command", required=True)

    post = commands.add_parser("postprocess", help="外部答案 + Passage JSON → Cited Answer JSON")
    post.add_argument("--passages", required=True, help="Passage JSON 清單檔")
    post.add_argument("--answer-file", help="答案文字檔；省略時從 stdin 讀入")
    post.add_argument("--input-marker-base", type=int, choices=(0, 1), default=1, help="答案編號的起點")
    post.set_defaults(run=_postprocess)
    return parser
