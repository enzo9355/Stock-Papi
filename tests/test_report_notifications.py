import datetime
import tempfile
import unittest
from pathlib import Path

from stock_papi.batch.notifications import NotificationManager


UTC = datetime.timezone.utc


class ReportNotificationTests(unittest.TestCase):
    def test_content_hash_receipt_is_pending_then_sent_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            calls = []
            manager = NotificationManager(Path(temporary), send=lambda message, audience: calls.append((message, audience)))
            kwargs = dict(report_type="post_close", content_sha256="a" * 64, audience="broadcast", public_url="https://stock.example/reports/trading-day/2026-07-15", summary=["市場整理"], now=datetime.datetime.now(UTC))
            first = manager.deliver(**kwargs)
            second = manager.deliver(**kwargs)
            self.assertEqual(first["status"], "sent")
            self.assertEqual(second["status"], "sent")
            self.assertEqual(len(calls), 1)

    def test_failure_retries_are_bounded_and_do_not_leak_error_or_private_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            attempts = []
            def fail(_message, _audience):
                attempts.append(1)
                raise RuntimeError("Bearer secret-token D:\\StockPapiData bucket-private")
            result = NotificationManager(Path(temporary), send=fail, max_attempts=2).deliver(
                report_type="pre_market", content_sha256="b" * 64, audience="admin",
                public_url="https://stock.example/reports/2026-07-15/pre-market",
                summary=["資料不足，維持盤後判斷"], now=datetime.datetime.now(UTC),
            )
            self.assertEqual(result["status"], "failed")
            self.assertEqual(len(attempts), 2)
            persisted = Path(result["receipt_path"]).read_text(encoding="utf-8")
            self.assertNotIn("secret-token", persisted)
            self.assertNotIn("StockPapiData", persisted)
            self.assertNotIn("bucket-private", persisted)

    def test_admin_and_broadcast_use_separate_receipts(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager = NotificationManager(Path(temporary), send=lambda *_: None)
            common = dict(report_type="post_close", content_sha256="c" * 64, public_url="https://stock.example/reports/trading-day/2026-07-15", summary=[], now=datetime.datetime.now(UTC))
            admin = manager.deliver(audience="admin", **common)
            broadcast = manager.deliver(audience="broadcast", **common)
            self.assertNotEqual(admin["notification_key"], broadcast["notification_key"])


if __name__ == "__main__":
    unittest.main()
