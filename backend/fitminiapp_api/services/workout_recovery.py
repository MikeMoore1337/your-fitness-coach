from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from fitminiapp_api.core.timezone import (
    is_valid_timezone,
    local_naive_to_utc_naive,
    now_in_timezone_naive,
    today_in_timezone,
    utc_naive_to_timezone_naive,
)
from fitminiapp_api.models.lifecycle_milestone import LifecycleMilestone
from fitminiapp_api.models.program import ProgramRevision, UserProgram, UserWorkout
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.workout import WorkoutRecoveryRequest
from fitminiapp_api.services.audit import record_audit_event
from fitminiapp_api.services.lifecycle_milestones import record_lifecycle_milestone
from fitminiapp_api.services.notifications import cancel_workout_reminder, queue_notification
from fitminiapp_api.services.program_versioning import record_program_revision

RULESET_VERSION = "schedule-recovery-v2"
RECOVERY_LIST_LIMIT = 5


class WorkoutRecoveryError(ValueError):
    def __init__(self, detail: str, *, status_code: int = 409) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _account_timezone_name(user: User) -> str:
    profile_timezone = getattr(getattr(user, "profile", None), "timezone", None)
    return profile_timezone if profile_timezone and is_valid_timezone(profile_timezone) else "UTC"


def _recovery_today(user: User) -> date:
    return today_in_timezone(_account_timezone_name(user))


def _recovery_now_naive(user: User) -> datetime:
    return now_in_timezone_naive(_account_timezone_name(user))


def recovery_today_for_user(user: User) -> date:
    return _recovery_today(user)


def recovery_now_for_user_naive(user: User) -> datetime:
    return _recovery_now_naive(user)


def recovery_user_local_naive_to_utc_naive(value: datetime, user: User) -> datetime:
    return local_naive_to_utc_naive(value, _account_timezone_name(user))


def missed_at_for_workout(workout: UserWorkout, user: User) -> datetime:
    """Return the UTC-naive instant when the workout's local day ended."""

    return local_naive_to_utc_naive(
        datetime.combine(workout.scheduled_date + timedelta(days=1), time.min),
        _account_timezone_name(user),
    )


def _current_revision_workout_ids(db: Session, program: UserProgram) -> set[int] | None:
    """Read the current server snapshot when revision lineage is available.

    Legacy programs without a revision snapshot remain usable. A present current
    snapshot is authoritative and therefore fail-closed for workouts it no longer
    contains.
    """

    if program.current_revision_number <= 0:
        return None
    revision = (
        db.query(ProgramRevision.snapshot)
        .filter(
            ProgramRevision.user_program_id == program.id,
            ProgramRevision.revision_number == program.current_revision_number,
        )
        .first()
    )
    if revision is None or not isinstance(revision[0], dict):
        return set()
    snapshot_workouts = revision[0].get("workouts")
    if not isinstance(snapshot_workouts, list):
        return set()
    return {
        int(item["id"])
        for item in snapshot_workouts
        if isinstance(item, dict) and isinstance(item.get("id"), int)
    }


def _has_corresponding_active_or_completed_workout(
    db: Session,
    workout: UserWorkout,
) -> bool:
    return (
        db.query(UserWorkout.id)
        .filter(
            UserWorkout.user_program_id == workout.user_program_id,
            UserWorkout.id != workout.id,
            UserWorkout.scheduled_date == workout.scheduled_date,
            UserWorkout.day_number == workout.day_number,
            UserWorkout.week_number == workout.week_number,
            or_(
                UserWorkout.status.in_({"in_progress", "completed"}),
                UserWorkout.started_at.is_not(None),
                UserWorkout.completed_at.is_not(None),
            ),
        )
        .first()
        is not None
    )


def is_recoverable_missed_workout(
    db: Session,
    user: User,
    workout: UserWorkout,
    *,
    program: UserProgram | None = None,
    authoritative_workout_ids: set[int] | None = None,
) -> bool:
    program = program or workout.user_program
    if program is None or not program.is_active or program.status not in {"scheduled", "active"}:
        return False
    if workout.status != "planned" or workout.scheduled_date >= _recovery_today(user):
        return False
    if authoritative_workout_ids is not None and workout.id not in authoritative_workout_ids:
        return False
    if workout.started_at is not None or workout.completed_at is not None:
        return False
    return not _has_corresponding_active_or_completed_workout(db, workout)


