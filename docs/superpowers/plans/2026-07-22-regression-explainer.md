# Implementation Plan: Task C Regression Explainer & Research Presentation Layer

**Date:** 2026-07-22  
**Status:** DRAFT — Pending Independent Review  
**Target Branch:** `antigravity/task-c-regression-explainer-design`  
**Design Spec:** [docs/superpowers/specs/2026-07-22-regression-explainer-design.md](file:///C:/Users/enzo/Documents/absorb-institutional-report/docs/superpowers/specs/2026-07-22-regression-explainer-design.md)  
**Base SHA:** `da25d594d3b76865da22b891285ac0c85e710d86`  
**Repository:** `enzo9355/absorb`  

---

## Safety & Boundaries

- **No Implementation Code Execution**: This document outlines the planned execution tasks for Task C. Actual code implementation will commence ONLY after user review and approval.
- **Forbidden Actions**:
  - NO LightGBM training or SHAP execution.
  - NO probability, win rate, or trading signal generation.
  - NO prediction capability gate modifications (gates remain BLOCKED / UNAVAILABLE).
  - NO Cloud Run deployment, Production GCS updates, backfills, or LINE notifications.
  - NO Task D execution.

---

## Detailed Task Plan

### Task A: Regression Schema Definitions & Validation
- **Goal**: Define `RegressionResearchArtifact`, `RegressionSpec`, `RegressionResultItem`, `RegressionFitStatistics`, `RegressionDiagnostics`, and `RegressionPresentation` dataclasses with strict JSON schema versioning (`schema_version = 1`, `kind = "absorb-regression-research-artifact"`, `MAX_REGRESSION_ARTIFACT_BYTES = 2_000_000`).
- **Exact Files**:
  - `[NEW] reporting/regression_schema.py`
  - `[NEW] tests/test_regression_schema.py`
- **RED Test**: `tests/test_regression_schema.py::test_empty_document_raises_validation_error`
- **Expected Failure**: `ModuleNotFoundError: No module named 'reporting.regression_schema'`
- **Minimal Implementation**: Dataclasses with `from_document()`, `to_document()`, exact `object_sha256` and semantic `content_sha256` calculation, finite JSON checks, and forbidden word filtering (`Probability`, `勝率`, `上漲機率`, `下跌機率`, `正式預測`, `買進訊號`, `賣出訊號`).
- **Focused Command**: `python -m unittest tests.test_regression_schema -v`
- **Acceptance Criteria**: `RegressionResearchArtifact.from_document(doc)` passes for valid documents, enforces $0 \le R^2 \le 1$, $\text{ci\_low} \le \text{coef} \le \text{ci\_high}$, $\text{SE} \ge 0$, degrees of freedom $>0$, and raises `ValueError` for non-finite values or forbidden terms.
- **Commit Message**: `feat(reporting): define regression research artifact schema and hash contracts`
- **Rollback Boundary**: Delete `reporting/regression_schema.py` and `tests/test_regression_schema.py`.

---

### Task B: Analysis Input & Point-in-Time Contract
- **Goal**: Implement temporal boundary validator enforcing `feature_start_date`, `feature_end_date`, `label_start_date`, `label_end_date`, `label_horizon_sessions = 5` with calendar-based trading session alignment (`feature_date < label_end_date <= source_market_date`).
- **Exact Files**:
  - `[NEW] reporting/regression_pit.py`
  - `[NEW] tests/test_regression_pit.py`
- **RED Test**: `tests/test_regression_pit.py::test_label_end_date_exceeding_source_market_date_fails`
- **Expected Failure**: `ModuleNotFoundError: No module named 'reporting.regression_pit'`
- **Minimal Implementation**: `validate_point_in_time_bounds(feature_dates, label_dates, source_market_date, calendar)` returning `is_valid: bool` and error reason. Rejects future look-ahead label leakage.
- **Focused Command**: `python -m unittest tests.test_regression_pit -v`
- **Acceptance Criteria**: Validates trading calendar session bounds and rejects any dataset where label end date extends past source market date.
- **Commit Message**: `feat(reporting): implement point in time temporal bounds validator for regression explainer`
- **Rollback Boundary**: Delete `reporting/regression_pit.py` and `tests/test_regression_pit.py`.

---

### Task C: Offline Dependency Boundary & Cold-Start Isolation
- **Goal**: Create offline research dependency loader and cold-start import isolation test to guarantee heavy econometric libraries (`statsmodels`) are NEVER imported at top level of `stock_papi.application`, HTTP routes, or Cloud Run cold-start paths.
- **Exact Files**:
  - `[NEW] stock_papi/research/regression_deps.py`
  - `[NEW] tests/test_cold_start_imports.py`
- **RED Test**: `tests/test_cold_start_imports.py::test_statsmodels_not_imported_on_application_import`
- **Expected Failure**: Assert `sys.modules` does not contain `statsmodels` when `import stock_papi.application` executes.
- **Minimal Implementation**: Lazy import wrapper inside `stock_papi/research/regression_deps.py` loading `statsmodels` exclusively inside function scope.
- **Focused Command**: `python -m unittest tests.test_cold_start_imports -v`
- **Acceptance Criteria**: `stock_papi.application` and `stock_papi.web.routes.reports` can be imported without loading `statsmodels` into `sys.modules`.
- **Commit Message**: `test(architecture): enforce cold start top level import isolation for statsmodels`
- **Rollback Boundary**: Delete `stock_papi/research/regression_deps.py` and `tests/test_cold_start_imports.py`.

---

### Task D: OLS & HAC Covariance Adapter
- **Goal**: Build `compute_ols_hac_regression(dependent_series, factor_matrix, lags=4)` using `statsmodels` inside offline research module to compute OLS estimates, Newey-West HAC robust standard errors (`hac_max_lags = 4`), t-statistics, p-values, and 95% confidence intervals.
- **Exact Files**:
  - `[NEW] reporting/regression_adapter.py`
  - `[NEW] tests/test_regression_adapter.py`
- **RED Test**: `tests/test_regression_adapter.py::test_computes_newey_west_hac_estimates`
- **Expected Failure**: `ModuleNotFoundError: No module named 'reporting.regression_adapter'`
- **Minimal Implementation**: Calculates OLS estimates with Newey-West HAC covariance matrix adjustment for overlapping 5-day return series.
- **Focused Command**: `python -m unittest tests.test_regression_adapter -v`
- **Acceptance Criteria**: Estimates match reference HAC standard errors, t-statistics, and confidence intervals.
- **Commit Message**: `feat(reporting): implement OLS factor regression adapter with Newey-West HAC covariance`
- **Rollback Boundary**: Delete `reporting/regression_adapter.py` and `tests/test_regression_adapter.py`.

---

### Task E: Diagnostics & Validation Engine
- **Goal**: Implement statistical validation engine evaluating sample count policy ($n < 30 \rightarrow \text{unavailable}$, $30 \le n < 60 \rightarrow \text{available\_with\_limited\_sample\_warning}$, $60 \le n \le 252 \rightarrow \text{available}$), design matrix rank, Breusch-Pagan heteroskedasticity test, VIF multicollinearity, and Durbin-Watson autocorrelation.
- **Exact Files**:
  - `[NEW] reporting/regression_validation.py`
  - `[NEW] tests/test_regression_validation.py`
- **RED Test**: `tests/test_regression_validation.py::test_sample_count_below_30_fails_hard`
- **Expected Failure**: `ModuleNotFoundError: No module named 'reporting.regression_validation'`
- **Minimal Implementation**: `validate_regression_diagnostics(fit_stats, diagnostics, sample_count)` separating Hard Failures ($n < 30$, rank deficient, non-finite values) from Warnings (VIF $\ge 5.0$, Breusch-Pagan $p < 0.05$).
- **Focused Command**: `python -m unittest tests.test_regression_validation -v`
- **Acceptance Criteria**: Hard Failures mark section `unavailable`; Diagnostic Warnings generate presentation badges without failing report.
- **Commit Message**: `feat(reporting): implement statistical validation and diagnostic engine for regression explainer`
- **Rollback Boundary**: Delete `reporting/regression_validation.py` and `tests/test_regression_validation.py`.

---

### Task F: Regression Artifact Builder
- **Goal**: Build `build_regression_research_artifact(...)` orchestrator to generate content-addressed `RegressionResearchArtifact` documents from verified market observation manifests.
- **Exact Files**:
  - `[NEW] reporting/regression_builder.py`
  - `[NEW] tests/test_regression_builder.py`
- **RED Test**: `tests/test_regression_builder.py::test_builds_valid_regression_research_artifact`
- **Expected Failure**: `ModuleNotFoundError: No module named 'reporting.regression_builder'`
- **Minimal Implementation**: Orchestrates adapter computation, validation engine, mandatory disclaimers, and content-addressed `object_sha256` and `content_sha256` generation. Returns `None` on Hard Failures.
- **Focused Command**: `python -m unittest tests.test_regression_builder -v`
- **Acceptance Criteria**: Successfully builds content-addressed `RegressionResearchArtifact` or returns `None` on invalid data.
- **Commit Message**: `feat(reporting): implement regression research artifact builder`
- **Rollback Boundary**: Delete `reporting/regression_builder.py` and `tests/test_regression_builder.py`.

---

### Task G: Regression Object Publisher
- **Goal**: Update `reporting/publisher.py` to execute the exact 10-step atomic publication sequence, writing `objects/regression/<object_sha256>.json` with atomic replace and read-back size/hash verification.
- **Exact Files**:
  - `[MODIFY] reporting/publisher.py`
  - `[MODIFY] tests/test_canonical_publisher_integrity.py`
- **RED Test**: `tests/test_canonical_publisher_integrity.py::test_publishes_regression_artifact_with_exact_ten_step_order`
- **Expected Failure**: `TypeError: publish_report_v2() got an unexpected keyword argument 'regression_artifact'`
- **Minimal Implementation**: Implements atomic write to `objects/regression/<object_sha256>.json`, read-back verification against `MAX_REGRESSION_ARTIFACT_BYTES = 2_000_000`, and exact metadata pointer injection (`metadata/<metadata_sha256>.json`).
- **Focused Command**: `python -m unittest tests.test_canonical_publisher_integrity -v`
- **Acceptance Criteria**: Publisher writes regression object, verifies SHA256 read-back, and injects exact metadata pointer.
- **Commit Message**: `feat(reporting): integrate regression artifact publishing into atomic ten step sequence`
- **Rollback Boundary**: `git checkout origin/main -- reporting/publisher.py`.

---

### Task H: Metadata Pointer Schema Extension
- **Goal**: Extend `ReportMetadataV2` in `reporting/schemas.py` to validate `regression_research` pointer dict (`object`, `sha256`, `content_sha256`, `schema_version`, `generator_version`, `code_commit_sha`).
- **Exact Files**:
  - `[MODIFY] reporting/schemas.py`
  - `[MODIFY] tests/test_professional_pointer_schema.py`
- **RED Test**: `tests/test_professional_pointer_schema.py::test_validates_regression_research_pointer`
- **Expected Failure**: `ValueError: report metadata v2 schema contains unknown key 'regression_research'`
- **Minimal Implementation**: Update `ReportMetadataV2.from_document()` to validate `regression_research` pointer keys enforcing `pointer.object == f"objects/regression/{pointer.sha256}.json"`.
- **Focused Command**: `python -m unittest tests.test_professional_pointer_schema -v`
- **Acceptance Criteria**: `ReportMetadataV2` parses and validates valid `regression_research` pointers and rejects malformed paths or SHA mismatches.
- **Commit Message**: `feat(reporting): extend metadata v2 schema with regression research pointer validation`
- **Rollback Boundary**: `git checkout origin/main -- reporting/schemas.py`.

---

### Task I: Optional Regression Binding Validator
- **Goal**: Implement `validate_regression_research_binding(metadata, professional_report, regression_pointer, regression_artifact)` in `reporting/professional_binding.py` for optional research binding validation.
- **Exact Files**:
  - `[MODIFY] reporting/professional_binding.py`
  - `[MODIFY] tests/test_professional_report_binding.py`
- **RED Test**: `tests/test_professional_report_binding.py::test_optional_regression_binding_validation`
- **Expected Failure**: `ImportError: cannot import name 'validate_regression_research_binding' from 'reporting.professional_binding'`
- **Minimal Implementation**: Cross-checks regression pointer SHA, semantic content SHA, source dates, manifest SHA, and commit SHA. On mismatch, raises `ValueError` caught by optional route handler (does NOT affect critical canonical binding `validate_professional_report_binding`).
- **Focused Command**: `python -m unittest tests.test_professional_report_binding -v`
- **Acceptance Criteria**: Validator verifies optional regression binding without mutating critical canonical report binding logic.
- **Commit Message**: `feat(reporting): implement optional regression research binding validator`
- **Rollback Boundary**: `git checkout origin/main -- reporting/professional_binding.py`.

---

### Task J: Application Raw-Bytes Regression Loader
- **Goal**: Add `load_regression_object(object_path, max_bytes=MAX_REGRESSION_ARTIFACT_BYTES)` in `stock_papi/application.py`.
- **Exact Files**:
  - `[MODIFY] stock_papi/application.py`
  - `[NEW] tests/test_regression_loader.py`
- **RED Test**: `tests/test_regression_loader.py::test_load_regression_object_validates_path_and_bytes`
- **Expected Failure**: `AttributeError: module 'stock_papi.application' has no attribute 'load_regression_object'`
- **Minimal Implementation**: Implements `load_regression_object` with regex `^objects/regression/[0-9a-f]{64}\.json$`, size limit `MAX_REGRESSION_ARTIFACT_BYTES = 2_000_000`, defensive parameter checks, and prefixing `reports/v2/`.
- **Focused Command**: `python -m unittest tests.test_regression_loader -v`
- **Acceptance Criteria**: Loader fetches raw bytes, validates exact regex path, rejects traversal/uppercase/oversized inputs, and returns `None` on error.
- **Commit Message**: `feat(application): implement raw bytes load_regression_object loader`
- **Rollback Boundary**: `git checkout origin/main -- stock_papi/application.py` and delete `tests/test_regression_loader.py`.

---

### Task K: Route Optional Loading & Graceful Degradation
- **Goal**: Update `_observation_page` in `stock_papi/web/routes/reports.py` to attempt optional regression loading using `load_regression_object`. If missing or invalid, gracefully degrades `quantitative_research` view model to `status = "unavailable"`, maintaining HTTP 200 OK.
- **Exact Files**:
  - `[MODIFY] stock_papi/web/routes/reports.py`
  - `[NEW] tests/test_regression_route.py`
- **RED Test**: `tests/test_regression_route.py::test_missing_regression_artifact_returns_200_with_unavailable_section`
- **Expected Failure**: Route attempts to invoke `load_regression_object` when passed in dependency injection.
- **Minimal Implementation**: Adds `load_regression_object=None` optional dependency to `register_report_routes`. Implements 7-step route data flow for regression artifact loading and optional binding validation.
- **Focused Command**: `python -m unittest tests.test_regression_route -v`
- **Acceptance Criteria**: Valid regression artifact populates `quantitative_research` view model; missing or corrupted regression artifact returns HTTP 200 OK with `status = "unavailable"`.
- **Commit Message**: `feat(web): add optional regression artifact loading with graceful 200 OK degradation`
- **Rollback Boundary**: `git checkout origin/main -- stock_papi/web/routes/reports.py` and delete `tests/test_regression_route.py`.

---

### Task L: HTML View Model Adapter
- **Goal**: Update `build_professional_report_view()` in `reporting/professional_html.py` to format `quantitative_research` section data into Jinja-safe view model with mandatory disclaimers and AI labels.
- **Exact Files**:
  - `[MODIFY] reporting/professional_html.py`
  - `[MODIFY] tests/test_professional_report_html.py`
- **RED Test**: `tests/test_professional_report_html.py::test_view_model_contains_regression_research_data`
- **Expected Failure**: `KeyError` or missing regression presentation fields in view model.
- **Minimal Implementation**: Formats Jinja-safe view model containing section title, `AI 模型參考建議`, `模型方向參考`, factor exposures table, diagnostic badges, and mandatory disclosure text.
- **Focused Command**: `python -m unittest tests.test_professional_report_html -v`
- **Acceptance Criteria**: View model contains structured factor exposures, mandatory disclaimers, and zero forbidden terms.
- **Commit Message**: `feat(reporting): format quantitative regression research section in HTML view model`
- **Rollback Boundary**: `git checkout origin/main -- reporting/professional_html.py`.

---

### Task M: HTML Template Rendering
- **Goal**: Update Jinja template `templates/reports/post_close_professional.html` to render the `quantitative_research` section card with factor exposure table, diagnostic badges, and mandatory disclaimers.
- **Exact Files**:
  - `[MODIFY] templates/reports/post_close_professional.html`
  - `[NEW] tests/test_reports_template_regression.py`
- **RED Test**: `tests/test_reports_template_regression.py::test_renders_quantitative_research_section_card`
- **Expected Failure**: Template output does not contain `量化與迴歸因子研究` or `模型方向參考`.
- **Minimal Implementation**: Adds Jinja block for `report.quantitative_research` rendering factor coefficients, t-stats, p-values, 95% CIs, diagnostic status, and limitations box.
- **Focused Command**: `python -m unittest tests.test_reports_template_regression -v`
- **Acceptance Criteria**: Template renders clean HTML table for `status == "available"` and alert card for `status == "unavailable"`.
- **Commit Message**: `feat(web): render quantitative regression research section in post-close report template`
- **Rollback Boundary**: `git checkout origin/main -- templates/reports/post_close_professional.html` and delete `tests/test_reports_template_regression.py`.

---

### Task N: Publisher Rollback & Failure Injection Tests
- **Goal**: Build failure injection tests verifying that if metadata, index, or latest write fails during publishing, newly created regression objects are cleanly unlinked without deleting pre-existing identical immutable objects.
- **Exact Files**:
  - `[NEW] tests/test_regression_publisher_rollback.py`
- **RED Test**: `tests/test_regression_publisher_rollback.py::test_publisher_rollback_cleans_uncommitted_objects`
- **Expected Failure**: Test fails until publisher cleanup logic handles regression artifact unlinking on write failure.
- **Minimal Implementation**: Verifies unlinking of newly created `objects/regression/<object_sha256>.json` when metadata or index write throws an exception.
- **Focused Command**: `python -m unittest tests.test_regression_publisher_rollback -v`
- **Acceptance Criteria**: Publisher rollback cleans up newly created regression artifacts without mutating existing files or pointers.
- **Commit Message**: `test(reporting): verify publisher rollback and failure injection for regression artifacts`
- **Rollback Boundary**: Delete `tests/test_regression_publisher_rollback.py`.

---

### Task O: Pre-market, Notification & PDF Non-regression Tests
- **Goal**: Verify pre-market core lineage (`content.core`), notification date semantics, and PDF generator remain 100% unaffected by regression explainer updates.
- **Exact Files**:
  - `[MODIFY] tests/test_pre_market_pipeline.py`
  - `[MODIFY] tests/test_report_notification_dates.py`
- **RED Test**: Run existing tests and verify zero regressions.
- **Expected Failure**: N/A (Non-regression assertion).
- **Minimal Implementation**: Ensures pre-market raw core lineage remains untouched and post-close notification URLs continue using `source_market_date`.
- **Focused Command**: `python -m unittest tests.test_pre_market_pipeline tests.test_report_notification_dates -v`
- **Acceptance Criteria**: All 100% of pre-market and notification tests pass cleanly with zero regressions.
- **Commit Message**: `test(pipeline): verify pre-market lineage and notification dates unaffected by regression explainer`
- **Rollback Boundary**: `git checkout origin/main -- tests/test_pre_market_pipeline.py tests/test_report_notification_dates.py`.

---

### Task P: Cold-start, Secret & Sample-Data Scans
- **Goal**: Execute security and code hygiene scans asserting zero secrets, zero legacy persona references, zero sample data leaks, and zero statsmodels top-level imports in web paths.
- **Exact Files**:
  - `[MODIFY] tests/test_absorb_security.py`
- **RED Test**: `tests/test_absorb_security.py::test_no_statsmodels_import_in_web_routes`
- **Expected Failure**: Test asserts web routes do not import statsmodels.
- **Minimal Implementation**: Scans codebase AST for forbidden top-level imports and hardcoded credentials.
- **Focused Command**: `python -m unittest tests.test_absorb_security -v`
- **Acceptance Criteria**: All security and import isolation checks pass.
- **Commit Message**: `test(security): audit code hygiene, secret scan, and import isolation for regression explainer`
- **Rollback Boundary**: `git checkout origin/main -- tests/test_absorb_security.py`.

---

### Task Q: Full Verification & Lint Audit
- **Goal**: Run full test suite, verify compilation, check JavaScript syntax, and audit git diff formatting.
- **Commands**:
  - `python -m unittest discover tests -v`
  - `python -m compileall reporting stock_papi tests`
  - `node --check static/app.js`
  - `git diff --check`
- **Commit Message**: `docs: resolve regression explainer integrity and statistical contracts`
- **Acceptance Criteria**: All 717+ unit tests pass, zero compile errors, zero git diff formatting warnings.
- **Rollback Boundary**: N/A.

---

## Acceptance Summary

Upon user approval of the Design Spec and Implementation Plan, execution of Tasks A through Q will proceed sequentially with per-task commits, RED/GREEN test cycles, and full rollback boundaries.
