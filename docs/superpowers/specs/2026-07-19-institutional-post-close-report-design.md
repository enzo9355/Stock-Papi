# ABSORB 機構級盤後研究報告設計規格

日期：2026-07-19  
狀態：已獲產品方向批准，待實作計畫  
適用專案：`enzo9355/absorb`

## 1. 目的

ABSORB 的盤前與盤後報告應是兩個不同產品：

- **盤前風險更新**：1–3 頁，聚焦隔夜變化、相對盤後基準的風險修正，以及開盤前觀察條件。
- **盤後機構級研究報告**：正常交易日 25–35 頁，重大事件日可延伸至約 40 頁，提供完整市場、產業、個股、ETF、量化回歸、模型驗證、回測、資料治理與下一交易日研究框架。

目前 `report_observation.html` 僅提供摘要層級內容，適合作為盤後報告前幾頁或網頁摘要，但不足以作為正式研究產品。現有 `reporting/pdf_generator.py` 具備 ReportLab、A4、多頁 PDF、中文文字抽取、大小限制、SHA 與原子替換等能力，應重用並升級，而不是另建低品質 PDF 管線。

本規格要求建立一份 Canonical Professional Report，讓以下輸出共享相同資料與結論：

1. 網頁完整版 HTML
2. 機構級 PDF
3. LINE 摘要
4. Gemini 自然語言問答資料來源

## 2. 核心產品原則

### 2.1 雙層閱讀

前 2–3 頁必須讓非專業使用者快速掌握：

- 今天市場發生什麼
- 目前風險狀態
- 最強與最弱產業
- 最重要風險
- 下一交易日觀察條件

後續章節提供可稽核的專業證據：

- 市場廣度
- 產業輪動
- 個股事件
- 解釋型回歸
- LightGBM 模型資訊
- OOS 驗證
- Calibration
- 策略回測
- 資料品質
- 方法論與限制

### 2.2 Observation 與 Prediction 分離

正式報告必須清楚區分：

1. **系統觀測事實**：價格、報酬、均線、成交量、廣度、籌碼、產業相對強弱。
2. **規則式風險判斷**：例如提高防守、短線乖離偏高。
3. **量化模型輸出**：僅限 Artifact 中存在且通過對應 Gate 的輸出。
4. **Gemini 解讀**：根據前三者整理的文字分析。

不得將 Observation Score 稱為預測機率，也不得將 SHAP、Feature Importance 稱為迴歸係數或統計顯著性。

### 2.3 模型失敗結果必須公開呈現

目前模型未通過 Ranking、Calibration、Quality 與 Transaction Value Gates。正式報告不得隱藏或美化此結果，應顯示：

- Accuracy 低於 Majority Baseline
- Holdout ROC-AUC 接近無訊號
- Brier Skill 為負
- Calibration 雖改善但未勝過 Climatology
- 成本後交易價值未獲證明
- Promotion 維持 BLOCKED

報告可提供 AI 參考建議，但不得描述為已驗證的上漲機率或穩定 Alpha。

### 2.4 同一 Canonical Schema

HTML、PDF、LINE 與 Gemini 不得各自重新計算或使用不同結論。所有輸出必須由同一份 Canonical Professional Report Schema 派生。

## 3. 產品命名

盤後正式名稱：

> **ABSORB 台股市場、產業與量化研究日報**

盤前正式名稱：

> **ABSORB 盤前風險更新**

盤後 Report Type 可維持 `post_close`，但需加入：

- `product_tier = institutional`
- `product_mode = observation_with_research`
- `report_schema_version`

盤前 Report Type 維持 `pre_market`，並標記：

- `product_tier = summary`
- `product_mode = overnight_update`

## 4. 目標篇幅

| 章節 | 頁數範圍 |
|---|---:|
| 決策摘要 | 2–3 |
| 市場與風險 | 3–4 |
| 資金與籌碼 | 2–3 |
| 產業分析 | 5–7 |
| 個股與 ETF | 4–6 |
| 量化回歸與模型 | 4–6 |
| 驗證與回測 | 4–6 |
| 下一交易日研究框架 | 1–2 |
| 方法與資料治理 | 2–4 |
| **正常總計** | **25–35** |

重大市場事件日可延伸至約 40 頁。頁數不是硬性填充目標；資料不足時應顯示 unavailable，而不是以重複內容灌頁數。

## 5. Canonical Professional Report Schema

建立 Typed Schema，例如：

```python
ProfessionalPostCloseReport(
    identity,
    executive_summary,
    key_events,
    market,
    capital_flows,
    industries,
    securities,
    quantitative_research,
    validation,
    next_session,
    governance,
    ai_reference,
)
```

### 5.1 `identity`

