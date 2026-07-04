# 本地資料保留與安全清理設計

## 目標

每日本地量化排程開始下載前，自動刪除 `D:\StockPapiData` 內已過期且可重建的資料，避免長期占用 D 槽；刪除範圍不得離開該根目錄。

## 清理範圍

| 路徑 | 保留期 |
| --- | ---: |
| `cache/tmp` | 1 天 |
| `cache/pycache` | 30 天 |
| `raw` | 30 天 |
| `logs` | 30 天 |
| `publish` | 30 天 |
| `checkpoints/runner.lock.stale.*` | 7 天 |

不清理 `secrets`、`artifacts/stocks`、`checkpoints/progress.json` 或目前的 `runner.lock`。股票 artifact 會依代碼原子覆寫，不需用期限刪除。

## 安全規則

- 入口仍強制根目錄為 `D:\StockPapiData`。
- 只掃描固定 allowlist；不接受外部傳入任意子路徑。
- symlink、junction 與其他 reparse point 一律跳過，不跟隨到根目錄外。
- 只刪除超過保留期的普通檔案，再嘗試移除清理後的空子目錄；allowlist 頂層目錄保留。
- 單檔刪除失敗記入摘要，不中斷整批；根目錄或邊界驗證失敗則拒絕執行。

## 執行時機與輸出

清理只在 `--run` 且時間位於 05:30–09:20 時執行，並放在 runner lock 內、載入市場 pipeline 之前。摘要寫入 `runner-status.json`，只包含刪除檔案數、回收位元組數、失敗數與跳過 reparse point 數，不記錄檔名或憑證。

## 驗證

- 單元測試驗證期限邊界、保留項目、reparse point 跳過與空目錄處理。
- CLI 測試驗證只在允許時段及 `--run` 路徑呼叫清理。
- 完整測試、Python compile、PowerShell parse、ShellWard 與 `git diff --check` 全部完成後才更新排程與推送。
