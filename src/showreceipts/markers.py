"""Citation Marker 處理：把 marker 群組正規化成逐一的 `[n]`，依首次出現順序重編號，刪除 Fabricated Marker。

套件內部 API：
- `resolve(text, numbering)`：pipeline 用，回傳處理後答案、被引用的 Passage、Fabricated Marker。
- `exempt_spans(text)`：fenced code block、inline code、純網址的 `[start, end)` 範圍；
  這些範圍內的方括號數字不計入、不刪除、不改號。
- `citation_markers(answer)`：處理後答案中每個 Citation Marker `[n]` 的位置與編號，不含豁免區；
  給 Quality Report 判斷句子是否有引用、併句與去掉 marker 用。
"""

import math
import re
import unicodedata
from collections.abc import Mapping
from typing import NamedTuple

from .models import Passage

_GROUP_CHARS = r" \t,，、\-–~～"
_GROUP_RE = re.compile(rf"\[((?:[{_GROUP_CHARS}]*\d)+[{_GROUP_CHARS}]*)\]")
_ITEM_SPLIT_RE = re.compile(r"[,，、]")
_NUMBER_RE = re.compile(r"\d+")
_RANGE_RE = re.compile(r"(\d+)[ \t]*[-–~～][ \t]*(\d+)")
_CITATION_RE = re.compile(r"\[(\d+)\]")
_MAX_DIGITS = 9
_SPACES = " \t"
_PUNCTUATION = frozenset("，。、；：！？）」』,.;:!?)")
# 依 CommonMark：反引號 fence 那一行不能再有反引號；inline code 由等長的反引號串收尾。
_FENCE_OPEN_RE = re.compile(r"^[ \t]*(`{3,}(?=[^`\n]*$)|~{3,})", re.M)
_INLINE_CODE_RE = re.compile(r"(?<!`)(`+)(?!`).+?(?<!`)\1(?!`)", re.S)
_URL_START_RE = re.compile(r"https?://")
# 私用區字元：改寫後的 marker 以 _OPEN/_CLOSE 暫代方括號，被刪的群組先換成 _DELETED。
_OPEN, _CLOSE, _DELETED = "", "", ""


class Resolved(NamedTuple):
    answer: str
    cited: list[Passage]
    fabricated: list[str]


class CitationMarker(NamedTuple):
    start: int
    end: int
    n: int


def resolve(text: str, numbering: Mapping[int, Passage]) -> Resolved:
    """把答案中的 marker 群組依 `numbering` 對到 Passage，改寫成首次出現順序的 `[n]`。

    `cited[i]` 是顯示編號 `i + 1` 對應的 Passage。含 Fabricated Marker 的群組以原字串記入
    `fabricated`；整組對不到時從答案刪除。豁免區原樣保留，只改寫豁免區之間的文字。
    """
    renumberer = _Renumberer(numbering)
    pieces: list[str] = []
    pos = 0
    for start, end in exempt_spans(text):
        pieces += [renumberer.rewrite(text[pos:start]), text[start:end]]
        pos = end
    pieces.append(renumberer.rewrite(text[pos:]))
    return Resolved("".join(pieces), renumberer.cited, list(renumberer.fabricated))


def exempt_spans(text: str) -> list[tuple[int, int]]:
    """依序找 fenced code block、inline code、純網址，後一種只在前面找到的範圍之外找。"""
    spans = _fenced_code(text)
    for find in (_inline_code, _bare_urls):
        spans = sorted(spans + [s for gap in _gaps(spans, len(text)) for s in find(text, *gap)])
    return spans


def citation_markers(answer: str) -> list[CitationMarker]:
    markers = []
    for gap in _gaps(exempt_spans(answer), len(answer)):
        markers += [CitationMarker(m.start(), m.end(), int(m[1])) for m in _CITATION_RE.finditer(answer, *gap)]
    return markers


def _gaps(spans: list[tuple[int, int]], length: int) -> list[tuple[int, int]]:
    edges = [0, *(i for span in spans for i in span), length]
    return list(zip(edges[::2], edges[1::2]))


