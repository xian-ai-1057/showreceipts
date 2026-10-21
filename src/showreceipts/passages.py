"""Passage 清單的去重：重複的 Passage ID 只留第一次出現者。"""

from collections.abc import Sequence

from .models import Passage


def dedupe(passages: Sequence[Passage]) -> list[Passage]:
    first: dict[str, Passage] = {}
    for i, passage in enumerate(passages):
        if not isinstance(passage, Passage):
            raise TypeError(f"passages[{i}] is {type(passage).__name__}, expected Passage")
        first.setdefault(passage.id, passage)
    return list(first.values())
