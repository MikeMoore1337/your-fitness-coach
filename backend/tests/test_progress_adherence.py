from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest

from fitminiapp_api.core.timezone import today_for_user, today_msk
from fitminiapp_api.db.performance import (
    begin_sql_metrics,
    current_sql_metrics,
    reset_sql_metrics,
)
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.exercise import Exercise
from fitminiapp_api.models.food_diary import FoodDiaryDayStatus, FoodDiaryEntry
from fitminiapp_api.models.nutrition import NutritionTarget
from fitminiapp_api.models.program import (
    UserProgram,
    UserWorkout,
    UserWorkoutExercise,
    UserWorkoutSet,
)
from fitminiapp_api.models.user import BodyMeasurement, CoachClient, User, UserProfile
from fitminiapp_api.services.progress import (
    build_trainer_client_summaries,
    calculate_adherence_component,
    calculate_overall_adherence,
    is_calorie_target_met,
    is_protein_target_met,
)


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


def _nutrition_target(user_id: int, *, cardio_per_week: int = 1) -> NutritionTarget:
    return NutritionTarget(
        user_id=user_id,
        sex="male",
        weight_kg=80,
        height_cm=180,
        age=30,
        daily_activity_level="moderate",
        daily_routine="mixed",
        steps_range="from_7000_to_10000",
        strength_trainings_per_week=3,
        strength_training_duration_minutes=60,
        strength_training_type="regular",
        strength_rest="one_to_two",
        cardio_trainings_per_week=cardio_per_week,
        cardio_training_duration_minutes=30,
        cardio_intensity="moderate",
        cardio_trainings=[],
        goal="maintenance",
        bmr=1800,
        tdee=2400,
        calories=2000,
        protein_g=150,
        fat_g=70,
        carbs_g=190,
        saved_at=datetime.combine(today_msk() - timedelta(days=30), time()),
    )


def _diary_entry(user_id: int, diary_date, *, weight_g: str = "200") -> FoodDiaryEntry:
    return FoodDiaryEntry(
        user_id=user_id,
        diary_date=diary_date,
        meal_type="dinner",
        amount=Decimal(weight_g),
        amount_unit="g",
        weight_g=Decimal(weight_g),
        food_name="Агрегированный тестовый рацион",
        energy_kcal_per_100g=Decimal("1000"),
        protein_g_per_100g=Decimal("75"),
        fat_g_per_100g=Decimal("10"),
        carbs_g_per_100g=Decimal("10"),
    )


def _complete_day(user_id: int, diary_date) -> FoodDiaryDayStatus:
    return FoodDiaryDayStatus(
        user_id=user_id,
        diary_date=diary_date,
        status="complete",
    )


def _add_workout(
    db,
    program: UserProgram,
    *,
    scheduled_date,
    status: str,
    exercise_id: int | None = None,
    weight: float = 20,
) -> UserWorkout:
    workout = UserWorkout(
        user_program_id=program.id,
        scheduled_date=scheduled_date,
        day_number=1,
        week_number=1,
        title="Силовая",
        status=status,
    )
    db.add(workout)
    db.flush()
    if exercise_id is not None:
        exercise = UserWorkoutExercise(
            workout_id=workout.id,
            exercise_id=exercise_id,
            sort_order=1,
            prescribed_sets=1,
            prescribed_reps="8",
            rest_seconds=60,
        )
        db.add(exercise)
        db.flush()
        db.add(
            UserWorkoutSet(
                workout_exercise_id=exercise.id,
                set_number=1,
                actual_reps=8,
                actual_weight=weight,
                is_completed=True,
            )
        )
    return workout


