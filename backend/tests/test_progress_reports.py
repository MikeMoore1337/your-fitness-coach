from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from fitminiapp_api.core.timezone import today_msk
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.check_in import WeeklyCheckIn
from fitminiapp_api.models.exercise import Exercise
from fitminiapp_api.models.food_diary import FoodDiaryDayStatus, FoodDiaryEntry
from fitminiapp_api.models.nutrition import NutritionTarget
from fitminiapp_api.models.program import (
    UserProgram,
    UserWorkout,
    UserWorkoutExercise,
    UserWorkoutSet,
)
from fitminiapp_api.models.user import BodyMeasurement, CoachClient, User
from fitminiapp_api.schemas.progress import NutritionReportPeriod
from fitminiapp_api.services import progress_report_pdf
from fitminiapp_api.services.progress_reports import build_progress_report


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


def _seed_report_data(user_id: int) -> None:
    today = today_msk()
    with get_session_context() as db:
        user = db.get(User, user_id)
        assert user is not None and user.profile is not None
        user.profile.full_name = "Александр Очень-Длинное-Имя Для Отчёта"
        user.profile.goal = "muscle_gain"
        program = UserProgram(
            user_id=user_id,
            start_date=today - timedelta(days=28),
            duration_weeks=8,
            schedule_weekdays=[0, 3],
            status="active",
            is_active=True,
        )
        db.add(program)
        db.flush()
        exercise_id = db.query(Exercise.id).order_by(Exercise.id).limit(1).scalar()
        completed = UserWorkout(
            user_program_id=program.id,
            scheduled_date=today - timedelta(days=4),
            day_number=1,
            week_number=4,
            title="Силовая тренировка",
            status="completed",
            completed_at=datetime.combine(today - timedelta(days=4), datetime.min.time()),
        )
        skipped = UserWorkout(
            user_program_id=program.id,
            scheduled_date=today - timedelta(days=2),
            day_number=2,
            week_number=4,
            title="Вторая тренировка",
            status="skipped",
        )
        db.add_all([completed, skipped])
        db.flush()
        workout_exercise = UserWorkoutExercise(
            workout_id=completed.id,
            exercise_id=exercise_id,
            sort_order=1,
            prescribed_sets=1,
            prescribed_reps="8",
            rest_seconds=90,
        )
        db.add(workout_exercise)
        db.flush()
        db.add(
            UserWorkoutSet(
                workout_exercise_id=workout_exercise.id,
                set_number=1,
                actual_reps=8,
                actual_weight=Decimal("50"),
                is_completed=True,
                set_kind="working",
            )
        )
        db.add_all(
            [
                BodyMeasurement(
                    user_id=user_id,
                    measured_on=today - timedelta(days=20),
                    weight_kg=80,
                    waist_cm=90,
                ),
                BodyMeasurement(
                    user_id=user_id,
                    measured_on=today - timedelta(days=3),
                    weight_kg=79,
                    waist_cm=89,
                ),
                NutritionTarget(
                    user_id=user_id,
                    assigned_by_user_id=user_id,
                    effective_from=today - timedelta(days=30),
                    source="manual",
                    calories=2200,
                    protein_g=160,
                    fat_g=70,
                    carbs_g=240,
                ),
                FoodDiaryEntry(
                    user_id=user_id,
                    diary_date=today - timedelta(days=1),
                    meal_type="dinner",
                    amount=Decimal("1000"),
                    amount_unit="g",
                    weight_g=Decimal("1000"),
                    food_name="Содержимое дневника не должно попасть в отчёт",
                    energy_kcal_per_100g=Decimal("210"),
                    protein_g_per_100g=Decimal("15.5"),
                    fat_g_per_100g=Decimal("6.8"),
                    carbs_g_per_100g=Decimal("23"),
                ),
                FoodDiaryDayStatus(
                    user_id=user_id,
                    diary_date=today - timedelta(days=1),
                    status="complete",
                ),
                WeeklyCheckIn(
                    user_id=user_id,
                    week_start=today - timedelta(days=6),
                    week_end=today,
                    submitted_on=today - timedelta(days=1),
                    timezone="Europe/Moscow",
                    status="completed",
                    summary_version="weekly-check-in-summary-v1",
                    summary={},
                    training_load=4,
                    recovery=3,
                    hunger=2,
                    adherence_difficulty=2,
                    note="Фактическая заметка пользователя " + "очень длинная " * 20,
                ),
            ]
        )


