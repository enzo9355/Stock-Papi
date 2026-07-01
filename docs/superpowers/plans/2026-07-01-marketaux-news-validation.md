# MarketAux News Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add MarketAux as an optional secondary news source without changing prediction probabilities or existing behavior when no token is configured.

**Architecture:** Reuse the current news item schema and `normalize_and_dedupe()` pipeline. Fetch and parse MarketAux only when `MARKETAUX_API_TOKEN` is present, merge the result with Google RSS, and fail closed to the existing source.

**Tech Stack:** Python 3.10, requests, unittest

---

### Task 1: Optional MarketAux parser and fetcher

**Files:**
- Modify: `tests/test_prediction_pipeline.py`
- Modify: `app.py`

- [ ] Write failing tests proving token gating, response parsing, and safe failure.
- [ ] Run `python -m unittest tests.test_prediction_pipeline.PredictionPipelineTests.test_marketaux_news_is_optional -v` and confirm the missing function causes failure.
- [ ] Add `MARKETAUX_API_TOKEN`, `parse_marketaux_items()` and `fetch_marketaux_news()` using `requests.get(..., timeout=5)`.
- [ ] Run the focused tests and confirm they pass.

### Task 2: Merge with the existing pipeline

**Files:**
- Modify: `tests/test_prediction_pipeline.py`
- Modify: `app.py`

- [ ] Write a failing test proving Google RSS and MarketAux items are merged and deduplicated.
- [ ] Run the focused test and confirm it fails because `get_news()` ignores MarketAux.
- [ ] Change `get_news()` to combine both sources before calling `normalize_and_dedupe()`.
- [ ] Run the focused tests and confirm they pass.

### Task 3: Document and verify

**Files:**
- Modify: `README.md`

- [ ] Document optional `MARKETAUX_API_TOKEN` behavior and limits.
- [ ] Run `python -m unittest discover -s tests -v`.
- [ ] Run `git diff --check` and inspect `git diff --stat`.
- [ ] Commit, push, deploy to Cloud Run, and verify the service health endpoint.
