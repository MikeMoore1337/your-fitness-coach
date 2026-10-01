from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal

from fitminiapp_api.core.timezone import today_msk
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.food_diary import FoodDiaryDayStatus, FoodDiaryEntry
from fitminiapp_api.models.nutrition import NutritionTarget
from fitminiapp_api.models.user import CoachClient, User
from fitminiapp_api.schemas.progress import NutritionReportPeriod
from fitminiapp_api.services.nutrition_reports import (
    _safe_csv_value,
    resolve_report_bounds,
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


def _target(
    user_id: int,
    *,
    effective_from,
    effective_to=None,
    calories: int = 2000,
    protein_g: int = 150,
    fat_g: int = 60,
    carbs_g: int = 200,
    source: str = "manual",
) -> NutritionTarget:
    return NutritionTarget(
        user_id=user_id,
        source=source,
        effective_from=effective_from,
        effective_to=effective_to,
        calories=calories,
        protein_g=protein_g,
        fat_g=fat_g,
        carbs_g=carbs_g,
        saved_at=datetime.combine(effective_from, time()),
    )


def _entry(user_id: int, diary_date, *, quick: bool = False) -> FoodDiaryEntry:
    common = {
        "user_id": user_id,
        "diary_date": diary_date,
        "meal_type": "dinner",
        "amount": Decimal("1") if quick else Decimal("200"),
        "amount_unit": "serving" if quick else "g",
        "weight_g": Decimal("1") if quick else Decimal("200"),
        "food_name": "Значение не должно попасть в отчёт",
        "energy_kcal_per_100g": Decimal("0") if quick else Decimal("1000"),
        "protein_g_per_100g": Decimal("0") if quick else Decimal("75"),
        "fat_g_per_100g": Decimal("0") if quick else Decimal("10"),
        "carbs_g_per_100g": Decimal("0") if quick else Decimal("10"),
    }
    if quick:
        common.update(
            {
                "entry_kind": "quick_add",
                "quick_energy_kcal": Decimal("500"),
                "serving_amount": Decimal("1"),
                "serving_unit": "serving",
                "serving_weight_g": Decimal("1"),
            }
        )
    return FoodDiaryEntry(**common)


def test_report_keeps_missing_and_current_days_explicit(client) -> None:
    headers = _auth(client, 57_001)
    response = client.get(
        "/api/v1/workouts/progress/nutrition-report?period=days_7",
        headers=headers,
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["summary"]["eligible_days"] == 7
    assert payload["summary"]["logged_days"] == 0
    assert payload["summary"]["coverage_percent"] == 0
    assert payload["summary"]["missing_days"] == 7
    assert payload["summary"]["current_day_status"] == "missing"
    assert len(payload["daily"]) == 7
    assert payload["daily"][-1]["is_current_day"] is True
    assert payload["daily"][-1]["calories"] is None


def test_report_aggregates_only_confirmed_days_against_effective_targets(client) -> None:
    headers = _auth(client, 57_002)
    user_id = _user_id(57_002)
    today = today_msk()
    old_day = today - timedelta(days=5)
    target_change_day = today - timedelta(days=3)
    fasted_day = today - timedelta(days=2)
    with get_session_context() as db:
        db.add_all(
            [
                _target(
                    user_id,
                    effective_from=today - timedelta(days=40),
                    effective_to=target_change_day,
                ),
                _target(
                    user_id,
                    effective_from=target_change_day,
                    calories=1800,
                    protein_g=140,
                    fat_g=55,
                    carbs_g=180,
                    source="adaptive",
                ),
                _entry(user_id, old_day),
                _entry(user_id, today, quick=True),
                FoodDiaryDayStatus(user_id=user_id, diary_date=old_day, status="complete"),
                FoodDiaryDayStatus(user_id=user_id, diary_date=fasted_day, status="fasted"),
                FoodDiaryDayStatus(user_id=user_id, diary_date=today, status="incomplete"),
            ]
        )

    response = client.get(
        "/api/v1/workouts/progress/nutrition-report",
        params={
            "period": "custom",
            "date_from": (today - timedelta(days=6)).isoformat(),
            "date_to": today.isoformat(),
        },
        headers=headers,
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    summary = payload["summary"]
    assert summary["logged_days"] == 2
    assert summary["eligible_days"] == 7
    assert summary["coverage_percent"] == 28.6
    assert summary["complete_days"] == 1
    assert summary["fasted_days"] == 1
    assert summary["incomplete_days"] == 1
    assert summary["missing_days"] == 4
    assert summary["current_day_status"] == "incomplete"
    assert summary["exact_entry_count"] == 1
    assert summary["approximate_entry_count"] == 0
    assert summary["partial_entry_count"] == 1
    assert summary["calories"] == {
        "average": 1000.0,
        "minimum": 0.0,
        "maximum": 2000.0,
        "sample_days": 2,
    }
    assert summary["protein_g"]["average"] == 75.0
    assert summary["fat_g"]["average"] == 10.0
    assert summary["carbs_g"]["average"] == 10.0
    assert summary["days_within_calorie_tolerance"] == 1
    assert summary["calorie_tolerance_evaluated_days"] == 2
    assert summary["days_meeting_protein_target"] == 1
    assert summary["protein_target_evaluated_days"] == 2
    assert summary["fat_comparison"] == {
        "average_actual": 10.0,
        "average_target": 57.5,
        "average_deviation": -47.5,
        "evaluated_days": 2,
    }
    assert payload["target_changes"] == [
        {
            "effective_from": target_change_day.isoformat(),
            "source": "adaptive",
            "calories": 1800,
            "protein_g": 140,
            "fat_g": 55,
            "carbs_g": 180,
        }
    ]
    current = payload["daily"][-1]
    assert current["status"] == "incomplete"
    assert current["calories"] == 500.0
    assert current["protein_g"] is None
    assert current["calorie_deviation"] is None
    assert current["within_calorie_tolerance"] is None
    marker = next(
        point for point in payload["daily"] if point["diary_date"] == target_change_day.isoformat()
    )
    assert marker["target_changed"] is True
    assert marker["target_calories"] == 1800

    csv_response = client.get(
        "/api/v1/workouts/progress/nutrition-report.csv",
        params={
            "period": "custom",
            "date_from": (today - timedelta(days=6)).isoformat(),
            "date_to": today.isoformat(),
        },
        headers=headers,
    )
    assert csv_response.status_code == 200
    assert csv_response.content.startswith(b"\xef\xbb\xbfrow_type,period_start")
    assert "summary,\\" not in csv_response.text
    assert "daily" in csv_response.text
    assert "food_name" not in csv_response.text
    assert "Значение не должно попасть" not in csv_response.text


def test_report_validates_custom_bounds_and_supports_bounded_long_history(client) -> None:
    headers = _auth(client, 57_003)
    today = today_msk()

    missing = client.get(
        "/api/v1/workouts/progress/nutrition-report?period=custom",
        headers=headers,
    )
    assert missing.status_code == 422
    future = client.get(
        "/api/v1/workouts/progress/nutrition-report",
        params={"period": "custom", "date_from": today, "date_to": today + timedelta(days=1)},
        headers=headers,
    )
    assert future.status_code == 422
    too_long = client.get(
        "/api/v1/workouts/progress/nutrition-report",
        params={
            "period": "custom",
            "date_from": today - timedelta(days=366),
            "date_to": today,
        },
        headers=headers,
    )
    assert too_long.status_code == 422
    bounded = client.get(
        "/api/v1/workouts/progress/nutrition-report",
        params={
            "period": "custom",
            "date_from": today - timedelta(days=365),
            "date_to": today,
        },
        headers=headers,
    )
    assert bounded.status_code == 200
    assert len(bounded.json()["daily"]) == 366

    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == 57_003).one()
        current_week = resolve_report_bounds(user, NutritionReportPeriod.CURRENT_WEEK)
    assert current_week.end == today
    assert current_week.start == today - timedelta(days=today.weekday())


def test_trainer_report_requires_active_relationship_and_isolates_clients(client) -> None:
    coach_headers = _auth(client, 57_101, is_coach=True)
    client_headers = _auth(client, 57_102)
    _auth(client, 57_103)
    coach_id = _user_id(57_101)
    managed_id = _user_id(57_102)
    other_id = _user_id(57_103)
    today = today_msk()
    with get_session_context() as db:
        db.add_all(
            [
                CoachClient(
                    coach_user_id=coach_id,
                    client_user_id=managed_id,
                    status="active",
                ),
                _entry(managed_id, today - timedelta(days=1)),
                FoodDiaryDayStatus(
                    user_id=managed_id,
                    diary_date=today - timedelta(days=1),
                    status="complete",
                ),
                _entry(other_id, today - timedelta(days=1)),
                FoodDiaryDayStatus(
                    user_id=other_id,
                    diary_date=today - timedelta(days=1),
                    status="complete",
                ),
            ]
        )

    allowed = client.get(
        f"/api/v1/coach/clients/{managed_id}/nutrition-report?period=days_7",
        headers=coach_headers,
    )
    assert allowed.status_code == 200
    assert allowed.json()["summary"]["logged_days"] == 1
    denied = client.get(
        f"/api/v1/coach/clients/{other_id}/nutrition-report?period=days_7",
        headers=coach_headers,
    )
    assert denied.status_code == 404
    own = client.get(
        "/api/v1/workouts/progress/nutrition-report?period=days_7",
        headers=client_headers,
    )
    assert own.status_code == 200

    with get_session_context() as db:
        relation = db.query(CoachClient).filter(CoachClient.client_user_id == managed_id).one()
        relation.status = "ended"
    revoked = client.get(
        f"/api/v1/coach/clients/{managed_id}/nutrition-report?period=days_7",
        headers=coach_headers,
    )
    assert revoked.status_code == 404


def test_csv_formula_injection_values_are_forced_to_text() -> None:
    assert _safe_csv_value("=1+1") == "'=1+1"
    assert _safe_csv_value("  @cmd") == "'  @cmd"
    assert _safe_csv_value("safe") == "safe"
