# /implement-spec 在這個 repo 的規則

這些規則給 implementer 與 merger 用，會疊加在 skill 本身的步驟上。

- spec issue 的 Testing Decisions 就是已同意的 seam，`/tdd` 不必再向使用者確認。
- 不得修改 `models.py`、`config.py` 與 spec issue。非改不可時停下，回報 `BLOCKED: contract` 並附上欄位 diff。merger 拒絕任何碰到這兩個檔的分支。
- README 與 CLAUDE.md 只由 spec 指定的文件 ticket 改寫，v1 是 #20。
- commit 標題：`<prefix>-NN (#N): …`，v1 的 prefix 是 `v1`。
- merger 每次合併後在 integration tip 上跑 `uv sync --all-extras && uv run --all-extras ruff check && uv run --all-extras pytest -q`，紅燈就退回 implementer。
- stage 時明確列出檔名，不用 `git add -A`。
