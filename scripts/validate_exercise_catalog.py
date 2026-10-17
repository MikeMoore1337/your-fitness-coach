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

from PIL import Image

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
MEDIA_DIR = BACKEND_DIR / "assets" / "exercise-guides"
MANIFEST_PATH = MEDIA_DIR / "manifest.json"
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
MEDIA_STATE_BY_SLUG = metadata_module.MEDIA_STATE_BY_SLUG
REMAINING_COVERAGE_SLUGS = metadata_module.REMAINING_COVERAGE_SLUGS
structured_catalog_metadata = metadata_module.structured_catalog_metadata
canonical_equipment_identifier = domain_module.canonical_equipment_identifier
canonical_muscle_identifier = domain_module.canonical_muscle_identifier
SLUG_TO_PROFILE = guides_module.SLUG_TO_PROFILE
PROFILES = guides_module.PROFILES
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

    for slug, metadata in structured_catalog_metadata().items():
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


def _validate_structured_metadata(catalog_slugs: set[str]) -> dict[str, int]:
    canonical_slugs = {canonical_slug(slug) for slug in catalog_slugs}
    records = structured_catalog_metadata()
    _require(set(records) == canonical_slugs, "Structured metadata/canonical catalogue mismatch")
    allowed_movements = set(get_args(ExerciseMovementPattern))
    allowed_machine_tags = set(get_args(ExerciseMachineVariantTag))
    allowed_execution_tags = set(get_args(ExerciseExecutionVariantTag))

    for slug, metadata in records.items():
        _require(metadata["primary_muscle"], f"Missing primary muscle metadata: {slug}")
        _require(metadata["secondary_muscles"], f"Missing secondary muscle metadata: {slug}")
        _require(metadata["equipment"], f"Missing equipment metadata: {slug}")
        _require(metadata["movement_pattern"] in allowed_movements, f"Invalid movement: {slug}")
        _require(
            metadata["difficulty_level"] in {"beginner", "intermediate", "advanced"},
            f"Invalid difficulty: {slug}",
        )
        _require(
            metadata["metric_type"] in {"strength", "cardio"},
            f"Invalid metric type: {slug}",
        )
        _require(
            canonical_muscle_identifier(metadata["primary_muscle"]) is not None,
            f"Unknown structured primary muscle: {slug}",
        )
        _require(
            canonical_equipment_identifier(metadata["equipment"]) is not None,
            f"Unknown structured equipment: {slug}",
        )
        _require(
            set(metadata["machine_variant_tags"]) <= allowed_machine_tags,
            f"Invalid structured machine tags: {slug}",
        )
        _require(
            set(metadata["execution_variant_tags"]) <= allowed_execution_tags,
            f"Invalid structured execution tags: {slug}",
        )

    machine_applicable = sum(
        canonical_equipment_identifier(metadata["equipment"]) == "machine"
        for metadata in records.values()
    )
    aliases_populated = sum(bool(metadata["aliases"]) for metadata in records.values())
    execution_populated = sum(
        bool(metadata["execution_variant_tags"]) for metadata in records.values()
    )
    machine_populated = sum(bool(metadata["machine_variant_tags"]) for metadata in records.values())
    return {
        "metadata_records": len(records),
        "metadata_required_missing": 0,
        "metadata_aliases_populated": aliases_populated,
        "metadata_aliases_reviewed_empty": len(records) - aliases_populated,
        "metadata_execution_populated": execution_populated,
        "metadata_execution_reviewed_empty": len(records) - execution_populated,
        "metadata_machine_applicable": machine_applicable,
        "metadata_machine_populated": machine_populated,
        "metadata_machine_reviewed_empty": machine_applicable - machine_populated,
    }


