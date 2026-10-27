"""Run a credential-free production-like A-to-B Caddy switch and failure drill."""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

if __package__:
    from scripts.check_deployment import check_deployment
else:
    from check_deployment import check_deployment


class DrillError(RuntimeError):
    """The production-like rollout contract was not observed."""


def _run(args: list[str], *, check: bool = True, capture: bool = False):
    return subprocess.run(args, check=check, text=True, capture_output=capture)


def _compose(compose_file: Path, project: str, *args: str, check: bool = True, capture=False):
    return _run(
        ["docker", "compose", "-p", project, "-f", str(compose_file), *args],
        check=check,
        capture=capture,
    )


def _wait_until_ready(base_url: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last_error: BaseException | None = None
    while time.monotonic() < deadline:
        try:
            check_deployment(base_url, timeout=1, expected_environment="prod")
            return
        except Exception as exc:
            last_error = exc
            time.sleep(0.2)
    raise DrillError(f"drill route was not ready: {last_error}")


def _read(opener, url: str) -> bytes:
    with opener.open(url, timeout=3) as response:
        return response.read()


def run_drill(*, port: int, artifact_root: Path) -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    compose_file = root / "tests" / "fixtures" / "zero-downtime" / "docker-compose.yml"
    project = f"yfc-zdt-drill-{os.getpid()}"
    base_url = f"http://127.0.0.1:{port}"
    artifact_root.mkdir(parents=True, exist_ok=True)
    probe_output = artifact_root / "continuous-probe.json"
    probe_stop = artifact_root / "continuous-probe.stop"
    probe_started = artifact_root / "continuous-probe.started"
    compatibility_stop = artifact_root / "asset-compatibility.stop"
    invalid_config = artifact_root / "Caddyfile.invalid"
    for stale_path in (probe_output, probe_stop, probe_started, compatibility_stop):
        stale_path.unlink(missing_ok=True)
    invalid_config.write_text(":8080 { reverse_proxy }\n", encoding="utf-8")
    previous_port = os.environ.get("DRILL_PORT")
    os.environ["DRILL_PORT"] = str(port)
    probe: subprocess.Popen[str] | None = None

    try:
        _run(
            [
                "docker",
                "compose",
                "-p",
                project,
                "-f",
                str(compose_file),
                "up",
                "-d",
                "release-a",
                "edge",
            ],
            check=True,
        )
        _wait_until_ready(base_url, 30)

        cookie_jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
        if _read(opener, f"{base_url}/session") != b"stable":
            raise DrillError("session bootstrap failed")

        probe = subprocess.Popen(
            [
                sys.executable,
                "scripts/continuous_deployment_probe.py",
                base_url,
                "--duration",
                "30",
                "--interval",
                "0.1",
                "--timeout",
                "1",
                "--expected-environment",
                "prod",
                "--output",
                str(probe_output),
                "--stop-file",
                str(probe_stop),
                "--started-file",
                str(probe_started),
                "--compatibility-stop-file",
                str(compatibility_stop),
            ],
            text=True,
        )
        deadline = time.monotonic() + 10
        while not probe_started.is_file() and time.monotonic() < deadline:
            if probe.poll() is not None:
                raise DrillError("continuous probe stopped before candidate start")
            time.sleep(0.1)
        if not probe_started.is_file():
            raise DrillError("continuous probe did not confirm active release A")

        _compose(compose_file, project, "up", "-d", "release-b")
        _compose(
            compose_file,
            project,
            "exec",
            "-T",
            "release-b",
            "python",
            "-c",
            "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=2)",
        )

        _compose(compose_file, project, "cp", str(invalid_config), "edge:/tmp/Caddyfile.invalid")
        invalid = _compose(
            compose_file,
            project,
            "exec",
            "-T",
            "edge",
            "caddy",
            "validate",
            "--config",
            "/tmp/Caddyfile.invalid",
            "--adapter",
            "caddyfile",
            check=False,
        )
        if invalid.returncode == 0:
            raise DrillError("invalid gateway config unexpectedly passed validation")
        if b'data-revision="a"' not in _read(opener, f"{base_url}/app"):
            raise DrillError("failed validation changed the active route")

        gateway_env = [
            "-e",
            "YFC_ACTIVE_UPSTREAM=release-b:8000",
            "-e",
            "YFC_ASSET_FALLBACK_UPSTREAM=release-a:8000",
        ]
        _compose(
            compose_file,
            project,
            "exec",
            "-T",
            *gateway_env,
            "edge",
            "caddy",
            "validate",
            "--config",
            "/etc/caddy/Caddyfile",
            "--adapter",
            "caddyfile",
        )
        idle_deadline = time.monotonic() + 10
        while time.monotonic() < idle_deadline:
            upstreams = json.loads(
                _compose(
                    compose_file,
                    project,
                    "exec",
                    "-T",
                    "edge",
                    "wget",
                    "-qO-",
                    "http://127.0.0.1:2019/reverse_proxy/upstreams",
                    capture=True,
                ).stdout
            )
            if all(item.get("num_requests") == 0 for item in upstreams):
                break
            time.sleep(0.05)
        else:
            raise DrillError("gateway had no bounded request-free switch point")
        _compose(
            compose_file,
            project,
            "exec",
            "-T",
            *gateway_env,
            "edge",
            "caddy",
            "reload",
            "--config",
            "/etc/caddy/Caddyfile",
            "--adapter",
            "caddyfile",
        )

        switched_document = _read(opener, f"{base_url}/app")
        if b'data-revision="b"' not in switched_document:
            current_config = _compose(
                compose_file,
                project,
                "exec",
                "-T",
                "edge",
                "wget",
                "-qO-",
                "http://127.0.0.1:2019/config/",
                capture=True,
            ).stdout
            raise DrillError(
                f"traffic did not switch to release B: document={switched_document!r}; "
                f"config={current_config}"
            )
        if _read(opener, f"{base_url}/assets/app-a.js") == b"":
            raise DrillError("old hashed asset fallback returned an empty body")
        if _read(opener, f"{base_url}/session") != b"stable":
            raise DrillError("active cookie session did not survive the switch")

        request = urllib.request.Request(
            f"{base_url}/write",
            method="POST",
            data=b"{}",
            headers={"Content-Type": "application/json", "Idempotency-Key": "drill-write-1"},
        )
        with opener.open(request, timeout=3) as response:
            write_result = json.loads(response.read())
        if write_result != {"revision": "b", "operation_id": "drill-write-1", "count": 1}:
            raise DrillError(f"safe write was duplicated or reached the wrong slot: {write_result}")

        compatibility_stop.write_text("compatibility window complete\n", encoding="utf-8")
        cleanup_env = [
            "-e",
            "YFC_ACTIVE_UPSTREAM=release-b:8000",
            "-e",
            "YFC_ASSET_FALLBACK_UPSTREAM=release-b:8000",
        ]
        _compose(
            compose_file,
            project,
            "exec",
            "-T",
            *cleanup_env,
            "edge",
            "caddy",
            "validate",
            "--config",
            "/etc/caddy/Caddyfile",
            "--adapter",
            "caddyfile",
        )
        idle_deadline = time.monotonic() + 10
        while time.monotonic() < idle_deadline:
            upstreams = json.loads(
                _compose(
                    compose_file,
                    project,
                    "exec",
                    "-T",
                    "edge",
                    "wget",
                    "-qO-",
                    "http://127.0.0.1:2019/reverse_proxy/upstreams",
                    capture=True,
                ).stdout
            )
            if all(item.get("num_requests") == 0 for item in upstreams):
                break
            time.sleep(0.05)
        else:
            raise DrillError("gateway had no request-free cleanup point")
        _compose(
            compose_file,
            project,
            "exec",
            "-T",
            *cleanup_env,
            "edge",
            "caddy",
            "reload",
            "--config",
            "/etc/caddy/Caddyfile",
            "--adapter",
            "caddyfile",
        )
        if b'data-revision="b"' not in _read(opener, f"{base_url}/app"):
            raise DrillError("cleanup reload changed the active release")
        _compose(compose_file, project, "stop", "release-a")

        probe_stop.write_text("stop\n", encoding="utf-8")
        if probe.wait(timeout=15) != 0:
            raise DrillError("continuous probe observed a rollout failure")
        report = json.loads(probe_output.read_text(encoding="utf-8"))
        if report.get("failure_count") != 0 or report.get("samples", 0) < 2:
            raise DrillError(f"continuous probe evidence is not green: {report}")
        result = {
            "verdict": "passed",
            "active_revision": "b",
            "old_asset": "available",
            "session": "preserved",
            "write_count": 1,
            "invalid_gateway_config": "kept_release_a",
            "probe": report,
        }
        (artifact_root / "summary.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return result
    finally:
        if probe is not None and probe.poll() is None:
            probe.terminate()
            probe.wait(timeout=5)
        _compose(
            compose_file,
            project,
            "down",
            "--volumes",
            "--remove-orphans",
            check=False,
        )
        if previous_port is None:
            os.environ.pop("DRILL_PORT", None)
        else:
            os.environ["DRILL_PORT"] = previous_port


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path(".artifacts/operations/deployments/zero-downtime-drill"),
    )
    args = parser.parse_args()
    try:
        result = run_drill(port=args.port, artifact_root=args.artifact_root)
    except (OSError, ValueError, subprocess.SubprocessError, DrillError) as exc:
        print(f"Zero-downtime drill failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
