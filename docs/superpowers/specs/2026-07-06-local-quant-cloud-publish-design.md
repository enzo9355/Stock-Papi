# 本地全市場回測雲端發布設計

## 目標

讓 Windows 本地端在 D 槽完成台股與美股回測後，即使少量股票失敗，仍可安全發布可用結果；Cloud Run 優先讀取已發布結果，缺漏或驗證失敗的股票才即時計算。

## 發布門檻

- 市場 universe 已全部嘗試後才評估發布。
- 失敗率必須嚴格低於 5%，亦即成功率高於 95%。
- manifest 必須記錄 universe 數量、成功數、失敗數、覆蓋率及失敗代碼。
- 失敗、缺檔、損壞或資料日期落後主要市場日期的 artifact 不得列入發布物件。
- 未達門檻時保留上一版 `latest`，不得發布不完整的新版本。

## 資料流

1. `local_quant.py` 完成市場掃描並產生每股 gzip JSON artifact。
2. 發布器驗證 schema、gzip、大小、SHA-256 與市場日期，建立 immutable manifest。
3. 每日 09:35 的獨立 Windows 工作排程只讀取 `D:\StockPapiData\publish\quant\v1`。
4. 上傳順序固定為：內容物件、manifest、`latest-<market>.json`。`latest` 最後更新，避免 Cloud Run 看到半套資料。
5. Cloud Run 依 `latest` 與 manifest 取得個股 artifact，驗證大小與 SHA-256 後才使用。
6. manifest 缺少股票、資料過期或任何驗證失敗時，沿用現有即時計算流程。

## 雲端儲存

- 使用專用私有 GCS bucket，不公開存取。
- 啟用 uniform bucket-level access、public access prevention 與生命週期清理。
- 本機沿用已登入的 `gcloud` 使用者憑證上傳，不建立或保存 service-account JSON key。
- Cloud Run service account 僅授予該 bucket 的 `Storage Object Viewer`。
- 每次 Web 請求只下載單一股票 artifact，不把全市場資料載入 1GB 記憶體。

## 網站與 LINE 行為

- 成功發布的股票：量化資料、回測與圖表使用本地 artifact；新聞與情緒維持即時取得。
- 失敗股票：使用目前的即時計算流程。
- 回應要顯示資料日期與來源狀態，避免把舊快照當成即時資料。
- 雲端讀取錯誤不得使 LINE webhook 或 Web 頁面失敗，必須自動降級。

## 排程與檔案安全

- 原有 02:30 至 09:30 計算時窗不變；台股優先、美股不得早於 05:30。
- 新增 09:35 上傳工作，與模型計算程序分離。
- 上傳器只能讀取 `D:\StockPapiData\publish\quant\v1`，不得掃描或刪除其他路徑。
- 不覆蓋 checkpoint，不補跑計算，不跟隨 symlink 或 junction。
- 上傳失敗只保留舊 `latest` 並寫入不含憑證的狀態日誌。

## 驗證

- 4.99% 失敗可發布；5.00% 失敗不可發布。
- manifest 明列失敗股票且不包含其物件。
- 上傳順序與路徑白名單有單元測試。
- SHA、gzip、schema、大小或日期驗證失敗時不更新 `latest`。
- Cloud Run 命中快照與即時計算 fallback 均有測試。
- 部署前執行完整測試、Python 語法、Git 差異與安全掃描。
