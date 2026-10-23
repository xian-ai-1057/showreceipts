# showreceipts — Project Guide for Claude

> 原名 Tag RAG（2026-10-19 改名）。Tier 2 程式以 git tag `tier2-final` 保存。

## What this is

不綁定任何 RAG 框架的引用層，一次處理一輪問答。v1 依 [issue #9](https://github.com/xian-ai-1057/showreceipts/issues/9)（唯一的 spec）重寫，拆成 ticket #11–#20。#9 末尾的「開跑前裁決（2026-10-20）」優先於它上方的內文與 Spec 106。

對外三個操作：`split`（Document → Passage）、`answer`（問題 + Passage → Cited Answer）、`postprocess`（外部答案 + Passage → Cited Answer）。Python API、CLI、demo HTTP 端點一一對應，輸入輸出是同一套 JSON，欄位名以 `models.py` 為準（例如 Citation 是 `{n, passage}`）。使用說明與架構圖見 README。

## 架構

```
split(Document) ─┐
Adapter(外部結果) ┴→ Passage 清單 → select → answer: prompts → Generator → _finalize → Cited Answer
                                   外部答案 → postprocess ─────────────────→ _finalize
_finalize = markers.resolve（正規化、重編號、刪 Fabricated Marker）→ Citation → quality.build_quality_report
```

不容易從程式碼一眼看出的不變式：

- **`answer` 從不自己選段**。select 由呼叫端明確呼叫：`cli._answer` 與 demo 的 `/answer` 在 document 和 passages 兩條路徑都先 select 再 answer。
- **編號**：`answer` 先去重（`passages.dedupe`），再依給定順序編 1..M。`postprocess` 以原始清單位置（含重複）加上 `input_marker_base` 對應編號，重複者收斂到第一次出現的 Passage。兩個入口只有在「ID 不重複且 base=1」時結果相同（裁決 8）。從不依 `score` 重排。
- **豁免區只在原始答案上判定**（fenced code、inline code、純網址）。`markers.resolve` 一併回傳處理後答案中的 `marker_spans`，`quality.py` 用它，不重掃處理後的答案。`marker_spans` 不在 JSON 裡，所以只有前端重掃（見下面 `citationMarkers`）。
- **Quality Report 的 `sentence` 是答案的逐字子字串**；`demo/index.html` 依序用 `indexOf` 定位句子，以 `sentence_index` 對回 Uncited Sentence。改句切分時兩邊要一起看。
- **Quality Report 只回報**：建構時拋例外就記 warning、`quality_report=None`，答案照常回傳。
- **Splitter**：每種格式的 reader 把檔案讀成 `(Locator, 內文)` 區段，再由同一套切段邏輯切成 Passage，Passage 不跨區段（PDF 一頁一個區段）。Passage ID 是 `sha256(位元組)[:12]:序號`。`pypdf`、`docx` 只在 reader 函式內 lazy import。缺 extra 拋 `ImportError`（訊息附安裝指令）；不支援或讀不了的檔案拋 `ValueError`。
- **錯誤對應**：CLI 接住 `OSError`、`ValueError`、`ImportError`、`GeneratorError`，訊息寫到 stderr、exit 1。demo 的 `GeneratorError` 回 502；輸入驗證、split 的 `ValueError`／`ImportError` 回 422；本文都是 `{"detail": ...}`。呼叫端自己的 Generator 拋的例外原樣往上拋。
- **模型端點設定**：`cli.default_generator` 讀 `SHOWRECEIPTS_BASE_URL`、`SHOWRECEIPTS_MODEL`、`SHOWRECEIPTS_API_KEY`、`SHOWRECEIPTS_TEMPERATURE`（`default` 表示不送 temperature），CLI、demo、LangChain 範例共用。核心套件不讀環境變數或 `.env`。
- **demo 前端的 `citationMarkers`（`index.html` 的 `<markers-port>` 區塊）是 `markers.py` 豁免判定的逐步移植**。`tests/test_demo_page.py` 用 node 拿 `test_markers.py` 的表格與隨機答案比對兩者；改了豁免規則、這個測試紅了，就同步改 `index.html`。
- **頂層 `__all__`** 是四個操作、`Selector`／`Generator` 型別與資料模型（清單由 `test_isolation.py` 釘住）。`showreceipts.adapters`、`quality.build_quality_report`、`prompts.build_prompt` 從子模組匯入。
- `data/richart_passages.json` 必須等於 `from_arrkb(data/sample_reranked.json)`（`tests/test_adapters.py` 檢查）。arrkb 欄位對應改了就用 adapter 重新產生這個檔案。

## 模組地圖

| 位置 | 內容 |
|---|---|
| `src/showreceipts/models.py` | 資料模型——**唯一的介面契約，鎖定** |
| `src/showreceipts/config.py` | `ShowReceiptsConfig`（frozen）——同屬鎖定的契約 |
| `src/showreceipts/pipeline.py` | `answer`、`postprocess` 與兩者共用的 `_finalize` |
| `src/showreceipts/passages.py` | `dedupe`：重複 ID 只留第一個 |
| `src/showreceipts/markers.py` | `resolve`：marker 群組解析、正規化、重編號、刪除 Fabricated Marker、豁免區 |
| `src/showreceipts/prompts.py` | 預設 prompt、`build_prompt`、模板單趟替換 |
| `src/showreceipts/generators.py` | `Generator` 型別、`OpenAICompatGenerator`（stdlib HTTP、重試）、`GeneratorError` |
| `src/showreceipts/quality.py` | `build_quality_report`：句切分、3-gram 支持度、NUM／DATE 實體、Uncited Sentence |
| `src/showreceipts/selector.py` | `Selector` 型別、`select`（字元 bigram BM25，超過預算才挑） |
| `src/showreceipts/splitter.py` | `split`：Markdown／純文字／PDF／DOCX reader 與共用的切段邏輯 |
| `src/showreceipts/adapters.py` | `from_arrkb`、`from_langchain`（duck typing，不 import LangChain） |
| `src/showreceipts/cli.py` | `main(argv=None, *, generator=None) -> int`、`default_generator`；console script `showreceipts` |
| `demo/app.py` | FastAPI `create_app(generator=None)`；HTTP 請求模型（不屬於契約）也在這裡 |
| `demo/index.html` | 單一 HTML 前端，原生 JS／CSS，無 build |
| `examples/langchain_postprocess.py` | LangChain 0-based 答案 → `postprocess(input_marker_base=0)` |
| `data/` | `sample_reranked.json`（arrkb 樣本）、`richart_passages.json`（貼上模式預填）、`richart.md`（上傳模式範例） |
| `docs/uat-v1.md` | v1 UAT 紀錄（真模型與假 Generator 模擬檢查） |
| `specs/archive/` | Tier 2 時期的 Spec 100–106，只供參考 |

新功能先找現有模組放；只有放不進去、又能讓架構更好畫時才新增檔案。

## 規則

- **可讀性最優先**：模組數量與層級以「能自己重畫架構」為準，不為抽象而抽象。
- 核心套件只 import stdlib 與 Pydantic v2，套件內部一律相對 import（`tests/test_isolation.py` 強制）；框架、demo 程式放在套件之外。
- 契約（`models.py`、`config.py`）要改，先改 #9 並經 Lead（KEE）同意。
- 術語依 GLOSSARY.md；與 ADR 衝突時明確提出，不要默默推翻。
- 格式與 lint 由 ruff 管（設定在 `pyproject.toml`）；註解密度、測試切面、對抗式檢查等判斷型規則在 `CODING_STANDARDS.md`，寫測試前與 review 時讀。

## 測試

- 檢查指令（CI 跑同一組，見 `.github/workflows/ci.yml`）：`uv sync --all-extras && uv run --all-extras ruff check && uv run --all-extras ruff format --check && uv run --all-extras pytest -q`。全部離線，模型一律用假 Generator；需要真模型的測試標 `requires_ollama`，`-m requires_ollama` 才跑
- 測試放哪一層、怎麼命名見 `CODING_STANDARDS.md`「測試切面」
- 真模型檢查：`uv run --env-file .env --all-extras showreceipts answer …`；demo 用 `.claude/launch.json` 的 `demo`（port 8765）
- `conftest.py` 的 autouse fixture 把 `SHOWRECEIPTS_BASE_URL` 指向關閉的 port，並設 `NO_PROXY=*`；不小心用到預設 Generator 的測試會很快失敗，不會打到真模型或 proxy
- golden fixtures 在 `tests/fixtures/golden/`，空白依 #9 裁決 6（例如 `0.3%。`，不是 Spec 106 的 `0.3% 。`）

## /implement-spec

implementer 與 merger 的 repo 規則見 `docs/agents/implement-spec.md`。

## Agent skills

### Issue tracker

Issues and specs live in this repo's GitHub Issues (`xian-ai-1057/showreceipts`). See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
