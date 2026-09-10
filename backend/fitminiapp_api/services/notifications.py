from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Literal, cast
from urllib.parse import parse_qs, urlsplit

import httpx
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fitminiapp_api.core.config import settings
from fitminiapp_api.core.timezone import (
    local_naive_to_utc_naive,
    now_for_user_naive,
    now_msk_naive,
    to_user_timezone_naive,
    today_in_timezone,
    user_local_naive_to_utc_naive,
)
from fitminiapp_api.models.check_in import WeeklyCheckIn
from fitminiapp_api.models.feedback import WorkoutComment
from fitminiapp_api.models.notification import (
    Notification,
    NotificationDelivery,
    NotificationSetting,
    WebPushSubscription,
)
from fitminiapp_api.models.program import UserProgram, UserWorkout
from fitminiapp_api.models.report_handoff import ReportHandoff
from fitminiapp_api.models.user import (
    BodyMeasurement,
    CoachClient,
    CoachClientInvite,
    User,
    UserProfile,
)
from fitminiapp_api.services.telegram_transport import TelegramPublicationError

MAX_DELIVERY_ATTEMPTS = 5
PROCESSING_TIMEOUT = timedelta(minutes=5)
TERMINAL_RETENTION = timedelta(days=90)
RETENTION_BATCH_SIZE = 1000
WORKOUT_REMINDER_LEAD = timedelta(hours=2)
NOTIFICATION_FALLBACK = "/app?section=profile#profile-notifications"
ALLOWED_NOTIFICATION_QUERY_KEYS = frozenset(
    {
        "section",
        "workout_id",
        "comment_id",
        "workout_exercise_id",
        "report_handoff_id",
        "weekly_review",
        "date",
        "meal",
        "hydration",
        "return_to",
    }
)
ALLOWED_NOTIFICATION_SECTIONS = frozenset({"today", "progress", "programs", "nutrition", "profile"})


