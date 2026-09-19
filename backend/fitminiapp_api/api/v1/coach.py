from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from fitminiapp_api.api.dependencies.auth import require_coach
from fitminiapp_api.core.config import settings
from fitminiapp_api.core.timezone import now_for_user_naive
from fitminiapp_api.db.session import get_db
from fitminiapp_api.models.program import (
    UserProgram,
    UserWorkout,
)
from fitminiapp_api.models.user import CoachClient, User
from fitminiapp_api.schemas.check_in import WeeklyCheckInHistoryResponse
from fitminiapp_api.schemas.coach_attention import CoachAttentionResponse
from fitminiapp_api.schemas.feedback import (
    WorkoutCommentCreate,
    WorkoutCommentResponse,
    WorkoutCommentUpdate,
)
from fitminiapp_api.schemas.invite import CoachInviteLinkResponse
from fitminiapp_api.schemas.program import (
    AssignTemplateToClientRequest,
    ClientResponse,
    CoachAssignedProgramResponse,
    CoachProgramExerciseAssignmentResponse,
    CoachProgramExerciseCreate,
    ProgramAssignmentResponse,
)
from fitminiapp_api.schemas.progress import (
    NutritionReportPeriod,
    NutritionReportResponse,
    ProgressPeriodDays,
    ProgressReportDownloadLinkResponse,
    ProgressReportResponse,
    ProgressSummaryResponse,
    TrainerClientProgressListResponse,
)
from fitminiapp_api.schemas.report_handoff import ReportHandoffResponse
from fitminiapp_api.schemas.user import UserProfileUpdate
from fitminiapp_api.schemas.workout import (
    BodyMeasurementDefinitionResponse,
    BodyMeasurementResponse,
    BodyMeasurementSave,
    TrainingAnalyticsResponse,
    WorkoutProgressResponse,
    WorkoutRescheduleRequest,
    WorkoutScheduleItem,
    WorkoutTimelineItem,
)
from fitminiapp_api.services.analytics import (
    build_training_analytics_for_range,
    build_user_progress,
    build_workout_timeline,
)
from fitminiapp_api.services.audit import record_audit_event
from fitminiapp_api.services.coach_attention import build_coach_attention
from fitminiapp_api.services.coach_clients import (
    create_coach_invite_link,
    get_client_managed_by_coach,
    remove_client_for_coach,
    revoke_coach_invite,
)
from fitminiapp_api.services.exercise_catalog import _effective_exercise_id, list_exercises
from fitminiapp_api.services.measurements import (
    MeasurementError,
    MeasurementNotFoundError,
    delete_measurement,
    list_custom_measurement_definitions,
    list_measurements,
    save_measurement,
    serialize_custom_measurement_definition,
    serialize_measurement,
)
from fitminiapp_api.services.notifications import cancel_workout_reminder, queue_notification
from fitminiapp_api.services.nutrition import NutritionError
from fitminiapp_api.services.nutrition_reports import (
    NutritionReportError,
    build_nutrition_report,
    nutrition_report_csv,
)
from fitminiapp_api.services.period_bounds import PeriodBoundsError, resolve_progress_bounds
from fitminiapp_api.services.profile import ProfileError, update_profile
from fitminiapp_api.services.program_common import ProgramError, assignment_error_status
from fitminiapp_api.services.program_versioning import upsert_future_program_exercise
from fitminiapp_api.services.programs import (
    assign_template_to_user,
    get_template_for_user,
    list_clients,
    list_coach_assigned_programs,
)
from fitminiapp_api.services.progress import (
    build_progress_summary_for_range,
    build_trainer_client_summaries,
)
from fitminiapp_api.services.progress_report_downloads import create_progress_report_download_token
from fitminiapp_api.services.progress_reports import build_progress_report
from fitminiapp_api.services.report_handoffs import (
    ReportHandoffError,
    list_trainer_report_handoffs,
)
from fitminiapp_api.services.weekly_check_ins import list_weekly_check_ins
from fitminiapp_api.services.workout_comments import (
    WorkoutCommentError,
    create_workout_comment,
    edit_workout_comment,
    list_trainer_workout_comments,
    serialize_workout_comment,
)

