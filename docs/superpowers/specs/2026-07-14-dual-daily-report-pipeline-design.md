# Stock Papi 雙每日報告與背景回測設計

## 1. 目標

Stock Papi 保持「預測接下來五個交易日方向」為核心，將現有單一批次拆成三個可獨立發布、互不冒充的產品：

- `post_close`：使用已驗證收盤資料，產生下一交易日可用的五日預測與盤後主報告。
- `pre_market`：只加入有來源、時間與新鮮度的隔夜風險，不修改盤後模型機率。
- `weekly_model`：只使用通過品質閘門的完整回測與已成熟預測，呈現模型驗證結果。

完整回測在本機低優先執行，可跨日 checkpoint／resume；Cloud Run 仍只讀取已完成且通過驗證的成品。

## 2. 2026-07-14 實際基線

### Repository

- branch：`main`，HEAD `45d315e`，與 `origin/main` 同步。
- tracked worktree 無修改。
- 既有未追蹤內容：`.codex/`、`AGENTS.md`、`0.26.0`、`deliverables/`、`static/samples/`；本任務不得覆蓋或納入 commit。
- 最新 commit 已包含版面強化、symbol 正規化、ETF 分離與術語修正。
- 完整測試在可讀取 `.deps`／`.report-deps` 的受控環境為 `391 tests` 全數通過，耗時 29.593 秒。

### 現有 route inventory

共有 27 條非 static route。報告只有：

- `GET /reports`
- `GET /reports/<report_date>`
- `GET /reports/<report_date>/preview`
- `GET /reports/<report_date>/download`
- `GET /reports/sample/download`

舊 preview/download 只 302 到 HTML，不回傳 PDF bytes。LINE Login 已有 Authorization Code Flow、OIDC verify、state、nonce、PKCE、server-side session、CSRF、safe return path 與 private/no-store 個人端點。

### 本機批次與排程

- `StockPapi-LocalQuant`：02:30，`StartWhenAvailable=False`、`WakeToRun=False`、`IgnoreNew`、PT7H。
- `StockPapi-QuantUpload`：09:35，`StartWhenAvailable=False`、`WakeToRun=False`、`IgnoreNew`、PT1H；2026-07-14 最後結果為 1，且 `upload-status.json` 仍停在 2026-07-09。
- wrapper 先跑 TW，再生成日報，等待 05:30 後才跑 US；upload 固定 09:35。
- `local_quant.py` 每檔讀取 730 日、重算特徵並呼叫同時包含 walk-forward 與最新推論的 `run_ai_engine()`。
- TW／US／insights 共用 `checkpoints/runner.lock`；長工作會阻塞其他工作。
- checkpoint 只有 market、next_index、failed、updated_at 等欄位，沒有固定 `target_market_date`、來源 manifest 或 model version；跨日續跑可能混合不同資料日。

### 正式資料

- TW quant latest：market_as_of `2026-07-09`，2,076 universe、2,071 symbols、5 failures、coverage 99.759%，model `lgbm-5d-v1`。
- US quant latest：market_as_of `2026-07-10`，12,719 universe、10,741 symbols、1,978 failures、coverage 84.448%。
- 2026-07-14 TW checkpoint：next_index 2,076、6 failures，但沒有 cycle completed／published 標記。
- 正式報告 latest 仍為資料日 `2026-07-09`，schema v1，8 頁；現存 metadata 沒有 `public_report`，Web 以 legacy summary 安全降級。

### 現有發布契約

- Quant：content-addressed gzip object → immutable manifest → atomic latest。
- Report：immutable PDF → immutable metadata → atomic index → atomic latest。
- uploader 先驗證 allowlist、reparse point、size、SHA-256、schema 與 source manifest，再依 PDF → metadata → index → latest 上傳。
- schema v1 以 `report_date` 為唯一鍵，同一天不能保存盤後與盤前兩份內容，且每份報告強制有 PDF。

## 3. 不建立第二套系統

沿用以下既有能力：

- `local_quant.py` 的 D 槽 allowlist、gzip/object/manifest/latest、原子寫入與 checkpoint 基礎。
- `reporting.source_loader` 的 SHA-256、size、uncompressed_size、schema、market、symbol、日期驗證。
- `reporting.publisher` 的 content-addressed 發布順序與 local mirror。
- `reporting.web`、`report_store` 的 GCS reader trust boundary。
- `recommendation_engine` 作為 Web、LINE、HTML、PDF 的唯一 action label 來源。
- `backtest/` 的 point-in-time contract、OOS、execution、portfolio、quality gate 與 rollback 骨架。
- 現有 LINE Login、Firestore user isolation、CSRF、cookie 與公開／私有快取邊界。

