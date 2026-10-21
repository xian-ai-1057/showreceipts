"""Splitter：把 Document 切成帶 Locator 的 Passage。

每種格式的 reader 把文字讀成 `(Locator, 內文)` 區段；同一個 chunker 再把每個區段切成約
`target_chars` 字的 Passage。Passage 不跨區段，所以 Locator 恆為單一標題路徑（Markdown、DOCX）
或單一頁碼（PDF，每頁一個區段）。
Passage ID 是 `sha256(Document 位元組)[:12] + ":" + 0-based 段落序號`，同一份 Document 重切得到相同 ID。

格式由副檔名決定（`_READERS`）。不支援的格式、不是 UTF-8 的文字、讀不了的 PDF／DOCX、抽不出文字的
掃描型 PDF 拋 ValueError；PDF、DOCX 需要選配 extra（`pypdf`、`python-docx`，只在 reader 內 lazy import），
沒裝時拋 ImportError，訊息附安裝指令。CLI 與 demo 都把這兩種例外當成輸入錯誤回報。
"""

import hashlib
import io
import re
import zipfile
from collections.abc import Callable
from pathlib import Path, PurePath

from .models import Passage

Section = tuple[str, str]
Block = tuple[int, str]

# 由粗到細的切點：空行（段落）、換行、句尾標點、空白。
_BOUNDARIES = (
    re.compile(r"(?<=\n\n)"),
    re.compile(r"(?<=\n)"),
    re.compile(r"(?<=[。！？；])|(?<=[.!?;][ \t])"),
    re.compile(r"(?<=[ \t])"),
)
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$")
# Word 內建標題樣式；其他工具產生的 DOCX 可能用中文樣式名稱。
_DOCX_HEADING_RE = re.compile(r"(?:Heading|標題|标题) ?([1-9])")


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
    """以 ATX 標題（`#`～`######`）分區段；fenced code 裡的 `#` 行不算標題。"""
    blocks: list[Block] = []
    fence = ""
    for line in _decode(data, filename).split("\n"):
        heading = None if fence else _HEADING_RE.match(line)
        if heading is None:
            fence = _fence_after(line, fence)
            blocks.append((0, line))
        else:
            blocks.append((len(heading.group(1)), (heading.group(2) or "").strip()))
    return _group_by_headings(blocks, joiner="\n")


def _fence_after(line: str, fence: str) -> str:
    """讀完這一行後所在 fenced code block 的開頭符號；不在 code block 裡時為空字串。"""
    if not fence:
        opener = _FENCE_RE.match(line)
        return opener.group(1) if opener else ""
    closes = line.strip().startswith(fence) and not line.strip().strip(fence[0])
    return "" if closes else fence


def _read_pdf(data: bytes, filename: str) -> list[Section]:
    """每頁一個區段，Locator 是「第 n 頁」（1-based）；沒有任何一頁抽得出文字時視為掃描型 PDF。"""
    try:
        from pypdf import PdfReader
        from pypdf.errors import PyPdfError
    except ImportError as exc:
        raise _missing_extra("PDF", "pdf") from exc
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [(f"第 {number} 頁", page.extract_text()) for number, page in enumerate(reader.pages, 1)]
    except PyPdfError as exc:
        raise ValueError(f"{filename} is not a readable PDF: {exc}") from None
    if not any(text.strip() for _, text in pages):
        raise ValueError(f"{filename} has no extractable text (a scanned PDF?); OCR is not supported")
    return pages


def _read_docx(data: bytes, filename: str) -> list[Section]:
    """以標題樣式分區段；段落與表格依文件順序，表格每列一行、儲存格以 ` | ` 隔開，空段落與空列略過。"""
    try:
        import docx
        from docx.table import Table
    except ImportError as exc:
        raise _missing_extra("DOCX", "docx") from exc
    try:
        document = docx.Document(io.BytesIO(data))
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ValueError(f"{filename} is not a readable DOCX file: {exc}") from None
    blocks: list[Block] = []
    for block in document.iter_inner_content():
        if isinstance(block, Table):
            rows = ([cell.text.strip() for cell in row.cells] for row in block.rows)
            level, text = 0, "\n".join(" | ".join(cells) for cells in rows if any(cells))
        else:
            heading = _DOCX_HEADING_RE.fullmatch(getattr(block.style, "name", None) or "")
            level, text = (int(heading.group(1)) if heading else 0), block.text.strip()
        if level or text:
            blocks.append((level, text))
    return _group_by_headings(blocks, joiner="\n\n")


def _missing_extra(kind: str, extra: str) -> ImportError:
    return ImportError(
        f"reading {kind} needs the optional {extra!r} extra: uv sync --extra {extra}, "
        f"or pip install 'showreceipts[{extra}]'"
    )


def _group_by_headings(blocks: list[Block], *, joiner: str) -> list[Section]:
    """依序把內文（層級 0）收進目前的區段，遇到標題（層級 ≥ 1）開新區段；Locator 是從最上層到該區段的標題路徑。"""
    sections: list[Section] = []
    headings: list[Block] = []
    body: list[str] = []
    for level, text in blocks:
        if not level:
            body.append(text)
            continue
        sections.append((_heading_path(headings), joiner.join(body)))
        headings = [(lv, title) for lv, title in headings if lv < level] + [(level, text)]
        body = []
    sections.append((_heading_path(headings), joiner.join(body)))
    return sections


def _heading_path(headings: list[Block]) -> str:
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
    ".pdf": _read_pdf,
    ".docx": _read_docx,
}
