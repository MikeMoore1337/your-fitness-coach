from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

from sqlalchemy import or_
from sqlalchemy.orm import Session

from fitminiapp_api.core.timezone import now_for_user_naive, today_for_user
from fitminiapp_api.models.exercise import Exercise, ExerciseAlternative
from fitminiapp_api.models.program import (
    TrainingBlock,
    TrainingBlockPriorityMuscle,
    UserWorkout,
    UserWorkoutExercise,
    WorkoutAdaptation,
)
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.workout import WorkoutAdaptationRequest
from fitminiapp_api.services.exercise_catalog import (
    _source_exercise_slug,
    get_visible_exercise_display_map,
)
from fitminiapp_api.services.exercise_catalog_metadata import exercise_catalog_metadata
from fitminiapp_api.services.prescription_semantics import compatible_for_substitution
from fitminiapp_api.services.workout_metrics import (
    exercise_metric_type,
    workout_exercise_metric_type,
)

RULESET_VERSION = "workout-adaptation-v1"
ACTIVE_SECONDS_PER_SET = 45
TRANSITION_SECONDS_PER_EXERCISE = 60
CORE_GROUP_COUNT = 2


class WorkoutAdaptationError(ValueError):
    def __init__(self, detail: str, *, status_code: int = 409) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


@dataclass(frozen=True)
class AlternativeCandidate:
    exercise: Exercise
    equipment_ids: tuple[str, ...]
    score: int
    reason_keys: tuple[str, ...]


def _effective_exercise_id(exercise: Exercise) -> int:
    return exercise.source_exercise_id or exercise.id


def _equipment_ids(exercise: Exercise) -> tuple[str, ...]:
    return tuple(link.equipment.identifier for link in exercise.equipment_links)


def _primary_muscle_ids(exercise: Exercise) -> set[int]:
    return {link.muscle_id for link in exercise.muscle_links if link.role == "primary"}


def _ordered_groups(workout: UserWorkout) -> list[list[UserWorkoutExercise]]:
    groups: list[list[UserWorkoutExercise]] = []
    supersets: dict[int, list[UserWorkoutExercise]] = {}
    for item in sorted(workout.exercises, key=lambda row: (row.sort_order, row.id)):
        if item.superset_group is None:
            groups.append([item])
            continue
        if item.superset_group not in supersets:
            supersets[item.superset_group] = []
            groups.append(supersets[item.superset_group])
        supersets[item.superset_group].append(item)
    return groups


def _priority_muscle_ids(db: Session, workout: UserWorkout) -> set[int]:
    return {
        row[0]
        for row in (
            db.query(TrainingBlockPriorityMuscle.muscle_id)
            .join(
                TrainingBlock,
                TrainingBlock.id == TrainingBlockPriorityMuscle.training_block_id,
            )
            .filter(
                TrainingBlock.user_program_id == workout.user_program_id,
                TrainingBlock.status.in_({"planned", "active"}),
                TrainingBlock.start_date <= workout.scheduled_date,
                TrainingBlock.end_date >= workout.scheduled_date,
            )
            .all()
        )
    }


def _priority_by_exercise_id(db: Session, workout: UserWorkout) -> dict[int, str]:
    priority_muscles = _priority_muscle_ids(db, workout)
    result: dict[int, str] = {}
    for index, group in enumerate(_ordered_groups(workout)):
        priority = "core" if index < CORE_GROUP_COUNT else "accessory"
        if (
            priority != "core"
            and priority_muscles
            and any(_primary_muscle_ids(item.exercise) & priority_muscles for item in group)
        ):
            priority = "priority"
        for item in group:
            result[item.id] = priority
    return result


def _estimated_seconds(exercises: list[dict]) -> int:
    if not exercises:
        return 0
    return sum(
        item["prescribed_sets"] * ACTIVE_SECONDS_PER_SET
        + max(item["prescribed_sets"] - 1, 0) * item["rest_seconds"]
        + TRANSITION_SECONDS_PER_EXERCISE
        for item in exercises
    )


def _estimated_minutes(exercises: list[dict]) -> int:
    return math.ceil(_estimated_seconds(exercises) / 60)


