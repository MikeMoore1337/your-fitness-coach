"""Conservative parser for the documented Russian FatSecret CSV profile."""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fitminiapp_api.services.nutrition_import_validation import (
    NutritionImportValidationError,
    validate_csv_upload,
)

ADAPTER_VERSION = "fatsecret-csv-v1"
DETAIL_HEADERS = (
    "калории (ккал)",
    "жир (г)",
    "н/жир (г)",
    "углеводы (г)",
    "клетчатка (г)",
    "сахар (г)",
    "белок (г)",
    "натрий (мг)",
    "холестерин (мг)",
    "калий (мг)",
)
SUMMARY_HEADERS = ("калории (ккал)", "жир (г)", "углеводы (г)", "белок (г)")
DETAIL_HEADERS_SHORT = (
    "кал (ккал)",
    "жир (г)",
    "н/жир (г)",
    "углев (г)",
    "клетч (г)",
    "сахар (г)",
    "белк (г)",
    "натри (мг)",
    "холес (мг)",
    "калий (мг)",
)
SUMMARY_HEADERS_SHORT = ("кал (ккал)", "жир (г)", "углев (г)", "белк (г)")
DETAIL_FIELDS = (
    ("energy_kcal", "kcal"),
    ("fat_g", "g"),
    (None, "g"),
    ("carbohydrate_g", "g"),
    ("fiber_g", "g"),
    ("sugars_g", "g"),
    ("protein_g", "g"),
    ("sodium_mg", "mg"),
    ("cholesterol_mg", "mg"),
    ("potassium_mg", "mg"),
)
SUMMARY_FIELDS = (DETAIL_FIELDS[0], DETAIL_FIELDS[1], DETAIL_FIELDS[3], DETAIL_FIELDS[6])
MEALS = {
    "завтрак": "breakfast",
    "обед": "lunch",
    "ужин": "dinner",
    "перекус": "snacks",
    "перекусы": "snacks",
    "перекус/другое": "snacks",
}
UNITS = {
    "г": "g",
    "гр": "g",
    "грамм": "g",
    "грамма": "g",
    "граммов": "g",
    "мл": "ml",
    "миллилитр": "ml",
    "миллилитра": "ml",
    "миллилитров": "ml",
    "шт": "piece",
    "шт.": "piece",
    "штука": "piece",
    "штуки": "piece",
    "штук": "piece",
    "порция": "serving",
    "порции": "serving",
    "порций": "serving",
}
_NUMBER = re.compile(r"[0-9]+(?:[,.][0-9]+)?\Z", re.ASCII)
_QUANTITY = re.compile(r"\s*([0-9]+(?:[,.][0-9]+)?)\s*([^\W\d_].*?)\s*\Z")
_MEASURED_AMOUNT = re.compile(
    r"(?P<quantity>[0-9]+(?:[,.][0-9]+)?)\s*"
    r"(?:(?:x|х|×)\s*(?P<multiplier>[0-9]+(?:[,.][0-9]+)?)\s*)?"
    r"(?P<unit>[^\W\d_]+)\s*(?:\(\s*[0-9]+(?:[,.][0-9]+)?\s*(?:г|мл)\s*\)|"
    r",\s*[0-9]+(?:[,.][0-9]+)?\s*(?:г|мл))\s*\Z",
    re.IGNORECASE,
)
_DATE = re.compile(r"Дата:\s*([0-9]{2}\.[0-9]{2}\.[0-9]{4})\Z", re.IGNORECASE)
_LONG_DATE = re.compile(
    r"(понедельник|вторник|среда|четверг|пятница|суббота|воскресенье),\s*"
    r"([а-яё]+)\s+([0-9]{1,2}),\s*([0-9]{4})\Z",
    re.IGNORECASE,
)
_MONTHS = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)
_MONTH_NAMES = set(_MONTHS) | {
    "январь",
    "февраль",
    "март",
    "апрель",
    "май",
    "июнь",
    "июль",
    "август",
    "сентябрь",
    "октябрь",
    "ноябрь",
    "декабрь",
}
_WEEKDAYS = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")
_REPORT_TITLE = "# Food Diary Report - Detailed Report"
_PERIOD = re.compile(
    r"Период:\s*([0-9]{2}\.[0-9]{2}\.[0-9]{4})\s*[-–—]\s*"
    r"([0-9]{2}\.[0-9]{2}\.[0-9]{4})\s*\Z",
    re.IGNORECASE,
)
_SEPARATOR = re.compile(r"#?[-–—=_*\s]{3,}\Z")
_TOTAL_LABEL = re.compile(
    r"^(?:(?:дневной|суточный|промежуточный)\s+)?"
    r"(?:итого|итог|всего|сумма)(?:$|[\s:,(.])"
)
_RESERVED_AMOUNT = re.compile(
    r"^(?:(?:дата|период|"
    r"понедельник|вторник|среда|четверг|пятница|суббота|воскресенье|"
    r"полдник|второй\s+завтрак)(?:$|[\s,:()])|"
    r"[0-9]{1,2}[.\-/][0-9]{1,2}[.\-/][0-9]{2,4}(?:$|\s)|"
    r"[0-9]{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|"
    r"августа|сентября|октября|ноября|декабря)\s+[0-9]{4}(?:$|[\s,])|#)"
)


