"""Hevy workout CSV export adapter."""

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
    unsupported,
)
from fitminiapp_api.services.workout_history_import_parser import (
    ImportIssue,
    ImportRow,
    WorkoutHistoryImportError,
)

_BASE = {
    "title",
    "start_time",
    "end_time",
    "description",
    "exercise_title",
    "superset_id",
    "exercise_notes",
    "set_index",
    "set_type",
    "reps",
    "duration_seconds",
    "rpe",
}
_WEIGHTS = {"weight_kg", "weight_lbs"}
_DISTANCES = {"distance_km", "distance_miles"}
_KINDS = {"normal": "working", "warmup": "warmup", "dropset": "drop", "failure": "working"}


def parse(content: bytes, *, weight_unit: str = "") -> tuple[ImportRow, ...]:
    del weight_unit
    limit = deadline()
    header, values = read_table(content, ",", limit)
    check_columns(header, _BASE, _BASE | _WEIGHTS | _DISTANCES)
    weights, distances = _WEIGHTS & set(header), _DISTANCES & set(header)
    if len(weights) != 1 or len(distances) != 1:
        raise WorkoutHistoryImportError(
            "columns", "Проверьте единицы веса и расстояния в файле Hevy"
        )
    weight_column, distance_column = next(iter(weights)), next(iter(distances))
    groups: dict[str, tuple[str, int, str]] = {}
    counters: defaultdict[tuple[str, str], int] = defaultdict(int)
    metadata: dict[str, str] = {}
    seen_sets: set[tuple[str, str, str]] = set()
    rows = []
    for line, fields in values:
        check_deadline(limit)
        start = timestamp(fields["start_time"], ())
        end = timestamp(fields["end_time"], ())
        workout_ref = ref("hevy", fields["title"], fields["start_time"])
        name = fields["exercise_title"]
        previous_name, occurrence, exercise_ref = groups.get(workout_ref, ("", 0, ""))
        if name != previous_name:
            occurrence += 1
            exercise_ref = ref(workout_ref, str(occurrence), name)
            groups[workout_ref] = (name, occurrence, exercise_ref)
        counters[(workout_ref, exercise_ref)] += 1
        kind = fields["set_type"].casefold()
        issues = []
        if start is None or end is None:
            issues.append(
                ImportIssue("invalid_time", "start_time", "Дата или время тренировки не распознаны")
            )
        elif (start.tzinfo is None) != (end.tzinfo is None) or end < start:
            issues.append(
                ImportIssue("invalid_time", "end_time", "Проверьте начало и окончание тренировки")
            )
        if not fields["set_index"].isdigit():
            issues.append(
                ImportIssue("invalid_set_order", "set_index", "Порядок подхода не распознан")
            )
        else:
            set_key = (workout_ref, exercise_ref, fields["set_index"])
            if set_key in seen_sets:
                issues.append(
                    ImportIssue("duplicate_set", "set_index", "Порядок подхода повторяется")
                )
            seen_sets.add(set_key)
        if kind not in _KINDS:
            issues.append(
                ImportIssue("unsupported_set_kind", "set_type", "Тип подхода не поддерживается")
            )
        if workout_ref in metadata and metadata[workout_ref] != fields["end_time"]:
            issues.append(
                ImportIssue(
                    "workout_conflict", "end_time", "Время окончания тренировки различается"
                )
            )
        metadata[workout_ref] = fields["end_time"]
        issues += unsupported(fields, (distance_column, "duration_seconds"), zero_is_empty=True)
        issues += unsupported(fields, ("superset_id",))
        source = {
            "workout_ref": workout_ref,
            "started_at": start.isoformat() if start else "",
            "completed_at": end.isoformat() if end else "",
            "performed_on": start.date().isoformat() if start else "",
            "workout_title": fields["title"],
            "status": "completed",
            "exercise_ref": exercise_ref,
            "exercise_name": name,
            "set_number": str(counters[(workout_ref, exercise_ref)]),
            "set_status": "completed",
            "set_kind": _KINDS.get(kind, ""),
            "reps": fields["reps"],
            "weight": fields[weight_column],
            "weight_unit": ("kg" if weight_column == "weight_kg" else "lb")
            if fields[weight_column]
            else "",
            "rpe": fields["rpe"],
            "reached_failure": "true" if kind == "failure" else "",
        }
        rows.append(row(line, fields, source, issues))
    return tuple(rows)
