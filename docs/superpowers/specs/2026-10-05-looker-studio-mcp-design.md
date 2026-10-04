# Looker Studio 報表 MCP 設計規格

日期：2026-10-05

## 目的

每接一個新客戶，用一句話就能從既有 Looker Studio 範本開出該客戶的成效報表，不必手動複製範本、逐一重接資料來源。

成功的樣子：在 Claude Code 說「幫某客戶開電商版報表」，拿到一條網址；打開後看到已換成該客戶 Meta、Google Ads、GA4、預算試算表資料的報表預覽，按「編輯及共用」即存成新報表。

## 做法

Looker Studio 沒有建立或編輯報表的 API，唯一的程式化入口是 Linking API：用網址參數指定範本報表與每個資料來源的新連線設定。MCP 的工作就是依客戶資料組出這條網址。

### 已實測的事實（2026-10-05，範本副本 `10c6e47c-64d9-41fa-a5b2-cad7602627b0`）

| 資料來源 | 網址參數 | 狀態 |
|---|---|---|
| Meta（Windsor 連接器） | `connector=community`、`connectorId=AKfycbwMs3jUvu_RtMs6XtlspAdiMR8X19N1DAi8mYOCfUxy6I3NHhXRR9qkqxg83fG2js71`、`configuredAccountsSelector=facebook__<廣告帳戶 ID>` | 實測可換，預覽的廣告活動清單已變成另一帳戶 |
| Google Ads | `connector=googleAds`、`accountId=<10 碼客戶 ID>`（`report` 會自動補 `ADWORDS_TANGLE_REPORT`） | 實測接受參數並重建連線；官方文件未列此連接器；尚未逐一比對數字 |
| GA4 | `connector=googleAnalytics`、`accountId`、`propertyId` | 官方文件明列，尚未實測 |
| Google 試算表 | `connector=googleSheets`、`spreadsheetId`、`worksheetId` | 官方文件明列，尚未實測 |

其他已確認的行為：

- 網址沒指定的內嵌資料來源會原樣複製；沒指定的「可重複使用」資料來源會沿用原客戶的連線。因此範本列出的每個資料來源都必須替換，不允許省略。
- 帳戶 ID 無效時，Looker Studio 會顯示錯誤並列出登入帳號可用的 ID。
- 新報表要有人在瀏覽器按「編輯及共用」才會存下來，沒有 API 可免除。
- 加上 `c.explain=true` 後，預覽頁的資訊按鈕會列出每個別名的處理方式，可用來驗收。

## 範圍

做：

- 讀範本清單與客戶清單
- 依「客戶 × 範本」組出 Linking API 網址
- 缺資料或格式錯誤時明確報錯

不做：

- 代點「編輯及共用」
- 設定報表分享權限
- 建立或修改範本（Looker Studio 介面手工）
- 讀取報表內的數據

## 架構

專案位置：`~/Desktop/vibe-coding playground/looker-studio-mcp/`

Python 寫成，使用官方 MCP SDK 的 FastMCP，以 stdio 方式掛在 Claude Code，用 `uv run` 啟動。

```
looker-studio-mcp/
├── server.py          # 註冊三個工具，只做參數轉接
├── registry.py        # 讀取並驗證兩份 YAML
├── url_builder.py     # 純函式：範本 + 客戶 → 網址
├── templates.yaml     # 範本清單
├── clients.yaml       # 客戶清單（含帳戶 ID，不進版控）
├── clients.example.yaml
├── tests/
│   ├── test_registry.py
│   └── test_url_builder.py
└── pyproject.toml
```

三個模組各管一件事：`registry.py` 只負責把 YAML 變成驗證過的資料；`url_builder.py` 不碰檔案也不碰網路，輸入資料、輸出字串，可單獨測試；`server.py` 把兩者接到 MCP 工具上。

## 設定檔

### templates.yaml

```yaml
templates:
  ecommerce:
    name: 電商成效報表
    report_id: 10c6e47c-64d9-41fa-a5b2-cad7602627b0
    sources:
      ds8:   { type: meta_windsor }
      ds25:  { type: google_ads }
      ds0:   { type: ga4 }
      ds119: { type: sheets, sheet: budget }
```

