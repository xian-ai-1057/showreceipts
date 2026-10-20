# demo_host_history_schema — Pydantic v2 Schema（Demo Host，非 showreceipts 模組）
# ---------------------------------------------------------------
# Spec: specs/106-showreceipts/spec.md §4.15.4
# Relation: Demo Host 於 spec 106 §7 步驟 6 起改載入本檔；Spec 103 history_schema.py 是否標記
#           superseded 待 spec §8 Q9 裁決
# Owner: spec-author（由本 spec 鎖死，後續 teammate 唯讀）
# ---------------------------------------------------------------
"""Demo Host 對話歷史 DTO（v2）。

與 Spec 103 版本的差異只在 `StoredCitation`：
  - `context_id` → `passage_id`（GLOSSARY：Passage ID）
  - `score` 改為選填（Passage.score 為選填，D20）
  - 新增 `source` / `locator`：外部 Passage 不在 Chroma，重載歷史時無法反查 metadata
  - 新增 `origin`：`external` 的引用重載時直接顯示快照、不加「⚠️ 文件已更新或被刪除」（D17）
  - `snapshot_text` 拿掉 `max_length=1000`：caller 傳完整 Passage.text，由
    `HistoryStore.add_message` 截斷至 ≤ 1000（含「…」）——Store 是唯一截斷點（plan.md 仲裁 #1；
    spec §4.15.4、§8 Q26）。外部 Passage 長度不受 chunk_size 限制，保留 max_length 會讓建構先失敗

舊 `data/history.sqlite` 不遷移，由 Lead 手動刪除（D27）。

本檔屬 Demo Host，`src/history/models.py` 以路徑載入（沿用 Spec 103 慣例）；
showreceipts 模組不得 import 本檔。

Fixtures:
    contracts/fixtures/stored_citation_external_example.json
    contracts/fixtures/message_example.json
    contracts/fixtures/conversation_example.json
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class OriginKind(StrEnum):
    """引用的 Passage 從哪條 Demo Host 路徑來。"""
    LOCAL = "local"        # 本地 Chroma 檢索；渲染時反查最新原文，查無加 stale 標籤
    EXTERNAL = "external"  # 貼上的 arrkb JSON；渲染時只顯示快照，不加 stale 標籤


class StoredCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passage_id: str = Field(..., min_length=1, description="與 Passage.id 同")
    display_n: int = Field(..., ge=1, description="答案中顯示的 [n]")
    score: float | None = Field(default=None, description="持久化當時的 Passage.score")
    snapshot_text: str = Field(
        ...,
        description="Passage.text 快照；HistoryStore.add_message 截斷至 ≤1000（含 '…'）",
    )
    source: str = Field(..., description="Passage.source")
    locator: str = Field(default="", description="Passage.locator")
    origin: OriginKind = Field(..., description="local / external")


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int | None = Field(default=None, description="DB 自動指派的 PK；create 前為 None")
    conv_id: str = Field(..., description="所屬 conversation id（UUID4）")
    role: MessageRole = Field(..., description="user / assistant")
    content: str = Field(..., description="訊息內文（Cited Answer 的 answer）")
    citations: list[StoredCitation] = Field(default_factory=list, description="assistant 訊息的引用")
    created_at: datetime = Field(..., description="UTC 時間戳")


class Conversation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="UUID4 字串")
    title: str = Field(..., description="對話標題")
    created_at: datetime = Field(..., description="UTC 時間戳")
