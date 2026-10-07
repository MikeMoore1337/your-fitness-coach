from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from fitminiapp_api.core.timezone import now_msk_naive, today_for_user
from fitminiapp_api.models.audit import AuditEvent
from fitminiapp_api.models.exercise import Exercise
from fitminiapp_api.models.program import (
    ProgramRevision,
    ProgramTemplate,
    ProgramTemplateExercise,
    UserProgram,
    UserWorkout,
    UserWorkoutExercise,
)
from fitminiapp_api.models.user import CoachClient, User
from fitminiapp_api.schemas.coach_program_rollout import (
    CoachProgramRolloutApplyRequest,
    CoachProgramRolloutPreviewRequest,
)
from fitminiapp_api.services.audit import record_audit_event
from fitminiapp_api.services.program_common import ProgramError
from fitminiapp_api.services.program_versioning import apply_imported_template_revision
from fitminiapp_api.services.programs import get_template_for_user

logger = logging.getLogger(__name__)

MAX_ROLLOUT_TARGETS = 100
ROLLOUT_ACTION = "coach.program_rollout"


class CoachProgramRolloutError(Exception):
    def __init__(self, detail: str, status_code: int = 409):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _template_fingerprint(template: ProgramTemplate) -> str:
    payload = {
        "id": template.id,
        "title": template.title,
        "goal": template.goal,
        "level": template.level,
        "duration_weeks": template.effective_duration_weeks,
        "days": [
            {
                "day_number": day.day_number,
                "title": day.title,
                "exercises": [
                    {
                        "id": item.id,
                        "exercise_id": item.exercise_id,
                        "sort_order": item.sort_order,
                        "sets": item.prescribed_sets,
                        "reps": item.prescribed_reps,
                        "duration": item.prescribed_duration_minutes,
                        "rest": item.rest_seconds,
                        "notes": item.notes,
                        "superset_group": item.superset_group,
                        "superset_order": item.superset_order,
                        "group_id": item.group_id,
                        "group_kind": item.group_kind,
                        "group_order": item.group_order,
                        "prescription": item.prescription,
                        "weekly": [
                            {
                                "id": weekly.id,
                                "exercise_id": weekly.exercise_id,
                                "week_number": weekly.week_number,
                                "sets": weekly.prescribed_sets,
                                "reps": weekly.prescribed_reps,
                                "duration": weekly.prescribed_duration_minutes,
                                "rest": weekly.rest_seconds,
                                "prescription": weekly.prescription,
                            }
                            for weekly in sorted(
                                item.weekly_prescriptions,
                                key=lambda row: row.week_number,
                            )
                        ],
                    }
                    for item in sorted(day.exercises, key=lambda row: row.sort_order)
                ],
            }
            for day in sorted(template.days, key=lambda row: row.day_number)
        ],
    }
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def _client_name(client: User, relation: CoachClient) -> str:
    if relation.private_name and relation.private_name.strip():
        return relation.private_name.strip()
    if client.profile and client.profile.full_name and client.profile.full_name.strip():
        return client.profile.full_name.strip()
    return client.username or f"Клиент #{client.id}"


def _load_clients_and_programs(
    db: Session,
    coach: User,
    client_ids: list[int],
) -> tuple[dict[int, User], dict[int, str], dict[int, UserProgram]]:
    if len(client_ids) > MAX_ROLLOUT_TARGETS:
        raise CoachProgramRolloutError("Можно выбрать не более 100 клиентов", 422)

    rows = (
        db.query(CoachClient, User)
        .join(User, User.id == CoachClient.client_user_id)
        .options(joinedload(User.profile))
        .filter(
            CoachClient.coach_user_id == coach.id,
            CoachClient.status == "active",
            User.is_active.is_(True),
            User.id.in_(client_ids),
        )
        .all()
    )
    if len(rows) != len(set(client_ids)):
        raise CoachProgramRolloutError("Один из клиентов больше не входит в рабочий список", 404)

    clients = {client.id: client for _relation, client in rows}
    names = {client.id: _client_name(client, relation) for relation, client in rows}
    programs = (
        db.query(UserProgram)
        .options(
            joinedload(UserProgram.template),
            selectinload(UserProgram.workouts)
            .selectinload(UserWorkout.exercises)
            .selectinload(UserWorkoutExercise.exercise),
        )
        .filter(
            UserProgram.user_id.in_(client_ids),
            UserProgram.assigned_by_user_id == coach.id,
            UserProgram.is_active.is_(True),
            UserProgram.status.in_(("scheduled", "active")),
        )
        .all()
    )
    by_client = {program.user_id: program for program in programs}
    return clients, names, by_client


