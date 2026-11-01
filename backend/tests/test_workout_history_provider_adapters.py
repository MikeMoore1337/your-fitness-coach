import csv
import io
from datetime import date
from decimal import Decimal

import pytest
from test_training_analytics import _auth, _user_id

from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.program import UserWorkout
from fitminiapp_api.models.user import User
from fitminiapp_api.models.workout_history_import import ImportedWorkout
from fitminiapp_api.services.account_export import build_account_export
from fitminiapp_api.services.workout_history_adapters import fitnotes, hevy, strong
from fitminiapp_api.services.workout_history_import_parser import (
    MAX_BYTES,
    WorkoutHistoryImportError,
)


def csv_file(columns, rows):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode()


HEVY = (
    "title",
    "start_time",
    "end_time",
    "description",
    "exercise_title",
    "superset_id",
    "exercise_notes",
    "set_index",
    "set_type",
    "weight_lbs",
    "reps",
    "distance_miles",
    "duration_seconds",
    "rpe",
)
STRONG = (
    "Date",
    "Workout Name",
    "Duration",
    "Exercise Name",
    "Set Order",
    "Weight",
    "Reps",
    "Distance",
    "Seconds",
    "Notes",
    "Workout Notes",
    "RPE",
)
FITNOTES = (
    "Date",
    "Exercise",
    "Category",
    "Weight",
    "Weight Unit",
    "Reps",
    "Distance",
    "Distance Unit",
    "Time",
    "Comment",
)


def hevy_row(**changes):
    return {
        "title": "Тренировка",
        "start_time": "22 Dec 2025, 08:00",
        "end_time": "22 Dec 2025, 08:37",
        "exercise_title": "Жим",
        "set_index": "0",
        "set_type": "normal",
        "weight_lbs": "100",
        "reps": "8",
        **changes,
    }


def strong_row(**changes):
    return {
        "Date": "2025-12-22 08:00:00",
        "Workout Name": "Верх",
        "Duration": "37m",
        "Exercise Name": "Жим",
        "Set Order": "1",
        "Weight": "100",
        "Reps": "8",
        "Distance": "0",
        "Seconds": "0",
        **changes,
    }


def fitnotes_row(**changes):
    return {
        "Date": "2025-12-22",
        "Exercise": "Жим",
        "Category": "Грудь",
        "Weight": "100",
        "Weight Unit": "lbs",
        "Reps": "8",
        **changes,
    }


@pytest.mark.parametrize(
    ("adapter", "columns", "source", "kwargs"),
    [
        (hevy.parse, HEVY, hevy_row(), {}),
        (strong.parse, STRONG, strong_row(), {"weight_unit": "lb"}),
        (fitnotes.parse, FITNOTES, fitnotes_row(), {}),
    ],
)
def test_source_weight_and_date_are_preserved_without_inventing_a_timezone(
    adapter, columns, source, kwargs
):
    (parsed,) = adapter(csv_file(columns, [source]), **kwargs)
    assert parsed.issues == ()
    assert parsed.completed_on == date(2025, 12, 22)
    assert parsed.completed_at_utc is None
    assert parsed.source["timezone"] == ""
    assert parsed.weight_kg == Decimal("45.36")
    assert parsed.source["weight"] == "100"
    assert parsed.source["weight_unit"] == "lb"
    assert parsed.provider_fields is not None


def test_strong_unit_must_be_supplied_and_rpe_is_not_guessed():
    (parsed,) = strong.parse(csv_file(STRONG, [strong_row(RPE="8")]))
    assert {issue.code for issue in parsed.issues} >= {"invalid_weight_unit", "unsupported_rpe"}
    assert parsed.provider_fields["RPE"] == "8"


def test_fitnotes_groups_by_date_and_leaves_time_and_set_type_unknown():
    rows = fitnotes.parse(csv_file(FITNOTES, [fitnotes_row(), fitnotes_row(Reps="10")]))
    assert rows[0].source["workout_ref"] == rows[1].source["workout_ref"]
    assert rows[0].source["completed_at"] == ""
    assert rows[0].source["set_kind"] == ""
    assert [item.set_number for item in rows] == [1, 2]


def test_fitnotes_ios_uses_the_declared_unit_and_rejects_two_weights():
    columns = (
        "Date",
        "Exercise",
        "Category",
        "Weight (kg)",
        "Weight (lbs)",
        "Reps",
        "Distance",
        "Distance Unit",
        "Time",
        "Notes",
        "Kind",
    )
    source = {
        "Date": "2025-12-22",
        "Exercise": "Жим",
        "Weight (lbs)": "100",
        "Reps": "8",
        "Kind": "wr",
    }
    (parsed,) = fitnotes.parse(csv_file(columns, [source]))
    assert parsed.weight_kg == Decimal("45.36")
    assert parsed.issues == ()
    (ambiguous,) = fitnotes.parse(csv_file(columns, [source | {"Weight (kg)": "45"}]))
    assert any(issue.code == "ambiguous_weight" for issue in ambiguous.issues)


