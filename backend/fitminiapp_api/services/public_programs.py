from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache

from fitminiapp_api.services.program_seed_data import (
    EXERCISE_CATALOG,
    STRENGTH_TEMPLATE_SPECS,
    exercise_difficulty_level,
)

PUBLIC_PROGRAM_SLUG = "full-body-3-days"
_SOURCE_PROGRAM_SLUG = "strength-fullbody-3d"
_REQUIRED_PROGRAM_TEXT_FIELDS = ("slug", "title", "goal", "level", "split_type")
_REQUIRED_EXERCISE_TEXT_FIELDS = (
    "slug",
    "title",
    "primary_muscle",
    "equipment",
    "difficulty_level",
    "prescribed_reps",
)


def public_program_quality_errors(program: Mapping[str, object]) -> tuple[str, ...]:
    """Return publishability errors for the one explicitly public program."""

    errors: list[str] = []
    for field in _REQUIRED_PROGRAM_TEXT_FIELDS:
        value = program.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(field)

    if program.get("slug") != PUBLIC_PROGRAM_SLUG:
        errors.append("slug")
    if program.get("goal") != "recomposition":
        errors.append("goal")
    if program.get("level") != "beginner":
        errors.append("level")
    if program.get("split_type") != "full_body":
        errors.append("split_type")

    raw_days = program.get("days")
    if not isinstance(raw_days, list) or len(raw_days) != 3:
        errors.append("days")
        return tuple(dict.fromkeys(errors))

    for day_index, raw_day in enumerate(raw_days, start=1):
        if not isinstance(raw_day, Mapping):
            errors.append(f"days[{day_index}]")
            continue
        day = raw_day
        if day.get("day_number") != day_index:
            errors.append(f"days[{day_index}].day_number")
        title = day.get("title")
        if not isinstance(title, str) or not title.strip():
            errors.append(f"days[{day_index}].title")
        raw_exercises = day.get("exercises")
        if not isinstance(raw_exercises, list) or not raw_exercises:
            errors.append(f"days[{day_index}].exercises")
            continue
        for exercise_index, raw_exercise in enumerate(raw_exercises, start=1):
            prefix = f"days[{day_index}].exercises[{exercise_index}]"
            if not isinstance(raw_exercise, Mapping):
                errors.append(prefix)
                continue
            for field in _REQUIRED_EXERCISE_TEXT_FIELDS:
                value = raw_exercise.get(field)
                if not isinstance(value, str) or not value.strip():
                    errors.append(f"{prefix}.{field}")
            sets = raw_exercise.get("prescribed_sets")
            if isinstance(sets, bool) or not isinstance(sets, int) or not 1 <= sets <= 10:
                errors.append(f"{prefix}.prescribed_sets")
            rest_seconds = raw_exercise.get("rest_seconds")
            if (
                isinstance(rest_seconds, bool)
                or not isinstance(rest_seconds, int)
                or not 0 <= rest_seconds <= 600
            ):
                errors.append(f"{prefix}.rest_seconds")

    return tuple(dict.fromkeys(errors))


def validate_public_program(program: Mapping[str, object]) -> None:
    errors = public_program_quality_errors(program)
    if errors:
        raise RuntimeError(
            "Published program fails the public quality contract: " + ", ".join(errors)
        )


@lru_cache(maxsize=1)
def public_program(slug: str) -> dict[str, object] | None:
    if slug != PUBLIC_PROGRAM_SLUG:
        return None

    source_spec = next(
        (spec for spec in STRENGTH_TEMPLATE_SPECS if spec.get("slug") == _SOURCE_PROGRAM_SLUG),
        None,
    )
    if not isinstance(source_spec, Mapping):
        raise RuntimeError(f"Public program source {_SOURCE_PROGRAM_SLUG!r} is missing")

    catalog = {
        slug_value: {
            "title": title,
            "primary_muscle": primary_muscle,
            "equipment": equipment,
        }
        for slug_value, title, primary_muscle, equipment in EXERCISE_CATALOG
    }
    raw_days = source_spec.get("days")
    if not isinstance(raw_days, list):
        raise RuntimeError(f"Public program source {_SOURCE_PROGRAM_SLUG!r} has no days")

    days: list[dict[str, object]] = []
    for day_number, raw_day in enumerate(raw_days, start=1):
        if not isinstance(raw_day, tuple) or len(raw_day) != 2:
            raise RuntimeError(f"Public program source day {day_number} is malformed")
        day_title, raw_exercises = raw_day
        if not isinstance(day_title, str) or not isinstance(raw_exercises, list):
            raise RuntimeError(f"Public program source day {day_number} is malformed")

        exercises: list[dict[str, object]] = []
        for exercise_index, raw_exercise in enumerate(raw_exercises, start=1):
            if not isinstance(raw_exercise, tuple) or len(raw_exercise) != 4:
                raise RuntimeError(
                    f"Public program source exercise {day_number}:{exercise_index} is malformed"
                )
            exercise_slug, prescribed_sets, prescribed_reps, rest_seconds = raw_exercise
            catalog_item = catalog.get(exercise_slug)
            if catalog_item is None:
                raise RuntimeError(
                    f"Public program source exercise {exercise_slug!r} is missing catalog data"
                )
            if (
                not isinstance(prescribed_sets, int)
                or isinstance(prescribed_sets, bool)
                or not isinstance(prescribed_reps, str)
                or not isinstance(rest_seconds, int)
                or isinstance(rest_seconds, bool)
            ):
                raise RuntimeError(
                    f"Public program source exercise {day_number}:{exercise_index} is malformed"
                )
            exercises.append(
                {
                    "slug": exercise_slug,
                    **catalog_item,
                    "difficulty_level": exercise_difficulty_level(exercise_slug),
                    "prescribed_sets": prescribed_sets,
                    "prescribed_reps": prescribed_reps,
                    "rest_seconds": rest_seconds,
                }
            )
        days.append({"day_number": day_number, "title": day_title, "exercises": exercises})

    program: dict[str, object] = {
        "slug": PUBLIC_PROGRAM_SLUG,
        "title": source_spec.get("title"),
        "goal": source_spec.get("goal"),
        "level": source_spec.get("level"),
        "split_type": source_spec.get("split_type"),
        "days": days,
    }
    validate_public_program(program)
    return program
