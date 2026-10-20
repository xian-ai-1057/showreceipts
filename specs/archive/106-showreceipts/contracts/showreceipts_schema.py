# showreceipts_schema — Pydantic v2 Schema
# ---------------------------------------------------------------
# Spec: specs/106-showreceipts/spec.md §4.4, §4.5, §4.6
# Owner: spec-author（由本 spec 鎖死，後續 teammate 唯讀）
# ---------------------------------------------------------------
"""showreceipts（引用層）的 DTO 契約。

術語一律依 GLOSSARY.md：Passage / Passage ID / Source / Locator / Citation /
Citation Marker / Fabricated Marker / Uncited Sentence / Cited Answer /
Quality Report / No-Answer Reply。

本檔只依賴 stdlib + Pydantic v2（D21）。runtime 版本在
`src/showreceipts/models.py`、`src/showreceipts/config.py`、
`src/showreceipts/quality/models.py`，必須與本檔 `model_json_schema()`（去除 description 後）完全相等
（AC #20）；runtime 不得以路徑載入本檔（會破壞 D8 的隔離與日後抽套件）。

Usage:
    from src.showreceipts import Passage, ShowReceiptsConfig, answer, postprocess

    passages = [Passage(id="p1", text="…", source="richart.docx.txt", locator="第 1 頁")]
    cited = postprocess("年費 NT$4,500 [1, 2]。", passages)

Fixtures:
    contracts/fixtures/passage_arrkb_example.json
    contracts/fixtures/cited_answer_example.json
    contracts/fixtures/cited_answer_no_answer_example.json
    contracts/fixtures/quality_report_uncited_example.json
    contracts/fixtures/config_default_example.json
"""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_NO_ANSWER_REPLY = "依現有資料無法回答"
DEFAULT_LANGUAGE = "繁體中文"
USER_PROMPT_PLACEHOLDERS = ("{context_blocks}", "{question}")
PASSAGE_BLOCK_PLACEHOLDERS = ("{n}", "{source}", "{locator}", "{text}")


# ---------------------------------------------------------------
# Enums
# ---------------------------------------------------------------

class EntityKind(StrEnum):
    """Quality Report 偵測到的實體類型（純 regex；沿用 Spec 104 值集合）。

    PER / ORG / LOC 保留 enum 但不偵測（不引入 NER：延續 Spec 104 Out of scope；本 spec §2 Out of scope）。
    """
    PER = "per"
    ORG = "org"
    LOC = "loc"
    NUM = "num"
    DATE = "date"
    MISC = "misc"


# ---------------------------------------------------------------
# Passage — 引用層唯一的輸入型別（D6 / D20）
# ---------------------------------------------------------------

