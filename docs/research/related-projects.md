# 相關專案調查：框架無關的 RAG 引用層

調查日期：2026-10-19。目的：在把本專案改成「可接任何 RAG 框架的引用層」之前，確認是否已有可直接採用或值得借鏡的專案。

## 結論

沒有找到同時具備下列五點的現成專案：(1) 只負責檢索之後的那一段、與框架無關；(2) 解析 `[n]` 並依首次出現順序重編號；(3) 從答案中移除 Fabricated Marker；(4) 不呼叫模型的中文品質檢查；(5) 可注入任意模型（含本地 Ollama）。現有專案大多只做其中一兩點，所以建議自建，但借用下面標出的幾個做法。

## 一、最接近的獨立套件

| 專案 | 做什麼 | 與本專案的差異 | 成熟度 |
|---|---|---|---|
| [citeformer](https://github.com/random-walks/citeformer) | 產生帶 `[n]` 的答案、用 grammar 限制解碼讓越界編號無法被生成、DeBERTa NLI 驗證、輸出學術書目格式；有 LangChain `Document` 與 LlamaIndex `NodeWithScore` 轉換範例 | 範圍最像，但依賴很重（transformers、vLLM、XGrammar…）；grammar 限制需要掌控解碼，透過 Ollama 的 OpenAI 相容介面做不到；NLI 模型以英文為主；沒有提到重編號 | v0.1.0，6 stars，Apache-2.0 |
| [groundcite](https://github.com/JafarBanar/groundcite) | 純規則、零依賴：檢查 `[n]` 是否都對應到送入的來源、計算「事實句有引用」的覆蓋率、可選逐字 quote 檢查；引用格式可用自訂 regex | 跟本專案的 `citation.py` + `eval/` 最像，但只檢查、不生成、不重編號 | 5 commits，0 stars，MIT |
| [rag-citation](https://deepwiki.com/rahulanand1103/rag-citation) | 事後比對：用 spaCy NER + SentenceTransformers 把答案對回來源，標出不被支持的日期、金額、數量 | 依賴 spaCy 與嵌入模型；概念類似本專案的 entity flags | 授權未標明 |

## 二、「逐字引述」型驗證閘（fail-closed）

這一類要求模型對每個引用附上一段原文 quote，再用確定性的子字串比對驗證，任一條不通過就整個拒答。

- [rag-citation-gate](https://github.com/yschang1688/rag-citation-gate)：繁體中文、台灣法規（銀行法、個資法、洗錢防制法），技術棧與本專案幾乎相同（Ollama、bge-m3、qwen3.5:9b）。三項檢查：引用必須來自本輪檢索、quote 去空白後逐字存在、quote 至少 8 字。16 commits，MIT。
- [citation-guard](https://github.com/sibalabs/citation-guard)：模型回傳 JSON（`answer` 含 `[n]`、`citations: [{n, quote}]`），quote 必須逐字出現在對應段落；若 quote 只出現在另一段，會自動改指；零依賴。1 commit，MIT。
- [verbatim-citation-gate](https://github.com/tonydzi/verbatim-citation-gate)：第一階段逐字比對（零 token），第二階段可選 LLM 判斷 quote 是否真的支持論述；LLM 以 `(system, user) -> str` callable 注入。v0.1.0，MIT。
- [grounding-verifier](https://github.com/sealmindset/grounding-verifier)：逐字或丟棄、LLM 事實檢查、無法解析就升級一次再 fail-closed。1 commit，MIT。

## 三、框架內建做法

- **LlamaIndex [CitationQueryEngine](https://developers.llamaindex.ai/python/examples/workflow/citation_query_engine/)**：把檢索到的 node 再切成約 512 token 的小段，全域編號為 `Source N`，prompt 要求依編號引用；不驗證、不重編號模型輸出的標記。本專案的 prompt 策略原本就是參考它。
- **Haystack [AnswerBuilder](https://docs.cloud.deepset.ai/docs/answerbuilder)**：以 `reference_pattern` regex 解析答案中的引用，`return_only_referenced_documents` 只保留被引用的文件，`expand_reference_ranges` 可把 `[6-10]` 展開。沒有說明會重編號或移除無效標記。
- **LangChain [QA citations how-to](https://www.langchain.com.cn/docs/how_to/qa_citations/)**：五種做法（structured output 回傳來源 ID、回傳 ID+quote、XML prompt、檢索後壓縮、生成後二次標註）。範例程式不驗證模型回傳的 ID。

## 四、模型原生引用

- **Anthropic [Citations API](https://claude.com/resources/articles/introducing-citations-api)**：送入文件（或自訂分段），模型回傳的引用直接指向原文片段。綁定特定供應商，無法用於本地 Ollama；可作為未來的一種 Generator 選項。
- [citeformer 的 ADR-013](https://citeformer.readthedocs.io/en/latest/decisions/013-citation-rich-attribution.html) 把這類供應商回報的 `cited_text`、`source_span` 收進統一的 Citation 欄位，作法可參考。

## 五、研究

- **VeriCite**（SIGIR-AP 2025，[論文](https://arxiv.org/html/2510.11394v1)）：生成初稿 → 用 NLI 模型逐句驗證並丟掉不被支持的句子 → 選證據 → 合併成最終答案。消融實驗中拿掉 NLI 驗證，引用 F1 從 77.7 掉到 68.9，而答案正確率幾乎不變；用生成模型自己當驗證者，品質反而下降。

## 可借鏡的做法（供設計討論）

1. **引用格式容錯**：Haystack 與 groundcite 都支援多種標記格式。本專案目前的 `CITE_RE` 只認 `[n]`，小模型常輸出的 `[1, 2]`、`[1-3]` 既不會被計入也不會被移除。
2. **未引用句覆蓋率**：groundcite 統計「有事實內容卻沒有引用」的句子，比單看有引用的句子更能抓到幻覺。
3. **逐字 quote 模式**：中文、同技術棧的 rag-citation-gate 已證明可行，比字元 3-gram 重疊更強，但需要模型配合輸出結構化 quote。
4. **fail-closed 選項**：驗證失敗時由呼叫端決定要顯示、警告或拒答。
5. **Generator 介面**：verbatim-citation-gate 的 `(system, user) -> str` 與本專案決定注入的 Generator 形狀一致，代表這個介面在其他專案也行得通。
