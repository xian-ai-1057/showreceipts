"""預設 prompt 與模板組裝：把問題與已去重的 Passage 組成 (system_prompt, user_prompt)。"""

import logging
import re
from collections.abc import Mapping, Sequence

from .config import ShowReceiptsConfig
from .models import Passage

DEFAULT_SYSTEM_PROMPT_TEMPLATE = """你是一個嚴謹的問答助理。你會收到使用者問題與多段【參考資料】，每段以 [n] 編號標示。

【作答規則】
1. 只能使用提供的參考資料；不得編造資訊。
2. 每段論述結尾必須標註來源編號，例如 [1] 或 [2][3]。
3. 若同一句話綜合多段資料，依重要性排序列出所有編號。
4. 若參考資料不足以回答問題，明確說「依現有資料無法回答」並指出缺什麼。
5. 使用{language}回答。
6. 不要在回答尾端加入「參考資料」、「來源清單」等清單 — 介面下方會另行顯示。"""

DEFAULT_USER_PROMPT_TEMPLATE = """【參考資料】
{context_blocks}

【使用者問題】
{question}

【回答】"""

_USER_REQUIRED = ("context_blocks", "question")
_BLOCK_REQUIRED = ("n", "text")

log = logging.getLogger(__name__)


def build_prompt(
    question: str, passages: Sequence[Passage], config: ShowReceiptsConfig | None = None
) -> tuple[str, str]:
    """`passages` 依給定順序編 1..M；呼叫端負責先去重。"""
    config = config or ShowReceiptsConfig()
    if config.system_prompt is not None:
        system = config.system_prompt
    else:
        system = DEFAULT_SYSTEM_PROMPT_TEMPLATE.replace("{language}", config.language)

    block_template = config.passage_block_template
    if block_template is not None:
        _warn_missing("passage_block_template", block_template, _BLOCK_REQUIRED)
    context_blocks = "\n".join(_block(n, p, block_template) for n, p in enumerate(passages, start=1))

    user_template = config.user_prompt_template
    if user_template is None:
        user_template = DEFAULT_USER_PROMPT_TEMPLATE
    else:
        _warn_missing("user_prompt_template", user_template, _USER_REQUIRED)
    user = _substitute(user_template, {"context_blocks": context_blocks, "question": question})
    return system, user


def _block(n: int, passage: Passage, template: str | None) -> str:
    if template is not None:
        values = {"n": str(n), "source": passage.source, "locator": passage.locator, "text": passage.text}
        return _substitute(template, values)
    head = f"[{n}] 來源: {passage.source}"
    if passage.locator:
        head += f"（{passage.locator}）"
    return f"{head}\n{passage.text}\n"


def _substitute(template: str, values: Mapping[str, str]) -> str:
    # 單趟替換：代入的值裡若出現 {question} 等字樣，不會被再次替換；其他大括號原樣保留。
    pattern = re.compile(r"\{(" + "|".join(values) + r")\}")
    return pattern.sub(lambda m: values[m[1]], template)


def _warn_missing(field: str, template: str, placeholders: Sequence[str]) -> None:
    for name in placeholders:
        if "{" + name + "}" not in template:
            log.warning("%s has no {%s} placeholder", field, name)
