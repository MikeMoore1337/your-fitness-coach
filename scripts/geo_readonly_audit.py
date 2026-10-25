"""Optional, operator-invoked, read-only GEO audit of allowlisted public YFC pages.

Does not install tools, persist results, mutate production, or call AI provider APIs.
The external GEO Optimizer CLI is only invoked with explicit --execute.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

CANONICAL_ORIGIN = "https://your-fitness-coach.ru"
PUBLIC_ROUTES = (
    "/",
    "/training",
    "/nutrition",
    "/calculators/1rm",
    "/programs/full-body-3-days",
    "/for-trainers",
)
MAX_TIMEOUT_SECONDS = 120
DEFAULT_TIMEOUT_SECONDS = 30
MAX_OUTPUT_CHARS = 4000
PASS_THROUGH_ENV = frozenset(
    {"PATH", "SYSTEMROOT", "WINDIR", "PATHEXT", "TMP", "TEMP", "TMPDIR", "LANG", "LC_ALL"}
)


def plan_audits(routes: Sequence[str]) -> list[list[str]]:
    """Build exact commands only for the published canonical allowlist."""
    if not routes:
        raise ValueError("at least one public route is required")
    if any(route not in PUBLIC_ROUTES for route in routes):
        raise ValueError("route is not an allowlisted public canonical page")
    return [
        ["geo", "audit", "--url", f"{CANONICAL_ORIGIN}{route}"]
        for route in dict.fromkeys(routes)
    ]


def restricted_environment(source: Mapping[str, str]) -> dict[str, str]:
    """Do not inherit bearer tokens, cloud credentials or application secrets."""
    environment = {key: value for key, value in source.items() if key.upper() in PASS_THROUGH_ENV}
    environment["NO_COLOR"] = "1"
    environment["PYTHONNOUSERSITE"] = "1"
    return environment


def audit(
    routes: Sequence[str],
    *,
    execute: bool,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    which: Callable[[str], str | None] = shutil.which,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    environment: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Return bounded factual results, never infer AI citations from a GEO score."""
    if not math.isfinite(timeout) or timeout <= 0 or timeout > MAX_TIMEOUT_SECONDS:
        raise ValueError("timeout must be finite and between 0 and 120 seconds")

    planned = plan_audits(routes)
    if not execute:
        return {
            "status": "PREVIEW_ONLY",
            "commands": planned,
            "external_execution": "NOT_EXECUTED",
            "real_ai_citations": "NOT_MEASURED",
        }

    binary = which("geo")
    if not binary or not Path(binary).is_absolute():
        raise RuntimeError("geo executable is unavailable as an absolute PATH-resolved binary")

    safe_env = restricted_environment(os.environ if environment is None else environment)
    results = []
    for command in planned:
        argv = [binary, *command[1:]]
        try:
            proc = run(
                argv,
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                env=safe_env,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("geo audit timed out; no result verified") from exc
        except OSError as exc:
            raise RuntimeError("geo audit could not execute; no result verified") from exc

        if proc.returncode != 0:
            raise RuntimeError(f"geo audit failed with exit code {proc.returncode}; no result verified")
        results.append({
            "url": command[3],
            "status": "CLI_EXIT_ZERO",
            "stdout_excerpt": (proc.stdout or "")[:MAX_OUTPUT_CHARS],
            "stdout_truncated": len(proc.stdout or "") > MAX_OUTPUT_CHARS,
            "score_is_tool_heuristic": True,
        })

    return {
        "status": "OBSERVED_CLI_RESULTS",
        "external_execution": "EXECUTED",
        "real_ai_citations": "NOT_MEASURED",
        "results": results,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--route",
        action="append",
        choices=PUBLIC_ROUTES,
        help="Allowlisted canonical route; may be repeated (default: /)",
    )
    parser.add_argument("--execute", action="store_true", help="Actually run read-only geo audit")
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Timeout per route (strictly positive, at most 120 seconds)",
    )
    args = parser.parse_args(argv)

    try:
        report = audit(args.route or ["/"], execute=args.execute, timeout=args.timeout)
    except (ValueError, RuntimeError) as exc:
        print(f"GEO_READONLY_NOT_VERIFIED: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
