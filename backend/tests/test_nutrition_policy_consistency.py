"""Cross-language policy drift and model invariants; not clinical validation.

These tests check consistency and conservation, *not* prediction accuracy.
See docs/nutrition/scientific-validation-1072-2026-10.md.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from fitminiapp_api.schemas.nutrition import NutritionTargetSave
from fitminiapp_api.services.energy_calibration import GOAL_MULTIPLIERS as ADAPTIVE_GOALS
from fitminiapp_api.services.nutrition import (
    GOAL_MULTIPLIERS as CALCULATOR_GOALS,
)
from fitminiapp_api.services.nutrition import (
    NutritionMacroAllocationError,
    calculate_nutrition,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_CALCULATOR = REPO_ROOT / "frontend/src/features/nutrition/nutritionCalculator.ts"


def test_goal_multipliers_have_single_approved_semantics_across_engines() -> None:
    source = FRONTEND_CALCULATOR.read_text(encoding="utf-8")
    match = re.search(r"export const goalMultipliers\s*=\s*\{([^}]+)\}", source)
    assert match is not None, "Frontend goal multiplier declaration not found"
    frontend_goals = {
        goal: float(value)
        for goal, value in re.findall(
            r"(fat_loss|recomposition|maintenance|muscle_gain):\s*([\d.]+)", match[1]
        )
    }
    assert frontend_goals == CALCULATOR_GOALS == ADAPTIVE_GOALS
    assert CALCULATOR_GOALS["recomposition"] == 0.95


@pytest.mark.parametrize("sex", ["male", "female"])
@pytest.mark.parametrize("goal", ["fat_loss", "recomposition", "maintenance", "muscle_gain"])
@pytest.mark.parametrize(
    "weight_kg,height_cm,age",
    [
        (20, 100, 18),
        (55, 165, 25),
        (78, 165, 34),
        (105, 185, 45),
        (160, 170, 65),
        (350, 100, 100),
    ],
)
def test_automated_goal_preserves_energy_and_does_not_relabel_a_surplus_as_deficit(
    sex: str, goal: str, weight_kg: int, height_cm: int, age: int
) -> None:
    payload = NutritionTargetSave(
        sex=sex,
        weight_kg=weight_kg,
        height_cm=height_cm,
        age=age,
        daily_routine="mostly_sitting",
        steps_range="up_to_4000",
        strength_trainings_per_week=0,
        cardio_trainings=[],
        goal=goal,
    )
    try:
        result = calculate_nutrition(payload)
    except NutritionMacroAllocationError:
        # Current bodyweight-based macros are infeasible: rejection is safer
        # than silently changing energy goals, until #1072 policy is validated.
        return

    assert result["carbs_g"] >= 0
    assert not result["macro_warning"]
    energy = 4 * result["protein_g"] + 9 * result["fat_g"] + 4 * result["carbs_g"]
    assert abs(energy - result["calories"]) <= 2
    if goal in {"fat_loss", "recomposition"}:
        assert result["calories"] <= result["tdee"]
    assert result["goal_multiplier"] == CALCULATOR_GOALS[goal]


def test_scientific_validation_does_not_infer_individual_accuracy_from_code_checks() -> None:
    # Predictions cannot be declared clinically accurate without external
    # measured REE/TDEE reference datasets, irrespective of passing unit tests.
    report = (REPO_ROOT / "docs/nutrition/scientific-validation-1072-2026-10.md").read_text(
        encoding="utf-8"
    )
    assert "NOT_VALIDATED" in report
    assert "measured REE" in report


@pytest.mark.parametrize(
    "case",
    json.loads(
        (REPO_ROOT / "frontend/tests/fixtures/nutrition-calculator-golden.json").read_text(
            encoding="utf-8"
        )
    ),
    ids=lambda item: item["name"],
)
def test_python_calculator_matches_shared_golden_cases(case: dict) -> None:
    payload = NutritionTargetSave(**case["input"])
    if case["expected"] is None:
        with pytest.raises(NutritionMacroAllocationError):
            calculate_nutrition(payload)
        return

    actual = calculate_nutrition(payload)
    for field, expected in case["expected"].items():
        assert actual[field] == expected, f"{case['name']} drifted on {field}"
