# Local Quant 02:30 Schedule Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓本地量化每日 02:30 先跑台股，05:30 後再跑美股，09:30 硬停止。

**Architecture:** Python 時間窗只調整開始時間；市場順序與美股延後由既有 PowerShell wrapper 負責。Windows Task Scheduler 維持單一 task，執行上限由 4 小時改為 7 小時。

**Tech Stack:** Python 3.10、PowerShell Task Scheduler、unittest。

---

### Task 1: 時間窗與 wrapper 順序

**Files:**
- Modify: `tests/test_local_quant.py`
- Modify: `tests/test_local_quant_task.py`
- Modify: `local_quant.py`
- Modify: `scripts/run_local_quant_task.ps1`

- [ ] 將時間邊界測試預期改為 02:29 closed、02:30 run，執行確認現行 05:30 設定使測試失敗。
- [ ] 將 wrapper 測試改為驗證 TW invocation 位於 `Start-Sleep` 前、US invocation 位於其後，且不再使用 `--market ALL`。
- [ ] 將 `RUN_START` 改為 02:30。
- [ ] wrapper 先執行 TW；成功後等待到當日 05:30；再執行 US。任一 runner 非零即回傳該 exit code。
- [ ] 執行 `python -m unittest tests.test_local_quant tests.test_local_quant_task -v` 與 PowerShell parse。

### Task 2: Installer、說明與實際排程

**Files:**
- Modify: `scripts/install_local_quant_task.ps1`
- Modify: `README.md`

- [ ] 將 installer 測試預期改為 `02:30`、`New-TimeSpan -Hours 7`，確認 RED。
- [ ] installer trigger 改為 02:30、execution limit 改為 7 小時，WhatIf 文字同步。
- [ ] README 記錄 02:30 台股、05:30 美股、09:20 drain、09:30 hard stop 與安全原則。
- [ ] 執行完整 unittest、compile、Node check、PowerShell parse、ShellWard、`git diff --check`。
- [ ] 重新執行 installer，唯讀確認 trigger、PT7H、IgnoreNew、StartWhenAvailable=false；非工作時段觸發確認不下載資料。
- [ ] 提交並推送 main；Cloud Run 不需部署。
