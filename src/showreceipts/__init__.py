"""showreceipts：不綁定任何 RAG 框架的引用層。

拿到 Passage（來自任何檢索系統，或直接從 Document 切出），產出帶 inline `[n]`
引用的答案與 Quality Report，一次處理一輪問答。架構與決策見 GLOSSARY.md、
docs/adr/ 與 GitHub issue #9。
"""

from .config import DEFAULT_NO_ANSWER_REPLY, ShowReceiptsConfig
from .models import (
    Citation,
    CitedAnswer,
    EntityFlag,
    EntityKind,
    Passage,
    QualityReport,
    SentenceSupport,
    UncitedSentence,
)

__all__ = [
    "Passage",
    "Citation",
    "CitedAnswer",
    "QualityReport",
    "SentenceSupport",
    "EntityFlag",
    "EntityKind",
    "UncitedSentence",
    "ShowReceiptsConfig",
    "DEFAULT_NO_ANSWER_REPLY",
]
