# Stock Papi Web Usability Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓使用者可從根網址直接進入網站、快速搜尋股票，並以清楚的頁內導覽、回測與情緒拆解完成個股判讀。

**Architecture:** 延用現有 Flask route、Jinja template、Vanilla JS 與 CSS。搜尋使用無副作用的 GET route；資料顯示沿用現有 `analyze()` 與 Dashboard API，不新增外部請求或前端依賴。

**Tech Stack:** Python 3.10、Flask、Jinja2、Vanilla JavaScript、CSS、Lightweight Charts、unittest。

---

### Task 1: 根網址、股票搜尋與 Dashboard 資料

**Files:**
- Modify: `app.py`
- Test: `tests/test_web_product.py`

- [ ] **Step 1: 寫失敗測試**

```python
def test_root_renders_dashboard_and_search_redirects_known_stock(self):
    client = stock_app.app.test_client()
    root = client.get("/")
    found = client.get("/search?q=台積電")
    missing = client.get("/search?q=不存在股票", follow_redirects=True)
    self.assertEqual(root.status_code, 200)
    self.assertIn("Stock Papi", root.get_data(as_text=True))
    self.assertTrue(found.headers["Location"].endswith("/stock/2330"))
    self.assertIn("找不到", missing.get_data(as_text=True))
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python -m unittest tests.test_web_product.WebProductTests.test_root_renders_dashboard_and_search_redirects_known_stock -v`

Expected: FAIL，根網址仍回傳健康文字且 `/search` 為 404。

- [ ] **Step 3: 實作最小 route**

```python
@app.route("/")
@app.route("/dashboard")
def dashboard_page():
    return render_template(
        "dashboard.html",
        search_query=request.args.get("q", "").strip(),
        search_error=request.args.get("error") == "not-found",
    )

@app.route("/search")
def search_page():
    query = request.args.get("q", "").strip()
    code, _name = search_stock_code(query)
    if code:
        return redirect(url_for("stock_page", code=code), code=302)
    return redirect(url_for("dashboard_page", q=query, error="not-found"), code=302)

@app.route("/healthz")
def healthz():
    return "ok", 200
```

Dashboard API 的 `market` 增加既有欄位：`as_of`、`sentiment_status`、`sentiment_score`、`confidence`。

- [ ] **Step 4: 執行 Web 測試**

Run: `python -m unittest tests.test_web_product -v`

Expected: PASS。

### Task 2: Dashboard 搜尋與資訊定位

**Files:**
- Modify: `templates/base.html`
- Modify: `templates/dashboard.html`
- Modify: `static/app.css`
- Modify: `static/app.js`
- Test: `tests/test_web_product.py`

- [ ] **Step 1: 寫失敗測試**

```python
def test_dashboard_has_real_search_and_section_navigation(self):
    html = stock_app.app.test_client().get("/dashboard").get_data(as_text=True)
    for marker in ('action="/search"', 'name="q"', 'id="market-pulse"',
                   'id="industry-forecast"', 'id="top-picks"', 'id="learn"'):
        self.assertIn(marker, html)
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python -m unittest tests.test_web_product.WebProductTests.test_dashboard_has_real_search_and_section_navigation -v`

Expected: FAIL，缺少搜尋表單與錨點。

- [ ] **Step 3: 實作 Jinja 與 CSS**

Hero 使用原生表單：

```html
<form class="stock-search" action="{{ url_for('search_page') }}" method="get" role="search">
  <label for="stock-search">搜尋股票</label>
  <div class="search-control glass-panel">
    <input id="stock-search" name="q" value="{{ search_query }}" placeholder="輸入 2330、台積電或 AAPL" required>
    <button type="submit">查看分析</button>
  </div>
</form>
```

各首頁區塊加入固定 `id`；側欄與 Hero 快捷列使用錨點。Dashboard JS 將 `as_of`、`sentiment_status` 與 `confidence` 放入市場摘要，不新增 fetch。

- [ ] **Step 4: 執行 Web 與 JS 語法測試**

