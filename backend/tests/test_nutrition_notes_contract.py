import pytest
from pydantic import ValidationError

from fitminiapp_api.schemas.nutrition_notes import NutritionMealNoteUpdate


def test_nutrition_note_values_are_independent_and_none_is_explicit():
    payload = NutritionMealNoteUpdate(hunger_before="none", note="Еда 🍲")
    assert payload.hunger_before == "none"
    assert payload.fullness_after is None
    assert payload.energy is None
    assert payload.note == "Еда 🍲"
    assert NutritionMealNoteUpdate().hunger_before is None


def test_nutrition_note_rejects_invalid_values_and_long_text():
    with pytest.raises(ValidationError):
        NutritionMealNoteUpdate(hunger_before="0")
    with pytest.raises(ValidationError):
        NutritionMealNoteUpdate(note="я" * 501)
    assert len(NutritionMealNoteUpdate(note="я" * 500).note or "") == 500
