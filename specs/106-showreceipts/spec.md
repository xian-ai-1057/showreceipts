# Spec 106 — showreceipts（框架無關引用層）

> 對應 [ADR-0001](../../docs/adr/0001-framework-agnostic-citation-layer.md)、[GLOSSARY.md](../../GLOSSARY.md)、[相關專案調查](../../docs/research/related-projects.md)，以及 Lead（KEE）已拍板的決策 D1–D28（本文以 `Dn` 標註出處）。
> 上游：Spec 100（`src/*` 拆檔與 DTO）、Spec 103（對話歷史）、Spec 104（品質評估演算法）、Spec 105（UI 整合）——本 spec 取代其中「檢索之後」的部分，其餘保留為 Demo Host。
> 下游：內部 demo（D2、D28）。之後的 IT 移交 spec、抽成獨立 pip 套件、LlamaIndex Adapter 都不在本 spec 範圍。

---

## 1. Context

Tier 2 的 citation 能力（`[n]` 引用、首次出現順序重編號、移除編造編號、句級品質檢查）已在 demo 中驗證，但它和本地 RAG 綁死，無法放到 production arrkb 或其他 RAG 框架後面用。痛點：

1. **生成與後處理綁在 LangChain + Chroma 上**：`src/rag_chain.py` import `langchain_core.messages`，`src/llm.py` 建 `ChatOpenAI`；工作型別 `RetrievedChunk` 的欄位（`context_id` / `file_id` / `filename` / `page` / `chunk_index`）是 Chroma / arrkb 專屬，arrkb 路徑只好在 `to_retrieved_chunk()` 把 `chunk_index` 填假值 0。LlamaIndex、Haystack 或自研 arrkb 若要用，得多帶整套 LangChain。
2. **只認 `[n]` 一種標記**：`src/utils.py::CITE_RE = \[(\d+)\]`。小模型常輸出 `[1, 2]`、`[1-3]`、`[1、3]`，這些既不會計入 Citation，也不會被當成 Fabricated Marker 移除，原樣留在答案裡（調查文件「可借鏡的做法」第 1 點）。
3. **品質檢查漏掉「有數字卻沒標來源」的句子**：Spec 104 只對有 marker 的句子算 3-gram 支持度、對實體做 substring 檢查；一句「一般消費回饋為 0.3%。」沒有任何 marker，數字又剛好在某段資料裡：實體檢查不會標它，句級檢查只把它算成一般的 unsupported，和「有標來源但重疊度低」的句子無從區分（groundcite 的覆蓋率做法，調查文件第 2 點）。
4. **沒有「只做後處理」的入口**：LlamaIndex CitationQueryEngine、LangChain 產生的答案無法交給本專案做正規化、重編號、移除 Fabricated Marker 與品質檢查。
5. **介面文字寫死在核心流程**：空檢索時 `query()` 回「依現有資料無法回答：知識庫目前是空的，請先在「文件管理」分頁上傳文件。」——「上傳文件」是 Streamlit 介面的概念，不該出現在可接任何框架的模組裡。
6. **外部 Passage 被誤標為過期**：`app.py::render_citations` 以「Chroma 查不到」判斷 stale，外部注入的 arrkb Passage 本來就不在 Chroma，因此每筆都被加上「⚠️ 文件已更新或被刪除」。

本 spec 把「檢索之後」的那一段抽成 repo 內的獨立子套件 **`src/showreceipts/`**（D1、D8、D9）：輸入是 Passage 清單，模型以注入的 Generator 呼叫，模組只依賴 Pydantic v2。本地檢索、loaders、chunking、Chroma、對話歷史與 Streamlit 降為 Demo Host（D4）。目標是內部 demo（D2）；IT 移交與抽套件之後再做。

---

## 2. Scope

### In scope

- 新增 `src/showreceipts/` 子套件（§4.1），內容：
  - 最小輸入型別 `Passage` 與輸出型別 `Citation` / `CitedAnswer` / `QualityReport`（D6、D19、D20）
  - 唯一設定物件 `ShowReceiptsConfig`（D19）
  - 兩個公開入口 `answer()` 與 `postprocess()`（D10、D19）
  - Citation Marker 解析：`[n]`、`[n][m]`、`[n, m]`（含全形逗號與頓號）、`[n-m]`，輸出一律正規化為逐一的 `[n][m]`（D11）；格式不良的近似 marker 寬鬆解析（暫定，§8 Q20）
  - D11 未列的寫法（全形括號、en dash、波浪號等）暫定不認，code / URL 內的 marker 暫定不豁免——待 §8 Q5、Q25 裁決
  - 依首次出現順序重編號、移除 Fabricated Marker、壓縮連續空白（沿用 Tier 1 規則）
  - 預設繁中 prompt（現行六條作答規則）；system prompt、user prompt 模板、Passage 區塊模板皆可整段覆寫（D15；範圍見 §8 Q15）；作答語言可設定（D15；範圍見 §8 Q18）
  - No-Answer Reply（D16）
  - Quality Report：自 `src/eval/` 移入、預設開啟、只報不攔，新增 Uncited Sentence 檢查（D7、D12、D13）
  - `Generator` 型別與預設的 OpenAI 相容 Generator（stdlib 實作）（D5、D21）
  - Adapter：arrkb dict、LangChain（duck typing，不 import langchain）（D6）
  - import 隔離的自動化檢查（D8、D21）
- Demo Host 調整（§4.15）：`src/rag_chain.py`、`src/llm.py`、`src/retrieval.py`、`src/utils.py`、`rag.py`、`src/history/`、`app.py`、新增 `src/citation_view/`、`examples/langchain_postprocess.py` 與 `data/demo/richart_sample.md`（§8 Q11）
- Streamlit「外部檢索結果」模式：貼上 arrkb JSON（預填 `data/sample_reranked.json`），外部 Passage 的 Citation 顯示快照、不加 stale 標籤（D17）
- 對話歷史 `StoredCitation` v2（新契約於本 spec `contracts/demo_host_history_schema.py`）；舊 `data/history.sqlite` 不遷移（D27）
- 契約：`contracts/showreceipts_schema.py`、`contracts/demo_host_history_schema.py` 與 golden fixtures
- 文件：README、CLAUDE.md、`specs/plan.md`、`specs/CLAUDE.md` 目錄清單（D28）
- 專案改名：`pyproject.toml` 的 `name` 與 README / CLAUDE.md 標題改為 showreceipts（D9 字面解讀；暫定，§8 Q13）
- Spec 100 contracts 標記 superseded（D18）

### Out of scope

- **Streaming**（**第 1 次重複提醒**）：重編號需要完整答案，demo 不做 streaming，留 backlog（D26）
- **逐字 quote 驗證模式**（**第 1 次重複提醒**）：rag-citation-gate / citation-guard 式「附原文 quote 再逐字比對」延到 demo 之後（D14）
- **LLM-as-judge**（**第 1 次重複提醒**）：Quality Report 永遠不呼叫模型（Spec 104 §3.1 延續）
- **NER 套件（spaCy / hanlp / ckip / jieba）**（**第 1 次重複提醒**）：實體與 Uncited Sentence 判定都是純 regex
- **依 score 重排 Passage**（**第 1 次重複提醒**）：Passage 依呼叫端給定順序（上游 rerank 順序）編 1..N，`score` 只供顯示（D22）
- **攔截、改寫或拒答**（**第 1 次重複提醒**）：Quality Report 只回報；要顯示、警告或拒答由呼叫端決定（D12）
- **模組內 import LangChain / Chroma / Streamlit**（**第 1 次重複提醒**）：`src/showreceipts/` 只准 stdlib + Pydantic v2，連 `openai`、`httpx`、`pydantic_settings` 都不行（D8、D21）
- 依賴 groundcite / citeformer / LlamaIndex / LangChain 的引用功能（D10：自建）
- LlamaIndex Adapter（D6：之後再做）
- IT 移交 spec（D2）、抽成獨立 pip 套件（D8：demo 被認可後）
- 遷移舊 `data/history.sqlite`（D27：Lead 手動刪除）
- Grammar 限制解碼、供應商原生引用（Anthropic Citations API）當 Generator
- repo 目錄（`tag_rag`）與 git remote 改名（§8 Q13 只涵蓋套件名稱與文件標題）
- 調整 Spec 104 門檻（`SUPPORT_OVERLAP_THRESHOLD = 0.15`、`NGRAM_SIZE = 3`）或把門檻開成設定
- Quality Report 持久化進 SQLite（Spec 104 backlog）
- 改 `context_id` 演算法、loaders、chunking、vectorstore、`Settings` 預設值
- Tier 3 backlog：多使用者隔離、OCR、URL fetch
- UI 美化（Spec 105 延續）

---

## 3. 核心設計決策

### 3.0 決策追溯表

| D | 內容摘要 | 本 spec 落點 |
|---|---|---|
| D1 | 檢索之後的部分成為框架無關模組 | §3.1 |
| D2 | 下一里程碑是內部 demo；IT 移交 spec 之後 | §1、§2 Out of scope |
| D3 | 術語依 GLOSSARY.md | §3.3、§4.16 |
| D4 | 模組只管檢索之後；其餘為 Demo Host | §3.1、§4.2 |
| D5 | Generator 為注入 callable；不依賴 LangChain；預設 OpenAI 相容 Generator；prompt 組裝與後處理是 pure function | §3.2、§4.9、§4.12 |
| D6 | 自訂 Passage + 各框架 Adapter（先 arrkb、LangChain） | §3.3、§4.13 |
| D7 | 品質評估移入模組，選配、預設開啟 | §3.8、§4.11 |
| D8 | repo 內隔離子套件，之後再抽 | §3.12、§4.14 |
| D9 | 名稱 showreceipts，路徑 `src/showreceipts/`，模組與專案同名 | §3.1、§4.15.8、§8 Q13 |
| D10 | 自建；另支援「只做後處理」 | §3.4、§3.13 |
| D11 | marker 解析格式與正規化輸出 | §3.6、§4.8、§8 Q5、Q20、Q21、Q22、Q25 |
| D12 | Quality Report 只報不攔 | §3.8、§4.10（例外防護）、§8 Q23 |
| D13 | 新增 Uncited Sentence 檢查 | §3.9、§4.11.3 |
| D14 | 逐字 quote 驗證延後 | §2 Out of scope |
| D15 | 預設繁中 prompt、可整段覆寫、語言可設定 | §3.10、§4.9、§8 Q15、Q18 |
| D16 | 零 Passage 不呼叫 Generator，回 No-Answer Reply；「請先上傳文件」移到 Demo Host | §3.11、§4.10、§4.15.2、§8 Q2、Q17 |
| D17 | Streamlit 外部檢索結果模式；外部 Citation 不加 stale 標籤；LangChain 範例腳本 | §3.14、§4.15.5–§4.15.7 |
| D18 | 依 SDD 流程；Spec 100 contracts 隨遷移標記 superseded | §3.15、§7 |
| D19 | 恰好兩個公開入口，皆回 Cited Answer；選項集中於一個設定物件 | §3.4、§4.3、§4.4 |
| D20 | Passage 欄位 | §4.5 |
| D21 | 模組唯一第三方依賴為 Pydantic v2 | §3.12、§4.12、§4.14 |
| D22 | 依給定順序編 1..N，不依 score 重排 | §3.5、§4.7 |
| D23 | 重複 Passage ID 只留第一個 | §3.5、§4.7 |
| D24 | post-process 時呼叫端須依原 prompt 順序傳 Passage；可選 0-based | §3.5、§4.7 |
| D25 | Python 3.11+ | §3.12 |
| D26 | demo 不做 streaming | §2 Out of scope |
| D27 | 舊 history.sqlite 不遷移，Lead 手動刪 | §4.15.4、§7 |
| D28 | demo 完成定義（三條路徑、Richart 問題、測試全綠、README） | §6 AC #25–#27、§8 Q11 |

### 3.1 模組邊界：只管「檢索之後」

**決定**：`src/showreceipts/` 負責且只負責：組編號 context → 呼叫 Generator → 解析、正規化、重編號 Citation Marker → 移除 Fabricated Marker → Quality Report（D4）。檢索、chunking、vector store、loaders、對話歷史與 Streamlit 都是 Demo Host。模組與專案同名 showreceipts（D9）。

**為何**：
- ADR-0001：實際要服務的是 arrkb 與其他未定框架，它們都已自帶檢索；本地檢索只是示範（D1）
- 邊界畫在「Passage 清單進、Cited Answer 出」，任何框架只要寫一個 Adapter 就能接

**影響**：`src/citation.py`、`src/prompts.py`、`src/eval/`、`src/utils.py::CITE_RE` 移入模組；`src/rag_chain.py` 縮成 Demo Host 膠水（§4.2）。

### 3.2 Generator 以 callable 注入，預設 OpenAI 相容 Generator 用 stdlib 實作

**決定**：`Generator = Callable[[str, str], str]`，即 `(system_prompt, user_prompt) -> answer_text`（D5）。模組另附 `OpenAICompatGenerator`，以 `urllib.request` 呼叫 `{base_url}/chat/completions`，預設 `temperature=0`（Tier 1 行為）、非 streaming（D26）。

**為何**：
- verbatim-citation-gate 採用同一形狀，證明此介面在別的專案也行得通（調查文件第 5 點）；任何 SDK 都能包成一個兩參數的 lambda，例如：

  ```python
  # LangChain（langchain-core ≥ 1.0：AIMessage.text 是 property，content 為 block list 時也回純文字）
  gen = lambda s, u: llm.invoke([SystemMessage(s), HumanMessage(u)]).text
  # LlamaIndex
  gen = lambda s, u: llm.chat([ChatMessage(role="system", content=s),
                               ChatMessage(role="user", content=u)]).message.content or ""
  ```

  直接用 `.content` 時，reasoning 模型或 Anthropic 等回傳的 content block list 不是 `str`，模組會拋 `TypeError`（§4.3；D5 字面：Generator 回 `str`）
- D21 只准 Pydantic 一個第三方依賴，因此預設 Generator 不能用 `openai` SDK 或 `httpx`，只能用 stdlib

**影響**：
- Demo Host 的 `src/llm.py` 不再建 `ChatOpenAI`，改為回傳指向 Ollama 的 `OpenAICompatGenerator`（§4.15.1）
- 預設逾時 600 秒、重試 2 次，比照現行 `ChatOpenAI`（未設 `request_timeout` / `max_retries`，沿用 openai SDK 預設）；錯誤包成新公開型別 `GeneratorError`（暫定，§8 Q19）
- 測試直接注入假 Generator，不再 `patch("src.rag_chain._get_llm")`
- `generator` 為必填參數；是否允許 `None` 時自動建預設 Generator 見 §8 Q4

### 3.3 Passage 是唯一輸入型別，框架知識只放在 Adapter

**決定**：模組定義自己的 `Passage`（`id` / `text` / `source` / `locator` / `score` / `metadata`，D20），先提供 arrkb dict 與 LangChain 兩個 Adapter（D6）。術語一律依 GLOSSARY.md（D3），舊名對照見 §4.16。

**為何**：GLOSSARY「Adapter：引用層對外部框架的所有認識都只存在於 Adapter」；`RetrievedChunk` 的 `chunk_index`、`file_id` 對多數框架沒有意義。

**影響**：
- `RetrievedChunk`、`to_retrieved_chunk()`、`coerce_reranked()` 刪除；arrkb 的 `RerankedChunk` 留在 Demo Host，作為本地 `retrieve()` 模擬 production 輸出的型別
- DTO 名稱採 GLOSSARY 名（`Passage`、`CitedAnswer`），不套 `specs/CLAUDE.md` §6 的 `<Feature>DTO` 命名慣例——D3 優先

### 3.4 恰好兩個公開入口，選項集中於一個設定物件

**決定**：
- `answer(question, passages, generator, *, config=None) -> CitedAnswer`：組 prompt、呼叫 Generator、後處理
- `postprocess(answer_text, passages, *, config=None) -> CitedAnswer`：「只做後處理」，處理別的框架產生的答案（D10）
- 所有選項都在 `ShowReceiptsConfig`（D19）