def test_adherence_formula_renormalizes_only_available_components() -> None:
    workouts = calculate_adherence_component(
        achieved=1,
        evaluated=2,
        weight=0.4,
        unavailable_status="not_applicable",
        unavailable_reason="no_plan",
    )
    calories = calculate_adherence_component(
        achieved=2,
        evaluated=2,
        weight=0.2,
        unavailable_status="insufficient_data",
        unavailable_reason="no_data",
    )
    cardio = calculate_adherence_component(
        achieved=0,
        evaluated=0,
        weight=0.2,
        unavailable_status="unsupported",
        unavailable_reason="cardio_log_unavailable",
    )

    overall, included = calculate_overall_adherence(
        {"workouts": workouts, "cardio": cardio, "calories": calories}
    )

    assert overall == 66.7
    assert included == ["workouts", "calories"]
    with pytest.raises(ValueError, match="achieved"):
        calculate_adherence_component(
            achieved=2,
            evaluated=1,
            weight=0.4,
            unavailable_status="not_applicable",
            unavailable_reason="no_plan",
        )
    assert is_calorie_target_met(Decimal("1800"), 2000)
    assert is_calorie_target_met(Decimal("2200"), 2000)
    assert not is_calorie_target_met(Decimal("1799.99"), 2000)
    assert not is_calorie_target_met(Decimal("2200.01"), 2000)
    assert not is_protein_target_met(Decimal("149.99"), 150)
    assert is_protein_target_met(Decimal("150"), 150)


