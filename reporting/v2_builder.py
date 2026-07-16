"""由已驗證 point-in-time source 建立盤後 report metadata v2。"""

import datetime

from reporting.public_report import build_public_report


def _summary(values):
    return [value if len(value) <= 500 else value[:497] + "..." for value in values[:20]]


def build_post_close_metadata(
    report, calendars, *, published_at=None, warnings=(), baseline=None
):
    source_date = report.source.manifest.market_as_of
    applicable = calendars.next_session(source_date)
    forecast_end = calendars.session_offset(applicable, 4)
    timestamp = published_at or report.generated_at
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("published_at must be timezone-aware")
    public_report = build_public_report(report)
    combined_warnings = list(report.warnings)
    for warning in warnings:
        if warning not in combined_warnings:
            combined_warnings.append(warning)
    baseline = baseline or {
        "status": "legacy_embedded",
        "backtest_as_of": source_date.isoformat(),
        "backtest_version": None,
        "model_version": next(iter(report.model_versions)),
        "feature_schema_version": None,
        "recommendation_policy_version": None,
        "mismatch_fields": [],
    }
    backtest_as_of = baseline.get("backtest_as_of")
    if backtest_as_of is not None:
        backtest_as_of = datetime.date.fromisoformat(str(backtest_as_of)).isoformat()
    return {
        "schema_version": 2,
        "report_type": "post_close",
        "market": "TW",
        "source_market_date": source_date.isoformat(),
        "applicable_trading_date": applicable.isoformat(),
        "published_at": timestamp.astimezone(datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "forecast_start_date": applicable.isoformat(),
        "forecast_end_date": forecast_end.isoformat(),
        "backtest_as_of": backtest_as_of,
        "data_as_of": source_date.isoformat(),
        "source_manifest": f"quant/v1/{report.source.manifest.manifest_path}",
        "source_manifest_sha256": report.source.manifest.manifest_sha256,
        "model_versions": report.model_versions,
        "title": f"{source_date.isoformat()} 盤後分析暨 {applicable.isoformat()} 交易展望",
        "summary": _summary(report.summary),
        "warnings": combined_warnings,
        "content": {
            "public_report": public_report,
            "prediction_horizon_sessions": 5,
            "source_coverage": report.source.manifest.coverage,
            "source_failure_rate": report.source.manifest.failure_rate,
            "inference_as_of": source_date.isoformat(),
            "baseline": dict(baseline),
        },
    }
