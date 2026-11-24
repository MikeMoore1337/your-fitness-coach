"""Run the cross-browser Playwright suite with isolated result directories."""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    import resource
except ImportError:  # Windows has no resource module.
    resource = None

BROWSERS: tuple[str, ...] = ("chromium", "firefox", "webkit")
DEFAULT_OUTPUT_DIR = Path(".artifacts/runtime/tests/playwright-cross-browser")


def _resolve_path(value: str | None, *, root: Path, default: Path) -> Path:
    candidate = Path(value) if value else default
    return candidate if candidate.is_absolute() else (root / candidate).resolve()


def _npm_command() -> str:
    command = "npm.cmd" if os.name == "nt" else "npm"
    return shutil.which(command) or command


def _available_ports(count: int) -> list[str]:
    sockets: list[socket.socket] = []
    try:
        for _ in range(count):
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sockets.append(listener)
            listener.bind(("127.0.0.1", 0))
        return [str(listener.getsockname()[1]) for listener in sockets]
    finally:
        for listener in sockets:
            listener.close()


def _run_browser(
    browser: str,
    *,
    root: Path,
    base_environment: dict[str, str],
    ports: tuple[str, str],
    runner: Callable[..., subprocess.CompletedProcess[str]],
    shard: str | None = None,
) -> int:
    environment = dict(base_environment)
    api_port, preview_port = ports
    environment.pop("PW_EXTERNAL_SERVER", None)
    environment["PW_API_PORT"] = api_port
    environment["PW_PREVIEW_PORT"] = preview_port
    environment["PW_BASE_URL"] = f"http://127.0.0.1:{preview_port}"
    output_root = _resolve_path(
        environment.get("PLAYWRIGHT_OUTPUT_DIR"), root=root, default=DEFAULT_OUTPUT_DIR
    )
    result_name = f"{browser}-shard-{shard.split('/')[0]}" if shard else browser
    environment["PLAYWRIGHT_OUTPUT_DIR"] = str(output_root / result_name)

    allure_root_value = environment.get("ALLURE_RESULTS_DIR", "").strip()
    if allure_root_value:
        allure_root = _resolve_path(allure_root_value, root=root, default=Path("."))
        environment["ALLURE_RESULTS_DIR"] = str(allure_root / result_name)
    else:
        environment.pop("ALLURE_RESULTS_DIR", None)

    command = [_npm_command(), "run", "e2e:cross-browser", "--", "--project", browser]
    if shard:
        command.append(f"--shard={shard}")
    completed = runner(
        command,
        cwd=root / "frontend",
        env=environment,
        check=False,
    )
    exit_code = int(completed.returncode)
    print(
        json.dumps({"browser": browser, "shard": shard, "exit_code": exit_code}, sort_keys=True),
        flush=True,
    )
    return exit_code


def run_cross_browser_regression(
    *,
    root: Path | None = None,
    browsers: Sequence[str] = BROWSERS,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    shard: str | None = None,
) -> int:
    """Run every browser even after a failure and return one aggregate exit code."""

    repository_root = (root or Path(__file__).resolve().parents[1]).resolve()
    process_runner = runner or subprocess.run
    base_environment = dict(os.environ)
    invalid = [browser for browser in browsers if browser not in BROWSERS]
    if invalid:
        raise ValueError(f"unsupported browser(s): {', '.join(invalid)}")
    if shard:
        match = re.fullmatch(r"([1-9][0-9]*)/([1-9][0-9]*)", shard)
        if not match or int(match.group(1)) > int(match.group(2)) or len(browsers) != 1:
            raise ValueError("a valid shard requires exactly one browser")
    if not browsers:
        return 0
    started = time.monotonic()
    usage_before = (
        resource.getrusage(resource.RUSAGE_CHILDREN) if resource and len(browsers) == 1 else None
    )
    selected_ports = iter(_available_ports(len(browsers) * 2))
    with ThreadPoolExecutor(max_workers=len(browsers)) as executor:
        futures = [
            executor.submit(
                _run_browser,
                browser,
                root=repository_root,
                base_environment=base_environment,
                ports=(next(selected_ports), next(selected_ports)),
                runner=process_runner,
                shard=shard,
            )
            for browser in browsers
        ]
        exit_codes = [future.result() for future in futures]
    if usage_before is not None and resource is not None:
        usage_after = resource.getrusage(resource.RUSAGE_CHILDREN)
        print(
            json.dumps(
                {
                    "browser": browsers[0],
                    "shard": shard,
                    "wall_seconds": round(time.monotonic() - started, 3),
                    "child_user_cpu_seconds": round(
                        usage_after.ru_utime - usage_before.ru_utime, 3
                    ),
                    "child_system_cpu_seconds": round(
                        usage_after.ru_stime - usage_before.ru_stime, 3
                    ),
                    "max_child_rss_platform_units": usage_after.ru_maxrss,
                },
                sort_keys=True,
            ),
            flush=True,
        )
    return 1 if any(exit_code != 0 for exit_code in exit_codes) else 0


if __name__ == "__main__":
    project = os.environ.get("YFC_CROSS_BROWSER_PROJECT")
    shard = os.environ.get("YFC_CROSS_BROWSER_SHARD")
    if bool(project) != bool(shard):
        raise SystemExit("browser and shard must both be configured")
    raise SystemExit(
        run_cross_browser_regression(browsers=(project,) if project else BROWSERS, shard=shard)
    )
