import datetime
import tempfile
import unittest
from pathlib import Path

from stock_papi.batch.post_close import PostClosePipeline, PostClosePipelineError


UTC = datetime.timezone.utc
MANIFEST = "quant/v1/manifests/TW-20260714T090000Z-aaaaaaaaaaaa.json"


def source(date="2026-07-14", failure_rate=0.01):
    return {
        "market": "TW",
        "market_as_of": date,
        "manifest_path": MANIFEST,
        "manifest_sha256": "a" * 64,
        "model_version": "lgbm-5d-v1",
        "failure_rate": failure_rate,
        "sample_data": False,
    }


def callbacks(calls, load_source=lambda: source()):
    return {
        "load_source": load_source,
        "infer": lambda value: calls.append("infer") or {"forecasts": 3},
        "settle": lambda value: calls.append("settle") or {"matured": 2},
        "aggregate": lambda value, inference, settlement: calls.append("aggregate") or {"content": "report"},
        "render": lambda report: calls.append("render") or {"pdf_path": "staging/report.pdf", "page_count": 8},
        "publish": lambda report, rendered: calls.append("publish") or {"content_sha256": "b" * 64},
        "upload": lambda receipt: calls.append("upload") or {"uploaded": True},
        "remote_verify": lambda receipt: calls.append("verify") or {"verified": True},
        "notify": lambda receipt: calls.append("notify") or {"sent": True},
    }


class PostClosePipelineTests(unittest.TestCase):
    def test_happy_path_runs_all_stages_in_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            calls = []
            result = PostClosePipeline(
                Path(temporary),
                target_market_date=datetime.date(2026, 7, 14),
                source_manifest=MANIFEST,
                source_manifest_sha256="a" * 64,
                model_version="lgbm-5d-v1",
                callbacks=callbacks(calls),
            ).run(now=datetime.datetime(2026, 7, 14, 10, tzinfo=UTC))

            self.assertEqual(
                calls,
                ["infer", "settle", "aggregate", "render", "publish", "upload", "verify", "notify"],
            )
            self.assertEqual(result["status"], "completed")

    def test_source_readiness_is_bounded_and_target_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            attempts = iter([None, None, source(date="2026-07-13")])
            calls = []
            pipeline = PostClosePipeline(
                Path(temporary),
                target_market_date=datetime.date(2026, 7, 14),
                source_manifest=MANIFEST,
                source_manifest_sha256="a" * 64,
                model_version="lgbm-5d-v1",
                callbacks=callbacks(calls, load_source=lambda: next(attempts)),
                max_source_attempts=3,
                sleep_fn=lambda _seconds: None,
            )

            with self.assertRaisesRegex(PostClosePipelineError, "target"):
                pipeline.run(now=datetime.datetime(2026, 7, 14, 10, tzinfo=UTC))
            self.assertEqual(calls, [])

    def test_rerun_resumes_after_upload_failure_without_duplicate_publish_or_notify(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls = []
            wired = callbacks(calls)
            failures = [True]

            def upload(_receipt):
                calls.append("upload")
                if failures:
                    failures.pop()
                    raise RuntimeError("temporary upload failure")
                return {"uploaded": True}

            wired["upload"] = upload
            pipeline = PostClosePipeline(
                root,
                target_market_date=datetime.date(2026, 7, 14),
                source_manifest=MANIFEST,
                source_manifest_sha256="a" * 64,
                model_version="lgbm-5d-v1",
                callbacks=wired,
            )
            with self.assertRaises(RuntimeError):
                pipeline.run(now=datetime.datetime(2026, 7, 14, 10, tzinfo=UTC))

            result = pipeline.run(now=datetime.datetime(2026, 7, 14, 10, 5, tzinfo=UTC))

            self.assertEqual(calls.count("publish"), 1)
            self.assertEqual(calls.count("upload"), 2)
            self.assertEqual(calls.count("notify"), 1)
            self.assertEqual(result["status"], "completed")

    def test_dry_run_rejects_sample_and_never_renders_publishes_or_notifies(self):
        with tempfile.TemporaryDirectory() as temporary:
            calls = []
            wired = callbacks(calls)
            result = PostClosePipeline(
                Path(temporary),
                target_market_date=datetime.date(2026, 7, 14),
                source_manifest=MANIFEST,
                source_manifest_sha256="a" * 64,
                model_version="lgbm-5d-v1",
                callbacks=wired,
            ).run(
                now=datetime.datetime(2026, 7, 14, 10, tzinfo=UTC), dry_run=True
            )
            self.assertEqual(calls, ["infer", "settle", "aggregate"])
            self.assertTrue(result["dry_run"])

            sample_callbacks = callbacks([], load_source=lambda: dict(source(), sample_data=True))
            with self.assertRaisesRegex(PostClosePipelineError, "sample"):
                PostClosePipeline(
                    Path(temporary) / "sample",
                    target_market_date=datetime.date(2026, 7, 14),
                    source_manifest=MANIFEST,
                    source_manifest_sha256="a" * 64,
                    model_version="lgbm-5d-v1",
                    callbacks=sample_callbacks,
                ).run(now=datetime.datetime(2026, 7, 14, 10, tzinfo=UTC), dry_run=True)


if __name__ == "__main__":
    unittest.main()
