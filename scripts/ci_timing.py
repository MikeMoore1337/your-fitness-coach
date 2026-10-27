"""Run one CI setup command and emit a machine-readable duration record."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", required=True)
    parser.add_argument("--command", required=True, dest="command_name")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def _write_record(record: dict[str, object]) -> None:
    destination = os.environ.get("CI_TIMING_FILE")
    if not destination:
        return
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    command = list(args.command)
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        parser.error("a command after -- is required")

    started = time.perf_counter()
    completed = subprocess.run(command, check=False)
    duration = time.perf_counter() - started
    status = "success" if completed.returncode == 0 else "failed"
    record = {
        "group": args.group,
        "command": args.command_name,
        "duration_seconds": round(duration, 3),
        "status": status,
        "attempts": 1,
    }
    print(
        f"CI_TIMING group={args.group} command={args.command_name} "
        f"duration_seconds={duration:.3f} status={status} attempts=1",
        flush=True,
    )
    _write_record(record)
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