def recoverable_missed_workouts(
    db: Session,
    user: User,
    program: UserProgram | None = None,
) -> list[UserWorkout]:
    program = program or _active_program(db, user)
    if program is None:
        return []
    today = _recovery_today(user)
    authoritative_workout_ids = _current_revision_workout_ids(db, program)
    rows = (
        db.query(UserWorkout)
        .filter(
            UserWorkout.user_program_id == program.id,
            UserWorkout.status == "planned",
            UserWorkout.scheduled_date < today,
        )
        .all()
    )
    return sorted(
        (
            row
            for row in rows
            if is_recoverable_missed_workout(
                db,
                user,
                row,
                program=program,
                authoritative_workout_ids=authoritative_workout_ids,
            )
        ),
        key=_workout_order_key,
    )


def recoverable_missed_workout_ids(db: Session, user: User) -> set[int]:
    return {row.id for row in recoverable_missed_workouts(db, user)}


def _workout_order_key(workout: UserWorkout) -> tuple:
    return (
        workout.week_number,
        workout.day_number,
        workout.scheduled_date,
        workout.scheduled_time or time.max,
        workout.id,
    )


def _item_order_key(item: dict) -> tuple:
    return (
        item["week_number"],
        item["day_number"],
        item["scheduled_date"],
        item["scheduled_time"] or time.max,
        item["id"],
    )


def serialize_schedule_item(
    workout: UserWorkout,
    current_user: User,
    *,
    status_override: str | None = None,
) -> dict:
    return {
        "id": workout.id,
        "scheduled_date": workout.scheduled_date,
        "scheduled_time": workout.scheduled_time,
        "title": workout.title,
        "status": status_override or workout.status,
        "day_number": workout.day_number,
        "week_number": workout.week_number,
    }


def _active_program(db: Session, current_user: User) -> UserProgram | None:
    return (
        db.query(UserProgram)
        .filter(
            UserProgram.user_id == current_user.id,
            UserProgram.is_active.is_(True),
            UserProgram.status.in_({"scheduled", "active"}),
        )
        .order_by(UserProgram.id.desc())
        .first()
    )


def _paused_program(db: Session, current_user: User) -> UserProgram | None:
    return (
        db.query(UserProgram)
        .filter(UserProgram.user_id == current_user.id, UserProgram.status == "paused")
        .order_by(UserProgram.id.desc())
        .first()
    )


def _workouts_for_recovery(
    db: Session,
    program: UserProgram,
    *,
    current_user: User,
    workout_id: int | None = None,
    action: str | None = None,
    scheduled_date: date | None = None,
    scheduled_time: time | None = None,
) -> list[dict]:
    rows = (
        db.query(UserWorkout)
        .filter(
            UserWorkout.user_program_id == program.id,
            UserWorkout.status.in_({"planned", "in_progress"}),
        )
        .order_by(
            UserWorkout.scheduled_date.asc(), UserWorkout.scheduled_time.asc(), UserWorkout.id.asc()
        )
        .all()
    )
    missed_ids = {row.id for row in recoverable_missed_workouts(db, current_user, program)}
    items: list[dict] = []
    for row in rows:
        if row.id == workout_id:
            if action == "skip":
                continue
            if action == "move" and scheduled_date is not None:
                item = serialize_schedule_item(row, current_user, status_override="planned")
                item["scheduled_date"] = scheduled_date
                item["scheduled_time"] = scheduled_time
                item["status"] = "planned"
                items.append(item)
                continue
        items.append(
            serialize_schedule_item(
                row,
                current_user,
                status_override="missed" if row.id in missed_ids else None,
            )
        )
    return sorted(items, key=_item_order_key)[:RECOVERY_LIST_LIMIT]


def _next_workout(items: list[dict], current_user: User) -> dict | None:
    today = _recovery_today(current_user)
    return next(
        (
            item
            for item in items
            if item["scheduled_date"] >= today and item["status"] in {"planned", "in_progress"}
        ),
        None,
    )


def recovery_state(db: Session, current_user: User) -> dict:
    program = _active_program(db, current_user)
    if program is None:
        paused = _paused_program(db, current_user)
        if paused is not None:
            return {
                "status": "paused",
                "missed_workouts": [],
                "next_workout": None,
                "paused_program_id": paused.id,
                "paused_program_title": paused.template.title if paused.template else None,
            }
        return {
            "status": "no_active_program",
            "missed_workouts": [],
            "next_workout": None,
            "paused_program_id": None,
            "paused_program_title": None,
        }

    missed = recoverable_missed_workouts(db, current_user, program)[:RECOVERY_LIST_LIMIT]
    remaining = _workouts_for_recovery(db, program, current_user=current_user)
    return {
        "status": "missed" if missed else "clear",
        "missed_workouts": [
            serialize_schedule_item(row, current_user, status_override="missed") for row in missed
        ],
        "next_workout": _next_workout(remaining, current_user),
        "paused_program_id": None,
        "paused_program_title": None,
    }