**為何**：兩個入口共用同一個後處理核心（§4.10 `_finalize`）。Passage ID 互不重複且 `input_marker_base=1` 時，同一段原始答案不論從哪個入口進來，正規化、重編號、Fabricated Marker 與 Quality Report 結果完全一致（AC #17）；有重複 ID 或 0-based 時兩個入口的 slot 對照本來就不同（§4.7），結果可以不同（例 19、20 與 `test_postprocess_differs_from_answer_with_duplicate_ids`）。

**影響**：`build_prompt()`（`showreceipts.prompts`）與 `build_quality_report()`（`showreceipts.quality`）是 pure function、可直接匯入，但不列入頂層 `__all__`；Adapter（`from_langchain` 的 `id_key` / `source_key` / `locator_fn`）與 `OpenAICompatGenerator` 的建構參數不屬於 `ShowReceiptsConfig`——D19 的「入口」與「單一設定物件」只約束 `answer()` / `postprocess()`（D19 字面解讀；§8 Q3）。

### 3.5 編號：依給定順序、不重排、重複 ID 取第一個、post-process 對齊原 prompt

**決定**：
- Passage 依呼叫端給定順序（上游 rerank 順序）編 1..N，模組不依 `score` 重排（D22）
- 重複 Passage ID 只保留第一次出現者（D23）
- `postprocess()` 時呼叫端（透過 Adapter）必須依原答案 prompt 的編號順序傳入 Passage；`config.input_marker_base = 0` 時答案中的 `[0]` 指第一個 Passage（D24，對應 LangChain how-to 從 0 編號）
- `answer()` 由模組自己組 prompt，一律 1-based，忽略 `input_marker_base`（D22）

**為何**：上游的 rerank 順序就是相關性判斷；模組再排一次等於覆蓋上游決策。post-process 模式下模組沒看過原 prompt，只能信任呼叫端給的順序。

**影響**：
- post-process 遇到重複 ID 時，marker 編號以「原始清單位置」對應，再收斂到第一次出現的 Passage（§4.7「slot 對照」）。這是 D23 與 D24 合併後的推導，列 §8 Q1 請 Lead 確認
- Citation 與 Quality Report 一律以第一次出現者的內文為準；後出現的同 ID Passage 的內文不進 prompt（answer 模式），也不參與句級支持度與實體檢查。post-process 模式下模型實際看到並引用的若是後者，Quality Report 會把該句判為 unsupported、把句中數字標成 unsupported entity（`test_postprocess_duplicate_later_copy_quality_uses_first_text`；§8 Q1）
- post-process 時重複 ID 不是邊角情況：LlamaIndex ≤ 0.14.23 的 CitationQueryEngine 把同一 node 切出的多個 Source 都沿用原 node ID（§4.13.3）

### 3.6 Citation Marker 解析與正規化

**用語**：本 spec 以「marker 群組」指模型原文中的一組方括號（非 GLOSSARY 術語，只供演算法說明）；Citation Marker 指正規化後的單一 `[n]`；Fabricated Marker 指群組中對不到任何送入 Passage 的單一數字或範圍成員，以及無法解析的項；「slot」指「marker 數字 → Passage 位置」對照（§4.7）。

**決定**：marker 群組是方括號內只含數字、空白 / tab、逗號（`,` / `，`）、頓號（`、`）與 ASCII hyphen-minus `-`，且至少含一個數字的片段。符合 D11 寫法的群組照常解析；格式不良的近似 marker（`[1,,2]`、`[1-]`、`[1 2]`、`[1-2-3]`）寬鬆解析——空項略過、可解析的項照常、其餘項視為 Fabricated（D11「輸出一律正規化」的字面解讀；暫定，§8 Q20）。每個群組改寫為逐一的 `[n]` 串接（無分隔字元），例如 `[1, 2]` → `[1][2]`、`[1-3]` → `[1][2][3]`（D11）。精確 regex 與演算法見 §4.8。

**為何**：Haystack AnswerBuilder（`expand_reference_ranges`）與 groundcite 都容許多種格式；小模型輸出 `[1, 2]` 時，Tier 1 會漏掉整個群組，殘留的舊編號還會指錯 Passage。

**影響**（以下凡 D11 未明定者皆為暫定值）：
- 範圍只認 ASCII hyphen-minus `-`；`a > b` 的反向範圍整段視為 Fabricated Marker；全形括號、en dash、波浪號、全形連字號、分號暫定不認（§8 Q5）
- 括號內任意空白 / tab 容忍（含 `[ 1 ]`、`[1 - 2]`）；列舉與範圍可混用於同一群組（`[3, 1-2]`）（§8 Q5）
- 部分越界的範圍保留界內成員，原群組記入 `fabricated_markers`（例 7、17；§8 Q21）
- 同一數字重複、或不同數字收斂到同一 Passage（重複 ID），照樣輸出重複 marker，不去重——維持 Tier 1 對 `[2][2]` 的既有行為（例 15、23；§8 Q5）
- 不豁免任何上下文：code block、inline code、URL、Markdown 連結文字中的 `[n]` 與正文同樣處理（維持 Tier 1；§8 Q25）；行首的 `[n]`（條列編號、模型照抄的來源清單）也一律視為 Citation Marker（§8 Q22）
- 範圍展開以 O(N) 實作，`[1-99999999]` 不會展開成上億個元素；長度超過 9 位的數字字串視為無限大、不呼叫 `int()`（Python 3.11 起，超過 4300 位數的字串轉 `int` 會拋 `ValueError`）

### 3.7 重編號與 Fabricated Marker 移除：Tier 1 規則原樣保留

**決定**：沿用 `specs/plan.md`「Tier 1 既有行為」表中三條需 Lead 批准才能改的規則：
1. 依答案中首次出現順序重編 1..N
2. Fabricated Marker 從答案文字中刪除（不只是過濾 Citation 清單）
3. 收尾 `re.sub(r" {2,}", " ", ...)`，作用於整段答案

正規化在重編號之前，因此「首次出現」以展開後的書寫順序計（`[3, 1-2]` 的順序是 3、1、2）。

**為何**：這三條是 Tier 1 已驗證、Lead 鎖定的行為；本 spec 只擴充可解析的格式，不改規則。

**影響**：`CitedAnswer.fabricated_markers` 記錄被移除（或部分移除）的原始群組字串，以及刪除群組後前後字元拼接出的群組（§4.8.2 第 3 步），供 UI 與除錯（欄位與記錄單位列 §8 Q14）。

### 3.8 Quality Report：移入模組、預設開啟、只報不攔

**決定**：`src/eval/` 的演算法（句切分、字元 3-gram 支持度、NUM / DATE 實體 substring 檢查、`quality_score`）整段移入 `src/showreceipts/quality/`，行為不變，只改欄位名（`best_match_context_id` → `best_match_passage_id`）與 `EntityFlag.reason` 字串（`"not found in any passage text"`）。`config.enable_quality_report` 預設 `True`（D7）。Quality Report 永遠不改 `answer`；`build_quality_report` 拋例外時，`_finalize` 記 `log.warning`（含 traceback）並令 `quality_report = None`，答案照常回傳（D12「never blocks」；§4.10）。

**為何**：品質檢查只看「答案文字 + 送入的 Passage」，與框架無關，屬於檢索之後；放在 Demo Host 的話其他框架用不到。

**影響**：
- 走 No-Answer Reply 或關閉時 `quality_report = None`（沿用 `app.py` 現行「`retrieved` 為空就不算」的行為）
- `app.py` 不再自行呼叫 `evaluate()`，改讀 `CitedAnswer.quality_report`

### 3.9 Uncited Sentence 檢查

**決定**：Quality Report 新增 `uncited_sentences`：答案中沒有任何 Citation Marker、且去掉行首清單序號後仍含十進位數字的句子（D13）。演算法見 §4.11.3。

**為何**：groundcite 的覆蓋率做法；它把「沒標來源的數字句」單獨列出——golden fixture 中「一般消費回饋為 0.3% 。」的 `[9]` 是 Fabricated Marker，被移除後整句沒有來源，但「0.3%」剛好出現在某段 Passage，實體檢查不會標它，句級檢查也只把它算成一般的 unsupported。

**影響**：
- v1 只以數字判定「事實內容」；中文數字（「三百萬」）、人名、組織名不在範圍（§8 Q6）
- `quality_score` 公式不變：沒有 marker 的句子本來就計為 unsupported
- 模型把 marker 寫在句號之後（「…4,500 元。[1]」）時，Spec 104 的句切分會把 `[1]` 切到下一句，前一句會被標成 Uncited Sentence；本 spec 不改句切分，列 §8 Q7

### 3.10 預設繁中 prompt、可整段覆寫、語言可設定

**決定**：預設 system prompt 是現行 `SYSTEM_PROMPT` 的六條作答規則，第 5 條由「使用繁體中文回答。」改為模板「使用{language}回答。」，`language` 預設「繁體中文」，只代入第 5 條（§8 Q18）。三處皆可整段覆寫（D15）：`config.system_prompt` 給值時原樣使用（此時 `language` 不生效）；`config.user_prompt_template` 覆寫 user prompt；`config.passage_block_template` 覆寫單段 Passage 區塊。placeholder 皆非必填，缺少時只記 `log.warning`（D15「整段覆寫」的字面解讀；暫定，§8 Q15）。

**為何**：
- 預設值下 system prompt 與 user prompt 都與 Tier 1 byte-identical（已以 `data/sample_reranked.json` 實測），不改變現有 demo 的模型行為
- 需要連整體 context 排版都自訂（例如區塊間的分隔、把問題放進 system prompt）的呼叫端，可自行組 prompt、呼叫模型，再走 `postprocess()`（D10）

**影響**：預設區塊 `[n] 來源: {source}（{locator}）` 是 marker 編號與 Passage 對應的契約；覆寫 `passage_block_template` 時，區塊內是否保留 `[{n}]` 由呼叫端負責（缺 `{n}` 時記 warning）。區塊之間固定以 `\n` 串接。

### 3.11 No-Answer Reply

**決定**：去重後沒有任何 Passage 時，`answer()` 不呼叫 Generator，直接回 `config.no_answer_reply`（預設「依現有資料無法回答」）（D16）。`postprocess()` 同樣回 No-Answer Reply，`raw_answer` 保留呼叫端傳入的原文（D16 字面解讀，列 §8 Q2）。

**為何**：沒有 Passage 時任何答案都無從引用；不呼叫模型也省一次延遲。

**影響**：「請先在「文件管理」分頁上傳文件」移到 Demo Host：`query()` 在本地與外部兩條路徑都以 `ShowReceiptsConfig(no_answer_reply=EMPTY_KB_REPLY)` 覆寫，維持現行「本地檢索為空」與「注入空清單」回同一句的行為（`specs/plan.md` Tier 1 表 Empty retrieval 列；外部模式是否改回預設值見 §8 Q17）。空知識庫字串因此與 Tier 1 完全相同（Spec 100 AC #6 的字串部分仍成立；`retrieved == []` 的部分見 §3.15）。

### 3.12 依賴、Python 版本與 import 隔離

**決定**：`src/showreceipts/` 只 import stdlib 與 `pydantic`（D21），內部一律用相對 import；Python 3.11+（D25，`StrEnum` 需要）。以兩個自動化測試強制（§4.14）：AST 掃描與「封鎖框架套件後 import」。

**為何**：D8 要求日後可直接抽成獨立套件；相對 import 讓搬家時不必改任何一行 import。

**影響**：
- 模組不得 import `src.config`、`src.utils` 等任何 Demo Host 模組
- 模組內 logger 一律 `logging.getLogger("rag")`，維持 Spec 100 §5.4 / AC #7「任一 `src` module 的 logger 名稱為 `"rag"`」（暫定；改用 `__name__` 以利 D8 抽套件與否見 §8 Q16）；模組本身不呼叫 `logging.basicConfig`

### 3.13 自建，不依賴現成引用套件

**決定**：不依賴 groundcite、citeformer、LlamaIndex、LangChain 的引用功能（D10）。

**為何**：調查文件結論——沒有一個現成專案同時涵蓋重編號、移除 Fabricated Marker、中文品質檢查與注入任意模型；citeformer 依賴過重且 grammar 解碼無法透過 Ollama OpenAI 相容介面使用。

**影響**：只借鏡做法（多格式 marker、未引用句覆蓋率、callable Generator），不 vendor 程式碼。

### 3.14 Demo Host：外部檢索結果模式、LangChain 範例、無 streaming

**決定**：
- Streamlit 問答分頁新增「檢索來源」切換：本地知識庫／外部檢索結果（貼上 arrkb JSON，預填 `data/sample_reranked.json`）（D17）
- 外部 Passage 的 Citation 只顯示快照，不反查 Chroma、不加「⚠️ 文件已更新或被刪除」（D17）
- 新增 `examples/langchain_postprocess.py`：LangChain 產生 0-based 答案 → `postprocess()`（D17、D28 第三條路徑）
- 新增 `data/demo/richart_sample.md`（由 `data/sample_reranked.json` 產生並 commit），供本地知識庫路徑入庫後問 Richart 問題（D28；暫定，§8 Q11）
- 答案生成完才顯示，無 streaming（D26）
- 舊 `data/history.sqlite` 不遷移（D27）

**為何**：D28 的 demo 完成定義要三條路徑都能現場展示。

**影響**：`StoredCitation` 需要記住引用來自哪條路徑，重載歷史時才能維持「外部不加 stale 標籤」（§4.15.4；欄位設計列 §8 Q10）。

### 3.15 SDD 流程與 contract 汰換

**決定**：本 spec 為單一事實，`contracts/` 鎖死介面；遷移到 §7 步驟 6 時，在 Spec 100 `contracts/chunk_schema.py` 檔頭加 superseded 註記（D18）。

**為何**：Spec 100 的 `RetrievedChunk` / `RagAnswer` / `CitedChunkRef` 在步驟 6 之後已無 runtime 對應。

**影響**：
- Spec 103 `history_schema.py` 與 Spec 104 `quality_report_schema.py` 同樣會失去 runtime 對應；是否比照標記見 §8 Q9。`tests/unit/test_contracts_fixtures.py` 仍驗證舊 contract 檔對自己的 fixture，所以標記後測試照樣綠
- 步驟 6 之後，下列上游 AC 引用的檔案或符號已刪除或改名，改由本 spec 的 AC 取代；`specs/plan.md`「完成定義」的「所有 spec AC 全綠」以本表為準（§7 步驟 8 補註）：

  | 上游 AC | 步驟 6 後 | 取代者 |
  |---|---|---|
  | Spec 100 AC #1（`test_citation.py::test_renumber_basic`） | 測試檔刪除 | 本 spec AC #3 |
  | Spec 100 AC #6（空知識庫 `citations == []`、`retrieved == []`） | `CitedAnswer` 無 `retrieved`；字串不變 | 本 spec AC #10（`passages == []`） |
  | Spec 100 AC #7（logger 名稱 `"rag"`） | 仍成立（§3.12，暫定，§8 Q16） | — |
  | Spec 100 AC #8（`src.prompts` 三個字串 byte-identical） | `src/prompts.py` 刪除 | 本 spec AC #11（比對步驟 4 凍結的 snapshot 檔） |
  | Spec 100 AC #9（`RetrievedChunk` / `RagAnswer` 驗 fixture） | 無 runtime 類別 | contract 檔自驗（`test_contract_fixture`）仍綠 |
  | Spec 103 AC #10 的 runtime 部分（`test_history_store.py::test_schema_fixtures_validate` 以 runtime 模型驗 103 fixture） | runtime 改載 v2 contract，103 fixture 驗不過 | 本 spec AC #24（改驗 106 fixtures）；103 contract 自驗仍由 `test_contract_fixture` 保持綠 |
  | Spec 104 AC #1–#8、#11（`evaluate(answer, retrieved)`、`best_match_chunk_id`） | `src/eval/` 刪除 | 本 spec AC #16（`test_quality_*`） |
  | Spec 104 AC #9（QualityReport 驗 fixture） | 無 runtime 對應 | contract 檔自驗（`test_contract_fixture`）仍綠 |
  | Spec 104 AC #10（`import src.eval.report` 無外部依賴） | 模組刪除 | 本 spec AC #21 |
  | Spec 105 AC #2「`retrieved == []` 時不顯示 QualityReport」 | 欄位改名 | `quality_report is None` 時不顯示（§4.15.6） |

