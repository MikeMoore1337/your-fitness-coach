"""Conservative parser for the documented Russian FatSecret CSV profile."""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime
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
_DATE = re.compile(r"Дата:\s*([0-9]{2}\.[0-9]{2}\.[0-9]{4})\Z", re.IGNORECASE)
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


def _header(row: list[str], expected: tuple[str, ...]) -> bool:
    return (
        len(row) == len(expected) + 1
        and tuple(value.strip().casefold() for value in row[1:]) == expected
    )


def _summary(records: list[tuple[int, list[str]]], report: dict[str, Any]) -> None:
    header: tuple[int, list[str]] | None = None
    period: tuple[int, str] | None = None
    entries: list[tuple[int, list[str]]] = []
    for row_number, row in records:
        if len(row) == 1 and row[0].strip().casefold().startswith("период:"):
            if period is not None or len(row[0]) > 256:
                raise _FormatError("invalid_period", row_number)
            period = row_number, row[0]
        elif _header(row, SUMMARY_HEADERS):
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


def _details(
    records: list[tuple[int, list[str]]], ends: dict[int, int], report: dict[str, Any]
) -> None:
    if not records or not _header(records[0][1], DETAIL_HEADERS):
        raise _FormatError("unknown_detail_header", records[0][0] if records else None)
    header = records[0][1]
    current_date: str | None = None
    meal: str | None = None
    context_ambiguous = False
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
            current_date, meal = _date(match.group(1), row_number), None
            context_ambiguous = False
        elif key in MEALS and len(row) in {1, 11}:
            if current_date is None:
                raise _FormatError("meal_without_date", row_number)
            meal = MEALS[key]
            if len(row) == 11 and any(value.strip() for value in row[1:]):
                facts, invalid = _detail_facts(row_number, row, header, report)
                report["original_totals"].append(
                    {
                        "scope": "meal",
                        "coordinates": _coordinates("report_details", row_number),
                        "diary_date": None if context_ambiguous else current_date,
                        "meal_type": meal,
                        "facts": facts,
                    }
                )
                if invalid:
                    report["diagnostics"].append(
                        _diagnostic(
                            "total_value_unreadable",
                            "report_details",
                            row_number,
                            severity="warning",
                        )
                    )
        elif key in {"итого", "итого за день", "всего за день"} and len(row) in {1, 11}:
            if len(row) == 11 and any(value.strip() for value in row[1:]):
                facts, invalid = _detail_facts(row_number, row, header, report)
                report["original_totals"].append(
                    {
                        "scope": "day" if key != "итого" else "unknown",
                        "coordinates": _coordinates("report_details", row_number),
                        "diary_date": None if context_ambiguous else current_date,
                        "facts": facts,
                    }
                )
                if invalid:
                    report["diagnostics"].append(
                        _diagnostic(
                            "total_value_unreadable",
                            "report_details",
                            row_number,
                            severity="warning",
                        )
                    )
            if key != "итого":
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
            if amount_error == "quantity_unrecognized" or (
                amount_error == "unknown_unit" and source_unit and re.search(r"[0-9]", source_unit)
            ):
                context_ambiguous = True
            index += 1
        else:
            raise _FormatError("unknown_detail_structure", row_number)
        index += 1
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
            len(markers) != 2
            or markers[0] != 0
            or records[markers[0]][1] != ["# Period Summary"]
            or records[markers[1]][1] != ["# Report Details"]
        ):
            raise _FormatError("unknown_sections")
        _summary(records[1 : markers[1]], report)
        section = "report_details"
        _details(records[markers[1] + 1 :], ends, report)
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
