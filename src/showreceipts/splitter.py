"""Splitter：把 Document 切成帶 Locator 的 Passage。

每種格式的 reader 把文字讀成 `(Locator, 內文)` 區段；同一個 chunker 再把每個區段切成約
`target_chars` 字的 Passage。Passage 不跨區段，所以 Locator 恆為單一標題路徑（PDF 則為單一頁碼）。
Passage ID 是 `sha256(Document 位元組)[:12] + ":" + 0-based 段落序號`，同一份 Document 重切得到相同 ID。

格式由副檔名決定（`_READERS`）。不支援的格式、不是 UTF-8 的文字拋 ValueError；需要選配 extra 的格式
在沒裝時拋 ImportError，訊息附安裝指令。CLI 與 demo 都把這兩種例外當成輸入錯誤回報。
"""

import hashlib
import re
from collections.abc import Callable
from pathlib import Path, PurePath

from .models import Passage

Section = tuple[str, str]

# 由粗到細的切點：空行（段落）、換行、句尾標點、空白。
_BOUNDARIES = (
    re.compile(r"(?<=\n\n)"),
    re.compile(r"(?<=\n)"),
    re.compile(r"(?<=[。！？；])|(?<=[.!?;][ \t])"),
    re.compile(r"(?<=[ \t])"),
)
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$")


def split(
    document: str | Path | tuple[bytes, str], *, target_chars: int = 500, source: str | None = None
) -> list[Passage]:
    if target_chars < 1:
        raise ValueError(f"target_chars must be at least 1, got {target_chars}")
    filename = document[1] if isinstance(document, tuple) else Path(document).name
    reader = _READERS.get(PurePath(filename).suffix.lower())
    if reader is None:
        supported = ", ".join(_READERS)
        raise ValueError(f"unsupported document format for {filename!r}; supported: {supported}")
    data = document[0] if isinstance(document, tuple) else Path(document).read_bytes()
    doc_hash = hashlib.sha256(data).hexdigest()[:12]
    chunks = [(locator, chunk) for locator, body in reader(data, filename) for chunk in _chunk(body, target_chars)]
    if source is None:
        source = PurePath(filename).name
    return [
        Passage(id=f"{doc_hash}:{i}", text=text, source=source, locator=locator)
        for i, (locator, text) in enumerate(chunks)
    ]


def _decode(data: bytes, filename: str) -> str:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{filename} is not UTF-8 text: {exc}") from None
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _read_text(data: bytes, filename: str) -> list[Section]:
    return [("", _decode(data, filename))]


def _read_markdown(data: bytes, filename: str) -> list[Section]:
    """以 ATX 標題（`#`～`######`）分區段，Locator 是從最上層到該區段的標題路徑；fenced code 裡的 `#` 行不算標題。"""
    sections: list[Section] = []
    headings: list[tuple[int, str]] = []
    body: list[str] = []
    fence = ""
    for line in _decode(data, filename).split("\n"):
        heading = None if fence else _HEADING_RE.match(line)
        if heading is None:
            fence = _fence_after(line, fence)
            body.append(line)
            continue
        sections.append((_heading_path(headings), "\n".join(body)))
        level = len(heading.group(1))
        headings = [(lv, title) for lv, title in headings if lv < level] + [(level, (heading.group(2) or "").strip())]
        body = []
    sections.append((_heading_path(headings), "\n".join(body)))
    return sections


def _fence_after(line: str, fence: str) -> str:
    """讀完這一行後所在 fenced code block 的開頭符號；不在 code block 裡時為空字串。"""
    if not fence:
        opener = _FENCE_RE.match(line)
        return opener.group(1) if opener else ""
    closes = line.strip().startswith(fence) and not line.strip().strip(fence[0])
    return "" if closes else fence


def _heading_path(headings: list[tuple[int, str]]) -> str:
    return " > ".join(title for _, title in headings if title)


def _chunk(text: str, target_chars: int) -> list[str]:
    """依序把切點放進同一段，直到下一塊會超過 target_chars；每塊在 `_pieces` 已經不超過上限。"""
    chunks, current = [], ""
    for piece in _pieces(text, target_chars, level=0):
        if current and len(current) + len(piece) > target_chars:
            chunks.append(current)
            current = ""
        current += piece
    chunks.append(current)
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def _pieces(text: str, limit: int, *, level: int) -> list[str]:
    """把超過 limit 的文字依 `_BOUNDARIES` 由粗到細切開（切點字元留在前一塊），都切不開才硬切。"""
    if len(text) <= limit:
        return [text]
    if level == len(_BOUNDARIES):
        return [text[i : i + limit] for i in range(0, len(text), limit)]
    parts = [part for part in _BOUNDARIES[level].split(text) if part]
    return [piece for part in parts for piece in _pieces(part, limit, level=level + 1)]


_READERS: dict[str, Callable[[bytes, str], list[Section]]] = {
    ".md": _read_markdown,
    ".txt": _read_text,
}