---

## 4. 詳細規格

### 4.1 檔案地圖：`src/showreceipts/`

```
src/showreceipts/
├── __init__.py            # 公開 API + __all__（§4.3）
├── models.py              # Passage / Citation / CitedAnswer + dedupe_passages()
├── config.py              # ShowReceiptsConfig + DEFAULT_* 常數
├── prompts.py             # 預設 prompt 字串 + build_prompt()（pure）
├── markers.py             # MARKER_GROUP_RE + normalize_and_renumber()（pure）
├── pipeline.py            # answer() / postprocess() / _finalize()
├── generators.py          # Generator 型別、OpenAICompatGenerator、GeneratorError
├── quality/
│   ├── __init__.py        # build_quality_report + DTO re-export（含 __all__，§4.3）
│   ├── models.py          # QualityReport / SentenceSupport / EntityFlag / EntityKind / UncitedSentence
│   ├── sentences.py       # split_sentences()（原 src/eval/support.py）
│   ├── support.py         # 3-gram overlap、evaluate_sentence_support()（原 src/eval/support.py）
│   ├── entities.py        # NUM / DATE regex（原 src/eval/entities.py）
│   ├── uncited.py         # find_uncited_sentences()（新）
│   └── report.py          # build_quality_report()（原 src/eval/report.py::evaluate）
└── adapters/
    ├── __init__.py        # from_arrkb / from_langchain（含 __all__）
    ├── arrkb.py
    └── langchain_docs.py  # duck typing，不 import langchain
```

**避免循環 import**：`models.py` 的 `CitedAnswer.quality_report` 需要 `quality.models.QualityReport`，而載入 `quality` 子套件會先執行 `quality/__init__.py`（re-export `build_quality_report` → `report.py`）。因此 `quality/` 內任何檔案在 runtime 都不得 import `..models`：需要 `Passage` / `Citation` 型別的檔案（如 `report.py`）一律 `from __future__ import annotations`，並只在 `if TYPE_CHECKING:` 下 `from ..models import Citation, Passage`。`quality/` 可 import `..markers`（純 regex，無其他依賴）。步驟 3 起 `python -c "import src.showreceipts"` 與 `python -c "import src.showreceipts.models"` 都必須成功（AC #21）。

`models.py`、`config.py`、`quality/models.py` 的類別必須與 `contracts/showreceipts_schema.py` 結構一致：`model_json_schema()` 遞迴去除 `description` 鍵後完全相等，且 model validator 拒絕同樣的非法輸入（AC #20）。最簡單的做法是整段複製 contract 類別。runtime 不得以路徑載入 contract 檔（`src/history/models.py` 的做法在這裡不適用：會讓模組依賴 `specs/` 目錄，抽套件時斷掉）。

### 4.2 搬移與保留對照

| 現有 | 去向 | 備註 |
|---|---|---|
| `src/citation.py::renumber_and_filter` | `src/showreceipts/markers.py::normalize_and_renumber` | 原檔刪除（§7 步驟 6） |
| `src/prompts.py` | `src/showreceipts/prompts.py` | 原檔刪除；刪除前於步驟 4 凍結 Tier 1 snapshot 檔（§7） |
| `src/utils.py::CITE_RE` | `src/showreceipts/markers.py::_SINGLE_MARKER_RE` | `utils.py` 只留 `preview`（Demo Host 用） |
| `src/eval/*` | `src/showreceipts/quality/*` | 原目錄刪除 |
| `src/retrieval.py::RetrievedChunk` / `to_retrieved_chunk` / `coerce_reranked` | 刪除 | 由 `Passage` + `from_arrkb` 取代 |
| `src/retrieval.py::RerankedChunk` / `RerankedKwargs` / `retrieve` | 留在 Demo Host | 本地檢索仍輸出 arrkb schema；`query()` 仍接受 `RerankedChunk` 實例 |
| `src/rag_chain.py::RagAnswer` / `CitedChunkRef` | 刪除 | 由 `CitedAnswer` / `StoredCitation` v2 取代 |
| `src/rag_chain.py::query` | 留在 Demo Host（膠水） | 回傳 `CitedAnswer`（§4.15.2） |
| `src/llm.py::_get_llm`（ChatOpenAI） | 改為 `get_generator()` | 不再 import `langchain_openai`（§4.15.1） |
| `app.py::_CitationView` / `_citation_view` | `src/citation_view/__init__.py`（新，Demo Host） | 抽出 pure 函式以便測試 stale 邏輯（§4.15.5）；依 CLAUDE.md「新模組放 `src/<feature>/`」 |
| `app.py::_format_source` | 留在 `app.py` | 行為不變（`#` → ` → `），本地與外部 Citation 標頭都套用（§4.15.6） |
| `src/history/models.py`、`src/history/__init__.py` | 改載 `specs/106-showreceipts/contracts/demo_host_history_schema.py`；兩者都多匯出 `OriginKind` | §4.15.4 |
| `tests/fixtures/snapshots/eval_*.json` | 新增 `quality_supported.json` / `quality_unsupported.json`（步驟 3）；舊檔於步驟 6.5 刪除 | §5.4 |
| `src/config.py`、`src/logging_setup.py`、`src/loaders/`、`src/chunking.py`、`src/vectorstore.py`、`src/ingest.py` | 不動 | Demo Host |
| — | `examples/langchain_postprocess.py`（新） | Demo Host，可 import langchain |
| — | `data/demo/richart_sample.md`（新） | Demo Host 本地路徑的 demo 文件（§4.15.9；§8 Q11） |

### 4.3 公開 API

```python
# src/showreceipts/__init__.py
__all__ = [
    "answer", "postprocess",                       # 恰好兩個入口（D19）
    "Passage", "Citation", "CitedAnswer",
    "QualityReport", "SentenceSupport", "EntityFlag", "EntityKind", "UncitedSentence",
    "ShowReceiptsConfig", "DEFAULT_NO_ANSWER_REPLY",
    "Generator", "OpenAICompatGenerator", "GeneratorError",
]

# src/showreceipts/adapters/__init__.py
__all__ = ["from_arrkb", "from_langchain"]

# src/showreceipts/quality/__init__.py
__all__ = ["build_quality_report", "QualityReport", "SentenceSupport", "EntityFlag",
           "EntityKind", "UncitedSentence"]
```

頂層 `__all__` 中，`inspect.isfunction` 為真的只有 `answer`、`postprocess`（AC #2）。`build_prompt`、`build_quality_report` 是可直接匯入的 pure function，不算公開入口（§3.4；§8 Q3）。

| 函式 / 類別 | Signature | 出處 |
|---|---|---|
| `answer` | `answer(question: str, passages: Sequence[Passage], generator: Generator, *, config: ShowReceiptsConfig \| None = None) -> CitedAnswer` | `pipeline.py` |
| `postprocess` | `postprocess(answer_text: str, passages: Sequence[Passage], *, config: ShowReceiptsConfig \| None = None) -> CitedAnswer` | `pipeline.py` |
| `Generator` | `Generator = Callable[[str, str], str]`（system_prompt, user_prompt → answer_text） | `generators.py` |
| `OpenAICompatGenerator` | `__init__(self, *, base_url: str, model: str, api_key: str = "", temperature: float = 0.0, timeout: float = 600.0, max_retries: int = 2)`；`__call__(self, system_prompt: str, user_prompt: str) -> str` | `generators.py` |
| `GeneratorError` | `class GeneratorError(RuntimeError)` | `generators.py` |
| `from_arrkb` | `from_arrkb(data: Mapping[str, Any] \| Sequence[Mapping[str, Any]]) -> list[Passage]` | `adapters/arrkb.py` |
| `from_langchain` | `from_langchain(docs: Iterable[Any], *, id_key: str \| None = None, source_key: str = "source", locator_fn: Callable[[Mapping[str, Any]], str] \| None = None) -> list[Passage]` | `adapters/langchain_docs.py` |
| `build_prompt`（非頂層） | `build_prompt(question: str, passages: Sequence[Passage], config: ShowReceiptsConfig \| None = None) -> tuple[str, str]` | `prompts.py` |
| `build_quality_report`（非頂層） | `build_quality_report(answer: str, citations: list[Citation], passages: list[Passage]) -> QualityReport` | `quality/report.py` |

錯誤行為：

| 情況 | 行為 |
|---|---|
| `passages` 內有非 `Passage` 元素 | `TypeError`（訊息含位置 index） |
| `generator` 不是 callable | `TypeError` |
| Generator 回傳非 `str` | `TypeError`（D5 字面；不做 `str()` 轉型，§8 Q19） |
| Generator 自己拋例外 | 原樣往上拋，模組不吞、不重試 |
| `postprocess` 的 `answer_text` 不是 `str` | `TypeError` |
| `OpenAICompatGenerator` 連線 / 逾時 / HTTP / 回應格式錯誤 | 依 §4.12 重試後仍失敗 → `GeneratorError`（以 `raise ... from err` 保留原因） |
| `from_arrkb` 輸入形狀或欄位錯誤 | 只拋 `ValueError`（含 Pydantic `ValidationError`）或 `TypeError`（§4.13.1） |
| `config` 欄位不合法 | 建立 `ShowReceiptsConfig` 時 Pydantic `ValidationError` |
| `build_quality_report` 拋例外 | 不往上拋：`quality_report = None`、記 warning（§4.10，D12） |

`passages` 接受任何 `Sequence`，進入函式後先 `list(passages)`，可重複走訪。

### 4.4 `ShowReceiptsConfig`

`model_config = ConfigDict(extra="forbid", frozen=True)`。

| 欄位 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `system_prompt` | `str \| None` | `None` | `None` → 預設模板代入 `language`；給字串 → 原樣使用（D15） |
| `user_prompt_template` | `str \| None` | `None` | `None` → 預設模板；給字串 → 整段覆寫，`{context_blocks}` / `{question}` 單趟替換、非必填（缺少時 `log.warning`；§8 Q15） |
| `passage_block_template` | `str \| None` | `None` | `None` → 預設區塊（§4.9 `_block`）；給字串 → 每段 Passage 以單趟替換代入 `{n}` / `{source}` / `{locator}` / `{text}`，非必填（缺 `{n}` 或 `{text}` 時 `log.warning`；§8 Q15） |
| `language` | `str`（min_length=1） | `"繁體中文"` | 只代入預設 system prompt 第 5 條（§8 Q18） |
| `no_answer_reply` | `str`（min_length=1） | `"依現有資料無法回答"` | No-Answer Reply（D16） |
| `input_marker_base` | `Literal[0, 1]` | `1` | 只影響 `postprocess()`（D24）；`answer()` 一律 1-based |
| `enable_quality_report` | `bool` | `True` | D7 |

不開放的設定：Spec 104 門檻、連續空白壓縮開關、Passage 區塊之間的分隔字元（固定 `\n`）。

### 4.5 DTO：Passage / Citation / CitedAnswer

模組自有 DTO 一律 `ConfigDict(extra="forbid")`。

**Passage**（D20）

| 欄位 | 型別 | 必填 | 說明 |
|---|---|---|---|
| `id` | `str`（min_length=1） | Y | Passage ID；格式由上游決定，模組不解讀 |
| `text` | `str` | Y | 內文快照（送進 prompt、Quality Report 比對） |
| `source` | `str` | Y | Source；只用於顯示與提示 |
| `locator` | `str` | N（`""`） | Locator，如「第 3 頁」「工作表：年費」；可為空 |
| `score` | `float \| None` | N（`None`） | 上游分數；只供顯示，不排序（D22） |
| `metadata` | `dict[str, Any]` | N（`{}`） | 上游其餘欄位；原樣保留 |

**Citation**

| 欄位 | 型別 | 必填 | 說明 |
|---|---|---|---|
| `n` | `int`（≥1） | Y | 顯示編號，與答案中的 `[n]` 一致 |
| `passage` | `Passage` | Y | 被引用的 Passage（重複 ID 時為第一次出現者） |

**CitedAnswer**

| 欄位 | 型別 | 必填 | 說明 |
|---|---|---|---|
| `answer` | `str` | Y | 正規化 + 重編號 + 移除 Fabricated Marker + 壓縮空白後的答案；可為 `""` 或純空白（§4.10「空答案」） |
| `raw_answer` | `str` | Y | Generator 原始輸出（answer 模式）或呼叫端傳入的 `answer_text`（postprocess 模式）；answer 模式走 No-Answer Reply 時為 `""` |
| `citations` | `list[Citation]` | N（`[]`） | 只含實際被引用者，`n` = 1..len |
| `passages` | `list[Passage]` | N（`[]`） | 去重後、給定順序的全部 Passage；`[]` 代表走了 No-Answer Reply |
| `fabricated_markers` | `list[str]` | N（`[]`） | 含 Fabricated Marker 的原始 marker 群組字串，以及刪除群組後拼接出的群組（§4.8.2 第 3 步），依首次出現、去重（記錄單位見 §8 Q14） |
| `quality_report` | `QualityReport \| None` | N（`None`） | 關閉或 No-Answer 時為 `None` |

`CitedAnswer` 的 model validator 守住不變式：`citations` 的 `n` 必須是 1..K 連號且依序；`passages` 無重複 ID；同一 Passage 在 `citations` 最多出現一次；每個被引用的 ID 都在 `passages` 中。

### 4.6 DTO：Quality Report

| 類別 | 欄位 | 說明 |
|---|---|---|
| `QualityReport` | `quality_score: float`（0..1） | supported 句數 / 總句數；無句子為 1.0 |
| | `sentence_supports: list[SentenceSupport]` | 順序同答案中的句子 |
| | `unsupported_entities: list[EntityFlag]` | NUM 先、DATE 後，同類依出現順序（Spec 104 §5.6） |
| | `uncited_sentences: list[UncitedSentence]` | 順序同答案中的句子（新） |
| `SentenceSupport` | `sentence: str`、`supported: bool`、`best_match_passage_id: str \| None`、`overlap_score: float`（0..1） | 欄位由 `best_match_context_id` 改名 |
| `EntityFlag` | `entity: str`、`kind: EntityKind`、`reason: str` | `reason` 固定 `"not found in any passage text"` |
| `UncitedSentence` | `sentence: str`、`sentence_index: int`（≥0）、`numbers: list[str]`（min_length=1） | 新；`sentence_index` 是在 `split_sentences` 結果中的位置（`sentence_index` / `numbers` 兩欄見 §8 Q14） |
| `EntityKind`（StrEnum） | `per` / `org` / `loc` / `num` / `date` / `misc` | 與 Spec 104 相同；只偵測 `num` / `date` |

### 4.7 編號、去重與 slot 對照

`dedupe_passages` 放在 `models.py`，由 `prompts.py` 與 `pipeline.py` 共用（放在 `pipeline.py` 會與 `prompts.py` 循環 import）。

```python
def dedupe_passages(passages: list[Passage]) -> tuple[list[Passage], dict[str, int]]:
    uniq: list[Passage] = []
    first_index: dict[str, int] = {}          # Passage ID → uniq 中的位置
    for i, p in enumerate(passages):
        if not isinstance(p, Passage):
            raise TypeError(f"passages[{i}] is {type(p).__name__}, expected Passage")
        if p.id not in first_index:
            first_index[p.id] = len(uniq)
            uniq.append(p)
    return uniq, first_index
```

「slot」（spec 內部用語，§3.6）是「答案中的 marker 數字 → `uniq` 中的位置」對照表：

| 入口 | slots |
|---|---|
| `answer()` | `{k + 1: k for k in range(len(uniq))}`——prompt 只列去重後的 Passage，編 1..M |
| `postprocess()` | `{pos + config.input_marker_base: first_index[p.id] for pos, p in enumerate(passages)}`——以**原始清單位置**（含重複）編號，重複者收斂到第一次出現的 Passage（§8 Q1） |

去重時以 `log.warning` 記錄被丟掉的重複 ID 數量。模組任何地方都不讀 `score` 來決定順序（D22）。

### 4.8 Citation Marker 正規化與重編號演算法

#### 4.8.1 Regex

