"""Contract and offline Windows regression for the optional Toolkit Harness2 bridge."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "harness2_dev.ps1"
PIN = "1cfe254e8d25b15f37048c3730134686abe60335"
TOOLKIT_FIX = "397b5e9241e1266e82c81f5924c8a72b0c47eacf"


class Harness2YfcContract(unittest.TestCase):
    def test_delegates_to_existing_toolkit_instead_of_running_shell(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn(
            "& $acceptancePath -Action $Action -Benchmark $Benchmark -Distribution $Distribution",
            source,
        )
        self.assertIn("integrations/harness2/acceptance.ps1", source)
        for forbidden in (
            "wsl.exe", "bash -c", "harness2-demo", "harness2-judge",
            "Invoke-Expression", "codex exec",
        ):
            self.assertNotIn(forbidden, source)

    def test_allowlist_and_safe_defaults(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("[string]$Action = 'Status'", source)
        self.assertIn("[ValidateSet('lab', 'jb', 'wb')]", source)
        for action in ("Preflight", "SetupPreview", "Check", "RunPreview", "Report", "Artifacts"):
            self.assertIn("'" + action + "'", source)
        for forbidden in ("'Install'", "'Setup'", "'Remove'"):
            self.assertNotIn(forbidden, source)
        self.assertIn("[string]$Distribution = 'auto'", source)
        self.assertIn("specify -ToolkitRoot", source)

    def test_upstream_and_local_toolkit_integrity_gates(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn(PIN, source)
        self.assertIn(TOOLKIT_FIX, source)
        for required in (
            "HARNESS2_TOOLKIT_CHECKOUT_MISSING",
            "HARNESS2_TOOLKIT_INCOMPLETE",
            "HARNESS2_TOOLKIT_UNTRUSTED_PATH",
            "HARNESS2_TOOLKIT_ORIGIN_MISMATCH",
            "HARNESS2_TOOLKIT_NOT_REPO_ROOT",
            "HARNESS2_TOOLKIT_REVISION_TOO_OLD_OR_SHALLOW",
            "HARNESS2_TOOLKIT_UNTRACKED_INTEGRATION",
            "HARNESS2_TOOLKIT_MODIFIED",
            "HARNESS2_UPSTREAM_PIN_CHANGED",
            "merge-base --is-ancestor",
            "diff --quiet HEAD -- @relativeFiles",
        ):
            self.assertIn(required, source)

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell 5.1 and 7 needed")
    def test_windows_powershell_with_stub_toolkit(self):
        # No WSL, network, upstream installation or model execution.
        interpreters = [shutil.which(name) for name in ("powershell.exe", "pwsh.exe")]
        interpreters = [name for name in interpreters if name]
        self.assertEqual(len(interpreters), 2, "Both Windows PowerShell 5.1 and 7 required")
        with tempfile.TemporaryDirectory(prefix="YFC Harness2 spaces ") as folder:
            toolkit = Path(folder) / "Toolkit checkout with spaces"
            integration = toolkit / "integrations" / "harness2"
            integration.mkdir(parents=True)
            for file in ("preflight.sh", "install.sh"):
                (integration / file).write_text("# mock-only\n", encoding="utf-8")
            (integration / "cli.sh").write_text(
                f'readonly UPSTREAM_SHA="{PIN}"\n', encoding="utf-8"
            )
            (integration / "acceptance.ps1").write_text(
                "param([string]$Action, [string]$Benchmark, [string]$Distribution)\n"
                "if ($env:YFC_TEST_UPSTREAM_REFUSAL -eq '1') { throw 'UPSTREAM_REFUSED' }\n"
                'Write-Output "ACTION=$Action;BENCH=$Benchmark;DISTRO=$Distribution"\n',
                encoding="utf-8",
            )
            mock = r"""