class _FormatError(Exception):
    def __init__(self, code: str, row: int | None = None) -> None:
        self.code = code
        self.row = row


def _coordinates(section: str, row: int) -> dict[str, Any]:
    return {
        "section": section,
        "section_kind": "summary" if section == "period_summary" else "detail",
        "row": row,
    }


def _diagnostic(
    code: str, section: str, row: int, *, severity: str = "error", field: str | None = None
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "coordinates": _coordinates(section, row),
        "field": field,
    }


def _document() -> dict[str, Any]:
    return {
        "schema_version": "nutrition-import-v3",
        "source": {
            "provider": "fatsecret",
            "source": "diary_export",
            "source_version": None,
            "adapter_version": ADAPTER_VERSION,
            "source_format": "csv",
            "transport": "upload",
            "publication_rights": "owner_reported",
        },
        "completeness": "unknown",
        "rows": [],
        "original_totals": [],
        "original_summaries": [],
        "original_detail_cells": [],
        "diagnostics": [],
    }


def _fact(value: str, unit: str) -> dict[str, Any]:
    text = value.strip()
    if not text:
        return {"value": None, "unit": unit, "evidence": "absent"}
    if len(text) > 64 or _NUMBER.fullmatch(text) is None:
        return {"value": None, "unit": unit, "evidence": "unreadable"}
    try:
        number = Decimal(text.replace(",", "."))
    except InvalidOperation:
        return {"value": None, "unit": unit, "evidence": "unreadable"}
    parts = number.as_tuple()
    if not isinstance(parts.exponent, int) or parts.exponent < -8 or len(parts.digits) > 18:
        return {"value": None, "unit": unit, "evidence": "unreadable"}
    return {"value": format(number, "f"), "unit": unit, "evidence": "read"}


def _date(value: str, row: int) -> str:
    try:
        return datetime.strptime(value, "%d.%m.%Y").date().isoformat()
    except ValueError:
        raise _FormatError("invalid_date", row) from None


def _long_date(value: str, row: int) -> str:
    match = _LONG_DATE.fullmatch(value.strip())
    if match is None:
        raise _FormatError("invalid_date", row)
    weekday, month, day, year = match.groups()
    try:
        parsed = date(int(year), _MONTHS.index(month.casefold()) + 1, int(day))
    except ValueError:
        raise _FormatError("invalid_date", row) from None
    if _WEEKDAYS[parsed.weekday()] != weekday.casefold():
        raise _FormatError("invalid_date", row)
    return parsed.isoformat()


def _header(row: list[str], *expected: tuple[str, ...]) -> bool:
    def normalize(value: str) -> str:
        return re.sub(
            r"\s*\(\s*([^()]*)\s*\)\s*",
            lambda match: f"({match.group(1).strip()})",
            value.strip().casefold(),
        )

    return any(
        len(row) == len(profile) + 1
        and tuple(normalize(value) for value in row[1:])
        == tuple(normalize(value) for value in profile)
        for profile in expected
    )


