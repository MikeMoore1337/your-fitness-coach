"""Scientific-model MET parameter drift guard (#1072), not a clinical accuracy test.

The same user input must not silently use different exercise coefficients
in Python and TypeScript. This intentionally does *not* assert that current
MET estimates are empirically correct or that categories match the Compendium.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from fitminiapp_api.services.nutrition import (
    CARDIO_BASE_MET_VALUES,
    CARDIO_INTENSITY_MULTIPLIERS,
    STRENGTH_MET_VALUES,
    STRENGTH_REST_ADJUSTMENTS,
)

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend/src/features/nutrition/nutritionCalculator.ts"

PARAMETER_MAPS = (
    ("strengthMetValues", STRENGTH_MET_VALUES),
    ("strengthRestAdjustments", STRENGTH_REST_ADJUSTMENTS),
    ("cardioMetValues", CARDIO_BASE_MET_VALUES),
    ("cardioIntensityMultipliers", CARDIO_INTENSITY_MULTIPLIERS),
)


def _typescript_numeric_map(source: str, name: str) -> dict[str, float]:
    """Parse only these simple declarative TS numeric maps; fail on shape drift."""
    pattern = rf"const\s+{re.escape(name)}\s*:[^=]+?=\s*\{{([^}}]+)\}}\s*;"
    match = re.search(pattern, source)
    assert match is not None, f"{name}: TS declaration changed, review parser"
    values: dict[str, float] = {}
    for line in match.group(1).strip().splitlines():
        entry = re.fullmatch(r"\s*(\w+):\s*(-?\d+(?:\.\d+)?),?\s*", line)
        assert entry is not None, f"{name}: unsupported entry: {line!r}"
        key, value = entry.groups()
        assert key not in values, f"{name}: duplicate key: {key}"
        values[key] = float(value)
    assert values, f"{name}: empty numeric map"
    return values


@pytest.mark.parametrize("typescript_name,python_values", PARAMETER_MAPS, ids=[m[0] for m in PARAMETER_MAPS])
def test_exercise_met_parameters_match_python_and_typescript(
    typescript_name: str, python_values: dict[str, float]
) -> None:
    ts_source = FRONTEND.read_text(encoding="utf-8")
    frontend_values = _typescript_numeric_map(ts_source, typescript_name)
    assert frontend_values == python_values, (
        f"{typescript_name}: changing exercise assumptions requires "
        "reviewing frontend/backend together and updating #1072 evidence"
    )