```python
_GROUP_CHARS = r" \t,，、\-"                    # 群組內允許的非數字字元
MARKER_GROUP_RE = re.compile(rf"\[((?:[{_GROUP_CHARS}]*\d)+[{_GROUP_CHARS}]*)\]")   # 至少一個數字
_ITEM_SPLIT_RE = re.compile(r"[ \t]*[,，、][ \t]*")
_NUM_RE = re.compile(r"\d+")
_RANGE_RE = re.compile(r"(\d+)[ \t]*-[ \t]*(\d+)")   # ASCII hyphen-minus
_MULTI_SPACE_RE = re.compile(r" {2,}")          # Tier 1 規則，原樣保留
_SINGLE_MARKER_RE = re.compile(r"\[(\d+)\]")    # 只用在「已正規化」的文字（Quality Report）
_MAX_DIGITS = 9                                 # 超過即視為無限大，不呼叫 int()
_OPEN, _CLOSE = "", ""              # 第 2 步暫代輸出 marker 的私用區字元
```

- `MARKER_GROUP_RE` 認得「方括號內只含數字、空白 / tab、`,`、`，`、`、`、`-`，且至少一個數字」的片段。`(?:[…]*\d)+[…]*` 這種寫法裡字元類與 `\d` 互斥，不會災難性回溯。符合 D11 寫法的群組是它的子集；其餘（`[1,,2]`、`[1-]`、`[1 2]`、`[1-2-3]`）是格式不良的近似 marker（§8 Q20）。不含數字的 `[ ]`、`[-]` 不是 marker；括號內有換行（`[1,\n2]`）也不是
- `\d` 沿用 Tier 1 `CITE_RE` 的 Unicode 語意：全形 `１` 等 Unicode Nd 數字視同 ASCII 數字、前導零照常（`[01]` 即 `[1]`）；上標 `²` 不是 Nd，不認。全形括號 `［1］`、`【1】` 不認（§8 Q5）
- `[n]` 單一 marker 的比對與 Tier 1 完全相同

#### 4.8.2 演算法

```python
def _to_int(digits: str) -> int | float:
    return math.inf if len(digits) > _MAX_DIGITS else int(digits)


def _resolve(body: str, slots: dict[int, int]) -> tuple[list[int], bool]:
    """回傳（可對應到 Passage 的 marker 數字，依書寫順序）與（本群組是否含 Fabricated Marker）。"""
    members: list[int] = []
    fabricated = False
    for item in _ITEM_SPLIT_RE.split(body.strip()):
        item = item.strip(" \t")
        if not item:                                   # 空項（`[1,,2]`、`[1,2,]`）略過
            continue
        if _NUM_RE.fullmatch(item):
            k = _to_int(item)
            if k in slots:
                members.append(k)
            else:
                fabricated = True
        elif rng := _RANGE_RE.fullmatch(item):
            a, b = _to_int(rng[1]), _to_int(rng[2])
            if a > b:                                  # 反向範圍整段視為 Fabricated（§8 Q5）
                fabricated = True
                continue
            hits = [k for k in sorted(slots) if a <= k <= b]   # O(N)，不展開 a..b
            fabricated |= len(hits) != b - a + 1               # 部分越界（§8 Q21）
            members.extend(hits)
        else:                                          # `1-`、`1-2-3`、`1 2`（§8 Q20）
            fabricated = True
    return members, fabricated


def normalize_and_renumber(
    raw: str, slots: dict[int, int]
) -> tuple[str, list[int], list[str]]:
    """回傳（最終答案, 依首次出現順序的 uniq 位置, fabricated_markers）。"""
    order: list[int] = []
    fabricated: list[str] = []
    for m in MARKER_GROUP_RE.finditer(raw):            # 第 1 步：掃描
        members, fab = _resolve(m[1], slots)
        for k in members:
            if slots[k] not in order:
                order.append(slots[k])
        if fab and m[0] not in fabricated:
            fabricated.append(m[0])
    display = {idx: n for n, idx in enumerate(order, start=1)}
    text = MARKER_GROUP_RE.sub(                        # 第 2 步：改寫（以私用區字元暫代）
        lambda m: "".join(f"{_OPEN}{display[slots[k]]}{_CLOSE}" for k in _resolve(m[1], slots)[0]),
        raw,
    )
    while spliced := MARKER_GROUP_RE.search(text):     # 第 3 步：防拼接
        if spliced[0] not in fabricated:
            fabricated.append(spliced[0])
        text = text[:spliced.start()] + text[spliced.end():]
    text = text.replace(_OPEN, "[").replace(_CLOSE, "]")
    return _MULTI_SPACE_RE.sub(" ", text), order, fabricated   # 第 4 步：Tier 1 壓縮
```

步驟說明：
1. **掃描**：依出現順序走訪每個群組，以分隔字元切項。`\d+` 是單一數字、`a-b` 是範圍（展開為界內 slot，遞增）、空項略過、其餘項視為 Fabricated。對得到 slot 的數字，把其 Passage 位置第一次出現時加入 `order`；群組只要含 Fabricated 的數字、範圍成員或無法解析的項，就以原始群組字串記入 `fabricated_markers`（去重）。長度超過 9 位的數字字串視為無限大：單一數字必為 Fabricated，範圍上界為無限大時保留界內成員（例 17、51）
2. **改寫**：每個群組改寫為其可對應數字的 `[display]` 串接；全部對不到則改寫為空字串。同一數字重複、或不同數字收斂到同一 Passage 時照樣重複輸出
3. **防拼接**：刪除群組可能讓前後字元拼成新的群組（`[[9]1]` → `[1]`、`[1-[9]2]` → `[1-2]`）。第 2 步輸出的 marker 以私用區字元 U+E000 / U+E001 暫代，因此第 3 步掃到的群組必定是拼接出來的：一律刪除並把字串依序記入 `fabricated_markers`，重複到沒有為止（每輪至少刪一個群組，必終止）。不變式：最終答案中每個 `MARKER_GROUP_RE` 比對都是 `[k]`、`k ∈ 1..len(citations)`，且 1..len(citations) 都出現（`test_markers_output_markers_all_resolve_to_citations`）。原文若本來就含 U+E000 / U+E001，會被換成方括號——私用區字元，視為不會出現
4. **壓縮**：整段答案做 `re.sub(r" {2,}", " ", ...)`（Tier 1）。只壓縮 ASCII 空白，不動換行與全形空白，也不清掉標點前的單一空白或被清空的括號（例 14、34–39；清理與否見 §8 Q24）
5. **Citation**：`[Citation(n=n, passage=uniq[idx]) for n, idx in enumerate(order, start=1)]`

v1 不豁免任何上下文：code block、inline code、URL、Markdown 連結文字中的 `[n]` 與正文同樣處理，會被重編號、算成 Citation，或被當成 Fabricated Marker 刪除（例 40–42；§8 Q25）。行首的 `[n]`（條列編號、模型違反規則 6 照抄的「[n] 來源: …」清單）也一律視為 Citation Marker（例 32、33；§8 Q22）。

#### 4.8.3 Tier 1 docstring 範例必須保留

```text
範例：
  passages 編號 = [1,2,3,4,5]
  原答：'句A [2]. 句B [4][2][99].'
  order = [2, 4]（99 對不到 slot）
  新答：'句A [1]. 句B [2][1].'
  citations = [Citation(n=1, 原 [2]), Citation(n=2, 原 [4])]
  fabricated_markers = ['[99]']
```

#### 4.8.4 Worked examples（以原型實測；P1..Pn 表示第 n 個 Passage；表中 `\n` 表示換行）

| # | 原答 | N | base | 最終答案 | citations（n=1..） | fabricated_markers |
|---|---|---|---|---|---|---|
| 1 | `句A [2]. 句B [4][2][99].` | 5 | 1 | `句A [1]. 句B [2][1].` | P2, P4 | `[99]` |
| 2 | `年費 NT$4,500 [1-3]。` | 5 | 1 | `年費 NT$4,500 [1][2][3]。` | P1, P2, P3 | — |
| 3 | `回饋 3.8% [1, 2]。` | 5 | 1 | `回饋 3.8% [1][2]。` | P1, P2 | — |
| 4 | `回饋 3.8% [2，1]。` | 5 | 1 | `回饋 3.8% [1][2]。` | P2, P1 | — |
| 5 | `保費 1.3% [1、3]。` | 5 | 1 | `保費 1.3% [1][2]。` | P1, P3 | — |
| 6 | `甲 [3, 1-2]。` | 5 | 1 | `甲 [1][2][3]。` | P3, P1, P2 | — |
| 7 | `乙 [4-7]。` | 5 | 1 | `乙 [1][2]。` | P4, P5 | `[4-7]` |
| 8 | `丙 [3-1] 丁 [2]。` | 5 | 1 | `丙 丁 [1]。` | P2 | `[3-1]` |
| 9 | `戊 [8, 9] 結束。` | 5 | 1 | `戊 結束。` | — | `[8, 9]` |
| 10 | `己 [0][1]。` | 3 | 1 | `己 [1]。` | P1 | `[0]` |
| 11 | `己 [0][1]。` | 3 | **0** | `己 [1][2]。` | P1, P2 | — |
| 12 | `庚 [3] 辛 [2]。` | 3 | **0** | `庚 辛 [1]。` | P3 | `[3]` |
| 13 | `甲 [99] 乙  丙 [1]。` | 3 | 1 | `甲 乙 丙 [1]。` | P1 | `[99]` |
| 14 | `甲 [99]。` | 3 | 1 | `甲 。` | — | `[99]` |
| 15 | `甲 [2][2] 乙 [1, 1]。` | 3 | 1 | `甲 [1][1] 乙 [2][2]。` | P2, P1 | — |
| 16 | `甲 [ 1 , 2 ] 乙 [1 - 2]。` | 3 | 1 | `甲 [1][2] 乙 [1][2]。` | P1, P2 | — |
| 17 | `甲 [1-99999999]。` | 3 | 1 | `甲 [1][2][3]。` | P1, P2, P3 | `[1-99999999]` |
| 18 | `陣列 [a] 與 [1.5] 與 【1】 與 [1–2]。` | 3 | 1 | 原樣不變 | — | — |
| 21 | `甲 [0-2]。` | 3 | **0** | `甲 [1][2][3]。` | P1, P2, P3 | — |
| 22 | `甲 [1-3]。` | 3 | **0** | `甲 [1][2]。` | P2, P3 | `[1-3]` |

重複 Passage ID（A、B、A′；A′ 與 A 同 ID、內文不同）：

| # | 入口 | 原答 | 最終答案 | citations | `passages` |
|---|---|---|---|---|---|
| 19 | `postprocess`（base 1；slots 1→A、2→B、3→A） | `x [3] y [2] z [1]。` | `x [1] y [2] z [1]。` | n1=A（內文取第一個 A）、n2=B | [A, B] |
| 20 | `answer`（prompt 只列 [1] A、[2] B） | `y [2] x [1]。` | `y [1] x [2]。` | n1=B、n2=A | [A, B] |
| 23 | `postprocess`（同例 19） | `x [1-3]。` | `x [1][2][1]。` | n1=A、n2=B | [A, B] |

格式不良的近似 marker（§8 Q20）：

| # | 原答 | N | base | 最終答案 | citations | fabricated_markers |
|---|---|---|---|---|---|---|
| 24 | `甲 [1,,2]。` | 3 | 1 | `甲 [1][2]。` | P1, P2 | — |
| 25 | `甲 [1,2,]。` | 3 | 1 | `甲 [1][2]。` | P1, P2 | — |
| 26 | `甲 [1-] 乙 [2]。` | 3 | 1 | `甲 乙 [1]。` | P2 | `[1-]` |
| 27 | `甲 [1-2-3] 乙 [1 2] 丙 [3]。` | 3 | 1 | `甲 乙 丙 [1]。` | P3 | `[1-2-3]`, `[1 2]` |
| 28 | `甲 [3] 乙 [1,,2]。` | 3 | 1 | `甲 [1] 乙 [2][3]。` | P3, P1, P2 | — |
| 29 | `甲 [1,\n2]。` | 3 | 1 | 原樣不變（括號內換行） | — | — |

正文中的方括號數字（R1；§8 Q21、Q22、Q25）：

| # | 原答 | N | base | 最終答案 | citations | fabricated_markers |
|---|---|---|---|---|---|---|
| 30 | `超商 [7-11] 消費。` | 6 | 1 | `超商 消費。` | — | `[7-11]` |
| 31 | `超商 [7-11] 消費。` | 12 | 1 | `超商 [1][2][3][4][5] 消費。` | P7..P11 | — |
| 32 | `答案如下：\n[1] 年費 4,500\n[2] 回饋 3.8%` | 1 | 1 | `答案如下：\n[1] 年費 4,500\n 回饋 3.8%` | P1 | `[2]` |
| 33 | `回答 [2]。\n\n[1] 來源: a.md（第 1 頁）\n[2] 來源: b.md` | 3 | 1 | `回答 [1]。\n\n[2] 來源: a.md（第 1 頁）\n[1] 來源: b.md` | P2, P1 | — |
| 40 | `` 用 `list[0]` 取值 [1] `` | 3 | **0** | `` 用 `list[1]` 取值 [2] `` | P1, P2 | — |
| 41 | `見 https://x.com/a[2]/b 甲 [1]。` | 3 | 1 | `見 https://x.com/a[1]/b 甲 [2]。` | P2, P1 | — |
| 42 | `[1](http://x) 甲` | 3 | 1 | `[1](http://x) 甲` | P1 | — |

刪除 marker 後的殘留（Tier 1 行為，不清理；§8 Q24）：

| # | 原答 | N | base | 最終答案 | citations | fabricated_markers |
|---|---|---|---|---|---|---|
| 34 | `甲（[9]）乙` | 3 | 1 | `甲（）乙` | — | `[9]` |
| 35 | `甲 ([9]) 乙` | 3 | 1 | `甲 () 乙` | — | `[9]` |
| 36 | `[9] 甲` | 3 | 1 | ` 甲`（開頭留一個空白） | — | `[9]` |
| 37 | `甲 [9]\n乙` | 3 | 1 | `甲 \n乙` | — | `[9]` |
| 38 | `甲　[9]　乙`（U+3000 全形空白） | 3 | 1 | `甲　　乙` | — | `[9]` |
| 39 | `甲 [9]，乙` | 3 | 1 | `甲 ，乙` | — | `[9]` |

Unicode 數字與前導零（沿用 Tier 1 `\d` 語意）：

| # | 原答 | N | base | 最終答案 | citations | fabricated_markers |
|---|---|---|---|---|---|---|
| 43 | `甲 [１][2]。`（全形 １） | 3 | 1 | `甲 [1][2]。` | P1, P2 | — |
| 44 | `甲 ［1］。`（全形括號） | 3 | 1 | 原樣不變 | — | — |
| 45 | `甲 [01]。` | 3 | 1 | `甲 [1]。` | P1 | — |
| 46 | `甲 [00]。` | 3 | **0** | `甲 [1]。` | P1 | — |

防拼接、超長數字、空答案：

| # | 原答 | N | base | 最終答案 | citations | fabricated_markers |
|---|---|---|---|---|---|---|
| 47 | `甲 [[9]1]。` | 3 | 1 | `甲 。` | — | `[9]`, `[1]` |
| 48 | `甲 [1-[9]2]。` | 3 | 1 | `甲 。` | — | `[9]`, `[1-2]` |
| 49 | `甲 [1] 乙 [[9]1]。` | 3 | 1 | `甲 [1] 乙 。` | P1 | `[9]`, `[1]` |
| 50 | `甲 [`＋5000 個 `1`＋`]。` | 3 | 1 | `甲 。` | — | 原群組字串 |
| 51 | `甲 [1-`＋5000 個 `9`＋`]。` | 3 | 1 | `甲 [1][2][3]。` | P1, P2, P3 | 原群組字串 |
| 52 | `[9][8]` | 3 | 1 | `""`（空字串；§4.10「空答案」） | — | `[9]`, `[8]` |
| 53 | `""` | 3 | 1 | `""` | — | — |

