# LINE Native Watchlist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move watchlists, alert setup, alert delivery, and personalized strong signals into LINE while keeping Web focused on detailed analysis.

**Architecture:** `app.py` remains the Flask and LINE entry point. A new dependency-free `line_state.py` owns validated user state and Firestore REST persistence; Cloud Scheduler calls one authenticated Flask task endpoint that analyzes the union of watched stocks once and pushes idempotent LINE alerts.

**Tech Stack:** Python 3.10 stdlib, Flask, `requests`, LINE Messaging API, Firestore REST API, Cloud Scheduler, existing unittest suite.

---

## Command convention

Run PowerShell commands from `C:\Users\enzo\Documents\line bot`. At the start of each execution session set:

```powershell
$env:PATH='C:\Users\enzo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python;' + $env:PATH
$env:PYTHONPATH='C:\Users\enzo\Documents\line bot\.deps'
$env:LINE_CHANNEL_ACCESS_TOKEN='test'
$env:LINE_CHANNEL_SECRET='test'
```

## File map

- Create `line_state.py`: state schema, watchlist/alert rules, metadata access token, Firestore REST reads and optimistic writes.
- Create `tests/test_line_state.py`: pure state and Firestore transport tests.
- Modify `app.py`: LINE postbacks, pending alert input, watchlist/strong-signal Flex messages, scheduler endpoint and data date.
- Create `tests/test_line_flow.py`: LINE-facing builders and scheduled alert behavior.
- Modify `templates/base.html`, `templates/dashboard.html`, `templates/stock_detail.html`, `static/app.js`, `static/app.css`: remove browser-side watchlist and alert UI.
- Delete `templates/watchlist.html`.
- Modify `tests/test_web_product.py`: enforce Web-only analysis behavior and compatibility redirect.
- Modify `docs/line-to-web-map.md`: document the final client boundary.

### Task 1: Pure LINE user state and alert rules

**Files:**
- Create: `line_state.py`
- Create: `tests/test_line_state.py`

- [ ] **Step 1: Write failing state tests**

```python
# tests/test_line_state.py
import unittest
from line_state import (
    StateError, add_alert, add_watch, consume_pending, empty_state,
    evaluate_alert, normalize_state, remove_watch, start_pending, top_signals,
)


class LineStateTests(unittest.TestCase):
    def test_watchlist_is_unique_and_limited_to_twelve(self):
        state = empty_state()
        for number in range(12):
            add_watch(state, str(1000 + number), f"股票{number}", now=1)
        add_watch(state, "1000", "股票0", now=2)
        self.assertEqual(len(state["watchlist"]), 12)
        with self.assertRaises(StateError):
            add_watch(state, "9999", "第十三檔", now=3)

    def test_pending_numeric_alert_expires_and_validates_probability(self):
        state = empty_state()
        start_pending(state, "2330", "台積電", "probability", now=100)
        with self.assertRaises(StateError):
            consume_pending(state, "100", now=101)
        start_pending(state, "2330", "台積電", "probability", now=100)
        alert = consume_pending(state, "65", now=101)
        self.assertEqual((alert["kind"], alert["value"]), ("probability", 65.0))
        start_pending(state, "2330", "台積電", "price", now=100)
        with self.assertRaises(StateError):
            consume_pending(state, "900", now=701)

    def test_alert_evaluation_and_signal_sorting(self):
        quote = {"code": "2330", "price": 1000.0, "prob": 68, "trend": "多頭"}
        self.assertTrue(evaluate_alert({"kind": "price", "value": 990}, quote))
        self.assertTrue(evaluate_alert({"kind": "probability", "value": 65}, quote))
        self.assertTrue(evaluate_alert({"kind": "trend", "value": "多頭"}, quote))
        items = top_signals([
            {"code": "2317", "prob": 55}, {"code": "2330", "prob": 68}
        ])
        self.assertEqual([item["code"] for item in items], ["2330", "2317"])

    def test_normalize_state_drops_unknown_and_malformed_values(self):
        state = normalize_state({"watchlist": "bad", "alerts": None, "extra": True})
        self.assertEqual(state, empty_state())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='.deps'; python -m unittest tests.test_line_state.LineStateTests -v
```

Expected: `ModuleNotFoundError: No module named 'line_state'`.

- [ ] **Step 3: Implement the minimum state module**

