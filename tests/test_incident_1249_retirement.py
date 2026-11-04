"""Regression gates for retiring emergency production restore access (#1249)."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
RETIRED_PATHS = (
    ".github/workflows/incident-1249-env-fix-once.yml",
    ".github/workflows/incident-1249-production-recovery.yml",
    ".github/workflows/incident-1249-restore-baseline.yml",
    "scripts/incident_1249_recovery.py",
    "scripts/incident_1249_restore_baseline.py",
)
PRODUCTION_ENTRY_POINTS = (
    ".github/workflows/deploy.yml",
    "scripts/zero_downtime_deploy.py",
    "scripts/deploy_production.sh",
)


@pytest.mark.parametrize("path", RETIRED_PATHS)
def test_owner_only_emergency_entry_points_removed(path: str) -> None:
    assert not (ROOT / path).exists(), f"Retired #1249 entry point must not ship: {path}"


@pytest.mark.parametrize("path", PRODUCTION_ENTRY_POINTS)
def test_production_does_not_shell_source_dotenv(path: str) -> None:
    source = (ROOT / path).read_text(encoding="utf-8")
    # Docker Compose env syntax need not be valid Bash; do not execute it in a shell.
    for line in source.splitlines():
        if line.lstrip().startswith("#"):
            continue
        assert not re.search(
            r"(?:^|[;\s])(?:source|\.\s+)\s*(?:[\"']?[^\s;]*\/)?\.env(?:[\"']|\s|$)",
            line,
        ), f"Do not shell-source the Compose .env in {path}"


@pytest.mark.skipif(os.name != "posix", reason="requires a POSIX shell and symlink")
def test_rollback_uses_matching_compose_config_as_data(tmp_path: Path) -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["rollback"]["steps"]
    command = next(
        step["run"] for step in steps if step["name"] == "Roll back and run production smoke"
    )
    app_root = tmp_path / "app"
    release = app_root / "releases" / ("a" * 40)
    release.mkdir(parents=True)
    (app_root / "current").symlink_to(release, target_is_directory=True)
    state_root = app_root / ".artifacts/operations/deployments"
    state_root.mkdir(parents=True)
    (state_root / "last-successful-revision").write_text("a" * 40 + "\n", encoding="utf-8")
    injected = tmp_path / "executed"
    environment = f"BACKEND_IMAGE=backend\nBOT_IMAGE=bot\nUNTRUSTED=$(touch '{injected}')\n"
    (app_root / ".env").write_text(environment, encoding="utf-8")
    (release / ".env").write_text(environment, encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ssh = bin_dir / "ssh"
    ssh.write_text('#!/bin/sh\nfor last do :; done\nexec /bin/bash -c "$last"\n', encoding="utf-8")
    ssh.chmod(0o755)
    python = bin_dir / "python3"
    python.write_text(
        '#!/bin/sh\nprintf "%s\\n%s\\n%s\\n%s\\n" "$COMPOSE_PROJECT_NAME" "$DEPLOY_STATE_ROOT" "${BACKEND_IMAGE-unset}" "${BOT_IMAGE-unset}" > "$CALLS_FILE"\n',
        encoding="utf-8",
    )
    python.chmod(0o755)
    calls = tmp_path / "calls"
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "PROD_PATH": str(app_root),
        "PROD_PORT": "22",
        "PROD_USER": "synthetic",
        "PROD_HOST": "synthetic",
        "ACTIVE_REVISION": "a" * 40,
        "PROD_URL": "https://app.example.test",
        "PROD_PUBLIC_URL": "https://example.test",
        "CALLS_FILE": str(calls),
        "BACKEND_IMAGE": "inherited-backend",
        "BOT_IMAGE": "inherited-bot",
    }

    result = subprocess.run(["/bin/bash", "-c", command], env=env, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    assert not injected.exists()
    assert calls.read_text(encoding="utf-8").splitlines() == [
        "fit-mini-app",
        str(state_root),
        "unset",
        "unset",
    ]

    calls.unlink()
    (app_root / ".env").write_text(environment + "DIFFERENT=1\n", encoding="utf-8")
    result = subprocess.run(["/bin/bash", "-c", command], env=env, capture_output=True, text=True)

    assert result.returncode != 0
    assert "environment files differ" in result.stderr
    assert not calls.exists()
    assert not injected.exists()