def _fenced_code(text: str) -> list[tuple[int, int]]:
    blocks = []
    end = 0
    while opening := _FENCE_OPEN_RE.search(text, end):
        fence = opening[1]
        closing_re = re.compile(rf"^[ \t]*{fence[0]}{{{len(fence)},}}[ \t\r]*$", re.M)
        closing = closing_re.search(text, opening.end())
        end = closing.end() if closing else len(text)
        blocks.append((opening.start(), end))
    return blocks


def _inline_code(text: str, start: int, end: int) -> list[tuple[int, int]]:
    return [m.span() for m in _INLINE_CODE_RE.finditer(text, start, end)]


def _bare_urls(text: str, start: int, end: int) -> list[tuple[int, int]]:
    urls = []
    while m := _URL_START_RE.search(text, start, end):
        start = m.end()
        while start < end and not _ends_url(text[start]):
            start += 1
        urls.append((m.start(), start))
    return urls


def _ends_url(char: str) -> bool:
    fullwidth = unicodedata.east_asian_width(char) in ("F", "W")
    return char.isspace() or (fullwidth and unicodedata.category(char).startswith("P"))


class _Renumberer:
    def __init__(self, numbering: Mapping[int, Passage]) -> None:
        self.numbering = numbering
        self.display: dict[str, int] = {}
        self.cited: list[Passage] = []
        self.fabricated: dict[str, None] = {}

    def rewrite(self, text: str) -> str:
        text = _remove_deleted(_GROUP_RE.sub(self._replace_group, text))
        # 改寫後的 marker 已換成私用區字元，此時還比對得到的群組都是刪除後前後拼接出來的。
        while spliced := _GROUP_RE.search(text):
            self.fabricated.setdefault(spliced[0])
            text = _remove_deleted(text[: spliced.start()] + _DELETED + text[spliced.end() :])
        return text.replace(_OPEN, "[").replace(_CLOSE, "]")

    def _replace_group(self, m: re.Match[str]) -> str:
        members, has_fabricated = _parse_group(m[1], self.numbering)
        if has_fabricated:
            self.fabricated.setdefault(m[0])
        if not members:
            return _DELETED
        return "".join(f"{_OPEN}{self._display(p)}{_CLOSE}" for p in members)

    def _display(self, passage: Passage) -> int:
        if passage.id not in self.display:
            self.display[passage.id] = len(self.display) + 1
            self.cited.append(passage)
        return self.display[passage.id]


def _parse_group(body: str, numbering: Mapping[int, Passage]) -> tuple[list[Passage], bool]:
    """回傳（群組中對得到的 Passage，依書寫順序）與（群組是否含 Fabricated Marker）。"""
    members: list[Passage] = []
    has_fabricated = False
    for item in _ITEM_SPLIT_RE.split(body):
        item = item.strip(_SPACES)
        if not item:
            continue
        if _NUMBER_RE.fullmatch(item):
            passage = numbering.get(_to_int(item))
            if passage is None:
                has_fabricated = True
            else:
                members.append(passage)
        elif rng := _RANGE_RE.fullmatch(item):
            low, high = _to_int(rng[1]), _to_int(rng[2])
            if low > high:
                has_fabricated = True
                continue
            # 只走訪既有編號，不展開 low..high。
            hits = [k for k in sorted(numbering) if low <= k <= high]
            has_fabricated |= len(hits) != high - low + 1
            members.extend(numbering[k] for k in hits)
        else:
            has_fabricated = True
    return members, has_fabricated


def _to_int(digits: str) -> int | float:
    # 超長數字不轉 int：視為無限大，也避開 int() 的位數上限。
    return math.inf if len(digits) > _MAX_DIGITS else int(digits)


def _remove_deleted(text: str) -> str:
    """拿掉 _DELETED，只在刪除處清理空白。

    後面緊接標點時，去掉刪除處前的半形空白與 tab；兩側都是半形空白或 tab 時，相接成的整串
    只留第一個字元。換行與全形空白不動。
    """
    pieces = text.split(_DELETED)
    out = pieces[0]
    for after in pieces[1:]:
        if after[:1] in _PUNCTUATION:
            out = out.rstrip(_SPACES)
        elif out.endswith(tuple(_SPACES)) and after.startswith(tuple(_SPACES)):
            out = out[: len(out.rstrip(_SPACES)) + 1]
            after = after.lstrip(_SPACES)
        out += after
    return out