def _exercise_payload(
    item: UserWorkoutExercise,
    *,
    exercise: Exercise,
    priority: str,
) -> dict:
    return {
        "workout_exercise_id": item.id,
        "exercise_id": exercise.id,
        "title": exercise.title,
        "equipment_ids": list(_equipment_ids(exercise)),
        "prescribed_sets": item.prescribed_sets,
        "prescribed_reps": item.prescribed_reps,
        "rest_seconds": item.rest_seconds,
        "sort_order": item.sort_order,
        "superset_group": item.superset_group,
        "prescription": item.prescription,
        "priority": priority,
    }


def _snapshot(
    db: Session,
    workout: UserWorkout,
    current_user: User,
    *,
    visible: dict[int, Exercise] | None = None,
) -> dict:
    visible = visible or get_visible_exercise_display_map(db, current_user)
    priorities = _priority_by_exercise_id(db, workout)
    exercises = []
    for item in sorted(workout.exercises, key=lambda row: (row.sort_order, row.id)):
        display = visible.get(_effective_exercise_id(item.exercise), item.exercise)
        exercises.append(_exercise_payload(item, exercise=display, priority=priorities[item.id]))
    return {
        "workout_id": workout.id,
        "scheduled_date": workout.scheduled_date.isoformat(),
        "status": workout.status,
        "adaptation_ids": [item.id for item in workout.adaptations],
        "exercises": exercises,
    }


def _request_payload(payload: WorkoutAdaptationRequest) -> dict:
    return payload.model_dump(mode="json", exclude={"preview_token"}, exclude_none=True)


def _preview_token(snapshot: dict, request: dict, changes: list[dict]) -> str:
    document = {
        "ruleset_version": RULESET_VERSION,
        "snapshot": snapshot,
        "request": request,
        "changes": changes,
    }
    encoded = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _validate_today_state(workout: UserWorkout, current_user: User, *, safety: bool) -> None:
    if workout.scheduled_date != today_for_user(current_user):
        raise WorkoutAdaptationError("Можно адаптировать только тренировку на сегодня")
    allowed = {"planned", "in_progress"} if safety else {"planned"}
    if workout.status not in allowed:
        raise WorkoutAdaptationError(
            "Изменить состав можно только до начала тренировки",
        )
    if not workout.user_program.is_active:
        raise WorkoutAdaptationError("Программа уже завершена или архивирована")


def _find_workout_exercise(workout: UserWorkout, workout_exercise_id: int | None):
    item = next(
        (row for row in workout.exercises if row.id == workout_exercise_id),
        None,
    )
    if item is None:
        raise WorkoutAdaptationError("Упражнение не входит в эту тренировку", status_code=404)
    return item


def _alternative_candidates(
    db: Session,
    current_user: User,
    target: UserWorkoutExercise,
    available_equipment_ids: set[str],
    *,
    visible: dict[int, Exercise] | None = None,
    pairs: list[ExerciseAlternative] | None = None,
    allow_catalog_fallback: bool = False,
) -> list[AlternativeCandidate]:
    from fitminiapp_api.services.training_preferences import avoided_exercise_ids

    visible = visible or get_visible_exercise_display_map(db, current_user)
    avoided_ids = avoided_exercise_ids(current_user.profile)
    target_id = _effective_exercise_id(target.exercise)
    if pairs is None:
        pairs = (
            db.query(ExerciseAlternative)
            .filter(
                or_(
                    ExerciseAlternative.exercise_id == target_id,
                    ExerciseAlternative.alternative_exercise_id == target_id,
                )
            )
            .all()
        )
    curated_ids = {
        pair.alternative_exercise_id if pair.exercise_id == target_id else pair.exercise_id
        for pair in pairs
        if target_id in {pair.exercise_id, pair.alternative_exercise_id}
    }
    candidate_ids = set(visible) if allow_catalog_fallback else curated_ids
    target_metric = workout_exercise_metric_type(target)
    target_metadata = exercise_catalog_metadata(_source_exercise_slug(target.exercise))
    target_muscles = _primary_muscle_ids(target.exercise)
    candidates = []
    for candidate_id in candidate_ids:
        exercise = visible.get(candidate_id)
        if exercise is None or _effective_exercise_id(exercise) in avoided_ids:
            continue
        if exercise_metric_type(exercise) != target_metric:
            continue
        equipment_ids = _equipment_ids(exercise)
        if equipment_ids and not set(equipment_ids).issubset(available_equipment_ids):
            continue
        if _effective_exercise_id(exercise) == target_id:
            continue
        metadata = exercise_catalog_metadata(_source_exercise_slug(exercise))
        reason_keys: list[str] = []
        score = 0
        if _effective_exercise_id(exercise) in curated_ids:
            score += 100
            reason_keys.append("curated_pair")
        if (
            target_metadata
            and metadata
            and metadata["movement_pattern"] == target_metadata["movement_pattern"]
        ):
            score += 50
            reason_keys.append("movement_pattern")
        if target_muscles & _primary_muscle_ids(exercise):
            score += 30
            reason_keys.append("primary_muscle")
        if target_metadata and metadata:
            if set(target_metadata["machine_variant_tags"]) & set(metadata["machine_variant_tags"]):
                score += 5
                reason_keys.append("machine_variant")
            if set(target_metadata["execution_variant_tags"]) & set(
                metadata["execution_variant_tags"]
            ):
                score += 5
                reason_keys.append("execution_variant")
        candidates.append(
            AlternativeCandidate(
                exercise=exercise,
                equipment_ids=equipment_ids,
                score=score,
                reason_keys=tuple(reason_keys),
            )
        )
    return sorted(
        candidates,
        key=lambda item: (
            -item.score,
            item.exercise.title.casefold(),
            _effective_exercise_id(item.exercise),
        ),
    )


