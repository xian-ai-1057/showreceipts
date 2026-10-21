"""Adapters：把外部檢索系統的結果轉成 Passage。引用層對 arrkb、LangChain 的認識只在這裡。"""

import hashlib
import logging
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from .models import Passage

log = logging.getLogger(__name__)


def from_arrkb(data: Any) -> list[Passage]:
    """`data` 可為 `{"data": [...]}` 外層、多筆 list，或單筆結果；Passage 依給定順序排列。"""
    if isinstance(data, Mapping):
        items = data["data"] if "data" in data and "context_id" not in data else [data]
    else:
        items = data
    return [_arrkb_passage(i, item) for i, item in enumerate(items)]


def _arrkb_passage(i: int, item: Mapping[str, Any]) -> Passage:
    for key in ("context_id", "content"):
        if key not in item:
            raise ValueError(f"arrkb item {i}: missing '{key}'")
    return Passage(
        id=str(item["context_id"]),
        text=item["content"],
        source=_first_present(item.get("filename")) or "?",
        locator=_page_locator(item.get("page")),
        score=(item.get("kwargs") or {}).get("relevance_score"),
        metadata={k: v for k, v in item.items() if k not in ("context_id", "content", "filename")},
    )


def _page_locator(page: Any) -> str:
    text = "" if page is None else str(page).strip()
    return f"第 {text} 頁" if text else ""


def from_langchain(
    docs: Iterable[Any],
    *,
    id_key: str = "id",
    source_key: str = "source",
    locator_fn: Callable[[dict[str, Any]], str] | None = None,
) -> list[Passage]:
    """以 duck typing 讀取有 `page_content`（str）與 `metadata`（Mapping）的物件，或 `(物件, score)`。

    缺 id 的文件以 Source 與內文的雜湊產生穩定 ID，整批只記一則 warning。
    """
    passages = []
    hashed = []
    for i, item in enumerate(docs):
        doc, score = item if isinstance(item, (tuple, list)) and len(item) == 2 else (item, None)
        text = getattr(doc, "page_content", None)
        metadata = getattr(doc, "metadata", None)
        if not isinstance(text, str) or not isinstance(metadata, Mapping):
            raise TypeError(f"docs[{i}]: expected an object with page_content and metadata, got {type(doc).__name__}")
        metadata = dict(metadata)
        source = _first_present(metadata.get(source_key)) or "?"
        passage_id = _first_present(getattr(doc, "id", None), metadata.get(id_key))
        if passage_id is None:
            passage_id = _content_hash(source, text)
            hashed.append(i)
        passages.append(
            Passage(
                id=passage_id,
                text=text,
                source=source,
                locator=locator_fn(metadata) if locator_fn else _page_locator(metadata.get("page")),
                score=score,
                metadata=metadata,
            )
        )
    if hashed:
        log.warning("docs %s have no id (.id or metadata[%r]); using a hash of source + text", hashed, id_key)
    return passages


def _content_hash(source: str, text: str) -> str:
    # NUL 分隔，("ab", "c") 與 ("a", "bc") 才不會得到同一個 ID。
    return hashlib.sha256(f"{source}\0{text}".encode()).hexdigest()[:12]


def _first_present(*values: Any) -> str | None:
    for value in values:
        if value is not None and str(value):
            return str(value)
    return None
