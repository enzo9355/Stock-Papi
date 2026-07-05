# 台股與美股雙市場本地量化設計

## 目標

每日 05:30–09:20 在本機依序更新台股與美股資料、特徵、五日預測及回測，所有產物留在 `D:\StockPapiData`。不新增虛擬貨幣功能。

## 市場與資料來源

- 台股 universe：沿用 `twstock` 的 `全市場`。
- 美股 universe：每日讀取 SEC 官方 `https://www.sec.gov/files/company_tickers_exchange.json`，只保留 `Nasdaq`、`NYSE`、`CBOE`。
- 排除 OTC、無交易所、無效 ticker，以及名稱明確包含 Bitcoin、Ethereum、Crypto、Solana、Litecoin、Dogecoin 的標的。
- 美股價格、S&P 500／SPY 市場背景與 VIX 特徵沿用既有 yfinance pipeline；不增加套件。
- SEC universe 成功下載後原子寫入 `D:\StockPapiData\raw\us-universe.json`。同日重跑使用快取；下載失敗時可使用既有成功快取，沒有快取才讓美股批次明確失敗。

## 代碼與 artifact

- 台股代碼維持 4–6 位數字。
- 美股允許 1–10 位大寫英數與單一連字號，例如 `AAPL`、`BRK-B`；拒絕斜線、反斜線、點與其他路徑字元。
- artifact 分開寫入：
  - `artifacts/stocks/TW/<symbol>.json.gz`
  - `artifacts/stocks/US/<symbol>.json.gz`
- schema 維持版本 1，`market` 欄位區分市場。

## Checkpoint 與排程

- 台股沿用 `checkpoints/progress.json`，保存目前已完成的 200 筆進度。
- 美股使用 `checkpoints/progress-US.json`。
- 每次排程取得單一 runner lock 後先執行台股，再以剩餘時間執行美股；每檔開始前都檢查 09:20 時間守門。
- 每個市場完成全 universe 後，隔日自行開啟下一輪；未完成則依各自 checkpoint 續跑。
- Windows Task Scheduler 仍於 09:30 硬停止，且 `IgnoreNew` 防止重複執行。

## 線上查詢相容性

- `is_us_ticker()` 擴充為支援 `BRK-B` 類別股代碼，但不接受任意標點。
- `search_stock_code()` 將輸入轉成大寫後使用同一驗證規則。
- LINE 與 Web 現有單股查詢可直接使用新代碼；本階段仍不讓 Cloud Run 直接讀取本地 artifact。

## 錯誤與安全

- SEC URL 固定為 HTTPS，不接受外部 URL。
- 回應設最大 5 MB、15 秒 timeout，解析前驗證 `fields` 與 `data` schema。
- checkpoint、cache 與 artifact 均原子寫入；錯誤摘要不保存外部回應本文或任何憑證。
- 單一股票資料失敗只記錄 symbol 與例外類型；磁碟寫入失敗立即停止。
- 不碰 `secrets` 與既有未追蹤檔 `0.26.0`。

## 驗證

- 純函式測試 SEC schema、交易所／虛擬貨幣排除、ticker 驗證與 cache fallback。
- 測試台美 checkpoint 互不覆蓋、artifact 路徑分離及 09:20 停止。
- 測試 CLI 同一 lock 內依序處理 TW、US，closed window 不下載 SEC。
- 執行完整測試、compile、PowerShell parse、ShellWard 與 `git diff --check` 後推送。