def _request_payload(payload: WorkoutRecoveryRequest) -> dict:
    return payload.model_dump(mode="json", exclude={"preview_token"}, exclude_none=True)


def _preview_token(
    workout: UserWorkout,
    program: UserProgram,
    payload: WorkoutRecoveryRequest,
    current_user: User,
) -> str:
    is_missed = workout.status == "planned" and workout.scheduled_date < _recovery_today(
        current_user
    )
    document = {
        "ruleset_version": RULESET_VERSION,
        "workout_id": workout.id,
        "program_id": program.id,
        "revision_number": program.current_revision_number,
        "timezone": _account_timezone_name(current_user),
        "derived_status": "missed" if is_missed else workout.status,
        "missed_at": (
            missed_at_for_workout(workout, current_user).isoformat() if is_missed else None
        ),
        "status": workout.status,
        "scheduled_date": workout.scheduled_date.isoformat(),
        "scheduled_time": workout.scheduled_time.isoformat() if workout.scheduled_time else None,
        "request": _request_payload(payload),
    }
    encoded = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _validate_request(
    db: Session,
    current_user: User,
    workout: UserWorkout,
    payload: WorkoutRecoveryRequest,
) -> UserProgram:
    program = workout.user_program
    if program is None or program.user_id != current_user.id:
        raise WorkoutRecoveryError("Тренировка не найдена", status_code=404)
    if not program.is_active or program.status not in {"scheduled", "active"}:
        raise WorkoutRecoveryError("Программа сейчас неактивна")
    authoritative_workout_ids = _current_revision_workout_ids(db, program)
    if authoritative_workout_ids is not None and workout.id not in authoritative_workout_ids:
        raise WorkoutRecoveryError("Расписание устарело. Сформируйте preview заново")
    if workout.status != "planned":
        raise WorkoutRecoveryError("Восстановить можно только запланированную тренировку")
    if workout.started_at is not None or workout.completed_at is not None:
        raise WorkoutRecoveryError("Тренировка уже имеет активный или завершённый результат")
    if (
        workout.scheduled_date != payload.expected_scheduled_date
        or workout.scheduled_time != payload.expected_scheduled_time
    ):
        raise WorkoutRecoveryError(
            "Расписание уже изменилось. Сформируйте preview заново",
        )

    if payload.action == "skip":
        return program

    assert payload.scheduled_date is not None
    if workout.scheduled_date < _recovery_today(current_user) and not is_recoverable_missed_workout(
        db,
        current_user,
        workout,
        program=program,
        authoritative_workout_ids=authoritative_workout_ids,
    ):
        raise WorkoutRecoveryError("Эта тренировка больше не доступна для восстановления")

    today = _recovery_today(current_user)
    if payload.scheduled_date < today:
        raise WorkoutRecoveryError("Нельзя назначить тренировку в прошлом", status_code=422)
    now = _recovery_now_naive(current_user)
    if (
        payload.scheduled_date == now.date()
        and payload.scheduled_time is not None
        and payload.scheduled_time < now.time()
    ):
        raise WorkoutRecoveryError("Нельзя назначить время в прошлом", status_code=422)
    if (
        payload.scheduled_date == workout.scheduled_date
        and payload.scheduled_time == workout.scheduled_time
    ):
        return program

    collision = (
        db.query(UserWorkout.id)
        .join(UserProgram, UserProgram.id == UserWorkout.user_program_id)
        .filter(
            UserProgram.user_id == current_user.id,
            UserProgram.is_active.is_(True),
            UserProgram.status.in_({"scheduled", "active"}),
            UserWorkout.id != workout.id,
            UserWorkout.scheduled_date == payload.scheduled_date,
            UserWorkout.status.notin_({"completed", "skipped", "cancelled"}),
        )
        .first()
    )
    if collision is not None:
        raise WorkoutRecoveryError("На эту дату уже назначена тренировка")
    return program


