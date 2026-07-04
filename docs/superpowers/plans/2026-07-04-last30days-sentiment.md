# Last 30 Days 輿論分析整合 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不增加依賴與背景服務的前提下，將近 30 日 StockTwits 美股社群多空比例加入既有新聞情緒分析。

**Architecture:** `app.py` 沿用既有抓取、解析、去重、評分與彙總流程；StockTwits 只產生一筆匿名彙總證據。所有網路失敗均回傳空清單，台股與既有 Google News／MarketAux 路徑不受影響。

**Tech Stack:** Python 3.10、requests、Flask、unittest、LINE Flex Message、Jinja2。

---

## File map

- Modify: `app.py` — StockTwits 抓取／解析、30 日過濾、權重、彙總欄位與 LINE／legacy Web 顯示。
- Modify: `templates/stock_detail.html` — 正式 Web 頁的新聞／輿論與來源摘要。
- Modify: `tests/test_prediction_pipeline.py` — 純函式、降級、整合與 UI 回歸測試。
- Modify: `README.md` — 公開說明資料來源、限制與不影響模型機率。

### Task 1: 近 30 日 StockTwits 彙總來源

**Files:**
- Modify: `tests/test_prediction_pipeline.py`
- Modify: `app.py:456-612`

- [ ] **Step 1: Write failing parser and fetch tests**

```python
def test_parse_stocktwits_sentiment_builds_anonymous_30_day_summary(self):
    now = datetime.datetime(2026, 7, 4, tzinfo=datetime.timezone.utc)
    payload = {"messages": [
        {"created_at": "2026-07-03T00:00:00Z", "entities": {"sentiment": {"basic": "Bullish"}}},
        {"created_at": "2026-07-02T00:00:00Z", "entities": {"sentiment": {"basic": "Bearish"}}},
        {"created_at": "2026-05-01T00:00:00Z", "entities": {"sentiment": {"basic": "Bullish"}}},
    ]}
    items = stock_app.parse_stocktwits_sentiment(payload, "AAPL", now=now)
    self.assertEqual(items[0]["social_sample_size"], 2)
    self.assertEqual(items[0]["external_sentiment_score"], 0)
    self.assertNotIn("author", items[0])

def test_stocktwits_fetch_is_us_only_and_fails_closed(self):
    with patch.object(stock_app.requests, "get") as get:
        self.assertEqual(stock_app.fetch_stocktwits_sentiment("2330"), [])
    get.assert_not_called()
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `python -m unittest tests.test_prediction_pipeline.PredictionPipelineTests.test_parse_stocktwits_sentiment_builds_anonymous_30_day_summary tests.test_prediction_pipeline.PredictionPipelineTests.test_stocktwits_fetch_is_us_only_and_fails_closed -v`

Expected: `AttributeError` because the two functions do not exist.

- [ ] **Step 3: Implement the minimal parser and fetcher**

```python
SOCIAL_WINDOW_DAYS = 30

def parse_stocktwits_sentiment(payload, code, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=SOCIAL_WINDOW_DAYS)
    bullish = bearish = 0
    newest = None
    for message in payload.get("messages", []):
        published = datetime.datetime.fromisoformat(
            str(message.get("created_at") or "").replace("Z", "+00:00")
        )
        if published < cutoff or published > now:
            continue
        label = (((message.get("entities") or {}).get("sentiment") or {}).get("basic"))
        bullish += label == "Bullish"
        bearish += label == "Bearish"
        newest = max(newest, published) if newest else published
    count = bullish + bearish
    if not count:
        return []
    return [{
        "title": f"{code} StockTwits 近 30 日多方 {bullish}、空方 {bearish}",
        "normalized_title": f"{code} StockTwits 近 30 日多方 {bullish}、空方 {bearish}",
        "link": f"https://stocktwits.com/symbol/{code}",
        "source": "StockTwits", "provider": "stocktwits",
        "published_at": newest.isoformat(),
        "age_hours": max(0.0, (now - newest).total_seconds() / 3600),
        "external_sentiment_score": (bullish - bearish) / count,
        "social_sample_size": count, "duplicate_count": 0,
        "parse_flags": {"missing_source": False, "missing_published_at": False},
    }]

def fetch_stocktwits_sentiment(code):
    if not is_us_ticker(code):
        return []
    try:
        response = requests.get(
            f"https://api.stocktwits.com/api/2/streams/symbol/{urllib.parse.quote(code)}.json",
            headers={"User-Agent": "Stock-Papi/1.0 sentiment"},
            timeout=3,
        )
        response.raise_for_status()
        return parse_stocktwits_sentiment(response.json(), code)
    except (requests.RequestException, AttributeError, TypeError, ValueError):
        return []
```

- [ ] **Step 4: Merge one social summary without displacing all news**

Change `get_news(name, code=None)` to merge Google News, MarketAux and StockTwits, filter dated items older than 30 days, and retain at most four news items plus one StockTwits summary.

- [ ] **Step 5: Run Task 1 tests**

Run: `python -m unittest tests.test_prediction_pipeline -v`

Expected: all prediction-pipeline tests pass.

### Task 2: 社群權重與來源覆蓋

**Files:**
- Modify: `tests/test_prediction_pipeline.py`
- Modify: `app.py:842-1017`

- [ ] **Step 1: Write failing scoring and aggregation tests**

```python
def test_stocktwits_direction_is_dampened_and_weight_capped(self):
    scored = stock_app.score_news_item({
        "title": "AAPL StockTwits 近 30 日多方 8、空方 2",
        "provider": "stocktwits", "source": "StockTwits",
        "external_sentiment_score": 0.6, "social_sample_size": 10,
        "age_hours": 1, "parse_flags": {},
    })
    self.assertAlmostEqual(scored["raw_score"], 0.36)
    self.assertLess(scored["source_weight"], 1)
    self.assertLessEqual(scored["engagement_weight"], 1)

