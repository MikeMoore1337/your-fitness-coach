from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from fitminiapp_api.core.timezone import now_in_timezone
from fitminiapp_api.models.exercise import Exercise
from fitminiapp_api.models.program import (
    UserProgram,
    UserWorkout,
    UserWorkoutExercise,
    UserWorkoutSet,
)
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.program import ExercisePrescriptionPlan
from fitminiapp_api.services.exercise_catalog_metadata import exercise_catalog_metadata
from fitminiapp_api.services.workout_sides import SIDE_MODES, serialize_sides, side_facts_present


class WorkoutSetHistoryNotFound(ValueError):
    pass


def _completion_bounds(workout: UserWorkout) -> tuple[datetime, datetime]:
    if workout.completed_at_utc is not None:
        return workout.completed_at_utc, workout.completed_at_utc
    assert workout.completed_at is not None
    # Legacy offsets are unknown; each supported UTC offset is strictly within 24h.
    return workout.completed_at - timedelta(days=1), workout.completed_at + timedelta(days=1)


def _set_identity(item: UserWorkoutSet) -> tuple:
    return (
        item.set_number,
        item.set_kind,
        item.planned_role,
        item.planned_position,
        item.planned_group_id,
        item.planned_group_kind,
        item.planned_round,
    )


def _topology(
    exercise: UserWorkoutExercise, catalog: Exercise, *, explicit_sides: bool = False
) -> tuple | None:
    metadata = exercise_catalog_metadata(catalog.slug)
    if not metadata or (
        not explicit_sides
        and {"unilateral", "alternating"}.intersection(metadata["execution_variant_tags"])
    ):
        return None
    if exercise.source_template_exercise_id is None or exercise.prescription is None:
        return None
    try:
        plan = ExercisePrescriptionPlan.model_validate(exercise.prescription)
    except ValidationError:
        return None
    if plan.metric_type != "strength" or exercise.metric_type not in {None, "strength"}:
        return None
    return (
        exercise.superset_group,
        exercise.superset_order,
        exercise.group_id,
        exercise.group_kind,
        exercise.group_order,
        tuple(
            (part.position, part.role, part.group_id, part.group_position, part.round_number)
            for part in plan.segments
        ),
        tuple(
            (group.group_id, group.kind, group.rounds, group.exercise_slot) for group in plan.groups
        ),
    )


def _result(item: UserWorkoutSet) -> dict:
    return {
        "set_id": item.id,
        "set_number": item.set_number,
        "set_version": item.version,
        "execution_mode": item.execution_mode,
        "first_side": item.first_side,
        "sides": serialize_sides(item),
        "is_completed": item.is_completed,
        "actual_weight": float(item.actual_weight) if item.actual_weight is not None else None,
        "actual_reps": item.actual_reps,
    }


def _matches_plan(exercise: UserWorkoutExercise, item: UserWorkoutSet) -> bool:
    if exercise.prescription is None or item.set_number != item.planned_position:
        return False
    segment = next(
        (
            part
            for part in exercise.prescription["segments"]
            if part["position"] == item.planned_position
        ),
        None,
    )
    if segment is None:
        return False
    group = next(
        (
            group
            for group in exercise.prescription.get("groups", [])
            if group["group_id"] == segment.get("group_id")
        ),
        None,
    )
    return (
        item.planned_role == segment["role"]
        and item.planned_group_id == segment.get("group_id")
        and item.planned_round == segment.get("round_number")
        and item.planned_group_kind == (group["kind"] if group else None)
    )


def _group_peers(entries: dict, exercise: UserWorkoutExercise) -> set[tuple]:
    return {
        (
            other.source_template_exercise_id,
            other.exercise_id,
            other.group_order,
            other.superset_order,
        )
        for other, _, _ in entries.values()
        if (exercise.group_id is not None and other.group_id == exercise.group_id)
        or (exercise.superset_group is not None and other.superset_group == exercise.superset_group)
    }


