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
GRAPHIFY_GRAPH = GRAPHIFY_OUTPUT / "graph.json"
SUPPORTED_GRAPHIFY_VERSION = "0.9.63"
INSTALL_SPEC = f"graphifyy=={SUPPORTED_GRAPHIFY_VERSION}"
INSTALL_COMMAND = f"uv tool install {INSTALL_SPEC}"


class GraphifyBootstrapError(RuntimeError):
    """Graphify cannot be made ready in the current development environment."""


def child_environment(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return an environment that keeps Graphify project artifacts under .artifacts/."""

    environment = dict(os.environ if base is None else base)
    environment["GRAPHIFY_OUT"] = str(GRAPHIFY_OUTPUT)
    environment["GRAPHIFY_QUERY_LOG"] = str(GRAPHIFY_OUTPUT / "queries.jsonl")
    return environment


def _run(
    command: Sequence[str],
    *,
    environment: Mapping[str, str] | None = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=REPOSITORY_ROOT,
        env=dict(os.environ) | dict(environment or {}),
        check=False,
        capture_output=capture_output,
        text=True,
        encoding="utf-8",
    )


def _uv_tool_bin(uv_executable: str) -> Path | None:
    completed = _run([uv_executable, "tool", "dir", "--bin"], capture_output=True)
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return Path(value) if value else None


def find_graphify(uv_executable: str | None = None) -> str | None:
    """Find Graphify on PATH or in uv's tool executable directory."""

    direct = shutil.which("graphify")
    if direct:
        return direct

    uv = uv_executable or shutil.which("uv")
    if uv is None:
        return None
    tool_bin = _uv_tool_bin(uv)
    if tool_bin is None:
        return None
    for name in ("graphify.exe", "graphify"):
        candidate = tool_bin / name
        if candidate.is_file():
            return str(candidate)
    return None


def graphify_version(executable: str) -> str | None:
    completed = _run([executable, "--version"], capture_output=True)
    if completed.returncode != 0:
        return None
    output = completed.stdout.strip()
    prefix = "graphify "
    if not output.startswith(prefix):
        return None
    version = output[len(prefix) :].strip()
    return version or None


def ensure_graphify() -> str:
    """Return the pinned Graphify executable, installing it with uv when necessary."""

    uv = shutil.which("uv")
    executable = find_graphify(uv)
    installed_version = graphify_version(executable) if executable else None
    if executable and installed_version == SUPPORTED_GRAPHIFY_VERSION:
        return executable

    if uv is None:
        if executable:
            detail = installed_version or "unknown"
            raise GraphifyBootstrapError(
                f"Graphify {detail} is installed, but YFC requires {SUPPORTED_GRAPHIFY_VERSION} "
                "and uv is unavailable to repair it."
            )
        raise GraphifyBootstrapError(
            "Graphify is not installed and uv is unavailable. "
            f"Install uv, then run: {INSTALL_COMMAND}"
        )

    command = [uv, "tool", "install"]
    if executable is not None:
        command.append("--force")
    command.append(INSTALL_SPEC)
    completed = _run(command)
    if completed.returncode != 0:
        raise GraphifyBootstrapError(
            f"Could not install pinned Graphify {SUPPORTED_GRAPHIFY_VERSION} with uv "
            f"(exit {completed.returncode})."
        )

    executable = find_graphify(uv)
    if executable is None:
        raise GraphifyBootstrapError(
            "uv installed Graphify but its executable could not be resolved "
            "via `uv tool dir --bin`."
        )
    installed_version = graphify_version(executable)
    if installed_version != SUPPORTED_GRAPHIFY_VERSION:
        raise GraphifyBootstrapError(
            "Graphify version verification failed after installation: "
            f"expected {SUPPORTED_GRAPHIFY_VERSION}, found {installed_version or 'unknown'}."
        )
    return executable


def bootstrap() -> int:
    """Ensure pinned Graphify exists and the canonical YFC code graph is current."""

    try:
        executable = ensure_graphify()
    except GraphifyBootstrapError as error:
        print(f"Graphify bootstrap unavailable: {error}", file=sys.stderr)
        return 127

    GRAPHIFY_OUTPUT.mkdir(parents=True, exist_ok=True)
    if GRAPHIFY_GRAPH.is_file():
        command = [executable, "update", ".", "--no-cluster"]
        action = "updated"
    else:
        command = [executable, "extract", ".", "--code-only", "--no-cluster"]
        action = "built"

    completed = _run(command, environment=child_environment())
    if completed.returncode != 0:
        return int(completed.returncode)
    if not GRAPHIFY_GRAPH.is_file():
        print(
            f"Graphify bootstrap finished without creating {GRAPHIFY_GRAPH}.",
            file=sys.stderr,
        )
        return 1
    print(
        f"Graphify ready: {action} {GRAPHIFY_GRAPH} "
        f"with graphify {SUPPORTED_GRAPHIFY_VERSION}."
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(
            "Usage: python scripts/graphify_yfc.py bootstrap | <graphify arguments>",
            file=sys.stderr,
        )
        return 2

    if args[0] == "bootstrap":
        if len(args) != 1:
            print("Usage: python scripts/graphify_yfc.py bootstrap", file=sys.stderr)
            return 2
        return bootstrap()

    executable = find_graphify(shutil.which("uv"))
    if executable is None:
        print(
            "Graphify is not installed. Run: python scripts/graphify_yfc.py bootstrap",
            file=sys.stderr,
        )
        return 127
    installed_version = graphify_version(executable)
    if installed_version != SUPPORTED_GRAPHIFY_VERSION:
        print(
            "Graphify version does not match the YFC pin "
            f"({installed_version or 'unknown'} != {SUPPORTED_GRAPHIFY_VERSION}). "
            "Run: python scripts/graphify_yfc.py bootstrap",
            file=sys.stderr,
        )
        return 127

    GRAPHIFY_OUTPUT.mkdir(parents=True, exist_ok=True)
    completed = _run(
        [executable, *args],
        environment=child_environment(),
    )
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
