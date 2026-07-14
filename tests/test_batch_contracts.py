import datetime
import unittest


from stock_papi.batch.calendar import TradingCalendarSet
from stock_papi.batch.contracts import (
    ContractError,
    DailyRunCheckpoint,
    build_post_close_timing,
)


def calendar_document(year, *, closed=()):
    return {
        "schema_version": 1,
        "market": "TW",
        "year": year,
        "source_url": "https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule",
        "fetched_at": f"{year - 1}-12-01T00:00:00Z",
        "source_sha256": "b" * 64,
        "valid_from": f"{year}-01-01",
        "valid_to": f"{year}-12-31",
        "closed_dates": list(closed),
        "special_open_dates": [],
    }


class BatchContractTests(unittest.TestCase):
    def setUp(self):
        self.calendars = TradingCalendarSet.from_documents([
            calendar_document(2026, closed=("2026-07-20",))
        ])

    def test_post_close_timing_uses_verified_sessions_and_aware_time(self):
        timing = build_post_close_timing(
            source_market_date=datetime.date(2026, 7, 17),
            published_at=datetime.datetime(
                2026, 7, 17, 10, 42, tzinfo=datetime.timezone.utc
            ),
            backtest_as_of=datetime.date(2026, 7, 15),
            calendars=self.calendars,
        )

        self.assertEqual(timing.applicable_trading_date, datetime.date(2026, 7, 21))
        self.assertEqual(timing.forecast_start_date, datetime.date(2026, 7, 21))
        self.assertEqual(timing.forecast_end_date, datetime.date(2026, 7, 27))
        self.assertEqual(timing.source_market_date, datetime.date(2026, 7, 17))
        self.assertEqual(timing.backtest_as_of, datetime.date(2026, 7, 15))

    def test_post_close_timing_rejects_naive_time_and_non_session_source(self):
        with self.assertRaises(ContractError):
            build_post_close_timing(
                source_market_date=datetime.date(2026, 7, 17),
                published_at=datetime.datetime(2026, 7, 17, 18, 42),
                backtest_as_of=datetime.date(2026, 7, 15),
                calendars=self.calendars,
            )

        with self.assertRaises(ContractError):
            build_post_close_timing(
                source_market_date=datetime.date(2026, 7, 20),
                published_at=datetime.datetime.now(datetime.timezone.utc),
                backtest_as_of=datetime.date(2026, 7, 15),
                calendars=self.calendars,
            )

    def test_daily_checkpoint_round_trip_preserves_target_and_versions(self):
        checkpoint = DailyRunCheckpoint(
            run_id="20260717T104200Z-abcdef12",
            target_market_date=datetime.date(2026, 7, 17),
            source_manifest="quant/v1/manifests/TW-20260717T100000Z-abcdef123456.json",
            source_manifest_sha256="c" * 64,
            model_version="lgbm-5d-v1",
            next_index=2,
            completed_symbols=("2330", "2317"),
            failed_symbols=("0000",),
            started_at=datetime.datetime(2026, 7, 17, 10, tzinfo=datetime.timezone.utc),
            updated_at=datetime.datetime(2026, 7, 17, 10, 42, tzinfo=datetime.timezone.utc),
            status="running",
        )

        self.assertEqual(DailyRunCheckpoint.from_dict(checkpoint.to_dict()), checkpoint)

    def test_daily_checkpoint_rejects_target_or_manifest_mismatch(self):
        document = {
            "schema_version": 1,
            "job_type": "daily_prediction",
            "run_id": "20260717T104200Z-abcdef12",
            "target_market_date": "2026-07-17",
            "source_manifest": "quant/v1/manifests/TW-20260717T100000Z-abcdef123456.json",
            "source_manifest_sha256": "c" * 64,
            "model_version": "lgbm-5d-v1",
            "next_index": 0,
            "completed_symbols": [],
            "failed_symbols": [],
            "started_at": "2026-07-17T10:00:00Z",
            "updated_at": "2026-07-17T10:00:00Z",
            "status": "running",
        }
        checkpoint = DailyRunCheckpoint.from_dict(document)

        checkpoint.assert_resume_compatible(
            target_market_date=datetime.date(2026, 7, 17),
            source_manifest_sha256="c" * 64,
            model_version="lgbm-5d-v1",
        )
        with self.assertRaises(ContractError):
            checkpoint.assert_resume_compatible(
                target_market_date=datetime.date(2026, 7, 18),
                source_manifest_sha256="c" * 64,
                model_version="lgbm-5d-v1",
            )

    def test_daily_checkpoint_rejects_non_date_target(self):
        with self.assertRaises(ContractError):
            DailyRunCheckpoint(
                run_id="20260717T104200Z-abcdef12",
                target_market_date="2026-07-17",
                source_manifest="quant/v1/manifests/TW-20260717T100000Z-abcdef123456.json",
                source_manifest_sha256="c" * 64,
                model_version="lgbm-5d-v1",
                next_index=0,
                completed_symbols=(),
                failed_symbols=(),
                started_at=datetime.datetime.now(datetime.timezone.utc),
                updated_at=datetime.datetime.now(datetime.timezone.utc),
                status="running",
            )


if __name__ == "__main__":
    unittest.main()