def _visible_exercises_by_client(
    db: Session,
    client_ids: list[int],
) -> dict[int, dict[int, Exercise]]:
    rows = (
        db.query(Exercise)
        .filter(
            (Exercise.created_by_user_id.is_(None) & Exercise.source_exercise_id.is_(None))
            | Exercise.created_by_user_id.in_(client_ids),
        )
        .all()
    )
    base = {
        row.id: row
        for row in rows
        if row.created_by_user_id is None and row.source_exercise_id is None and not row.is_deleted
    }
    personal_by_client: dict[int, list[Exercise]] = {}
    for row in rows:
        if row.created_by_user_id is not None:
            personal_by_client.setdefault(row.created_by_user_id, []).append(row)

    visible: dict[int, dict[int, Exercise]] = {}
    for client_id in client_ids:
        overrides = {
            row.source_exercise_id: row
            for row in personal_by_client.get(client_id, [])
            if row.source_exercise_id is not None
        }
        current = {}
        for effective_id, row in base.items():
            override = overrides.get(effective_id)
            if override is not None:
                if not override.is_deleted:
                    current[effective_id] = override
            else:
                current[effective_id] = row
        current.update(
            {
                row.id: row
                for row in personal_by_client.get(client_id, [])
                if row.source_exercise_id is None and not row.is_deleted
            }
        )
        visible[client_id] = current
    return visible


def _weekly_item(item: ProgramTemplateExercise, week_number: int):
    return next(
        (weekly for weekly in item.weekly_prescriptions if weekly.week_number == week_number),
        item,
    )


def _desired_rows(
    template: ProgramTemplate, week_number: int, day_number: int
) -> list[dict[str, Any]]:
    day = next(day for day in template.days if day.day_number == day_number)
    result = []
    for item in sorted(day.exercises, key=lambda row: row.sort_order):
        weekly = _weekly_item(item, week_number)
        result.append(
            {
                "exercise_id": weekly.exercise_id,
                "title": item.exercise.title,
                "sets": weekly.prescribed_sets,
                "reps": weekly.prescribed_reps,
                "duration": weekly.prescribed_duration_minutes,
                "rest": weekly.rest_seconds,
                "notes": item.notes,
                "superset_group": item.superset_group,
                "superset_order": item.superset_order,
                "group_id": item.group_id,
                "group_kind": item.group_kind,
                "group_order": item.group_order,
                "prescription": weekly.prescription or item.prescription,
                "sort_order": item.sort_order,
            }
        )
    return result


def _current_signature(row: UserWorkoutExercise) -> tuple[Any, ...]:
    return (
        row.exercise_id,
        row.prescribed_sets,
        row.prescribed_reps,
        row.prescribed_duration_minutes,
        row.rest_seconds,
        row.notes,
        row.superset_group,
        row.superset_order,
        row.group_id,
        row.group_kind,
        row.group_order,
        _stable_json(row.prescription),
    )


def _desired_signature(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row["exercise_id"],
        row["sets"],
        row["reps"],
        row["duration"],
        row["rest"],
        row["notes"],
        row["superset_group"],
        row["superset_order"],
        row["group_id"],
        row["group_kind"],
        row["group_order"],
        _stable_json(row["prescription"]),
    )


