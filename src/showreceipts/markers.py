"""Citation Marker 處理：把 marker 群組正規化成逐一的 `[n]`，依首次出現順序重編號，刪除 Fabricated Marker。

對外只有 `resolve(text, numbering)`，由 pipeline 呼叫；fenced code 的判定（`FENCE_OPEN_RE`、
`fence_close_re`、`fence_quotes`）splitter 也共用。fenced code block、inline code、連結網址、純網址是
豁免區，區內的方括號數字不計入、不刪除、不改號。豁免區只在原始答案上判定；刪除 marker 後再判定結果可能
不同，所以處理後答案中的 marker 位置由 `resolve` 一併回傳（`marker_spans`），不要重掃處理後的答案。
內部以答案裡沒有的私用區字元暫代方括號；不能假設答案不含私用區，台灣 Big5 的造字就對應到這裡。
"""

import itertools
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
_MAX_DIGITS = 9
_SPACES = " \t"
_PUNCTUATION = frozenset("，。、；：！？）」』,.;:!?)")
# CommonMark：反引號 fence 那一行不能再有反引號。縮排不限，寧可多豁免。fence 可接在引言符號 `>` 與
# 清單符號之後（容器區塊）；group 1 是 fence。
_CONTAINER_PREFIX = r"[ \t]*(?:>[ \t]*|(?:[-*+]|\d{1,9}[.)])[ \t]+)*"
FENCE_OPEN_RE = re.compile(rf"^{_CONTAINER_PREFIX}(`{{3,}}(?=[^`\n]*$)|~{{3,}})", re.M)
# inline code 由等長的反引號串收尾，可跨行但不跨空行（段落邊界）；跳脫的 \` 不能開頭。
_NOT_BLANK_LINE = r"(?!\n[ \t\r]*\n)."
_INLINE_CODE_RE = re.compile(rf"(?<![`\\])(`+)(?!`)(?:{_NOT_BLANK_LINE})+?(?<!`)\1(?!`)", re.S)
# Markdown 連結 `](…)` 與 autolink `<…>` 的網址不是純網址，由連結語法的括號收尾（CommonMark）。
_LINK_URL_RE = re.compile(
    r"(?<=\]\()https?://(?:[^\s()]|\([^\s()]*\))*(?=[\s)])"
    r"|(?<=<)https?://[^\s<>]*(?=>)"
)
_URL_START_RE = re.compile(r"https?://")
# 全形標點是東亞寬度 F、W 的標點，再加上中文排版占一字寬、Unicode 卻歸為寬度 A 的 `“”‘’…—`，
# 以及歸為符號的 `～`。
_FULLWIDTH_EXTRA = frozenset("“”‘’…—～")


class Resolved(NamedTuple):
    answer: str
    cited: list[Passage]
    fabricated: list[str]
    marker_spans: list[tuple[int, int]]


def resolve(text: str, numbering: Mapping[int, Passage]) -> Resolved:
    """把答案中的 marker 群組依 `numbering` 對到 Passage，改寫成首次出現順序的 `[n]`。

    `cited[i]` 是顯示編號 `i + 1` 對應的 Passage。含 Fabricated Marker 的群組以原字串記入
    `fabricated`；整組對不到時從答案刪除。豁免區原樣保留，只改寫豁免區之間的文字。
    `marker_spans` 是改寫後每個 `[n]` 在答案中的位置，依序排列。
    """
    renumberer = _Renumberer(numbering, text)
    pieces: list[str] = []
    pos = 0
    for start, end in _exempt_spans(text):
        pieces += [renumberer.rewrite(text[pos:start]), text[start:end]]
        pos = end
    pieces.append(renumberer.rewrite(text[pos:]))
    written = "".join(pieces)
    # 暫代符號與方括號都是單一字元，換回方括號不會移動位置。
    spans = [m.span() for m in renumberer.written_re.finditer(written)]
    answer = written.replace(renumberer.open, "[").replace(renumberer.close, "]")
    return Resolved(answer, renumberer.cited, list(renumberer.fabricated), spans)


def _exempt_spans(text: str) -> list[tuple[int, int]]:
    """依序找 fenced code block、inline code、連結網址、純網址，後一種只在前面找到的範圍之外找。"""
    spans = _fenced_code(text)
    for find in (_inline_code, _link_urls, _bare_urls):
        found: list[tuple[int, int]] = []
        for gap_start, gap_end in _gaps(spans, len(text)):
            found += find(text, gap_start, gap_end)
        spans = sorted(spans + found)
    return spans


def _gaps(spans: list[tuple[int, int]], length: int) -> list[tuple[int, int]]:
    edges = [0, *(i for span in spans for i in span), length]
    return list(zip(edges[::2], edges[1::2], strict=True))


