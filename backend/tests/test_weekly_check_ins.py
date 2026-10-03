from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.check_in import WeeklyCheckIn
from fitminiapp_api.models.food_diary import FoodDiaryDayStatus, FoodDiaryEntry
from fitminiapp_api.models.lifecycle_milestone import LifecycleMilestone
from fitminiapp_api.models.notification import Notification, NotificationSetting
from fitminiapp_api.models.nutrition import NutritionTarget
from fitminiapp_api.models.user import BodyMeasurement, CoachClient, User
from fitminiapp_api.services import measurements as measurements_service
from fitminiapp_api.services import notifications as notifications_service
from fitminiapp_api.services import progress_weekly_action as progress_action_service
from fitminiapp_api.services import weekly_check_ins as check_in_service
from fitminiapp_api.services.notifications import sync_weekly_check_in_reminders


def _auth(client, telegram_user_id: int, *, is_coach: bool = False) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "is_coach": is_coach},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _user_id(telegram_user_id: int) -> int:
    with get_session_context() as db:
        return db.query(User.id).filter(User.telegram_user_id == telegram_user_id).scalar()


def test_weekly_action_is_tied_to_the_saved_cycle_and_measurement_completion_is_idempotent(
    client, monkeypatch
) -> None:
    headers = _auth(client, 34_051)
    user_id = _user_id(34_051)
    fixed_local_day = date(2030, 1, 10)
    monkeypatch.setattr(check_in_service, "today_for_user", lambda _user: fixed_local_day)
    monkeypatch.setattr(progress_action_service, "today_for_user", lambda _user: fixed_local_day)
    monkeypatch.setattr(measurements_service, "today_for_user", lambda _user: fixed_local_day)

    before_review = client.get("/api/v1/check-ins/weekly/current", headers=headers)
    assert before_review.status_code == 200
    assert before_review.json()["progress_action"] == {
        "kind": "weekly_review",
        "status": "available",
        "target": "weekly_review",
        "reason": "review_required",
        "title": "Пройти недельный обзор",
        "detail": "Сверьте факты недели и зафиксируйте следующий шаг.",
        "completed_at": None,
    }

    with get_session_context() as db:
        user = db.get(User, user_id)
        assert user is not None and user.profile is not None
        row = WeeklyCheckIn(
            user_id=user_id,
            week_start=date(2030, 1, 7),
            week_end=date(2030, 1, 13),
            submitted_on=fixed_local_day,
            timezone=user.profile.timezone,
            status="completed",
            summary_version="weekly-review-summary-v2",
            summary=before_review.json()["summary"],
            progress_action_kind="measurement",
            created_at=datetime(2020, 1, 1),
        )
        db.add(row)
        db.commit()

    current = client.get("/api/v1/check-ins/weekly/current", headers=headers)
    assert current.status_code == 200
    assert current.json()["progress_action"]["kind"] == "measurement"
    assert current.json()["progress_action"]["status"] == "available"

    first = client.post(
        "/api/v1/workouts/diary",
        headers=headers,
        json={"measured_on": fixed_local_day.isoformat(), "weight_kg": 75},
    )
    assert first.status_code == 200, first.text
    second = client.post(
        "/api/v1/workouts/diary",
        headers=headers,
        json={"measured_on": fixed_local_day.isoformat(), "weight_kg": 75},
    )
    assert second.status_code == 200, second.text

    with get_session_context() as db:
        saved = db.query(WeeklyCheckIn).filter(WeeklyCheckIn.user_id == user_id).one()
        assert saved.progress_action_completed_at is not None
        assert (
            db.query(LifecycleMilestone)
            .filter(
                LifecycleMilestone.user_id == user_id,
                LifecycleMilestone.milestone_type == "progress_next_action_completed",
            )
            .count()
            == 1
        )

    completed = client.get("/api/v1/check-ins/weekly/current", headers=headers)
    assert completed.json()["progress_action"]["status"] == "completed"
    assert completed.json()["progress_action"]["title"] == "Шаг выполнен"


