"""Conservative coordinate-based FatSecret detailed-report adapter."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from fitminiapp_api.services import nutrition_import_fatsecret_csv as csv_adapter
from fitminiapp_api.services.nutrition_import_pdf_text import PdfLine, extract_pdf_lines
from fitminiapp_api.services.nutrition_import_validation import NutritionImportValidationError

ADAPTER_VERSION = "fatsecret-pdf-v1"
_EN_HEADERS = (
    "calories",
    "fat",
    "sat. fat",
    "carbs",
    "fiber",
    "sugar",
    "protein",
    "sodium",
    "chol",
    "potassium",
)
_MEALS = {
    "breakfast": "Завтрак",
    "lunch": "Обед",
    "dinner": "Ужин",
    "snacks/other": "Перекус",
    "snacks": "Перекус",
}


def _groups(lines: list[PdfLine]) -> list[list[PdfLine]]:
    groups: list[list[PdfLine]] = []
    for line in sorted(lines, key=lambda line: (line.page, -line.bbox[3], line.bbox[0])):
        if (
            not groups
            or groups[-1][0].page != line.page
            or abs(groups[-1][0].bbox[3] - line.bbox[3]) > 3
        ):
            groups.append([line])
        else:
            groups[-1].append(line)
    return [sorted(group, key=lambda item: item.bbox[0]) for group in groups]


def _date(text: str) -> str | None:
    match = re.fullmatch(r"(?:Дата|Date):\s*(\d{2}\.\d{2}\.\d{4})", text, re.I)
    if match:
        return csv_adapter._date(match.group(1), 0)
    if csv_adapter._LONG_DATE.fullmatch(text):
        return csv_adapter._long_date(text, 0)
    try:
        value = datetime.strptime(text, "%A, %B %d, %Y").date()
        if value.strftime("%A").casefold() != text.split(",", 1)[0].casefold():
            raise csv_adapter._FormatError("invalid_date")
        return value.isoformat()
    except ValueError:
        return None


def _attach_pages(value: object, pages: dict[int, int]) -> None:
    if isinstance(value, dict):
        if value.get("section_kind") in {"detail", "summary"} and isinstance(value.get("row"), int):
            value["page"] = pages[value["row"]]
        for child in value.values():
            _attach_pages(child, pages)
    elif isinstance(value, list):
        for child in value:
            _attach_pages(child, pages)


def parse(source: bytes) -> dict[str, Any]:
    report = csv_adapter._document()
    report["source"].update(adapter_version=ADAPTER_VERSION, source_format="pdf")
    try:
        groups = _groups(extract_pdf_lines(source))
        records: list[tuple[int, list[str]]] = []
        pages: dict[int, int] = {}
        positions: list[float] | None = None
        section = False
        meal_record: int | None = None
        current_date: str | None = None
        current_date_page: int | None = None
        continuation: tuple[int, int, float, float] | None = None
        for group in groups:
            text = " ".join(part.text for part in group).strip()
            key = text.casefold()
            if key in {"report details", "# report details", "детали отчёта", "детали отчета"}:
                section = True
                continue
            if not section:
                continue
            values = [part.text.strip() for part in group]
            header = tuple(value.casefold() for value in values[-10:])
            if header in {
                _EN_HEADERS,
                csv_adapter.DETAIL_HEADERS,
                csv_adapter.DETAIL_HEADERS_SHORT,
            }:
                positions = [part.bbox[0] for part in group[-10:]]
                if not records:
                    records.append((1, ["Метка", *csv_adapter.DETAIL_HEADERS]))
                    pages[1] = group[0].page
                continue
            if positions is None:
                raise csv_adapter._FormatError("unknown_detail_header")
            if re.fullmatch(r"(?:page|страница)\s+\d+(?:\s*/\s*\d+)?", key):
                continue
            record_id = len(records) + 1
            page = group[0].page
            day = _date(text)
            if day is not None:
                continuation = None
                if day == current_date and page == current_date_page:
                    raise csv_adapter._FormatError("pdf_date_ambiguous", record_id)
                if day != current_date:
                    current_date = day
                    records.append(
                        (record_id, ["Дата: " + datetime.fromisoformat(day).strftime("%d.%m.%Y")])
                    )
                    pages[record_id] = page
                    meal_record = None
                current_date_page = page
                continue
            meal = _MEALS.get(key, text if key in csv_adapter.MEALS else None)
            if meal:
                records.append((record_id, [meal]))
                pages[record_id] = page
                meal_record = len(records) - 1
                continuation = None
                continue
            # shortcut: only hyphenated wraps are joined; upgrade after validating report geometry.
            if continuation and len(group) == 1:
                index, previous_page, previous_x, previous_y = continuation
                item = group[0]
                if (
                    page == previous_page
                    and abs(item.bbox[0] - previous_x) < 3
                    and 0 < previous_y - item.bbox[3] <= 18
                    and records[index][1][0].endswith("-")
                ):
                    records[index][1][0] += " " + item.text.strip()
                    continuation = (index, page, previous_x, item.bbox[3])
                    continue
            cells = [""] * 10
            left: list[str] = []
            for part in group:
                x = part.bbox[0]
                if x < positions[0] - 5:
                    left.append(part.text.strip())
                else:
                    index = min(range(10), key=lambda i: abs(positions[i] - x))
                    if abs(positions[index] - x) > 18 or cells[index]:
                        raise csv_adapter._FormatError("pdf_column_ambiguous", record_id)
                    cells[index] = part.text.strip()
            label = " ".join(left).strip()
            total = re.fullmatch(r"(?:total|итого|всего)\s+(.+)", label, re.I)
            if total and total.group(1).casefold() in {*_MEALS, *csv_adapter.MEALS}:
                continuation = None
                if meal_record is None or len(records[meal_record][1]) != 1:
                    raise csv_adapter._FormatError("unknown_total_scope", record_id)
                records[meal_record][1].extend(cells)
                pages[records[meal_record][0]] = page
                continue
            if label.casefold() in {"total", "итого", "всего"}:
                continuation = None
                records.append((record_id, ["Итого за день", *cells]))
                pages[record_id] = page
                continue
            if len(left) != 2 or not any(cells):
                raise csv_adapter._FormatError("pdf_row_ambiguous", record_id)
            amount, food = left
            records.append((record_id, [food, *cells]))
            pages[record_id] = page
            continuation = (len(records) - 1, page, group[1].bbox[0], group[1].bbox[3])
            records.append((record_id + 1, [amount]))
            pages[record_id + 1] = page
        if not records:
            raise csv_adapter._FormatError("pdf_no_details")
        csv_adapter._details(records, {row: row for row, _ in records}, report)
        units = {
            "g": "g",
            "grams": "g",
            "ml": "ml",
            "piece": "piece",
            "pieces": "piece",
            "serving": "serving",
            "servings": "serving",
        }
        for row in report["rows"]:
            unit = units.get((row.get("source_unit") or "").casefold())
            if row["quantity"] is not None and unit:
                row["amount_unit"] = unit
                row["diagnostics"] = [
                    item for item in row["diagnostics"] if item["code"] != "unknown_unit"
                ]
        _attach_pages(report, pages)
    except (NutritionImportValidationError, csv_adapter._FormatError) as exc:
        report = csv_adapter._document()
        report["source"].update(adapter_version=ADAPTER_VERSION, source_format="pdf")
        report["diagnostics"].append({"code": exc.code, "severity": "error"})
    return report
