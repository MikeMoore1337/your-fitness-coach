from __future__ import annotations

import hashlib
import json
from datetime import date, time

from sqlalchemy.orm import Session

from fitminiapp_api.core.timezone import now_for_user_naive, today_for_user
from fitminiapp_api.models.program import UserProgram, UserWorkout
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.workout import WorkoutRecoveryRequest
from fitminiapp_api.services.audit import record_audit_event
from fitminiapp_api.services.lifecycle_milestones import record_lifecycle_milestone
from fitminiapp_api.services.notifications import cancel_workout_reminder, queue_notification
from fitminiapp_api.services.program_versioning import record_program_revision

RULESET_VERSION = "schedule-recovery-v1"
RECOVERY_LIST_LIMIT = 5


class WorkoutRecoveryError(ValueError):
    def __init__(self, detail: str, *, status_code: int = 409) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _display_status(workout: UserWorkout, today: date) -> str:
    if workout.status == "planned" and workout.scheduled_date < today:
        return "missed"
    return workout.status


def serialize_schedule_item(workout: UserWorkout, current_user: User) -> dict:
    return {
        "id": workout.id,
        "scheduled_date": workout.scheduled_date,
        "scheduled_time": workout.scheduled_time,
        "title": workout.title,
        "status": _display_status(workout, today_for_user(current_user)),
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
    items: list[dict] = []
    for row in rows:
        if row.id == workout_id:
            if action == "skip":
                continue
            if action == "move" and scheduled_date is not None:
                item = serialize_schedule_item(row, current_user)
                item["scheduled_date"] = scheduled_date
                item["scheduled_time"] = scheduled_time
                item["status"] = "planned"
                items.append(item)
                continue
        items.append(serialize_schedule_item(row, current_user))
    return sorted(
        items,
        key=lambda item: (
            item["scheduled_date"],
            item["scheduled_time"] or time.max,
            item["id"],
        ),
    )[:RECOVERY_LIST_LIMIT]


def _next_workout(items: list[dict], current_user: User) -> dict | None:
    today = today_for_user(current_user)
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

    today = today_for_user(current_user)
    missed = (
        db.query(UserWorkout)
        .filter(
            UserWorkout.user_program_id == program.id,
            UserWorkout.status == "planned",
            UserWorkout.scheduled_date < today,
        )
        .order_by(UserWorkout.scheduled_date.asc(), UserWorkout.id.asc())
        .limit(RECOVERY_LIST_LIMIT)
        .all()
    )
    remaining = _workouts_for_recovery(db, program, current_user=current_user)
    return {
        "status": "missed" if missed else "clear",
        "missed_workouts": [serialize_schedule_item(row, current_user) for row in missed],
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
) -> str:
    document = {
        "ruleset_version": RULESET_VERSION,
        "workout_id": workout.id,
        "program_id": program.id,
        "revision_number": program.current_revision_number,
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
    if workout.status != "planned":
        raise WorkoutRecoveryError("Восстановить можно только запланированную тренировку")
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
    today = today_for_user(current_user)
    if payload.scheduled_date < today:
        raise WorkoutRecoveryError("Нельзя назначить тренировку в прошлом", status_code=422)
    now = now_for_user_naive(current_user)
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
            "Перенесём только эту тренировку. Упражнения, порядок и программа останутся прежними."
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
        message = "Отметим тренировку пропущенной. Будущие тренировки и программа не изменятся."
        remaining = _workouts_for_recovery(
            db,
            program,
            current_user=current_user,
            workout_id=workout.id,
            action="skip",
        )

    return {
        "status": "preview",
        "workout": serialize_schedule_item(workout, current_user),
        "action": payload.action,
        "ruleset_version": RULESET_VERSION,
        "changes": changes,
        "remaining_workouts": remaining,
        "warnings": [],
        "message": message,
        "preview_token": _preview_token(workout, program, payload),
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
        program.completed_at = now_for_user_naive(current_user)
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


def apply_recovery(
    db: Session,
    current_user: User,
    workout: UserWorkout,
    payload: WorkoutRecoveryRequest,
    preview_token: str,
) -> dict:
    program = _validate_request(db, current_user, workout, payload)
    preview = build_recovery_preview(db, current_user, workout, payload)
    if preview["status"] != "preview" or preview["preview_token"] != preview_token:
        raise WorkoutRecoveryError(
            "Расписание или условия изменились. Сформируйте preview заново",
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

    record_lifecycle_milestone(
        db,
        current_user,
        "recovery_action_confirmed",
        day_scope=True,
    )

    db.commit()
    remaining = _workouts_for_recovery(db, program, current_user=current_user)
    return {
        "applied_at": now_for_user_naive(current_user),
        "workout": serialize_schedule_item(workout, current_user),
        "remaining_workouts": remaining,
        "next_workout": _next_workout(remaining, current_user),
    }
