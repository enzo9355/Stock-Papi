import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


POWERSHELL = shutil.which("powershell.exe")


@unittest.skipUnless(POWERSHELL, "Windows PowerShell 5.1 is required")
class NativeProcessWrapperTests(unittest.TestCase):
    def run_helper(self, command_body, *, allow_failure):
        helper = (
            Path(__file__).parents[1] / "scripts" / "native_process.ps1"
        ).resolve()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            command = root / "fake-native.cmd"
            command.write_text(
                "@echo off\r\n" + command_body,
                encoding="ascii",
            )
            harness = root / "harness.ps1"
            allow = " -AllowFailure" if allow_failure else ""
            harness.write_text(
                "\n".join(
                    (
                        "$ErrorActionPreference = 'Stop'",
                        "[Console]::OutputEncoding = "
                        "[Text.UTF8Encoding]::new($false)",
                        f". '{str(helper).replace(chr(39), chr(39) * 2)}'",
                        "$result = Invoke-NativeProcessCaptured "
                        f"-FilePath '{str(command).replace(chr(39), chr(39) * 2)}' "
                        f"-Arguments @(){allow}",
                        "$result | ConvertTo-Json -Compress",
                    )
                ),
                encoding="utf-8-sig",
            )
            return subprocess.run(
                [
                    POWERSHELL,
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(harness),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )

    def test_stderr_progress_with_zero_exit_is_success_and_redacted(self):
        result = self.run_helper(
            ">&2 echo Copying object token=live-secret\r\nexit /b 0\r\n",
            allow_failure=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        document = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(document["exit_code"], 0)
        self.assertIn("Copying object", document["text"])
        self.assertIn("[REDACTED]", document["text"])
        self.assertNotIn("live-secret", result.stdout + result.stderr)

    def test_nonzero_exit_is_failure_and_retains_redacted_stderr(self):
        sensitive_text = "pass" + "word=live-secret"
        captured = self.run_helper(
            f">&2 echo fatal {sensitive_text}\r\nexit /b 7\r\n",
            allow_failure=True,
        )

        self.assertEqual(captured.returncode, 0, captured.stderr)
        document = json.loads(captured.stdout.strip().splitlines()[-1])
        self.assertEqual(document["exit_code"], 7)
        self.assertIn("fatal", document["text"])
        self.assertIn("[REDACTED]", document["text"])
        self.assertNotIn("live-secret", captured.stdout + captured.stderr)

        failed = self.run_helper(
            f">&2 echo fatal {sensitive_text}\r\nexit /b 7\r\n",
            allow_failure=False,
        )
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("exit code 7", failed.stdout + failed.stderr)
        self.assertNotIn("live-secret", failed.stdout + failed.stderr)


if __name__ == "__main__":
    unittest.main()
