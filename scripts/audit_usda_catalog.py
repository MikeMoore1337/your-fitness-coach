"""Quarterly read-only USDA review: build candidate, compare to approved baseline.

Run in the trusted YFC backend container with USDA_FDC_API_KEY available from
the runtime environment. Never write to application database.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(*, baseline: Path, candidate: Path, report: Path) -> int:
    """Return 0 for unchanged published data, 2 for review, 1 for validation errors."""

    scripts = Path(__file__).resolve().parent
    summary: dict[str, object] = {
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "status": "error",
        "db_mutations": False,
        "upstream": "USDA FoodData Central",
    }
    status = 1
    try:
        if not baseline.is_file() or not baseline.stat().st_size:
            raise ValueError("missing approved baseline snapshot")
        if candidate.exists() or report.exists():
            raise ValueError("refusing to overwrite existing audit artifacts")
        result = subprocess.run(
            [
                sys.executable,
                str(scripts / "export_usda_reviewed_catalog.py"),
                "--output",
                str(candidate),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0 or not candidate.is_file():
            raise ValueError("candidate export failed; existing baseline remains intact")
        compare = subprocess.run(
            [
                sys.executable,
                str(scripts / "compare_usda_reviewed_catalogs.py"),
                str(baseline),
                str(candidate),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=40,
        )
        if compare.returncode not in {0, 2}:
            raise ValueError("candidate comparison failed; baseline unchanged")
        metrics = json.loads(compare.stdout)
        if not isinstance(metrics, dict):
            raise ValueError("malformed comparison")
        summary["comparison"] = metrics
        summary["baseline_sha256"] = _digest(baseline)
        summary["candidate_sha256"] = _digest(candidate)
        summary["status"] = (
            "needs_review"
            if compare.returncode == 2 or metrics.get("added_count", 0)
            else "unchanged"
        )
        status = 2 if summary["status"] == "needs_review" else 0
    except OSError, ValueError, subprocess.TimeoutExpired:
        summary["status"] = "error"
        summary["error_code"] = "source_unavailable_or_invalid"
        status = 1
    finally:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps({"status": summary["status"], "db_mutations": False}))
    return status


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    opts = parser.parse_args()
    raise SystemExit(audit(baseline=opts.baseline, candidate=opts.candidate, report=opts.report))


if __name__ == "__main__":
    main()
