from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal

from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.food_diary import FoodDiaryEntry
from fitminiapp_api.models.hydration import HydrationEntry
from fitminiapp_api.models.notification import Notification, NotificationSetting
from fitminiapp_api.models.reminder_template import ReminderTemplateSchedule
from fitminiapp_api.models.user import User, UserProfile
from fitminiapp_api.services import reminder_templates
from fitminiapp_api.services.notifications import neutral_telegram_text, reminder_category_enabled


def _auth(client, telegram_user_id: int) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "is_coach": False, "is_admin": False},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _add_food_entry(db, user_id: int, *, diary_date: date, meal_type: str) -> None:
    db.add(
        FoodDiaryEntry(
            user_id=user_id,
            diary_date=diary_date,
            meal_type=meal_type,
            entry_kind="quick_add",
            amount=Decimal("1"),
            amount_unit="serving",
            weight_g=Decimal("1"),
            food_name="Быстрая запись",
            energy_kcal_per_100g=Decimal("100"),
            protein_g_per_100g=Decimal("10"),
            fat_g_per_100g=Decimal("5"),
            carbs_g_per_100g=Decimal("10"),
            quick_energy_kcal=Decimal("100"),
            quick_protein_g=Decimal("10"),
            quick_fat_g=Decimal("5"),
            quick_carbs_g=Decimal("10"),
        )
    )


def test_templates_are_default_off_and_update_is_idempotent(client) -> None:
    headers = _auth(client, 84_001)

    listed = client.get("/api/v1/notifications/templates", headers=headers)
    assert listed.status_code == 200
    templates = listed.json()
    assert [template["template_key"] for template in templates] == [
        "meal_logging",
        "hydration",
        "movement_break",
    ]
    assert all(template["default_enabled"] is False for template in templates)
    assert all(template["enabled"] is False for template in templates)
    assert templates[0]["times"] == ["08:00:00", "13:00:00", "19:00:00"]
    assert templates[1]["window_start"] == "09:00:00"
    assert templates[1]["window_end"] == "21:00:00"

    payload = {
        "enabled": True,
        "weekdays": [0, 1, 2, 3, 4, 5, 6],
        "times": ["09:00:00", "14:00:00", "20:00:00"],
        "max_per_day": 3,
        "minimum_spacing_minutes": 120,
    }
    saved = client.patch(
        "/api/v1/notifications/templates/meal_logging", headers=headers, json=payload
    )
    replay = client.patch(
        "/api/v1/notifications/templates/meal_logging", headers=headers, json=payload
    )
    assert saved.status_code == replay.status_code == 200
    assert saved.json()["enabled"] is True
    assert replay.json()["times"] == ["09:00:00", "14:00:00", "20:00:00"]

    invalid = client.patch(
        "/api/v1/notifications/templates/meal_logging",
        headers=headers,
        json={"times": ["09:00:00", "09:30:00"], "max_per_day": 2},
    )
    assert invalid.status_code == 422


