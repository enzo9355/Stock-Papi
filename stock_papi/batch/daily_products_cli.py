"""Create or locally promote verified post-close product candidates."""

import argparse
import datetime
import json
from pathlib import Path


def _calendars(paths):
    from stock_papi.batch.calendar import TradingCalendarSet

    return TradingCalendarSet.from_documents(
        [json.loads(Path(path).read_text(encoding="utf-8")) for path in paths]
    )


def build(args):
    from reporting.cli import _load_industry_map
    from reporting.config import ReportConfig
    from reporting.industry_analytics import build_daily_report
    from reporting.source_loader import (
        load_previous_report_source,
        load_report_source_manifest,
    )
    from reporting.v2_builder import build_post_close_metadata
    from stock_papi.batch.backtest_store import (
        BacktestStore,
        assess_backtest_compatibility,
    )
    from stock_papi.batch.daily_products import (
        build_daily_products,
        write_daily_candidate,
    )
    from stock_papi.quant.model import FEATURE_SCHEMA_VERSION, MODEL_VERSION
    from stock_papi.services.recommendation_engine import (
        RECOMMENDATION_POLICY_VERSION,
    )

    config = ReportConfig(root=args.root, market="TW")
    source = load_report_source_manifest(
        args.root,
        args.source_manifest,
        args.source_manifest_sha256,
        market="TW",
        report_date=args.source_market_date,
        config=config,
    )
    versions = {stock.model_version for stock in source.stocks}
    if versions != {MODEL_VERSION}:
        raise ValueError("daily source model version is incompatible")
    promoted = BacktestStore(args.root, "TW").load_latest()
    compatibility = (
        assess_backtest_compatibility(
            promoted,
            expected_model_version=MODEL_VERSION,
            expected_feature_schema_version=FEATURE_SCHEMA_VERSION,
            expected_recommendation_policy_version=RECOMMENDATION_POLICY_VERSION,
        )
        if promoted is not None
        else None
    )
    if compatibility is not None and compatibility["compatible"]:
        baseline = {
            "status": "validated_compatible",
            "backtest_as_of": compatibility["backtest_as_of"],
            "backtest_version": compatibility["backtest_version"],
            "model_version": MODEL_VERSION,
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "recommendation_policy_version": RECOMMENDATION_POLICY_VERSION,
            "mismatch_fields": [],
        }
        warnings = ()
    elif args.allow_degraded_bootstrap:
        baseline = {
            "status": "initial_backtest_bootstrap",
            "backtest_as_of": None,
            "backtest_version": None,
            "model_version": MODEL_VERSION,
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "recommendation_policy_version": RECOMMENDATION_POLICY_VERSION,
            "mismatch_fields": (
                compatibility["mismatch_fields"]
                if compatibility is not None
                else ["validated_backtest_baseline"]
            ),
        }
        warnings = (
            "首次回測基準尚未通過 promotion；本候選不含績效背書，可信度降級。",
        )
    else:
        reason = compatibility["reason"] if compatibility else "baseline_unavailable"
        raise ValueError(f"validated compatible baseline is unavailable: {reason}")

    previous = load_previous_report_source(
        args.root,
        args.source_market_date,
        market="TW",
        config=config,
    )
    report = build_daily_report(
        source,
        _load_industry_map(args.root),
        config,
        previous_source=previous,
    )
    metadata = build_post_close_metadata(
        report,
        _calendars(args.calendar_artifact),
        published_at=datetime.datetime.fromisoformat(
            source.manifest.generated_at.replace("Z", "+00:00")
        ),
        warnings=warnings,
        baseline=baseline,
    )
    dashboard = build_daily_products(report, metadata, baseline)
    directory = write_daily_candidate(args.root, metadata, dashboard)
    return {
        "mode": "candidate",
        "candidate_path": str(directory),
        "baseline": baseline,
        "dashboard_path": str(directory / "dashboard-snapshot.json"),
        "sector_path": str(directory / "sector-snapshot.json"),
        "heatmap_path": str(directory / "heatmap.json"),
        "daily_focus_path": str(directory / "daily-focus.json"),
        "top_picks_path": str(directory / "top-picks.json"),
        "post_close_v2_path": str(directory / "post-close-report-v2.json"),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="ABSORB daily product candidate")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("build")
    create.add_argument("--root", type=Path, default=Path(r"D:\AbsorbData"))
    create.add_argument("--source-market-date", type=datetime.date.fromisoformat, required=True)
    create.add_argument("--source-manifest", required=True)
    create.add_argument("--source-manifest-sha256", required=True)
    create.add_argument("--calendar-artifact", type=Path, action="append", required=True)
    create.add_argument("--allow-degraded-bootstrap", action="store_true")
    promote = subparsers.add_parser("promote")
    promote.add_argument("--root", type=Path, default=Path(r"D:\AbsorbData"))
    promote.add_argument("--candidate", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "build":
        result = build(args)
    else:
        from stock_papi.batch.daily_products import promote_daily_candidate

        result = {"mode": "local-promotion", **promote_daily_candidate(args.root, args.candidate)}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
