import datetime
import hashlib
import json
import unittest

from stock_papi.repositories.dashboard_snapshots import load_dashboard_snapshot


class DashboardSnapshotRepositoryTests(unittest.TestCase):
    def test_reads_only_hash_verified_dashboard_object(self):
        document = {
            "schema_version": 1,
            "kind": "absorb-daily-dashboard",
            "market": "TW",
            "inference_as_of": "2026-07-15",
            "sector_snapshot": {"sectors": {}},
            "heatmap": [],
            "daily_focus": [],
            "top_picks": [],
        }
        content = json.dumps(document, separators=(",", ":")).encode()
        digest = hashlib.sha256(content).hexdigest()
        latest = json.dumps({
            "schema_version": 1,
            "kind": "absorb-daily-dashboard",
            "market": "TW",
            "inference_as_of": "2026-07-15",
            "path": f"objects/{digest}.json",
            "sha256": digest,
            "size": len(content),
        }).encode()
        objects = {
            "dashboard/v1/latest-TW.json": latest,
            f"dashboard/v1/objects/{digest}.json": content,
        }
        result = load_dashboard_snapshot(
            today=datetime.date(2026, 7, 16),
            load_object=lambda name, _limit: objects.get(name),
            cache={},
        )
        self.assertEqual(result["inference_as_of"], "2026-07-15")


if __name__ == "__main__":
    unittest.main()
