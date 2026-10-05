# Looker Studio Linking API 研究（2026-10-04）

## 結論
- GA4 可靠網址參數替換；Google Ads 在官方 Linking API 頁面「查無」支援；Windsor（社群連接器）語法上可帶參數，但 Windsor 的 connectorId 與設定欄位查無公開資料，帳戶選擇依文件描述綁在 Windsor 帳號端。
- 開網址後存成正式報表需使用者按「編輯並共用」，查無免除方法。
- Looker Studio API 僅能搜尋資產與管理權限，且限 Workspace／Cloud Identity 並需網域全域委派。

## 1. Linking API 規格（來源明確說）
來源：https://developers.google.com/looker-studio/integrate/linking-api （最後更新 2026-04-30 UTC）
- 網址：https://datastudio.google.com/reporting/create?參數
- 控制：c.reportId（範本報表 ID）、c.pageId、c.mode（view|edit，預設 view）、c.explain（除錯對話框）
- 報表：r.reportName、r.measurementId（GA 測量 ID，逗號分隔）、r.keepMeasurementId
- 資料來源：ds.<別名>.connector / datasourceName / keepDatasourceName / refreshFields；ds.* 萬用字元套用全部，個別別名優先
- 別名查法：編輯報表 → 資源 → 管理已新增的資料來源 → 別名欄；單一資料來源可省略別名
- 指定 ds.<別名>.connector = 完全取代（需給齊必填參數）；省略 = 更新範本設定
- GA（connector=googleAnalytics）：accountId（必填）、propertyId（必填）、viewId（僅 UA 必填，GA4 省略）
- 頁面列出的連接器只有 BigQuery、Cloud Spanner、Community Connectors、Google Analytics、Google Cloud Storage、Google Sheets、Looker、Search Console。
- **Google Ads：該頁未列出，查無官方 Linking API 參數。** 試過：連接器參考頁 /looker-studio/connector/linking-api（404）、/connector/google-ads（404）、搜尋 googleAds customerId（僅得使用說明與第三方連接器）。
- 授權：Reusable 資料來源做 Replace 不需範本檢視權；Update 需檢視權；Embedded 繼承報表。

## 2. 社群連接器（來源明確說）
- connector=community；connectorId（亦稱 deploymentId）必填；其餘參數為連接器設定中定義的自訂參數：ds.<別名>.<參數>=<值>
- Linking API 頁面未說明：參數是否須在 getConfig 宣告、overridable、授權限制（未確認）。
- Direct Link 頁（https://developers.google.com/looker-studio/connector/direct-links，2026-04-30）：datasources/create?connectorId=...&connectorConfig=<URL 編碼 JSON>；若連接器尚未授權，預填不生效，使用者須先授權再重開連結。文字欄位用字串、核取方塊用布林、多選用字串陣列。
- 推論：Linking API 對社群連接器的授權限制應與 Direct Link 相同（使用者須先授權過），但 Linking API 頁未明講，屬推論。

## 3. Windsor.ai
- connectorId：**查無公開資料**。
- 設定參數：查無。文件描述為在 Windsor 端授權並選帳戶，再按 Connect → Create Report（https://windsor.ai/how-to-connect-facebook-ads-to-looker-studio/ ；https://windsor.ai/connect/facebook-ads-google-data-studio-integration/ ）。
- Windsor 範本頁（更新 2026-09-07）只提供一條範本編輯連結並要求使用者複製、選 CREATE NEW DATA SOURCE：https://windsor.ai/looker-studio-facebook-ads-dashboard-template/ 。範本網址：https://lookerstudio.google.com/u/1/reporting/f82f3866-6af2-4fcd-95c5-c4ff4ee557a9/page/T4YOB/edit
- 未見任何 Windsor 文件提及 Linking API 或網址建立報表。
- 試過頁面：上述三頁、windsor.ai/documentation/connector-setup-guides、/destinations/google-data-studio（僅搜尋結果列出，未深入抓取）；關鍵字：Windsor Linking API、connectorId、Facebook Ads by Windsor.ai datasources create。
- 推論：帳戶綁在 Windsor 端，網址替換不一定能換帳戶；需實測連接器 getConfig 才知（未確認）。可用 Playwright 開連接器建立頁看網址中的 connectorId，或直接聯絡 Windsor。
- 備註：已有 Windsor MCP（get_data）可直接取數，可作為不經 Looker 的替代設計。

## 4. 儲存正式報表
來源 Linking API 頁：使用者點「編輯並共用」，報表才存到其帳戶。官方頁查無免除此步的 API。

## 5. Looker Studio API
來源：https://developers.google.com/looker-studio/integrate/api
- 主要為 assets:search（資產 ID、標題、擁有者、時間戳、類型、垃圾桶狀態）與權限管理；無法取得報表內部篩選器、區段、維度。
- 資格：須屬 Google Workspace 或 Cloud Identity 組織，需網域全域委派，OAuth 2.0；scope 含 https://www.googleapis.com/auth/datastudio 與唯讀版。
- 頁面未說明建立報表或替換資料來源能力（查無）。權限端點的確切名稱本次未逐一抓取（未確認）。

## 範例網址（GA4 + Windsor；Google Ads 部分無官方語法）
```
https://datastudio.google.com/reporting/create
 ?c.reportId=<範本報表ID>
 &c.mode=edit
 &r.reportName=客戶A_成效報表
 &ds.ga4.connector=googleAnalytics
 &ds.ga4.accountId=<GA帳戶ID>
 &ds.ga4.propertyId=<GA4資源ID>
 &ds.meta.connector=community
 &ds.meta.connectorId=<Windsor Facebook Ads 的 deploymentId：未確認>
 &ds.meta.<帳戶參數名：未確認>=<Meta廣告帳戶ID>
 &ds.gads.connector=<Google Ads 語法：查無>
```
別名 ga4／meta／gads 須與範本內實際別名一致（預設為 ds0、ds1…）。

## 矛盾
- 官方 Linking API 頁（2026-04-30）未列 Google Ads；一般認知中該連接器可用，但本次無官方來源佐證，不採信。
