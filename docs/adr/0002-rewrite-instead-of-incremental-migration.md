# 重寫而非漸進遷移：丟掉 Tier 2 程式與 Tier 1 相容性限制

Spec 106 原本以「漸進遷移」把引用層從 Tier 2 程式中抽出，因此背了一串相容性包袱：prompt 必須與 Tier 1 逐字相同、八步遷移每步都要全綠、runtime DTO 與 `specs/` 內的 contract 各存一份再以測試比對、舊對話歷史的 v1/v2 契約並存。為了讓程式可讀、架構能一眼畫出來，改為依新規劃從零重寫：Tier 2 程式以 git tag `tier2-final` 保存後自工作樹刪除，Spec 100–105 移入 `specs/archive/`；引用層的行為設計（marker 文法、首次出現重編號、刪除 Fabricated Marker、No-Answer Reply、只報不攔的 Quality Report）沿用 Spec 106 作為基準。

## Consequences

- 引用層成為唯一可安裝套件，import 名稱是 `showreceipts`（不是 `src.showreceipts`），核心只依賴 Pydantic；Demo 放在 `demo/`，依賴走 `showreceipts[demo]` extra。
- 介面契約只有一份：Phase 0 直接寫進套件的 models 檔並鎖定，不再另放 `specs/.../contracts/*_schema.py` 副本。
- 解除 Tier 1 鎖定：不再要求 prompt 與 Tier 1 逐字相同（Locator 可改為人類習慣的頁碼）；連續空白只清理刪除 Fabricated Marker 後留下的空白，不再整段壓縮（避免 code block 縮排被壓掉）。首次出現重編號與刪除 Fabricated Marker 兩條規則保留。

## Considered Options

- **照 Spec 106 §7 漸進遷移**：每一步都可運行，但新架構會被舊介面的形狀綁住，且相容性測試與雙份契約本身就是要長期維護的程式。