def build_recovery_preview(
    db: Session,
    current_user: User,
    workout: UserWorkout,
    payload: WorkoutRecoveryRequest,
) -> dict:
    program = _validate_request(db, current_user, workout, payload)
    no_changes = (
        payload.action == "move"
        and payload.scheduled_date == workout.scheduled_date
        and payload.scheduled_time == workout.scheduled_time
    )
    if no_changes:
        remaining = _workouts_for_recovery(db, program, current_user=current_user)
        return {
            "status": "no_changes",
            "workout": serialize_schedule_item(workout, current_user),
            "action": payload.action,
            "ruleset_version": RULESET_VERSION,
            "changes": [],
            "remaining_workouts": remaining,
            "warnings": [],
            "message": "Расписание уже содержит выбранную дату.",
            "preview_token": None,
        }

    if payload.action == "move":
        assert payload.scheduled_date is not None
        changes = [
            {
                "kind": "moved",
                "from_scheduled_date": workout.scheduled_date,
                "from_scheduled_time": workout.scheduled_time,
                "to_scheduled_date": payload.scheduled_date,
                "to_scheduled_time": payload.scheduled_time,
            }
        ]
        message = (
            "Изменится только дата этой тренировки. Упражнения, порядок и остальные тренировки "
            "останутся прежними."
        )
        remaining = _workouts_for_recovery(
            db,
            program,
            current_user=current_user,
            workout_id=workout.id,
            action="move",
            scheduled_date=payload.scheduled_date,
            scheduled_time=payload.scheduled_time,
        )
    else:
        changes = [
            {
                "kind": "skipped",
                "from_scheduled_date": workout.scheduled_date,
                "from_scheduled_time": workout.scheduled_time,
                "to_scheduled_date": None,
                "to_scheduled_time": None,
            }
        ]
        message = (
            "Тренировка будет отмечена пропущенной. Будущие тренировки и программа не изменятся."
        )
        remaining = _workouts_for_recovery(
            db,
            program,
            current_user=current_user,
            workout_id=workout.id,
            action="skip",
        )

    return {
        "status": "preview",
        "workout": serialize_schedule_item(
            workout,
            current_user,
            status_override=(
                "missed"
                if is_recoverable_missed_workout(db, current_user, workout, program=program)
                else None
            ),
        ),
        "action": payload.action,
        "ruleset_version": RULESET_VERSION,
        "changes": changes,
        "remaining_workouts": remaining,
        "warnings": [],
        "message": message,
        "preview_token": _preview_token(workout, program, payload, current_user),
    }


def _reconcile_program_completion(
    db: Session,
    program: UserProgram,
    current_user: User,
) -> None:
    remaining_workout = (
        db.query(UserWorkout.id)
        .filter(
            UserWorkout.user_program_id == program.id,
            UserWorkout.status.notin_({"completed", "skipped", "cancelled"}),
        )
        .first()
    )
    if remaining_workout is None and program.status != "completed":
        previous_status = program.status
        program.status = "completed"
        program.is_active = False
        program.completed_at = _recovery_now_naive(current_user)
        revision = record_program_revision(
            db,
            program,
            actor=current_user,
            change_kind="program_lifecycle",
            reason="Все тренировки программы завершены",
            changed_fields={
                "operation": "program_completed_from_schedule_recovery",
                "previous_status": previous_status,
                "status": program.status,
                "is_active": program.is_active,
            },
        )
        record_audit_event(
            db,
            actor_user_id=current_user.id,
            target_user_id=program.user_id,
            action="program.completed",
            resource_type="user_program",
            resource_id=program.id,
            details={"revision_number": revision.revision_number},
        )


def _apply_result(
    db: Session,
    current_user: User,
    program: UserProgram,
    workout: UserWorkout,
    *,
    applied_at: datetime,
) -> dict:
    remaining = _workouts_for_recovery(db, program, current_user=current_user)
    return {
        "applied_at": applied_at,
        "workout": serialize_schedule_item(workout, current_user),
        "remaining_workouts": remaining,
        "next_workout": _next_workout(remaining, current_user),
    }


def _idempotent_apply_result(
    db: Session,
    current_user: User,
    workout: UserWorkout,
    payload: WorkoutRecoveryRequest,
) -> dict | None:
    event = (
        db.query(LifecycleMilestone)
        .filter(
            LifecycleMilestone.user_id == current_user.id,
            LifecycleMilestone.milestone_type == "recovery_action_confirmed",
            LifecycleMilestone.workout_id == workout.id,
        )
        .first()
    )
    if event is None:
        return None
    if payload.action == "skip" and workout.status != "skipped":
        return None
    if payload.action == "move" and not (
        workout.status == "planned"
        and payload.scheduled_date == workout.scheduled_date
        and payload.scheduled_time == workout.scheduled_time
    ):
        return None
    program = workout.user_program
    if program is None:
        return None
    applied_at = utc_naive_to_timezone_naive(
        event.occurred_at,
        _account_timezone_name(current_user),
    )
    return _apply_result(
        db,
        current_user,
        program,
        workout,
        applied_at=applied_at,
    )