## 4. 交易日與時間語意

### 權威來源

本機同步 TWSE 官方 OpenAPI `https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule`，建立內容定址的年度 calendar artifact。官方 Swagger 明確將此端點定義為「有價證券集中交易市場開（休）市日期」。

calendar artifact 必須包含：

- `schema_version`
- `market`
- `year`
- `source_url`
- `fetched_at`
- `source_sha256`
- `closed_dates`
- `special_open_dates`
- `valid_from`／`valid_to`

交易日由「週一至週五基礎集合 - 官方休市 + 官方特殊開市」計算。沒有涵蓋目標日期且通過驗證的 calendar artifact 時 fail closed；不得只靠 weekday 繼續發布。

### 統一欄位

所有新報告必須保存：

- `source_market_date`
- `applicable_trading_date`
- `published_at`
- `forecast_start_date`
- `forecast_end_date`
- `backtest_as_of`
- `data_as_of`

盤後 `source_market_date` 必須等於已驗證 quant manifest 的 `market_as_of`；`applicable_trading_date` 與五日終點只由已驗證交易日曆計算。盤前沿用 base post-close 的核心模型欄位，另存 `overnight_as_of`。

## 5. Job 與資源邊界

固定 job type：

- `daily_prediction`
- `post_close_report`
- `pre_market_update`
- `full_backtest`
- `weekly_model_report`
- `upload`

每個 job 有獨立 lock、checkpoint、status 與 output namespace。daily job 建立 `daily-pipeline.lock` 時，full backtest 只在 symbol／fold 邊界 yield，保存 checkpoint 後退出；daily 不等待 full backtest lock。

lock 必須包含 pid、ownership token、job type、target date、started_at、updated_at。只允許 owner token release；stale lock 封存，不直接覆寫。

## 6. Daily Prediction Fast Lane

現有 `run_ai_engine()` 同時做 walk-forward OOS 與最新 final fit。第一階段拆出共用 final-fit helper：

- `run_latest_inference()`：只訓練現行 final model 並產生最新 `AI_P`。
- `run_ai_engine()`：繼續做 walk-forward，再呼叫相同 final-fit helper。
- parity test 必須證明相同輸入與 model version 下，fast lane 機率等於完整引擎的最新機率。

fast lane 先沿用既有 730 日 cache 與特徵流程，不新增 pickle/joblib 或第二套模型。完整回測結果改由最近一次已 promotion 的 backtest artifact 提供；若 model version 不相符，confidence 降級且禁止強 action。

## 7. Full Backtest Worker

full backtest 使用固定 dataset snapshot 與 immutable candidate artifact，可跨日執行。candidate 至少綁定：

- dataset manifest path／SHA-256
- model version／feature schema version
- cutoff／data range
- walk-forward folds／five-session gap
- OOS predictions
- strategy metrics、calibration、cost sensitivity、year／regime breakdown
- generated_at／git SHA

只有 parity、leakage、calibration、schema、安全與品質閘門全通過，才 atomic promote `backtests/v1/latest-TW.json`。daily 只讀 promoted latest。

## 8. Prediction Ledger

不用可覆寫資料列。採 immutable file ledger：

```text
predictions/v1/records/<forecast_id>.json
predictions/v1/settlements/<forecast_id>-<content_sha256>.json
predictions/v1/index-TW.json
```

`forecast_id` 由 market、entity type/id、source market date、model version、source manifest hash 的 canonical bytes 決定。相同內容重跑回傳既有 record；不同內容不得覆寫同 id。

settlement 只追加，原始 probability、action、issued_at、model version 與 data hash 永不修改。成熟判斷使用 ledger 綁定的 forecast sessions；active／invalid 不納入 accuracy。

## 9. Pipeline

### Post-close

1. 固定 run_id、target market date 與 calendar version。
2. 輪詢 quant manifest readiness；manifest 日期不符時 bounded retry，deadline 後 fail closed。
3. 執行 fast lane、產業聚合與既有 recommendation engine。
4. 結算已滿五個實際交易日的舊 forecast。
5. 寫入 immutable prediction records 與 development projection。
6. 建立 report schema v2 metadata；盤後 PDF 仍可生成。
7. 驗證後依 immutable object／metadata → index → latest 發布。
8. 上傳、remote read-back、通知；通知失敗不回滾成功發布。