例 13 示範連續空白壓縮：移除 `[99]` 留下的兩個空白，與原文「乙  丙」的兩個空白都壓成一個。例 18 中 `[a]`、`[1.5]`、全形括號、en dash 都不是 Citation Marker。例 30、31：正文的「7-11」（超商）寫在方括號裡時會被當成範圍——N < 7 時整段刪除；N ≥ 11 時靜默產生 5 個 Citation 且不記 fabricated（Tier 1 原本保留 `[7-11]`；R1）。

### 4.9 Prompt 組裝

```python
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
```

```python
_USER_PLACEHOLDER_RE = re.compile(r"\{(context_blocks|question)\}")
_BLOCK_PLACEHOLDER_RE = re.compile(r"\{(n|source|locator|text)\}")

def _block(n: int, p: Passage, template: str | None) -> str:
    if template is None:                                            # 預設區塊（Tier 1 同形）
        head = f"[{n}] 來源: {p.source}（{p.locator}）" if p.locator else f"[{n}] 來源: {p.source}"
        return f"{head}\n{p.text}\n"
    values = {"n": str(n), "source": p.source, "locator": p.locator, "text": p.text}
    return _BLOCK_PLACEHOLDER_RE.sub(lambda m: values[m[1]], template)   # 單趟替換

def build_prompt(question, passages, config=None) -> tuple[str, str]:
    cfg = config or ShowReceiptsConfig()
    uniq, _ = dedupe_passages(list(passages))
    system = (
        cfg.system_prompt if cfg.system_prompt is not None
        else DEFAULT_SYSTEM_PROMPT_TEMPLATE.replace("{language}", cfg.language)
    )
    context_blocks = "\n".join(
        _block(n, p, cfg.passage_block_template) for n, p in enumerate(uniq, start=1)
    )
    template = (
        cfg.user_prompt_template if cfg.user_prompt_template is not None
        else DEFAULT_USER_PROMPT_TEMPLATE
    )
    values = {"context_blocks": context_blocks, "question": question}
    user = _USER_PLACEHOLDER_RE.sub(lambda m: values[m[1]], template)   # 單趟替換
    return system, user
```

規則：
- 預設值下 `system == src/prompts.py::SYSTEM_PROMPT`（Tier 1 字串），byte-identical（AC #11）
- Locator 非空時，區塊與 Tier 1 `_BLOCK_TEMPLATE = "[{n}] 來源: {filename}（第 {page} 頁）\n{content}\n"` 同形；Demo Host 給 `locator="第 {page} 頁"`，因此本地與 arrkb 路徑的 user prompt 與 Tier 1 byte-identical（已以 `data/sample_reranked.json` 實測）
- Locator 為空字串時省略括號（「[1] 來源: foo.md」）
- user 模板與區塊模板都以單趟 regex 替換，不用 `str.format`：模板內的其他大括號（如 JSON 範例）不會出錯；Passage 內文或問題中出現字面的 `{question}`、`{n}` 也不會被二次替換
- 覆寫的模板缺 placeholder 時不拋例外（D15 字面；§8 Q15）：`user_prompt_template` 缺 `{context_blocks}` 或 `{question}`、`passage_block_template` 缺 `{n}` 或 `{text}` 時，`build_prompt` 各記一次 `log.warning`。給空字串 `""` 也照字面使用（不回退到預設模板）
- 區塊之間固定以 `"\n"` 串接；預設區塊本身以 `\n` 結尾，因此預設值下區塊之間空一行（Tier 1 同形）
- `build_prompt` 自己也做去重，直接呼叫時編號與 `answer()` 一致

### 4.10 `answer()` / `postprocess()` 主流程與 No-Answer Reply

```python
def answer(question, passages, generator, *, config=None) -> CitedAnswer:
    cfg = config or ShowReceiptsConfig()
    if not callable(generator):
        raise TypeError("generator must be callable (system_prompt, user_prompt) -> str")
    uniq, _ = dedupe_passages(list(passages))
    if not uniq:                                            # No-Answer Reply（D16）
        return CitedAnswer(answer=cfg.no_answer_reply, raw_answer="")
    system, user = build_prompt(question, uniq, cfg)
    log.debug("[showreceipts] full user prompt:\n%s", user)
    raw = generator(system, user)
    if not isinstance(raw, str):
        raise TypeError(f"generator returned {type(raw).__name__}, expected str")
    slots = {k + 1: k for k in range(len(uniq))}
    return _finalize(raw, slots, uniq, cfg)


def postprocess(answer_text, passages, *, config=None) -> CitedAnswer:
    cfg = config or ShowReceiptsConfig()
    if not isinstance(answer_text, str):
        raise TypeError(f"answer_text is {type(answer_text).__name__}, expected str")
    passages = list(passages)
    uniq, first_index = dedupe_passages(passages)
    if not uniq:                                            # §8 Q2
        return CitedAnswer(answer=cfg.no_answer_reply, raw_answer=answer_text)
    slots = {pos + cfg.input_marker_base: first_index[p.id] for pos, p in enumerate(passages)}
    return _finalize(answer_text, slots, uniq, cfg)


def _finalize(raw, slots, uniq, cfg) -> CitedAnswer:
    text, order, fabricated = normalize_and_renumber(raw, slots)
    citations = [Citation(n=n, passage=uniq[idx]) for n, idx in enumerate(order, start=1)]
    report = None
    if cfg.enable_quality_report:
        try:
            report = build_quality_report(text, citations, uniq)
        except Exception:                                   # D12：Quality Report 不得擋答案
            log.warning("[showreceipts] quality report failed; quality_report=None", exc_info=True)
    log.info("[showreceipts] cited=%s fabricated=%s",
             [c.passage.id for c in citations], fabricated or "—")
    return CitedAnswer(
        answer=text, raw_answer=raw, citations=citations, passages=uniq,
        fabricated_markers=fabricated, quality_report=report,
    )
```

Logging 沿用 Tier 1 分級：INFO 記流程（Passage 數、去重數、引用與 fabricated），DEBUG 記完整 prompt；logger 名稱 `"rag"`（§3.12，§8 Q16）。

**Quality Report 例外防護**：`build_quality_report` 拋任何 `Exception` 時，`_finalize` 記 `log.warning`（含 traceback）並令 `quality_report = None`，`answer` / `citations` / `fabricated_markers` 照常回傳（D12；`test_answer_quality_report_exception_returns_none_not_raise`）。

**空答案**：Generator 回 `""`、`postprocess("")`，或答案只剩 Fabricated Marker（`"[9][8]"`，例 52）時，照常回傳 `answer == ""`（或純空白）、`citations == []`、`passages` 非空、`quality_report.quality_score == 1.0`（Spec 104「無句子為 1.0」），不換成 No-Answer Reply——換掉屬於改寫答案（D12；暫定，§8 Q23）。呼叫端可用 `not cited.answer.strip()` 或 `fabricated_markers` 自行判斷（README 註明）。`passages == []` 是 No-Answer Reply 的唯一判準；`raw_answer == ""` 不足以判斷。

No-Answer 輸出（golden：`contracts/fixtures/cited_answer_no_answer_example.json`）：

```json
{"answer": "依現有資料無法回答", "raw_answer": "", "citations": [], "passages": [],
 "fabricated_markers": [], "quality_report": null}
```

### 4.11 Quality Report 演算法

#### 4.11.1 主流程

```python
ENTITY_REASON = "not found in any passage text"

def build_quality_report(answer: str, citations: list[Citation], passages: list[Passage]) -> QualityReport:
    text_by_id = {c.passage.id: c.passage.text for c in citations}
    id_by_n = {c.n: c.passage.id for c in citations}
    all_text = "\n".join(p.text for p in passages)          # 模型看得到的全部 Passage
    sentences = split_sentences(answer)
    supports = [
        evaluate_sentence_support(s, [id_by_n[n] for n in cited_ns(s) if n in id_by_n], text_by_id)
        for s in sentences
    ]
    entities = [
        EntityFlag(entity=e, kind=k, reason=ENTITY_REASON)
        for e, k in extract_entities(answer) if e not in all_text
    ]
    total = len(supports)
    score = sum(1 for s in supports if s.supported) / total if total else 1.0
    return QualityReport(
        quality_score=score, sentence_supports=supports,
        unsupported_entities=entities, uncited_sentences=find_uncited_sentences(sentences),
    )
```

`passages` 是去重後的 `uniq`、`citations` 指向第一次出現者，所以後出現的同 ID Passage 內文不參與任何檢查（§3.5）。`report.py` 只讀 `Citation` / `Passage` 的屬性，型別只在 `TYPE_CHECKING` 下 import（§4.1 避免循環 import）。

#### 4.11.2 自 `src/eval/` 原樣移入的部分

以下以現行 `src/eval/*.py` 的實作為準（實作與 Spec 104 文字有出入處，以現行程式為準，例如算 3-gram 前會先去掉句中 marker），只做改名：

| 現行 | 移入後 | 變動 |
|---|---|---|
| `support.split_sentences` | `quality/sentences.split_sentences` | 無 |
| `support.char_3gram_overlap` / `_char_ngram_set` / `_overlap` | `quality/support.py` | 無 |
| `support.evaluate_sentence_support(sentence, cited_context_ids, chunk_text_by_id)` | `quality/support.evaluate_sentence_support(sentence, cited_passage_ids, text_by_id)` | 參數改名；回傳 `best_match_passage_id` |
| `support.extract_cited_ns` | `quality/support.cited_ns` | 改用 `..markers._SINGLE_MARKER_RE` |
| `support._strip_markers`（用 `src.utils.CITE_RE`） | `quality/support._strip_markers` | 改用 `..markers._SINGLE_MARKER_RE`（照原樣複製會 import Demo Host，違反 §4.14） |
| `entities.extract_entities` / `_ENTITY_PATTERNS` | `quality/entities.py` | 無 |
| `entities.find_unsupported_entities(answer_text, cited_chunk_text)` | 併入 `build_quality_report` | reason 字串改為 `ENTITY_REASON` |
| `report.evaluate(answer: RagAnswer)` | `quality/report.build_quality_report(answer, citations, passages)` | 不再吃 `RagAnswer` |
| `SUPPORT_OVERLAP_THRESHOLD = 0.15`、`NGRAM_SIZE = 3` | `quality/support.py` 常數 | 值不變、不開設定 |

Quality Report 只在**已正規化**的答案上執行；依 §4.8.2 第 3 步的不變式，句中的 marker 只剩有效的 `[k]`，`_SINGLE_MARKER_RE` 就夠用。

#### 4.11.3 Uncited Sentence（新）

```python
_ENUM_PREFIX_RE = re.compile(                                   # 行首清單序號
    r"^\s*(?:[(（]\d+[)）]\s*|\d+[.)](?!\d)\s*|\d+、|[-*+](?:\s+|$))"
)
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")

def find_uncited_sentences(sentences: list[str]) -> list[UncitedSentence]:
    out: list[UncitedSentence] = []
    for i, s in enumerate(sentences):
        if _SINGLE_MARKER_RE.search(s):
            continue
        body = _ENUM_PREFIX_RE.sub("", s, count=1)
        numbers = _NUMBER_RE.findall(body)
        if numbers:
            out.append(UncitedSentence(sentence=s, sentence_index=i, numbers=numbers))
    return out
```

規則：
- 句子沒有任何 Citation Marker，且去掉行首清單序號（`1. `、`1.`（無空白）、`2) `、`(1) `、`（1）`、`3、`、`- `、`* `、`+ `）後仍含十進位數字 → Uncited Sentence
- `\d+[.)](?!\d)`：序號後不得緊接數字，所以「3.8% 回饋」不會被當成序號「3.」；「1.年費 4,500 元。」去掉「1.」後 `numbers == ["4,500"]`；「(1) 假日刷：」「1.注意事項」不標（`data/sample_reranked.json` 實際含「(1) 【假日刷】」這類序號）
- Spec 104 的句切分遇到「2. 年費 4,500 元」會在「.」後的空白切開，得到「2.」與「年費 4,500 元」兩句；只剩序號的「2.」不被標，「年費 4,500 元」照常判定
- `numbers` 是觸發判定的數字片段（`NT$4,500` → `4,500`、`0.3%` → `0.3`），供 UI 說明「為什麼被標」；`[.,]` 只認 ASCII，全形逗號不合併（「年費４，５００元。」→ `["４", "５００"]`）
- 「Q1：」「A1：」這類問答前綴不排除（會被標），是否排除見 §8 Q6
- 不含數字的未引用句（如「依現有資料無法回答。」）不標
- 因 Fabricated Marker 被移除而失去 marker 的句子，照樣會被標——這正是此檢查要抓的情況

#### 4.11.4 Worked example（golden：`cited_answer_example.json` / `quality_report_uncited_example.json`）

Passage 為 `[Passage.model_validate(p) for p in cited_answer_example.json["passages"]]`（等同 `from_arrkb(sample)[:4]`，該等式由 `test_arrkb_*` 另行驗證，因此本例在 §7 步驟 4 不需要 Adapter），假 Generator 回：

```text
切換【Pay 著刷】方案並以臺新 Pay 支付，最高可享 3.8% 臺新 Point 回饋 [1、3]。繳保費免切換即享 1.3% 回饋，切換「假日刷」最高可享 2% [4][2]。一般消費回饋為 0.3% [9]。
```

結果：

| 項目 | 值 |
|---|---|
| `answer` | `切換【Pay 著刷】方案並以臺新 Pay 支付，最高可享 3.8% 臺新 Point 回饋 [1][2]。繳保費免切換即享 1.3% 回饋，切換「假日刷」最高可享 2% [3][4]。一般消費回饋為 0.3% 。` |
| `citations` | n1=`…054657`、n2=`…054730`、n3=`…054734`、n4=`…054735` |
| `fabricated_markers` | `["[9]"]` |
| `sentence_supports` | 句 0 supported（0.5366，`…054657`）；句 1 supported（0.6129，`…054735`）；句 2 unsupported（0.0） |
| `unsupported_entities` | `[]`（3.8% / 1.3% / 2% / 0.3% 都出現在某段 Passage） |
| `uncited_sentences` | `[{"sentence": "一般消費回饋為 0.3% 。", "sentence_index": 2, "numbers": ["0.3"]}]` |
| `quality_score` | 0.6666666666666666 |

### 4.12 Generator 與 `OpenAICompatGenerator`

`OpenAICompatGenerator.__call__` 規格（逾時、重試與錯誤型別皆為暫定值，§8 Q19）：

| 項目 | 規格 |
|---|---|
| 實作 | 只用 `urllib.request`、`urllib.error`、`http.client`、`json`、`time`（D21） |
| Endpoint | `POST {base_url.rstrip('/')}/chat/completions` |
| Headers | `Content-Type: application/json`；`api_key` 非空時加 `Authorization: Bearer {api_key}` |
| Body | `{"model": model, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], "temperature": temperature, "stream": false}` |
| 回傳 | `response["choices"][0]["message"]["content"]`，必須是 `str` |
| 逾時 | `timeout` 秒（預設 600.0，比照 openai SDK 預設），傳給 `urlopen`（socket 層逾時） |
| 重試 | 最多 `max_retries` 次（預設 2，比照 openai SDK 預設）。只在可重試的失敗重試：連線失敗（`URLError` 但非 `HTTPError`、`ConnectionError`、`TimeoutError`、`http.client.HTTPException`）與 HTTP 408 / 409 / 429 / ≥ 500。第 i 次重試前 `time.sleep(min(0.5 * 2 ** i, 8.0))`（0.5 s、1 s；不加 jitter，測試以 monkeypatch 取代 `time.sleep`） |
| 錯誤 | 重試用完仍失敗，或遇到不重試的失敗——`OSError`（含 `URLError` / `HTTPError` / `TimeoutError` / `ConnectionError`）、`http.client.HTTPException`（含 `RemoteDisconnected`）、`ValueError`（含 `json.JSONDecodeError`、`UnicodeDecodeError`）、回應缺 `choices[0].message.content` 或其值非 `str`——一律 `GeneratorError`（`raise ... from err`）。urllib 對「等待回應逾時」拋 `TimeoutError`、對「連線被中斷」拋 `RemoteDisconnected`，兩者都不是 `URLError`，所以不能只接 `URLError` |

Demo Host 預設指向 Ollama：`OpenAICompatGenerator(base_url=settings.ollama_base_url, model=settings.llm_model, api_key=settings.ollama_api_key)`（逾時與重試用預設值，與現行 `ChatOpenAI` 行為相同）。

