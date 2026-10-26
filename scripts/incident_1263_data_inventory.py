#!/usr/bin/env python3
"""#1263 - production-data recovery read-only preflight.

Collects numeric record counts and backup metadata only. No personal rows, dump
bytes, credentials, host paths or raw container diagnostics leave the server.
It must never create, move, delete, dump or restore production data.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from datetime import UTC, datetime
from pathlib import Path

APP_ROOT = Path("/srv/yfc/fit-mini-app")
BACKUP_ROOT = APP_ROOT / ".artifacts" / "operations" / "backups"
EXPECTED_23 = "c6728e5f6b3f8fbb66053b0408aa51df7208dee0a1c168b52c432409a81875bc"
BACKUP_NAME = re.compile(r"^backup-2026-10-(2[3-9]|3[01])\.tar\.gz$")
TABLES = (
    "users",
    "user_programs",
    "user_workouts",
    "user_workout_exercises",
    "user_workout_sets",
    "body_measurements",
    "food_diary_entries",
    "nutrition_targets",
)


def run(argv: list[str], *, timeout: int = 15) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, check=False, timeout=timeout)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def inventory_archives() -> list[dict[str, object]]:
    if not BACKUP_ROOT.is_dir():
        return []
    items: list[dict[str, object]] = []
    # Only vetted publication folders: no arbitrary recursive filesystem traversal.
    for directory in (BACKUP_ROOT, BACKUP_ROOT / "offhost-tar"):
        if not directory.is_dir() or directory.is_symlink():
            continue
        for path in sorted(directory.glob("backup-2026-10-*.tar.gz")):
            if not BACKUP_NAME.fullmatch(path.name) or path.is_symlink():
                continue
            try:
                info = path.stat()
                if not stat.S_ISREG(info.st_mode):
                    continue
                entry: dict[str, object] = {
                    "date": path.name[len("backup-") : len("backup-") + 10],
                    "location": "published" if directory != BACKUP_ROOT else "backup_root",
                    "size_bytes": info.st_size,
                    "mtime_utc": datetime.fromtimestamp(info.st_mtime, UTC).isoformat(),
                    "readable": os.access(path, os.R_OK),
                }
                if entry["readable"]:
                    try:
                        fingerprint = digest(path)
                        entry["sha256_matches_oct23_proven_copy"] = (
                            fingerprint == EXPECTED_23 if entry["date"] == "2026-10-23" else None
                        )
                        entry["sha256_prefix"] = fingerprint[:16]
                    except OSError:
                        entry["digest_available"] = False
                manifest = path.with_name(path.name + ".manifest.json")
                if manifest.is_file() and not manifest.is_symlink():
                    try:
                        if manifest.stat().st_size <= 16 * 1024:
                            raw = json.loads(manifest.read_text(encoding="utf-8"))
                            entry["manifest_match"] = (
                                isinstance(raw, dict)
                                and raw.get("archive_sha256", "")[:16]
                                == entry.get("sha256_prefix", "!")
                                and raw.get("archive_size_bytes") == info.st_size
                                and raw.get("archive_name") == path.name
                            )
                            entry["schema_revision"] = (
                                raw.get("schema_revision", "")[:60]
                                if isinstance(raw, dict)
                                and isinstance(raw.get("schema_revision", ""), str)
                                else None
                            )
                    except OSError, ValueError:
                        entry["manifest_match"] = False
                items.append(entry)
            except OSError:
                continue
    return sorted(items, key=lambda x: (str(x["date"]), str(x["location"])), reverse=True)[:16]


def database_counts() -> dict[str, object]:
    ps = run(
        ["docker", "ps", "--filter", "label=com.docker.compose.service=db", "--format", "{{.ID}}"]
    )
    ids = ps.stdout.splitlines() if ps.returncode == 0 else []
    if len(ids) != 1 or not re.fullmatch(r"[0-9a-f]{12,64}", ids[0]):
        return {"database_available": False, "reason": "db_container_not_unique"}
    cid = ids[0]
    counts: dict[str, int | None] = {}
    for table in TABLES:
        # Identifiers are code-defined, not user or environment input.
        query = "SELECT COUNT(*) FROM public." + table if table.isidentifier() else "SELECT 0"
        cmd = [
            "docker",
            "exec",
            cid,
            "sh",
            "-c",
            'export PGOPTIONS="-c default_transaction_read_only=on -c statement_timeout=6000"; '
            'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atq -v ON_ERROR_STOP=1 -c "$1"',
            "--",
            query,
        ]
        try:
            result = run(cmd)
            value = result.stdout.strip()
            counts[table] = int(value) if result.returncode == 0 and value.isdigit() else None
        except OSError, subprocess.TimeoutExpired:
            counts[table] = None
    return {"database_available": True, "counts": counts}


def main() -> int:
    try:
        result = {
            "task": "1263-data-recovery",
            "mode": "read_only",
            "archives": inventory_archives(),
            "database": database_counts(),
            "application_mutation": False,
            "database_mutation": False,
            "data_transferred": False,
        }
        print(json.dumps(result, sort_keys=True))
        return 0
    except OSError, subprocess.SubprocessError as exc:
        print(
            json.dumps(
                {
                    "task": "1263-data-recovery",
                    "status": "BLOCKED",
                    "error_type": type(exc).__name__,
                }
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
