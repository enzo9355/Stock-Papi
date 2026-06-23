# Return Calculator and Foreign Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a beginner-friendly return calculator and foreign-flow/chip signal to the stock detail page, then add a button-first LINE calculator flow.

**Architecture:** Keep all calculations inside `app.py` with small pure helper functions. Render Web data through the existing `/stock/<code>` response and use vanilla JS for amount changes. LINE uses postbacks for preset amounts and one text command only for custom amount fallback.

**Tech Stack:** Python 3.10, Flask/Jinja, unittest, vanilla JavaScript, LINE Flex Message JSON.

---

## File map

- Modify `app.py`: add calculator helpers, foreign-flow summary, analysis payload fields, LINE Flex builders, postback/text handling.
- Modify `templates/stock_detail.html`: add two panels below the chart.
- Modify `static/app.js`: recalculate amount display from embedded data and native number input.
- Modify `static/app.css`: style calculator/chip panels with existing panel/card primitives.
- Modify `tests/test_prediction_pipeline.py`: pure calculation and foreign-flow tests.
- Modify `tests/test_web_product.py`: Web page and JS marker tests.
- Modify `tests/test_line_flow.py`: LINE button/postback/text fallback tests.
- Modify `docs/line-to-web-map.md`: note that LINE has a button-first calculator and Web has the full table.

---

### Task 1: Calculation and foreign-flow helpers

**Files:**
- Modify: `tests/test_prediction_pipeline.py`
- Modify: `app.py`

- [ ] **Step 1: Write failing tests**

Add tests to `PredictionPipelineTests`:

```python
    def test_investment_projection_calculates_shares_profit_and_annualized_return(self):
        result = stock_app.calculate_investment_projection(
            100000,
            {"price": 100.0, "bt": {"strat_cum": 8.0, "bh_cum": 5.0, "days": 252}},
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["shares"], 1000)
        self.assertEqual(result["deployed_amount"], 100000)
        self.assertAlmostEqual(result["strategy_profit"], 8000)
        self.assertAlmostEqual(result["buy_hold_profit"], 5000)
        self.assertAlmostEqual(result["strategy_annualized"], 8.0)

    def test_investment_projection_rejects_amount_too_small_for_one_share(self):
        result = stock_app.calculate_investment_projection(
            50,
            {"price": 100.0, "bt": {"strat_cum": 8.0, "bh_cum": 5.0, "days": 252}},
        )

        self.assertFalse(result["ok"])

    def test_merge_chip_data_prefers_foreign_flow_when_available(self):
        price = pd.DataFrame({"Date": pd.to_datetime(["2026-01-02"]), "Close": [100.0]})
        institutional = pd.DataFrame({
            "date": ["2026-01-02", "2026-01-02"],
            "name": ["Foreign_Dealer", "Investment_Trust"],
            "buy": [1000, 500],
            "sell": [200, 100],
        })

        result = stock_app.merge_chip_data(price, institutional)

        self.assertEqual(result.loc[0, "InstitutionalNet"], 1200)
        self.assertEqual(result.loc[0, "ForeignNet"], 800)

    def test_foreign_flow_summary_reports_status_and_missing_data(self):
        frame = pd.DataFrame({"ForeignNet": [100.0] * 20})
        positive = stock_app.summarize_foreign_flow(frame)
        missing = stock_app.summarize_foreign_flow(pd.DataFrame({"ForeignNet": [0.0] * 20}))

        self.assertEqual(positive["status"], "外資偏多")
        self.assertFalse(missing["available"])
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
$env:PYTHONPATH='C:\Users\enzo\Documents\line bot\.deps'; $env:LINE_CHANNEL_ACCESS_TOKEN='test'; $env:LINE_CHANNEL_SECRET='test'; & 'C:\Users\enzo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_prediction_pipeline -v
```

Expected: FAIL because helper functions/fields do not exist.

- [ ] **Step 3: Implement minimal helpers**

In `app.py`:

```python
def _annualized_percent(total_percent, days):
    if not days or days <= 0 or total_percent <= -100:
        return None
    return ((1 + total_percent / 100) ** (252 / days) - 1) * 100


def calculate_investment_projection(amount, data):
    try:
        amount = float(amount)
        price = float(data["price"])
        bt = data["bt"]
    except (KeyError, TypeError, ValueError):
        return {"ok": False}
    if amount <= 0 or price <= 0:
        return {"ok": False}
    shares = int(amount // price)
    if shares <= 0:
        return {"ok": False}
    deployed = shares * price
    strategy_profit = deployed * float(bt.get("strat_cum", 0)) / 100
    buy_hold_profit = deployed * float(bt.get("bh_cum", 0)) / 100
    return {
        "ok": True,
        "amount": amount,
        "shares": shares,
        "deployed_amount": deployed,
        "strategy_profit": strategy_profit,
        "buy_hold_profit": buy_hold_profit,
        "strategy_annualized": _annualized_percent(float(bt.get("strat_cum", 0)), int(bt.get("days", 0))),
        "buy_hold_annualized": _annualized_percent(float(bt.get("bh_cum", 0)), int(bt.get("days", 0))),
    }
```

