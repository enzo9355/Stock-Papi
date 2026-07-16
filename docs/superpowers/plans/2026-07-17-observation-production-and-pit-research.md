# ABSORB Observation Production 與 PIT 模型研究實作計畫

> 執行原則：每一項行為修改都先建立 failing test，再做最小實作；每個階段完成後執行 focused verification，最後執行完整驗證與實際環境查核。

**Goal:** 可回滾地上線 Observation-only Production，並建立 fail-closed 的 PIT 模型研究管線；沒有模型 Gate 全過時，Prediction 永遠保持 research。

**Architecture:** 新增集中式 capability state 與純 Observation builder。正式 API／報告只讀 hash-verified Observation artifacts；現有 model candidate、preview 與 OOS diagnostics 保留在 research 邊界。發布採 immutable -> read-back -> index -> latest，mutable pointer 使用 generation precondition。

**Tech Stack:** Python 3.12、Flask、PowerShell、GCS、Cloud Run、unittest；研究端沿用現有 pandas／LightGBM 依賴，但不得進入 Cloud Run import path。

---

## Task 1：Prediction capability fail-closed

**Files**

- Create: `stock_papi/config/capabilities.py`
- Test: `tests/test_prediction_capability.py`
- Modify: `stock_papi/application.py`

**RED**

- 測試預設 mode 為 `research`。
- 測試所有 probability／ranking／strong action／performance flags 預設 false。
- 測試 research mode 即使 env flag 為 true 仍 fail-closed。
- 測試 preview prefix 空字串正規化為 `None`。

**GREEN**

- 實作 immutable `PredictionCapabilityState`。
- 實作單一 env parser 與 contradiction warnings。
- 在 application dependencies 中注入 capability state，不載入重型套件。

**Verify**

```powershell
python -m unittest tests.test_prediction_capability -v
```

## Task 2：純 Observation builder

**Files**

- Create: `stock_papi/batch/observation_products.py`
- Test: `tests/test_observation_products.py`
- Reuse: `reporting/schemas.py`
- Reuse: `reporting/source_loader.py`

**RED**

- 建立含極高／極低 `AI_P` 的兩份 fixture，實際行情相同；輸出必須完全相同。
- 驗證禁止 keys 不存在。
- 驗證市場、產業、股票事件與 ETF 觀察只由實際欄位決定。
- 驗證 NaN／Infinity、SAMPLE、低 coverage 與 stale source fail-closed。
- 驗證 deterministic ordering。

**GREEN**

- 實作純函式計算實際報酬、breadth、量能、籌碼與風險事件。
- 實作 dashboard v2 schema validator。
- 將 prediction capability 固定嵌入 artifact。

**Verify**

```powershell
python -m unittest tests.test_observation_products -v
```

## Task 3：Observation report metadata 與本機 candidate

**Files**

- Modify: `reporting/schemas.py`
- Create: `reporting/observation_v2.py`
- Create: `stock_papi/batch/observation_products_cli.py`
- Modify: `reporting/publisher.py`
- Test: `tests/test_observation_report_v2.py`
- Test: `tests/test_observation_candidate.py`

**RED**

- Observation report 允許空 `model_versions`，Prediction 舊文件仍要求非空。
- Observation report 必須有 `product_mode` 與 observation window。
- metadata／dashboard candidate immutable 且 hash verified。
- local publish 順序為 metadata objects -> index -> latest。
- 同 logical key 不同內容拒絕覆寫。

**GREEN**

- 新增 backward-compatible Observation metadata。
- 新增 post-close observation builder。
- 新增 candidate write/read/promote。
- 不修改舊 Prediction candidate 行為。

**Verify**

```powershell
python -m unittest tests.test_observation_report_v2 tests.test_observation_candidate -v
```

## Task 4：Dashboard repository 與 API 改讀 Observation

**Files**

- Modify: `stock_papi/repositories/dashboard_snapshots.py`
- Modify: `stock_papi/web/routes/market.py`
- Modify: `stock_papi/web/routes/dashboard.py`
- Modify: `stock_papi/web/route_registration.py`
- Test: `tests/test_dashboard_snapshot_repository.py`
- Test: `tests/test_market_routes.py`

**RED**

- repository 接受 v2 Observation，拒絕 prediction keys、hash mismatch、stale、oversize。
- API 有 verified snapshot 時不呼叫 `analyze`。
- snapshot 缺失時回 503，不 fallback 至 model。
- `/preview/report` 在 prefix 空白時 404。

**GREEN**

- production loader 只回傳 Observation v2。
- preview loader 繼續接受 research candidate。
- dashboard API 直接輸出 observation sections。
- route registration 依 preview capability gate preview route。

