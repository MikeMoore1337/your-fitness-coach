from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from datetime import date, timedelta
from itertools import pairwise

from sqlalchemy import and_, inspect, or_
from sqlalchemy.orm import Session, SessionTransactionOrigin, joinedload, selectinload

from fitminiapp_api.core.timezone import now_msk_naive, today_for_user
from fitminiapp_api.models.exercise import Exercise, Muscle
from fitminiapp_api.models.program import (
    ProgramRevision,
    ProgramTemplate,
    ProgramTemplateDay,
    ProgramTemplateExercise,
    TrainingBlock,
    TrainingBlockPriorityMuscle,
    UserProgram,
    UserWorkout,
    UserWorkoutExercise,
    UserWorkoutSet,
)
from fitminiapp_api.models.user import CoachClient, User, UserProfile
from fitminiapp_api.schemas.program import (
    CoachProgramExerciseCreate,
    ProgramCycleDisableRequest,
    ProgramCycleDurationPreviewRequest,
    ProgramCycleEnableRequest,
    ProgramCycleRevisionRequest,
    ProgramLifecycleActionRequest,
    ProgramWeekTypeRevisionRequest,
    TrainingBlockActionRequest,
    TrainingBlockCreate,
    TrainingBlockUpdate,
)
from fitminiapp_api.services.audit import record_audit_event
from fitminiapp_api.services.exercise_catalog import (
    _effective_exercise_id,
    _load_visible_exercise_rows,
)
from fitminiapp_api.services.notifications import cancel_workout_reminder, queue_notification
from fitminiapp_api.services.prescription_semantics import ensure_plan
from fitminiapp_api.services.program_common import MAX_GENERATED_SETS, ProgramError
from fitminiapp_api.services.workout_metrics import (
    exercise_metric_type,
    workout_exercise_metric_type,
)

MUTABLE_PROGRAM_STATUSES = {"scheduled", "active"}
BLOCK_STATUS_TRANSITIONS = {
    "planned": {"active", "archived"},
    "active": {"completed", "archived"},
    "completed": set(),
    "archived": set(),
}


def _required_plan_number(value: int | None) -> int:
    if value is None:
        raise ProgramError("Для тренировки нет данных плана")
    return value


def _validate_workout_group_assignments(
    exercises: list[UserWorkoutExercise],
    *,
    target: UserWorkoutExercise | None,
    candidate: tuple[int | None, str | None, int | None],
) -> None:
    groups: dict[int, tuple[str, list[int]]] = {}

    def add(group_id: int | None, group_kind: str | None, group_order: int | None) -> None:
        if group_id is None and group_kind is None and group_order is None:
            return
        if group_id is None or group_kind is None or group_order is None:
            raise ProgramError("Exercise group fields must be provided together")
        existing = groups.get(group_id)
        if existing is None:
            groups[group_id] = (group_kind, [group_order])
            return
        existing_kind, orders = existing
        if existing_kind != group_kind or group_order in orders:
            raise ProgramError("Exercise group kind and order must be consistent")
        orders.append(group_order)

    for exercise in exercises:
        if exercise is target:
            continue
        group_id = exercise.group_id if exercise.group_id is not None else exercise.superset_group
        group_kind = exercise.group_kind or ("superset" if exercise.superset_group else None)
        group_order = (
            exercise.group_order if exercise.group_order is not None else exercise.superset_order
        )
        add(group_id, group_kind, group_order)
    add(*candidate)

    for group_kind, orders in groups.values():
        ordered = sorted(orders)
        if ordered != list(range(1, len(ordered) + 1)):
            raise ProgramError("Exercise group orders must be contiguous and unique")
        if group_kind == "superset" and ordered != [1, 2]:
            raise ProgramError("A superset must contain exactly two ordered exercises")


def _actor_role(program: UserProgram, actor: User | None) -> str:
    if actor is None:
        return "system"
    if actor.id == program.user_id:
        return "self"
    return "trainer"


def get_program_for_actor(
    db: Session,
    actor: User,
    program_id: int,
    *,
    lock: bool = False,
) -> tuple[UserProgram, str]:
    query = db.query(UserProgram).filter(UserProgram.id == program_id)
    if lock:
        query = query.populate_existing().with_for_update()
    program = query.first()
    if program is None:
        raise ProgramError("Assigned program not found")
    role = _actor_role(program, actor)
    if role == "self":
        return program, role
    if (
        actor.is_coach
        and program.assigned_by_user_id == actor.id
        and db.query(CoachClient.id)
        .filter(
            CoachClient.coach_user_id == actor.id,
            CoachClient.client_user_id == program.user_id,
            CoachClient.status == "active",
        )
        .first()
        is not None
    ):
        return program, role
    raise ProgramError("Assigned program not found")


def list_program_import_targets(db: Session, actor: User) -> list[dict[str, object]]:
    access_filters = [UserProgram.user_id == actor.id]
    if actor.is_coach:
        client_ids = [
            row[0]
            for row in db.query(CoachClient.client_user_id)
            .filter(CoachClient.coach_user_id == actor.id, CoachClient.status == "active")
            .all()
        ]
        if client_ids:
            access_filters.append(
                and_(
                    UserProgram.assigned_by_user_id == actor.id,
                    UserProgram.user_id.in_(client_ids),
                )
            )
    programs = (
        db.query(UserProgram)
        .options(joinedload(UserProgram.template))
        .filter(
            UserProgram.is_active.is_(True),
            UserProgram.status.in_(MUTABLE_PROGRAM_STATUSES),
            or_(*access_filters),
        )
        .order_by(UserProgram.id.asc())
        .all()
    )
    program_ids = [program.id for program in programs]
    owner_ids = {program.user_id for program in programs if program.user_id != actor.id}
    profiles_by_user_id = {
        profile.user_id: profile
        for profile in (
            db.query(UserProfile).filter(UserProfile.user_id.in_(owner_ids)).all()
            if owner_ids
            else []
        )
    }
    day_numbers_by_program: dict[int, set[int]] = {}
    if program_ids:
        day_rows = (
            db.query(UserWorkout.user_program_id, UserWorkout.day_number)
            .filter(UserWorkout.user_program_id.in_(program_ids))
            .distinct()
            .all()
        )
        for program_id, day_number in day_rows:
            day_numbers_by_program.setdefault(program_id, set()).add(day_number)

    result: list[dict[str, object]] = []
    for program in programs:
        owner_name = None
        if program.user_id != actor.id:
            profile = profiles_by_user_id.get(program.user_id)
            owner_name = (
                profile.full_name if profile is not None else f"Пользователь {program.user_id}"
            )
        day_numbers = sorted(day_numbers_by_program.get(program.id, set()))
        if not day_numbers or len(day_numbers) > 8:
            continue
        result.append(
            {
                "program_id": program.id,
                "title": program.template.title if program.template else "Архивная программа",
                "owner_name": owner_name,
                "duration_weeks": program.duration_weeks,
                "current_revision_number": program.current_revision_number,
                "status": program.status,
                "day_numbers": day_numbers,
            }
        )
    return result


def _serialize_block(block: TrainingBlock) -> dict:
    return {
        "id": block.id,
        "user_program_id": block.user_program_id,
        "title": block.title,
        "start_date": block.start_date,
        "end_date": block.end_date,
        "duration_days": (block.end_date - block.start_date).days + 1,
        "purpose": block.purpose,
        "priority_muscle_ids": [link.muscle.identifier for link in block.priority_links],
        "notes": block.notes,
        "is_deload": block.is_deload,
        "status": block.status,
        "created_by_user_id": block.created_by_user_id,
        "created_at": block.created_at,
        "updated_at": block.updated_at,
    }


def _load_blocks(db: Session, program_id: int) -> list[TrainingBlock]:
    return (
        db.query(TrainingBlock)
        .options(
            selectinload(TrainingBlock.priority_links).joinedload(
                TrainingBlockPriorityMuscle.muscle
            )
        )
        .filter(TrainingBlock.user_program_id == program_id)
        .order_by(TrainingBlock.start_date.asc(), TrainingBlock.id.asc())
        .all()
    )


def _build_program_snapshot(db: Session, program: UserProgram) -> dict:
    loaded = (
        db.query(UserProgram)
        .options(joinedload(UserProgram.template))
        .filter(UserProgram.id == program.id)
        .one()
    )
    workouts = (
        db.query(UserWorkout)
        .options(selectinload(UserWorkout.exercises).selectinload(UserWorkoutExercise.sets))
        .filter(UserWorkout.user_program_id == program.id)
        .order_by(UserWorkout.scheduled_date.asc(), UserWorkout.id.asc())
        .all()
    )
    return {
        "program": {
            "id": loaded.id,
            "user_id": loaded.user_id,
            "template_id": loaded.template_id,
            "title": loaded.template.title if loaded.template else "Архивная программа",
            "goal": loaded.template.goal if loaded.template else None,
            "level": loaded.template.level if loaded.template else None,
            "provenance_type": loaded.template.provenance_type if loaded.template else None,
            "provenance": loaded.template.provenance if loaded.template else None,
            "program_metadata": loaded.template.program_metadata if loaded.template else None,
            "start_date": loaded.start_date.isoformat(),
            "duration_weeks": loaded.duration_weeks,
            "schedule_weekdays": list(loaded.schedule_weekdays),
            "status": loaded.status,
            "is_active": loaded.is_active,
            "current_revision_number": loaded.current_revision_number,
            "restarted_from_program_id": loaded.restarted_from_program_id,
        },
        "workout_policy": "only_future_planned_workouts_are_structurally_mutable",
        "workouts": [
            {
                "id": workout.id,
                "scheduled_date": workout.scheduled_date.isoformat(),
                "day_number": workout.day_number,
                "week_number": workout.week_number,
                "source_cycle_week": workout.source_cycle_week,
                "cycle_iteration": workout.cycle_iteration,
                "plan_revision_number": workout.plan_revision_number,
                "plan_materialized": workout.plan_materialized,
                "title": workout.title,
                "status": workout.status,
                "exercises": [
                    {
                        "exercise_id": exercise.exercise_id,
                        "metric_type": workout_exercise_metric_type(exercise),
                        "sort_order": exercise.sort_order,
                        "prescribed_sets": exercise.prescribed_sets,
                        "prescribed_reps": exercise.prescribed_reps,
                        "prescribed_duration_minutes": exercise.prescribed_duration_minutes,
                        "rest_seconds": exercise.rest_seconds,
                        "notes": exercise.notes,
                        "superset_group": exercise.superset_group,
                        "superset_order": exercise.superset_order,
                        "source_template_exercise_id": exercise.source_template_exercise_id,
                        "source_weekly_prescription_id": exercise.source_weekly_prescription_id,
                        "group_id": exercise.group_id,
                        "group_kind": exercise.group_kind,
                        "group_order": exercise.group_order,
                        "prescription": exercise.prescription,
                        "sets": [
                            {
                                "set_number": item.set_number,
                                "set_kind": item.set_kind,
                                "planned_role": item.planned_role,
                                "planned_group_id": item.planned_group_id,
                                "planned_group_kind": item.planned_group_kind,
                                "planned_position": item.planned_position,
                                "planned_round": item.planned_round,
                                "is_completed": item.is_completed,
                            }
                            for item in sorted(exercise.sets, key=lambda row: row.set_number)
                        ],
                    }
                    for exercise in sorted(
                        workout.exercises, key=lambda row: (row.sort_order, row.id)
                    )
                ],
            }
            for workout in workouts
        ],
        "training_blocks": [
            {
                **_serialize_block(block),
                "start_date": block.start_date.isoformat(),
                "end_date": block.end_date.isoformat(),
                "created_at": block.created_at.isoformat(),
                "updated_at": block.updated_at.isoformat() if block.updated_at else None,
            }
            for block in _load_blocks(db, program.id)
        ],
    }


def _cycle_occurrence_overrides(
    db: Session, program_id: int, *, revisions: list[ProgramRevision] | None = None
) -> list[dict]:
    result = []
    if revisions is None:
        revisions = (
            db.query(ProgramRevision)
            .filter_by(user_program_id=program_id)
            .order_by(ProgramRevision.revision_number)
            .all()
        )
    for revision in revisions:
        result.extend(revision.changed_fields.get("inherited_occurrence_overrides", []))
        if "occurrence_override" in revision.changed_fields:
            result.append(revision.changed_fields["occurrence_override"])
    return result


def _cycle_assignment(
    db: Session, program: UserProgram, *, revisions: list[ProgramRevision] | None = None
) -> ProgramRevision | None:
    if revisions is not None:
        return next(
            (item for item in revisions if item.change_kind in {"assigned", "program_restarted"}),
            None,
        )
    return (
        db.query(ProgramRevision)
        .filter(
            ProgramRevision.user_program_id == program.id,
            ProgramRevision.change_kind.in_(["assigned", "program_restarted"]),
        )
        .order_by(ProgramRevision.revision_number)
        .first()
    )


def _cycle_configurations(
    db: Session, program: UserProgram, *, revisions: list[ProgramRevision] | None = None
) -> list[dict]:
    configs = []
    if revisions is None:
        revisions = (
            db.query(ProgramRevision)
            .filter_by(user_program_id=program.id)
            .order_by(ProgramRevision.revision_number)
            .all()
        )
    for revision in revisions:
        configs.extend(revision.changed_fields.get("inherited_cycle_configurations", []))
        if "cycle_configuration" in revision.changed_fields:
            configs.append(revision.changed_fields["cycle_configuration"])
    return configs


def _cycle_plan_at(
    db: Session, program: UserProgram, week: int, *, revisions: list[ProgramRevision] | None = None
) -> tuple[dict, list[dict], int] | None:
    revision = _cycle_assignment(db, program, revisions=revisions)
    if revision is None:
        return None
    cycle = revision.changed_fields.get("week_cycle") or (
        revision.snapshot["program"].get("program_metadata") or {}
    ).get("week_cycle")
    source = revision.snapshot.get(
        "logical_cycle", revision.changed_fields.get("logical_cycle", revision.snapshot["workouts"])
    )
    boundary = 1
    for config in _cycle_configurations(db, program, revisions=revisions):
        if config["effective_from_week"] <= week:
            cycle, source, boundary = (
                config["week_cycle"],
                config["logical_cycle"],
                config["effective_from_week"],
            )
    return (cycle, source, boundary) if cycle else None


def _override_matches(override: dict, week: int, source_week: int, boundary: int = 1) -> bool:
    if override.get("source_cycle_boundary", boundary) != boundary:
        return False
    if "weeks" in override:
        return week in override["weeks"]
    return override["from_week"] <= week <= override.get("to_week", week) and (
        override.get("source_cycle_week") is None or override["source_cycle_week"] == source_week
    )


def _cycle_workout_plans(
    db: Session,
    program: UserProgram,
    week: int,
    *,
    revisions: list[ProgramRevision] | None = None,
    source_index: dict[int, dict[int, list[dict]]] | None = None,
    scheduled_dates: dict[int, date] | None = None,
) -> list[dict]:
    config = _cycle_plan_at(db, program, week, revisions=revisions)
    if config is None:
        return []
    cycle, source, boundary = config
    if not cycle["repeat"] and week - boundary >= cycle["length_weeks"]:
        return []
    source_week = (week - boundary) % cycle["length_weeks"] + 1
    overrides = _cycle_occurrence_overrides(db, program.id, revisions=revisions)[
        cycle.get("baked_override_count", 0) :
    ]
    plans = []
    originals: Iterable[dict]
    if source_index is not None:
        indexed = source_index.get(id(source))
        if indexed is None:
            indexed = {}
            for original in source:
                indexed.setdefault(original["week_number"], []).append(original)
            source_index[id(source)] = indexed
        originals = indexed.get(source_week, [])
    else:
        originals = (original for original in source if original["week_number"] == source_week)
    for original in originals:
        result = deepcopy(original)
        result["source_cycle_week"] = source_week
        result["cycle_iteration"] = (week - boundary) // cycle["length_weeks"] + 1
        result["scheduled_date"] = (
            date.fromisoformat(original["scheduled_date"]) + timedelta(weeks=week - source_week)
        ).isoformat()
        effective_date = (
            scheduled_dates[result["day_number"]].isoformat()
            if scheduled_dates and result["day_number"] in scheduled_dates
            else result["scheduled_date"]
        )
        for override in overrides:
            if (
                "week_type" in override
                or not _override_matches(override, week, source_week, boundary)
                or result["day_number"] != override["day_number"]
                or effective_date < override.get("not_before_date", "")
            ):
                continue
            for item in result["exercises"]:
                if (
                    item.get("source_template_exercise_id")
                    != override["source_template_exercise_id"]
                ):
                    continue
                item.update(override["exercise"])
                item["sets"] = _cycle_plan_sets(item["prescription"])
        plans.append(result)
    return plans


def _cycle_type_for_date(
    cycle: dict, overrides: list[dict], week: int, source_week: int, boundary: int, scheduled: date
) -> str | None:
    types = cycle.get("week_types")
    result = types[source_week - 1] if types is not None else None
    for override in overrides[cycle.get("baked_override_count", 0) :]:
        if (
            "week_type" in override
            and _override_matches(override, week, source_week, boundary)
            and scheduled.isoformat() >= override.get("not_before_date", "")
        ):
            result = override["week_type"]
    return result


