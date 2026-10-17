from __future__ import annotations

import copy
import csv
from collections import Counter
from pathlib import Path

from scripts.import_full_hd_exercise_media import _build_matrix


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
    assert Counter(row["previous_status"] for row in rows) == Counter(
        {"approved": 167, "blocked": 39}
    )
    assert Counter(row["current_status"] for row in rows) == Counter(
        {"approved": 171, "blocked": 35}
    )
    for slug in ("chin-up", "russian-twist"):
        row = next(item for item in rows if item["canonical_slug"] == slug)
        assert row["semantic_status"] == "REVIEW"
        assert row["import_status"] == "skipped"
        assert row["current_media_source"].startswith("gymvisual/")


def test_full_hd_matrix_history_is_stable_on_reimport() -> None:
    titles = {
        "side-plank": (
            "Боковая планка",
            {
                "aliases": [],
                "primary_muscle": "Core",
                "movement_pattern": "anti_lateral_flexion",
                "equipment": "Собственный вес",
            },
        )
    }
    baseline = {
        "side-plank": {
            "canonical_slug": "side-plank",
            "current_status": "blocked",
            "current_media_source": "blocked/no media",
            "status": "NO_MATCH",
        }
    }
    old_manifest = {"exercises": {"side-plank": {"status": "blocked", "media": []}}}
    new_manifest = {
        "exercises": {
            "side-plank": {
                "status": "approved",
                "media": [{"type": "image", "path": "exercises-media/side-plank/poster-1280.jpg"}],
            }
        }
    }
    planned = {
        "side-plank": {
            "mapping": {
                "source_gender": "male",
                "source_slug": "side-bridge-side-plank",
                "semantic_status": "VERIFIED_SEMANTIC",
                "confidence": "high",
                "review_note": "exact semantic name",
            },
            "fallback": {"width": 1280, "height": 720, "byte_size": 42, "sha256": "sha"},
            "provenance": {"url": "https://example.test/source"},
        }
    }

    first = _build_matrix(titles, baseline, old_manifest, new_manifest, planned)
    second = _build_matrix(titles, baseline, new_manifest, copy.deepcopy(new_manifest), planned)

    assert first == second
    assert first[0]["previous_status"] == "blocked"
    assert first[0]["current_status"] == "approved"
    assert first[0]["previous_media_source"] == "blocked/no media"
