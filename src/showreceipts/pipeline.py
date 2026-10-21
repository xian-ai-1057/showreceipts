"""postprocess 與 answer 的流程；兩者都經由 `_finalize` 把原始答案收成 Cited Answer。"""

import logging
from collections.abc import Mapping, Sequence

from . import markers
from .config import ShowReceiptsConfig
from .generators import Generator
from .models import Citation, CitedAnswer, Passage
from .passages import dedupe
from .prompts import build_prompt
from .quality import build_quality_report

log = logging.getLogger(__name__)


def answer(
    question: str,
    passages: Sequence[Passage],
    generator: Generator,
    *,
    config: ShowReceiptsConfig | None = None,
) -> CitedAnswer:
    if not callable(generator):
        raise TypeError(f"generator must be callable, got {type(generator).__name__}")
    config = config or ShowReceiptsConfig()
    unique = dedupe(passages)
    if not unique:
        log.info("no passages; returning the No-Answer Reply without calling the generator")
        return _no_answer_reply(config, raw_answer="")
    system_prompt, user_prompt = build_prompt(question, unique, config)
    log.info("calling generator with %d passages", len(unique))
    log.debug("system prompt:\n%s\nuser prompt:\n%s", system_prompt, user_prompt)
    raw_answer = generator(system_prompt, user_prompt)
    if not isinstance(raw_answer, str):
        raise TypeError(f"generator returned {type(raw_answer).__name__}, expected str")
    return _finalize(raw_answer, unique, {n: p for n, p in enumerate(unique, start=1)}, config)


def postprocess(
    answer_text: str, passages: Sequence[Passage], *, config: ShowReceiptsConfig | None = None
) -> CitedAnswer:
    config = config or ShowReceiptsConfig()
    unique = dedupe(passages)
    if not unique:
        return _no_answer_reply(config, raw_answer=answer_text)
    first = {p.id: p for p in unique}
    numbering = {i + config.input_marker_base: first[p.id] for i, p in enumerate(passages)}
    return _finalize(answer_text, unique, numbering, config)


def _no_answer_reply(config: ShowReceiptsConfig, *, raw_answer: str) -> CitedAnswer:
    return CitedAnswer(answer=config.no_answer_reply, raw_answer=raw_answer)


def _finalize(
    raw_answer: str, passages: list[Passage], numbering: Mapping[int, Passage], config: ShowReceiptsConfig
) -> CitedAnswer:
    """`passages` 是去重後的非空清單；`numbering` 把答案中的編號對到其中的 Passage。"""
    resolved = markers.resolve(raw_answer, numbering)
    text = resolved.answer if resolved.answer.strip() else ""
    citations = [Citation(n=i, passage=p) for i, p in enumerate(resolved.cited, start=1)]
    report = None
    if config.enable_quality_report:
        try:
            report = build_quality_report(text, citations, passages, resolved.marker_spans)
        except Exception:
            # Quality Report 只回報、不攔截：建構失敗時照常回傳答案。
            log.warning("quality report failed; returning the answer without it", exc_info=True)
    return CitedAnswer(
        answer=text,
        raw_answer=raw_answer,
        citations=citations,
        passages=passages,
        fabricated_markers=resolved.fabricated,
        quality_report=report,
    )