def test_strong_semicolon_export_uses_its_weight_header_and_reports_rest_rows():
    columns = (
        "Workout #",
        "Date",
        "Workout Name",
        "Duration (sec)",
        "Exercise Name",
        "Set Order",
        "Weight (kg)",
        "Reps",
        "RPE",
        "Distance (meters)",
        "Seconds",
        "Notes",
        "Workout Notes",
    )
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, delimiter=";", quoting=csv.QUOTE_ALL)
    writer.writeheader()
    source = {
        "Workout #": "1",
        "Date": "2025-12-22 08:00:00",
        "Workout Name": "Верх",
        "Exercise Name": "Жим",
        "Set Order": "1",
        "Weight (kg)": "45",
        "Reps": "8",
    }
    writer.writerow(source)
    writer.writerow(
        source | {"Set Order": "Rest Timer", "Weight (kg)": "", "Reps": "", "Seconds": "120"}
    )
    first, rest = strong.parse(output.getvalue().encode())
    assert first.weight_kg == Decimal("45.00")
    assert first.issues == ()
    assert any(issue.code == "unsupported_set_kind" for issue in rest.issues)
    assert rest.provider_fields["Seconds"] == "120"



def test_fitnotes_android_named_weight_columns_and_conflicts():
    columns = (
        "Date", "Exercise", "Category", "Weight (kgs)", "Weight (lbs)",
        "Reps", "Distance", "Distance Unit", "Time", "Comment",
    )
    source = {
        "Date": "2025-12-22",
        "Exercise": "Жим",
        "Weight (kgs)": "100",
        "Reps": "8",
    }
    kg, lb = fitnotes.parse(
        csv_file(columns, [source, source | {"Weight (kgs)": "", "Weight (lbs)": "135"}])
    )
    assert kg.issues == ()
    assert lb.issues == ()
    assert kg.weight_kg == Decimal("100")
    assert lb.weight_kg == Decimal("61.23")
    assert lb.source["weight_unit"] == "lb"
    (ambiguous,) = fitnotes.parse(
        csv_file(columns, [source | {"Weight (lbs)": "220"}])
    )
    assert any(issue.code == "ambiguous_weight" for issue in ambiguous.issues)


def test_fitnotes_ios_distance_kind_cannot_be_silently_dropped():
    columns = (
        "Date", "Exercise", "Category", "Weight (kg)", "Weight (lbs)",
        "Reps", "Distance", "Distance Unit", "Time", "Notes", "Kind",
    )
    (parsed,) = fitnotes.parse(
        csv_file(columns, [{
            "Date": "2025-12-22",
            "Exercise": "Жим",
            "Weight (kg)": "45",
            "Reps": "8",
            "Kind": "wrd",
        }])
    )
    assert any(
        issue.code == "unsupported_metric" and issue.field == "Kind"
        for issue in parsed.issues
    )
    assert parsed.provider_fields["Kind"] == "wrd"


def test_strong_modern_workout_number_and_high_precision_weight():
    columns = (
        "Workout #", "Date", "Workout Name", "Duration (sec)", "Exercise Name",
        "Set Order", "Weight (kg)", "Reps", "RPE", "Distance (meters)",
        "Seconds", "Notes", "Workout Notes",
    )

    def modern_file(rows):
        output = io.StringIO(newline="")
        writer = csv.DictWriter(
            output, fieldnames=columns, delimiter=";", quoting=csv.QUOTE_ALL
        )
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue().encode()

    source = {
        "Workout #": "21",
        "Date": "2025-12-22 08:00:00",
        "Workout Name": "Верх",
        "Exercise Name": "Жим",
        "Set Order": "1",
        "Weight (kg)": "61.23492",
        "Reps": "8",
    }
    first, second = strong.parse(modern_file([source, source | {"Workout #": "22"}]))
    assert first.issues == ()
    assert second.issues == ()
    assert first.source["workout_ref"] != second.source["workout_ref"]
    assert first.weight_kg == Decimal("61.23")
    assert first.source["weight"] == "61.23"
    assert first.provider_fields["Weight (kg)"] == "61.23492"
    (missing,) = strong.parse(modern_file([source | {"Workout #": ""}]))
    assert any(issue.code == "invalid_source_id" for issue in missing.issues)
    _, conflict = strong.parse(modern_file([source, source | {"Workout Name": "Низ"}]))
    assert any(issue.code == "workout_conflict" for issue in conflict.issues)