class NotificationDeliveryError(RuntimeError):
    """A safe delivery outcome that can control canonical retry state."""

    def __init__(
        self,
        code: str,
        *,
        retry_after: timedelta | None = None,
        terminal_status: Literal["cancelled", "failed"] | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.retry_after = retry_after
        self.terminal_status = terminal_status


def normalize_notification_action_url(action_url: str | None) -> str | None:
    if action_url is None:
        return None
    parsed = urlsplit(action_url)
    if parsed.scheme or parsed.netloc or parsed.path != "/app" or parsed.fragment:
        raise ValueError("unsafe notification action URL")
    query = parse_qs(parsed.query, keep_blank_values=True)
    if any(key not in ALLOWED_NOTIFICATION_QUERY_KEYS for key in query):
        raise ValueError("unsupported notification action URL")
    if any(len(values) != 1 for values in query.values()):
        raise ValueError("duplicate notification action parameter")
    section = query.get("section", [None])[0]
    if section is not None and section not in ALLOWED_NOTIFICATION_SECTIONS:
        raise ValueError("unsupported notification section")
    for key in ("workout_id", "comment_id", "workout_exercise_id", "report_handoff_id"):
        value = query.get(key, [None])[0]
        if value is not None and (not value.isdigit() or int(value) <= 0):
            raise ValueError("invalid notification entity identifier")
    if query.get("report_handoff_id") is not None and section != "progress":
        raise ValueError("report handoff must open progress section")
    weekly_review = query.get("weekly_review", [None])[0]
    if weekly_review is not None and weekly_review != "1":
        raise ValueError("invalid weekly review destination")
    date_value = query.get("date", [None])[0]
    if date_value is not None:
        try:
            date.fromisoformat(date_value)
        except ValueError as exc:
            raise ValueError("invalid notification date") from exc
    meal = query.get("meal", [None])[0]
    if meal is not None and meal not in {"breakfast", "lunch", "dinner", "snacks"}:
        raise ValueError("invalid notification meal")
    hydration = query.get("hydration", [None])[0]
    if hydration is not None and hydration != "quick":
        raise ValueError("invalid hydration destination")
    if meal is not None and section != "nutrition":
        raise ValueError("meal must open nutrition section")
    if hydration is not None and section != "nutrition":
        raise ValueError("hydration must open nutrition section")
    return_to = query.get("return_to", [None])[0]
    if return_to is not None and return_to != "/app?section=profile#profile-notifications":
        raise ValueError("invalid notification return destination")
    return action_url


def validate_notification_destination(destination: str) -> str:
    """Validate a destination already resolved by the canonical notification router."""
    if destination == NOTIFICATION_FALLBACK:
        return destination
    normalized = normalize_notification_action_url(destination)
    if normalized is None:
        raise ValueError("missing notification destination")
    return normalized


def neutral_telegram_text(notification: Notification) -> str:
    copy_by_category = {
        "workout_reminder": "Пора готовиться к тренировке. Подробности — в приложении.",
        "trainer_comment": "У вас новый комментарий тренера. Подробности — в приложении.",
        "trainer_program_update": "Тренер обновил программу. Подробности — в приложении.",
        "weekly_check_in_reminder": "Пора подвести итоги недели. Подробности — в приложении.",
        "measurement_reminder": "Можно обновить замеры. Подробности — в приложении.",
        "meal_logging_reminder": "Можно записать приём пищи. Подробности — в приложении.",
        "hydration_reminder": "Можно выпить воды. Подробности — в приложении.",
        "movement_break_reminder": (
            "Пора сделать короткий перерыв и немного подвигаться. Подробности — в приложении."
        ),
        "relationship_event": "Статус связи с тренером изменился. Подробности — в приложении.",
        "nutrition_update": "Ориентиры питания обновлены. Подробности — в приложении.",
        "workout_change": "Расписание тренировки изменилось. Подробности — в приложении.",
        "custom_reminder": "У вас запланировано личное напоминание. Подробности — в приложении.",
    }
    return copy_by_category.get(
        notification.category,
        "В приложении есть новое уведомление.",
    )


def reminder_category_enabled(
    notification: Notification,
    setting: NotificationSetting,
) -> bool:
    if notification.event_kind != "reminder":
        return True
    category_flags = {
        "workout_reminder": setting.workout_reminders_enabled,
        "weekly_check_in_reminder": setting.weekly_check_in_reminders_enabled,
        "measurement_reminder": setting.measurement_reminders_enabled,
        "meal_logging_reminder": setting.meal_reminders_enabled,
        "hydration_reminder": setting.hydration_reminders_enabled,
        "movement_break_reminder": setting.movement_reminders_enabled,
    }
    return category_flags.get(notification.category, True)


def quiet_hours_retry_at(
    setting: NotificationSetting,
    user: User,
    *,
    now_local: datetime | None = None,
) -> datetime | None:
    start = setting.quiet_hours_start
    end = setting.quiet_hours_end
    if start is None or end is None or start == end:
        return None
    local_now = now_local or now_for_user_naive(user)
    local_time = local_now.time().replace(tzinfo=None)
    if start < end:
        if not start <= local_time < end:
            return None
        end_date = local_now.date()
    else:
        if not (local_time >= start or local_time < end):
            return None
        end_date = local_now.date() + (timedelta(days=1) if local_time >= start else timedelta())
    local_end = datetime.combine(end_date, end)
    return user_local_naive_to_utc_naive(local_end, user)


def resolve_notification_destination(
    db: Session,
    user: User,
    notification: Notification,
) -> tuple[str, bool]:
    default_destinations = {
        "workout_reminder": "/app?section=today",
        "trainer_program_update": "/app?section=programs",
        "weekly_check_in_reminder": "/app?section=progress&weekly_review=1",
        "measurement_reminder": "/app?section=progress",
        "meal_logging_reminder": "/app?section=nutrition",
        "hydration_reminder": "/app?section=nutrition",
        "movement_break_reminder": "/app?section=today",
        "relationship_event": "/app?section=profile",
        "nutrition_update": "/app?section=nutrition",
        "workout_change": "/app?section=progress",
    }
    try:
        destination = normalize_notification_action_url(notification.action_url)
    except ValueError:
        return NOTIFICATION_FALLBACK, True
    destination = destination or default_destinations.get(notification.category)
    if destination is None:
        return NOTIFICATION_FALLBACK, True

    query = parse_qs(urlsplit(destination).query)
    report_handoff_id_value = query.get("report_handoff_id", [None])[0]
    if report_handoff_id_value is not None:
        if notification.category != "report_handoff":
            return NOTIFICATION_FALLBACK, True
        handoff = (
            db.query(ReportHandoff)
            .filter(
                ReportHandoff.id == int(report_handoff_id_value),
                ReportHandoff.notification_id == notification.id,
                ReportHandoff.trainer_user_id == user.id,
            )
            .first()
        )
        if handoff is None:
            return NOTIFICATION_FALLBACK, True
        active_relation = (
            db.query(CoachClient.id)
            .join(User, User.id == CoachClient.coach_user_id)
            .filter(
                CoachClient.id == handoff.relationship_id,
                CoachClient.coach_user_id == handoff.trainer_user_id,
                CoachClient.client_user_id == handoff.sender_user_id,
                CoachClient.status == "active",
                User.id == user.id,
                User.is_active.is_(True),
                User.is_coach.is_(True),
            )
            .first()
        )
        sender_is_active = (
            db.query(User.id)
            .filter(User.id == handoff.sender_user_id, User.is_active.is_(True))
            .first()
            is not None
        )
        if active_relation is None or not sender_is_active:
            return NOTIFICATION_FALLBACK, True
    workout_id_value = query.get("workout_id", [None])[0]
    if workout_id_value is not None:
        workout_id = int(workout_id_value)
        workout_exists = (
            db.query(UserWorkout.id)
            .join(UserProgram, UserProgram.id == UserWorkout.user_program_id)
            .filter(UserWorkout.id == workout_id, UserProgram.user_id == user.id)
            .first()
            is not None
        )
        if not workout_exists:
            return NOTIFICATION_FALLBACK, True
        comment_id_value = query.get("comment_id", [None])[0]
        if comment_id_value is not None:
            comment_exists = (
                db.query(WorkoutComment.id)
                .filter(
                    WorkoutComment.id == int(comment_id_value),
                    WorkoutComment.workout_id == workout_id,
                    WorkoutComment.client_user_id == user.id,
                )
                .first()
                is not None
            )
            if not comment_exists:
                return NOTIFICATION_FALLBACK, True
    return destination, False


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def safe_delivery_error(error: Exception) -> str:
    """Return a bounded diagnostic code without serializing request URLs or secrets."""
    if isinstance(error, NotificationDeliveryError):
        return error.code
    if isinstance(error, TelegramPublicationError):
        return error.code
    if isinstance(error, httpx.HTTPStatusError):
        return f"http_status:{error.response.status_code}"
    if isinstance(error, httpx.TimeoutException):
        return "timeout"
    if isinstance(error, httpx.RequestError):
        return "transport_error"
    return f"unexpected:{type(error).__name__}"[:2000]


def get_or_create_settings(db: Session, user: User) -> NotificationSetting:
    setting = db.query(NotificationSetting).filter(NotificationSetting.user_id == user.id).first()
    if not setting:
        db.query(User).filter(User.id == user.id).with_for_update().one()
        setting = (
            db.query(NotificationSetting).filter(NotificationSetting.user_id == user.id).first()
        )
        if not setting:
            setting = NotificationSetting(
                user_id=user.id,
                workout_reminders_enabled=True,
                weekly_check_in_reminders_enabled=True,
                measurement_reminders_enabled=False,
                telegram_enabled=True,
                reminder_hour=9,
            )
            db.add(setting)
            db.commit()
            db.refresh(setting)
    return setting


def list_my_notifications(db: Session, user: User, limit: int = 100) -> list[Notification]:
    return (
        db.query(Notification)
        .filter(Notification.user_id == user.id)
        .order_by(Notification.scheduled_for.desc(), Notification.id.desc())
        .limit(limit)
        .all()
    )


def prune_terminal_records(db: Session) -> int:
    """Bound terminal operational history while preserving relation/audit rows."""
    cutoff = now_msk_naive() - TERMINAL_RETENTION
    terminal_notifications = [
        (row.id, row.status)
        for row in db.query(Notification.id, Notification.status)
        .filter(
            Notification.status.in_(("sent", "cancelled", "failed")),
            Notification.created_at < cutoff,
        )
        .order_by(Notification.id.asc())
        .limit(RETENTION_BATCH_SIZE)
        .all()
    ]
    notification_ids = [notification_id for notification_id, _status in terminal_notifications]
    invite_ids = [
        row.id
        for row in db.query(CoachClientInvite.id)
        .filter(
            CoachClientInvite.status.in_(("expired", "revoked")),
            CoachClientInvite.created_at < cutoff,
        )
        .order_by(CoachClientInvite.id.asc())
        .limit(RETENTION_BATCH_SIZE)
        .all()
    ]
    if notification_ids:
        delivered_ids = [
            notification_id
            for notification_id, notification_status in terminal_notifications
            if notification_status == "sent"
        ]
        failed_ids = [
            notification_id
            for notification_id, notification_status in terminal_notifications
            if notification_status != "sent"
        ]
        if delivered_ids:
            db.query(ReportHandoff).filter(ReportHandoff.notification_id.in_(delivered_ids)).update(
                {ReportHandoff.delivery_status: "delivered"}, synchronize_session=False
            )
        if failed_ids:
            db.query(ReportHandoff).filter(ReportHandoff.notification_id.in_(failed_ids)).update(
                {ReportHandoff.delivery_status: "failed"}, synchronize_session=False
            )
        db.query(Notification).filter(Notification.id.in_(notification_ids)).delete(
            synchronize_session=False
        )
    if invite_ids:
        db.query(CoachClientInvite).filter(CoachClientInvite.id.in_(invite_ids)).delete(
            synchronize_session=False
        )
    deleted = len(notification_ids) + len(invite_ids)
    if deleted:
        db.commit()
    return deleted


def get_due_notifications(
    db: Session,
    now: datetime | None = None,
    limit: int = 100,
) -> list[Notification]:
    if now and now.tzinfo is not None:
        current_utc = now.astimezone(UTC).replace(tzinfo=None)
    else:
        current_utc = now or utcnow()
    return (
        db.query(Notification)
        .filter(
            Notification.status == "queued",
            Notification.scheduled_for_utc <= current_utc,
            or_(Notification.next_attempt_at.is_(None), Notification.next_attempt_at <= utcnow()),
        )
        .order_by(Notification.scheduled_for_utc.asc(), Notification.id.asc())
        .limit(limit)
        .all()
    )


def sync_workout_reminders(db: Session) -> int:
    prune_terminal_records(db)
    created = 0
    rows = (
        db.query(NotificationSetting, User, UserProfile.timezone)
        .join(User, User.id == NotificationSetting.user_id)
        .outerjoin(UserProfile, UserProfile.user_id == User.id)
        .filter(User.is_active.is_(True))
        .all()
    )
    if not rows:
        return 0

    user_ids = [user.id for _, user, _ in rows]
    settings_by_user = {user.id: (setting, user, timezone) for setting, user, timezone in rows}
    min_today = min(now_for_user_naive(user).date() for _, user, _ in rows)

    workouts = (
        db.query(UserWorkout, UserProgram.user_id)
        .join(UserProgram, UserProgram.id == UserWorkout.user_program_id)
        .filter(
            UserProgram.user_id.in_(user_ids),
            UserProgram.is_active.is_(True),
            UserWorkout.status == "planned",
            UserWorkout.scheduled_date >= min_today,
        )
        .all()
    )
    scheduled_workouts: list[tuple[UserWorkout, User, str | None, datetime]] = []
    active_keys: set[str] = set()
    for workout, user_id in workouts:
        setting, user, timezone = settings_by_user[user_id]
        if not setting.workout_reminders_enabled:
            continue
        local_now = now_for_user_naive(user)
        if workout.scheduled_date < local_now.date():
            continue
        if workout.scheduled_time is not None:
            workout_at = datetime.combine(workout.scheduled_date, workout.scheduled_time)
            if workout_at <= local_now:
                continue
            scheduled_for = max(workout_at - WORKOUT_REMINDER_LEAD, local_now)
        else:
            scheduled_for = datetime.combine(
                workout.scheduled_date,
                time(hour=setting.reminder_hour),
            )
        dedupe_key = f"workout:{workout.id}:reminder"
        active_keys.add(dedupe_key)
        scheduled_workouts.append(
            (
                workout,
                user,
                timezone,
                scheduled_for,
            )
        )

    reminder_scope = [Notification.status == "queued"]
    if active_keys:
        reminder_scope.append(Notification.dedupe_key.in_(active_keys))
    reminders = (
        db.query(Notification)
        .filter(
            Notification.user_id.in_(user_ids),
            Notification.dedupe_key.like("workout:%"),
            or_(*reminder_scope),
        )
        .all()
    )
    reminders_by_key = {row.dedupe_key: row for row in reminders}
    queued_by_user: dict[int, list[Notification]] = {}
    for notification in reminders:
        if notification.status == "queued":
            queued_by_user.setdefault(notification.user_id, []).append(notification)

    for workout, user, timezone, scheduled_for in scheduled_workouts:
        dedupe_key = f"workout:{workout.id}:reminder"
        existing_notification = reminders_by_key.get(dedupe_key)
        if existing_notification:
            if existing_notification.status in {"queued", "cancelled"}:
                was_cancelled = existing_notification.status == "cancelled"
                existing_notification.status = "queued"
                existing_notification.scheduled_for = scheduled_for
                existing_notification.scheduled_for_utc = local_naive_to_utc_naive(
                    scheduled_for,
                    timezone,
                )
                if was_cancelled:
                    existing_notification.attempt_count = 0
                    existing_notification.last_error = None
                    existing_notification.next_attempt_at = None
                    existing_notification.processing_started_at = None
            continue
        notification = Notification(
            user_id=user.id,
            channel="telegram",
            category="workout_reminder",
            event_kind="reminder",
            title="Скоро тренировка",
            body=f"По плану: {workout.title}",
            scheduled_for=scheduled_for,
            scheduled_for_utc=local_naive_to_utc_naive(scheduled_for, timezone),
            status="queued",
            dedupe_key=dedupe_key,
            action_url="/app?section=today",
        )
        db.add(notification)
        reminders_by_key[dedupe_key] = notification
        created += 1

    for user_id, notifications in queued_by_user.items():
        setting, _, _ = settings_by_user[user_id]
        for notification in notifications:
            if not setting.workout_reminders_enabled or notification.dedupe_key not in active_keys:
                notification.status = "cancelled"

    try:
        db.commit()
    except IntegrityError:
        # Параллельный worker мог первым создать тот же dedupe_key.
        db.rollback()
        return 0
    return created


def cancel_workout_reminder(db: Session, workout_id: int) -> int:
    """Invalidate an unsent reminder in the same transaction as a workout mutation."""
    return (
        db.query(Notification)
        .filter(
            Notification.dedupe_key == f"workout:{workout_id}:reminder",
            Notification.status.in_(("queued", "processing", "failed")),
        )
        .update(
            {
                Notification.status: "cancelled",
                Notification.last_error: "workout_reminder_invalidated",
                Notification.processing_started_at: None,
                Notification.next_attempt_at: None,
            },
            synchronize_session=False,
        )
    )


def sync_weekly_check_in_reminders(db: Session) -> int:
    created = 0
    rows = (
        db.query(NotificationSetting, User, UserProfile.timezone)
        .join(User, User.id == NotificationSetting.user_id)
        .outerjoin(UserProfile, UserProfile.user_id == User.id)
        .filter(User.is_active.is_(True))
        .all()
    )
    if not rows:
        return 0

    week_by_user: dict[int, tuple[date, date]] = {}
    for _setting, user, timezone in rows:
        local_day = today_in_timezone(timezone)
        week_start = local_day - timedelta(days=local_day.weekday())
        week_by_user[user.id] = (week_start, week_start + timedelta(days=6))
    existing_check_ins = {
        (row.user_id, row.week_start)
        for row in db.query(WeeklyCheckIn.user_id, WeeklyCheckIn.week_start)
        .filter(
            or_(
                *(
                    (WeeklyCheckIn.user_id == user.id)
                    & (WeeklyCheckIn.week_start == week_by_user[user.id][0])
                    for _setting, user, _timezone in rows
                )
            )
        )
        .all()
    }

    active: dict[str, tuple[User, str | None, datetime]] = {}
    for setting, user, timezone in rows:
        week_start, week_end = week_by_user[user.id]
        if (
            not setting.weekly_check_in_reminders_enabled
            or (user.id, week_start) in existing_check_ins
        ):
            continue
        dedupe_key = f"weekly_check_in:{user.id}:{week_start.isoformat()}"
        active[dedupe_key] = (
            user,
            timezone,
            datetime.combine(week_end, time(hour=setting.reminder_hour)),
        )

    active_keys = set(active)
    reminder_scope = [Notification.status == "queued"]
    if active_keys:
        reminder_scope.append(Notification.dedupe_key.in_(active_keys))
    reminders = (
        db.query(Notification)
        .filter(
            Notification.dedupe_key.like("weekly_check_in:%"),
            or_(*reminder_scope),
        )
        .all()
    )
    reminders_by_key = {row.dedupe_key: row for row in reminders}

    for dedupe_key, (user, timezone, scheduled_for) in active.items():
        existing = reminders_by_key.get(dedupe_key)
        if existing:
            if existing.status in {"queued", "cancelled"}:
                was_cancelled = existing.status == "cancelled"
                existing.status = "queued"
                existing.scheduled_for = scheduled_for
                existing.scheduled_for_utc = local_naive_to_utc_naive(scheduled_for, timezone)
                if was_cancelled:
                    existing.attempt_count = 0
                    existing.last_error = None
                    existing.next_attempt_at = None
                    existing.processing_started_at = None
            continue
        db.add(
            Notification(
                user_id=user.id,
                channel="telegram",
                category="weekly_check_in_reminder",
                event_kind="reminder",
                title="Еженедельные итоги",
                body="Подведите итоги недели: тренировки, питание и самочувствие.",
                scheduled_for=scheduled_for,
                scheduled_for_utc=local_naive_to_utc_naive(scheduled_for, timezone),
                status="queued",
                dedupe_key=dedupe_key,
                action_url="/app?section=progress&weekly_review=1",
            )
        )
        created += 1

    for reminder in reminders:
        if reminder.status == "queued" and reminder.dedupe_key not in active_keys:
            reminder.status = "cancelled"

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return 0
    return created


def sync_measurement_reminders(db: Session) -> int:
    created = 0
    rows = (
        db.query(NotificationSetting, User, UserProfile.timezone)
        .join(User, User.id == NotificationSetting.user_id)
        .outerjoin(UserProfile, UserProfile.user_id == User.id)
        .filter(User.is_active.is_(True))
        .all()
    )
    if not rows:
        return 0

    last_measurement_rows = cast(
        list[tuple[int, date]],
        db.query(BodyMeasurement.user_id, func.max(BodyMeasurement.measured_on))
        .filter(BodyMeasurement.user_id.in_([user.id for _setting, user, _timezone in rows]))
        .group_by(BodyMeasurement.user_id)
        .all(),
    )
    last_measurement_by_user: dict[int, date] = dict(last_measurement_rows)
    active: dict[str, tuple[User, str | None, datetime]] = {}
    for setting, user, timezone in rows:
        local_day = today_in_timezone(timezone)
        last_measurement = last_measurement_by_user.get(user.id)
        if not setting.measurement_reminders_enabled or (
            last_measurement is not None and local_day - last_measurement < timedelta(days=14)
        ):
            continue
        week_start = local_day - timedelta(days=local_day.weekday())
        week_end = week_start + timedelta(days=6)
        dedupe_key = f"measurement:{user.id}:{week_start.isoformat()}"
        active[dedupe_key] = (
            user,
            timezone,
            datetime.combine(week_end, time(hour=setting.reminder_hour)),
        )

    active_keys = set(active)
    reminder_scope = [Notification.status == "queued"]
    if active_keys:
        reminder_scope.append(Notification.dedupe_key.in_(active_keys))
    reminders = (
        db.query(Notification)
        .filter(Notification.dedupe_key.like("measurement:%"), or_(*reminder_scope))
        .all()
    )
    reminders_by_key = {row.dedupe_key: row for row in reminders}
    for dedupe_key, (user, timezone, scheduled_for) in active.items():
        existing = reminders_by_key.get(dedupe_key)
        if existing:
            if existing.status in {"queued", "cancelled"}:
                was_cancelled = existing.status == "cancelled"
                existing.status = "queued"
                existing.scheduled_for = scheduled_for
                existing.scheduled_for_utc = local_naive_to_utc_naive(scheduled_for, timezone)
                if was_cancelled:
                    existing.attempt_count = 0
                    existing.last_error = None
                    existing.next_attempt_at = None
                    existing.processing_started_at = None
            continue
        db.add(
            Notification(
                user_id=user.id,
                channel="telegram",
                category="measurement_reminder",
                event_kind="reminder",
                title="Пора обновить замеры",
                body="Регулярные замеры помогают видеть фактическую динамику без оценочных выводов.",
                scheduled_for=scheduled_for,
                scheduled_for_utc=local_naive_to_utc_naive(scheduled_for, timezone),
                status="queued",
                dedupe_key=dedupe_key,
                action_url="/app?section=progress",
            )
        )
        created += 1

    for reminder in reminders:
        if reminder.status == "queued" and reminder.dedupe_key not in active_keys:
            reminder.status = "cancelled"

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return 0
    return created


def claim_due_notifications(db: Session, limit: int = 100) -> list[Notification]:
    stale_before = utcnow() - PROCESSING_TIMEOUT
    db.query(Notification).filter(
        Notification.status == "processing",
        Notification.processing_started_at < stale_before,
        Notification.attempt_count < MAX_DELIVERY_ATTEMPTS,
    ).update(
        {
            Notification.status: "queued",
            Notification.processing_started_at: None,
        },
        synchronize_session=False,
    )
    db.commit()

    due = get_due_notifications(db, limit=limit)
    claimed_ids: list[int] = []
    started_at = utcnow()
    for notification in due:
        updated = (
            db.query(Notification)
            .filter(
                Notification.id == notification.id,
                Notification.status == "queued",
            )
            .update(
                {
                    Notification.status: "processing",
                    Notification.processing_started_at: started_at,
                },
                synchronize_session=False,
            )
        )
        if updated == 1:
            claimed_ids.append(notification.id)
    db.commit()
    if not claimed_ids:
        return []
    return db.query(Notification).filter(Notification.id.in_(claimed_ids)).all()


def enqueue_web_push_deliveries(
    db: Session,
    notifications: list[Notification],
) -> int:
    """Fan out one canonical event to each currently owned browser subscription."""

    if not settings.web_push_enabled or not notifications:
        return 0
    user_ids = {notification.user_id for notification in notifications}
    users = {user.id: user for user in db.query(User).filter(User.id.in_(user_ids)).all()}
    notification_settings = {
        setting.user_id: setting
        for setting in db.query(NotificationSetting)
        .filter(NotificationSetting.user_id.in_(user_ids))
        .all()
    }
    subscriptions = (
        db.query(WebPushSubscription)
        .filter(WebPushSubscription.user_id.in_(user_ids))
        .order_by(WebPushSubscription.id.asc())
        .all()
    )
    subscriptions_by_user: dict[int, list[WebPushSubscription]] = {}
    for subscription in subscriptions:
        subscriptions_by_user.setdefault(subscription.user_id, []).append(subscription)
    notification_ids = [notification.id for notification in notifications if notification.id]
    existing_pairs = {
        (notification_id, subscription_id)
        for notification_id, subscription_id in db.query(
            NotificationDelivery.notification_id,
            NotificationDelivery.subscription_id,
        )
        .filter(NotificationDelivery.notification_id.in_(notification_ids))
        .all()
    }

    created = 0
    for notification in notifications:
        user = users.get(notification.user_id)
        if user is None or not user.is_active:
            continue
        setting = notification_settings.get(notification.user_id)
        if notification.event_kind == "reminder" and setting is None:
            continue
        if setting is not None and not reminder_category_enabled(notification, setting):
            continue
        retry_at = (
            None
            if notification.event_kind == "security" or setting is None
            else quiet_hours_retry_at(setting, user)
        )
        for subscription in subscriptions_by_user.get(notification.user_id, []):
            pair = (notification.id, subscription.id)
            if pair in existing_pairs:
                continue
            db.add(
                NotificationDelivery(
                    notification_id=notification.id,
                    subscription_id=subscription.id,
                    next_attempt_at=retry_at,
                )
            )
            existing_pairs.add(pair)
            created += 1
    if created:
        db.flush()
    return created


def claim_due_web_push_deliveries(db: Session, limit: int = 500) -> list[NotificationDelivery]:
    stale_before = utcnow() - PROCESSING_TIMEOUT
    db.query(NotificationDelivery).filter(
        NotificationDelivery.status == "processing",
        NotificationDelivery.processing_started_at < stale_before,
        NotificationDelivery.attempt_count < MAX_DELIVERY_ATTEMPTS,
    ).update(
        {
            NotificationDelivery.status: "queued",
            NotificationDelivery.processing_started_at: None,
        },
        synchronize_session=False,
    )
    db.commit()

    current = utcnow()
    due = (
        db.query(NotificationDelivery)
        .join(Notification, Notification.id == NotificationDelivery.notification_id)
        .filter(
            NotificationDelivery.status == "queued",
            Notification.scheduled_for_utc <= current,
            or_(
                NotificationDelivery.next_attempt_at.is_(None),
                NotificationDelivery.next_attempt_at <= current,
            ),
        )
        .order_by(Notification.scheduled_for_utc.asc(), NotificationDelivery.id.asc())
        .limit(limit)
        .all()
    )
    claimed_ids: list[int] = []
    started_at = utcnow()
    for delivery in due:
        updated = (
            db.query(NotificationDelivery)
            .filter(
                NotificationDelivery.id == delivery.id,
                NotificationDelivery.status == "queued",
            )
            .update(
                {
                    NotificationDelivery.status: "processing",
                    NotificationDelivery.processing_started_at: started_at,
                },
                synchronize_session=False,
            )
        )
        if updated == 1:
            claimed_ids.append(delivery.id)
    db.commit()
    if not claimed_ids:
        return []
    return db.query(NotificationDelivery).filter(NotificationDelivery.id.in_(claimed_ids)).all()


def cancel_web_push_delivery(
    db: Session,
    delivery: NotificationDelivery,
    reason: str,
) -> None:
    delivery.status = "cancelled"
    delivery.last_error = reason
    delivery.processing_started_at = None
    delivery.next_attempt_at = None


def mark_web_push_delivery_succeeded(
    db: Session,
    delivery: NotificationDelivery,
    subscription: WebPushSubscription,
    *,
    commit: bool = True,
) -> None:
    now = now_msk_naive()
    delivery.status = "sent"
    delivery.sent_at = now
    delivery.last_error = None
    delivery.processing_started_at = None
    delivery.next_attempt_at = None
    subscription.last_success_at = now
    subscription.last_error = None
    subscription.failure_count = 0
    if commit:
        db.commit()


def mark_web_push_delivery_failed(
    db: Session,
    delivery: NotificationDelivery,
    error: Exception,
    *,
    subscription: WebPushSubscription | None = None,
    commit: bool = True,
) -> None:
    delivery.attempt_count += 1
    delivery.last_error = safe_delivery_error(error)
    delivery.processing_started_at = None
    now = now_msk_naive()
    subscription = subscription or db.get(WebPushSubscription, delivery.subscription_id)
    remove_subscription = bool(getattr(error, "remove_subscription", False))
    if subscription is not None:
        subscription.last_failure_at = now
        subscription.failure_count += 1
        subscription.last_error = delivery.last_error

    terminal_status = (
        getattr(error, "terminal_status", None)
        if isinstance(error, NotificationDeliveryError)
        else None
    )
    if remove_subscription:
        delivery.status = "cancelled"
        delivery.next_attempt_at = None
        if subscription is not None:
            db.delete(subscription)
    elif terminal_status is not None:
        delivery.status = terminal_status
        delivery.next_attempt_at = None
    elif delivery.attempt_count >= MAX_DELIVERY_ATTEMPTS:
        delivery.status = "failed"
        delivery.next_attempt_at = None
    else:
        delivery.status = "queued"
        retry_after = error.retry_after if isinstance(error, NotificationDeliveryError) else None
        if retry_after is None:
            retry_after = timedelta(minutes=min(60, 2 ** (delivery.attempt_count - 1)))
        delivery.next_attempt_at = utcnow() + retry_after
    if commit:
        db.commit()


def mark_delivery_succeeded(
    db: Session,
    notification: Notification,
    user: User,
    *,
    commit: bool = True,
) -> None:
    notification.status = "sent"
    notification.sent_at = now_for_user_naive(user)
    notification.last_error = None
    notification.processing_started_at = None
    notification.next_attempt_at = None
    if commit:
        db.commit()


def mark_delivery_failed(
    db: Session,
    notification: Notification,
    error: Exception,
    *,
    commit: bool = True,
) -> None:
    notification.attempt_count += 1
    notification.last_error = safe_delivery_error(error)
    notification.processing_started_at = None
    if isinstance(error, NotificationDeliveryError) and error.terminal_status is not None:
        notification.status = error.terminal_status
        notification.next_attempt_at = None
    elif notification.attempt_count >= MAX_DELIVERY_ATTEMPTS:
        notification.status = "failed"
        notification.next_attempt_at = None
    else:
        notification.status = "queued"
        retry_after = error.retry_after if isinstance(error, NotificationDeliveryError) else None
        if retry_after is None:
            delay_minutes = min(60, 2 ** (notification.attempt_count - 1))
            retry_after = timedelta(minutes=delay_minutes)
        notification.next_attempt_at = utcnow() + retry_after
    if commit:
        db.commit()


def create_manual_notification(
    db: Session,
    user: User,
    title: str,
    body: str,
    scheduled_for: datetime,
    channel: str = "telegram",
) -> Notification:
    notification = Notification(
        user_id=user.id,
        channel=channel,
        category="custom_reminder",
        event_kind="reminder",
        title=title.strip(),
        body=body.strip(),
        scheduled_for=to_user_timezone_naive(scheduled_for, user),
        scheduled_for_utc=(
            scheduled_for.astimezone(UTC).replace(tzinfo=None)
            if scheduled_for.tzinfo is not None
            else user_local_naive_to_utc_naive(scheduled_for, user)
        ),
        status="queued",
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification


def queue_notification(
    db: Session,
    user: User,
    *,
    category: str,
    title: str,
    body: str,
    dedupe_key: str | None = None,
    action_url: str | None = None,
    event_kind: str = "transactional",
) -> Notification:
    """Add one canonical in-app event with optional Telegram delivery."""
    scheduled_for = now_for_user_naive(user)
    notification = Notification(
        user_id=user.id,
        channel="telegram",
        category=category,
        event_kind=event_kind,
        title=title.strip(),
        body=body.strip(),
        scheduled_for=scheduled_for,
        scheduled_for_utc=user_local_naive_to_utc_naive(scheduled_for, user),
        status="queued",
        dedupe_key=dedupe_key,
        action_url=normalize_notification_action_url(action_url),
    )
    db.add(notification)
    return notification


def mark_notification_read(db: Session, user: User, notification_id: int) -> Notification | None:
    notification = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == user.id)
        .first()
    )
    if notification is None:
        return None
    if notification.read_at is None:
        notification.read_at = now_for_user_naive(user)
        db.commit()
        db.refresh(notification)
    return notification


def mark_all_notifications_read(db: Session, user: User) -> int:
    read_at = now_for_user_naive(user)
    updated = (
        db.query(Notification)
        .filter(Notification.user_id == user.id, Notification.read_at.is_(None))
        .update({Notification.read_at: read_at}, synchronize_session=False)
    )
    db.commit()
    return updated


def delete_notification_for_user(
    db: Session,
    user: User,
    notification_id: int,
) -> bool:
    row = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.user_id == user.id,
        )
        .first()
    )
    if not row:
        return False

    handoffs = db.query(ReportHandoff).filter(ReportHandoff.notification_id == row.id).all()
    for handoff in handoffs:
        handoff.delivery_status = "delivered" if row.status == "sent" else "failed"
    if handoffs:
        db.flush()
    db.delete(row)
    db.commit()
    return True
