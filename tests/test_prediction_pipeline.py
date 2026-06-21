import os
import unittest

import numpy as np
import pandas as pd

os.environ.setdefault("LINE_CHANNEL_ACCESS_TOKEN", "test")
os.environ.setdefault("LINE_CHANNEL_SECRET", "test")

import app as stock_app


class PredictionPipelineTests(unittest.TestCase):
    def test_last_five_rows_have_no_training_target(self):
        frame = pd.DataFrame({"Close": np.arange(1.0, 21.0)})

        result = stock_app.add_prediction_target(frame)

        horizon = stock_app.PREDICTION_HORIZON
        self.assertTrue(result["FUTURE_RET_5"].tail(horizon).isna().all())
        self.assertTrue(result["T"].tail(horizon).isna().all())
        self.assertEqual(int(result["T"].notna().sum()), 15)

    def test_walk_forward_splits_keep_five_row_gap(self):
        for train, test in stock_app.build_time_splits(120):
            self.assertLess(train[-1], test[0])
            self.assertGreaterEqual(
                test[0] - train[-1] - 1,
                stock_app.PREDICTION_HORIZON,
            )

    def test_backtest_uses_five_day_returns_and_cost(self):
        future = pd.Series([0.02] * 10)
        probabilities = pd.Series([0.7] * 10)

        metrics = stock_app.score_oos_predictions(future, probabilities)

        expected = (
            (1 + 0.02 - stock_app.ROUND_TRIP_COST) ** 2 - 1
        ) * 100
        self.assertAlmostEqual(metrics["strat_cum"], expected, places=8)
        self.assertEqual(metrics["trades"], 2)


if __name__ == "__main__":
    unittest.main()