- `schema_version`
- `report_type`
- `product_tier`
- `product_mode`
- `market`
- `source_market_date`
- `applicable_trading_date`
- `published_at`
- `generated_at`
- `source_manifest`
- `source_manifest_sha256`
- `content_sha256`
- `report_id`
- `generator_version`
- `code_commit_sha`
- `model_version`
- `feature_schema_version`
- `recommendation_policy_version`

### 5.2 `executive_summary`

- `market_state`
- `one_line_conclusion`
- `supporting_evidence`
- `opposing_evidence`
- `largest_risk`
- `strongest_industries`
- `weakest_industries`
- `next_session_watch_conditions`
- `ai_reference_summary`

### 5.3 `key_events`

最多 5–8 項，每項包含：

- `headline`
- `description`
- `metric_name`
- `metric_value`
- `comparison_basis`
- `historical_percentile`
- `why_it_matters`
- `affected_entities`
- `data_as_of`
- `source`

### 5.4 `market`

- 加權指數與櫃買指數
- 1／5／20／60 日報酬
- MA20／MA60 距離與斜率
- RSI
- 成交量與量比
- 20／60 日實現波動率
- 近期高低點距離
- 市場 Regime
- 上漲、下跌、平盤家數
- 上漲比例
- 站上 MA20／MA60 比例
- 新高／新低家數
- 個股中位數報酬
- 市值加權報酬
- 上市／櫃買差異
- 歷史分位數

### 5.5 `capital_flows`

- 外資、投信、自營商 1／5／20 日累計
- 法人買賣超集中產業
- 權值股貢獻
- 前十大成交占比
- 市場集中度
- 大型股與中小型股差異

### 5.6 `industries`

每個產業包含：

- `industry_id`
- `name`
- `component_count`
- `available_count`
- `coverage`
- 1／5／20／60 日報酬
- 相對大盤報酬
- 上漲參與度
- 站上 MA20／MA60 比例
- 成交量比
- 波動率
- 法人流向
- 集中度
- 領漲與拖累公司
- 短期強弱
- 中期趨勢
- 廣度品質
- 量能確認
- 籌碼支持
- 風險程度
- 輪動象限
- 連續改善／惡化天數
- 支持因素
- 反對因素
- 失效條件

### 5.7 `securities`

分成：

- `positive_observations`
- `risk_observations`
- `high_anomaly_observations`
- `etf_observations`

每檔股票至少包含：

- 代碼與名稱
- 產業
- 收盤價
- 1／5／20 日報酬
- 相對大盤報酬
- 相對產業報酬
- RSI
- MA20／MA60 乖離
- 量比
- 波動率
- 法人流向
- 觸發事件
- 支持證據
- 反對證據
- 失效條件
- 風險提示
- AI 參考建議

ETF 必須使用 ETF 專屬欄位，不得硬套個股法人或產業欄位。

### 5.8 `quantitative_research`

包含兩種模型：

#### 解釋型回歸

至少支援一個明確版本化的解釋模型，例如：

```text
產業或個股相對報酬
= 市場因子
+ 動能因子
+ 波動因子
+ 成交量因子
+ 籌碼因子
+ 產業固定效果
+ 日期固定效果
```

輸出：

- 係數
- Robust／Clustered Standard Error
- t 值
- p 值
- 95% 信賴區間
- 樣本數
- R²
- Adjusted R²
- 固定效果
- 標準誤方法
- 樣本期間
- 模型限制

報告必須聲明：統計關聯不等於因果關係，也不保證交易獲利。

#### 預測模型

- Target
- Horizon
- Universe
- Feature Schema
- Training Window
- Validation Window
- Final Holdout
- Feature Count
- Missingness
- Hyperparameter Version
- Model SHA
- Feature Importance
- Mean Absolute SHAP
- 正向／負向貢獻
- 資料漂移狀態

### 5.9 `validation`

- Training／Validation／Holdout 日期
- 樣本數
- ROC-AUC
- PR-AUC
- Accuracy
- Majority Baseline
- Brier
- Climatology Brier
- Log Loss
- ECE
- Rank IC
- ICIR
- Calibration Curve
- Reliability Table
- Prediction Histogram
- Strategy Definition
- Benchmark
- Transaction Costs
- Tax
- Slippage
- Turnover
- Cumulative Return
- Annualized Return
- Max Drawdown
- Sharpe
- Sortino
- Win Rate
- Profit Factor
- Exposure
- Cash Ratio
- Year／Regime／Industry／Liquidity／Market-cap breakdown
- Bootstrap Confidence Intervals

Gate 狀態：

- Point-in-Time
- Leakage
- Schema
- Security
- Ranking
- Calibration
- Quality
- Transaction Value
- Promotion