```python
# line_state.py
import copy
import time
import uuid

MAX_WATCHLIST = 12
MAX_ALERTS = 20
PENDING_SECONDS = 600


class StateError(ValueError):
    pass


def empty_state():
    return {"watchlist": [], "alerts": [], "pending": None, "signals": {"as_of": None, "items": []}}


def normalize_state(value):
    state = empty_state()
    if not isinstance(value, dict):
        return state
    if isinstance(value.get("watchlist"), list):
        state["watchlist"] = [item for item in value["watchlist"] if isinstance(item, dict) and isinstance(item.get("code"), str) and item["code"].isalnum() and isinstance(item.get("name"), str)][:MAX_WATCHLIST]
    if isinstance(value.get("alerts"), list):
        state["alerts"] = [item for item in value["alerts"] if isinstance(item, dict) and item.get("kind") in {"price", "probability", "trend"} and isinstance(item.get("code"), str) and isinstance(item.get("id"), str)][:MAX_ALERTS]
    if isinstance(value.get("pending"), dict):
        state["pending"] = value["pending"]
    if isinstance(value.get("signals"), dict):
        state["signals"] = {
            "as_of": value["signals"].get("as_of"),
            "items": value["signals"].get("items", [])[:5] if isinstance(value["signals"].get("items"), list) else [],
        }
    return state


def add_watch(state, code, name, now=None):
    if not isinstance(code, str) or not code.isalnum() or not isinstance(name, str) or not name.strip():
        raise StateError("股票資料格式錯誤")
    if any(item.get("code") == code for item in state["watchlist"]):
        return state
    if len(state["watchlist"]) >= MAX_WATCHLIST:
        raise StateError("關注清單最多 12 檔")
    state["watchlist"].append({"code": code, "name": name, "added_at": now or time.time()})
    return state


def remove_watch(state, code):
    state["watchlist"] = [item for item in state["watchlist"] if item.get("code") != code]
    state["alerts"] = [item for item in state["alerts"] if item.get("code") != code]
    return state


def start_pending(state, code, name, kind, now=None):
    if kind not in {"price", "probability"}:
        raise StateError("不支援的提醒類型")
    now = now or time.time()
    state["pending"] = {"code": code, "name": name, "kind": kind, "expires_at": now + PENDING_SECONDS}
    return state


def add_alert(state, code, name, kind, value):
    if kind not in {"price", "probability", "trend"}:
        raise StateError("不支援的提醒類型")
    if kind == "trend" and value not in {"多頭", "空頭"}:
        raise StateError("趨勢條件格式錯誤")
    if len(state["alerts"]) >= MAX_ALERTS:
        raise StateError("提醒最多 20 條")
    alert = {"id": uuid.uuid4().hex, "code": code, "name": name, "kind": kind, "value": value, "enabled": True, "last_triggered_date": None}
    state["alerts"].append(alert)
    return alert


def consume_pending(state, text, now=None):
    pending = state.get("pending")
    now = now or time.time()
    if not pending or pending.get("expires_at", 0) < now:
        state["pending"] = None
        raise StateError("提醒設定已逾時")
    try:
        value = float(text)
    except (TypeError, ValueError) as error:
        raise StateError("請輸入有效數字") from error
    if pending["kind"] == "price" and value <= 0:
        raise StateError("價格必須大於 0")
    if pending["kind"] == "probability" and not 1 <= value <= 99:
        raise StateError("機率必須介於 1 到 99")
    alert = add_alert(state, pending["code"], pending["name"], pending["kind"], value)
    state["pending"] = None
    return alert


def evaluate_alert(alert, quote):
    if alert["kind"] == "price":
        return quote["price"] >= float(alert["value"])
    if alert["kind"] == "probability":
        return quote["prob"] >= float(alert["value"])
    return alert["kind"] == "trend" and quote["trend"] == alert["value"]


def top_signals(quotes):
    return sorted((copy.deepcopy(item) for item in quotes), key=lambda item: item["prob"], reverse=True)[:5]
```

- [ ] **Step 4: Run tests and verify GREEN**

Run the Step 2 command. Expected: four tests pass.

- [ ] **Step 5: Commit**

```powershell
git add line_state.py tests/test_line_state.py
git commit -m "feat: add LINE watchlist state rules"
```

### Task 2: Firestore REST persistence with optimistic writes

