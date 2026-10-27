from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST_PYTHON = (3, 12)
HOST_FILES = (
    Path("deploy/hermes-discovery/discovery_runner.py"),
    Path("deploy/hermes-discovery/hermes_egress.py"),
    Path("deploy/hermes-discovery/hermes_health.py"),
    Path("deploy/hermes-discovery/hermes_resource_guard.py"),
    Path("deploy/hermes-discovery/hermes_worker_drain.py"),
    Path("scripts/hermes_colocation.py"),
    Path("scripts/generate_hermes_source_definitions.py"),
)


def validate_file(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    try:
        ast.parse(source, filename=str(path), feature_version=HOST_PYTHON)
    except SyntaxError as exc:
        line = exc.lineno or 0
        raise SystemExit(
            f"{path.relative_to(ROOT)} is not compatible with Python "
            f"{HOST_PYTHON[0]}.{HOST_PYTHON[1]} at line {line}: {exc.msg}"
        ) from exc


def main() -> int:
    missing = [path for path in HOST_FILES if not (ROOT / path).is_file()]
    if missing:
        rendered = ", ".join(str(path) for path in missing)
        raise SystemExit(f"Hermes host Python contract references missing files: {rendered}")
    for relative in HOST_FILES:
        validate_file(ROOT / relative)
    print(
        f"Hermes host Python compatibility passed: {len(HOST_FILES)} files, "
        f"Python {HOST_PYTHON[0]}.{HOST_PYTHON[1]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
