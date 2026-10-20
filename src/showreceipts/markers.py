"""Citation Marker 處理：依答案中首次出現的順序重編號，刪除 Fabricated Marker。"""

import re
from collections.abc import Mapping
from typing import NamedTuple

from .models import Passage

_MARKER_RE = re.compile(r"\[(\d+)\]")
_MAX_DIGITS = 9
_SPACES = " \t"
_SPACE_CHARS = (" ", "\t")
_PUNCTUATION = frozenset("，。、；：！？）」』,.;:!?)")


class Resolved(NamedTuple):
    answer: str
    cited: list[Passage]
    fabricated: list[str]


def resolve(text: str, numbering: Mapping[int, Passage]) -> Resolved:
    """把答案中的 `[k]` 依 `numbering` 對到 Passage，改寫成首次出現順序的 `[n]`。

    `cited[i]` 是顯示編號 `i + 1` 對應的 Passage。對不到的 marker 從答案刪除並記入
    `fabricated`；刪除處只清掉標點前的空白，以及刪除後左右相接的重複空白。
    """
    display: dict[str, int] = {}
    cited: list[Passage] = []
    fabricated: dict[str, None] = {}
    out = ""
    pos = 0
    for m in _MARKER_RE.finditer(text):
        out += text[pos : m.start()]
        pos = m.end()
        passage = _lookup(m.group(1), numbering)
        if passage is None:
            fabricated.setdefault(m.group(0))
            following = text[pos : pos + 1]
            if following in _PUNCTUATION:
                out = out.rstrip(_SPACES)
            elif out.endswith(_SPACE_CHARS) and following in _SPACE_CHARS:
                while text[pos : pos + 1] in _SPACE_CHARS:
                    pos += 1
            continue
        if passage.id not in display:
            display[passage.id] = len(display) + 1
            cited.append(passage)
        out += f"[{display[passage.id]}]"
    out += text[pos:]
    return Resolved(out, cited, list(fabricated))


def _lookup(digits: str, numbering: Mapping[int, Passage]) -> Passage | None:
    # 超長數字不轉 int：對不到任何 Passage，也避開 int() 的位數上限。
    if len(digits) > _MAX_DIGITS:
        return None
    return numbering.get(int(digits))
