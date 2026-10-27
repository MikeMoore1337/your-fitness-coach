from __future__ import annotations

from datetime import date
from decimal import Decimal

from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.food_diary import FoodDiaryDayStatus, FoodDiaryEntry
from fitminiapp_api.models.nutrition import NutritionTarget
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.progress import NutritionReportPeriod
from fitminiapp_api.services.energy_calibration import _load_inputs
from fitminiapp_api.services.nutrition_reports import _aggregated_diary_days
from fitminiapp_api.services.period_bounds import ReportBounds
from fitminiapp_api.services.progress import build_progress_summary_for_range
from fitminiapp_api.services.weekly_check_ins import _suspicious_low_nutrition_days


def _auth(client, telegram_user_id: int) -> None:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "is_coach": False},
    )
    assert response.status_code == 200


def _basis_aware_entry(user_id: int, diary_date: date) -> FoodDiaryEntry:
    return FoodDiaryEntry(
        user_id=user_id,
        diary_date=diary_date,
        meal_type="dinner",
        entry_kind="food",
        amount=Decimal("250"),
        amount_unit="ml",
        weight_g=None,
        food_name="Отсканированный продукт",
        food_brand="Тестовый бренд",
        energy_kcal_per_100g=None,
        protein_g_per_100g=None,
        fat_g_per_100g=None,
        carbs_g_per_100g=None,
        fiber_g_per_100g=None,
        nutrition_basis_kind="per_100_ml",
        nutrition_basis_amount=Decimal("100"),
        nutrition_basis_unit="ml",
        nutrition_amount={
            "energy_kcal": "250.00",
            "protein_g": "10.000",
            "fat_g": "5.000",
            "carbs_g": "20.000",
            "fiber_g": None,
        },
        serving_amount=Decimal("250"),
        serving_unit="ml",
        serving_weight_g=None,
    )


def test_basis_aware_snapshot_feeds_all_nutrition_readers(client) -> None:
    telegram_user_id = 128_201
    _auth(client, telegram_user_id)
    logged_on = date(2026, 8, 20)
    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == telegram_user_id).one()
        db.add(
            NutritionTarget(
                user_id=user.id,
                assigned_by_user_id=user.id,
                effective_from=date(2026, 8, 1),
                source="manual",
                calories=2000,
                protein_g=140,
                fat_g=70,
                carbs_g=200,
            )
        )
        db.add(_basis_aware_entry(user.id, logged_on))
        db.add(FoodDiaryDayStatus(user_id=user.id, diary_date=logged_on, status="complete"))
        db.commit()

        bounds = ReportBounds(
            period=NutritionReportPeriod.CUSTOM,
            start=logged_on,
            end=logged_on,
        )
        report_day = _aggregated_diary_days(db, user.id, bounds)[logged_on]
        assert report_day.calories == Decimal("250.00")
        assert report_day.protein_g == Decimal("10.000")

        day_totals, _ = _load_inputs(db, user, logged_on, logged_on)
        assert day_totals == {logged_on: 250.0}

        progress = build_progress_summary_for_range(db, user, logged_on, logged_on)
        assert progress["nutrition"]["average_calories"] == 250.0
        assert progress["nutrition"]["average_protein_g"] == 10.0

        assert _suspicious_low_nutrition_days(
            db,
            user,
            period_start=logged_on,
            period_end=logged_on,
        ) == [
            {
                "diary_date": logged_on,
                "calories": 250,
                "target_calories": 2000,
            }
        ]
