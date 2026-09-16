from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache

from fitminiapp_api.services.exercise_guide_media import get_guide_media
from fitminiapp_api.services.exercise_guides import (
    DEFAULT_SAFETY_NOTES,
    PROFILES,
    SLUG_TO_PROFILE,
    SOURCE_LICENSE,
    SOURCE_LICENSE_URL,
    SOURCE_NAME,
    SOURCE_URL,
)
from fitminiapp_api.services.program_seed_data import EXERCISE_CATALOG, exercise_difficulty_level

# A deliberately small editorial allowlist. It prevents the public surface from
# turning the whole exercise catalogue into thin pages and excludes every
# user-created or personalized exercise by construction.
PUBLIC_EXERCISE_SLUGS = ("bench-press", "lat-pulldown", "squat")
_REQUIRED_TEXT_FIELDS = (
    "slug",
    "title",
    "primary_muscle",
    "equipment",
    "breathing",
    "source_name",
    "source_url",
    "source_license",
)
_REQUIRED_LIST_FIELDS = (
    "secondary_muscles",
    "technique_steps",
    "common_mistakes",
    "safety_notes",
)
_REQUIRED_MEDIA_TEXT_FIELDS = ("url", "alt", "phase", "source_name", "source_url", "source_license")


def public_exercise_quality_errors(exercise: Mapping[str, object]) -> tuple[str, ...]:
    """Return publishability errors for one explicitly allowlisted exercise record."""

    errors: list[str] = []
    for field in _REQUIRED_TEXT_FIELDS:
        value = exercise.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(field)
    for field in _REQUIRED_LIST_FIELDS:
        value = exercise.get(field)
        if not isinstance(value, list) or not value:
            errors.append(field)
            continue
        if any(not isinstance(item, str) or not item.strip() for item in value):
            errors.append(field)
    media = exercise.get("media")
    if not isinstance(media, list) or any(
        not isinstance(item, Mapping)
        or any(
            not isinstance(item.get(field), str) or not item[field].strip()
            for field in _REQUIRED_MEDIA_TEXT_FIELDS
        )
        for item in media
    ):
        errors.append("media")
    return tuple(errors)


def validate_public_exercise_quality(exercise: Mapping[str, object]) -> None:
    errors = public_exercise_quality_errors(exercise)
    if errors:
        slug = exercise.get("slug", "<unknown>")
        raise RuntimeError(
            f"Published exercise {slug!r} fails the public quality contract: {', '.join(errors)}"
        )


@lru_cache(maxsize=1)
def public_exercises() -> tuple[dict[str, object], ...]:
    catalog = {
        slug: (title, primary_muscle, equipment)
        for slug, title, primary_muscle, equipment in EXERCISE_CATALOG
    }
    records: list[dict[str, object]] = []

    for slug in PUBLIC_EXERCISE_SLUGS:
        catalog_item = catalog.get(slug)
        profile_name = SLUG_TO_PROFILE.get(slug)
        if catalog_item is None or profile_name is None:
            raise RuntimeError(f"Published exercise {slug!r} is missing canonical domain data")
        title, primary_muscle, equipment = catalog_item
        profile = PROFILES[profile_name]
        record: dict[str, object] = {
            "slug": slug,
            "title": title,
            "primary_muscle": primary_muscle,
            "secondary_muscles": list(profile["secondary"]),
            "equipment": equipment,
            "difficulty_level": exercise_difficulty_level(slug),
            "technique_steps": list(profile["steps"]),
            "breathing": profile["breathing"],
            "common_mistakes": list(profile["mistakes"]),
            "safety_notes": list(DEFAULT_SAFETY_NOTES),
            "media": get_guide_media(
                slug,
                exercise_title=title,
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                source_license=SOURCE_LICENSE,
                source_license_url=SOURCE_LICENSE_URL,
            ),
            "source_name": SOURCE_NAME,
            "source_url": SOURCE_URL,
            "source_license": SOURCE_LICENSE,
            "source_license_url": SOURCE_LICENSE_URL,
        }
        validate_public_exercise_quality(record)
        records.append(record)
    return tuple(records)


def public_exercise(slug: str) -> dict[str, object] | None:
    return next((item for item in public_exercises() if item["slug"] == slug), None)
