# ABSORB Observation Production 與 PIT 模型研究設計

日期：2026-07-17  
分支：`codex/absorb-observation-production`  
基準 SHA：`fa110a0284803cc388b3cf43a46018b2183314fd`

## 1. 目標

本次工作分成兩條互不混用的產品線：

1. **Observation Production**
   - 使用已驗證的實際市場資料，恢復每日 Dashboard、盤後觀察、盤前風險更新、Web、LINE 與對話工具。
   - 不依賴模型基準、模型校準或回測 Gate。
   - 不顯示機率、模型分數、預測排名、買賣建議或績效背書。
   - 通過 Observation Production Gates 後，可依授權切換正式流量。

2. **Prediction Research**
   - 模型維持 fail-closed。
   - 只有 point-in-time 資料、獨立 challenger、walk-forward／purged split／embargo、排名、校準、交易與穩定性 Gates 全部通過，才可產生 validated candidate 與 no-traffic preview。
   - 即使通過，也不得自動切換 Production 預測流量。

## 2. 已驗證現況與根因

### 2.1 正式環境

- Cloud Run 正式流量目前為 `line-stock-bot-00097-vam`，100% traffic。
- 正式 revision commit label 為 `cc80f53006a595773f4012c3162813eb35ae4ecd`。
- 最新 preview revision 為 `line-stock-bot-00102-map`，0% traffic，含 `ABSORB_PREVIEW_CANDIDATE_PREFIX`。
- 正式 revision 沒有 preview prefix。
- GCS 沒有 `dashboard/v1/latest-TW.json`、`reports/v2/index-TW.json`、`reports/v2/latest-TW-post_close.json` 或 `reports/v2/latest-TW-pre_market.json`。
- 正式 `/api/dashboard` 因此改走 request-time `analyze("TAIEX")` fallback；雖回傳 HTTP 200，但仍包含未驗證的 `prob` 與推薦語言，且 heatmap 為空。

### 2.2 Windows 每日流程

- 本機 quant 最新資料已到 2026-07-15，coverage 約 99.71%。
- `TW-PostClose` 排程呼叫 `run_tw_post_close_pipeline.ps1` 時沒有任何參數。
- 該腳本只有在 `-AllowDegradedBootstrap` 時才允許無 validated baseline；只有在 `-Publish` 時才會 promote、upload 與 notify。
- 因此現行排程同時缺少「允許建立候選」與「正式發布」兩個條件，必然無法完成日報上線。
- 現有 degraded bootstrap candidate 仍直接取用 `AI_P`，並產生 `prob`、`score`、`direction_score`、model-based heatmap 與 top picks。這不是 Observation，只是改名後的 Prediction。
- `TW-PreMarket` 因沒有已發布 post-close base 而 fail-closed。
- `ReportUploadRecovery` 的 allowlist parent traversal 在 parent 變成空值時仍呼叫 `ContainsKey`，造成 null key 例外。

### 2.3 根因結論

真正根因不是單一 UI bug，而是：

1. Observation 與 Prediction 沒有獨立資料契約。
2. 日報排程把「模型可否發布」與「實際市場觀察可否發布」綁在同一條 pipeline。
3. Production API 在快照不存在時執行 request-time 模型分析，破壞 fail-closed 與 cold-start 邊界。
4. mutable pointers 沒有完整的 generation precondition、LKG／previous 記錄與可驗證 rollback。

## 3. 現有五個 commit 的分類

### 3.1 可保留的 Production 平台能力

- content-addressed daily candidate 與 hash read-back。
- GCS path allowlist、size／SHA-256／uncompressed size 驗證。
- preview 部署的 no-traffic、retry、read-back 與 build context 排除。
- `model_evidence` 的 fail-closed sanitization，僅作 Prediction 防線。

### 3.2 Preview-only

- `ABSORB_PREVIEW_CANDIDATE_PREFIX`。
- `/preview/report` 與 preview candidate repository。
- `scripts/deploy_preview.ps1`。
- preview route 在 prefix 為空時必須 404，且不得出現在正式導覽。

### 3.3 Research-only

- `stock_papi/batch/oos_diagnostics.py` 及其 CLI／測試。
- 現有 OOS diagnostics 只能當研究診斷，不能代表已完成獨立 retraining 或正式 challenger。

### 3.4 不得作為 Production 資料