urllib 會讀 `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY`（大小寫皆可）；`NO_PROXY` 未含 `localhost,127.0.0.1` 時，本機 Ollama 的請求可能被送進 proxy（R4）。

### 4.13 Adapters

#### 4.13.1 arrkb：`from_arrkb(data)`

| 項目 | 規格 |
|---|---|
| 輸入 | `{"data": [...]}`（`data/sample_reranked.json` 的外層）或 item list；兩者結果相同 |
| 必要欄位 | `context_id`、`content`；缺任一 → `ValueError(f"arrkb item {i}: missing '{key}'")` |
| `id` | `str(item["context_id"])` |
| `text` | `item["content"]` |
| `source` | `item.get("filename")` 非空則用之，否則 `"?"`（沿用現行 `RerankedChunk.filename` 預設） |
| `locator` | `page = item.get("page")`；`None` → `""`；否則 `s = str(page).strip()`，`s` 非空 → `f"第 {s} 頁"`，空 → `""` |
| `score` | `item["kwargs"]["relevance_score"]` 存在 → `float(...)`；否則 `None` |
| `metadata` | item 中 `context_id` / `content` / `filename` 以外的全部 key（含 `type`、`kb_name`、`file_id`、`page`、`kwargs` 與 production 多帶的欄位），淺拷貝 |
| 順序 | 原樣保留（D22） |

arrkb 是外部 schema：Adapter 不對 item 套 `extra="forbid"`，多帶欄位進 `metadata`。golden：`contracts/fixtures/passage_arrkb_example.json` = `from_arrkb(sample)[0]`。

#### 4.13.2 LangChain：`from_langchain(docs, *, id_key="id", source_key="source", locator_fn=None)`

**不得 import langchain**（**第 2 次重複提醒**：模組內 import LangChain 違反 D5 / D8）。以 duck typing 判斷：

| 項目 | 規格 |
|---|---|
| 元素 | Document 類物件，或 `(document, score)` 二元 tuple / list（對應 `similarity_search_with_relevance_scores` 輸出） |
| Document 類物件 | 有 `page_content: str` 與 `metadata: Mapping` 屬性；否則 `TypeError(f"docs[{i}]: expected object with page_content and metadata")` |
| `id` | `getattr(doc, "id", None)` 為非空字串則用之；否則 `metadata.get(id_key)` 非空則 `str(...)`；都沒有 → `ValueError`（§8 Q8） |
| `text` | `doc.page_content` |
| `source` | `metadata.get(source_key)` 非空則 `str(...)`，否則 `"?"` |
| `locator` | 有 `locator_fn` → `locator_fn(metadata)`；否則 `metadata.get("page")` 不為 `None` → `f"第 {page} 頁"`，否則 `""` |
| `score` | tuple 第二個元素 → `float(...)`；否則 `None` |
| `metadata` | `dict(doc.metadata)` |
| 順序 | 原樣保留 |

LangChain 的 0-based 頁碼原樣顯示（與 Demo Host 現行「第 {page} 頁」一致；§8 Q12）。

### 4.14 Import 隔離如何強制

1. **AST 掃描**（`test_isolation_ast_only_stdlib_and_pydantic_imports`）：走訪 `src/showreceipts/**/*.py`，每個 `Import` / `ImportFrom` 若 `level == 0`，頂層名稱必須在 `sys.stdlib_module_names ∪ {"pydantic"}` 中；任何 `src.` 開頭的絕對 import 都算違規（模組內一律相對 import）。
2. **封鎖框架套件後 import**（`test_isolation_import_with_blocked_frameworks_succeeds`）：以 `subprocess.run([sys.executable, "-c", CODE])` 在乾淨直譯器中執行：
   ```python
   import importlib.abc, sys
   BLOCKED = {"langchain", "langchain_core", "langchain_openai", "langchain_chroma",
              "langchain_community", "langchain_text_splitters", "chromadb", "streamlit",
              "openai", "httpx", "requests", "pydantic_settings", "llama_index"}
   class _Block(importlib.abc.MetaPathFinder):
       def find_spec(self, name, path=None, target=None):
           if name.split(".")[0] in BLOCKED:
               raise ImportError(f"blocked: {name}")
           return None
   sys.meta_path.insert(0, _Block())
   import src.showreceipts as sr
   from src.showreceipts.adapters import from_arrkb, from_langchain
   # 跑一次 answer()（假 Generator）、postprocess()、from_arrkb(sample)、from_langchain(SimpleNamespace docs)
   assert not {m.split(".")[0] for m in sys.modules} & BLOCKED
   assert {m for m in sys.modules if m.startswith("src.") and not m.startswith("src.showreceipts")} <= {"src.logging_setup"}
   ```
   `src/__init__.py` 會載入 `src.logging_setup`（只用 stdlib），這是目前唯一允許的 `src.*` 例外，抽套件後自然消失。
3. **runtime 與 contract 一致**：`test_contract_runtime_json_schema_matches_contract` 對 `Passage`、`Citation`、`CitedAnswer`、`QualityReport`、`SentenceSupport`、`EntityFlag`、`UncitedSentence`、`ShowReceiptsConfig` 比對 `model_json_schema()`（遞迴去除 `description`——docstring 與欄位說明是文件，不是介面）；JSON schema 看不到 validator，所以另以 `test_contract_runtime_validators_reject_same_invalid_inputs` 對兩邊餵同一組非法輸入（`n` 不連號、重複 Passage ID、引用不在 `passages` 的 Passage、缺 placeholder 的模板、`input_marker_base=2`、未知欄位、空 `id`），都必須 `ValidationError`。

### 4.15 Demo Host 變更

#### 4.15.1 `src/llm.py`

```python
from functools import lru_cache
from src.config import settings
from src.showreceipts import Generator, OpenAICompatGenerator

@lru_cache(maxsize=4)
def _generator_for(model: str, base_url: str, api_key: str) -> OpenAICompatGenerator:
    return OpenAICompatGenerator(base_url=base_url, model=model, api_key=api_key)

def get_generator() -> Generator:
    return _generator_for(settings.llm_model, settings.ollama_base_url, settings.ollama_api_key)
```

`langchain_openai.ChatOpenAI` 不再用於問答（`OpenAIEmbeddings` 仍留在 `src/vectorstore.py`）。

#### 4.15.2 `src/rag_chain.py`

```python
EMPTY_KB_REPLY = "依現有資料無法回答：知識庫目前是空的，請先在「文件管理」分頁上傳文件。"

def query(
    question: str,
    reranked: Mapping[str, Any] | Sequence[Mapping[str, Any] | RerankedChunk] | None = None,
    *,
    generator: Generator | None = None,
) -> CitedAnswer:
    if reranked is None:                                      # 本地知識庫
        passages = from_arrkb([r.model_dump() for r in retrieve(question)])
        config = ShowReceiptsConfig(no_answer_reply=EMPTY_KB_REPLY)
    else:                                                     # 外部檢索結果
        items = reranked if isinstance(reranked, Mapping) else [
            r.model_dump() if isinstance(r, RerankedChunk) else r for r in reranked
        ]
        passages = from_arrkb(items)
        config = ShowReceiptsConfig()
    return answer(question, passages, generator or get_generator(), config=config)
```

- 本地檢索空 → 回 `EMPTY_KB_REPLY`（與 Tier 1 / Spec 100 AC #6 相同字串）；外部清單空 → 回預設 No-Answer Reply
- `generator` 參數讓測試直接注入，不必 patch
- 不再 import `langchain_core.messages`

#### 4.15.3 `src/retrieval.py`、`src/utils.py`、`rag.py`

- `src/retrieval.py`：刪 `RetrievedChunk`、`to_retrieved_chunk`、`coerce_reranked`；保留 `RerankedChunk`、`RerankedKwargs`、`retrieve`
- `src/utils.py`：刪 `CITE_RE`；保留 `preview`
- `rag.py`（façade，仍遵守 Spec 100 AC #10：≤ 12 行、只有 import 與 `__all__`）：

  ```python
  """Backward-compat façade. New code: import from `src.*` directly."""
  from src.ingest import ingest_paths
  from src.rag_chain import query
  from src.retrieval import RerankedChunk, retrieve
  from src.showreceipts import CitedAnswer, Passage
  from src.vectorstore import fetch_chunks_by_ids, list_sources

  __all__ = ["ingest_paths", "query", "RerankedChunk", "retrieve",
             "CitedAnswer", "Passage", "fetch_chunks_by_ids", "list_sources"]
  ```

  CLAUDE.md 的 CLI smoke（`result = query('問題'); print(result.answer)`）不必改。

#### 4.15.4 對話歷史（history v2）

- `src/history/models.py` 改以路徑載入 `specs/106-showreceipts/contracts/demo_host_history_schema.py`（沿用 Spec 103 慣例），並多匯出 `OriginKind`
- `StoredCitation` v2：

  | 欄位 | 型別 | 必填 | 說明 |
  |---|---|---|---|
  | `passage_id` | `str`（min_length=1） | Y | 原 `context_id` |
  | `display_n` | `int`（≥1） | Y | 不變 |
  | `score` | `float \| None` | N（`None`） | 原為必填；Passage.score 選填（D20） |
  | `snapshot_text` | `str`（≤1000） | Y | 不變；store 仍是唯一截斷點（plan.md 仲裁 #1） |
  | `source` | `str` | Y | 新；外部 Passage 重載時無 Chroma metadata 可查 |
  | `locator` | `str` | N（`""`） | 新 |
  | `origin` | `OriginKind`（`local` / `external`） | Y | 新；`external` 重載時不加 stale 標籤（D17） |

- `Message` / `Conversation` 不變；SQLite 表結構不變（citations 仍以 JSON 存在 `citations_json`）
- 舊資料不遷移（D27）：Lead 在 §7 步驟 6 合併前手動刪 `data/history.sqlite`；`HistoryStore` 不寫相容程式碼，舊列載入時 `ValidationError` 即為預期

#### 4.15.5 `src/citation_view.py`（新，Demo Host，pure、不 import streamlit）

```python
@dataclass
class CitationView:
    display_n: int
    text: str
    source: str
    locator: str
    chunk_index: int | None
    score: float | None
    passage_id: str
    stale: bool

def citation_view(c: Citation | StoredCitation, origin: OriginKind, live: dict[str, dict]) -> CitationView: ...
def live_lookup_ids(items: list[tuple[Citation | StoredCitation, OriginKind]]) -> list[str]: ...
```

規則：
- `origin == external`：不放進 `live_lookup_ids`（不呼叫 `fetch_chunks_by_ids`）；`text` = 快照（`passage.text` 或 `snapshot_text`）；`stale = False`；`chunk_index = None`
- `origin == local`：`text` 優先用 Chroma 最新原文；查不到 → 快照 + `stale = True`（Tier 1 fallback 行為不變）；`chunk_index` 取 live metadata（有才顯示）

#### 4.15.6 `app.py`

- import 改為 `src.showreceipts`（`CitedAnswer`、`QualityReport`）、`src.rag_chain.query`、`src.citation_view`、`src.history`；拿掉 `src.eval`、`src.retrieval.RetrievedChunk`
- 問答分頁頂端加 `st.radio("檢索來源", ["本地知識庫", "外部檢索結果（貼上 arrkb JSON）"], horizontal=True)`
  - 外部模式顯示 `st.text_area`，預設值為啟動時讀入的 `data/sample_reranked.json` 全文
  - 送出問題時先 `json.loads` + `from_arrkb`；`json.JSONDecodeError` / `ValueError` / `TypeError` → `st.error("arrkb JSON 無法解析：…")`，不寫入任何歷史訊息、不呼叫 Generator
  - 合法時呼叫 `query(q, reranked=parsed)`
- `render_citations` 改用 `citation_view`；每筆標頭如下，`locator` 為空、`chunk_index` 或 `score` 為 `None` 的片段省略，stale 標籤文字不變：

  ```text
  **[{n}]** `{source}` · {locator} · 第 {chunk_index} 段 · score={score:.3f} · `id={passage_id}`{stale_tag}
  ```

- `render_quality_report` 讀 `CitedAnswer.quality_report`（`None` 不顯示），新增「含數字但未標來源的句子」小節列出 `uncited_sentences`；`best_match_context_id` 改讀 `best_match_passage_id`
- 寫入歷史時 `StoredCitation(passage_id=…, display_n=c.n, score=c.passage.score, snapshot_text=c.passage.text, source=…, locator=…, origin=…)`，`origin` 依當次檢索來源
- session 內 assistant 訊息另記 `origin`，供重繪時使用
- 無 streaming（D26）

#### 4.15.7 `examples/langchain_postprocess.py`（新，Demo Host）

```python
def build_documents(sample_path: Path) -> list[Document]:
    """data/sample_reranked.json → LangChain Document（id=context_id, metadata={"source": filename, "page": page}）。"""

def run(question: str, llm: BaseChatModel, docs: list[Document]) -> CitedAnswer:
    """LangChain 以 0-based「[0] …」編號組 context（同 LangChain QA citations how-to），
    以 `prompt | llm | StrOutputParser()` 產生答案，再交給
    postprocess(text, from_langchain(docs), config=ShowReceiptsConfig(input_marker_base=0))。"""

def main() -> None:
    """argparse 取問題；llm = ChatOpenAI(base_url=settings.ollama_base_url, model=settings.llm_model,
    api_key=settings.ollama_api_key, temperature=0)；印出 raw_answer、answer、citations、quality_report。"""
```

測試以 `langchain_core.language_models.fake_chat_models.FakeListChatModel` 取代真模型（不打 Ollama）。

#### 4.15.8 `pyproject.toml` 與文件

- `pyproject.toml`：`dependencies` 明列 `"pydantic>=2.6"`（模組直接 import；目前只是間接依賴）；不加其他套件
- `README.md`：新增 showreceipts 章節（兩個入口、Generator、Adapter、Config、Quality Report 含 Uncited Sentence）、三條 demo 路徑操作步驟、`examples/langchain_postprocess.py` 用法；更新「結構」與「品質評估」
- `CLAUDE.md`：更新「查詢管線」與「重點檔案」表
- `specs/plan.md`：Spec 索引加 106；`specs/CLAUDE.md` 目錄清單加 `106-showreceipts/`

### 4.16 術語對照（舊 → 新，D3）

| 舊（程式 / spec） | 新（GLOSSARY） | 新欄位 / 型別 |
|---|---|---|
| `RetrievedChunk`、`RerankedChunk`（作為引用輸入） | Passage | `Passage` |
| `context_id` / `chunk_id` | Passage ID | `Passage.id`、`StoredCitation.passage_id` |
| `filename` | Source | `Passage.source` |
| `page` / `chunk_index` | Locator | `Passage.locator`（`chunk_index` 只在 Demo Host 顯示） |
| `content` | （Passage 內文） | `Passage.text` |
| `RagAnswer` | Cited Answer | `CitedAnswer` |
| `citations: list[RetrievedChunk]` | Citation | `list[Citation]` |
| 編造編號 / `fabricated` | Fabricated Marker | `CitedAnswer.fabricated_markers` |
| `[n]` / CITE_RE | Citation Marker | `MARKER_GROUP_RE` |
| LLM / `_get_llm()` | Generator | `Generator`、`OpenAICompatGenerator` |
| 「依現有資料無法回答：知識庫目前是空的…」 | No-Answer Reply（Demo Host 覆寫值） | `ShowReceiptsConfig.no_answer_reply` |
| `best_match_context_id` | — | `best_match_passage_id` |

---

## 5. 測試計畫

規約：LLM 一律 mock（假 Generator、`FakeListChatModel`、本機 `http.server`），不打真 Ollama；命名 `test_<feature>_<scenario>_<expected>()`。新增 `tests/unit/showreceipts/__init__.py`。

### 5.1 `tests/unit/showreceipts/test_markers.py`