router = APIRouter()

WorkoutCommentIdempotencyKey = Annotated[
    str | None,
    Header(alias="Idempotency-Key", min_length=8, max_length=128),
]


def _comment_error(exc: WorkoutCommentError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get(
    "/clients/{client_id}/workouts/{workout_id}/comments",
    response_model=list[WorkoutCommentResponse],
)
def get_client_workout_comments(
    client_id: int,
    workout_id: int,
    current_user: User = Depends(require_coach),
    db: Session = Depends(get_db),
):
    try:
        comments = list_trainer_workout_comments(
            db, current_user, client_id=client_id, workout_id=workout_id
        )
    except WorkoutCommentError as exc:
        raise _comment_error(exc) from exc
    return [serialize_workout_comment(comment) for comment in comments]


@router.post(
    "/clients/{client_id}/workouts/{workout_id}/comments",
    response_model=WorkoutCommentResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_client_workout_comment(
    client_id: int,
    workout_id: int,
    payload: WorkoutCommentCreate,
    idempotency_key: WorkoutCommentIdempotencyKey = None,
    current_user: User = Depends(require_coach),
    db: Session = Depends(get_db),
):
    try:
        comment = create_workout_comment(
            db,
            current_user,
            client_id=client_id,
            workout_id=workout_id,
            workout_exercise_id=payload.workout_exercise_id,
            body=payload.body,
            idempotency_key=idempotency_key,
        )
    except WorkoutCommentError as exc:
        raise _comment_error(exc) from exc
    return serialize_workout_comment(comment)


@router.patch(
    "/clients/{client_id}/workouts/{workout_id}/comments/{comment_id}",
    response_model=WorkoutCommentResponse,
)
def update_client_workout_comment(
    client_id: int,
    workout_id: int,
    comment_id: int,
    payload: WorkoutCommentUpdate,
    current_user: User = Depends(require_coach),
    db: Session = Depends(get_db),
):
    try:
        comment = edit_workout_comment(
            db,
            current_user,
            client_id=client_id,
            workout_id=workout_id,
            comment_id=comment_id,
            body=payload.body,
        )
    except WorkoutCommentError as exc:
        raise _comment_error(exc) from exc
    return serialize_workout_comment(comment)


def _managed_client(db: Session, coach: User, client_id: int) -> User:
    try:
        return get_client_managed_by_coach(db, coach, client_id)
    except ProgramError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _client_list_entry(db: Session, coach: User, client_id: int) -> dict:
    return next(
        row
        for row in list_clients(db, coach, include_preferences_context=True)
        if row["id"] == client_id
    )


@router.get("/clients", response_model=list[ClientResponse])
def coach_clients(
    current_user: User = Depends(require_coach),
    db: Session = Depends(get_db),
):
    return list_clients(db, current_user)


@router.get("/attention", response_model=CoachAttentionResponse)
def coach_attention(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(require_coach),
    db: Session = Depends(get_db),
) -> CoachAttentionResponse:
    return CoachAttentionResponse.model_validate(
        build_coach_attention(db, current_user, limit=limit)
    )


@router.get(
    "/assigned-programs",
    response_model=list[CoachAssignedProgramResponse],
)
def coach_assigned_programs(
    current_user: User = Depends(require_coach),
    db: Session = Depends(get_db),
):
    return list_coach_assigned_programs(db, current_user)


@router.get(
    "/clients/{client_id}/analytics",
    response_model=WorkoutProgressResponse,
)
def coach_client_analytics(
    client_id: int,
    current_user: User = Depends(require_coach),
    db: Session = Depends(get_db),
):
    client = _managed_client(db, current_user, client_id)
    return build_user_progress(db, client)


@router.get(
    "/clients/{client_id}/summary",
    response_model=ProgressSummaryResponse,
)
def coach_client_progress_summary(
    client_id: int,
    period_days: ProgressPeriodDays | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    current_user: User = Depends(require_coach),
    db: Session = Depends(get_db),
):
    client = _managed_client(db, current_user, client_id)
    try:
        bounds = resolve_progress_bounds(
            client,
            period_days,
            date_from=date_from,
            date_to=date_to,
        )
        return build_progress_summary_for_range(db, client, bounds.start, bounds.end)
    except PeriodBoundsError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


def _client_nutrition_report_or_422(
    db: Session,
    client: User,
    period: NutritionReportPeriod,
    date_from: date | None,
    date_to: date | None,
) -> dict:
    try:
        return build_nutrition_report(
            db,
            client,
            period,
            date_from=date_from,
            date_to=date_to,
        )
    except NutritionReportError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


@router.get(
    "/clients/{client_id}/nutrition-report",
    response_model=NutritionReportResponse,
)
def coach_client_nutrition_report(
    client_id: int,
    period: NutritionReportPeriod = NutritionReportPeriod.DAYS_30,
    date_from: date | None = None,
    date_to: date | None = None,
    current_user: User = Depends(require_coach),
    db: Session = Depends(get_db),
):
    client = _managed_client(db, current_user, client_id)
    return _client_nutrition_report_or_422(db, client, period, date_from, date_to)


@router.get(
    "/clients/{client_id}/progress-report",
    response_model=ProgressReportResponse,
)
def coach_client_progress_report(
    client_id: int,
    period: NutritionReportPeriod = NutritionReportPeriod.DAYS_30,
    date_from: date | None = None,
    date_to: date | None = None,
    current_user: User = Depends(require_coach),
    db: Session = Depends(get_db),
):
    client = _managed_client(db, current_user, client_id)
    try:
        return build_progress_report(
            db,
            client,
            period,
            date_from=date_from,
            date_to=date_to,
            subject_role="client",
        )
    except NutritionReportError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


@router.get(
    "/clients/{client_id}/report-handoffs",
    response_model=list[ReportHandoffResponse],
)
def coach_client_report_handoffs(
    client_id: int,
    limit: int = Query(default=5, ge=1, le=20),
    current_user: User = Depends(require_coach),
    db: Session = Depends(get_db),
) -> list[ReportHandoffResponse]:
    try:
        return list_trainer_report_handoffs(db, current_user, client_id, limit=limit)
    except ReportHandoffError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post(
    "/clients/{client_id}/progress-report/download-link",
    response_model=ProgressReportDownloadLinkResponse,
)
def coach_client_progress_report_download_link(
    client_id: int,
    period: NutritionReportPeriod = NutritionReportPeriod.DAYS_30,
    date_from: date | None = None,
    date_to: date | None = None,
    current_user: User = Depends(require_coach),
    db: Session = Depends(get_db),
) -> ProgressReportDownloadLinkResponse:
    client = _managed_client(db, current_user, client_id)
    try:
        report = build_progress_report(
            db,
            client,
            period,
            date_from=date_from,
            date_to=date_to,
            subject_role="client",
        )
    except NutritionReportError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    token, expires_at = create_progress_report_download_token(
        actor_user_id=current_user.id,
        subject_user_id=client.id,
        subject_role="client",
        period=NutritionReportPeriod.CUSTOM,
        date_from=date.fromisoformat(report["period_start"]),
        date_to=date.fromisoformat(report["period_end"]),
    )
    filename = f"progress-report-{report['period_start']}_{report['period_end']}.pdf"
    return ProgressReportDownloadLinkResponse(
        url=f"{settings.frontend_base_url.rstrip('/')}/api/v1/workouts/progress/report/file/{token}",
        filename=filename,
        expires_at=expires_at,
    )


@router.get("/clients/{client_id}/nutrition-report.csv")
def coach_client_nutrition_report_export(
    client_id: int,
    period: NutritionReportPeriod = NutritionReportPeriod.DAYS_30,
    date_from: date | None = None,
    date_to: date | None = None,
    current_user: User = Depends(require_coach),
    db: Session = Depends(get_db),
):
    client = _managed_client(db, current_user, client_id)
    report = _client_nutrition_report_or_422(db, client, period, date_from, date_to)
    filename = f"nutrition-report-{report['period_start']}-{report['period_end']}.csv"
    return Response(
        content="\ufeff" + nutrition_report_csv(report),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/clients/{client_id}/weekly-check-ins",
    response_model=WeeklyCheckInHistoryResponse,
)
def coach_client_weekly_check_ins(
    client_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10_000),
    current_user: User = Depends(require_coach),
    db: Session = Depends(get_db),
):
    client = _managed_client(db, current_user, client_id)
    return list_weekly_check_ins(db, client, limit=limit, offset=offset)


@router.get(
    "/clients/{client_id}/training-analytics",
    response_model=TrainingAnalyticsResponse,
)
def coach_client_training_analytics(
    client_id: int,
    period_days: ProgressPeriodDays | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    exercise_history_limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(require_coach),
    db: Session = Depends(get_db),
):
    client = _managed_client(db, current_user, client_id)
    try:
        bounds = resolve_progress_bounds(
            client,
            period_days,
            date_from=date_from,
            date_to=date_to,
        )
        return build_training_analytics_for_range(
            db,
            client,
            bounds.start,
            bounds.end,
            exercise_history_limit=exercise_history_limit,
        )
    except PeriodBoundsError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


@router.get(
    "/client-summaries",
    response_model=TrainerClientProgressListResponse,
)
def coach_client_progress_summaries(
    period_days: ProgressPeriodDays | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10_000),
    current_user: User = Depends(require_coach),
    db: Session = Depends(get_db),
):
    try:
        return build_trainer_client_summaries(
            db,
            current_user,
            period_days,
            limit=limit,
            offset=offset,
            date_from=date_from,
            date_to=date_to,
        )
    except PeriodBoundsError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