def workout_cycle_week_type(
    db: Session, workout: UserWorkout, revisions: list[ProgramRevision]
) -> tuple[str | None, bool]:
    """Resolve the type from the workout's saved plan revision; false means unknown."""
    if workout.source_cycle_week is None:
        return None, workout.plan_revision_number is None
    if (
        workout.user_program is None
        or workout.user_program_id is None
        or workout.week_number is None
    ):
        return None, False
    number = workout.plan_revision_number
    if number is None or not any(item.revision_number == number for item in revisions):
        return None, False
    available = [item for item in revisions if item.revision_number <= number]
    try:
        config = _cycle_plan_at(db, workout.user_program, workout.week_number, revisions=available)
        if config is None:
            return None, False
        cycle, _source, boundary = config
        length = cycle["length_weeks"]
        if (
            cycle.get("schema_version") != 1
            or type(length) is not int
            or length < 1
            or type(cycle.get("repeat")) is not bool
            or workout.week_number < boundary
            or (not cycle["repeat"] and workout.week_number - boundary >= length)
            or workout.source_cycle_week != (workout.week_number - boundary) % length + 1
            or workout.cycle_iteration != (workout.week_number - boundary) // length + 1
        ):
            return None, False
        types = cycle.get("week_types")
        if types is not None and (
            not isinstance(types, list)
            or len(types) != length
            or any(item is not None and item not in {"light", "medium", "heavy"} for item in types)
        ):
            return None, False
        result = _cycle_type_for_date(
            cycle,
            _cycle_occurrence_overrides(db, workout.user_program_id, revisions=available),
            workout.week_number,
            workout.source_cycle_week,
            boundary,
            workout.scheduled_date,
        )
        if result is not None and result not in {"light", "medium", "heavy"}:
            return None, False
        return result, True
    except AttributeError, KeyError, OverflowError, TypeError, ValueError, ZeroDivisionError:
        return None, False


