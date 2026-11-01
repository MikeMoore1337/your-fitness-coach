"""Strong workout CSV export adapter."""

from __future__ import annotations

from collections import defaultdict

from fitminiapp_api.services.workout_history_adapters.common import (
    check_columns,
    check_deadline,
    deadline,
    read_table,
    ref,
    row,
    timestamp,
    unit,
    unsupported,
)
from fitminiapp_api.services.workout_history_import_parser import ImportIssue, ImportRow

_COLUMNS = {
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
}
_NEW_COLUMNS = (_COLUMNS - {"Duration", "Weight", "Distance"}) | {
    "Workout #",
    "Duration (sec)",
    "Weight (kg)",
    "Distance (meters)",
}


def parse(content: bytes, *, weight_unit: str = "") -> tuple[ImportRow, ...]:
    limit = deadline()
    first_line = content.split(b"\n", 1)[0]
    delimiter = ";" if b"Workout #" in first_line and b";" in first_line else ","
    header, values = read_table(content, delimiter, limit)
    columns = _NEW_COLUMNS if delimiter == ";" else _COLUMNS
    check_columns(header, columns, columns)
    new_format = delimiter == ";"
    groups: dict[str, tuple[str, int, str]] = {}
    counters: defaultdict[tuple[str, str], int] = defaultdict(int)
    seen_sets: set[tuple[str, str, str]] = set()
    workout_numbers: dict[str, str] = {}
    rows = []
    for line, fields in values:
        check_deadline(limit)
        start = timestamp(fields["Date"], ("%Y-%m-%d %H:%M",))
        workout_ref = ref("strong", fields["Date"], fields["Workout Name"])
        name = fields["Exercise Name"]
        previous_name, occurrence, exercise_ref = groups.get(workout_ref, ("", 0, ""))
        if name != previous_name:
            occurrence += 1
            exercise_ref = ref(workout_ref, str(occurrence), name)
            groups[workout_ref] = (name, occurrence, exercise_ref)
        counters[(workout_ref, exercise_ref)] += 1
        order = fields["Set Order"].strip().casefold()
        kinds = {"w": "warmup", "d": "drop", "f": "working"}
        issues = []
        if start is None:
            issues.append(
                ImportIssue("invalid_time", "Date", "Дата или время тренировки не распознаны")
            )
        if new_format:
            number = fields["Workout #"]
            if workout_ref in workout_numbers and workout_numbers[workout_ref] != number:
                issues.append(
                    ImportIssue(
                        "workout_conflict",
                        "Workout #",
                        "Тренировки с одинаковым временем нельзя различить",
                    )
                )
            workout_numbers[workout_ref] = number
        if (not order.isdigit() and order not in kinds) or (order.isdigit() and int(order) < 1):
            issues.append(
                ImportIssue(
                    "unsupported_set_kind", "Set Order", "Порядок или тип подхода не поддерживается"
                )
            )
        if order.isdigit():
            set_key = (workout_ref, exercise_ref, order)
            if set_key in seen_sets:
                issues.append(
                    ImportIssue("duplicate_set", "Set Order", "Порядок подхода повторяется")
                )
            seen_sets.add(set_key)
        issues += unsupported(
            fields,
            ("Distance (meters)" if new_format else "Distance", "Seconds"),
            zero_is_empty=True,
        )
        weight = fields["Weight (kg)" if new_format else "Weight"]
        source = {
            "workout_ref": workout_ref,
            "started_at": start.isoformat() if start else "",
            "performed_on": start.date().isoformat() if start else "",
            "workout_title": fields["Workout Name"],
            "status": "completed",
            "exercise_ref": exercise_ref,
            "exercise_name": name,
            "set_number": str(counters[(workout_ref, exercise_ref)]),
            "set_status": "completed",
            "set_kind": kinds.get(order, "working" if order.isdigit() else ""),
            "reps": fields["Reps"],
            "weight": weight,
            "weight_unit": ("kg" if new_format else unit(weight_unit)) if weight else "",
            "rpe": fields["RPE"],
            "reached_failure": "true" if order == "f" else "",
        }
        rows.append(row(line, fields, source, issues))
    return tuple(rows)
