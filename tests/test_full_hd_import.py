from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path


def test_full_hd_matrix_records_final_import_statuses() -> None:
    matrix_path = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "exercises"
        / "catalog-v2"
        / "986_FULL_HD_COVERAGE.csv"
    )
    with matrix_path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))

    assert len(rows) == 206
    assert Counter(row["import_status"] for row in rows) == Counter(
        {"imported_replaced": 71, "imported_added": 4, "skipped": 131}
    )
    assert Counter(row["semantic_status"] for row in rows) == Counter(
        {"VERIFIED_SEMANTIC": 75, "REVIEW": 37, "NO_MATCH": 94}
    )