function global:git.exe {
    if ($args[2] -eq 'remote') {
        Write-Output $env:YFC_TEST_ORIGIN
        $global:LASTEXITCODE = 0
    } elseif ($args[2] -eq 'rev-parse') {
        Write-Output $env:YFC_TEST_ROOT
        $global:LASTEXITCODE = 0
    } elseif ($args[2] -eq 'ls-files') {
        $global:LASTEXITCODE = [int]$env:YFC_TEST_UNTRACKED
    } elseif ($args[2] -eq 'merge-base') {
        $global:LASTEXITCODE = [int]$env:YFC_TEST_TOO_OLD
    } elseif ($args[2] -eq 'diff') {
        $global:LASTEXITCODE = [int]$env:YFC_TEST_DIRTY
    } else {
        throw 'UNEXPECTED_GIT_COMMAND'
    }
}
try {
    & $env:YFC_HARNESS2_SCRIPT -Action $env:YFC_TEST_ACTION -Benchmark lab -Distribution $env:YFC_TEST_DISTRIBUTION -ToolkitRoot $env:YFC_TEST_ROOT
    exit 0
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 10
}
"""
            base_env = {
                **os.environ,
                "YFC_HARNESS2_SCRIPT": str(SCRIPT),
                "YFC_TEST_ROOT": str(toolkit),
                "YFC_TEST_ORIGIN": "https://github.com/MikeMoore1337/ai-development-toolkit.git",
                "YFC_TEST_TOO_OLD": "0",
                "YFC_TEST_DIRTY": "0",
                "YFC_TEST_UNTRACKED": "0",
                "YFC_TEST_DISTRIBUTION": "Ubuntu-24.04",
                "YFC_TEST_UPSTREAM_REFUSAL": "0",
            }

            def run(shell: str, action: str, **changes: str) -> subprocess.CompletedProcess[str]:
                environment = {**base_env, "YFC_TEST_ACTION": action, **changes}
                return subprocess.run(
                    [shell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                     "-Command", mock],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=environment,
                    timeout=30,
                    check=False,
                )

            for shell in interpreters:
                with self.subTest(interpreter=shell, case="status"):
                    result = run(shell, "Status")
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("ACTION=Status;BENCH=lab;DISTRO=Ubuntu-24.04", result.stdout)
                with self.subTest(interpreter=shell, case="idempotent"):
                    result = run(shell, "Status")
                    self.assertEqual(result.returncode, 0, result.stderr)
                for action in ("Preflight", "SetupPreview", "Check", "RunPreview", "Report", "Artifacts"):
                    with self.subTest(interpreter=shell, action=action):
                        result = run(shell, action)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertIn("ACTION=" + action + ";", result.stdout)
                for case, changes, expected in (
                    ("origin", {"YFC_TEST_ORIGIN": "https://example.invalid/x"}, "HARNESS2_TOOLKIT_ORIGIN_MISMATCH"),
                    ("revision", {"YFC_TEST_TOO_OLD": "1"}, "HARNESS2_TOOLKIT_REVISION_TOO_OLD_OR_SHALLOW"),
                    ("untracked", {"YFC_TEST_UNTRACKED": "1"}, "HARNESS2_TOOLKIT_UNTRACKED_INTEGRATION"),
                    ("dirty", {"YFC_TEST_DIRTY": "1"}, "HARNESS2_TOOLKIT_MODIFIED"),
                    ("upstream", {"YFC_TEST_UPSTREAM_REFUSAL": "1"}, "UPSTREAM_REFUSED"),
                    ("docker", {"YFC_TEST_DISTRIBUTION": "docker-desktop"}, "docker-desktop"),
                    ("forbidden-action", {}, "Install"),
                ):
                    with self.subTest(interpreter=shell, negative=case):
                        action = "Install" if case == "forbidden-action" else "Status"
                        result = run(shell, action, **changes)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn(expected, result.stderr)
                with self.subTest(interpreter=shell, negative="missing-toolkit"):
                    result = run(shell, "Status", YFC_TEST_ROOT=str(Path(folder) / "missing"))
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("HARNESS2_TOOLKIT_CHECKOUT_MISSING", result.stderr)
                with self.subTest(interpreter=shell, negative="pin"):
                    (integration / "cli.sh").write_text(
                        'readonly UPSTREAM_SHA="0000"\n', encoding="utf-8"
                    )
                    result = run(shell, "Status")
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("HARNESS2_UPSTREAM_PIN_CHANGED", result.stderr)
                    (integration / "cli.sh").write_text(
                        f'readonly UPSTREAM_SHA="{PIN}"\n', encoding="utf-8"
                    )


if __name__ == "__main__":
    unittest.main()
