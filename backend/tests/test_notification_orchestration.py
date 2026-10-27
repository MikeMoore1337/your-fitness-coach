import asyncio
from datetime import date, datetime, time, timedelta
from unittest.mock import AsyncMock

import pytest

from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.check_in import WeeklyCheckIn
from fitminiapp_api.models.notification import Notification, NotificationSetting
from fitminiapp_api.models.program import ProgramTemplate, UserProgram, UserWorkout
from fitminiapp_api.models.user import BodyMeasurement, User, UserProfile
from fitminiapp_api.services import notifications as notification_service
from fitminiapp_api.services import worker
from fitminiapp_api.services.notifications import (
    can_scheduler_reactivate_cancelled_notification,
    cancel_workout_reminder,
    neutral_telegram_text,
    quiet_hours_retry_at,
    reminder_category_enabled,
    sync_measurement_reminders,
    sync_weekly_check_in_reminders,
    sync_workout_reminders,
)


def auth(client, telegram_user_id: int) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={
            "telegram_user_id": telegram_user_id,
            "is_coach": False,
            "is_admin": False,
        },
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_preferences_support_channels_categories_and_quiet_hours(client) -> None:
    headers = auth(client, 86401)

    updated = client.patch(
        "/api/v1/notifications/settings",
        headers=headers,
        json={
            "measurement_reminders_enabled": True,
            "telegram_enabled": False,
            "quiet_hours_start": "22:00:00",
            "quiet_hours_end": "08:00:00",
        },
    )

    assert updated.status_code == 200
    assert updated.json() == {
        "workout_reminders_enabled": True,
        "weekly_check_in_reminders_enabled": True,
        "measurement_reminders_enabled": True,
        "meal_reminders_enabled": False,
        "hydration_reminders_enabled": False,
        "movement_reminders_enabled": False,
        "telegram_enabled": False,
        "telegram_linked": True,
        "reminder_hour": 9,
        "quiet_hours_start": "22:00:00",
        "quiet_hours_end": "08:00:00",
    }
    invalid = client.patch(
        "/api/v1/notifications/settings",
        headers=headers,
        json={"quiet_hours_start": "23:00:00"},
    )
    assert invalid.status_code == 422


@pytest.mark.parametrize(
    ("category", "setting_name"),
    [
        ("workout_reminder", "workout_reminders_enabled"),
        ("weekly_check_in_reminder", "weekly_check_in_reminders_enabled"),
        ("measurement_reminder", "measurement_reminders_enabled"),
    ],
)
def test_each_optional_reminder_category_is_rechecked_before_delivery(
    category: str,
    setting_name: str,
) -> None:
    setting = NotificationSetting(
        workout_reminders_enabled=True,
        weekly_check_in_reminders_enabled=True,
        measurement_reminders_enabled=True,
    )
    event = Notification(
        user_id=1,
        category=category,
        event_kind="reminder",
        title="Reminder",
        body="Body",
        scheduled_for=datetime(2026, 8, 24, 9),
        scheduled_for_utc=datetime(2026, 8, 24, 6),
    )

    assert reminder_category_enabled(event, setting) is True
    setattr(setting, setting_name, False)
    assert reminder_category_enabled(event, setting) is False

    event.event_kind = "transactional"
    assert reminder_category_enabled(event, setting) is True


@pytest.mark.parametrize(
    ("last_error", "expected"),
    [
        ("workout_reminder_invalidated", True),
        (None, True),
        ("telegram_chat_unavailable", False),
        ("telegram_http_status:400", False),
        ("unknown_cancellation", False),
    ],
)
def test_scheduler_reactivation_policy_is_semantic_and_fail_closed(
    last_error: str | None,
    expected: bool,
) -> None:
    notification = Notification(
        user_id=1,
        category="workout_reminder",
        event_kind="reminder",
        title="Reminder",
        body="Body",
        scheduled_for=datetime(2026, 8, 24, 9),
        scheduled_for_utc=datetime(2026, 8, 24, 6),
        status="cancelled",
        last_error=last_error,
        dedupe_key="workout:1:reminder",
    )

    assert can_scheduler_reactivate_cancelled_notification(notification) is expected


def test_scheduler_reactivation_policy_rejects_non_reminder_events() -> None:
    notification = Notification(
        user_id=1,
        category="workout_reminder",
        event_kind="security",
        title="Security",
        body="Body",
        scheduled_for=datetime(2026, 8, 24, 9),
        scheduled_for_utc=datetime(2026, 8, 24, 6),
        status="cancelled",
        last_error="workout_reminder_invalidated",
        dedupe_key="workout:1:reminder",
    )

    assert can_scheduler_reactivate_cancelled_notification(notification) is False


