"""Quality Report：不呼叫模型的字面檢查，只回報、不改動答案。

演算法沿用 Tier 2 的 `src/eval/`（#9 開跑前裁決第 7 條）：句切分、句級字元 3-gram 重疊率、
NUM／DATE 實體的子字串比對，另加 Uncited Sentence。句子以答案中的位置表示，`sentence` 欄位
一律是答案的逐字子字串；Citation Marker 的位置由 `markers.resolve` 提供，不重掃答案，
所以 code 與網址裡的方括號數字不會被當成 marker。
"""

import re
from collections.abc import Sequence

from .models import Citation, EntityFlag, EntityKind, Passage, QualityReport, SentenceSupport, UncitedSentence

SUPPORT_THRESHOLD = 0.15
NGRAM_SIZE = 3

_SENTENCE_BREAK_RE = re.compile(r"(?<=[。！？])|\n+|(?<=[.!?])\s+")
# 行首清單序號：「1. 」「1.」「2) 」「(1) 」「（1）」「3、」「- 」「* 」「+ 」；序號後緊接數字的不算（「3.8%」）。
_ENUMERATOR_RE = re.compile(r"\s*(?:[(（]\d+[)）]\s*|\d+[.)](?!\d)\s*|\d+、|[-*+](?:\s+|$))")
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")
# 「元」不算數量單位，單獨的「4,500」不是實體（Spec 104 的 Lead 裁決）；千分位要整串取，「1,500萬」不能只取「500萬」。
_NUM_RE = re.compile(r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*(?:億|萬|百萬|千|%|‰)")
_DATE_RES = [
    re.compile(r"民國\s*\d{1,3}\s*年(?:\s*\d{1,2}\s*月(?:\s*\d{1,2}\s*日)?)?"),
    re.compile(r"\d{4}\s*年"),
    re.compile(r"\d{4}-\d{1,2}-\d{1,2}"),
    re.compile(r"\d{1,2}\s*月\s*\d{1,2}\s*日"),
    re.compile(r"Q[1-4]\s?\d{4}|\d{4}\s?Q[1-4]"),
]
ENTITY_REASON = "not found in any passage text"

Span = tuple[int, int]


def build_quality_report(
    answer: str,
    citations: Sequence[Citation],
    passages: Sequence[Passage],
    marker_spans: Sequence[Span],
) -> QualityReport:
    """`citations` 與 `passages` 同 Cited Answer；`marker_spans` 是答案中每個 `[n]` 的位置。"""
    sentences = _split_sentences(answer, marker_spans)
    passage_by_n = {c.n: c.passage for c in citations}
    supports = []
    uncited = []
    for index, (start, end) in enumerate(sentences):
        sentence = answer[start:end]
        markers = [(s, e) for s, e in marker_spans if start <= s < end]
        cited_ns = dict.fromkeys(int(answer[s + 1 : e - 1]) for s, e in markers)
        content = _without(answer, start, end, markers)
        supports.append(_support(sentence, content, [passage_by_n[n] for n in cited_ns]))
        if not markers:
            enumerator = _ENUMERATOR_RE.match(sentence)
            numbers = _NUMBER_RE.findall(sentence, enumerator.end() if enumerator else 0)
            if numbers:
                uncited.append(UncitedSentence(sentence=sentence, sentence_index=index, numbers=numbers))
    supported = sum(s.supported for s in supports)
    passage_text = "\n".join(p.text for p in passages)
    return QualityReport(
        quality_score=supported / len(supports) if supports else 1.0,
        sentence_supports=supports,
        unsupported_entities=[
            EntityFlag(entity=entity, kind=kind, reason=ENTITY_REASON)
            for entity, kind in _entities(answer)
            if entity not in passage_text
        ],
        uncited_sentences=uncited,
    )


def _split_sentences(text: str, marker_spans: Sequence[Span]) -> list[Span]:
    """Tier 2 的句切分，再做兩項修正；回傳每句在 `text` 中的範圍，併句時連同中間的分隔字元。

    - 句首的 marker 併回前一句（「…元。[1]」）。換行後的 marker 只有在該行沒有其他內容時才併回，
      行首 marker 後面還有內容時，視為那一行自己的 marker。
    - 只有清單序號的片段（「2. 年費…」切出的「2.」）併入下一句。
    """
    marker_end = dict(marker_spans)
    sentences: list[list[int]] = []
    enumerator: list[int] | None = None  # 等著併入下一句的清單序號範圍
    for start, end in _pieces(text):
        if sentences and enumerator is None:
            run_end = _marker_run_end(text, start, end, marker_end)
            same_line = "\n" not in text[sentences[-1][1] : start]
            if run_end is not None and (run_end == end or same_line):
                sentences[-1][1] = run_end
                start = _strip(text, run_end, end)[0]
                if start == end:
                    continue
        if _ENUMERATOR_RE.fullmatch(text, start, end):
            enumerator = [enumerator[0] if enumerator else start, end]
            continue
        if enumerator:
            start, enumerator = enumerator[0], None
        sentences.append([start, end])
    if enumerator:
        sentences.append(enumerator)
    return [(start, end) for start, end in sentences]


def _pieces(text: str) -> list[Span]:
    pieces = []
    pos = 0
    for brk in _SENTENCE_BREAK_RE.finditer(text):
        pieces.append(_strip(text, pos, brk.start()))
        pos = brk.end()
    pieces.append(_strip(text, pos, len(text)))
    return [(s, e) for s, e in pieces if s < e]


# `text[start:end]` 開頭是一串 marker（中間只隔空白）時，回傳最後一個 marker 的結尾。
def _marker_run_end(text: str, start: int, end: int, marker_end: dict[int, int]) -> int | None:
    run_end = None
    pos = start
    while pos in marker_end:
        run_end = pos = marker_end[pos]
        pos = _strip(text, pos, end)[0]
    return run_end


def _strip(text: str, start: int, end: int) -> Span:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _without(text: str, start: int, end: int, spans: Sequence[Span]) -> str:
    pieces = []
    for s, e in spans:
        pieces.append(text[start:s])
        start = e
    pieces.append(text[start:end])
    return "".join(pieces).strip()


def _support(sentence: str, content: str, cited: Sequence[Passage]) -> SentenceSupport:
    best_score, best_id = 0.0, None
    grams = _ngrams(content)
    if grams:
        for passage in cited:
            score = len(grams & _ngrams(passage.text)) / len(grams)
            if score > best_score:
                best_score, best_id = score, passage.id
    supported = best_score >= SUPPORT_THRESHOLD
    return SentenceSupport(
        sentence=sentence,
        supported=supported,
        best_match_passage_id=best_id if supported else None,
        overlap_score=round(best_score, 4),
    )


def _ngrams(text: str) -> set[str]:
    if len(text) < NGRAM_SIZE:
        return {text} if text else set()
    return {text[i : i + NGRAM_SIZE] for i in range(len(text) - NGRAM_SIZE + 1)}


def _entities(text: str) -> list[tuple[str, EntityKind]]:
    """NUM 在前、DATE 在後，同類依出現順序，同一字串只列一次。

    DATE 的各式樣互相重疊時（「民國115年1月1日」含「1月1日」）取最左、最長的那個。
    """
    dates: list[re.Match[str]] = []
    candidates = sorted((m for r in _DATE_RES for m in r.finditer(text)), key=lambda m: (m.start(), -m.end()))
    for m in candidates:
        if not dates or m.start() >= dates[-1].end():
            dates.append(m)
    found = [(m[0], EntityKind.NUM) for m in _NUM_RE.finditer(text)] + [(m[0], EntityKind.DATE) for m in dates]
    return list(dict.fromkeys(found))
