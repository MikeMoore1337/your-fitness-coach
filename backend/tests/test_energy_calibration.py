from datetime import date, timedelta
from decimal import Decimal

import pytest

from fitminiapp_api.core.timezone import today_msk
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.food_diary import FoodDiaryDayStatus, FoodDiaryEntry
from fitminiapp_api.models.nutrition import EnergyCalibration, NutritionTarget
from fitminiapp_api.models.user import BodyMeasurement, CoachClient, User
from fitminiapp_api.services.energy_calibration import evaluate_energy_calibration


def _target(*, goal: str = "maintenance", calories: int = 2000) -> NutritionTarget:
    return NutritionTarget(
        user_id=1,
        assigned_by_user_id=1,
        sex="male",
        weight_kg=80,
        height_cm=180,
        age=32,
        daily_activity_level="moderate",
        daily_routine="mixed",
        steps_range="from_7000_to_10000",
        strength_trainings_per_week=3,
        strength_training_duration_minutes=60,
        strength_training_type="regular",
        strength_rest="one_to_two",
        cardio_trainings_per_week=0,
        cardio_training_duration_minutes=30,
        cardio_intensity="moderate",
        cardio_trainings=[],
        goal=goal,
        bmr=1750,
        tdee=calories,
        calories=calories,
        protein_g=144,
        fat_g=72,
        carbs_g=194,
    )


def _days(today: date, calories: float = 2400, count: int = 28) -> dict[date, float]:
    return {today - timedelta(days=offset): calories for offset in range(1, count + 1)}


def _weights(today: date, start: float = 80.0, end: float = 80.0) -> list[tuple[date, float]]:
    period_start = today - timedelta(days=28)
    return [
        (period_start, start),
        (period_start + timedelta(days=3), start + 0.1),
        (period_start + timedelta(days=6), start - 0.1),
        (today - timedelta(days=7), end + 0.1),
        (today - timedelta(days=4), end - 0.1),
        (today - timedelta(days=1), end),
    ]


def test_sparse_data_does_not_produce_confident_calibration() -> None:
    today = date(2026, 8, 19)

    result = evaluate_energy_calibration(
        target=_target(),
        day_totals=_days(today, count=5),
        weights=_weights(today)[:2],
        today=today,
    )

    assert result.status == "insufficient"
    assert result.estimated_expenditure_kcal is None
    assert result.proposed_target_calories is None
    assert "too_few_logged_days" in result.reason_keys


def test_noisy_data_returns_range_but_never_a_target_proposal() -> None:
    today = date(2026, 8, 19)
    day_totals = {
        logged_on: 900 if index % 2 else 3500 for index, logged_on in enumerate(_days(today))
    }
    weights = _weights(today)
    weights[1] = (weights[1][0], 84.0)

    result = evaluate_energy_calibration(
        target=_target(calories=1500),
        day_totals=day_totals,
        weights=weights,
        today=today,
    )

    assert result.status == "limited"
    assert result.estimated_expenditure_kcal is not None
    assert result.estimate_low_kcal < result.estimated_expenditure_kcal
    assert result.estimated_expenditure_kcal < result.estimate_high_kcal
    assert result.proposed_target_calories is None
    assert "intake_is_highly_variable" in result.reason_keys
    assert "weight_is_highly_variable" in result.reason_keys


def test_formula_uses_smoothed_weight_change_and_not_single_day_weight() -> None:
    today = date(2026, 8, 19)

    result = evaluate_energy_calibration(
        target=_target(calories=2200),
        day_totals=_days(today, calories=2000),
        weights=_weights(today, start=80.0, end=79.3),
        today=today,
    )

    assert result.smoothed_start_weight_kg == 80.0
    assert result.smoothed_end_weight_kg == 79.3
    assert result.estimated_expenditure_kcal == 2260


def test_out_of_range_estimate_is_limited_and_cannot_change_target() -> None:
    today = date(2026, 8, 19)

    result = evaluate_energy_calibration(
        target=_target(calories=2000),
        day_totals=_days(today, calories=900),
        weights=_weights(today, start=80.0, end=85.0),
        today=today,
    )

    assert result.status == "limited"
    assert result.estimated_expenditure_kcal == 800
    assert result.proposed_target_calories is None
    assert "estimate_outside_supported_range" in result.reason_keys


