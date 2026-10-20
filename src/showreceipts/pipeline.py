"""postprocess 與 answer 的流程；兩者都經由 `_finalize` 把原始答案收成 Cited Answer。"""

from collections.abc import Mapping, Sequence

from . import markers
from .config import ShowReceiptsConfig
from .models import Citation, CitedAnswer, Passage
from .passages import dedupe


def postprocess(
    answer_text: str, passages: Sequence[Passage], *, config: ShowReceiptsConfig | None = None
) -> CitedAnswer:
    config = config or ShowReceiptsConfig()
    unique = dedupe(passages)
    if not unique:
        return _no_answer_reply(config, raw_answer=answer_text)
    first = {p.id: p for p in unique}
    numbering = {i + config.input_marker_base: first[p.id] for i, p in enumerate(passages)}
    return _finalize(answer_text, unique, numbering)


def _no_answer_reply(config: ShowReceiptsConfig, *, raw_answer: str) -> CitedAnswer:
    return CitedAnswer(answer=config.no_answer_reply, raw_answer=raw_answer)


def _finalize(raw_answer: str, passages: list[Passage], numbering: Mapping[int, Passage]) -> CitedAnswer:
    """`passages` 是去重後的非空清單；`numbering` 把答案中的編號對到其中的 Passage。"""
    resolved = markers.resolve(raw_answer, numbering)
    return CitedAnswer(
        answer=resolved.answer if resolved.answer.strip() else "",
        raw_answer=raw_answer,
        citations=[Citation(n=i, passage=p) for i, p in enumerate(resolved.cited, start=1)],
        passages=passages,
        fabricated_markers=resolved.fabricated,
    )