class Passage(BaseModel):
    """餵進引用層的一段可引用文字；`[n]` 能指向的最小單位。

    編號規則（D22）：依呼叫端給定的順序編 1..N，引用層不依 score 重排。
    重複 Passage ID（D23）：只保留第一次出現者。

    Acceptance:
        - 對應 spec.md §6 AC #1、#7、#8
        - golden fixture：contracts/fixtures/passage_arrkb_example.json
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, description="Passage ID；格式由上游決定，引用層不解讀其結構")
    text: str = Field(..., description="Passage 內文（送進 prompt 與 Quality Report 比對的快照）")
    source: str = Field(..., description="Source：所屬文件的人類可讀名稱，只用於顯示與提示")
    locator: str = Field(
        default="",
        description="Locator：Source 內的位置描述（如「第 3 頁」「工作表：年費」）；可為空字串",
    )
    score: float | None = Field(default=None, description="上游分數；僅供顯示，引用層不據此排序")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="上游框架的其餘欄位；引用層原樣保留、不解讀",
    )


# ---------------------------------------------------------------
# Citation — 答案實際引用到的 Passage + 顯示編號
# ---------------------------------------------------------------

class Citation(BaseModel):
    """答案實際引用到的 Passage，連同它在答案中的顯示編號。

    `n` 依答案中首次出現的順序從 1 連號（Tier 1 renumber 規則）。

    Acceptance:
        - 對應 spec.md §6 AC #3、#4
    """

    model_config = ConfigDict(extra="forbid")

    n: int = Field(..., ge=1, description="顯示編號；與答案文字中的 [n] 一致")
    passage: Passage = Field(..., description="被引用的 Passage（重複 ID 時為第一次出現者）")


# ---------------------------------------------------------------
# Quality Report（D7 / D12 / D13）
# ---------------------------------------------------------------

class SentenceSupport(BaseModel):
    """單句的字元 3-gram 支持判定（沿用 Spec 104 演算法；欄位改用新術語）。"""

    model_config = ConfigDict(extra="forbid")

    sentence: str = Field(..., description="原句字串（含正規化後的 [n]）")
    supported: bool = Field(..., description="overlap_score >= 0.15")
    best_match_passage_id: str | None = Field(
        default=None,
        description="supported=True 時為 overlap 最高的 Passage ID；否則為 None",
    )
    overlap_score: float = Field(..., ge=0.0, le=1.0, description="句子 3-gram 在 Passage 中的覆蓋率")


class EntityFlag(BaseModel):
    """答案中偵測到、但在任何送入 Passage 的文字中都找不到的實體。"""

    model_config = ConfigDict(extra="forbid")

    entity: str = Field(..., description="regex match 字串")
    kind: EntityKind = Field(..., description="實體類型")
    reason: str = Field(..., description="被標記原因；固定為 'not found in any passage text'")


class UncitedSentence(BaseModel):
    """帶有數字內容、卻沒有任何 Citation Marker 的句子（D13）。

    Acceptance:
        - 對應 spec.md §6 AC #15
        - golden fixture：contracts/fixtures/quality_report_uncited_example.json
    """

    model_config = ConfigDict(extra="forbid")

    sentence: str = Field(..., description="原句字串")
    sentence_index: int = Field(..., ge=0, description="該句在 split_sentences 結果中的 0-based 位置")
    numbers: list[str] = Field(
        ...,
        min_length=1,
        description="句中觸發判定的數字片段，依出現順序（如 ['0.3']、['4,500']）",
    )


class QualityReport(BaseModel):
    """對 Cited Answer 做的確定性、不呼叫模型的檢查結果。

    只回報、不攔截、不改寫答案（D12）；顯示、警告或拒答由呼叫端決定。
    quality_score = supported 句數 / 總句數；無句子時為 1.0（Spec 104 規則）。

    Acceptance:
        - 對應 spec.md §6 AC #13 ~ #16
        - golden fixture：contracts/fixtures/quality_report_uncited_example.json
    """

    model_config = ConfigDict(extra="forbid")

    quality_score: float = Field(..., ge=0.0, le=1.0, description="supported 句子比例")
    sentence_supports: list[SentenceSupport] = Field(
        default_factory=list,
        description="逐句支持判定，順序與答案中句子順序一致",
    )
    unsupported_entities: list[EntityFlag] = Field(
        default_factory=list,
        description="在所有送入 Passage 文字中都找不到的 NUM / DATE 實體",
    )
    uncited_sentences: list[UncitedSentence] = Field(
        default_factory=list,
        description="Uncited Sentence 清單，順序與答案中句子順序一致",
    )


# ---------------------------------------------------------------
# CitedAnswer — 兩個公開入口的共同輸出（D19）
# ---------------------------------------------------------------

class CitedAnswer(BaseModel):
    """`answer()` 與 `postprocess()` 的輸出。

    - `answer`：正規化 + 重編號 + 移除 Fabricated Marker + 壓縮連續空白後的答案
    - `raw_answer`：Generator 原始輸出（answer 模式）或呼叫端傳入的 answer_text
      （postprocess 模式）；answer 模式走 No-Answer Reply 時為空字串
    - `citations`：只含答案實際引用的 Passage，n = 1..len(citations)
    - `passages`：去重後、依給定順序的全部 Passage；空 list 代表走了 No-Answer Reply
    - `fabricated_markers`：含 Fabricated Marker 的原始 marker 群組字串（依首次出現、去重；
      含刪除群組後拼接出的群組，見 spec §4.8.2 第 3 步；記錄單位見 spec §8 Q14）
    - `quality_report`：config.enable_quality_report=False 或走 No-Answer Reply 時為 None

    Acceptance:
        - 對應 spec.md §6 AC #2 ~ #10、#17
        - golden fixtures：
            contracts/fixtures/cited_answer_example.json
            contracts/fixtures/cited_answer_no_answer_example.json
    """

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(..., description="最終答案文字")
    raw_answer: str = Field(..., description="後處理前的答案文字")
    citations: list[Citation] = Field(default_factory=list, description="被引用的 Passage，依 n 排序")
    passages: list[Passage] = Field(default_factory=list, description="去重後的全部 Passage（給定順序）")
    fabricated_markers: list[str] = Field(
        default_factory=list,
        description="被移除（或部分移除）的 marker 群組原字串，如 '[7]'、'[2, 9]'、'[4-7]'",
    )
    quality_report: QualityReport | None = Field(default=None, description="選配的 Quality Report")

    @model_validator(mode="after")
    def _check_invariants(self) -> "CitedAnswer":
        ns = [c.n for c in self.citations]
        if ns != list(range(1, len(ns) + 1)):
            raise ValueError(f"citations n must be 1..{len(ns)} in order, got {ns}")
        ids = [p.id for p in self.passages]
        if len(ids) != len(set(ids)):
            raise ValueError("passages must not contain duplicate Passage IDs")
        id_set = set(ids)
        cited_ids = [c.passage.id for c in self.citations]
        if len(cited_ids) != len(set(cited_ids)):
            raise ValueError("a Passage may be cited at most once in citations")
        missing = [i for i in cited_ids if i not in id_set]
        if missing:
            raise ValueError(f"cited Passage IDs not in passages: {missing}")
        return self


# ---------------------------------------------------------------
# ShowReceiptsConfig — 唯一的設定物件（D19）
# ---------------------------------------------------------------

class ShowReceiptsConfig(BaseModel):
    """`answer()` / `postprocess()` 的全部選項。

    - `system_prompt`：None → 用預設繁中六條作答規則（第 5 條代入 `language`）；
      給字串 → 原樣使用（此時 `language` 不生效）（D15）
    - `user_prompt_template`：None → 預設模板；給字串 → 整段覆寫，以單趟替換代入
      `{context_blocks}` / `{question}`（不用 str.format）；placeholder 非必填，缺少時只記 warning
      （D15 字面解讀，spec §8 Q15）
    - `passage_block_template`：None → 預設區塊 `[n] 來源: {source}（{locator}）` + 內文
      （Locator 為空時省略括號）；給字串 → 每段 Passage 以單趟替換代入
      `{n}` / `{source}` / `{locator}` / `{text}`（spec §4.9、§8 Q15）
    - `language`：預設 system prompt 第 5 條「使用{language}回答。」的代入值
    - `no_answer_reply`：零 Passage 時回覆的 No-Answer Reply（D16）
    - `input_marker_base`：postprocess 模式下答案的編號起點；0 給 LangChain how-to 類 0-based 答案（D24）。
      answer 模式一律 1-based（D22），忽略本欄
    - `enable_quality_report`：是否產生 Quality Report（D7，預設開啟）

    Acceptance:
        - 對應 spec.md §6 AC #12、#18
        - golden fixture：contracts/fixtures/config_default_example.json
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    system_prompt: str | None = Field(default=None, description="整段覆寫 system prompt；None 用預設")
    user_prompt_template: str | None = Field(
        default=None,
        description="整段覆寫 user prompt 模板；可用 {context_blocks} 與 {question}（非必填）",
    )
    passage_block_template: str | None = Field(
        default=None,
        description="整段覆寫單段 Passage 區塊；可用 {n} / {source} / {locator} / {text}；None 用預設",
    )
    language: str = Field(default=DEFAULT_LANGUAGE, min_length=1, description="預設 prompt 的作答語言")
    no_answer_reply: str = Field(
        default=DEFAULT_NO_ANSWER_REPLY,
        min_length=1,
        description="零 Passage 時的固定回覆",
    )
    input_marker_base: Literal[0, 1] = Field(
        default=1,
        description="postprocess 模式下 Citation Marker 的編號起點（0 或 1）",
    )
    enable_quality_report: bool = Field(default=True, description="是否產生 Quality Report")