def cycle_workout_count(
    db: Session,
    program: UserProgram,
    *,
    start: date | None = None,
    end: date | None = None,
    missing_only: bool = False,
) -> int:
    """Count the logical schedule without creating future workouts or iterating over N."""
    configurations = _cycle_configurations(db, program)
    boundaries = sorted(
        {1, program.duration_weeks + 1}
        | {
            item["effective_from_week"]
            for item in configurations
            if item["effective_from_week"] <= program.duration_weeks
        }
    )
    total = 0
    for left, right in pairwise(boundaries):
        resolved = _cycle_plan_at(db, program, left)
        if resolved is None:
            if not missing_only:
                total += sum(
                    left <= _required_plan_number(row.week_number) < right
                    and (start is None or row.scheduled_date >= start)
                    and (end is None or row.scheduled_date <= end)
                    for row in program.workouts
                )
            continue
        cycle, source, boundary = resolved
        length = cycle["length_weeks"]
        for plan in source:
            offset = (
                date.fromisoformat(plan["scheduled_date"])
                - program.start_date
                - timedelta(weeks=plan["week_number"] - 1)
            )
            first = (
                max(left, -((program.start_date + offset - start).days // 7) + 1) if start else left
            )
            last = (
                min(right - 1, (end - program.start_date - offset).days // 7 + 1)
                if end
                else right - 1
            )
            if not cycle["repeat"]:
                last = min(last, boundary + length - 1)
            first += (boundary + plan["week_number"] - 1 - first) % length
            if first > last:
                continue
            total += (last - first) // length + 1
            if missing_only:
                total -= sum(
                    first <= _required_plan_number(row.week_number) <= last
                    and (_required_plan_number(row.week_number) - first) % length == 0
                    and row.day_number == plan["day_number"]
                    for row in program.workouts
                )
    return total


def _cycle_plan_sets(plan: dict) -> list[dict]:
    return [
        {
            "set_number": index,
            "set_kind": "working",
            "planned_role": segment["role"],
            "planned_position": segment["position"],
            "planned_group_id": segment.get("group_id"),
            "planned_group_kind": next(
                (
                    group["kind"]
                    for group in plan.get("groups", [])
                    if group["group_id"] == segment.get("group_id")
                ),
                None,
            ),
            "planned_round": segment.get("round_number"),
        }
        for index, segment in enumerate(plan["segments"], 1)
    ]


def _write_cycle_exercises(
    db: Session, workout: UserWorkout, plan: dict, *, target_slot: int | None = None
) -> None:
    if workout.user_program is None:
        raise ProgramError("Для тренировки нет данных плана")
    if (
        workout.status != "planned"
        or workout.started_at is not None
        or _workout_has_recorded_data(workout)
    ):
        raise ProgramError("Нельзя заменить начатую тренировку или записанные результаты")
    by_slot = {
        ("template", item.source_template_exercise_id)
        if item.source_template_exercise_id is not None
        else ("manual", item.sort_order): item
        for item in workout.exercises
    }
    if len(by_slot) != len(workout.exercises):
        raise ProgramError("Позиции упражнений в тренировке неоднозначны")
    retained = set()
    for source in plan["exercises"]:
        if target_slot is not None and source["source_template_exercise_id"] != target_slot:
            continue
        slot = (
            ("template", source["source_template_exercise_id"])
            if source["source_template_exercise_id"] is not None
            else ("manual", source["sort_order"])
        )
        if slot in retained:
            raise ProgramError("Позиции упражнений в плане неоднозначны")
        retained.add(slot)
        exercise = by_slot.get(slot)
        values = {key: value for key, value in source.items() if key != "sets"}
        changed_exercise = False
        if exercise is None:
            exercise = UserWorkoutExercise(workout=workout, **values)
            db.add(exercise)
        else:
            changed_exercise = any(getattr(exercise, key) != value for key, value in values.items())
            for key, value in values.items():
                setattr(exercise, key, value)
        old_sets = {item.set_number: item for item in exercise.sets}
        for source_set in source["sets"]:
            values = {key: value for key, value in source_set.items() if key != "is_completed"}
            item = old_sets.pop(source_set["set_number"], None)
            if item is None:
                db.add(UserWorkoutSet(workout_exercise=exercise, is_completed=False, **values))
            else:
                changed = changed_exercise or any(
                    getattr(item, key) != value for key, value in values.items()
                )
                for key, value in values.items():
                    setattr(item, key, value)
                if changed:
                    item.version += 1
                    item.plan_version = item.version
        for item in old_sets.values():
            db.delete(item)
    for slot, exercise in by_slot.items():
        if target_slot is None and slot not in retained:
            db.delete(exercise)
    workout.plan_materialized = True
    workout.plan_revision_number = workout.user_program.current_revision_number
    workout.source_cycle_week = plan["source_cycle_week"]
    workout.cycle_iteration = plan["cycle_iteration"]
    db.flush()
    for exercise in workout.exercises:
        if inspect(exercise).persistent:
            db.expire(exercise, ["sets", "exercise"])
    db.expire(workout, ["exercises"])


def hydrate_cycle_workout(db: Session, workout: UserWorkout) -> bool:
    if workout.source_cycle_week is None or workout.status != "planned":
        return False
    program = (
        db.query(UserProgram)
        .filter_by(id=workout.user_program_id)
        .with_for_update()
        .populate_existing()
        .one()
    )
    db.refresh(workout)
    if workout.status != "planned" or _workout_has_recorded_data(workout):
        return False
    if workout.week_number is None or workout.day_number is None:
        raise ProgramError("Для тренировки нет данных плана")
    if (
        workout.plan_materialized is not False
        and workout.plan_revision_number == program.current_revision_number
    ):
        return False
    revisions = (
        db.query(ProgramRevision)
        .filter_by(user_program_id=program.id)
        .order_by(ProgramRevision.revision_number)
        .all()
    )
    plan = next(
        (
            item
            for item in _cycle_workout_plans(
                db,
                program,
                workout.week_number,
                revisions=revisions,
                scheduled_dates={workout.day_number: workout.scheduled_date},
            )
            if item["day_number"] == workout.day_number
        ),
        None,
    )
    if plan is None:
        raise ProgramError("Не найден исходный план тренировки")
    if workout.plan_materialized is not False and workout.plan_revision_number is not None:
        previous_revisions = [
            revision
            for revision in revisions
            if revision.revision_number <= workout.plan_revision_number
        ]
        if any(revision.revision_number == workout.plan_revision_number for revision in revisions):
            previous = next(
                (
                    item
                    for item in _cycle_workout_plans(
                        db,
                        program,
                        workout.week_number,
                        revisions=previous_revisions,
                        scheduled_dates={workout.day_number: workout.scheduled_date},
                    )
                    if item["day_number"] == workout.day_number
                ),
                None,
            )
            if previous is not None:
                old = {item["source_template_exercise_id"]: item for item in previous["exercises"]}
                new = {item["source_template_exercise_id"]: item for item in plan["exercises"]}
                if (
                    len(old) == len(previous["exercises"])
                    and len(new) == len(plan["exercises"])
                    and old.keys() == new.keys()
                    and (None not in new or old[None] == new[None])
                ):
                    for slot in new:
                        if slot is not None and old[slot] != new[slot]:
                            _write_cycle_exercises(db, workout, plan, target_slot=slot)
                    workout.source_cycle_week = plan["source_cycle_week"]
                    workout.cycle_iteration = plan["cycle_iteration"]
                    workout.plan_revision_number = program.current_revision_number
                    db.flush()
                    return True
    _write_cycle_exercises(db, workout, plan)
    return True


def materialize_cycle_schedule(
    db: Session, program: UserProgram, start: date, end: date, *, with_sets: bool = False
) -> int:
    if (end - start).days > 92:
        raise ProgramError("Диапазон расписания не может быть больше 93 дней")
    program = (
        db.query(UserProgram).filter_by(id=program.id).with_for_update().populate_existing().one()
    )
    if _cycle_plan_at(db, program, program.duration_weeks) is None:
        return 0
    first = max(1, (start - program.start_date).days // 7 + 1)
    last = min(program.duration_weeks, (end - program.start_date).days // 7 + 1)
    existing = {
        (row.week_number, row.day_number): row
        for row in db.query(UserWorkout).filter(
            UserWorkout.user_program_id == program.id, UserWorkout.week_number.between(first, last)
        )
    }
    workout: UserWorkout | None
    created = 0
    hydrated_sets = 0
    for week in range(first, last + 1):
        for plan in _cycle_workout_plans(db, program, week):
            key = (week, plan["day_number"])
            scheduled = date.fromisoformat(plan["scheduled_date"])
            newly_created = key not in existing and start <= scheduled <= end
            if newly_created:
                workout = UserWorkout(
                    user_program=program,
                    week_number=week,
                    day_number=plan["day_number"],
                    scheduled_date=scheduled,
                    title=plan["title"],
                    status="planned",
                    plan_materialized=False,
                    source_cycle_week=plan["source_cycle_week"],
                    cycle_iteration=plan["cycle_iteration"],
                    plan_revision_number=program.current_revision_number,
                )
                db.add(workout)
                existing[key] = workout
                created += 1
            workout = existing.get(key)
            if (
                with_sets
                and workout is not None
                and workout.plan_materialized is False
                and start <= workout.scheduled_date <= end
                and hydrated_sets + sum(len(item["sets"]) for item in plan["exercises"])
                <= MAX_GENERATED_SETS
            ):
                _write_cycle_exercises(db, workout, plan)
                hydrated_sets += sum(len(item["sets"]) for item in plan["exercises"])
                if not newly_created:
                    created += 1
    db.flush()
    return created


def materialize_next_cycle_window(
    db: Session, program: UserProgram, *, through_date: date | None = None
) -> int:
    if _cycle_plan_at(db, program, program.duration_weeks) is None:
        return 0
    if through_date is None:
        rows = db.query(UserWorkout).filter_by(user_program_id=program.id).all()
        if any(row.status not in {"completed", "skipped", "cancelled"} for row in rows):
            return 0
        existing = {(row.week_number, row.day_number) for row in rows}
        first = next(
            (
                week
                for week in range(1, program.duration_weeks + 1)
                if any(
                    (week, item["day_number"]) not in existing
                    for item in _cycle_workout_plans(db, program, week)
                )
            ),
            program.duration_weeks + 1,
        )
        if first > program.duration_weeks:
            return 0
        through_date = program.start_date + timedelta(weeks=first - 1)
    horizon = min(27, (date.max - through_date).days)
    return materialize_cycle_schedule(
        db, program, through_date, through_date + timedelta(days=horizon), with_sets=True
    )


def materialize_cycle_read_window(
    db: Session, program_ids: list[int], start: date, end: date | None = None
) -> int:
    if not program_ids:
        return 0
    _release_cycle_read_transaction(db)
    # Read projections own their transaction; never flush or commit the caller's work.
    with Session(bind=db.get_bind().engine, autoflush=False) as projection:
        programs = (
            projection.query(UserProgram)
            .filter(
                UserProgram.id.in_(program_ids),
                UserProgram.is_active.is_(True),
                UserProgram.status.in_({"active", "scheduled"}),
            )
            .order_by(UserProgram.id)
            .all()
        )
        changed = 0
        for program in programs:
            changed += (
                materialize_next_cycle_window(projection, program, through_date=start)
                if end is None
                else materialize_cycle_schedule(projection, program, start, end)
            )
        projection.commit()
        return changed


def _release_cycle_read_transaction(db: Session) -> None:
    # A clean GET must release its connection before opening the independent projection.
    transaction = db.get_transaction()
    if (
        db.info.get("releasable_cycle_read")
        and transaction is not None
        and transaction.origin is SessionTransactionOrigin.AUTOBEGIN
        and not db.in_nested_transaction()
        and not (db.new or db.dirty or db.deleted)
        and db.get_bind().dialect.name == "postgresql"
        and db.connection()
        .exec_driver_sql(
            "SELECT pg_current_xact_id_if_assigned() IS NULL AND NOT EXISTS ("
            "SELECT 1 FROM pg_locks WHERE pid = pg_backend_pid() AND granted AND ("
            "locktype = 'advisory' OR (locktype = 'relation' AND mode <> 'AccessShareLock')))"
        )
        .scalar()
    ):
        db.rollback()


def hydrate_cycle_read_workout(db: Session, workout: UserWorkout) -> bool:
    if workout.source_cycle_week is None or workout.status != "planned":
        return False
    workout_id = workout.id
    loaded = [
        (exercise, list(inspect(exercise).dict.get("sets", [])))
        for exercise in inspect(workout).dict.get("exercises", [])
    ]
    _release_cycle_read_transaction(db)
    with Session(bind=db.get_bind().engine, autoflush=False) as projection:
        current = projection.get(UserWorkout, workout_id)
        changed = current is not None and hydrate_cycle_workout(projection, current)
        projection.commit()
    if changed:
        # Relationship expiry alone leaves held child identities stale; retain caller edits.
        for exercise, sets in loaded:
            for item in [exercise, *sets]:
                state = inspect(item)
                if not state.persistent:
                    continue
                clean = [
                    attr.key
                    for attr in state.mapper.column_attrs
                    if attr.key != "id" and not state.attrs[attr.key].history.has_changes()
                ]
                if clean:
                    db.expire(item, clean)
            clean_relationships = [
                key
                for key in ("sets", "exercise")
                if not inspect(exercise).attrs[key].history.has_changes()
            ]
            if inspect(exercise).persistent and clean_relationships:
                db.expire(exercise, clean_relationships)
        clean_parent = [
            key
            for key in (
                "exercises",
                "plan_materialized",
                "source_cycle_week",
                "cycle_iteration",
                "plan_revision_number",
            )
            if not inspect(workout).attrs[key].history.has_changes()
        ]
        if clean_parent:
            db.expire(workout, clean_parent)
    return changed


def revise_program_cycle(
    db: Session, actor: User, program_id: int, payload: ProgramCycleRevisionRequest
) -> int:
    program, _ = get_program_for_actor(db, actor, program_id, lock=True)
    _ensure_program_mutable(program)
    _ensure_expected_revision(program, payload.expected_revision_number)
    owner = db.get(User, program.user_id)
    boundary = payload.effective_from_week
    if boundary > program.duration_weeks + 1 or program.start_date + timedelta(
        weeks=boundary - 1
    ) < today_for_user(owner):
        raise ProgramError("Выберите будущую неделю в пределах программы для изменения цикла")
    previous = _cycle_plan_at(db, program, min(boundary, program.duration_weeks))
    if previous is None:
        raise ProgramError("У назначения нет сохранённого цикла")
    cycle, source, _old_boundary = previous
    duration = payload.duration_weeks or program.duration_weeks
    if duration < boundary - 1 or duration > (date.max - program.start_date).days // 7:
        raise ProgramError("Некорректная длительность программы")
    affected = (
        db.query(UserWorkout)
        .filter(UserWorkout.user_program_id == program.id, UserWorkout.week_number >= boundary)
        .all()
    )
    if any(
        row.status in {"in_progress", "completed", "skipped"} or _workout_has_recorded_data(row)
        for row in affected
    ):
        raise ProgramError(
            "Изменение цикла не может затрагивать выполненные или начатые тренировки"
        )
    config: dict | None = None
    if (
        payload.source_week_order is not None
        or payload.repeat is not None
        or "week_types" in payload.model_fields_set
    ):
        order = payload.source_week_order or list(range(1, cycle["length_weeks"] + 1))
        if any(week > cycle["length_weeks"] for week in order):
            raise ProgramError("Некорректное соответствие исходных недель")
        by_week = {
            week: [item for item in source if item["week_number"] == week] for week in set(order)
        }
        if (
            sum(
                sum(
                    len(exercise["sets"])
                    for item in by_week[week]
                    for exercise in item["exercises"]
                )
                for week in order
            )
            > MAX_GENERATED_SETS
        ):
            raise ProgramError("Размер плана превышает допустимый объём одной операции")
        new_source = []
        for index, old_week in enumerate(order, 1):
            for original in by_week[old_week]:
                item = deepcopy(original)
                item["week_number"] = index
                item["scheduled_date"] = (
                    date.fromisoformat(original["scheduled_date"])
                    + timedelta(weeks=index - old_week)
                ).isoformat()
                new_source.append(item)
        new_cycle = {
            **cycle,
            "length_weeks": len(order),
            "repeat": payload.repeat if payload.repeat is not None else cycle["repeat"],
            "week_types": payload.week_types
            if "week_types" in payload.model_fields_set
            else (
                [cycle["week_types"][week - 1] for week in order]
                if cycle.get("week_types")
                else None
            ),
        }
        if new_cycle["week_types"] is not None and len(new_cycle["week_types"]) != len(order):
            raise ProgramError("Укажите тип для каждой недели нового цикла")
        if not new_cycle["repeat"] and duration - boundary + 1 > len(order):
            raise ProgramError("Длительность программы превышает длину цикла без повторения")
        config = {
            "effective_from_week": boundary,
            "week_cycle": new_cycle,
            "logical_cycle": new_source,
        }
    elif not cycle["repeat"] and duration - _old_boundary + 1 > cycle["length_weeks"]:
        raise ProgramError("Длительность программы превышает длину цикла без повторения")
    cancelled_by_plan = {
        workout_id
        for event in db.query(ProgramRevision).filter_by(user_program_id=program.id)
        for key in ("duration_cancelled_workout_ids", "structure_cancelled_workout_ids")
        for workout_id in event.changed_fields.get(key, [])
    }
    program.duration_weeks = duration
    revision = record_program_revision(
        db,
        program,
        actor=actor,
        change_kind="plan_updated",
        reason=payload.reason,
        changed_fields={
            "operation": "cycle_revised",
            "duration_cancelled_workout_ids": [
                row.id
                for row in affected
                if _required_plan_number(row.week_number) > duration and row.status == "planned"
            ],
            "duration_weeks": duration,
            **({"cycle_configuration": config} if config else {}),
        },
    )
    db.flush()
    current_revisions = (
        db.query(ProgramRevision)
        .filter_by(user_program_id=program.id)
        .order_by(ProgramRevision.revision_number)
        .all()
    )
    indexed_sources: dict[int, dict[int, list[dict]]] = {}
    revised_sets = 0
    for workout in affected:
        if workout.week_number is None or workout.day_number is None:
            raise ProgramError("Для тренировки нет данных плана")
        if workout.week_number > duration:
            workout.status = "cancelled"
            cancel_workout_reminder(db, workout.id)
        elif workout.status == "planned" or (
            workout.status == "cancelled" and workout.id in cancelled_by_plan
        ):
            plan = next(
                (
                    item
                    for item in _cycle_workout_plans(
                        db,
                        program,
                        workout.week_number,
                        revisions=current_revisions,
                        source_index=indexed_sources,
                        scheduled_dates={workout.day_number: workout.scheduled_date},
                    )
                    if item["day_number"] == workout.day_number
                ),
                None,
            )
            if plan is None:
                continue
            if config is None and workout.status == "planned":
                if (workout.source_cycle_week, workout.cycle_iteration) == (
                    plan["source_cycle_week"],
                    plan["cycle_iteration"],
                ):
                    workout.plan_revision_number = revision.revision_number
                continue
            workout.status = "planned"
            if workout.plan_materialized is not False:
                count = sum(len(item["sets"]) for item in plan["exercises"])
                if revised_sets + count > MAX_GENERATED_SETS:
                    continue
                _write_cycle_exercises(db, workout, plan)
                revised_sets += count
            workout.source_cycle_week = plan["source_cycle_week"]
            workout.cycle_iteration = plan["cycle_iteration"]
            workout.plan_revision_number = revision.revision_number
    revision.snapshot = _build_program_snapshot(db, program)
    record_audit_event(
        db,
        actor_user_id=actor.id,
        target_user_id=program.user_id,
        action="program.cycle_revised",
        resource_type="user_program",
        resource_id=program.id,
        details={"revision_number": revision.revision_number, "effective_from_week": boundary},
    )
    db.commit()
    return revision.revision_number


def enable_program_cycle(
    db: Session, actor: User, program_id: int, payload: ProgramCycleEnableRequest, *, preview: bool
) -> dict:
    program, _ = get_program_for_actor(db, actor, program_id, lock=not preview)
    _ensure_program_mutable(program)
    _ensure_expected_revision(program, payload.expected_revision_number)
    boundary, duration = payload.effective_from_week, payload.duration_weeks
    today = today_for_user(db.get(User, program.user_id))
    if (
        boundary > program.duration_weeks
        or duration < boundary
        or duration > (date.max - program.start_date).days // 7
        or program.start_date + timedelta(weeks=boundary - 1) < today
    ):
        raise ProgramError("Выберите будущую неделю и допустимую длительность программы")
    revisions = (
        db.query(ProgramRevision)
        .filter_by(user_program_id=program.id)
        .order_by(ProgramRevision.revision_number)
        .all()
    )
    current = _cycle_plan_at(db, program, boundary, revisions=revisions)
    if current is not None and not current[0].get("periodization_disabled"):
        raise ProgramError("Периодизация уже включена")
    if any(
        config["effective_from_week"] > boundary
        and not config["week_cycle"].get("periodization_disabled")
        for config in _cycle_configurations(db, program, revisions=revisions)
    ):
        raise ProgramError("Для будущих недель уже настроена периодизация")
    cycle = payload.week_cycle.model_dump()
    cycle["baked_override_count"] = len(
        _cycle_occurrence_overrides(db, program.id, revisions=revisions)
    )
    length = cycle["length_weeks"]
    if length > MAX_GENERATED_SETS or (not cycle["repeat"] and duration - boundary + 1 > length):
        raise ProgramError("Длительность программы превышает длину цикла без повторения")
    snapshot = _build_program_snapshot(db, program)
    legacy: dict[int, list[dict]] = {}
    indexed_sources: dict[int, dict[int, list[dict]]] = {}
    for workout in snapshot["workouts"]:
        legacy.setdefault(workout["week_number"], []).append(workout)

    def originals(week: int) -> list[dict]:
        if current is not None:
            return _cycle_workout_plans(
                db, program, week, revisions=revisions, source_index=indexed_sources
            )
        return legacy.get(week, [])

    fallback = originals(boundary)
    if not fallback:
        raise ProgramError("В выбранной неделе нет исходных тренировок")
    source = []
    set_count = 0
    for index in range(1, length + 1):
        source_week = boundary + index - 1
        rows = originals(source_week) if source_week <= program.duration_weeks else []
        if not rows:
            rows, source_week = fallback, boundary
        for source_row in rows:
            slots = [item.get("source_template_exercise_id") for item in source_row["exercises"]]
            if not slots or None in slots or len(set(slots)) != len(slots):
                raise ProgramError(
                    "Исходный план содержит позиции без устойчивой связи с программой"
                )
            item = deepcopy(source_row)
            item["week_number"] = index
            item["scheduled_date"] = (
                date.fromisoformat(item["scheduled_date"]) + timedelta(weeks=index - source_week)
            ).isoformat()
            for exercise in item["exercises"]:
                for workout_set in exercise["sets"]:
                    workout_set["is_completed"] = False
                set_count += len(exercise["sets"])
            if set_count > MAX_GENERATED_SETS:
                raise ProgramError("Размер плана превышает допустимый объём одной операции")
            source.append(item)

    source_by_week: dict[int, list[dict]] = {}
    for item in source:
        source_by_week.setdefault(item["week_number"], []).append(item)

    def plans(week: int) -> list[dict]:
        if week > duration or (not cycle["repeat"] and week - boundary >= length):
            return []
        source_week = (week - boundary) % length + 1
        result = []
        for original in source_by_week.get(source_week, []):
            item = deepcopy(original)
            item["scheduled_date"] = (
                date.fromisoformat(item["scheduled_date"]) + timedelta(weeks=week - source_week)
            ).isoformat()
            item["source_cycle_week"] = source_week
            item["cycle_iteration"] = (week - boundary) // length + 1
            result.append(item)
        return result

    existing = (
        db.query(UserWorkout)
        .options(selectinload(UserWorkout.exercises).selectinload(UserWorkoutExercise.sets))
        .filter(UserWorkout.user_program_id == program.id, UserWorkout.week_number >= boundary)
        .all()
    )
    by_key = {(row.week_number, row.day_number): row for row in existing}
    if preview:
        total = max(program.duration_weeks, duration) - boundary + 1
        weeks = []
        for week in range(
            boundary + payload.offset, min(boundary + payload.offset + 50, boundary + total)
        ):
            workout_plans = plans(week)
            day_numbers = {plan["day_number"] for plan in workout_plans}
            workouts = []
            for plan in workout_plans:
                row = by_key.get((week, plan["day_number"]))
                scheduled = (
                    row.scheduled_date if row else date.fromisoformat(plan["scheduled_date"])
                )
                workouts.append(
                    {
                        "id": row.id if row else None,
                        "day_number": plan["day_number"],
                        "title": row.title if row else plan["title"],
                        "scheduled_date": scheduled.isoformat(),
                        "status": row.status if row else "planned",
                        "changeable": scheduled >= today
                        and (
                            row is None
                            or (row.status == "planned" and not _workout_has_recorded_data(row))
                        ),
                    }
                )
            for row in existing:
                if row.week_number == week and row.day_number not in day_numbers:
                    workouts.append(
                        {
                            "id": row.id,
                            "day_number": row.day_number,
                            "title": row.title,
                            "scheduled_date": row.scheduled_date.isoformat(),
                            "status": row.status,
                            "changeable": row.scheduled_date >= today
                            and row.status == "planned"
                            and not _workout_has_recorded_data(row),
                            "removed": True,
                        }
                    )
            source_week = (week - boundary) % length + 1
            weeks.append(
                {
                    "week_number": week,
                    "source_cycle_week": source_week,
                    "cycle_iteration": (week - boundary) // length + 1,
                    "workouts": workouts,
                }
            )
        return {"weeks": weeks, "total_weeks": total, "offset": payload.offset}
    revised_sets = sum(
        len(item["sets"])
        for row in existing
        if _required_plan_number(row.week_number) <= duration
        and row.status == "planned"
        and row.scheduled_date >= today
        and not _workout_has_recorded_data(row)
        for plan in plans(_required_plan_number(row.week_number))
        if plan["day_number"] == row.day_number
        for item in plan["exercises"]
    )
    if revised_sets > MAX_GENERATED_SETS:
        raise ProgramError("Размер плана превышает допустимый объём одной операции")
    program.duration_weeks = duration
    revision = record_program_revision(
        db,
        program,
        actor=actor,
        change_kind="plan_updated",
        changed_fields={
            "operation": "cycle_enabled",
            "cycle_configuration": {
                "effective_from_week": boundary,
                "week_cycle": cycle,
                "logical_cycle": source,
            },
        },
    )
    for row in existing:
        if row.scheduled_date < today or row.status != "planned" or _workout_has_recorded_data(row):
            continue
        if row.week_number is None:
            raise ProgramError("Для тренировки нет данных плана")
        target_plan: dict | None = next(
            (item for item in plans(row.week_number) if item["day_number"] == row.day_number), None
        )
        if target_plan is None:
            row.status = "cancelled"
            cancel_workout_reminder(db, row.id)
        elif row.plan_materialized is False:
            row.source_cycle_week = target_plan["source_cycle_week"]
            row.cycle_iteration = target_plan["cycle_iteration"]
            row.plan_revision_number = revision.revision_number
        else:
            _write_cycle_exercises(db, row, target_plan)
    db.flush()
    first_date = program.start_date + timedelta(weeks=boundary - 1)
    materialize_cycle_schedule(
        db, program, first_date, first_date + timedelta(days=min(27, (date.max - first_date).days))
    )
    revision.snapshot = _build_program_snapshot(db, program)
    record_audit_event(
        db,
        actor_user_id=actor.id,
        target_user_id=program.user_id,
        action="program.cycle_enabled",
        resource_type="user_program",
        resource_id=program.id,
        details={"revision_number": revision.revision_number, "effective_from_week": boundary},
    )
    db.commit()
    return {"current_revision_number": revision.revision_number}


def preview_cycle_duration(
    db: Session, actor: User, program_id: int, payload: ProgramCycleDurationPreviewRequest
) -> dict:
    program, _ = get_program_for_actor(db, actor, program_id)
    _ensure_program_mutable(program)
    _ensure_expected_revision(program, payload.expected_revision_number)
    boundary, duration = payload.effective_from_week, payload.duration_weeks
    if (
        boundary > program.duration_weeks + 1
        or duration < boundary - 1
        or duration > (date.max - program.start_date).days // 7
        or program.start_date + timedelta(weeks=boundary - 1)
        < today_for_user(db.get(User, program.user_id))
    ):
        raise ProgramError("Выберите будущую неделю и допустимую длительность программы")
    revisions = (
        db.query(ProgramRevision)
        .filter_by(user_program_id=program.id)
        .order_by(ProgramRevision.revision_number)
        .all()
    )
    config = _cycle_plan_at(db, program, min(boundary, program.duration_weeks), revisions=revisions)
    if config is None:
        raise ProgramError("У назначения нет сохранённого цикла")
    cycle, _source, phase = config
    if not cycle["repeat"] and duration - phase + 1 > cycle["length_weeks"]:
        raise ProgramError("Длительность программы превышает длину цикла без повторения")
    total = max(0, max(program.duration_weeks, duration) - boundary + 1)
    first = boundary + payload.offset
    last = min(first + 50, boundary + total)
    existing = {
        (row.week_number, row.day_number): row
        for row in db.query(UserWorkout)
        .options(selectinload(UserWorkout.exercises).selectinload(UserWorkoutExercise.sets))
        .filter(UserWorkout.user_program_id == program.id, UserWorkout.week_number >= boundary)
    }
    weeks = []
    today = today_for_user(db.get(User, program.user_id))
    indexed_sources: dict[int, dict[int, list[dict]]] = {}
    for week in range(first, last):
        workouts = []
        for plan in _cycle_workout_plans(
            db, program, week, revisions=revisions, source_index=indexed_sources
        ):
            row = existing.get((week, plan["day_number"]))
            scheduled = row.scheduled_date if row else date.fromisoformat(plan["scheduled_date"])
            workouts.append(
                {
                    "id": row.id if row else None,
                    "day_number": plan["day_number"],
                    "title": row.title if row else plan["title"],
                    "scheduled_date": scheduled.isoformat(),
                    "status": row.status if row else "planned",
                    "changeable": scheduled >= today
                    and (
                        row is None
                        or (row.status == "planned" and not _workout_has_recorded_data(row))
                    ),
                }
            )
        weeks.append(
            {
                "week_number": week,
                "change": "added"
                if week > program.duration_weeks
                else "removed"
                if week > duration
                else "unchanged",
                "workouts": workouts,
            }
        )
    return {"weeks": weeks, "total_weeks": total, "offset": payload.offset}


def disable_program_cycle(
    db: Session,
    actor: User,
    program_id: int,
    payload: ProgramCycleDisableRequest,
    *,
    preview: bool,
) -> dict:
    program, _ = get_program_for_actor(db, actor, program_id, lock=not preview)
    _ensure_program_mutable(program)
    _ensure_expected_revision(program, payload.expected_revision_number)
    boundary = payload.effective_from_week
    today = today_for_user(db.get(User, program.user_id))
    if (
        boundary > program.duration_weeks
        or program.start_date + timedelta(weeks=boundary - 1) < today
    ):
        raise ProgramError("Выберите будущую неделю в пределах программы")
    revisions = (
        db.query(ProgramRevision)
        .filter_by(user_program_id=program.id)
        .order_by(ProgramRevision.revision_number)
        .all()
    )
    config = _cycle_plan_at(db, program, boundary, revisions=revisions)
    if config is None or config[0].get("periodization_disabled"):
        raise ProgramError("У назначения нет включённой периодизации")
    total = program.duration_weeks - boundary + 1
    if total > MAX_GENERATED_SETS:
        raise ProgramError("Размер плана превышает допустимый объём одной операции")
    existing = (
        db.query(UserWorkout)
        .options(selectinload(UserWorkout.exercises).selectinload(UserWorkoutExercise.sets))
        .filter(UserWorkout.user_program_id == program.id, UserWorkout.week_number >= boundary)
        .all()
    )
    by_key = {(row.week_number, row.day_number): row for row in existing}
    indexed_sources: dict[int, dict[int, list[dict]]] = {}
    existing_by_week: dict[int, list[UserWorkout]] = {}
    dates_by_week: dict[int, dict[int, date]] = {}
    for row in existing:
        if row.week_number is None or row.day_number is None:
            raise ProgramError("Для тренировки нет данных плана")
        existing_by_week.setdefault(row.week_number, []).append(row)
        dates_by_week.setdefault(row.week_number, {})[row.day_number] = row.scheduled_date
    if preview:
        weeks = []
        for week in range(
            boundary + payload.offset,
            min(boundary + payload.offset + 50, program.duration_weeks + 1),
        ):
            workouts = []
            for plan in _cycle_workout_plans(
                db,
                program,
                week,
                revisions=revisions,
                source_index=indexed_sources,
                scheduled_dates=dates_by_week.get(week),
            ):
                row = by_key.get((week, plan["day_number"]))
                scheduled = (
                    row.scheduled_date if row else date.fromisoformat(plan["scheduled_date"])
                )
                workouts.append(
                    {
                        "id": row.id if row else None,
                        "day_number": plan["day_number"],
                        "title": row.title if row else plan["title"],
                        "scheduled_date": scheduled.isoformat(),
                        "status": row.status if row else "planned",
                        "changeable": scheduled >= today
                        and (
                            row is None
                            or (row.status == "planned" and not _workout_has_recorded_data(row))
                        ),
                    }
                )
            weeks.append({"week_number": week, "workouts": workouts})
        return {"weeks": weeks, "total_weeks": total, "offset": payload.offset}
    frozen = []
    plans_by_key = {}
    sets = 0
    snapshot_by_key = {
        (item["week_number"], item["day_number"]): item
        for item in _build_program_snapshot(db, program)["workouts"]
    }
    for week in range(boundary, program.duration_weeks + 1):
        week_plans = {
            plan["day_number"]: plan
            for plan in _cycle_workout_plans(
                db,
                program,
                week,
                revisions=revisions,
                source_index=indexed_sources,
                scheduled_dates=dates_by_week.get(week),
            )
        }
        for row in existing_by_week.get(week, []):
            if (
                row.scheduled_date >= today
                and row.status == "planned"
                and row.plan_materialized is not False
                and not _workout_has_recorded_data(row)
            ):
                week_plans[row.day_number] = snapshot_by_key[(week, row.day_number)]
        for plan in week_plans.values():
            sets += sum(len(exercise["sets"]) for exercise in plan["exercises"])
            if sets > MAX_GENERATED_SETS:
                raise ProgramError("Размер плана превышает допустимый объём одной операции")
            item = deepcopy(plan)
            item["week_number"] = week - boundary + 1
            item["scheduled_date"] = (
                date.fromisoformat(item["scheduled_date"]) - timedelta(weeks=boundary - 1)
            ).isoformat()
            frozen.append(item)
            plans_by_key[(week, plan["day_number"])] = {
                **plan,
                "source_cycle_week": week - boundary + 1,
                "cycle_iteration": 1,
            }
    revision = record_program_revision(
        db,
        program,
        actor=actor,
        change_kind="plan_updated",
        changed_fields={
            "operation": "cycle_disabled",
            "cycle_configuration": {
                "effective_from_week": boundary,
                "week_cycle": {
                    "schema_version": 1,
                    "length_weeks": total,
                    "repeat": False,
                    "week_types": None,
                    "periodization_disabled": True,
                    "baked_override_count": len(
                        _cycle_occurrence_overrides(db, program.id, revisions=revisions)
                    ),
                },
                "logical_cycle": frozen,
            },
        },
    )
    for row in existing:
        if row.week_number is None or row.day_number is None:
            raise ProgramError("Для тренировки нет данных плана")
        target_plan = plans_by_key.get((row.week_number, row.day_number))
        if (
            target_plan is None
            or row.scheduled_date < today
            or row.status != "planned"
            or _workout_has_recorded_data(row)
        ):
            continue
        row.source_cycle_week = target_plan["source_cycle_week"]
        row.cycle_iteration = 1
        row.plan_revision_number = revision.revision_number
    revision.snapshot = _build_program_snapshot(db, program)
    record_audit_event(
        db,
        actor_user_id=actor.id,
        target_user_id=program.user_id,
        action="program.cycle_disabled",
        resource_type="user_program",
        resource_id=program.id,
        details={"revision_number": revision.revision_number, "effective_from_week": boundary},
    )
    db.commit()
    return {"current_revision_number": revision.revision_number}


def revise_program_week_type(
    db: Session,
    actor: User,
    program_id: int,
    payload: ProgramWeekTypeRevisionRequest,
    *,
    preview: bool,
) -> dict:
    program, _ = get_program_for_actor(db, actor, program_id, lock=not preview)
    _ensure_program_mutable(program)
    _ensure_expected_revision(program, payload.expected_revision_number)
    revisions = (
        db.query(ProgramRevision)
        .filter_by(user_program_id=program.id)
        .order_by(ProgramRevision.revision_number)
        .all()
    )
    today = today_for_user(db.get(User, program.user_id))
    scope: dict = {}
    if payload.occurrence_weeks is not None:
        weeks = sorted(set(payload.occurrence_weeks))
        if any(week > program.duration_weeks for week in weeks):
            raise ProgramError("Некорректный номер недели программы")
        scope = {"weeks": weeks}
        total = len(weeks)
        page = weeks[payload.offset : payload.offset + 50]
    else:
        first = payload.from_week
        if first is None or first > program.duration_weeks:
            raise ProgramError("Некорректный номер недели программы")
        resolved = _cycle_plan_at(db, program, first, revisions=revisions)
        if resolved is None:
            raise ProgramError("У назначения нет сохранённого цикла")
        cycle, _source, boundary = resolved
        source_week = payload.source_cycle_week
        if source_week is None or source_week > cycle["length_weeks"]:
            raise ProgramError("Некорректный номер исходной недели цикла")
        end = min(
            [program.duration_weeks]
            + [
                config["effective_from_week"] - 1
                for config in _cycle_configurations(db, program, revisions=revisions)
                if config["effective_from_week"] > first
            ]
        )
        if not cycle["repeat"]:
            end = min(end, boundary + cycle["length_weeks"] - 1)
        first += (boundary + source_week - 1 - first) % cycle["length_weeks"]
        total = max(0, (end - first) // cycle["length_weeks"] + 1)
        page = [
            first + index * cycle["length_weeks"]
            for index in range(payload.offset, min(payload.offset + 50, total))
        ]
        scope = {
            "from_week": payload.from_week,
            "to_week": end,
            "source_cycle_week": source_week,
            "source_cycle_boundary": boundary,
        }
    scope["not_before_date"] = today.isoformat()
    existing = (
        db.query(UserWorkout)
        .options(selectinload(UserWorkout.exercises).selectinload(UserWorkoutExercise.sets))
        .filter_by(user_program_id=program.id)
        .all()
    )
    by_key = {(row.week_number, row.day_number): row for row in existing}
    indexed_sources: dict[int, dict[int, list[dict]]] = {}
    dates_by_week: dict[int, dict[int, date]] = {}
    for row in existing:
        if row.week_number is None or row.day_number is None:
            raise ProgramError("Для тренировки нет данных плана")
        dates_by_week.setdefault(row.week_number, {})[row.day_number] = row.scheduled_date
    if preview:
        result = []
        overrides = _cycle_occurrence_overrides(db, program.id, revisions=revisions)
        for week in page:
            config = _cycle_plan_at(db, program, week, revisions=revisions)
            if config is None:
                raise ProgramError("У назначения нет сохранённого цикла")
            cycle, _source, boundary = config
            source_week = (week - boundary) % cycle["length_weeks"] + 1
            workouts = []
            for plan in _cycle_workout_plans(
                db,
                program,
                week,
                revisions=revisions,
                source_index=indexed_sources,
                scheduled_dates=dates_by_week.get(week),
            ):
                row = by_key.get((week, plan["day_number"]))
                scheduled = (
                    row.scheduled_date if row else date.fromisoformat(plan["scheduled_date"])
                )
                needs_refresh = bool(
                    row is not None
                    and row.plan_materialized is not False
                    and (
                        row.source_cycle_week != plan["source_cycle_week"]
                        or row.cycle_iteration != plan["cycle_iteration"]
                    )
                )
                changeable = scheduled >= today and (
                    row is None
                    or (
                        row.status == "planned"
                        and not _workout_has_recorded_data(row)
                        and not needs_refresh
                    )
                )
                current_type = (
                    workout_cycle_week_type(db, row, revisions)[0]
                    if row is not None and not changeable
                    else _cycle_type_for_date(
                        cycle, overrides, week, source_week, boundary, scheduled
                    )
                )
                workouts.append(
                    {
                        "id": row.id if row else None,
                        "title": row.title if row else plan["title"],
                        "scheduled_date": scheduled.isoformat(),
                        "status": row.status if row else "planned",
                        "changeable": changeable,
                        "needs_refresh": needs_refresh,
                        "week_type": current_type,
                        "day_number": plan["day_number"],
                        "exercises": [
                            {
                                key: exercise.get(key)
                                for key in (
                                    "source_template_exercise_id",
                                    "exercise_id",
                                    "prescribed_sets",
                                    "prescribed_reps",
                                    "prescribed_duration_minutes",
                                    "rest_seconds",
                                    "notes",
                                    "prescription",
                                    "metric_type",
                                )
                            }
                            for exercise in plan["exercises"]
                        ],
                    }
                )
            result.append(
                {
                    "week_number": week,
                    "source_cycle_week": source_week,
                    "cycle_iteration": (week - boundary) // cycle["length_weeks"] + 1,
                    "cycle_length": cycle["length_weeks"],
                    "repeat": cycle["repeat"],
                    "periodization_enabled": not cycle.get("periodization_disabled", False),
                    "workouts": workouts,
                }
            )
        return {"weeks": result, "total_weeks": total, "offset": payload.offset}

    candidates = []
    for row in existing:
        if row.week_number is None or row.day_number is None:
            raise ProgramError("Для тренировки нет данных плана")
        config = _cycle_plan_at(db, program, row.week_number, revisions=revisions)
        if config is None or row.scheduled_date < today:
            continue
        cycle, _source, boundary = config
        source_week = (row.week_number - boundary) % cycle["length_weeks"] + 1
        if (
            _override_matches(scope, row.week_number, source_week, boundary)
            and row.status == "planned"
            and not _workout_has_recorded_data(row)
        ):
            target_plan: dict | None = next(
                (
                    item
                    for item in _cycle_workout_plans(
                        db,
                        program,
                        row.week_number,
                        revisions=revisions,
                        source_index=indexed_sources,
                        scheduled_dates={row.day_number: row.scheduled_date},
                    )
                    if item["day_number"] == row.day_number
                ),
                None,
            )
            if target_plan is not None:
                if row.plan_materialized is not False and (
                    row.source_cycle_week != target_plan["source_cycle_week"]
                    or row.cycle_iteration != target_plan["cycle_iteration"]
                ):
                    raise ProgramError(
                        "Откройте тренировку и обновите её план перед изменением типа"
                    )
                candidates.append((row, target_plan))
    revision = record_program_revision(
        db,
        program,
        actor=actor,
        change_kind="plan_updated",
        changed_fields={"occurrence_override": {**scope, "week_type": payload.week_type}},
    )
    for row, plan in candidates:
        row.source_cycle_week = plan["source_cycle_week"]
        row.cycle_iteration = plan["cycle_iteration"]
        row.plan_revision_number = revision.revision_number
    revision.snapshot = _build_program_snapshot(db, program)
    record_audit_event(
        db,
        actor_user_id=actor.id,
        target_user_id=program.user_id,
        action="program.week_type_revised",
        resource_type="user_program",
        resource_id=program.id,
        details={"revision_number": revision.revision_number, "scope": scope},
    )
    db.commit()
    return {"current_revision_number": revision.revision_number}


def record_program_revision(
    db: Session,
    program: UserProgram,
    *,
    actor: User | None,
    change_kind: str,
    changed_fields: dict,
    reason: str | None = None,
) -> ProgramRevision:
    program.current_revision_number += 1
    db.flush()
    revision = ProgramRevision(
        user_program_id=program.id,
        revision_number=program.current_revision_number,
        changed_by_user_id=actor.id if actor else None,
        actor_role=_actor_role(program, actor),
        change_kind=change_kind,
        reason=reason.strip() if reason and reason.strip() else None,
        changed_fields=changed_fields,
        snapshot=_build_program_snapshot(db, program),
    )
    db.add(revision)
    db.flush()
    return revision


def list_program_revisions(
    db: Session,
    actor: User,
    program_id: int,
) -> list[ProgramRevision]:
    get_program_for_actor(db, actor, program_id)
    return (
        db.query(ProgramRevision)
        .filter(ProgramRevision.user_program_id == program_id)
        .order_by(ProgramRevision.revision_number.desc())
        .all()
    )


def list_training_blocks(db: Session, actor: User, program_id: int) -> list[dict]:
    get_program_for_actor(db, actor, program_id)
    return [_serialize_block(block) for block in _load_blocks(db, program_id)]


def _lifecycle_block_summary(
    block: TrainingBlock,
    workouts: list[UserWorkout],
) -> dict[str, object]:
    block_weeks = [
        _required_plan_number(workout.week_number)
        for workout in workouts
        if block.start_date <= workout.scheduled_date <= block.end_date
    ]
    return {
        "id": block.id,
        "title": block.title,
        "start_date": block.start_date,
        "end_date": block.end_date,
        "week_start": min(block_weeks) if block_weeks else None,
        "week_end": max(block_weeks) if block_weeks else None,
        "is_deload": block.is_deload,
        "status": block.status,
    }


def program_lifecycle_summary(db: Session, actor: User, program_id: int) -> dict[str, object]:
    program, _role = get_program_for_actor(db, actor, program_id)
    owner = db.query(User).filter(User.id == program.user_id).one()
    today = today_for_user(owner)
    workouts_query = (
        db.query(UserWorkout)
        .filter(UserWorkout.user_program_id == program.id)
        .order_by(UserWorkout.scheduled_date.asc(), UserWorkout.id.asc())
    )
    workouts = workouts_query.all()
    if (
        any(row.source_cycle_week is not None for row in workouts)
        and program.is_active
        and program.status in {"scheduled", "active"}
        and materialize_cycle_read_window(db, [program.id], today, today + timedelta(days=27))
    ):
        workouts = workouts_query.all()
    in_progress = next((workout for workout in workouts if workout.status == "in_progress"), None)
    planned = [workout for workout in workouts if workout.status == "planned"]
    next_workout = in_progress or next(
        (workout for workout in planned if workout.scheduled_date >= today),
        planned[0] if planned else None,
    )
    current_week = next_workout.week_number if next_workout else None
    blocks = _load_blocks(db, program.id)
    current_block = next((block for block in blocks if block.status == "active"), None)
    reference_date = next_workout.scheduled_date if next_workout else today
    if current_block is None:
        current_block = next(
            (
                block
                for block in blocks
                if block.status == "planned"
                and block.start_date <= reference_date <= block.end_date
            ),
            None,
        )
    if current_block is None:
        current_block = next(
            (block for block in blocks if block.status == "planned"),
            next((block for block in reversed(blocks) if block.status == "completed"), None),
        )
    next_block = next(
        (
            block
            for block in blocks
            if block.status == "planned"
            and (current_block is None or block.start_date > current_block.start_date)
        ),
        None,
    )
    next_deload = next(
        (
            block
            for block in blocks
            if block.is_deload and block.status in {"planned", "active"} and block.end_date >= today
        ),
        None,
    )
    return {
        "program_id": program.id,
        "status": program.status,
        "is_active": program.is_active,
        "start_date": program.start_date,
        "duration_weeks": program.duration_weeks,
        "current_revision_number": program.current_revision_number,
        "current_week_number": current_week,
        "current_block": (
            _lifecycle_block_summary(current_block, workouts) if current_block else None
        ),
        "next_block": _lifecycle_block_summary(next_block, workouts) if next_block else None,
        "next_workout": (
            {
                "id": next_workout.id,
                "scheduled_date": next_workout.scheduled_date,
                "week_number": next_workout.week_number,
                "day_number": next_workout.day_number,
                "title": next_workout.title,
                "status": next_workout.status,
            }
            if next_workout
            else None
        ),
        "next_deload": (_lifecycle_block_summary(next_deload, workouts) if next_deload else None),
        "restarted_from_program_id": program.restarted_from_program_id,
    }


def _copy_scheduled_workout(
    db: Session,
    source: UserWorkout,
    *,
    program_id: int,
    scheduled_date: date,
    week_number: int,
) -> UserWorkout:
    workout = UserWorkout(
        user_program_id=program_id,
        scheduled_date=scheduled_date,
        scheduled_time=source.scheduled_time,
        day_number=source.day_number,
        week_number=week_number,
        title=source.title,
        status="planned",
        plan_materialized=source.plan_materialized,
        source_cycle_week=source.source_cycle_week,
        cycle_iteration=source.cycle_iteration,
        plan_revision_number=1 if source.source_cycle_week is not None else None,
    )
    db.add(workout)
    db.flush()
    for source_exercise in source.exercises:
        exercise = UserWorkoutExercise(
            workout_id=workout.id,
            exercise_id=source_exercise.exercise_id,
            source_template_exercise_id=source_exercise.source_template_exercise_id,
            source_weekly_prescription_id=source_exercise.source_weekly_prescription_id,
            metric_type=source_exercise.metric_type,
            sort_order=source_exercise.sort_order,
            prescribed_sets=source_exercise.prescribed_sets,
            prescribed_reps=source_exercise.prescribed_reps,
            prescribed_duration_minutes=source_exercise.prescribed_duration_minutes,
            rest_seconds=source_exercise.rest_seconds,
            notes=source_exercise.notes,
            superset_group=source_exercise.superset_group,
            superset_order=source_exercise.superset_order,
            group_id=source_exercise.group_id,
            group_kind=source_exercise.group_kind,
            group_order=source_exercise.group_order,
            prescription=source_exercise.prescription,
        )
        db.add(exercise)
        db.flush()
        for source_set in sorted(source_exercise.sets, key=lambda row: row.set_number):
            db.add(
                UserWorkoutSet(
                    workout_exercise_id=exercise.id,
                    set_number=source_set.set_number,
                    set_kind=source_set.set_kind,
                    planned_role=source_set.planned_role,
                    planned_group_id=source_set.planned_group_id,
                    planned_group_kind=source_set.planned_group_kind,
                    planned_position=source_set.planned_position,
                    planned_round=source_set.planned_round,
                    is_completed=False,
                    version=1,
                )
            )
    return workout


def _copy_training_block(
    db: Session,
    source: TrainingBlock,
    *,
    program_id: int,
    start_date: date,
    created_by_user_id: int,
) -> TrainingBlock:
    block = TrainingBlock(
        user_program_id=program_id,
        title=source.title,
        start_date=start_date,
        end_date=start_date + timedelta(days=(source.end_date - source.start_date).days),
        purpose=source.purpose,
        notes=source.notes,
        is_deload=source.is_deload,
        status="planned",
        created_by_user_id=created_by_user_id,
    )
    db.add(block)
    db.flush()
    for source_priority in source.priority_links:
        db.add(
            TrainingBlockPriorityMuscle(
                training_block_id=block.id,
                muscle_id=source_priority.muscle_id,
                position=source_priority.position,
            )
        )
    return block


def _cancel_planned_workouts(db: Session, program: UserProgram) -> int:
    planned = (
        db.query(UserWorkout)
        .filter(
            UserWorkout.user_program_id == program.id,
            UserWorkout.status == "planned",
        )
        .with_for_update()
        .all()
    )
    for workout in planned:
        workout.status = "cancelled"
        cancel_workout_reminder(db, workout.id)
    return len(planned)


def apply_program_lifecycle_action(
    db: Session,
    actor: User,
    program_id: int,
    payload: ProgramLifecycleActionRequest,
) -> dict[str, object]:
    program, _role = get_program_for_actor(db, actor, program_id)
    # Match assignment/deletion: lock the owner before the program.
    owner = db.query(User).filter(User.id == program.user_id).with_for_update().one()
    program, _role = get_program_for_actor(db, actor, program_id, lock=True)
    _ensure_expected_revision(program, payload.expected_revision_number)
    previous_status = program.status
    now = now_msk_naive()

    if payload.action == "restart":
        _validate_restart_source_owner(program, owner)
        active_other = (
            db.query(UserProgram.id)
            .filter(
                UserProgram.user_id == program.user_id,
                UserProgram.is_active.is_(True),
                UserProgram.id != program.id,
            )
            .first()
        )
        if active_other is not None:
            raise ProgramError("Another active program must be completed or paused before resuming")
        has_in_progress = (
            db.query(UserWorkout.id)
            .filter(
                UserWorkout.user_program_id == program.id,
                UserWorkout.status == "in_progress",
            )
            .first()
        )
        if has_in_progress is not None:
            raise ProgramError("Cannot change program lifecycle while a workout is in progress")
        source_workouts = (
            db.query(UserWorkout)
            .options(selectinload(UserWorkout.exercises).selectinload(UserWorkoutExercise.sets))
            .filter(UserWorkout.user_program_id == program.id)
            .order_by(UserWorkout.scheduled_date.asc(), UserWorkout.id.asc())
            .all()
        )
        if not source_workouts:
            raise ProgramError("Program has no scheduled workouts to restart")
        restarting_cycle = _cycle_plan_at(db, program, 1) is not None
        source_blocks = _load_blocks(db, program.id)
        if program.status in MUTABLE_PROGRAM_STATUSES or program.status == "paused":
            cancelled_workouts = _cancel_planned_workouts(db, program)
            program.is_active = False
            program.status = "archived"
            program.archived_at = now
        else:
            cancelled_workouts = 0
            program.is_active = False

        today = today_for_user(owner)
        first_day = today + timedelta(days=1)
        first_weekday = (
            program.schedule_weekdays[0] if program.schedule_weekdays else first_day.weekday()
        )
        start_date = first_day + timedelta(days=(first_weekday - first_day.weekday()) % 7)
        new_program = UserProgram(
            user_id=program.user_id,
            template_id=program.template_id,
            assigned_by_user_id=program.assigned_by_user_id,
            start_date=start_date,
            duration_weeks=program.duration_weeks,
            schedule_weekdays=list(program.schedule_weekdays),
            status="scheduled" if start_date > today else "active",
            is_active=True,
            restarted_from_program_id=program.id,
        )
        db.add(new_program)
        db.flush()
        date_shift = start_date - program.start_date
        for workout in source_workouts:
            if restarting_cycle:
                continue
            if workout.scheduled_date < program.start_date:
                raise ProgramError("Program contains a workout before its start date")
            _copy_scheduled_workout(
                db,
                workout,
                program_id=new_program.id,
                scheduled_date=workout.scheduled_date + date_shift,
                week_number=_required_plan_number(workout.week_number),
            )
        for block in source_blocks:
            if block.status != "archived":
                _copy_training_block(
                    db,
                    block,
                    program_id=new_program.id,
                    start_date=block.start_date + date_shift,
                    created_by_user_id=actor.id,
                )

        record_program_revision(
            db,
            program,
            actor=actor,
            change_kind="program_lifecycle",
            reason=payload.reason,
            changed_fields={
                "operation": "program_restarted",
                "previous_status": previous_status,
                "new_program_id": new_program.id,
                "cancelled_future_workouts": cancelled_workouts,
                "history_boundary": "new_program",
            },
        )
        original_revision = (
            db.query(ProgramRevision)
            .filter(
                ProgramRevision.user_program_id == program.id,
                ProgramRevision.change_kind.in_(["assigned", "program_restarted"]),
            )
            .order_by(ProgramRevision.revision_number)
            .first()
        )
        inherited_cycle = (
            deepcopy(
                original_revision.snapshot.get(
                    "logical_cycle", original_revision.changed_fields.get("logical_cycle", [])
                )
            )
            if original_revision
            else []
        )
        inherited_configurations = deepcopy(_cycle_configurations(db, program))
        inherited_overrides = deepcopy(_cycle_occurrence_overrides(db, program.id))
        for override in inherited_overrides:
            if "not_before_date" in override:
                override["not_before_date"] = (
                    date.fromisoformat(override["not_before_date"]) + date_shift
                ).isoformat()
        for configuration in inherited_configurations:
            for day in configuration["logical_cycle"]:
                day["scheduled_date"] = (
                    date.fromisoformat(day["scheduled_date"]) + date_shift
                ).isoformat()
        for day_plan in inherited_cycle:
            day_plan["scheduled_date"] = (
                date.fromisoformat(day_plan["scheduled_date"]) + date_shift
            ).isoformat()
        restarted_revision = record_program_revision(
            db,
            new_program,
            actor=actor,
            change_kind="program_restarted",
            reason=payload.reason,
            changed_fields={
                "logical_cycle": inherited_cycle,
                "week_cycle": (
                    original_revision.changed_fields.get("week_cycle")
                    or (original_revision.snapshot["program"].get("program_metadata") or {}).get(
                        "week_cycle"
                    )
                )
                if original_revision
                else None,
                "inherited_cycle_configurations": inherited_configurations,
                "inherited_occurrence_overrides": inherited_overrides,
                "source_program_id": program.id,
                "history_boundary": "new_program",
                "workouts_created": len(source_workouts),
            },
        )
        if restarting_cycle:
            db.flush()
            materialize_next_cycle_window(db, new_program, through_date=new_program.start_date)
            restarted_revision.snapshot = _build_program_snapshot(db, new_program)
        record_audit_event(
            db,
            actor_user_id=actor.id,
            target_user_id=program.user_id,
            action="program.restarted",
            resource_type="user_program",
            resource_id=new_program.id,
            details={"source_program_id": program.id},
        )
        db.commit()
        return {
            "program_id": program.id,
            "status": program.status,
            "is_active": program.is_active,
            "current_revision_number": program.current_revision_number,
            "restarted_from_program_id": program.restarted_from_program_id,
            "new_program_id": new_program.id,
        }

    if payload.action == "pause":
        if program.status not in MUTABLE_PROGRAM_STATUSES or not program.is_active:
            raise ProgramError("Only an active or scheduled program can be paused")
        has_in_progress = (
            db.query(UserWorkout.id)
            .filter(
                UserWorkout.user_program_id == program.id,
                UserWorkout.status == "in_progress",
            )
            .first()
        )
        if has_in_progress is not None:
            raise ProgramError("Cannot change program lifecycle while a workout is in progress")
        program.status = "paused"
        program.is_active = False
    elif payload.action == "resume":
        if program.status != "paused":
            raise ProgramError("Only a paused program can be resumed")
        active_other = (
            db.query(UserProgram.id)
            .filter(
                UserProgram.user_id == program.user_id,
                UserProgram.is_active.is_(True),
                UserProgram.id != program.id,
            )
            .first()
        )
        if active_other is not None:
            raise ProgramError("Another active program must be completed or paused before resuming")
        program.is_active = True
        program.status = "scheduled" if program.start_date > today_for_user(owner) else "active"
    elif payload.action in {"complete", "terminate"}:
        if program.status not in MUTABLE_PROGRAM_STATUSES | {"paused"}:
            raise ProgramError("Only an active, scheduled, or paused program can be ended")
        has_in_progress = (
            db.query(UserWorkout.id)
            .filter(
                UserWorkout.user_program_id == program.id,
                UserWorkout.status == "in_progress",
            )
            .first()
        )
        if has_in_progress is not None:
            raise ProgramError("Cannot change program lifecycle while a workout is in progress")
        cancelled_workouts = _cancel_planned_workouts(db, program)
        program.is_active = False
        program.status = "completed" if payload.action == "complete" else "terminated"
        if payload.action == "complete":
            program.completed_at = now
        else:
            program.archived_at = now
    else:
        raise ProgramError("Unsupported program lifecycle action")

    changed_fields = {
        "operation": payload.action,
        "previous_status": previous_status,
        "status": program.status,
        "is_active": program.is_active,
    }
    if payload.action in {"complete", "terminate"}:
        changed_fields["cancelled_future_workouts"] = cancelled_workouts
    revision = record_program_revision(
        db,
        program,
        actor=actor,
        change_kind="program_lifecycle",
        reason=payload.reason,
        changed_fields=changed_fields,
    )
    record_audit_event(
        db,
        actor_user_id=actor.id,
        target_user_id=program.user_id,
        action=f"program.{payload.action}",
        resource_type="user_program",
        resource_id=program.id,
        details={"revision_number": revision.revision_number},
    )
    db.commit()
    return {
        "program_id": program.id,
        "status": program.status,
        "is_active": program.is_active,
        "current_revision_number": revision.revision_number,
        "restarted_from_program_id": program.restarted_from_program_id,
        "new_program_id": None,
    }


def _ensure_expected_revision(program: UserProgram, expected_revision_number: int) -> None:
    if program.current_revision_number != expected_revision_number:
        raise ProgramError("Program revision conflict")


def _validate_restart_source_owner(program: UserProgram, owner: User) -> None:
    if program.user_id != owner.id:
        raise ProgramError("Restart source program must belong to its owner")


def _ensure_program_mutable(program: UserProgram) -> None:
    if not program.is_active or program.status not in MUTABLE_PROGRAM_STATUSES:
        raise ProgramError("Assigned program is not editable")


def _workout_has_recorded_data(workout: UserWorkout) -> bool:
    """Treat persisted workout facts as immutable even if status is inconsistent."""
    if (
        workout.started_at is not None
        or workout.started_at_utc is not None
        or workout.completed_at is not None
    ):
        return True
    return any(
        workout_set.is_completed
        or (workout_set.version > 1 and workout_set.version != workout_set.plan_version)
        or any(
            value is not None
            for value in (
                workout_set.actual_reps,
                workout_set.actual_weight,
                workout_set.duration_minutes,
                workout_set.distance_km,
                workout_set.average_heart_rate_bpm,
                workout_set.heart_rate_zone,
                workout_set.rir,
                workout_set.reached_failure,
            )
        )
        for exercise in workout.exercises
        for workout_set in exercise.sets
    )


def _replace_workout_exercises_from_template(
    db: Session,
    workout: UserWorkout,
    day: ProgramTemplateDay,
    visible_by_id: dict[int, Exercise],
) -> None:
    for previous in list(workout.exercises):
        for previous_set in list(previous.sets):
            db.delete(previous_set)
        db.delete(previous)
    db.flush()
    for template_exercise in sorted(day.exercises, key=lambda item: item.sort_order):
        weekly = next(
            (
                item
                for item in template_exercise.weekly_prescriptions
                if item.week_number == workout.week_number
            ),
            None,
        )
        exercise_id = weekly.exercise_id if weekly is not None else template_exercise.exercise_id
        exercise = visible_by_id.get(exercise_id)
        if exercise is None:
            raise ProgramError("Imported exercise is not available for program owner")
        prescription = weekly or template_exercise
        plan, projection = ensure_plan(
            prescription.prescription or template_exercise.prescription,
            metric_type=exercise_metric_type(exercise),
            prescribed_sets=prescription.prescribed_sets,
            prescribed_reps=prescription.prescribed_reps,
            prescribed_duration_minutes=prescription.prescribed_duration_minutes,
            rest_seconds=prescription.rest_seconds,
        )
        if exercise_metric_type(exercise) == "strength" and projection.rest_seconds < 15:
            raise ProgramError("Strength rest must be at least 15 seconds")
        has_structured_plan = template_exercise.prescription is not None or (
            weekly is not None and weekly.prescription is not None
        )
        group_id = (
            template_exercise.group_id
            if template_exercise.group_id is not None
            else template_exercise.superset_group
        )
        group_kind = template_exercise.group_kind or (
            "superset" if template_exercise.superset_group is not None else None
        )
        group_order = (
            template_exercise.group_order
            if template_exercise.group_order is not None
            else template_exercise.superset_order
        )
        workout_exercise = UserWorkoutExercise(
            workout_id=workout.id,
            exercise_id=exercise_id,
            source_template_exercise_id=template_exercise.id,
            source_weekly_prescription_id=weekly.id if weekly is not None else None,
            metric_type=exercise_metric_type(exercise),
            sort_order=template_exercise.sort_order,
            prescribed_sets=projection.prescribed_sets,
            prescribed_reps=projection.prescribed_reps,
            prescribed_duration_minutes=projection.prescribed_duration_minutes,
            rest_seconds=projection.rest_seconds,
            notes=template_exercise.notes,
            superset_group=template_exercise.superset_group,
            superset_order=template_exercise.superset_order,
            group_id=group_id,
            group_kind=group_kind,
            group_order=group_order,
            prescription=plan.model_dump(mode="json") if has_structured_plan else None,
        )
        db.add(workout_exercise)
        groups = {item.group_id: item.kind for item in plan.groups}
        for set_number, segment in enumerate(plan.segments, start=1):
            db.add(
                UserWorkoutSet(
                    workout_exercise=workout_exercise,
                    set_number=set_number,
                    actual_reps=None,
                    actual_weight=None,
                    set_kind="working",
                    reached_failure=None,
                    is_completed=False,
                    planned_role=segment.role if has_structured_plan else None,
                    planned_group_id=segment.group_id if has_structured_plan else None,
                    planned_group_kind=(
                        groups.get(segment.group_id)
                        if has_structured_plan and segment.group_id is not None
                        else None
                    ),
                    planned_position=segment.position if has_structured_plan else None,
                    planned_round=segment.round_number if has_structured_plan else None,
                )
            )


def _schedule_offsets_for_program(
    program: UserProgram,
    day_numbers: list[int],
    schedule_weekdays: list[int] | None,
) -> tuple[dict[int, int], int]:
    if len(day_numbers) > 7:
        if schedule_weekdays is not None:
            raise ProgramError("An eight-day cycle uses automatic sequential scheduling")
        return {day_number: index for index, day_number in enumerate(day_numbers)}, 0
    weekdays = schedule_weekdays
    if weekdays is not None:
        if len(weekdays) != len(day_numbers):
            raise ProgramError("Choose one weekday for every program day")
        offsets = [(weekday - weekdays[0]) % 7 for weekday in weekdays]
        if offsets != sorted(offsets):
            raise ProgramError("Program weekdays must follow the order of program days")
    if weekdays is None or len(weekdays) != len(day_numbers):
        weekdays = list(program.schedule_weekdays)
    if len(weekdays) != len(day_numbers):
        weekdays = [(program.start_date.weekday() + index) % 7 for index in range(len(day_numbers))]
    first_weekday = weekdays[0]
    return (
        {
            day_number: (weekday - first_weekday) % 7
            for day_number, weekday in zip(day_numbers, weekdays, strict=True)
        },
        (first_weekday - program.start_date.weekday()) % 7,
    )


def _import_cycle_revision(
    db: Session,
    actor: User,
    program: UserProgram,
    template: ProgramTemplate,
    *,
    import_id: str,
    reason: str | None,
    allow_structure_changes: bool,
    schedule_weekdays: list[int] | None,
    send_notification: bool,
) -> tuple[UserProgram, int, int]:
    owner = db.query(User).filter_by(id=program.user_id).one()
    today = today_for_user(owner)
    historical = (
        db.query(UserWorkout)
        .filter(
            UserWorkout.user_program_id == program.id,
            UserWorkout.status.in_({"completed", "skipped", "in_progress"}),
        )
        .all()
    )
    if any(row.status == "in_progress" for row in historical):
        raise ProgramError("Дождитесь завершения текущей тренировки перед изменением цикла")
    boundary = max(
        max((_required_plan_number(row.week_number) for row in historical), default=0) + 1,
        max(1, (today - program.start_date).days // 7 + 1),
    )
    if boundary > program.duration_weeks:
        raise ProgramError("В программе нет будущих тренировок для применения импорта")
    old = _cycle_plan_at(db, program, boundary)
    if old is None:
        raise ProgramError("У назначения нет сохранённого цикла")
    old_cycle, old_source, _ = old
    days = sorted(template.days, key=lambda item: item.day_number)
    if len(days) > 7:
        raise ProgramError("В календарной неделе может быть не больше семи тренировочных дней")
    if not allow_structure_changes and {day.day_number for day in days} != {
        row["day_number"] for row in old_source
    }:
        raise ProgramError("Тренировочные дни импорта должны соответствовать назначенному циклу")
    cycle = (template.program_metadata or {}).get("week_cycle") or {
        "schema_version": 1,
        "length_weeks": template.effective_duration_weeks,
        "week_types": None,
        "repeat": old_cycle["repeat"],
    }
    if not cycle["repeat"] and program.duration_weeks - boundary + 1 > cycle["length_weeks"]:
        raise ProgramError("Длительность программы превышает длину цикла без повторения")

    def segment_count(prescription, slot) -> int:
        structured = prescription.prescription or slot.prescription
        return len(structured["segments"]) if structured else prescription.prescribed_sets

    if (
        cycle["length_weeks"]
        * sum(
            max(
                [segment_count(item, item)]
                + [segment_count(row, item) for row in item.weekly_prescriptions]
            )
            for day in days
            for item in day.exercises
        )
        > MAX_GENERATED_SETS
    ):
        raise ProgramError("Размер плана превышает допустимый объём одной операции")
    visible = {
        _effective_exercise_id(item): item for item in _load_visible_exercise_rows(db, owner)
    }
    weekdays = (
        schedule_weekdays if schedule_weekdays is not None else list(program.schedule_weekdays)
    )
    if len(weekdays) != len(days):
        weekdays = [(program.start_date.weekday() + index) % 7 for index in range(len(days))]
    if len(set(weekdays)) != len(weekdays) or any(day < 0 or day > 6 for day in weekdays):
        raise ProgramError("Program weekdays must be unique and valid")
    offsets = [(day - program.start_date.weekday()) % 7 for day in weekdays]
    if offsets != sorted(offsets):
        raise ProgramError("Program weekdays must follow the order of program days")
    source: list[dict] = []
    for week in range(1, cycle["length_weeks"] + 1):
        for day, offset in zip(days, offsets, strict=True):
            exercises: list[dict] = []
            for slot in sorted(day.exercises, key=lambda item: item.sort_order):
                weekly = next(
                    (row for row in slot.weekly_prescriptions if row.week_number == week), None
                )
                if slot.weekly_prescriptions and weekly is None:
                    raise ProgramError("Periodized template has an incomplete weekly prescription")
                prescription = weekly or slot
                exercise_id = prescription.exercise_id
                exercise = visible.get(exercise_id)
                if exercise is None:
                    raise ProgramError("Imported exercise is not available for program owner")
                plan, projection = ensure_plan(
                    prescription.prescription or slot.prescription,
                    metric_type=exercise_metric_type(exercise),
                    prescribed_sets=prescription.prescribed_sets,
                    prescribed_reps=prescription.prescribed_reps,
                    prescribed_duration_minutes=prescription.prescribed_duration_minutes,
                    rest_seconds=prescription.rest_seconds,
                )
                structured = slot.prescription is not None or (
                    weekly is not None and weekly.prescription is not None
                )
                projected_sets = _cycle_plan_sets(plan.model_dump(mode="json"))
                if not structured:
                    for item in projected_sets:
                        for key in list(item):
                            if key.startswith("planned_"):
                                item[key] = None
                exercises.append(
                    {
                        "exercise_id": exercise_id,
                        "metric_type": exercise_metric_type(exercise),
                        "sort_order": slot.sort_order,
                        "source_template_exercise_id": slot.id,
                        "source_weekly_prescription_id": weekly.id if weekly else None,
                        "prescribed_sets": projection.prescribed_sets,
                        "prescribed_reps": projection.prescribed_reps,
                        "prescribed_duration_minutes": projection.prescribed_duration_minutes,
                        "rest_seconds": projection.rest_seconds,
                        "notes": slot.notes,
                        "superset_group": slot.superset_group,
                        "superset_order": slot.superset_order,
                        "group_id": slot.group_id
                        if slot.group_id is not None
                        else slot.superset_group,
                        "group_kind": slot.group_kind
                        or ("superset" if slot.superset_group is not None else None),
                        "group_order": slot.group_order
                        if slot.group_order is not None
                        else slot.superset_order,
                        "prescription": plan.model_dump(mode="json") if structured else None,
                        "sets": projected_sets,
                    }
                )
            source.append(
                {
                    "week_number": week,
                    "day_number": day.day_number,
                    "title": day.title,
                    "scheduled_date": (
                        program.start_date + timedelta(weeks=week - 1, days=offset)
                    ).isoformat(),
                    "exercises": exercises,
                }
            )
    if sum(len(item["sets"]) for row in source for item in row["exercises"]) > MAX_GENERATED_SETS:
        raise ProgramError("Размер плана превышает допустимый объём одной операции")
    revision = record_program_revision(
        db,
        program,
        actor=actor,
        change_kind="plan_updated",
        reason=reason,
        changed_fields={
            "operation": "imported_cycle_revised",
            "import_id": import_id,
            "cycle_configuration": {
                "effective_from_week": boundary,
                "week_cycle": cycle,
                "logical_cycle": source,
            },
        },
    )
    db.flush()
    updated = 0
    revised_sets = 0
    structure_cancelled = {
        workout_id
        for event in db.query(ProgramRevision).filter_by(user_program_id=program.id)
        for workout_id in event.changed_fields.get("structure_cancelled_workout_ids", [])
    }
    cancelled_ids = []
    for workout in db.query(UserWorkout).filter(
        UserWorkout.user_program_id == program.id,
        UserWorkout.week_number >= boundary,
        UserWorkout.week_number <= program.duration_weeks,
        or_(
            UserWorkout.status == "planned",
            and_(UserWorkout.status == "cancelled", UserWorkout.id.in_(structure_cancelled)),
        ),
    ):
        if _workout_has_recorded_data(workout) or workout.started_at is not None:
            raise ProgramError(
                "Изменение цикла не может затрагивать выполненные или начатые тренировки"
            )
        if workout.week_number is None:
            raise ProgramError("Для тренировки нет данных плана")
        effective = next(
            (
                item
                for item in _cycle_workout_plans(db, program, workout.week_number)
                if item["day_number"] == workout.day_number
            ),
            None,
        )
        if effective is None:
            if workout.status == "cancelled":
                continue
            workout.status = "cancelled"
            cancelled_ids.append(workout.id)
            cancel_workout_reminder(db, workout.id)
        else:
            workout.status = "planned"
        if effective is not None and workout.plan_materialized is not False:
            count = sum(len(item["sets"]) for item in effective["exercises"])
            if revised_sets + count > MAX_GENERATED_SETS:
                continue
            _write_cycle_exercises(db, workout, effective)
            revised_sets += count
        workout.plan_revision_number = revision.revision_number
        updated += 1
    revision.changed_fields = {
        **revision.changed_fields,
        "structure_cancelled_workout_ids": cancelled_ids,
    }
    program.template_id = template.id
    program.schedule_weekdays = weekdays
    revision.snapshot = _build_program_snapshot(db, program)
    record_audit_event(
        db,
        actor_user_id=actor.id,
        target_user_id=program.user_id,
        action="program.imported_plan_applied",
        resource_type="user_program",
        resource_id=program.id,
        details={"revision_number": revision.revision_number, "import_id": import_id},
    )
    if actor.id != owner.id and send_notification:
        queue_notification(
            db,
            owner,
            category="trainer_program_update",
            title="Программа тренировок изменена",
            body="Тренер обновил будущий план тренировок.",
            dedupe_key=f"program_import_revision:{program.id}:{revision.revision_number}",
        )
    db.flush()
    return program, updated, revision.revision_number


def apply_imported_template_revision(
    db: Session,
    actor: User,
    program_id: int,
    template: ProgramTemplate,
    *,
    expected_revision_number: int,
    import_id: str,
    rollout_id: str | None = None,
    reason: str | None = None,
    allow_structure_changes: bool = False,
    schedule_weekdays: list[int] | None = None,
    send_notification: bool = True,
    operation: str | None = None,
) -> tuple[UserProgram, int, int]:
    program, role = get_program_for_actor(db, actor, program_id, lock=True)
    _ensure_program_mutable(program)
    _ensure_expected_revision(program, expected_revision_number)
    if _cycle_plan_at(db, program, program.duration_weeks) is not None:
        return _import_cycle_revision(
            db,
            actor,
            program,
            template,
            import_id=import_id,
            reason=reason,
            allow_structure_changes=allow_structure_changes,
            schedule_weekdays=schedule_weekdays,
            send_notification=send_notification,
        )
    current_template = program.template
    if (
        allow_structure_changes
        and current_template is not None
        and current_template.sessions_per_week != len(current_template.days)
    ):
        # The revision builder keys slots by week/day and cannot preserve repeated cycle days.
        raise ProgramError(
            "Изменение структуры чередующегося цикла пока не поддерживается. Создайте отдельную программу; текущие тренировки сохранены."
        )
    if program.duration_weeks != template.effective_duration_weeks and not (
        allow_structure_changes and template.effective_duration_weeks == 1
    ):
        raise ProgramError("Imported duration must match the assigned program")

    db.flush()
    loaded_template = (
        db.query(ProgramTemplate)
        .options(
            selectinload(ProgramTemplate.days)
            .selectinload(ProgramTemplateDay.exercises)
            .selectinload(ProgramTemplateExercise.weekly_prescriptions)
        )
        .filter(ProgramTemplate.id == template.id)
        .populate_existing()
        .one()
    )
    days_by_number = {day.day_number: day for day in loaded_template.days}
    all_workouts = (
        db.query(UserWorkout)
        .filter(UserWorkout.user_program_id == program.id)
        .order_by(UserWorkout.week_number, UserWorkout.day_number)
        .all()
    )
    if not allow_structure_changes:
        expected_pairs = {
            (week_number, day_number)
            for week_number in range(1, program.duration_weeks + 1)
            for day_number in days_by_number
        }
        actual_pairs = {(row.week_number, row.day_number) for row in all_workouts}
        if actual_pairs != expected_pairs or len(actual_pairs) != len(all_workouts):
            raise ProgramError("Imported days and weeks must match the assigned program schedule")

    target_user = db.query(User).filter(User.id == program.user_id).one()
    visible_by_id = {
        _effective_exercise_id(exercise): exercise
        for exercise in _load_visible_exercise_rows(db, target_user)
    }
    future_workouts = (
        db.query(UserWorkout)
        .options(selectinload(UserWorkout.exercises).selectinload(UserWorkoutExercise.sets))
        .filter(
            UserWorkout.user_program_id == program.id,
            UserWorkout.status == "planned",
            UserWorkout.started_at.is_(None),
            UserWorkout.scheduled_date >= today_for_user(target_user),
        )
        .order_by(UserWorkout.scheduled_date.asc(), UserWorkout.id.asc())
        .all()
    )
    future_workouts = [
        workout for workout in future_workouts if not _workout_has_recorded_data(workout)
    ]
    workouts_updated = 0
    if allow_structure_changes:
        day_numbers = sorted(days_by_number)
        schedule_offsets, cycle_start_offset = _schedule_offsets_for_program(
            program,
            day_numbers,
            schedule_weekdays,
        )
        cycle_span_days = 8 if len(day_numbers) > 7 else 7
        today = today_for_user(target_user)
        existing_by_pair: dict[tuple[int, int], UserWorkout] = {}
        for row in all_workouts:
            if row.week_number is None or row.day_number is None:
                raise ProgramError("Для тренировки нет данных плана")
            pair = (row.week_number, row.day_number)
            if pair in existing_by_pair:
                raise ProgramError("Assigned program contains duplicate workout days")
            existing_by_pair[pair] = row

        for workout in future_workouts:
            if workout.week_number is None or workout.day_number is None:
                raise ProgramError("Для тренировки нет данных плана")
            day = days_by_number.get(workout.day_number)
            if day is None:
                workout.status = "cancelled"
                cancel_workout_reminder(db, workout.id)
                workouts_updated += 1
                continue
            desired_date = program.start_date + timedelta(
                days=cycle_start_offset
                + (workout.week_number - 1) * cycle_span_days
                + schedule_offsets[workout.day_number]
            )
            if desired_date >= today:
                workout.scheduled_date = desired_date
            workout.title = day.title
            _replace_workout_exercises_from_template(db, workout, day, visible_by_id)
            workouts_updated += 1

        for week_number in range(1, program.duration_weeks + 1):
            for day_number in day_numbers:
                pair = (week_number, day_number)
                existing = existing_by_pair.get(pair)
                if existing is not None and existing.status != "cancelled":
                    continue
                desired_date = program.start_date + timedelta(
                    days=cycle_start_offset
                    + (week_number - 1) * cycle_span_days
                    + schedule_offsets[day_number]
                )
                if desired_date < today:
                    continue
                day = days_by_number[day_number]
                if existing is not None:
                    if _workout_has_recorded_data(existing):
                        continue
                    existing.status = "planned"
                    existing.scheduled_date = desired_date
                    existing.title = day.title
                    _replace_workout_exercises_from_template(db, existing, day, visible_by_id)
                    workouts_updated += 1
                    continue
                workout = UserWorkout(
                    user_program_id=program.id,
                    scheduled_date=desired_date,
                    day_number=day_number,
                    week_number=week_number,
                    title=day.title,
                    status="planned",
                )
                db.add(workout)
                db.flush()
                _replace_workout_exercises_from_template(db, workout, day, visible_by_id)
                workouts_updated += 1
        if len(day_numbers) <= 7:
            program.schedule_weekdays = [
                program.start_date.weekday() + cycle_start_offset + schedule_offsets[day_number]
                for day_number in day_numbers
            ]
            program.schedule_weekdays = [weekday % 7 for weekday in program.schedule_weekdays]
    else:
        for workout in future_workouts:
            if workout.day_number is None:
                raise ProgramError("Для тренировки нет данных плана")
            day = days_by_number[workout.day_number]
            workout.title = day.title
            _replace_workout_exercises_from_template(db, workout, day, visible_by_id)
        workouts_updated = len(future_workouts)

    prior_template_id = program.template_id
    program.template_id = loaded_template.id
    program.template = loaded_template
    revision = record_program_revision(
        db,
        program,
        actor=actor,
        change_kind="plan_updated",
        reason=reason or "Импорт новой ревизии программы",
        changed_fields={
            "operation": operation
            or ("program_rollout" if rollout_id is not None else "program_import_revision"),
            "import_id": import_id,
            "previous_template_id": prior_template_id,
            "template_id": loaded_template.id,
            "workouts_updated": workouts_updated,
            **({"rollout_id": rollout_id} if rollout_id is not None else {}),
        },
    )
    record_audit_event(
        db,
        actor_user_id=actor.id,
        target_user_id=program.user_id,
        action=(
            "coach.program_rollout.applied"
            if rollout_id is not None
            else "program.template_revision_applied"
            if operation == "template_update"
            else "program_import.revision_confirmed"
        ),
        resource_type="user_program",
        resource_id=program.id,
        details={
            "import_id": import_id,
            "revision_number": revision.revision_number,
            **({"rollout_id": rollout_id} if rollout_id is not None else {}),
        },
    )
    if role == "trainer" and send_notification:
        queue_notification(
            db,
            target_user,
            category="trainer_program_update",
            title="Программа тренировок изменена",
            body="Тренер обновил предстоящие тренировки. История изменений сохранена.",
            action_url="/app?section=programs",
        )
    db.flush()
    return program, workouts_updated, revision.revision_number


def _validate_block_dates(
    db: Session,
    program: UserProgram,
    start_date: date,
    end_date: date,
    *,
    block_id: int | None = None,
) -> None:
    if end_date < start_date:
        raise ProgramError("Training block end date must not precede its start date")
    program_end = program.start_date + timedelta(weeks=program.duration_weeks) - timedelta(days=1)
    if start_date < program.start_date or end_date > program_end:
        raise ProgramError("Training block dates must stay within the assigned program")
    overlap_query = db.query(TrainingBlock.id).filter(
        TrainingBlock.user_program_id == program.id,
        TrainingBlock.status != "archived",
        TrainingBlock.start_date <= end_date,
        TrainingBlock.end_date >= start_date,
    )
    if block_id is not None:
        overlap_query = overlap_query.filter(TrainingBlock.id != block_id)
    if overlap_query.first() is not None:
        raise ProgramError("Training blocks must not overlap")


def _replace_priority_muscles(
    db: Session,
    block: TrainingBlock,
    identifiers: list[str],
) -> None:
    muscles = (
        db.query(Muscle).filter(Muscle.identifier.in_(identifiers)).all() if identifiers else []
    )
    by_identifier = {muscle.identifier: muscle for muscle in muscles}
    if set(by_identifier) != set(identifiers):
        raise ProgramError("Unknown priority muscle")
    block.priority_links.clear()
    db.flush()
    for position, identifier in enumerate(identifiers):
        block.priority_links.append(
            TrainingBlockPriorityMuscle(
                muscle_id=by_identifier[identifier].id,
                position=position,
            )
        )


def create_training_block(
    db: Session,
    actor: User,
    program_id: int,
    payload: TrainingBlockCreate,
) -> tuple[dict, int]:
    program, _role = get_program_for_actor(db, actor, program_id, lock=True)
    _ensure_program_mutable(program)
    _ensure_expected_revision(program, payload.expected_revision_number)
    _validate_block_dates(db, program, payload.start_date, payload.end_date)
    title = payload.title.strip()
    purpose = payload.purpose.strip()
    if not title or not purpose:
        raise ProgramError("Training block title and purpose are required")
    block = TrainingBlock(
        user_program_id=program.id,
        title=title,
        start_date=payload.start_date,
        end_date=payload.end_date,
        purpose=purpose,
        notes=payload.notes.strip() if payload.notes and payload.notes.strip() else None,
        is_deload=payload.is_deload,
        status="planned",
        created_by_user_id=actor.id,
    )
    db.add(block)
    db.flush()
    _replace_priority_muscles(db, block, payload.priority_muscle_ids)
    revision = record_program_revision(
        db,
        program,
        actor=actor,
        change_kind="block_created",
        reason=payload.reason,
        changed_fields={"block_id": block.id, "status": block.status},
    )
    record_audit_event(
        db,
        actor_user_id=actor.id,
        target_user_id=program.user_id,
        action="program.training_block_created",
        resource_type="training_block",
        resource_id=block.id,
        details={"user_program_id": program.id, "revision_number": revision.revision_number},
    )
    db.commit()
    loaded = next(item for item in _load_blocks(db, program.id) if item.id == block.id)
    return _serialize_block(loaded), revision.revision_number


def _validate_block_status_transition(
    db: Session,
    block: TrainingBlock,
    next_status: str,
) -> None:
    if next_status == block.status:
        return
    if next_status not in BLOCK_STATUS_TRANSITIONS[block.status]:
        raise ProgramError("Invalid training block status transition")
    if next_status == "active":
        previous_incomplete = (
            db.query(TrainingBlock.id)
            .filter(
                TrainingBlock.user_program_id == block.user_program_id,
                TrainingBlock.id != block.id,
                TrainingBlock.start_date < block.start_date,
                TrainingBlock.status.in_({"planned", "active"}),
            )
            .first()
        )
        if previous_incomplete is not None:
            raise ProgramError("Complete the previous training block first")
        other_active = (
            db.query(TrainingBlock.id)
            .filter(
                TrainingBlock.user_program_id == block.user_program_id,
                TrainingBlock.id != block.id,
                TrainingBlock.status == "active",
            )
            .first()
        )
        if other_active is not None:
            raise ProgramError("Another training block is already active")


def update_training_block(
    db: Session,
    actor: User,
    program_id: int,
    block_id: int,
    payload: TrainingBlockUpdate,
) -> tuple[dict, int]:
    program, _role = get_program_for_actor(db, actor, program_id, lock=True)
    _ensure_program_mutable(program)
    _ensure_expected_revision(program, payload.expected_revision_number)
    block = (
        db.query(TrainingBlock)
        .options(selectinload(TrainingBlock.priority_links))
        .filter(
            TrainingBlock.id == block_id,
            TrainingBlock.user_program_id == program.id,
        )
        .first()
    )
    if block is None:
        raise ProgramError("Training block not found")
    if block.status in {"completed", "archived"}:
        raise ProgramError("Completed or archived training blocks are immutable")

    changes = payload.model_dump(
        exclude_unset=True,
        exclude={"expected_revision_number", "reason", "priority_muscle_ids"},
    )
    next_start = changes.get("start_date", block.start_date)
    next_end = changes.get("end_date", block.end_date)
    _validate_block_dates(db, program, next_start, next_end, block_id=block.id)
    next_status = changes.get("status", block.status)
    _validate_block_status_transition(db, block, next_status)

    for field, value in changes.items():
        if field in {"title", "purpose"} and isinstance(value, str):
            value = value.strip()
            if not value:
                raise ProgramError("Training block title and purpose are required")
        if field == "notes" and isinstance(value, str):
            value = value.strip() or None
        setattr(block, field, value)
    if payload.priority_muscle_ids is not None:
        _replace_priority_muscles(db, block, payload.priority_muscle_ids)
    block.updated_at = now_msk_naive()
    change_kind = (
        "block_status_changed" if "status" in payload.model_fields_set else "block_updated"
    )
    changed_field_names = sorted(payload.model_fields_set - {"expected_revision_number", "reason"})
    revision = record_program_revision(
        db,
        program,
        actor=actor,
        change_kind=change_kind,
        reason=payload.reason,
        changed_fields={"block_id": block.id, "fields": changed_field_names},
    )
    record_audit_event(
        db,
        actor_user_id=actor.id,
        target_user_id=program.user_id,
        action="program.training_block_updated",
        resource_type="training_block",
        resource_id=block.id,
        details={
            "user_program_id": program.id,
            "revision_number": revision.revision_number,
            "fields": changed_field_names,
        },
    )
    db.commit()
    loaded = next(item for item in _load_blocks(db, program.id) if item.id == block.id)
    return _serialize_block(loaded), revision.revision_number


def advance_training_block(
    db: Session,
    actor: User,
    program_id: int,
    block_id: int,
    payload: TrainingBlockActionRequest,
) -> tuple[dict, int, int]:
    program, _role = get_program_for_actor(db, actor, program_id, lock=True)
    _ensure_program_mutable(program)
    _ensure_expected_revision(program, payload.expected_revision_number)
    current = (
        db.query(TrainingBlock)
        .filter(
            TrainingBlock.id == block_id,
            TrainingBlock.user_program_id == program.id,
        )
        .with_for_update()
        .first()
    )
    if current is None:
        raise ProgramError("Training block not found")
    if current.status != "active":
        raise ProgramError("Only the active training block can advance")
    in_progress = (
        db.query(UserWorkout.id)
        .filter(
            UserWorkout.user_program_id == program.id,
            UserWorkout.status == "in_progress",
            UserWorkout.scheduled_date.between(current.start_date, current.end_date),
        )
        .first()
    )
    if in_progress is not None:
        raise ProgramError("Cannot advance a block while a workout is in progress")
    next_block = (
        db.query(TrainingBlock)
        .filter(
            TrainingBlock.user_program_id == program.id,
            TrainingBlock.status == "planned",
            TrainingBlock.start_date > current.start_date,
        )
        .order_by(TrainingBlock.start_date.asc(), TrainingBlock.id.asc())
        .with_for_update()
        .first()
    )
    if next_block is None:
        raise ProgramError("There is no planned training block to advance to")
    current.status = "completed"
    current.updated_at = now_msk_naive()
    db.flush()
    _validate_block_status_transition(db, next_block, "active")
    next_block.status = "active"
    next_block.updated_at = now_msk_naive()
    revision = record_program_revision(
        db,
        program,
        actor=actor,
        change_kind="block_status_changed",
        reason=payload.reason,
        changed_fields={
            "operation": "block_advanced",
            "completed_block_id": current.id,
            "active_block_id": next_block.id,
        },
    )
    record_audit_event(
        db,
        actor_user_id=actor.id,
        target_user_id=program.user_id,
        action="program.training_block_advanced",
        resource_type="training_block",
        resource_id=next_block.id,
        details={"user_program_id": program.id, "revision_number": revision.revision_number},
    )
    db.commit()
    loaded = next(item for item in _load_blocks(db, program.id) if item.id == next_block.id)
    return _serialize_block(loaded), current.id, revision.revision_number


def repeat_training_block(
    db: Session,
    actor: User,
    program_id: int,
    block_id: int,
    payload: TrainingBlockActionRequest,
) -> tuple[dict, int, int]:
    program, _role = get_program_for_actor(db, actor, program_id, lock=True)
    _ensure_program_mutable(program)
    _ensure_expected_revision(program, payload.expected_revision_number)
    source = (
        db.query(TrainingBlock)
        .options(selectinload(TrainingBlock.priority_links))
        .filter(
            TrainingBlock.id == block_id,
            TrainingBlock.user_program_id == program.id,
        )
        .with_for_update()
        .first()
    )
    if source is None:
        raise ProgramError("Training block not found")
    if source.status != "completed":
        raise ProgramError("Complete the training block before repeating it")
    first_week = (source.start_date - program.start_date).days // 7 + 1
    last_week = (source.end_date - program.start_date).days // 7 + 1
    if (
        _cycle_plan_at(db, program, first_week) is None
        and _cycle_plan_at(db, program, last_week) is not None
    ):
        raise ProgramError("Нельзя повторить блок, пересекающий начало периодизации")
    if _cycle_plan_at(db, program, first_week) is not None:
        length = last_week - first_week + 1
        if length > MAX_GENERATED_SETS:
            raise ProgramError("Размер плана превышает допустимый объём одной операции")
        logical_source = []
        week_types = []
        revisions = (
            db.query(ProgramRevision)
            .filter_by(user_program_id=program.id)
            .order_by(ProgramRevision.revision_number)
            .all()
        )
        overrides = _cycle_occurrence_overrides(db, program.id, revisions=revisions)
        rows = {
            (row.week_number, row.day_number): row
            for row in db.query(UserWorkout).filter_by(user_program_id=program.id)
        }
        indexed_sources: dict[int, dict[int, list[dict]]] = {}
        for old_week in range(first_week, last_week + 1):
            old_config = _cycle_plan_at(db, program, old_week, revisions=revisions)
            types = set()
            for original in _cycle_workout_plans(
                db, program, old_week, revisions=revisions, source_index=indexed_sources
            ):
                scheduled = date.fromisoformat(original["scheduled_date"])
                if source.start_date <= scheduled <= source.end_date:
                    row = rows.get((old_week, original["day_number"]))
                    if row is not None:
                        resolved_type, known = workout_cycle_week_type(db, row, revisions)
                        if not known:
                            raise ProgramError("Тип недели исходного блока неизвестен")
                    else:
                        assert old_config is not None
                        cycle, _old_source, boundary = old_config
                        resolved_type = _cycle_type_for_date(
                            cycle,
                            overrides,
                            old_week,
                            original["source_cycle_week"],
                            boundary,
                            scheduled,
                        )
                    types.add(resolved_type)
                    item = deepcopy(original)
                    item["week_number"] = old_week - first_week + 1
                    item["scheduled_date"] = (
                        scheduled - timedelta(weeks=first_week - 1)
                    ).isoformat()
                    logical_source.append(item)
            if len(types) > 1:
                raise ProgramError("В одной неделе исходного блока сохранены разные типы")
            week_types.append(next(iter(types), None))
        if (
            not logical_source
            or sum(len(item["sets"]) for day in logical_source for item in day["exercises"])
            > MAX_GENERATED_SETS
        ):
            raise ProgramError("Нет плана блока, который можно повторить в пределах одной операции")
        old_duration = program.duration_weeks
        if old_duration + length > (date.max - program.start_date).days // 7:
            raise ProgramError(
                "Длительность программы выходит за поддерживаемый диапазон календарных дат"
            )
        offset = (source.start_date - (program.start_date + timedelta(weeks=first_week - 1))).days
        new_start = program.start_date + timedelta(weeks=old_duration, days=offset)
        program.duration_weeks = old_duration + length
        repeated = _copy_training_block(
            db, source, program_id=program.id, start_date=new_start, created_by_user_id=actor.id
        )
        revision = record_program_revision(
            db,
            program,
            actor=actor,
            change_kind="block_created",
            reason=payload.reason,
            changed_fields={
                "operation": "block_repeated",
                "block_id": repeated.id,
                "repeated_from_block_id": source.id,
                "weeks_added": length,
                "cycle_configuration": {
                    "effective_from_week": old_duration + 1,
                    "week_cycle": {
                        "schema_version": 1,
                        "length_weeks": length,
                        "repeat": True,
                        "baked_override_count": len(overrides),
                        "week_types": week_types
                        if any(item is not None for item in week_types)
                        else None,
                    },
                    "logical_cycle": logical_source,
                },
            },
        )
        db.flush()
        materialize_next_cycle_window(db, program, through_date=new_start)
        revision.snapshot = _build_program_snapshot(db, program)
        record_audit_event(
            db,
            actor_user_id=actor.id,
            target_user_id=program.user_id,
            action="program.training_block_repeated",
            resource_type="training_block",
            resource_id=repeated.id,
            details={"user_program_id": program.id, "revision_number": revision.revision_number},
        )
        db.commit()
        return _serialize_block(repeated), program.duration_weeks, revision.revision_number

    workouts = (
        db.query(UserWorkout)
        .options(selectinload(UserWorkout.exercises).selectinload(UserWorkoutExercise.sets))
        .filter(
            UserWorkout.user_program_id == program.id,
            UserWorkout.scheduled_date.between(source.start_date, source.end_date),
        )
        .order_by(UserWorkout.scheduled_date.asc(), UserWorkout.id.asc())
        .all()
    )
    if not workouts:
        raise ProgramError("Training block has no scheduled workouts to repeat")
    first_source_week = min(_required_plan_number(workout.week_number) for workout in workouts)
    last_source_week = max(_required_plan_number(workout.week_number) for workout in workouts)
    source_week_start = program.start_date + timedelta(weeks=first_source_week - 1)
    start_offset = (source.start_date - source_week_start).days
    duration_days = (source.end_date - source.start_date).days + 1
    additional_weeks = max(
        last_source_week - first_source_week + 1,
        (start_offset + duration_days + 6) // 7,
    )
    old_duration_weeks = program.duration_weeks
    next_duration = old_duration_weeks + additional_weeks
    new_block_start = (
        program.start_date + timedelta(weeks=old_duration_weeks) + timedelta(days=start_offset)
    )
    program.duration_weeks = next_duration
    _validate_block_dates(
        db,
        program,
        new_block_start,
        new_block_start + timedelta(days=duration_days - 1),
    )
    repeated = _copy_training_block(
        db,
        source,
        program_id=program.id,
        start_date=new_block_start,
        created_by_user_id=actor.id,
    )
    week_shift = old_duration_weeks + 1 - first_source_week
    for workout in workouts:
        if workout.week_number is None:
            raise ProgramError("Для тренировки нет данных плана")
        new_week = workout.week_number + week_shift
        old_week_start = program.start_date + timedelta(weeks=workout.week_number - 1)
        day_offset = (workout.scheduled_date - old_week_start).days
        new_date = program.start_date + timedelta(weeks=new_week - 1, days=day_offset)
        _copy_scheduled_workout(
            db,
            workout,
            program_id=program.id,
            scheduled_date=new_date,
            week_number=new_week,
        )
    revision = record_program_revision(
        db,
        program,
        actor=actor,
        change_kind="block_created",
        reason=payload.reason,
        changed_fields={
            "block_id": repeated.id,
            "operation": "block_repeated",
            "repeated_from_block_id": source.id,
            "week_start": old_duration_weeks + 1,
            "weeks_added": additional_weeks,
            "workouts_created": len(workouts),
        },
    )
    record_audit_event(
        db,
        actor_user_id=actor.id,
        target_user_id=program.user_id,
        action="program.training_block_repeated",
        resource_type="training_block",
        resource_id=repeated.id,
        details={"user_program_id": program.id, "revision_number": revision.revision_number},
    )
    db.commit()
    loaded = next(item for item in _load_blocks(db, program.id) if item.id == repeated.id)
    return _serialize_block(loaded), program.duration_weeks, revision.revision_number


def upsert_future_program_exercise(
    db: Session,
    actor: User,
    program_id: int,
    payload: CoachProgramExerciseCreate,
) -> tuple[int, int]:
    program, role = get_program_for_actor(db, actor, program_id, lock=True)
    _ensure_program_mutable(program)
    _ensure_expected_revision(program, payload.expected_revision_number)
    target_user = db.query(User).filter(User.id == program.user_id).one()
    visible_by_effective_id = {
        _effective_exercise_id(exercise): exercise
        for exercise in _load_visible_exercise_rows(db, target_user)
    }
    exercise = visible_by_effective_id.get(payload.exercise_id)
    if exercise is None:
        raise ProgramError("Exercise is not available for program owner")
    plan, projection = ensure_plan(
        payload.prescription,
        metric_type=exercise_metric_type(exercise),
        prescribed_sets=payload.prescribed_sets,
        prescribed_reps=payload.prescribed_reps,
        prescribed_duration_minutes=payload.prescribed_duration_minutes,
        rest_seconds=payload.rest_seconds,
    )
    if exercise_metric_type(exercise) == "strength" and projection.rest_seconds < 15:
        raise ProgramError("Strength rest must be at least 15 seconds")

    if _cycle_plan_at(db, program, program.duration_weeks) is not None:
        explicit = payload.occurrence_weeks
        if payload.effective_scope != "future_program" and any(
            value is not None for value in (explicit, payload.from_week, payload.source_cycle_week)
        ):
            raise ProgramError("Явную область недель можно задать только для будущего плана")
        if explicit is not None and (
            payload.from_week is not None
            or payload.source_cycle_week is not None
            or payload.effective_date is not None
        ):
            raise ProgramError("Выберите конкретные недели или область повторения изменений")
        today = today_for_user(target_user)
        first_week = payload.from_week or max(
            1, ((payload.effective_date or today) - program.start_date).days // 7 + 1
        )
        weeks = sorted(set(explicit)) if explicit is not None else []
        if (
            any(week < 1 or week > program.duration_weeks for week in weeks)
            or first_week > program.duration_weeks
        ):
            raise ProgramError("Некорректный номер недели программы")
        target_week = min(weeks) if weeks else first_week
        resolved = _cycle_plan_at(db, program, target_week)
        if resolved is None:
            raise ProgramError("У назначения нет сохранённого цикла")
        cycle, source, cycle_boundary = resolved
        if (
            payload.source_cycle_week is not None
            and payload.source_cycle_week > cycle["length_weeks"]
        ):
            raise ProgramError("Некорректный номер исходной недели цикла")
        candidates = [
            (row["day_number"], item)
            for row in source
            for item in row["exercises"]
            if (payload.day_number is None or row["day_number"] == payload.day_number)
            and (
                (
                    payload.target_template_exercise_id is not None
                    and item.get("source_template_exercise_id")
                    == payload.target_template_exercise_id
                )
                or (
                    payload.target_template_exercise_id is None
                    and item["exercise_id"] == payload.exercise_id
                )
            )
        ]
        identities = {(day, item["source_template_exercise_id"]) for day, item in candidates}
        if len(identities) != 1:
            raise ProgramError("Укажите тренировочный день и исходную позицию упражнения")
        selected_day, selected_slot = next(iter(identities))
        if selected_slot is None:
            raise ProgramError("У исходного упражнения нет устойчивой позиции")
        if any(
            payload.model_dump()[key] is not None
            for key in ("group_id", "group_kind", "group_order", "superset_group", "superset_order")
        ):
            raise ProgramError(
                "Для изменения групп упражнений используйте ревизию структуры программы"
            )
        if payload.effective_date is not None and payload.effective_date < today:
            raise ProgramError("Изменения должны относиться к будущим тренировкам")
        for week in weeks:
            existing_workout = (
                db.query(UserWorkout)
                .filter_by(user_program_id=program.id, week_number=week, day_number=selected_day)
                .first()
            )
            selected_plan = next(
                (
                    item
                    for item in _cycle_workout_plans(db, program, week)
                    if item["day_number"] == selected_day
                ),
                None,
            )
            if selected_plan is None:
                raise ProgramError("В выбранной неделе нет этой тренировки")
            scheduled = (
                existing_workout.scheduled_date
                if existing_workout
                else date.fromisoformat(selected_plan["scheduled_date"])
            )
            if scheduled < today and not payload.skip_protected:
                raise ProgramError("Изменения должны относиться к будущим тренировкам")
        scope: dict = (
            {"weeks": weeks}
            if explicit is not None
            else {"from_week": first_week, "source_cycle_week": payload.source_cycle_week}
        )
        if payload.source_cycle_week is not None:
            scope["source_cycle_boundary"] = cycle_boundary
        if explicit is None:
            scope["not_before_date"] = (payload.effective_date or today).isoformat()
        elif payload.skip_protected:
            scope["not_before_date"] = today.isoformat()
        if payload.effective_scope == "next_workout":
            if explicit is not None or payload.source_cycle_week is not None:
                raise ProgramError(
                    "Область ближайшей тренировки нельзя совмещать с повторением изменений"
                )
            materialize_cycle_schedule(db, program, today, today + timedelta(days=27))
            upcoming = (
                db.query(UserWorkout)
                .filter(
                    UserWorkout.user_program_id == program.id,
                    UserWorkout.status == "planned",
                    UserWorkout.day_number == selected_day,
                    UserWorkout.scheduled_date >= today,
                )
                .order_by(UserWorkout.scheduled_date, UserWorkout.id)
                .first()
            )
            if upcoming is None:
                raise ProgramError("No next planned workout for this revision")
            scope = {"weeks": [upcoming.week_number]}
        elif payload.effective_scope == "current_block":
            block = (
                db.query(TrainingBlock)
                .filter_by(user_program_id=program.id, status="active")
                .first()
            )
            if block is None:
                raise ProgramError("A current training block is required for this revision scope")
            scope["from_week"] = max(
                first_week, (block.start_date - program.start_date).days // 7 + 1
            )
            scope["to_week"] = (block.end_date - program.start_date).days // 7 + 1
        existing = []
        for row in db.query(UserWorkout).filter_by(
            user_program_id=program.id, day_number=selected_day
        ):
            if row.scheduled_date.isoformat() < scope.get("not_before_date", ""):
                continue
            if row.week_number is None:
                raise ProgramError("Для тренировки нет данных плана")
            config = _cycle_plan_at(db, program, row.week_number)
            if config is None:
                continue
            row_source = (row.week_number - config[2]) % config[0]["length_weeks"] + 1
            if _override_matches(scope, row.week_number, row_source, config[2]):
                if row.status == "cancelled" and explicit is None:
                    continue
                if (
                    payload.skip_protected
                    and row.status == "planned"
                    and not _workout_has_recorded_data(row)
                    and row.plan_materialized is not False
                    and (
                        row.source_cycle_week != row_source
                        or row.cycle_iteration
                        != (row.week_number - config[2]) // config[0]["length_weeks"] + 1
                    )
                ):
                    raise ProgramError(
                        "Откройте тренировку и обновите её план перед изменением упражнения"
                    )
                existing.append(row)
        if not payload.skip_protected and any(
            row.status != "planned" or row.started_at is not None or _workout_has_recorded_data(row)
            for row in existing
        ):
            raise ProgramError("Нельзя заменить начатую тренировку или записанные результаты")
        if payload.skip_protected:
            existing = [
                row
                for row in existing
                if row.status == "planned" and not _workout_has_recorded_data(row)
            ]
        override: dict = {
            **scope,
            "day_number": selected_day,
            "source_template_exercise_id": selected_slot,
            "exercise": {
                "exercise_id": payload.exercise_id,
                "metric_type": exercise_metric_type(exercise),
                "prescribed_sets": projection.prescribed_sets,
                "prescribed_reps": projection.prescribed_reps,
                "prescribed_duration_minutes": projection.prescribed_duration_minutes,
                "rest_seconds": projection.rest_seconds,
                "notes": payload.notes,
                "prescription": plan.model_dump(mode="json"),
            },
        }
        revision = record_program_revision(
            db,
            program,
            actor=actor,
            change_kind="plan_updated",
            reason=payload.reason,
            changed_fields={"occurrence_override": override},
        )
        db.flush()
        revisions = (
            db.query(ProgramRevision)
            .filter_by(user_program_id=program.id)
            .order_by(ProgramRevision.revision_number)
            .all()
        )
        indexed_sources: dict[int, dict[int, list[dict]]] = {}
        revised_sets = 0
        updated_count = 0
        for workout in existing:
            if workout.week_number is None or workout.day_number is None:
                raise ProgramError("Для тренировки нет данных плана")
            effective = next(
                (
                    item
                    for item in _cycle_workout_plans(
                        db,
                        program,
                        workout.week_number,
                        revisions=revisions,
                        source_index=indexed_sources,
                        scheduled_dates={workout.day_number: workout.scheduled_date},
                    )
                    if item["day_number"] == workout.day_number
                ),
                None,
            )
            if effective is None:
                continue
            target = next(
                (
                    item
                    for item in effective["exercises"]
                    if item.get("source_template_exercise_id") == selected_slot
                ),
                None,
            )
            if target is None:
                continue
            count = len(target["sets"])
            if (
                workout.plan_materialized is not False
                and revised_sets + count <= MAX_GENERATED_SETS
            ):
                _write_cycle_exercises(db, workout, effective, target_slot=selected_slot)
                revised_sets += count
                updated_count += 1
            elif workout.plan_materialized is False:
                workout.plan_revision_number = revision.revision_number
                updated_count += 1
        revision.snapshot = _build_program_snapshot(db, program)
        record_audit_event(
            db,
            actor_user_id=actor.id,
            target_user_id=program.user_id,
            action="program.exercise_upserted",
            resource_type="user_program",
            resource_id=program.id,
            details={"revision_number": revision.revision_number, "scope": scope},
        )
        db.commit()
        return updated_count, revision.revision_number

    if payload.skip_protected or any(
        value is not None
        for value in (payload.occurrence_weeks, payload.from_week, payload.source_cycle_week)
    ):
        raise ProgramError("У назначения нет сохранённого цикла")
    today = today_for_user(target_user)
    planned_workouts_query = (
        db.query(UserWorkout)
        .options(selectinload(UserWorkout.exercises))
        .filter(
            UserWorkout.user_program_id == program.id,
            UserWorkout.status == "planned",
        )
        .order_by(UserWorkout.scheduled_date.asc(), UserWorkout.id.asc())
    )
    if payload.effective_scope == "next_workout":
        future_workouts = planned_workouts_query.all()
        effective_date = future_workouts[0].scheduled_date if future_workouts else today
    else:
        effective_date = payload.effective_date or today
        if effective_date < today:
            raise ProgramError("A program revision cannot take effect in the past")
        future_workouts = planned_workouts_query.filter(
            UserWorkout.scheduled_date >= effective_date
        ).all()
    if payload.effective_scope == "current_block":
        active_block = (
            db.query(TrainingBlock)
            .filter(
                TrainingBlock.user_program_id == program.id,
                TrainingBlock.status == "active",
            )
            .first()
        )
        if active_block is None:
            raise ProgramError("A current training block is required for this revision scope")
        future_workouts = [
            workout
            for workout in future_workouts
            if active_block.start_date <= workout.scheduled_date <= active_block.end_date
        ]
    selected_day = payload.day_number
    if payload.effective_scope == "next_workout":
        next_workout = future_workouts[0] if future_workouts else None
        if next_workout is None:
            raise ProgramError("No next planned workout for this revision")
        if selected_day is not None and selected_day != next_workout.day_number:
            raise ProgramError("Next-workout scope cannot target a different program day")
        selected_day = next_workout.day_number
        planned_workouts = [next_workout]
    else:
        available_days = sorted(
            {_required_plan_number(workout.day_number) for workout in future_workouts}
        )
        if payload.target_template_exercise_id is None and selected_day is None:
            if len(available_days) != 1:
                raise ProgramError("Choose a program day for the exercise")
            selected_day = available_days[0]
        planned_workouts = (
            [workout for workout in future_workouts if workout.day_number == selected_day]
            if selected_day is not None
            else future_workouts
        )
    if not planned_workouts:
        raise ProgramError("No future planned workouts for the selected day")

    replacement_lineage: list[dict[str, object]] = []
    for workout in planned_workouts:
        workout_exercise = next(
            (
                row
                for row in workout.exercises
                if (
                    payload.target_template_exercise_id is not None
                    and row.source_template_exercise_id == payload.target_template_exercise_id
                )
                or (
                    payload.target_template_exercise_id is None
                    and row.exercise_id == payload.exercise_id
                )
            ),
            None,
        )
        if payload.target_template_exercise_id is not None and workout_exercise is None:
            continue
        preserve_existing_group = (
            workout_exercise is not None
            and payload.target_template_exercise_id is not None
            and payload.group_id is None
            and payload.group_kind is None
            and payload.group_order is None
            and payload.superset_group is None
            and payload.superset_order is None
        )
        candidate_group = (
            (
                workout_exercise.group_id
                if workout_exercise.group_id is not None
                else workout_exercise.superset_group,
                workout_exercise.group_kind
                or ("superset" if workout_exercise.superset_group else None),
                workout_exercise.group_order
                if workout_exercise.group_order is not None
                else workout_exercise.superset_order,
            )
            if preserve_existing_group and workout_exercise is not None
            else (
                payload.group_id if payload.group_id is not None else payload.superset_group,
                payload.group_kind or ("superset" if payload.superset_group else None),
                payload.group_order if payload.group_order is not None else payload.superset_order,
            )
        )
        _validate_workout_group_assignments(
            workout.exercises,
            target=workout_exercise,
            candidate=candidate_group,
        )
        if payload.superset_group is not None:
            conflict = next(
                (
                    row
                    for row in workout.exercises
                    if row.id != getattr(workout_exercise, "id", None)
                    and row.superset_group == payload.superset_group
                    and row.superset_order == payload.superset_order
                ),
                None,
            )
            if conflict is not None:
                raise ProgramError("Superset position is already occupied")
        if workout_exercise is None:
            workout_exercise = UserWorkoutExercise(
                workout_id=workout.id,
                exercise_id=payload.exercise_id,
                metric_type=exercise_metric_type(exercise),
                sort_order=max((row.sort_order for row in workout.exercises), default=0) + 1,
                prescribed_sets=projection.prescribed_sets,
                prescribed_reps=projection.prescribed_reps,
                prescribed_duration_minutes=projection.prescribed_duration_minutes,
                rest_seconds=projection.rest_seconds,
                notes=payload.notes,
                superset_group=payload.superset_group,
                superset_order=payload.superset_order,
                source_template_exercise_id=payload.target_template_exercise_id,
                group_id=payload.group_id or payload.superset_group,
                group_kind=payload.group_kind or ("superset" if payload.superset_group else None),
                group_order=payload.group_order or payload.superset_order,
                prescription=plan.model_dump(mode="json"),
            )
            db.add(workout_exercise)
            db.flush()
        else:
            original_exercise_id = workout_exercise.exercise_id
            superset_group = (
                workout_exercise.superset_group
                if preserve_existing_group
                else payload.superset_group
            )
            superset_order = (
                workout_exercise.superset_order
                if preserve_existing_group
                else payload.superset_order
            )
            group_id = (
                workout_exercise.group_id
                if preserve_existing_group
                else payload.group_id or payload.superset_group
            )
            group_kind = (
                workout_exercise.group_kind
                if preserve_existing_group
                else payload.group_kind or ("superset" if payload.superset_group else None)
            )
            group_order = (
                workout_exercise.group_order
                if preserve_existing_group
                else payload.group_order or payload.superset_order
            )
            workout_exercise.metric_type = exercise_metric_type(exercise)
            workout_exercise.exercise_id = payload.exercise_id
            workout_exercise.prescribed_sets = projection.prescribed_sets
            workout_exercise.prescribed_reps = projection.prescribed_reps
            workout_exercise.prescribed_duration_minutes = projection.prescribed_duration_minutes
            workout_exercise.rest_seconds = projection.rest_seconds
            workout_exercise.notes = payload.notes
            workout_exercise.superset_group = superset_group
            workout_exercise.superset_order = superset_order
            workout_exercise.group_id = group_id
            workout_exercise.group_kind = group_kind
            workout_exercise.group_order = group_order
            workout_exercise.prescription = plan.model_dump(mode="json")
            db.query(UserWorkoutSet).filter(
                UserWorkoutSet.workout_exercise_id == workout_exercise.id
            ).delete(synchronize_session=False)
            if payload.target_template_exercise_id is not None:
                replacement_lineage.append(
                    {
                        "workout_id": workout.id,
                        "workout_exercise_id": workout_exercise.id,
                        "from_exercise_id": original_exercise_id,
                        "to_exercise_id": payload.exercise_id,
                        "scope": "assigned_program",
                        "compatibility": "compatible_with_load_reset",
                        "load_reset_required": True,
                    }
                )

        group_kinds = {
            group["group_id"]: group["kind"] for group in plan.model_dump(mode="json")["groups"]
        }
        for set_number, segment in enumerate(plan.model_dump(mode="json")["segments"], start=1):
            db.add(
                UserWorkoutSet(
                    workout_exercise_id=workout_exercise.id,
                    set_number=set_number,
                    actual_reps=None,
                    actual_weight=None,
                    set_kind="working",
                    reached_failure=None,
                    is_completed=False,
                    planned_role=segment["role"],
                    planned_group_id=segment.get("group_id"),
                    planned_group_kind=group_kinds.get(segment.get("group_id")),
                    planned_position=segment["position"],
                    planned_round=segment.get("round_number"),
                )
            )

    workouts_updated = (
        len(replacement_lineage)
        if payload.target_template_exercise_id is not None
        else len(planned_workouts)
    )
    if payload.target_template_exercise_id is not None and not replacement_lineage:
        raise ProgramError("Target template exercise is not present in future planned workouts")

    revision = record_program_revision(
        db,
        program,
        actor=actor,
        change_kind="plan_updated",
        reason=payload.reason,
        changed_fields={
            "operation": (
                "exercise_replaced"
                if payload.target_template_exercise_id is not None
                else "prescription_updated"
                if payload.prescription is not None
                else "exercise_upserted"
            ),
            "day_number": selected_day,
            "exercise_id": payload.exercise_id,
            "workouts_updated": workouts_updated,
            "effective_scope": payload.effective_scope,
            "effective_date": effective_date.isoformat(),
            **(
                {
                    "target_template_exercise_id": payload.target_template_exercise_id,
                    "lineage": replacement_lineage,
                }
                if payload.target_template_exercise_id is not None
                else {}
            ),
        },
    )
    record_audit_event(
        db,
        actor_user_id=actor.id,
        target_user_id=program.user_id,
        action="program.exercise_upserted",
        resource_type="user_program",
        resource_id=program.id,
        details={
            "day_number": selected_day,
            "exercise_id": payload.exercise_id,
            "workouts_updated": workouts_updated,
            "revision_number": revision.revision_number,
        },
    )
    if role == "trainer":
        queue_notification(
            db,
            target_user,
            category="trainer_program_update",
            title="Программа тренировок изменена",
            body="Тренер обновил предстоящие тренировки. История изменений сохранена.",
            action_url="/app?section=programs",
        )
    db.commit()
    return workouts_updated, revision.revision_number
