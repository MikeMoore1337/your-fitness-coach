"""Conservative coordinate-based FatSecret detailed-report adapter."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from functools import partial
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
_HEADER_FIELDS = {
    label: index
    for profile in (_EN_HEADERS, csv_adapter.DETAIL_HEADERS, csv_adapter.DETAIL_HEADERS_SHORT)
    for index, label in enumerate(profile)
}
_RU_DETAIL_LABELS = (
    "кал",
    "жир",
    "н/жир",
    "углев",
    "клетч",
    "сахар",
    "белк",
    "натри",
    "холес",
    "калий",
)
_RU_SUMMARY_LABELS = ("кал", "жир", "углев", "белк")
_DETAIL_UNITS = ("(ккал)", "(г)", "(г)", "(г)", "(г)", "(г)", "(г)", "(мг)", "(мг)", "(мг)")
_SUMMARY_UNITS = ("(ккал)", "(г)", "(г)", "(г)")


class _PdfLayoutError(csv_adapter._FormatError):
    def __init__(self, code: str, page: int, row: int, section: str) -> None:
        super().__init__(code, row)
        self.page = page
        self.section = section


def _split_report_cells(group: list[PdfLine], anchors: list[float]) -> tuple[str, list[str]]:
    cells = [""] * len(anchors)
    labels: list[str] = []
    baseline_counts = Counter(
        round(part.bbox[1], 1)
        for part in group
        if part.bbox[0] >= anchors[0] + 25
        and re.fullmatch(r"[0-9]+(?:[,.][0-9]+)?", part.text.strip())
    )
    numeric_baseline = baseline_counts.most_common(1)[0][0] if baseline_counts else None
    for part in group:
        left, right = part.text, ""
        center = (part.bbox[0] + part.bbox[2]) / 2
        if part.bbox[0] < anchors[0] - 18 and part.bbox[2] > anchors[0] - 13:
            first = next(
                (
                    i
                    for i, char in enumerate(part.chars)
                    if numeric_baseline is not None
                    and abs(char[3] - numeric_baseline) <= 0.5
                    and char[0] in "0123456789,."
                    and abs((char[1] + char[2]) / 2 - anchors[0]) <= 18
                ),
                None,
            )
            previous = next(
                (i for i in range((first or 0) - 1, -1, -1) if part.chars[i][0].strip()), None
            )
            if (
                first is None
                or previous is None
                or (
                    part.chars[first][1] - part.chars[previous][2] < 4
                    and abs(part.chars[first][3] - part.chars[previous][3]) < 1
                )
            ):
                raise csv_adapter._FormatError("pdf_column_ambiguous")
            left = "".join(char[0] for char in part.chars[:first]).strip()
            right = "".join(char[0] for char in part.chars[first:]).strip()
            center = (part.chars[first][1] + part.chars[-1][2]) / 2
        elif part.bbox[0] >= anchors[0] - 18:
            left, right = "", part.text.strip()
        if left.strip():
            labels.append(left.strip())
        if right:
            possible = [i for i, anchor in enumerate(anchors) if abs(anchor - center) <= 18]
            if (
                len(possible) != 1
                or cells[possible[0]]
                or not re.fullmatch(r"[0-9]+(?:[,.][0-9]+)?", right)
            ):
                raise csv_adapter._FormatError("pdf_column_ambiguous")
            cells[possible[0]] = right
    if len(labels) > 1:
        raise csv_adapter._FormatError("pdf_row_ambiguous")
    return (labels[0] if labels else ""), cells


def _parse_ru_report(lines: list[PdfLine]) -> dict[str, Any]:
    report = csv_adapter._document()
    report["source"].update(adapter_version=ADAPTER_VERSION, source_format="pdf")
    groups = _groups(lines)
    pages: dict[int, int] = {}
    records: list[tuple[int, list[str]]] = []
    summary: list[tuple[int, list[str]]] = []
    summary_header: list[float] | None = None
    columns: list[float] | None = None
    pending_units: str | None = None
    active_date: str | None = None
    pending_date: tuple[str, int] | None = None
    current_page = 0
    meal_index: int | None = None
    meal_indent: float | None = None
    food: tuple[str, list[str], int] | None = None
    next_row = 1
    in_summary = False
    repeated: dict[tuple[str, int, int], set[int]] = {}
    for line in lines:
        if line.page_height and line.bbox[3] > line.page_height - 25:
            repeat_key = (line.text, round(line.bbox[0]), round(line.bbox[3]))
            repeated.setdefault(repeat_key, set()).add(line.page)
    for group_id, group in enumerate(groups, 1):
        first = group[0]
        error = partial(
            _PdfLayoutError,
            page=first.page,
            row=group_id,
            section="period_summary" if in_summary else "report_details",
        )

        text = " ".join(item.text.strip() for item in group)
        key = text.casefold().strip()
        if first.page != current_page:
            current_page = first.page
            columns = None
            pending_units = None
        if all(
            item.page_height
            and item.bbox[3] > item.page_height - 25
            and len(repeated.get((item.text, round(item.bbox[0]), round(item.bbox[3])), set())) > 1
            for item in group
        ):
            continue
        if re.fullmatch(r"(?:page|страница)\s+\d+(?:\s+(?:of|из)\s+\d+)?", key):
            continue
        if key == "period summary":
            in_summary = True
            continue
        values = tuple(item.text.strip().casefold() for item in group)
        labels = values[-10:]
        if len(labels) == 10 and labels == _RU_DETAIL_LABELS:
            columns = [(item.bbox[0] + item.bbox[2]) / 2 for item in group[-10:]]
            pending_units = "detail"
            in_summary = False
            continue
        if in_summary and len(values) >= 5 and values[-4:] == _RU_SUMMARY_LABELS:
            summary_header = [(item.bbox[0] + item.bbox[2]) / 2 for item in group[-4:]]
            summary.append((next_row, [group[0].text, *csv_adapter.SUMMARY_HEADERS_SHORT]))
            pages[next_row] = first.page
            next_row += 1
            pending_units = "summary"
            continue
        if pending_units:
            expected = _DETAIL_UNITS if pending_units == "detail" else _SUMMARY_UNITS
            if values != expected:
                raise error("pdf_unit_header_unknown")
            pending_units = None
            if columns is not None and not records:
                records.append((next_row, ["Метка", *csv_adapter.DETAIL_HEADERS_SHORT]))
                pages[next_row] = first.page
                next_row += 1
            if pending_date is not None:
                date_text, date_page = pending_date
                if date_text != active_date:
                    if food is not None:
                        raise error("quantity_association_ambiguous")
                    records.append(
                        (
                            next_row,
                            ["Дата: " + datetime.fromisoformat(date_text).strftime("%d.%m.%Y")],
                        )
                    )
                    pages[next_row] = date_page
                    next_row += 1
                    active_date, meal_index, meal_indent = date_text, None, None
                pending_date = None
            continue
        try:
            day = _date(text)
        except csv_adapter._FormatError as exc:
            raise error(exc.code) from None
        if day is not None:
            if pending_date is not None:
                raise error("pdf_date_ambiguous")
            pending_date = (day, first.page)
            continue
        if in_summary:
            if summary_header is None:
                raise error("unknown_summary_structure")
            try:
                label, values4 = _split_report_cells(group, summary_header)
            except csv_adapter._FormatError as exc:
                raise error(exc.code) from None
            if not label:
                raise error("unknown_summary_structure")
            summary.append((next_row, [label, *values4]))
            pages[next_row] = first.page
            next_row += 1
            continue
        if columns is None or pending_date is not None or not records:
            raise error("unknown_detail_header")
        try:
            label, cells = _split_report_cells(group, columns)
        except csv_adapter._FormatError as exc:
            raise error(exc.code) from None
        lowered = label.casefold()
        if lowered in csv_adapter.MEALS and not any(cells):
            if food is not None:
                raise error("quantity_association_ambiguous")
            records.append((next_row, [label]))
            pages[next_row] = first.page
            next_row += 1
            meal_index = len(records) - 1
            meal_indent = first.bbox[0]
        elif lowered in {"итого", "всего"} and any(cells):
            if food is not None:
                raise error("quantity_association_ambiguous")
            if meal_indent is None or first.bbox[0] < meal_indent + 1:
                raise error("pdf_total_ambiguous")
            if meal_index is not None:
                records[meal_index][1].extend(cells)
                pages[records[meal_index][0]] = first.page
                meal_index = None
            else:
                records.append((next_row, ["Итого за день", *cells]))
                pages[next_row] = first.page
                next_row += 1
        elif label and any(cells):
            if food is not None or meal_index is None:
                raise error("pdf_row_ambiguous")
            food = (label, cells, first.page)
        elif label and not any(cells) and food is not None and first.bbox[3] - first.bbox[1] <= 8.5:
            name, facts, food_page = food
            records.append((next_row, [name, *facts]))
            pages[next_row] = food_page
            next_row += 1
            records.append((next_row, [label]))
            pages[next_row] = first.page
            next_row += 1
            food = None
        else:
            raise error("pdf_row_ambiguous")
    if pending_units or pending_date or food is not None or not records:
        raise csv_adapter._FormatError("pdf_incomplete")
    if summary:
        csv_adapter._summary(summary, report)
    csv_adapter._details(records, {row: row for row, _ in records}, report)
    _compare_days(report)
    _attach_pages(report, pages)
    return report


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


def _compare_days(report: dict[str, Any]) -> None:
    if any(
        item["code"] in {"source_context_ambiguous", "quantity_unrecognized"}
        for row in report["rows"]
        for item in row["diagnostics"]
    ):
        return
    totals = report["original_totals"]
    cells = {
        cell["coordinates"]["row"]: cell["fact"]
        for cell in report["original_detail_cells"]
        if cell["source_column"] == 4
    }
    diagnostics: list[dict[str, Any]] = []
    days: dict[str, list[dict[str, Any]]] = {}
    for item in totals:
        if item.get("diary_date"):
            days.setdefault(item["diary_date"], []).append(item)
    for same_day in days.values():
        day_totals = [item for item in same_day if item["scope"] == "day"]
        if len(day_totals) != 1:
            continue
        entries = [
            item for item in same_day if item["scope"] == "unknown" and item.get("meal_type")
        ]
        csv_adapter._compare_source_values(
            day_totals[0], entries, cells, "day_source_values_differ", diagnostics
        )
    existing = {
        (item["code"], item.get("field"), item.get("coordinates", {}).get("row"))
        for item in report["diagnostics"]
    }
    for item in diagnostics:
        key = (item["code"], item.get("field"), item["coordinates"]["row"])
        if key not in existing:
            if len(report["diagnostics"]) >= csv_adapter.MAX_ADAPTER_LIST:
                raise csv_adapter._FormatError("adapter_diagnostics_limit")
            report["diagnostics"].append(item)
            existing.add(key)


def parse(source: bytes) -> dict[str, Any]:
    report = csv_adapter._document()
    report["source"].update(adapter_version=ADAPTER_VERSION, source_format="pdf")
    try:
        lines = extract_pdf_lines(source)
        groups = _groups(lines)
        if any(
            tuple(item.text.strip().casefold() for item in group) == _RU_DETAIL_LABELS
            for group in groups
        ):
            return _parse_ru_report(lines)
        records: list[tuple[int, list[str]]] = []
        pages: dict[int, int] = {}
        positions: list[float] | None = None
        header_page: int | None = None
        column_fields: list[int] = []
        row_headers: dict[int, dict[int, str]] = {}
        row_fields: dict[int, list[int]] = {}
        current_headers: dict[int, str] = {}
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
            mapped_header = [_HEADER_FIELDS.get(value) for value in header]
            if len(mapped_header) == 10 and set(mapped_header) == set(range(10)):
                positions = [part.bbox[0] for part in group[-10:]]
                header_page = group[0].page
                column_fields = [int(index) for index in mapped_header if index is not None]
                current_headers = dict(zip(column_fields, values[-10:], strict=True))
                if not records:
                    records.append((1, ["Метка", *csv_adapter.DETAIL_HEADERS]))
                    pages[1] = group[0].page
                continue
            if positions is None or header_page != group[0].page:
                raise csv_adapter._FormatError("unknown_detail_header")
            if re.fullmatch(r"(?:page|страница)\s+\d+(?:\s*/\s*\d+)?", key):
                continue
            record_id = len(records) + 1
            page = group[0].page
            row_headers[record_id] = current_headers
            row_fields[record_id] = column_fields
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
                    candidates = [i for i, pos in enumerate(positions) if abs(pos - x) <= 18]
                    if len(candidates) != 1:
                        raise csv_adapter._FormatError("pdf_column_ambiguous", record_id)
                    index = candidates[0]
                    field = column_fields[index]
                    if cells[field]:
                        raise csv_adapter._FormatError("pdf_column_ambiguous", record_id)
                    cells[field] = part.text.strip()
            label = " ".join(left).strip()
            total = re.fullmatch(r"(?:total|итого|всего)\s+(.+)", label, re.I)
            if total and total.group(1).casefold() in {*_MEALS, *csv_adapter.MEALS}:
                continuation = None
                if meal_record is None or len(records[meal_record][1]) != 1:
                    raise csv_adapter._FormatError("unknown_total_scope", record_id)
                records[meal_record][1].extend(cells)
                pages[records[meal_record][0]] = page
                row_headers[records[meal_record][0]] = current_headers
                row_fields[records[meal_record][0]] = column_fields
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
        _compare_days(report)
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
        for cell in report["original_detail_cells"]:
            row = cell["coordinates"]["row"]
            field = cell["source_column"] - 2
            cell["source_header"] = row_headers[row][field]
            cell["source_column"] = row_fields[row].index(field) + 2
    except (NutritionImportValidationError, csv_adapter._FormatError) as exc:
        report = csv_adapter._document()
        report["source"].update(adapter_version=ADAPTER_VERSION, source_format="pdf")
        diagnostic: dict[str, Any] = {"code": exc.code, "severity": "error"}
        if isinstance(exc, _PdfLayoutError):
            diagnostic["coordinates"] = {
                "section": exc.section,
                "section_kind": "summary" if exc.section == "period_summary" else "detail",
                "page": exc.page,
                "row": exc.row,
            }
        report["diagnostics"].append(diagnostic)
    return report
