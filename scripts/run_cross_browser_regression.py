"""Run the cross-browser Playwright suite with isolated result directories."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BROWSERS: tuple[str, ...] = ("chromium", "firefox", "webkit")
BROWSER_PORTS: dict[str, tuple[str, str]] = {
    "chromium": ("8001", "4174"),
    "firefox": ("8002", "4175"),
    "webkit": ("8003", "4176"),
}
DEFAULT_OUTPUT_DIR = Path(".artifacts/runtime/tests/playwright-cross-browser")


def _resolve_path(value: str | None, *, root: Path, default: Path) -> Path:
    candidate = Path(value) if value else default
    return candidate if candidate.is_absolute() else (root / candidate).resolve()


def _npm_command() -> str:
    command = "npm.cmd" if os.name == "nt" else "npm"
    return shutil.which(command) or command


def _run_browser(
    browser: str,
    *,
    root: Path,
    base_environment: dict[str, str],
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> int:
    environment = dict(base_environment)
    api_port, preview_port = BROWSER_PORTS[browser]
    environment.pop("PW_EXTERNAL_SERVER", None)
    environment["PW_API_PORT"] = api_port
    environment["PW_PREVIEW_PORT"] = preview_port
    environment["PW_BASE_URL"] = f"http://127.0.0.1:{preview_port}"
    output_root = _resolve_path(
        environment.get("PLAYWRIGHT_OUTPUT_DIR"), root=root, default=DEFAULT_OUTPUT_DIR
    )
    environment["PLAYWRIGHT_OUTPUT_DIR"] = str(output_root / browser)

    allure_root_value = environment.get("ALLURE_RESULTS_DIR", "").strip()
    if allure_root_value:
        allure_root = _resolve_path(allure_root_value, root=root, default=Path("."))
        environment["ALLURE_RESULTS_DIR"] = str(allure_root / browser)
    else:
        environment.pop("ALLURE_RESULTS_DIR", None)

    completed = runner(
        [_npm_command(), "run", "e2e:cross-browser", "--", "--project", browser],
        cwd=root / "frontend",
        env=environment,
        check=False,
    )
    exit_code = int(completed.returncode)
    print(json.dumps({"browser": browser, "exit_code": exit_code}, sort_keys=True), flush=True)
    return exit_code


def run_cross_browser_regression(
    *,
    root: Path | None = None,
    browsers: Sequence[str] = BROWSERS,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> int:
    """Run every browser even after a failure and return one aggregate exit code."""

    repository_root = (root or Path(__file__).resolve().parents[1]).resolve()
    process_runner = runner or subprocess.run
    base_environment = dict(os.environ)
    invalid = [browser for browser in browsers if browser not in BROWSERS]
    if invalid:
        raise ValueError(f"unsupported browser(s): {', '.join(invalid)}")
    if not browsers:
        return 0
    with ThreadPoolExecutor(max_workers=len(browsers)) as executor:
        futures = [
            executor.submit(
                _run_browser,
                browser,
                root=repository_root,
                base_environment=base_environment,
                runner=process_runner,
            )
            for browser in browsers
        ]
        exit_codes = [future.result() for future in futures]
    return 1 if any(exit_code != 0 for exit_code in exit_codes) else 0


if __name__ == "__main__":
    raise SystemExit(run_cross_browser_regression())