def test_aggregate_reports_source_and_social_coverage(self):
    result = stock_app.analyze_sentiment_detail([
        {"title": "營收創新高", "source": "財經報", "provider": "news", "age_hours": 1},
        {"title": "AAPL 社群偏多", "source": "StockTwits", "provider": "stocktwits",
         "external_sentiment_score": 0.5, "social_sample_size": 10, "age_hours": 1},
    ])
    self.assertEqual(result["source_count"], 2)
    self.assertEqual(result["social_sample_size"], 10)
    self.assertEqual(result["window_days"], 30)
```

- [ ] **Step 2: Run focused tests and verify failure**

Expected: missing `engagement_weight`, `source_count`, `social_sample_size` or `window_days`.

- [ ] **Step 3: Implement the minimum scoring changes**

For `provider == "stocktwits"`, set `raw_score = external_sentiment_score * 0.6`, `source_weight = 0.6`, and `engagement_weight = min(1.0, 0.7 + log1p(sample_size) / 12)`. Other providers keep raw lexicon scoring and `engagement_weight = 1.0`.

Set `final_weight = time_weight * source_weight * event_weight * engagement_weight`. Aggregate distinct `provider` values with `news` as the default provider, sum `social_sample_size`, and return `window_days = 30`.

- [ ] **Step 4: Pass the stock code into the source pipeline**

Change `_do_analyze()` from `get_news(name)` to `get_news(name, code)` and copy `source_count`, `social_sample_size`, and `sentiment_window_days` into the result dictionary.

- [ ] **Step 5: Run Task 2 tests**

Run: `python -m unittest tests.test_prediction_pipeline -v`

Expected: all tests pass and existing five-day probability tests remain unchanged.

### Task 3: LINE／Web 顯示與文件

**Files:**
- Modify: `app.py:1105-1125,1790-1857`
- Modify: `templates/stock_detail.html:57-71`
- Modify: `README.md:3-12,106-113,212-216`
- Modify: `tests/test_prediction_pipeline.py`

- [ ] **Step 1: Write a failing UI regression test**

```python
def test_line_and_web_show_sentiment_source_coverage(self):
    data = sample_analysis_data()
    data.update({
        "s_score": 60.0, "s_status": "偏多", "news_count": 5,
        "news_positive_ratio": 0.6, "news_negative_ratio": 0.2,
        "news_confidence": "中", "news_source_count": 2,
        "social_sample_size": 10,
    })
    with stock_app.app.app_context():
        legacy_html = stock_app.render_web(data)
        template_html = stock_app.render_template("stock_detail.html", d=data)
    flex = json.dumps(
        stock_app.build_stock_flex_message("AAPL", "美股 AAPL", data, "https://example.com"),
        ensure_ascii=False,
    )
    for output in (legacy_html, template_html, flex):
        self.assertIn("新聞／輿論情緒", output)
        self.assertIn("2 個來源", output)
        self.assertIn("社群 10 則", output)
```

- [ ] **Step 2: Run the UI test and verify failure**

Expected: existing output still says `新聞情緒` and lacks coverage text.

- [ ] **Step 3: Implement compact conditional summaries**

Use one small helper to format `N 則｜M 個來源｜社群 K 則｜可信度X`; omit the social segment when `K == 0`. Replace user-facing `新聞情緒` with `新聞／輿論情緒` and `近期新聞` with `近期新聞與輿論`.

- [ ] **Step 4: Document source limits**

README must state StockTwits is only queried for validated US tickers, is self-reported retail sentiment, fails closed, and never directly changes the five-day model probability.

- [ ] **Step 5: Run all verification**

Run: `python -m unittest discover -s tests -v`

Run: `git diff --check`

Expected: all tests pass; diff check emits no output.

- [ ] **Step 6: Commit implementation**

```powershell
git add -- app.py templates/stock_detail.html tests/test_prediction_pipeline.py README.md docs/superpowers/plans/2026-07-04-last30days-sentiment.md
git commit -m "feat: add last30days social sentiment signal"
```

### Task 4: Publish and production verification

**Files:**
- No source changes expected.

- [ ] **Step 1: Push the verified commits**

Run: `git push origin main`

Expected: remote `main` advances to the implementation commit.

- [ ] **Step 2: Deploy a clean tracked-file archive**

Create a temporary directory from `git archive HEAD`, then run:

```powershell
gcloud run deploy line-stock-bot --source <clean-dir> --project line-stock-bot-498908 --region asia-east1 --quiet
```

Expected: a new revision reaches Ready and receives 100% traffic.

- [ ] **Step 3: Verify production**

Check the service URL health endpoint, a Taiwan stock page, and an American stock page. Confirm Cloud Run logs contain no new unhandled StockTwits error and the deployed revision commit matches GitHub.