**Files:**
- Modify: `line_state.py`
- Modify: `tests/test_line_state.py`

- [ ] **Step 1: Add failing persistence tests**

Add a small `FakeResponse` and mock `requests.Session.request`. Verify these concrete behaviors:

```python
from unittest.mock import Mock
from line_state import FirestoreStore, StoreConflict

def test_firestore_document_round_trip_uses_update_time(self):
    session = Mock()
    session.request.side_effect = [
        Mock(status_code=200, json=lambda: {"fields": {"state": {"stringValue": '{"watchlist": []}'}}, "updateTime": "v1"}),
        Mock(status_code=200, json=lambda: {"updateTime": "v2"}),
    ]
    store = FirestoreStore("project", session=session, token_provider=lambda: "token")
    state, version = store.load("U123")
    store.save("U123", state, version)
    self.assertEqual(version, "v1")
    self.assertEqual(session.request.call_args.kwargs["params"]["currentDocument.updateTime"], "v1")

def test_firestore_update_retries_one_conflict(self):
    store = Mock(spec=FirestoreStore)
    store.load.side_effect = [(empty_state(), "v1"), (empty_state(), "v2")]
    store.save.side_effect = [StoreConflict(), "v3"]
    result = FirestoreStore.update(store, "U123", lambda state: add_watch(state, "2330", "台積電"))
    self.assertEqual(result["watchlist"][0]["code"], "2330")
    self.assertEqual(store.save.call_count, 2)
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
$env:PYTHONPATH='.deps'; python -m unittest tests.test_line_state -v
```

Expected: import failure for `FirestoreStore`.

- [ ] **Step 3: Implement Firestore REST methods**

Add to `line_state.py`:

```python
import json
import os
import urllib.parse
import requests

METADATA_TOKEN_URL = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"


class StoreError(RuntimeError):
    pass


class StoreConflict(StoreError):
    pass


class FirestoreStore:
    def __init__(self, project_id, session=None, token_provider=None):
        self.project_id = project_id
        self.session = session or requests.Session()
        self.token_provider = token_provider or self._metadata_token
        self._cached_token = None
        self._token_expires = 0

    @property
    def collection_url(self):
        return f"https://firestore.googleapis.com/v1/projects/{self.project_id}/databases/(default)/documents/line_users"

    def _metadata_token(self):
        now = time.time()
        if self._cached_token and now < self._token_expires:
            return self._cached_token
        response = self.session.get(METADATA_TOKEN_URL, headers={"Metadata-Flavor": "Google"}, timeout=3)
        response.raise_for_status()
        payload = response.json()
        self._cached_token = payload["access_token"]
        self._token_expires = now + int(payload["expires_in"]) - 60
        return self._cached_token

    def _headers(self):
        return {"Authorization": f"Bearer {self.token_provider()}", "Content-Type": "application/json"}

    def load(self, user_id):
        url = f"{self.collection_url}/{urllib.parse.quote(user_id, safe='')}"
        response = self.session.request("GET", url, headers=self._headers(), timeout=5)
        if response.status_code == 404:
            return empty_state(), None
        if response.status_code != 200:
            raise StoreError(f"Firestore read failed: {response.status_code}")
        document = response.json()
        raw = document.get("fields", {}).get("state", {}).get("stringValue", "{}")
        try:
            state = normalize_state(json.loads(raw))
        except (TypeError, ValueError):
            state = empty_state()
        return state, document.get("updateTime")

    def save(self, user_id, state, update_time):
        url = f"{self.collection_url}/{urllib.parse.quote(user_id, safe='')}"
        params = {"updateMask.fieldPaths": "state"}
        if update_time:
            params["currentDocument.updateTime"] = update_time
        body = {"fields": {"state": {"stringValue": json.dumps(normalize_state(state), ensure_ascii=False, separators=(",", ":"))}}}
        response = self.session.request("PATCH", url, headers=self._headers(), params=params, json=body, timeout=5)
        if response.status_code in {409, 412}:
            raise StoreConflict()
        if response.status_code != 200:
            raise StoreError(f"Firestore write failed: {response.status_code}")
        return response.json().get("updateTime")

    def update(self, user_id, mutate):
        for attempt in range(2):
            state, version = self.load(user_id)
            mutate(state)
            try:
                self.save(user_id, state, version)
                return state
            except StoreConflict:
                if attempt == 1:
                    raise
        raise StoreConflict()

    def iter_users(self):
        page_token = None
        while True:
            params = {"pageSize": 100}
            if page_token:
                params["pageToken"] = page_token
            response = self.session.request("GET", self.collection_url, headers=self._headers(), params=params, timeout=10)
            if response.status_code != 200:
                raise StoreError(f"Firestore list failed: {response.status_code}")
            payload = response.json()
            for document in payload.get("documents", []):
                user_id = urllib.parse.unquote(document["name"].rsplit("/", 1)[-1])
                raw = document.get("fields", {}).get("state", {}).get("stringValue", "{}")
                try:
                    yield user_id, normalize_state(json.loads(raw)), document.get("updateTime")
                except (TypeError, ValueError):
                    yield user_id, empty_state(), document.get("updateTime")
            page_token = payload.get("nextPageToken")
            if not page_token:
                return
```

