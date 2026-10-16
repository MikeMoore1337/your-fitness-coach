#!/usr/bin/env python3
"""Offline integrity verification for SHA-pinned external UI reference snapshots."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "docs/development/external-ui-sources.json"


def main() -> int:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    if lock.get("schema_version") != 1:
        raise ValueError("Unsupported lockfile schema")
    errors: list[str] = []
    for entry in lock["files"]:
        path = (ROOT / entry["local"]).resolve()
        if path == ROOT or ROOT not in path.parents:
            errors.append(f"Unsafe path: {entry['local']}")
            continue
        if entry["ref"] != lock["sources"][entry["source"]]["commit"]:
            errors.append(f"Unpinned source: {entry['local']}")
        elif not path.is_file():
            errors.append(f"Missing source: {entry['local']}")
        else:
            data = path.read_bytes()
            digest = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
            if digest != entry["git_blob_sha"]:
                errors.append(f"SHA mismatch: {entry['local']}")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Verified {len(lock['files'])} pinned references.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
