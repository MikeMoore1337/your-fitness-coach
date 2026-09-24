from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session, joinedload, selectinload

from fitminiapp_api.core.timezone import now_msk_naive, today_for_user
from fitminiapp_api.models.exercise import Muscle
from fitminiapp_api.models.program import (
    ProgramRevision,
    TrainingBlock,
    TrainingBlockPriorityMuscle,
    UserProgram,
    UserWorkout,
    UserWorkoutExercise,
    UserWorkoutSet,
)
from fitminiapp_api.models.user import CoachClient, User
from fitminiapp_api.schemas.program import (
    CoachProgramExerciseCreate,
    TrainingBlockCreate,
    TrainingBlockUpdate,
)
from fitminiapp_api.services.audit import record_audit_event
from fitminiapp_api.services.exercise_catalog import (
    _effective_exercise_id,
    _load_visible_exercise_rows,
)
from fitminiapp_api.services.notifications import queue_notification
from fitminiapp_api.services.prescription_semantics import ensure_plan
from fitminiapp_api.services.program_common import ProgramError
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
        query = query.with_for_update()
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
            "start_date": loaded.start_date.isoformat(),
            "duration_weeks": loaded.duration_weeks,
            "schedule_weekdays": list(loaded.schedule_weekdays),
            "status": loaded.status,
            "is_active": loaded.is_active,
            "current_revision_number": loaded.current_revision_number,
        },
        "workout_policy": "only_future_planned_workouts_are_structurally_mutable",
        "workouts": [
            {
                "id": workout.id,
                "scheduled_date": workout.scheduled_date.isoformat(),
                "day_number": workout.day_number,
                "week_number": workout.week_number,
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


def _ensure_expected_revision(program: UserProgram, expected_revision_number: int) -> None:
    if program.current_revision_number != expected_revision_number:
        raise ProgramError("Program revision conflict")


def _ensure_program_mutable(program: UserProgram) -> None:
    if not program.is_active or program.status not in MUTABLE_PROGRAM_STATUSES:
        raise ProgramError("Assigned program is not editable")


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
    workout_range = (
        db.query(UserWorkout.scheduled_date)
        .filter(UserWorkout.user_program_id == program.id)
        .order_by(UserWorkout.scheduled_date.asc())
        .all()
    )
    if workout_range:
        first_workout = workout_range[0][0]
        last_workout = workout_range[-1][0]
        if start_date < first_workout or end_date > last_workout:
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

    future_workouts = (
        db.query(UserWorkout)
        .options(selectinload(UserWorkout.exercises))
        .filter(
            UserWorkout.user_program_id == program.id,
            UserWorkout.status == "planned",
            UserWorkout.scheduled_date >= today_for_user(target_user),
        )
        .order_by(UserWorkout.scheduled_date.asc(), UserWorkout.id.asc())
        .all()
    )
    available_days = sorted({workout.day_number for workout in future_workouts})
    selected_day = payload.day_number
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
