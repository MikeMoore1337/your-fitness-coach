#!/usr/bin/env python3
"""Offline read-only verdict for pinned Jev Test Impact --static pilot output."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

CASES = {
    "shared-module": False,
    "workout-ui": False,
    "tsconfig": True,
    "lockfile": True,
}


def evaluate(samples: dict[str, dict]) -> dict:
    findings = []
    metrics = {}
    invalid_evidence = False
    for case, require_full in CASES.items():
        data = samples.get(case)
        if not isinstance(data, dict) or data.get("_invalid"):
            findings.append(f"{case}: MISSING_OR_INVALID_RESULT")
            invalid_evidence = True
            continue
        discovered = data.get("testsDiscovered")
        selected = data.get("selected")
        # Upstream selected is a list; upstream metrics.selected is numeric.
        selected_count = len(selected) if isinstance(selected, list) else None
        changes = data.get("changedFiles")
        requests = data.get("jevRequests")
        full = data.get("fullSuite") is True
        if not isinstance(discovered, int) or discovered <= 0:
            findings.append(f"{case}: NO_DISCOVERED_TESTS")
        if not isinstance(changes, int) or changes != 1:
            findings.append(f"{case}: INVALID_DIFF_SCOPE")
        if not isinstance(selected_count, int) or selected_count > discovered:
            findings.append(f"{case}: INVALID_SELECTION")
        if requests not in (0, None):
            findings.append(f"{case}: API_MODE_NOT_ALLOWED")
        if require_full and (not full or selected_count != discovered):
            findings.append(f"{case}: MISSED_FULL_SUITE_FALLBACK")
        if not require_full and (selected_count is None or selected_count == 0):
            findings.append(f"{case}: NO_SOURCE_TESTS_SELECTED")
        playwright = (
            sum("tests/e2e/" in x.get("path", "") for x in selected if isinstance(x, dict))
            if isinstance(selected, list)
            else 0
        )
        if playwright:
            findings.append(f"{case}: PLAYWRIGHT_SPECS_IN_VITEST_SELECTION")
        metrics[case] = {
            "discovered": discovered,
            "selected": selected_count,
            "playwright_selected": playwright,
            "changed": changes,
            "full": full,
            "selection_ms": data.get("selectionMs"),
        }
    return {
        "schema": 1,
        "verdict": "EVIDENCE_INVALID"
        if invalid_evidence
        else "NO_GO"
        if findings
        else "STATIC_DISCOVERY_PLAUSIBLE_NOT_ADOPTED",
        "findings": findings,
        "metrics": metrics,
        "runtime_test_recall": "NOT_MEASURED",
        "full_vs_selected_execution_ms": "NOT_MEASURED",
        "free_provider_calls": 0,
    }


def parse_upstream_output(raw: str) -> dict:
    """Accept only JSON or the observed, bounded PNPM informational preamble."""
    text = raw.lstrip()
    if text.startswith("{"):
        return json.loads(text)
    prefix, separator, tail = text.partition("{")
    lines = prefix.strip().splitlines()
    if (
        not separator
        or len(prefix) > 256
        or len(lines) != 2
        or (
            lines[0] != "Already up to date"
            or not (lines[1].startswith("Done in ") and " using pnpm v11.5.0" in lines[1])
        )
    ):
        raise ValueError("unexpected upstream output format")
    return json.loads("{" + tail)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    args = parser.parse_args()
    samples = {}
    for name in CASES:
        path = args.results / f"{name}.json"
        if path.is_file():
            try:
                samples[name] = parse_upstream_output(path.read_text(encoding="utf-8"))
            except ValueError, OSError, UnicodeError:
                samples[name] = {"_invalid": True}
    print(json.dumps(evaluate(samples), ensure_ascii=False, sort_keys=True))
    # An unexpected static miss is a valid NEGATIVE experiment; not a CI failure.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
