"""Validate the deterministic Issue #396 program library source data."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

EXPECTED_GENERIC_SLUGS = {
    "strength-pplf-4d",
    "strength-pplf-8d",
    "strength-pull-legs-push-legs-4d",
    "strength-pull-legs-push-legs-8d",
    "strength-split-5d",
    "strength-push-pull-legs-6d",
    "strength-upper-lower-4d",
    "strength-fullbody-3d",
}
EXPECTED_SOURCE_SLUGS = {
    "stronglifts-5x5",
    "gzclp",
    "531-for-beginners",
    "phul",
    "nsuns-4d",
    "metallicdpa-linear-progression-ppl",
    "bwf-recommended-routine",
    "dumbbell-ppl-gregarioushermit",
}
ALLOWED_ADAPTATION_STATUSES = {"EXACT", "ADAPTED", "MANUAL_RULE", "UNSUPPORTED"}
ALLOWED_MAPPING_STATUSES = {"EXACT", "ADAPTED", "MANUAL_RULE", "UNSUPPORTED"}
EXPECTED_MAPPING_STAGES = [
    "source_exercise",
    "canonical_slug",
    "alias",
    "variant",
    "exercise_metadata",
    "movement_equipment_validation",
]
EXPECTED_FALSE_GAPS = {
    "single-leg-rdl",
    "skull-crusher",
    "glute-ham-raise",
    "chest-dip",
    "weighted-dip",
    "rear-delt-fly",
}
EXPECTED_TRUE_GAPS = {"power-clean", "dumbbell-floor-press"}
EXPECTED_DEFERRED = {
    "Starting Strength",
    "PHAT",
    "Dumbbell Stopgap",
    "r/Fitness Basic Beginner",
    "Greyskull LP",
    "Frankoman DB Only",
    "SBS / Greg Nuckols collections",
    "Strong Curves",
    "WS4SB",
    "Arnold-style",
    "Deep Water",
}


def _unpack(seed: tuple) -> tuple[str, int, str, int, dict[str, object]]:
    if len(seed) == 4:
        slug, sets, reps, rest = seed
        return slug, sets, reps, rest, {}
    slug, sets, reps, rest, metadata = seed
    return slug, sets, reps, rest, metadata


def _plans(spec: dict[str, object]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for _day_title, exercises in spec["days"]:
        for seed in exercises:
            _slug, _sets, _reps, _rest, metadata = _unpack(seed)
            plan = metadata.get("prescription")
            if not isinstance(plan, dict):
                raise AssertionError(f"Missing structured prescription in {spec['slug']}")
            result.append(plan)
            weekly = metadata.get("weekly_plans")
            if weekly is not None:
                if not isinstance(weekly, list):
                    raise AssertionError(f"weekly_plans must be a list in {spec['slug']}")
                if not all(isinstance(item, dict) for item in weekly):
                    raise AssertionError(f"weekly_plans contain invalid data in {spec['slug']}")
                result.extend(weekly)
    return result


def _load_kinds(plan: dict[str, object]) -> set[str]:
    return {
        segment["load_target"]["kind"]
        for segment in plan["segments"]
        if isinstance(segment, dict)
        and isinstance(segment.get("load_target"), dict)
        and isinstance(segment["load_target"].get("kind"), str)
    }


def validate() -> dict[str, int]:
    from pydantic import ValidationError

    from fitminiapp_api.schemas.program import ExercisePrescriptionPlan
    from fitminiapp_api.services.program_seed_data import (
        EXERCISE_CATALOG,
        STRENGTH_TEMPLATE_SPECS,
    )

    catalog_slugs = [row[0] for row in EXERCISE_CATALOG]
    assert len(EXERCISE_CATALOG) == 207, len(EXERCISE_CATALOG)
    assert len(set(catalog_slugs)) == 207, "duplicate stored exercise slug"
    assert "kettlebell-goblet-squat" in catalog_slugs
    assert "goblet-squat" in catalog_slugs
    assert len(catalog_slugs) - 1 == 206, "canonical catalog count changed"
    catalog = {row[0]: row for row in EXERCISE_CATALOG}

    assert len(STRENGTH_TEMPLATE_SPECS) == 16, len(STRENGTH_TEMPLATE_SPECS)
    specs = {str(spec["slug"]): spec for spec in STRENGTH_TEMPLATE_SPECS}
    assert len(specs) == 16, "duplicate template slug"
    assert set(specs) == EXPECTED_GENERIC_SLUGS | EXPECTED_SOURCE_SLUGS
    assert not (EXPECTED_GENERIC_SLUGS & EXPECTED_SOURCE_SLUGS)

    for slug in EXPECTED_GENERIC_SLUGS:
        spec = specs[slug]
        assert spec.get("provenance") is None
        for _day_title, exercises in spec["days"]:
            for seed in exercises:
                exercise_slug, _sets, _reps, _rest, metadata = _unpack(seed)
                assert exercise_slug in catalog, f"missing generic exercise: {exercise_slug}"
                assert "prescription" not in metadata

    for slug in EXPECTED_SOURCE_SLUGS:
        spec = specs[slug]
        provenance = spec.get("provenance")
        assert isinstance(provenance, dict)
        assert provenance["provenance_type"] == "SOURCE_ADAPTATION"
        assert provenance["canonical_source"]
        assert provenance["creator"]
        assert provenance["adaptation_status"] == "ADAPTED"

        mapping_gate = provenance["mapping_gate"]
        assert mapping_gate["stages"] == EXPECTED_MAPPING_STAGES
        assert set(mapping_gate["known_false_gaps"]) == EXPECTED_FALSE_GAPS
        assert set(mapping_gate["genuine_gaps"]) == EXPECTED_TRUE_GAPS
        assert catalog.keys() >= EXPECTED_FALSE_GAPS
        assert not EXPECTED_TRUE_GAPS & catalog.keys()

        deferred = {item["program"] for item in provenance["deferred_library_ledger"]}
        assert deferred == EXPECTED_DEFERRED
        for item in provenance["adaptation_ledger"]:
            assert item["status"] in ALLOWED_ADAPTATION_STATUSES
            if item["status"] == "UNSUPPORTED":
                assert item.get("blocking") is False, (
                    f"material unsupported adaptation in {slug}: {item['field']}"
                )

        for source_name, mapping in provenance["exercise_mapping"].items():
            assert mapping["status"] in ALLOWED_MAPPING_STATUSES, (slug, source_name)
            canonical_slug = mapping.get("canonical_slug")
            if canonical_slug is None:
                assert source_name == "remaining_source_rows"
                continue
            assert canonical_slug in catalog, (slug, source_name, canonical_slug)
            _title, _muscle, equipment = catalog[canonical_slug][1:]
            assert _title and _muscle and equipment, (slug, canonical_slug)

        duration_weeks = spec.get("default_duration_weeks", 1)
        assert isinstance(duration_weeks, int) and 1 <= duration_weeks <= 24
        source_load_kinds: set[str] = set()
        for _day_title, exercises in spec["days"]:
            for seed in exercises:
                exercise_slug, _sets, _reps, _rest, metadata = _unpack(seed)
                assert exercise_slug in catalog, f"missing source exercise: {exercise_slug}"
                plan = metadata.get("prescription")
                try:
                    parsed = ExercisePrescriptionPlan.model_validate(plan)
                except ValidationError as exc:
                    raise AssertionError(f"invalid prescription in {slug}/{exercise_slug}") from exc
                assert parsed.metric_type == "strength"
                plan_load_kinds = _load_kinds(plan)
                source_load_kinds.update(plan_load_kinds)
                assert "percent_1rm" not in plan_load_kinds
                if duration_weeks > 1:
                    weekly = metadata.get("weekly_plans")
                    if weekly is None:
                        weekly = [plan] * duration_weeks
                    assert isinstance(weekly, list) and len(weekly) == duration_weeks, (
                        slug,
                        exercise_slug,
                    )
                    for weekly_plan in weekly:
                        ExercisePrescriptionPlan.model_validate(weekly_plan)
        if slug in {"531-for-beginners", "nsuns-4d"}:
            assert "percent_training_max" in source_load_kinds

    return {
        "stored_exercise_rows": len(EXERCISE_CATALOG),
        "canonical_exercise_rows": len(EXERCISE_CATALOG) - 1,
        "generic_templates": len(EXPECTED_GENERIC_SLUGS),
        "source_templates": len(EXPECTED_SOURCE_SLUGS),
        "total_templates": len(STRENGTH_TEMPLATE_SPECS),
    }


if __name__ == "__main__":
    summary = validate()
    print("Issue #396 program library validation: PASS")
    for key, value in summary.items():
        print(f"{key}={value}")