- [ ] **Step 4: Add pagination, 404 and second-conflict tests**

```python
def test_firestore_missing_document_returns_empty_state(self):
    session = Mock()
    session.request.return_value = Mock(status_code=404)
    store = FirestoreStore("project", session=session, token_provider=lambda: "token")
    self.assertEqual(store.load("U123"), (empty_state(), None))

def test_firestore_list_follows_page_token(self):
    session = Mock()
    first = Mock(status_code=200, json=lambda: {"documents": [], "nextPageToken": "next"})
    second = Mock(status_code=200, json=lambda: {"documents": []})
    session.request.side_effect = [first, second]
    store = FirestoreStore("project", session=session, token_provider=lambda: "token")
    self.assertEqual(list(store.iter_users()), [])
    self.assertEqual(session.request.call_args.kwargs["params"]["pageToken"], "next")

def test_firestore_update_stops_after_second_conflict(self):
    store = Mock(spec=FirestoreStore)
    store.load.return_value = (empty_state(), "v1")
    store.save.side_effect = StoreConflict()
    with self.assertRaises(StoreConflict):
        FirestoreStore.update(store, "U123", lambda state: state)
    self.assertEqual(store.save.call_count, 2)
```

Run the Step 2 command. Expected: all `test_line_state` tests pass.

- [ ] **Step 5: Commit**

```powershell
git add line_state.py tests/test_line_state.py
git commit -m "feat: persist LINE user state in Firestore"
```

### Task 3: LINE-native watchlist and alert conversation

**Files:**
- Modify: `app.py`
- Create: `tests/test_line_flow.py`

- [ ] **Step 1: Write failing LINE flow tests**

Use existing unittest and patched `line_bot_api`. Tests must assert:

```python
def test_stock_flex_has_line_actions_and_one_web_analysis_uri():
    card = stock_app.build_stock_flex_message("2330", "台積電", sample_data(), "https://example.com/stock/2330", watched=False)
    actions = [item["action"] for item in card["footer"]["contents"]]
    self.assertEqual([action["type"] for action in actions], ["postback", "postback", "uri"])
    self.assertEqual(actions[-1]["uri"], "https://example.com/stock/2330")

def test_watchlist_flex_stays_inside_line_except_analysis_links():
    state = {"watchlist": [{"code": "2330", "name": "台積電"}], "signals": {"as_of": "2026-06-22", "items": []}}
    message = stock_app.build_watchlist_flex(state, "https://example.com")
    self.assertIn("2330", str(message))
    self.assertNotIn("/watchlist", str(message))
```

Use `SimpleNamespace` events and verify the postback boundary directly:

```python
from types import SimpleNamespace

def postback_event(data):
    return SimpleNamespace(
        source=SimpleNamespace(user_id="U123"),
        postback=SimpleNamespace(data=data),
        reply_token="reply",
    )

@patch.object(stock_app, "line_bot_api")
@patch.object(stock_app, "line_store")
def test_watch_add_postback_updates_current_line_user(self, store, line_api):
    store.update.side_effect = lambda user_id, mutate: mutate(empty_state())
    stock_app.handle_postback(postback_event("watch:add:2330"))
    self.assertEqual(store.update.call_args.args[0], "U123")
    line_api.reply_message.assert_called_once()

@patch.object(stock_app, "line_bot_api")
@patch.object(stock_app, "line_store")
def test_alert_start_postback_saves_pending_state(self, store, line_api):
    captured = {}
    def update(user_id, mutate):
        captured["state"] = empty_state()
        mutate(captured["state"])
        return captured["state"]
    store.update.side_effect = update
    stock_app.handle_postback(postback_event("alert:start:2330:probability"))
    self.assertEqual(captured["state"]["pending"]["kind"], "probability")
    line_api.reply_message.assert_called_once()
```

