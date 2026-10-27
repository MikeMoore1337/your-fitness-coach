"""Regression gates for retiring emergency production restore access (#1249)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

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
