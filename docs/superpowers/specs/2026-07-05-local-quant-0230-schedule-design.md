# 本地量化 02:30–09:30 安全排程設計

## 目標

將本地量化與回測時段調整為台北時間 02:30–09:30，台股優先；美股仍須等美盤收盤後才處理。使用者資料、憑證、D 槽檔案與系統穩定性優先於處理速度。

## 執行順序

1. Windows Task Scheduler 每日 02:30 啟動單一 `StockPapi-LocalQuant` task。
2. wrapper 先執行 `--market TW --limit 5000`。
3. 台股完成後，若時間早於 05:30，wrapper 使用 `Start-Sleep` 等待，不下載、不訓練、不持有 Python 模型程序。
4. 05:30 後執行 `--market US --limit 5000`。
5. Python 每檔開始前仍於 09:20 停止領取新工作；Task Scheduler 於啟動滿 7 小時，也就是 09:30，硬停止 wrapper 與子程序。

如果台股執行至 09:20，美股本次會以 closed／drain 狀態安全略過，隔日再依 `progress-US.json` 續跑。不讓美股為了趕進度使用未收盤資料。

## 安全規則

- 台股與美股維持獨立 checkpoint 與 artifact 目錄。
- wrapper 每個市場執行後檢查 exit code；台股 runner 發生系統級失敗時不繼續美股。
- 等待期間不繞過 Windows Task Scheduler 的 `IgnoreNew`，不建立第二個 task。
- 不變更 `D:\StockPapiData` ACL、allowlist 清理規則、100 GB 空間門檻或 secrets 排除規則。
- 不在目前非允許時段補跑實際市場下載。

## 驗證

- Python 邊界測試：02:29 closed、02:30 run、09:20 drain、09:30 closed。
- wrapper 靜態測試：TW 位於 US 前、含 05:30 等待、兩次執行均為 5,000 上限。
- installer 靜態與實際驗證：02:30 trigger、PT7H、IgnoreNew、StartWhenAvailable=false、Limited principal。
- 完整回歸、安全掃描與非工作時段 closed 實測後才推送。
