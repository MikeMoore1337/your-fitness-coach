import csv
import io
from datetime import date, datetime
from decimal import Decimal

import pytest

from fitminiapp_api.services import workout_history_import_parser
from fitminiapp_api.services.workout_history_import_parser import (
    CSV_COLUMNS,
    MAX_BYTES,
    MAX_CELL_CHARS,
    MAX_ROWS,
    WorkoutHistoryImportError,
    parse_workout_history_csv,
)


def _row(**changes):
    row = {
        "workout_ref": "workout-1",
        "completed_at": "2025-10-12T18:30:00+03:00",
        "timezone": "Europe/Moscow",
        "workout_title": "Верх тела",
        "status": "completed",
        "exercise_ref": "exercise-1",
        "exercise_name": "Жим штанги лёжа",
        "set_number": "1",
        "set_status": "completed",
        "set_kind": "working",
        "reps": "8",
        "weight": "100",
        "weight_unit": "lb",
        "rir": "2",
        "rpe": "",
        "side": "",
    }
    return row | changes


def _csv(*rows, columns=CSV_COLUMNS, marker=("yfc_workout_history", "1")):
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(marker)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row.get(column, "") for column in columns])
    return output.getvalue().encode("utf-8")


def _codes(row):
    return {issue.code for issue in row.issues}


def test_parser_stops_when_time_budget_is_exceeded(monkeypatch):
    times = iter((0.0, 6.0))
    monkeypatch.setattr(workout_history_import_parser, "monotonic", lambda: next(times))
    with pytest.raises(WorkoutHistoryImportError) as error:
        parse_workout_history_csv(_csv(_row()))
    assert error.value.code == "parse_timeout"


def test_normalizes_completed_set_without_inventing_values():
    (row,) = parse_workout_history_csv(_csv(_row()))
    assert row.issues == ()
    assert row.line == 3
    assert row.completed_at_utc == datetime(2025, 10, 12, 15, 30)
    assert row.completed_on == date(2025, 10, 12)
    assert row.reps == 8
    assert row.weight_kg == Decimal("45.36")
    assert row.source["weight"] == "100"
    assert row.source["weight_unit"] == "lb"
    assert row.source["rir"] == "2"


def test_missing_weight_stays_missing():
    (row,) = parse_workout_history_csv(_csv(_row(weight="", weight_unit="")))
    assert row.issues == ()
    assert row.weight_kg is None
    assert row.reps == 8


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"timezone": "No/Such_Zone"}, "invalid_timezone"),
        ({"timezone": "../secret"}, "invalid_timezone"),
        ({"timezone": "x" * 129}, "invalid_timezone"),
        ({"completed_at": "2025-02-30T12:00:00+03:00"}, "invalid_completed_at"),
        ({"completed_at": "0001-01-01T00:00:00+03:00"}, "invalid_completed_at"),
        ({"completed_at": "2999-01-01T12:00:00+03:00"}, "future_completed_at"),
        ({"completed_at": "2025-10-12T18:30:00"}, "invalid_completed_at"),
        ({"completed_at": "2025-10-12T18:30:00+02:00"}, "timezone_mismatch"),
        (
            {"completed_at": "2025-03-09T02:30:00-05:00", "timezone": "America/New_York"},
            "timezone_mismatch",
        ),
        ({"weight_unit": "stone"}, "invalid_weight_unit"),
        ({"weight": "-1"}, "invalid_weight"),
        ({"weight": "NaN"}, "invalid_weight"),
        ({"weight": "0.001", "weight_unit": "kg"}, "weight_precision"),
        ({"weight": "0.001", "weight_unit": "lb"}, "weight_precision"),
        ({"weight": "", "weight_unit": "kg"}, "weight_missing"),
        ({"reps": "", "weight": "", "weight_unit": ""}, "result_missing"),
        ({"reps": "2.5"}, "invalid_integer"),
        ({"set_number": "0"}, "invalid_integer"),
        ({"rir": "5"}, "invalid_rir"),
        ({"set_kind": ""}, "invalid_set_kind"),
        ({"status": "planned"}, "not_completed"),
        ({"set_status": "planned"}, "set_not_completed"),
        ({"exercise_name": "=HYPERLINK(1)"}, "unsafe_text"),
        ({"workout_title": ""}, "invalid_text"),
    ],
)
def test_invalid_values_are_blocking_and_identified(changes, expected):
    (row,) = parse_workout_history_csv(_csv(_row(**changes)))
    assert expected in _codes(row)


def test_unsupported_rpe_and_per_side_values_are_not_discarded():
    (row,) = parse_workout_history_csv(_csv(_row(rpe="8", side="left")))
    assert {"unsupported_rpe", "unsupported_side"} <= _codes(row)
    assert row.source["rpe"] == "8"
    assert row.source["side"] == "left"


def test_duplicate_set_and_inconsistent_workout_or_exercise_are_reported():
    first, second = parse_workout_history_csv(
        _csv(_row(), _row(workout_title="Другая", exercise_name="Тяга"))
    )
    assert first.issues == ()
    assert {"duplicate_set", "workout_conflict", "exercise_conflict"} <= _codes(second)


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b"", "file_size"),
        (b"x" * (MAX_BYTES + 1), "file_size"),
        (b"\xff", "encoding"),
        (_csv(_row(), marker=("unknown", "1")), "version"),
        (_csv(_row(), columns=CSV_COLUMNS[:-1]), "columns"),
        (_csv(), "empty"),
        (_csv(_row(exercise_name="x" * (MAX_CELL_CHARS + 1))), "cell_limit"),
        (_csv(_row(exercise_name="one\ntwo")), "cell_limit"),
        (
            b"yfc_workout_history,1\n"
            + b",".join(x.encode() for x in CSV_COLUMNS)
            + b'\n"unterminated',
            "malformed_csv",
        ),
        (_csv(_row()) + b"only-one-column\n", "row_width"),
        (_csv(_row(exercise_name="unsafe\x00name")), "control_character"),
        (_csv(_row(exercise_name="unsafe\tname")), "control_character"),
    ],
    ids=[
        "empty",
        "oversized",
        "encoding",
        "version",
        "columns",
        "no-rows",
        "long-cell",
        "multiline-cell",
        "malformed-csv",
        "row-width",
        "control-character",
        "tab-in-cell",
    ],
)
def test_bad_files_fail_closed(content, expected):
    with pytest.raises(WorkoutHistoryImportError) as error:
        parse_workout_history_csv(content)
    assert error.value.code == expected
    assert "unsafe\x00name" not in str(error.value)


def test_row_limit_is_enforced():
    content = _csv(*(_row(set_number=str(i)) for i in range(1, MAX_ROWS + 2)))
    assert len(content) < MAX_BYTES
    with pytest.raises(WorkoutHistoryImportError) as error:
        parse_workout_history_csv(content)
    assert error.value.code == "row_limit"