def _prescription_label(row: UserWorkoutExercise | dict[str, Any]) -> str:
    if isinstance(row, dict):
        if row["duration"] is not None:
            return f"{row['duration']} мин"
        return f"{row['sets']}×{row['reps']}"
    if row.prescribed_duration_minutes is not None:
        return f"{row.prescribed_duration_minutes} мин"
    return f"{row.prescribed_sets}×{row.prescribed_reps}"


def _target_preview(
    *,
    client: User,
    client_name: str,
    program: UserProgram | None,
    template: ProgramTemplate,
    visible_exercises: dict[int, Exercise],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "client_id": client.id,
        "client_name": client_name,
        "program_id": program.id if program else None,
        "current_revision_number": program.current_revision_number if program else None,
        "classification": "manual_review_required",
        "can_apply": False,
        "reason_codes": [],
        "diff": [],
    }
    if program is None:
        result["reason_codes"] = ["no_active_program"]
        return result

    reason_codes: list[str] = []
    template_days = {day.day_number for day in template.days}
    actual_pairs = {(workout.week_number, workout.day_number) for workout in program.workouts}
    expected_pairs = {
        (week_number, day_number)
        for week_number in range(1, program.duration_weeks + 1)
        for day_number in template_days
    }
    if template.effective_duration_weeks != program.duration_weeks:
        reason_codes.append("duration_mismatch")
    if actual_pairs != expected_pairs or len(actual_pairs) != len(program.workouts):
        reason_codes.append("schedule_mismatch")
    if any(workout.status == "in_progress" for workout in program.workouts):
        reason_codes.append("in_progress_workout")

    required_exercise_ids = {
        weekly.exercise_id
        for day in template.days
        for item in day.exercises
        for weekly in item.weekly_prescriptions
    }
    required_exercise_ids.update(
        item.exercise_id for day in template.days for item in day.exercises
    )
    missing_exercises = sorted(required_exercise_ids - set(visible_exercises))
    if missing_exercises:
        reason_codes.append("exercise_unavailable")

    future_workouts = [
        workout
        for workout in program.workouts
        if workout.status == "planned" and workout.scheduled_date >= today_for_user(client)
    ]
    if not future_workouts:
        reason_codes.append("no_future_workouts")

    diff: list[dict[str, Any]] = []
    replacement_seen = False
    removal_seen = False
    template_day_numbers = {day.day_number for day in template.days}
    for workout in future_workouts:
        desired = (
            _desired_rows(template, workout.week_number, workout.day_number)
            if workout.day_number in template_day_numbers
            else []
        )
        current = sorted(workout.exercises, key=lambda row: (row.sort_order, row.id))
        by_sort_order = {row.sort_order: row for row in current}
        for desired_row in desired:
            current_row = by_sort_order.get(desired_row["sort_order"])
            if current_row is None:
                diff.append(
                    {
                        "week_number": workout.week_number,
                        "day_number": workout.day_number,
                        "exercise_title": desired_row["title"],
                        "change": "added",
                        "current": None,
                        "proposed": _prescription_label(desired_row),
                    }
                )
                continue
            if _current_signature(current_row) != _desired_signature(desired_row):
                replacement = current_row.exercise_id != desired_row["exercise_id"]
                replacement_seen = replacement_seen or replacement
                diff.append(
                    {
                        "week_number": workout.week_number,
                        "day_number": workout.day_number,
                        "exercise_title": desired_row["title"],
                        "change": "updated",
                        "current": _prescription_label(current_row),
                        "proposed": _prescription_label(desired_row),
                    }
                )
        extra = [
            row for row in current if row.sort_order not in {item["sort_order"] for item in desired}
        ]
        for current_row in extra:
            removal_seen = True
            diff.append(
                {
                    "week_number": workout.week_number,
                    "day_number": workout.day_number,
                    "exercise_title": current_row.exercise.title,
                    "change": "removed",
                    "current": _prescription_label(current_row),
                    "proposed": None,
                }
            )

    if replacement_seen:
        reason_codes.append("exercise_replacement")
    if removal_seen:
        reason_codes.append("future_exercise_removal")
    if diff and not replacement_seen and not removal_seen:
        if any(item["change"] == "added" for item in diff):
            reason_codes.append("new_exercises")
        if any(item["change"] == "updated" for item in diff):
            reason_codes.append("prescription_changes")
    if not diff and not reason_codes:
        reason_codes.append("already_current")

    manual_codes = {
        "duration_mismatch",
        "schedule_mismatch",
        "in_progress_workout",
        "no_future_workouts",
        "exercise_replacement",
        "future_exercise_removal",
    }
    if any(code in manual_codes for code in reason_codes):
        classification = "manual_review_required"
    elif "exercise_unavailable" in reason_codes:
        classification = "personalization_required"
    else:
        classification = "compatible"

    result.update(
        classification=classification,
        can_apply=classification == "compatible" and bool(diff),
        reason_codes=reason_codes,
        diff=diff[:50],
    )
    return result