def test_workout_reminder_uses_exact_time_reschedules_and_cancels(monkeypatch) -> None:
    fixed_now = datetime(2026, 3, 9, 10)
    monkeypatch.setattr(notification_service, "now_for_user_naive", lambda _user: fixed_now)

    with get_session_context() as session:
        user = User(telegram_user_id=86402, is_coach=False)
        session.add(user)
        session.flush()
        session.add(UserProfile(user_id=user.id, timezone="America/New_York"))
        session.add(NotificationSetting(user_id=user.id))
        template = session.query(ProgramTemplate).first()
        program = UserProgram(user_id=user.id, template_id=template.id, is_active=True)
        session.add(program)
        session.flush()
        workout = UserWorkout(
            user_program_id=program.id,
            scheduled_date=date(2026, 3, 9),
            scheduled_time=time(18, 0),
            day_number=1,
            title="Вечерняя тренировка",
            status="planned",
        )
        session.add(workout)
        session.commit()
        workout_id = workout.id

    with get_session_context() as session:
        assert sync_workout_reminders(session) == 1
        reminder = (
            session.query(Notification).filter_by(dedupe_key=f"workout:{workout_id}:reminder").one()
        )
        assert reminder.category == "workout_reminder"
        assert reminder.event_kind == "reminder"
        assert reminder.scheduled_for == datetime(2026, 3, 9, 16)
        # America/New_York is UTC-4 after the 2026 spring DST transition.
        assert reminder.scheduled_for_utc == datetime(2026, 3, 9, 20)

        workout = session.get(UserWorkout, workout_id)
        workout.scheduled_date = date(2026, 3, 10)
        workout.scheduled_time = time(19, 0)
        assert cancel_workout_reminder(session, workout.id) == 1
        session.commit()
        session.refresh(reminder)
        assert reminder.status == "cancelled"
        assert reminder.last_error == "workout_reminder_invalidated"
        assert sync_workout_reminders(session) == 0
        session.refresh(reminder)
        assert reminder.scheduled_for == datetime(2026, 3, 10, 17)
        assert reminder.last_error is None

        workout.status = "completed"
        session.commit()
        assert sync_workout_reminders(session) == 0
        session.refresh(reminder)
        assert reminder.status == "cancelled"


def test_measurement_reminder_is_optional_deduplicated_and_cancelled(monkeypatch) -> None:
    local_day = date(2026, 8, 24)
    monkeypatch.setattr(notification_service, "today_in_timezone", lambda _timezone: local_day)

    with get_session_context() as session:
        user = User(telegram_user_id=86403, is_coach=False)
        session.add(user)
        session.flush()
        session.add(UserProfile(user_id=user.id, timezone="Europe/Moscow"))
        session.add(
            NotificationSetting(
                user_id=user.id,
                measurement_reminders_enabled=True,
                reminder_hour=9,
            )
        )
        session.commit()
        user_id = user.id

    with get_session_context() as session:
        assert sync_measurement_reminders(session) == 1
        assert sync_measurement_reminders(session) == 0
        reminder = (
            session.query(Notification)
            .filter(
                Notification.user_id == user_id, Notification.category == "measurement_reminder"
            )
            .one()
        )
        assert reminder.scheduled_for == datetime(2026, 8, 30, 9)

        session.add(BodyMeasurement(user_id=user_id, measured_on=local_day, weight_kg=80))
        session.commit()
        assert sync_measurement_reminders(session) == 0
        session.refresh(reminder)
        assert reminder.status == "cancelled"
        assert reminder.last_error == "measurement_reminder_not_due"

        session.query(BodyMeasurement).filter(BodyMeasurement.user_id == user_id).delete()
        session.commit()
        assert sync_measurement_reminders(session) == 0
        session.refresh(reminder)
        assert reminder.status == "queued"
        assert reminder.last_error is None


