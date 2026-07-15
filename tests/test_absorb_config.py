import unittest
from pathlib import Path

from absorb.config import AbsorbConfig, AbsorbConfigError, migrated_env


class AbsorbConfigTests(unittest.TestCase):
    def test_absorb_name_wins_and_legacy_falls_back(self):
        self.assertEqual(migrated_env("ABSORB_ENV", "STOCK_PAPI_ENV", environ={"ABSORB_ENV": "prod"}), "prod")
        self.assertEqual(migrated_env("ABSORB_ENV", "STOCK_PAPI_ENV", environ={"STOCK_PAPI_ENV": "legacy"}), "legacy")

    def test_conflicting_new_and_legacy_values_fail_closed_without_values_in_error(self):
        with self.assertRaises(AbsorbConfigError) as caught:
            migrated_env(
                "ABSORB_DATA_ROOT", "STOCK_PAPI_DATA_ROOT",
                environ={"ABSORB_DATA_ROOT": "secret-new", "STOCK_PAPI_DATA_ROOT": "secret-old"},
            )
        self.assertNotIn("secret-new", str(caught.exception))
        self.assertNotIn("secret-old", str(caught.exception))

    def test_typed_config_defaults_to_absorb_data_root(self):
        config = AbsorbConfig.from_env({})
        self.assertEqual(config.data_root, Path(r"D:\AbsorbData"))
        self.assertEqual(config.report_root, Path(r"D:\AbsorbData\reports"))


if __name__ == "__main__":
    unittest.main()
