# Stock Papi 雙每日報告與背景回測 Implementation Plan

## 原則

- 不使用 subagent 或 superpowers 技能。
- 使用現有 `unittest`；每階段先寫會失敗的 focused test，再做最小實作。
- 每個 commit 只含該階段檔案，不納入既有未追蹤內容。
- 每階段完成後執行 focused tests；改動 trust boundary、route 或 scheduler 時再跑相應 regression。
- production GCS、LINE push 與 Task Scheduler cutover 不在未授權情況下執行。

## Phase 1：交易日、時間語意與 checkpoint 安全

**新增／修改**

- Create `stock_papi/batch/__init__.py`
- Create `stock_papi/batch/calendar.py`
- Create `stock_papi/batch/contracts.py`
- Create `tests/test_batch_calendar.py`
- Create `tests/test_batch_contracts.py`
- Modify `local_quant.py`
- Modify `tests/test_local_quant.py`

**TDD 驗收**

- 官方休市、週末、特殊開市與缺少年度 calendar fail closed。
- source/applicable/forecast start/end 全由 session calendar 計算。
- aware Taipei/UTC datetime；拒絕 naive datetime。
- daily checkpoint 固定 run_id、target_market_date、source manifest、model version、completed/failed symbols。
- target date 不同時封存舊 checkpoint並建立新 run，不默默續跑。
- TW artifact `as_of != target_market_date` 時拒絕加入正式 manifest。

**commit**：`feat: bind daily runs to verified trading dates`

## Phase 2：job lock、pipeline status 與背景 yield

**新增／修改**

- Create `stock_papi/batch/runtime.py`
- Create `stock_papi/batch/status.py`
- Create `stock_papi/batch/cli.py`
- Create `tests/test_batch_runtime.py`
- Create `tests/test_pipeline_status.py`
- Modify `local_quant.py`

**TDD 驗收**

- 六種 job 使用分離 lock/checkpoint/output namespace。
- owner token、stale archive、兩 process 不可寫同一 checkpoint。
- daily lock 不被 full-backtest lock 阻擋。
- full backtest 在 symbol/fold 邊界看見 daily lock後保存 checkpoint並 yield，之後可 resume。
- status stage allowlist、atomic current、append transcript、redaction、CLI summary。

**commit**：`feat: isolate batch jobs and pipeline status`

## Phase 3：Daily inference 與 full backtest 分離

**新增／修改**

- Modify `stock_papi/quant/model.py`
- Modify `stock_papi/application.py` compatibility wrapper only as needed
- Modify `local_quant.py`
- Create `stock_papi/batch/backtest_store.py`
- Create `tests/test_daily_inference.py`
- Create `tests/test_backtest_worker.py`

**TDD 驗收**

- `run_latest_inference()` 不建立 walk-forward folds。
- 相同輸入/model version 下 fast lane 機率與完整引擎最新機率 parity。
- daily report 只讀 promoted backtest latest，不等待 running candidate。
- candidate 綁 dataset hash/model version/cutoff；quality gate 前不可替換 latest。
- model/backtest version mismatch 降級 recommendation confidence 且禁止 strong action。
- background worker checkpoint/resume 與跨日固定 dataset snapshot。

**commit**：`feat: split daily inference from full backtest`

## Phase 4：Append-only prediction ledger

**新增／修改**

- Create `stock_papi/batch/prediction_ledger.py`
- Create `tests/test_prediction_ledger.py`

**TDD 驗收**

- market/industry/stock record schema、deterministic forecast id、immutable create。
- 相同內容重跑冪等；相同 id 不同內容拒絕。
- 五個實際 trading sessions 才 mature；calendar five days 不可取代。
- active 不納入 accuracy；settlement 只追加且保留錯誤預測。
- suspended/missing price 產生 invalid settlement，不改原 record。
- development projection 顯示機率變化、趨勢、理由變化、版本變化與最近成熟結果。

**commit**：`feat: add immutable prediction ledger`

## Phase 5：Report schema v2 與通用 publisher

**新增／修改**

- Modify `reporting/schemas.py`
- Modify `reporting/publisher.py`
- Modify `reporting/web.py`
- Modify `stock_papi/repositories/report_store.py`
- Modify `tests/test_daily_report_publish.py`
- Modify `tests/test_report_web.py`
- Create `tests/test_report_schema_v2.py`

**TDD 驗收**

- v1 reader compatibility 且安全映射為 post_close。
- v2 三種 report type；同一 applicable trading date 可有兩份 daily content。
- writer 只寫 v2；metadata immutable、index atomic、latest last。
- pre_market 無 PDF 仍可發布；PDF bytes 不公開。
- duplicate content 不增加 index；衝突內容拒絕覆寫。

**commit**：`feat: publish versioned multi-type reports`

## Phase 6：Post-close pipeline

**新增／修改**

- Create `stock_papi/batch/post_close.py`
- Create `scripts/run_tw_post_close_pipeline.ps1`
- Create `tests/test_post_close_pipeline.py`
- Modify `reporting/cli.py`

**TDD 驗收**

- data ready success、bounded retry、deadline fail closed、target mismatch。
- partial failure threshold、inference、settlement、aggregation、render、publish、upload callback、remote verify callback、notify callback。
- stage crash recovery、同 input 冪等重跑、duplicate notification prevention。
- previous latest 在任何 validation/publish 失敗時保持不變。
- `--dry-run` 不發布、不通知、不使用 sample。

**commit**：`feat: add fail-closed post-close pipeline`

