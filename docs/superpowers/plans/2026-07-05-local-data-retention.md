# Local Data Retention Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 每日本地量化工作開始前，只在 `D:\StockPapiData` 的固定 allowlist 內刪除過期且可重建的資料。

**Architecture:** 在既有 `local_quant.py` 增加單一 `cleanup_expired_data()` 純檔案操作入口，以固定 retention mapping 掃描普通檔案，跳過 reparse point，回傳不含檔名的摘要。CLI 只在 `--run`、run window 且取得 runner lock 後呼叫，摘要併入現有狀態 JSON。

**Tech Stack:** Python 3.10 stdlib `pathlib`、`os`、`stat`、既有 `unittest`。

---

### Task 1: 安全期限清理器

**Files:**
- Modify: `tests/test_local_quant.py`
- Modify: `local_quant.py`

- [ ] **Step 1: 寫失敗測試**

建立舊檔、新檔、受保護 artifact、stale lock 與 symlink（平台允許時），呼叫：

```python
summary = cleanup_expired_data(root, now=at(6, 0))
```

驗證舊暫存／舊日誌／七日前 stale lock 被刪除，新檔、artifact、`progress.json`、目前 lock 與 symlink 目標保留，摘要只有 `deleted_files`、`reclaimed_bytes`、`failed`、`skipped_reparse_points`。

- [ ] **Step 2: 確認 RED**

Run: `python -m unittest tests.test_local_quant.LocalQuantTests.test_cleanup_expired_data_is_allowlisted_and_age_bounded -v`

Expected: `ImportError`，因 `cleanup_expired_data` 尚未存在。

- [ ] **Step 3: 最小實作**

在 `local_quant.py` 定義固定 mapping：

```python
RETENTION_DAYS = {
    "cache/tmp": 1,
    "cache/pycache": 30,
    "raw": 30,
    "logs": 30,
    "publish": 30,
}
```

實作 `cleanup_expired_data(root, now=None)`：先驗證 root；使用 `os.scandir()` 且 `follow_symlinks=False`，reparse point 只計數不跟隨；普通檔案以 `mtime < cutoff` 判斷；另只比對 `checkpoints/runner.lock.stale.*` 且保留 7 天。刪檔失敗增加 `failed`，不輸出路徑。

- [ ] **Step 4: 確認 GREEN**

Run: `python -m unittest tests.test_local_quant -v`

Expected: all tests pass。

- [ ] **Step 5: 提交**

```powershell
git add -- local_quant.py tests/test_local_quant.py
git commit -m "feat: clean expired local quant data"
```

### Task 2: 排程整合與驗證

**Files:**
- Modify: `tests/test_local_quant.py`
- Modify: `README.md`

- [ ] **Step 1: 寫 CLI 失敗測試**

在既有 `test_cli_run_loads_pipeline_only_inside_work_window` patch `cleanup_expired_data`，驗證 run window 呼叫一次且 closed window 完全不呼叫。

- [ ] **Step 2: 確認 RED**

Run: `python -m unittest tests.test_local_quant.LocalQuantTests.test_cli_run_loads_pipeline_only_inside_work_window -v`

Expected: FAIL，因 CLI 尚未呼叫 cleanup。

- [ ] **Step 3: 最小整合**

在 `main()` 的 `with acquire_lock(...)` 內、`load_stock_pipeline(root)` 前執行：

```python
cleanup = cleanup_expired_data(root, now=checked_at)
```

並將摘要寫回 `runner-status.json`；README 記錄固定路徑與保留期。

- [ ] **Step 4: 完整驗證**

```powershell
python -m unittest discover -s tests -v
python -m py_compile app.py line_state.py local_quant.py
node --check static/app.js
shellward scan --json .
git diff --check
```

Expected: tests exit 0、compile/check exit 0、ShellWard 無新增真實 secret。

- [ ] **Step 5: 重新安裝並安全實測排程**

執行 installer，於非 run window 手動觸發後確認 `LastTaskResult=0`、artifact 數不變、無 lock；在測試資料夾建立一個超過保留期的假檔，以函式直接驗證只刪該檔，不碰其他目錄。

- [ ] **Step 6: 提交與推送**

```powershell
git add -- README.md tests/test_local_quant.py local_quant.py
git commit -m "docs: document local data retention"
git push origin main
```