def test_weekly_check_in_scheduler_cancellation_reactivates(monkeypatch) -> None:
    local_day = date(2026, 8, 24)
    monkeypatch.setattr(notification_service, "today_in_timezone", lambda _timezone: local_day)

    with get_session_context() as session:
        user = User(telegram_user_id=86408, is_coach=False)
        session.add(user)
        session.flush()
        session.add(UserProfile(user_id=user.id, timezone="Europe/Moscow"))
        session.add(NotificationSetting(user_id=user.id, reminder_hour=9))
        session.commit()
        user_id = user.id

        assert sync_weekly_check_in_reminders(session) >= 1
        reminder = (
            session.query(Notification)
            .filter(Notification.dedupe_key.like(f"weekly_check_in:{user_id}:%"))
            .one()
        )
        week_start = local_day - timedelta(days=local_day.weekday())
        session.add(
            WeeklyCheckIn(
                user_id=user_id,
                week_start=week_start,
                week_end=week_start + timedelta(days=6),
                submitted_on=local_day,
                timezone="Europe/Moscow",
                status="completed",
                summary_version="v1",
                summary={},
            )
        )
        session.commit()

        assert sync_weekly_check_in_reminders(session) == 0
        session.refresh(reminder)
        assert reminder.status == "cancelled"
        assert reminder.last_error == "weekly_check_in_not_due"

        session.query(WeeklyCheckIn).filter(WeeklyCheckIn.user_id == user_id).delete()
        session.commit()
        assert sync_weekly_check_in_reminders(session) == 0
        session.refresh(reminder)
        assert reminder.status == "queued"
        assert reminder.last_error is None


def test_workout_terminal_delivery_cancellation_is_not_reactivated(monkeypatch) -> None:
    fixed_now = datetime(2026, 8, 24, 10)
    monkeypatch.setattr(notification_service, "now_for_user_naive", lambda _user: fixed_now)

    with get_session_context() as session:
        user = User(telegram_user_id=86409, is_coach=False)
        session.add(user)
        session.flush()
        session.add(UserProfile(user_id=user.id, timezone="Europe/Moscow"))
        session.add(NotificationSetting(user_id=user.id))
        template = session.query(ProgramTemplate).first()
        assert template is not None
        program = UserProgram(user_id=user.id, template_id=template.id, is_active=True)
        session.add(program)
        session.flush()
        workout = UserWorkout(
            user_program_id=program.id,
            scheduled_date=fixed_now.date(),
            scheduled_time=time(18),
            day_number=1,
            title="Тренировка",
            status="planned",
        )
        session.add(workout)
        session.flush()
        assert sync_workout_reminders(session) == 1
        reminder = (
            session.query(Notification).filter_by(dedupe_key=f"workout:{workout.id}:reminder").one()
        )
        reminder.status = "cancelled"
        reminder.attempt_count = 1
        reminder.last_error = "telegram_chat_unavailable"
        reminder.next_attempt_at = None
        reminder.processing_started_at = None
        session.commit()

        assert sync_workout_reminders(session) == 0
        session.refresh(reminder)
        assert reminder.status == "cancelled"
        assert reminder.attempt_count == 1
        assert reminder.last_error == "telegram_chat_unavailable"
        assert reminder.next_attempt_at is None


def test_weekly_check_in_terminal_delivery_cancellation_is_not_reactivated(monkeypatch) -> None:
    local_day = date(2026, 8, 24)
    monkeypatch.setattr(notification_service, "today_in_timezone", lambda _timezone: local_day)

    with get_session_context() as session:
        user = User(telegram_user_id=86410, is_coach=False)
        session.add(user)
        session.flush()
        session.add(UserProfile(user_id=user.id, timezone="Europe/Moscow"))
        session.add(NotificationSetting(user_id=user.id, reminder_hour=9))
        session.commit()
        assert sync_weekly_check_in_reminders(session) >= 1
        reminder = (
            session.query(Notification)
            .filter(Notification.dedupe_key.like(f"weekly_check_in:{user.id}:%"))
            .one()
        )
        reminder.status = "cancelled"
        reminder.attempt_count = 1
        reminder.last_error = "telegram_chat_unavailable"
        reminder.next_attempt_at = None
        session.commit()

        assert sync_weekly_check_in_reminders(session) == 0
        session.refresh(reminder)
        assert reminder.status == "cancelled"
        assert reminder.attempt_count == 1
        assert reminder.last_error == "telegram_chat_unavailable"


def test_measurement_terminal_delivery_cancellation_is_not_reactivated(monkeypatch) -> None:
    local_day = date(2026, 8, 24)
    monkeypatch.setattr(notification_service, "today_in_timezone", lambda _timezone: local_day)

    with get_session_context() as session:
        user = User(telegram_user_id=86411, is_coach=False)
        session.add(user)
        session.flush()
        session.add(UserProfile(user_id=user.id, timezone="Europe/Moscow"))
        session.add(
            NotificationSetting(
                user_id=user.id,
                measurement_reminders_enabled=True,
                reminder_hour=9,
            )
        )
        session.commit()
        assert sync_measurement_reminders(session) == 1
        reminder = (
            session.query(Notification)
            .filter(
                Notification.user_id == user.id, Notification.category == "measurement_reminder"
            )
            .one()
        )
        reminder.status = "cancelled"
        reminder.attempt_count = 1
        reminder.last_error = "telegram_chat_unavailable"
        reminder.next_attempt_at = None
        session.commit()

        assert sync_measurement_reminders(session) == 0
        session.refresh(reminder)
        assert reminder.status == "cancelled"
        assert reminder.attempt_count == 1
        assert reminder.last_error == "telegram_chat_unavailable"


