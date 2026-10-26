#!/usr/bin/env python3
"""Read-only #1249 proof of known-good OCI images and live Alembic revision."""

from __future__ import annotations

import json
import re
import subprocess

BASELINE = "0e6aa0376f672f4b598f92ccf1a48f704e3de8e8"
REPO = "ghcr.io/mikemoore1337/your-fitness-coach"
REVISION_LABEL = "org.opencontainers.image.revision"
REVISION_RE = re.compile(r"^[0-9a-f]{1,64}$")


class ProbeError(RuntimeError):
    pass


def capture(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False, timeout=20)


def inspect_image(kind: str) -> dict[str, object]:
    ref = f"{REPO}-{kind}:{BASELINE}"
    result = capture(["docker", "image", "inspect", ref])
    if result.returncode:
        return {"available": False, "label_matches": False, "has_repo_digest": False}
    try:
        rows = json.loads(result.stdout)
        if not isinstance(rows, list) or len(rows) != 1:
            raise ProbeError("unexpected image inspection count")
        image = rows[0]
        labels = (image.get("Config") or {}).get("Labels") or {}
        repo_digests = image.get("RepoDigests") or []
        return {
            "available": True,
            "label_matches": labels.get(REVISION_LABEL) == BASELINE,
            "has_repo_digest": bool(
                isinstance(repo_digests, list)
                and any(
                    isinstance(value, str)
                    and re.search(r"@sha256:[0-9a-f]{64}$", value)
                    for value in repo_digests
                )
            ),
        }
    except (ValueError, AttributeError, TypeError):
        raise ProbeError("malformed image inspection result") from None


def inspect_database() -> dict[str, object]:
    ps = capture(
        [
            "docker",
            "ps",
            "--filter",
            "label=com.docker.compose.service=db",
            "--format",
            "{{.ID}}",
        ]
    )
    if ps.returncode:
        return {"accessible": False}
    ids = [item for item in ps.stdout.splitlines() if item]
    if len(ids) != 1:
        return {"accessible": False, "db_running_count": len(ids)}
    query = 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atqc "SELECT version_num FROM alembic_version ORDER BY version_num"'
    process = capture(["docker", "exec", ids[0], "sh", "-c", query])
    if process.returncode:
        return {"accessible": False, "db_running_count": 1}
    revisions = [line.strip() for line in process.stdout.splitlines() if line.strip()]
    return {
        "accessible": bool(revisions),
        "db_running_count": 1,
        "migration_revisions": revisions if all(REVISION_RE.fullmatch(r) for r in revisions) else [],
    }


def main() -> int:
    try:
        images = {kind: inspect_image(kind) for kind in ("backend", "bot")}
        database = inspect_database()
        ready = all(
            image["available"] and image["label_matches"] and image["has_repo_digest"]
            for image in images.values()
        )
        print(
            json.dumps(
                {
                    "incident": 1249,
                    "mode": "immutable_baseline_and_database_readonly",
                    "expected_baseline": BASELINE,
                    "images": images,
                    "baseline_images_locally_verified": ready,
                    "database": database,
                    "application_mutation": False,
                },
                sort_keys=True,
            )
        )
        return 0
    except (ProbeError, OSError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"incident": 1249, "status": "BLOCKED", "reason": type(exc).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
