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
    for case, require_full in CASES.items():
        data = samples.get(case)
        if not isinstance(data, dict):
            findings.append(f"{case}: MISSING_RESULT")
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
        metrics[case] = {"discovered": discovered, "selected": selected_count,
                         "changed": changes, "full": full,
                         "selection_ms": data.get("selectionMs")}
    return {
        "schema": 1,
        "verdict": "NO_GO" if findings else "STATIC_DISCOVERY_PLAUSIBLE_NOT_ADOPTED",
        "findings": findings,
        "metrics": metrics,
        "runtime_test_recall": "NOT_MEASURED",
        "full_vs_selected_execution_ms": "NOT_MEASURED",
        "free_provider_calls": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    args = parser.parse_args()
    samples = {}
    for name in CASES:
        path = args.results / f"{name}.json"
        if path.is_file():
            try:
                samples[name] = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError, UnicodeError):
                samples[name] = {}
    print(json.dumps(evaluate(samples), ensure_ascii=False, sort_keys=True))
    # An unexpected static miss is a valid NEGATIVE experiment; not a CI failure.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