**Verify**

```powershell
python -m unittest tests.test_dashboard_snapshot_repository tests.test_market_routes -v
```

## Task 5：首頁、market-map 與個股 Observation UI

**Files**

- Modify: `templates/dashboard.html`
- Modify: `templates/market_map.html`
- Modify: `templates/stock_detail.html`
- Modify: `static/app.js`
- Create: `stock_papi/services/observation_view.py`
- Modify: `stock_papi/web/routes/market.py`
- Test: `tests/test_observation_views.py`
- Test: `tests/test_web_smoke.py`

**RED**

- rendered HTML 不含機率、direction score、top picks、推薦 action。
- 個股 serializer 移除 `prob`、`prob_h`、recommendation、model performance。
- JS 有 timeout、error state、`finally`。
- 各 dashboard section 可獨立顯示 unavailable。

**GREEN**

- 首頁與 market-map 改為市場／產業／事件 observation。
- 個股頁只傳實際技術與籌碼欄位。
- 顯示「AI 預測研究中」與資料日期。

**Verify**

```powershell
python -m unittest tests.test_observation_views tests.test_web_smoke -v
```

## Task 6：對話工具與 LINE Observation mode

**Files**

- Modify: `stock_papi/conversation/tools.py`
- Modify: `stock_papi/conversation/prompts.py`
- Modify: `stock_papi/integrations/line/presentation.py`
- Modify: `stock_papi/integrations/line/notifications.py`
- Modify: `stock_papi/integrations/line/flex.py`
- Test: `tests/test_absorb_conversation.py`
- Test: `tests/test_line_flow.py`
- Test: `tests/test_line_report_notifications.py`

**RED**

- research mode 不註冊 prediction history／market outlook／model performance。
- 回覆與通知不含上漲機率、偏多推薦、績效背書。
- 固定 LINE 指令、rich menu 與帳號綁定流程不變。

**GREEN**

- capability-aware tool registry。
- observation-only system prompt。
- post-close／pre-market observation notification。

**Verify**

```powershell
python -m unittest tests.test_absorb_conversation tests.test_line_flow tests.test_line_report_notifications -v
```

## Task 7：Post-close／pre-market 排程

**Files**

- Modify: `scripts/run_tw_post_close_pipeline.ps1`
- Modify: `scripts/run_tw_pre_market_pipeline.ps1`
- Modify: `scripts/invoke_pipeline_task.ps1`
- Modify: `stock_papi/batch/pre_market.py`
- Test: `tests/test_pipeline_scheduler.py`
- Test: `tests/test_pre_market_pipeline.py`

**RED**

- TW-PostClose 排程明確傳 `-PublishObservation`。
- 不傳 `-AllowDegradedBootstrap`。
- pre-market 只接受 `product_mode=observation` 的 post-close base。
- 隔夜來源全缺時仍可產生 `insufficient` observation overlay。

**GREEN**

- post-close script 改走 observation CLI。
- pre-market metadata 保留 observation mode 與 capability。
- Recovery 要求 report v2 + dashboard。

**Verify**

```powershell
python -m unittest tests.test_pipeline_scheduler tests.test_pre_market_pipeline -v
```

## Task 8：修正 uploader path traversal 與 conditional pointers

**Files**

- Modify: `scripts/upload_local_quant.ps1`
- Create: `scripts/capture_observation_lkg.ps1`
- Create: `scripts/rollback_observation.ps1`
- Test: `tests/test_local_quant_task.py`
- Create: `tests/test_observation_release_scripts.py`

**RED**

- 以臨時 allowlisted tree 重現 parent null，不得再拋 `ContainsKey(null)`。
- mutable index／latest 命令必須帶 generation-match。
- immutable 物件先上傳、read-back，才可更新 index／latest。
- LKG 可表示 pointer absent。
- rollback 只在 generation match 時恢復或刪除本次 pointer。
- 禁止 recursive delete／rsync／關閉 hash。

**GREEN**

- traversal 先檢查 `$null` 且 root 必須可達。
- 封裝 GCS generation read／conditional copy／conditional delete。
- capture 與 rollback artifact 寫入 allowlisted本機目錄。

**Verify**

```powershell
python -m unittest tests.test_local_quant_task tests.test_observation_release_scripts -v
```

```powershell
$null = [System.Management.Automation.Language.Parser]::ParseFile(
  'scripts\upload_local_quant.ps1', [ref]$null, [ref]$null
)
```

## Task 9：Observation Production deploy 與 cutover

**Files**

