from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from fitminiapp_api.core.timezone import now_msk_naive, today_for_user
from fitminiapp_api.models.exercise import Muscle
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
    ProgramLifecycleActionRequest,
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
from fitminiapp_api.services.program_common import MAX_PROGRAM_DURATION_WEEKS, ProgramError
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


def _lifecycle_block_summary(
    block: TrainingBlock,
    workouts: list[UserWorkout],
) -> dict[str, object]:
    block_weeks = [
        workout.week_number
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
    workouts = (
        db.query(UserWorkout)
        .filter(UserWorkout.user_program_id == program.id)
        .order_by(UserWorkout.scheduled_date.asc(), UserWorkout.id.asc())
        .all()
    )
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
    program, _role = get_program_for_actor(db, actor, program_id, lock=True)
    _ensure_expected_revision(program, payload.expected_revision_number)
    owner = db.query(User).filter(User.id == program.user_id).with_for_update().one()
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
            if workout.scheduled_date < program.start_date:
                raise ProgramError("Program contains a workout before its start date")
            _copy_scheduled_workout(
                db,
                workout,
                program_id=new_program.id,
                scheduled_date=workout.scheduled_date + date_shift,
                week_number=workout.week_number,
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
        record_program_revision(
            db,
            new_program,
            actor=actor,
            change_kind="program_restarted",
            reason=payload.reason,
            changed_fields={
                "source_program_id": program.id,
                "history_boundary": "new_program",
                "workouts_created": len(source_workouts),
            },
        )
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
) -> tuple[UserProgram, int, int]:
    program, role = get_program_for_actor(db, actor, program_id, lock=True)
    _ensure_program_mutable(program)
    _ensure_expected_revision(program, expected_revision_number)
    if program.duration_weeks != template.effective_duration_weeks:
        raise ProgramError("Imported duration must match the assigned program")

    loaded_template = (
        db.query(ProgramTemplate)
        .options(
            selectinload(ProgramTemplate.days)
            .selectinload(ProgramTemplateDay.exercises)
            .selectinload(ProgramTemplateExercise.weekly_prescriptions)
        )
        .filter(ProgramTemplate.id == template.id)
        .one()
    )
    days_by_number = {day.day_number: day for day in loaded_template.days}
    expected_pairs = {
        (week_number, day_number)
        for week_number in range(1, program.duration_weeks + 1)
        for day_number in days_by_number
    }
    all_workouts = (
        db.query(UserWorkout)
        .filter(UserWorkout.user_program_id == program.id)
        .order_by(UserWorkout.week_number, UserWorkout.day_number)
        .all()
    )
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
            UserWorkout.scheduled_date >= today_for_user(target_user),
        )
        .order_by(UserWorkout.scheduled_date.asc(), UserWorkout.id.asc())
        .all()
    )
    for workout in future_workouts:
        day = days_by_number[workout.day_number]
        workout.title = day.title
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
            exercise_id = (
                weekly.exercise_id if weekly is not None else template_exercise.exercise_id
            )
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
            "operation": "program_rollout" if rollout_id is not None else "program_import_revision",
            "import_id": import_id,
            "previous_template_id": prior_template_id,
            "template_id": loaded_template.id,
            "workouts_updated": len(future_workouts),
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
    if role == "trainer":
        queue_notification(
            db,
            target_user,
            category="trainer_program_update",
            title="Программа тренировок изменена",
            body="Тренер обновил предстоящие тренировки. История изменений сохранена.",
            action_url="/app?section=programs",
        )
    db.flush()
    return program, len(future_workouts), revision.revision_number


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
    first_source_week = min(workout.week_number for workout in workouts)
    last_source_week = max(workout.week_number for workout in workouts)
    source_week_start = program.start_date + timedelta(weeks=first_source_week - 1)
    start_offset = (source.start_date - source_week_start).days
    duration_days = (source.end_date - source.start_date).days + 1
    additional_weeks = max(
        last_source_week - first_source_week + 1,
        (start_offset + duration_days + 6) // 7,
    )
    old_duration_weeks = program.duration_weeks
    next_duration = old_duration_weeks + additional_weeks
    if next_duration > MAX_PROGRAM_DURATION_WEEKS:
        raise ProgramError(
            f"Program reached its {MAX_PROGRAM_DURATION_WEEKS}-week limit; restart it to begin a new cycle"
        )
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
        available_days = sorted({workout.day_number for workout in future_workouts})
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
