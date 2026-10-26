#!/usr/bin/env python3
"""Read-only assessment for safely restarting the *existing* YFC containers.

This script does not read production secrets, source .env, change files or start services.
It is intended to be streamed over owner-gated GitHub Actions SSH.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path("/srv/yfc/fit-mini-app")
BASELINE = "0e6aa0376f672f4b598f92ccf1a48f704e3de8e8"
REVISION_LABEL = "org.opencontainers.image.revision"
SERVICES = ("backend", "worker", "bot", "db", "edge", "setup")
APP_SERVICES = ("backend", "worker", "bot")
SHA = re.compile(r"^[0-9a-f]{40}$")


class ProbeError(RuntimeError):
    pass


def run_json(arguments: list[str]) -> object:
    proc = subprocess.run(arguments, capture_output=True, text=True, check=False, timeout=15)
    if proc.returncode != 0:
        raise ProbeError("Docker metadata unavailable")
    return json.loads(proc.stdout)


def container(service: str) -> dict[str, object]:
    proc = subprocess.run(
        [
            "docker",
            "ps",
            "-a",
            "--filter",
            f"label=com.docker.compose.service={service}",
            "--format",
            "{{.ID}}",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    if proc.returncode:
        return {"service": service, "valid": False, "reason": "docker_ps_unavailable"}
    ids = [item for item in proc.stdout.splitlines() if item]
    if len(ids) != 1:
        return {"service": service, "valid": False, "reason": "not_exactly_one_container", "count": len(ids)}
    details = run_json(["docker", "inspect", ids[0]])
    if not isinstance(details, list) or len(details) != 1:
        raise ProbeError("Docker inspect did not return exactly one container")
    row = details[0]
    state = row.get("State") or {}
    config = row.get("Config") or {}
    image = row.get("Image")
    labels = config.get("Labels") or {}
    image_data = run_json(["docker", "image", "inspect", image])
    if not isinstance(image_data, list) or len(image_data) != 1:
        raise ProbeError("Docker image inspection is not unique")
    img = image_data[0]
    image_labels = (img.get("Config") or {}).get("Labels") or {}
    digests = img.get("RepoDigests") or []
    status = state.get("Status")
    health = (state.get("Health") or {}).get("Status")
    rev = image_labels.get(REVISION_LABEL)
    project = labels.get("com.docker.compose.project")
    return {
        "service": service,
        "valid": True,
        "status": status,
        "health": health,
        "exit_code": state.get("ExitCode") if status == "exited" else None,
        "revision_matches_baseline": rev == BASELINE if service in APP_SERVICES else None,
        "image_id_matches": image == img.get("Id"),
        "image_has_digest": bool(digests),
        "compose_project": project if isinstance(project, str) and re.fullmatch(r"[A-Za-z0-9_-]+", project) else "INVALID",
        "image_id": image if service in ("backend", "worker") else None,
    }


def inspect() -> dict[str, object]:
    marker = ROOT / ".artifacts/operations/deployments/last-successful-revision"
    try:
        recorded = marker.read_text(encoding="ascii").strip()
        deployed = (ROOT / "releases" / BASELINE / ".deployment-sha").read_text(encoding="ascii").strip()
        current = (ROOT / "current").resolve(strict=True)
    except (OSError, UnicodeError):
        raise ProbeError("durable deployment metadata missing") from None
    baseline_valid = (
        bool(SHA.fullmatch(recorded))
        and recorded == BASELINE
        and deployed == BASELINE
        and current == ROOT / "releases" / BASELINE
    )
    records = {name: container(name) for name in SERVICES}
    app = [records[name] for name in APP_SERVICES]
    projects = {record["compose_project"] for record in records.values() if record.get("valid")}
    app_consistent = all(
        x.get("valid")
        and x.get("status") == "exited"
        and x.get("revision_matches_baseline") is True
        and x.get("image_id_matches") is True
        and x.get("image_has_digest") is True
        for x in app
    )
    backend_worker_equal = records["backend"].get("image_id") == records["worker"].get("image_id")
    supporting = all(
        records[s].get("valid")
        and records[s].get("status") == "running"
        and records[s].get("health") == "healthy"
        for s in ("db", "edge")
    )
    setup = records["setup"]
    setup_ready = (
        setup.get("valid")
        and setup.get("status") == "exited"
        and setup.get("exit_code") == 0
    )
    eligible = all(
        (baseline_valid, app_consistent, backend_worker_equal, supporting, setup_ready, len(projects) == 1, "INVALID" not in projects)
    )
    # Never print container image IDs, token values or raw Docker metadata.
    for row in records.values():
        row.pop("image_id", None)
        row.pop("compose_project", None)
    return {
        "incident": 1249,
        "mode": "existing_container_preflight",
        "baseline_sha": BASELINE,
        "durable_baseline_valid": baseline_valid,
        "app_images_consistent": bool(app_consistent),
        "backend_worker_same_image": backend_worker_equal,
        "db_edge_healthy": bool(supporting),
        "setup_completed": bool(setup_ready),
        "single_compose_project": len(projects) == 1 and "INVALID" not in projects,
        "existing_container_restart_candidate": bool(eligible),
        "services": records,
        "application_mutation": False,
    }


if __name__ == "__main__":
    try:
        print(json.dumps(inspect(), sort_keys=True))
    except (ProbeError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(json.dumps({"incident": 1249, "status": "BLOCKED", "reason": type(exc).__name__}))
        raise SystemExit(2) from None