def _summary(
    records: list[tuple[int, list[str]]],
    report: dict[str, Any],
    metadata: tuple[int, str, str] | None = None,
) -> None:
    header: tuple[int, list[str]] | None = None
    period: tuple[int, str] | None = None
    entries: list[tuple[int, list[str]]] = []
    for row_number, row in records:
        if len(row) == 1 and row[0].strip().casefold().startswith("период:"):
            if period is not None or len(row[0]) > 256:
                raise _FormatError("invalid_period", row_number)
            period = row_number, row[0]
        elif _header(row, SUMMARY_HEADERS, SUMMARY_HEADERS_SHORT):
            if header is not None or entries or len(row[0]) > 256:
                raise _FormatError("invalid_summary_header", row_number)
            header = row_number, row
        elif header is not None and len(row) == 5:
            entries.append((row_number, row))
        else:
            raise _FormatError("unknown_summary_structure", row_number)
    if header is None:
        raise _FormatError("missing_summary_header")

    summary: dict[str, Any] = {
        "header_coordinates": _coordinates("period_summary", header[0]),
        "header_label": header[1][0],
        "aggregation": {"kind": "unknown", "evidence": "unknown"},
        "rows": [],
    }
    if metadata is not None:
        row_number, start, end = metadata
        if period is not None or start > end:
            raise _FormatError("invalid_period", row_number)
        summary["period_start"], summary["period_end"] = start, end
        summary["period_coordinates"] = _coordinates("period_summary", row_number)
    if period is not None:
        row_number, label = period
        summary["period_label"] = label
        summary["period_coordinates"] = _coordinates("period_summary", row_number)
        match = _PERIOD.fullmatch(label.strip())
        if match is not None:
            start, end = (_date(value, row_number) for value in match.groups())
            if start > end:
                raise _FormatError("invalid_period", row_number)
            summary["period_start"], summary["period_end"] = start, end
        else:
            report["diagnostics"].append(
                _diagnostic("period_unrecognized", "period_summary", row_number, severity="warning")
            )
    for row_number, row in entries:
        if len(row[0]) > 256 or any(len(value) > 128 for value in row[1:]):
            raise _FormatError("field_too_long", row_number)
        label = row[0].strip().casefold()
        meal = MEALS.get(label)
        scope = "meal" if meal else "overall" if label in {"итого", "всего"} else "unknown"
        values = []
        for index, ((field, unit), value) in enumerate(
            zip(SUMMARY_FIELDS, row[1:], strict=True), 1
        ):
            fact = _fact(value, unit)
            if fact["evidence"] == "unreadable":
                report["diagnostics"].append(
                    _diagnostic(
                        "summary_value_unreadable",
                        "period_summary",
                        row_number,
                        severity="warning",
                        field=field,
                    )
                )
            values.append(
                {
                    "source_column": index + 1,
                    "source_header": header[1][index],
                    "source_value": value,
                    "nutrient_field": field,
                    "mapping_evidence": "source_label",
                    "fact": fact,
                }
            )
        summary["rows"].append(
            {
                "coordinates": _coordinates("period_summary", row_number),
                "source_label": row[0],
                "scope": scope,
                "meal_type": meal,
                "values": values,
            }
        )
    report["original_summaries"].append(summary)
    report["diagnostics"].append(
        _diagnostic("summary_aggregation_unknown", "period_summary", header[0], severity="warning")
    )