def test_progress_report_reuses_canonical_facts_without_internal_ids(client) -> None:
    headers = _auth(client, 67_001)
    user_id = _user_id(67_001)
    _seed_report_data(user_id)
    today = today_msk()

    response = client.get(
        "/api/v1/workouts/progress/report",
        params={
            "period": "custom",
            "date_from": (today - timedelta(days=29)).isoformat(),
            "date_to": today.isoformat(),
        },
        headers=headers,
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["subject"] == {
        "name": "Александр Очень-Длинное-Имя Для Отчёта",
        "role": "self",
        "goal": "muscle_gain",
    }
    assert payload["period_start"] == (today - timedelta(days=29)).isoformat()
    assert payload["period_end"] == today.isoformat()
    assert payload["timezone"] == "Europe/Moscow"
    assert payload["training"]["planned_workouts"] == 2
    assert payload["training"]["completed_workouts"] == 1
    assert payload["training"]["skipped_workouts"] == 1
    assert payload["training"]["completed_working_sets"] == 1
    assert payload["training"]["external_load_volume_kg"] == 400.0
    assert (
        payload["training"]["exercises"][0]["sessions"][0]["performed_on"]
        == (today - timedelta(days=4)).isoformat()
    )
    assert (
        payload["body"]["trends"][0]["first_measured_on"]
        == (today - timedelta(days=20)).isoformat()
    )
    assert payload["nutrition"]["summary"]["logged_days"] == 1
    assert payload["nutrition"]["summary"]["missing_days"] == 29
    assert payload["nutrition"]["target_changes"] == []
    assert payload["program"]["title"] == "Текущая программа"
    assert payload["check_ins"][0]["recovery"] == 3
    assert "food_name" not in response.text
    assert "Содержимое дневника" not in response.text
    assert "user_id" not in response.text
    assert '"id"' not in response.text


def test_progress_report_download_uses_custom_definition_label_in_pdf(client, monkeypatch) -> None:
    headers = _auth(client, 67_051)
    user_id = _user_id(67_051)
    _seed_report_data(user_id)
    definition = client.post(
        "/api/v1/workouts/diary/custom-definitions",
        json={"label": "Пользовательский показатель"},
        headers=headers,
    )
    assert definition.status_code == 201, definition.text
    measurement = client.post(
        "/api/v1/workouts/diary",
        json={
            "measured_on": today_msk().isoformat(),
            "custom_values": [{"definition_id": definition.json()["id"], "value": 86}],
        },
        headers=headers,
    )
    assert measurement.status_code == 200, measurement.text

    rendered_paragraphs: list[str] = []
    original_paragraph = progress_report_pdf.Paragraph

    def capture_paragraph(text, style, *args, **kwargs):
        rendered_paragraphs.append(str(text))
        return original_paragraph(text, style, *args, **kwargs)

    monkeypatch.setattr(progress_report_pdf, "Paragraph", capture_paragraph)
    created = client.post(
        "/api/v1/workouts/progress/report/download-link",
        params={"period": "days_30"},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    downloaded = client.get(created.json()["url"])
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.content.startswith(b"%PDF-")
    assert any("Пользовательский показатель" in paragraph for paragraph in rendered_paragraphs)
    assert all("custom:" not in paragraph for paragraph in rendered_paragraphs)

    with get_session_context() as db:
        user = db.get(User, user_id)
        assert user is not None
        report = build_progress_report(
            db,
            user,
            NutritionReportPeriod.DAYS_30,
        )
    custom_trend = next(
        trend
        for trend in report["body"]["trends"]
        if trend["definition_id"] == definition.json()["id"]
    )
    assert custom_trend["label"] == "Пользовательский показатель"
    assert custom_trend["latest_value"] == 86


def test_progress_report_pdf_uses_neutral_label_for_missing_custom_definition_label() -> None:
    assert progress_report_pdf._body_metric(
        "custom:1",
        label="",
        unit="cm",
    ) == ("Пользовательский показатель", " см")


def test_progress_report_validates_bounds_and_trainer_access_revocation(client) -> None:
    own_headers = _auth(client, 67_101)
    coach_headers = _auth(client, 67_102, is_coach=True)
    other_coach_headers = _auth(client, 67_103, is_coach=True)
    user_id = _user_id(67_101)
    coach_id = _user_id(67_102)
    today = today_msk()
    with get_session_context() as db:
        db.add(CoachClient(coach_user_id=coach_id, client_user_id=user_id, status="active"))

    invalid = client.get(
        "/api/v1/workouts/progress/report",
        params={"period": "custom"},
        headers=own_headers,
    )
    assert invalid.status_code == 422
    too_long = client.get(
        "/api/v1/workouts/progress/report",
        params={
            "period": "custom",
            "date_from": (today - timedelta(days=366)).isoformat(),
            "date_to": today.isoformat(),
        },
        headers=own_headers,
    )
    assert too_long.status_code == 422

    allowed = client.get(
        f"/api/v1/coach/clients/{user_id}/progress-report?period=days_7",
        headers=coach_headers,
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["subject"]["role"] == "client"
    denied = client.get(
        f"/api/v1/coach/clients/{user_id}/progress-report?period=days_7",
        headers=other_coach_headers,
    )
    assert denied.status_code == 404

    with get_session_context() as db:
        relation = db.query(CoachClient).filter(CoachClient.client_user_id == user_id).one()
        relation.status = "ended"
    revoked = client.get(
        f"/api/v1/coach/clients/{user_id}/progress-report?period=days_7",
        headers=coach_headers,
    )
    assert revoked.status_code == 404


def test_historical_range_evaluates_its_last_day(client) -> None:
    headers = _auth(client, 67_201)
    user_id = _user_id(67_201)
    _seed_report_data(user_id)
    today = today_msk()
    historical_end = today - timedelta(days=2)
    with get_session_context() as db:
        workout = (
            db.query(UserWorkout)
            .join(UserProgram, UserProgram.id == UserWorkout.user_program_id)
            .filter(
                UserProgram.user_id == user_id,
                UserWorkout.scheduled_date == historical_end,
            )
            .one()
        )
        workout.status = "planned"

    response = client.get(
        "/api/v1/workouts/progress/report",
        params={
            "period": "custom",
            "date_from": (today - timedelta(days=4)).isoformat(),
            "date_to": historical_end.isoformat(),
        },
        headers=headers,
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    training = payload["training"]
    assert training["planned_workouts"] == 2
    assert training["completed_workouts"] == 1
    assert training["skipped_workouts"] == 0
    assert payload["data_sufficiency"]["nutrition_coverage"]["counters"]["eligible_day_count"] == 3


def test_progress_report_download_link_returns_a_native_pdf_file(client) -> None:
    headers = _auth(client, 67_301)
    user_id = _user_id(67_301)
    _seed_report_data(user_id)

    created = client.post(
        "/api/v1/workouts/progress/report/download-link",
        params={"period": "days_30"},
        headers=headers,
    )

    assert created.status_code == 200, created.text
    link = created.json()
    assert link["filename"].startswith("progress-report-")
    assert link["filename"].endswith(".pdf")
    assert link["url"].startswith(
        "https://app.your-fitness-coach.ru/api/v1/workouts/progress/report/file/"
    )

    downloaded = client.get(link["url"])
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.headers["content-type"] == "application/pdf"
    assert downloaded.headers["content-disposition"] == f'attachment; filename="{link["filename"]}"'
    assert downloaded.headers["access-control-allow-origin"] == "https://web.telegram.org"
    assert set(downloaded.headers["cache-control"].split(", ")) == {"private", "no-store"}
    assert int(downloaded.headers["content-length"]) == len(downloaded.content)
    assert downloaded.content.startswith(b"%PDF-")
    assert len(downloaded.content) > 5_000

    invalid = client.get("/api/v1/workouts/progress/report/file/not-a-token")
    assert invalid.status_code == 404


def test_coach_progress_report_download_rechecks_active_relationship(client) -> None:
    _auth(client, 67_401)
    coach_headers = _auth(client, 67_402, is_coach=True)
    user_id = _user_id(67_401)
    coach_id = _user_id(67_402)
    with get_session_context() as db:
        db.add(CoachClient(coach_user_id=coach_id, client_user_id=user_id, status="active"))

    created = client.post(
        f"/api/v1/coach/clients/{user_id}/progress-report/download-link",
        params={"period": "days_7"},
        headers=coach_headers,
    )
    assert created.status_code == 200, created.text
    file_url = created.json()["url"]

    with get_session_context() as db:
        relation = db.query(CoachClient).filter(CoachClient.client_user_id == user_id).one()
        relation.status = "ended"

    revoked = client.get(file_url)
    assert revoked.status_code == 404
