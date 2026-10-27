from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess

from scripts import run_cross_browser_regression


def test_cross_browser_runner_isolates_results_ports_and_runs_all_browsers_after_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ALLURE_RESULTS_DIR", "results")
    monkeypatch.setenv("PLAYWRIGHT_OUTPUT_DIR", "playwright-output")
    monkeypatch.setenv("PW_EXTERNAL_SERVER", "true")
    monkeypatch.setenv("PW_BASE_URL", "http://external.example")
    calls: list[dict[str, object]] = []

    def fake_run(command, *, cwd, env, check):
        browser = command[-1]
        calls.append({"command": command, "cwd": cwd, "env": env, "check": check})
        return CompletedProcess(command, {"chromium": 1, "firefox": 0, "webkit": 2}[browser])

    result = run_cross_browser_regression.run_cross_browser_regression(
        root=tmp_path,
        runner=fake_run,
    )

    assert result == 1
    assert sorted(call["command"][-1] for call in calls) == ["chromium", "firefox", "webkit"]
    for call in calls:
        browser = call["command"][-1]
        assert call["cwd"] == tmp_path / "frontend"
        assert call["check"] is False
        environment = call["env"]
        assert environment["ALLURE_RESULTS_DIR"] == str(tmp_path / "results" / browser)
        assert environment["PLAYWRIGHT_OUTPUT_DIR"] == str(tmp_path / "playwright-output" / browser)
        api_port, preview_port = run_cross_browser_regression.BROWSER_PORTS[browser]
        assert environment["PW_API_PORT"] == api_port
        assert environment["PW_PREVIEW_PORT"] == preview_port
        assert "PW_EXTERNAL_SERVER" not in environment
        assert environment["PW_BASE_URL"] == f"http://127.0.0.1:{preview_port}"


def test_cross_browser_runner_does_not_enable_allure_when_not_configured(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("ALLURE_RESULTS_DIR", raising=False)
    calls: list[dict[str, object]] = []

    def fake_run(command, *, cwd, env, check):
        calls.append({"command": command, "cwd": cwd, "env": env, "check": check})
        return CompletedProcess(command, 0)

    result = run_cross_browser_regression.run_cross_browser_regression(
        root=tmp_path,
        browsers=("webkit",),
        runner=fake_run,
    )

    assert result == 0
    assert "ALLURE_RESULTS_DIR" not in calls[0]["env"]
    assert calls[0]["env"]["PLAYWRIGHT_OUTPUT_DIR"] == str(
        tmp_path / ".artifacts" / "runtime" / "tests" / "playwright-cross-browser" / "webkit"
    )