Add equivalent table-driven cases for `watch:remove`, `alert:trend` and `alert:remove`. For pending numeric text and `取消`, call `handle_message` with `SimpleNamespace(message=SimpleNamespace(text="65"), source=SimpleNamespace(user_id="U123"), reply_token="reply")`; assert numeric input creates one alert while cancellation clears pending without creating one.

- [ ] **Step 2: Run and verify RED**

```powershell
$env:PYTHONPATH='.deps'; $env:LINE_CHANNEL_ACCESS_TOKEN='test'; $env:LINE_CHANNEL_SECRET='test'; python -m unittest tests.test_line_flow -v
```

Expected: missing `build_watchlist_flex` and unsupported `watched` argument.

- [ ] **Step 3: Add the lightweight store and LINE actions**

In `app.py`:

```python
from linebot.models import PostbackEvent
from line_state import FirestoreStore, StateError, StoreError, add_alert, add_watch, consume_pending, remove_watch, start_pending

GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
line_store = FirestoreStore(GCP_PROJECT_ID) if GCP_PROJECT_ID else None


def get_line_state(user_id):
    if not line_store:
        raise StoreError("Firestore is not configured")
    return line_store.load(user_id)[0]


def update_line_state(user_id, mutate):
    if not line_store:
        raise StoreError("Firestore is not configured")
    return line_store.update(user_id, mutate)
```

Change `build_stock_flex_message(..., watched=False)` so its footer contains exactly these three actions:

```python
[
    {"type": "button", "style": "secondary", "action": {"type": "postback", "label": "移除關注" if watched else "加入關注", "data": f"watch:{'remove' if watched else 'add'}:{code}"}},
    {"type": "button", "style": "secondary", "action": {"type": "postback", "label": "設定提醒", "data": f"alert:menu:{code}"}},
    {"type": "button", "style": "primary", "color": "#39c6a3", "action": {"type": "uri", "label": "查看完整分析", "uri": url}},
]
```

Add these exact builder interfaces:

```python
def build_watchlist_flex(state, base_url):
    return {"type": "carousel", "contents": [build_line_stock_action_card(item, base_url) for item in state["watchlist"]]}

def build_alert_menu_flex(code, name):
    return build_line_choice_card(
        f"設定 {name} 提醒",
        [("收盤價門檻", f"alert:start:{code}:price"), ("機率門檻", f"alert:start:{code}:probability"),
         ("趨勢轉多", f"alert:trend:{code}:多頭"), ("趨勢轉空", f"alert:trend:{code}:空頭")],
    )

def build_strong_signals_flex(state, base_url):
    return build_line_signal_carousel(state["signals"]["items"], state["signals"]["as_of"], base_url)
```

`build_line_stock_action_card`, `build_line_choice_card` and `build_line_signal_carousel` return raw LINE Flex dictionaries and escape no text because values are passed as JSON fields, not HTML. Each signal card has one URI action to `/stock/<code>`.

Add `@handler.add(PostbackEvent)` and dispatch only validated payloads matching:

```text
watch:add:<code>
watch:remove:<code>
alert:menu:<code>
alert:start:<code>:price
alert:start:<code>:probability
alert:trend:<code>:多頭
alert:trend:<code>:空頭
alert:remove:<alert_id>
```

Resolve `<code>` through `search_stock_code`; reject unknown codes and unknown operations. For numeric text, load pending state before stock lookup; `取消` clears pending. Add `我的關注` and `強勢訊號` branches that read Firestore and reply inside LINE.

Wrap every store operation in `except (StoreError, StateError)` and reply with the exception's safe Chinese message; never include `userId`, access tokens or raw Firestore response bodies in user replies or logs.

- [ ] **Step 4: Run LINE flow and full regression tests**

```powershell
$env:PYTHONPATH='.deps'; $env:LINE_CHANNEL_ACCESS_TOKEN='test'; $env:LINE_CHANNEL_SECRET='test'; python -m unittest tests.test_line_flow -v
python -m unittest discover -s tests -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add app.py tests/test_line_flow.py
git commit -m "feat: manage watchlists and alerts in LINE"
```

