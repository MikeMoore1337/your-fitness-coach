#!/usr/bin/env python3
"""One-shot, fail-closed recovery of the verified YFC single-slot baseline.

No Bash sourcing, secrets, migrations, image pulls, DB restores, or metadata rewrites.
Only existing immutable baseline images may replace the three failed consumer containers.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path("/srv/yfc/fit-mini-app")
BASELINE = "0e6aa0376f672f4b598f92ccf1a48f704e3de8e8"
FAILED = "3beb1adc968cc951395bc409c3eafcef3c3764c1"
ORIGINAL_ENV_SHA = "8f53745d9f6dbf84adeea0486bee634957a4e4dc461c85a9f22a540ec850f983"
REGISTRY = "ghcr.io/mikemoore1337/your-fitness-coach"
REVISION_LABEL = "org.opencontainers.image.revision"
RESTORE_SERVICES = ("backend", "worker", "bot")
ALL_SERVICES = (*RESTORE_SERVICES, "db", "edge")


class RecoveryBlocked(RuntimeError):
    pass


def call(argv: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=180, check=False
    )
    if result.returncode:
        raise RecoveryBlocked("subprocess failed during guarded recovery")
    return result.stdout


def json_call(argv: list[str]) -> dict[str, object]:
    try:
        result = json.loads(call(argv))
        if not isinstance(result, list) or len(result) != 1 or not isinstance(result[0], dict):
            raise RecoveryBlocked("Docker returned ambiguous inspection data")
        return result[0]
    except (ValueError, TypeError) as exc:
        raise RecoveryBlocked("invalid structured Docker metadata") from exc


def service(service_name: str) -> dict[str, object]:
    ids = [
        item
        for item in call(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                f"label=com.docker.compose.service={service_name}",
                "--format",
                "{{.ID}}",
            ]
        ).splitlines()
        if item
    ]
    if len(ids) != 1:
        raise RecoveryBlocked("not exactly one container for required service")
    result = json_call(["docker", "inspect", ids[0]])
    state = result.get("State") or {}
    labels = (result.get("Config") or {}).get("Labels") or {}
    if not isinstance(state, dict) or not isinstance(labels, dict):
        raise RecoveryBlocked("container state/labels malformed")
    return {
        "status": state.get("Status"),
        "health": (state.get("Health") or {}).get("Status"),
        "revision": labels.get(REVISION_LABEL),
        "project": labels.get("com.docker.compose.project"),
    }


def check_image(kind: str) -> bool:
    ref = f"{REGISTRY}-{kind}:{BASELINE}"
    data = json_call(["docker", "image", "inspect", ref])
    labels = (data.get("Config") or {}).get("Labels") or {}
    digests = data.get("RepoDigests") or []
    tags = data.get("RepoTags") or []
    return (
        isinstance(labels, dict)
        and labels.get(REVISION_LABEL) == BASELINE
        and isinstance(tags, list)
        and ref in tags
        and isinstance(digests, list)
        and any(
            isinstance(item, str) and re.search(r"@sha256:[0-9a-f]{64}$", item) for item in digests
        )
    )


def private_env(path: Path) -> bytes:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        raise RecoveryBlocked("configuration file permissions are not private")
    return path.read_bytes()


def preflight() -> tuple[dict[str, str], dict[str, object]]:
    marker = ROOT / ".artifacts/operations/deployments/last-successful-revision"
    release = ROOT / "releases" / BASELINE
    try:
        if marker.read_text(encoding="ascii").strip() != BASELINE:
            raise RecoveryBlocked("durable release marker changed")
        if (release / ".deployment-sha").read_text(encoding="ascii").strip() != BASELINE:
            raise RecoveryBlocked("release provenance does not match baseline")
        if (ROOT / "current").resolve(strict=True) != release:
            raise RecoveryBlocked("current release symlink changed")
        root_env = private_env(ROOT / ".env")
        release_env = private_env(release / ".env")
        if hashlib.sha256(root_env).hexdigest() != ORIGINAL_ENV_SHA:
            raise RecoveryBlocked("production env changed since trusted inspection")
        if root_env != release_env:
            raise RecoveryBlocked("release and persisted env differ")
    except (OSError, UnicodeError) as exc:
        raise RecoveryBlocked("durable baseline/config metadata unavailable") from exc

    if not check_image("backend") or not check_image("bot"):
        raise RecoveryBlocked("immutable known-good images not present")
    values = {name: service(name) for name in ALL_SERVICES}
    projects = {entry["project"] for entry in values.values()}
    if (
        len(projects) != 1
        or not isinstance(next(iter(projects)), str)
        or not re.fullmatch(r"[a-zA-Z0-9_-]+", next(iter(projects)))
    ):
        raise RecoveryBlocked("Compose project identity mismatch")
    if not all(
        values[name]["status"] == "exited" and values[name]["revision"] == FAILED
        for name in RESTORE_SERVICES
    ):
        raise RecoveryBlocked("failed revision consumers were replaced or already restarted")
    if values["db"]["status"] != "running" or values["db"]["health"] != "healthy":
        raise RecoveryBlocked("PostgreSQL is not healthy")
    if values["edge"]["status"] != "running":
        raise RecoveryBlocked("edge proxy is not running")

    project = next(iter(projects))
    env = dict(os.environ)
    env["COMPOSE_PROJECT_NAME"] = project
    env["BACKEND_IMAGE"] = f"{REGISTRY}-backend:{BASELINE}"
    env["BOT_IMAGE"] = f"{REGISTRY}-bot:{BASELINE}"
    env["YFC_CONSUMER_RESTART_POLICY"] = "no"
    call(["docker", "compose", "config", "--quiet"], cwd=release, env=env)
    report: dict[str, object] = {
        "incident": 1249,
        "mode": "known_good_baseline_recovery",
        "preflight": "PASS",
        "expected_revision": BASELINE,
        "application_mutation": False,
    }
    return env, report


def restore() -> dict[str, object]:
    env, report = preflight()
    release = ROOT / "releases" / BASELINE
    started: list[str] = []
    for name in RESTORE_SERVICES:
        call(
            [
                "docker",
                "compose",
                "up",
                "-d",
                "--no-build",
                "--no-deps",
                "--pull",
                "never",
                "--force-recreate",
                "--wait",
                "--wait-timeout",
                "120",
                name,
            ],
            cwd=release,
            env=env,
        )
        state = service(name)
        if state["status"] != "running" or state["revision"] != BASELINE:
            raise RecoveryBlocked("restored container provenance/health incorrect")
        if name in ("backend", "worker") and state["health"] != "healthy":
            raise RecoveryBlocked("restored service did not become healthy")
        started.append(name)
    report["operation"] = "restore"
    report["started_services"] = started
    report["application_mutation"] = True
    report["owner_and_public_smoke_verified"] = False
    return report


def main() -> int:
    try:
        if len(sys.argv) != 2 or sys.argv[1] not in ("preflight", "restore"):
            raise RecoveryBlocked("unsupported operation")
        if sys.argv[1] == "preflight":
            result = preflight()[1]
        else:
            result = restore()
        print(json.dumps(result, sort_keys=True))
        return 0
    except (RecoveryBlocked, subprocess.TimeoutExpired, ValueError) as exc:
        print(json.dumps({"incident": 1249, "status": "BLOCKED", "reason": type(exc).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