@router.get(
    "/clients/{client_id}/workouts",
    response_model=list[WorkoutTimelineItem],
)
def coach_client_workout_timeline(
    client_id: int,
    limit: int = Query(default=30, ge=1, le=100),
    current_user: User = Depends(require_coach),
    db: Session = Depends(get_db),
):
    client = _managed_client(db, current_user, client_id)
    return build_workout_timeline(db, client, limit=limit)


@router.patch(
    "/clients/{client_id}/workouts/{workout_id}/schedule",
    response_model=WorkoutScheduleItem,
)
def coach_reschedule_client_workout(
    client_id: int,
    workout_id: int,
    payload: WorkoutRescheduleRequest,
    current_user: User = Depends(require_coach),
    db: Session = Depends(get_db),
):
    managed_client = _managed_client(db, current_user, client_id)
    workout = (
        db.query(UserWorkout)
        .join(UserProgram, UserProgram.id == UserWorkout.user_program_id)
        .filter(
            UserWorkout.id == workout_id,
            UserProgram.user_id == managed_client.id,
            UserProgram.is_active.is_(True),
        )
        .with_for_update()
        .first()
    )
    if workout is None:
        raise HTTPException(status_code=404, detail="Тренировка клиента не найдена")
    if workout.status != "planned":
        raise HTTPException(
            status_code=409,
            detail="Перенести можно только запланированную тренировку",
        )

    now = now_for_user_naive(managed_client)
    if payload.scheduled_date < now.date() or (
        payload.scheduled_date == now.date()
        and payload.scheduled_time is not None
        and payload.scheduled_time < now.time()
    ):
        raise HTTPException(status_code=422, detail="Нельзя назначить дату и время в прошлом")

    collision = (
        db.query(UserWorkout.id)
        .join(UserProgram, UserProgram.id == UserWorkout.user_program_id)
        .filter(
            UserProgram.user_id == managed_client.id,
            UserProgram.is_active.is_(True),
            UserWorkout.id != workout.id,
            UserWorkout.scheduled_date == payload.scheduled_date,
            UserWorkout.status.notin_({"completed", "skipped", "cancelled"}),
        )
        .first()
    )
    if collision is not None:
        raise HTTPException(status_code=409, detail="На эту дату уже назначена тренировка")

    workout.scheduled_date = payload.scheduled_date
    workout.scheduled_time = payload.scheduled_time
    cancel_workout_reminder(db, workout.id)
    time_text = f" в {payload.scheduled_time.strftime('%H:%M')}" if payload.scheduled_time else ""
    queue_notification(
        db,
        managed_client,
        category="workout_change",
        title="Тренер изменил тренировку",
        body=(
            f"Тренер перенёс тренировку «{workout.title}» на "
            f"{payload.scheduled_date:%d.%m.%Y}{time_text}."
        ),
        action_url="/app?section=progress",
    )
    db.commit()
    return {
        "id": workout.id,
        "scheduled_date": workout.scheduled_date,
        "scheduled_time": workout.scheduled_time,
        "title": workout.title,
        "status": workout.status,
        "day_number": workout.day_number,
        "week_number": workout.week_number,
    }


