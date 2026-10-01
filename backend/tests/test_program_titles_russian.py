from fitminiapp_api.services.program_seed_data import (
    STRENGTH_TEMPLATE_SPECS,
)

BANNED_GENERIC_ENGLISH = (
    "Beginner",
    "Intermediate",
    "Advanced",
    "Full Body",
    "Upper/Lower",
    "Push/Pull/Legs",
    "Hypertrophy",
)


def test_builtin_program_titles_are_russian_first() -> None:
    titles = [str(spec["title"]) for spec in STRENGTH_TEMPLATE_SPECS]

    assert titles
    for title in titles:
        assert all(token not in title for token in BANNED_GENERIC_ENGLISH), title


def test_generic_split_titles_explain_abbreviations_in_russian() -> None:
    by_slug = {str(spec["slug"]): str(spec["title"]) for spec in STRENGTH_TEMPLATE_SPECS}

    assert by_slug["strength-fullbody-3d"] == "Всё тело · 3 дня"
    assert by_slug["strength-upper-lower-4d"] == "Верх/низ · 4 дня"
    assert by_slug["strength-push-pull-legs-6d"] == "Толкай/тяни/ноги (PPL) · 6 дней"


BANNED_VISIBLE_NOTE_ENGLISH = (
    "last set",
    "Main lift",
    "Alternating main lift",
    "Source range",
    "Training Max",
    "TRAINING_MAX",
    "selected DB",
    "Assistance boundary",
)


def test_builtin_program_exercise_copy_is_russian_first() -> None:
    for spec in STRENGTH_TEMPLATE_SPECS:
        for _day_title, exercises in spec["days"]:
            for exercise in exercises:
                reps = str(exercise[2])
                assert "AMRAP" not in reps, (spec["slug"], reps)

                if len(exercise) < 5:
                    continue
                metadata = exercise[4]
                notes = metadata.get("notes")
                if not isinstance(notes, str):
                    continue

                assert all(token not in notes for token in BANNED_VISIBLE_NOTE_ENGLISH), (
                    spec["slug"],
                    notes,
                )
                if "AMRAP" in notes:
                    assert "максимум повторений" in notes, (spec["slug"], notes)
                if any(tier in notes for tier in ("T1", "T2", "T3")):
                    assert " - " in notes, (spec["slug"], notes)
                if "FSL" in notes:
                    assert "Повтор первого рабочего подхода" in notes, (spec["slug"], notes)
