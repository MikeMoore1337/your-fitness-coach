from __future__ import annotations

import shutil
import subprocess
import sys

PINNED_UV_VERSION = "0.11.32"


def command(args: list[str]) -> list[str]:
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("uv is required to run project_uv.py")
    return [
        uv,
        "tool",
        "run",
        "--from",
        f"uv=={PINNED_UV_VERSION}",
        "uv",
        *args,
    ]


def main() -> int:
    if len(sys.argv) == 1:
        raise SystemExit("usage: python scripts/project_uv.py <uv arguments...>")
    return subprocess.run(command(sys.argv[1:]), check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
