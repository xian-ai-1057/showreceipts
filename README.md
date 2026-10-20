# showreceipts

不綁定任何 RAG 框架的引用層：拿到段落（來自任何檢索系統，或直接從上傳的文件切出），產出帶 inline `[n]` 引用的答案，並附上不呼叫模型的品質檢查。

> 原名 Tag RAG。Tier 2 的本地 RAG demo（Streamlit + Chroma + LangChain）以 git tag `tier2-final` 保存；目前依 [issue #9](https://github.com/xian-ai-1057/showreceipts/issues/9) 重寫中。

## 狀態

重寫依 #9 拆成 10 張 ticket（#11–#20）。目前完成 v1-01：套件骨架與資料模型契約，還沒有可呼叫的操作。完整的使用說明會在 v1-10 補上。

## 開發

```bash
uv sync              # 安裝核心（只依賴 pydantic）與測試工具
uv run pytest -q     # 全部測試皆離線執行
```

選配依賴：`pdf`、`docx`（文件切段）、`demo`（demo 後端），例如 `uv sync --extra demo`。

## 文件

- [GLOSSARY.md](GLOSSARY.md)：術語（Passage、Citation Marker、Fabricated Marker、Selector…）
- [docs/adr/](docs/adr/)：架構決策（0001 引用層定位、0002 重寫、0003 文件切段）
- [docs/research/related-projects.md](docs/research/related-projects.md)：相關專案調查
- [specs/archive/](specs/archive/)：Tier 2 時期的 Spec 100–106（只供參考）
