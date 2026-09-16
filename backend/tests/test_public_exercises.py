import pytest

from fitminiapp_api.services.exercise_guides import PROFILES
from fitminiapp_api.services.public_exercises import (
    public_exercise,
    public_exercise_quality_errors,
    public_exercises,
    validate_public_exercise_quality,
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
    assert len(media) == 2
    assert all(item["source_name"] == "free-exercise-db" for item in media)
