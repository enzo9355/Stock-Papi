# MarketAux 新聞交叉驗證設計

## 目標

在不影響既有 Google News RSS、模型機率、冷啟動與 1GB 記憶體限制的前提下，選用 MarketAux 補充結構化金融新聞。

## 設計

- `MARKETAUX_API_TOKEN` 未設定時維持既有流程，不發出額外請求。
- 已設定時，以公司名稱查詢最多 3 篇繁體中文金融新聞，再與 Google RSS 結果合併並沿用既有去重流程。
- MarketAux 的原始情緒分數保留為 `external_sentiment_score`，僅供後續驗證；目前仍由既有中文規則統一計算對外情緒，且不修改五日上漲機率。
- API 失敗、超時或回傳格式錯誤時回傳空清單，Google RSS 仍可獨立工作。
- 不增加第三方套件；沿用 `requests`、既有資料結構與測試框架。

## 驗證

- 單元測試涵蓋：未設定金鑰不呼叫、正確解析、異常降級、跨來源去重。
- 執行完整測試、`git diff --check` 與部署後 HTTP 健康檢查。