def _load_rollout_template(db: Session, coach: User, template_id: int) -> ProgramTemplate:
    try:
        return get_template_for_user(db, coach, template_id)
    except ProgramError as exc:
        raise CoachProgramRolloutError("Шаблон программы недоступен", 404) from exc


def preview_coach_program_rollout(
    db: Session,
    coach: User,
    payload: CoachProgramRolloutPreviewRequest,
) -> dict[str, Any]:
    template = _load_rollout_template(db, coach, payload.template_id)
    clients, names, programs = _load_clients_and_programs(db, coach, payload.client_ids)
    visible = _visible_exercises_by_client(db, payload.client_ids)
    targets = [
        _target_preview(
            client=clients[client_id],
            client_name=names[client_id],
            program=programs.get(client_id),
            template=template,
            visible_exercises=visible[client_id],
        )
        for client_id in payload.client_ids
    ]
    return {
        "template_id": template.id,
        "template_title": template.title,
        "template_fingerprint": _template_fingerprint(template),
        "targets": targets,
        "generated_at": now_msk_naive(),
    }


def _request_fingerprint(payload: CoachProgramRolloutApplyRequest) -> str:
    return hashlib.sha256(
        _stable_json(
            {
                "template_id": payload.template_id,
                "template_fingerprint": payload.template_fingerprint,
                "targets": sorted(
                    (target.client_id, target.program_id) for target in payload.targets
                ),
            }
        ).encode("utf-8")
    ).hexdigest()


def _error_code(exc: Exception) -> tuple[str, str]:
    mapping = {
        "Program revision conflict": (
            "stale_revision",
            "Программа уже изменилась после предпросмотра.",
        ),
        "Assigned program is not editable": (
            "program_not_editable",
            "Программа больше не редактируется.",
        ),
        "Imported duration must match the assigned program": (
            "duration_mismatch",
            "Длительность шаблона не совпадает с программой клиента.",
        ),
        "Imported days and weeks must match the assigned program schedule": (
            "schedule_mismatch",
            "Расписание программы изменилось; нужен новый предпросмотр.",
        ),
        "Imported exercise is not available for program owner": (
            "exercise_unavailable",
            "Одно из упражнений недоступно клиенту без персонализации.",
        ),
        "Strength rest must be at least 15 seconds": (
            "invalid_prescription",
            "Отдых между силовыми подходами должен составлять не менее 15 секунд.",
        ),
    }
    return mapping.get(str(exc), ("apply_failed", "Не удалось применить rollout к клиенту."))


def _already_applied(db: Session, program_id: int, rollout_id: str) -> bool:
    rows = (
        db.query(ProgramRevision.changed_fields)
        .filter(ProgramRevision.user_program_id == program_id)
        .all()
    )
    return any(
        isinstance(fields, dict) and fields.get("rollout_id") == rollout_id for (fields,) in rows
    )