Extend `merge_chip_data()` to create `ForeignNet` and `_clean_df()` to preserve it. Add `summarize_foreign_flow(df)` and attach `"foreign_flow"` plus `"projection"` in `do_analyze()`.

- [ ] **Step 4: Run tests and verify they pass**

Run the same `tests.test_prediction_pipeline` command.

Expected: PASS.

---

### Task 2: Web panels and client-side amount recalculation

**Files:**
- Modify: `tests/test_web_product.py`
- Modify: `templates/stock_detail.html`
- Modify: `static/app.js`
- Modify: `static/app.css`

- [ ] **Step 1: Write failing tests**

Update `analysis_data()` in `tests/test_web_product.py` with:

```python
        "projection": {
            "ok": True, "amount": 100000, "shares": 1000, "deployed_amount": 100000,
            "strategy_profit": 8000, "buy_hold_profit": 5000,
            "strategy_annualized": 8.0, "buy_hold_annualized": 5.0,
        },
        "foreign_flow": {
            "available": True, "net_5": 1500, "net_20": 3200,
            "status": "外資偏多", "source": "外資",
        },
```

Extend `test_stock_page_is_the_core_analysis_workspace`:

```python
        for label in ["投資金額試算", "外資買賣超", "約可買股數", "外資偏多"]:
            self.assertIn(label, html)
```

Extend `test_browser_bundle_has_no_local_watchlist_storage`:

```python
        self.assertIn("initReturnCalculator", source)
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
$env:PYTHONPATH='C:\Users\enzo\Documents\line bot\.deps'; $env:LINE_CHANNEL_ACCESS_TOKEN='test'; $env:LINE_CHANNEL_SECRET='test'; & 'C:\Users\enzo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_web_product -v
```

Expected: FAIL because labels and JS function are absent.

- [ ] **Step 3: Implement Web panels**

In `templates/stock_detail.html`, add below chart:

```html
  <div class="analysis-grid">
    <section class="panel calculator-panel" data-return-calculator
      data-price="{{ '%.4f'|format(d.price) }}"
      data-strategy-return="{{ '%.6f'|format(d.bt.strat_cum) }}"
      data-buyhold-return="{{ '%.6f'|format(d.bt.bh_cum) }}">
      <div class="section-heading"><div><p class="eyebrow">RETURN CHECK</p><h2>投資金額試算</h2></div></div>
      <label class="amount-field">投入金額<input type="number" min="0" step="1000" value="100000" data-investment-amount></label>
      <div class="indicator-grid">
        <article><span>約可買股數</span><strong data-shares>{{ d.projection.shares if d.projection.ok else '—' }}</strong><small>以最新收盤價估算</small></article>
        <article><span>實際投入</span><strong data-deployed>{{ '%.0f'|format(d.projection.deployed_amount) if d.projection.ok else '—' }}</strong><small>不含手續費與稅</small></article>
        <article><span>AI 策略估算損益</span><strong data-strategy-profit>{{ '%.0f'|format(d.projection.strategy_profit) if d.projection.ok else '—' }}</strong><small>歷史回測換算</small></article>
        <article><span>買進持有估算損益</span><strong data-buyhold-profit>{{ '%.0f'|format(d.projection.buy_hold_profit) if d.projection.ok else '—' }}</strong><small>歷史回測換算</small></article>
      </div>
      <p class="muted small">年化：AI 策略 {{ '%.2f'|format(d.projection.strategy_annualized) if d.projection.strategy_annualized is not none else '—' }}%，買進持有 {{ '%.2f'|format(d.projection.buy_hold_annualized) if d.projection.buy_hold_annualized is not none else '—' }}%。這是歷史回測換算，不代表未來獲利。</p>
    </section>

    <section class="panel foreign-panel">
      <div class="section-heading"><div><p class="eyebrow">FOREIGN FLOW</p><h2>外資買賣超</h2></div><strong class="{{ 'positive' if d.foreign_flow.status == '外資偏多' else 'negative' if d.foreign_flow.status == '外資偏空' else '' }}">{{ d.foreign_flow.status }}</strong></div>
      <div class="indicator-grid">
        <article><span>近 5 日</span><strong>{{ '{:,.0f}'.format(d.foreign_flow.net_5) if d.foreign_flow.available else '—' }}</strong><small>{{ d.foreign_flow.source }}</small></article>
        <article><span>近 20 日</span><strong>{{ '{:,.0f}'.format(d.foreign_flow.net_20) if d.foreign_flow.available else '—' }}</strong><small>籌碼資料可能延遲</small></article>
      </div>
    </section>
  </div>
```

In `static/app.js`, add `initReturnCalculator()` using dataset values and native input events. In `static/app.css`, add only small rules for `.amount-field` and `.calculator-panel`.

- [ ] **Step 4: Run tests and verify they pass**

Run the same `tests.test_web_product` command.

Expected: PASS.

---

### Task 3: LINE button-first calculator

**Files:**
- Modify: `tests/test_line_flow.py`
- Modify: `app.py`
- Modify: `docs/line-to-web-map.md`

