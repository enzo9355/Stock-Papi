import json
import tempfile
import unittest
from pathlib import Path

from reporting.observation_v2 import build_post_close_observation_metadata
from stock_papi.batch.observation_products import (
    promote_observation_candidate,
    write_observation_candidate,
)
from tests.test_observation_report_v2 import Calendar, dashboard


class ObservationCandidateTests(unittest.TestCase):
    def test_candidate_is_immutable_and_does_not_cut_over(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            snapshot = dashboard()
            metadata = build_post_close_observation_metadata(snapshot, Calendar())

            candidate = write_observation_candidate(root, metadata, snapshot)

            manifest = json.loads(
                (candidate / "candidate.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["kind"], "absorb-observation-candidate")
            self.assertEqual(manifest["product_mode"], "observation")
            self.assertEqual(
                set(manifest["files"]),
                {"dashboard-snapshot.json", "post-close-report-v2.json"},
            )
            self.assertFalse(
                (root / "publish" / "dashboard" / "v1" / "latest-TW.json").exists()
            )
            self.assertFalse(
                (
                    root
                    / "publish"
                    / "reports"
                    / "v2"
                    / "latest-TW-post_close.json"
                ).exists()
            )

    def test_promote_verifies_candidate_and_writes_latest_after_objects(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            snapshot = dashboard()
            metadata = build_post_close_observation_metadata(snapshot, Calendar())
            candidate = write_observation_candidate(root, metadata, snapshot)

            receipt = promote_observation_candidate(root, candidate)

            dashboard_latest = Path(receipt["dashboard_latest"])
            report_latest = Path(receipt["report_latest"])
            dashboard_pointer = json.loads(
                dashboard_latest.read_text(encoding="utf-8")
            )
            dashboard_object = (
                root
                / "publish"
                / "dashboard"
                / "v1"
                / dashboard_pointer["path"]
            )
            self.assertTrue(dashboard_object.is_file())
            self.assertEqual(dashboard_pointer["schema_version"], 2)
            self.assertEqual(
                dashboard_pointer["kind"], "absorb-observation-dashboard"
            )
            self.assertTrue(report_latest.is_file())

    def test_tampered_candidate_cannot_be_promoted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            snapshot = dashboard()
            metadata = build_post_close_observation_metadata(snapshot, Calendar())
            candidate = write_observation_candidate(root, metadata, snapshot)
            (candidate / "dashboard-snapshot.json").write_text(
                '{"tampered":true}', encoding="utf-8"
            )

            with self.assertRaisesRegex(ValueError, "hash"):
                promote_observation_candidate(root, candidate)


if __name__ == "__main__":
    unittest.main()
