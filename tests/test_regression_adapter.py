# -*- coding: utf-8 -*-
"""Tests for OLS factor regression adapter with Newey-West HAC covariance."""

import unittest


class TestRegressionAdapter(unittest.TestCase):

    def test_computes_newey_west_hac_estimates(self):
        from reporting.regression_adapter import compute_ols_hac_regression

        # Synthetic 100-session dataset with deterministic linear relationship
        import numpy as np
        np.random.seed(42)
        n = 100
        x1 = np.random.normal(0, 1, n)
        x2 = np.random.normal(0, 1, n)
        # y = 0.05 + 0.04*x1 + 0.08*x2 + e
        e = np.random.normal(0, 0.01, n)
        y = 0.05 + 0.04 * x1 + 0.08 * x2 + e

        dependent_series = y.tolist()
        factor_matrix = np.column_stack([x1, x2]).tolist()
        factor_names = ["volume_surge_ratio", "foreign_net_flow_ratio"]

        fit_stats, results, diag = compute_ols_hac_regression(
            dependent_series=dependent_series,
            factor_matrix=factor_matrix,
            factor_names=factor_names,
            lags=4,
        )

        self.assertGreater(fit_stats["r_squared"], 0.8)
        self.assertEqual(len(results), 2)
        item1 = next(r for r in results if r["factor_name"] == "volume_surge_ratio")
        self.assertAlmostEqual(item1["coefficient"], 0.04, delta=0.01)
        self.assertGreater(item1["t_statistic"], 0)
        self.assertLess(item1["p_value"], 0.05)
        self.assertIn("multicollinearity", diag)

    def test_rank_deficient_matrix_raises_value_error(self):
        from reporting.regression_adapter import compute_ols_hac_regression

        # Dependent and collinear factor columns
        y = [0.01 * i for i in range(50)]
        x1 = [1.0 * i for i in range(50)]
        x2 = [2.0 * i for i in range(50)]  # Perfect collinearity with x1

        with self.assertRaises((ValueError, RuntimeError)):
            compute_ols_hac_regression(
                dependent_series=y,
                factor_matrix=[[a, b] for a, b in zip(x1, x2)],
                factor_names=["x1", "x2"],
                lags=4,
            )


if __name__ == "__main__":
    unittest.main()
