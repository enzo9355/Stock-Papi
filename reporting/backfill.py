"""安全回補缺失盤後報告；預設只驗證並顯示計畫。"""

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
from pathlib import Path


class BackfillError(ValueError):
    pass


def _canonical(document):
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _write_exclusive(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        if path.read_bytes() != content:
            raise BackfillError("immutable backfill audit conflict")
        return
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _load_calendars(paths):
    from stock_papi.batch.calendar import TradingCalendarSet

    documents = []
    for path in paths:
        try:
            documents.append(json.loads(Path(path).read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            raise BackfillError("calendar artifact is unavailable or invalid") from exc
    try:
        return TradingCalendarSet.from_documents(documents)
    except ValueError as exc:
        raise BackfillError(str(exc)) from exc


def plan_backfill(
    *,
    dates,
    manifest_path,
    manifest_sha256,
    model_version,
    load_verified_manifest,
    today=None,
    dry_run=True,
):
    """保留可測試的純規劃介面；不接受未驗證或未明確指定的來源。"""
    today = today or datetime.date.today()
    if (
        not dry_run
        or not callable(load_verified_manifest)
        or not isinstance(dates, (list, tuple))
        or not dates
        or re.fullmatch(
            r"quant/v1/manifests/TW-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}\.json",
            str(manifest_path),
        )
        is None
        or re.fullmatch(r"[0-9a-f]{64}", str(manifest_sha256)) is None
        or not isinstance(model_version, str)
        or not model_version
    ):
        raise BackfillError(
            "backfill requires explicit verified identity and defaults to dry-run"
        )
    verified = load_verified_manifest(manifest_path, manifest_sha256)
    if (
        not isinstance(verified, dict)
        or verified.get("path") != manifest_path
        or verified.get("sha256") != manifest_sha256
    ):
        raise BackfillError("verified manifest is unavailable")
    source_date = verified.get("market_as_of")
    commands = []
    for value in dates:
        if type(value) is not datetime.date or value > today:
            continue
        if value.isoformat() != source_date:
            continue
        commands.append(
            "python -m reporting.backfill --market TW --report-type post_close "
            f"--source-market-date {value.isoformat()} --source-manifest {manifest_path} "
            f"--source-manifest-sha256 {manifest_sha256} --model-version {model_version}"
        )
    if not commands:
        raise BackfillError("no requested date has a verified matching manifest")
    return {
        "dry_run": True,
        "commands": commands,
        "manifest_path": manifest_path,
        "manifest_sha256": manifest_sha256,
        "model_version": model_version,
    }


def _execute(args):
    from reporting.config import ReportConfig
    from reporting.industry_analytics import build_daily_report
    from reporting.pdf_generator import DailyIndustryReportGenerator
    from reporting.publisher import publish_report_v2
    from reporting.source_loader import (
        load_previous_report_source,
        load_report_source_manifest,
    )
    from reporting.v2_builder import build_post_close_metadata
    from reporting.cli import _load_industry_map

    if args.report_type != "post_close":
        raise BackfillError(
            "historical pre-market data is not retained; only post_close can be backfilled"
        )
    if args.source_market_date > datetime.date.today():
        raise BackfillError("future report backfill is forbidden")
    config = ReportConfig(root=args.root, market="TW")
    source = load_report_source_manifest(
        args.root,
        args.source_manifest,
        args.source_manifest_sha256,
        market="TW",
        report_date=args.source_market_date,
        config=config,
    )
    model_versions = {stock.model_version for stock in source.stocks}
    if model_versions != {args.model_version}:
        raise BackfillError("source model version does not match explicit model version")
    calendars = _load_calendars(args.calendar_artifact)
    if not calendars.is_session(args.source_market_date):
        raise BackfillError("source market date is not a verified trading session")
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
    generated_at = datetime.datetime.fromisoformat(
        source.manifest.generated_at.replace("Z", "+00:00")
    )
    metadata = build_post_close_metadata(
        report,
        calendars,
        published_at=generated_at,
        warnings=("歷史回補：只使用指定 immutable manifest 的 point-in-time 資料。",),
    )
    plan = {
        "schema_version": 1,
        "mode": "apply" if args.apply else "dry-run",
        "report_type": "post_close",
        "source_market_date": args.source_market_date.isoformat(),
        "applicable_trading_date": metadata["applicable_trading_date"],
        "source_manifest": args.source_manifest,
        "source_manifest_sha256": args.source_manifest_sha256,
        "model_version": args.model_version,
    }
    if not args.apply:
        return plan

    output_dir = args.root / "reports" / "TW" / ".staging"
    output = output_dir / f"backfill-post-close-{args.source_market_date.isoformat()}.pdf"
    generation = DailyIndustryReportGenerator(config).generate(report, output)
    if not generation.success:
        raise BackfillError(generation.error_message or "PDF generation failed")
    try:
        latest = publish_report_v2(
            args.root,
            metadata,
            pdf_path=output,
            page_count=generation.page_count,
            config=config,
        )
    finally:
        output.unlink(missing_ok=True)
    plan["latest_path"] = str(latest)
    audit_bytes = _canonical(plan)
    audit_id = hashlib.sha256(audit_bytes).hexdigest()
    _write_exclusive(
        args.root / "logs" / "backfill-audit" / f"{audit_id}.json", audit_bytes
    )
    plan["audit_id"] = audit_id
    return plan


def main(argv=None):
    parser = argparse.ArgumentParser(description="Stock Papi verified report backfill")
    parser.add_argument("--root", type=Path, default=Path(r"D:\StockPapiData"))
    parser.add_argument("--market", choices=("TW",), default="TW")
    parser.add_argument("--report-type", choices=("post_close", "pre_market"), required=True)
    parser.add_argument("--source-market-date", type=datetime.date.fromisoformat, required=True)
    parser.add_argument("--source-manifest", required=True)
    parser.add_argument("--source-manifest-sha256", required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--calendar-artifact", type=Path, action="append", required=True)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="正式寫入；省略時只做 dry-run",
    )
    args = parser.parse_args(argv)
    try:
        result = _execute(args)
    except Exception as exc:
        print(
            json.dumps(
                {"success": False, "error_type": type(exc).__name__, "error": str(exc)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps({"success": True, **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