def list_compatible_alternatives(
    db: Session,
    current_user: User,
    workout: UserWorkout,
    workout_exercise_id: int,
    available_equipment_ids: set[str],
) -> list[dict]:
    _validate_today_state(workout, current_user, safety=False)
    target = _find_workout_exercise(workout, workout_exercise_id)
    used_ids = {_effective_exercise_id(item.exercise) for item in workout.exercises}
    return [
        {
            "exercise_id": candidate.exercise.id,
            "title": candidate.exercise.title,
            "equipment_ids": list(candidate.equipment_ids),
            "score": candidate.score,
            "reason_keys": list(candidate.reason_keys),
        }
        for candidate in _alternative_candidates(
            db,
            current_user,
            target,
            available_equipment_ids,
            allow_catalog_fallback=True,
        )
        if _effective_exercise_id(candidate.exercise) not in used_ids
    ]


def _replacement_change(
    target: UserWorkoutExercise,
    candidate: AlternativeCandidate,
) -> dict:
    return {
        "kind": "replaced",
        "workout_exercise_id": target.id,
        "from_exercise_id": target.exercise.id,
        "from_title": target.exercise.title,
        "to_exercise_id": candidate.exercise.id,
        "to_title": candidate.exercise.title,
        "transfer": "compatible_with_load_reset",
        "load_reset_required": True,
        "reason_keys": list(candidate.reason_keys),
    }


def _ensure_replacement_unstarted(workout: UserWorkout, target: UserWorkoutExercise) -> None:
    if workout.status != "planned":
        raise WorkoutAdaptationError("Заменить упражнение можно только до начала тренировки")
    if any(
        item.is_completed
        or item.actual_reps is not None
        or item.actual_weight is not None
        or item.duration_minutes is not None
        or item.distance_km is not None
        for item in target.sets
    ):
        raise WorkoutAdaptationError("Заменить упражнение можно только до записи подходов")


def _time_budget_changes(
    workout: UserWorkout, snapshot: dict, budget: int
) -> tuple[list[dict], list[str]]:
    remaining_ids = {item["workout_exercise_id"] for item in snapshot["exercises"]}
    changes: list[dict] = []
    warnings: list[str] = []
    payload_by_id = {item["workout_exercise_id"]: item for item in snapshot["exercises"]}
    for group in reversed(_ordered_groups(workout)):
        remaining = [payload_by_id[item_id] for item_id in remaining_ids]
        if _estimated_minutes(remaining) <= budget:
            break
        if any(payload_by_id[item.id]["priority"] != "accessory" for item in group):
            continue
        for item in group:
            source = payload_by_id[item.id]
            remaining_ids.remove(item.id)
            changes.append(
                {
                    "kind": "removed",
                    "workout_exercise_id": item.id,
                    "from_exercise_id": source["exercise_id"],
                    "from_title": source["title"],
                    "to_exercise_id": None,
                    "to_title": None,
                }
            )
    adapted = [
        item for item in snapshot["exercises"] if item["workout_exercise_id"] in remaining_ids
    ]
    if _estimated_minutes(adapted) > budget:
        warnings.append(
            "Заданный бюджет меньше расчётного времени сохранённой основы тренировки. "
            "Основные и приоритетные упражнения не удалены."
        )
    return sorted(changes, key=lambda item: item["workout_exercise_id"]), warnings