- 任一 `initial_backtest_bootstrap` candidate。
- 任一含 `AI_P`、`prob`、`direction_score`、模型排名或推薦 action 的 dashboard／report candidate。
- 任一 preview prefix 下的物件。

## 4. 能力狀態

新增集中式 `PredictionCapabilityState`，唯一決定預測能力是否可露出：

```text
mode: research | validated_preview | production
observation_enabled: bool
probability_allowed: bool
ranking_allowed: bool
strong_action_allowed: bool
performance_endorsement_allowed: bool
preview_candidate_prefix: str | None
```

Production 預設：

```text
ABSORB_PREDICTION_MODE=research
ABSORB_OBSERVATION_ENABLED=true
ABSORB_PREDICTION_PROBABILITY_ENABLED=false
ABSORB_PREDICTION_RANKING_ENABLED=false
ABSORB_PREDICTION_STRONG_ACTIONS_ENABLED=false
ABSORB_PREDICTION_PERFORMANCE_ENDORSEMENT_ENABLED=false
ABSORB_PREVIEW_CANDIDATE_PREFIX=
```

矛盾設定必須 fail-closed。例如 `mode=research` 但 probability flag 為 true 時，狀態仍回傳 false，並標記 configuration warning；不得因單一環境變數而解鎖預測。

## 5. Observation 資料契約

### 5.1 原則

- 只從已驗證的 immutable quant manifest 與其列出的股票物件建立。
- 計算只使用實際欄位，例如 `Close`、歷史 Close、`MA20`、`MA60`、`RSI`、`VOL_RATIO`、`INST_NET_RATIO`、`ForeignNet`、market return、data warning。
- 不讀取 `AI_P`。
- 不依賴 backtest、baseline 或 recommendation engine。
- 所有排序僅是確定性展示排序，例如「產業 5 日實際相對報酬」或「異常事件嚴重度」，欄位名稱不得使用 prediction rank／score。

### 5.2 Dashboard v2

正式 dashboard 使用：

```json
{
  "schema_version": 2,
  "kind": "absorb-observation-dashboard",
  "product_mode": "observation",
  "market": "TW",
  "observation_as_of": "YYYY-MM-DD",
  "generated_at": "...Z",
  "source_manifest": "quant/v1/manifests/...",
  "source_manifest_sha256": "...",
  "prediction_capability": {
    "mode": "research",
    "probability_allowed": false,
    "ranking_allowed": false,
    "strong_action_allowed": false,
    "performance_endorsement_allowed": false
  },
  "market_observation": {},
  "industry_observations": [],
  "heatmap": [],
  "stock_events": [],
  "etf_observations": [],
  "daily_focus": [],
  "data_quality": {},
  "gates": {}
}
```

禁止欄位：

- `prob`
- `probability`
- `direction_score`
- `score`（若語意可被誤認為模型排名）
- `recommendation`
- `top_picks`
- `model_version`
- `backtest_version`
- `performance`

### 5.3 Observation 指標

市場：

- 1／5／20／60 日實際報酬。
- 上漲／下跌家數。
- 站上 MA20／MA60 比率。
- 20 日新高／新低家數。
- 量能比中位數。
- 已實現波動。
- 資料警示率與來源新鮮度。

產業：

- 1／5／20 日實際報酬。
- 相對市場 5／20 日報酬。
- advancing ratio。
- MA20 breadth。
- 量能比。
- 機構淨流向比。
- coverage 與有效樣本數。
- deterministic phase：`strengthening`、`strong`、`weakening`、`weak`、`insufficient`。

股票事件：

- 單日漲跌幅異常。
- 量能異常。
- RSI 過熱／超賣。
- 突破或跌破 MA20／MA60。
- 20 日新高／新低。
- 外資近五日大幅買超／賣超。
- 資料品質警示。

ETF：

- 僅以 instrument type 與實際報酬／均線／量能產生觀察。
- 不混入一般股票異常事件排名。

### 5.4 報告 v2 相容策略

- `schema_version=2` 保持可讀舊資料。
- Observation 新 metadata 新增：
  - `product_mode="observation"`
  - `observation_start_date`
  - `observation_end_date`
  - `prediction_capability`
