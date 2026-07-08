# Cloud Run 冷啟動最佳化設計

## 目標

在不改變 Stock Papi 路由、LINE 指令、模型、資料來源、回覆內容、1 GiB 記憶體與 scale-to-zero 設定的前提下，降低 `/callback` 冷啟動時間。

## 已確認瓶頸

- 冷啟動請求耗時 13.61 秒。
- 部署映像為 346 MB。
- `pandas`、`numpy`、`scikit-learn`、`lightgbm`、`google.generativeai` 在 `app.py` 匯入時立即載入。
- 不需要個人狀態的 LINE 指令仍會等待最多 0.25 秒的 Firestore 讀取。

## 設計

1. 使用標準函式與鎖延遲載入 Pandas、NumPy 與 Gemini；不新增依賴。
2. 將 `TimeSeriesSplit` 與 `LGBMClassifier` 匯入移到實際回測函式內。
3. 只有依賴關注、提醒或 pending 狀態的指令才讀 Firestore；其餘流程與輸出不變。
4. Docker 建置保留必要編譯能力，但最終執行映像不保留 `build-essential`。
5. 保留 1 worker、8 threads、startup CPU boost 與 scale-to-zero。

## 安全邊界

- 不改憑證、IAM、公開路由與資料權限。
- 延遲載入採執行緒安全初始化。
- 既有完整測試必須通過；部署後以 LINE 官方 webhook 與 Cloud Run 日誌驗證。
- 若映像建置或行為測試失敗，不切換正式流量。

## 成功條件

- 啟動後尚未載入五個重型套件。
- 量化分析與 Gemini 呼叫時仍可正常載入既有實作。
- 不需要狀態的 LINE 選單不讀 Firestore。
- scale-to-zero 後的實測冷啟動顯著低於 13.61 秒；以低於 5 秒為目標，不預先保證。