def test_contextual_sync_suppresses_logged_meals_and_recent_hydration(monkeypatch) -> None:
    fixed_now = datetime(2026, 3, 8, 7)
    monkeypatch.setattr(reminder_templates, "now_for_user_naive", lambda _user: fixed_now)

    with get_session_context() as db:
        user = User(telegram_user_id=84_002, is_coach=False)
        db.add(user)
        db.flush()
        db.add(UserProfile(user_id=user.id, timezone="America/New_York"))
        db.add(
            NotificationSetting(
                user_id=user.id,
                meal_reminders_enabled=True,
                hydration_reminders_enabled=True,
            )
        )
        meal_schedule = ReminderTemplateSchedule(
            user_id=user.id,
            template_key="meal_logging",
            template_version="v1",
            weekdays=[6],
            schedule_times=["09:00:00", "13:00:00", "19:00:00"],
            max_per_day=3,
            minimum_spacing_minutes=120,
        )
        hydration_schedule = ReminderTemplateSchedule(
            user_id=user.id,
            template_key="hydration",
            template_version="v1",
            weekdays=[6],
            schedule_times=[],
            window_start=time(9),
            window_end=time(13),
            interval_minutes=120,
            max_per_day=3,
            minimum_spacing_minutes=120,
        )
        db.add_all([meal_schedule, hydration_schedule])
        db.flush()
        _add_food_entry(db, user.id, diary_date=date(2026, 3, 8), meal_type="lunch")
        db.add(
            HydrationEntry(
                user_id=user.id,
                occurred_at=datetime(2026, 3, 8, 12, 30, tzinfo=UTC),
                diary_date=date(2026, 3, 8),
                timezone="America/New_York",
                volume_ml=250,
                beverage_type="water",
                source="manual",
                request_key="contextual-hydration-test",
                payload_fingerprint="contextual-hydration-fingerprint",
            )
        )
        db.commit()

        assert reminder_templates.sync_contextual_reminders(db) == 4
        assert reminder_templates.sync_contextual_reminders(db) == 0
        rows = (
            db.query(Notification)
            .filter(Notification.user_id == user.id)
            .order_by(Notification.scheduled_for.asc())
            .all()
        )
        assert [(row.category, row.scheduled_for.time()) for row in rows] == [
            ("meal_logging_reminder", time(9)),
            ("hydration_reminder", time(11)),
            ("hydration_reminder", time(13)),
            ("meal_logging_reminder", time(19)),
        ]
        assert all("&meal=lunch" not in (row.action_url or "") for row in rows)
        assert rows[0].action_url == "/app?section=nutrition&date=2026-03-08&meal=breakfast"
        assert rows[1].scheduled_for_utc == datetime(2026, 3, 8, 15)
        assert len({row.dedupe_key for row in rows}) == len(rows)

        settings = db.query(NotificationSetting).filter_by(user_id=user.id).one()
        settings.meal_reminders_enabled = False
        db.commit()
        assert reminder_templates.sync_contextual_reminders(db) == 0
        assert (
            db.query(Notification)
            .filter(
                Notification.user_id == user.id,
                Notification.category == "meal_logging_reminder",
                Notification.status == "queued",
            )
            .count()
            == 0
        )


def test_contextual_sync_skips_quiet_and_missed_slots_without_catch_up(monkeypatch) -> None:
    fixed_now = datetime(2026, 8, 24, 9)
    monkeypatch.setattr(reminder_templates, "now_for_user_naive", lambda _user: fixed_now)

    with get_session_context() as db:
        user = User(telegram_user_id=84_003, is_coach=False)
        db.add(user)
        db.flush()
        db.add(UserProfile(user_id=user.id, timezone="Europe/Moscow"))
        db.add(
            NotificationSetting(
                user_id=user.id,
                movement_reminders_enabled=True,
                quiet_hours_start=time(22),
                quiet_hours_end=time(8),
            )
        )
        db.add(
            ReminderTemplateSchedule(
                user_id=user.id,
                template_key="movement_break",
                template_version="v1",
                weekdays=list(range(7)),
                schedule_times=[],
                window_start=time(7),
                window_end=time(8),
                interval_minutes=30,
                max_per_day=2,
                minimum_spacing_minutes=30,
            )
        )
        db.commit()

        assert reminder_templates.sync_contextual_reminders(db) == 0
        assert db.query(Notification).filter(Notification.user_id == user.id).count() == 0


