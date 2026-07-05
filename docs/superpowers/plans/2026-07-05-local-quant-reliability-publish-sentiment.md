# Stock Papi Local Quant Reliability, Publish, and Sentiment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓全市場批次失敗可續跑、完整產物可安全形成發布版本，並增加不造成回測偷看的細緻情緒候選指標。

**Architecture:** 延用 `local_quant.py` 的逐股原子 artifact 與 checkpoint，加入持久失敗佇列及 manifest-last 本地發布。情緒只擴充 `app.py` 既有純聚合函式，不增加來源、依賴或正式模型欄位。

**Tech Stack:** Python 3.10 stdlib、Flask 既有程式、unittest、JSON + gzip + SHA-256。

---

### Task 1: 跨批次失敗重試

**Files:**
- Modify: `local_quant.py`
- Test: `tests/test_local_quant_batch.py`

- [ ] 先寫失敗測試，證明前一批失敗股票會在下一批優先重試。
- [ ] 執行單一測試，確認因現有流程忽略舊失敗清單而失敗。
- [ ] 最小修改 `run_market_batch()`，持久保存去重後的待重試項目。
- [ ] 執行批次測試，確認成功重試會移除、再次失敗不重複。

### Task 2: 本地 immutable manifest 與 latest 切換

**Files:**
- Modify: `local_quant.py`
- Test: `tests/test_local_quant_publish.py`

- [ ] 先寫完整與缺檔兩個失敗測試。
- [ ] 實作串流 SHA-256、gzip JSON 驗證與 manifest 建立。
- [ ] manifest 驗證成功後才原子寫入 `latest-<market>.json`。
- [ ] 在市場批次完成且無待重試時呼叫發布函式。
- [ ] 執行發布測試與本地量化完整測試。

### Task 3: 細緻情緒候選指標

**Files:**
- Modify: `app.py`
- Test: `tests/test_sentiment.py`

- [ ] 先寫失敗測試，涵蓋情緒波動、動能、分歧、有效樣本與欄位缺漏。
- [ ] 在 `aggregate_news_sentiment()` 以現有權重計算有限值。
- [ ] 空資料回傳完整的中性 schema。
- [ ] 執行情緒與全套測試，確認既有五級標籤相容。

### Task 4: 驗證、文件與發布

**Files:**
- Modify: `README.md`

- [ ] 更新本地重試、發布門檻與候選情緒欄位說明。
- [ ] 執行 `python -m unittest discover -s tests -v`。
- [ ] 執行 `python -m py_compile app.py local_quant.py line_state.py`、`node --check static/app.js`、`git diff --check`。
- [ ] 執行安全掃描與第二審查；只提交本次檔案，保留 `0.26.0` 及競賽文件未追蹤狀態。
- [ ] 推送 GitHub。若未新增 Cloud Run 讀取發布檔，這一階段不部署 Cloud Run。

