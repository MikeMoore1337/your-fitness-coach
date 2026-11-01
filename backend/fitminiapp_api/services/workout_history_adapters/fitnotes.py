"""FitNotes Android and iOS spreadsheet export adapter."""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from fitminiapp_api.services.workout_history_adapters.common import (
    check_columns,
    check_deadline,
    deadline,
    read_table,
    ref,
    row,
    unit,
    unsupported,
)
from fitminiapp_api.services.workout_history_import_parser import ImportIssue, ImportRow

_COLUMNS = {
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
}
_IOS_COLUMNS = (_COLUMNS - {"Weight", "Weight Unit", "Comment"}) | {
    "Weight (kg)",
    "Weight (lbs)",
    "Notes",
    "Kind",
}
_ANDROID_NAMED_COLUMNS = (_COLUMNS - {"Weight", "Weight Unit"}) | {
    "Weight (kgs)",
    "Weight (lbs)",
}


def parse(content: bytes, *, weight_unit: str = "") -> tuple[ImportRow, ...]:
    del weight_unit
    limit = deadline()
    header, values = read_table(content, ",", limit)
    ios = "Kind" in header
    named_android = not ios and "Weight (kgs)" in header
    columns = _IOS_COLUMNS if ios else (_ANDROID_NAMED_COLUMNS if named_android else _COLUMNS)
    check_columns(header, columns, columns)
    groups: dict[str, tuple[str, int, str]] = {}
    counters: defaultdict[tuple[str, str], int] = defaultdict(int)
    rows = []
    for line, fields in values:
        check_deadline(limit)
        try:
            day = date.fromisoformat(fields["Date"])
            if day.isoformat() != fields["Date"]:
                raise ValueError
        except ValueError:
            day = None
        workout_ref = ref("fitnotes", fields["Date"])
        name = fields["Exercise"]
        previous_name, occurrence, exercise_ref = groups.get(workout_ref, ("", 0, ""))
        if name != previous_name:
            occurrence += 1
            exercise_ref = ref(workout_ref, str(occurrence), name)
            groups[workout_ref] = (name, occurrence, exercise_ref)
        counters[(workout_ref, exercise_ref)] += 1
        issues = []
        if day is None:
            issues.append(ImportIssue("invalid_date", "Date", "Дата тренировки не распознана"))
        if ios:
            if fields["Weight (kg)"] and fields["Weight (lbs)"]:
                issues.append(
                    ImportIssue("ambiguous_weight", "Weight (kg)", "Указан вес в двух единицах")
                )
            weight = fields["Weight (kg)"] or fields["Weight (lbs)"]
            source_unit = "kg" if fields["Weight (kg)"] else "lb"
            kind = fields["Kind"].casefold()
            if kind and any(char not in "wrdt" for char in kind):
                issues.append(
                    ImportIssue("unsupported_metric", "Kind", "Тип результата не поддерживается")
                )
            elif any(char in "dt" for char in kind):
                issues.append(
                    ImportIssue(
                        "unsupported_metric", "Kind", "Время или расстояние пока не поддерживаются"
                    )
                )
        elif named_android:
            if fields["Weight (kgs)"] and fields["Weight (lbs)"]:
                issues.append(
                    ImportIssue("ambiguous_weight", "Weight (kgs)", "Указан вес в двух единицах")
                )
            weight = fields["Weight (kgs)"] or fields["Weight (lbs)"]
            source_unit = "kg" if fields["Weight (kgs)"] else "lb"
        else:
            weight = fields["Weight"]
            source_unit = unit(fields["Weight Unit"])
        issues += unsupported(fields, ("Distance", "Time"), zero_is_empty=True)
        source = {
            "workout_ref": workout_ref,
            "performed_on": day.isoformat() if day else "",
            "workout_title": "FitNotes",
            "status": "completed",
            "exercise_ref": exercise_ref,
            "exercise_name": name,
            "set_number": str(counters[(workout_ref, exercise_ref)]),
            "set_status": "completed",
            "reps": fields["Reps"],
            "weight": weight,
            "weight_unit": source_unit if weight else "",
        }
        rows.append(row(line, fields, source, issues))
    return tuple(rows)
