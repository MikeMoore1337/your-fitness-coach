from decimal import Decimal

import pytest
from pydantic import ValidationError

from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.cardio import CardioSession
from fitminiapp_api.models.nutrition import NutritionTarget
from fitminiapp_api.models.user import BodyMeasurement, User
from fitminiapp_api.schemas.cardio import CardioSessionUpdate
from fitminiapp_api.schemas.food import FoodValuesInput
from fitminiapp_api.schemas.nutrition import NutritionManualTargetSave, NutritionTargetSave
from fitminiapp_api.schemas.nutrition_label import NutritionLabelFactsEdit
from fitminiapp_api.schemas.program import PrescriptionLoadTarget, ProgramCoachingRule
from fitminiapp_api.schemas.workout import (
    BodyMeasurementCustomValueSave,
    BodyMeasurementSave,
    WarmupProposalRow,
    WorkoutSetUpdate,
)


def test_fractional_measurement_contract_accepts_two_decimal_values() -> None:
    target = NutritionTargetSave(
        sex="male",
        weight_kg="72.34",
        height_cm="178.25",
        age=34,
        strength_trainings_per_week=0,
        goal="maintenance",
    )
    measurement = BodyMeasurementSave(
        weight_kg="72.34",
        waist_cm="84.25",
        custom_values=[BodyMeasurementCustomValueSave(definition_id=1, value="42.25")],
    )
    workout_set = WorkoutSetUpdate(actual_weight="42.25", distance_km="5.24")
    cardio = CardioSessionUpdate(distance_km="72.34")
    warmup = WarmupProposalRow(weight_kg="42.25", reps=8)

    assert target.weight_kg == Decimal("72.34")
    assert target.height_cm == Decimal("178.25")
    assert measurement.weight_kg == Decimal("72.34")
    assert measurement.custom_values[0].value == Decimal("42.25")
    assert workout_set.actual_weight == Decimal("42.25")
    assert workout_set.distance_km == Decimal("5.24")
    assert cardio.distance_km == Decimal("72.34")
    assert warmup.weight_kg == Decimal("42.25")
    assert PrescriptionLoadTarget(kind="absolute", value="72.34").value == 72.34
    assert (
        ProgramCoachingRule(
            kind="linear_load", increment_value="2.25", increment_unit="kg"
        ).increment_value
        == 2.25
    )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: NutritionTargetSave(
            sex="male",
            weight_kg="72.345",
            height_cm=178,
            age=34,
            strength_trainings_per_week=0,
            goal="maintenance",
        ),
        lambda: BodyMeasurementSave(weight_kg="72.345"),
        lambda: BodyMeasurementSave(
            custom_values=[BodyMeasurementCustomValueSave(definition_id=1, value="42.345")]
        ),
        lambda: WorkoutSetUpdate(actual_weight="42.345"),
        lambda: WorkoutSetUpdate(distance_km="5.678"),
        lambda: CardioSessionUpdate(distance_km="72.345"),
        lambda: WarmupProposalRow(weight_kg="42.345", reps=8),
        lambda: FoodValuesInput(name="Тест", energy_kcal_per_100g="72.345"),
        lambda: NutritionLabelFactsEdit(source_basis="per_100_g", energy_kcal="72.345"),
        lambda: PrescriptionLoadTarget(kind="absolute", value="72.345"),
        lambda: ProgramCoachingRule(
            kind="linear_load", increment_value="2.345", increment_unit="kg"
        ),
    ],
)
def test_fractional_contract_rejects_values_beyond_storage_scale(factory) -> None:
    with pytest.raises(ValidationError):
        factory()


def test_integer_only_nutrition_targets_reject_fractional_values() -> None:
    with pytest.raises(ValidationError):
        NutritionManualTargetSave(
            calories="2400.5",
            protein_g=150,
            fat_g=70,
            carbs_g=280,
        )


def _auth(client, telegram_user_id: int) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "is_coach": False},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_fractional_profile_target_measurement_and_cardio_round_trip(client) -> None:
    headers = _auth(client, 119_034)
    profile = client.patch(
        "/api/v1/me/profile",
        headers=headers,
        json={"height_cm": 178.25, "weight_kg": 72.34},
    )
    assert profile.status_code == 200, profile.text
    assert profile.json()["profile"]["height_cm"] == 178.25
    assert profile.json()["profile"]["weight_kg"] == 72.34

    target = client.post(
        "/api/v1/nutrition/targets",
        headers=headers,
        json={
            "sex": "male",
            "weight_kg": 72.34,
            "height_cm": 178.25,
            "age": 34,
            "strength_trainings_per_week": 0,
            "goal": "maintenance",
        },
    )
    assert target.status_code == 200, target.text
    assert target.json()["weight_kg"] == 72.34
    assert target.json()["height_cm"] == 178.25
    history = client.get("/api/v1/nutrition/targets/history", headers=headers)
    assert history.status_code == 200
    assert history.json()["items"][0]["height_cm"] == 178.25

    measurement = client.post(
        "/api/v1/workouts/diary",
        headers=headers,
        json={"weight_kg": 72.34, "waist_cm": 84.25},
    )
    assert measurement.status_code == 200, measurement.text
    assert measurement.json()["weight_kg"] == 72.34
    assert client.get("/api/v1/workouts/diary", headers=headers).json()[0]["weight_kg"] == 72.34

    cardio = client.post(
        "/api/v1/workouts/cardio",
        headers=headers,
        json={
            "client_request_id": "00000000-0000-4000-8000-000000119034",
            "activity_type": "running",
            "duration_minutes": 35,
            "distance_km": 72.34,
            "scheduled_at": "2026-01-10T12:00",
            "status": "completed",
        },
    )
    assert cardio.status_code == 201, cardio.text
    assert cardio.json()["distance_km"] == 72.34
    assert client.get("/api/v1/workouts/cardio", headers=headers).json()[0]["distance_km"] == 72.34

    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == 119_034).one()
        assert user.profile is not None
        assert user.profile.height_cm == Decimal("178.25")
        assert user.profile.weight_kg == Decimal("72.34")
        assert db.query(NutritionTarget).filter_by(user_id=user.id).one().height_cm == Decimal(
            "178.25"
        )
        assert db.query(BodyMeasurement).filter_by(user_id=user.id).one().weight_kg == Decimal(
            "72.34"
        )
        assert db.query(CardioSession).filter_by(user_id=user.id).one().distance_km == Decimal(
            "72.34"
        )

    exported = client.get("/api/v1/me/export", headers=headers)
    assert exported.status_code == 200
    assert exported.json()["profile"]["height_cm"] == 178.25
    assert exported.json()["measurements"][0]["weight_kg"] == 72.34
    assert exported.json()["cardio_sessions"][0]["distance_km"] == 72.34
