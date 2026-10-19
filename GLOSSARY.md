# 引用層（Citation Layer）

一個可接在任何 RAG 框架後面的模組：拿到上游已檢索好的段落，產出帶 inline `[n]` 引用的答案與品質檢查結果。本 repo 其餘部分是它的示範宿主。

## Language

### 輸入

**Passage**：
餵進引用層的一段可引用文字，由上游框架檢索後提供。一個 Passage 是 `[n]` 能指向的最小單位。
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
把某個 RAG 框架的檢索結果轉成 Passage 的轉換器；引用層對外部框架的所有認識都只存在於 Adapter。
_Avoid_: connector, loader, plugin

**Generator**：
引用層用來產生答案文字的語言模型，由使用者提供；引用層不綁定任何特定模型或 SDK。
_Avoid_: LLM client, backend

### 輸出

**Citation**：
答案實際引用到的 Passage，連同它在答案中的顯示編號。編號依答案中首次出現的順序從 1 連號。
_Avoid_: reference, source（指引用時）

**Fabricated Marker**：
答案中出現、但不對應任何送入 Passage 的引用標記；引用層會把它從答案中移除。
_Avoid_: invalid citation, hallucinated citation

**Cited Answer**：
引用層的輸出，包含重編號後的答案文字、Citation 清單，以及選配的 Quality Report。
_Avoid_: RagAnswer, response

**Quality Report**：
對 Cited Answer 做的確定性、不呼叫模型的檢查結果，供人工覆核參考，不代表答案正確。
_Avoid_: hallucination score, accuracy

### 邊界

**Demo Host**：
本 repo 中不屬於引用層的部分（本地檢索、文件載入、對話歷史、介面），用來示範與測試引用層。
_Avoid_: core, app（指整個專案時）