def _validate_media(catalog_slugs: set[str]) -> tuple[int, int, int, int, int]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    exercises = manifest["exercises"]
    manifest_slugs = set(exercises)
    canonical_slugs = {canonical_slug(slug) for slug in catalog_slugs}
    _require(manifest.get("schema_version") == 3, "Stage 4 media manifest is not active")
    _require(manifest_slugs == canonical_slugs, "Stage 4 manifest/catalog canonical mismatch")
    counts = manifest.get("counts", {})
    _require(counts.get("canonical_exercises") == len(canonical_slugs), "Canonical count drift")
    _require(
        counts.get("remote_runtime_assets") == 0,
        "Remote runtime asset count drift",
    )
    actual_animated = 0
    actual_static = 0
    actual_blocked = 0
    referenced_paths: set[str] = set()

    def asset_path(relative: str, slug: str, field: str) -> Path:
        path = Path(relative)
        _require(
            not path.is_absolute() and ".." not in path.parts, f"Invalid media path: {slug}/{field}"
        )
        resolved = MEDIA_DIR / path
        _require(resolved.is_file(), f"Referenced media is missing: {relative}")
        referenced_paths.add(relative)
        return resolved

    def check_source(source: dict, slug: str, field: str, *, require_image: bool = False) -> None:
        path = asset_path(str(source["path"]), slug, field)
        data = path.read_bytes()
        _require(source.get("byte_size") == len(data), f"Stale media byte count: {source['path']}")
        if source.get("sha256") is not None:
            _require(
                source["sha256"] == hashlib.sha256(data).hexdigest(),
                f"Stale media hash: {source['path']}",
            )
        if require_image:
            with Image.open(path) as image:
                _require(
                    image.size == (source["width"], source["height"]),
                    f"Image dimensions drifted: {source['path']}",
                )
                _require(
                    image.format in {"JPEG", "WEBP"}, f"Unsupported image format: {source['path']}"
                )
                _require(not image.getexif(), f"Image metadata was not stripped: {source['path']}")

    for slug, item in exercises.items():
        source = item.get("source", {})
        status = item.get("status")
        if status == "blocked":
            _require(not source and not item.get("media"), f"Blocked media is not empty: {slug}")
            actual_blocked += 1
            continue
        _require(status == "approved", f"Invalid Stage 4 media status: {slug}")
        _require(
            len(item.get("media", [])) == 1, f"Approved media must have one media item: {slug}"
        )
        for media in item["media"]:
            media_type = media.get("type")
            _require(media_type in {"animation", "image"}, f"Invalid media type: {slug}")
            if media_type == "animation":
                actual_animated += 1
                _require(
                    source.get("name") == "Gym visual"
                    and source.get("url") == "https://github.com/hasaneyldrm/exercises-dataset"
                    and source.get("license") == "Owner-purchased GymVisual license",
                    f"Invalid animation provenance: {slug}",
                )
            else:
                actual_static += 1
                _require(
                    source.get("name") == "Exercises Media"
                    and source.get("url") == "https://github.com/akajdid-mostafa/exercises-media"
                    and source.get("source_revision") == "18742da40b0627c85925c5dd4441dc3eac0594d0",
                    f"Invalid static provenance: {slug}",
                )
            path = asset_path(str(media["path"]), slug, "path")
            poster_path = asset_path(str(media["poster_path"]), slug, "poster_path")
            path = MEDIA_DIR / media["path"]
            poster_path = MEDIA_DIR / media["poster_path"]
            _require(
                media.get("width", 0) > 0 and media.get("height", 0) > 0,
                f"Invalid dimensions: {slug}",
            )
            if media_type == "animation":
                _require(
                    media.get("animated") is True and media.get("frame_count", 0) > 1,
                    f"Animation metadata is invalid: {slug}",
                )
            else:
                _require(
                    media.get("animated") is False and media.get("frame_count") == 1,
                    f"Static metadata is invalid: {slug}",
                )
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            _require(media.get("asset_sha256") == digest, f"Stale media hash: {media['path']}")
            poster_digest = hashlib.sha256(poster_path.read_bytes()).hexdigest()
            _require(
                media.get("poster_sha256") == poster_digest,
                f"Stale poster hash: {media['poster_path']}",
            )
            _require(
                media.get("poster_byte_size") == poster_path.stat().st_size,
                f"Stale poster byte count: {slug}",
            )
            poster_source = media.get("poster_source")
            if poster_source is not None:
                _require(
                    poster_source.get("name") == "Exercises Media"
                    and poster_source.get("url")
                    == "https://github.com/akajdid-mostafa/exercises-media"
                    and poster_source.get("source_revision")
                    == "18742da40b0627c85925c5dd4441dc3eac0594d0"
                    and poster_source.get("rights_basis")
                    == "owner_confirmed_hq_media_usage_and_derivatives_2026-10-16"
                    and media["poster_path"].startswith("exercises-media/")
                    and media.get("poster_dimensions") == {"width": 1280, "height": 720}
                    and media.get("poster_preferred") is True,
                    f"Unauthorized or malformed HQ poster provenance: {slug}",
                )
                with Image.open(poster_path) as hq_poster:
                    _require(
                        hq_poster.format == "JPEG"
                        and hq_poster.size == (1280, 720)
                        and not hq_poster.getexif(),
                        f"HQ poster image metadata mismatch: {slug}",
                    )
            if media_type == "animation":
                _require(
                    media.get("sources")
                    == [
                        {
                            "path": media["path"],
                            "mime_type": "image/gif",
                            "width": media["width"],
                            "height": media["height"],
                            "byte_size": media["byte_size"],
                        }
                    ],
                    f"Animation source metadata drifted: {slug}",
                )
            else:
                _require(
                    len(media.get("sources", [])) == 6,
                    f"Static responsive source count drift: {slug}",
                )
            for descriptor in media.get("sources", []):
                check_source(descriptor, slug, "source", require_image=media_type == "image")
            for descriptor in media.get("poster_sources", []):
                check_source(descriptor, slug, "poster_source", require_image=True)
            video_sources = media.get("video_sources", [])
            if video_sources:
                _require(len(video_sources) == 2, f"Unexpected HD video profile count: {slug}")
                provenance = media.get("video_provenance") or {}
                _require(
                    provenance.get("source_revision") == "18742da40b0627c85925c5dd4441dc3eac0594d0",
                    f"Unpinned H.264 source: {slug}",
                )
                if slug not in {"barbell-curl", "burpee"}:
                    poster_provenance = media.get("poster_source") or {}
                    _require(
                        bool(poster_provenance)
                        and provenance.get("source_path")
                        == "public/videos/"
                        + poster_provenance["source_gender"]
                        + "/"
                        + poster_provenance["source_slug"]
                        + ".mp4",
                        f"Video does not match verified poster: {slug}",
                    )
                for video, (width, height) in zip(
                    video_sources, [(854, 480), (1280, 720)], strict=True
                ):
                    _require(
                        video.get("mime_type") == "video/mp4"
                        and video.get("width") == width
                        and video.get("height") == height,
                        f"Invalid H.264 source profile: {slug}",
                    )
                    relative_video = Path(video.get("path", ""))
                    _require(
                        relative_video.as_posix()
                        == f"exercises-media/videos/{slug}-{height}p-h264.mp4",
                        f"Unexpected video path: {slug}",
                    )
                    video_file = MEDIA_DIR / relative_video
                    _require(video_file.is_file(), f"Missing video file: {slug}")
                    referenced_paths.add(str(relative_video))
                    data = video_file.read_bytes()
                    _require(
                        len(data) == video.get("byte_size")
                        and hashlib.sha256(data).hexdigest() == video.get("sha256"),
                        f"Invalid video file checksum/size: {slug}",
                    )
    approved_videos = [
        media
        for item in exercises.values()
        for media in item.get("media", [])
        if media.get("video_sources")
    ]
    _require(
        len(approved_videos) == manifest.get("hq_video_count"),
        "Verified H.264 exercise count drift",
    )
    _require(
        sum(video["byte_size"] for media in approved_videos for video in media["video_sources"])
        == manifest.get("hq_video_total_bytes"),
        "Verified H.264 total size drift",
    )
    # Some approved canonical variants intentionally point to the same source
    # record. The manifest keeps the source asset identity explicit instead of
    # inventing a derivative to make hashes unique.
    _require(counts.get("approved_animated") == actual_animated, "Approved animation count drift")
    _require(counts.get("approved_static") == actual_static, "Approved static count drift")
    _require(counts.get("static_only") == actual_static, "Static-only count drift")
    _require(counts.get("blocked") == actual_blocked, "Blocked media total drift")
    _require(manifest.get("asset_count") == len(referenced_paths), "Manifest asset count drift")
    _require(
        manifest.get("total_bytes")
        == sum((MEDIA_DIR / relative).stat().st_size for relative in referenced_paths),
        "Manifest total byte count drift",
    )
    _require(
        manifest.get("derivative_count")
        == sum(
            1
            for item in exercises.values()
            for media in item.get("media", [])
            if media.get("poster_source")
        ),
        "HD derivative count drift",
    )
    return (
        manifest["asset_count"],
        manifest["derivative_count"],
        manifest["counts"]["approved_animated"],
        manifest["counts"]["blocked"],
        manifest["counts"]["static_only"],
    )


