"""Run Graphify with Your Fitness Coach's canonical local artifact layout."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
GRAPHIFY_OUTPUT = REPOSITORY_ROOT / ".artifacts" / "shared" / "graphify"
SUPPORTED_GRAPHIFY_VERSION = "0.9.63"
INSTALL_COMMAND = f"uv tool install graphifyy=={SUPPORTED_GRAPHIFY_VERSION}"


def child_environment(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return an environment that keeps Graphify project artifacts under .artifacts/."""

    environment = dict(os.environ if base is None else base)
    environment["GRAPHIFY_OUT"] = str(GRAPHIFY_OUTPUT)
    environment["GRAPHIFY_QUERY_LOG"] = str(GRAPHIFY_OUTPUT / "queries.jsonl")
    return environment


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(
            "Usage: python scripts/graphify_yfc.py <graphify arguments>",
            file=sys.stderr,
        )
        return 2

    executable = shutil.which("graphify")
    if executable is None:
        print(
            f"Graphify is not installed. Install the supported version with: {INSTALL_COMMAND}",
            file=sys.stderr,
        )
        return 127

    GRAPHIFY_OUTPUT.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [executable, *args],
        cwd=REPOSITORY_ROOT,
        env=child_environment(),
        check=False,
    )
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
