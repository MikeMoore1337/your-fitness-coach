"""Continuously verify the public release path and the pre-switch asset compatibility contract."""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
from dataclasses import asdict, dataclass, field
from pathlib import Path

if __package__:
    from scripts.check_deployment import _first_versioned_asset, _read, check_deployment
else:
    from check_deployment import _first_versioned_asset, _read, check_deployment


# The anonymous refresh endpoint is limited to 10 requests per minute. Seven
# seconds keeps the continuous probe below that limit even with a sliding window.
AUTH_REFRESH_PROBE_INTERVAL_SECONDS = 7.0


@dataclass
class ProbeReport:
    started_at: float
    ended_at: float = 0.0
    requests: int = 0
    samples: int = 0
    failures: dict[str, int] = field(
        default_factory=lambda: {
            "transport": 0,
            "http_4xx": 0,
            "http_5xx": 0,
            "asset_mismatch": 0,
            "contract": 0,
        }
    )
    first_error: str | None = None
    compatibility_asset: str | None = None
    latency_max_ms: float = 0.0
    latency_p95_ms: float = 0.0

    @property
    def failure_count(self) -> int:
        return sum(self.failures.values())


def _atomic_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _classify(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        if 400 <= exc.code < 500:
            return "http_4xx"
        if exc.code >= 500:
            return "http_5xx"
    if isinstance(exc, (urllib.error.URLError, TimeoutError, ConnectionError, OSError)):
        return "transport"
    text = str(exc).lower()
    if "asset" in text or "/assets/" in text:
        return "asset_mismatch"
    if "returned 4" in text:
        return "http_4xx"
    if "returned 5" in text:
        return "http_5xx"
    return "contract"


def run_probe(
    base_url: str,
    *,
    duration: float,
    interval: float,
    timeout: float,
    expected_environment: str,
    stop_requested=lambda: False,
    compatibility_required=lambda: True,
    on_started=lambda: None,
    clock=time.monotonic,
    sleeper=time.sleep,
) -> ProbeReport:
    started = clock()
    report = ProbeReport(started_at=started)
    sample_latencies_ms: list[float] = []
    initial_document = _read(base_url, "/app", timeout=timeout)
    report.requests += 1
    report.compatibility_asset = _first_versioned_asset(initial_document.body)
    on_started()
    next_refresh_boundary_at = started

    while True:
        sample_started = clock()
        check_refresh_boundary = sample_started >= next_refresh_boundary_at
        if check_refresh_boundary:
            next_refresh_boundary_at = sample_started + max(
                interval, AUTH_REFRESH_PROBE_INTERVAL_SECONDS
            )
        try:
            check_deployment(
                base_url,
                timeout=timeout,
                expected_environment=expected_environment,
                check_refresh_boundary=check_refresh_boundary,
            )
            report.requests += 8 + int(check_refresh_boundary)
            if compatibility_required():
                old_asset = _read(base_url, report.compatibility_asset, timeout=timeout)
                report.requests += 1
                if old_asset.status != 200 or not old_asset.body:
                    raise RuntimeError(
                        f"compatibility asset returned {old_asset.status} or an empty body: "
                        f"{report.compatibility_asset}"
                    )
        except BaseException as exc:  # bounded evidence must survive every request failure
            category = _classify(exc)
            report.failures[category] += 1
            if report.first_error is None:
                report.first_error = f"{type(exc).__name__}: {exc}"
        report.samples += 1
        sample_latencies_ms.append((clock() - sample_started) * 1000)
        elapsed = clock() - started
        if elapsed >= duration or stop_requested():
            report.ended_at = clock()
            ordered = sorted(sample_latencies_ms)
            report.latency_max_ms = round(ordered[-1], 3)
            p95_index = min(len(ordered) - 1, max(0, int(len(ordered) * 0.95) - 1))
            report.latency_p95_ms = round(ordered[p95_index], 3)
            return report
        sleeper(min(interval, max(0.0, duration - elapsed)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url")
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--expected-environment", default="prod")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--stop-file", type=Path)
    parser.add_argument("--started-file", type=Path)
    parser.add_argument("--compatibility-stop-file", type=Path)
    args = parser.parse_args()
    if args.duration <= 0 or args.interval <= 0 or args.timeout <= 0:
        parser.error("duration, interval and timeout must be positive")

    try:
        if args.started_file is not None:
            args.started_file.parent.mkdir(parents=True, exist_ok=True)
        report = run_probe(
            args.base_url,
            duration=args.duration,
            interval=args.interval,
            timeout=args.timeout,
            expected_environment=args.expected_environment,
            stop_requested=(
                (lambda: args.stop_file.is_file())
                if args.stop_file is not None
                else (lambda: False)
            ),
            compatibility_required=(
                (lambda: not args.compatibility_stop_file.is_file())
                if args.compatibility_stop_file is not None
                else (lambda: True)
            ),
            on_started=(
                (lambda: args.started_file.write_text("started\n", encoding="utf-8"))
                if args.started_file is not None
                else (lambda: None)
            ),
        )
    except BaseException as exc:
        report = ProbeReport(started_at=time.monotonic(), ended_at=time.monotonic())
        category = _classify(exc)
        report.failures[category] = 1
        report.first_error = f"{type(exc).__name__}: {exc}"

    payload = asdict(report)
    payload["failure_count"] = report.failure_count
    _atomic_json(args.output, payload)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if report.failure_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
