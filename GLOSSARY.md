# 引用層（Citation Layer）

一個不綁定任何 RAG 框架的模組：拿到段落（來自任何檢索系統，或直接從文件切出），產出帶 inline `[n]` 引用的答案與品質檢查結果，一次處理一輪問答。本 repo 其餘部分是它的示範宿主。

## Language

### 輸入

**Passage**：
餵進引用層的一段可引用文字，由上游檢索系統提供，或由引用層從文件切出。一個 Passage 是 `[n]` 能指向的最小單位。
_Avoid_: chunk, RetrievedChunk, RerankedChunk, node, document

**Passage ID**：
Passage 的穩定識別字串，格式由上游框架決定，引用層不解讀其結構。
_Avoid_: context_id, chunk_id, doc_id

**Source**：
Passage 所屬文件的人類可讀名稱，只用於顯示與提示，不是識別碼。
_Avoid_: filename, file

**Locator**：
Passage 在 Source 內的位置描述，例如頁碼、工作表或章節；可以沒有。
_Avoid_: page, chunk_index, offset

**Adapter**：
把某個檢索系統（例如 arrkb、LangChain）的結果轉成 Passage 的轉換器；引用層對外部檢索系統的所有認識都只存在於 Adapter。
_Avoid_: connector, loader, plugin

**Generator**：
引用層用來產生答案文字的語言模型，由使用者提供；引用層不綁定任何特定模型或 SDK。
_Avoid_: LLM client, backend

### 輸出

**Citation**：
答案實際引用到的 Passage，連同它在答案中的顯示編號。編號依答案中首次出現的順序從 1 連號。
_Avoid_: reference, source（指引用時）

**Citation Marker**：
答案文字中指向 Passage 的編號標記。模型可能寫成 `[1, 2]` 或 `[1-3]`，引用層一律正規化為逐一的 `[1][2]` 形式。
_Avoid_: tag, footnote, 角標

**Fabricated Marker**：
不對應任何送入 Passage 的 Citation Marker；引用層會把它從答案中移除。
_Avoid_: invalid citation, hallucinated citation

**Uncited Sentence**：
答案中帶有數字或事實內容、卻沒有任何 Citation Marker 的句子；Quality Report 會標出它。
_Avoid_: missing citation, orphan sentence

**Cited Answer**：
引用層的輸出，包含重編號後的答案文字、Citation 清單，以及選配的 Quality Report。
_Avoid_: RagAnswer, response

**Quality Report**：
對 Cited Answer 做的確定性、不呼叫模型的檢查結果，供人工覆核參考，不代表答案正確。它只回報、不攔截；顯示、警告或拒答由呼叫端決定。
_Avoid_: hallucination score, accuracy

**No-Answer Reply**：
沒有任何 Passage 可用時，引用層不呼叫模型、直接回覆的固定訊息（預設「依現有資料無法回答」，可覆寫）。
_Avoid_: empty answer, fallback message

### 邊界

**Demo Host**：
本 repo 中不屬於引用層、只用來示範與測試它的部分（介面與範例腳本）。
_Avoid_: core, app（指整個專案時）