@pytest.mark.parametrize(
    ("goal", "current_target"),
    [
        ("maintenance", 2400),
        ("recomposition", 2400),
        ("fat_loss", 2050),
        ("muscle_gain", 2500),
    ],
)
def test_full_data_keeps_goal_target_when_it_is_inside_range(
    goal: str,
    current_target: int,
) -> None:
    today = date(2026, 8, 19)

    result = evaluate_energy_calibration(
        target=_target(goal=goal, calories=current_target),
        day_totals=_days(today, calories=2400),
        weights=_weights(today),
        today=today,
    )

    assert result.sufficiency_status == "sufficient"
    assert result.status == "no_change"
    assert result.proposed_target_calories is None


@pytest.mark.parametrize("goal", ["maintenance", "recomposition", "fat_loss", "muscle_gain"])
def test_full_data_proposes_only_a_gradual_change_for_each_goal(goal: str) -> None:
    today = date(2026, 8, 19)

    result = evaluate_energy_calibration(
        target=_target(goal=goal, calories=1500),
        day_totals=_days(today, calories=2600),
        weights=_weights(today),
        today=today,
    )

    assert result.status == "pending"
    assert result.proposed_target_calories == 1700


def _auth(client, telegram_user_id: int, *, is_coach: bool = False) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "is_coach": is_coach},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _seed_full_history(telegram_user_id: int, *, calories: int = 2600) -> int:
    today = today_msk()
    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == telegram_user_id).one()
        target = _target(calories=1500)
        target.user_id = user.id
        target.assigned_by_user_id = user.id
        db.add(target)
        for logged_on in _days(today):
            db.add(
                FoodDiaryEntry(
                    user_id=user.id,
                    diary_date=logged_on,
                    meal_type="lunch",
                    amount=Decimal("400"),
                    amount_unit="g",
                    weight_g=Decimal("400"),
                    food_name="Тестовый день",
                    energy_kcal_per_100g=Decimal(calories) / Decimal("4"),
                    protein_g_per_100g=Decimal("0"),
                    fat_g_per_100g=Decimal("0"),
                    carbs_g_per_100g=Decimal("0"),
                )
            )
            db.add(
                FoodDiaryDayStatus(
                    user_id=user.id,
                    diary_date=logged_on,
                    status="complete",
                )
            )
        for measured_on, weight in _weights(today):
            db.add(
                BodyMeasurement(
                    user_id=user.id,
                    measured_on=measured_on,
                    weight_kg=weight,
                )
            )
        db.commit()
        return user.id


def test_preview_and_explicit_accept_update_target_and_history(client) -> None:
    telegram_user_id = 933001
    headers = _auth(client, telegram_user_id)
    user_id = _seed_full_history(telegram_user_id)

    preview = client.post("/api/v1/nutrition/energy-calibration/preview", headers=headers)

    assert preview.status_code == 200
    proposal = preview.json()
    assert proposal["status"] == "pending"
    assert proposal["current_target_calories"] == 1500
    assert proposal["proposed_target_calories"] == 1700
    assert proposal["current_target_protein_g"] == 144
    assert proposal["proposed_target_protein_g"] == 144
    assert proposal["proposed_effective_from"] is not None
    assert proposal["sufficiency"]["counters"]["exact_entry_count"] == 28
    assert proposal["sufficiency"]["counters"]["approximate_entry_count"] == 0
    assert proposal["sufficiency"]["counters"]["partial_entry_count"] == 0

    accepted = client.post(
        f"/api/v1/nutrition/energy-calibration/{proposal['id']}/decision",
        json={"decision": "accept"},
        headers=headers,
    )

    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"
    replayed = client.post(
        f"/api/v1/nutrition/energy-calibration/{proposal['id']}/decision",
        json={"decision": "accept"},
        headers=headers,
    )
    assert replayed.status_code == 200
    assert replayed.json()["status"] == "accepted"
    review = client.post(
        "/api/v1/check-ins/weekly",
        json={
            "status": "completed",
            "recovery": 4,
            "energy_calibration_id": proposal["id"],
        },
        headers=headers,
    )
    assert review.status_code == 201, review.text
    adaptive = review.json()["summary"]["adaptive_energy"]
    assert adaptive["decision"] == "accepted"
    assert adaptive["calibration"]["status"] == "accepted"
    assert adaptive["calibration"]["current_target_calories"] == 1500
    assert adaptive["calibration"]["proposed_target_calories"] == 1700

    coach_headers = _auth(client, 933_011, is_coach=True)
    with get_session_context() as db:
        coach_id = db.query(User.id).filter(User.telegram_user_id == 933_011).scalar()
        db.add(CoachClient(coach_user_id=coach_id, client_user_id=user_id, status="active"))
    trainer_history = client.get(
        f"/api/v1/coach/clients/{user_id}/weekly-check-ins",
        headers=coach_headers,
    )
    assert trainer_history.status_code == 200
    assert trainer_history.json()["items"][0]["summary"]["adaptive_energy"] == adaptive
    history = client.get("/api/v1/nutrition/energy-calibration/history", headers=headers)
    assert history.status_code == 200
    assert history.json()["items"][0]["status"] == "accepted"
    exported = client.get("/api/v1/me/export", headers=headers)
    assert exported.status_code == 200
    assert exported.json()["energy_calibrations"][0]["status"] == "accepted"
    with get_session_context() as db:
        target = (
            db.query(NutritionTarget)
            .filter(
                NutritionTarget.user_id == user_id,
                NutritionTarget.effective_to.is_(None),
            )
            .one()
        )
        record = db.query(EnergyCalibration).filter(EnergyCalibration.user_id == user_id).one()
        assert target.calories == 1700
        assert target.source == "adaptive"
        assert target.tdee == proposal["estimated_expenditure_kcal"]
        assert abs(target.protein_g * 4 + target.fat_g * 9 + target.carbs_g * 4 - 1700) <= 2
        target_history = (
            db.query(NutritionTarget)
            .filter(NutritionTarget.user_id == user_id)
            .order_by(NutritionTarget.effective_from.asc(), NutritionTarget.id.asc())
            .all()
        )
        assert len(target_history) == 2
        assert target_history[0].effective_to == target.effective_from
        assert target_history[0].superseded_by_id == target.id
        assert sum(row.effective_to is None for row in target_history) == 1
        assert record.status == "accepted"


