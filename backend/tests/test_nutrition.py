import math

import pytest
from pydantic import ValidationError

from fitminiapp_api.schemas.nutrition import NutritionTargetSave
from fitminiapp_api.services.nutrition import calculate_nutrition


def nutrition_payload(**overrides) -> NutritionTargetSave:
    values = {
        "sex": "male",
        "weight_kg": 78,
        "height_cm": 165,
        "age": 34,
        "daily_routine": "mixed",
        "steps_range": "from_4000_to_7000",
        "strength_trainings_per_week": 4,
        "strength_training_duration_minutes": 60,
        "strength_training_type": "regular",
        "strength_rest": "two_to_three",
        "cardio_trainings": [
            {
                "kind": "running",
                "trainings_per_week": 3,
                "duration_minutes": 30,
                "intensity": "moderate",
            }
        ],
        "goal": "recomposition",
    }
    values.update(overrides)
    return NutritionTargetSave(**values)


def test_calculates_new_activity_inputs_and_net_training_calories() -> None:
    result = calculate_nutrition(nutrition_payload())

    assert result == {
        "bmr": 1646,
        "base_tdee": 2140,
        "strength_daily_calories": 187,
        "cardio_daily_calories": 123,
        "tdee": 2450,
        "goal_multiplier": 0.95,
        "calories": 2330,
        "protein_g": 156,
        "fat_g": 62,
        "carbs_g": 287,
        "macro_warning": False,
    }


def test_mifflin_st_jeor_uses_female_constant() -> None:
    result = calculate_nutrition(
        nutrition_payload(
            sex="female",
            weight_kg=64,
            height_cm=168,
            age=28,
            daily_routine="mostly_sitting",
            steps_range="up_to_4000",
            strength_trainings_per_week=0,
            cardio_trainings=[],
            goal="maintenance",
        )
    )

    assert result["bmr"] == 1389


@pytest.mark.parametrize(
    ("routine", "steps", "coefficient"),
    [
        ("mostly_sitting", "up_to_4000", 1.2),
        ("mostly_sitting", "over_14000", 1.4),
        ("mixed", "from_7000_to_10000", 1.35),
        ("mostly_on_feet", "unknown", 1.4),
        ("physical_work", "from_10000_to_14000", 1.55),
    ],
)
def test_routine_and_steps_select_one_activity_coefficient(
    routine: str,
    steps: str,
    coefficient: float,
) -> None:
    result = calculate_nutrition(
        nutrition_payload(
            daily_routine=routine,
            steps_range=steps,
            strength_trainings_per_week=0,
            cardio_trainings=[],
            goal="maintenance",
        )
    )

    assert result["base_tdee"] == math.floor((1646.25 * coefficient) + 0.5)
    assert result["strength_daily_calories"] == 0
    assert result["cardio_daily_calories"] == 0


@pytest.mark.parametrize(
    ("goal", "multiplier", "protein_per_kg", "fat_per_kg"),
    [
        ("fat_loss", 0.85, 2.2, 0.8),
        ("recomposition", 0.95, 2.0, 0.8),
        ("maintenance", 1.0, 1.8, 0.9),
        ("muscle_gain", 1.05, 1.8, 0.9),
    ],
)
def test_goal_adjustments_and_weight_based_macros(
    goal: str,
    multiplier: float,
    protein_per_kg: float,
    fat_per_kg: float,
) -> None:
    result = calculate_nutrition(nutrition_payload(goal=goal))

    assert result["goal_multiplier"] == multiplier
    assert result["calories"] % 10 == 0
    assert result["protein_g"] == math.floor(78 * protein_per_kg + 0.5)
    assert result["fat_g"] == math.floor(78 * fat_per_kg + 0.5)
    macro_calories = result["protein_g"] * 4 + result["fat_g"] * 9 + result["carbs_g"] * 4
    assert abs(macro_calories - result["calories"]) <= 10


def test_strength_type_rest_and_duration_determine_net_calories() -> None:
    regular = calculate_nutrition(nutrition_payload(cardio_trainings=[]))
    dense = calculate_nutrition(
        nutrition_payload(
            cardio_trainings=[],
            strength_training_type="dense",
            strength_rest="under_60",
            strength_training_duration_minutes=75,
        )
    )

    expected_regular = round((5 - 1) * 3.5 * 78 / 200 * 60 * 4 / 7)
    expected_dense = round((6.5 - 1) * 3.5 * 78 / 200 * 75 * 4 / 7)
    assert regular["strength_daily_calories"] == expected_regular
    assert dense["strength_daily_calories"] == expected_dense


def test_each_cardio_training_is_calculated_and_summed_as_net_energy() -> None:
    result = calculate_nutrition(
        nutrition_payload(
            strength_trainings_per_week=0,
            cardio_trainings=[
                {
                    "kind": "walking",
                    "trainings_per_week": 2,
                    "duration_minutes": 45,
                    "intensity": "light",
                },
                {
                    "kind": "swimming",
                    "trainings_per_week": 1,
                    "duration_minutes": 60,
                    "intensity": "hard",
                },
            ],
        )
    )

    walking = max(0, (3.5 * 0.85 - 1) * 3.5 * 78 / 200 * 45) * 2
    swimming = max(0, (6 * 1.2 - 1) * 3.5 * 78 / 200 * 60)
    assert result["cardio_daily_calories"] == round((walking + swimming) / 7)


def test_legacy_payload_is_still_accepted_during_frontend_rollout() -> None:
    payload = NutritionTargetSave(
        sex="male",
        weight_kg=80,
        height_cm=180,
        age=30,
        strength_trainings_per_week=3,
        cardio_trainings_per_week=1,
        goal="muscle_gain",
    )

    result = calculate_nutrition(payload)

    assert result["base_tdee"] == 2136
    assert result["strength_daily_calories"] > 0
    assert result["cardio_daily_calories"] > 0


def test_detailed_payload_requires_strength_type_and_cardio_list() -> None:
    with pytest.raises(ValidationError, match="strength_training_type"):
        nutrition_payload(strength_training_type=None)

    values = nutrition_payload().model_dump(exclude={"cardio_trainings"})
    values.pop("daily_activity_level")
    values.pop("cardio_trainings_per_week")
    values.pop("cardio_training_duration_minutes")
    values.pop("cardio_intensity")
    with pytest.raises(ValidationError, match="cardio_trainings"):
        NutritionTargetSave(**values)


def test_negative_carbohydrate_result_is_clamped_and_warned() -> None:
    result = calculate_nutrition(
        nutrition_payload(
            weight_kg=350,
            height_cm=100,
            age=100,
            daily_routine="mostly_sitting",
            steps_range="up_to_4000",
            strength_trainings_per_week=0,
            cardio_trainings=[],
            goal="fat_loss",
        )
    )

    assert result["carbs_g"] == 0
    assert result["macro_warning"] is True
    assert result["calories"] == result["protein_g"] * 4 + result["fat_g"] * 9


@pytest.mark.parametrize(
    "overrides",
    [
        {"weight_kg": float("nan")},
        {"height_cm": float("inf")},
        {"age": 0},
        {"strength_trainings_per_week": -1},
        {"strength_training_duration_minutes": 9},
        {"daily_routine": "mixed", "steps_range": None},
        {
            "cardio_trainings": [
                {
                    "kind": "running",
                    "trainings_per_week": 15,
                    "duration_minutes": 30,
                    "intensity": "moderate",
                }
            ]
        },
    ],
)
def test_invalid_or_unrealistic_values_are_rejected(overrides: dict) -> None:
    with pytest.raises(ValidationError):
        nutrition_payload(**overrides)