- Create: `scripts/deploy_observation_production.ps1`
- Modify: `scripts/verify_cutover.ps1`
- Modify: `scripts/manual_rollback.ps1`
- Test: `tests/test_observation_deploy_scripts.py`
- Modify: `docs/absorb-cutover-checklist.md`

**RED**

- deploy script 明確設定 research／observation env。
- 明確清空 preview prefix。
- 先 no-traffic deploy，再 smoke，再 traffic。
- 保存前一 revision／traffic／env／pointer state。
- verify script 檢查 response 禁止 prediction fields。

**GREEN**

- 實作 clean production deploy。
- 實作 observation-specific smoke 與 rollback。

**Verify**

```powershell
python -m unittest tests.test_observation_deploy_scripts -v
```

## Task 10：PIT availability audit 與 immutable dataset manifest

**Files**

- Create: `stock_papi/research/pit_dataset.py`
- Create: `stock_papi/research/pit_dataset_cli.py`
- Test: `tests/test_pit_dataset.py`

**RED**

- 每個 PIT requirement 有 `available|unavailable` 與證據。
- 缺資料不允許 dependent formal dataset。
- dataset manifest 綁 source SHA、code SHA、feature／target／split policy。
- immutable conflict fail-closed。

**GREEN**

- 掃描現有本機來源 metadata，不推測缺少的歷史欄位。
- 產生 availability audit。
- 只對可驗證資料建立 immutable dataset。

**Verify**

```powershell
python -m unittest tests.test_pit_dataset -v
```

## Task 11：獨立 baselines／challengers 與嚴格 Gates

**Files**

- Create: `stock_papi/research/challengers.py`
- Create: `stock_papi/research/evaluation.py`
- Create: `stock_papi/research/promotion.py`
- Create: `stock_papi/research/cli.py`
- Test: `tests/test_research_challengers.py`
- Test: `tests/test_research_evaluation.py`
- Test: `tests/test_research_promotion.py`

**RED**

- baseline 與 challenger 必須從 dataset features 重新 fit。
- 5-session purge／embargo 與 untouched holdout。
- classification、ranking、transaction、stability metrics。
- unavailable PIT dependency -> `NOT_RUN`。
- 任一 Gate fail -> prediction latest 不變。
- 全過只產生 validated candidate／preview receipt。

**GREEN**

- 先實作最小 baseline。
- 在環境依賴可用時實作兩個獨立 LightGBM challengers。
- promotion 只寫 immutable research artifact 與 no-traffic preview input。

**Verify**

```powershell
python -m unittest tests.test_research_challengers tests.test_research_evaluation tests.test_research_promotion -v
```

## Task 12：完整本機驗證

**Verify focused and full**

```powershell
python -m unittest discover -s tests -v
```

```powershell
git diff --check
```

- 執行 import cold-start。
- 搜尋 Production template／API 的 prediction keys 與禁用文案。
- 掃描 secrets／PII／path traversal。
- 執行 desktop 與 390px mobile visual QA。
- 執行 `agy` second review；若工具不可用，記錄 executable／auth／log 證據。

## Task 13：本機實際 Observation 發布

1. 以 `D:\AbsorbData` 最新 verified manifest 建立 observation candidate。
2. 驗證 candidate hashes、schema、dates、coverage、禁止 fields。
3. promote 至本機 `publish/dashboard/v1` 與 `publish/reports/v2`。
4. 執行 pre-market observation。
5. 執行 uploader，確認 GCS immutable、index、latest 與 generation。
6. 重新執行 recovery，驗證 idempotency。
7. 驗證 scheduled task 定義與 wrapper。

## Task 14：Cloud Run no-traffic、切流量與回滾演練

1. capture LKG。
2. push feature／integration commit。
3. deploy no-traffic production candidate。
4. smoke `/health`、`/`、`/api/dashboard`、`/reports`、`/market-map`、代表個股頁。
5. 檢查 env 沒有 preview prefix，prediction flags 全 false。
6. 通過全部 Observation Gates 後切 100% traffic。
7. 重新查 revision、traffic、HTTP、GCS pointers。
8. 以 dry-run／non-mutating verification 證明 rollback receipt 可用；只有實際失敗時執行 rollback。

## Task 15：執行 PIT 研究與最終報告

1. 執行 PIT availability audit。
2. 建立可用 dataset manifest。
3. 執行 baselines 與可執行 challengers。
4. 產生 classification／ranking／transaction／stability evidence。
5. 執行 promotion Gates。
6. 未全過時維持 research，不建立正式 prediction latest。
7. 全過時只建立 validated candidate 與 no-traffic preview，不切 Production。
8. 最終報告逐項回覆原需求 35 個證據項目，清楚標記 PASS／FAIL／BLOCKED／NOT_RUN，不使用「應該通過」。

