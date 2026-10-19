# 引用層也負責把文件切成 Passage（擴大 ADR-0001 的邊界）

ADR-0001 把引用層限定在「檢索之後」，假設 Passage 一定來自某個 RAG 框架。但 arrkb 還在改、未來不一定沿用，而且要支援「在 harness 對話中直接上傳文件就問答」——這個情境沒有任何檢索系統。因此引用層也提供「文件 → Passage」：切段並標上 Locator（頁碼、章節）。檢索結果仍可來自任何外部系統，經 Adapter 轉成 Passage；arrkb 只是其中一個 Adapter，不再有特殊地位。核心依舊只依賴 Pydantic，PDF、DOCX 等格式解析放在 extra。

## Considered Options

- **維持只管檢索之後，切段交給呼叫端**：每個 harness 都得自己切段、自己產生 Locator；而 Locator 的品質（頁碼對不對）直接決定引用能不能被查證，等於把引用品質的一半交給別人。
