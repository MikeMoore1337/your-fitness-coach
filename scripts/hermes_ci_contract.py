"""Compile and import every tracked Hermes operational Python module."""

from __future__ import annotations

import importlib
import json
import py_compile
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    discovery_root = root / "deploy" / "hermes-discovery"
    worker_root = root / "deploy" / "hermes-editorial-worker"
    script_paths = tuple(sorted(root.glob("scripts/*hermes*.py")))
    operational_paths = (
        tuple(sorted(discovery_root.glob("*.py")))
        + tuple(sorted(worker_root.glob("*.py")))
        + script_paths
    )
    for path in operational_paths:
        py_compile.compile(str(path), doraise=True)

    sys.path.insert(0, str(discovery_root))
    for module in (
        "discovery_runner",
        "hermes_egress",
        "hermes_health",
        "hermes_resource_guard",
        "hermes_worker_drain",
    ):
        importlib.import_module(module)
    sys.path.insert(0, str(worker_root))
    importlib.import_module("editorial_worker")
    sys.path.insert(0, str(root / "scripts"))
    for module in (
        "generate_hermes_source_definitions",
        "hermes_colocation",
        "hermes_discovery",
        "hermes_release",
        "hermes_worker",
    ):
        importlib.import_module(module)
    print(json.dumps({"status": "pass", "compiled_modules": len(operational_paths)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
