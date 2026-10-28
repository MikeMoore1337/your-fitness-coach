"""Console-free Windows DEV scheduled updater contracts (#1300)."""

import runpy
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SILENT_LAUNCHER = ROOT / "scripts/dev_update_silent.pyw"
UPDATE_SCRIPT = ROOT / "scripts/update_dev.ps1"


@pytest.mark.parametrize("exit_code", [0, 1, 2])
def test_pythonw_launcher_uses_no_console_and_preserves_exit_code(
    monkeypatch: pytest.MonkeyPatch, exit_code: int
) -> None:
    launcher = runpy.run_path(str(SILENT_LAUNCHER), run_name="contract-test")
    startup = SimpleNamespace(dwFlags=0, wShowWindow=99)
    recorded = {}

    monkeypatch.setattr(subprocess, "STARTUPINFO", lambda: startup, raising=False)
    monkeypatch.setattr(subprocess, "STARTF_USESHOWWINDOW", 1, raising=False)
    monkeypatch.setattr(subprocess, "SW_HIDE", 0, raising=False)
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)

    def fake_run(argv, **kwargs):
        recorded["argv"] = argv
        recorded["kwargs"] = kwargs
        return SimpleNamespace(returncode=exit_code)

    monkeypatch.setattr(subprocess, "run", fake_run)
    updater = ROOT / "scripts/update_dev.ps1"
    powershell = Path("C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")

    assert launcher["run_hidden"](updater, powershell) == exit_code
    assert recorded["argv"] == [
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
    ]
    args = recorded["kwargs"]
    assert args["cwd"] == updater.parent.parent
    assert args["shell"] is False
    assert args["creationflags"] == 0x08000000
    assert args["startupinfo"] is startup
    assert startup.dwFlags & 1
    assert startup.wShowWindow == 0
    assert args["stdin"] == subprocess.DEVNULL
    assert args["stdout"] == subprocess.DEVNULL
    assert args["stderr"] == subprocess.DEVNULL
    assert args["check"] is False


def test_scheduler_executable_is_pythonw_not_interactive_powershell() -> None:
    source = UPDATE_SCRIPT.read_text(encoding="utf-8-sig")
    register = source.split("        'Register' {", 1)[1].split(
        "        'InstallSilentAction' {", 1
    )[0]

    assert "New-SilentUpdaterAction" in register
    assert "New-ScheduledTaskTrigger" in register
    assert "New-TimeSpan -Minutes 5" in register
    assert "-LogonType Interactive" in register
    assert "-RunLevel Limited" in register
    assert "pythonw.exe" in source
    assert "dev_update_silent.pyw" in source
    assert "New-ScheduledTaskAction -Execute $pythonw" in source
    assert "Get-TaskHost" not in source
    # Legacy migration may mention WScript; fresh Register must never launch it.
    assert "wscript.exe" not in register.lower()


def test_existing_task_can_be_silenced_without_resetting_auto_apply() -> None:
    source = UPDATE_SCRIPT.read_text(encoding="utf-8-sig")
    upgrade = source.split("        'InstallSilentAction' {", 1)[1].split(
        "        'Unregister' {", 1
    )[0]

    assert "Set-ScheduledTask" in upgrade
    assert "-Action $action" in upgrade
    assert "TASK_ACTION_UNEXPECTED" in upgrade
    assert "New-SilentUpdaterAction" in upgrade
    assert "Remove-Item -LiteralPath $script:AutoApplyPath" not in upgrade
    assert "Register-ScheduledTask" not in upgrade
    assert "Unregister-ScheduledTask" not in upgrade
    assert "Enable-ScheduledTask" not in upgrade


def test_missing_pythonw_fails_closed_instead_of_using_visible_terminal() -> None:
    source = UPDATE_SCRIPT.read_text(encoding="utf-8-sig")
    host = source.split("function Get-DevPythonwHost", 1)[1].split(
        "function New-SilentUpdaterAction", 1
    )[0]

    assert "py -3.14" in host
    assert "PYTHONW_UNAVAILABLE" in host
    assert "Test-Path -LiteralPath $pythonw" in host
    assert "Get-Command powershell" not in host
    assert "Get-Command pwsh" not in host


def test_launcher_is_restricted_to_windows_and_no_shell_interpolation() -> None:
    source = SILENT_LAUNCHER.read_text(encoding="utf-8")
    assert 'os.name != "nt"' in source
    assert "shell=False" in source
    assert "creationflags=subprocess.CREATE_NO_WINDOW" in source
    assert "SystemRoot" in source
    assert "stdout=subprocess.DEVNULL" in source
    assert "stderr=subprocess.DEVNULL" in source


def test_exact_legacy_vbs_action_can_migrate_without_resetting_scheduler() -> None:
    source = UPDATE_SCRIPT.read_text(encoding="utf-8-sig")
    migration = source.split("        'InstallSilentAction' {", 1)[1].split(
        "        'Unregister' {", 1
    )[0]

    # Regression: previous locally-installed silent workaround used precisely:
    # C:\\WINDOWS\\System32\\wscript.exe //B //Nologo "<repo>\\.artifacts\\runtime\\dev-update\\silent-update.vbs"
    assert "$oldWscript" in migration
    assert "'System32\\wscript.exe'" in migration
    assert "'silent-update.vbs'" in migration
    assert "'//B //Nologo" in migration
    assert "$arguments.Trim() -ieq $expectedLegacyArgs" in migration
    assert "$executable -ieq $systemWscript" in migration
    assert "'scripts\\update_dev.ps1'" in migration
    assert "Get-Content -LiteralPath $legacyVbsPath -Raw" in migration
    assert "IndexOf($expectedUpdater" in migration
    assert "WScript\\.Shell" in migration
    assert "($oldPowerShell -or $newPythonw -or $oldWscript)" in migration

    # No direct execution of the legacy VBS; the migration simply replaces
    # the trusted task action, keeping principal, trigger and auto-apply state.
    assert "Set-ScheduledTask -TaskName $script:TaskName -Action $action" in migration
    for forbidden in (
        "Register-ScheduledTask",
        "Unregister-ScheduledTask",
        "Remove-Item -LiteralPath $script:AutoApplyPath",
        "Start-Process",
        "shell.Run(",
    ):
        assert forbidden not in migration


def test_legacy_vbs_migration_rejects_unrecognized_scripts() -> None:
    source = UPDATE_SCRIPT.read_text(encoding="utf-8-sig")
    migration = source.split("        'InstallSilentAction' {", 1)[1].split(
        "        'Unregister' {", 1
    )[0]

    # Must reject unknown VBS location, content or executable instead of
    # silently accepting arbitrary script-host commands.
    assert "$systemWscript = Join-Path $env:WINDIR" in migration
    assert "$legacyVbsPath = Join-Path $script:StateRoot" in migration
    assert "Test-Path -LiteralPath $legacyVbsPath -PathType Leaf" in migration
    assert "$legacyContent -notmatch '(?i)-Mode\\s+Check\\s+-Automatic'" in migration
    assert "$legacyContent -notmatch '(?i)WScript\\.Shell'" in migration
    assert migration.count("Stop-Update -Code 'TASK_ACTION_UNEXPECTED'") >= 4