- 舊的 `forecast_start_date`／`forecast_end_date` 保留為相容欄位，但新 Observation 文件中等同 applicable observation window，不得在 UI 顯示為預測期間。
- `model_versions` 在 Observation 文件允許 `{}`；舊 Prediction 文件仍維持非空驗證。
- post-close title 改為「盤後市場觀察」；pre-market title 改為「盤前風險更新」。
- `content` 只能引用 Observation dashboard 的實際資料子集與隔夜 overlay。

## 6. 服務與 UI 邊界

### 6.1 API

- `/api/dashboard` 先讀 hash-verified Observation snapshot。
- 缺少或驗證失敗時回傳 503 與明確 unavailable 狀態，不得呼叫 `analyze("TAIEX")`。
- Snapshot 各區段獨立，單一區段資料不足不得破壞其他區段。
- API 回傳 `prediction_capability` 與固定文字「AI 預測研究中」。

### 6.2 首頁與市場地圖

- 首頁顯示市場實況、產業實際強弱、風險事件、ETF 觀察、資料日期與來源品質。
- heatmap 使用產業實際相對 5 日報酬或 breadth，不使用機率。
- 不顯示「熱門推薦」、「Top Picks」、「勝率」、「機率」。
- JS fetch 必須有 timeout、錯誤態與 `finally`，避免 loading 永久卡住。

### 6.3 個股頁

- Prediction research 模式下，`analyze()` 結果必須經 Observation serializer，只留下實際價格、均線、RSI、量能、籌碼、歷史圖與風險事件。
- 不傳 `AI_P` chart、機率、推薦 action 或模型績效至 template。

### 6.4 對話與 LINE

- research 模式隱藏 prediction history、market outlook、model performance 等預測工具。
- 保留查價、技術觀察、產業實際強弱、報告、關注清單與提醒。
- 固定顯示「AI 預測研究中；目前提供市場觀察，不提供上漲機率或買賣建議。」
- LINE 通知使用盤後觀察／盤前風險更新摘要，不使用偏多、優先關注、勝率或機率措辭。

## 7. 本機發布與排程

### 7.1 Post-close

新增 Observation builder／CLI，流程為：

1. calendar Gate。
2. 讀取明確 quant manifest path + SHA。
3. hash／size／schema／finite JSON／sample-data Gates。
4. 建立 Observation dashboard 與 post-close report candidate。
5. candidate read-back。
6. 明確 `-PublishObservation` 時才 promote。
7. immutable objects／metadata。
8. local index。
9. local latest last。
10. GCS immutable upload。
11. GCS read-back。
12. GCS index conditional update。
13. GCS latest conditional update last。
14. notification。

排程的 `TW-PostClose` 需明確傳入 `-PublishObservation`；不再傳入 `-AllowDegradedBootstrap`，因 Observation 不需要 baseline。

### 7.2 Pre-market

- 只讀已驗證的 Observation post-close metadata。
- 隔夜來源可用時建立 risk-on／risk-off／mixed overlay；不可用時標示資料不足並維持盤後觀察。
- 不更動 post-close core。
- immutable metadata -> index -> latest。

### 7.3 Recovery

- 修正 parent traversal null bug。
- `ReportUploadRecovery` 要求 report v2 與 dashboard。
- Recovery 只能重送已驗證本機成品，不重新計算模型或觀察。

## 8. GCS 原子性與回滾

### 8.1 發布前保存

保存：

- Cloud Run service YAML。
- Production revision 與 traffic。
- Production env。
- `quant/v1/latest-TW.json` generation 與內容。
- `dashboard/v1/latest-TW.json` generation 與內容；不存在時明確記錄 `absent`。
- `reports/v2/index-TW.json` 及各 latest generation／內容；不存在時記錄 `absent`。

### 8.2 Conditional mutation

- immutable object 使用 no-clobber。
- mutable pointer 使用 generation-match。
- 原先不存在時使用 generation `0`。
- mutation 後立即 read-back，比對 SHA、identity、path、size 與 generation。
- 任一 read-back 不一致即停止，不更新下一個 pointer。

### 8.3 Rollback

- Cloud Run traffic 切回前一 revision。
- 已存在的 previous pointer 依其內容與 generation 條件恢復。
- 原本不存在的 pointer，rollback 時只刪除本次建立且 generation 完全匹配的物件。
- immutable objects 保留。
- 不改動 backtest latest。

## 9. Observation Production Gates

全部通過才可正式切流量：

