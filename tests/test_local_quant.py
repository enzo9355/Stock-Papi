import datetime
import unittest
from pathlib import Path

from local_quant import TAIPEI, validate_data_root, window_phase


def at(hour, minute):
    return datetime.datetime(2026, 7, 4, hour, minute, tzinfo=TAIPEI)


class LocalQuantTests(unittest.TestCase):
    def test_data_root_must_be_stock_papi_directory_on_d_drive(self):
        self.assertEqual(
            validate_data_root(Path("D:/StockPapiData")),
            Path("D:/StockPapiData"),
        )
        for invalid in ("C:/StockPapiData", "D:/Other", "StockPapiData"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_data_root(Path(invalid))

    def test_window_phases_enforce_run_drain_checkpoint_and_closed(self):
        self.assertEqual(window_phase(at(5, 29)), "closed")
        self.assertEqual(window_phase(at(5, 30)), "run")
        self.assertEqual(window_phase(at(9, 19)), "run")
        self.assertEqual(window_phase(at(9, 20)), "drain")
        self.assertEqual(window_phase(at(9, 25)), "checkpoint")
        self.assertEqual(window_phase(at(9, 30)), "closed")


if __name__ == "__main__":
    unittest.main()
