"""Splitter：把 Document 切成帶 Locator 的 Passage。

每種格式的 reader 把文字讀成 `(Locator, 內文)` 區段，再以同一套規則（`_pack`）把每個區段切成約
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
from typing import Any

from .markers import FENCE_OPEN_RE, fence_close_re, fence_quotes
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
_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$")
# Word 內建標題樣式；其他工具產生的 DOCX 可能用中文樣式名稱。
_DOCX_HEADING_RE = re.compile(r"(?:Heading|標題|标题) ?([1-9])")
_DOCX_MAX_XML_BYTES = 50_000_000
# 例外訊息裡的 repr 位址（`<… at 0x…>`），以及 pypdf IndirectObject repr 帶的 id(reader)。
_ADDRESS_RE = re.compile(r" at 0x[0-9a-fA-F]+")
_INDIRECT_OBJECT_ID_RE = re.compile(r"(IndirectObject\(\d+, \d+), \d+\)")


def split(
    document: str | Path | tuple[bytes, str], *, target_chars: int = 500, source: str | None = None
) -> list[Passage]:
    if target_chars < 1:
        raise ValueError(f"target_chars must be at least 1, got {target_chars}")
    if isinstance(document, tuple):
        data, filename = document
    else:
        data, filename = None, Path(document).name
    reader = _READERS.get(PurePath(filename).suffix.lower())
    if reader is None:
        supported = ", ".join(_READERS)
        raise ValueError(f"unsupported document format for {filename!r}; supported: {supported}")
    if data is None:
        data = Path(document).read_bytes()
    doc_hash = hashlib.sha256(data).hexdigest()[:12]
    texts = [(locator, text) for locator, body in reader(data, filename) for text in _pack(body, target_chars)]
    if source is None:
        source = PurePath(filename).name
    return [
        Passage(id=f"{doc_hash}:{i}", text=text, source=source, locator=locator)
        for i, (locator, text) in enumerate(texts)
    ]


# PDF 的「第 n 頁」Locator，Adapter 轉換外部頁碼時共用；沒有頁碼時為空字串。
def page_locator(page: object) -> str:
    text = "" if page is None else str(page).strip()
    return f"第 {text} 頁" if text else ""


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
    closing: re.Pattern[str] | None = None
    for line in _decode(data, filename).split("\n"):
        heading = None if closing else _HEADING_RE.match(line)
        if heading is None:
            closing = _fence_closing_after(line, closing)
            blocks.append((0, line))
        else:
            blocks.append((len(heading.group(1)), (heading.group(2) or "").strip()))
    return _group_by_headings(blocks, joiner="\n")


def _fence_closing_after(line: str, closing: re.Pattern[str] | None) -> re.Pattern[str] | None:
    """讀完 `line` 後仍在 fenced code 裡時，回傳收尾行的 pattern。"""
    if closing is None:
        opener = FENCE_OPEN_RE.match(line)
        return fence_close_re(opener[1], fence_quotes(opener)) if opener else None
    return None if closing.match(line) else closing


def _read_pdf(data: bytes, filename: str) -> list[Section]:
    """每頁一個區段，Locator 是「第 n 頁」（1-based）；沒有任何一頁抽得出文字時視為掃描型 PDF。"""
    try:
        from pypdf import PdfReader
        from pypdf.errors import DependencyError
    except ImportError as exc:
        raise _missing_extra("PDF", "pdf") from exc
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [(page_locator(number), page.extract_text()) for number, page in enumerate(reader.pages, 1)]
    except DependencyError as exc:
        # AES 加密（Acrobat 限制列印、複製的預設）要 cryptography，pdf extra 以 pypdf[crypto] 帶進來。
        if "cryptography" in str(exc):
            raise _missing_extra("an AES-encrypted PDF", "pdf") from exc
        raise ValueError(f"{filename} is not a readable PDF: {_reason(exc)}") from None
    except Exception as exc:
        # 損壞的 PDF 除了 PyPdfError，也常讓 pypdf 丟出 KeyError、TypeError 等內建例外。
        raise ValueError(f"{filename} is not a readable PDF: {_reason(exc)}") from None
    if not any(text.strip() for _, text in pages):
        raise ValueError(f"{filename} has no extractable text (a scanned PDF?); OCR is not supported")
    return pages


def _read_docx(data: bytes, filename: str) -> list[Section]:
    """以標題樣式分區段；段落與表格依文件順序，表格每列一行、儲存格以 ` | ` 隔開，空段落、空標題與空列略過。"""
    try:
        import docx
    except ImportError as exc:
        raise _missing_extra("DOCX", "docx") from exc
    # python-docx 不限制解壓後的大小：幾十 KB 的 DOCX 就能展開成吃掉上 GB 記憶體的 XML。媒體檔不解析，不計入。
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as package:
            xml_size = sum(m.file_size for m in package.infolist() if m.filename.endswith((".xml", ".rels")))
    except zipfile.BadZipFile as exc:
        raise ValueError(f"{filename} is not a readable DOCX file: {exc}") from None
    if xml_size > _DOCX_MAX_XML_BYTES:
        raise ValueError(
            f"{filename} unzips to {xml_size:,} bytes of XML, more than the {_DOCX_MAX_XML_BYTES:,}-byte limit"
        )
    # 壞掉的 DOCX（zip、XML、文件結構）會讓 python-docx 丟出各種例外，沒有共同的例外類別。
    try:
        blocks = _docx_blocks(docx.Document(io.BytesIO(data)))
    except Exception as exc:
        raise ValueError(f"{filename} is not a readable DOCX file: {_reason(exc)}") from None
    return _group_by_headings(blocks, joiner="\n\n")


def _docx_blocks(document: Any) -> list[Block]:
    from docx.table import Table

    blocks: list[Block] = []
    for block in document.iter_inner_content():
        if isinstance(block, Table):
            rows = (_docx_row_cells(row) for row in block.rows)
            level, text = 0, "\n".join(" | ".join(cells) for cells in rows if any(cells))
        else:
            heading = _DOCX_HEADING_RE.fullmatch(getattr(block.style, "name", None) or "")
            level, text = (int(heading.group(1)) if heading else 0), block.text.strip()
        if text:
            blocks.append((level, text))
    return blocks


def _docx_row_cells(row: Any) -> list[str]:
    """一列的儲存格文字：多段落的儲存格以空白接成一行，水平合併的儲存格（同一個 `w:tc`）只取一次。"""
    cells, previous = [], None
    for cell in row.cells:
        if cell._tc is not previous:
            cells.append(" ".join(text for p in cell.paragraphs if (text := p.text.strip())))
        previous = cell._tc
    return cells


def _reason(exc: Exception) -> str:
    """例外的類別與訊息，去掉每次執行都不同的物件位址。"""
    reason = _INDIRECT_OBJECT_ID_RE.sub(r"\1)", _ADDRESS_RE.sub("", str(exc)))
    return f"{type(exc).__name__}: {reason}"


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


def _pack(text: str, target_chars: int) -> list[str]:
    """依序把切點放進同一段，直到下一塊會超過 target_chars；每塊在 `_pieces` 已經不超過上限。"""
    packed, current = [], ""
    for piece in _pieces(text, target_chars, level=0):
        if current and len(current) + len(piece) > target_chars:
            packed.append(current)
            current = ""
        current += piece
    packed.append(current)
    return [part.strip() for part in packed if part.strip()]


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