### Task 4: Scheduled strong signals and LINE push alerts

**Files:**
- Modify: `app.py`
- Modify: `tests/test_line_flow.py`

- [ ] **Step 1: Write failing scheduler tests**

Add the complete scheduler test fixture and tests:

```python
class FakeStore:
    def __init__(self, states):
        self.states = states

    def iter_users(self):
        for user_id, state in self.states.items():
            yield user_id, state, "v1"

    def update(self, user_id, mutate):
        mutate(self.states[user_id])
        return self.states[user_id]


def test_alert_task_requires_configured_constant_time_token():
    with patch.object(stock_app, "ALERT_TASK_TOKEN", None):
        self.assertEqual(stock_app.app.test_client().post("/tasks/check-alerts").status_code, 503)
    with patch.object(stock_app, "ALERT_TASK_TOKEN", "secret"):
        self.assertEqual(stock_app.app.test_client().post("/tasks/check-alerts", headers={"Authorization": "Bearer wrong"}).status_code, 403)

def test_scheduled_scan_analyzes_each_code_once_and_marks_only_successful_pushes():
    alert = {"id": "a1", "code": "2330", "kind": "probability", "value": 65, "enabled": True, "last_triggered_date": None}
    states = {
        "U1": {**empty_state(), "watchlist": [{"code": "2330", "name": "台積電"}], "alerts": [dict(alert)]},
        "U2": {**empty_state(), "watchlist": [{"code": "2330", "name": "台積電"}], "alerts": [dict(alert)]},
    }
    store = FakeStore(states)
    analyze = Mock(return_value=sample_data(code="2330", as_of="2026-06-22", prob=70))
    push = Mock()
    stock_app.run_alert_checks(store, analyze, push, "2026-06-22", "https://example.com")
    self.assertEqual(analyze.call_count, 1)
    self.assertEqual(push.call_count, 2)
    self.assertTrue(all(state["alerts"][0]["last_triggered_date"] == "2026-06-22" for state in states.values()))

def test_push_failure_does_not_mark_alert_triggered(self):
    state = {**empty_state(), "watchlist": [{"code": "2330", "name": "台積電"}], "alerts": [{"id": "a1", "code": "2330", "kind": "probability", "value": 65, "enabled": True, "last_triggered_date": None}]}
    store = FakeStore({"U1": state})
    with self.assertRaises(RuntimeError):
        stock_app.run_alert_checks(store, lambda code: sample_data(code=code, as_of="2026-06-22", prob=70), Mock(side_effect=RuntimeError("push failed")), "2026-06-22", "https://example.com")
    self.assertIsNone(state["alerts"][0]["last_triggered_date"])

def test_stale_market_date_does_not_push_again(self):
    state = {**empty_state(), "watchlist": [{"code": "2330", "name": "台積電"}], "signals": {"as_of": "2026-06-22", "items": []}}
    push = Mock()
    stock_app.run_alert_checks(FakeStore({"U1": state}), lambda code: sample_data(code=code, as_of="2026-06-22", prob=70), push, "2026-06-23", "https://example.com")
    push.assert_not_called()
```

- [ ] **Step 2: Run and verify RED**

Run the Task 3 Step 4 targeted command. Expected: missing `run_alert_checks` and route 404.

- [ ] **Step 3: Add analysis date, scan function and authenticated endpoint**

Add `"as_of": str(df.index[-1].date())` to `_do_analyze()` output.

In `app.py`:

```python
ALERT_TASK_TOKEN = os.getenv("ALERT_TASK_TOKEN")


def run_alert_checks(store, analyze_fn, push_fn, today, base_url):
    users = list(store.iter_users())
    codes = sorted({item["code"] for _, state, _ in users for item in state["watchlist"]})
    quotes = {code: analyze_fn(code) for code in codes}
    quotes = {code: quote for code, quote in quotes.items() if quote}
    for user_id, state, _version in users:
        watched = [quotes[item["code"]] for item in state["watchlist"] if item["code"] in quotes]
        newest = max((item["as_of"] for item in watched), default=None)
        if not newest or state["signals"].get("as_of") == newest:
            continue
        signals = {"as_of": newest, "items": top_signals(watched)}
        hits = []
        for alert in state["alerts"]:
            quote = quotes.get(alert["code"])
            if alert.get("enabled") and quote and alert.get("last_triggered_date") != today and evaluate_alert(alert, quote):
                hits.append((alert, quote))
        if hits:
            push_fn(user_id, build_alert_push_flex(hits, base_url))
        triggered_ids = {alert["id"] for alert, _quote in hits}
        def merge_scan(current):
            current["signals"] = signals
            for alert in current["alerts"]:
                if alert.get("id") in triggered_ids:
                    alert["last_triggered_date"] = today
        store.update(user_id, merge_scan)


@app.post("/tasks/check-alerts")
def check_alerts_task():
    if not ALERT_TASK_TOKEN:
        return "alert task is not configured", 503
    supplied = request.headers.get("Authorization", "").removeprefix("Bearer ")
    if not hmac.compare_digest(supplied, ALERT_TASK_TOKEN):
        abort(403)
    run_alert_checks(line_store, analyze, lambda user_id, flex: line_bot_api.push_message(user_id, FlexSendMessage(alt_text="關注股票提醒", contents=flex)), datetime.date.today().isoformat(), request.host_url.rstrip("/"))
    return "OK", 200
```

Import `evaluate_alert` and `top_signals`. Ensure the endpoint returns 503 when Firestore is not configured. Build `build_alert_push_flex` with one bubble per hit and one Web CTA per bubble.

- [ ] **Step 4: Run scheduler and full regression tests**

Run Task 3 Step 4 commands. Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add app.py tests/test_line_flow.py
git commit -m "feat: push scheduled LINE stock alerts"
```

### Task 5: Remove browser watchlist behavior

**Files:**
- Modify: `templates/base.html`
- Modify: `templates/dashboard.html`
- Modify: `templates/stock_detail.html`
- Modify: `static/app.js`
- Modify: `static/app.css`
- Delete: `templates/watchlist.html`
- Modify: `app.py`
- Modify: `tests/test_web_product.py`
- Modify: `docs/line-to-web-map.md`

- [ ] **Step 1: Write failing Web boundary tests**

```python
def test_web_is_analysis_only_and_old_watchlist_redirects(self):
    dashboard = stock_app.app.test_client().get("/dashboard").get_data(as_text=True)
    with patch.object(stock_app, "analyze", return_value=analysis_data()):
        stock = stock_app.app.test_client().get("/stock/2330").get_data(as_text=True)
    watchlist = stock_app.app.test_client().get("/watchlist")
    self.assertNotIn("data-watchlist", dashboard + stock)
    self.assertNotIn("設定提醒", dashboard + stock)
    self.assertEqual(watchlist.status_code, 302)
    self.assertTrue(watchlist.headers["Location"].endswith("/dashboard"))

def test_browser_bundle_has_no_local_watchlist_storage(self):
    source = Path(stock_app.app.static_folder, "app.js").read_text(encoding="utf-8")
    self.assertNotIn("localStorage", source)
    self.assertNotIn("quant-watchlist", source)
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
$env:PYTHONPATH='.deps'; $env:LINE_CHANNEL_ACCESS_TOKEN='test'; $env:LINE_CHANNEL_SECRET='test'; python -m unittest tests.test_web_product.WebProductTests.test_web_is_analysis_only_and_old_watchlist_redirects tests.test_web_product.WebProductTests.test_browser_bundle_has_no_local_watchlist_storage -v
```

Expected: existing Web buttons and local storage cause failures.

- [ ] **Step 3: Delete browser-side watchlist code**

- Change `/watchlist` to `return redirect(url_for("dashboard_page"), code=302)` and import `redirect`.
- Remove watchlist navigation, alert dialog and toast from `base.html`.
- Remove Dashboard watchlist and recent-alert sections.
- Remove stock-page action buttons.
- Delete everything in `static/app.js` from `const STORE=` through the final local preview calls.
- Delete watchlist/dialog/toast CSS selectors and `templates/watchlist.html`.
- Update `docs/line-to-web-map.md` so `我的關注` and `強勢訊號` are message/postback flows; only market and stock analysis use Web routes.

The compatibility route is exactly:

```python
@app.route("/watchlist")
def watchlist_page():
    return redirect(url_for("dashboard_page"), code=302)