1. source manifest path allowlist。
2. source manifest SHA-256。
3. source object SHA-256／size／uncompressed size。
4. source schema。
5. finite JSON。
6. 非 SAMPLE。
7. coverage／failure-rate。
8. observation builder 不讀 `AI_P`。
9. dashboard 禁止預測欄位。
10. report 禁止預測語言與欄位。
11. prediction capability 預設 research 且全部 false。
12. dashboard immutable object read-back。
13. report immutable metadata read-back。
14. index before latest。
15. generation precondition。
16. web desktop + 390px mobile visual QA。
17. `/health`、首頁、dashboard API、reports、stock、market-map、LINE smoke。

## 10. PIT 模型研究

### 10.1 Dataset availability audit

先建立不可變的 PIT audit artifact，逐項檢查：

- 歷史產業成分 membership。
- shares outstanding。
- market cap。
- 可交易 universe。
- listing／delisting。
- suspension。
- corporate actions。
- source timestamp／revision。
- manifest path／SHA。

缺少欄位必須記為 `unavailable`，不得補假資料。依賴缺失欄位的正式 challenger 必須 `NOT_RUN`。

### 10.2 Dataset binding

可用資料建立 immutable dataset manifest：

- dataset SHA-256。
- source manifests 與 SHA。
- code SHA。
- feature schema version。
- target definition。
- PIT policy。
- split policy。

### 10.3 Challengers

必須是獨立訓練，不得重標舊 `AI_P`：

- Baseline：常數先驗、簡單 momentum、簡單 mean-reversion。
- LightGBM challenger A：5-session direction classification。
- LightGBM challenger B：5-session cross-sectional ranking。
- 若 PIT industry／universe 不完整，相關產業或橫截面 challenger 標示 `NOT_RUN`。

### 10.4 評估

- expanding walk-forward。
- purged split。
- 5-session embargo。
- untouched final holdout。
- classification：Brier、log loss、AUC、calibration slope／intercept、ECE。
- ranking：Spearman IC、top-decile spread、turnover。
- transaction：費用、滑價、容量敏感度。
- stability：月份、產業、市況、樣本數與 bootstrap CI。

### 10.5 Promotion Gates

Probability candidate 必須同時通過：

- leakage/PIT。
- schema/security。
- coverage。
- Brier 與 calibration 門檻。
- holdout 不劣於 baseline。
- transaction-aware utility。
- stability。

Ranking-only candidate 必須同時通過：

- leakage/PIT。
- schema/security。
- ranking IC／spread。
- turnover／cost。
- stability。

任一 Gate 未通過：

- prediction mode 保持 `research`。
- 不更新 prediction latest。
- 不顯示機率、排名、推薦。
- 研究報告記錄 `BLOCKED`／`FAIL`／`NOT_RUN` 與證據。

## 11. 測試與驗證

- 新功能先寫 failing test。
- pure builder 單元測試需明確放入極高 `AI_P`，驗證輸出完全不變且不含 prediction keys。
- repository 測試 hash、size、age、schema、v1 backward compatibility。
- route 測試驗證 snapshot 缺失時 503 且不呼叫 `analyze`。
- PowerShell parser 與 focused test 驗證 parent traversal。
- full Python suite。
- import cold-start test。
- secret／PII／path traversal／XSS／external-link sanitization。
- desktop 與 390px mobile screenshot。
- no-traffic Cloud Run smoke。
- Production cutover 後重新查 revision、traffic、env、GCS pointers 與 HTTP。
- 修改完成且本機驗證後執行 `agy` second review；工具不可用時保留環境證據。

## 12. 非目標

- 不修改 LightGBM 正式模型公式。
- 不降低任何既有 Gate。
- 不在 Cloud Run request、LINE webhook 或 Flask import 執行重型分析。
- 不把 research artifact 混入 Production dashboard／report。
- 不刪除 immutable objects。
- 不自動啟用 Prediction Production。

## 13. 自我審查結論

- Observation 與 Prediction 在 schema、builder、route、UI、排程與發布上都有獨立邊界。
- 正式恢復不再被 validated model baseline 阻擋，但資料與發布安全 Gate 仍 fail-closed。
- 預測能力沒有因 Observation 上線而被間接解鎖。
- 現有 preview／research 工作可保留，且不需回退五個既有 commit。
- 最小安全路徑是先完成 capability state、Observation builder、repository／route、local publish，再處理 UI／LINE、conditional GCS、deploy 與 PIT research。

