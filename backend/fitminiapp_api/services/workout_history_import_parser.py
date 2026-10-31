"""Bounded parser for the neutral workout-history CSV v1 format.

This module does not persist data or resolve catalog exercises.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from time import monotonic
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MAX_BYTES = 1_000_000
MAX_ROWS = 5_000
MAX_CELL_CHARS = 512
MAX_PARSE_SECONDS = 5.0
MAX_DB_WEIGHT = Decimal("99999999.99")
POUND_IN_KG = Decimal("0.45359237")
CSV_VERSION = "1"
CSV_COLUMNS = (
    "workout_ref",
    "completed_at",
    "timezone",
    "workout_title",
    "status",
    "exercise_ref",
    "exercise_name",
    "set_number",
    "set_status",
    "set_kind",
    "reps",
    "weight",
    "weight_unit",
    "rir",
    "rpe",
    "side",
)
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})")
_NUMBER = re.compile(r"\d{1,10}(?:\.\d{1,4})?")
_INTEGER = re.compile(r"\d{1,10}")


class WorkoutHistoryImportError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ImportIssue:
    code: str
    field: str
    message: str


@dataclass(frozen=True)
class ImportRow:
    line: int
    source: dict[str, str]
    completed_at_utc: datetime | None
    completed_on: date | None
    set_number: int | None
    reps: int | None
    weight_kg: Decimal | None
    issues: tuple[ImportIssue, ...]


def _issue(issues: list[ImportIssue], code: str, field: str, message: str) -> None:
    issues.append(ImportIssue(code, field, message))


def _integer(
    value: str, field: str, issues: list[ImportIssue], *, required: bool, minimum: int
) -> int | None:
    if not value and not required:
        return None
    if not _INTEGER.fullmatch(value) or not minimum <= int(value) <= 2_147_483_647:
        _issue(issues, "invalid_integer", field, "Укажите допустимое целое число")
        return None
    return int(value)


def _completion(
    value: str, timezone_name: str, issues: list[ImportIssue]
) -> tuple[datetime | None, date | None]:
    if not timezone_name or len(timezone_name) > 128:
        _issue(issues, "invalid_timezone", "timezone", "Укажите действительный часовой пояс")
        return None, None
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError, ValueError, OSError:
        _issue(issues, "invalid_timezone", "timezone", "Укажите действительный часовой пояс")
        return None, None
    if not _TIMESTAMP.fullmatch(value):
        _issue(
            issues,
            "invalid_completed_at",
            "completed_at",
            "Укажите дату и время завершения со смещением часового пояса",
        )
        return None, None
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _issue(issues, "invalid_completed_at", "completed_at", "Дата завершения не распознана")
        return None, None
    try:
        local = timestamp.astimezone(zone)
        completed_at = timestamp.astimezone(UTC).replace(tzinfo=None)
    except ValueError, OverflowError:
        _issue(issues, "invalid_completed_at", "completed_at", "Дата завершения не распознана")
        return None, None
    if local.replace(tzinfo=None) != timestamp.replace(tzinfo=None):
        _issue(
            issues,
            "timezone_mismatch",
            "completed_at",
            "Смещение времени не соответствует указанному часовому поясу",
        )
        return None, None
    if completed_at > datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=5):
        _issue(issues, "future_completed_at", "completed_at", "Дата завершения ещё не наступила")
        return None, None
    return completed_at, local.date()


def _weight(value: str, unit: str, issues: list[ImportIssue]) -> Decimal | None:
    if not value:
        if unit:
            _issue(issues, "weight_missing", "weight", "Укажите вес или уберите единицу измерения")
        return None
    if unit not in {"kg", "lb"}:
        _issue(issues, "invalid_weight_unit", "weight_unit", "Укажите единицу kg или lb")
        return None
    if not _NUMBER.fullmatch(value):
        _issue(issues, "invalid_weight", "weight", "Укажите неотрицательный числовой вес")
        return None
    try:
        source_weight = Decimal(value)
        converted = source_weight if unit == "kg" else source_weight * POUND_IN_KG
        weight_kg = converted.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        _issue(issues, "invalid_weight", "weight", "Вес не распознан")
        return None
    if weight_kg > MAX_DB_WEIGHT:
        _issue(issues, "invalid_weight", "weight", "Вес превышает допустимое значение")
        return None
    if (unit == "kg" and weight_kg != source_weight) or (source_weight > 0 and weight_kg == 0):
        _issue(issues, "weight_precision", "weight", "Вес нельзя точно сохранить с этой точностью")
        return None
    return weight_kg


def _parse_row(line: int, source: dict[str, str]) -> ImportRow:
    issues: list[ImportIssue] = []
    for field in ("workout_ref", "workout_title", "exercise_ref", "exercise_name"):
        value = source[field]
        if not value or len(value) > 128:
            _issue(issues, "invalid_text", field, "Заполните поле: не более 128 символов")
        elif value[0] in "=+-@":
            _issue(issues, "unsafe_text", field, "Значение начинается с недопустимого символа")
    if source["status"] != "completed":
        _issue(
            issues, "not_completed", "status", "Можно импортировать только завершённые тренировки"
        )
    if source["set_status"] != "completed":
        _issue(issues, "set_not_completed", "set_status", "Подход должен быть отмечен выполненным")
    if source["set_kind"] not in {"warmup", "working", "drop"}:
        _issue(issues, "invalid_set_kind", "set_kind", "Укажите поддерживаемый тип подхода")
    if source["rir"] not in {"", "0", "1", "2", "3", "4+"}:
        _issue(issues, "invalid_rir", "rir", "Укажите RIR: 0, 1, 2, 3 или 4+")
    if source["rpe"]:
        _issue(issues, "unsupported_rpe", "rpe", "RPE пока нельзя перенести без потери смысла")
    if source["side"]:
        _issue(issues, "unsupported_side", "side", "Раздельные стороны пока не поддерживаются")
    completed_at, completed_on = _completion(source["completed_at"], source["timezone"], issues)
    set_number = _integer(source["set_number"], "set_number", issues, required=True, minimum=1)
    reps = _integer(source["reps"], "reps", issues, required=False, minimum=0)
    weight_kg = _weight(source["weight"], source["weight_unit"], issues)
    if not source["reps"] and not source["weight"]:
        _issue(issues, "result_missing", "reps", "Укажите фактические повторы или вес")
    return ImportRow(
        line, source, completed_at, completed_on, set_number, reps, weight_kg, tuple(issues)
    )


def parse_workout_history_csv(content: bytes) -> tuple[ImportRow, ...]:
    deadline = monotonic() + MAX_PARSE_SECONDS
    if not content or len(content) > MAX_BYTES:
        raise WorkoutHistoryImportError("file_size", "Файл пуст или превышает допустимый размер")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise WorkoutHistoryImportError("encoding", "Используйте CSV в кодировке UTF-8") from exc
    if any(ord(character) < 32 and character not in "\r\n\t" for character in text):
        raise WorkoutHistoryImportError("control_character", "Файл содержит управляющие символы")

    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    rows: list[ImportRow] = []
    workout_data: dict[str, tuple[str, str, str, str]] = {}
    exercise_names: dict[tuple[str, str], str] = {}
    seen_sets: set[tuple[str, str, int]] = set()
    try:
        if next(reader, None) != ["yfc_workout_history", CSV_VERSION]:
            raise WorkoutHistoryImportError("version", "Нужен шаблон истории YFC версии 1")
        header = next(reader, None)
        if header is None or len(header) != len(CSV_COLUMNS) or set(header) != set(CSV_COLUMNS):
            raise WorkoutHistoryImportError("columns", "Проверьте колонки шаблона истории")
        for values in reader:
            if monotonic() > deadline:
                raise WorkoutHistoryImportError("parse_timeout", "Файл обрабатывался слишком долго")
            line = reader.line_num
            if len(rows) >= MAX_ROWS:
                raise WorkoutHistoryImportError("row_limit", "Файл превышает лимит строк")
            if len(values) != len(header):
                raise WorkoutHistoryImportError(
                    "row_width", f"Проверьте число полей в строке {line}"
                )
            if any(
                len(value) > MAX_CELL_CHARS or "\n" in value or "\r" in value for value in values
            ):
                raise WorkoutHistoryImportError("cell_limit", f"Проверьте значение в строке {line}")
            if any(
                any(ord(character) < 32 or ord(character) == 127 for character in value)
                for value in values
            ):
                raise WorkoutHistoryImportError(
                    "control_character", f"Недопустимый символ в строке {line}"
                )
            source = dict(zip(header, (value.strip() for value in values), strict=True))
            row = _parse_row(line, source)
            issues = list(row.issues)
            workout_ref = source["workout_ref"]
            exercise_ref = source["exercise_ref"]
            metadata = (
                source["completed_at"],
                source["timezone"],
                source["workout_title"],
                source["status"],
            )
            if (
                workout_ref
                and workout_ref in workout_data
                and workout_data[workout_ref] != metadata
            ):
                _issue(issues, "workout_conflict", "workout_ref", "Данные тренировки не совпадают")
            elif workout_ref:
                workout_data[workout_ref] = metadata
            exercise_key = (workout_ref, exercise_ref)
            if all(exercise_key) and exercise_key in exercise_names:
                if exercise_names[exercise_key] != source["exercise_name"]:
                    _issue(
                        issues,
                        "exercise_conflict",
                        "exercise_ref",
                        "Названия упражнения не совпадают",
                    )
            elif all(exercise_key):
                exercise_names[exercise_key] = source["exercise_name"]
            if all(exercise_key) and row.set_number is not None:
                set_key = (*exercise_key, row.set_number)
                if set_key in seen_sets:
                    _issue(issues, "duplicate_set", "set_number", "Номер подхода повторяется")
                seen_sets.add(set_key)
            rows.append(
                ImportRow(
                    row.line,
                    row.source,
                    row.completed_at_utc,
                    row.completed_on,
                    row.set_number,
                    row.reps,
                    row.weight_kg,
                    tuple(issues),
                )
            )
    except csv.Error as exc:
        raise WorkoutHistoryImportError("malformed_csv", "Не удалось прочитать CSV-файл") from exc
    if not rows:
        raise WorkoutHistoryImportError("empty", "В файле нет подходов")
    return tuple(rows)
