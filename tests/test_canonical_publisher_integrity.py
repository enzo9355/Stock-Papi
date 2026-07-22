import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reporting.config import MAX_CANONICAL_REPORT_BYTES, ReportConfig
from reporting.exceptions import ReportPublishError
from reporting.professional_schema import (
    ProfessionalPostCloseReport,
    compute_content_sha256,
)
from reporting.publisher import publish_report_v2
from tests.test_professional_report_schema import ProfessionalReportSchemaTests


class CanonicalPublisherIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_publishes_regression_artifact_with_single_hash_ownership(self):
        report_doc = self._base_report_doc()
        metadata_doc = self._base_metadata_doc(report_doc)
        prof_report = ProfessionalPostCloseReport.from_document(report_doc)

        reg_artifact_doc = {
            "schema_version": 1,
            "kind": "absorb-regression-research-artifact",
            "identity": {
                "artifact_id": "TW-20260717-regression-ols-v1",
                "market": "TW",
                "source_market_date": "2026-07-17",
                "applicable_trading_date": "2026-07-20",
                "generated_at": "2026-07-17T10:30:00Z",
                "source_manifest": "quant/v1/manifests/TW-20260717T103000Z-a1b2c3d4e5f6.json",
                "source_manifest_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "input_dataset_object": "objects/regression-input/f1e2d3c4b5a697887766554433221100f1e2d3c4b5a697887766554433221100.json",
                "input_dataset_sha256": "f1e2d3c4b5a697887766554433221100f1e2d3c4b5a697887766554433221100",
                "input_dataset_content_sha256": "e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6",
                "input_dataset_rows_sha256": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2",
                "code_commit_sha": "da25d594d3b76865da22b891285ac0c85e710d86",
                "generator_version": "1.0.0",
                "content_sha256": "8f7e6d5c4b3a2109876543210fedcba98f7e6d5c4b3a2109876543210fedcba9",
                "regression_spec_version": "1.0"
            },
            "regression_spec": {
                "analysis_scope": "market_level_daily",
                "entity_type": "market_index",
                "universe_definition": "TWSE_TAIEX",
                "observation_unit": "daily_session",
                "model_family": "ols_linear_factor",
                "dependent_variable": "five_session_forward_return",
                "dependent_variable_definition": "5-session forward return over official TAIEX daily closing prices",
                "independent_variables": ["volume_surge_ratio"],
                "intercept": True,
                "frequency": "daily",
                "first_feature_session": "2025-07-10",
                "last_feature_session": "2026-07-10",
                "first_label_end_session": "2025-07-17",
                "last_label_end_session": "2026-07-17",
                "label_horizon_sessions": 5,
                "sample_count": 245,
                "missing_value_policy": "listwise_deletion",
                "standardization_policy": "z_score",
                "outlier_policy": "winsorize_1_99",
                "covariance_estimator": "newey_west_hac",
                "hac_max_lags": 4,
                "confidence_level": 0.95
            },
            "results": [],
            "fit_statistics": {
                "r_squared": 0.1,
                "adjusted_r_squared": 0.09,
                "residual_standard_error": 0.01,
                "degrees_of_freedom": 200,
                "f_statistic": 10.0,
                "f_p_value": 0.001
            },
            "diagnostics": {
                "multicollinearity": {"status": "passed", "max_vif": 1.0, "vif_details": {}},
                "heteroskedasticity": {"status": "passed", "test_name": "breusch_pagan", "test_statistic": 1.0, "p_value": 0.5, "threshold": 0.05},
                "autocorrelation": {"status": "passed", "durbin_watson": 2.0},
                "residual_normality": {"status": "passed", "jarque_bera_p_value": 0.5},
                "data_quality": {"missing_rate": 0.0, "outlier_count": 0},
                "warnings": []
            },
            "presentation": {
                "headline": "近 245 個交易日因子迴歸分析顯示相關性",
                "summary": "迴歸分析摘要",
                "key_exposures": [],
                "limitations": "歷史數據結果",
                "disclosure": "模型尚未通過 Ranking、Calibration、Quality 與 Transaction Value，因此不提供正式預測機率。"
            }
        }

        latest_path = publish_report_v2(
            self.root,
            metadata_doc,
            professional_report=prof_report,
            regression_artifact=reg_artifact_doc,
        )
        self.assertTrue(latest_path.exists())
        latest_doc = json.loads(latest_path.read_text(encoding="utf-8"))
        self.assertIn("metadata", latest_doc)
        meta_file = self.root / "publish" / "reports" / "v2" / latest_doc["metadata"]
        published_meta = json.loads(meta_file.read_text(encoding="utf-8"))
        self.assertIn("regression_research", published_meta)
        reg_ptr = published_meta["regression_research"]
        reg_file = self.root / "publish" / "reports" / "v2" / reg_ptr["object"]
        self.assertTrue(reg_file.exists())

    def _base_report_doc(self):
        return ProfessionalReportSchemaTests()._document()

    def _base_metadata_doc(self, report_doc):
        identity = report_doc["identity"]
        return {
            "schema_version": 2,
            "report_type": "post_close",
            "market": "TW",
            "source_market_date": identity["source_market_date"],
            "applicable_trading_date": identity["applicable_trading_date"],
            "published_at": "2026-07-17T10:30:00Z",
            "forecast_start_date": identity["applicable_trading_date"],
            "forecast_end_date": "2026-07-24",
            "backtest_as_of": None,
            "data_as_of": identity["source_market_date"],
            "source_manifest": identity["source_manifest"],
            "source_manifest_sha256": identity["source_manifest_sha256"],
            "model_versions": {},
            "title": "ABSORB 日報",
            "summary": ["日報"],
            "warnings": [],
            "content": {"observation": "test"},
            "product_mode": "observation",
            "observation_start_date": identity["source_market_date"],
            "observation_end_date": identity["applicable_trading_date"],
            "prediction_capability": {
                "mode": "research",
                "observation_enabled": True,
                "probability_allowed": False,
                "ranking_allowed": False,
                "strong_action_allowed": False,
                "performance_endorsement_allowed": False,
            },
        }

    def _create_padded_report(self, target_bytes: int) -> ProfessionalPostCloseReport:
        report_doc = self._base_report_doc()
        report_doc["market"]["data"]["padding"] = ""
        report_doc["identity"]["content_sha256"] = compute_content_sha256(report_doc)
        base_bytes = len(
            json.dumps(report_doc, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        )
        needed = target_bytes - base_bytes
        if needed < 0:
            raise ValueError(f"target_bytes {target_bytes} smaller than base_bytes {base_bytes}")
        report_doc["market"]["data"]["padding"] = "x" * needed
        report_doc["identity"]["content_sha256"] = compute_content_sha256(report_doc)
        actual_bytes = len(
            json.dumps(report_doc, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        )
        self.assertEqual(actual_bytes, target_bytes)
        return ProfessionalPostCloseReport.from_document(report_doc)

    def test_successful_canonical_report_publishing(self):
        report_doc = self._base_report_doc()
        metadata_doc = self._base_metadata_doc(report_doc)
        professional_report = ProfessionalPostCloseReport.from_document(report_doc)

        latest_path = publish_report_v2(
            root=self.root,
            metadata=metadata_doc,
            professional_report=professional_report,
        )

        self.assertTrue(latest_path.exists())
        publish_dir = self.root / "publish" / "reports" / "v2"

        index_path = publish_dir / "index-TW.json"
        self.assertTrue(index_path.exists())
        index_data = json.loads(index_path.read_text(encoding="utf-8"))
        self.assertEqual(len(index_data["reports"]), 1)

        meta_rel = index_data["reports"][0]["metadata"]
        meta_path = publish_dir / meta_rel
        self.assertTrue(meta_path.exists())
        meta_content = json.loads(meta_path.read_text(encoding="utf-8"))
        self.assertIn("professional_report", meta_content)

        ptr = meta_content["professional_report"]
        canonical_obj_path = publish_dir / ptr["object"]
        self.assertTrue(canonical_obj_path.exists())

        canonical_bytes = canonical_obj_path.read_bytes()
        self.assertGreater(len(canonical_bytes), 0)
        self.assertEqual(hashlib.sha256(canonical_bytes).hexdigest(), ptr["sha256"])

        readback_canonical = json.loads(canonical_bytes.decode("utf-8"))
        self.assertEqual(readback_canonical["identity"]["content_sha256"], ptr["content_sha256"])

    def test_fails_closed_on_binding_mismatch(self):
        report_doc = self._base_report_doc()
        metadata_doc = self._base_metadata_doc(report_doc)
        metadata_doc["source_manifest"] = "quant/v1/manifests/TW-20260717T091000Z-999999999aaa.json"
        professional_report = ProfessionalPostCloseReport.from_document(report_doc)

        with self.assertRaises(ReportPublishError):
            publish_report_v2(
                root=self.root,
                metadata=metadata_doc,
                professional_report=professional_report,
            )

        publish_dir = self.root / "publish" / "reports" / "v2"
        canonical_dir = publish_dir / "objects" / "canonical"
        if canonical_dir.exists():
            self.assertEqual(len(list(canonical_dir.glob("*.json"))), 0)

    def test_fails_closed_on_corrupted_content_sha(self):
        import dataclasses
        report_doc = self._base_report_doc()
        professional_report = ProfessionalPostCloseReport.from_document(report_doc)
        bad_identity = dataclasses.replace(professional_report.identity, content_sha256="a" * 64)
        professional_report = dataclasses.replace(professional_report, identity=bad_identity)
        metadata_doc = self._base_metadata_doc(report_doc)

        with self.assertRaises(ReportPublishError):
            publish_report_v2(
                root=self.root,
                metadata=metadata_doc,
                professional_report=professional_report,
            )

    def test_rejects_dict_professional_report(self):
        report_doc = self._base_report_doc()
        metadata_doc = self._base_metadata_doc(report_doc)

        with self.assertRaises(ReportPublishError):
            publish_report_v2(
                root=self.root,
                metadata=metadata_doc,
                professional_report=report_doc,
            )

        publish_dir = self.root / "publish" / "reports" / "v2"
        canonical_dir = publish_dir / "objects" / "canonical"
        if canonical_dir.exists():
            self.assertEqual(len(list(canonical_dir.glob("*.json"))), 0)

    def test_prewrite_payload_exact_max_bytes_passes(self):
        report = self._create_padded_report(MAX_CANONICAL_REPORT_BYTES)
        report_doc = self._base_report_doc()
        metadata_doc = self._base_metadata_doc(report_doc)

        latest_path = publish_report_v2(
            root=self.root,
            metadata=metadata_doc,
            professional_report=report,
        )
        self.assertTrue(latest_path.exists())

    def test_prewrite_payload_exceeding_max_bytes_raises_publish_error(self):
        report = self._create_padded_report(MAX_CANONICAL_REPORT_BYTES + 1)
        report_doc = self._base_report_doc()
        metadata_doc = self._base_metadata_doc(report_doc)

        with self.assertRaises(ReportPublishError) as cm:
            publish_report_v2(
                root=self.root,
                metadata=metadata_doc,
                professional_report=report,
            )
        self.assertIn("canonical report object size invalid", str(cm.exception))

    def test_readback_payload_exceeding_max_bytes_raises_publish_error(self):
        import reporting.publisher

        report_doc = self._base_report_doc()
        metadata_doc = self._base_metadata_doc(report_doc)
        professional_report = ProfessionalPostCloseReport.from_document(report_doc)

        original_write_atomic = reporting.publisher._write_atomic

        def fake_write_atomic(path, content):
            if "objects/canonical" in path.as_posix():
                original_write_atomic(path, b"x" * (MAX_CANONICAL_REPORT_BYTES + 1))
            else:
                original_write_atomic(path, content)

        with patch("reporting.publisher._write_atomic", side_effect=fake_write_atomic):
            with self.assertRaises(ReportPublishError) as cm:
                publish_report_v2(
                    root=self.root,
                    metadata=metadata_doc,
                    professional_report=professional_report,
                )
            self.assertIn("canonical read-back size invalid", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
