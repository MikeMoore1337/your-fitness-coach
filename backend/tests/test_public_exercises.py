import pytest

from fitminiapp_api.services.exercise_guides import PROFILES
from fitminiapp_api.services.public_exercises import (
    public_exercise,
    public_exercise_quality_errors,
    public_exercises,
    validate_public_exercise_quality,
)
from fitminiapp_api.services.public_programs import (
    public_program,
    public_program_quality_errors,
    validate_public_program,
)


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("technique_steps", []),
        ("common_mistakes", []),
        ("safety_notes", []),
        ("source_name", ""),
        ("source_license", ""),
    ],
)
def test_quality_contract_rejects_missing_required_public_content(field, invalid_value):
    exercise = public_exercise("bench-press")
    assert exercise is not None
    broken = dict(exercise)
    broken[field] = invalid_value

    assert field in public_exercise_quality_errors(broken)
    with pytest.raises(RuntimeError, match="public quality contract"):
        validate_public_exercise_quality(broken)


def test_allowlisted_builder_applies_quality_gate(monkeypatch):
    profile = dict(PROFILES["chest_press"])
    profile["mistakes"] = []
    monkeypatch.setitem(PROFILES, "chest_press", profile)
    public_exercises.cache_clear()

    try:
        with pytest.raises(RuntimeError, match="common_mistakes"):
            public_exercises()
    finally:
        public_exercises.cache_clear()


def test_bench_press_public_record_uses_existing_media_provenance():
    exercise = public_exercise("bench-press")
    assert exercise is not None
    assert public_exercise_quality_errors(exercise) == ()
    assert exercise["slug"] == "bench-press"
    media = exercise["media"]
    assert isinstance(media, list)
    assert len(media) == 1
    assert media[0]["source_name"] == "Gym visual"
    assert media[0]["source_license"] == "Owner-purchased GymVisual license"


def test_full_body_public_program_reuses_canonical_three_day_seed():
    program = public_program("full-body-3-days")

    assert program is not None
    assert public_program_quality_errors(program) == ()
    assert [day["title"] for day in program["days"]] == [
        "Фуллбади A",
        "Фуллбади B",
        "Фуллбади C",
    ]
    assert len(program["days"]) == 3
    assert program["days"][0]["exercises"][0] == {
        "slug": "squat",
        "title": "Приседания",
        "primary_muscle": "Квадрицепс",
        "equipment": "Штанга",
        "difficulty_level": "intermediate",
        "prescribed_sets": 4,
        "prescribed_reps": "6-8",
        "rest_seconds": 150,
    }


def test_public_program_quality_gate_rejects_non_three_day_shape():
    program = public_program("full-body-3-days")
    assert program is not None
    broken = dict(program)
    broken["days"] = list(program["days"])[:2]

    assert "days" in public_program_quality_errors(broken)
    with pytest.raises(RuntimeError, match="public quality contract"):
        validate_public_program(broken)