```

- [ ] **Step 4: Run targeted tests, Node syntax and full suite**

```powershell
python -m unittest tests.test_web_product -v
node --check static/app.js
python -m unittest discover -s tests -v
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 5: Commit**

```powershell
git add app.py static templates tests/test_web_product.py docs/line-to-web-map.md
git commit -m "refactor: keep watchlists and alerts inside LINE"
```

### Task 6: Security scan, GCP configuration and production verification

**Files:**
- Modify: `docs/line-to-web-map.md` only if the deployed command or schedule differs from the documented design.

- [ ] **Step 1: Run final local verification**

```powershell
$securityTools="$env:TEMP\linestockbot-security-tools"
python -m pip install --target $securityTools bandit pip-audit
$env:PYTHONPATH="$securityTools;C:\Users\enzo\Documents\line bot\.deps"
python -m unittest discover -s tests -v
python -m py_compile app.py line_state.py
node --check static/app.js
python -m bandit -q -r app.py line_state.py
python -m pip_audit --path .deps --progress-spinner off
git diff --check
git status --short
```

Expected: all tests pass, no medium/high Bandit findings, no known dependency vulnerabilities, clean worktree.

- [ ] **Step 2: Push the feature branch and confirm Cloud Build**

```powershell
git push -u origin codex/line-native-watchlist
```

Do not merge until Firestore and service-account permissions are ready.

- [ ] **Step 3: Configure GCP from Cloud Shell or an installed current gcloud CLI**

```bash
PROJECT=line-stock-bot-498908
REGION=asia-east1
SERVICE=line-stock-bot
gcloud config set project "$PROJECT"
gcloud firestore databases create --database='(default)' --location="$REGION" --type=firestore-native
SERVICE_ACCOUNT=$(gcloud run services describe "$SERVICE" --region="$REGION" --format='value(spec.template.spec.serviceAccountName)')
gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$SERVICE_ACCOUNT" --role='roles/datastore.user'
ALERT_TASK_TOKEN=$(python -c 'import secrets; print(secrets.token_urlsafe(32))')
gcloud run services update "$SERVICE" --region="$REGION" --set-env-vars="GCP_PROJECT_ID=$PROJECT,ALERT_TASK_TOKEN=$ALERT_TASK_TOKEN"
gcloud scheduler jobs create http line-stock-alerts --location="$REGION" --schedule='30 14 * * 1-5' --time-zone='Asia/Taipei' --uri="https://line-stock-bot-1067991373149.asia-east1.run.app/tasks/check-alerts" --http-method=POST --headers="Authorization=Bearer $ALERT_TASK_TOKEN"
```

If the default Firestore database already exists, verify it and skip only the create command. If the Scheduler job exists, use `gcloud scheduler jobs update http` with the same schedule, URI, method and header.

- [ ] **Step 4: Merge to main, push and verify production**

```powershell
git switch main
git merge --ff-only codex/line-native-watchlist
git push origin main
```

Wait for the Cloud Build check on the pushed SHA to conclude `success`, then verify:

```powershell
Invoke-WebRequest -UseBasicParsing 'https://line-stock-bot-1067991373149.asia-east1.run.app/'
Invoke-WebRequest -MaximumRedirection 0 -SkipHttpErrorCheck 'https://line-stock-bot-1067991373149.asia-east1.run.app/watchlist'
Invoke-WebRequest -Method Post -Headers @{Authorization='Bearer wrong'} -SkipHttpErrorCheck 'https://line-stock-bot-1067991373149.asia-east1.run.app/tasks/check-alerts'
```

Expected: health 200, `/watchlist` 302 to `/dashboard`, wrong scheduler token 403.

- [ ] **Step 5: Perform one controlled LINE acceptance test**

With one LINE test user:

1. Query `2330`, press `加入關注`, then send `我的關注`; confirm 2330 appears without opening Web.
2. Set probability threshold 1 so the next scheduler check can trigger.
3. Run the Scheduler job once from GCP and confirm one LINE Push message arrives.
4. Run it again for the same data date and confirm there is no duplicate push.
5. Press `查看完整分析` and confirm `/stock/2330` opens with no Web watchlist controls.

- [ ] **Step 6: Record final deployment evidence**

Report the GitHub SHA, Cloud Build URL and conclusion, production route statuses, Firestore database state, Scheduler job state, test count, Bandit result and pip-audit result.