def apply_recovery(
    db: Session,
    current_user: User,
    workout: UserWorkout,
    payload: WorkoutRecoveryRequest,
    preview_token: str,
) -> dict:
    replay = _idempotent_apply_result(db, current_user, workout, payload)
    if replay is not None:
        return replay

    program = _validate_request(db, current_user, workout, payload)
    preview = build_recovery_preview(db, current_user, workout, payload)
    if preview["status"] != "preview" or preview["preview_token"] != preview_token:
        raise WorkoutRecoveryError(
            "Расписание или условия изменились. Сформируйте preview заново",
        )

    authoritative_workout_ids = _current_revision_workout_ids(db, program)
    was_missed = is_recoverable_missed_workout(
        db,
        current_user,
        workout,
        program=program,
        authoritative_workout_ids=authoritative_workout_ids,
    )
    missed_at = missed_at_for_workout(workout, current_user) if was_missed else None
    missed_revision_number = program.current_revision_number
    confirmed_at_local = _recovery_now_naive(current_user)
    confirmed_at_utc = local_naive_to_utc_naive(
        confirmed_at_local,
        _account_timezone_name(current_user),
    )

    previous_date = workout.scheduled_date
    previous_time = workout.scheduled_time
    if payload.action == "move":
        assert payload.scheduled_date is not None
        workout.scheduled_date = payload.scheduled_date
        workout.scheduled_time = payload.scheduled_time
        operation = "workout_recovery_move"
    else:
        workout.status = "skipped"
        cancel_workout_reminder(db, workout.id)
        operation = "workout_recovery_skip"

    revision = record_program_revision(
        db,
        program,
        actor=current_user,
        change_kind="plan_updated",
        reason="Восстановление расписания после пропуска",
        changed_fields={
            "operation": operation,
            "workout_id": workout.id,
            "previous_scheduled_date": previous_date.isoformat(),
            "previous_scheduled_time": previous_time.isoformat() if previous_time else None,
            "scheduled_date": workout.scheduled_date.isoformat(),
            "scheduled_time": workout.scheduled_time.isoformat()
            if workout.scheduled_time
            else None,
            "status": workout.status,
        },
    )
    record_audit_event(
        db,
        actor_user_id=current_user.id,
        target_user_id=program.user_id,
        action=f"workout.{operation}",
        resource_type="user_workout",
        resource_id=workout.id,
        details={"program_id": program.id, "revision_number": revision.revision_number},
    )
    if (
        payload.action == "move"
        and program.assigned_by_user_id
        and program.assigned_by_user_id != current_user.id
    ):
        trainer = db.query(User).filter(User.id == program.assigned_by_user_id).first()
        if trainer is not None and trainer.is_active:
            time_text = f" в {workout.scheduled_time:%H:%M}" if workout.scheduled_time else ""
            queue_notification(
                db,
                trainer,
                category="workout_change",
                title="Клиент изменил тренировку",
                body=(
                    f"Клиент перенёс тренировку «{workout.title}» на "
                    f"{workout.scheduled_date:%d.%m.%Y}{time_text}."
                ),
                action_url="/app?section=progress",
            )
    if payload.action == "skip":
        _reconcile_program_completion(db, program, current_user)

    if was_missed and missed_at is not None:
        record_lifecycle_milestone(
            db,
            current_user,
            "workout_missed",
            occurred_at=missed_at,
            workout_id=workout.id,
            program_id=program.id,
            program_revision_number=missed_revision_number,
            missed_at=missed_at,
        )
    record_lifecycle_milestone(
        db,
        current_user,
        "recovery_action_confirmed",
        occurred_at=confirmed_at_utc,
        workout_id=workout.id,
        program_id=program.id,
        program_revision_number=program.current_revision_number,
        missed_at=missed_at if was_missed and payload.action == "move" else None,
    )

    db.commit()
    return _apply_result(
        db,
        current_user,
        program,
        workout,
        applied_at=confirmed_at_local,
    )