def _detail_facts(
    row_number: int, row: list[str], header: list[str], report: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    facts: dict[str, Any] = {}
    invalid: list[str] = []
    for index, ((field, unit), value) in enumerate(zip(DETAIL_FIELDS, row[1:], strict=True), 1):
        if len(value) > 128:
            raise _FormatError("field_too_long", row_number)
        fact = _fact(value, unit)
        if field is not None:
            facts[field] = fact
        if field is None or fact["evidence"] == "unreadable":
            report["original_detail_cells"].append(
                {
                    "coordinates": _coordinates("report_details", row_number),
                    "source_column": index + 1,
                    "source_header": header[index],
                    "source_value": value,
                    "nutrient_field": field,
                    "mapping_evidence": "source_label" if field else "unknown",
                    "fact": fact,
                }
            )
        if fact["evidence"] == "unreadable":
            invalid.append(field or "unmapped_nutrient")
    return facts, invalid


def _amount(label: str, row: int) -> tuple[str | None, str | None, str | None, str | None]:
    if len(label) > 256:
        raise _FormatError("field_too_long", row)
    measured = _MEASURED_AMOUNT.fullmatch(label.strip())
    if measured is not None and measured.group("unit").casefold() not in _MONTH_NAMES:
        source_unit = label.strip()[measured.end("quantity") :].strip()
        if len(source_unit) > 128:
            raise _FormatError("field_too_long", row)
        if measured.group("multiplier") is not None:
            return None, None, source_unit, "quantity_unrecognized"
        fact = _fact(measured.group("quantity"), "g")
        if fact["value"] is None or Decimal(fact["value"]) <= 0:
            return None, None, source_unit, "invalid_quantity"
        unit = UNITS.get(measured.group("unit").casefold())
        return fact["value"], unit, source_unit, None if unit else "unknown_unit"
    match = _QUANTITY.fullmatch(label)
    if match is None:
        return None, None, None, "quantity_unrecognized"
    value, unit = match.groups()
    if len(unit) > 128:
        raise _FormatError("field_too_long", row)
    fact = _fact(value, "g")
    if fact["value"] is None or Decimal(fact["value"]) <= 0:
        return None, None, unit, "invalid_quantity"
    canonical_unit = UNITS.get(unit.casefold())
    return fact["value"], canonical_unit, unit, None if canonical_unit else "unknown_unit"


def _compare_day_meals(
    day: dict[str, Any] | None, meals: list[dict[str, Any]], report: dict[str, Any]
) -> None:
    if (
        day is None
        or len(meals) != 4
        or {item["meal_type"] for item in meals}
        != {
            "breakfast",
            "lunch",
            "dinner",
            "snacks",
        }
    ):
        return
    for field, unit in DETAIL_FIELDS:
        if field is None:
            continue
        facts = [day["facts"].get(field), *(meal["facts"].get(field) for meal in meals)]
        if any(
            fact is None or fact["evidence"] != "read" or fact["unit"] != unit for fact in facts
        ):
            continue
        values = [Decimal(fact["value"]) for fact in facts]
        if values[0] != sum(values[1:], Decimal(0)):
            report["diagnostics"].append(
                _diagnostic(
                    "day_meal_totals_differ",
                    "report_details",
                    day["coordinates"]["row"],
                    severity="warning",
                    field=field,
                )
            )
            return


def _details(
    records: list[tuple[int, list[str]]],
    ends: dict[int, int],
    report: dict[str, Any],
    period_bounds: tuple[str, str] | None = None,
) -> None:
    if not records or not _header(records[0][1], DETAIL_HEADERS, DETAIL_HEADERS_SHORT):
        raise _FormatError("unknown_detail_header", records[0][0] if records else None)
    header = records[0][1]
    current_date: str | None = None
    meal: str | None = None
    context_ambiguous = False
    day_total: dict[str, Any] | None = None
    day_meals: list[dict[str, Any]] = []
    duplicate_day_total = False

    def finish_day() -> None:
        if not context_ambiguous and not duplicate_day_total:
            _compare_day_meals(day_total, day_meals, report)

    def validate_period(value: str, row: int) -> str:
        if period_bounds is not None:
            start, end = period_bounds
        elif report["original_summaries"]:
            summary = report["original_summaries"][0]
            start, end = summary.get("period_start"), summary.get("period_end")
        else:
            start, end = None, None
        if (start is not None and value < start) or (end is not None and value > end):
            raise _FormatError("date_outside_period", row)
        return value

    seen: set[tuple[Any, ...]] = set()
    index = 1
    while index < len(records):
        row_number, row = records[index]
        label = row[0].strip()
        key = label.casefold()
        if len(row) == 1 and key.startswith("дата:"):
            match = _DATE.fullmatch(label)
            if match is None:
                raise _FormatError("invalid_date", row_number)
            finish_day()
            current_date, meal = (
                validate_period(_date(match.group(1), row_number), row_number),
                None,
            )
            context_ambiguous = False
            day_total, day_meals, duplicate_day_total = None, [], False
        elif len(row) == 11 and _LONG_DATE.fullmatch(label):
            finish_day()
            current_date, meal = validate_period(_long_date(label, row_number), row_number), None
            context_ambiguous = False
            day_total, day_meals, duplicate_day_total = None, [], False
            if any(value.strip() for value in row[1:]):
                facts, invalid = _detail_facts(row_number, row, header, report)
                day_total = {
                    "scope": "day",
                    "coordinates": _coordinates("report_details", row_number),
                    "diary_date": current_date,
                    "facts": facts,
                }
                report["original_totals"].append(day_total)
                if invalid:
                    report["diagnostics"].append(
                        _diagnostic(
                            "total_value_unreadable",
                            "report_details",
                            row_number,
                            severity="warning",
                        )
                    )
        elif key in MEALS and len(row) in {1, 11}:
            if current_date is None:
                raise _FormatError("meal_without_date", row_number)
            meal = MEALS[key]
            if len(row) == 11 and any(value.strip() for value in row[1:]):
                facts, invalid = _detail_facts(row_number, row, header, report)
                meal_total = {
                    "scope": "meal",
                    "coordinates": _coordinates("report_details", row_number),
                    "diary_date": None if context_ambiguous else current_date,
                    "meal_type": meal,
                    "facts": facts,
                }
                report["original_totals"].append(meal_total)
                day_meals.append(meal_total)
                if invalid:
                    report["diagnostics"].append(
                        _diagnostic(
                            "total_value_unreadable",
                            "report_details",
                            row_number,
                            severity="warning",
                        )
                    )
        elif key in {"итого", "итого за день", "всего за день", "всего"} and len(row) in {1, 11}:
            if key == "всего" and index != len(records) - 1:
                raise _FormatError("unknown_total_scope", row_number)
            if len(row) == 11 and any(value.strip() for value in row[1:]):
                facts, invalid = _detail_facts(row_number, row, header, report)
                total = {
                    "scope": "day" if key in {"итого за день", "всего за день"} else "unknown",
                    "coordinates": _coordinates("report_details", row_number),
                    "diary_date": None if context_ambiguous else current_date,
                    "facts": facts,
                }
                report["original_totals"].append(total)
                if total["scope"] == "day":
                    if day_total is None:
                        day_total = total
                    else:
                        duplicate_day_total = True
                if invalid:
                    report["diagnostics"].append(
                        _diagnostic(
                            "total_value_unreadable",
                            "report_details",
                            row_number,
                            severity="warning",
                        )
                    )
            if key in {"итого за день", "всего за день", "всего"}:
                meal = None
        elif _TOTAL_LABEL.match(key):
            raise _FormatError("unknown_total_scope", row_number)
        elif _RESERVED_AMOUNT.match(key):
            raise _FormatError("unknown_detail_structure", row_number)
        elif len(row) == 11 and current_date and meal and index + 1 < len(records):
            amount_row, amount = records[index + 1]
            if (
                len(amount) != 1
                or amount_row != ends[row_number] + 1
                or not amount[0].strip()
                or amount[0].strip().casefold() in MEALS
                or _TOTAL_LABEL.match(amount[0].strip().casefold())
                or _RESERVED_AMOUNT.match(amount[0].strip().casefold())
            ):
                raise _FormatError("quantity_association_ambiguous", row_number)
            if not label or len(label) > 256:
                raise _FormatError("invalid_food_label", row_number)
            quantity, unit, source_unit, amount_error = _amount(amount[0], amount_row)
            facts, invalid = _detail_facts(row_number, row, header, report)
            diagnostics = [
                _diagnostic("nutrient_unreadable", "report_details", row_number, field=field)
                for field in invalid
            ]
            if context_ambiguous:
                diagnostics.append(
                    _diagnostic("source_context_ambiguous", "report_details", row_number)
                )
            if amount_error:
                diagnostics.append(
                    _diagnostic(amount_error, "report_details", amount_row, field="quantity")
                )
            if row[3].strip():
                diagnostics.append(
                    _diagnostic(
                        "saturated_fat_mapping_unconfirmed",
                        "report_details",
                        row_number,
                        severity="warning",
                    )
                )
            if row[10].strip():
                diagnostics.append(
                    _diagnostic(
                        "potassium_not_in_catalog",
                        "report_details",
                        row_number,
                        severity="warning",
                    )
                )
            signature = (current_date, meal, label, tuple(row[1:]), amount[0])
            if signature in seen:
                diagnostics.append(
                    _diagnostic(
                        "possible_duplicate", "report_details", row_number, severity="warning"
                    )
                )
            seen.add(signature)
            report["rows"].append(
                {
                    "coordinates": _coordinates("report_details", row_number),
                    "quantity_coordinates": [_coordinates("report_details", amount_row)],
                    "diary_date": None if context_ambiguous else current_date,
                    "meal_type": meal,
                    "food": {"name": label, "kind": "unknown"},
                    "quantity": quantity,
                    "amount_unit": unit,
                    "source_unit": source_unit,
                    "serving_label": amount[0],
                    "nutrition": {"basis": None, "facts": {}},
                    "diagnostics": diagnostics,
                }
            )
            report["original_totals"].append(
                {
                    "scope": "unknown",
                    "coordinates": _coordinates("report_details", row_number),
                    "diary_date": None if context_ambiguous else current_date,
                    "meal_type": meal,
                    "facts": facts,
                }
            )
            measured_amount = _MEASURED_AMOUNT.fullmatch(amount[0].strip())
            known_measure_shape = (
                measured_amount is not None
                and measured_amount.group("unit").casefold() not in _MONTH_NAMES
            )
            if not known_measure_shape and (
                amount_error == "quantity_unrecognized"
                or (
                    amount_error == "unknown_unit"
                    and source_unit
                    and re.search(r"[0-9]", source_unit)
                )
            ):
                context_ambiguous = True
            index += 1
        else:
            raise _FormatError("unknown_detail_structure", row_number)
        index += 1
    finish_day()
    if report["original_totals"]:
        report["diagnostics"].append(
            _diagnostic(
                "totals_not_comparable", "report_details", records[0][0], severity="warning"
            )
        )


def parse(content: bytes) -> dict[str, Any]:
    report = _document()
    section = "period_summary"
    try:
        validate_csv_upload(content, filename="source.csv", content_type="text/csv", delimiter=",")
        reader = csv.reader(io.StringIO(content.decode("utf-8-sig"), newline=""), strict=True)
        records = []
        ends = {}
        while True:
            row_number = reader.line_num + 1
            try:
                row = next(reader)
            except StopIteration:
                break
            if not row or not any(value.strip() for value in row):
                continue
            if len(row) == 1 and _SEPARATOR.fullmatch(row[0].strip()):
                continue
            records.append((row_number, row))
            ends[row_number] = reader.line_num
        markers = [
            index
            for index, (_, row) in enumerate(records)
            if row in (["# Period Summary"], ["# Report Details"])
        ]
        if (
            len(markers) == 2
            and records[markers[0]][1] == ["# Period Summary"]
            and records[markers[1]][1] == ["# Report Details"]
        ):
            metadata = None
            prefix = records[: markers[0]]
            if prefix:
                if len(prefix) != 1 or len(prefix[0][1]) != 3 or prefix[0][1][0] != _REPORT_TITLE:
                    raise _FormatError("unknown_sections")
                row_number, title = prefix[0]
                metadata = (
                    row_number,
                    _long_date(title[1], row_number),
                    _long_date(title[2], row_number),
                )
            _summary(records[markers[0] + 1 : markers[1]], report, metadata)
            section = "report_details"
            _details(records[markers[1] + 1 :], ends, report)
        elif len(markers) == 1 and records[markers[0]][1] == ["# Report Details"]:
            prefix = records[: markers[0]]
            if len(prefix) != 1 or len(prefix[0][1]) != 2 or prefix[0][1][0] != _REPORT_TITLE:
                raise _FormatError("unknown_sections")
            row_number, title = prefix[0]
            day = _long_date(title[1], row_number)
            section = "report_details"
            _details(records[markers[0] + 1 :], ends, report, (day, day))
        else:
            raise _FormatError("unknown_sections")
    except NutritionImportValidationError as exc:
        report = _document()
        report["diagnostics"].append({"code": exc.code, "severity": "error"})
    except UnicodeDecodeError, csv.Error:
        report = _document()
        report["diagnostics"].append({"code": "invalid_csv", "severity": "error"})
    except _FormatError as exc:
        report = _document()
        diagnostic: dict[str, Any] = {"code": exc.code, "severity": "error"}
        if exc.row is not None:
            diagnostic["coordinates"] = _coordinates(section, exc.row)
        report["diagnostics"].append(diagnostic)
    return report
