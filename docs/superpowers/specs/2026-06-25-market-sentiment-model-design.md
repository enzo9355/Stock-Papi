# 市場情緒與 yfinance 輔助特徵設計

## 目標

在不增加 Cloud Run 1GB RAM 風險、不拉長 LINE webhook 回應時間的前提下，提高五日上漲機率模型的資料品質與市場真實感。

本階段只做 A+B：

- A：FinMind 價格資料維持主資料源，yfinance 做價格交叉驗證與市場環境補強。
- B：把現有新聞情緒分數整理成輕量、可測試、可顯示的輔助訊號；可即時顯示，但不把今天新聞硬塞進歷史回測。

## 不做的事

- 不用 yfinance 取代 FinMind。yfinance 官方定位是 Yahoo Finance 公開資料工具，適合研究用途，不適合作為台股主資料源。
- 不新增 BERT、FinBERT、transformers、jieba、SnowNLP 等重型 NLP 套件。
- 不在 LINE webhook 裡做大量新聞分析、LLM 分析或全市場重訓。
- 不把「今天抓到的新聞」回填到過去兩年的回測資料，避免未來資料洩漏。
- 不實作 C 計畫的本地 LLM 批次。C 先保留為後續獨立設計。

## 現況

目前 `get_data()` 已有 yfinance fallback：

```text
FinMind TaiwanStockPrice 成功
  -> 使用 FinMind 價格
FinMind 無價格資料
  -> yfinance 依序嘗試 <code>.TW / <code>.TWO
```

目前模型特徵集中在技術面、成交量、法人與融資融券：

```text
MA_5, MA20, RET_1, RET_5, RET_20, RSI, Volat,
RANGE_PCT, VOL_RATIO, VOL_CHG, INST_NET_RATIO,
MARGIN_CHG, SHORT_CHG, MACD_OSC, K, D
```

目前新聞情緒是查詢個股時即時抓 Google News RSS，再用關鍵字字典計分。這個分數目前只顯示在 UI，不進 LightGBM 訓練。

## 架構

```text
FinMind 台股價格 / 籌碼
  -> 主要 OHLCV、法人、融資融券

yfinance
  -> 價格交叉驗證
  -> 大盤與 ETF 市場環境序列

Google News RSS
  -> 查詢當下的新聞情緒輔助訊號

calc_all()
  -> 技術面 + 籌碼面 + 市場環境特徵

run_ai_engine()
  -> LightGBM walk-forward 回測
  -> 比較新增特徵前後 metrics
```

## A：yfinance 價格交叉驗證

新增一個小型 helper，把 FinMind 價格與 yfinance 價格對齊最近幾個交易日。

輸出欄位：

```text
DATA_PRICE_DIFF_PCT
DATA_PRICE_WARNING
YF_CLOSE
```

規則：

- 預設比較最近 5 個共同交易日。
- 若平均收盤價差異超過 2%，標記 `DATA_PRICE_WARNING = 1`。
- 若 yfinance 抓不到資料，所有檢查欄位回到中性值，不中斷分析。
- `DATA_PRICE_WARNING` 不直接當買賣訊號，只用於資料品質提示與模型輔助。

## A：yfinance 市場環境特徵

新增輕量市場 proxy，不抓太多標的。

初版只抓：

```text
^TWII      台股大盤
0050.TW    台灣大型權值 ETF
```

可選但初版不做：

```text
^IXIC
SOXX
```

原因是海外 proxy 會牽涉台美交易日對齊、匯率、時差與半導體權重問題，先不把範圍拉大。

新增特徵：

```text
MARKET_RET_1
MARKET_RET_5
MARKET_RET_20
MARKET_VOL_20
ETF50_RET_5
STOCK_VS_MARKET_5
```

缺資料時全部補 0，避免模型因市場資料短缺而整檔分析失敗。

## B：輕量新聞情緒特徵

本階段不把即時新聞情緒納入歷史 LightGBM 訓練，原因是沒有歷史每日新聞快照，直接納入會造成未來資料洩漏。

本階段做兩件事：

1. 把 `analyze_sentiment()` 拆成可測試的純 helper。
2. 讓 UI 顯示更具體的情緒拆解。

輸出欄位：

```text
NEWS_SENTIMENT_SCORE
NEWS_COUNT
NEWS_NEGATIVE_RATIO
NEWS_POSITIVE_RATIO
NEWS_STATUS
```

用途：

- LINE / Web 顯示市場情緒。
- 產業預測排序可作為小權重加分，但不回填歷史模型。
- 未來若累積每日快照，再正式加入 `MODEL_FEATURES`。

## 模型特徵調整

本階段正式加入模型的只有可歷史對齊的市場特徵：

```text
MARKET_RET_1
MARKET_RET_5
MARKET_RET_20
MARKET_VOL_20
ETF50_RET_5
STOCK_VS_MARKET_5
DATA_PRICE_DIFF_PCT
DATA_PRICE_WARNING
```

新聞情緒不加入 `MODEL_FEATURES`，只作 UI 與排序輔助。

## 回測比較

新增或更新測試，確保：

- yfinance 已裝好時，不新增依賴。
- FinMind 價格正常時，仍以 FinMind 為主。
- yfinance 缺資料時分析不失敗。
- 市場特徵能依日期對齊到個股資料。
- `MODEL_FEATURES` 包含市場特徵。
- 新聞情緒 helper 不會改變模型機率本身。

人工驗證時比較新舊模型：

```text
accuracy
brier
strat_cum
bh_cum
mdd
sharpe
trades
```

若新增市場特徵讓 brier 變差且策略報酬沒有改善，應保留資料品質提示，但不要把該特徵放進正式 `MODEL_FEATURES`。

## 錯誤處理

- yfinance timeout 或空資料：印出簡短錯誤，回傳中性欄位。
- 市場 proxy 日期缺口：用日期 merge 後 forward-fill，再限制只用已知過去資料。
- FinMind 與 yfinance 價格差異過大：不阻斷分析，只顯示資料品質警示。
- 新聞 RSS 失敗：情緒分數回到 50，中性。

## 效能限制

- yfinance 只在 `get_data()` 分析流程中 lazily import，不放在 module global。
- 市場 proxy 需要快取，避免同一輪多檔股票重複下載。
- 不新增背景 worker、不新增資料庫、不新增大型套件。
- Cloud Run webhook 仍依現有 `_SYSTEM_CACHE` 避免重複分析。

## 交付範圍

本階段交付：

- yfinance 市場 proxy helper。
- yfinance / FinMind 價格品質檢查 helper。
- 新市場特徵加入 `calc_all()` 與 `MODEL_FEATURES`。
- 情緒 helper 結構化輸出。
- LINE / Web 可讀取新的情緒與資料品質欄位。
- 對應單元測試與完整 regression test。

本階段不交付：

- 本地 LLM 批次。
- 歷史新聞資料庫。
- 情緒快照正式入模。
- 新部署架構。

