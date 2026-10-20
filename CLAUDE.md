# showreceipts — Project Guide for Claude

> 原名 Tag RAG（2026-10-19 改名）。Tier 2 程式以 git tag `tier2-final` 保存。

## What this is

不綁定任何 RAG 框架的引用層，一次處理一輪問答。依 [issue #9](https://github.com/xian-ai-1057/showreceipts/issues/9)（唯一的 spec）重寫中，拆成 ticket #11–#20，依 GitHub 上的 blocking 關係開工。

對外三個操作：`split`（Document → Passage）、`answer`（問題 + Passage → Cited Answer）、`postprocess`（外部答案 + Passage → Cited Answer）；Python API、CLI、demo HTTP 端點一一對應，輸入輸出是同一套 JSON。

## 結構

檔名已定案（2026-10-20，見 #9「開跑前裁決」）；尚未建立的檔案由對應 ticket 新增，不要另取名字。

| 位置 | 內容 | ticket |
|---|---|---|
| `src/showreceipts/models.py` | 資料模型——**唯一的介面契約，鎖定** | v1-01 |
| `src/showreceipts/config.py` | `ShowReceiptsConfig`——同屬鎖定的契約 | v1-01 |
| `src/showreceipts/passages.py` | Passage 去重（重複 ID 只留第一個） | v1-02 |
| `src/showreceipts/markers.py` | Citation Marker 解析、正規化、重編號、刪除 Fabricated Marker | v1-02、v1-05 |
| `src/showreceipts/pipeline.py` | `answer`、`postprocess` 與兩者共用的 `_finalize` | v1-02、v1-03 |
| `src/showreceipts/prompts.py` | 預設 prompt 與模板組裝 | v1-03 |
| `src/showreceipts/generators.py` | `Generator` 型別、`OpenAICompatGenerator`、`GeneratorError` | v1-03 |
| `src/showreceipts/quality.py` | Quality Report | v1-07 |
| `src/showreceipts/adapters.py` | `from_arrkb`、`from_langchain` | v1-06 |
| `src/showreceipts/splitter.py` | `split`，含 Markdown／純文字／PDF／DOCX 讀取 | v1-08、v1-09 |
| `src/showreceipts/selector.py` | `select`（字元 bigram BM25） | v1-08 |
| `src/showreceipts/cli.py` | `main(argv=None, *, generator=None) -> int`；console script `showreceipts` | v1-02 |
| `demo/app.py` | FastAPI `create_app(generator=None)`；請求模型也放這裡 | v1-02 |
| `demo/index.html` | 單一 HTML 前端 | v1-04 |
| `examples/langchain_postprocess.py` | LangChain 範例腳本 | v1-06 |
| `data/sample_reranked.json` | arrkb 樣本 | — |
| `data/richart_passages.json`、`data/richart.md` | Richart 範例（貼上模式、上傳模式） | v1-04、v1-08 |
| `tests/conftest.py` | `fake_generator` fixture；離線測試的端點固定指向關閉的 port | — |
| `tests/fixtures/golden/` | golden fixtures | — |
| `tests/fixtures/docs/` | `tiny.md`、`tiny.txt`、`tiny_text.pdf`（兩頁文字）；`tiny.pdf` 是兩張空白頁，當掃描型 PDF 的負面樣本 | — |
| `specs/archive/` | Tier 2 時期的 Spec 100–106，只供參考 | — |

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

- `uv sync --all-extras` 後跑 `uv run --all-extras pytest -q`；全部離線，模型一律用假 Generator，不打真 Ollama（需要真模型的測試標 `requires_ollama`，預設不執行，`-m requires_ollama` 才跑）
- 測「沒裝 extra」的情境時用 `monkeypatch.setitem(sys.modules, "pypdf", None)` 模擬，不用 `importorskip`
- 只測外部行為：呼叫公開函式、比對輸出 JSON，不測內部函式
- 命名：`test_<feature>_<scenario>_<expected>`

## AFK 規則（/implement-spec 的 implementer 與 merger）

- #9 的 Testing Decisions 就是已同意的 seam；`/tdd` 不必再向使用者確認。
- 不得修改 `models.py`、`config.py` 與 issue #9。非改不可時停下，回報 `BLOCKED: contract` 並附上欄位 diff；merger 拒絕任何碰到這兩個檔的分支。
- README 與 CLAUDE.md 只由 v1-10（#20）改寫，其他 ticket 不動。
- commit 標題：`v1-NN (#N): …`。
- merger 每次合併後在 integration tip 上跑 `uv sync --all-extras && uv run --all-extras pytest -q`，紅燈就退回 implementer；stage 時明確列出檔名，不用 `git add -A`。

## Agent skills

### Issue tracker

Issues and specs live in this repo's GitHub Issues (`xian-ai-1057/showreceipts`). See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
