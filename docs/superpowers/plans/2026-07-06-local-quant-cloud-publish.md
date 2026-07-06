# Local Quant Cloud Publishing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish TW/US local quant artifacts when the failure rate is below 5%, upload them privately after 09:30, and let Cloud Run use verified artifacts with live-analysis fallback.

**Architecture:** Extend the existing content-addressed local publisher instead of adding a second format. A separate 09:35 Windows task uploads referenced objects, manifest, then `latest` to a private GCS bucket. Cloud Run reads one artifact at a time through the existing metadata-token path and falls back to `_do_analyze` when the artifact is missing, stale, or invalid.

**Tech Stack:** Python 3.10 stdlib, Flask, pandas, requests, PowerShell Scheduled Tasks, gcloud CLI, Google Cloud Storage.

---

### Task 1: Publish a market with less than 5% failures

**Files:**
- Modify: `local_quant.py`
- Modify: `tests/test_local_quant_publish.py`
- Modify: `tests/test_local_quant.py`

- [ ] **Step 1: Write failing threshold and manifest tests**

Add tests that create 100-symbol universes and assert four failures publish while five failures preserve the previous `latest`. Assert manifest schema fields:

```python
self.assertEqual(manifest["universe_count"], 100)
self.assertEqual(manifest["symbol_count"], 96)
self.assertEqual(manifest["failure_count"], 4)
self.assertEqual(manifest["failed_symbols"], ["0096", "0097", "0098", "0099"])
self.assertAlmostEqual(manifest["coverage"], 0.96)
```

Add a CLI test where `next_index == len(symbols)` and one failed symbol still calls `publish_market_snapshot(..., failed_symbols=[...])`.

- [ ] **Step 2: Run tests and verify RED**

```powershell
$env:PYTHONPATH=(Resolve-Path '.deps').Path
& 'C:\Users\enzo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_local_quant_publish tests.test_local_quant -v
```

Expected: FAIL because `publish_market_snapshot` does not accept `failed_symbols` and CLI blocks all partial publication.

- [ ] **Step 3: Implement partial publication**

Change the publisher signature and validate all usable artifacts before updating `latest`:

```python
def publish_market_snapshot(
    root, market, symbols, generated_at=None, failed_symbols=()
):
    universe = sorted({validate_market_symbol(market, item) for item in symbols})
    excluded = {validate_market_symbol(market, item) for item in failed_symbols}
    # Validate candidates, add missing/corrupt/stale symbols to excluded.
    # Abort without replacing latest when len(excluded) / len(universe) >= 0.05.
```

Manifest schema version 2 must contain `universe_count`, `symbol_count`, `failure_count`, `failure_rate`, `coverage`, `failed_symbols`, `market_as_of`, and `symbols`. Only write the `latest` pointer after every included object and the immutable manifest are complete.

In `main`, call the publisher whenever the scan reached the end. Pass the checkpoint failure codes, catch publication validation errors without deleting the previous pointer, and record `published`, `coverage`, and a sanitized `publish_error` in the summary.

- [ ] **Step 4: Run tests and verify GREEN**

Run the command from Step 2. Expected: all local quant publication tests pass.

- [ ] **Step 5: Commit**

```powershell
git add -- local_quant.py tests/test_local_quant_publish.py tests/test_local_quant.py
git commit -m "feat: publish high-coverage quant snapshots"
```

### Task 2: Add a private, allowlisted 09:35 uploader

**Files:**
- Create: `scripts/upload_local_quant.ps1`
- Create: `config/quant-snapshot-lifecycle.json`
- Modify: `scripts/install_local_quant_task.ps1`
- Modify: `tests/test_local_quant_task.py`

- [ ] **Step 1: Write failing uploader safety tests**

Assert the uploader contains the exact D-drive allowlist, validates manifest/object relative paths, uploads objects before manifests and `latest`, invokes `gcloud storage cp`, and contains no service-account key, password, delete, or recursive bucket-sync command. Assert the installer registers `StockPapi-QuantUpload` at `09:35` with `RunLevel Limited` and a one-hour limit.

- [ ] **Step 2: Run tests and verify RED**

```powershell
$env:PYTHONPATH=(Resolve-Path '.deps').Path
& 'C:\Users\enzo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_local_quant_task -v
```

Expected: FAIL because the uploader and second task do not exist.

- [ ] **Step 3: Implement the uploader and installer changes**

The uploader accepts only these values:

```powershell
param(
    [string]$DataRoot = 'D:\StockPapiData',
    [string]$Bucket = 'line-stock-bot-498908-quant-snapshots'
)
if ($DataRoot -ne 'D:\StockPapiData') { throw 'Data root is not allowlisted' }
if ($Bucket -ne 'line-stock-bot-498908-quant-snapshots') { throw 'Bucket is not allowlisted' }
```

For `latest-TW.json` and `latest-US.json`, parse JSON, require manifest paths matching `^manifests/[A-Z]+-[0-9TZ]+-[0-9a-f]{12}\.json$`, require object paths matching `^objects/[0-9a-f]{64}\.json\.gz$`, resolve every local path under `publish\quant\v1`, then upload referenced objects, manifest, and latest in that order. Use `gcloud storage cp --quiet`; never delete or sync.

Register a separate daily task at 09:35. Keep the existing compute task unchanged.

Use a 30-day GCS lifecycle rule:

```json
{"rule":[{"action":{"type":"Delete"},"condition":{"age":30}}]}
```

- [ ] **Step 4: Run tests and verify GREEN**

Run the command from Step 2. Expected: all task safety tests pass.

- [ ] **Step 5: Commit**