def _validate_guide_content(catalog_slugs: set[str]) -> dict[str, int]:
    canonical_slugs = {canonical_slug(slug) for slug in catalog_slugs}
    _require(set(SLUG_TO_PROFILE) >= canonical_slugs, "Guide profile coverage is incomplete")
    _require(
        set(MEDIA_STATE_BY_SLUG) <= canonical_slugs,
        "Media state references a non-canonical exercise",
    )
    for slug in canonical_slugs:
        profile_name = SLUG_TO_PROFILE[slug]
        content = ITEM_GUIDE_CONTENT.get(slug, PROFILES[profile_name])
        _require(len(content["steps"]) == 3, f"Expected three technique steps: {slug}")
        _require(len(content["mistakes"]) >= 3, f"Expected three common mistakes: {slug}")
        _require(bool(content["breathing"]), f"Missing breathing guidance: {slug}")
    for slug, state in MEDIA_STATE_BY_SLUG.items():
        if state["state"] == "repdb_phased":
            _require(state["phases"] == ("start", "peak"), f"Invalid phased media state: {slug}")
        elif state["state"] == "repdb_single_static":
            _require(state["phases"] == ("main",), f"Invalid static media state: {slug}")
        else:
            _require(not state["phases"], f"Source-gap media state has phases: {slug}")
    return {
        "guide_profile_records": len(canonical_slugs),
        "guide_item_content_records": sum(slug in ITEM_GUIDE_CONTENT for slug in canonical_slugs),
        "new_guide_content_records": sum(
            slug in ITEM_GUIDE_CONTENT for slug in MEDIA_STATE_BY_SLUG
        ),
    }


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
    metadata_report = _validate_structured_metadata(catalog_slugs)
    guide_report = _validate_guide_content(catalog_slugs)
    asset_count, derivative_count, approved_media, blocked_media, static_only_media = (
        _validate_media(catalog_slugs)
    )
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
        "media_approved_animated": approved_media,
        "media_blocked": blocked_media,
        "media_static_only": static_only_media,
        "media_remote_runtime_assets": 0,
        **metadata_report,
        **guide_report,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    report = validate_catalog()
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