| Test | 驗證 |
|---|---|
| `test_markers_tier1_docstring_example_renumbers_and_drops_fabricated` | §4.8.3：`句A [1]. 句B [2][1].`、`fabricated_markers == ["[99]"]` |
| `test_markers_no_marker_returns_text_unchanged` | 無 marker → 原字串、`order == []` |
| `test_markers_worked_examples_match_table` | 參數化跑 §4.8.4 例 1–18，逐列比對最終答案、citation 順序、fabricated_markers |
| `test_markers_huge_range_completes_fast` | 例 17 在 50 ms 內完成 |
| `test_markers_fabricated_group_recorded_once_in_order` | 同一 `[99]` 出現兩次只記一次，多個依首次出現排序 |
| `test_markers_double_space_compressed_globally` | 無 marker 的「甲  乙」也壓成「甲 乙」（Tier 1） |
| `test_markers_single_marker_matches_tier1_cite_re` | 對只含 `[n]` 的字串，新舊結果相同（固定 seed 的生成樣本；測試檔內保留一份 Tier 1 `renumber_and_filter` 作對照，因原檔於步驟 6 刪除） |

### 5.2 `tests/unit/showreceipts/test_pipeline.py`

| Test | 驗證 |
|---|---|
| `test_answer_generator_receives_default_prompts_byte_identical` | 假 Generator 收到的 system / user 等於 Tier 1 snapshot 字串 |
| `test_answer_passages_numbered_in_given_order_not_by_score` | score 遞增的 Passage 仍依給定順序編 [1]..[N] |
| `test_answer_duplicate_passage_ids_keep_first` | §4.8.4 例 20；prompt 只列兩段 |
| `test_answer_zero_passages_skips_generator_returns_no_answer_reply` | Generator 呼叫次數 0；結果等於 no-answer golden |
| `test_answer_custom_no_answer_reply_used` | `no_answer_reply="查無資料"` 生效 |
| `test_answer_quality_report_on_by_default` | 預設有 `quality_report` |
| `test_answer_quality_report_disabled_returns_none` | `enable_quality_report=False` → `None`，其餘欄位不變 |
| `test_answer_text_identical_with_and_without_quality_report` | 開關 Quality Report，`answer` / `citations` 完全相同（D12） |
| `test_answer_ignores_input_marker_base_zero` | `input_marker_base=0` 時 answer 模式仍 1-based |
| `test_answer_generator_non_str_raises_type_error` | 回傳 `None` → `TypeError` |
| `test_answer_generator_exception_propagates` | 假 Generator 拋 `RuntimeError` → 原樣拋出 |
| `test_answer_non_passage_element_raises_type_error` | 傳 dict → `TypeError` |
| `test_answer_reproduces_golden_cited_answer` | §4.11.4 輸入 → `model_dump()` 等於 `cited_answer_example.json` |
| `test_postprocess_matches_answer_for_same_raw_text` | 同一 raw 文字，`postprocess` 與 `answer` 的 `answer` / `citations` / `quality_report` 相同 |
| `test_postprocess_zero_based_answer_normalized` | §4.8.4 例 11、12 |
| `test_postprocess_duplicate_ids_positional_slots_resolve_to_first` | §4.8.4 例 19 |
| `test_postprocess_zero_passages_returns_no_answer_reply` | `answer == no_answer_reply`、`raw_answer` 保留原文 |

### 5.3 `tests/unit/showreceipts/test_prompts.py`

| Test | 驗證 |
|---|---|
| `test_prompts_default_system_prompt_equals_tier1_snapshot` | 等於 Tier 1 `SYSTEM_PROMPT` 字串（snapshot 寫在測試內） |
| `test_prompts_language_substitutes_rule_five_only` | `language="English"` 只改第 5 條 |
| `test_prompts_system_override_used_verbatim` | `system_prompt` 原樣使用、`language` 不生效 |
| `test_prompts_user_template_override_single_pass_substitution` | Passage 內文含字面 `{question}` 不被替換；模板含 `{"k": 1}` 不出錯 |
| `test_prompts_user_template_missing_placeholder_rejected` | 缺 `{context_blocks}` → `ValidationError` |
| `test_config_frozen_rejects_mutation_and_unknown_fields` | 指派欄位、未知欄位、`input_marker_base=2` 都 `ValidationError` |
| `test_prompts_empty_locator_omits_parenthetical` | `locator=""` → `[1] 來源: foo.md` |
| `test_prompts_arrkb_sample_user_prompt_byte_identical_to_tier1` | `from_arrkb(sample)` 組出的 user prompt 等於 Tier 1 snapshot |

### 5.4 `tests/unit/showreceipts/test_quality.py`

原 `tests/unit/test_eval_support.py`、`test_eval_entities.py` 全數移入並改名（例：`test_split_sentences_chinese` → `test_quality_split_sentences_chinese_splits_on_terminators`、`test_evaluate_performance` → `test_quality_performance_under_500ms`），斷言只改欄位名。另加：

| Test | 驗證 |
|---|---|
| `test_quality_supported_sentence_has_best_match_passage_id` | Spec 104 AC #1 改用新欄位 |
| `test_quality_unsupported_entity_flagged_with_passage_reason` | reason 為 `"not found in any passage text"` |
| `test_quality_uncited_numeric_sentence_flagged` | 「一般消費回饋為 0.3% 。」→ `numbers == ["0.3"]` |
| `test_quality_uncited_sentence_with_marker_not_flagged` | 有 `[1]` 的數字句不標 |
| `test_quality_uncited_list_enumerator_ignored` | 答案「2. 注意事項\n2. 年費 4,500 元」切成「2.」「注意事項」「2.」「年費 4,500 元」四句，只有「年費 4,500 元」被標，`numbers == ["4,500"]` |
| `test_quality_uncited_sentence_without_digits_not_flagged` | 「依現有資料無法回答。」不標 |
| `test_quality_reproduces_golden_uncited_report` | 等於 `quality_report_uncited_example.json` |
| `test_quality_never_modifies_answer` | 呼叫前後答案字串相同 |

### 5.5 `tests/unit/showreceipts/test_adapters_arrkb.py`

| Test | 驗證 |
|---|---|
| `test_arrkb_sample_first_item_matches_golden_passage` | `from_arrkb(sample)[0]` 等於 `passage_arrkb_example.json` |
| `test_arrkb_envelope_and_bare_list_equivalent` | `{"data": [...]}` 與 list 結果相同 |
| `test_arrkb_extra_fields_kept_in_metadata` | 多帶欄位出現在 `metadata` |
| `test_arrkb_missing_context_id_raises_value_error` | 訊息含 item index |
| `test_arrkb_empty_page_gives_empty_locator` | `page=""` / 缺 → `locator == ""`；`page=0` → `第 0 頁` |
| `test_arrkb_missing_kwargs_gives_none_score` | 無 `kwargs` → `score is None` |
| `test_arrkb_order_preserved_not_sorted_by_score` | 分數遞增的輸入順序不變 |

### 5.6 `tests/unit/showreceipts/test_adapters_langchain.py`

| Test | 驗證 |
|---|---|
| `test_langchain_duck_typed_object_converted_without_langchain` | `SimpleNamespace(page_content=…, metadata=…, id=…)` 可轉 |
| `test_langchain_score_tuple_sets_score` | `(doc, 0.9)` → `score == 0.9` |
| `test_langchain_id_from_metadata_when_doc_id_missing` | `id_key="context_id"` 生效 |
| `test_langchain_missing_id_raises_value_error` | 無 id → `ValueError` |
| `test_langchain_non_document_raises_type_error` | 傳 str → `TypeError` |
| `test_langchain_locator_fn_overrides_default` | 自訂 `locator_fn` 生效 |
| `test_langchain_real_document_converted` | `pytest.importorskip("langchain_core")` 後用真 `Document` |

### 5.7 `tests/unit/showreceipts/test_generators.py`

| Test | 驗證 |
|---|---|
| `test_openai_compat_posts_chat_completions_payload` | 本機 `http.server` 收到正確 path / body，回傳 content |
| `test_openai_compat_sends_bearer_when_api_key` | 有 `api_key` 才有 `Authorization` |
| `test_openai_compat_http_error_raises_generator_error` | 500 → `GeneratorError` |
| `test_openai_compat_malformed_response_raises_generator_error` | 缺 `choices` → `GeneratorError` |

### 5.8 `tests/unit/showreceipts/test_isolation.py`、`test_contract_parity.py`

| Test | 驗證 |
|---|---|
| `test_isolation_ast_only_stdlib_and_pydantic_imports` | §4.14 第 1 點 |
| `test_isolation_import_with_blocked_frameworks_succeeds` | §4.14 第 2 點，subprocess 退出碼 0 |
| `test_isolation_public_api_all_matches_spec` | 兩個 `__all__` 與 §4.3 完全相同 |
| `test_contract_runtime_json_schema_matches_contract` | §4.14 第 3 點（參數化 8 個類別，去除 `description` 後比對） |
| `test_contract_runtime_validators_reject_same_invalid_inputs` | §4.14 第 3 點（同一組非法輸入兩邊都 `ValidationError`） |

### 5.9 既有測試的增修

| 檔案 | 動作 |
|---|---|
| `tests/unit/test_contracts_fixtures.py` | `_FIXTURE_MAP` 加入本 spec 6 個 fixture（含 `stored_citation_external_example.json` → `demo_host_history_schema.StoredCitation`） |
| `tests/unit/test_history_store.py` | 改用 v2 欄位；新增 `test_history_external_citation_roundtrip_keeps_origin_source_locator`、`test_history_v1_context_id_field_rejected` |
| `tests/unit/test_citation_view.py`（新） | `test_citation_view_external_origin_not_stale_not_looked_up`、`test_citation_view_local_missing_marks_stale_with_snapshot`、`test_citation_view_local_hit_uses_live_text` |
| `tests/unit/test_citation.py`、`test_eval_support.py`、`test_eval_entities.py`、`test_reranked_adapter.py` | 刪除（內容已移入 §5.1、§5.4、§5.5） |
| `tests/integration/test_pipeline_end_to_end.py` | 保留 `test_fetch_chunks_partial_hit`；`test_query_smoke`、`test_query_with_injected_reranked_dicts` 移到 `test_demo_host_paths.py` 並改寫；`test_pipeline_smoke_with_ollama` 改斷言 `CitedAnswer` |

### 5.10 `tests/integration/test_demo_host_paths.py`（新）

| Test | 驗證 |
|---|---|
| `test_demo_local_path_cites_with_injected_generator` | patch `retrieve` 回 2 筆 `RerankedChunk`、注入假 Generator → `CitedAnswer` 含 `[1]`、`len(passages) == 2` |
| `test_demo_local_path_empty_kb_returns_upload_hint` | `retrieve` 回 `[]` → `answer == EMPTY_KB_REPLY`、Generator 未被呼叫 |
| `test_demo_external_sample_json_cites_sample_passages` | `query(q, reranked=json.load(sample))` → citations 的 id 都在 sample 中 |
| `test_demo_external_dicts_skip_local_retrieve` | `retrieve` 被呼叫即失敗；結果同現行 `test_query_with_injected_reranked_dicts` 斷言 |
| `test_demo_external_empty_list_returns_default_no_answer_reply` | `reranked=[]` → 「依現有資料無法回答」 |
| `test_demo_langchain_example_fake_llm_zero_based_postprocess` | 以 `importlib` 依路徑載入 `examples/langchain_postprocess.py`；`FakeListChatModel(responses=["…[0]…[2, 1]…[7]。"])` 跑 `run(…, build_documents(sample))`（6 段，合法編號 0–5）→ 正規化為 `[1]`、`[2][3]`，`fabricated_markers == ["[7]"]` |

---

## 6. Acceptance Criteria

1. **Passage 契約與 arrkb golden**：`Passage.model_validate(passage_arrkb_example.json)` 不 raise；`from_arrkb(json.load(open("data/sample_reranked.json")))[0].model_dump() == passage_arrkb_example.json`（`test_arrkb_sample_first_item_matches_golden_passage`、`test_contract_fixture`）。
2. **恰好兩個入口**：`src.showreceipts.__all__` 與 §4.3 清單完全相同，其中可呼叫且回傳 `CitedAnswer` 的只有 `answer`、`postprocess`（`test_isolation_public_api_all_matches_spec`）。
3. **Tier 1 重編號保留**：`postprocess("句A [2]. 句B [4][2][99].", 5 段 Passage)` 的 `answer == "句A [1]. 句B [2][1]."`、`[c.n for c in citations] == [1, 2]`（`test_markers_tier1_docstring_example_renumbers_and_drops_fabricated`）。
4. **Marker 正規化**：§4.8.4 例 1–18 全部逐列相符，含 `[1-3]`、`[1, 2]`、`[2，1]`、`[1、3]`、`[0]`（1-based 與 0-based）（`test_markers_worked_examples_match_table`）。
5. **Fabricated Marker 移除並記錄**：被移除的群組不出現在 `answer`，並以原字串、首次出現順序、去重記入 `fabricated_markers`（`test_markers_worked_examples_match_table`、`test_markers_fabricated_group_recorded_once_in_order`）。
6. **連續空白壓縮**：§4.8.4 例 13 結果為 `甲 乙 丙 [1]。`；無 marker 的「甲  乙」亦壓成「甲 乙」（`test_markers_double_space_compressed_globally`）。
7. **不依 score 重排**：score 遞增的 3 段 Passage，prompt 中 `[1]`/`[2]`/`[3]` 依給定順序對應（`test_answer_passages_numbered_in_given_order_not_by_score`、`test_arrkb_order_preserved_not_sorted_by_score`）。
8. **重複 Passage ID 取第一個**：§4.8.4 例 19、20 相符，`passages` 只含 [A, B]，Citation 內文為第一個 A（`test_answer_duplicate_passage_ids_keep_first`、`test_postprocess_duplicate_ids_positional_slots_resolve_to_first`）。
9. **0-based 選項**：`input_marker_base=0` 時 §4.8.4 例 11、12 相符；`answer()` 不受影響（`test_postprocess_zero_based_answer_normalized`、`test_answer_ignores_input_marker_base_zero`）。
10. **No-Answer Reply**：零 Passage 時 Generator 呼叫次數為 0，結果等於 `cited_answer_no_answer_example.json`；`no_answer_reply` 可覆寫；Demo Host 本地空知識庫回 `"依現有資料無法回答：知識庫目前是空的，請先在「文件管理」分頁上傳文件。"`（`test_answer_zero_passages_skips_generator_returns_no_answer_reply`、`test_answer_custom_no_answer_reply_used`、`test_demo_local_path_empty_kb_returns_upload_hint`）。
11. **預設 prompt byte-identical**：預設 system prompt 等於 Tier 1 `SYSTEM_PROMPT`；`from_arrkb(sample)` 組出的 user prompt 等於 Tier 1 `build_user_message` 對同一份資料的輸出（snapshot 字串寫死在測試內）（`test_prompts_default_system_prompt_equals_tier1_snapshot`、`test_prompts_arrkb_sample_user_prompt_byte_identical_to_tier1`、`test_answer_generator_receives_default_prompts_byte_identical`）。
12. **Prompt 覆寫與語言**：`language` 只改第 5 條；`system_prompt` 原樣使用；`user_prompt_template` 單趟替換（`test_prompts_language_substitutes_rule_five_only`、`test_prompts_system_override_used_verbatim`、`test_prompts_user_template_override_single_pass_substitution`）。
13. **Quality Report 預設開啟、可關閉**：預設 `quality_report is not None`；`enable_quality_report=False` → `None`（`test_answer_quality_report_on_by_default`、`test_answer_quality_report_disabled_returns_none`）。
14. **Quality Report 只報不攔**：開關 Quality Report 時 `answer` 與 `citations` 完全相同；Quality Report 任何結果都不使入口拋例外（`test_answer_text_identical_with_and_without_quality_report`、`test_quality_never_modifies_answer`）。
15. **Uncited Sentence**：§4.11.4 輸入產生的 `quality_report` 等於 `quality_report_uncited_example.json`，`uncited_sentences[0].sentence == "一般消費回饋為 0.3% 。"`；清單序號與無數字句不標（`test_quality_reproduces_golden_uncited_report`、`test_quality_uncited_*`）。
16. **Spec 104 行為保留**：移入後的測試全綠，含 `quality_score` 為 supported 比例、`100 億` 被標、連跑 5 次 `model_dump()` 相同、5 段 × 300 字答案 < 500 ms、空答案分數 1.0（`test_quality_*`）。
17. **兩入口共用核心**：同一段 raw 文字經 `postprocess()` 與經 `answer()`（假 Generator 回該文字）得到相同 `answer` / `citations` / `fabricated_markers` / `quality_report`（`test_postprocess_matches_answer_for_same_raw_text`）。
18. **Config 驗證**：未知欄位、`input_marker_base=2`、缺 placeholder 的 `user_prompt_template` 都 `ValidationError`；實例 frozen（`test_prompts_user_template_missing_placeholder_rejected`、`test_config_frozen_rejects_mutation_and_unknown_fields`）。
19. **預設 Generator**：`OpenAICompatGenerator` 對本機 `http.server` 送出 §4.12 規格的請求並回傳 content；HTTP 500 與格式錯誤 → `GeneratorError`（`test_openai_compat_*`）。
20. **runtime 與 contract 一致**：8 個類別的 `model_json_schema()` 去除 `description` 後與 `contracts/showreceipts_schema.py` 相等，且兩邊 validator 拒絕同一組非法輸入（`test_contract_runtime_json_schema_matches_contract`、`test_contract_runtime_validators_reject_same_invalid_inputs`）。
21. **Import 隔離**：AST 掃描無 stdlib / pydantic 以外的絕對 import；封鎖 langchain* / chromadb / streamlit / openai / httpx / requests / pydantic_settings / llama_index 後，import 與執行兩個入口與兩個 Adapter 成功，且未載入任何 Demo Host 模組（`test_isolation_ast_only_stdlib_and_pydantic_imports`、`test_isolation_import_with_blocked_frameworks_succeeds`）。
22. **LangChain Adapter 不需 langchain**：duck typing 物件與真 `Document` 都能轉；缺 id → `ValueError`；非文件物件 → `TypeError`（`test_langchain_*`）。
23. **外部路徑與 stale 標籤**：`query(q, reranked=sample)` 不呼叫 `retrieve`；`citation_view(..., origin=external, ...)` 的 `stale is False` 且該 id 不在 `live_lookup_ids` 結果中；本地查無仍 `stale is True`（`test_demo_external_*`、`test_citation_view_*`）。
24. **History v2**：外部引用經 `add_message` → `load_conversation` 後 `origin == "external"`、`source` / `locator` 保留；含舊欄位 `context_id` 的資料 `ValidationError`（`test_history_external_citation_roundtrip_keeps_origin_source_locator`、`test_history_v1_context_id_field_rejected`）。
25. **LangChain 範例**：`examples/langchain_postprocess.run()` 搭配 `FakeListChatModel` 回 0-based 答案，經 `postprocess` 正規化為 1-based、移除 `[7]`（`test_demo_langchain_example_fake_llm_zero_based_postprocess`）。
26. **全套測試綠**：`pytest -m "not requires_ollama" -q` 退出碼 0；`bash scripts/regression.sh` 退出碼 0。
27. **Demo UAT（D28，手動）**：Streamlit 中依序完成——(a) 本地知識庫模式問「臺新 Richart 卡鈦金商務卡年費多少？」得到帶 `[n]` 的答案（前提見 §8 Q11）；(b) 外部檢索結果模式以預填的 sample JSON 問「切換 Pay 著刷最高回饋多少？在超商用 LINE Pay 有回饋嗎？」「繳保費可以拿到多少回饋？切換假日刷呢？」，Citation 顯示快照且無 stale 標籤、重新整理頁面後仍無；(c) 終端執行 `python examples/langchain_postprocess.py "一般消費回饋是多少？有上限嗎？"` 印出 raw 與正規化後答案；README 有三條路徑的操作說明。
28. **Spec 100 contracts 標記 superseded**：`specs/100-migration-foundation/contracts/chunk_schema.py` 檔頭含 `Superseded by: specs/106-showreceipts`（`grep -q` 成功），且 `test_contract_fixture` 仍綠。

