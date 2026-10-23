# Coding Standards

這裡只放需要判斷的規則，在 review 時讀。機械型的規則由 ruff（`pyproject.toml`）與 `tests/test_isolation.py`、`tests/test_demo_page.py` 檢查，不在這裡重複。

## 可讀性

- 模組的數量與層級以「讀者能自己重畫架構」為準。新功能先放進現有模組（CLAUDE.md 的模組地圖），只有放不進去、而且新檔案能讓架構更好畫時才新增檔案。
- 預設不寫註解。只有非顯然的不變式或 workaround 才加一行註解。docstring 只寫在 module-level 與複雜邏輯上。這條在 v1 的 5 張 ticket 都超標過，review 時逐一看新增的註解與 docstring。
- 術語依 GLOSSARY.md，連私有名稱也一樣（例如用 Passage，不用 chunk）。與 ADR 衝突時明確提出，不要默默推翻。

## 測試切面

測試切面依 #9 的 Testing Decisions：

| 檔案 | 測什麼 |
|---|---|
| 主切面（`test_answer.py`、`test_postprocess.py`、`test_markers.py`、`test_quality.py`、`test_splitter.py`、`test_selector.py`、`test_adapters.py`） | 公開 API 加 `fake_generator` fixture，比對輸出的 JSON |
| `test_properties.py` | Hypothesis 產生的輸入下的不變式：marker 外的文字不變、select 不超過預算、壞檔只拋 `ValueError` |
| `test_cli.py`、`test_demo.py`（包裝層） | 只驗證每個操作經包裝後的 JSON 等於直接呼叫 Python API 的結果。行為不在這層重測 |
| `test_generators.py`（網路） | 用 `chat_server` fixture 在 127.0.0.1 起的假端點 |
| `test_isolation.py`（結構） | import 邊界、`__all__`、`extra="forbid"`、環境變數、logging |
| `test_demo_page.py`（前端） | `index.html` 裡 Python 規則的複本，用 node 比對 |

畫面的其餘部分以手動 UAT 驗收，記在 `docs/uat-v1.md`。

- 只測外部行為：呼叫公開函式、比對輸出 JSON，不測內部函式。前端複本是例外，必須拿 `markers.resolve` 的 `marker_spans` 來比對。
- 命名：`test_<feature>_<scenario>_<expected>`。
- 模擬「沒裝 extra」時用 `monkeypatch.setitem(sys.modules, "pypdf", None)`，不用 `importorskip`。
- spec 的每條 AC 都要對應到一個名字看得出 AC 的測試。review 時把 ticket 的 AC 逐條對到測試名稱，對不到就是缺口。v1 的 #19 AC1（加密 PDF）就是這樣漏掉的。

## 對抗式檢查

review 不只對照規則與 spec，還要替新程式碼找出會讓它失敗的輸入。v1 的 bug 都落在這三類：

- **錯誤對應**：使用者可控的輸入（答案文字、Passage JSON、上傳檔）只能拋出 CLAUDE.md「錯誤對應」列出的例外。函式庫的原始例外（`KeyError`、`AttributeError`、`zlib.error`、`DependencyError`…）要包成 `ValueError`。新增的入口或格式要加進 `test_properties.py` 的 fuzz。
- **複雜度**：迴圈裡的 regex、字串拼接、重複掃描，要用 10 萬字等級的輸入想一遍。有疑慮就加計時測試（例如 `test_markers_answer_of_135000_chars_resolved_under_500ms`），門檻 0.5 秒。
- **spec 灰區**：spec 用的是類別詞（「全形標點」「加密的 PDF」「Markdown 的程式碼區塊」）時，實作要涵蓋整個類別，不能只涵蓋舉例。可以拿真實的 Markdown 結構來對照：清單項目、引言、連結、autolink、跳脫字元。