def test_explicit_reject_preserves_current_target(client) -> None:
    telegram_user_id = 933002
    headers = _auth(client, telegram_user_id)
    user_id = _seed_full_history(telegram_user_id)
    preview = client.post(
        "/api/v1/nutrition/energy-calibration/preview",
        headers=headers,
    ).json()

    rejected = client.post(
        f"/api/v1/nutrition/energy-calibration/{preview['id']}/decision",
        json={"decision": "reject"},
        headers=headers,
    )

    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    replayed = client.post(
        f"/api/v1/nutrition/energy-calibration/{preview['id']}/decision",
        json={"decision": "reject"},
        headers=headers,
    )
    assert replayed.status_code == 200
    assert replayed.json()["status"] == "rejected"
    changed_decision = client.post(
        f"/api/v1/nutrition/energy-calibration/{preview['id']}/decision",
        json={"decision": "accept"},
        headers=headers,
    )
    assert changed_decision.status_code == 409
    with get_session_context() as db:
        target = db.query(NutritionTarget).filter(NutritionTarget.user_id == user_id).one()
        assert target.calories == 1500

    deleted = client.request(
        "DELETE",
        "/api/v1/me/account",
        json={"confirmation": "DELETE"},
        headers=headers,
    )
    assert deleted.status_code == 204
    with get_session_context() as db:
        assert (
            db.query(EnergyCalibration).filter(EnergyCalibration.user_id == user_id).first() is None
        )


def test_decision_is_owner_only_and_rejects_stale_preview(client) -> None:
    telegram_user_id = 933003
    headers = _auth(client, telegram_user_id)
    user_id = _seed_full_history(telegram_user_id)
    preview = client.post(
        "/api/v1/nutrition/energy-calibration/preview",
        headers=headers,
    ).json()
    stranger_headers = _auth(client, 933004)

    stranger = client.post(
        f"/api/v1/nutrition/energy-calibration/{preview['id']}/decision",
        json={"decision": "accept"},
        headers=stranger_headers,
    )

    assert stranger.status_code == 404
    with get_session_context() as db:
        target = db.query(NutritionTarget).filter(NutritionTarget.user_id == user_id).one()
        target.saved_at = target.saved_at + timedelta(seconds=1)
        db.commit()

    stale = client.post(
        f"/api/v1/nutrition/energy-calibration/{preview['id']}/decision",
        json={"decision": "accept"},
        headers=headers,
    )

    assert stale.status_code == 409
    with get_session_context() as db:
        record = db.query(EnergyCalibration).filter(EnergyCalibration.id == preview["id"]).one()
        target = db.query(NutritionTarget).filter(NutritionTarget.user_id == user_id).one()
        assert record.status == "superseded"
        assert target.calories == 1500