def test_weekly_check_in_uses_local_week_snapshots_summary_and_rejects_duplicate(
    client, monkeypatch
) -> None:
    headers = _auth(client, 34_001)
    other_headers = _auth(client, 34_002)
    user_id = _user_id(34_001)
    fixed_local_day = date(2030, 1, 10)
    monkeypatch.setattr(check_in_service, "today_for_user", lambda _user: fixed_local_day)

    with get_session_context() as db:
        user = db.get(User, user_id)
        assert user is not None and user.profile is not None
        user.profile.timezone = "Pacific/Kiritimati"
        user.profile.goal = "muscle_gain"
        db.add_all(
            [
                BodyMeasurement(
                    user_id=user_id,
                    measured_on=fixed_local_day - timedelta(days=30),
                    weight_kg=80,
                    waist_cm=90,
                ),
                BodyMeasurement(
                    user_id=user_id,
                    measured_on=fixed_local_day - timedelta(days=15),
                    weight_kg=79.5,
                    waist_cm=89.5,
                ),
                BodyMeasurement(
                    user_id=user_id,
                    measured_on=fixed_local_day,
                    weight_kg=79,
                    waist_cm=89,
                ),
            ]
        )

    current = client.get("/api/v1/check-ins/weekly/current", headers=headers)
    assert current.status_code == 200, current.text
    assert current.json()["week_start"] == "2030-01-07"
    assert current.json()["week_end"] == "2030-01-13"
    assert current.json()["timezone"] == "Pacific/Kiritimati"
    summary = current.json()["summary"]
    assert summary["ruleset_version"] == "weekly-review-summary-v2"
    assert summary["period_start"] == "2030-01-07"
    assert summary["period_end"] == "2030-01-10"
    assert summary["goal"] == "muscle_gain"
    assert summary["weight_trend"]["change"] == -1.0
    assert [row["metric"] for row in summary["anthropometry_trends"]] == ["waist_cm"]
    assert summary["data_sufficiency"]["anthropometry"]["status"] == "sufficient"

    created = client.post(
        "/api/v1/check-ins/weekly",
        headers=headers,
        json={
            "status": "completed",
            "training_load": 4,
            "recovery": 3,
            "hunger": 2,
            "adherence_difficulty": 1,
            "note": "  Хорошая неделя  ",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["note"] == "Хорошая неделя"
    assert created.json()["summary"] == {
        **summary,
        "adaptive_energy": created.json()["summary"]["adaptive_energy"],
    }
    assert created.json()["summary"]["adaptive_energy"]["decision"] == "not_available"

    with get_session_context() as db:
        user = db.get(User, user_id)
        assert user is not None and user.profile is not None
        user.profile.goal = "weight_loss"

    saved_current = client.get("/api/v1/check-ins/weekly/current", headers=headers)
    assert saved_current.status_code == 200
    assert saved_current.json()["existing"]["summary"]["goal"] == "muscle_gain"
    assert saved_current.json()["summary"]["goal"] == "muscle_gain"

    duplicate = client.post(
        "/api/v1/check-ins/weekly",
        headers=headers,
        json={"status": "skipped"},
    )
    assert duplicate.status_code == 409

    history = client.get("/api/v1/check-ins/weekly?limit=1&offset=0", headers=headers)
    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert history.json()["items"][0]["user_id"] == user_id
    exported = client.get("/api/v1/me/export", headers=headers)
    assert exported.status_code == 200
    assert exported.json()["weekly_check_ins"][0]["summary_version"] == ("weekly-review-summary-v2")
    assert client.get("/api/v1/check-ins/weekly", headers=other_headers).json()["items"] == []


def test_weekly_check_in_skip_optional_validation_and_timezone_week_boundary(
    client, monkeypatch
) -> None:
    first_headers = _auth(client, 34_101)
    second_headers = _auth(client, 34_102)
    first_id = _user_id(34_101)
    second_id = _user_id(34_102)

    with get_session_context() as db:
        first = db.get(User, first_id)
        second = db.get(User, second_id)
        assert first is not None and first.profile is not None
        assert second is not None and second.profile is not None
        first.profile.timezone = "Pacific/Honolulu"
        second.profile.timezone = "Pacific/Kiritimati"

    def local_day(user: User) -> date:
        return (
            date(2030, 1, 6)
            if user.profile and user.profile.timezone == "Pacific/Honolulu"
            else date(2030, 1, 7)
        )

    monkeypatch.setattr(check_in_service, "today_for_user", local_day)
    first = client.get("/api/v1/check-ins/weekly/current", headers=first_headers).json()
    second = client.get("/api/v1/check-ins/weekly/current", headers=second_headers).json()
    assert first["week_start"] == "2029-12-31"
    assert second["week_start"] == "2030-01-07"

    skipped = client.post(
        "/api/v1/check-ins/weekly",
        headers=second_headers,
        json={"status": "skipped"},
    )
    assert skipped.status_code == 201
    assert skipped.json()["training_load"] is None
    assert skipped.json()["status"] == "skipped"
    skipped_id = skipped.json()["id"]

    deleted = client.request(
        "DELETE",
        "/api/v1/me/account",
        headers=second_headers,
        json={"confirmation": "DELETE"},
    )
    assert deleted.status_code == 204
    with get_session_context() as db:
        assert db.get(WeeklyCheckIn, skipped_id) is None

    invalid = client.post(
        "/api/v1/check-ins/weekly",
        headers=first_headers,
        json={"status": "completed", "recovery": 6},
    )
    assert invalid.status_code == 422


def test_weekly_review_separates_diary_states_and_only_marks_selected_low_days(
    client, monkeypatch
) -> None:
    headers = _auth(client, 34_150)
    user_id = _user_id(34_150)
    fixed_local_day = date(2026, 8, 21)
    monkeypatch.setattr(check_in_service, "today_for_user", lambda _user: fixed_local_day)

    with get_session_context() as db:
        db.add(
            NutritionTarget(
                user_id=user_id,
                assigned_by_user_id=user_id,
                effective_from=date(2026, 8, 1),
                source="manual",
                calories=2000,
                protein_g=140,
                fat_g=70,
                carbs_g=200,
            )
        )
        for diary_date, calories, status in (
            (date(2026, 8, 18), 600, "complete"),
            (date(2026, 8, 19), 300, "incomplete"),
        ):
            db.add(
                FoodDiaryEntry(
                    user_id=user_id,
                    diary_date=diary_date,
                    meal_type="lunch",
                    amount=Decimal("100"),
                    amount_unit="g",
                    weight_g=Decimal("100"),
                    food_name="Тестовый день",
                    energy_kcal_per_100g=Decimal(calories),
                    protein_g_per_100g=Decimal("0"),
                    fat_g_per_100g=Decimal("0"),
                    carbs_g_per_100g=Decimal("0"),
                )
            )
            db.add(FoodDiaryDayStatus(user_id=user_id, diary_date=diary_date, status=status))
        db.add(FoodDiaryDayStatus(user_id=user_id, diary_date=date(2026, 8, 20), status="fasted"))

    summary = client.get("/api/v1/check-ins/weekly/current", headers=headers).json()["summary"]
    assert summary["nutrition"]["complete_days"] == 1
    assert summary["nutrition"]["incomplete_days"] == 1
    assert summary["nutrition"]["fasted_days"] == 1
    assert summary["nutrition"]["unlogged_days"] == 2
    assert summary["nutrition"]["current_target"] == {
        "effective_from": "2026-08-01",
        "source": "manual",
        "calories": 2000,
        "protein_g": 140,
        "fat_g": 70,
        "carbs_g": 200,
    }
    assert summary["nutrition"]["suspicious_low_days"] == [
        {
            "diary_date": "2026-08-18",
            "calories": 600,
            "target_calories": 2000,
        }
    ]

    marked = client.put(
        "/api/v1/nutrition/diary/status",
        headers=headers,
        json={"diary_date": "2026-08-18", "status": "incomplete"},
    )
    assert marked.status_code == 200
    updated = client.get("/api/v1/check-ins/weekly/current", headers=headers).json()["summary"]
    assert updated["nutrition"]["complete_days"] == 0
    assert updated["nutrition"]["incomplete_days"] == 2
    assert updated["nutrition"]["fasted_days"] == 1
    assert updated["nutrition"]["unlogged_days"] == 2
    assert updated["nutrition"]["suspicious_low_days"] == []


def test_weekly_review_flags_explicitly_complete_zero_day_without_counting_unlogged_day(
    client, monkeypatch
) -> None:
    headers = _auth(client, 34_151)
    user_id = _user_id(34_151)
    monkeypatch.setattr(check_in_service, "today_for_user", lambda _user: date(2026, 8, 19))

    with get_session_context() as db:
        db.add(
            NutritionTarget(
                user_id=user_id,
                assigned_by_user_id=user_id,
                effective_from=date(2026, 8, 1),
                source="manual",
                calories=2000,
                protein_g=140,
                fat_g=70,
                carbs_g=200,
            )
        )
        db.add(
            FoodDiaryDayStatus(
                user_id=user_id,
                diary_date=date(2026, 8, 17),
                status="complete",
            )
        )

    nutrition = client.get("/api/v1/check-ins/weekly/current", headers=headers).json()["summary"][
        "nutrition"
    ]
    assert nutrition["complete_days"] == 1
    assert nutrition["unlogged_days"] == 2
    assert nutrition["suspicious_low_days"] == [
        {
            "diary_date": "2026-08-17",
            "calories": 0,
            "target_calories": 2000,
        }
    ]


def test_trainer_weekly_check_in_access_is_revoked_with_relationship(client, monkeypatch) -> None:
    coach_headers = _auth(client, 34_201, is_coach=True)
    client_headers = _auth(client, 34_202)
    other_coach_headers = _auth(client, 34_203, is_coach=True)
    coach_id = _user_id(34_201)
    managed_id = _user_id(34_202)
    monkeypatch.setattr(check_in_service, "today_for_user", lambda _user: date(2030, 2, 5))

    created = client.post(
        "/api/v1/check-ins/weekly",
        headers=client_headers,
        json={"status": "completed", "recovery": 4},
    )
    assert created.status_code == 201
    with get_session_context() as db:
        db.add(CoachClient(coach_user_id=coach_id, client_user_id=managed_id, status="active"))

    allowed = client.get(
        f"/api/v1/coach/clients/{managed_id}/weekly-check-ins",
        headers=coach_headers,
    )
    assert allowed.status_code == 200
    assert allowed.json()["items"][0]["recovery"] == 4
    denied = client.get(
        f"/api/v1/coach/clients/{managed_id}/weekly-check-ins",
        headers=other_coach_headers,
    )
    assert denied.status_code == 404

    with get_session_context() as db:
        relation = db.query(CoachClient).filter(CoachClient.client_user_id == managed_id).one()
        relation.status = "ended"

    revoked = client.get(
        f"/api/v1/coach/clients/{managed_id}/weekly-check-ins",
        headers=coach_headers,
    )
    assert revoked.status_code == 404


def test_weekly_check_in_notification_respects_preference_completion_and_dedupe(
    client, monkeypatch
) -> None:
    headers = _auth(client, 34_301)
    user_id = _user_id(34_301)
    week_start = date(2030, 3, 4)
    week_end = date(2030, 3, 10)
    monkeypatch.setattr(
        notifications_service,
        "today_in_timezone",
        lambda _timezone: week_end,
    )

    updated = client.patch(
        "/api/v1/notifications/settings",
        headers=headers,
        json={
            "workout_reminders_enabled": True,
            "weekly_check_in_reminders_enabled": True,
            "reminder_hour": 18,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["weekly_check_in_reminders_enabled"] is True

    with get_session_context() as db:
        assert sync_weekly_check_in_reminders(db) >= 1
        assert sync_weekly_check_in_reminders(db) == 0
        reminder = (
            db.query(Notification)
            .filter(Notification.dedupe_key == f"weekly_check_in:{user_id}:2030-03-04")
            .one()
        )
        assert reminder.scheduled_for == datetime(2030, 3, 10, 18)
        assert reminder.action_url == "/app?section=progress&weekly_review=1"

        db.add(
            WeeklyCheckIn(
                user_id=user_id,
                week_start=week_start,
                week_end=week_end,
                submitted_on=week_end,
                timezone="Europe/Moscow",
                status="skipped",
                summary_version="weekly-check-in-summary-v1",
                summary={},
                created_at=datetime(2030, 3, 10, 12),
            )
        )

    with get_session_context() as db:
        assert sync_weekly_check_in_reminders(db) == 0
        reminder = (
            db.query(Notification)
            .filter(Notification.dedupe_key == f"weekly_check_in:{user_id}:2030-03-04")
            .one()
        )
        assert reminder.status == "cancelled"

        setting = db.query(NotificationSetting).filter_by(user_id=user_id).one()
        setting.weekly_check_in_reminders_enabled = False

    next_week_start = week_start + timedelta(days=7)
    monkeypatch.setattr(
        notifications_service,
        "today_in_timezone",
        lambda _timezone: next_week_start,
    )
    with get_session_context() as db:
        sync_weekly_check_in_reminders(db)
        assert (
            db.query(Notification)
            .filter(Notification.dedupe_key == f"weekly_check_in:{user_id}:2030-03-11")
            .first()
            is None
        )