```powershell
git add -- scripts/upload_local_quant.ps1 scripts/install_local_quant_task.ps1 config/quant-snapshot-lifecycle.json tests/test_local_quant_task.py
git commit -m "feat: schedule private quant uploads"
```

### Task 3: Read verified GCS artifacts in Cloud Run

**Files:**
- Modify: `app.py`
- Modify: `tests/test_prediction_pipeline.py`
- Modify: `templates/stock_detail.html`
- Modify: `tests/test_web_product.py`

- [ ] **Step 1: Write failing snapshot-hit and fallback tests**

Mock three authenticated GCS responses: latest, manifest, and gzip object. Assert a valid object bypasses `get_data` and `run_ai_engine`, but still calls `get_news`. Add cases for missing symbol, stale `market_as_of`, oversized object, bad SHA-256, invalid gzip, and schema mismatch; each must call the existing live path. Assert the Web page displays `本地回測快照` or `即時計算`.

- [ ] **Step 2: Run tests and verify RED**

```powershell
$env:PYTHONPATH=(Resolve-Path '.deps').Path
& 'C:\Users\enzo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_prediction_pipeline tests.test_web_product -v
```

Expected: FAIL because Cloud Run has no GCS snapshot reader.

- [ ] **Step 3: Implement authenticated, bounded reads**

Add `QUANT_SNAPSHOT_BUCKET` and a five-minute latest/manifest cache. Reuse `line_store.token_provider()` for the metadata access token. Fetch objects through the GCS JSON API with URL-encoded object names and five-second timeouts. Require:

```python
MAX_QUANT_ARTIFACT_COMPRESSED_BYTES = 5 * 1024 * 1024
MAX_QUANT_ARTIFACT_UNCOMPRESSED_BYTES = 20 * 1024 * 1024
```

Verify bucket name, latest/manifest schema, market, symbol membership, age no greater than seven calendar days, compressed size, SHA-256, gzip expansion limit, artifact schema, market, symbol, and `as_of` before returning a snapshot. Never log tokens or response bodies.

Refactor `_do_analyze` minimally:

```python
snapshot = fetch_published_quant_snapshot(code)
if snapshot:
    df = dataframe_from_quant_snapshot(snapshot)
    bt = snapshot["backtest"]
    quant_source = "本地回測快照"
else:
    df = calc_all(get_data(code))
    bt = run_ai_engine(df)
    quant_source = "即時計算"
```

Keep news and sentiment live. Add `quant_source` to the result and render it beside the data date.

- [ ] **Step 4: Run tests and verify GREEN**

Run the command from Step 2. Expected: snapshot and fallback tests pass.

- [ ] **Step 5: Commit**

```powershell
git add -- app.py templates/stock_detail.html tests/test_prediction_pipeline.py tests/test_web_product.py
git commit -m "feat: serve verified local quant snapshots"
```

### Task 4: Provision GCS and install the upload task

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Create and harden the bucket**

```powershell
gcloud storage buckets create gs://line-stock-bot-498908-quant-snapshots --project=line-stock-bot-498908 --location=asia-east1 --uniform-bucket-level-access
gcloud storage buckets update gs://line-stock-bot-498908-quant-snapshots --public-access-prevention
gcloud storage buckets update gs://line-stock-bot-498908-quant-snapshots --lifecycle-file=config/quant-snapshot-lifecycle.json
```

If the bucket already exists, inspect its project, location, uniform access, public-access prevention, and lifecycle before changing IAM.

- [ ] **Step 2: Grant least-privilege Cloud Run access**

Read the service account from `gcloud run services describe`, then grant only `roles/storage.objectViewer` on this bucket. Do not create or download a service-account key.

- [ ] **Step 3: Install and inspect the 09:35 task**

```powershell
pwsh -File scripts/install_local_quant_task.ps1
Get-ScheduledTaskInfo 'StockPapi-QuantUpload'
```

Use `-WhatIf` first. Confirm the compute checkpoint is byte-for-byte unchanged before and after installation.

- [ ] **Step 4: Produce the current partial TW publication and upload it**

Invoke only the publication function against existing artifacts and current checkpoint; do not rerun market analysis. Verify coverage exceeds 95%, then run `scripts/upload_local_quant.ps1`. Confirm remote object, manifest, and latest exist and hashes match.

- [ ] **Step 5: Document operations**

Update README with the 95% threshold, failure fallback, bucket security, 09:35 task, result-source label, and safe verification commands.

- [ ] **Step 6: Commit**

```powershell
git add -- README.md
git commit -m "docs: explain quant snapshot publishing"
```

### Task 5: Full verification, push, and deploy

**Files:**
- No new files.

- [ ] **Step 1: Run full local verification**

```powershell
$env:PYTHONPATH=(Resolve-Path '.deps').Path
& 'C:\Users\enzo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s tests -v
& 'C:\Users\enzo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m py_compile app.py local_quant.py line_state.py
git diff --check
shellward scan --json .
```

Expected: all tests and syntax checks pass; ShellWard has no confirmed embedded secret.

- [ ] **Step 2: Push main**

```powershell
git push origin main
```

- [ ] **Step 3: Deploy Cloud Run with the bucket setting**

```powershell
gcloud run deploy line-stock-bot --source . --region asia-east1 --project line-stock-bot-498908 --allow-unauthenticated --update-env-vars QUANT_SNAPSHOT_BUCKET=line-stock-bot-498908-quant-snapshots --quiet
```

- [ ] **Step 4: Verify live state**

Confirm the latest ready revision receives 100% traffic, `/health` returns 200, `/stock/2330` returns 200, displays `本地回測快照`, and a failed symbol displays `即時計算`. Confirm local HEAD equals `origin/main` and unrelated untracked files remain untouched.
