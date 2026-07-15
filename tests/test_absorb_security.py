import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOG_BOUNDARY_FILES = (
    ROOT / "line_state.py",
    ROOT / "backtest" / "publish.py",
    ROOT / "stock_papi" / "application.py",
    ROOT / "stock_papi" / "quant" / "model.py",
    ROOT / "stock_papi" / "integrations" / "market_data" / "provider.py",
    ROOT / "stock_papi" / "integrations" / "line" / "state.py",
)


class AbsorbSecurityContractTests(unittest.TestCase):
    def test_boundary_logs_do_not_include_exception_values_or_user_ids(self):
        prohibited = (
            "exc_info=True",
            '%s", exc',
            "{e}",
            "{reply_err}",
            "{exc}",
            "user {user_id}",
        )
        for path in LOG_BOUNDARY_FILES:
            source = path.read_text(encoding="utf-8")
            for token in prohibited:
                with self.subTest(path=path.relative_to(ROOT), token=token):
                    self.assertNotIn(token, source)
            for line_number, line in enumerate(source.splitlines(), 1):
                if "logger." in line:
                    with self.subTest(path=path.relative_to(ROOT), line=line_number):
                        self.assertNotIn("user_id", line)


if __name__ == "__main__":
    unittest.main()