def _replacement_changes(
    db: Session,
    current_user: User,
    workout: UserWorkout,
    payload: WorkoutAdaptationRequest,
    visible: dict[int, Exercise],
) -> list[dict]:
    available: set[str] = set(payload.available_equipment_ids or [])
    if payload.reason in {"unavailable_equipment", "replace_exercise"}:
        targets = [_find_workout_exercise(workout, payload.target_workout_exercise_id)]
        if payload.reason == "unavailable_equipment":
            current_equipment = _equipment_ids(targets[0].exercise)
            if current_equipment and set(current_equipment).issubset(available):
                targets = []
    else:
        targets = [
            item
            for item in workout.exercises
            if not _equipment_ids(item.exercise)
            or not set(_equipment_ids(item.exercise)).issubset(available)
        ]
    if not targets:
        return []

    target_ids = {_effective_exercise_id(item.exercise) for item in targets}
    pairs = (
        db.query(ExerciseAlternative)
        .filter(
            or_(
                ExerciseAlternative.exercise_id.in_(target_ids),
                ExerciseAlternative.alternative_exercise_id.in_(target_ids),
            )
        )
        .all()
    )
    used_ids = {_effective_exercise_id(item.exercise) for item in workout.exercises}
    changes = []
    for target in sorted(targets, key=lambda item: (item.sort_order, item.id)):
        _ensure_replacement_unstarted(workout, target)
        candidates = [
            candidate
            for candidate in _alternative_candidates(
                db,
                current_user,
                target,
                available,
                visible=visible,
                pairs=pairs,
                allow_catalog_fallback=payload.reason == "replace_exercise",
            )
            if _effective_exercise_id(candidate.exercise) not in used_ids
        ]
        if payload.reason == "replace_exercise":
            candidate = next(
                (
                    item
                    for item in candidates
                    if payload.replacement_exercise_id
                    in {item.exercise.id, _effective_exercise_id(item.exercise)}
                ),
                None,
            )
            if candidate is None:
                raise WorkoutAdaptationError(
                    "Выбранная замена не входит в проверенные альтернативы или требует "
                    "недоступное оборудование"
                )
        else:
            candidate = candidates[0] if candidates else None
            if candidate is None:
                raise WorkoutAdaptationError(
                    f"Для упражнения «{target.exercise.title}» нет проверенной замены "
                    "под выбранное оборудование"
                )
        compatible, reason_keys = compatible_for_substitution(
            target.prescription,
            target.prescription,
            source_metric=workout_exercise_metric_type(target),
            target_metric=exercise_metric_type(candidate.exercise),
        )
        if not compatible:
            raise WorkoutAdaptationError("Выбранная замена несовместима с предписанием")
        change = _replacement_change(target, candidate)
        change["reason_keys"] = list(dict.fromkeys([*change["reason_keys"], *reason_keys]))
        changes.append(change)
        used_ids.add(_effective_exercise_id(candidate.exercise))
    return changes