def build_workout_set_history(db: Session, user: User, workout_id: int) -> dict:
    target = (
        select(UserWorkout.user_program_id)
        .join(UserProgram, UserProgram.id == UserWorkout.user_program_id)
        .where(UserWorkout.id == workout_id, UserProgram.user_id == user.id)
        .scalar_subquery()
    )
    lineage = (
        select(UserProgram.id, UserProgram.restarted_from_program_id)
        .where(UserProgram.id == target, UserProgram.user_id == user.id)
        .cte("set_history_lineage", recursive=True)
    )
    # UNION also terminates malformed cyclic lineage without following another owner's program.
    lineage = lineage.union(
        select(UserProgram.id, UserProgram.restarted_from_program_id)
        .join(lineage, UserProgram.id == lineage.c.restarted_from_program_id)
        .where(UserProgram.user_id == user.id)
    )
    # One statement observes target versions, source facts and lineage together, without hydration.
    with db.no_autoflush:
        rows = (
            db.query(
                UserWorkout,
                UserWorkoutExercise,
                UserWorkoutSet,
                Exercise,
                UserProgram.current_revision_number,
            )
            .join(UserProgram, UserProgram.id == UserWorkout.user_program_id)
            .outerjoin(UserWorkoutExercise, UserWorkoutExercise.workout_id == UserWorkout.id)
            .outerjoin(UserWorkoutSet, UserWorkoutSet.workout_exercise_id == UserWorkoutExercise.id)
            .outerjoin(Exercise, Exercise.id == UserWorkoutExercise.exercise_id)
            .options(joinedload(UserWorkoutSet.side_results))
            .filter(
                UserProgram.id.in_(select(lineage.c.id)),
                UserProgram.user_id == user.id,
                or_(UserWorkout.id == workout_id, UserWorkout.status == "completed"),
            )
            .all()
        )
    current = next((row[0] for row in rows if row[0].id == workout_id), None)
    if current is None:
        raise WorkoutSetHistoryNotFound("Тренировка не найдена")
    workouts: dict[int, UserWorkout] = {}
    exercises: dict[int, dict[int, tuple[UserWorkoutExercise, Exercise, list[UserWorkoutSet]]]] = {}
    revision_number = 0
    for workout, exercise, item, catalog, revision in rows:
        workouts[workout.id] = workout
        if workout.id == workout_id:
            revision_number = revision
        if exercise is not None and catalog is not None:
            entry = exercises.setdefault(workout.id, {}).setdefault(
                exercise.id, (exercise, catalog, [])
            )
            if item is not None and all(row.id != item.id for row in entry[2]):
                entry[2].append(item)
    if current.started_at is not None:
        cutoff_min = current.started_at - timedelta(days=1)
        cutoff_max = current.started_at + timedelta(days=1)
    elif current.completed_at is not None or current.completed_at_utc is not None:
        cutoff_min, cutoff_max = _completion_bounds(current)
    else:
        cutoff_min = cutoff_max = now_in_timezone("UTC").replace(tzinfo=None)
    items = []
    for exercise, catalog, sets in exercises.get(workout_id, {}).values():
        matching_workouts = [
            workout
            for workout in workouts.values()
            if workout.id != workout_id
            and workout.status == "completed"
            and workout.day_number == current.day_number
            and any(
                other.exercise_id == exercise.exercise_id
                and other.source_template_exercise_id == exercise.source_template_exercise_id
                for other, _, _ in exercises.get(workout.id, {}).values()
            )
        ]
        unknown_completion = any(
            row.completed_at is None and row.completed_at_utc is None for row in matching_workouts
        )
        candidates = [
            row
            for row in matching_workouts
            if (row.completed_at is not None or row.completed_at_utc is not None)
            and _completion_bounds(row)[0] < cutoff_max
        ]
        source = max(candidates, key=lambda row: (_completion_bounds(row)[0], row.id), default=None)
        source_entries = (
            [
                entry
                for entry in exercises.get(source.id, {}).values()
                if entry[0].source_template_exercise_id == exercise.source_template_exercise_id
            ]
            if source
            else []
        )
        current_slots = [
            entry
            for entry in exercises[workout_id].values()
            if entry[0].source_template_exercise_id == exercise.source_template_exercise_id
        ]
        source_sets: list[UserWorkoutSet] = []
        explicit_sides = any(item.execution_mode in SIDE_MODES for item in sets) or any(
            item.execution_mode in SIDE_MODES for _, _, rows in source_entries for item in rows
        )
        topology = _topology(exercise, catalog, explicit_sides=explicit_sides)
        proven = (
            topology is not None
            and len(current_slots) == 1
            and not unknown_completion
            and current.plan_materialized is not False
        )
        if source is not None:
            source_min, source_max = _completion_bounds(source)
            proven = proven and source.completed_at is not None and source_max < cutoff_min
            proven = proven and all(
                other.id == source.id or _completion_bounds(other)[1] < source_min
                for other in candidates
            )
        if current.status == "planned" and current.source_cycle_week is not None:
            proven = proven and current.plan_revision_number == revision_number
        if source is not None:
            proven = proven and len(source_entries) == 1
            if proven:
                source_exercise, source_catalog, source_sets = source_entries[0]
                proven = topology == _topology(
                    source_exercise, source_catalog, explicit_sides=explicit_sides
                )

                proven = proven and _group_peers(exercises[workout_id], exercise) == _group_peers(
                    exercises[source.id], exercise
                )
        previous = None
        for item in sorted(
            sets,
            key=lambda row: (
                0 if row.set_kind == "warmup" or row.planned_role == "warmup" else 1,
                row.set_number,
                row.id,
            ),
        ):
            past = None
            status = "identity_unproven" if not proven else "no_previous_workout"
            if proven and source is not None and source.completed_at is not None:
                status = "no_matching_set"
                match = next(
                    (row for row in source_sets if _set_identity(row) == _set_identity(item)), None
                )
                if (
                    item.set_kind is not None
                    and item.planned_role is not None
                    and item.planned_position is not None
                    and match is not None
                    and _matches_plan(exercise, item)
                    and _matches_plan(source_entries[0][0], match)
                    and (match.is_completed or side_facts_present(match))
                    and (
                        match.actual_weight is not None
                        or match.actual_reps is not None
                        or side_facts_present(match)
                    )
                ):
                    past = {
                        **_result(match),
                        "workout_id": source.id,
                        "workout_exercise_id": source_entries[0][0].id,
                        "completed_at": source.completed_at,
                        "performed_on": source.completed_at.date(),
                    }
                    status = "matched"
            items.append(
                {
                    "set_id": item.id,
                    "set_number": item.set_number,
                    "set_version": item.version,
                    "workout_exercise_id": exercise.id,
                    "exercise_id": exercise.exercise_id,
                    "source_template_exercise_id": exercise.source_template_exercise_id,
                    "previous_today": previous,
                    "previous_workout": past,
                    "history_status": status,
                }
            )
            if item.is_completed and (
                item.actual_weight is not None
                or item.actual_reps is not None
                or side_facts_present(item)
            ):
                previous = _result(item)
    return {
        "workout_id": workout_id,
        "user_program_id": current.user_program_id,
        "program_revision_number": revision_number,
        "sets": items,
    }
