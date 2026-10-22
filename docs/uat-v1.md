# v1 UAT 紀錄

demo 前端（`demo/index.html`）沒有自動化測試，依 #9 的 Testing Decisions 以手動 UAT 驗收。驗收項目來自 #20 的留言：

- 貼上模式問兩題，題目是 Spec 106 AC #27(b) 的兩題。
- 上傳模式用 `data/richart.md` 問一題。
- 每個 `[n]` 都要點開，查證側欄原文確實支持該句。

本紀錄分兩部分：

| 部分 | 狀態 |
|---|---|
| [真模型 UAT](#真模型-uat) | **待 Lead 以 .env 模型執行**。v1-10 的容器裡沒有 Ollama，也沒有 Lead 提供的 `.env`。 |
| [模擬檢查（假 Generator）](#模擬檢查假-generator) | 2026-10-21 完成，37/37 通過。這部分只檢查畫面機制，不檢查模型答案的品質。 |

## 真模型 UAT

### 執行方式

```bash
cp .env.example .env                    # Lead 填入端點、模型與 API key；.env 已被 gitignore
export NO_PROXY=localhost,127.0.0.1     # 連本機模型時
uv run --env-file .env --all-extras uvicorn demo.app:create_app --factory
# 打開 http://127.0.0.1:8000/
```

**API key 不得寫進本檔、終端輸出、截圖或 issue。** 本檔只記錄模型名稱與端點類型（例如「本機 Ollama」）。

- 執行日期：（待填）
- 模型 `SHOWRECEIPTS_MODEL`：（待填）
- 端點類型：（待填，不寫 key）

### 檢查清單

| # | 模式 | 問題 | 通過條件 | 結果 |
|---|---|---|---|---|
| R1 | 貼上（預填 Richart 樣本） | 切換 Pay 著刷最高回饋多少？在超商用 LINE Pay 有回饋嗎？ | 答出 3.8% 與「LINE Pay 在超商無回饋」；每個 `[n]` 的側欄原文都支持該句 | 待 Lead 以 .env 模型執行 |
| R2 | 貼上（預填 Richart 樣本） | 繳保費可以拿到多少回饋？切換假日刷呢？ | 答出免切換 1.3%、切換假日刷最高 2%；每個 `[n]` 的側欄原文都支持該句 | 待 Lead 以 .env 模型執行 |
| R3 | 上傳 `data/richart.md` | Richart 卡正卡年費多少？一般消費的回饋是多少？ | 答出 NT$4,500 與 0.3%；側欄的 Locator 是標題路徑；每個 `[n]` 的側欄原文都支持該句 | 待 Lead 以 .env 模型執行 |
| R4 | R1–R3 共同 | — | Quality Report 的底色、虛線、紅字標示與答案內容相符 | 待 Lead 以 .env 模型執行 |
| R5 | R1–R3 共同 | — | 展開「原始答案 vs. 處理後答案」，列出的 Fabricated Marker 確實已從答案刪除；若模型沒寫錯編號，清單為空 | 待 Lead 以 .env 模型執行 |
| R6 | R1–R3 共同 | — | 終端與畫面都沒有印出 API key | 待 Lead 以 .env 模型執行 |

### 查證參考

下表依資料內容整理，不是模型輸出。答案中的 `[n]` 依首次出現順序編號，和 Passage 在清單中的位置無關，所以請以側欄的 Passage ID 或 Locator 對照下表。

| # | 支持答案的 Passage |
|---|---|
| R1 | `…054735`（「於四大超商繫結臺新 Pay 享最高 3.8%（注意: LINE Pay 超商無回饋）」）；`…054657`（「切換【Pay 著刷】方案享最高 3.8%」） |
| R2 | `…054734`（「保費免切換 1.3%」）；`…054735`（「保費切換『假日刷』享 2% 回饋嗎？…可享最高 2% 回饋」） |
| R3 | `二、年費辦法`（「正卡每卡每年 NT$4,500」）；`四、保費與一般消費 > 一般消費 0.3%`（「一般消費享 0.3% … 回饋無上限」） |

### 每個 `[n]` 的查證紀錄

由 Lead 執行時填寫。每題的每個 `[n]` 各一列。

| # | `[n]` | 側欄的 Source · Locator · Passage ID | 原文是否支持該句 |
|---|---|---|---|
| R1 | | | |
| R2 | | | |
| R3 | | | |

## 模擬檢查（假 Generator）

這部分檢查畫面上的每個機制都接得上：點 `[n]` 開側欄、原始答案與處理後答案的對照、Fabricated Marker 清單、Quality Report 標示、錯誤訊息。檢查以真瀏覽器操作真的 demo 後端，只有 Generator 換成假的。

### 做法

- **時間與版本**：2026-10-21，分支 `claude/v1-10`，基底是 integration tip `3638718`。
- **後端**：以 `create_app(generator=fake_generator)` 建立 app，由 uvicorn 跑在 `127.0.0.1`。沒有讀 `.env`，也沒有用到任何 API key。
- **瀏覽器**：Playwright 1.56.1 驅動 headless Chromium，逐項斷言 DOM，並留下截圖。
- 腳本是 repo 外的一次性腳本，沒有 commit；playwright 也沒有加進專案依賴。

假 Generator 的行為：

- 先從 prompt 的第 `[1]` 段抄一行文字，接上 `[1]`。這一句應該 supported。
- 再接三句固定文字：

  ```text
  這句話是假 Generator 自己寫的，來源裡沒有[2, 99]。正卡年費 4,500 元，回饋上限 100 億。
  詳情請洽客服[3-1]。
  ```

  - `[2, 99]` 只有 99 越界。
  - `[3-1]` 是反向範圍。
  - 第三句有數字卻沒標來源，而且「100 億」在所有來源裡都找不到。
- 問題含「觸發錯誤」時，拋出 `GeneratorError`。

依 #9 的規則，處理後答案應是 `…[1]。這句話是假 Generator 自己寫的，來源裡沒有[2]。正卡年費 4,500 元，回饋上限 100 億。\n詳情請洽客服。`，畫面上也應該看到以下結果：

| 項目 | 預期 |
|---|---|
| `fabricated_markers` | `["[2, 99]", "[3-1]"]` |
| 句子 | 4 句，1 句 supported，`quality_score` 0.25 |
| Uncited Sentence | 1 句，數字是 `4,500`、`100` |
| 來源裡找不到的實體 | `100 億` |

貼上模式問的是 R1、R2 兩題，上傳模式問的是 R3。模型答案由假 Generator 產生，所以這部分不驗證答案內容是否正確。

### 結果

37/37 通過。

| 檢查項 | 貼上 | 上傳 | 觀察到的畫面 |
|---|---|---|---|
| 進入模式時的預設內容 | 通過 | 通過 | 貼上：切到貼上模式，輸入框預填的 JSON 等於 `data/richart_passages.json`（6 段）。上傳：預設就是上傳模式，預選 repo 附的 `richart.md`，重新整理後問答清空。 |
| 以檔案選擇器上傳 | — | 通過 | 選 `data/richart.md` 後，顯示「目前的 Document：richart.md，6,022 bytes」 |
| 預覽切段 | — | 通過 | 列出 15 段，每段有 Locator（標題路徑）、字數與 Passage ID，例如「一、卡片介紹 > 卡片名稱 · 57 字 · 6b32fff5b9ee:0」 |
| 送出問題時的請求內容 | 通過 | 通過 | `/answer` 回 200。貼上：請求帶 6 段 `passages`、不帶 `document`。上傳：請求帶 `document`（richart.md 的 base64）、不帶 `passages` |
| 上傳模式的 Passage 來自 split | — | 通過 | 被引用的 Passage ID 是「文件 sha256 前 12 碼:序號」，Source 是 `richart.md`，Locator 是標題路徑 |
| 答案中只有有效的 `[n]` 可點 | 通過 | 通過 | 答案裡只有 `[1]`、`[2]` 兩個按鈕，處理後答案不含 99 與 `[3-1]` |
| 點答案中的 `[1]` 開側欄 | 通過 | 通過 | 側欄標題「引用 [1]」，Source、Locator、Passage ID 與原文都等於第 1 段。貼上模式另有 Score（0.98095703125）；上傳模式沒有 score，不顯示 Score 列 |
| 點 `[2]` 換段 | 通過 | 通過 | 側欄換成第 2 段（貼上 `…054735`；上傳 `一、卡片介紹 > 臺新信用卡切換刷平臺`），反白從 `[1]` 移到 `[2]` |
| 答案下方的引用清單 | 通過 | 通過 | 列出 `[1]`、`[2]` 與各自的 Source（Locator）；點清單裡的 `[1]` 也會開側欄 |
| 原始答案 vs. 處理後答案 | 通過 | 通過 | 預設收合，點開後左右對照：原始答案含 `[2, 99]`、`[3-1]`，處理後答案不含 |
| 被刪除的 Fabricated Marker 清單 | 通過 | 通過 | 摘要寫「刪除的 Fabricated Marker：2 個」，清單是 `[2, 99]`、`[3-1]` |
| 含數字但未標來源的句子加底色 | 通過 | 通過 | 只有「正卡年費 4,500 元，回饋上限 100 億。」加底色，滑鼠提示是「含數字但沒有標來源：4,500、100」 |
| 低支持度句加虛線 | 通過 | 通過 | 4 句中有 3 句加虛線；抄自來源的第 1 句沒有虛線 |
| 來源找不到的數字標紅 | 通過 | 通過 | 只有「100 億」標紅，位在加底色的那一句裡 |
| Quality Report 摘要 | 通過 | 通過 | 「Quality Report（字面重疊訊號，不代表答案正確）：1/4 句達支持度門檻，quality_score 0.25。」 |
| 連問第 2 題 | 通過 | — | R2 的問答排在最上面，R1 仍保留在頁面上 |
| GeneratorError 的錯誤訊息 | 通過 | 通過 | 後端回 502。畫面顯示「Generator 無法使用（HTTP 502）：simulated failure from the fake generator (endpoint unreachable)」；不新增問答，「提問」按鈕恢復可按 |
| 輸入錯誤（422）的錯誤訊息 | 通過 | 通過 | 貼上：Passage 的 `id` 為空時顯示「輸入有誤（HTTP 422）：body.passages.0.id：String should have at least 1 character」。上傳：不是 UTF-8 的 `.txt` 顯示「輸入有誤（HTTP 422）：bad.txt is not UTF-8 text: …」 |
| 不支援的格式 | — | 通過 | 對 `.xlsx` 按「預覽切段」，顯示「輸入有誤（HTTP 422）：unsupported document format for 'table.xlsx'; supported: .md, .txt, .pdf, .docx」 |
| 輸入框不是 JSON | 通過 | — | 送出前就顯示「Passage JSON 格式錯誤：…」 |
| 重新載入範例 | 通過 | 通過 | 貼上：「重新載入 Richart 樣本」還原輸入框。上傳：「改用範例 richart.md」換回範例文件 |
| 全程沒有 JavaScript 錯誤 | 通過 | 通過 | 沒有 `pageerror`，也沒有 console error。刻意觸發 422／502 時，瀏覽器記下的 "Failed to load resource" 不計 |
