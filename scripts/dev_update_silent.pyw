"""Console-free entry point for the existing Windows DEV scheduled task.

Task Scheduler launches this file with pythonw.exe (GUI subsystem).  The updater
still runs in PowerShell with its original CI, lock, RBAC, and backup gates.
Nothing here accesses production or modifies the DEV database directly.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def run_hidden(updater: Path, powershell: Path) -> int:
    """Run the updater without ever allocating a console; keep its exit code."""
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    completed = subprocess.run(
        [
            str(powershell),
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(updater),
            "-Mode",
            "Check",
            "-Automatic",
        ],
        cwd=updater.parent.parent,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        startupinfo=startup,
        creationflags=subprocess.CREATE_NO_WINDOW,
        check=False,
    )
    return completed.returncode if completed.returncode >= 0 else 1


def main() -> int:
    if os.name != "nt":
        return 1
    updater = Path(__file__).resolve().with_name("update_dev.ps1")
    system_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR")
    if not updater.is_file() or not system_root:
        return 1
    powershell = (
        Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    )
    if not powershell.is_file():
        return 1
    try:
        return run_hidden(updater, powershell)
    except (OSError, subprocess.SubprocessError):
        # pythonw has no stderr; Task Scheduler exposes a nonzero LastTaskResult.
        # update_dev.ps1 writes structured status when PowerShell itself starts.
        return 1


if __name__ == "__main__":
    sys.exit(main())