Run: `python -m unittest tests.test_web_product -v`

Run: `node --check static/app.js`

Expected: 兩者 PASS。

### Task 3: 個股頁導覽、回測、試算按鈕與情緒篩選

**Files:**
- Modify: `templates/stock_detail.html`
- Modify: `static/app.css`
- Modify: `static/app.js`
- Test: `tests/test_web_product.py`

- [ ] **Step 1: 寫失敗測試**

```python
@patch.object(stock_app, "analyze", return_value=analysis_data())
def test_stock_page_has_guided_analysis_controls(self, _analyze):
    html = stock_app.app.test_client().get("/stock/2330").get_data(as_text=True)
    for marker in ('class="page-jump-nav"', 'data-amount-preset="10000"',
                   'id="backtest"', 'id="sentiment"', 'data-news-filter="positive"'):
        self.assertIn(marker, html)
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python -m unittest tests.test_web_product.WebProductTests.test_stock_page_has_guided_analysis_controls -v`

Expected: FAIL，控制項尚不存在。

- [ ] **Step 3: 實作模板**

加入：

```html
<nav class="page-jump-nav" aria-label="個股分析快速導覽">
  <a href="#summary">摘要</a><a href="#chart">圖表</a><a href="#calculator">試算</a>
  <a href="#backtest">回測</a><a href="#sentiment">情緒</a><a href="#risk">風險</a>
</nav>
```

試算輸入下方加入三個 `data-amount-preset` 按鈕；回測區直接顯示 `strat_cum`、`bh_cum`、`win_rate`、`mdd`、`trades`、`brier`；情緒區顯示 `news_momentum`、`news_weighted_volatility`、`news_disagreement`、`news_effective_sample_size`、`news_publisher_count` 與 metadata 完整度。

新聞連結只加 `data-news-direction="{{ item.direction }}"`，外部標題仍由 Jinja escape。

- [ ] **Step 4: 實作既有 DOM 的互動**

```javascript
document.addEventListener("click", (event) => {
  const preset = event.target.closest("[data-amount-preset]");
  if (preset) {
    const input = bySelector("[data-investment-amount]");
    input.value = preset.dataset.amountPreset;
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }
  const filter = event.target.closest("[data-news-filter]");
  if (filter) {
    const direction = filter.dataset.newsFilter;
    document.querySelectorAll("[data-news-direction]").forEach((item) => {
      item.hidden = direction !== "all" && item.dataset.newsDirection !== direction;
    });
  }
});
```

- [ ] **Step 5: 執行 Web 與 JS 測試**

Run: `python -m unittest tests.test_web_product -v`

Run: `node --check static/app.js`

Expected: PASS。

### Task 4: 響應式、完整驗證與發布

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 增加 390px 與可及性 CSS 斷言**

測試 `.page-jump-nav` 具 `overflow-x:auto`、搜尋按鈕至少 44px、760px 以下卡片單欄、`prefers-reduced-motion` 保留。

- [ ] **Step 2: 更新 README**

說明根網址、股票搜尋、頁內導覽、快速試算、回測摘要與情緒拆解；維持 Web 不管理關注與提醒。

- [ ] **Step 3: 執行完整驗證**

Run: `python -m unittest discover -s tests -v`

Run: `python -m py_compile app.py local_quant.py line_state.py`

Run: `node --check static/app.js`

Run: `git diff --check`

Expected: 全部 exit 0。

- [ ] **Step 4: 瀏覽器驗證**

啟動本機 Flask，驗證 `/`、`/dashboard` 與 mock 個股頁的桌機／390px 手機寬度；檢查搜尋、錨點、試算按鈕、新聞篩選、水平溢位與圖表尺寸。

- [ ] **Step 5: 安全掃描、提交與部署**

Run: `shellward scan --json .`

Run: `agy --sandbox --print "唯讀審查目前 git diff"`

只提交本次檔案，推送 `main`，再部署 Cloud Run；確認新 revision 100% 流量且 `/dashboard`、`/healthz` 回應 200。

