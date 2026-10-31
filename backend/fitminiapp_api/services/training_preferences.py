from __future__ import annotations

import math
from datetime import time

from sqlalchemy.orm import Session, selectinload

from fitminiapp_api.models.exercise import Exercise, ExerciseEquipment
from fitminiapp_api.models.program import UserProgram, UserWorkout, UserWorkoutExercise
from fitminiapp_api.models.user import User, UserProfile
from fitminiapp_api.schemas.user import (
    TrainingPreferencesResponse,
    TrainingPreferencesUpdate,
)
from fitminiapp_api.services.exercise_catalog import (
    _effective_exercise_id,
    get_visible_exercise_display_map,
)
from fitminiapp_api.services.exercise_domain import EQUIPMENT_NAME_BY_IDENTIFIER

ACTIVE_SECONDS_PER_SET = 45
TRANSITION_SECONDS_PER_EXERCISE = 60


def _normalized_note(value: str | None) -> str | None:
    normalized = (value or "").strip()
    return normalized or None


def _preference_payload(profile: UserProfile) -> dict:
    return {
        "preferred_duration_min": profile.preferred_workout_duration_min,
        "preferred_duration_max": profile.preferred_workout_duration_max,
        "preferred_weekdays": list(profile.preferred_training_weekdays or []),
        "preferred_time": profile.preferred_training_time,
        "location_profiles": list(profile.training_location_profiles or []),
        "preferred_exercise_ids": list(profile.preferred_exercise_ids or []),
        "avoided_exercises": list(profile.avoided_exercises or []),
        "note": profile.training_preferences_note,
    }


def _has_training_preferences(profile: UserProfile) -> bool:
    payload = _preference_payload(profile)
    return any(value not in (None, [], "") for value in payload.values())


def replace_training_preferences(
    db: Session,
    profile: UserProfile,
    owner: User,
    preferences: TrainingPreferencesUpdate | None,
    changed_by: User,
) -> bool:
    normalized = preferences or TrainingPreferencesUpdate()
    visible_ids = set(get_visible_exercise_display_map(db, owner))
    selected_ids = set(normalized.preferred_exercise_ids) | {
        item.exercise_id for item in normalized.avoided_exercises
    }
    if not selected_ids.issubset(visible_ids):
        raise ValueError("One or more selected exercises are unavailable")

    payload = normalized.model_dump(mode="python")
    payload["preferred_weekdays"] = sorted(payload["preferred_weekdays"])
    payload["location_profiles"] = sorted(
        (
            {
                "location": item["location"],
                "equipment_ids": sorted(item["equipment_ids"]),
            }
            for item in payload["location_profiles"]
        ),
        key=lambda item: item["location"],
    )
    payload["preferred_exercise_ids"] = sorted(payload["preferred_exercise_ids"])
    payload["avoided_exercises"] = sorted(
        payload["avoided_exercises"], key=lambda item: item["exercise_id"]
    )
    payload["note"] = _normalized_note(payload["note"])

    current = _preference_payload(profile)
    if current == payload:
        return False

    profile.preferred_workout_duration_min = payload["preferred_duration_min"]
    profile.preferred_workout_duration_max = payload["preferred_duration_max"]
    profile.preferred_training_weekdays = payload["preferred_weekdays"]
    profile.preferred_training_time = payload["preferred_time"]
    profile.training_location_profiles = payload["location_profiles"]
    profile.preferred_exercise_ids = payload["preferred_exercise_ids"]
    profile.avoided_exercises = payload["avoided_exercises"]
    profile.training_preferences_note = payload["note"]
    profile.training_preferences_updated_by_user_id = changed_by.id
    from fitminiapp_api.core.timezone import now_msk_naive

    profile.training_preferences_updated_at = now_msk_naive()
    return True


def avoided_exercise_ids(profile: UserProfile | None) -> frozenset[int]:
    if profile is None:
        return frozenset()
    return frozenset(
        item["exercise_id"]
        for item in (profile.avoided_exercises or [])
        if isinstance(item, dict) and isinstance(item.get("exercise_id"), int)
    )


def preferred_exercise_ids(profile: UserProfile | None) -> frozenset[int]:
    if profile is None:
        return frozenset()
    return frozenset(
        item for item in (profile.preferred_exercise_ids or []) if isinstance(item, int)
    )


def equipment_for_location(
    profile: UserProfile | None, location: str | None
) -> frozenset[str] | None:
    if profile is None:
        return None
    profiles = [
        item for item in (profile.training_location_profiles or []) if isinstance(item, dict)
    ]
    if location is not None:
        profiles = [item for item in profiles if item.get("location") == location]
    elif len(profiles) != 1:
        return None
    if not profiles:
        return None
    return frozenset(item for item in profiles[0].get("equipment_ids", []) if isinstance(item, str))


def single_training_location(profile: UserProfile | None) -> str | None:
    if profile is None:
        return None
    profiles = [
        item for item in (profile.training_location_profiles or []) if isinstance(item, dict)
    ]
    return profiles[0].get("location") if len(profiles) == 1 else None