def test_user_progress_summary_handles_periods_current_day_and_isolation(client) -> None:
    headers = _auth(client, 21_001)
    other_headers = _auth(client, 21_002)
    user_id = _user_id(21_001)
    other_user_id = _user_id(21_002)
    today = today_msk()

    empty = client.get("/api/v1/workouts/progress/summary?period_days=7", headers=headers)
    assert empty.status_code == 200
    assert empty.json()["adherence"]["overall_percent"] is None
    assert empty.json()["adherence"]["workouts"]["status"] == "not_applicable"
    assert empty.json()["adherence"]["calories"]["status"] == "not_applicable"
    empty_sufficiency = empty.json()["data_sufficiency"]
    assert empty_sufficiency["nutrition_coverage"]["status"] == "insufficient"
    assert empty_sufficiency["weight_trend"]["status"] == "insufficient"
    assert empty_sufficiency["anthropometry"]["status"] == "insufficient"
    assert empty_sufficiency["schedule_adherence"]["status"] == "insufficient"

    with get_session_context() as db:
        db.add(_nutrition_target(user_id))
    target_without_diary = client.get(
        "/api/v1/workouts/progress/summary?period_days=7", headers=headers
    )
    assert target_without_diary.status_code == 200
    assert target_without_diary.json()["adherence"]["calories"]["status"] == ("insufficient_data")

    with get_session_context() as db:
        exercise_id = db.query(Exercise.id).order_by(Exercise.id).limit(1).scalar()
        program = UserProgram(
            user_id=user_id,
            start_date=today - timedelta(days=120),
            duration_weeks=20,
            schedule_weekdays=[0],
            status="active",
            is_active=True,
        )
        db.add(program)
        db.flush()
        _add_workout(
            db,
            program,
            scheduled_date=today - timedelta(days=100),
            status="completed",
            exercise_id=exercise_id,
            weight=10,
        )
        _add_workout(
            db,
            program,
            scheduled_date=today - timedelta(days=1),
            status="completed",
            exercise_id=exercise_id,
        )
        _add_workout(db, program, scheduled_date=today - timedelta(days=2), status="skipped")
        _add_workout(db, program, scheduled_date=today, status="planned")
        db.add_all(
            [
                BodyMeasurement(
                    user_id=user_id,
                    measured_on=today - timedelta(days=6),
                    weight_kg=80,
                    waist_cm=90,
                ),
                BodyMeasurement(
                    user_id=user_id,
                    measured_on=today - timedelta(days=1),
                    weight_kg=79,
                    waist_cm=89,
                ),
                BodyMeasurement(
                    user_id=other_user_id,
                    measured_on=today - timedelta(days=1),
                    weight_kg=250,
                ),
                _nutrition_target(other_user_id),
                _diary_entry(user_id, today - timedelta(days=60), weight_g="20"),
                _complete_day(user_id, today - timedelta(days=60)),
                _diary_entry(user_id, today - timedelta(days=1)),
                _complete_day(user_id, today - timedelta(days=1)),
                _diary_entry(user_id, today, weight_g="20"),
                _diary_entry(other_user_id, today - timedelta(days=1), weight_g="25"),
                _complete_day(other_user_id, today - timedelta(days=1)),
            ]
        )

    response = client.get("/api/v1/workouts/progress/summary?period_days=7", headers=headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["period_days"] == 7
    assert payload["training"] == {
        "planned_workouts": 2,
        "completed_workouts": 1,
        "skipped_workouts": 1,
        "frequency_per_week": 1.0,
        "volume_kg": 160.0,
        "new_personal_records": 1,
        "last_completed_workout_on": (today - timedelta(days=1)).isoformat(),
        "next_workout": {
            "id": payload["training"]["next_workout"]["id"],
            "scheduled_date": today.isoformat(),
            "scheduled_time": None,
            "title": "Силовая",
            "status": "planned",
        },
    }
    assert payload["nutrition"] == {
        "visible": True,
        "logged_days": 1,
        "complete_days": 1,
        "incomplete_days": 0,
        "fasted_days": 0,
        "unlogged_days": 5,
        "adherence_evaluated_days": 1,
        "average_calories": 2000.0,
        "target_calories": 2000,
        "average_protein_g": 150.0,
        "target_protein_g": 150,
        "target_effective_on": (today - timedelta(days=30)).isoformat(),
    }
    assert payload["adherence"]["workouts"]["percent"] == 50.0
    assert payload["adherence"]["cardio"] == {
        "status": "available",
        "percent": 0.0,
        "achieved": 0,
        "evaluated": 1,
        "weight": 0.2,
        "reason": None,
    }
    assert payload["adherence"]["calories"]["percent"] == 100.0
    assert payload["adherence"]["protein"]["percent"] == 100.0
    assert payload["adherence"]["overall_percent"] == 60.0
    assert payload["body"]["latest_measurement"]["weight_kg"] == 79.0
    weight_trend = next(
        trend for trend in payload["body"]["trends"] if trend["metric"] == "weight_kg"
    )
    assert weight_trend["change"] == -1.0
    sufficiency = payload["data_sufficiency"]
    assert sufficiency["nutrition_coverage"]["status"] == "limited"
    assert sufficiency["nutrition_coverage"]["counters"]["eligible_day_count"] == 6
    assert sufficiency["weight_trend"]["status"] == "limited"
    assert sufficiency["anthropometry"]["status"] == "limited"
    assert sufficiency["workout_logging"]["status"] == "sufficient"
    assert sufficiency["working_sets"]["status"] == "limited"
    assert sufficiency["rir_coverage"]["status"] == "insufficient"
    assert sufficiency["schedule_adherence"]["status"] == "limited"
    assert payload["user_id"] == user_id

    longer_period = client.get(
        "/api/v1/workouts/progress/summary?period_days=90", headers=headers
    ).json()
    assert longer_period["nutrition"]["logged_days"] == 2
    assert longer_period["nutrition"]["adherence_evaluated_days"] == 1

    invalid = client.get("/api/v1/workouts/progress/summary?period_days=14", headers=headers)
    assert invalid.status_code == 422
    other = client.get("/api/v1/workouts/progress/summary?period_days=7", headers=other_headers)
    assert other.status_code == 200
    assert other.json()["body"]["latest_measurement"]["weight_kg"] == 250.0


def test_progress_counts_fasted_as_logged_and_excludes_incomplete_days(client) -> None:
    headers = _auth(client, 21_003)
    user_id = _user_id(21_003)
    today = today_msk()

    with get_session_context() as db:
        db.add(_nutrition_target(user_id, cardio_per_week=0))
        db.add_all(
            [
                FoodDiaryDayStatus(
                    user_id=user_id,
                    diary_date=today - timedelta(days=1),
                    status="fasted",
                ),
                FoodDiaryDayStatus(
                    user_id=user_id,
                    diary_date=today - timedelta(days=2),
                    status="incomplete",
                ),
            ]
        )

    response = client.get("/api/v1/workouts/progress/summary?period_days=7", headers=headers)

    assert response.status_code == 200, response.text
    nutrition = response.json()["nutrition"]
    assert nutrition == {
        "visible": True,
        "logged_days": 1,
        "complete_days": 0,
        "incomplete_days": 1,
        "fasted_days": 1,
        "unlogged_days": 4,
        "adherence_evaluated_days": 1,
        "average_calories": 0.0,
        "target_calories": 2000,
        "average_protein_g": 0.0,
        "target_protein_g": 150,
        "target_effective_on": (today - timedelta(days=30)).isoformat(),
    }
    coverage = response.json()["data_sufficiency"]["nutrition_coverage"]
    assert coverage["counters"]["logged_day_count"] == 1
    assert coverage["counters"]["eligible_day_count"] == 6


def test_progress_uses_calories_only_quick_add_without_inventing_protein(client) -> None:
    headers = _auth(client, 21_050)
    user_id = _user_id(21_050)
    diary_date = today_msk() - timedelta(days=1)

    with get_session_context() as db:
        db.add(_nutrition_target(user_id, cardio_per_week=0))
        db.add(
            FoodDiaryEntry(
                user_id=user_id,
                diary_date=diary_date,
                meal_type="dinner",
                entry_kind="quick_add",
                amount=Decimal("1"),
                amount_unit="serving",
                weight_g=Decimal("1"),
                food_name="Быстрый ввод",
                energy_kcal_per_100g=Decimal("0"),
                protein_g_per_100g=Decimal("0"),
                fat_g_per_100g=Decimal("0"),
                carbs_g_per_100g=Decimal("0"),
                serving_amount=Decimal("1"),
                serving_unit="serving",
                serving_weight_g=Decimal("1"),
                quick_energy_kcal=Decimal("2000"),
            )
        )
        db.add(_complete_day(user_id, diary_date))

    response = client.get("/api/v1/workouts/progress/summary?period_days=7", headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["nutrition"]["average_calories"] == 2000.0
    assert payload["nutrition"]["average_protein_g"] is None
    assert payload["adherence"]["calories"]["evaluated"] == 1
    assert payload["adherence"]["calories"]["percent"] == 100.0
    assert payload["adherence"]["protein"]["evaluated"] == 0
    assert payload["adherence"]["protein"]["status"] == "insufficient_data"


def test_trainer_summary_requires_current_relationship_and_revokes_access(client) -> None:
    coach_headers = _auth(client, 21_101, is_coach=True)
    client_headers = _auth(client, 21_102)
    other_coach_headers = _auth(client, 21_103, is_coach=True)
    coach_id = _user_id(21_101)
    managed_client_id = _user_id(21_102)

    with get_session_context() as db:
        db.add(
            CoachClient(
                coach_user_id=coach_id,
                client_user_id=managed_client_id,
                private_name="Клиент для сводки",
                status="active",
            )
        )

    detail = client.get(
        f"/api/v1/coach/clients/{managed_client_id}/summary?period_days=30",
        headers=coach_headers,
    )
    assert detail.status_code == 200
    assert detail.json()["user_id"] == managed_client_id
    assert detail.json()["data_sufficiency"]["ruleset_version"] == "data-sufficiency-v1"
    assert "food_name" not in detail.text
    assert "meals" not in detail.text

    denied = client.get(
        f"/api/v1/coach/clients/{managed_client_id}/summary?period_days=30",
        headers=other_coach_headers,
    )
    assert denied.status_code == 404

    own = client.get("/api/v1/workouts/progress/summary", headers=client_headers)
    assert own.status_code == 200

    bulk_active = client.get(
        "/api/v1/coach/client-summaries?period_days=30&limit=1&offset=0",
        headers=coach_headers,
    )
    assert bulk_active.status_code == 200
    assert bulk_active.json()["total"] == 1
    assert bulk_active.json()["limit"] == 1
    assert bulk_active.json()["offset"] == 0
    assert bulk_active.json()["items"][0]["user_id"] == managed_client_id
    assert "food_name" not in bulk_active.text
    invalid_page = client.get(
        "/api/v1/coach/client-summaries?limit=101",
        headers=coach_headers,
    )
    assert invalid_page.status_code == 422

    with get_session_context() as db:
        relation = (
            db.query(CoachClient)
            .filter(
                CoachClient.coach_user_id == coach_id,
                CoachClient.client_user_id == managed_client_id,
            )
            .one()
        )
        relation.status = "ended"

    revoked = client.get(
        f"/api/v1/coach/clients/{managed_client_id}/summary",
        headers=coach_headers,
    )
    assert revoked.status_code == 404
    bulk = client.get("/api/v1/coach/client-summaries", headers=coach_headers)
    assert bulk.status_code == 200
    assert bulk.json() == {"items": [], "total": 0, "limit": 20, "offset": 0}


def test_bulk_trainer_summaries_use_constant_query_count() -> None:
    today = today_msk()
    with get_session_context() as db:
        coach = User(telegram_user_id=21_200, username="summary_coach", is_coach=True)
        db.add(coach)
        db.flush()
        db.add(UserProfile(user_id=coach.id, full_name="Summary Coach"))
        for index in range(25):
            user = User(telegram_user_id=21_201 + index, username=f"summary_client_{index}")
            db.add(user)
            db.flush()
            db.add(UserProfile(user_id=user.id, full_name=f"Summary Client {index}"))
            db.add(
                CoachClient(
                    coach_user_id=coach.id,
                    client_user_id=user.id,
                    private_name=f"Private {index}",
                )
            )
            db.add(
                BodyMeasurement(
                    user_id=user.id,
                    measured_on=today - timedelta(days=1),
                    weight_kg=70 + index,
                )
            )
            if index == 0:
                db.add(_nutrition_target(user.id))
                db.add(_diary_entry(user.id, today - timedelta(days=1)))
                db.add(_complete_day(user.id, today - timedelta(days=1)))
        db.commit()
        db.refresh(coach)

        token = begin_sql_metrics()
        try:
            page = build_trainer_client_summaries(
                db,
                coach,
                90,
                limit=10,
                offset=5,
            )
            metrics = current_sql_metrics()
        finally:
            reset_sql_metrics(token)

    summaries = page["items"]
    assert page["total"] == 25
    assert page["limit"] == 10
    assert page["offset"] == 5
    assert len(summaries) == 10
    summaries_by_name = {summary["client_name"]: summary for summary in summaries}
    assert summaries_by_name["Private 19"]["body"]["latest_measurement"]["weight_kg"] == 89
    assert summaries_by_name["Private 10"]["body"]["latest_measurement"]["weight_kg"] == 80
    assert all(summary["nutrition"]["target_calories"] is None for summary in summaries)
    assert metrics.query_count == 14


def test_nutrition_target_effective_date_keeps_client_local_wall_date(client) -> None:
    headers = _auth(client, 21_300)
    user_id = _user_id(21_300)

    with get_session_context() as db:
        user = db.get(User, user_id)
        assert user is not None and user.profile is not None
        user.profile.timezone = "Pacific/Kiritimati"
        local_today = today_for_user(user)
        saved_local_date = local_today - timedelta(days=3)
        target = _nutrition_target(user_id, cardio_per_week=0)
        target.saved_at = datetime.combine(saved_local_date, time(hour=20))
        db.add(target)
        db.add_all(
            [
                _diary_entry(user_id, saved_local_date),
                _complete_day(user_id, saved_local_date),
                _diary_entry(user_id, saved_local_date + timedelta(days=1)),
                _complete_day(user_id, saved_local_date + timedelta(days=1)),
            ]
        )

    response = client.get(
        "/api/v1/workouts/progress/summary?period_days=7",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["nutrition"]["logged_days"] == 2
    assert payload["nutrition"]["target_effective_on"] == saved_local_date.isoformat()
    assert payload["nutrition"]["adherence_evaluated_days"] == 2