@router.post(
    "/clients/{client_id}/programs/{program_id}/exercises",
    response_model=CoachProgramExerciseAssignmentResponse,
)
def add_exercise_to_client_program(
    client_id: int,
    program_id: int,
    payload: CoachProgramExerciseCreate,
    current_user: User = Depends(require_coach),
    db: Session = Depends(get_db),
):
    """Add or update an exercise in future occurrences of one selected program day."""
    managed_client = _managed_client(db, current_user, client_id)
    if (
        db.query(UserProgram.id)
        .filter(
            UserProgram.id == program_id,
            UserProgram.user_id == managed_client.id,
            UserProgram.assigned_by_user_id == current_user.id,
        )
        .first()
        is None
    ):
        raise HTTPException(status_code=404, detail="Программа клиента не найдена")
    try:
        workouts_updated, revision_number = upsert_future_program_exercise(
            db,
            current_user,
            program_id,
            payload,
        )
    except ProgramError as exc:
        detail = str(exc)
        if detail == "Assigned program not found":
            raise HTTPException(status_code=404, detail=detail) from exc
        if detail in {
            "Program revision conflict",
            "Assigned program is not editable",
            "No future planned workouts for the selected day",
            "Superset position is already occupied",
        }:
            raise HTTPException(status_code=409, detail=detail) from exc
        raise HTTPException(status_code=422, detail=detail) from exc
    return {
        "workouts_updated": workouts_updated,
        "current_revision_number": revision_number,
    }


