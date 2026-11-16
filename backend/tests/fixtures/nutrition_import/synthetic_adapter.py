"""Synthetic adapter for isolation tests; not registered in the application."""

import csv
import io


def parse(content: bytes) -> dict:
    if b"__BUSY__" in content:
        while True:
            pass
    if b"__MEMORY__" in content:
        return {"unused": "x" * (512 * 1024 * 1024)}
    if b"__SLEEP__" in content:
        import time

        time.sleep(10)
    if b"__TOO_LARGE__" in content:
        return {"unused": "x" * (3 * 1024 * 1024)}
    rows = list(csv.reader(io.StringIO(content.decode("utf-8"))))
    if rows != [["name", "quantity"], ["Synthetic", "1"]]:
        raise ValueError("invalid synthetic input")
    return {
        "schema_version": "nutrition-import-v2",
        "source": {
            "provider": "fixture_provider",
            "source": "fixture",
            "adapter_version": "synthetic-v2",
            "source_format": "csv",
            "transport": "upload",
        },
        "completeness": "partial",
        "rows": [
            {
                "coordinates": {"section": "detail", "section_kind": "detail", "row": 2},
                "diary_date": "2024-03-02",
                "meal_type": "breakfast",
                "food": {"name": "Synthetic", "kind": "unknown"},
                "quantity": "1.000",
                "amount_unit": "g",
                "nutrition": {"basis": None, "facts": {}},
            }
        ],
        "original_totals": [],
        "original_summaries": [],
        "diagnostics": [],
    }
