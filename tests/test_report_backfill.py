import datetime
import unittest
from types import SimpleNamespace

from reporting.backfill import BackfillError, plan_backfill
from reporting.schemas import ReportMetadataV2
from reporting.v2_builder import build_post_close_metadata
from stock_papi.batch.calendar import TradingCalendarSet, TWSE_CALENDAR_URL


class ReportBackfillTests(unittest.TestCase):
    def test_default_is_dry_run_and_only_verified_explicit_manifest_is_planned(self):
        manifest = "quant/v1/manifests/TW-20260713T090000Z-aaaaaaaaaaaa.json"
        plan = plan_backfill(
            dates=[datetime.date(2026, 7, 13), datetime.date(2026, 7, 14)],
            manifest_path=manifest, manifest_sha256="a" * 64, model_version="lgbm-5d-v1",
            load_verified_manifest=lambda path, sha: {"path": path, "sha256": sha, "market_as_of": "2026-07-13"},
            today=datetime.date(2026, 7, 14),
        )
        self.assertTrue(plan["dry_run"])
        self.assertEqual(len(plan["commands"]), 1)
        self.assertIn("2026-07-13", plan["commands"][0])

    def test_unverified_future_and_missing_identity_fail_closed(self):
        common = dict(dates=[datetime.date(2026, 7, 15)], manifest_path="quant/v1/manifests/TW-20260715T090000Z-aaaaaaaaaaaa.json", manifest_sha256="a" * 64, model_version="lgbm-5d-v1", today=datetime.date(2026, 7, 14))
        with self.assertRaises(BackfillError): plan_backfill(load_verified_manifest=lambda *_: None, **common)

    def test_v2_builder_uses_verified_sessions_and_point_in_time_source(self):
        calendars = TradingCalendarSet.from_documents(
            [
                {
                    "schema_version": 1,
                    "market": "TW",
                    "year": 2026,
                    "source_url": TWSE_CALENDAR_URL,
                    "fetched_at": "2026-01-01T00:00:00Z",
                    "source_sha256": "a" * 64,
                    "valid_from": "2026-01-01",
                    "valid_to": "2026-12-31",
                    "closed_dates": ["2026-07-20"],
                    "special_open_dates": [],
                }
            ]
        )
        source = SimpleNamespace(
            manifest=SimpleNamespace(
                market_as_of=datetime.date(2026, 7, 17),
                manifest_path="manifests/TW-20260717T090000Z-aaaaaaaaaaaa.json",
                manifest_sha256="a" * 64,
                coverage=0.99,
                failure_rate=0.01,
            )
        )
        report = SimpleNamespace(
            source=source,
            generated_at=datetime.datetime(2026, 7, 17, 10, tzinfo=datetime.timezone.utc),
            warnings=[],
            summary=["市場整理"],
            model_versions={"lgbm-5d-v1": 100},
        )
        import reporting.v2_builder as builder

        original = builder.build_public_report
        builder.build_public_report = lambda _report: {"schema_version": 1}
        try:
            metadata = build_post_close_metadata(report, calendars)
        finally:
            builder.build_public_report = original

        self.assertEqual(metadata["applicable_trading_date"], "2026-07-21")
        self.assertEqual(metadata["forecast_end_date"], "2026-07-27")
        self.assertEqual(ReportMetadataV2.from_document(metadata).source_market_date, datetime.date(2026, 7, 17))


if __name__ == "__main__": unittest.main()
