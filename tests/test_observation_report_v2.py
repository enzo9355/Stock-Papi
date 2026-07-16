import datetime
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from reporting.observation_v2 import build_post_close_observation_metadata
from reporting.publisher import publish_report_v2
from reporting.schemas import ReportMetadataV2
from reporting.web import validate_report_index, validate_report_metadata
from reporting.exceptions import ReportWebError


def dashboard():
    return {
        "schema_version": 2,
        "kind": "absorb-observation-dashboard",
        "product_mode": "observation",
        "market": "TW",
        "observation_as_of": "2026-07-16",
        "generated_at": "2026-07-16T10:30:00Z",
        "source_manifest": (
            "quant/v1/manifests/TW-20260716T100000Z-aaaaaaaaaaaa.json"
        ),
        "source_manifest_sha256": "a" * 64,
        "prediction_capability": {
            "mode": "research",
            "observation_enabled": True,
            "probability_allowed": False,
            "ranking_allowed": False,
            "strong_action_allowed": False,
            "performance_endorsement_allowed": False,
        },
        "market_observation": {
            "return_1d_pct": 0.6,
            "risk_state": "normal",
        },
        "industry_observations": [
            {
                "name": "半導體",
                "relative_return_5d_pct": 1.2,
                "display_order": 1,
            }
        ],
        "heatmap": [
            {
                "name": "半導體",
                "metric_name": "relative_return_5d_pct",
                "metric_value_pct": 1.2,
            }
        ],
        "stock_events": [],
        "etf_observations": [],
        "daily_focus": ["市場風險狀態：normal", "半導體 5 日相對大盤 +1.20%"],
        "data_quality": {"coverage": 0.997, "failure_rate": 0.003},
        "gates": {"prediction_separation": "PASS"},
    }


class Calendar:
    def next_session(self, value):
        self.requested = value
        return datetime.date(2026, 7, 17)


class ObservationReportV2Tests(unittest.TestCase):
    def test_builder_creates_backward_compatible_observation_metadata(self):
        metadata = build_post_close_observation_metadata(dashboard(), Calendar())
        parsed = ReportMetadataV2.from_document(metadata)

        self.assertEqual(parsed.product_mode, "observation")
        self.assertEqual(parsed.model_versions, {})
        self.assertEqual(metadata["title"], "2026-07-16 盤後市場觀察")
        self.assertEqual(metadata["observation_start_date"], "2026-07-16")
        self.assertEqual(metadata["observation_end_date"], "2026-07-17")
        self.assertEqual(
            metadata["prediction_capability"]["mode"], "research"
        )
        encoded = json.dumps(metadata, ensure_ascii=False)
        for forbidden in ("上漲機率", "推薦買進", "勝率", "direction_score"):
            self.assertNotIn(forbidden, encoded)

    def test_prediction_metadata_still_requires_model_versions(self):
        document = build_post_close_observation_metadata(dashboard(), Calendar())
        document.pop("product_mode")
        document.pop("observation_start_date")
        document.pop("observation_end_date")
        document.pop("prediction_capability")

        with self.assertRaisesRegex(ValueError, "schema"):
            ReportMetadataV2.from_document(document)

    def test_publisher_indexes_product_mode_and_latest_last(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            metadata = build_post_close_observation_metadata(
                dashboard(), Calendar()
            )

            latest_path = publish_report_v2(root, metadata)

            publish = root / "publish" / "reports" / "v2"
            latest = json.loads(latest_path.read_text(encoding="utf-8"))
            index = json.loads(
                (publish / "index-TW.json").read_text(encoding="utf-8")
            )
            entry = index["reports"][0]
            metadata_bytes = (publish / entry["metadata"]).read_bytes()
            saved = json.loads(metadata_bytes)
            self.assertEqual(entry["product_mode"], "observation")
            self.assertEqual(latest["product_mode"], "observation")
            self.assertEqual(saved["product_mode"], "observation")
            self.assertEqual(saved["model_versions"], {})
            self.assertEqual(
                hashlib.sha256(metadata_bytes).hexdigest(),
                entry["metadata_sha256"],
            )
            self.assertEqual(latest["metadata"], entry["metadata"])
            verified = validate_report_index(
                (publish / "index-TW.json").read_bytes()
            )
            self.assertEqual(
                validate_report_metadata(metadata_bytes, verified[0])[
                    "product_mode"
                ],
                "observation",
            )

    def test_web_validation_binds_observation_mode_to_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            publish_report_v2(
                root,
                build_post_close_observation_metadata(dashboard(), Calendar()),
            )
            publish = root / "publish" / "reports" / "v2"
            item = validate_report_index(
                (publish / "index-TW.json").read_bytes()
            )[0]
            metadata = json.loads(
                (publish / item["metadata"]).read_text(encoding="utf-8")
            )
            metadata.pop("product_mode")
            metadata.pop("observation_start_date")
            metadata.pop("observation_end_date")
            metadata.pop("prediction_capability")
            encoded = json.dumps(
                metadata,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            tampered_item = {
                **item,
                "metadata_sha256": hashlib.sha256(encoded).hexdigest(),
            }

            with self.assertRaises(ReportWebError):
                validate_report_metadata(encoded, tampered_item)


if __name__ == "__main__":
    unittest.main()