def test_contextual_scheduler_cancellation_reactivates_but_terminal_does_not(monkeypatch) -> None:
    fixed_now = datetime(2026, 8, 24, 9)
    monkeypatch.setattr(reminder_templates, "now_for_user_naive", lambda _user: fixed_now)

    with get_session_context() as db:
        user = User(telegram_user_id=84_006, is_coach=False)
        db.add(user)
        db.flush()
        db.add(UserProfile(user_id=user.id, timezone="Europe/Moscow"))
        setting = NotificationSetting(user_id=user.id, meal_reminders_enabled=True)
        db.add(setting)
        db.add(
            ReminderTemplateSchedule(
                user_id=user.id,
                template_key="meal_logging",
                template_version="v1",
                weekdays=[0],
                schedule_times=["10:00:00"],
                max_per_day=1,
                minimum_spacing_minutes=120,
            )
        )
        db.commit()

        assert reminder_templates.sync_contextual_reminders(db) == 1
        reminder = db.query(Notification).filter(Notification.user_id == user.id).one()

        setting.meal_reminders_enabled = False
        db.commit()
        assert reminder_templates.sync_contextual_reminders(db) == 0
        db.refresh(reminder)
        assert reminder.status == "cancelled"
        assert reminder.last_error == "contextual_reminder_not_due"

        setting.meal_reminders_enabled = True
        db.commit()
        assert reminder_templates.sync_contextual_reminders(db) == 0
        db.refresh(reminder)
        assert reminder.status == "queued"
        assert reminder.last_error is None

        reminder.status = "cancelled"
        reminder.attempt_count = 1
        reminder.last_error = "telegram_chat_unavailable"
        db.commit()
        assert reminder_templates.sync_contextual_reminders(db) == 0
        db.refresh(reminder)
        assert reminder.status == "cancelled"
        assert reminder.attempt_count == 1
        assert reminder.last_error == "telegram_chat_unavailable"


def test_contextual_dedupe_is_scoped_per_user(monkeypatch) -> None:
    fixed_now = datetime(2026, 3, 8, 7)
    monkeypatch.setattr(reminder_templates, "now_for_user_naive", lambda _user: fixed_now)

    with get_session_context() as db:
        users = [
            User(telegram_user_id=84_004, is_coach=False),
            User(telegram_user_id=84_005, is_coach=False),
        ]
        db.add_all(users)
        db.flush()
        for user in users:
            db.add(UserProfile(user_id=user.id, timezone="Europe/Moscow"))
            db.add(NotificationSetting(user_id=user.id, meal_reminders_enabled=True))
            db.add(
                ReminderTemplateSchedule(
                    user_id=user.id,
                    template_key="meal_logging",
                    template_version="v1",
                    weekdays=[6],
                    schedule_times=["09:00:00"],
                    max_per_day=1,
                    minimum_spacing_minutes=120,
                )
            )
        db.commit()

        assert reminder_templates.sync_contextual_reminders(db) == 2
        rows = db.query(Notification).order_by(Notification.user_id.asc()).all()
        assert len(rows) == 2
        assert rows[0].dedupe_key != rows[1].dedupe_key
        assert reminder_templates.sync_contextual_reminders(db) == 0


def test_contextual_categories_are_rechecked_and_telegram_copy_is_neutral() -> None:
    setting = NotificationSetting(
        meal_reminders_enabled=True,
        hydration_reminders_enabled=True,
        movement_reminders_enabled=True,
    )
    for category, flag, expected in (
        (
            "meal_logging_reminder",
            "meal_reminders_enabled",
            "Можно записать приём пищи. Подробности — в приложении.",
        ),
        (
            "hydration_reminder",
            "hydration_reminders_enabled",
            "Можно выпить воды. Подробности — в приложении.",
        ),
        (
            "movement_break_reminder",
            "movement_reminders_enabled",
            "Пора сделать короткий перерыв и немного подвигаться. Подробности — в приложении.",
        ),
    ):
        notification = Notification(
            user_id=1,
            category=category,
            event_kind="reminder",
            title="Внутренний заголовок",
            body="Внутреннее тело",
            scheduled_for=datetime(2026, 8, 24, 9),
            scheduled_for_utc=datetime(2026, 8, 24, 6),
        )
        assert reminder_category_enabled(notification, setting) is True
        assert neutral_telegram_text(notification) == expected
        setattr(setting, flag, False)
        assert reminder_category_enabled(notification, setting) is False
