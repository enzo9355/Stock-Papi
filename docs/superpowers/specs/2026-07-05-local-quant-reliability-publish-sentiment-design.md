# Stock Papi 本地量化可靠度、發布與情緒候選因子設計

## 目標

在不增加 Cloud Run 1GB 記憶體與 webhook 延遲的前提下，補強三個現有缺口：失敗股票能跨夜優先重試、完整市場產物能形成可驗證且不可變的本地發布版本、現有新聞情緒輸出能提供比五級標籤更細的候選因子。

## 範圍

1. `run_market_batch()` 保存跨批次失敗佇列，下一次同市場執行時先重試，再繼續新的 universe 位置。
2. 只有預期 universe 全部有合法 artifact 且沒有待重試股票時，才建立內容雜湊 manifest 與原子 `latest-<market>.json`。
3. 情緒聚合新增加權波動、近期動能、正負分歧、有效樣本數、發布者數與欄位缺漏率。
4. 新情緒欄位先作為候選特徵與 Web／LINE 解釋資料，不直接加入 `MODEL_FEATURES`。

## 資料流

```text
逐股分析
  -> 原子 artifact
  -> checkpoint（next_index + pending failures）
  -> universe 完成且 pending failures 為空
  -> 串流驗證每個 gzip JSON、SHA-256、schema、market、symbol
  -> immutable manifest
  -> 原子更新 latest-<market>.json
```

情緒資料仍沿用 Google News RSS、MarketAux 與美股 StockTwits。聚合層只對已取得的資料做純函式計算，不增加新的網路來源或重型 NLP 套件。

## 發布格式

本地發布目錄：

```text
D:\StockPapiData\publish\quant\v1\manifests\<market>-<run-id>.json
D:\StockPapiData\publish\quant\v1\latest-TW.json
D:\StockPapiData\publish\quant\v1\latest-US.json
```

manifest 至少包含 schema version、market、generated_at、symbol_count、market watermark，以及每檔 artifact 的相對路徑、SHA-256、壓縮大小、as_of 與 model_version。`latest` 只保存 manifest 相對路徑與 manifest SHA-256。

## 發布門檻

- 預期 universe 不得為空。
- 每個 symbol 必須存在對應 artifact，且 gzip、JSON、schema、market、symbol、日期與有限數值驗證成功。
- checkpoint 不得存在待重試股票。
- manifest 完成並重新驗證 SHA-256 後，才原子切換 `latest`。
- 任一步驟失敗時保留上一版 `latest`。

## 情緒候選因子

- `weighted_volatility`：單篇情緒相對加權平均的離散程度，0～100。
- `momentum`：24 小時內與較早新聞的加權情緒差，-100～100；任一視窗無資料時為 0 並標記資料不足。
- `disagreement`：正向與負向權重同時存在的程度，0～100。
- `effective_sample_size`：權重集中度校正後的有效樣本數。
- `publisher_count`：實際新聞發布者去重數，不以 provider 類型代替。
- `missing_metadata_ratio`：來源或發布時間缺漏比例。

這些欄位不直接改變正式五日上漲機率。後續必須累積逐日歷史，使用相同 walk-forward 與五日 gap 比較 Brier score、accuracy、最大回撤與產業覆蓋，通過門檻才可加入正式模型。

## 失敗與安全

- 單股資料或情緒來源失敗只保存 symbol 與錯誤類型，不保存外部回應、標題全文、作者或憑證。
- 磁碟寫入、manifest 驗證或 SHA 不一致立即停止發布，不更新 `latest`。
- 只讀取 `D:\StockPapiData\artifacts\stocks\TW|US`，只寫入既有 `publish` allowlist。
- 不新增依賴、不新增公開匯入 API、不改 LINE callback。

## 測試

- 失敗股票跨批次優先重試，成功後從 checkpoint 移除；重試再失敗不重複累積。
- universe 未完成、缺檔、損壞、symbol 不符時不得更新 `latest`。
- 完整 artifact 產生 deterministic manifest，`latest` 指向正確 SHA。
- 情緒空資料、單一時間窗、正負衝突、權重集中與欄位缺漏均輸出有限值。

