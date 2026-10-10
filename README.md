# looker-studio-mcp

每接一個新客戶，從既有的 Looker Studio 範本開出一份成效報表，資料來源自動換成該客戶的帳戶。

Looker Studio 沒有新增或編輯圖表的 API，所以這個專案分兩塊：

| 部分 | 做什麼 | 怎麼做到 |
|------|--------|----------|
| MCP server | 替指定客戶組出「從範本建立報表」的網址 | Looker Studio Linking API |
| 編輯器腳本 | 改報表內容（樣式、欄位、比較期間） | Playwright 操作編輯器畫面 |

## 需求

- Python 3.11 以上
- [uv](https://docs.astral.sh/uv/)
- 客戶的 Meta 廣告帳戶已在 Windsor 連接
- 開啟網址的 Google 帳號有該客戶 Google Ads、GA4 與試算表的存取權

## 安裝

```bash
git clone https://github.com/Liiiiwei/looker-studio-mcp.git
cd looker-studio-mcp
uv sync
cp clients.example.yaml clients.yaml
```

把 MCP server 註冊到 Claude Code：

```bash
claude mcp add --scope user looker-studio -- uv run --directory "$(pwd)" python server.py
```

註冊後要開新對話才看得到工具。

## 設定

### 範本：`templates.yaml`

每份範本記錄報表 ID，以及報表裡每個資料來源的別名與類型。

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

類型有四種：`meta_windsor`、`google_ads`、`ga4`、`sheets`。別名（`ds8` 這類）要從範本報表的「資源 → 管理已新增的資料來源」查。

### 客戶：`clients.yaml`

這個檔不進版控。格式見 `clients.example.yaml`，所有 ID 都要加引號。

| 欄位 | 填什麼 |
|------|--------|
| `meta_account_id` | Meta 廣告帳戶 ID，不含 `act_` |
| `google_ads_account_id` | Google Ads 客戶 ID，10 碼，有無連字號皆可 |
| `ga4.account_id`、`ga4.property_id` | GA4 帳戶與資源 ID |
| `sheets.<名稱>.spreadsheet_id` | 試算表網址 `/d/` 與 `/edit` 之間那一段 |
| `sheets.<名稱>.worksheet_id` | 工作表網址 `gid=` 後面的數字 |

設定檔預設讀專案目錄；要放別處就設環境變數 `LOOKER_STUDIO_MCP_CONFIG_DIR`。

## MCP 工具

| 工具 | 用途 |
|------|------|
| `list_templates` | 列出範本：代號、名稱、報表 ID、各資料來源的類型 |
| `list_clients` | 列出客戶：已填齊的資料類型，以及套用每份範本還缺哪些欄位 |
| `build_report_url` | 替指定客戶從指定範本組出建立報表的網址 |

`build_report_url` 的參數：

| 參數 | 說明 |
|------|------|
| `client` | 客戶代號 |
| `template` | 範本代號 |
| `report_name` | 報表名稱，不填為「客戶名稱-範本名稱」 |
| `explain` | 設為 `true` 時，預覽頁會列出每個資料來源的處理方式，除錯用 |

客戶缺少範本需要的任何帳戶 ID 時會報錯，不會產出網址。

這個工具只產生網址。報表要在瀏覽器開啟網址、確認預覽數據是該客戶的，再按右上角「編輯及共用」才會存下來。

## 編輯器腳本

把要做的編輯步驟寫成 JSON，組成一支 Playwright 腳本一次跑完，最後只截一張圖確認。

```bash
uv run python editor_script.py editor_steps/smoke-check.json \
  -o run.js --screenshot .playwright-mcp/done.png
```

產出的 `run.js` 交給 Playwright MCP 的 `browser_run_code_unsafe`（`filename` 參數）執行。回傳每一步的成敗；遇到第一個錯誤就停。

步驟清單範例：

```json
[
  {"op": "goto", "url": "https://datastudio.google.com/u/0/reporting/<報表 ID>/page/<頁面 ID>"},
  {"op": "mode", "name": "編輯"},
  {"op": "select", "x": 500, "y": 350},
  {"op": "set_select", "label": "行高", "option": "32px"},
  {"op": "mode", "name": "查看"}
]
```

可用的步驟：

| `op` | 必填欄位 | 作用 |
|------|----------|------|
| `goto` | `url` | 開啟報表網址 |
| `mode` | `name` | 切換模式，`name` 是右上角按鈕文字（「編輯」或「查看」） |
| `select` | `x`、`y` | 點選畫布上的元件 |
| `tab` | `name` | 切換屬性面板分頁（「設定」或「樣式」） |
| `set_select` | `label`、`option` | 樣式面板的下拉選單，依標籤與選項文字 |
| `pick_color` | `label`、`col`、`row` | 從色盤選色，欄列從 1 起算 |
| `rename_field` | `from`、`to` | 改欄位在這張圖表上的顯示名稱 |
| `set_field` | `from`、`to` | 把圖表上的欄位換成另一個欄位 |
| `compare_previous` | 無 | 開啟比較日期範圍，選「上一個時段」 |
| `copy_paste` | 無 | 複製選取的元件，貼在同一區段 |
| `drag` | `from`、`to` | 拖曳，兩者都是 `[x, y]` |
| `type_text` | `x`、`y`、`text` | 連點兩下文字方塊，整段換掉 |
| `click` | `x`、`y` | 點一下 |
| `press` | `key` | 按鍵 |
| `wait` | `ms` | 等待 |

限制：

- 瀏覽器視窗必須是 1680×1000，座標以此為準。
- `select`、`click`、`drag`、`type_text` 用的是視窗座標，換一頁要先截圖取座標。
- 只在 `smoke-check.json` 用到的步驟（`goto`、`mode`、`select`、`set_select`）以腳本形式實跑過；其餘步驟的手法逐步操作時驗證過，尚未用腳本跑過。

## 測試

```bash
uv run pytest
```

## 文件

| 檔案 | 內容 |
|------|------|
| `docs/superpowers/specs/2026-10-05-looker-studio-mcp-design.md` | MCP 的設計規格 |
| `docs/superpowers/specs/2026-10-05-report-style-design.md` | 報表樣式規格：內容規則、版面網格、顏色角色、字級、驗收十題 |
| `docs/research/2026-10-05-linking-api-research.md` | Linking API 的查證筆記 |
