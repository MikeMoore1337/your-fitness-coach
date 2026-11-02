from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session, selectinload

from fitminiapp_api.core.timezone import today_for_user
from fitminiapp_api.models.exercise import Exercise
from fitminiapp_api.models.notification import Notification
from fitminiapp_api.models.program import (
    ProgramRevision,
    UserProgram,
    UserWorkout,
    UserWorkoutExercise,
)
from fitminiapp_api.models.user import CoachClient, User
from fitminiapp_api.schemas.program import (
    SessionRotationExtendRequest,
    SessionRotationSettingsRequest,
)
from fitminiapp_api.schemas.workout import (
    SessionRotationActionRequest,
    SessionRotationTransitionRequest,
)
from fitminiapp_api.services.audit import record_audit_event
from fitminiapp_api.services.lifecycle_milestones import record_lifecycle_milestone
from fitminiapp_api.services.notifications import cancel_workout_reminder
from fitminiapp_api.services.program_versioning import (
    _copy_scheduled_workout,
    _cycle_configurations,
    _cycle_occurrence_overrides,
    _cycle_plan_at,
    _cycle_plan_sets,
    _cycle_workout_plans,
    _ensure_cycle_plan_editor,
    _ensure_expected_revision,
    _ensure_program_mutable,
    _workout_has_recorded_data,
    _write_cycle_exercises,
    get_program_for_actor,
    record_program_revision,
)
from fitminiapp_api.services.workout_recovery import recovery_utc_naive_to_user_local


class SessionRotationError(ValueError):
    def __init__(self, detail: str, status_code: int = 409) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _hash(value: object) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _owner(db: Session, program: UserProgram) -> User:
    owner = db.get(User, program.user_id)
    if owner is None:
        raise SessionRotationError("Программа не найдена", 404)
    return owner


