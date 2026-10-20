# showreceipts — Project Guide for Claude

> 原名 Tag RAG（2026-10-19 改名）。Tier 2 程式以 git tag `tier2-final` 保存。

## What this is

不綁定任何 RAG 框架的引用層，一次處理一輪問答。依 [issue #9](https://github.com/xian-ai-1057/showreceipts/issues/9)（唯一的 spec）重寫中，拆成 ticket #11–#20，依 GitHub 上的 blocking 關係開工。

對外三個操作：`split`（Document → Passage）、`answer`（問題 + Passage → Cited Answer）、`postprocess`（外部答案 + Passage → Cited Answer）；Python API、CLI、demo HTTP 端點一一對應，輸入輸出是同一套 JSON。

## 結構（逐張 ticket 補齊）

| 位置 | 內容 |
|---|---|
| `src/showreceipts/models.py` | 資料模型——**唯一的介面契約，鎖定** |
| `src/showreceipts/config.py` | `ShowReceiptsConfig`——同屬鎖定的契約 |
| `tests/fixtures/golden/` | golden fixtures |
| `data/sample_reranked.json` | arrkb 樣本，供 Richart 範例與 Adapter 測試 |
| `specs/archive/` | Tier 2 時期的 Spec 100–106，只供參考 |

## 規則

- **可讀性最優先**：模組數量與層級以「能自己重畫架構」為準，不為抽象而抽象。
- 核心套件只 import stdlib 與 Pydantic v2，套件內部一律相對 import（`tests/test_isolation.py` 強制）；框架、demo 程式放在套件之外。
- 契約（`models.py`、`config.py`）要改，先改 #9 並經 Lead（KEE）同意。
- 術語依 GLOSSARY.md；與 ADR 衝突時明確提出，不要默默推翻。

## 程式碼風格

- Python 3.11+；型別寫 `str | None`，不用 `Optional`
- DTO 用 Pydantic v2，`model_config = ConfigDict(extra="forbid")`
- logger 用 `logging.getLogger(__name__)`；套件本身不設定 logging
- 預設不寫註解，只在非顯然的不變式或 workaround 加單行註解；docstring 只寫 module-level 與複雜邏輯

## 測試

- `uv run pytest -q`；全部離線，模型一律用假 Generator，不打真 Ollama（需要真模型的測試標 `requires_ollama`）
- 只測外部行為：呼叫公開函式、比對輸出 JSON，不測內部函式
- 命名：`test_<feature>_<scenario>_<expected>`

## Agent skills

### Issue tracker

Issues and specs live in this repo's GitHub Issues (`xian-ai-1057/showreceipts`). See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
