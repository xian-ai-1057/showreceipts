# 引用層做成框架無關的模組，檢索與模型都由外部注入

專案原本是「本地 Chroma + Ollama + LangChain」的完整 RAG demo，但實際要服務的是 Taishin production RAG（arrkb）以及其他未定的 RAG 框架。因此把「檢索之後」的那一段（組 context、呼叫模型、解析與重編 `[n]`、品質檢查）抽成獨立模組：輸入是 Passage 清單，模型以使用者注入的 Generator 呼叫，模組本身不 import Chroma、Streamlit 或 LangChain。各框架的差異只放在 Adapter（先做 arrkb 與 LangChain）；本地檢索、loaders、對話歷史與 Streamlit 降為 Demo Host。模組先以 repo 內子套件存在，用 import 規則隔離，demo 被認可後再抽成獨立套件。

## Considered Options

- **繼續做完整本地 RAG（Tier 3）**：與「接任何框架」的目標衝突，檢索層會跟 production 重複。
- **沿用 LangChain 當抽象層**：其他框架（LlamaIndex、Haystack、自研 arrkb）就得多帶一個重依賴，且 LangChain 介面變動頻繁。
- **直接採用現成套件**（如 citeformer、groundcite）：見 [docs/research/related-projects.md](../research/related-projects.md)，沒有一個同時涵蓋「重編號＋移除 Fabricated Marker＋中文品質檢查＋注入任意模型」。