def _editor_payload(db: Session, owner: User, editor_id: int | None) -> dict | None:
    if editor_id is None:
        return None
    editor = db.query(User).filter(User.id == editor_id).one_or_none()
    if editor is None:
        return None
    profile_name = editor.profile.full_name if editor.profile else None
    display_name = profile_name or " ".join(
        part for part in (editor.first_name, editor.last_name) if part
    )
    return {
        "user_id": editor.id,
        "display_name": display_name or editor.username or f"Пользователь {editor.id}",
        "role": "self" if editor.id == owner.id else "trainer",
    }


def _estimated_minutes(items: list[UserWorkoutExercise]) -> int:
    seconds = 0
    for item in items:
        sets, rest = item.prescribed_sets, item.rest_seconds
        if sets is None or rest is None:
            raise ValueError("Missing planned exercise parameters")
        seconds += (
            sets * ACTIVE_SECONDS_PER_SET
            + max(sets - 1, 0) * rest
            + TRANSITION_SECONDS_PER_EXERCISE
        )
    return math.ceil(seconds / 60) if seconds else 0


def _equipment_ids(exercise: Exercise) -> set[str]:
    return {
        link.equipment.identifier
        for link in exercise.equipment_links
        if link.equipment.identifier != "bodyweight"
    }


def _time_text(value: time) -> str:
    return value.strftime("%H:%M")


def build_training_preferences_conflict(db: Session, owner: User, profile: UserProfile) -> dict:
    program = (
        db.query(UserProgram)
        .filter(UserProgram.user_id == owner.id, UserProgram.is_active.is_(True))
        .one_or_none()
    )
    if program is None:
        return {"status": "none", "active_program_id": None, "reasons": []}

    reasons: list[str] = []
    preferred_weekdays = set(profile.preferred_training_weekdays or [])
    if preferred_weekdays and not set(program.schedule_weekdays or []).issubset(preferred_weekdays):
        reasons.append("Расписание активной программы не совпадает с выбранными днями.")

    workouts = (
        db.query(UserWorkout)
        .options(
            selectinload(UserWorkout.exercises)
            .joinedload(UserWorkoutExercise.exercise)
            .selectinload(Exercise.equipment_links)
            .joinedload(ExerciseEquipment.equipment)
        )
        .filter(
            UserWorkout.user_program_id == program.id,
            UserWorkout.status.in_(("planned", "in_progress")),
        )
        .all()
    )
    avoided_ids = avoided_exercise_ids(profile)
    if avoided_ids and any(
        _effective_exercise_id(item.exercise) in avoided_ids
        for workout in workouts
        for item in workout.exercises
    ):
        reasons.append("В активной программе есть упражнение из списка «избегать».")

    locations = [
        item for item in (profile.training_location_profiles or []) if isinstance(item, dict)
    ]
    available_sets = [set(item.get("equipment_ids", [])) for item in locations]
    required_equipment = {
        equipment_id
        for workout in workouts
        for item in workout.exercises
        for equipment_id in _equipment_ids(item.exercise)
    }
    if (
        available_sets
        and required_equipment
        and not any(required_equipment.issubset(available) for available in available_sets)
    ):
        missing_names = sorted(
            EQUIPMENT_NAME_BY_IDENTIFIER.get(item, item)
            for item in required_equipment
            if not any(item in available for available in available_sets)
        )
        suffix = f": {', '.join(missing_names)}" if missing_names else ""
        reasons.append(f"Для активной программы может не хватать оборудования{suffix}.")

    durations = [_estimated_minutes(workout.exercises) for workout in workouts if workout.exercises]
    minimum = profile.preferred_workout_duration_min
    maximum = profile.preferred_workout_duration_max
    if durations and (
        (minimum is not None and any(value < minimum for value in durations))
        or (maximum is not None and any(value > maximum for value in durations))
    ):
        reasons.append("Расчётная длительность текущих тренировок выходит за выбранный диапазон.")

    preferred_time = profile.preferred_training_time
    if preferred_time is not None and any(
        workout.scheduled_time != preferred_time for workout in workouts
    ):
        reasons.append(
            f"Время активной программы нужно сверить с предпочтением {_time_text(preferred_time)}."
        )

    return {
        "status": "review_required" if reasons else "none",
        "active_program_id": program.id,
        "reasons": reasons,
    }


def serialize_training_preferences(
    db: Session,
    owner: User,
    profile: UserProfile,
    *,
    include_runtime_context: bool = True,
) -> TrainingPreferencesResponse:
    has_preferences = _has_training_preferences(profile)
    include_editor = include_runtime_context and (
        profile.training_preferences_updated_at is not None
        or profile.training_preferences_updated_by_user_id is not None
    )
    return TrainingPreferencesResponse.model_validate(
        {
            **_preference_payload(profile),
            "updated_at": profile.training_preferences_updated_at,
            "updated_by": (
                _editor_payload(db, owner, profile.training_preferences_updated_by_user_id)
                if include_editor
                else None
            ),
            "conflict": (
                build_training_preferences_conflict(db, owner, profile)
                if include_runtime_context and has_preferences
                else {"status": "none", "active_program_id": None, "reasons": []}
            ),
        }
    )
