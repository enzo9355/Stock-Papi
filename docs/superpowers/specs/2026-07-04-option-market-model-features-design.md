# 選擇權市場模型特徵設計

## 目標

將有完整歷史、可按日期對齊且不會引入未來資料的中高價值選擇權市場資訊加入五日 LightGBM 預測，同時維持 1GB Cloud Run、Python 3.10 與低冷啟動。

## 資料選擇

本階段採用 Cboe 波動率期限結構的公開歷史指數：

- VIX：S&P 500 選擇權隱含的 30 日預期波動。
- VIX9D：9 日預期波動。
- VIX3M：3 個月預期波動。

Yahoo Finance 已能透過現有 `yfinance` 取得約兩年的每日歷史，不新增套件或 API 金鑰。這些是整體選擇權市場風險代理，會同時加入台股與美股模型。

TAIFEX Put/Call OpenAPI 目前只提供約一個月資料；若直接加入 730 日訓練，會形成近期才有值的時間偏差。TAIWAN VIX 官方歷史則分散在每月檔案。本階段不讓這兩者直接改模型，後續以每日快照累積並完成樣本外驗證後再啟用。

## 模型特徵

- `OPTION_IV_LEVEL`：VIX 除以 100。
- `OPTION_IV_CHG_1`：VIX 一日變化率。
- `OPTION_IV_CHG_5`：VIX 五日變化率。
- `OPTION_IV_TERM_9D_3M`：VIX9D／VIX3M－1；正值代表短期事件風險高於三個月預期。
- `OPTION_DATA_MISSING`：當日與最近四日均無 VIX 時為 1，避免把缺資料誤認為低波動。

## 日期與資料洩漏

先在 VIX 交易日期計算變化率，再使用 backward as-of merge 對齊股票交易日，最多沿用最近四個曆日資料：

- 只允許使用當日或更早資料。
- 台美休市不同時可沿用最近一次已知值。
- 超過四日仍無資料時填 0，並將缺漏旗標設為 1。
- 不使用向前填入的未來值。

## 程式結構

- 沿用 `fetch_yfinance_price_history()` 與現有一小時快取。
- 新增 `fetch_option_context_history()`，用標準函式庫並行取得三個指數。
- 新增純資料函式 `add_option_context_features()`，負責計算與日期對齊。
- `OPTION_FEATURES` 加入 `MODEL_FEATURES`、`calc_all()` 與 `_clean_df()` 的數值欄位。
- 台股與美股 `get_data()` 在價格資料取得後合併相同的市場級特徵。

## 驗證標準

- 缺資料時五個特徵皆為安全中性值，缺漏旗標為 1。
- 週末或單一市場休市時只沿用過去資料。
- 未來日期資料不得出現在較早的股票列。
- `MODEL_FEATURES`、訓練與最新推論使用完全相同欄位。
- 現有時間序列切分、五日 gap、Brier Score 與模型機率範圍測試維持通過。
- 完整測試、實際資料 smoke test、敏感資訊掃描與部署後頁面檢查。

## 本階段不做

- 不把即時 Options Flow、0DTE、Open Interest、GEX 或 Vanna 直接加入模型。
- 不用當下 Option Chain 回填歷史。
- 不以未回測規則人工加減最終機率。
- 不新增資料庫、背景 worker 或重型套件。

