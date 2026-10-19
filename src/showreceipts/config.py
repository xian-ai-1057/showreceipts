"""answer 與 postprocess 的設定物件；與 models.py 同屬鎖定的契約。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_NO_ANSWER_REPLY = "依現有資料無法回答"
DEFAULT_LANGUAGE = "繁體中文"


class ShowReceiptsConfig(BaseModel):
    """answer 與 postprocess 的全部選項。

    三個模板欄位給 None 時用預設值，給字串時整段覆寫；模板缺少 placeholder
    只記 warning、不拋例外。`system_prompt` 被覆寫時 `language` 不生效。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    system_prompt: str | None = Field(default=None, description="整段覆寫 system prompt")
    user_prompt_template: str | None = Field(
        default=None, description="整段覆寫 user prompt；可用 {context_blocks}、{question}"
    )
    passage_block_template: str | None = Field(
        default=None, description="整段覆寫單段 Passage 區塊；可用 {n}、{source}、{locator}、{text}"
    )
    language: str = Field(default=DEFAULT_LANGUAGE, min_length=1, description="預設 system prompt 的作答語言")
    no_answer_reply: str = Field(
        default=DEFAULT_NO_ANSWER_REPLY, min_length=1, description="沒有任何 Passage 時的固定回覆"
    )
    input_marker_base: Literal[0, 1] = Field(
        default=1, description="postprocess 時答案編號的起點；answer 一律從 1 開始"
    )
    enable_quality_report: bool = Field(default=True, description="是否產生 Quality Report")
