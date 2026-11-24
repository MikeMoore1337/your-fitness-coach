from __future__ import annotations

import json
from pathlib import Path
from subprocess import CompletedProcess
from types import SimpleNamespace

import pytest
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
    ports: set[str] = set()
    for call in calls:
        browser = call["command"][-1]
        assert call["cwd"] == tmp_path / "frontend"
        assert call["check"] is False
        environment = call["env"]
        assert environment["ALLURE_RESULTS_DIR"] == str(tmp_path / "results" / browser)
        assert environment["PLAYWRIGHT_OUTPUT_DIR"] == str(tmp_path / "playwright-output" / browser)
        api_port, preview_port = environment["PW_API_PORT"], environment["PW_PREVIEW_PORT"]
        assert 0 < int(api_port) < 65536
        assert 0 < int(preview_port) < 65536
        ports.update((api_port, preview_port))
        assert "PW_EXTERNAL_SERVER" not in environment
        assert environment["PW_BASE_URL"] == f"http://127.0.0.1:{preview_port}"
    assert len(ports) == 2 * len(calls)


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


def test_cross_browser_shard_forwards_selection_and_isolates_outputs(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("ALLURE_RESULTS_DIR", "results")
    calls: list[dict[str, object]] = []

    def fake_run(command, *, cwd, env, check):
        calls.append({"command": command, "env": env})
        return CompletedProcess(command, 0)

    assert (
        run_cross_browser_regression.run_cross_browser_regression(
            root=tmp_path, browsers=("firefox",), shard="3/5", runner=fake_run
        )
        == 0
    )
    assert calls[0]["command"][-3:] == ["--project", "firefox", "--shard=3/5"]
    assert calls[0]["env"]["ALLURE_RESULTS_DIR"] == str(tmp_path / "results" / "firefox-shard-3")
    assert calls[0]["env"]["PLAYWRIGHT_OUTPUT_DIR"].endswith("firefox-shard-3")


@pytest.mark.parametrize("shard", ["0/5", "6/5", "1/0", "1/5 extra", "1/5/2"])
def test_cross_browser_rejects_invalid_shards(tmp_path: Path, shard: str) -> None:
    with pytest.raises(ValueError, match="valid shard"):
        run_cross_browser_regression.run_cross_browser_regression(
            root=tmp_path, browsers=("firefox",), shard=shard
        )


def test_cross_browser_rejects_shard_without_single_browser(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="exactly one browser"):
        run_cross_browser_regression.run_cross_browser_regression(root=tmp_path, shard="1/5")


def test_single_shard_reports_limited_child_resource_metrics(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    samples = iter(
        [
            SimpleNamespace(ru_utime=1.0, ru_stime=0.5, ru_maxrss=5),
            SimpleNamespace(ru_utime=3.0, ru_stime=1.5, ru_maxrss=100),
        ]
    )
    monkeypatch.setattr(
        run_cross_browser_regression,
        "resource",
        SimpleNamespace(RUSAGE_CHILDREN=0, getrusage=lambda _: next(samples)),
    )

    def fake_run(command, *, cwd, env, check):
        return CompletedProcess(command, 1)

    assert (
        run_cross_browser_regression.run_cross_browser_regression(
            root=tmp_path, browsers=("webkit",), shard="1/5", runner=fake_run
        )
        == 1
    )
    metrics = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert metrics["child_user_cpu_seconds"] == 2.0
    assert metrics["child_system_cpu_seconds"] == 1.0
    assert metrics["max_child_rss_platform_units"] == 100
