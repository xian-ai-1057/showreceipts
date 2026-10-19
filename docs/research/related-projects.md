# 相關專案調查：框架無關的 RAG 引用層

調查日期：2026-10-19。目的：本專案要改成「接在任何 RAG 框架檢索之後的引用層」。改之前，先確認有沒有可直接採用的現成專案，以及有哪些做法值得借用。

## 結論

**原主張大致成立，但措辭要改得更精確。**「沒有現成專案同時具備五項能力」這點，經過反向檢驗仍然成立：下表中沒有任何一列有三項以上的 ✓。不過，五項能力**各自都已有前例**：
- 依首次出現順序重編號：[STORM](https://github.com/stanford-oval/storm)、[langchain-references](https://www.github.com/pprados/langchain-references)；供應商端有 [xAI](https://docs.x.ai/developers/tools/citations)
- 刪除 Fabricated Marker：[Onyx](https://github.com/onyx-dot-app/onyx/blob/main/backend/onyx/chat/citation_processor.py)、STORM、[LongCite](https://raw.githubusercontent.com/THUDM/LongCite/HEAD/vllm_inference.py)，以及閉源的 [Vaquill](https://www.vaquill.ai/engineering/catching-a-fabricated-citation)
- 可處理 CJK 的確定性檢查：[citeglow](https://pypi.org/project/citeglow/)、[axiom-rag-engine](https://github.com/FurkhanShaikh/axiom-rag-engine)
- `(system, user) -> str` 注入介面：[verbatim-citation-gate](https://github.com/tonydzi/verbatim-citation-gate)

所以本專案的新意在於「組合」。建議改寫成：

> 沒有找到一個**與框架無關、事後處理**的函式庫，能同時做到：(a) 在答案文字中依首次出現順序把 `[n]` 重編為 1..N；(b) 刪除指向不存在段落的標記；(c) 產出不呼叫模型、針對繁體中文調校的品質報告（字元 n-gram，加上萬／億、民國年等數字與日期檢查）；(d) 生成端以 callable 注入。

### 最接近的候選

✓ 有、✗ 無、？ 未確認。

| 候選 | ① 框架無關、檢索後 | ② 解析＋首次出現重編號 | ③ 刪除 Fabricated Marker | ④ 不呼叫模型、可用於中文的檢查 | ⑤ 注入任意模型 |
|---|---|---|---|---|---|
| [STORM](https://github.com/stanford-oval/storm) | ✗ 重編號寫在 `StormArticle` 內（[storm_dataclass.py](https://raw.githubusercontent.com/stanford-oval/storm/HEAD/knowledge_storm/storm_wiki/modules/storm_dataclass.py)） | ✓ `reorder_reference_index` | ✓ 刪越界標記，但有 off-by-one（[utils.py](https://raw.githubusercontent.com/stanford-oval/storm/HEAD/knowledge_storm/utils.py)） | ✗ | ✗ |
| [Onyx](https://github.com/onyx-dot-app/onyx) `DynamicCitationProcessor` | ✗ 應用內部 | ✗ 顯示原編號，新文件取 `max+1`（[source](https://github.com/onyx-dot-app/onyx/blob/main/backend/onyx/chat/citation_processor.py)） | ✓ HYPERLINK／REMOVE 模式丟棄未知編號；`[1, 99]` 只保留 1 | ✗ | ✗ 應用本身支援 Ollama，但沒有注入介面 |
| [langchain-references](https://www.github.com/pprados/langchain-references) | ✗ 包裝 LangChain Runnable | ✓ 去重、重編號 | ？ | ✗ | 只能透過 LangChain 模型 |
| [LongCite](https://github.com/THUDM/LongCite) | ✗ | ✗ | ✓ 只限它自己的 `<cite>[a-b]` 格式（[vllm_inference.py](https://raw.githubusercontent.com/THUDM/LongCite/HEAD/vllm_inference.py)） | ✗ 以 GPT-4o 評審 | ✗ |
| [groundcite](https://github.com/JafarBanar/groundcite) | ✓ 零依賴 | ✗ | ✗ 只回報 `unresolved_refs` | 部分：覆蓋率與 quote 檢查是規則式，未提 CJK | 不適用（不生成答案） |
| [citation-guard](https://github.com/sibalabs/citation-guard) | ✓ 零依賴 | ✗ 只改指 | ✗ 不通過就整份拒絕 | 部分：逐字子字串比對，未提 CJK | 不適用 |
| [verbatim-citation-gate](https://github.com/tonydzi/verbatim-citation-gate) | ✓ | ✗ 不處理 `[n]` | ✗ | 部分：Stage 1 逐字比對，CJK 未測 | ✓ `llm_call(system, user) -> str` |
| [acclaim](https://github.com/jwallat/acclaim) | ✓ | ✗ | ✗ 只計算 `hallucination_rate` | ✗ 英文 pysbd＋空白切詞（[text_utils.py](https://raw.githubusercontent.com/jwallat/acclaim/main/acclaim/text_utils.py)） | ✓ LiteLLM，含 Ollama |
| [citeformer](https://pypi.org/project/citeformer/) | 部分：自己負責生成；LangChain 與 LlamaIndex 要手動轉成 `Source` | ✗ 未提 | ✗ 靠 grammar 讓越界編號無法生成，不是事後刪除 | ✗ DeBERTa NLI | ？ 後端清單沒有 Ollama，有 `Backend` ABC（[GitHub](https://github.com/random-walks/citeformer)） |
| [axiom-rag-engine](https://github.com/FurkhanShaikh/axiom-rag-engine) | ✗ LangGraph／FastAPI 服務 | ？ | ？ | ✓ CJK quote 至少 12 字、逐字比對 | ✓ 經 LiteLLM，不是 callable |
| [rag-citation-gate](https://github.com/yschang1688/rag-citation-gate) | ✗ 應用／demo | ✗ | ✗ 整份拒答 | ✓ 繁中逐字 quote，三項規則 | ✗ 固定使用 Ollama |
| [RAGFlow](https://github.com/infiniflow/ragflow) | ✗ | ✗ 只依首見順序抽出（[citation.go](https://github.com/infiniflow/ragflow/blob/main/internal/service/citation.go)） | ✗ `stripCitations` 不檢查範圍 | ✗ 九成權重靠嵌入模型，沒有報告 | ✗ |
| [MariaDB AI RAG](https://mariadb.com/docs/tools/mariadb-ai-rag/reference/citations) | ✗ 內部元件 | ？ | ？ 文件寫「確認沒有引用不存在的來源」，但沒說怎麼處置 | ✗ | ？ |
| [Vaquill](https://www.vaquill.ai/engineering/catching-a-fabricated-citation)（閉源） | ✗ | ✗ | ✓ 已知規格中最精確 | ✗ 含數字的主張會轉交模型（[來源](https://www.vaquill.ai/engineering/what-our-citation-verifier-checks)） | ✗ |

**本輪調查的限制**
- WebSearch 的共用額度已用完，這輪只能用 WebFetch 直接抓已知頁面。
- 未確認的項目：
  - Open WebUI 怎麼處理引用：[README](https://github.com/open-webui/open-webui) 與 [RAG 文件頁](https://docs.openwebui.com/features/rag)都沒寫，原始碼的 raw 檔被 robots 擋下。
  - R2R 的 `raw_index` 與 `index` 是什麼關係。
  - MariaDB 遇到無效標記會怎麼處置。
  - Microsoft GraphRAG、gpt-researcher、open_deep_research 的引用格式。
  - 台灣專案：只查了 rag-citation-gate、[MarkdownKB](https://github.com/jeff377/markdown-kb) 與 [Kuwa GenAI OS](https://github.com/kuwaai/genai-os)。Kuwa 的 README 沒有任何引用細節。
- 星數一律取自調查當日抓到的頁面，查不到的寫「未確認」。

## 一、引用標記處理的獨立套件與程式碼

| 專案 | 做什麼 | 與本專案的差異 | 成熟度 |
|---|---|---|---|
| [groundcite](https://github.com/JafarBanar/groundcite) | 純規則：檢查引用是否都對應到送入的來源；計算「事實句有引用」的覆蓋率，標題、表格、code block 不列入；quote 檢查可選。格式支援 `[3]`、`[3, 5]`、`[3][5]`、`[Source 3]`、`[SB-2231]`，也可自訂 regex | 只檢查、不重編號；沒說會不會刪除標記；沒有數字或日期檢查 | 0 stars、5 commits、MIT |
| [citation-guard](https://github.com/sibalabs/citation-guard) | 每個 `[n]` 都要有逐字 quote；quote 只出現在**唯一另一段**時自動改指，有歧義就拒絕；答案沒有標記時，只替已驗證的 quote 補上標記 | 不重編號；失敗時整份拒絕，不是刪掉單一標記 | 0 stars、1 commit、MIT |
| [langchain-references](https://www.github.com/pprados/langchain-references) | 串流時先暫存疑似標記的 token；去重並重編號；同一 URL 的片段共用一個編號；未被引用的片段不列入參考清單 | 綁定 LangChain；README 裡的標記格式前後不一致；未說明怎麼處理無效 ID | 2 stars、Apache-2.0、PyPI 1.0.0（2025-12-22，[PyPI](https://pypi.org/project/langchain-references/)） |
| [Onyx `citation_processor.py`](https://github.com/onyx-dot-app/onyx/blob/main/backend/onyx/chat/citation_processor.py) | regex 接受 `[n]`、`[[n]]`、`[1, 2]` 以及全形 `【】`、`［］`；略過 code fence 內的標記；串流時暫存不完整標記；三種模式 HYPERLINK／KEEP_MARKERS／REMOVE | 不重編號（`cited_documents_in_order` 只記錄順序，不改寫文字）；是應用內部元件 | Onyx 32.5k stars，CE 為 MIT（[repo](https://github.com/onyx-dot-app/onyx)） |
| [STORM `ArticleTextProcessing`](https://raw.githubusercontent.com/stanford-oval/storm/HEAD/knowledge_storm/utils.py) | `update_citation_index` 經 `__PLACEHOLDER_n__` 分兩段替換，避免連鎖替換；[`reorder_reference_index`](https://raw.githubusercontent.com/stanford-oval/storm/HEAD/knowledge_storm/storm_wiki/modules/storm_dataclass.py) 依首次出現編成 1..N；刪除越界標記 | 1-based 標記被當成 0-based 處理，`[len(sources)]` 這個合法編號也會被刪掉；`parse_citation_indices` 不認 `[1, 2]` | 31.6k stars、MIT、knowledge-storm 1.1.1（[PyPI](https://pypi.org/project/knowledge-storm)） |
| [citecite / citecite-mcp](https://www.getdrio.com/mcp/io-github-mukundakatta-citecite-mcp/md) | 一個 Rust crate 加 npm MCP server，提供 `inject_citations`、`parse_citations`、`strip_citations` 三個工具（[mcp-stack](https://github.com/MukundaKatta/mcp-stack)、[rust-llm-stack](https://github.com/MukundaKatta/rust-llm-stack)） | 文件沒寫是否重編號、是否刪除無效標記 | npm 0.1.1、0 stars、MIT OR Apache-2.0 |
| [ragcite](https://github.com/pcbeingused333/ragcite) | 確定性的 ID 集合比對，回傳 `fabricated` 集合；`strip_reasoning` 移除 `<think>`；`judge_fn` 可注入；`check_judge_independence` 防止評審模型和受測系統是同一個 | 只評估，不改寫答案 | v0.6.0、0 stars、9 commits、MIT，尚未上 PyPI |
| [markdown-ai-cite-remove（mdcr）](https://dev.to/opensite/santa-came-early-i-just-published-a-rust-crate-and-cli-tool-to-take-care-of-ai-markdown-citations-521h) | 移除 `[1]`、`[source:1]`、`[ref:2]`、參考連結定義、References 標題 | 全部刪掉，不驗證也不重編號 | crates.io；repo 未確認 |
| [Autosearch citation-index](https://openskillindex.com/skills/0xmariowu-autosearch-autosearch-citation-index) | 先把 URL 正規化，再依首見順序編號，把 `[ref: url]` 改寫成數字 | Agent skill 的虛擬碼，不處理既有的 `[n]` | MIT，屬 skill manifest |
| [80,000 Hours citations.py](https://huggingface.co/spaces/Automaton9/80000_Hours_AI_Assistant/blob/main/citations.py) | 拒絕 `<1` 或越界的 source_id；用 rapidfuzz 比對 quote；quote 對上別段時改指（`remapped: True`） | 不改寫答案文字、不重編號；輸入是 JSON 格式 | HF Space 單檔，授權未確認 |

其他查過、但對本專案價值較低的：
- [CodeRAG CitationParser](https://huggingface.co/spaces/Sebastiangmz/CodeRAG/blob/main/src/coderag/generation/citations.py)：只拆成 (valid, invalid)，不改寫文字。
- [Agentset 指引](https://docs.agentset.ai/search-and-retrieval/citations.md)：建議模型引用穩定的 chunk ID，輸出時才換成顯示編號；比對不到的 ID 保留成純文字。
- [Vercel InlineCitation](https://elements.ai-sdk.dev/components/inline-citation)：UI 元件，預告 2026 年 11 月底淘汰。

## 二、不呼叫模型的品質檢查

| 專案 | 做什麼 | 與本專案的差異 | 成熟度 |
|---|---|---|---|
| [sourced-evidence](https://pypi.org/project/sourced-evidence/0.4.0/) | 逐句分成 grounded／contradicted／unverified；數字依值比較（`56B` 等於 `$56 billion`，`5` 不算出現在 `56` 裡）；數字、quote、名稱必須同時出現在同一段 | 沒有 `[n]` 處理；名稱判斷靠英文大寫；不處理萬／億、民國年 | 0.4.1（2026-10-15）、MIT |
| [ancora-rag](https://pypi.org/project/ancora-rag/0.1.1/) | 以 IDF 加權的 token 覆蓋率判定支持度；可要求每個數字都必須出現在段落中，支援 pt-BR／it-IT／en-US 的數字格式；可轉交人工或拒答 | 沒有 `[n]` 重編號；未提 CJK | 0.1.1（2026-10-09）、Beta、MIT |
| [cite-check](https://github.com/habib-analyst/cite-check) | 分數 = 0.55×關鍵詞覆蓋 + 0.45×TF 重疊；數字不符時分數上限 0.25；否定翻轉判為 CONTRADICTED | README 明寫只支援英文；只有 CLI | 0 stars、2 commits、MIT |
| [citeglow](https://pypi.org/project/citeglow/) | 以 LCS 錨點找出來源中支持答案的字元區間；`char` tokenizer 可處理中文 | 只做高亮，不判定支持度 | 0.1.2（2026-05-06）、MIT |
| [verbatimeter](https://pypi.org/project/verbatimeter/) | 計算連續 n-gram 加 LCS 子序列的逐字重用率 | 頁面寫明「Chinese… not yet supported」 | 0.1.3、MIT |
| [citesure](https://pypi.org/project/citesure/) | 規則式詞彙覆蓋，可再加一層 NLI；解析不到的標記放進 `dropped_markers` 列出 | 自報只用詞彙時一致率 38%，低於全判不支持的 59.3% | 0.2.2、alpha、MIT |
| [ragground](https://pypi.org/project/ragground/) | 先跑模糊重疊，再把數字或實體有變動的句子交給 ONNX NLI；提供 `tune_thresholds` | NLI 模型以英文為主 | 0.2.2、MIT |
| [raguard-py](https://pypi.org/project/raguard-py/) | 日期 regex、spaCy NER、空泛指涉詞表；p95 < 10ms | v1 不檢查數字；中文要自己裝 spaCy 模型 | 0.1.1、MIT |
| [ClaimCheck rules](https://huggingface.co/NagaYu/claimcheck-rules) | 狀態分 supported／derived／approximate／unsupported／contradicted；處理千／万／億／兆與日本年號；提供分階段 preset | 只文件化英文與日文；作者自報約 13.9% 誤報 | v1.1.0、Apache-2.0 |
| [onus](https://pypi.org/project/onus) | 數字與日期以確定性規則檢查，模型推翻不了；規則代碼採 Ruff 風格（`ONS001`） | 處理 pptx／docx 的 CLI，沒有 Python API | 0.1.0 alpha、MIT |
| [acclaim](https://github.com/jwallat/acclaim) | 確定性指標：coverage、hallucination_rate、token_overlap；支持度由 LLM 判斷 | 英文斷句加空白切詞，中文不適用 | PyPI 0.1.0、0 stars、MIT |
| [axiom-rag-engine](https://github.com/FurkhanShaikh/axiom-rag-engine) | 標點視為 token 邊界（1.5 不會配對到 15）；CJK quote 至少 12 字 | 是完整服務，沒有可單獨呼叫的階段 API | 0.1.0b2、0 stars、MIT |
| [legal-rag-verifier](https://pypi.org/project/legal-rag-verifier/0.1.0/) | 檢查數字、日期、情態動詞與限定詞；遺漏限定詞只抓到 6/18 | 範圍是英文與英國法規；授權 **AGPL-3.0** | 0.2.0 |
| [anchor](https://github.com/hnvivek/anchor) | 純 Python 的否定詞閘門，加上本地 DeBERTa NLI | 核心靠模型 | 0 stars、MIT |
| [citationguard](https://socket.dev/pypi/package/citationguard) | 書目引用稽核；CJK 用字元 bigram 斷詞 | 不處理 RAG 的 `[n]` | 0.1.3、alpha、MIT |
| [citefact](https://pypi.org/project/citefact/) | 稽核學術稿件；報告附 `schema_version` | 只支援作者-年份格式 | 0.3.0、MIT |
| [ragproof](https://pypi.org/project/ragproof/) | CI 測試框架；算不出的指標標成 skipped 並附原因 | 端到端測試，不是檢索後元件 | 1.0.0（Alpha）、MIT |

## 三、逐字 quote 驗證閘（fail-closed）

| 專案 | 做什麼 | 與本專案的差異 | 成熟度 |
|---|---|---|---|
| [rag-citation-gate](https://github.com/yschang1688/rag-citation-gate) | 繁中台灣法規；三項規則 RETRIEVED／VERBATIM（去空白後為子字串）／NONEMPTY（至少 8 字）；任一失敗整份拒答；Ollama＋bge-m3＋qwen3.5:9b | 是應用不是函式庫；不處理 `[n]`；20 題測試集取自語料原文，作者自己也說分數可能偏高 | 0 stars、16 commits、MIT |
| [verbatim-citation-gate](https://github.com/tonydzi/verbatim-citation-gate) | Stage 1 逐字比對（零 token）；Stage 2 由 LLM 判斷支持程度；模型無法解析時 fail-closed | 不處理 `[n]`；單字 quote 目前會判為 found（issue #4） | v0.1.0、4 stars、38 commits、MIT |
| [grounding-verifier](https://github.com/sealmindset/grounding-verifier) | 逐字比對不過就丟棄 → LLM 嚴格 JSON 查核 → 無法解析時升級一次 → fail-closed；`LLMBackend` 是兩個方法的 protocol | 輸入是 `Citation(source_id, quote)` 物件，不是 `[n]` | 0 stars、1 commit、MIT |
| [bearout](https://pypi.org/project/bearout/0.0.3/) | 逐句由注入的 judge 判斷（duck-typed 的 async `chat`）；不支持的句子刪除；judge 出錯一律算不支持 | 依賴 LLM；自報誤刪率 20.2% | 0.0.3、alpha、Apache-2.0 |
| [Vaquill gate](https://www.vaquill.ai/engineering/verify-ai-citations-in-code)（閉源） | 展開 `[a,b]`、`[a-b]`，只刪越界的部分；無法解析的標記不動；只在編輯點清理空白；正規化做 NFKC 並統一引號、破折號、NBSP | 閉源、沒有授權 | 已用於生產環境 |
| [Instructor CitationMixin](https://python.useinstructor.com/concepts/citation/) | quote 有 5 字元以內的誤差時，校正成原文的精確片段 | 不處理 `[n]` | 版本與授權未確認 |

## 四、生成加引用一體的套件

| 專案 | 做什麼 | 與本專案的差異 | 成熟度 |
|---|---|---|---|
| [citeformer](https://pypi.org/project/citeformer/) | 以 grammar 限制解碼，讓越界的 `[n]` 無法被生成；DeBERTa NLI 驗證；確定性的書目渲染；[ADR-013](https://citeformer.readthedocs.io/en/latest/decisions/013-citation-rich-attribution.html) 新增 `cited_text`、`source_span`、`document_title` 欄位，目前只有 Anthropic 會填 | 後端清單沒有 Ollama；沒提重編號；沒有不靠模型的主張檢查 | PyPI 0.3.1（2026-04-27）、6 stars、98 commits、Apache-2.0（[GitHub](https://github.com/random-walks/citeformer)） |
| [rag-citation](https://github.com/rahulanand1103/rag-citation) | 預設不呼叫 LLM：spaCy NER 加 SentenceTransformers 把答案對回來源；Beta 功能會標出 DATE、MONEY、CARDINAL 等不在 context 裡的實體；另有經 LiteLLM 的 LLM 模式 | 範例用英文 spaCy 模型；沒說會解析或重編號 `[n]` | 56 stars、33 commits、MIT |
| [Citekit](https://arxiv.org/pdf/2408.04662) / [CiteLab25](https://github.com/SjJ1017/CiteLab25) | 引用研究用的模組化工具；評估器能解析 `[1, 2]` | 越界標記只計 0 分，不刪除；只支援 OpenAI 舊 API 或 HF 模型 | Citekit 18 stars、MIT（[repo](https://github.com/SjJ1017/Citekit)）；CiteLab25 10 stars、MIT |

## 五、框架與應用內建的做法

| 專案 | 做什麼 | 與本專案的差異 | 成熟度 |
|---|---|---|---|
| [LlamaIndex CitationQueryEngine](https://developers.llamaindex.ai/python/framework-api-reference/query_engine/citation) | 把 node 用 SentenceSplitter 再切（`citation_chunk_size` 512），全域標成 `Source N`；prompt 要求依編號引用 | 不解析、不驗證、不重編號（[workflow 範例](https://developers.llamaindex.ai/python/examples/workflow/citation_query_engine)） | llama-index-core；星數未確認 |
| [Haystack AnswerBuilder](https://github.com/deepset-ai/haystack/blob/main/haystack/components/builders/answer_builder.py) | `reference_pattern` 預設 `None`，也就是不解析；`expand_reference_ranges` 可展開 `[1,2]`、`[3-5]`；明確擋下 `[0]`；越界引用不放進文件清單並記警告 | 越界標記**仍留在答案文字中**；依輸入順序輸出，不重編號；`return_only_referenced_documents` 在原始碼預設 True，但 [deepset 文件](https://docs.cloud.deepset.ai/docs/answerbuilder)寫 False | 26.2k stars、Apache-2.0、v3.4.0（[repo](https://github.com/deepset-ai/haystack)） |
| [deepset ReferencePredictor](https://docs.cloud.deepset.ai/docs/referencepredictor) | 生成後用 cross-encoder 逐句比對來源 | 已淘汰；預設模型只支援英文 | Deprecated |
| [LangChain Citation content block](https://reference.langchain.com/python/langchain-core/messages/content/Citation) | 與供應商無關的資料模型：`url`、`title`、`start_index`／`end_index`（指答案文字中的位置）、`cited_text`、`extras` | 只定義資料結構；舊的 QA citations how-to 已從官方文件移除（[原 URL](https://python.langchain.com/docs/how_to/qa_citations) 302 轉到 v1 總覽） | langchain-core v1；2025-09-03 公告時為 alpha（[blog](https://www.langchain.com/blog/standard-message-content)） |
| [DSPy `experimental.Citations`](https://dspy.ai/current/api/experimental/Citations/) | Citation 型別：`document_index` 加字元 offset；只有 `anthropic/` 模型走原生引用 | 不解析 inline `[n]`；不檢查範圍 | Experimental |
| [Semantic Kernel TextSearchProvider](https://learn.microsoft.com/en-us/semantic-kernel/frameworks/agent/agent-rag) | context prompt 與 `IncludeCitationsPrompt`（引用指示）可分開覆寫 | 不驗證模型產出的引用 | Experimental，僅 C# |
| [txtai RAG `output="reference"`](https://dev.to/neuml/build-rag-pipelines-with-txtai-nd9) | 事後比對答案與 context，回傳最可能的來源 id | 沒有 inline 標記；比對方法未說明 | 12.9k stars、Apache-2.0（[repo](https://github.com/neuml/txtai)） |
| [R2R](https://github.com/SciPhi-AI/R2R) | 7～8 字元的短 ID 標記 `[abc1234]`；串流用 CitationTracker；CitationEvent 同時有 `raw_index` 與顯示用的 `index`（[io.net 文件](https://io.net/docs/reference/rag/retrieval/streaming-retrieval-api)） | 兩者關係、是否丟棄未知 ID，皆未確認 | 8.0k stars、MIT |
| [Kotaemon](https://cinnamon.github.io/kotaemon/reference/indices/qa/citation_qa_inline/) | 解析 `【n】`，並拆開合併寫法 `【1, 2】`；用 START／END phrase 加 `SequenceMatcher` 定位原文（[utils.py](https://github.com/Cinnamon/kotaemon/blob/main/libs/kotaemon/kotaemon/indices/qa/utils.py)） | 不檢查範圍；[issue #541](https://github.com/Cinnamon/kotaemon/issues/541) 回報 Llama3.1-8B on Ollama 引用高亮成功率不到 1/10 | 25.7k stars、Apache-2.0（[repo](https://github.com/Cinnamon/kotaemon)） |
| [MariaDB AI RAG CitationProcessor](https://mariadb.com/docs/tools/mariadb-ai-rag/reference/citations) | 同時回傳 `markdown_content`、去掉所有標記的 `raw_content`，以及 `citation_spans` | 文件沒說無效標記怎麼處置、是否重編號 | 商業產品，授權未確認 |
| [Griptape FootnotePromptResponseRagModule](https://docs.griptape.ai/latest/griptape-framework/engines/rag-engines/) | 自動加註腳；範例中同一來源出現兩次 | 依 chunk 編號而非依來源，是推論 | 未確認 |

其他查過、價值較低的：
- [Dify](https://docs.dify.ai/guides/knowledge-base/retrieval-test-and-citation)：答案下方列出引用段落與匹配度，沒有 inline 標記；152.4k stars（[repo](https://github.com/langgenius/dify)）。
- [Verba](https://weaviate.io/blog/verba-open-source-rag-app)：已淘汰。
- [PraisonAI](https://praison.ai/docs/rag/citations)：未說明怎麼處理無效標記。
- [Tensorlake](https://tensorlake.ai/blog/rag-citations)：頁碼加 bbox 錨點，不驗證回傳的 ID。

## 六、中文生態

| 專案 | 做什麼 | 與本專案的差異 | 成熟度 |
|---|---|---|---|
| [RAGFlow `insert_citations`](https://github.com/infiniflow/ragflow/blob/main/rag/nlp/search.py) | 生成後以相似度插入 `[ID:n]`，詞彙 0.1、向量 0.9；門檻從 0.63 起每輪 ×0.8，降到 0.3 為止；斷句含全形 `；。？！`；保留 code fence；短於 5 字的片段跳過 | 需要嵌入模型；每句最多 4 個引用，但是從無序集合中取，結果不確定；不重編號 | 88.7k stars、Apache-2.0、v0.26.4（[repo](https://github.com/infiniflow/ragflow)） |
| [RAGFlow `citation.go`](https://github.com/infiniflow/ragflow/blob/main/internal/service/citation.go) | 修復 `【ID: 12】`、`(ID: 12)`、`ref12`、`(**ID: 12**)` 等壞格式；抽取時依首見順序並做 `[0, max)` 範圍檢查；串流尾端暫存 | 只過濾抽出的清單，文字中的越界標記不刪 | 同上 |
| [RAGFlow citation_prompt.md](https://github.com/infiniflow/ragflow/blob/main/rag/prompts/citation_prompt.md) | 要求逐一寫 `[ID:i]`，禁止合併與範圍寫法；引用放在句末標點前；每句最多 4 個；列出必須引用與不必引用的句型 | 只是 prompt | 同上 |
| [FastGPT](https://github.com/labring/FastGPT/blob/main/packages/global/core/ai/prompt/AIChat.ts) | `[id](CITE)` 這種 Markdown 連結式標記；prompt 寫「不要伪造 id」；模板依版本號管理 | 程式碼中沒有驗證 | 29.6k stars、FastGPT 自訂授權，禁 SaaS（[repo](https://github.com/labring/FastGPT)） |
| [Tencent WeKnora](https://github.com/Tencent/WeKnora/blob/main/frontend/src/utils/citationMarkdown.ts) | `<kb doc chunk_id/>` 標籤；容錯解析，依序嘗試 position、chunk_index、標題、DOC-n；以 placeholder 保護標籤不被 Markdown 改寫；依首次出現建立來源清單 | 解析不到的 ID 原樣保留；不重編號 | 26.8k stars、MIT、v0.8.0（[repo](https://github.com/Tencent/WeKnora)） |
| [MindSearch](https://github.com/InternLM/MindSearch/blob/main/mindsearch/agent/mindsearch_agent.py) | 跨子問題把 `[[n]]` 加 offset 重編號 | 依 set 迭代順序而非首次出現；節點之間的編號有缺口；無效 ID 仍留在文字中 | 6.9k stars、Apache-2.0（[repo](https://github.com/InternLM/MindSearch)） |
| [LightRAG](https://github.com/HKUDS/LightRAG) | 回傳結構化的 `references` 欄位；用 user_prompt 要求模型寫 `[^n]` 註腳（[v1.4.9](https://newreleases.io/project/github/HKUDS/LightRAG/release/v1.4.9)） | 不驗證、不重編號 | 39.3k stars、MIT |
| [Langchain-Chatchat](https://github.com/chatchat-space/Langchain-Chatchat/blob/master/libs/chatchat-server/chatchat/server/chat/kb_chat.py) | 由程式組出「出处 [n]」；檢索不到時改用 empty prompt，並附「該回答為大模型自身能力解答」的提示 | context 不帶編號，模型無法輸出對應的 `[n]` | 38.5k stars、Apache-2.0（[repo](https://github.com/chatchat-space/Langchain-Chatchat)） |
| [QAnything](https://github.com/netease-youdao/QAnything) | 「溯源」功能只是來源清單加預覽 | prompt 沒要求 inline 標記 | 14.2k stars、**AGPL-3.0** |
| [MaxKB](https://github.com/1Panel-dev/MaxKB) | 顯示知識來源段落；有 `no_references_setting`（[DeepWiki](https://deepwiki.com/1Panel-dev/MaxKB/5.4-chat-pipeline-system)） | 沒有 inline 標記；選項未確認 | 22.9k stars、**GPL-3.0** |
| [openJiuwen DeepSearch SourceTracer](https://gitcode.com/LiNianFang/deepsearch/blob/dev/openjiuwen_deepsearch/algorithm/source_trace/source_tracer.py) | 先切掉模型自己寫的參考段落，用 LLM 對回來源，最後重接標準參考段 | 不檢查範圍；分批時索引沒加 offset 就合併，會指錯段落 | README 寫 Apache 2.0；星數未確認 |
| [Jimmy Song RAG 手冊](https://jimmysong.io/zh/book/rag-handbook/quality/answer-quality-optimization/) | `validateAnswer` 檢查 `1 ≤ n ≤ blockCount`；提出 `citation_count`、`citation_match_rate` 兩個指標 | 只是範例程式；不刪除、不重編號 | 線上手冊 |
| [串流引用對齊文章（CSDN）](https://gitcode.csdn.net/69e394280a2f6a37c5a0c41b.html) | 文字與引用 metadata 分成兩個 SSE 事件；串流結束時整段重新解析 | 對不到的標記顯示 `[?]` 或保留原樣 | 部落格，頁面註明部分內容為 AI 生成 |

## 七、模型與雲端 API 的原生引用及接地檢查

| 專案 | 做什麼 | 與本專案的差異 | 成熟度 |
|---|---|---|---|
| [Anthropic search_result blocks](https://platform.claude.com/docs/en/build-with-claude/search-results) | 直接送入已檢索的分段；回傳 `search_result_index`（0-based）與 `cited_text`；不需 beta header；除 Claude Haiku 3 外所有現役模型都支援 | 綁定供應商；可當成一種 Generator adapter（另見 [Citations API](https://claude.com/resources/articles/introducing-citations-api)） | 正式 API |
| [Cohere RAG citations](https://docs.cohere.com/docs/rag-citations) | 回傳 start／end 區間；accurate 與 fast 兩種模式 | 不插入標記，也沒有驗證 | 商業 API |
| [OpenAI citation formatting guide](https://developers.openai.com/api/docs/guides/citation-formatting.md) | 用特殊分隔符包住 `cite`、source_id、`L8-L13`；`strip_citations` 從字串尾端往前刪 | 只檢查格式，不拒絕未知 ID；不重編號 | 官方文件 |
| [OpenAI file_search annotations](https://developers.openai.com/api/docs/guides/tools-file-search) | `file_citation` 只標到檔案層級 | 無法對到 chunk | Responses API |
| [OpenAI Assistants annotations](https://developers.openai.com/api/docs/assistants/deep-dive.md) | 官方範例依 annotation 順序編號，從 0 起算 `[0]`，重複引用也給新號 | 反例 | 已於 2026-08-26 關閉 |
| [xAI citations](https://docs.x.ai/developers/tools/citations) | 由 1 起依首次出現編號，重複引用沿用原號；`response.citations` 與實際引用分開 | 由供應商端完成 | 商業 API |
| [Gemini grounding](https://ai.google.dev/gemini-api/docs/generate-content/google-search) | `groundingSupports` 的區間對應到 chunk 索引；官方範例由尾端往前插入 | 編號跟著 chunk 順序走，所以 `[4]` 可能出現在 `[1]` 之前 | GA 狀態未確認 |
| [Vertex AI Check Grounding](https://docs.cloud.google.com/generative-ai-app-builder/docs/check-grounding?authuser=0) | 一句視為一個主張；位置以 UTF-8 **byte** 表示；有 `groundingCheckRequired`；`citationThreshold` 預設 0.6；只部分被蘊涵就判為未接地 | 雲端服務；語言支援未說明 | Google Cloud |
| [Vertex AI Search 摘要引用](https://oneuptime.com/blog/post/2026-02-17-how-to-implement-answer-generation-with-citations-in-vertex-ai-search/markdown) | `references` 與 `citations` 兩個清單分開 | 只有第三方部落格來源 | 未確認 |
| [Bedrock KB RetrieveAndGenerate](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-retrieve-generate.html) | 引用格式指示放在獨立的 `$output_format_instructions$` 插槽 | 沒有文件化 inline 格式或驗證 | AWS |
| [Bedrock Converse citations](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_CitationsContentBlock.html) | `CitationsConfig.enabled` | 支援哪些模型未確認 | AWS |
| [Bedrock Guardrails contextual grounding](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-contextual-grounding-check.html) | grounding 與 relevance 兩個門檻；`ApplyGuardrail` 不呼叫模型，任何模型的輸出都能送檢 | 只到答案層級；不支援對話式 QA | AWS |
| [Azure AI Search answer synthesis](https://learn.microsoft.com/en-my/Azure/search/agentic-retrieval-how-to-answer-synthesis) | `[ref_id:N]` 標記 | 未說明驗證方式 | Preview |
| [Azure Foundry Agents AI Search](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/ai-search) | `[message_idx:search_idx†source]`；C# 範例用全形 `【…】` | 只有人工檢查清單 | GA 未確認 |
| [Azure On Your Data](https://learn.microsoft.com/en-us/azure/foundry-classic/openai/references/on-your-data) | `[docN]` 依位置對應；有 `filter_reason` | 不驗證 | **2026-10-14 已退役** |
| [Azure groundedness detection](https://learn.microsoft.com/en-gb/azure/ai-services/content-safety/concepts/groundedness) | 可修正數字與日期 | 只支援英文 | 特定區域 |
| [Perplexity streaming cookbook](https://docs.perplexity.ai/docs/cookbook/articles/streaming-citations/README.md) | 每個 delta 都重掃累積的全文 | 對不到的標記保留純文字 | 廠商文件 |

## 八、評估框架與小型檢查模型

| 專案 | 做什麼 | 與本專案的差異 | 成熟度 |
|---|---|---|---|
| [RAGAS Faithfulness](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/faithfulness/) | 主張 → 逐一驗證 → 計算比例；FaithfulnesswithHHEM 只把驗證那一步換成小模型 | 抽主張要靠 LLM；只到答案層級 | 0.4.3、Apache-2.0（[PyPI](https://pypi.org/project/ragas/)） |
| [RAGAS traditional metrics](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/traditional/) | chrF（字元 n-gram F 分數）、ROUGE、BLEU 等 | 都是和 reference 比，不是和 context 比 | 同上 |
| [RAGAS Context Utilization](https://docs.ragas.io/en/v0.1.21/concepts/metrics/context_utilization.html) | 依排名加權，算檢索段落被用到的比例 | 要 LLM 判斷 | 同上 |
| [DeepEval Citation Faithfulness](https://deepeval.com/docs/metrics-citation-faithfulness) | 判斷 `[N]` 是否指向真正支持該主張的段落；把「指錯段落」獨立成一種錯誤 | 靠 LLM 或遠端的 Jev 模型 | community metric；DeepEval 18,938 stars、Apache-2.0（[OSSInsight](https://ossinsight.io/analyze/confident-ai/deepeval)） |
| [DeepEval Faithfulness](https://www.deepeval.com/docs/metrics-faithfulness) | 定義是「與事實不矛盾」；有 `penalize_ambiguous_claims` 選項 | 只到答案層級 | docs v4.3.1 |
| [TruLens groundedness](https://trulens.org/trulens/evaluation/feedback_implementations/stock) | 逐句評分，先剔除瑣碎句；拒答預設視為已接地 | 靠 LLM 或 NLI；中文未確認 | 3.5k stars、MIT（[repo](https://github.com/truera/trulens)） |
| [Arize Phoenix](https://arize.com/docs/phoenix/evaluation/pre-built-metrics/faithfulness) | 用 LLM 分類 faithful／unfaithful；`@create_evaluator(kind='code')` 可掛自訂程式 | 只到答案層級 | 約 11k stars、**ELv2**（[repo](https://github.com/Arize-ai/phoenix)） |
| [Haystack FaithfulnessEvaluator](https://docs.haystack.deepset.ai/docs/model-based-evaluation) | 逐條 statement 評分；`chat_generator` 可接本地模型 | 靠 LLM | Haystack 3.4 |
| [RAGChecker](https://github.com/amazon-science/RAGChecker) | 主張層級的 noise sensitivity、hallucination、self-knowledge | 需要 `gt_answer`，只能離線用 | 1.1k stars、Apache-2.0 |
| [RefChecker](https://github.com/amazon-science/RefChecker) | 三元組三分類：entailment／contradiction／neutral | 英文 | 434 stars、Apache-2.0、2026-04-08 封存 |
| [Vectara HHEM-2.1-Open](https://huggingface.co/vectara/hallucination%5Fevaluation%5Fmodel) | 輸入 (premise, hypothesis)，輸出 0～1 | 開源版只支援英文；商用 HHEM-2.3 列有簡體中文（[docs](https://docs.vectara.com/docs/learn/hallucination-evaluation)） | Apache-2.0 |
| [MiniCheck](https://github.com/Liyan06/MiniCheck) | 逐句檢查主張 vs 文件；Bespoke-MiniCheck-7B 可在 [Ollama](https://registry.ollama.ai/blog/reduce-hallucinations-with-bespoke-minicheck) 上執行 | 7B 版標英文，授權 **CC BY-NC 4.0** | 219 stars、Apache-2.0 |
| [AlignScore](https://github.com/yuh-zha/AlignScore) | 每句取各段落的最大值，再對各句取平均 | 只支援英文 | 168 stars、MIT |
| [LettuceDetect](https://cdn.jsdelivr.net/gh/KRLabsOrg/LettuceDetect@main/README.md) | 輸出不被支持的字元區間；EuroBERT 版支援 7 語，含中文 | 靠模型；沒有中文的評測數字 | 0.2.2、MIT（[PyPI](https://pypi.org/project/lettucedetect)） |
| [mDeBERTa-v3-xnli-multilingual](https://huggingface.co/MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7) | 多語 NLI；XNLI zh 準確率 0.803 | 繁體表現未確認 | MIT、0.3B |
| [Patronus Lynx](https://patronus.ai/blog/lynx-state-of-the-art-open-source-hallucination-detection-model) | 8B／70B 的忠實度評審模型 | 答案層級、英文 | 授權未確認 |
| [Guardrails provenance_embeddings](https://guardrailsai.com/hub/validator/guardrails/provenance_embeddings) | 逐句 embedding 距離；可注入 `embed_function`；`on_fail` 有多種策略 | 只標英文 | MIT |
| [NeMo Guardrails fact-checking](https://docs.nvidia.com/nemo/guardrails/latest/configure-guardrails/guardrail-catalog/fact-checking) | 沒有判定結果時給 0.0，預設擋下（fail-closed） | 只能在 LLMRails 內使用 | 版本未確認 |
| [open-rag-eval](https://github.com/vectara/open-rag-eval) | 用 UMBRELA、AutoNuggetizer、HHEM 評估 | 沒有引用專屬指標 | 411 stars、Apache-2.0 |
| [ContextCite](https://github.com/MadryLab/context-cite) | 對 context 做消融，再以 LASSO 代理模型歸因 | 需要模型 logits，字串介面的 callable 給不出來 | 340 stars、MIT |
| [LettucePrevent](https://github.com/lebe1/LettucePrevent) | 解碼時以數字 regex 壓低 logits | 要掌控解碼，Ollama 的 OpenAI 相容介面做不到 | 0 stars、MIT |
| [SemanticCite](https://github.com/sebhaan/semanticcite) | 四級標籤：Supported／Partially／Unsupported／Uncertain | 靠 LLM | 25 stars、MIT |

## 九、研究與基準

| 專案 | 做什麼 | 與本專案的差異 | 成熟度 |
|---|---|---|---|
| [ALCE](https://github.com/princeton-nlp/ALCE) | citation recall／precision 的標準定義；[eval.py](https://raw.githubusercontent.com/princeton-nlp/ALCE/main/eval.py) 用 `r"\[\d+"`，含越界標記的句子 recall 記 0，每句最多看 3 個引用 | 只計分不刪除；`[1, 2]` 只會被讀成 1 | 526 stars、MIT、EMNLP 2023 |
| [On the Capacity of Citation Generation](https://arxiv.org/html/2410.11217v1) | 沒有任何段落支持的未引用句，不計入 recall 分母；接受多段聯合支持 | NLI | arXiv |
| [LongCite / LongBench-Cite](https://github.com/THUDM/LongCite) | 功能句（開場、轉折、總結）免引用；有中文子集 MultiFieldQA-zh、DuReader；斷句用 Punkt 加 `[。；！？]` | 以 GPT-4o 評審 | 522 stars、Apache-2.0（[論文](https://arxiv.org/pdf/2409.02897v3)） |
| [WebCiteS](https://github.com/HarlynDN/WebCiteS) | 約 7k 筆中文附引用摘要；mT5-XNLI 檢查器準確率 82.3%；把句子拆成子主張 | 繁體或簡體未確認 | 14 stars、Apache-2.0、ACL 2024 |
| [CitaLaw](https://arxiv.org/abs/2412.14556) | 中文法律引用，以三段論評估 | 程式碼與資料是否釋出未確認 | arXiv |
| [VeriCite](https://arxiv.org/html/2510.11394v1) | Table 3（ASQA、Llama3-8B）：拿掉 NLI 驗證後 citation F1 由 77.73 降到 68.91，EM 41.63 對 41.59；Table 4：改用生成模型自己驗證，F1 由 80.05 降到 73.01 | [程式碼](https://github.com/QianHaosheng/VeriCite)會把引用越界或沒有引用的整句丟掉 | SIGIR-AP 2025、3 stars、無授權 |
| [CiteFix](https://arxiv.org/html/2504.15629v2) | 事後修正引用；某模型無法驗證的論點中，80.6% 是引錯段落，19.4% 才是純粹幻覺 | 程式碼未確認 | arXiv |
| [CiteEval](https://github.com/amazon-science/CiteEval) | 分成 Cited 與 Full 兩種視角；非可引用句記為 N/A；以「刪除 [k]／新增 [j]」的編輯動作描述問題（[論文](https://arxiv.org/html/2506.01829v1)） | GPT-4o | 9 stars、**CC-BY-NC-4.0** |
| [TRUE](https://arxiv.org/abs/2204.04991) | token-level F1 的 ROC AUC 只有 63.8，ANLI T5-11B 是 81.5 | 只測英文 | NAACL 2022 |
| [Correctness is not Faithfulness](https://arxiv.org/abs/2412.18004) | 最多 57% 的引用是事後找理由補上的 | — | arXiv |
| [AttributionBench](https://github.com/OSU-NLP-Group/AttributionBench) | 超過 66% 的錯誤來自對細節不敏感 | — | 10 stars、ACL 2024 Findings |
| [Liu et al. 可驗證性稽核](https://arxiv.org/abs/2304.09848) | 生成式搜尋引擎平均只有 51.5% 的句子被引用完整支持 | — | Findings EMNLP 2023 |
| [WebGLM](https://arxiv.org/pdf/2306.07906) | 用 Rouge-1 重新連結答案片段與參考，最佳門檻 0.57 | 只用在訓練資料，不是推論時 | KDD'23 |
| [AGRaME / PROPCITE](https://arxiv.org/pdf/2405.15028) | 事後補引用，加 margin 門檻 1.0 | 靠多向量模型 | arXiv |
| [Trust-Align / trust_eval](https://github.com/declare-lab/trust-align) | 把有依據的拒答當成正式結果 | trust_eval 為 **CC BY-NC 4.0** | 76 stars、ICLR 2025 |
| [SelfCite](https://github.com/facebookresearch/SelfCite) | 以必要性與充分性的消融結果當獎勵 | 非商用授權、已封存 | 30 stars、ICML 2025 |
| [ALiiCE](https://arxiv.org/abs/2406.13375) | 評估句中任意位置的引用 | 程式碼未確認 | arXiv |
| [L-CiteEval](https://github.com/LCM-Lab/L-CITEEVAL) | 照搬 ALCE 的解析慣例；NLI 用 DeBERTa-base | 英文 | 30 stars |
| [CRUD-RAG](https://github.com/IAAR-Shanghai/CRUD_RAG) / [UHGEval](https://iaar-shanghai.github.io/UHGEval/) / [Bi'an](https://arxiv.org/html/2502.19209v1) | 中文 RAG 與幻覺的基準 | 沒有引用；Bi'an 的資料尚未釋出 | 414 stars、Apache-2.0；ACL 2024；arXiv |

只有訓練或模型內部方法、無法透過注入 callable 套用的，列出供參考：[Self-RAG](https://github.com/AkariAsai/self-rag)、[FRONT](https://github.com/LuckyyySTA/Fine-grained-Attribution)、[APO](https://github.com/HITsz-TMG/ATG-PO)、[AGREE](https://arxiv.org/abs/2311.09533)、[MIRAGE](https://arxiv.org/abs/2406.13663)、[AttrScore](https://github.com/OSU-NLP-Group/AttrScore)、[Attribute First](https://github.com/lovodkin93/attribute-first-then-generate)、[RARR](https://github.com/anthonywchen/RARR)、[CEG](https://arxiv.org/abs/2402.16063)。

## 十、中文文字處理基礎工具（補查）

前面各類調查都沒涵蓋這一塊，但它是數字、日期檢查與 3-gram 正規化的前置步驟：

| 專案 | 做什麼 | 與本專案的差異 | 成熟度 |
|---|---|---|---|
| [OpenCC](https://github.com/BYVoid/OpenCC) | 以字典做確定性的繁簡轉換，可離線執行；有台灣標準設定 `s2tw`、`tw2s`、`s2twp`、`t2tw` | 可在 3-gram 比對前統一繁簡寫法 | 9.9k stars、Apache-2.0、`pip install opencc` |
| [cn2an](https://github.com/Ailln/cn2an) | 中文數字與阿拉伯數字互轉，有 strict／normal／smart 模式；可處理日期、百分比；`transform` 是實驗性功能 | README 沒提繁體的「萬」「億」，要自己測 | 766 stars、MIT、v0.5.24 |
| [JioNLP](https://github.com/dongrixinyu/JioNLP) | 有 `extract_money`、`extract_time`、`parse_time`，以及 `tra2sim`／`sim2tra`（[README](https://raw.githubusercontent.com/dongrixinyu/JioNLP/master/README.md)） | 以簡中為主；沒提民國年 | 3.9k stars、Apache-2.0 |

## 可借鏡的做法

### A. 解析與清理標記（`src/citation.py`、`src/utils.py`）

1. **先正規化、再解析**
   - 展開 `[1, 2]` 與 `[1-3]`，參考 [Haystack EXPANDED_REFERENCE_PATTERN](https://github.com/deepset-ai/haystack/blob/main/haystack/components/builders/answer_builder.py) 與 [groundcite NUMERIC](https://github.com/JafarBanar/groundcite)。
   - 只刪越界的部分，例如 `[2,7]` 變成 `[2]`；無法解析的標記不動（[Vaquill](https://www.vaquill.ai/engineering/verify-ai-citations-in-code)）。
   - 一併接受 `【n】`、`［n］`、`[[n]]`（[Onyx](https://github.com/onyx-dot-app/onyx/blob/main/backend/onyx/chat/citation_processor.py)、[Kotaemon](https://cinnamon.github.io/kotaemon/reference/indices/qa/citation_qa_inline/)）。
   - 目前 `CITE_RE = r"\[(\d+)\]"` 不認這些寫法。不要照抄 ALCE 的 `r"\[\d+"`，它會把 `[1, 2]` 讀成 1（[eval.py](https://raw.githubusercontent.com/princeton-nlp/ALCE/main/eval.py)）。
2. **邊界案例寫成回歸測試**
   - `[0]` 不能當成 -1 處理（Haystack 有明確的範圍判斷）。
   - `n == len(passages)` 必須保留（STORM 的 [off-by-one](https://raw.githubusercontent.com/stanford-oval/storm/HEAD/knowledge_storm/utils.py)）。
   - 現在 `renumber_and_filter` 用一次 `re.sub` 加 callback 替換，本來就不會發生 STORM 擔心的連鎖替換。之後若改成逐一 `str.replace`，就要改用 placeholder 兩段式。
3. **只在編輯點清理空白**（Vaquill），並略過 code fence 內的標記（[Onyx CodeFenceTracker](https://github.com/onyx-dot-app/onyx/blob/main/backend/onyx/chat/citation_processor.py)；[RAGFlow 也保留 code fence](https://github.com/infiniflow/ragflow/blob/main/rag/nlp/search.py)）。目前 `_MULTI_SPACE_RE` 會對全文壓縮連續空白，可能破壞 Markdown 縮排。若要從字串中刪多處，應由尾端往前刪（[OpenAI strip_citations](https://developers.openai.com/api/docs/guides/citation-formatting.md)、[Gemini 範例](https://ai.google.dev/gemini-api/docs/generate-content/google-search)）。
4. **解析前先剝掉 `<think>`**（[ragcite `strip_reasoning`](https://github.com/pcbeingused333/ragcite)），否則 qwen3 系列思考區塊裡的 `[n]` 也會被算進去。
5. **先記錄、再刪除**
   - 輸出 fabricated 清單與比例（[acclaim hallucination_rate](https://github.com/jwallat/acclaim)、[citesure dropped_markers](https://pypi.org/project/citesure/)）。
   - 在清理前另算一次 ALCE 式 recall（含越界標記的句子記 0），以便和文獻比較。
6. **內部用穩定 ID，輸出才換成顯示編號**。這和目前 chunk_id 加重編號的設計一致，也有 [Agentset](https://docs.agentset.ai/search-and-retrieval/citations.md)、[R2R](https://io.net/docs/reference/rag/retrieval/streaming-retrieval-api)、[xAI](https://docs.x.ai/developers/tools/citations) 的前例。另可提供「同一文件合併成一個編號」的選項（[langchain-references](https://www.github.com/pprados/langchain-references)；[Autosearch](https://openskillindex.com/skills/0xmariowu-autosearch-autosearch-citation-index) 會先把 key 正規化）。

### B. 品質報告（`src/eval/`）

7. **中文斷句**：加上 `；` 與換行；code fence 整塊保留；短於 5 字的片段跳過（[RAGFlow](https://github.com/infiniflow/ragflow/blob/main/rag/nlp/search.py)、[LongCite](https://raw.githubusercontent.com/THUDM/LongCite/HEAD/vllm_inference.py)）。目前 `_CN_TERMINATORS = "。！？"`，沒有 `；`。
8. **比對前先正規化**：NFKC 加引號、破折號、NBSP 統一（Vaquill）；必要時用 [OpenCC](https://github.com/BYVoid/OpenCC) 統一繁簡寫法。RAGFlow 在查詢端也做全半形與繁簡轉換（[query.py](https://github.com/infiniflow/ragflow/blob/main/rag/nlp/query.py)）。
9. **數字依值比較，不用子字串**
   - 子字串比對會讓 `5` 命中 `56`（[sourced-evidence](https://pypi.org/project/sourced-evidence/0.4.0/)）；標點要當成 token 邊界（[axiom](https://github.com/FurkhanShaikh/axiom-rag-engine)）。
   - 正規化萬／億（[ClaimCheck](https://huggingface.co/NagaYu/claimcheck-rules) 處理千／万／億／兆），中文數字可評估用 [cn2an](https://github.com/Ailln/cn2an)。
   - 加上民國年，類比 ClaimCheck 處理日本年號的方式。目前 `\d{4}\s*年` 抓不到「113年」，`find_unsupported_entities` 也是子字串比對。
   - 從引用數字算出來的值，例如百分比變化，標成 `derived`，不要直接判錯（ClaimCheck；[LettucePrevent](https://github.com/lebe1/LettucePrevent) 指出這類誤判）。
10. **三態判定加上 N/A**
    - grounded／contradicted／unverified（sourced-evidence）。
    - 功能句、非可引用句記為 N/A，不算 unsupported（[LongCite](https://github.com/THUDM/LongCite)、[Vertex groundingCheckRequired](https://docs.cloud.google.com/generative-ai-app-builder/docs/check-grounding?authuser=0)、[CiteEval](https://github.com/amazon-science/CiteEval)、[TruLens](https://trulens.org/trulens/evaluation/feedback_implementations/stock)）。
    - 算不出的指標標成 skipped 並附原因（[ragproof](https://pypi.org/project/ragproof/)）。
11. **「被引段落」與「最佳段落」各算一次**：取被引段落的最大值，再取全部段落的最大值（[AlignScore](https://github.com/yuh-zha/AlignScore) 的聚合方式）。兩者落差大，代表引錯段落（[DeepEval](https://deepeval.com/docs/metrics-citation-faithfulness)、[RAGChecker](https://github.com/amazon-science/RAGChecker)），可在報告中給出建議改指，但不自動改寫（[CiteFix](https://arxiv.org/html/2504.15629v2)、[citation-guard](https://github.com/sibalabs/citation-guard)）。
12. **否定詞與限定詞**：「不、未、非、無、僅、不得、應、得、須」這類詞在句子與段落間不一致時另外標記。n-gram 重疊抓不到這種錯（[ClaimCheck 的警告](https://huggingface.co/NagaYu/claimcheck-rules)、[legal-rag-verifier 只抓到 6/18](https://pypi.org/project/legal-rag-verifier/0.1.0/)、[anchor](https://github.com/hnvivek/anchor)）。
13. **罕見 n-gram 加權**，避免常見片語灌高重疊分數（[ancora IDF](https://pypi.org/project/ancora-rag/0.1.1/)）。
14. **輸出格式**
    - 位置用字元 offset，不用 byte（Vertex 用 byte；一個繁中字是 3 byte）。
    - 附上在段落中的支持區間（[citeglow](https://pypi.org/project/citeglow/)）。
    - 規則代碼（[onus](https://pypi.org/project/onus)）與 `schema_version`（[citefact](https://pypi.org/project/citefact/)）。
    - 同時提供 `raw_content`、渲染版與 spans 三種視圖（[MariaDB](https://mariadb.com/docs/tools/mariadb-ai-rag/reference/citations)）。
    - 欄位命名對齊 [LangChain Citation](https://reference.langchain.com/python/langchain-core/messages/content/Citation)。
15. **誠實命名**：分數叫「lexical support（heuristic）」，不要叫 faithfulness（[TRUE](https://arxiv.org/abs/2204.04991)、[Correctness≠Faithfulness](https://arxiv.org/abs/2412.18004)）。門檻要能調整並經過校正（[ragground tune_thresholds](https://pypi.org/project/ragground/)），可參考 [WebGLM 的 Rouge-1 0.57](https://arxiv.org/pdf/2306.07906)，中文資料可用 [WebCiteS](https://github.com/HarlynDN/WebCiteS)、[LongBench-Cite](https://github.com/THUDM/LongCite)。

### C. 介面與政策

16. **Generator 用 `(system, user) -> str`**，與 [verbatim-citation-gate](https://github.com/tonydzi/verbatim-citation-gate) 的介面相同。模型輸出無法解析時，一律當成「不支持」（[bearout](https://pypi.org/project/bearout/0.0.3/)、[grounding-verifier](https://github.com/sealmindset/grounding-verifier)）。
17. **可替換的 SupportScorer 接縫**：預設用字元 3-gram，選配 NLI 模型（[RAGAS FaithfulnesswithHHEM](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/faithfulness/) 的做法）。候選有 [mDeBERTa-XNLI](https://huggingface.co/MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7)、[LettuceDetect EuroBERT](https://cdn.jsdelivr.net/gh/KRLabsOrg/LettuceDetect@main/README.md)。若用 LLM 驗證，要警告不可與生成模型相同（[VeriCite Table 4](https://arxiv.org/html/2510.11394v1)、[ragcite](https://github.com/pcbeingused333/ragcite)）。
18. **失敗處置的政策詞彙**：用 `on_fail` 列舉值（[Guardrails](https://guardrailsai.com/hub/validator/guardrails/provenance_embeddings)），提供分階段 preset（ClaimCheck），預設 fail-closed（[NeMo](https://docs.nvidia.com/nemo/guardrails/latest/configure-guardrails/guardrail-catalog/fact-checking)）。
19. **Prompt**
    - 引用放在句末標點前；每句最多 4 個；禁止合併與範圍寫法（[RAGFlow citation_prompt](https://github.com/infiniflow/ragflow/blob/main/rag/prompts/citation_prompt.md)）。
    - 「如何引用」的指示做成獨立插槽，方便換成繁中說明（[Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-retrieve-generate.html)、[Semantic Kernel](https://learn.microsoft.com/en-us/semantic-kernel/frameworks/agent/agent-rag)）。
20. **有依據的拒答是正式結果**：沒有標記也合法，不算「未引用」（[Trust-Align](https://github.com/declare-lab/trust-align)）。檢索為空時，報告最上層要有一個狀態欄位標示（[Langchain-Chatchat](https://github.com/chatchat-space/Langchain-Chatchat/blob/master/libs/chatchat-server/chatchat/server/chat/kb_chat.py)）。

### 前例中的教訓與風險

- **事後插入引用 vs. prompt 標記**
  - 事後插入（[RAGFlow](https://github.com/infiniflow/ragflow/blob/main/rag/nlp/search.py)、[PROPCITE](https://arxiv.org/pdf/2405.15028)、[txtai](https://dev.to/neuml/build-rag-pipelines-with-txtai-nd9)）不依賴模型遵守格式，但通常需要嵌入模型，RAGFlow 還有「從無序集合取前 4 個」的不確定性。
  - Prompt 標記成本低，但小模型容易引錯；CiteFix 統計 80.6% 是引錯段落，而不是憑空編造。
  - 建議：以 prompt 標記為主，再用確定性的「建議改指」補強；答案完全沒有標記時，才考慮事後歸因當備援。
- **逐字 quote 模式不一定適合本地小模型**：[Kotaemon #541](https://github.com/Cinnamon/kotaemon/issues/541) 回報 8B 本地模型成功率不到 1/10。[rag-citation-gate](https://github.com/yschang1688/rag-citation-gate) 的滿分只建立在 20 題、取自語料原文的測試集上。
- **純詞彙比對的上限低**：citesure 不用 NLI 時一致率只有 38%，低於全判不支持的 59.3%；TRUE 的 token F1 ROC AUC 只有 63.8。數字、日期、否定詞檢查是必要的補強。
- **需要 logits 或掌控解碼的方法無法套用**，因為我們用的是字串介面：ContextCite、MIRAGE、LettucePrevent、citeformer 的 grammar 限制。
- **授權地雷**（銀行產品不宜採用其程式碼）：
  - 非商用：CiteEval、trust_eval、SelfCite、Bespoke-MiniCheck-7B
  - AGPL：legal-rag-verifier、QAnything
  - GPL：MaxKB
  - ELv2：Phoenix
- **來源原文本身可能含 `[1]`**，例如法規或報告的註腳。模型照抄原文時會被誤當成引用而刪掉，[OpenAI 指南](https://developers.openai.com/api/docs/guides/citation-formatting.md)正是為此改用不會與正文衝突的分隔符。

## 對設計的新問題

1. 合併與範圍標記展開後，輸出要寫成 `[1][2]` 還是保留 `[1, 2]`？部分有效的 `[2,7]` 要截成 `[2]` 嗎？
2. 除了 `[n]`，要接受並正規化哪些寫法：`【n】`、`［n］`、`[[n]]`、`[^n]`、`[ID:n]`、`[ref_id:n]`？無法解析的寫法要保留、刪除，還是只列在報告裡？
3. 一句話唯一的標記是編造的：保留成未引用句（現行做法）、整句刪除（VeriCite）、還是整份拒答（rag-citation-gate）？要不要做成 `on_fail` 政策？
4. 「建議改指」只放在報告裡，還是在唯一明確時自動改寫，像 citation-guard 那樣？自動改寫要怎麼留下稽核紀錄？
5. 指標要在清理前算、清理後算，還是兩者都給？`hallucination_rate` 的分母用標記數還是句數？
6. 顯示編號要以 chunk 為單位，還是同一文件合併成一號？arrkb 的 reranked 結果可能有多個 chunk 來自同一份文件。
7. 不呼叫模型的前提下，怎麼判定功能句或非可引用句？靠長度、有沒有數字、轉折詞表，還是由 prompt 要求模型標記？
8. 3-gram 比對前要做哪些正規化：NFKC、全半形、繁簡統一（OpenCC）、標點去除？要把「臺／台」視為同一字嗎？
9. 數字檢查的範圍：萬／億、中文數字（要不要依賴 cn2an）、民國年、百分比與「成」、區間？「矛盾」需要對齊同一個欄位，「缺席」不需要，這兩者用規則做得到可靠區分嗎？
10. 否定詞與限定詞表要放進預設檢查，還是先做成 observe-only，避免誤報？
11. 現行門檻 `SUPPORT_OVERLAP_THRESHOLD = 0.15` 用什麼資料校正？WebCiteS（繁簡未確認）、LongBench-Cite zh，還是需要自建一套繁中標註集？
12. 輸出 schema：答案中的 offset 是重編號後的字元位置嗎？要不要附上段落內的支持區間？欄位名要不要對齊 LangChain 或 DSPy 的 Citation？
13. `<think>` 的剝除放在 Generator adapter，還是核心模組？
14. 答案完全沒有標記、但內容有事實時，要不要做事後歸因？還是只回報 uncited，並辨識有依據的拒答？
15. Tier 3 串流：現在的 API 是否要預留暫存不完整標記的介面（Onyx、langchain-references、RAGFlow Go、WeKnora 的做法）？
16. 選配的模型檢查層（mDeBERTa-XNLI、LettuceDetect、經 Ollama 的 Bespoke-MiniCheck）算不算這次範圍？若要做，是走同一個 SupportScorer 接縫，還是另開一個 Verifier 介面？