def fence_close_re(fence: str, quotes: int = 0) -> re.Pattern[str]:
    """收尾行：同字元、不短於 `fence`，前面的引言符號 `>` 與開頭行一樣是 `quotes` 層。"""
    quote = rf"(?:>[ \t]*){{{quotes}}}"
    return re.compile(rf"^[ \t]*{quote}{fence[0]}{{{len(fence)},}}[ \t\r]*$", re.M)


def fence_quotes(opening: re.Match[str]) -> int:
    """`FENCE_OPEN_RE` 比對到的 fence 行在幾層引言裡。"""
    return opening.string[opening.start() : opening.start(1)].count(">")


def _fenced_code(text: str) -> list[tuple[int, int]]:
    blocks = []
    end = 0
    while opening := FENCE_OPEN_RE.search(text, end):
        closing = fence_close_re(opening[1], fence_quotes(opening)).search(text, opening.end())
        end = closing.end() if closing else len(text)
        blocks.append((opening.start(), end))
    return blocks


def _inline_code(text: str, start: int, end: int) -> list[tuple[int, int]]:
    return [m.span() for m in _INLINE_CODE_RE.finditer(text, start, end)]


def _link_urls(text: str, start: int, end: int) -> list[tuple[int, int]]:
    return [m.span() for m in _LINK_URL_RE.finditer(text, start, end)]


def _bare_urls(text: str, start: int, end: int) -> list[tuple[int, int]]:
    urls = []
    while m := _URL_START_RE.search(text, start, end):
        pos = m.end()
        while pos < end and not _ends_url(text[pos]):
            pos += 1
        urls.append((m.start(), pos))
        start = pos
    return urls


def _ends_url(char: str) -> bool:
    if char.isspace() or char in _FULLWIDTH_EXTRA:
        return True
    fullwidth = unicodedata.east_asian_width(char) in ("F", "W")
    return fullwidth and unicodedata.category(char).startswith("P")


class _Renumberer:
    def __init__(self, numbering: Mapping[int, Passage], text: str) -> None:
        self.numbering = numbering
        # 改寫後的 marker 以 open/close 暫代方括號，被刪的群組先換成 deleted。
        self.open, self.close, self.deleted = _unused_private_use_chars(text)
        self.written_re = re.compile(f"{re.escape(self.open)}\\d+{re.escape(self.close)}")
        self.display: dict[str, int] = {}
        self.cited: list[Passage] = []
        self.fabricated: dict[str, None] = {}

    def rewrite(self, text: str) -> str:
        text = _remove_deleted(_GROUP_RE.sub(self._replace_group, text), self.deleted)
        # 改寫後的 marker 已換成私用區字元，此時還比對得到的群組都是刪除後前後拼接出來的。
        while spliced := _GROUP_RE.search(text):
            self.fabricated.setdefault(spliced[0])
            text = _remove_deleted(text[: spliced.start()] + self.deleted + text[spliced.end() :], self.deleted)
        return text

    def _replace_group(self, m: re.Match[str]) -> str:
        members, has_fabricated = _parse_group(m[1], self.numbering)
        if has_fabricated:
            self.fabricated.setdefault(m[0])
        if not members:
            return self.deleted
        return "".join(f"{self.open}{self._display(p)}{self.close}" for p in members)

    def _display(self, passage: Passage) -> int:
        if passage.id not in self.display:
            self.display[passage.id] = len(self.display) + 1
            self.cited.append(passage)
        return self.display[passage.id]


def _unused_private_use_chars(text: str) -> list[str]:
    present = set(text)
    private_use = itertools.chain(range(0xE000, 0xF900), range(0xF0000, 0x110000))
    unused = list(itertools.islice((c for c in map(chr, private_use) if c not in present), 3))
    if len(unused) < 3:
        raise ValueError("answer uses almost every private-use character; no placeholder is left")
    return unused


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
    # 前導零不算位數。超長數字不轉 int：視為無限大，也避開 int() 的位數上限。
    significant = "".join(str(unicodedata.decimal(d)) for d in digits).lstrip("0")
    return math.inf if len(significant) > _MAX_DIGITS else int(significant or "0")


def _remove_deleted(text: str, deleted: str) -> str:
    """拿掉代表刪除處的 `deleted` 字元，只在刪除處清理空白。

    刪除處兩側的半形空白與 tab 相接成一串：後面接著標點時整串去掉；否則兩側都有空白時只留
    第一個字元，只有一側有空白時不動。換行與全形空白不動。
    """
    pieces = text.split(deleted)
    out = pieces[0]
    for after in pieces[1:]:
        rest = after.lstrip(_SPACES)
        if rest[:1] in _PUNCTUATION:
            out, after = out.rstrip(_SPACES), rest
        elif out.endswith(tuple(_SPACES)) and after.startswith(tuple(_SPACES)):
            out, after = out[: len(out.rstrip(_SPACES)) + 1], rest
        out += after
    return out