def test_quiet_hours_cross_midnight_and_use_account_timezone() -> None:
    with get_session_context() as session:
        user = User(telegram_user_id=86404, is_coach=False)
        session.add(user)
        session.flush()
        session.add(UserProfile(user_id=user.id, timezone="Asia/Tokyo"))
        setting = NotificationSetting(
            user_id=user.id,
            quiet_hours_start=time(22),
            quiet_hours_end=time(8),
        )
        session.add(setting)
        session.commit()
        session.refresh(user)

        retry_at = quiet_hours_retry_at(setting, user, now_local=datetime(2026, 8, 24, 23, 30))
        assert retry_at == datetime(2026, 8, 24, 23)
        assert (
            quiet_hours_retry_at(
                setting,
                user,
                now_local=datetime(2026, 8, 24, 12),
            )
            is None
        )


def test_worker_rechecks_disabled_channel_without_losing_in_app_event(monkeypatch) -> None:
    fixed_now = datetime(2026, 8, 24, 9)
    monkeypatch.setattr(notification_service, "utcnow", lambda: fixed_now)
    send = AsyncMock()
    monkeypatch.setattr(worker, "send_telegram_message", send)

    with get_session_context() as session:
        user = User(telegram_user_id=86405, is_coach=False)
        session.add(user)
        session.flush()
        session.add(UserProfile(user_id=user.id, timezone="Europe/Moscow"))
        session.add(NotificationSetting(user_id=user.id, telegram_enabled=False))
        event = Notification(
            user_id=user.id,
            channel="telegram",
            category="trainer_program_update",
            event_kind="transactional",
            title="Программа обновлена",
            body="Внутренние подробности",
            scheduled_for=fixed_now,
            scheduled_for_utc=fixed_now,
            status="queued",
            action_url="/app?section=programs",
        )
        session.add(event)
        session.commit()
        event_id = event.id

    asyncio.run(worker.run_once(sync_reminders=False))
    send.assert_not_awaited()
    with get_session_context() as session:
        stored = session.get(Notification, event_id)
        assert stored.status == "cancelled"
        assert stored.last_error == "telegram_channel_disabled"
        assert stored.title == "Программа обновлена"
        assert stored.body == "Внутренние подробности"


def test_telegram_copy_is_neutral_and_does_not_expose_event_body() -> None:
    event = Notification(
        user_id=1,
        category="trainer_comment",
        event_kind="transactional",
        title="Sensitive title",
        body="Private body measurements and trainer text",
        scheduled_for=datetime(2026, 8, 24, 9),
        scheduled_for_utc=datetime(2026, 8, 24, 6),
    )

    rendered = neutral_telegram_text(event)
    assert "Sensitive" not in rendered
    assert "measurements" not in rendered
    assert rendered == "У вас новый комментарий тренера. Подробности — в приложении."


def test_notification_open_is_owned_idempotent_and_stale_safe(client) -> None:
    first_headers = auth(client, 86406)
    second_headers = auth(client, 86407)
    with get_session_context() as session:
        first = session.query(User).filter(User.telegram_user_id == 86406).one()
        stale = Notification(
            user_id=first.id,
            channel="telegram",
            category="trainer_comment",
            event_kind="transactional",
            title="Старый комментарий",
            body="Связанный объект удалён",
            scheduled_for=datetime(2026, 8, 24, 9),
            scheduled_for_utc=datetime(2026, 8, 24, 6),
            status="sent",
            action_url="/app?workout_id=999999&comment_id=999999",
        )
        session.add(stale)
        session.commit()
        notification_id = stale.id

    unauthorized = client.post(
        f"/api/v1/notifications/{notification_id}/open",
        headers=second_headers,
    )
    assert unauthorized.status_code == 404

    first_open = client.post(
        f"/api/v1/notifications/{notification_id}/open",
        headers=first_headers,
    )
    second_open = client.post(
        f"/api/v1/notifications/{notification_id}/open",
        headers=first_headers,
    )
    assert first_open.status_code == second_open.status_code == 200
    assert first_open.json() == second_open.json()
    assert first_open.json()["stale"] is True
    assert first_open.json()["destination"] == "/app?section=profile#profile-notifications"
    with get_session_context() as session:
        stored = session.get(Notification, notification_id)
        assert stored.read_at is not None
