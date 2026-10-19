"""showreceipts 的資料模型——全專案唯一的介面契約。

Python API、CLI 與 demo 的 HTTP 端點都以這些模型的 JSON 形式交換資料。
本檔鎖定：任何欄位或驗證規則的變更都要先改 spec（GitHub issue #9）並經 Lead 同意。
術語依 GLOSSARY.md。
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Passage(BaseModel):
    """一段可引用的文字；`[n]` 能指向的最小單位。

    來源可能是外部檢索系統（經 Adapter 轉換）或由 Splitter 從 Document 切出。
    引用層依呼叫端給定的順序編號，從不依 `score` 重排。
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, description="Passage ID；格式由上游決定，引用層不解讀")
    text: str = Field(..., description="內文；送進 prompt，也是 Quality Report 的比對對象")
    source: str = Field(..., description="所屬文件的人類可讀名稱，只供顯示與提示")
    locator: str = Field(default="", description="在 Source 內的位置，例如「第 3 頁」；可為空")
    score: float | None = Field(default=None, description="上游分數，只供顯示")
    metadata: dict[str, Any] = Field(default_factory=dict, description="上游其餘欄位，原樣保留")


class Citation(BaseModel):
    """答案實際引用到的 Passage，連同它在答案中的顯示編號。"""

    model_config = ConfigDict(extra="forbid")

    n: int = Field(..., ge=1, description="顯示編號，與答案中的 [n] 一致；依首次出現順序從 1 連號")
    passage: Passage = Field(..., description="被引用的 Passage（重複 ID 時為第一次出現者）")


class EntityKind(StrEnum):
    """Quality Report 的實體種類；目前只偵測 NUM 與 DATE。"""

    PER = "per"
    ORG = "org"
    LOC = "loc"
    NUM = "num"
    DATE = "date"
    MISC = "misc"


class SentenceSupport(BaseModel):
    """單句與它引用的 Passage 之間的字元 3-gram 重疊判定。"""

    model_config = ConfigDict(extra="forbid")

    sentence: str = Field(..., description="答案中的原句（含 [n]）")
    supported: bool = Field(..., description="overlap_score 是否達門檻")
    best_match_passage_id: str | None = Field(default=None, description="supported 時重疊最高的 Passage ID")
    overlap_score: float = Field(..., ge=0.0, le=1.0, description="句子 3-gram 被 Passage 覆蓋的比例")


class EntityFlag(BaseModel):
    """答案中出現、但所有 Passage 內文都找不到的數字或日期。"""

    model_config = ConfigDict(extra="forbid")

    entity: str = Field(..., description="答案中擷取到的字串")
    kind: EntityKind = Field(..., description="實體種類")
    reason: str = Field(..., description="被標記的原因")


class UncitedSentence(BaseModel):
    """含數字內容、卻沒有任何 Citation Marker 的句子。"""

    model_config = ConfigDict(extra="forbid")

    sentence: str = Field(..., description="答案中的原句")
    sentence_index: int = Field(..., ge=0, description="在句切分結果中的 0-based 位置")
    numbers: list[str] = Field(..., min_length=1, description="句中觸發判定的數字，依出現順序")


class QualityReport(BaseModel):
    """不呼叫模型的字面檢查結果，供人工覆核參考；只回報、不攔截、不改寫答案。"""

    model_config = ConfigDict(extra="forbid")

    quality_score: float = Field(..., ge=0.0, le=1.0, description="supported 句數 / 總句數；無句子為 1.0")
    sentence_supports: list[SentenceSupport] = Field(default_factory=list, description="逐句判定，順序同答案")
    unsupported_entities: list[EntityFlag] = Field(default_factory=list, description="NUM 在前、DATE 在後")
    uncited_sentences: list[UncitedSentence] = Field(default_factory=list, description="順序同答案")


class CitedAnswer(BaseModel):
    """answer 與 postprocess 的共同輸出。

    `passages` 為空清單代表走了 No-Answer Reply；`quality_report` 在關閉或
    No-Answer Reply 時為空。驗證守住四條不變式：citations 的 n 是 1..K 連號且依序、
    passages 沒有重複 ID、同一 Passage 最多被引用一次、被引用的 ID 都在 passages 中。
    """

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(..., description="最終答案；可為空字串")
    raw_answer: str = Field(..., description="後處理前的答案；answer 走 No-Answer Reply 時為空字串")
    citations: list[Citation] = Field(default_factory=list, description="實際被引用的 Passage，依 n 排序")
    passages: list[Passage] = Field(default_factory=list, description="去重後、依給定順序的全部 Passage")
    fabricated_markers: list[str] = Field(
        default_factory=list,
        description="含 Fabricated Marker 的原始 marker 群組字串，依首次出現、去重",
    )
    quality_report: QualityReport | None = Field(default=None, description="Quality Report")

    @model_validator(mode="after")
    def _check_invariants(self) -> "CitedAnswer":
        ns = [c.n for c in self.citations]
        if ns != list(range(1, len(ns) + 1)):
            raise ValueError(f"citations n must be 1..{len(ns)} in order, got {ns}")
        ids = [p.id for p in self.passages]
        if len(ids) != len(set(ids)):
            raise ValueError("passages must not contain duplicate Passage IDs")
        cited_ids = [c.passage.id for c in self.citations]
        if len(cited_ids) != len(set(cited_ids)):
            raise ValueError("a Passage may be cited at most once")
        missing = [i for i in cited_ids if i not in set(ids)]
        if missing:
            raise ValueError(f"cited Passage IDs not in passages: {missing}")
        return self
