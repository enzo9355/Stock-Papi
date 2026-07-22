# -*- coding: utf-8 -*-
"""Tests for Regression Research Artifact schema definitions and canonical serializer."""

import unittest


class TestRegressionSchema(unittest.TestCase):

    def test_empty_document_raises_validation_error(self):
        from reporting.regression_schema import RegressionResearchArtifact
        with self.assertRaises((ValueError, KeyError, TypeError)):
            RegressionResearchArtifact.from_document({})

    def test_valid_document_serialization_and_hash(self):
        from reporting.regression_schema import (
            RegressionResearchArtifact,
            serialize_regression_artifact,
        )
        doc = {
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
                "content_sha256": "",
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
                "independent_variables": [
                    "volume_surge_ratio",
                    "foreign_net_flow_ratio",
                    "volatility_20d"
                ],
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
            "results": [
                {
                    "factor_name": "volume_surge_ratio",
                    "display_label": "成交量異常放大比率",
                    "coefficient": 0.0425,
                    "standard_error": 0.0112,
                    "t_statistic": 3.7946,
                    "p_value": 0.0002,
                    "confidence_interval_low": 0.0205,
                    "confidence_interval_high": 0.0645,
                    "direction": "positive",
                    "economic_magnitude": "moderate",
                    "display_status": "statistically_significant"
                }
            ],
            "fit_statistics": {
                "r_squared": 0.2845,
                "adjusted_r_squared": 0.2726,
                "residual_standard_error": 0.0312,
                "degrees_of_freedom": 241,
                "f_statistic": 47.92,
                "f_p_value": 0.000001
            },
            "diagnostics": {
                "multicollinearity": {
                    "status": "passed",
                    "max_vif": 1.85,
                    "vif_details": {"volume_surge_ratio": 1.42}
                },
                "heteroskedasticity": {
                    "status": "passed",
                    "test_name": "breusch_pagan",
                    "test_statistic": 3.38,
                    "p_value": 0.184,
                    "threshold": 0.05
                },
                "autocorrelation": {
                    "status": "passed",
                    "durbin_watson": 1.94
                },
                "residual_normality": {
                    "status": "passed",
                    "jarque_bera_p_value": 0.125
                },
                "data_quality": {
                    "missing_rate": 0.0,
                    "outlier_count": 3
                },
                "warnings": []
            },
            "presentation": {
                "headline": "近 245 個交易日因子迴歸分析顯示外資動向與成交量異常具有統計顯著相關性",
                "summary": "在控制 20 日波動度後，外資買賣超比率與成交量放大比率對大盤 5 日未來報酬展現正向係數關係 (p < 0.01)。",
                "key_exposures": [
                    "外資買賣超比率: 係數 +0.0812 (t=4.16, p < 0.001)"
                ],
                "limitations": "本分析為歷史 OLS 迴歸結果，反映過去 245 個交易日之統計相關性，不代表未來因果關係。",
                "disclosure": "模型尚未通過 Ranking、Calibration、Quality 與 Transaction Value，因此不提供正式預測機率。"
            }
        }
        artifact = RegressionResearchArtifact.from_document(doc)
        self.assertEqual(artifact.schema_version, 1)
        self.assertEqual(artifact.kind, "absorb-regression-research-artifact")
        serialized = serialize_regression_artifact(artifact.to_document())
        self.assertIsInstance(serialized, bytes)
        self.assertTrue(len(serialized) > 0)

    def test_forbidden_words_rejected_in_presentation(self):
        from reporting.regression_schema import RegressionResearchArtifact
        doc = {
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
                "content_sha256": "",
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
                "headline": "預測勝率為 80%",
                "summary": "買進訊號強烈",
                "key_exposures": [],
                "limitations": "無",
                "disclosure": "模型尚未通過 Ranking..."
            }
        }
        with self.assertRaises(ValueError):
            RegressionResearchArtifact.from_document(doc)


if __name__ == "__main__":
    unittest.main()