def build_adaptation_preview(
    db: Session,
    current_user: User,
    workout: UserWorkout,
    payload: WorkoutAdaptationRequest,
) -> dict:
    safety = payload.reason == "pain_or_injury"
    _validate_today_state(workout, current_user, safety=safety)
    visible = get_visible_exercise_display_map(db, current_user)
    snapshot = _snapshot(db, workout, current_user, visible=visible)
    original_exercises = snapshot["exercises"]
    original_minutes = _estimated_minutes(original_exercises)
    if safety:
        return {
            "status": "safety_stop",
            "workout_id": workout.id,
            "reason": payload.reason,
            "ruleset_version": RULESET_VERSION,
            "original_estimated_minutes": original_minutes,
            "adapted_estimated_minutes": original_minutes,
            "time_budget_minutes": None,
            "changes": [],
            "original_exercises": original_exercises,
            "adapted_exercises": original_exercises,
            "warnings": [],
            "message": (
                "При боли или травме приложение не подбирает медицинскую замену. "
                "Остановите упражнение и обратитесь к квалифицированному специалисту; "
                "при острой или усиливающейся боли прекратите тренировку."
            ),
            "preview_token": None,
        }

    if payload.reason == "limited_time":
        changes, warnings = _time_budget_changes(
            workout,
            snapshot,
            payload.time_budget_minutes or 0,
        )
    else:
        changes = _replacement_changes(db, current_user, workout, payload, visible)
        warnings = []

    removed_ids = {
        change["workout_exercise_id"] for change in changes if change["kind"] == "removed"
    }
    replacements = {
        change["workout_exercise_id"]: change for change in changes if change["kind"] == "replaced"
    }
    adapted_exercises = []
    for item in original_exercises:
        workout_exercise_id = item["workout_exercise_id"]
        if workout_exercise_id in removed_ids:
            continue
        replacement = replacements.get(workout_exercise_id)
        if replacement is None:
            adapted_exercises.append(item)
            continue
        exercise = next(
            (row for row in visible.values() if row.id == replacement["to_exercise_id"]),
            None,
        )
        if exercise is None:
            raise WorkoutAdaptationError("Проверенная замена больше недоступна")
        adapted_exercises.append(
            {
                **item,
                "exercise_id": exercise.id,
                "title": exercise.title,
                "equipment_ids": list(_equipment_ids(exercise)),
            }
        )

    status = "preview" if changes else "no_changes"
    request = _request_payload(payload)
    return {
        "status": status,
        "workout_id": workout.id,
        "reason": payload.reason,
        "ruleset_version": RULESET_VERSION,
        "original_estimated_minutes": original_minutes,
        "adapted_estimated_minutes": _estimated_minutes(adapted_exercises),
        "time_budget_minutes": payload.time_budget_minutes,
        "changes": changes,
        "original_exercises": original_exercises,
        "adapted_exercises": adapted_exercises,
        "warnings": warnings,
        "message": (
            "Проверьте изменения перед применением. Будет изменена только эта тренировка."
            if changes
            else "Подходящих изменений для выбранных условий нет."
        ),
        "preview_token": _preview_token(snapshot, request, changes) if changes else None,
    }


def apply_adaptation(
    db: Session,
    current_user: User,
    workout: UserWorkout,
    payload: WorkoutAdaptationRequest,
    preview_token: str,
) -> WorkoutAdaptation:
    existing = (
        db.query(WorkoutAdaptation)
        .filter(
            WorkoutAdaptation.workout_id == workout.id,
            WorkoutAdaptation.preview_token == preview_token,
        )
        .first()
    )
    if existing is not None:
        if existing.request_payload != _request_payload(payload):
            raise WorkoutAdaptationError("Preview token не соответствует условиям изменения")
        return existing

    preview = build_adaptation_preview(db, current_user, workout, payload)
    if preview["status"] != "preview" or not preview["changes"]:
        raise WorkoutAdaptationError("Нет изменений, которые можно применить")
    if preview["preview_token"] != preview_token:
        raise WorkoutAdaptationError(
            "Тренировка или условия изменились. Сформируйте preview заново"
        )

    original_snapshot = {
        "workout_id": workout.id,
        "scheduled_date": workout.scheduled_date.isoformat(),
        "status": workout.status,
        "adaptation_ids": [item.id for item in workout.adaptations],
        "exercises": preview["original_exercises"],
    }
    by_id = {item.id: item for item in workout.exercises}
    for change in preview["changes"]:
        target = by_id[change["workout_exercise_id"]]
        if change["kind"] == "removed":
            db.delete(target)
        else:
            target.exercise_id = change["to_exercise_id"]
            target.metric_type = workout_exercise_metric_type(target)

    adaptation = WorkoutAdaptation(
        workout_id=workout.id,
        reason=payload.reason,
        preview_token=preview_token,
        request_payload=_request_payload(payload),
        original_snapshot=original_snapshot,
        applied_diff=preview["changes"],
        ruleset_version=RULESET_VERSION,
        applied_at=now_for_user_naive(current_user),
    )
    db.add(adaptation)
    db.commit()
    db.refresh(adaptation)
    return adaptation
