"""Run pending discovery jobs through the separately configured editorial worker.

This host-side adapter is intentionally not part of the discovery container.  It
is the only component here that receives provider and YFC intake credentials.  A
transient or uncertain worker call leaves the same job file in place; terminal
validation/remediation failures are recorded and quarantined without retry.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from discovery_runner import (
    EXTERNAL_MODE,
    DiscoveryError,
    _exclusive_lock,
    _load_state,
    load_source_definitions,
    mark_candidate_status,
)

IMAGE_DIGEST_PATTERN = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
DOCKER_NETWORK_NAME_PATTERN = re.compile(r"^hermes-[a-z0-9][a-z0-9_.-]{0,56}$")
JOB_NAME_PATTERN = re.compile(r"^[0-9a-f]{64}\.json$")
DEFAULT_MAX_JOBS = 1
MAX_JOBS = 20
DEFAULT_DOCKER_NETWORK = "hermes-net"
RESERVED_DOCKER_NETWORK_NAMES = frozenset({"bridge", "default", "host", "none"})
WORKER_ENV_NAMES = (
    "HERMES_PROVIDER_BASE_URL",
    "HERMES_PROVIDER_API_KEY",
    "HERMES_PROVIDER_MODEL",
    "HERMES_PROVIDER_TIMEOUT_SECONDS",
    "HERMES_PROVIDER_MAX_ATTEMPTS",
    "HERMES_PROVIDER_RETRY_BACKOFF_SECONDS",
    "YFC_INTAKE_URL",
    "YFC_HERMES_KEY_ID",
    "YFC_HERMES_SHARED_SECRET",
    "YFC_INTAKE_TIMEOUT_SECONDS",
)
TERMINAL_WORKER_ERRORS = frozenset(
    {
        "editorial_preflight_repair_failed",
        "editorial_remediation_exhausted",
        "intake_rejected",
        "source_content_digest_mismatch",
        "source_content_too_large",
        "source_not_allowlisted",
        "source_prompt_injection_blocked",
    }
)


class DrainError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise DrainError(f"{name.casefold()}_missing")
    return value


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError as exc:
        raise DrainError(f"{name.casefold()}_invalid") from exc
    if not minimum <= value <= maximum:
        raise DrainError(f"{name.casefold()}_invalid")
    return value


def _definitions_path() -> Path:
    value = os.environ.get(
        "HERMES_DISCOVERY_DEFINITIONS", "/etc/hermes/source-definitions.json"
    ).strip()
    if not value:
        raise DrainError("hermes_discovery_definitions_missing")
    return Path(value).resolve()


def _state_dir() -> Path:
    return Path(os.environ.get("HERMES_DISCOVERY_STATE_DIR", "/var/lib/hermes")).resolve()


def _outbox_dir() -> Path:
    return Path(os.environ.get("HERMES_DISCOVERY_OUTBOX_DIR", "/var/lib/hermes/outbox")).resolve()


def _worker_image() -> str:
    value = _required_env("HERMES_WORKER_IMAGE")
    if IMAGE_DIGEST_PATTERN.fullmatch(value) is None or "latest" in value.casefold():
        raise DrainError("hermes_worker_image_not_immutable")
    return value


def _validate_docker_network(value: str) -> str:
    network = value.strip()
    if (
        network.casefold() in RESERVED_DOCKER_NETWORK_NAMES
        or DOCKER_NETWORK_NAME_PATTERN.fullmatch(network) is None
    ):
        raise DrainError("hermes_docker_network_invalid")
    return network


def _docker_network() -> str:
    return _validate_docker_network(os.environ.get("HERMES_DOCKER_NETWORK", DEFAULT_DOCKER_NETWORK))


def _worker_command(
    job: Path, *, image: str, source_allowlist: str, network: str | None = None
) -> list[str]:
    job_dir = job.parent
    docker_network = _validate_docker_network(network) if network is not None else _docker_network()
    command = [
        "docker",
        "run",
        "--rm",
        "--network",
        docker_network,
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=64m,uid=10000,gid=10000,mode=700",
        "--mount",
        f"type=bind,source={job_dir},target=/opt/data,readonly",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--pids-limit",
        "32",
        "--memory",
        "512m",
        "--cpus",
        "0.50",
        "--user",
        "10000:10000",
        "--env",
        "HERMES_HOME=/opt/data",
        "--env",
        f"HERMES_SOURCE_ALLOWLIST={source_allowlist}",
        "--env",
        "HERMES_PROVIDER_MODE=external",
    ]
    for name in WORKER_ENV_NAMES:
        _required_env(name)
        # Docker copies the already validated systemd environment value.  The
        # secret itself is therefore absent from the process argv and logs.
        command.extend(["--env", name])
    command.extend([image, "--job-file", f"/opt/data/{job.name}"])
    return command


def _result_code(completed: subprocess.CompletedProcess[str]) -> str:
    if completed.returncode == 0:
        try:
            document = json.loads(completed.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):  # fmt: skip
            return "worker_output_invalid"
        if isinstance(document, dict) and document.get("status") in {"accepted", "duplicate"}:
            return str(document["status"])
        return "worker_output_invalid"
    try:
        document = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):  # fmt: skip
        return "worker_failed"
    if isinstance(document, dict) and isinstance(document.get("error"), str):
        return str(document["error"])
    return "worker_failed"


def drain_once() -> dict[str, Any]:
    definitions_path = _definitions_path()
    state_dir = _state_dir()
    outbox_dir = _outbox_dir()
    image = _worker_image()
    network = _docker_network()
    max_jobs = _bounded_int("HERMES_WORKER_MAX_JOBS", DEFAULT_MAX_JOBS, 1, MAX_JOBS)
    timeout_seconds = _bounded_int("HERMES_WORKER_TIMEOUT_SECONDS", 120, 10, 300)
    stale_seconds = _bounded_int("HERMES_DISCOVERY_LOCK_STALE_SECONDS", 900, 30, 86_400)
    try:
        _definitions, sources = load_source_definitions(definitions_path, mode=EXTERNAL_MODE)
    except DiscoveryError as exc:
        raise DrainError(exc.code) from exc
    source_allowlist = ",".join(source.source_id for source in sources if source.enabled)
    if not source_allowlist:
        raise DrainError("source_allowlist_empty")
    state_path = state_dir / "state.json"
    try:
        _load_state(state_path)
    except DiscoveryError as exc:
        raise DrainError(exc.code) from exc
    outbox_dir.mkdir(parents=True, exist_ok=True)
    jobs = [
        path
        for path in sorted(outbox_dir.glob("*.json"))
        if JOB_NAME_PATTERN.fullmatch(path.name) is not None
    ][:max_jobs]
    completed_jobs: list[dict[str, str]] = []
    failed_jobs: list[dict[str, str]] = []
    with _exclusive_lock(state_dir / ".worker-drain.lock", stale_seconds=stale_seconds):
        for job in jobs:
            try:
                completed = subprocess.run(
                    _worker_command(
                        job,
                        image=image,
                        source_allowlist=source_allowlist,
                        network=network,
                    ),
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=timeout_seconds,
                )
            except subprocess.TimeoutExpired:
                failed_jobs.append({"job": job.stem, "code": "worker_timeout"})
                continue
            code = _result_code(completed)
            if code in {"accepted", "duplicate"}:
                try:
                    mark_candidate_status(
                        state_dir,
                        job.stem,
                        code,
                        stale_seconds=float(stale_seconds),
                    )
                    job.unlink()
                except (DiscoveryError, OSError) as exc:
                    failed_jobs.append({"job": job.stem, "code": "state_update_failed"})
                    if isinstance(exc, DiscoveryError):
                        continue
                else:
                    completed_jobs.append({"job": job.stem, "status": code})
            else:
                if code in TERMINAL_WORKER_ERRORS:
                    try:
                        mark_candidate_status(
                            state_dir,
                            job.stem,
                            "failed",
                            stale_seconds=float(stale_seconds),
                            error_code=code,
                        )
                        job.unlink()
                    except DiscoveryError, OSError:
                        failed_jobs.append({"job": job.stem, "code": "state_update_failed"})
                    else:
                        failed_jobs.append({"job": job.stem, "code": code, "status": "terminal"})
                else:
                    failed_jobs.append({"job": job.stem, "code": code})
    return {
        "status": "completed" if not failed_jobs else "partial",
        "processed": completed_jobs,
        "failed": failed_jobs,
        "provider_fallback": "disabled; manual/no-provider only",
        "secrets_logged": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.once:
            print("bounded worker drain supports only --once", file=sys.stderr)
            return 2
        print(json.dumps(drain_once(), ensure_ascii=False, sort_keys=True))
        return 0
    except DrainError as exc:
        print(json.dumps({"error": exc.code}, ensure_ascii=False, sort_keys=True))
        return 75 if exc.code == "scheduler_overlap" else 1
    except (
        AttributeError,
        KeyError,
        LookupError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        print(
            json.dumps({"error": f"drain_internal_{type(exc).__name__.casefold()}"}, sort_keys=True)
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
