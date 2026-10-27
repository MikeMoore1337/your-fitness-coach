from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from fitminiapp_api.api.dependencies.auth import require_user
from fitminiapp_api.core.config import settings
from fitminiapp_api.db.session import get_db
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.notification import (
    NotificationCreateRequest,
    NotificationOpenResponse,
    NotificationReadAllResponse,
    NotificationResponse,
    NotificationSettingResponse,
    NotificationSettingUpdate,
    ReminderTemplateResponse,
    ReminderTemplateUpdate,
    WebPushConfigResponse,
    WebPushStatusResponse,
    WebPushSubscriptionDeleteRequest,
    WebPushSubscriptionRequest,
    WebPushSubscriptionResponse,
)
from fitminiapp_api.services.notifications import (
    ManualNotificationScheduleError,
    create_manual_notification,
    delete_notification_for_user,
    get_or_create_settings,
    list_my_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    resolve_notification_destination,
)
from fitminiapp_api.services.reminder_templates import (
    get_template_definition,
    list_reminder_templates,
    update_reminder_template,
)
from fitminiapp_api.services.web_push import (
    WebPushDisabledError,
    WebPushSubscriptionError,
    has_registered_subscription,
    register_subscription,
    revoke_subscription,
)

router = APIRouter()


@router.get("/web-push/config", response_model=WebPushConfigResponse)
def get_web_push_config(
    current_user: User = Depends(require_user),
):
    del current_user
    return WebPushConfigResponse(
        enabled=settings.web_push_enabled,
        application_server_key=(
            settings.web_push_vapid_public_key if settings.web_push_enabled else None
        ),
    )


@router.get("/web-push/status", response_model=WebPushStatusResponse)
def get_web_push_status(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return WebPushStatusResponse(
        enabled=settings.web_push_enabled,
        registered=has_registered_subscription(db, current_user),
    )


@router.post(
    "/web-push/subscription",
    response_model=WebPushSubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "Web Push is disabled or not configured"
        }
    },
)
def register_web_push_subscription(
    payload: WebPushSubscriptionRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        register_subscription(
            db,
            current_user,
            endpoint=payload.endpoint,
            p256dh=payload.keys.p256dh,
            auth=payload.keys.auth,
        )
        db.commit()
    except WebPushDisabledError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Уведомления браузера сейчас недоступны",
        ) from exc
    except WebPushSubscriptionError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Недопустимая подписка браузера",
        ) from exc
    return WebPushSubscriptionResponse(status="registered")


@router.delete("/web-push/subscription", status_code=status.HTTP_204_NO_CONTENT)
def revoke_web_push_subscription(
    payload: WebPushSubscriptionDeleteRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    revoke_subscription(db, current_user, payload.endpoint)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _settings_response(settings, user: User) -> NotificationSettingResponse:
    return NotificationSettingResponse(
        workout_reminders_enabled=settings.workout_reminders_enabled,
        weekly_check_in_reminders_enabled=settings.weekly_check_in_reminders_enabled,
        measurement_reminders_enabled=settings.measurement_reminders_enabled,
        meal_reminders_enabled=settings.meal_reminders_enabled,
        hydration_reminders_enabled=settings.hydration_reminders_enabled,
        movement_reminders_enabled=settings.movement_reminders_enabled,
        telegram_enabled=settings.telegram_enabled,
        telegram_linked=user.telegram_user_id is not None,
        reminder_hour=settings.reminder_hour,
        quiet_hours_start=settings.quiet_hours_start,
        quiet_hours_end=settings.quiet_hours_end,
    )


def _notification_response(row) -> NotificationResponse:
    return NotificationResponse(
        id=row.id,
        category=row.category,
        event_kind=row.event_kind,
        title=row.title,
        body=row.body,
        created_at=row.created_at,
        scheduled_for=row.scheduled_for,
        status=row.status,
        delivery_status=row.status,
        sent_at=row.sent_at,
        read_at=row.read_at,
        action_url=row.action_url,
    )


@router.get("/settings", response_model=NotificationSettingResponse)
def get_notification_settings(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    settings = get_or_create_settings(db, current_user)
    return _settings_response(settings, current_user)


@router.patch("/settings", response_model=NotificationSettingResponse)
def update_notification_settings(
    payload: NotificationSettingUpdate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    fields = payload.model_fields_set
    if ("quiet_hours_start" in fields) != ("quiet_hours_end" in fields):
        raise HTTPException(
            status_code=422,
            detail="Начало и окончание тихих часов нужно сохранить вместе",
        )
    if "quiet_hours_start" in fields and (payload.quiet_hours_start is None) != (
        payload.quiet_hours_end is None
    ):
        raise HTTPException(
            status_code=422,
            detail="Для тихих часов нужны оба значения или ни одного",
        )

    settings = get_or_create_settings(db, current_user)
    for field in (
        "workout_reminders_enabled",
        "weekly_check_in_reminders_enabled",
        "measurement_reminders_enabled",
        "meal_reminders_enabled",
        "hydration_reminders_enabled",
        "movement_reminders_enabled",
        "telegram_enabled",
        "reminder_hour",
        "quiet_hours_start",
        "quiet_hours_end",
    ):
        if field in fields:
            setattr(settings, field, getattr(payload, field))
    db.commit()
    db.refresh(settings)
    return _settings_response(settings, current_user)


@router.get("/templates", response_model=list[ReminderTemplateResponse])
def get_reminder_templates(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    settings = get_or_create_settings(db, current_user)
    return list_reminder_templates(db, current_user, settings)


@router.patch("/templates/{template_key}", response_model=ReminderTemplateResponse)
def patch_reminder_template(
    template_key: str,
    payload: ReminderTemplateUpdate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        get_template_definition(template_key)
        settings = get_or_create_settings(db, current_user)
        return update_reminder_template(db, current_user, settings, template_key, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("", response_model=list[NotificationResponse])
def get_notifications(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    rows = list_my_notifications(db, current_user)
    return [_notification_response(row) for row in rows]


@router.patch("/read-all", response_model=NotificationReadAllResponse)
def read_all_notifications(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return NotificationReadAllResponse(updated=mark_all_notifications_read(db, current_user))


@router.post("", response_model=NotificationResponse, status_code=status.HTTP_201_CREATED)
def create_notification(
    payload: NotificationCreateRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    title = payload.title.strip()
    body = payload.body.strip()

    if not title:
        raise HTTPException(status_code=400, detail="title обязателен")
    if not body:
        raise HTTPException(status_code=400, detail="body обязателен")

    try:
        row = create_manual_notification(
            db,
            current_user,
            title=title,
            body=body,
            scheduled_for=payload.scheduled_for,
        )
    except ManualNotificationScheduleError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _notification_response(row)


@router.post("/{notification_id}/open", response_model=NotificationOpenResponse)
def open_notification(
    notification_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    row = mark_notification_read(db, current_user, notification_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Уведомление не найдено")
    destination, stale = resolve_notification_destination(db, current_user, row)
    return NotificationOpenResponse(
        destination=destination,
        stale=stale,
        message=(
            "Связанный объект больше недоступен. Вы вернулись в центр уведомлений."
            if stale
            else None
        ),
    )


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
def read_notification(
    notification_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    row = mark_notification_read(db, current_user, notification_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Уведомление не найдено")
    return _notification_response(row)


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notification(
    notification_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if not delete_notification_for_user(db, current_user, notification_id):
        raise HTTPException(status_code=404, detail="Напоминание не найдено")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
