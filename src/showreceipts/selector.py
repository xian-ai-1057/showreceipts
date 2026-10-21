"""預設 Selector：Passage 總字數超過預算時，依問題挑出最相關的幾段。

計分是字元 bigram 的 BM25（純 stdlib）。依分數由高到低取段，放不進剩餘預算的那段跳過、繼續試下一段；
同分依原順序；回傳時恢復原本順序。預算算的是 `Passage.text` 的字數，不含 prompt 裡的來源標頭。
重複的 Passage ID 只以第一次出現者計分與計字數，和 answer 的去重規則一致；兩條路徑回傳的都是輸入清單
的子序列，被選中 ID 的重複項跟著保留（answer 會再去重）。
"""

import math
import re
from collections import Counter
from collections.abc import Callable, Sequence

from .models import Passage
from .passages import dedupe

Selector = Callable[[str, Sequence[Passage], int], list[Passage]]

_K1 = 1.5
_B = 0.75
_WORD_RE = re.compile(r"\w+")


def select(question: str, passages: Sequence[Passage], budget: int = 12000) -> list[Passage]:
    if budget < 0:
        raise ValueError(f"budget must not be negative, got {budget}")
    candidates = dedupe(passages)
    if sum(len(p.text) for p in candidates) <= budget:
        return list(passages)
    scores = _bm25(_bigrams(question), [_bigrams(p.text) for p in candidates])
    ranked = sorted(range(len(candidates)), key=lambda i: (-scores[i], i))
    chosen, used = set(), 0
    for i in ranked:
        if used + len(candidates[i].text) <= budget:
            chosen.add(candidates[i].id)
            used += len(candidates[i].text)
    return [p for p in passages if p.id in chosen]


def _bigrams(text: str) -> list[str]:
    tokens: list[str] = []
    # 連續的字母、數字、漢字切成字元 bigram；只有一個字的片段保留該字。
    for word in _WORD_RE.findall(text.casefold()):
        tokens.extend([word] if len(word) == 1 else [word[i : i + 2] for i in range(len(word) - 1)])
    return tokens


def _bm25(query: list[str], documents: list[list[str]]) -> list[float]:
    counts = [Counter(doc) for doc in documents]
    avg_len = sum(len(doc) for doc in documents) / len(documents) or 1.0
    # 依問題中首次出現的順序加總，浮點結果不受 set 的雜湊順序影響。
    terms = list(dict.fromkeys(query))
    idf = {}
    for term in terms:
        df = sum(1 for count in counts if term in count)
        idf[term] = math.log(1 + (len(documents) - df + 0.5) / (df + 0.5))
    scores = []
    for doc, count in zip(documents, counts):
        norm = _K1 * (1 - _B + _B * len(doc) / avg_len)
        scores.append(sum(idf[t] * count[t] * (_K1 + 1) / (count[t] + norm) for t in terms if t in count))
    return scores
