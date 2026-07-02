# Full Market Prefilter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Select daily prediction candidates from the full supported Taiwan market while keeping expensive model runs bounded for 1GB Cloud Run.

**Architecture:** Fetch one bulk quote payload each from TWSE and TPEx, normalize turnover and volume by stock code, then rank every supported code before the existing bounded analysis loop. If either source fails, use available data; if both fail, preserve the existing code order.

**Tech Stack:** Python 3.10, requests, unittest

---

### Task 1: Bulk market activity

**Files:**
- Modify: `tests/test_line_flow.py`
- Modify: `app.py`

- [ ] Add a failing test for normalizing TWSE and TPEx bulk quote fields.
- [ ] Run the focused test and confirm `fetch_market_activity()` is missing.
- [ ] Implement two bounded HTTP requests and normalize `{code: {trade_value, trade_volume}}`.
- [ ] Run the focused test and confirm it passes.

### Task 2: Full-universe candidate ranking

**Files:**
- Modify: `tests/test_line_flow.py`
- Modify: `app.py`

- [ ] Add a failing test proving high-turnover stocks are selected from beyond the old first-60 window.
- [ ] Run the focused test and confirm the old static-order selection fails.
- [ ] Extend `sector_candidates()` to rank supported codes by turnover and volume, with static-order fallback.
- [ ] Fetch activity once in `refresh_sector_signals()` and pass it into the existing snapshot builder.
- [ ] Run the focused tests and confirm they pass.

### Task 3: Documentation and release

**Files:**
- Modify: `README.md`

- [ ] Document full-market prefiltering and bounded full-model analysis.
- [ ] Run the complete unit test suite and `git diff --check`.
- [ ] Commit, push, deploy from a clean Git archive, and verify the Cloud Run revision and HTTP response.