def test_fitnotes_explicit_set_kind_changes_statistics_without_claiming_it_came_from_file(client):
    headers = _auth(client, 834_104)
    content = csv_file(FITNOTES, [fitnotes_row(Exercise="barbell bench press")])
    response = client.post(
        "/api/v1/workout-history-imports",
        headers=headers,
        data={"provider": "fitnotes"},
        files={"file": ("history.csv", content, "text/csv")},
    )
    assert response.status_code == 201, response.text
    preview = response.json()
    line = preview["rows"][0]["line"]
    resolved = client.post(
        f"/api/v1/workout-history-imports/{preview['id']}/resolve",
        headers=headers,
        json={"version": preview["version"], "set_kind_choices": {str(line): "working"}},
    )
    assert resolved.status_code == 200, resolved.text
    preview = resolved.json()
    assert preview["rows"][0]["source"]["set_kind"] == ""
    assert preview["rows"][0]["manual_set_kind"] == "working"
    confirmed = client.post(
        f"/api/v1/workout-history-imports/{preview['id']}/confirm",
        headers=headers,
        json={"version": preview["version"], "preview_signature": preview["preview_signature"]},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert client.get("/api/v1/workouts/history/summary", headers=headers).json() == {
        "workouts_completed": 1,
        "completed_sets": 1,
        "volume_kg": 362.88,
    }
    with get_session_context() as db:
        provenance = db.get(ImportedWorkout, confirmed.json()["result"]["workout_ids"][0])
        assert provenance.source_data["sets"][0]["user_set_kind"] == "working"


def test_hevy_unsupported_duration_is_visible_and_blocks_the_row():
    (parsed,) = hevy.parse(csv_file(HEVY, [hevy_row(duration_seconds="75")]))
    assert any(issue.field == "duration_seconds" for issue in parsed.issues)
    assert parsed.provider_fields["duration_seconds"] == "75"


@pytest.mark.parametrize("adapter", [hevy.parse, strong.parse, fitnotes.parse])
def test_adapters_reject_malformed_and_oversized_input(adapter):
    for content in (b'"unclosed', b"x" * (MAX_BYTES + 1), b"\xff"):
        with pytest.raises(WorkoutHistoryImportError):
            adapter(content)


@pytest.mark.parametrize(
    ("provider", "columns", "source", "later", "weight_unit", "identity"),
    [
        (
            "hevy",
            HEVY,
            hevy_row(exercise_title="barbell bench press"),
            hevy_row(
                title="Другая",
                start_time="23 Dec 2025, 08:00",
                end_time="23 Dec 2025, 08:37",
                exercise_title="barbell bench press",
            ),
            "",
            834_101,
        ),
        (
            "strong",
            STRONG,
            strong_row(**{"Exercise Name": "barbell bench press"}),
            strong_row(**{"Date": "2025-12-23 08:00:00", "Exercise Name": "barbell bench press"}),
            "lb",
            834_102,
        ),
        (
            "fitnotes",
            FITNOTES,
            fitnotes_row(Exercise="barbell bench press"),
            fitnotes_row(Date="2025-12-23", Exercise="barbell bench press"),
            "",
            834_103,
        ),
    ],
)
def test_provider_preview_commit_and_overlapping_export(
    client, provider, columns, source, later, weight_unit, identity
):
    headers = _auth(client, identity)

    def upload(rows):
        return client.post(
            "/api/v1/workout-history-imports",
            headers=headers,
            data={"provider": provider, "weight_unit": weight_unit},
            files={"file": ("history.csv", csv_file(columns, rows), "text/csv")},
        )

    response = upload([source])
    assert response.status_code == 201, response.text
    preview = response.json()
    assert preview["provider"] == provider
    assert preview["rows"][0]["blocking_issues"] == []
    assert preview["rows"][0]["completed_at_utc"] is None
    assert preview["rows"][0]["provider_fields"]
    confirmed = client.post(
        f"/api/v1/workout-history-imports/{preview['id']}/confirm",
        headers=headers,
        json={"version": preview["version"], "preview_signature": preview["preview_signature"]},
    )
    assert confirmed.status_code == 200, confirmed.text
    workout_id = confirmed.json()["result"]["workout_ids"][0]
    with get_session_context() as db:
        workout = db.get(UserWorkout, workout_id)
        provenance = db.get(ImportedWorkout, workout_id)
        assert workout.completed_at_utc is None
        assert workout.scheduled_date == date(2025, 12, 22)
        assert workout.exercises[0].sets[0].actual_weight == Decimal("45.36")
        assert provenance.source_timezone == ""
        assert provenance.source_data["sets"][0]["fields"]
        if provider == "fitnotes":
            assert workout.completed_at is None
            assert workout.exercises[0].sets[0].set_kind is None
            assert workout.exercises[0].sets[0].set_kind_known is False
        exported = build_account_export(db, db.get(User, _user_id(identity)))
        assert exported["imported_workouts"][0]["source_data"] == provenance.source_data

    replay = upload([source, later])
    assert replay.status_code == 201, replay.text
    candidates = [
        candidate for group in replay.json()["duplicates"] for candidate in group["candidates"]
    ]
    assert any(
        candidate["kind"] == "source" and candidate["workout_id"] == workout_id
        for candidate in candidates
    )
    assert (
        client.post(
            f"/api/v1/workout-history-imports/{preview['id']}/confirm",
            headers=headers,
            json={"version": preview["version"], "preview_signature": preview["preview_signature"]},
        ).json()
        == confirmed.json()
    )
