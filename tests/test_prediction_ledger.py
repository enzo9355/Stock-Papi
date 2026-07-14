import datetime
import json
import tempfile
import unittest
from pathlib import Path

from stock_papi.batch.calendar import TradingCalendarSet, TWSE_CALENDAR_URL
from stock_papi.batch.prediction_ledger import PredictionLedger, PredictionLedgerError


UTC = datetime.timezone.utc


def calendars():
    return TradingCalendarSet.from_documents(
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


def forecast_kwargs():
    return {
        "entity_type": "stock",
        "entity_id": "2330",
        "source_market_date": datetime.date(2026, 7, 17),
        "probability": 64.5,
        "action": "優先關注",
        "reasons": ("機率高於門檻", "產業同步轉強"),
        "issued_at": datetime.datetime(2026, 7, 17, 9, tzinfo=UTC),
        "model_version": "lgbm-5d-v1",
        "source_manifest_sha256": "b" * 64,
    }


class PredictionLedgerTests(unittest.TestCase):
    def test_market_industry_and_stock_records_share_one_safe_schema(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = PredictionLedger(Path(temporary), "TW", calendars())
            records = [
                ledger.write_forecast(
                    **dict(forecast_kwargs(), entity_type=entity_type, entity_id=entity_id)
                )
                for entity_type, entity_id in (
                    ("market", "TAIEX"),
                    ("industry", "半導體"),
                    ("stock", "2330"),
                )
            ]

            self.assertEqual(
                {record["entity_type"] for record in records},
                {"market", "industry", "stock"},
            )
            self.assertTrue(
                all(Path(record["record_path"]).name == f"{record['forecast_id']}.json" for record in records)
            )

    def test_forecast_id_is_deterministic_idempotent_and_conflict_safe(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = PredictionLedger(Path(temporary), "TW", calendars())
            first = ledger.write_forecast(**forecast_kwargs())
            second = ledger.write_forecast(**forecast_kwargs())

            self.assertEqual(first["forecast_id"], second["forecast_id"])
            self.assertEqual(first["content_sha256"], second["content_sha256"])
            self.assertEqual(len(ledger.list_records()), 1)
            changed = dict(forecast_kwargs(), probability=99.0)
            with self.assertRaises(PredictionLedgerError):
                ledger.write_forecast(**changed)

    def test_five_actual_sessions_cross_weekend_and_holiday_before_maturity(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = PredictionLedger(Path(temporary), "TW", calendars())
            record = ledger.write_forecast(**forecast_kwargs())

            self.assertEqual(
                record["forecast_sessions"],
                ["2026-07-21", "2026-07-22", "2026-07-23", "2026-07-24", "2026-07-27"],
            )
            with self.assertRaisesRegex(PredictionLedgerError, "still active"):
                ledger.settle(
                    record["forecast_id"],
                    evaluated_on=datetime.date(2026, 7, 24),
                    status="matured",
                    actual_return=0.03,
                    reason=None,
                    settled_at=datetime.datetime(2026, 7, 24, 9, tzinfo=UTC),
                )

    def test_matured_and_invalid_settlements_append_without_mutating_forecast(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = PredictionLedger(Path(temporary), "TW", calendars())
            positive = ledger.write_forecast(**forecast_kwargs())
            invalid = ledger.write_forecast(
                **dict(forecast_kwargs(), entity_id="2317", probability=42.0)
            )
            ledger.write_forecast(
                **dict(
                    forecast_kwargs(),
                    entity_id="2454",
                    source_market_date=datetime.date(2026, 7, 28),
                    issued_at=datetime.datetime(2026, 7, 28, 9, tzinfo=UTC),
                    source_manifest_sha256="c" * 64,
                )
            )
            before = Path(positive["record_path"]).read_bytes()
            outcome = ledger.settle(
                positive["forecast_id"],
                evaluated_on=datetime.date(2026, 7, 27),
                status="matured",
                actual_return=0.03,
                reason=None,
                settled_at=datetime.datetime(2026, 7, 27, 9, tzinfo=UTC),
            )
            ledger.settle(
                invalid["forecast_id"],
                evaluated_on=datetime.date(2026, 7, 27),
                status="invalid",
                actual_return=None,
                reason="suspended",
                settled_at=datetime.datetime(2026, 7, 27, 9, tzinfo=UTC),
            )

            self.assertTrue(outcome["direction_correct"])
            self.assertEqual(Path(positive["record_path"]).read_bytes(), before)
            self.assertEqual(ledger.accuracy_summary(), {"matured": 1, "correct": 1, "accuracy": 1.0, "invalid": 1})

    def test_development_projection_shows_probability_reason_version_and_outcome_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = PredictionLedger(Path(temporary), "TW", calendars())
            prior = ledger.write_forecast(**forecast_kwargs())
            ledger.settle(
                prior["forecast_id"],
                evaluated_on=datetime.date(2026, 7, 27),
                status="matured",
                actual_return=0.03,
                reason=None,
                settled_at=datetime.datetime(2026, 7, 27, 9, tzinfo=UTC),
            )
            later = dict(
                forecast_kwargs(),
                source_market_date=datetime.date(2026, 7, 28),
                probability=58.0,
                reasons=("估值偏高",),
                model_version="lgbm-5d-v2",
                source_manifest_sha256="c" * 64,
                issued_at=datetime.datetime(2026, 7, 28, 9, tzinfo=UTC),
            )
            ledger.write_forecast(**later)

            projection = ledger.development_projection("stock", "2330")

            self.assertEqual(projection["probability_change"], -6.5)
            self.assertEqual(projection["trend"], "down")
            self.assertEqual(projection["reasons_added"], ["估值偏高"])
            self.assertEqual(
                projection["reasons_removed"], ["機率高於門檻", "產業同步轉強"]
            )
            self.assertTrue(projection["model_version_changed"])
            self.assertEqual(projection["recent_matured"][0]["direction_correct"], True)


if __name__ == "__main__":
    unittest.main()