def _calendar_week(program: UserProgram, today) -> int:
    return max(1, min(program.duration_weeks, (today - program.start_date).days // 7 + 1))


def _days(db: Session, program: UserProgram) -> list[dict]:
    week = _calendar_week(program, today_for_user(_owner(db, program)))
    plans = _cycle_workout_plans(db, program, week)
    if plans:
        return [{"day_number": plan["day_number"], "title": plan["title"]} for plan in plans]
    rows = (
        db.query(UserWorkout)
        .filter(
            UserWorkout.user_program_id == program.id,
            UserWorkout.rotation_epoch.is_(None),
        )
        .order_by(UserWorkout.week_number, UserWorkout.scheduled_date, UserWorkout.id)
        .all()
    )
    days: dict[int, dict] = {}
    for row in rows:
        if row.day_number is not None and row.status != "cancelled":
            days.setdefault(row.day_number, {"day_number": row.day_number, "title": row.title})
    known = {row.day_number for row in rows}
    if program.template is not None:
        for day in program.template.days:
            if day.day_number not in known:
                days[day.day_number] = {
                    "day_number": day.day_number,
                    "title": day.title,
                    "from_template": True,
                }
    return [days[number] for number in sorted(days)]


def _supplement_plans(db: Session, program: UserProgram, days: list[dict]) -> list[dict]:
    missing = {day["day_number"] for day in days if day.get("from_template")}
    if not missing or program.template is None:
        return []
    from fitminiapp_api.services.exercise_catalog import get_visible_exercise_display_map
    from fitminiapp_api.services.programs import _group_projection, _input_prescription
    from fitminiapp_api.services.workout_metrics import exercise_metric_type

    old_revision = (
        db.query(ProgramRevision)
        .filter_by(user_program_id=program.id, revision_number=program.rotation_epoch)
        .first()
        if program.rotation_epoch is not None
        else None
    )
    previous = {
        item["day_number"]: item
        for item in (
            old_revision.changed_fields.get("rotation_supplement_plans", []) if old_revision else []
        )
    }
    visible = get_visible_exercise_display_map(db, _owner(db, program))
    result = []
    for day in sorted(program.template.days, key=lambda item: item.day_number):
        if day.day_number not in missing:
            continue
        if day.day_number in previous:
            result.append(previous[day.day_number])
            continue
        exercises = []
        for slot in sorted(day.exercises, key=lambda item: item.sort_order):
            weekly = next(
                (item for item in slot.weekly_prescriptions if item.week_number == 1), None
            )
            exercise_id = weekly.exercise_id if weekly else slot.exercise_id
            exercise = visible.get(exercise_id)
            if exercise is None:
                raise SessionRotationError("Упражнение из шаблона недоступно владельцу программы")
            source = weekly or slot
            structured = bool(
                (weekly and weekly.prescription is not None) or slot.prescription is not None
            )
            plan, projection = _input_prescription(
                exercise,
                prescription=(weekly.prescription if weekly else None) or slot.prescription,
                prescribed_sets=source.prescribed_sets,
                prescribed_reps=source.prescribed_reps,
                prescribed_duration_minutes=source.prescribed_duration_minutes,
                rest_seconds=source.rest_seconds,
            )
            sets = _cycle_plan_sets(plan)
            if not structured:
                for item in sets:
                    for key in (
                        "planned_role",
                        "planned_position",
                        "planned_group_id",
                        "planned_group_kind",
                        "planned_round",
                    ):
                        item[key] = None
            group_id, group_kind, group_order = _group_projection(slot)
            exercises.append(
                {
                    "exercise_id": exercise_id,
                    "metric_type": exercise_metric_type(exercise),
                    "sort_order": slot.sort_order,
                    "source_template_exercise_id": slot.id,
                    "source_assignment_slot_id": None,
                    "source_weekly_prescription_id": weekly.id if weekly else None,
                    "prescribed_sets": projection.prescribed_sets,
                    "prescribed_reps": projection.prescribed_reps,
                    "prescribed_duration_minutes": projection.prescribed_duration_minutes,
                    "rest_seconds": projection.rest_seconds,
                    "notes": slot.notes,
                    "superset_group": slot.superset_group,
                    "superset_order": slot.superset_order,
                    "group_id": group_id,
                    "group_kind": group_kind,
                    "group_order": group_order,
                    "prescription": plan if structured else None,
                    "sets": sets,
                }
            )
        result.append(
            {
                "day_number": day.day_number,
                "week_number": 1,
                "title": day.title,
                "source_cycle_week": None,
                "cycle_iteration": None,
                "exercises": exercises,
            }
        )
    return result


def _reminder_workout_ids(db: Session, program: UserProgram) -> list[int]:
    return [
        row.id
        for row in db.query(UserWorkout.id)
        .filter(
            UserWorkout.user_program_id == program.id,
            UserWorkout.rotation_epoch.is_(None),
            UserWorkout.status == "planned",
        )
        .all()
    ]


def _reminder_count(db: Session, program: UserProgram) -> int:
    return len(_reminders(db, program))


def _calendar_options(db: Session, program: UserProgram) -> list[dict]:
    today = today_for_user(_owner(db, program))
    start = max(today, program.start_date)
    end = min(
        today + timedelta(days=min(27, (date.max - today).days)),
        program.start_date + timedelta(days=program.duration_weeks * 7 - 1),
    )
    if end < start:
        return []
    rows = (
        db.query(UserWorkout)
        .filter(UserWorkout.user_program_id == program.id, UserWorkout.rotation_epoch.is_(None))
        .all()
    )
    if _cycle_plan_at(db, program, program.duration_weeks) is None:
        return [
            {
                "week_number": row.week_number,
                "day_number": row.day_number,
                "scheduled_date": row.scheduled_date.isoformat(),
                "title": row.title,
            }
            for row in sorted(rows, key=lambda item: (item.scheduled_date, item.id))
            if row.status == "planned" and start <= row.scheduled_date <= end
        ]
    existing = {(row.week_number, row.day_number): row for row in rows}
    options = []
    first = max(1, (start - program.start_date).days // 7 + 1)
    last = min(program.duration_weeks, (end - program.start_date).days // 7 + 1)
    for week in range(first, last + 1):
        for plan in _cycle_workout_plans(db, program, week):
            row = existing.get((week, plan["day_number"]))
            if row is not None and row.status != "planned":
                continue
            scheduled = row.scheduled_date if row else date.fromisoformat(plan["scheduled_date"])
            if start <= scheduled <= end:
                options.append(
                    {
                        "week_number": week,
                        "day_number": plan["day_number"],
                        "scheduled_date": scheduled.isoformat(),
                        "title": row.title if row else plan["title"],
                    }
                )
    return sorted(
        options, key=lambda item: (item["scheduled_date"], item["week_number"], item["day_number"])
    )


def _reminders(db: Session, program: UserProgram) -> list[dict]:
    workouts = (
        db.query(UserWorkout)
        .filter(
            UserWorkout.user_program_id == program.id,
            UserWorkout.rotation_epoch.is_(None),
            UserWorkout.status == "planned",
        )
        .all()
    )
    by_key = {f"workout:{item.id}:reminder": item for item in workouts}
    if not by_key:
        return []
    reminders = (
        db.query(Notification)
        .filter(
            Notification.user_id == program.user_id,
            Notification.dedupe_key.in_(by_key),
            Notification.status.in_(("queued", "processing", "failed")),
        )
        .order_by(Notification.id)
        .all()
    )
    return [
        {
            "workout_id": by_key[item.dedupe_key or ""].id,
            "title": by_key[item.dedupe_key or ""].title,
            "scheduled_date": by_key[item.dedupe_key or ""].scheduled_date.isoformat(),
            "status": item.status,
        }
        for item in reminders
    ]


def settings(db: Session, actor: User, program_id: int) -> dict:
    program, _ = get_program_for_actor(db, actor, program_id)
    return {
        "program_id": program.id,
        "mode": program.schedule_mode,
        "revision_number": program.current_revision_number,
        "days": _days(db, program),
        "first_day_number": program.rotation_first_day,
        "future_reminders": _reminder_count(db, program),
        "calendar_options": _calendar_options(db, program)
        if program.schedule_mode == "rotation"
        else [],
    }


def preview_settings(
    db: Session, actor: User, program_id: int, payload: SessionRotationSettingsRequest
) -> dict:
    program, _ = get_program_for_actor(db, actor, program_id)
    _ensure_program_mutable(program)
    _ensure_expected_revision(program, payload.expected_revision_number)
    days = _days(db, program)
    if payload.mode == "rotation" and payload.first_day_number not in {
        day["day_number"] for day in days
    }:
        raise SessionRotationError("Выберите доступную тренировку", 422)
    in_progress = (
        db.query(UserWorkout.id)
        .filter(UserWorkout.user_program_id == program.id, UserWorkout.status == "in_progress")
        .first()
    )
    if in_progress:
        raise SessionRotationError("Сначала завершите или отмените начатую тренировку")
    if program.schedule_mode == "rotation":
        previous = _state(db, program, _owner(db, program))
        if previous["current"] and previous["current"].get("status") == "cancelled":
            raise SessionRotationError("Сначала восстановите незавершённую тренировку")
    options = (
        _calendar_options(db, program)
        if payload.mode == "calendar" and program.schedule_mode == "rotation"
        else []
    )
    selected = next(
        (
            item
            for item in options
            if item["week_number"] == payload.resume_calendar_week
            and item["day_number"] == payload.resume_calendar_day
        ),
        None,
    )
    if payload.mode == "calendar" and program.schedule_mode == "rotation" and selected is None:
        raise SessionRotationError(
            "Выберите доступную тренировку для возвращения к расписанию", 422
        )
    reminders = _reminders(db, program) if payload.mode == "rotation" else []
    supplement = _supplement_plans(db, program, days) if payload.mode == "rotation" else []
    exercise_ids = {item["exercise_id"] for plan in supplement for item in plan["exercises"]}
    titles = {row.id: row.title for row in db.query(Exercise).filter(Exercise.id.in_(exercise_ids))}
    result: dict = {
        "program_id": program.id,
        "mode": payload.mode,
        "revision_number": program.current_revision_number,
        "days": days,
        "first_day_number": payload.first_day_number,
        "future_reminders": len(reminders),
        "reminders": reminders,
        "calendar_options": options,
        "calendar_resume": selected,
        "template_plans": [
            {
                "day_number": plan["day_number"],
                "title": plan["title"],
                "week_number": 1,
                "exercises": [
                    {
                        "title": titles.get(item["exercise_id"], "Упражнение"),
                        "prescribed_sets": item["prescribed_sets"],
                        "prescribed_reps": item["prescribed_reps"],
                    }
                    for item in plan["exercises"]
                ],
            }
            for plan in supplement
        ],
        "_supplement_snapshot": supplement,
    }
    result["preview_token"] = _hash(result)
    return result


def apply_settings(
    db: Session,
    actor: User,
    program_id: int,
    payload: SessionRotationSettingsRequest,
    preview_token: str,
) -> dict:
    program, _ = get_program_for_actor(db, actor, program_id, lock=True)
    last_revision = (
        db.query(ProgramRevision)
        .filter_by(user_program_id=program.id, revision_number=program.current_revision_number)
        .first()
    )
    if (
        last_revision
        and last_revision.changed_fields.get("rotation_preview_token") == preview_token
    ):
        if last_revision.changed_fields.get("rotation_settings_hash") != _hash(
            payload.model_dump(mode="json")
        ):
            raise SessionRotationError("Повтор запроса отличается от сохранённого действия")
        return settings(db, actor, program_id)
    _ensure_cycle_plan_editor(db, program, actor)
    _ensure_program_mutable(program)
    _ensure_expected_revision(program, payload.expected_revision_number)
    preview = preview_settings(db, actor, program_id, payload)
    if preview["preview_token"] != preview_token:
        raise SessionRotationError("Программа изменилась. Проверьте настройки ещё раз")
    program.schedule_mode = payload.mode
    program.rotation_first_day = payload.first_day_number
    program.rotation_epoch = (
        program.current_revision_number + 1 if payload.mode == "rotation" else None
    )
    program.rotation_accepted_revision = program.rotation_epoch
    if payload.mode == "rotation":
        for workout_id in _reminder_workout_ids(db, program):
            cancel_workout_reminder(db, workout_id)
    record_program_revision(
        db,
        program,
        actor=actor,
        change_kind="plan_updated",
        reason="Изменён порядок тренировок",
        changed_fields={
            "operation": "session_rotation_mode",
            "rotation_preview_token": preview_token,
            "rotation_settings_hash": _hash(payload.model_dump(mode="json")),
            "rotation_days": preview["days"] if payload.mode == "rotation" else [],
            "rotation_supplement_plans": preview["_supplement_snapshot"],
            "rotation_effective_date": (
                preview["calendar_resume"]["scheduled_date"]
                if preview["calendar_resume"]
                else today_for_user(_owner(db, program)).isoformat()
            ),
            "mode": payload.mode,
        },
    )
    db.commit()
    return settings(db, actor, program_id)


def _active_program(db: Session, owner: User, *, lock: bool = False) -> UserProgram | None:
    query = db.query(UserProgram).filter(
        UserProgram.user_id == owner.id,
        UserProgram.is_active.is_(True),
        UserProgram.status.in_({"scheduled", "active"}),
    )
    if lock:
        query = query.populate_existing().with_for_update()
    return query.first()


def _state(db: Session, program: UserProgram, owner: User) -> dict:
    epoch = program.rotation_epoch
    if epoch is None:
        raise SessionRotationError("Не удалось определить очередь программы. Откройте настройки")
    revision = (
        db.query(ProgramRevision)
        .filter_by(user_program_id=program.id, revision_number=epoch)
        .first()
    )
    if revision is None:
        raise SessionRotationError("Не удалось определить очередь программы. Откройте настройки")
    days = [dict(item) for item in revision.changed_fields.get("rotation_days", [])]
    if not days:
        raise SessionRotationError("Не удалось определить очередь программы. Откройте настройки")
    events = (
        db.query(UserWorkout)
        .filter_by(user_program_id=program.id, rotation_epoch=epoch)
        .order_by(UserWorkout.id)
        .all()
    )
    consumed = next(
        (
            item
            for item in reversed(events)
            if item.rotation_role == "ordered" and item.status in {"completed", "skipped"}
        ),
        None,
    )
    active = next((item for item in reversed(events) if item.status == "in_progress"), None)
    cancelled = next(
        (item for item in reversed(events) if item.status == "cancelled" and item.started_at), None
    )
    if cancelled and any(item.id > cancelled.id and item.status != "cancelled" for item in events):
        cancelled = None
    numbers = [item["day_number"] for item in days]
    next_number = program.rotation_first_day
    if consumed and consumed.day_number in numbers:
        next_number = numbers[(numbers.index(consumed.day_number) + 1) % len(numbers)]
    queued = next((item for item in days if item["day_number"] == next_number), None)
    following = days[(numbers.index(next_number) + 1) % len(days)] if queued is not None else None
    current = dict(queued) if queued is not None else None
    next_day = dict(following) if following is not None else None
    current_workout = active or cancelled
    if current_workout is not None:
        current = {
            "day_number": current_workout.day_number,
            "title": current_workout.title,
            "workout_id": current_workout.id,
            "status": current_workout.status,
        }
        if current_workout.rotation_role == "extra":
            next_day = queued
    needs_review = (
        db.query(ProgramRevision.id)
        .filter(
            ProgramRevision.user_program_id == program.id,
            ProgramRevision.revision_number > (program.rotation_accepted_revision or 0),
            ProgramRevision.change_kind == "plan_updated",
        )
        .first()
        is not None
    )
    today = today_for_user(owner)
    end = program.start_date + timedelta(days=program.duration_weeks * 7 - 1)
    default_weeks: dict[int, int] = {}
    if program.duration_weeks == 1:
        default_weeks = dict.fromkeys(numbers, 1)
    else:
        calendar_week = _calendar_week(program, today)
        config = _cycle_plan_at(db, program, calendar_week)
        if (
            config is not None
            and config[0]["length_weeks"] == 1
            and config[0]["repeat"]
            and not _cycle_configurations(db, program)
            and not _cycle_occurrence_overrides(db, program.id)
            and set(numbers).issubset(
                {item["day_number"] for item in _cycle_workout_plans(db, program, calendar_week)}
            )
        ):
            default_weeks = dict.fromkeys(numbers, calendar_week)
        elif config is None:
            changed = any(
                row.changed_fields.get("operation") != "session_rotation_mode"
                for row in db.query(ProgramRevision.changed_fields).filter_by(
                    user_program_id=program.id, change_kind="plan_updated"
                )
            )
            weekly = (
                db.query(UserWorkoutExercise.id)
                .join(UserWorkout, UserWorkout.id == UserWorkoutExercise.workout_id)
                .filter(
                    UserWorkout.user_program_id == program.id,
                    UserWorkout.rotation_epoch.is_(None),
                    UserWorkoutExercise.source_weekly_prescription_id.is_not(None),
                )
                .first()
            )
            supplement = revision.changed_fields.get("rotation_supplement_plans", [])
            if (
                not changed
                and weekly is None
                and not any(
                    item.get("source_weekly_prescription_id")
                    for plan in supplement
                    for item in plan["exercises"]
                )
            ):
                slots = (
                    db.query(UserWorkout.day_number, UserWorkout.week_number)
                    .filter(
                        UserWorkout.user_program_id == program.id,
                        UserWorkout.rotation_epoch.is_(None),
                        UserWorkout.status != "cancelled",
                    )
                    .order_by(UserWorkout.week_number)
                    .all()
                )
                for day_number, week_number in slots:
                    if day_number in numbers and week_number is not None:
                        default_weeks.setdefault(day_number, week_number)
                for plan in supplement:
                    default_weeks.setdefault(plan["day_number"], 1)
    for day in days:
        day["default_plan_week"] = default_weeks.get(day["day_number"])
    if current is not None:
        current["default_plan_week"] = default_weeks.get(current["day_number"])
    default_week = current["default_plan_week"] if current is not None else None
    if current_workout is not None and current is not None:
        current["exercise_count"] = len(current_workout.exercises)
        current["set_count"] = sum(len(item.sets) for item in current_workout.exercises)
    elif current and default_week is not None:
        try:
            planned, source = _plan(db, program, current["day_number"], default_week)
        except SessionRotationError:
            default_week = None
        else:
            if planned is not None:
                current["exercise_count"] = len(planned["exercises"])
                current["set_count"] = sum(len(item["sets"]) for item in planned["exercises"])
            elif source is not None:
                current["exercise_count"] = len(source.exercises)
                current["set_count"] = sum(len(item.sets) for item in source.exercises)
    status = (
        "in_progress"
        if active
        else "expired"
        if today > end
        else "cancelled"
        if cancelled
        else "review_required"
        if needs_review
        else "ready"
        if queued
        else "empty"
    )
    cursor = _hash(
        {
            "program": program.id,
            "revision": program.current_revision_number,
            "epoch": epoch,
            "consumed": consumed.id if consumed else None,
            "active": active.id if active else None,
            "cancelled": cancelled.id if cancelled else None,
            "last_event": events[-1].id if events else None,
            "last_transition": events[-1].rotation_transition_id if events else None,
            "today": today.isoformat(),
            "status": status,
        }
    )
    last_completed = next((item for item in reversed(events) if item.status == "completed"), None)
    last_completion_date = (
        (
            last_completed.completed_at.date()
            if last_completed.completed_at
            else last_completed.scheduled_date
        )
        if last_completed
        else None
    )
    coach_id = program.assigned_by_user_id
    can_extend = not (
        status == "expired"
        and coach_id is not None
        and coach_id != owner.id
        and db.query(CoachClient.id)
        .filter_by(coach_user_id=coach_id, client_user_id=owner.id, status="active")
        .first()
        is not None
    )
    return {
        "mode": "rotation",
        "status": status,
        "program_id": program.id,
        "revision_number": program.current_revision_number,
        "cursor": cursor,
        "current": current,
        "next": next_day,
        "days": days,
        "program_end_date": end,
        "duration_weeks": program.duration_weeks,
        "default_plan_week": default_week,
        "min_extension_weeks": max(
            program.duration_weeks + 1, (today - program.start_date).days // 7 + 1
        ),
        "can_extend": can_extend,
        "days_since_last_completion": max(0, (today - last_completion_date).days)
        if last_completion_date
        else None,
        "undo_skip_workout_id": (
            events[-1].id if events and events[-1].status == "skipped" else None
        ),
    }


def state(db: Session, owner: User) -> dict:
    program = _active_program(db, owner)
    if program is None or program.schedule_mode != "rotation":
        return {"mode": "calendar", "status": "disabled", "days": []}
    return _state(db, program, owner)


def _plan(
    db: Session, program: UserProgram, day_number: int, week: int
) -> tuple[dict | None, UserWorkout | None]:
    if week > program.duration_weeks:
        raise SessionRotationError("Выберите неделю в пределах программы", 422)
    plans = _cycle_workout_plans(db, program, week)
    if plans:
        plan = next((item for item in plans if item["day_number"] == day_number), None)
        if plan is None:
            raise SessionRotationError("В выбранной неделе нет этой тренировки")
        return plan, None
    sources = (
        db.query(UserWorkout)
        .options(selectinload(UserWorkout.exercises).selectinload(UserWorkoutExercise.sets))
        .filter(
            UserWorkout.user_program_id == program.id,
            UserWorkout.rotation_epoch.is_(None),
            UserWorkout.week_number == week,
            UserWorkout.day_number == day_number,
            UserWorkout.status != "cancelled",
        )
        .all()
    )
    if not sources and week == 1:
        revision = (
            db.query(ProgramRevision)
            .filter_by(user_program_id=program.id, revision_number=program.rotation_epoch)
            .first()
        )
        supplement = (
            next(
                (
                    item
                    for item in revision.changed_fields.get("rotation_supplement_plans", [])
                    if item["day_number"] == day_number
                ),
                None,
            )
            if revision
            else None
        )
        if supplement is not None:
            return supplement, None
    if len(sources) != 1:
        raise SessionRotationError("Не удалось однозначно определить план тренировки")
    if sources[0].status != "planned" or _workout_has_recorded_data(sources[0]):
        revisions = (
            db.query(ProgramRevision)
            .filter_by(user_program_id=program.id)
            .order_by(ProgramRevision.revision_number.desc())
        )
        saved = next(
            (
                item
                for revision in revisions
                for item in revision.snapshot.get("workouts", [])
                if item.get("rotation_epoch") is None
                and item.get("status") == "planned"
                and item.get("week_number") == week
                and item.get("day_number") == day_number
            ),
            None,
        )
        if saved is None:
            raise SessionRotationError("Не удалось восстановить исходный план тренировки")
        return saved, None
    return None, sources[0]


def preview_plan(db: Session, owner: User, day_number: int, week_number: int) -> dict:
    program = _active_program(db, owner)
    if program is None or program.schedule_mode != "rotation":
        raise SessionRotationError("Режим тренировок по очереди не включён")
    current = _state(db, program, owner)
    if day_number not in {item["day_number"] for item in current["days"]}:
        raise SessionRotationError("Тренировка больше не доступна")
    plan, source = _plan(db, program, day_number, week_number)
    if plan is not None:
        rows = plan["exercises"]
        ids = {item["exercise_id"] for item in rows}
        titles = {item.id: item.title for item in db.query(Exercise).filter(Exercise.id.in_(ids))}
        exercises = [
            {
                "title": titles.get(item["exercise_id"], "Упражнение"),
                "prescribed_sets": item["prescribed_sets"],
                "prescribed_reps": item["prescribed_reps"],
            }
            for item in rows
        ]
        title = plan["title"]
    else:
        assert source is not None
        exercises = [
            {
                "title": item.exercise.title if item.exercise else "Упражнение",
                "prescribed_sets": item.prescribed_sets,
                "prescribed_reps": item.prescribed_reps,
            }
            for item in source.exercises
        ]
        title = source.title
    return {"title": title, "week_number": week_number, "exercises": exercises}


def create_session(
    db: Session,
    owner: User,
    payload: SessionRotationActionRequest,
    *,
    skip: bool = False,
) -> UserWorkout:
    program = _active_program(db, owner, lock=True)
    if program is None or program.schedule_mode != "rotation" or program.rotation_epoch is None:
        raise SessionRotationError("Режим тренировок по очереди не включён")
    request_hash = _hash({"request": payload.model_dump(mode="json"), "skip": skip})
    replay = (
        db.query(UserWorkout)
        .filter_by(user_program_id=program.id, rotation_mutation_id=payload.mutation_id)
        .first()
    )
    if replay:
        if replay.rotation_request_hash != request_hash:
            raise SessionRotationError("Повтор запроса отличается от сохранённого действия")
        return replay
    current = _state(db, program, owner)
    if current["cursor"] != payload.expected_cursor:
        raise SessionRotationError("Очередь изменилась. Обновите данные")
    if current["status"] != "ready":
        raise SessionRotationError("Сначала проверьте состояние программы или текущую тренировку")
    available = {item["day_number"] for item in current["days"]}
    if payload.expected_day_number not in available:
        raise SessionRotationError("Тренировка больше не доступна")
    expected = current["current"]["day_number"]
    if (payload.expected_day_number != expected) != payload.out_of_order or (
        skip and payload.out_of_order
    ):
        raise SessionRotationError("Проверьте выбранную тренировку")
    today = today_for_user(owner)
    if today < program.start_date:
        raise SessionRotationError("Программа ещё не началась")
    selected = next(
        item for item in current["days"] if item["day_number"] == payload.expected_day_number
    )
    week = payload.plan_week_number or selected.get("default_plan_week")
    if week is None:
        raise SessionRotationError("Выберите неделю программы для этой тренировки", 422)
    plan, source = _plan(db, program, payload.expected_day_number, week)
    if plan is not None:
        workout = UserWorkout(
            user_program=program,
            scheduled_date=today,
            day_number=payload.expected_day_number,
            week_number=week,
            title=plan["title"],
            status="planned",
            plan_materialized=False,
            rotation_source_cycle_week=plan["source_cycle_week"],
            cycle_iteration=plan["cycle_iteration"],
            plan_revision_number=program.current_revision_number,
            rotation_epoch=program.rotation_epoch,
            rotation_role="extra" if payload.out_of_order else "ordered",
            rotation_mutation_id=payload.mutation_id,
            rotation_request_hash=request_hash,
        )
        db.add(workout)
        db.flush()
        _write_cycle_exercises(db, workout, plan)
    else:
        assert source is not None
        workout = _copy_scheduled_workout(
            db,
            source,
            program_id=program.id,
            scheduled_date=today,
            week_number=week,
            rotation_epoch=program.rotation_epoch,
        )
        workout.rotation_epoch = program.rotation_epoch
        workout.rotation_role = "extra" if payload.out_of_order else "ordered"
        workout.rotation_mutation_id = payload.mutation_id
        workout.rotation_request_hash = request_hash
    if skip:
        workout.status = "skipped"
    else:
        workout.started_at_utc = datetime.now(UTC).replace(tzinfo=None)
        workout.started_at = recovery_utc_naive_to_user_local(workout.started_at_utc, owner)
        workout.status = "in_progress"
        record_lifecycle_milestone(db, owner, "workout_started", occurred_at=workout.started_at_utc)
        if program.status == "scheduled":
            program.status = "active"
            revision = record_program_revision(
                db,
                program,
                actor=owner,
                change_kind="program_lifecycle",
                reason="Первая тренировка программы начата",
                changed_fields={
                    "operation": "program_started",
                    "previous_status": "scheduled",
                    "status": "active",
                },
            )
            record_audit_event(
                db,
                actor_user_id=owner.id,
                target_user_id=owner.id,
                action="program.started",
                resource_type="user_program",
                resource_id=program.id,
                details={"revision_number": revision.revision_number},
            )
    db.commit()
    db.refresh(workout)
    return workout


def transition(
    db: Session,
    owner: User,
    payload: SessionRotationTransitionRequest,
    action: str,
) -> dict:
    program = _active_program(db, owner, lock=True)
    if program is None or program.schedule_mode != "rotation" or program.rotation_epoch is None:
        raise SessionRotationError("Режим тренировок по очереди не включён")
    workout = (
        db.query(UserWorkout)
        .filter_by(
            id=payload.workout_id, user_program_id=program.id, rotation_epoch=program.rotation_epoch
        )
        .with_for_update()
        .first()
    )
    if workout is None:
        raise SessionRotationError("Тренировка не найдена", 404)
    request_hash = _hash({"request": payload.model_dump(mode="json"), "action": action})
    if workout.rotation_transition_id == payload.mutation_id:
        if workout.rotation_transition_hash != request_hash:
            raise SessionRotationError("Повтор запроса отличается от сохранённого действия")
        return _state(db, program, owner)
    current = _state(db, program, owner)
    if current["cursor"] != payload.expected_cursor:
        raise SessionRotationError("Очередь изменилась. Обновите данные")
    latest = (
        db.query(UserWorkout.id)
        .filter_by(user_program_id=program.id, rotation_epoch=program.rotation_epoch)
        .order_by(UserWorkout.id.desc())
        .first()
    )
    if latest is None or latest.id != workout.id:
        raise SessionRotationError("После этой тренировки очередь уже изменилась")
    if action == "cancel" and workout.status == "in_progress":
        workout.status = "cancelled"
    elif action == "restore" and workout.status == "cancelled" and workout.started_at is not None:
        workout.status = "in_progress"
    elif action == "undo-skip" and workout.status == "skipped" and workout.started_at is None:
        workout.status = "cancelled"
    else:
        raise SessionRotationError("Это действие недоступно для текущего состояния тренировки")
    workout.rotation_transition_id = payload.mutation_id
    workout.rotation_transition_hash = request_hash
    db.flush()
    result = _state(db, program, owner)
    db.commit()
    return result


def extend_program(
    db: Session, actor: User, program_id: int, payload: SessionRotationExtendRequest
) -> dict:
    program, _ = get_program_for_actor(db, actor, program_id, lock=True)
    _ensure_cycle_plan_editor(db, program, actor)
    _ensure_program_mutable(program)
    if program.schedule_mode != "rotation" or program.rotation_epoch is None:
        raise SessionRotationError("Режим тренировок по очереди не включён")
    owner = _owner(db, program)
    request_hash = _hash(payload.model_dump(mode="json"))
    last = (
        db.query(ProgramRevision)
        .filter_by(user_program_id=program.id, revision_number=program.current_revision_number)
        .first()
    )
    if last and last.changed_fields.get("rotation_extension_id") == payload.mutation_id:
        if last.changed_fields.get("rotation_extension_hash") != request_hash:
            raise SessionRotationError("Повтор запроса отличается от сохранённого действия")
        return _state(db, program, owner)
    _ensure_expected_revision(program, payload.expected_revision_number)
    current = _state(db, program, owner)
    if current["cursor"] != payload.expected_cursor:
        raise SessionRotationError("Очередь изменилась. Обновите данные")
    if payload.duration_weeks <= program.duration_weeks:
        raise SessionRotationError("Новая длительность должна быть больше прежней", 422)
    if payload.duration_weeks > (date.max - program.start_date).days // 7:
        raise SessionRotationError("Длительность выходит за допустимые даты", 422)
    end = program.start_date + timedelta(days=payload.duration_weeks * 7 - 1)
    if end < today_for_user(owner):
        raise SessionRotationError("Продлите программу как минимум до сегодняшнего дня", 422)
    if _cycle_plan_at(db, program, program.duration_weeks) and not _cycle_workout_plans(
        db, program, payload.duration_weeks
    ):
        raise SessionRotationError("Для продления сначала измените настройки периодизации")
    previous = program.duration_weeks
    program.duration_weeks = payload.duration_weeks
    revision = record_program_revision(
        db,
        program,
        actor=actor,
        change_kind="program_lifecycle",
        reason="Продлена программа тренировок",
        changed_fields={
            "operation": "rotation_duration_extended",
            "old_duration_weeks": previous,
            "duration_weeks": payload.duration_weeks,
            "rotation_extension_id": payload.mutation_id,
            "rotation_extension_hash": request_hash,
        },
    )
    record_audit_event(
        db,
        actor_user_id=actor.id,
        target_user_id=program.user_id,
        action="program.duration_extended",
        resource_type="user_program",
        resource_id=program.id,
        details={"revision_number": revision.revision_number},
    )
    db.commit()
    return _state(db, program, owner)