@router.post(
    "/invite-links",
    response_model=CoachInviteLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_invite_link(
    current_user: User = Depends(require_coach),
    db: Session = Depends(get_db),
) -> dict:
    return create_coach_invite_link(db, current_user)


@router.patch("/clients/{client_id}/profile", response_model=ClientResponse)
def update_coach_client_profile(
    client_id: int,
    payload: UserProfileUpdate,
    current_user: User = Depends(require_coach),
    db: Session = Depends(get_db),
):
    client = _managed_client(db, current_user, client_id)
    profile_changes = payload.model_dump(exclude_unset=True)
    changed_fields = sorted(profile_changes)
    if "full_name" in profile_changes:
        relation = (
            db.query(CoachClient)
            .filter(
                CoachClient.coach_user_id == current_user.id,
                CoachClient.client_user_id == client.id,
                CoachClient.status == "active",
            )
            .one()
        )
        private_name = profile_changes.pop("full_name")
        relation.private_name = (private_name.strip() or None) if private_name else None

    if profile_changes:
        try:
            update_profile(
                db,
                client,
                UserProfileUpdate.model_validate(profile_changes),
                changed_by=current_user,
                commit=False,
            )
        except (NutritionError, ProfileError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_audit_event(
        db,
        actor_user_id=current_user.id,
        target_user_id=client.id,
        action="coach.client_profile_updated",
        resource_type="user_profile",
        resource_id=client.profile.id if client.profile else None,
        details={"fields": changed_fields},
    )
    db.commit()
    return _client_list_entry(db, current_user, client_id)


@router.get(
    "/clients/{client_id}/measurements",
    response_model=list[BodyMeasurementResponse],
)
def coach_client_measurements(
    client_id: int,
    limit: int = Query(default=12, ge=1, le=60),
    current_user: User = Depends(require_coach),
    db: Session = Depends(get_db),
):
    client = _managed_client(db, current_user, client_id)
    return [serialize_measurement(row) for row in list_measurements(db, client, limit=limit)]


@router.get(
    "/clients/{client_id}/measurements/custom-definitions",
    response_model=list[BodyMeasurementDefinitionResponse],
)
def coach_client_measurement_definitions(
    client_id: int,
    include_archived: bool = Query(default=True),
    current_user: User = Depends(require_coach),
    db: Session = Depends(get_db),
):
    client = _managed_client(db, current_user, client_id)
    return [
        serialize_custom_measurement_definition(row)
        for row in list_custom_measurement_definitions(
            db,
            client,
            include_archived=include_archived,
        )
    ]


@router.post(
    "/clients/{client_id}/measurements",
    response_model=BodyMeasurementResponse,
)
def save_coach_client_measurement(
    client_id: int,
    payload: BodyMeasurementSave,
    current_user: User = Depends(require_coach),
    db: Session = Depends(get_db),
):
    client = _managed_client(db, current_user, client_id)
    try:
        row = save_measurement(db, client, payload, changed_by=current_user)
    except MeasurementError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return serialize_measurement(row)


@router.delete(
    "/clients/{client_id}/measurements/{measurement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_coach_client_measurement(
    client_id: int,
    measurement_id: int,
    current_user: User = Depends(require_coach),
    db: Session = Depends(get_db),
):
    client = _managed_client(db, current_user, client_id)
    try:
        delete_measurement(db, client, measurement_id, changed_by=current_user)
    except MeasurementNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MeasurementError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/clients/{client_id}/templates/{template_id}/assign",
    response_model=ProgramAssignmentResponse,
)
def assign_template_to_coach_client(
    client_id: int,
    template_id: int,
    payload: AssignTemplateToClientRequest | None = None,
    current_user: User = Depends(require_coach),
    db: Session = Depends(get_db),
):
    client = _managed_client(db, current_user, client_id)
    try:
        template = get_template_for_user(db, current_user, template_id)
        visible_exercise_ids = {
            _effective_exercise_id(exercise) for exercise in list_exercises(db, client)
        }
        template_exercise_ids = {
            exercise.exercise_id for day in template.days for exercise in day.exercises
        }
        if not template_exercise_ids.issubset(visible_exercise_ids):
            raise ProgramError("Template contains exercises unavailable to client")
        program, created = assign_template_to_user(
            db,
            template,
            client,
            current_user,
            start_date=payload.start_date if payload else None,
            duration_weeks=payload.duration_weeks if payload else 1,
            schedule_weekdays=payload.schedule_weekdays if payload else None,
            replace_active=payload.replace_active if payload else False,
        )
        record_audit_event(
            db,
            actor_user_id=current_user.id,
            target_user_id=client.id,
            action="coach.program_assigned",
            resource_type="user_program",
            resource_id=program.id,
            details={
                "template_id": template.id,
                "workouts_created": created,
                "duration_weeks": program.duration_weeks,
            },
        )
        db.commit()
    except ProgramError as exc:
        detail = str(exc)
        if detail == "Template not found":
            raise HTTPException(status_code=404, detail=detail) from exc
        error_status = assignment_error_status(detail)
        if error_status != 400:
            raise HTTPException(status_code=error_status, detail=detail) from exc
        raise HTTPException(status_code=403, detail=detail) from exc
    return {
        "user_program_id": program.id,
        "workouts_created": created,
        "status": program.status,
        "start_date": program.start_date,
        "duration_weeks": program.duration_weeks,
    }


@router.delete("/clients/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_coach_client(
    client_id: int,
    current_user: User = Depends(require_coach),
    db: Session = Depends(get_db),
):
    try:
        remove_client_for_coach(db, current_user, client_id)
    except ProgramError as exc:
        detail = str(exc)
        if detail == "Client link not found":
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=400, detail=detail)


@router.delete("/client-invites/id/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_coach_client_invite_by_id(
    invite_id: int,
    current_user: User = Depends(require_coach),
    db: Session = Depends(get_db),
):
    try:
        revoke_coach_invite(db, current_user, invite_id)
    except ProgramError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
