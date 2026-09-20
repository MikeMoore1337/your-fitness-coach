"""Fast deterministic integrity checks for the checked-in exercise catalogue."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import get_args

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
MEDIA_DIR = BACKEND_DIR / "assets" / "exercise-guides"
MANIFEST_PATH = MEDIA_DIR / "manifest.json"
PILOT_MANIFEST_PATH = MEDIA_DIR / "pilot-manifest.json"
COVERAGE_PATH = ROOT_DIR / "docs" / "exercises" / "catalog-v2" / "COVERAGE_MATRIX.csv"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

schema = importlib.import_module("fitminiapp_api.schemas.program")
metadata_module = importlib.import_module("fitminiapp_api.services.exercise_catalog_metadata")
domain_module = importlib.import_module("fitminiapp_api.services.exercise_domain")
guides_module = importlib.import_module("fitminiapp_api.services.exercise_guides")
seed_module = importlib.import_module("fitminiapp_api.services.program_seed_data")

ExerciseExecutionVariantTag = schema.ExerciseExecutionVariantTag
ExerciseMachineVariantTag = schema.ExerciseMachineVariantTag
ExerciseMovementPattern = schema.ExerciseMovementPattern
CANONICAL_EXERCISE_REDIRECTS = metadata_module.CANONICAL_EXERCISE_REDIRECTS
CATALOG_METADATA = metadata_module.CATALOG_METADATA
ITEM_GUIDE_CONTENT = metadata_module.ITEM_GUIDE_CONTENT
MEDIA_ALT_BY_PHASE = metadata_module.MEDIA_ALT_BY_PHASE
REMAINING_COVERAGE_SLUGS = metadata_module.REMAINING_COVERAGE_SLUGS
canonical_equipment_identifier = domain_module.canonical_equipment_identifier
canonical_muscle_identifier = domain_module.canonical_muscle_identifier
SLUG_TO_PROFILE = guides_module.SLUG_TO_PROFILE
YFC_GENERATED_120D_SLUGS = guides_module.YFC_GENERATED_120D_SLUGS
EXERCISE_CATALOG = seed_module.EXERCISE_CATALOG

_SEPARATORS = re.compile(r"[^\w]+", flags=re.UNICODE)


def normalize_search_text(value: str) -> str:
    """Mirror the frontend search normalisation contract."""

    normalized = unicodedata.normalize("NFKC", value).casefold().replace("ё", "е")
    return " ".join(_SEPARATORS.sub(" ", normalized).split())


def canonical_slug(slug: str) -> str:
    return CANONICAL_EXERCISE_REDIRECTS.get(slug, slug)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _validate_aliases(catalog_slugs: set[str]) -> None:
    allowed_movements = set(get_args(ExerciseMovementPattern))
    allowed_machine_tags = set(get_args(ExerciseMachineVariantTag))
    allowed_execution_tags = set(get_args(ExerciseExecutionVariantTag))
    search_terms: dict[str, set[str]] = defaultdict(set)

    for slug, title, *_ in EXERCISE_CATALOG:
        search_terms[normalize_search_text(title)].add(canonical_slug(slug))

    for slug, metadata in CATALOG_METADATA.items():
        _require(slug in catalog_slugs, f"Metadata references unknown exercise: {slug}")
        aliases = metadata["aliases"]
        normalized = [normalize_search_text(alias) for alias in aliases]
        _require(all(normalized), f"Empty alias after normalization: {slug}")
        _require(len(normalized) == len(set(normalized)), f"Duplicate aliases: {slug}")
        _require(
            metadata["movement_pattern"] in allowed_movements,
            f"Invalid movement pattern: {slug}",
        )
        _require(
            set(metadata["machine_variant_tags"]) <= allowed_machine_tags,
            f"Invalid machine variant tag: {slug}",
        )
        _require(
            set(metadata["execution_variant_tags"]) <= allowed_execution_tags,
            f"Invalid execution variant tag: {slug}",
        )
        for alias in normalized:
            search_terms[alias].add(canonical_slug(slug))

    collisions = {term: sorted(slugs) for term, slugs in search_terms.items() if len(slugs) > 1}
    _require(not collisions, f"Cross-canonical search term collisions: {collisions}")


def _validate_media(catalog_slugs: set[str]) -> tuple[int, int]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    exercises = manifest["exercises"]
    _require(set(exercises) == catalog_slugs, "Manifest/catalog exercise mismatch")
    cross_exercise_hashes: dict[str, set[str]] = defaultdict(set)

    for slug, item in exercises.items():
        source = item.get("source", {})
        _require(source.get("name") and source.get("license"), f"Invalid provenance: {slug}")
        _require(item.get("media"), f"Missing guide media: {slug}")
        for media in item["media"]:
            path = MEDIA_DIR / media["path"]
            _require(path.is_file(), f"Referenced media is missing: {media['path']}")
            _require(
                media.get("width", 0) > 0 and media.get("height", 0) > 0,
                f"Invalid dimensions: {slug}",
            )
            _require(
                media.get("alt") == MEDIA_ALT_BY_PHASE.get(slug, {}).get(media["phase_id"]),
                f"Missing or stale media alt: {slug}/{media['phase_id']}",
            )
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            _require(media.get("asset_sha256") == digest, f"Stale media hash: {media['path']}")
            cross_exercise_hashes[digest].add(canonical_slug(slug))

    duplicates = {
        digest: sorted(slugs) for digest, slugs in cross_exercise_hashes.items() if len(slugs) > 1
    }
    _require(not duplicates, f"Cross-exercise duplicate media: {duplicates}")
    return manifest["asset_count"], manifest["derivative_count"]


def _validate_pilot_media(catalog_slugs: set[str]) -> None:
    if not PILOT_MANIFEST_PATH.is_file():
        return
    manifest = json.loads(PILOT_MANIFEST_PATH.read_text(encoding="utf-8"))
    exercises = manifest.get("exercises", {})
    _require(set(exercises) <= catalog_slugs, "Pilot references unknown exercise")
    for slug, item in exercises.items():
        source = item.get("source", {})
        _require(
            source.get("name") and source.get("url") and source.get("license"),
            f"Invalid pilot provenance: {slug}",
        )
        _require(item.get("media"), f"Missing pilot media: {slug}")
        for media in item["media"]:
            _require(media.get("type") == "image", f"Pilot media must be static: {slug}")
            for field in ("path", "poster_path"):
                relative = Path(media[field])
                _require(
                    not relative.is_absolute() and ".." not in relative.parts,
                    f"Invalid pilot path: {slug}/{field}",
                )
                _require(
                    (MEDIA_DIR / relative).is_file(),
                    f"Referenced pilot media is missing: {media[field]}",
                )
            asset_path = MEDIA_DIR / media["path"]
            _require(
                media.get("width", 0) > 0 and media.get("height", 0) > 0,
                f"Invalid pilot dimensions: {slug}",
            )
            _require(
                media.get("asset_sha256") == hashlib.sha256(asset_path.read_bytes()).hexdigest(),
                f"Stale pilot media hash: {media['path']}",
            )
            poster_hash = media.get("poster_sha256")
            if poster_hash:
                poster_path = MEDIA_DIR / media["poster_path"]
                _require(
                    poster_hash == hashlib.sha256(poster_path.read_bytes()).hexdigest(),
                    f"Stale pilot poster hash: {media['poster_path']}",
                )


def _validate_final_coverage() -> int:
    with COVERAGE_PATH.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    decisions = [
        row for row in rows if row["record_type"] in {"gap", "decision"} and "120" in row["batch"]
    ]
    allowed_statuses = {"covered", "intentionally_merged_as_variant"}
    for row in decisions:
        _require(
            row["status"] in allowed_statuses,
            f"Coverage decision is not final: {row['slug_or_gap_id']}",
        )
        if row["priority"] == "must":
            _require(
                row["status"] in allowed_statuses,
                f"Must coverage was deferred: {row['slug_or_gap_id']}",
            )
    return len(decisions)


def validate_catalog() -> dict[str, int]:
    slugs = [slug for slug, *_ in EXERCISE_CATALOG]
    titles = [title for _, title, *_ in EXERCISE_CATALOG]
    catalog_slugs = set(slugs)
    _require(len(slugs) == len(catalog_slugs), "Duplicate catalogue slug")
    _require(
        all(
            slug and title and muscle and equipment
            for slug, title, muscle, equipment in EXERCISE_CATALOG
        ),
        "Missing required catalogue field",
    )
    _require(
        all(canonical_muscle_identifier(muscle) for _, _, muscle, _ in EXERCISE_CATALOG),
        "Exercise uses unknown muscle taxonomy value",
    )
    _require(
        all(canonical_equipment_identifier(equipment) for _, _, _, equipment in EXERCISE_CATALOG),
        "Exercise uses unknown equipment taxonomy value",
    )
    _require(set(CANONICAL_EXERCISE_REDIRECTS) <= catalog_slugs, "Redirect source is missing")
    _require(
        set(CANONICAL_EXERCISE_REDIRECTS.values()) <= catalog_slugs, "Redirect target is missing"
    )
    _require(
        not (set(CANONICAL_EXERCISE_REDIRECTS.values()) & set(CANONICAL_EXERCISE_REDIRECTS)),
        "Redirect chains are not allowed",
    )
    _require(catalog_slugs <= set(SLUG_TO_PROFILE), "Exercise guide profile is missing")

    required_metadata = set(REMAINING_COVERAGE_SLUGS) | {"cable-fly", "goblet-squat"}
    _require(required_metadata <= set(CATALOG_METADATA), "Task 120D metadata is incomplete")
    _require(
        set(REMAINING_COVERAGE_SLUGS) <= set(ITEM_GUIDE_CONTENT),
        "Task 120D guide content is incomplete",
    )
    _require(
        set(YFC_GENERATED_120D_SLUGS)
        == {
            "bodyweight-glute-bridge",
            "dead-hang",
            "pendlay-row",
            "weighted-dip",
            "single-leg-calf-raise",
            "hollow-hold",
            "belt-squat",
            "wall-sit",
        },
        "Task 120D generated-media contract drifted",
    )

    for slug in REMAINING_COVERAGE_SLUGS:
        content = ITEM_GUIDE_CONTENT[slug]
        _require(len(content["steps"]) == 3, f"Expected three technique steps: {slug}")
        _require(len(content["mistakes"]) >= 3, f"Expected three common mistakes: {slug}")
        _require(bool(content["breathing"]), f"Missing breathing guidance: {slug}")

    _validate_aliases(catalog_slugs)
    asset_count, derivative_count = _validate_media(catalog_slugs)
    _validate_pilot_media(catalog_slugs)
    coverage_decisions = _validate_final_coverage()
    cardio_count = sum(
        canonical_muscle_identifier(muscle) == "cardio" for _, _, muscle, _ in EXERCISE_CATALOG
    )
    return {
        "catalog_records": len(slugs),
        "canonical_records": len({canonical_slug(slug) for slug in slugs}),
        "titles": len(titles),
        "cardio_records": cardio_count,
        "assets": asset_count,
        "derivatives": derivative_count,
        "coverage_decisions": coverage_decisions,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    report = validate_catalog()
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
