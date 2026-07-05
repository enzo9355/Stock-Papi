# Local Taiwan and US Markets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在同一個 05:30–09:20 本地排程中，以獨立進度安全更新台股與美股全市場快照。

**Architecture:** 泛化既有 artifact、snapshot 與 checkpoint 介面支援 `TW`、`US`，台股保留現有進度檔，美股新增獨立進度檔。美股 universe 從固定 SEC HTTPS JSON 取得並快取至 D 槽；runner 同一把 lock 內依序執行兩市場，每檔仍受 09:20 時間守門。

**Tech Stack:** Python 3.10 stdlib、既有 requests/pandas/yfinance/LightGBM、PowerShell、unittest。

---

### Task 1: 市場感知 artifact 與 checkpoint

**Files:**
- Modify: `tests/test_local_quant_batch.py`
- Modify: `local_quant.py`

- [ ] 先寫失敗測試：`write_stock_artifact(root, "US", "BRK-B", payload)` 寫入 `artifacts/stocks/US/BRK-B.json.gz`；`../AAPL`、`AAPL/evil`、`AAPL.B` 被拒絕。
- [ ] 寫失敗測試：TW 與 US checkpoint 分別寫入 `progress.json`、`progress-US.json`，內容互不覆蓋。
- [ ] 執行 `python -m unittest tests.test_local_quant_batch -v`，確認現行 TW-only 驗證失敗。
- [ ] 實作 `validate_market_symbol(market, symbol)`、`_checkpoint_path(root, market)`；`load_checkpoint`、`save_checkpoint` 接受可選 `market="TW"`，保持既有呼叫相容。
- [ ] `run_market_batch()` 依 market 使用獨立 checkpoint，錯誤與時間守門行為不變。
- [ ] 測試通過後提交 `feat: separate Taiwan and US market state`。

### Task 2: SEC 美股 universe 與安全快取

**Files:**
- Modify: `tests/test_local_quant_batch.py`
- Modify: `local_quant.py`

- [ ] 先寫失敗測試：`parse_sec_us_universe()` 依 `fields` 位置解析，保留 Nasdaq/NYSE/CBOE、正規化大寫與去重，排除 OTC、無效 ticker 及明確 crypto 名稱。
- [ ] 先寫失敗測試：`get_us_symbols(root, fetch_json, now)` 同日使用 `raw/us-universe.json`；下載失敗使用舊快取；無快取時重新拋出安全例外。
- [ ] 執行焦點測試確認缺少函式。
- [ ] 使用既有 `requests.get()` 透過注入的 `fetch_json` 封裝固定 SEC URL、15 秒 timeout、5 MB `Content-Length` 與實際 response bytes 上限。
- [ ] cache 使用 `_write_json_atomic`，只保存 `as_of`、`source`、`symbols`，不保存完整 SEC 回應。
- [ ] 測試通過後提交 `feat: add SEC US stock universe`。

### Task 3: 泛化單股 snapshot 與美股代碼

**Files:**
- Modify: `tests/test_local_quant_batch.py`
- Modify: `tests/test_prediction_pipeline.py`
- Modify: `local_quant.py`
- Modify: `app.py`

- [ ] 先寫失敗測試：`build_stock_snapshot(pipeline, "US", "AAPL")` 呼叫既有 `get_data("AAPL", 730)` 並輸出 `market="US"` 的資料。
- [ ] 先寫失敗測試：`is_us_ticker("BRK-B")` 與 `search_stock_code("brk-b")` 成功，含點、斜線、超過 10 字元則失敗。
- [ ] 將 `build_taiwan_stock_snapshot` 重新命名為 `build_stock_snapshot`，呼叫前使用共用市場代碼驗證；payload 保持原 schema。
- [ ] 將 `app.is_us_ticker()` 改成 `(?=.{1,10}\Z)[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)?`，維持 `TAIEX` 排除。
- [ ] 測試通過後提交 `feat: support US stock snapshot symbols`。

### Task 4: 雙市場 CLI 與排程

**Files:**
- Modify: `tests/test_local_quant.py`
- Modify: `tests/test_local_quant_task.py`
- Modify: `local_quant.py`
- Modify: `scripts/run_local_quant_task.ps1`
- Modify: `README.md`

- [ ] 先寫失敗測試：`--market ALL` 在同一 lock 內依序呼叫 TW、US；TW 使用 `get_taiwan_symbols`，US 使用 `get_us_symbols`；closed window 兩者均不載入。
- [ ] CLI choices 改為 `TW`、`US`、`ALL`；將單一市場執行抽成最小 `_run_market()` helper，兩市場共享同一 pipeline 與即時 `now_fn`。
- [ ] wrapper 改為 `--market ALL --limit 5000`；靜態測試拒絕 `--market TW`。
- [ ] README 說明台美市場路徑、獨立 checkpoint、SEC 來源與不含虛擬貨幣。
- [ ] 焦點測試通過後提交 `feat: run Taiwan and US local markets`。

### Task 5: 完整驗證與啟用

**Files:**
- No production changes expected.

- [ ] 執行 201+ 項完整 unittest、Python compile、Node check、PowerShell parse、ShellWard 與 `git diff --check`。
- [ ] 在非 run window 手動觸發排程，確認 closed、artifact 數不變；不得繞過時間窗下載美股。
- [ ] 唯讀確認 task action 仍指向 wrapper、05:30、PT4H、IgnoreNew。
- [ ] 推送 main；Cloud Run 不部署，因本階段仍是本機產物管線。