### Pre-market

- 必須先有相同 applicable trading date、通過驗證的 post-close base。
- 外部來源逐筆有 source、as_of、freshness、timeout、size/schema limit 與錯誤隔離。
- overlay 狀態固定 allowlist；不得改寫 core probability、score、calibration 或 model evidence。
- 所有來源不可用時顯示「資料不足，維持盤後判斷」。沒有 base report 時不生成正常快報。
- 以 HTML/JSON metadata 為主，不生成無用途 PDF。

### Weekly model

- 只由成功 promotion 的 backtest artifact 與 matured ledger 生成。
- 嚴格分開五日上漲機率、歷史方向準確率、策略交易勝率、高分訊號實際上漲率。
- 沒有新 promoted backtest 時保留上一份週報，不生成假的新版本。

## 10. Report schema v2

writer 只寫 v2；reader 同時接受嚴格驗證的 v1 與 v2。v1 映射為 `post_close`，`source_market_date = applicable_trading_date = report_date`，未知新欄位保持 `None`，不推測。

v2 index 唯一鍵為 `(report_type, source_market_date, applicable_trading_date, content_sha256)`，允許同一適用交易日包含 post-close 與 pre-market。PDF 欄位只對 `post_close`／`weekly_model` 可選存在；`pre_market` 不要求 PDF。

舊 `/reports/<date>` 永遠解析為該 source date 的 post-close。新增：

- `GET /reports/trading-day/<trading_date>`
- `GET /reports/<trading_date>/pre-market`
- `GET /reports/weekly/<week_id>`

## 11. Web 與 LINE

- Dashboard 最前面顯示「今日交易準備」；資料只來自已驗證 public report metadata。
- 盤前未發布時只顯示緊湊狀態，不補 `--` 或假值。
- 非交易日由 calendar artifact 決定，顯示最近有效交易日與「今日休市」。
- 個股／產業頁分開 core model as_of 與 pre-market overlay as_of。
- 公開頁不混入登入狀態；個人關注仍走 private/no-store endpoint。
- LINE 公開摘要使用 report content hash 形成 notification key；receipt 先保存 pending，成功後保存 sent，重試不重複推送。

## 12. Status、backfill 與排程

status 使用 `logs/pipeline-status/current-<job>.json` 與每次 run transcript；所有寫入原子化，錯誤文字經 redaction，不記錄 token、header、user id 或 credential。

先做本機 CLI，不新增 Web admin page。`pipeline status` 顯示最近成功、目前 stage、最後錯誤、manifest/report date。

backfill 預設 dry-run，只接受明確 source manifest path + hash + model version；不存在 verified manifest 時拒絕。歷史 overnight context 未保存時不回補 pre-market。

新排程：

- `StockPapi-TW-PostClose`
- `StockPapi-TW-PreMarket`
- `StockPapi-FullBacktest`
- `StockPapi-US-Daily`
- `StockPapi-ReportUploadRecovery`（必要時）

設定 `StartWhenAvailable=True`、`WakeToRun=True`、`IgnoreNew` 與有限 retry。舊排程在 shadow 驗證前不刪除。

## 13. 安全與 rollout

- 不降低 manifest hash、size、uncompressed size、schema、path allowlist、reparse point、CSRF、session、GCS private policy 或 point-in-time checks。
- immutable object 使用 no-clobber；index 原子替換；latest 永遠最後。
- 外部內容只作資料，不作 template 或指令；HTML 由 Jinja autoescape，外部 URL 維持 HTTPS allowlist 與 noopener noreferrer。
- 先 local candidate shadow，通過 fixture/parity/dry-run 後再安裝新排程；沒有多日實測不得聲稱 production 已驗證。
- 本任務不直接修改 production GCS、LINE 或 Task Scheduler；外部 cutover 需另行明確授權。

## 14. 明確不做

- 不新增 Google／Email Login、付費牆或個人化買賣建議。
- 不在 Cloud Run request、webhook 或 import 階段訓練模型或跑報告。
- 不新增訊息佇列、資料庫、ORM、pickle/joblib 模型或 calendar 大型相依套件。
- 不把盤前 overlay 偽裝成新模型機率。
- 不因本次功能順便重構 application compatibility facade。