def apply_coach_program_rollout(
    db: Session,
    coach: User,
    payload: CoachProgramRolloutApplyRequest,
    *,
    header_idempotency_key: str | None,
) -> dict[str, Any]:
    if not payload.confirmed:
        raise CoachProgramRolloutError("Для rollout требуется явное подтверждение тренера", 422)
    idempotency_key = (header_idempotency_key or payload.idempotency_key or "").strip()
    if len(idempotency_key) < 8:
        raise CoachProgramRolloutError("Для rollout требуется Idempotency-Key", 422)

    template = _load_rollout_template(db, coach, payload.template_id)
    current_fingerprint = _template_fingerprint(template)
    if current_fingerprint != payload.template_fingerprint:
        raise CoachProgramRolloutError(
            "Шаблон изменился после предпросмотра. Сначала соберите новый предпросмотр.",
            409,
        )
    client_ids = [target.client_id for target in payload.targets]
    clients, names, programs = _load_clients_and_programs(db, coach, client_ids)
    visible = _visible_exercises_by_client(db, client_ids)
    rollout_id = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    request_fingerprint = _request_fingerprint(payload)
    existing_start = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.actor_user_id == coach.id,
            AuditEvent.action == f"{ROLLOUT_ACTION}.started",
            AuditEvent.resource_id == rollout_id,
        )
        .order_by(AuditEvent.id.desc())
        .first()
    )
    if (
        existing_start is not None
        and existing_start.details.get("request_fingerprint") != request_fingerprint
    ):
        raise CoachProgramRolloutError(
            "Этот Idempotency-Key уже использован для другого rollout", 409
        )
    if existing_start is None:
        record_audit_event(
            db,
            actor_user_id=coach.id,
            target_user_id=coach.id,
            action=f"{ROLLOUT_ACTION}.started",
            resource_type="program_rollout",
            resource_id=rollout_id,
            details={
                "template_id": template.id,
                "target_count": len(payload.targets),
                "request_fingerprint": request_fingerprint,
            },
        )

    results: list[dict[str, Any]] = []
    for target in payload.targets:
        client = clients[target.client_id]
        client_name = names[target.client_id]
        program = programs.get(target.client_id)
        if program is None or program.id != target.program_id:
            results.append(
                {
                    "client_id": target.client_id,
                    "client_name": client_name,
                    "program_id": target.program_id,
                    "status": "failed",
                    "code": "program_changed",
                    "detail": "Активная программа клиента изменилась; соберите новый предпросмотр.",
                }
            )
            record_audit_event(
                db,
                actor_user_id=coach.id,
                target_user_id=client.id,
                action=f"{ROLLOUT_ACTION}.failed",
                resource_type="user_program",
                resource_id=target.program_id,
                details={"rollout_id": rollout_id, "reason_code": "program_changed"},
            )
            continue

        try:
            with db.begin_nested():
                locked_program = (
                    db.query(UserProgram)
                    .filter(UserProgram.id == target.program_id)
                    .with_for_update()
                    .first()
                )
                if locked_program is None or locked_program.user_id != client.id:
                    raise CoachProgramRolloutError("Программа клиента недоступна", 404)
                if _already_applied(db, locked_program.id, rollout_id):
                    results.append(
                        {
                            "client_id": client.id,
                            "client_name": client_name,
                            "program_id": locked_program.id,
                            "status": "already_applied",
                            "code": "already_applied",
                            "detail": "Этот rollout уже применён к клиенту.",
                            "current_revision_number": locked_program.current_revision_number,
                        }
                    )
                    continue

                target_preview = _target_preview(
                    client=client,
                    client_name=client_name,
                    program=locked_program,
                    template=template,
                    visible_exercises=visible[client.id],
                )
                if not target_preview["can_apply"]:
                    code = str(target_preview["classification"])
                    raise CoachProgramRolloutError(f"rollout_classification:{code}", 409)
                if locked_program.current_revision_number != target.expected_revision_number:
                    raise ProgramError("Program revision conflict")

                _target_program, workouts_updated, revision_number = (
                    apply_imported_template_revision(
                        db,
                        coach,
                        target.program_id,
                        template,
                        expected_revision_number=target.expected_revision_number,
                        import_id=rollout_id,
                        rollout_id=rollout_id,
                        reason=payload.reason,
                    )
                )
                results.append(
                    {
                        "client_id": client.id,
                        "client_name": client_name,
                        "program_id": target.program_id,
                        "status": "applied",
                        "code": "applied",
                        "detail": "Rollout применён к будущим тренировкам.",
                        "workouts_updated": workouts_updated,
                        "current_revision_number": revision_number,
                    }
                )
        except CoachProgramRolloutError as exc:
            if exc.detail.startswith("rollout_classification:"):
                code = exc.detail.split(":", 1)[1]
                detail = "Клиент не прошёл безопасную классификацию rollout."
            else:
                code, detail = "manual_review_required", exc.detail
            result = {
                "client_id": client.id,
                "client_name": client_name,
                "program_id": target.program_id,
                "status": "failed",
                "code": code,
                "detail": detail,
            }
            results.append(result)
            record_audit_event(
                db,
                actor_user_id=coach.id,
                target_user_id=client.id,
                action=f"{ROLLOUT_ACTION}.failed",
                resource_type="user_program",
                resource_id=target.program_id,
                details={"rollout_id": rollout_id, "reason_code": code},
            )
        except (ProgramError, IntegrityError) as exc:
            code, detail = _error_code(exc)
            results.append(
                {
                    "client_id": client.id,
                    "client_name": client_name,
                    "program_id": target.program_id,
                    "status": "failed",
                    "code": code,
                    "detail": detail,
                }
            )
            record_audit_event(
                db,
                actor_user_id=coach.id,
                target_user_id=client.id,
                action=f"{ROLLOUT_ACTION}.failed",
                resource_type="user_program",
                resource_id=target.program_id,
                details={"rollout_id": rollout_id, "reason_code": code},
            )
        except Exception:
            logger.exception(
                "coach_program_rollout_target_failed", extra={"rollout_id": rollout_id}
            )
            results.append(
                {
                    "client_id": client.id,
                    "client_name": client_name,
                    "program_id": target.program_id,
                    "status": "failed",
                    "code": "apply_failed",
                    "detail": "Не удалось применить rollout к клиенту.",
                }
            )
            record_audit_event(
                db,
                actor_user_id=coach.id,
                target_user_id=client.id,
                action=f"{ROLLOUT_ACTION}.failed",
                resource_type="user_program",
                resource_id=target.program_id,
                details={"rollout_id": rollout_id, "reason_code": "apply_failed"},
            )

    applied_count = sum(result["status"] == "applied" for result in results)
    already_applied_count = sum(result["status"] == "already_applied" for result in results)
    failed_count = sum(result["status"] == "failed" for result in results)
    record_audit_event(
        db,
        actor_user_id=coach.id,
        target_user_id=coach.id,
        action=f"{ROLLOUT_ACTION}.completed",
        resource_type="program_rollout",
        resource_id=rollout_id,
        details={
            "template_id": template.id,
            "target_count": len(results),
            "applied_count": applied_count,
            "already_applied_count": already_applied_count,
            "failed_count": failed_count,
        },
    )
    db.commit()
    return {
        "rollout_id": rollout_id,
        "template_id": template.id,
        "results": results,
        "applied_count": applied_count,
        "already_applied_count": already_applied_count,
        "failed_count": failed_count,
        "completed_at": now_msk_naive(),
    }


__all__ = [
    "CoachProgramRolloutError",
    "apply_coach_program_rollout",
    "preview_coach_program_rollout",
]