## Phase 7：Pre-market overlay pipeline

**新增／修改**

- Create `stock_papi/batch/pre_market.py`
- Create `stock_papi/integrations/market_data/overnight.py`
- Create `scripts/run_tw_pre_market_pipeline.ps1`
- Create `tests/test_pre_market_pipeline.py`

**TDD 驗收**

- valid base、missing/invalid base、source success/partial/stale/all unavailable。
- 每個來源 timeout、size、schema、timestamp、freshness、attribution。
- overlay allowlist，且 core probability/model evidence bytes 不變。
- all unavailable → 資料不足且維持盤後判斷。
- HTML/JSON 發布、冪等通知、無 PDF。

**commit**：`feat: add pre-market risk overlay`

## Phase 8：Weekly model report

**新增／修改**

- Create `stock_papi/batch/weekly_model.py`
- Create `tests/test_weekly_model_report.py`
- Modify `reporting/public_report.py`
- Modify PDF generator only if weekly PDF is retained

**TDD 驗收**

- 只接受 promoted backtest + matured ledger。
- accuracy/win rate/high-score realized rate/probability 分欄。
- Brier/calibration/expectancy/profit factor/MDD/streak/year/regime/cost/drift/data quality。
- 無新 backtest 時不生成假的週報。

**commit**：`feat: add weekly model validation report`

## Phase 9：Web routes、首頁與 details

**新增／修改**

- Modify `stock_papi/web/routes/reports.py`
- Modify `stock_papi/web/routes/dashboard.py`
- Modify `stock_papi/web/route_registration.py`
- Modify `templates/dashboard.html`
- Modify `templates/reports.html`
- Modify `templates/report_detail.html`
- Create `templates/report_trading_day.html`
- Modify `templates/stock_detail.html`
- Modify `static/app.css`／`static/app.js` only when needed
- Modify `tests/test_route_inventory.py`
- Modify `tests/test_report_web.py`
- Modify `tests/test_web_product.py`

**TDD 驗收**

- 首頁兩卡、pending compact state、休市、partial/stale/unavailable。
- 報告依 applicable trading date 分組，daily/weekly 分類。
- 新 routes、舊 route compatibility、public cache 無 user data。
- detail 的時間語意、AI prediction development、overlay 分離。
- mobile/keyboard/aria/no duplicate IDs/no color-only/no `AI 勝率`。

**commit**：`feat: show post-close and pre-market reports`

## Phase 10：LINE notification receipt

**新增／修改**

- Create `stock_papi/batch/notifications.py`
- Modify `stock_papi/integrations/line/notifications.py` only for shared formatter if useful
- Create `tests/test_report_notifications.py`

**TDD 驗收**

- content hash notification key、pending/sent/failed receipt、bounded retry。
- post-close/pre-market formatter，不含 token、local path、bucket internals 或個資。
- publish success + LINE failure 不回滾 report。
- 管理員與一般 broadcast 狀態分開。

**commit**：`feat: make report notifications idempotent`

## Phase 11：Scheduler、uploader、backfill 與 migration

**新增／修改**

- Create `scripts/install_pipeline_tasks.ps1`
- Modify `scripts/upload_local_quant.ps1`
- Create `reporting/backfill.py`
- Create `tests/test_pipeline_scheduler.py`
- Create `tests/test_report_backfill.py`
- Modify `.env.example`

**TDD 驗收**

- separate TW post-close/pre-market/full-backtest/US task。
- StartWhenAvailable/WakeToRun/retry/IgnoreNew/limited principal/no secret args。
- uploader 接受 v1/v2，驗證全部 immutable artifact，index 後 latest。
- backfill 預設 dry-run，指定 manifest+hash+model，拒絕未驗證／未來／衝突內容。
- 2026-07-13/14 只有 verified manifest 存在才輸出可執行指令，不自動發布 production。

**commit**：`feat: add safe pipeline scheduling and backfill`

## Phase 12：文件與最終驗證

**修改**

- `README.md`
- `docs/architecture_overview.md`
- `docs/deployment_guide.md`
- `docs/runbook_incident_response.md`
- `.env.example`

**驗證命令**

1. focused tests for every phase
2. `python -m unittest discover -s tests -v`
3. `python -m compileall -q stock_papi reporting backtest`
4. `python -m py_compile app.py line_state.py local_quant.py market_insights.py`
5. `node --check static/app.js`
6. PowerShell parser check for changed scripts
7. `git diff --check`
8. route inventory
9. cold-start heavy import check
10. secret/path/header scan
11. v1/v2 schema and private PDF regression
12. post-close/pre-market/backfill dry-run fixtures
13. full-backtest yield/resume, duplicate publish, crash recovery, target mismatch, maturity simulations
14. desktop/mobile HTML render and empty/partial/stale states
15. Task Scheduler `-WhatIf`
16. `agy` second review after local verification；若 auth/log 環境阻擋，只記錄限制

**commit**：`docs: document dual daily report operations`

## 外部 cutover（完成程式後仍需明確授權）

1. 新 tasks `-WhatIf`。
2. 安裝但使用 shadow/local candidate，不替換 production latest。
3. 與舊流程比較數日；記錄日期、manifest hash、機率 parity、報告差異與耗時。
4. 驗證 GCS candidate read-back、LINE 測試 recipient 與 Cloud Run candidate revision。
5. 才停用舊 `StockPapi-LocalQuant`／09:35 uploader，保留 rollback definition。
6. rollback 只切回舊 task 與上一份 verified latest，不刪 immutable artifacts。

