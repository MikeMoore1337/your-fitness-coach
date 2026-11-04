"""Bounded CSV reading and shared normalization for provider adapters."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import replace
from datetime import datetime
from time import monotonic

from fitminiapp_api.services.workout_history_import_parser import (
    CSV_COLUMNS_V2,
    MAX_BYTES,
    MAX_CELL_CHARS,
    MAX_PARSE_SECONDS,
    MAX_ROWS,
    ImportIssue,
    ImportRow,
    WorkoutHistoryImportError,
    _parse_row,
)

_MONTHS = {
    name: number
    for number, name in enumerate(
        ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
        1,
    )
}


def deadline() -> float:
    return monotonic() + MAX_PARSE_SECONDS


def check_deadline(limit: float) -> None:
    if monotonic() > limit:
        raise WorkoutHistoryImportError("parse_timeout", "Файл обрабатывался слишком долго")


def read_table(
    content: bytes, delimiter: str, limit: float
) -> tuple[list[str], list[tuple[int, dict[str, str]]]]:
    if not content or len(content) > MAX_BYTES:
        raise WorkoutHistoryImportError("file_size", "Файл пуст или превышает допустимый размер")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise WorkoutHistoryImportError("encoding", "Используйте CSV в кодировке UTF-8") from exc
    if any((ord(char) < 32 and char not in "\r\n\t") or ord(char) == 127 for char in text):
        raise WorkoutHistoryImportError("control_character", "Файл содержит управляющие символы")
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
    try:
        header = next(reader, None)
        if not header or len(header) > 64 or len(set(header)) != len(header):
            raise WorkoutHistoryImportError("columns", "Проверьте колонки файла")
        rows: list[tuple[int, dict[str, str]]] = []
        for values in reader:
            check_deadline(limit)
            if len(rows) >= MAX_ROWS:
                raise WorkoutHistoryImportError("row_limit", "Файл превышает лимит строк")
            if len(values) != len(header):
                raise WorkoutHistoryImportError(
                    "row_width", f"Проверьте число полей в строке {reader.line_num}"
                )
            if any(len(value) > MAX_CELL_CHARS for value in values):
                raise WorkoutHistoryImportError(
                    "cell_limit", f"Проверьте значение в строке {reader.line_num}"
                )
            rows.append(
                (reader.line_num, dict(zip(header, (v.strip() for v in values), strict=True)))
            )
    except csv.Error as exc:
        raise WorkoutHistoryImportError("malformed_csv", "Не удалось прочитать CSV-файл") from exc
    if not rows:
        raise WorkoutHistoryImportError("empty", "В файле нет подходов")
    return header, rows


def check_columns(header: list[str], required: set[str], allowed: set[str]) -> None:
    if not required <= set(header) or not set(header) <= allowed:
        raise WorkoutHistoryImportError(
            "columns", "Колонки файла не соответствуют выбранному источнику"
        )


def ref(*parts: str) -> str:
    value = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def timestamp(value: str, formats: tuple[str, ...]) -> datetime | None:
    if not value:
        return None
    try:
        if "T" in value or " " in value:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        pass
    match = re.fullmatch(
        r"(\d{1,2}) ([A-Za-z]{3}) (\d{4}), (\d{1,2}):(\d{2})(?:\s*(AM|PM))?",
        value,
        flags=re.IGNORECASE,
    )
    if match:
        day, month, year, hour, minute, meridiem = match.groups()
        try:
            hour_number = int(hour)
            if meridiem:
                if not 1 <= hour_number <= 12:
                    return None
                hour_number = hour_number % 12 + (12 if meridiem.upper() == "PM" else 0)
            return datetime(int(year), _MONTHS[month.title()], int(day), hour_number, int(minute))
        except KeyError, ValueError:
            return None
    match = re.fullmatch(
        r"([A-Za-z]{3}) (\d{1,2}), (\d{4}), (\d{1,2}):(\d{2})\s*(AM|PM)",
        value,
        flags=re.IGNORECASE,
    )
    if match:
        month, day, year, hour, minute, meridiem = match.groups()
        try:
            hour_number = int(hour)
            if not 1 <= hour_number <= 12:
                return None
            hour_number = hour_number % 12 + (12 if meridiem.upper() == "PM" else 0)
            return datetime(int(year), _MONTHS[month.title()], int(day), hour_number, int(minute))
        except KeyError, ValueError:
            return None
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def unit(value: str) -> str:
    return {"kg": "kg", "kgs": "kg", "lb": "lb", "lbs": "lb"}.get(value.casefold(), value)


def row(
    line: int,
    fields: dict[str, str],
    source: dict[str, str],
    issues: list[ImportIssue],
    *,
    completion_unknown: bool = False,
) -> ImportRow:
    normalized = dict.fromkeys(CSV_COLUMNS_V2, "") | source
    parsed = _parse_row(line, normalized, "3", completion_unknown=completion_unknown)
    return replace(parsed, issues=parsed.issues + tuple(issues), provider_fields=fields)


def unsupported(
    fields: dict[str, str], names: tuple[str, ...], *, zero_is_empty: bool = False
) -> list[ImportIssue]:
    return [
        ImportIssue(
            "unsupported_field",
            name,
            "Показатель из исходного файла пока нельзя перенести без потери данных",
        )
        for name in names
        if fields.get(name, "") and (not zero_is_empty or fields[name] not in {"0", "0.0", "0.00"})
    ]