- [ ] **Step 1: Write failing tests**

Update `sample_data()` with `"bt"` fields used by the calculator. Update stock card test:

```python
        self.assertEqual([action["type"] for action in actions], ["postback", "postback", "postback", "uri"])
        self.assertEqual(actions[2]["data"], "calc:menu:2330")
```

Add postback tests:

```python
    def test_calculator_menu_replies_with_preset_amount_buttons(self):
        store, line_api = self.call("calc:menu:2330")

        self.assertEqual(store.updated_user_ids, [])
        reply = line_api.reply_message.call_args.args[1]
        self.assertEqual(reply.type, "flex")
        self.assertIn("1 萬", str(reply.contents))
        self.assertIn("calc:amount:2330:100000", str(reply.contents))

    @patch.object(stock_app, "analyze")
    def test_calculator_amount_postback_replies_with_projection(self, analyze):
        analyze.return_value = {
            "code": "2330", "name": "台積電", "price": 100.0,
            "bt": {"strat_cum": 8.0, "bh_cum": 5.0, "days": 252},
        }
        store, line_api = self.call("calc:amount:2330:100000")

        self.assertEqual(store.updated_user_ids, [])
        self.assertIn("約可買", str(line_api.reply_message.call_args.args[1].contents))
```

Add message fallback test:

```python
    def test_text_calculator_command_replies_with_projection(self):
        data = {
            "code": "2330", "name": "台積電", "price": 100.0,
            "bt": {"strat_cum": 8.0, "bh_cum": 5.0, "days": 252},
        }
        line_api = Mock()
        with stock_app.app.test_request_context("/callback", base_url="https://example.com/"), \
             patch.object(stock_app, "line_store", None), \
             patch.object(stock_app, "line_bot_api", line_api), \
             patch.object(stock_app, "search_stock_code", return_value=("2330", "台積電")), \
             patch.object(stock_app, "analyze", return_value=data):
            stock_app.handle_message(message_event("試算 2330 100000"))

        self.assertIn("約可買", str(line_api.reply_message.call_args.args[1].contents))
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
$env:PYTHONPATH='C:\Users\enzo\Documents\line bot\.deps'; $env:LINE_CHANNEL_ACCESS_TOKEN='test'; $env:LINE_CHANNEL_SECRET='test'; & 'C:\Users\enzo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_line_flow -v
```

Expected: FAIL because calculator postbacks and Flex builders are absent.

- [ ] **Step 3: Implement LINE builders and routes**

In `app.py`:

- Add a `投資試算` postback button to stock card footer: `calc:menu:<code>`.
- Accept `calc:menu:<code>` and `calc:amount:<code>:<amount>` in `handle_postback()`.
- Add `build_calculator_menu_flex(code, name)` with buttons for 10000, 50000, 100000 and custom text hint.
- Add `build_projection_flex(code, name, data, amount, base_url)` using `calculate_investment_projection()`.
- Add text command parsing near the top of `handle_message()`:

```python
calc_text = re.fullmatch(r"試算\s+([A-Za-z0-9]+)\s+([0-9]+(?:\.[0-9]+)?)", msg)
```

- [ ] **Step 4: Update docs**

In `docs/line-to-web-map.md`, add a short row/note that `投資試算` starts in LINE buttons and full details live in `/stock/<code>`.

- [ ] **Step 5: Run targeted tests**

Run:

```powershell
$env:PYTHONPATH='C:\Users\enzo\Documents\line bot\.deps'; $env:LINE_CHANNEL_ACCESS_TOKEN='test'; $env:LINE_CHANNEL_SECRET='test'; & 'C:\Users\enzo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_line_flow tests.test_web_product tests.test_prediction_pipeline -v
```

Expected: PASS.

---

### Task 4: Full verification and commit

**Files:**
- Verify all modified files.

- [ ] **Step 1: Run full test suite**

Run:

```powershell
$env:PYTHONPATH='C:\Users\enzo\Documents\line bot\.deps'; $env:LINE_CHANNEL_ACCESS_TOKEN='test'; $env:LINE_CHANNEL_SECRET='test'; & 'C:\Users\enzo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s tests -v
```

Expected: all tests pass.

- [ ] **Step 2: Run syntax/static checks**

Run:

```powershell
$env:PYTHONPATH='C:\Users\enzo\Documents\line bot\.deps'; $env:LINE_CHANNEL_ACCESS_TOKEN='test'; $env:LINE_CHANNEL_SECRET='test'; & 'C:\Users\enzo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m py_compile app.py line_state.py
node --check static/app.js
git diff --check
```

Expected: no output/errors.

- [ ] **Step 3: Commit**

Run:

```powershell
git add app.py templates/stock_detail.html static/app.js static/app.css tests/test_prediction_pipeline.py tests/test_web_product.py tests/test_line_flow.py docs/line-to-web-map.md docs/superpowers/plans/2026-06-23-return-calculator-foreign-flow.md
git commit -m "feat: add return calculator and foreign flow"
```

Expected: one feature commit.
