import subprocess
import sys
import unittest


class AbsorbPackageTests(unittest.TestCase):
    def test_canonical_package_is_lightweight(self):
        command = "import sys; import absorb; assert 'pandas' not in sys.modules; assert 'google.generativeai' not in sys.modules"
        result = subprocess.run([sys.executable, "-c", command], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_canonical_conversation_import_does_not_load_legacy_application(self):
        command = "import sys; import absorb.conversation; assert 'stock_papi.application' not in sys.modules"
        result = subprocess.run([sys.executable, "-c", command], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