### 5.10 `next_session`

- 正向情境
- 中性情境
- 負向情境
- 關鍵觀察清單
- 各條件對原判斷的影響

### 5.11 `governance`

- Universe
- 有效標的
- 失敗標的
- Coverage
- 缺值率
- Stale Data
- Source Status
- Manifest SHA
- Report SHA
- 各來源截止時間
- 失敗股票清單
- Point-in-Time 方法
- Trading Calendar
- Corporate Actions
- 報酬計算
- 產業分類
- ETF 分離
- 缺值處理
- 異常值處理
- 回歸方法
- 模型方法
- Calibration 方法
- 回測方法
- 成本假設
- 限制與免責聲明

### 5.12 `ai_reference`

- `status`
- `provider`
- `generated_at`
- `conclusion`
- `reference_action`
- `supporting_evidence`
- `opposing_evidence`
- `invalidation_conditions`
- `data_as_of`
- `model_reference_value`
- `model_reference_status`
- `disclaimer`

Gemini 只能使用 Canonical Schema 中存在的資料，不得自行創造數字。

## 6. PDF 章節設計

### 6.1 決策摘要

1. 封面與報告身份
2. Executive Summary
3. 今日五大重點

### 6.2 市場總體與風險

4. 大盤價格與趨勢
5. 市場廣度
6. 市場風險儀表板

### 6.3 資金與籌碼

7. 法人交易
8. 市場集中度

### 6.4 產業輪動與排名

9. 產業綜合排名
10. 產業輪動圖
11. 強勢產業深度分析
12. 弱勢與風險產業

### 6.5 個股與 ETF

13. 個股異常事件總覽
14. 深度個股案例
15. ETF 觀察

### 6.6 量化回歸與模型解釋

16. 解釋型回歸
17. 預測模型說明
18. Feature Importance 與 SHAP
19. AI 模型參考建議

### 6.7 模型驗證與策略回測

20. OOS 模型驗證
21. Calibration
22. 策略回測
23. 穩健性與分層

### 6.8 下一交易日研究框架

24. 正向／中性／負向情境
25. 關鍵觀察清單

### 6.9 資料治理與方法論

26. 資料品質
27. 方法論
28. 限制與免責聲明

## 7. 網頁完整版

盤後 canonical route：

```text
/reports/<source_market_date>/post-close
```

網頁版必須：

- 使用同一 Canonical Professional Report Schema
- 前段完整顯示摘要與核心圖表
- 專業章節可折疊，但預設不得全部隱藏
- 支援章節目錄
- 支援 Anchor Navigation
- 支援列印樣式
- 支援「下載完整 PDF」
- 手機仍可閱讀
- 不直接把 Raw Metadata 傳給 Jinja

## 8. PDF 下載

建立 canonical download route：

```text
/reports/<source_market_date>/post-close/download
```

或：

```text
/reports/<source_market_date>/post-close.pdf
```

安全要求：

- GCS Bucket 維持 Private
- Flask 驗證 Metadata、Object Allowlist、SHA、Size 後串流，或使用短效 Signed URL
- `Content-Type: application/pdf`
- `Content-Disposition: attachment`
- `X-Content-Type-Options: nosniff`
- PDF Size Limit
- 不接受任意 Object Path
- 不包含 Watchlist、LINE ID、Session 或使用者資料

## 9. Metadata 擴充

Reports v2 Metadata 新增：

- `html_available`
- `pdf_available`
- `pdf_object`
- `pdf_sha256`
- `pdf_size`
- `pdf_page_count`
- `report_schema_version`
- `generator_version`
- `code_commit_sha`
- `ai_reference_status`

發布順序：

1. 建立 Canonical Content
2. 建立 HTML View Model
3. 建立 PDF
4. 驗證 PDF
5. 上傳 Immutable Content／PDF
6. Read-back SHA／Size／Schema
7. 更新 Index
8. 最後原子更新 Latest Pointer

不得先更新 Pointer 再產生 PDF。

## 10. 舊版相容

- 保留舊 Reports v1 Reader
- 不改寫舊 Immutable PDF
- 舊網址可安全 Redirect 或顯示 Legacy 標記
- 新報告統一走 v2 Canonical Schema
- `reporting/pdf_generator.py` 可重構，但舊樣本測試不得無理由破壞

## 11. 報告列表修正

`templates/reports.html` 必須改為：

- `reports_v2` 有內容時顯示 v2
- `reports` 有內容時顯示 legacy
- Legacy 無資料時省略 Legacy Section
- 只有兩者皆空時才顯示全頁 Empty State
- `unavailable=true` 時顯示服務錯誤，而非資料尚未發布