---

## 7. 遷移步驟

每一步結束時 `pytest -m "not requires_ollama" -q` 必須全綠，`streamlit run app.py` 必須能啟動。

1. **契約與骨架**：新增 `src/showreceipts/{__init__,models,config}.py`、`quality/{__init__,models}.py`、`adapters/__init__.py`（先空 `__all__`），內容與 contract 一致；`pyproject.toml` 明列 `pydantic>=2.6`；加 `test_contract_parity.py`、`test_isolation_ast_only_stdlib_and_pydantic_imports`、`test_contracts_fixtures.py` 新 fixture 列。既有程式不動。
2. **Marker 正規化**：新增 `markers.py` 與 `test_markers.py`。`src/citation.py` 仍在、仍被 `rag_chain` 使用。
3. **Quality Report**：新增 `quality/{sentences,support,entities,uncited,report}.py`（從 `src/eval/` 複製後改名）與 `test_quality.py`。`src/eval/` 仍在、仍被 `app.py` 使用。
4. **Prompt、Generator、入口**：新增 `prompts.py`、`generators.py`、`pipeline.py`；`__init__.py` 補齊 `__all__`；加 `test_prompts.py`、`test_pipeline.py`、`test_generators.py`、`test_isolation_import_with_blocked_frameworks_succeeds`、`test_isolation_public_api_all_matches_spec`（此時兩者中涉及 Adapter 的部分先跳過，步驟 5 打開）。
5. **Adapters**：新增 `adapters/arrkb.py`、`adapters/langchain_docs.py` 與兩份測試；打開步驟 4 跳過的 Adapter 斷言（`adapters.__all__`、封鎖 import 時執行 `from_arrkb` / `from_langchain`）。
6. **Demo Host 切換**（同一個 commit 內完成，避免中途壞掉）：
   1. Lead 手動刪除 `data/history.sqlite`（D27）
   2. 改 `src/llm.py`、`src/rag_chain.py`、`src/retrieval.py`、`src/utils.py`、`rag.py`
   3. 改 `src/history/models.py`（載入 106 `demo_host_history_schema.py`）與 `src/history/store.py`
   4. 新增 `src/citation_view.py`；`app.py` 改用 `CitedAnswer` / `citation_view` / `quality_report`（此步不加外部模式）
   5. 刪除 `src/citation.py`、`src/prompts.py`、`src/eval/`，以及 `tests/unit/test_citation.py`、`test_eval_support.py`、`test_eval_entities.py`、`test_reranked_adapter.py`
   6. 改 `tests/unit/test_history_store.py`；新增 `tests/unit/test_citation_view.py`、`tests/integration/test_demo_host_paths.py`（本地與外部 dict 路徑）；調整 `tests/integration/test_pipeline_end_to_end.py`
   7. 在 Spec 100 `contracts/chunk_schema.py` 檔頭加 `Superseded by: specs/106-showreceipts`（D18）；Spec 103 / 104 contracts 是否比照，依 §8 Q9 裁決執行
7. **Demo 功能**：`app.py` 加「外部檢索結果」模式與「含數字但未標來源的句子」小節；新增 `examples/langchain_postprocess.py` 與 `test_demo_langchain_example_fake_llm_zero_based_postprocess`、`test_demo_external_sample_json_cites_sample_passages`、`test_demo_external_empty_list_returns_default_no_answer_reply`。
8. **文件與 UAT**：更新 README、CLAUDE.md、`specs/plan.md`、`specs/CLAUDE.md`；跑 AC #27 手動 UAT。

---

## 8. Risks / 開放問題

### 8.1 Risks

| # | 風險 | 影響 | 緩解 |
|---|---|---|---|
| R1 | marker 文法變寬，正文中的方括號數字（`[2024]`、程式碼裡的 `[1, 2]`）更容易被當成 Fabricated Marker 刪掉 | 答案內容被誤刪 | Tier 1 已會刪 `[n]`，範圍只是變大；刪掉的群組都記在 `fabricated_markers`，UI 可追查；code block 豁免列 Out of scope |
| R2 | 整段答案做連續空白壓縮，會壓掉 code block 縮排與對齊空白 | 程式碼答案排版變形 | Tier 1 既有行為，需 Lead 批准才改；本 spec 不動 |
| R3 | 模型把 marker 寫在句號後（「…。[1]」） | 前一句被標為 Uncited Sentence 與 unsupported，`quality_score` 偏低 | Quality Report 只報不攔（D12）；修法見 Q7 |
| R4 | `OpenAICompatGenerator` 用 `urllib`：會讀 `HTTP(S)_PROXY`；`NO_PROXY` 未含 localhost 時，連本機 Ollama 可能被送進 proxy；無重試 | demo 現場連不上模型 | README 註明 `NO_PROXY=localhost,127.0.0.1`；錯誤統一包成 `GeneratorError` 便於顯示 |
| R5 | `import src.showreceipts` 會觸發 `src/__init__.py` 的 `setup_logging()`（`basicConfig`） | 在 repo 內使用時有全域 logging 副作用 | 模組本身不設定 logging；抽套件後自然消失；隔離測試明列此唯一例外 |
| R6 | runtime DTO 與 contract 檔各有一份 | 兩邊漂移 | `test_contract_runtime_json_schema_matches_contract`、`test_contract_runtime_validators_reject_same_invalid_inputs` |
| R7 | Uncited Sentence 只看數字，Markdown 表格列、含年份的標題也會被標 | 誤報增加 | 只報不攔；判定範圍見 Q6 |
| R8 | 使用者把 `quality_score` 當正確率 | 誤解 demo 結論 | 沿用 README 現有說明：字面重疊訊號，不代表事實正確 |
| R9 | Spec 104 句切分把有序清單的「2.」切成獨立句（既有行為），它在 `sentence_supports` 中計為 unsupported | `quality_score` 對條列式答案偏低 | Uncited 檢查已排除純序號句；句切分本身見 Q7 |

### 8.2 開放問題（請 Lead 裁決；本 spec 先採「維持既有行為」或「D 決策的最字面解讀」為暫定值，並已寫進 §4 與測試）

| # | 問題 | 暫定值（已寫入 spec） | 替代方案 |
|---|---|---|---|
| Q1 | post-process 遇到重複 Passage ID：D23「只留第一個」與 D24「依原 prompt 順序對齊」合併時，marker 編號該怎麼對 | 以原始清單位置（含重複）建 slot，重複者收斂到第一次出現的 Passage（§4.7、例 19） | 先去重再編號——但會讓重複之後的所有編號錯位 |
| Q2 | `postprocess()` 收到零 Passage 時 | 依 D16 字面回 No-Answer Reply，`raw_answer` 保留原文 | 保留原答案文字，只把所有 marker 當 Fabricated 移除 |
| Q3 | D5「prompt 組裝是 pure function、不需模型即可使用」與 D19「恰好兩個公開入口」 | `build_prompt` 可從 `showreceipts.prompts` 匯入，但不列頂層 `__all__` | 列入頂層 `__all__`，明定「入口」只指產生 Cited Answer 的函式 |
| Q4 | D5「預設 Generator」的意思 | `generator` 必填；`OpenAICompatGenerator` 是隨附的預設實作 | `generator=None` 時以 config 內的 base_url / model 自動建立（需在 `ShowReceiptsConfig` 加連線欄位） |
| Q5 | D11 未涵蓋的寫法 | 反向範圍 `[3-1]` 整段視為 Fabricated；en dash `[1–3]`、波浪號 `[1~3]`、全形括號 `【1】` / `［1］` 不認；同號重複 `[1, 1]` → `[1][1]` 不去重（維持 Tier 1 `[2][2]` 行為） | 反向範圍自動對調；擴充分隔字元；同群組內去重 |
| Q6 | D13「數字或事實內容」的範圍 | v1 只看十進位數字（排除行首清單序號） | 加中文數字（「三百萬」）、百分比文字、專有名詞等規則 |
| Q7 | Spec 104 句切分的兩個既有問題：marker 寫在句末標點之後（R3）、有序清單「2.」被切成獨立句（R9） | 不改 Spec 104 句切分，兩者誤差照舊 | 切句後把句首的純 marker 併回前一句、把純序號片段併入下一句（兩者都會改變 `quality_score` 既有算法） |
| Q8 | LangChain 文件沒有 id | `ValueError`，請呼叫端指定 `id_key` | 以 `page_content` 的雜湊產生穩定 ID |
| Q9 | D18 只點名 Spec 100；Spec 103 `history_schema.py`、Spec 104 `quality_report_schema.py` 也會失去 runtime 對應 | v2 history 契約放在本 spec `contracts/demo_host_history_schema.py`；103 / 104 是否加 superseded 註記待裁決 | 直接修改 Spec 103 contract 檔；或 103 / 104 不標記 |
| Q10 | 外部引用重載後不加 stale 標籤需要記住來源 | `StoredCitation` 每筆加 `origin`（`local` / `external`），並存 `source` / `locator` | 在 `Message` 層記一個 retrieval mode |
| Q11 | D28 本地路徑要問 Richart 問題，但 `data/docs/*` 被 `.gitignore` 排除，repo 內沒有可入庫的 Richart 文件 | 未決；AC #27(a) 以「Lead 事先上傳一份 Richart 文件」為前提 | 由 `data/sample_reranked.json` 產生 `data/demo/richart_sample.md` 並 commit，UAT 先入庫此檔 |
| Q12 | 頁碼顯示 | 維持「第 {page} 頁」原值（本地 PDF 為 0-based、非 PDF 顯示「第 0 頁」），以保持 prompt byte-identical | 本地 PDF 改 1-based、非 PDF 留空 Locator（會改變 prompt） |
| Q13 | D9「模組與專案同名」是否包含現在就把 `pyproject.toml` 的 `name = "tag-rag"`、README 標題改為 showreceipts | 本 spec 只建 `src/showreceipts/`，不改專案名 | 步驟 8 一併改名 |
| Q14 | `CitedAnswer` 除 GLOSSARY 所列（答案、Citation、Quality Report）外另有 `raw_answer`、`passages`、`fabricated_markers` | 保留（`passages` 對應現行 `retrieved`；另兩欄供 demo 展示與除錯） | 刪去 `raw_answer` / `fabricated_markers`，只在 log 中記錄 |

---

## 9. Out of scope（再次強調）

- **Streaming**（**第 2 次重複提醒**）：D26
- **逐字 quote 驗證模式**（**第 2 次重複提醒**）：D14，demo 之後
- **LLM-as-judge**（**第 2 次重複提醒**）：Quality Report 永遠不呼叫模型
- **NER 套件**（**第 2 次重複提醒**）：不引入 spaCy / hanlp / ckip / jieba
- **依 score 重排 Passage**（**第 2 次重複提醒**）：D22
- **攔截、改寫或拒答**（**第 2 次重複提醒**）：D12，Quality Report 只回報
- **模組內 import LangChain / Chroma / Streamlit**（**第 3 次重複提醒**）：D8 / D21；LangChain Adapter 也只能 duck typing
- LlamaIndex Adapter、IT 移交 spec、抽 pip 套件
- 遷移舊對話歷史
- 依賴 groundcite / citeformer / LlamaIndex / LangChain 的引用功能
- 調整 Spec 104 門檻、Quality Report 持久化
- 改 `context_id` 演算法、loaders、chunking、vectorstore、`Settings` 預設值
- Code block 內 marker 豁免、全形括號與 en dash 範圍（待 Q5）
- UI 美化

---

## 10. 參考

- 決策紀錄：[ADR-0001](../../docs/adr/0001-framework-agnostic-citation-layer.md)
- 術語：[GLOSSARY.md](../../GLOSSARY.md)
- 調查：[docs/research/related-projects.md](../../docs/research/related-projects.md)
- 上游 spec：[Spec 100](../100-migration-foundation/spec.md)、[Spec 103](../103-chat-history-persistence/spec.md)、[Spec 104](../104-quality-eval-hallucination/spec.md)、[Spec 105](../105-ui-integration/spec.md)
- SDD 規範：[specs/CLAUDE.md](../CLAUDE.md)、[specs/plan.md](../plan.md)（Tier 1 既有行為表）
- 契約：[contracts/showreceipts_schema.py](contracts/showreceipts_schema.py)、[contracts/demo_host_history_schema.py](contracts/demo_host_history_schema.py)、[contracts/fixtures/](contracts/fixtures/)
- 範例輸入：[data/sample_reranked.json](../../data/sample_reranked.json)