`sources` 的鍵是範本裡的資料來源別名（在「資源 → 管理已新增的資料來源」的別名欄）。`type` 只能是 `meta_windsor`、`google_ads`、`ga4`、`sheets` 四種。`sheets` 類型要用 `sheet` 指出對應客戶的哪一份試算表。

### clients.yaml

```yaml
clients:
  happyhabit:
    name: 每日衡好
    meta_account_id: "1234567890123456"
    google_ads_account_id: "1234567890"
    ga4:
      account_id: "123456789"
      property_id: "987654321"
    sheets:
      budget:
        spreadsheet_id: "1AbC..."
        worksheet_id: "0"
```

所有 ID 一律寫成字串。

### 連接器常數

Windsor 連接器 ID 與四種類型對應的參數名稱寫在 `url_builder.py` 的常數裡，不放進 YAML：它們是 Looker Studio 與 Windsor 的固定值，不隨客戶或範本變。

## 工具

### list_templates

無參數。回傳每份範本的代號、名稱、報表 ID、各別名的類型。

### list_clients

無參數。回傳每個客戶的代號、名稱、已填的資料類型，以及對每份範本而言還缺哪些欄位。

### build_report_url

參數：

| 名稱 | 必填 | 說明 |
|---|---|---|
| `client` | 是 | 客戶代號 |
| `template` | 是 | 範本代號 |
| `report_name` | 否 | 新報表名稱，預設「<客戶名稱>-<範本名稱>」 |
| `explain` | 否 | 預設 `false`；`true` 時加上 `c.explain=true` |

回傳：網址、報表名稱、每個別名被換成什麼（類型與 ID）的摘要。

組網址的規則：

- 基底為 `https://lookerstudio.google.com/reporting/create`
- `c.reportId` 帶範本報表 ID，`r.reportName` 帶報表名稱
- 範本的每個別名各產生一組 `ds.<別名>.*` 參數，並帶 `ds.<別名>.datasourceName`，格式為「<客戶名稱> <類型中文名>」
- 所有值做網址編碼

## 資料驗證與錯誤處理

載入時（`registry.py`）：

- YAML 缺檔或格式錯誤：報錯並指出檔名與位置
- 範本缺 `report_id`、`sources` 為空、`type` 不在四種之內、`sheets` 類型沒有 `sheet`：報錯並指出是哪份範本的哪個別名

組網址時（`build_report_url`）：

- 客戶或範本代號不存在：報錯並列出所有有效代號
- 客戶缺少範本需要的欄位：一次列出全部缺項，不產出網址
- ID 正規化：Google Ads 客戶 ID 去掉連字號後必須是 10 碼數字；Meta 廣告帳戶 ID 去掉 `act_` 前綴後必須是純數字；GA4 兩個 ID 必須是純數字。不符合就報錯並指出欄位

工具無法事先得知的錯誤（Windsor 尚未連接該廣告帳戶、登入的 Google 帳號無權存取該 Google Ads 或 GA4）會在開啟網址時由 Looker Studio 顯示，工具的回傳訊息固定附上這兩項前置條件。

## 測試

單元測試（pytest）：

- `url_builder`：四種類型各自產出的參數正確；多個別名同時存在；中文報表名稱的編碼；`explain` 開關
- `registry`：正常載入；各種格式錯誤的報錯訊息；缺欄位時列出全部缺項；ID 正規化的通過與拒絕案例

實地驗收（固定題庫，三題全過才算完成）：

1. 用範本副本與一個非原客戶的帳戶組合，同時替換 Meta、Google Ads、GA4、試算表四個資料來源，預覽頁無錯誤載入
2. 加 `explain` 開啟，資訊視窗裡四個別名都顯示「先複製範本資料來源，再取代連線設定」
3. Meta、Google Ads、GA4 各取一個指標，與該客戶後台同日期區間的數字相符

## 使用前的手工準備

- 把範本整理成乾淨版：刪除沒有圖表使用的資料來源（測試用副本 15 個裡只有 4 個在用），客戶商標與名稱換成通用字樣
- 每份範本到「管理已新增的資料來源」抄下各別名與類型，填入 `templates.yaml`
- 每個客戶的帳戶 ID 填入 `clients.yaml`；新客戶的 Meta 廣告帳戶要先在 Windsor 連接