每張盤後報告卡提供：

- 閱讀網頁完整版
- 下載完整 PDF

盤前卡提供：

- 閱讀盤前摘要
- 可選擇生成精簡 PDF，但不是本階段必要條件

## 12. AI 參考建議

報告可加入：

> **AI 模型參考建議**

固定聲明：

> 內容由 Gemini 根據 ABSORB 可取得的市場、產業、個股及量化研究資料整理，不構成個人化投資建議，亦不保證未來結果。

若使用未校準數值：

- 標示為「模型方向參考值」
- 顯示尚未通過機率校準
- 不得稱為真實上漲機率
- 不得顯示歷史勝率背書

## 13. 錯誤處理

### 13.1 Canonical Content 不完整

- 關鍵 identity／market／governance 缺失：停止發布
- 非關鍵章節缺失：顯示 unavailable 並保留其他章節
- 不得以 0 取代 None
- 不得以 Sample Data 補位

### 13.2 PDF 失敗

- 不更新 Latest Pointer
- 保存 Candidate 與 Failure Receipt
- 網頁 Candidate 不得冒充完整發布
- 記錄 Stage、Error Code、Correlation ID
- 不在公開頁顯示 Stack Trace

### 13.3 Gemini 失敗

- Canonical 報告仍可發布
- AI 章節顯示暫時不可用
- 不影響市場、產業、回歸與驗證章節
- 不以固定模板假裝 Gemini 已執行

## 14. 測試要求

### 14.1 Schema

- Canonical Schema 驗證
- Finite JSON
- None／0 區分
- Date Semantics
- SHA Identity
- Unsupported Version Fail Closed

### 14.2 HTML

- 完整章節存在
- 單一 H1
- 章節目錄
- Anchor Navigation
- Mobile Layout
- 缺少單一章節不造成整頁 500
- 不直接渲染 Raw Metadata

### 14.3 PDF

- 成功產生 25–35 頁標準報告 fixture
- 最低頁數 Gate
- 中文文字可抽取
- 必要章節文字存在
- PDF SHA／Size／Page Count 正確
- 不含 Stock Papi
- 不含 Sample／Test Data
- 不含測試股票
- 原子替換
- Immutable Conflict

### 14.4 Parity

- HTML 與 PDF 使用相同 `content_sha256`
- 資料日一致
- 市場結論一致
- 產業排名一致
- 個股事件一致
- Coverage 一致
- AI 參考建議一致
- LINE 摘要不得與正式報告相反

### 14.5 安全

- Invalid Object Path 拒絕
- SHA 錯誤 503
- Size 錯誤 503
- Bucket 保持 Private
- PDF 不含使用者資料
- Download Route 不暴露 GCS 內部路徑
- Secret Scan

### 14.6 模型揭露

- Failed Gates 必須顯示
- 未校準數值正確標記
- Gemini 不編造數字
- Promotion BLOCKED 時不得顯示正式 Prediction Probability

## 15. Production Cutover

1. 完成 Canonical Schema
2. 完成 HTML Renderer
3. 重構 PDF Generator
4. 建立 Candidate-only 報告
5. 驗證頁數、內容與 Parity
6. 上傳 Immutable Objects
7. Read-back 驗證
8. 部署 Cloud Run No-Traffic Revision
9. 使用 Production GCS Candidate Smoke Test
10. 保存 PreviousRevision 與 Previous Pointers
11. 更新 Reports Index／Latest
12. 切換 Production Traffic
13. Production HTML／PDF Smoke Test
14. 失敗立即 Rollback

不得建立 `backtests/v1/latest-TW.json`，除非模型真正通過全部 Model Gates。

## 16. 明確不在本階段範圍

- 重新設計 ABSORB 品牌
- 重做多頁資訊架構
- 重寫盤前報告為長版
- 降低模型 Gate
- 將未校準輸出重新命名成正式機率
- 使用目前分類回填歷史 PIT 研究資料
- 新增付費牆或訂閱系統

## 17. 完成定義

本功能完成時必須達成：

1. 盤前維持 1–3 頁精簡更新。
2. 盤後產生 25–35 頁機構級研究報告。
3. HTML 與 PDF 使用同一 Canonical Schema。
4. 網頁提供完整閱讀與 PDF 下載。
5. PDF 包含市場、廣度、風險、籌碼、產業、個股、ETF、回歸、模型、驗證、回測、資料治理與下一交易日框架。
6. 模型失敗結果如實呈現。
7. Gemini 只解讀既有資料，不創造數字。
8. Reports 頁不再顯示假的 Empty State。
9. PDF 保持 Private Storage、Validated Delivery。
10. 完整測試、No-Traffic、Production Smoke 與 Rollback 通過。
