from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, timedelta
from typing import cast

from sqlalchemy.orm import Session, joinedload, selectinload

from fitminiapp_api.core.timezone import now_msk_naive, today_for_user
from fitminiapp_api.models.check_in import WeeklyCheckIn
from fitminiapp_api.models.coach_crm import CoachBusinessSession, CoachTask
from fitminiapp_api.models.coach_reviews import CoachCheckInReview
from fitminiapp_api.models.program import UserProgram
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.coach_crm import CoachTaskResponse
from fitminiapp_api.schemas.coach_review_workspace import (
    CoachReviewActionState,
    CoachReviewChange,
    CoachReviewCheckInSnapshot,
    CoachReviewMeasurementFacts,
    CoachReviewNutritionFacts,
    CoachReviewPrivateNote,
    CoachReviewProgram,
    CoachReviewProgressionFacts,
    CoachReviewTrainingFacts,
    CoachReviewWorkspaceResponse,
)

_PRIVATE_NOTE_LOOKBACK = timedelta(days=180)


def _number(value: object, *, integer: bool = False) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value) if integer else float(value)


def _mapping(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _date_value(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _client_name(client: User) -> str:
    profile = client.profile
    return (
        profile.full_name.strip()
        if profile and profile.full_name and profile.full_name.strip()
        else client.username or f"Клиент #{client.id}"
    )


def _task_response(task: CoachTask, client_name: str) -> CoachTaskResponse:
    from zoneinfo import ZoneInfo

    return CoachTaskResponse(
        id=task.id,
        client_id=task.client_user_id,
        client_name=client_name,
        title=task.title,
        due_at=task.due_at_utc.replace(tzinfo=UTC).astimezone(ZoneInfo(task.timezone)),
        due_at_utc=task.due_at_utc.replace(tzinfo=UTC),
        timezone=task.timezone,
        kind=cast(object, task.kind),
        source_kind=cast(object, task.source_kind),
        source_id=task.source_id,
        reason=task.reason,
        state=cast(object, task.state),
        completed_at=task.completed_at,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _training_facts(check_in: WeeklyCheckIn | None) -> CoachReviewTrainingFacts:
    if check_in is None:
        return CoachReviewTrainingFacts()
    summary = _mapping(check_in.summary)
    training = _mapping(summary.get("training"))
    adherence = _mapping(training.get("adherence"))
    progression = _mapping(summary.get("progression"))
    return CoachReviewTrainingFacts(
        planned_workouts=_number(training.get("planned_workouts"), integer=True),
        completed_workouts=_number(training.get("completed_workouts"), integer=True),
        adherence_percent=_number(adherence.get("percent")),
        volume_kg=_number(progression.get("training_volume_kg")),
        training_load=check_in.training_load,
        recovery=check_in.recovery,
        adherence_difficulty=check_in.adherence_difficulty,
    )


def _progression_facts(check_in: WeeklyCheckIn | None) -> CoachReviewProgressionFacts:
    if check_in is None:
        return CoachReviewProgressionFacts()
    progression = _mapping(_mapping(check_in.summary).get("progression"))
    return CoachReviewProgressionFacts(
        training_volume_kg=_number(progression.get("training_volume_kg")),
        new_personal_records=_number(progression.get("new_personal_records"), integer=True),
    )


def _nutrition_facts(check_in: WeeklyCheckIn | None) -> CoachReviewNutritionFacts:
    if check_in is None:
        return CoachReviewNutritionFacts()
    nutrition = _mapping(_mapping(check_in.summary).get("nutrition"))
    return CoachReviewNutritionFacts(
        logged_days=_number(nutrition.get("logged_days"), integer=True),
        complete_days=_number(nutrition.get("complete_days"), integer=True),
        average_calories=_number(nutrition.get("average_calories")),
        target_calories=_number(nutrition.get("target_calories"), integer=True),
        average_protein_g=_number(nutrition.get("average_protein_g")),
        target_protein_g=_number(nutrition.get("target_protein_g"), integer=True),
    )


def _measurement_facts(check_in: WeeklyCheckIn | None) -> CoachReviewMeasurementFacts:
    if check_in is None:
        return CoachReviewMeasurementFacts()
    summary = _mapping(check_in.summary)
    weight = _mapping(summary.get("weight_trend"))
    anthropometry = summary.get("anthropometry_trends")
    waist = next(
        (
            _mapping(item)
            for item in (anthropometry if isinstance(anthropometry, list) else [])
            if isinstance(item, dict) and item.get("metric") == "waist_cm"
        ),
        {},
    )
    return CoachReviewMeasurementFacts(
        weight_kg=_number(weight.get("latest_value")),
        weight_change_kg=_number(weight.get("change")),
        waist_cm=_number(waist.get("latest_value")),
        latest_measured_on=_date_value(weight.get("latest_measured_on")),
    )


def _snapshot(check_in: WeeklyCheckIn | None) -> CoachReviewCheckInSnapshot | None:
    if check_in is None:
        return None
    return CoachReviewCheckInSnapshot(
        id=check_in.id,
        week_start=check_in.week_start,
        week_end=check_in.week_end,
        submitted_on=check_in.submitted_on,
        status=cast(object, check_in.status),
        training=_training_facts(check_in),
        progression=_progression_facts(check_in),
        nutrition=_nutrition_facts(check_in),
        measurements=_measurement_facts(check_in),
    )


def _state(current: CoachReviewCheckInSnapshot | None) -> str:
    if current is None:
        return "no_data"
    sections = (current.training, current.progression, current.nutrition, current.measurements)
    populated = sum(
        any(value is not None for value in section.model_dump().values()) for section in sections
    )
    return "available" if populated == len(sections) else "partial"


def _changes(
    previous: CoachReviewCheckInSnapshot | None,
    current: CoachReviewCheckInSnapshot | None,
) -> list[CoachReviewChange]:
    if previous is None or current is None:
        return []
    changes: list[CoachReviewChange] = []
    comparisons = (
        (
            "training",
            "completed_workouts",
            "Завершённые тренировки",
            previous.training.completed_workouts,
            current.training.completed_workouts,
        ),
        (
            "training",
            "adherence_percent",
            "Соблюдение плана",
            previous.training.adherence_percent,
            current.training.adherence_percent,
        ),
        (
            "progression",
            "training_volume_kg",
            "Объём тренинга",
            previous.progression.training_volume_kg,
            current.progression.training_volume_kg,
        ),
        (
            "progression",
            "new_personal_records",
            "Новые личные рекорды",
            previous.progression.new_personal_records,
            current.progression.new_personal_records,
        ),
        (
            "nutrition",
            "logged_days",
            "Дни с дневником питания",
            previous.nutrition.logged_days,
            current.nutrition.logged_days,
        ),
        (
            "nutrition",
            "average_calories",
            "Средняя калорийность",
            previous.nutrition.average_calories,
            current.nutrition.average_calories,
        ),
        (
            "nutrition",
            "average_protein_g",
            "Средний белок",
            previous.nutrition.average_protein_g,
            current.nutrition.average_protein_g,
        ),
        (
            "measurements",
            "weight_kg",
            "Последний вес",
            previous.measurements.weight_kg,
            current.measurements.weight_kg,
        ),
        (
            "measurements",
            "waist_cm",
            "Талия",
            previous.measurements.waist_cm,
            current.measurements.waist_cm,
        ),
    )
    for domain, key, label, old, new in comparisons:
        if old is None or new is None or old == new:
            continue
        changes.append(
            CoachReviewChange(
                domain=cast(object, domain),
                key=f"{domain}.{key}",
                label=label,
                previous=old,
                current=new,
            )
        )
    return changes


def _programs(
    db: Session,
    clients: Iterable[User],
) -> dict[int, CoachReviewProgram]:
    client_by_id = {client.id: client for client in clients}
    if not client_by_id:
        return {}
    rows = (
        db.query(UserProgram)
        .options(joinedload(UserProgram.template), selectinload(UserProgram.workouts))
        .filter(
            UserProgram.user_id.in_(client_by_id),
            UserProgram.is_active.is_(True),
            UserProgram.status.in_(("scheduled", "active", "paused")),
        )
        .order_by(UserProgram.user_id.asc(), UserProgram.assigned_at.desc(), UserProgram.id.desc())
        .all()
    )
    result: dict[int, CoachReviewProgram] = {}
    for program in rows:
        if program.user_id in result:
            continue
        client = client_by_id[program.user_id]
        today = today_for_user(client)
        workouts = list(program.workouts)
        upcoming = [
            workout.scheduled_date
            for workout in workouts
            if workout.status in {"planned", "in_progress"} and workout.scheduled_date >= today
        ]
        result[program.user_id] = CoachReviewProgram(
            id=program.id,
            title=program.template.title if program.template else "Архивная программа",
            status=cast(object, program.status),
            start_date=program.start_date,
            duration_weeks=program.duration_weeks,
            current_revision_number=program.current_revision_number,
            workouts_total=len(workouts),
            workouts_completed=sum(workout.status == "completed" for workout in workouts),
            next_workout_date=min(upcoming) if upcoming else None,
        )
    return result


def _private_notes(
    db: Session,
    coach: User,
    client_ids: Iterable[int],
) -> dict[int, list[CoachReviewPrivateNote]]:
    client_ids = list(client_ids)
    if not client_ids:
        return {}
    rows = (
        db.query(CoachBusinessSession)
        .filter(
            CoachBusinessSession.coach_user_id == coach.id,
            CoachBusinessSession.client_user_id.in_(client_ids),
            CoachBusinessSession.status != "cancelled",
            CoachBusinessSession.private_note.is_not(None),
            CoachBusinessSession.starts_at_utc >= now_msk_naive() - _PRIVATE_NOTE_LOOKBACK,
        )
        .order_by(CoachBusinessSession.starts_at_utc.desc(), CoachBusinessSession.id.desc())
        .all()
    )
    result: dict[int, list[CoachReviewPrivateNote]] = defaultdict(list)
    for row in rows:
        if row.private_note and len(result[row.client_user_id]) < 10:
            result[row.client_user_id].append(
                CoachReviewPrivateNote(
                    session_id=row.id,
                    starts_at_utc=row.starts_at_utc,
                    status=cast(object, row.status),
                    text=row.private_note,
                )
            )
    return dict(result)


def _actions(
    db: Session,
    coach: User,
    clients: dict[int, User],
    current_by_client: dict[int, WeeklyCheckIn | None],
) -> dict[int, CoachReviewActionState]:
    client_ids = list(clients)
    reviews = (
        db.query(CoachCheckInReview)
        .filter(
            CoachCheckInReview.coach_user_id == coach.id,
            CoachCheckInReview.client_user_id.in_(client_ids),
        )
        .all()
        if client_ids
        else []
    )
    reviews_by_check_in = {review.check_in_id: review for review in reviews}
    task_rows = (
        db.query(CoachTask)
        .filter(
            CoachTask.coach_user_id == coach.id,
            CoachTask.client_user_id.in_(client_ids),
            CoachTask.kind.in_(("update_program", "schedule_follow_up")),
        )
        .order_by(CoachTask.created_at.desc(), CoachTask.id.desc())
        .all()
        if client_ids
        else []
    )
    tasks_by_client: dict[int, list[CoachTask]] = defaultdict(list)
    for task in task_rows:
        if len(tasks_by_client[task.client_user_id]) < 20:
            tasks_by_client[task.client_user_id].append(task)

    result: dict[int, CoachReviewActionState] = {}
    for client_id, client in clients.items():
        current = current_by_client.get(client_id)
        review = reviews_by_check_in.get(current.id) if current else None
        tasks = tasks_by_client.get(client_id, [])
        follow_up = next(
            (task for task in tasks if review and task.id == review.follow_up_task_id),
            None,
        )
        result[client_id] = CoachReviewActionState(
            review_status=(
                "no_check_in" if current is None else "reviewed" if review else "pending"
            ),
            review_response=review.response if review else None,
            reviewed_at=review.reviewed_at if review else None,
            follow_up=_task_response(follow_up, _client_name(client)) if follow_up else None,
            program_proposals=[
                _task_response(task, _client_name(client))
                for task in tasks
                if task.kind == "update_program"
            ],
            next_reviews=[
                _task_response(task, _client_name(client))
                for task in tasks
                if task.kind == "schedule_follow_up"
                and task.id != (follow_up.id if follow_up else None)
            ],
        )
    return result


def _build(
    db: Session,
    coach: User,
    clients: list[User],
) -> dict[int, CoachReviewWorkspaceResponse]:
    client_ids = [client.id for client in clients]
    check_ins = (
        db.query(WeeklyCheckIn)
        .filter(WeeklyCheckIn.user_id.in_(client_ids), WeeklyCheckIn.status == "completed")
        .order_by(
            WeeklyCheckIn.user_id.asc(), WeeklyCheckIn.week_start.desc(), WeeklyCheckIn.id.desc()
        )
        .all()
        if client_ids
        else []
    )
    check_ins_by_client: dict[int, list[WeeklyCheckIn]] = defaultdict(list)
    for row in check_ins:
        if len(check_ins_by_client[row.user_id]) < 2:
            check_ins_by_client[row.user_id].append(row)
    current_by_client = {
        client.id: check_ins_by_client.get(client.id, [None])[0] for client in clients
    }
    programs = _programs(db, clients)
    notes = _private_notes(db, coach, client_ids)
    actions = _actions(db, coach, {client.id: client for client in clients}, current_by_client)
    result: dict[int, CoachReviewWorkspaceResponse] = {}
    for client in clients:
        rows = check_ins_by_client.get(client.id, [])
        current = _snapshot(rows[0] if rows else None)
        previous = _snapshot(rows[1] if len(rows) > 1 else None)
        training = current.training if current else CoachReviewTrainingFacts()
        progression = current.progression if current else CoachReviewProgressionFacts()
        nutrition = current.nutrition if current else CoachReviewNutritionFacts()
        measurements = current.measurements if current else CoachReviewMeasurementFacts()
        result[client.id] = CoachReviewWorkspaceResponse(
            client_id=client.id,
            client_name=_client_name(client),
            state=cast(object, _state(current)),
            previous_check_in=previous,
            current_check_in=current,
            training_actuals=training,
            progression_facts=progression,
            nutrition=nutrition,
            measurements=measurements,
            current_program=programs.get(client.id),
            private_notes=notes.get(client.id, []),
            meaningful_changes=_changes(previous, current),
            actions=actions[client.id],
        )
    return result


def build_coach_review_workspace(
    db: Session,
    coach: User,
    client: User,
) -> CoachReviewWorkspaceResponse:
    return _build(db, coach, [client])[client.id]


def build_coach_review_workspaces(
    db: Session,
    coach: User,
    clients: list[User],
) -> dict[int, CoachReviewWorkspaceResponse]:
    return _build(db, coach, clients)


__all__ = [
    "build_coach_review_workspace",
    "build_coach_review_workspaces",
]
