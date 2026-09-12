from __future__ import annotations

import csv
import hashlib
import html
import io
import logging
import posixpath
import re
import time
import unicodedata
import zipfile
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from itertools import pairwise
from typing import Final, Literal, NotRequired, TypedDict, cast
from uuid import uuid4
from xml.etree import ElementTree

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fitminiapp_api.core.config import settings
from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.models.exercise import Exercise
from fitminiapp_api.models.program import (
    ProgramTemplate,
    ProgramTemplateExerciseWeekPrescription,
)
from fitminiapp_api.models.program_import import ProgramImport
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.program import (
    ProgramTemplateCreate,
    ProgramTemplateDayCreate,
    ProgramTemplateExerciseCreate,
)
from fitminiapp_api.services.audit import record_audit_event
from fitminiapp_api.services.exercise_catalog import (
    _effective_exercise_id,
    _load_visible_exercise_rows,
    _source_exercise_slug,
    get_visible_exercise_display_map,
)
from fitminiapp_api.services.exercise_catalog_metadata import (
    CANONICAL_EXERCISE_REDIRECTS,
    exercise_catalog_metadata,
)
from fitminiapp_api.services.program_common import ProgramError
from fitminiapp_api.services.program_import_ai import (
    PROGRAM_IMPORT_AI_CONTRACT_VERSION,
    PROGRAM_IMPORT_AI_PROMPT_VERSION,
    DisabledProgramImportAiPort,
    ProgramImportAiPort,
    ProgramImportAiProposal,
    ProgramImportAiRequest,
    ProgramImportAiResponse,
    ProgramImportAiRowContext,
    ProgramImportAiSourceSpan,
)
from fitminiapp_api.services.programs import create_template
from fitminiapp_api.services.workout_metrics import (
    exercise_metric_type,
    normalize_exercise_prescription,
)

logger = logging.getLogger(__name__)

PROGRAM_IMPORT_SCHEMA_VERSION: Final = 2
PROGRAM_IMPORT_PARSER_VERSION: Final = "program-import-v3"
PROGRAM_IMPORT_CANONICAL_LAYOUT: Final = "canonical-table-v1"
PROGRAM_IMPORT_MATRIX_LAYOUT: Final = "weekly-matrix-v1"
PROGRAM_IMPORT_GENERIC_LAYOUT: Final = "generic-table-v1"
PROGRAM_IMPORT_TEXT_LAYOUT: Final = "text-list-v1"
PROGRAM_IMPORT_DOCX_LAYOUT: Final = "docx-document-v1"
PROGRAM_IMPORT_MARKER: Final = "#yfc_template_version"
PROGRAM_IMPORT_MARKER_VALUE: Final = "1"
PROGRAM_IMPORT_COLUMNS: Final = (
    "program_title",
    "goal",
    "level",
    "day_number",
    "day_title",
    "exercise_name",
    "prescribed_sets",
    "prescribed_reps",
    "rest_seconds",
    "exercise_id",
    "exercise_slug",
    "metric_type",
    "prescribed_duration_minutes",
    "notes",
    "superset_group",
    "superset_order",
)
PROGRAM_IMPORT_REQUIRED_COLUMNS: Final = frozenset(
    {
        "program_title",
        "goal",
        "level",
        "day_number",
        "day_title",
        "exercise_name",
        "prescribed_sets",
        "prescribed_reps",
        "rest_seconds",
    }
)
PROGRAM_IMPORT_MAX_CANDIDATES: Final = 5
PROGRAM_IMPORT_SUPPORTED_FORMATS: Final = frozenset({"csv", "xlsx", "txt", "docx"})
PROGRAM_IMPORT_TEMPLATE_FORMATS: Final = frozenset({"csv", "xlsx"})
_CONTROL_CHARACTERS = frozenset(chr(value) for value in range(32)) - {"\t", "\r", "\n"}
_INTEGER_PATTERN = re.compile(r"\d+")
_COLUMN_PATTERN = re.compile(r"[A-Z]+")
_CELL_REFERENCE_PATTERN = re.compile(r"([A-Z]+)(\d+)\Z")
_CELL_RANGE_PATTERN = re.compile(r"([A-Z]+)(\d+):([A-Z]+)(\d+)\Z")
_REL_NAMESPACE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_WEEK_HEADER_PATTERN = re.compile(r"^неделя\s*(\d+)$", re.IGNORECASE)
_DAY_HEADER_PATTERN = re.compile(r"^день\s*(\d+)$", re.IGNORECASE)
_DOCUMENT_DAY_PATTERN = re.compile(
    r"^(?:[-*•]\s*)?(?:день|day)\s*(\d+)\s*(?:[-:–—]\s*(.*))?$", re.IGNORECASE
)
_DOCUMENT_WEEK_PATTERN = re.compile(
    r"^(?:[-*•]\s*)?(?:неделя|week)\s*(\d+)\s*(?:[-:–—]\s*(.*))?$", re.IGNORECASE
)
_DOCUMENT_REST_PATTERN = re.compile(
    r"^(?:[-*•]\s*)?(?:отдых|rest)\s*[:：-]?\s*(\d+(?:[.,]\d+)?)\s*"
    r"(сек(?:унд)?|с|seconds?|sec|мин(?:уты|ут)?|м|minutes?|min)?\s*$",
    re.IGNORECASE,
)
_DOCUMENT_LIST_PREFIX_PATTERN = re.compile(r"^(?:[-*•]\s+|\d+[.)]\s+)")
_PRESCRIPTION_PATTERN = re.compile(
    r"^(?P<sets>\d{1,2})\s*(?:×|x|х|\*)\s*(?P<reps>.+)$", re.IGNORECASE
)
_SETS_REPS_TEXT_PATTERN = re.compile(
    r"^(?P<sets>\d{1,2})\s*(?:подход(?:а|ов)?|sets?)\s*(?:по|x|×|х)?\s*(?P<reps>.+)$",
    re.IGNORECASE,
)
_GENERIC_HEADER_ALIASES: dict[str, frozenset[str]] = {
    "program_title": frozenset({"programtitle", "названиепрограммы", "названиеплана", "программа"}),
    "goal": frozenset({"goal", "цель", "цельпрограммы"}),
    "level": frozenset({"level", "уровень"}),
    "day_number": frozenset(
        {"day", "daynumber", "workout", "workoutnumber", "день", "номердня", "тренировка"}
    ),
    "day_title": frozenset({"daytitle", "названиедня", "тренировочныйдень"}),
    "week_number": frozenset({"week", "weeknumber", "неделя", "номернедели"}),
    "exercise_name": frozenset(
        {"exercise", "exercisename", "movement", "упражнение", "названиеупражнения"}
    ),
    "prescribed_sets": frozenset(
        {"sets", "set", "prescribedsets", "подход", "подходы", "количествоподходов"}
    ),
    "prescribed_reps": frozenset(
        {
            "reps",
            "rep",
            "repetitions",
            "prescribedreps",
            "повтор",
            "повторы",
            "повторения",
            "количествоповторов",
        }
    ),
    "prescribed_duration_minutes": frozenset(
        {"duration", "durationminutes", "минуты", "длительность", "времяминуты"}
    ),
    "rest_seconds": frozenset({"rest", "restseconds", "отдых", "отдыхсекунды"}),
    "notes": frozenset({"notes", "note", "comment", "comments", "заметки", "примечание"}),
    "source_auxiliary": frozenset({"weight", "load", "вес", "нагрузка", "рабочийвес", "вескг"}),
}
_SOURCE_EXERCISE_ALIASES: dict[str, tuple[str, ...]] = {
    "выпадынаместе": ("Выпады",),
    "выпаданаместе": ("Выпады",),
    "махигантелейвстороны": ("Подъем гантелей через стороны",),
    "приседаниявколодец": ("Приседания",),
    "протяжка": ("Тяга к подбородку",),
    "разгибанияногсидя": ("Разгибание ног",),
    "сведениявкроссоверекнизу": ("Сведение рук сверху вниз в кроссовере",),
    "сгибаниясezгрифом": ("Подъем EZ-штанги на бицепс",),
    "сгибаниястоя": ("Сгибание ноги стоя",),
    "тягаверхнегоблокаузким": ("Вертикальная тяга узким хватом",),
    "тягаверхнегошироким": ("Вертикальная тяга",),
    "французскийжим": ("Французский жим лежа",),
    "сведениявбабочке": ("Сведение рук в тренажере",),
    "пэкдэк": ("Сведение рук в тренажере",),
    "пэкдек": ("Сведение рук в тренажере",),
    "молоты": ("Молотковые сгибания",),
    "молотки": ("Молотковые сгибания",),
    "икрыстоя": ("Подъемы на носки стоя",),
    "скручиваниянапресс": ("Скручивания",),
    "жимгантелейнанаклонной": ("Жим гантелей на наклонной скамье",),
}
_TRANSLITERATION = str.maketrans(
    {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "j",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "c",
        "ч": "ch",
        "ш": "sh",
        "щ": "shh",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
    }
)


class ProgramImportError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class _GridCell:
    row: int
    column: int
    address: str
    value: str


@dataclass(frozen=True)
class _ExtractedRow:
    row_number: int
    source_row: int
    source_range: str
    source_cells: dict[str, str]
    values: dict[str, str]
    week_number: int | None = None
    source_auxiliary: str | None = None
    resolution_key: str | None = None
    exercise_match_name: str | None = None
    source_sheet: str | None = None
    source_evidence: str | None = None


@dataclass(frozen=True)
class _DocumentLine:
    line_number: int
    text: str
    source_range: str
    source_cells: dict[str, str]
    cells: tuple[str, ...] = ()
    table_id: int | None = None


@dataclass(frozen=True)
class _Table:
    header: tuple[str, ...]
    rows: tuple[tuple[int, tuple[str, ...]], ...]
    cell_count: int
    sheet_name: str | None
    layout_version: str = PROGRAM_IMPORT_CANONICAL_LAYOUT
    duration_weeks: int | None = None
    grid: tuple[_GridCell, ...] = ()
    merged_ranges: tuple[tuple[int, int, int, int], ...] = ()
    layout_warnings: tuple[tuple[str, str, str], ...] = ()


@dataclass(frozen=True)
class _Candidate:
    exercise_id: int
    title: str
    slug: str
    metric_type: str
    match_type: str


class _Issue(TypedDict):
    code: str
    severity: str
    message: str
    location: str
    field: str
    row_number: int | None
    source_sheet: str | None
    source_row: int | None
    source_cell: str | None


class _CandidateData(TypedDict):
    exercise_id: int
    title: str
    slug: str
    metric_type: str
    match_type: str


class _RowDraft(TypedDict, total=False):
    row_number: int
    source_row: int
    source_sheet: str | None
    source_range: str
    source_cells: dict[str, str]
    week_number: int | None
    source_auxiliary: str | None
    resolution_key: str | None
    exercise_match_name: str | None
    name_normalized: bool
    source_alias_used: bool
    day_number: int | None
    day_title: str | None
    exercise_name: str | None
    exercise_id: int | None
    exercise_slug: str | None
    metric_type: str | None
    prescribed_sets: int | None
    prescribed_reps: str | None
    prescribed_duration_minutes: int | None
    rest_seconds: int | None
    notes: str | None
    superset_group: int | None
    superset_order: int | None
    manual_exercise_id: int | None
    resolved_exercise_id: int | None
    resolved_exercise_title: str | None
    match_status: str
    match_type: str | None
    candidates: list[_CandidateData]
    issues: list[_Issue]
    parse_issues: list[_Issue]
    program_title: str | None
    goal: str | None
    level: str | None
    source_evidence: str | None
    rest_defaulted: bool
    ai_proposals: list[dict[str, object]]
    ai_candidate_order: list[int]
    ai_rerank_reason: str | None


class _Summary(TypedDict):
    row_count: int
    cell_count: int
    matched_row_count: int
    unresolved_row_count: int
    blocking_issue_count: int
    warning_count: int


class _Draft(TypedDict):
    source_format: str
    schema_version: int
    parser_version: str
    layout_version: str
    duration_weeks: int
    program_title: str | None
    goal: str | None
    level: str | None
    rows: list[_RowDraft]
    issues: list[_Issue]
    summary: _Summary
    ai: NotRequired[dict[str, object]]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _text(value: object) -> str:
    if value is None:
        return ""
    return unicodedata.normalize("NFKC", str(value)).strip()


def _optional_text(value: object) -> str | None:
    normalized = _text(value)
    return normalized or None


def _issue(
    code: str,
    severity: str,
    message: str,
    *,
    row_number: int | None = None,
    field: str | None = None,
) -> _Issue:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "location": f"Строка {row_number}" if row_number is not None else "Файл",
        "field": field or "",
        "row_number": row_number,
        "source_sheet": None,
        "source_row": None,
        "source_cell": None,
    }


def _issue_key(item: _Issue) -> tuple[str, str, str, str]:
    return (
        item["code"],
        item["severity"],
        item["location"],
        item["field"],
    )


def _append_issue(
    issues: list[_Issue],
    code: str,
    severity: str,
    message: str,
    *,
    row_number: int | None = None,
    field: str | None = None,
) -> None:
    item = _issue(code, severity, message, row_number=row_number, field=field)
    if not any(_issue_key(existing) == _issue_key(item) for existing in issues):
        issues.append(item)


def _validate_text_cells(rows: list[tuple[int, tuple[str, ...]]]) -> None:
    for row_number, row in rows:
        for value in row:
            if "\x00" in value or any(character in _CONTROL_CHARACTERS for character in value):
                raise ProgramImportError(
                    "control_character",
                    f"Недопустимый управляющий символ в строке {row_number}",
                )
            if len(value) > settings.program_import_max_cell_chars:
                raise ProgramImportError(
                    "cell_too_long",
                    f"Значение в строке {row_number} превышает лимит длины ячейки",
                )


def _validate_table(
    *,
    marker: tuple[str, ...] | None,
    header: tuple[str, ...] | None,
    rows: list[tuple[int, tuple[str, ...]]],
    cell_count: int,
    sheet_name: str | None,
    grid: tuple[_GridCell, ...] = (),
    merged_ranges: tuple[tuple[int, int, int, int], ...] = (),
    layout_warnings: tuple[tuple[str, str, str], ...] = (),
) -> _Table:
    if marker != (PROGRAM_IMPORT_MARKER, PROGRAM_IMPORT_MARKER_VALUE):
        raise ProgramImportError(
            "template_version_required",
            "Нужен канонический шаблон YFC версии 1",
        )
    if header is None:
        raise ProgramImportError("header_missing", "В файле отсутствует строка заголовков")
    if not header or len(header) > settings.program_import_max_columns:
        raise ProgramImportError("column_limit", "В файле слишком много или слишком мало колонок")

    normalized_header = tuple(_text(value).lower() for value in header)
    if any(not value for value in normalized_header):
        raise ProgramImportError("empty_column", "Заголовок колонки не может быть пустым")
    if len(set(normalized_header)) != len(normalized_header):
        raise ProgramImportError("duplicate_column", "В файле есть дублирующиеся колонки")
    unknown = sorted(set(normalized_header) - set(PROGRAM_IMPORT_COLUMNS))
    if unknown:
        raise ProgramImportError(
            "unknown_column",
            "Файл содержит неподдерживаемые колонки: " + ", ".join(unknown),
        )
    missing = sorted(PROGRAM_IMPORT_REQUIRED_COLUMNS - set(normalized_header))
    if missing:
        raise ProgramImportError(
            "required_column_missing",
            "Отсутствуют обязательные колонки: " + ", ".join(missing),
        )
    if len(rows) > settings.program_import_max_rows:
        raise ProgramImportError("row_limit", "Файл превышает лимит строк")
    if cell_count > settings.program_import_max_cells:
        raise ProgramImportError("cell_limit", "Файл превышает лимит ячеек")

    width = len(normalized_header)
    normalized_rows: list[tuple[int, tuple[str, ...]]] = []
    for row_number, row in rows:
        if len(row) > width:
            raise ProgramImportError(
                "row_width",
                f"В строке {row_number} больше значений, чем колонок в заголовке",
            )
        normalized_rows.append((row_number, tuple(row) + ("",) * (width - len(row))))
    _validate_text_cells(normalized_rows)
    return _Table(
        header=normalized_header,
        rows=tuple(normalized_rows),
        cell_count=cell_count,
        sheet_name=sheet_name,
        layout_version=PROGRAM_IMPORT_CANONICAL_LAYOUT,
        grid=grid,
        merged_ranges=merged_ranges,
        layout_warnings=layout_warnings,
    )


def _detect_csv_delimiter(text: str) -> str:
    sample = "\n".join(text.splitlines()[:64])
    candidates: list[tuple[tuple[int, int, int, int], str]] = []
    for priority, delimiter in enumerate((",", ";", "\t")):
        try:
            parsed = list(
                csv.reader(io.StringIO(sample, newline=""), delimiter=delimiter, strict=True)
            )
        except csv.Error:
            continue
        non_empty = [row for row in parsed if any(_text(value) for value in row)]
        multi_column = sum(len(row) > 1 for row in non_empty)
        if not multi_column:
            continue
        widths = [len(row) for row in non_empty]
        consistent = sum(width == max(widths) for width in widths)
        candidates.append(((multi_column, consistent, max(widths), -priority), delimiter))
    return max(candidates, default=((0, 0, 0, 0), ","))[1]


def _parse_csv(source: bytes) -> _Table:
    if not source:
        raise ProgramImportError("empty_file", "Файл пуст")
    if source.startswith((b"\xff\xfe", b"\xfe\xff", b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        raise ProgramImportError("csv_encoding", "CSV должен быть сохранён в UTF-8")
    try:
        text = source.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ProgramImportError("csv_encoding", "CSV должен быть сохранён в UTF-8") from exc
    delimiter = _detect_csv_delimiter(text)
    csv.field_size_limit(settings.program_import_max_cell_chars)
    try:
        rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True))
    except (csv.Error, UnicodeError) as exc:
        raise ProgramImportError(
            "csv_malformed", "CSV содержит некорректные кавычки или строки"
        ) from exc
    raw_rows = [(index, tuple(row)) for index, row in enumerate(rows, start=1)]
    if raw_rows and raw_rows[0][1] == (PROGRAM_IMPORT_MARKER, PROGRAM_IMPORT_MARKER_VALUE):
        if len(raw_rows) < 2:
            raise ProgramImportError("header_missing", "В CSV отсутствует строка заголовков")
        return _validate_table(
            marker=raw_rows[0][1],
            header=raw_rows[1][1],
            rows=[
                (row_number, row)
                for row_number, row in raw_rows[2:]
                if any(_text(value) for value in row)
            ],
            cell_count=sum(1 for _, row in raw_rows for value in row if _text(value)),
            sheet_name=None,
            grid=_grid_from_rows(raw_rows),
        )

    return _generic_table_from_rows(raw_rows, sheet_name=None)


def _grid_from_rows(rows: list[tuple[int, tuple[str, ...]]]) -> tuple[_GridCell, ...]:
    cells: list[_GridCell] = []
    for row_number, values in rows:
        if len(values) > settings.program_import_max_columns:
            raise ProgramImportError("column_limit", "В файле слишком много колонок")
        for column_number, value in enumerate(values, start=1):
            normalized = _text(value)
            if not normalized:
                continue
            cells.append(
                _GridCell(
                    row=row_number,
                    column=column_number,
                    address=f"{_xlsx_column_label(column_number)}{row_number}",
                    value=normalized,
                )
            )
    if len(cells) > settings.program_import_max_cells:
        raise ProgramImportError("cell_limit", "Файл превышает лимит ячеек")
    _validate_text_cells(
        [(row_number, tuple(_text(value) for value in values)) for row_number, values in rows]
    )
    return tuple(cells)


def _generic_table_from_rows(
    rows: list[tuple[int, tuple[str, ...]]],
    *,
    sheet_name: str | None,
    grid: tuple[_GridCell, ...] | None = None,
    merged_ranges: tuple[tuple[int, int, int, int], ...] = (),
    layout_warnings: tuple[tuple[str, str, str], ...] = (),
) -> _Table:
    if not rows:
        raise ProgramImportError("empty_file", "Файл пуст")
    if len(rows) > settings.program_import_max_rows:
        raise ProgramImportError("row_limit", "Файл превышает лимит строк")
    if grid is None:
        grid = _grid_from_rows(rows)
    return _Table(
        header=(),
        rows=tuple(
            (row_number, tuple(_text(value) for value in values))
            for row_number, values in rows
            if any(_text(value) for value in values)
        ),
        cell_count=sum(1 for cell in grid if cell.value),
        sheet_name=sheet_name,
        layout_version=PROGRAM_IMPORT_GENERIC_LAYOUT,
        grid=grid,
        merged_ranges=merged_ranges,
        layout_warnings=layout_warnings,
    )


def _safe_zip_path(name: str, *, container: str = "XLSX") -> str:
    normalized = name.replace("\\", "/")
    if not normalized or normalized.startswith("/") or ":" in normalized.split("/", 1)[0]:
        raise ProgramImportError(
            f"{container.casefold()}_path",
            f"{container} содержит небезопасный путь внутри архива",
        )
    parts = normalized.split("/")
    path_parts = parts[:-1] if parts[-1] == "" else parts
    if any(part in {"", ".", ".."} for part in path_parts):
        raise ProgramImportError(
            f"{container.casefold()}_path",
            f"{container} содержит небезопасный путь внутри архива",
        )
    return normalized


def _xml_root(source: bytes, code: str, *, container: str = "XLSX") -> ElementTree.Element:
    lowered = source.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise ProgramImportError(
            f"{container.casefold()}_xml",
            f"{container} содержит запрещённую XML-конструкцию",
        )
    try:
        return ElementTree.fromstring(source)
    except ElementTree.ParseError as exc:
        raise ProgramImportError(code, f"{container} содержит некорректный XML") from exc


def _xlsx_relationship_target(source: bytes) -> dict[str, str]:
    root = _xml_root(source, "xlsx_relationships")
    result: dict[str, str] = {}
    for relationship in root.iter():
        if _local_name(relationship.tag) != "Relationship":
            continue
        rel_id = relationship.attrib.get("Id", "")
        target = relationship.attrib.get("Target", "")
        if relationship.attrib.get("TargetMode", "").lower() == "external":
            raise ProgramImportError("xlsx_external_link", "XLSX не должен содержать внешние связи")
        if re.match(r"(?i)https?://", target) or target.startswith("//"):
            raise ProgramImportError("xlsx_external_link", "XLSX не должен содержать внешние связи")
        if rel_id and target:
            result[rel_id] = target
    return result


def _xlsx_validate_sheet_relationships(source: bytes) -> bool:
    """Allow external hyperlinks as inert annotations, but reject other externals."""
    root = _xml_root(source, "xlsx_relationships")
    ignored_hyperlink = False
    for relationship in root.iter():
        if _local_name(relationship.tag) != "Relationship":
            continue
        target = relationship.attrib.get("Target", "")
        is_external = relationship.attrib.get("TargetMode", "").lower() == "external"
        is_external = (
            is_external or bool(re.match(r"(?i)https?://", target)) or target.startswith("//")
        )
        relationship_type = relationship.attrib.get("Type", "").lower()
        is_hyperlink = relationship_type.endswith("/hyperlink")
        if is_external and is_hyperlink:
            ignored_hyperlink = True
            continue
        if is_external:
            raise ProgramImportError(
                "xlsx_external_link", "XLSX содержит запрещённую внешнюю связь"
            )
    return ignored_hyperlink


def _read_xlsx_member(archive: zipfile.ZipFile, name: str) -> bytes:
    try:
        return archive.read(name)
    except (KeyError, zipfile.BadZipFile) as exc:
        raise ProgramImportError(
            "xlsx_container", "XLSX повреждён или содержит отсутствующую запись"
        ) from exc


def _xlsx_column_number(reference: str) -> int:
    match = _COLUMN_PATTERN.fullmatch(reference)
    if match is None:
        raise ProgramImportError(
            "xlsx_cell_reference", "XLSX содержит некорректную ссылку на ячейку"
        )
    number = 0
    for character in match.group(0):
        number = number * 26 + ord(character) - ord("A") + 1
    return number


def _xlsx_column_label(column_number: int) -> str:
    value = column_number
    letters = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def _xlsx_cell_value(cell: ElementTree.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t", "")
    if any(_local_name(child.tag) == "f" for child in cell):
        raise ProgramImportError("xlsx_formula", "Формулы в импортируемом XLSX запрещены")
    if cell_type == "inlineStr":
        return "".join(text.text or "" for text in cell.iter() if _local_name(text.tag) == "t")
    value = next(
        (child.text or "" for child in cell if _local_name(child.tag) == "v"),
        "",
    )
    if cell_type == "s":
        if not _INTEGER_PATTERN.fullmatch(value) or int(value) >= len(shared_strings):
            raise ProgramImportError(
                "xlsx_shared_string", "XLSX содержит некорректную shared string"
            )
        return shared_strings[int(value)]
    if cell_type == "b":
        return "TRUE" if value == "1" else "FALSE"
    return value


def _parse_xlsx(source: bytes) -> _Table:
    if not source.startswith(b"PK"):
        raise ProgramImportError(
            "xlsx_signature", "Файл с расширением XLSX не является ZIP-контейнером"
        )
    try:
        archive = zipfile.ZipFile(io.BytesIO(source))
    except zipfile.BadZipFile as exc:
        raise ProgramImportError(
            "xlsx_container", "XLSX повреждён или не является ZIP-контейнером"
        ) from exc

    with archive:
        infos = archive.infolist()
        if len(infos) > settings.program_import_max_xlsx_entries:
            raise ProgramImportError(
                "xlsx_entry_limit", "XLSX содержит слишком много архивных записей"
            )
        names: list[str] = []
        expanded_bytes = 0
        for info in infos:
            name = _safe_zip_path(info.filename)
            if name in names:
                raise ProgramImportError(
                    "xlsx_duplicate_entry", "XLSX содержит дублирующиеся записи"
                )
            names.append(name)
            if info.flag_bits & 0x1:
                raise ProgramImportError("xlsx_encrypted", "Зашифрованные XLSX не поддерживаются")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ProgramImportError(
                    "xlsx_symlink", "XLSX содержит небезопасную архивную запись"
                )
            expanded_bytes += info.file_size
            if expanded_bytes > settings.program_import_max_xlsx_expanded_bytes:
                raise ProgramImportError(
                    "xlsx_expansion", "XLSX превышает лимит распакованного размера"
                )
            if (
                info.file_size
                > max(1, info.compress_size) * settings.program_import_max_xlsx_compression_ratio
            ):
                raise ProgramImportError(
                    "xlsx_compression_ratio", "XLSX имеет небезопасный коэффициент сжатия"
                )
            if name.lower().endswith(("/vbaproject.bin", ".bin")) or "/embeddings/" in name.lower():
                raise ProgramImportError(
                    "xlsx_active_content", "Макросы и встроенные объекты XLSX запрещены"
                )
            if "/externallinks/" in name.lower() or name.lower().endswith("connections.xml"):
                raise ProgramImportError("xlsx_external_link", "Внешние связи XLSX запрещены")

        name_set = set(names)
        required = {"[Content_Types].xml", "xl/workbook.xml", "xl/_rels/workbook.xml.rels"}
        if not required.issubset(name_set):
            raise ProgramImportError("xlsx_structure", "XLSX не содержит поддерживаемую книгу")
        workbook_source = _read_xlsx_member(archive, "xl/workbook.xml")
        workbook = _xml_root(workbook_source, "xlsx_workbook")
        sheets = [element for element in workbook.iter() if _local_name(element.tag) == "sheet"]
        if len(sheets) != 1:
            raise ProgramImportError(
                "xlsx_sheet_count", "Поддерживается XLSX ровно с одним видимым листом"
            )
        if sheets[0].attrib.get("state", "visible") != "visible":
            raise ProgramImportError("xlsx_hidden_sheet", "Скрытые листы XLSX не поддерживаются")
        sheet_name = _text(sheets[0].attrib.get("name"))
        if (
            not sheet_name
            or len(sheet_name) > 31
            or any(character in _CONTROL_CHARACTERS for character in sheet_name)
            or any(character in sheet_name for character in "[]:*?/\\")
        ):
            raise ProgramImportError("xlsx_sheet_name", "XLSX содержит недопустимое имя листа")
        relationship_id = sheets[0].attrib.get(f"{{{_REL_NAMESPACE}}}id") or sheets[0].attrib.get(
            "r:id"
        )
        relationships = _xlsx_relationship_target(
            _read_xlsx_member(archive, "xl/_rels/workbook.xml.rels")
        )
        target = relationships.get(relationship_id or "")
        if target is None:
            raise ProgramImportError("xlsx_sheet_reference", "Не удалось найти лист XLSX")
        sheet_path = posixpath.normpath(posixpath.join("xl", target.lstrip("/")))
        if not sheet_path.startswith("xl/") or sheet_path not in name_set:
            raise ProgramImportError("xlsx_sheet_reference", "XLSX ссылается на небезопасный лист")

        layout_warnings: list[tuple[str, str, str]] = []
        sheet_relationship_path = posixpath.join(
            posixpath.dirname(sheet_path),
            "_rels",
            posixpath.basename(sheet_path) + ".rels",
        )
        if sheet_relationship_path in name_set and _xlsx_validate_sheet_relationships(
            _read_xlsx_member(archive, sheet_relationship_path)
        ):
            layout_warnings.append(
                (
                    "xlsx_external_hyperlinks_ignored",
                    "warning",
                    "Внешние ссылки на видео обнаружены, но не загружаются и не становятся частью программы",
                )
            )

        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in name_set:
            shared_root = _xml_root(
                _read_xlsx_member(archive, "xl/sharedStrings.xml"), "xlsx_shared_strings"
            )
            for item in shared_root.iter():
                if _local_name(item.tag) == "si":
                    shared_strings.append(
                        "".join(
                            child.text or ""
                            for child in item.iter()
                            if _local_name(child.tag) == "t"
                        )
                    )
                    if len(shared_strings) > settings.program_import_max_cells:
                        raise ProgramImportError(
                            "xlsx_shared_string_limit", "XLSX содержит слишком много shared strings"
                        )

        sheet_source = _read_xlsx_member(archive, sheet_path)
        sheet_root = _xml_root(sheet_source, "xlsx_sheet")
        row_elements = [
            element for element in sheet_root.iter() if _local_name(element.tag) == "row"
        ]
        merged_ranges: list[tuple[int, int, int, int]] = []
        merged_coordinates: set[tuple[int, int]] = set()
        merged_cell_budget = 0
        for element in sheet_root.iter():
            if _local_name(element.tag) == "mergeCells":
                for merge_cell in element:
                    if _local_name(merge_cell.tag) != "mergeCell":
                        continue
                    reference = merge_cell.attrib.get("ref", "")
                    match = _CELL_RANGE_PATTERN.fullmatch(reference)
                    if match is None:
                        raise ProgramImportError(
                            "xlsx_merge_reference",
                            "XLSX содержит некорректный диапазон объединённых ячеек",
                        )
                    min_column = _xlsx_column_number(match.group(1))
                    min_row = int(match.group(2))
                    max_column = _xlsx_column_number(match.group(3))
                    max_row = int(match.group(4))
                    if (
                        min_column > max_column
                        or min_row < 1
                        or min_row > max_row
                        or max_column > settings.program_import_max_columns
                        or max_row > settings.program_import_max_xlsx_physical_rows
                    ):
                        raise ProgramImportError(
                            "xlsx_merge_reference",
                            "Диапазон объединённых ячеек XLSX выходит за лимиты",
                        )
                    merge_area = (max_column - min_column + 1) * (max_row - min_row + 1)
                    merged_cell_budget += merge_area
                    if merged_cell_budget > settings.program_import_max_xlsx_physical_cells:
                        raise ProgramImportError(
                            "xlsx_merge_limit", "XLSX содержит слишком большое объединение ячеек"
                        )
                    for merge_row in range(min_row, max_row + 1):
                        for merge_column in range(min_column, max_column + 1):
                            coordinate = (merge_row, merge_column)
                            if coordinate in merged_coordinates:
                                raise ProgramImportError(
                                    "xlsx_merge_overlap",
                                    "XLSX содержит пересекающиеся объединённые ячейки",
                                )
                            merged_coordinates.add(coordinate)
                    merged_ranges.append((min_row, min_column, max_row, max_column))
            if _local_name(element.tag) in {"row", "col"} and element.attrib.get("hidden", "0") in {
                "1",
                "true",
            }:
                raise ProgramImportError(
                    "xlsx_hidden_rows", "Скрытые строки и колонки XLSX не поддерживаются"
                )

        parsed_rows: dict[int, tuple[str, ...]] = {}
        physical_cell_count = 0
        cell_count = 0
        grid_cells: list[_GridCell] = []
        for fallback_row_number, row_element in enumerate(row_elements, start=1):
            raw_row_number = row_element.attrib.get("r", str(fallback_row_number))
            if not _INTEGER_PATTERN.fullmatch(raw_row_number):
                raise ProgramImportError(
                    "xlsx_row_reference", "XLSX содержит некорректный номер строки"
                )
            row_number = int(raw_row_number)
            if row_number < 1 or row_number > settings.program_import_max_xlsx_physical_rows:
                raise ProgramImportError("row_limit", "XLSX превышает лимит физических строк")
            if row_number in parsed_rows:
                raise ProgramImportError("xlsx_duplicate_row", "XLSX содержит дублирующиеся строки")
            values: dict[int, str] = {}
            fallback_column = 1
            for cell in row_element:
                if _local_name(cell.tag) != "c":
                    continue
                physical_cell_count += 1
                if physical_cell_count > settings.program_import_max_xlsx_physical_cells:
                    raise ProgramImportError("cell_limit", "XLSX превышает лимит физических ячеек")
                reference = cell.attrib.get("r", "")
                if reference:
                    cell_reference = _CELL_REFERENCE_PATTERN.fullmatch(reference)
                    if cell_reference is None or int(cell_reference.group(2)) != row_number:
                        raise ProgramImportError(
                            "xlsx_cell_reference",
                            "XLSX содержит некорректную ссылку на ячейку",
                        )
                    column_number = _xlsx_column_number(cell_reference.group(1))
                else:
                    column_number = fallback_column
                if column_number > settings.program_import_max_columns:
                    raise ProgramImportError("column_limit", "XLSX превышает лимит колонок")
                fallback_column = column_number + 1
                if column_number in values:
                    raise ProgramImportError(
                        "xlsx_duplicate_cell", "XLSX содержит дублирующуюся ячейку"
                    )
                value = _xlsx_cell_value(cell, shared_strings)
                if "\x00" in value or any(character in _CONTROL_CHARACTERS for character in value):
                    raise ProgramImportError(
                        "control_character",
                        f"Недопустимый управляющий символ в строке {row_number}",
                    )
                if len(value) > settings.program_import_max_cell_chars:
                    raise ProgramImportError(
                        "cell_too_long", "XLSX содержит слишком длинное значение"
                    )
                values[column_number] = value
                normalized_value = _text(value)
                if normalized_value:
                    cell_count += 1
                    if cell_count > settings.program_import_max_cells:
                        raise ProgramImportError(
                            "cell_limit", "XLSX превышает лимит непустых ячеек"
                        )
                    grid_cells.append(
                        _GridCell(
                            row=row_number,
                            column=column_number,
                            address=f"{_xlsx_column_label(column_number)}{row_number}",
                            value=normalized_value,
                        )
                    )
            width = max(values, default=0)
            parsed_rows[row_number] = tuple(values.get(index, "") for index in range(1, width + 1))

        grid_by_coordinate = {(cell.row, cell.column): cell for cell in grid_cells}
        for min_row, min_column, max_row, max_column in merged_ranges:
            anchor = grid_by_coordinate.get((min_row, min_column))
            if anchor is None or not anchor.value:
                continue
            for merge_row in range(min_row, max_row + 1):
                for merge_column in range(min_column, max_column + 1):
                    coordinate = (merge_row, merge_column)
                    existing = grid_by_coordinate.get(coordinate)
                    if existing is not None:
                        if existing.value != anchor.value and coordinate != (min_row, min_column):
                            raise ProgramImportError(
                                "xlsx_merge_value",
                                "Объединённые ячейки XLSX содержат разные значения",
                            )
                        continue
                    grid_by_coordinate[coordinate] = _GridCell(
                        row=merge_row,
                        column=merge_column,
                        address=f"{_xlsx_column_label(merge_column)}{merge_row}",
                        value=anchor.value,
                    )

        marker = parsed_rows.get(1)
        header = parsed_rows.get(2)
        data_rows = [
            (row_number, values)
            for row_number, values in sorted(parsed_rows.items())
            if row_number > 2 and any(_text(value) for value in values)
        ]
        grid = tuple(sorted(grid_by_coordinate.values(), key=lambda cell: (cell.row, cell.column)))
        if marker == (PROGRAM_IMPORT_MARKER, PROGRAM_IMPORT_MARKER_VALUE):
            if header is None:
                raise ProgramImportError("header_missing", "В XLSX отсутствует строка заголовков")
            return _validate_table(
                marker=marker,
                header=header,
                rows=data_rows,
                cell_count=cell_count,
                sheet_name=sheet_name,
                grid=grid,
                merged_ranges=tuple(merged_ranges),
                layout_warnings=tuple(layout_warnings),
            )
        return _generic_table_from_rows(
            [
                (row_number, values)
                for row_number, values in sorted(parsed_rows.items())
                if any(_text(value) for value in values)
            ],
            sheet_name=sheet_name,
            grid=grid,
            merged_ranges=tuple(merged_ranges),
            layout_warnings=tuple(layout_warnings),
        )


def _parse_txt(source: bytes) -> tuple[_DocumentLine, ...]:
    try:
        text = source.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ProgramImportError("text_encoding", "TXT должен быть сохранён в UTF-8") from exc
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if len(lines) > settings.program_import_max_txt_lines:
        raise ProgramImportError("text_line_limit", "TXT превышает лимит строк")
    parsed: list[_DocumentLine] = []
    for line_number, raw_line in enumerate(lines, start=1):
        if "\x00" in raw_line or any(character in _CONTROL_CHARACTERS for character in raw_line):
            raise ProgramImportError(
                "control_character", f"Недопустимый управляющий символ в строке {line_number}"
            )
        if len(raw_line) > settings.program_import_max_cell_chars:
            raise ProgramImportError("line_too_long", f"Строка {line_number} превышает лимит длины")
        value = _text(raw_line)
        if not value:
            continue
        source_range = f"строка {line_number}"
        parsed.append(
            _DocumentLine(
                line_number=line_number,
                text=value,
                source_range=source_range,
                source_cells={"text": source_range},
                cells=(value,),
            )
        )
    return tuple(parsed)


def _docx_text(element: ElementTree.Element) -> str:
    parts: list[str] = []
    for child in element.iter():
        local_name = _local_name(child.tag)
        if local_name == "t":
            parts.append(child.text or "")
        elif local_name == "tab":
            parts.append("\t")
        elif local_name in {"br", "cr"}:
            parts.append("\n")
    return _text("".join(parts))


def _parse_docx(source: bytes) -> tuple[_DocumentLine, ...]:
    if not source.startswith(b"PK"):
        raise ProgramImportError(
            "docx_signature", "Файл с расширением DOCX не является ZIP-контейнером"
        )
    try:
        archive = zipfile.ZipFile(io.BytesIO(source))
    except zipfile.BadZipFile as exc:
        raise ProgramImportError(
            "docx_container", "DOCX повреждён или не является ZIP-контейнером"
        ) from exc

    with archive:
        infos = archive.infolist()
        if len(infos) > settings.program_import_max_docx_entries:
            raise ProgramImportError(
                "docx_entry_limit", "DOCX содержит слишком много архивных записей"
            )
        names: list[str] = []
        expanded_bytes = 0
        for info in infos:
            name = _safe_zip_path(info.filename, container="DOCX")
            if name in names:
                raise ProgramImportError(
                    "docx_duplicate_entry", "DOCX содержит дублирующиеся записи"
                )
            names.append(name)
            if info.flag_bits & 0x1:
                raise ProgramImportError("docx_encrypted", "Зашифрованные DOCX не поддерживаются")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ProgramImportError(
                    "docx_symlink", "DOCX содержит небезопасную архивную запись"
                )
            expanded_bytes += info.file_size
            if expanded_bytes > settings.program_import_max_docx_expanded_bytes:
                raise ProgramImportError(
                    "docx_expansion", "DOCX превышает лимит распакованного размера"
                )
            if (
                info.file_size
                > max(1, info.compress_size) * settings.program_import_max_docx_compression_ratio
            ):
                raise ProgramImportError(
                    "docx_compression_ratio", "DOCX имеет небезопасный коэффициент сжатия"
                )
            lowered_name = name.casefold()
            if lowered_name.endswith((".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar", ".cab")):
                raise ProgramImportError(
                    "docx_nested_archive", "DOCX не должен содержать вложенные архивы"
                )
            if (
                lowered_name.endswith((".bin", ".exe", ".dll", ".js", ".vbs", ".docm"))
                or "/embeddings/" in lowered_name
                or lowered_name.endswith("/altchunk.xml")
            ):
                raise ProgramImportError(
                    "docx_active_content", "Макросы и встроенные объекты DOCX запрещены"
                )

        name_set = set(names)
        required = {"[Content_Types].xml", "word/document.xml"}
        if not required.issubset(name_set):
            raise ProgramImportError("docx_structure", "DOCX не содержит поддерживаемый документ")
        _xml_root(
            archive.read("[Content_Types].xml"),
            "docx_content_types",
            container="DOCX",
        )
        for name in names:
            if not name.casefold().endswith(".rels"):
                continue
            root = _xml_root(
                archive.read(name),
                "docx_relationships",
                container="DOCX",
            )
            for relationship in root.iter():
                if _local_name(relationship.tag) != "Relationship":
                    continue
                target = relationship.attrib.get("Target", "")
                if (
                    relationship.attrib.get("TargetMode", "").casefold() == "external"
                    or re.match(r"(?i)https?://", target)
                    or target.startswith("//")
                ):
                    raise ProgramImportError(
                        "docx_external_link", "DOCX не должен содержать внешние связи"
                    )

        document_root = _xml_root(
            archive.read("word/document.xml"),
            "docx_document",
            container="DOCX",
        )
        body = next(
            (element for element in document_root.iter() if _local_name(element.tag) == "body"),
            None,
        )
        if body is None:
            raise ProgramImportError("docx_structure", "DOCX не содержит тела документа")

        parsed: list[_DocumentLine] = []
        paragraph_count = 0
        table_cell_count = 0
        physical_line = 0
        table_number = 0
        for child in body:
            local_name = _local_name(child.tag)
            if local_name == "p":
                paragraph_count += 1
                if paragraph_count > settings.program_import_max_docx_paragraphs:
                    raise ProgramImportError(
                        "docx_paragraph_limit", "DOCX содержит слишком много абзацев"
                    )
                paragraph_text = _docx_text(child)
                for part_number, raw_part in enumerate(
                    paragraph_text.splitlines() or (paragraph_text,), start=1
                ):
                    value = _text(raw_part)
                    if not value:
                        continue
                    physical_line += 1
                    source_range = f"абзац {paragraph_count}" + (
                        f", строка {part_number}" if "\n" in paragraph_text else ""
                    )
                    parsed.append(
                        _DocumentLine(
                            line_number=physical_line,
                            text=value,
                            source_range=source_range,
                            source_cells={"text": source_range},
                            cells=(value,),
                        )
                    )
                continue
            if local_name != "tbl":
                continue
            table_number += 1
            table_rows = [row for row in child.iter() if _local_name(row.tag) == "tr"]
            for row_number, row in enumerate(table_rows, start=1):
                cells = [cell for cell in row if _local_name(cell.tag) == "tc"]
                table_cell_count += len(cells)
                if table_cell_count > settings.program_import_max_docx_table_cells:
                    raise ProgramImportError(
                        "docx_cell_limit", "DOCX содержит слишком много ячеек таблиц"
                    )
                values = tuple(_docx_text(cell) for cell in cells)
                if not any(values):
                    continue
                physical_line += 1
                source_range = f"таблица {table_number}, строка {row_number}"
                source_cells = {
                    f"column_{index}": f"таблица {table_number}, строка {row_number}, ячейка {index}"
                    for index in range(1, len(values) + 1)
                }
                parsed.append(
                    _DocumentLine(
                        line_number=physical_line,
                        text=" | ".join(value for value in values if value),
                        source_range=source_range,
                        source_cells=source_cells,
                        cells=values,
                        table_id=table_number,
                    )
                )
        return tuple(parsed)


def _document_header_mapping(values: tuple[str, ...]) -> tuple[dict[str, int], int | None]:
    mapping: dict[str, int] = {}
    prescription_index: int | None = None
    for index, value in enumerate(values):
        key = _normalized_header_key(value)
        if key in {"setsreps", "подходыповторы", "подходыповторения"}:
            prescription_index = index
            continue
        for field, aliases in _GENERIC_HEADER_ALIASES.items():
            if key in aliases and field not in mapping:
                mapping[field] = index
                break
    return mapping, prescription_index


def _document_metadata(label: str, value: str) -> tuple[str, str] | None:
    key = _normalized_match_key(label)
    field_by_key = {
        "название": "program_title",
        "названиепрограммы": "program_title",
        "программа": "program_title",
        "title": "program_title",
        "program": "program_title",
        "programtitle": "program_title",
        "цель": "goal",
        "цельпрограммы": "goal",
        "goal": "goal",
        "уровень": "level",
        "level": "level",
    }
    field = field_by_key.get(key)
    if field is None:
        return None
    normalized = _optional_text(value)
    if normalized is None:
        return None
    return field, _normalize_document_metadata_value(field, normalized)


def _normalize_document_metadata_value(field: str, normalized: str) -> str:
    if field == "goal":
        normalized = {
            "набормышечноймассы": "muscle_gain",
            "набормассы": "muscle_gain",
            "снижениевеса": "fat_loss",
            "жиросжигание": "fat_loss",
            "поддержаниеформы": "maintenance",
            "поддержание": "maintenance",
            "рекомпозиция": "recomposition",
        }.get(_normalized_match_key(normalized), normalized)
    elif field == "level":
        normalized = {
            "начальный": "beginner",
            "начинающий": "beginner",
            "средний": "intermediate",
            "продвинутый": "advanced",
        }.get(_normalized_match_key(normalized), normalized)
    return normalized


def _document_context(
    value: str | None, kind: Literal["day", "week"]
) -> tuple[int, str | None] | None:
    normalized = _optional_text(value)
    if normalized is None:
        return None
    pattern = _DOCUMENT_DAY_PATTERN if kind == "day" else _DOCUMENT_WEEK_PATTERN
    match = pattern.fullmatch(normalized)
    if match is not None:
        label = _optional_text(match.group(2))
        return int(match.group(1)), label
    if normalized.isdecimal():
        return int(normalized), None
    return None


def _document_rest_seconds(value: str) -> int | None:
    match = _DOCUMENT_REST_PATTERN.fullmatch(_text(value))
    if match is None:
        return None
    amount = float(match.group(1).replace(",", "."))
    unit = (match.group(2) or "сек").casefold()
    seconds = round(amount * 60) if unit.startswith(("м", "min", "minute")) else round(amount)
    return seconds


def _parse_integer_text(value: str | None) -> int | None:
    normalized = _optional_text(value)
    if normalized is None or not _INTEGER_PATTERN.fullmatch(normalized):
        return None
    return int(normalized)


def _document_exercise(value: str) -> tuple[str | None, int | None, str | None]:
    normalized = _optional_text(_DOCUMENT_LIST_PREFIX_PATTERN.sub("", value, count=1))
    if normalized is None:
        return None, None, None
    name, sets, reps = _exercise_name_and_prescription(normalized)
    if sets is not None and reps is not None:
        return _optional_text(name), sets, reps
    text_match = re.search(
        r"\s+(?P<sets>\d{1,2})\s*(?:подход(?:а|ов)?|sets?)\s*"
        r"(?:по|x|×|х)?\s*(?P<reps>[^\n]+)$",
        normalized,
        flags=re.IGNORECASE,
    )
    if text_match is not None:
        reps_text = _normalize_repetitions(text_match.group("reps"))
        return (
            _optional_text(normalized[: text_match.start()]),
            int(text_match.group("sets")),
            reps_text,
        )
    return normalized, None, None


def _document_evidence(line: _DocumentLine) -> str:
    return _text(line.text or " | ".join(line.cells))[:512]


def _document_values(
    *,
    line: _DocumentLine,
    metadata: dict[str, str],
    day_number: int | None,
    day_title: str | None,
    week_number: int | None,
    exercise_name: str,
    prescribed_sets: int | None,
    prescribed_reps: str | None,
    rest_seconds: int | None,
    source_sheet: str | None,
    source_cells: dict[str, str] | None = None,
    extra: dict[str, str] | None = None,
) -> _ExtractedRow:
    values = {
        "program_title": metadata.get("program_title", ""),
        "goal": metadata.get("goal", ""),
        "level": metadata.get("level", ""),
        "day_number": str(day_number) if day_number is not None else "",
        "day_title": day_title or "",
        "week_number": str(week_number) if week_number is not None else "",
        "exercise_name": exercise_name,
        "prescribed_sets": str(prescribed_sets) if prescribed_sets is not None else "",
        "prescribed_reps": prescribed_reps or "",
        "rest_seconds": str(rest_seconds) if rest_seconds is not None else "",
    }
    if extra:
        values.update(extra)
    return _ExtractedRow(
        row_number=0,
        source_row=line.line_number,
        source_range=line.source_range,
        source_cells=source_cells or {"exercise_name": line.source_range},
        values=values,
        week_number=week_number,
        resolution_key=_normalized_match_key(exercise_name),
        source_sheet=source_sheet,
        source_evidence=_document_evidence(line),
    )


def _extract_document_rows(
    lines: tuple[_DocumentLine, ...],
    *,
    source_format: str,
) -> tuple[tuple[_ExtractedRow, ...], int, tuple[tuple[str, str, str], ...], str]:
    metadata: dict[str, str] = {}
    current_day: int | None = None
    current_day_title: str | None = None
    current_week: int | None = None
    current_rest: int | None = None
    active_table_id: int | None = None
    table_mapping: tuple[dict[str, int], int | None] | None = None
    extracted: list[_ExtractedRow] = []
    current_day_start_index = 0
    saw_explicit_day = False
    saw_explicit_week = False
    last_row: _ExtractedRow | None = None

    for line in lines:
        if line.table_id != active_table_id:
            active_table_id = line.table_id
            table_mapping = None

        if line.table_id is not None and len(line.cells) > 1:
            mapping, prescription_index = _document_header_mapping(line.cells)
            if "exercise_name" in mapping and len(mapping) >= 2:
                table_mapping = (mapping, prescription_index)
                continue
            if table_mapping is not None:
                mapping, prescription_index = table_mapping
                row_cells = line.cells
                field_mapping = mapping

                def cell(
                    field: str,
                    *,
                    cells: tuple[str, ...] = row_cells,
                    mapping_snapshot: dict[str, int] = field_mapping,
                ) -> str:
                    index = mapping_snapshot.get(field)
                    return cells[index] if index is not None and index < len(cells) else ""

                raw_exercise = cell("exercise_name")
                exercise_name, inline_sets, inline_reps = _document_exercise(raw_exercise)
                if exercise_name is None:
                    continue
                sets = _parse_integer_text(cell("prescribed_sets")) or inline_sets
                reps = _optional_text(cell("prescribed_reps")) or inline_reps
                if sets is None or reps is None:
                    combined = (
                        line.cells[prescription_index]
                        if prescription_index is not None and prescription_index < len(line.cells)
                        else ""
                    )
                    parsed = _parse_prescription(combined)
                    if parsed is not None:
                        sets, reps = parsed
                day_context = _document_context(cell("day_number"), "day")
                week_context = _document_context(cell("week_number"), "week")
                if day_context is not None:
                    current_day, explicit_title = day_context
                    current_day_title = (
                        _optional_text(cell("day_title")) or explicit_title or f"День {current_day}"
                    )
                    saw_explicit_day = True
                if week_context is not None:
                    current_week = week_context[0]
                    saw_explicit_week = True
                day_number = day_context[0] if day_context is not None else current_day
                day_title = _optional_text(cell("day_title")) or current_day_title
                week_number = week_context[0] if week_context is not None else current_week
                local_metadata = dict(metadata)
                for field in ("program_title", "goal", "level"):
                    value = _optional_text(cell(field))
                    if value is not None:
                        normalized_value = _normalize_document_metadata_value(field, value)
                        local_metadata[field] = normalized_value
                        metadata[field] = normalized_value
                rest = _document_rest_seconds(cell("rest_seconds"))
                if rest is None:
                    rest = _parse_integer_text(cell("rest_seconds"))
                values_extra = {
                    "notes": cell("notes"),
                    "rest_seconds": str(
                        rest
                        if rest is not None
                        else current_rest
                        if current_rest is not None
                        else ""
                    ),
                }
                source_cells = {
                    field: line.source_cells.get(f"column_{index + 1}", line.source_range)
                    for field, index in mapping.items()
                    if index < len(line.cells)
                }
                extracted_row = _document_values(
                    line=line,
                    metadata=local_metadata,
                    day_number=day_number,
                    day_title=day_title,
                    week_number=week_number,
                    exercise_name=exercise_name,
                    prescribed_sets=sets,
                    prescribed_reps=reps,
                    rest_seconds=rest if rest is not None else current_rest,
                    source_cells=source_cells,
                    source_sheet="DOCX" if source_format == "docx" else None,
                    extra=values_extra,
                )
                extracted.append(extracted_row)
                last_row = extracted_row
                continue

        content = line.text
        day_match = _DOCUMENT_DAY_PATTERN.fullmatch(content)
        if day_match is not None:
            current_day = int(day_match.group(1))
            current_day_title = _optional_text(day_match.group(2)) or f"День {current_day}"
            current_day_start_index = len(extracted)
            saw_explicit_day = True
            continue
        week_match = _DOCUMENT_WEEK_PATTERN.fullmatch(content)
        if week_match is not None:
            current_week = int(week_match.group(1))
            saw_explicit_week = True
            continue
        metadata_match = re.match(
            r"^(?:[-*•]\s*)?(.+?)\s*[:：-]\s*(.+)$", content, flags=re.IGNORECASE
        )
        if metadata_match is not None:
            metadata_item = _document_metadata(metadata_match.group(1), metadata_match.group(2))
            if metadata_item is not None:
                metadata[metadata_item[0]] = metadata_item[1]
                continue
        rest = _document_rest_seconds(content)
        if rest is not None:
            current_rest = rest
            for index in range(current_day_start_index, len(extracted)):
                previous = extracted[index]
                if previous.values.get("rest_seconds"):
                    continue
                previous.values["rest_seconds"] = str(rest)
                extracted[index] = replace(
                    previous,
                    source_evidence=f"{previous.source_evidence} | {content}"[:512],
                )
            continue
        if re.match(r"^(?:примечание|заметка|note|notes)\s*[:：-]", content, re.IGNORECASE):
            note = _optional_text(re.split(r"[:：-]", content, maxsplit=1)[1])
            if note is not None and last_row is not None:
                last_row.values["notes"] = note
                last_row = replace(
                    last_row,
                    source_evidence=f"{last_row.source_evidence} | {content}"[:512],
                )
                extracted[-1] = last_row
            continue
        standalone_prescription = _parse_prescription(content)
        if standalone_prescription is not None and last_row is not None:
            sets, reps = standalone_prescription
            last_row.values["prescribed_sets"] = str(sets)
            last_row.values["prescribed_reps"] = reps
            last_row = replace(
                last_row,
                source_evidence=f"{last_row.source_evidence} | {content}"[:512],
            )
            extracted[-1] = last_row
            continue

        name, sets, reps = _document_exercise(content)
        if name is None:
            continue
        has_list_prefix = _DOCUMENT_LIST_PREFIX_PATTERN.match(content) is not None
        if sets is None and reps is None and current_day is None and not has_list_prefix:
            continue
        extracted.append(
            _document_values(
                line=line,
                metadata=metadata,
                day_number=current_day,
                day_title=current_day_title,
                week_number=current_week,
                exercise_name=name,
                prescribed_sets=sets,
                prescribed_reps=reps,
                rest_seconds=current_rest,
                source_sheet="DOCX" if source_format == "docx" else None,
                source_cells={
                    "exercise_name": line.source_cells.get("text", line.source_range),
                    "prescribed_sets": line.source_cells.get("text", line.source_range),
                    "prescribed_reps": line.source_cells.get("text", line.source_range),
                    "rest_seconds": line.source_cells.get("text", line.source_range),
                },
            )
        )
        last_row = extracted[-1]

    warnings: tuple[tuple[str, str, str], ...]
    if not extracted:
        warnings = (
            (
                "document_no_structured_rows",
                "warning",
                "В документе не найдены строки упражнений; можно использовать ручное исправление после распознавания",
            ),
        )
    else:
        warnings_list: list[tuple[str, str, str]] = [
            (
                "document_layout_detected",
                "warning",
                "Распознан текстовый документ; проверьте каждое предложенное поле перед сохранением",
            )
        ]
        if not saw_explicit_day:
            warnings_list.append(
                (
                    "day_inferred",
                    "warning",
                    "День не указан явно; его нужно подтвердить вручную или заполнить предложением",
                )
            )
        if not saw_explicit_week:
            warnings_list.append(
                (
                    "week_inferred",
                    "warning",
                    "Неделя не указана явно, поэтому документ рассматривается как одна неделя",
                )
            )
        warnings = tuple(warnings_list)
    duration_weeks = max((row.week_number or 1 for row in extracted), default=1)
    if duration_weeks > 24:
        raise ProgramImportError("week_limit", "Документ содержит более 24 недель")
    return (
        tuple(extracted),
        duration_weeks,
        warnings,
        (PROGRAM_IMPORT_DOCX_LAYOUT if source_format == "docx" else PROGRAM_IMPORT_TEXT_LAYOUT),
    )


def _normalized_header_key(value: str) -> str:
    return _normalized_match_key(value)


def _normalize_repetitions(value: str) -> str:
    normalized = _text(value)
    normalized = re.sub(r"\b(?:макс(?:имум)?|max)\b", "MAX", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s*(?:×|x|х)\s*", "/", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s*/\s*", "/", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _parse_prescription(value: str | None) -> tuple[int, str] | None:
    if not value:
        return None
    lines = [_text(line) for line in str(value).replace("\r\n", "\n").split("\n")]
    lines = [line for line in lines if line]
    candidates = list(reversed(lines))
    for candidate in candidates:
        match = _PRESCRIPTION_PATTERN.fullmatch(candidate) or _SETS_REPS_TEXT_PATTERN.fullmatch(
            candidate
        )
        if match is not None:
            reps = _normalize_repetitions(match.group("reps"))
            if reps:
                return int(match.group("sets")), reps
        inline = re.search(
            r"(?P<sets>\d{1,2})\s*(?:×|x|х|\*)\s*(?P<reps>[^\n]+)$",
            candidate,
            flags=re.IGNORECASE,
        )
        if inline is not None and inline.start() > 0:
            reps = _normalize_repetitions(inline.group("reps"))
            if reps:
                return int(inline.group("sets")), reps
    return None


def _exercise_name_and_prescription(value: str | None) -> tuple[str | None, int | None, str | None]:
    normalized = _optional_text(value)
    if normalized is None:
        return None, None, None
    lines = [_text(line) for line in normalized.replace("\r\n", "\n").split("\n")]
    lines = [line for line in lines if line]
    last_line = lines[-1] if lines else normalized
    is_standalone_prescription = (
        _PRESCRIPTION_PATTERN.fullmatch(last_line) is not None
        or _SETS_REPS_TEXT_PATTERN.fullmatch(last_line) is not None
    )
    parsed = _parse_prescription(last_line) if is_standalone_prescription else None
    if parsed is not None:
        name_lines = lines[:-1]
        if not name_lines:
            return None, parsed[0], parsed[1]
        return "\n".join(name_lines), parsed[0], parsed[1]
    inline = re.search(
        r"\s+(?P<sets>\d{1,2})\s*(?:×|x|х|\*)\s*(?P<reps>[^\n]+)$",
        normalized,
        flags=re.IGNORECASE,
    )
    if inline is not None:
        name = _optional_text(normalized[: inline.start()])
        reps = _normalize_repetitions(inline.group("reps"))
        return name, int(inline.group("sets")), reps or None
    return normalized, None, None


def _context_number(value: str | None, kind: str) -> int | None:
    normalized = _text(value)
    if not normalized:
        return None
    if normalized.isdecimal():
        return int(normalized)
    pattern = _DAY_HEADER_PATTERN if kind == "day" else _WEEK_HEADER_PATTERN
    match = pattern.search(normalized)
    return int(match.group(1)) if match is not None else None


def _context_label(value: str | None, kind: str) -> str | None:
    normalized = _optional_text(value)
    if normalized is None:
        return None
    pattern = _DAY_HEADER_PATTERN if kind == "day" else _WEEK_HEADER_PATTERN
    return normalized if pattern.search(normalized) is not None else None


def _generic_header_mapping(
    row_cells: list[_GridCell],
) -> tuple[dict[str, _GridCell], _GridCell | None]:
    mapping: dict[str, _GridCell] = {}
    prescription_cell: _GridCell | None = None
    for cell in row_cells:
        key = _normalized_header_key(cell.value)
        if key in {
            "setsreps",
            "подходыповторы",
            "подходыповторения",
            "количествоподходовиповторов",
        }:
            prescription_cell = cell
            continue
        for field, aliases in _GENERIC_HEADER_ALIASES.items():
            if key in aliases and field not in mapping:
                mapping[field] = cell
                break
    return mapping, prescription_cell


def _find_generic_header(
    rows: dict[int, list[_GridCell]],
) -> tuple[int | None, dict[str, _GridCell], _GridCell | None]:
    best: tuple[int, int, dict[str, _GridCell], _GridCell | None] | None = None
    for row_number, cells in rows.items():
        mapping, prescription_cell = _generic_header_mapping(cells)
        score = len(mapping) + (1 if prescription_cell is not None else 0)
        if "exercise_name" not in mapping or score < 2:
            continue
        candidate = (score, -row_number, mapping, prescription_cell)
        if best is None or candidate[:2] > best[:2]:
            best = candidate
    if best is None:
        return None, {}, None
    return -best[1], best[2], best[3]


def _row_range(cells: list[_GridCell]) -> str:
    if not cells:
        return ""
    first = min(cell.column for cell in cells)
    last = max(cell.column for cell in cells)
    row_number = cells[0].row
    return f"{_xlsx_column_label(first)}{row_number}:{_xlsx_column_label(last)}{row_number}"


def _generic_exercise_cell(
    cells: list[_GridCell],
    mapped_exercise: _GridCell | None,
) -> tuple[_GridCell | None, str | None, int | None, str | None]:
    if mapped_exercise is not None and mapped_exercise.value:
        name, sets, reps = _exercise_name_and_prescription(mapped_exercise.value)
        return mapped_exercise, name, sets, reps
    for cell in cells:
        name, sets, reps = _exercise_name_and_prescription(cell.value)
        if sets is not None and reps is not None:
            return cell, name, sets, reps
    candidates = [
        cell
        for cell in cells
        if not _context_label(cell.value, "day")
        and not _context_label(cell.value, "week")
        and not cell.value.isdecimal()
    ]
    if not candidates:
        return None, None, None, None
    cell = max(candidates, key=lambda item: len(item.value))
    name, sets, reps = _exercise_name_and_prescription(cell.value)
    return cell, name, sets, reps


def _extract_generic_rows(
    table: _Table,
) -> tuple[tuple[_ExtractedRow, ...], int, tuple[tuple[str, str, str], ...]]:
    cells_by_row: dict[int, list[_GridCell]] = defaultdict(list)
    for cell in table.grid:
        if cell.value:
            cells_by_row[cell.row].append(cell)
    for cells in cells_by_row.values():
        cells.sort(key=lambda cell: cell.column)
    if not cells_by_row:
        raise ProgramImportError(
            "layout_not_supported", "В файле не найдено содержимое для импорта"
        )

    header_row, mapping, combined_prescription = _find_generic_header(cells_by_row)
    data_rows = [
        (row_number, cells)
        for row_number, cells in sorted(cells_by_row.items())
        if header_row is None or row_number > header_row
    ]
    current_day: int | None = None
    current_week: int | None = None
    day_titles: dict[int, str] = {}
    extracted: list[_ExtractedRow] = []
    saw_explicit_day = "day_number" in mapping
    saw_explicit_week = "week_number" in mapping
    saw_auxiliary = False
    next_row_number = 3

    for source_row, cells in data_rows:
        values_by_column = {cell.column: cell for cell in cells}
        for cell in cells:
            context_day = _context_number(cell.value, "day")
            context_week = _context_number(cell.value, "week")
            if context_day is not None and not cell.value.isdecimal():
                current_day = context_day
                day_titles[context_day] = _context_label(cell.value, "day") or f"День {context_day}"
                saw_explicit_day = True
            if context_week is not None and not cell.value.isdecimal():
                current_week = context_week
                saw_explicit_week = True

        day_cell = values_by_column.get(mapping.get("day_number", _GridCell(0, 0, "", "")).column)
        week_cell = values_by_column.get(mapping.get("week_number", _GridCell(0, 0, "", "")).column)
        day_number = _context_number(day_cell.value, "day") if day_cell is not None else current_day
        week_number = (
            _context_number(week_cell.value, "week") if week_cell is not None else current_week
        )
        if day_number is None:
            day_number = 1
        if week_number is None:
            week_number = 1
        if day_cell is not None and day_number is not None:
            current_day = day_number
        if week_cell is not None and week_number is not None:
            current_week = week_number

        mapped_exercise = values_by_column.get(
            mapping.get("exercise_name", _GridCell(0, 0, "", "")).column
        )
        exercise_cell, exercise_name, inline_sets, inline_reps = _generic_exercise_cell(
            cells,
            mapped_exercise,
        )
        if exercise_cell is None or exercise_name is None:
            continue

        sets = inline_sets
        reps = inline_reps
        source_sets = values_by_column.get(
            mapping.get("prescribed_sets", _GridCell(0, 0, "", "")).column
        )
        source_reps = values_by_column.get(
            mapping.get("prescribed_reps", _GridCell(0, 0, "", "")).column
        )
        source_combined = values_by_column.get(
            combined_prescription.column if combined_prescription is not None else 0
        )
        if sets is None or reps is None:
            combined = _parse_prescription(source_combined.value if source_combined else None)
            if combined is None:
                combined = _parse_prescription(
                    " × ".join(
                        part
                        for part in (
                            source_sets.value if source_sets else "",
                            source_reps.value if source_reps else "",
                        )
                        if part
                    )
                )
            if combined is not None:
                sets, reps = combined

        row_cells = [cell for cell in cells if cell.value]
        source_cells: dict[str, str] = {"exercise_name": exercise_cell.address}
        source_coordinate_fields: tuple[tuple[str, _GridCell | None], ...] = (
            ("day_number", day_cell),
            ("week_number", week_cell),
            ("prescribed_sets", source_sets),
            ("prescribed_reps", source_reps),
            (
                "prescribed_duration_minutes",
                values_by_column.get(
                    mapping.get("prescribed_duration_minutes", _GridCell(0, 0, "", "")).column
                ),
            ),
            (
                "rest_seconds",
                values_by_column.get(mapping.get("rest_seconds", _GridCell(0, 0, "", "")).column),
            ),
            ("notes", values_by_column.get(mapping.get("notes", _GridCell(0, 0, "", "")).column)),
            (
                "source_auxiliary",
                values_by_column.get(
                    mapping.get("source_auxiliary", _GridCell(0, 0, "", "")).column
                ),
            ),
        )
        for field, coordinate_cell in source_coordinate_fields:
            if coordinate_cell is not None:
                source_cells[field] = coordinate_cell.address
        auxiliary_cell = values_by_column.get(
            mapping.get("source_auxiliary", _GridCell(0, 0, "", "")).column
        )
        auxiliary = _optional_text(auxiliary_cell.value if auxiliary_cell else None)
        saw_auxiliary = saw_auxiliary or auxiliary is not None
        day_title_cell = values_by_column.get(
            mapping.get("day_title", _GridCell(0, 0, "", "")).column
        )
        day_title = _optional_text(day_title_cell.value if day_title_cell else None)
        day_title = day_title or day_titles.get(day_number) or f"День {day_number}"
        values = {
            "program_title": values_by_column.get(
                mapping.get("program_title", _GridCell(0, 0, "", "")).column,
                _GridCell(0, 0, "", ""),
            ).value,
            "goal": values_by_column.get(
                mapping.get("goal", _GridCell(0, 0, "", "")).column, _GridCell(0, 0, "", "")
            ).value,
            "level": values_by_column.get(
                mapping.get("level", _GridCell(0, 0, "", "")).column, _GridCell(0, 0, "", "")
            ).value,
            "day_number": str(day_number),
            "day_title": day_title,
            "week_number": str(week_number),
            "exercise_name": exercise_name,
            "prescribed_sets": "" if sets is None else str(sets),
            "prescribed_reps": reps or "",
            "prescribed_duration_minutes": values_by_column.get(
                mapping.get("prescribed_duration_minutes", _GridCell(0, 0, "", "")).column,
                _GridCell(0, 0, "", ""),
            ).value,
            "rest_seconds": values_by_column.get(
                mapping.get("rest_seconds", _GridCell(0, 0, "", "")).column, _GridCell(0, 0, "", "")
            ).value
            or "90",
            "notes": values_by_column.get(
                mapping.get("notes", _GridCell(0, 0, "", "")).column, _GridCell(0, 0, "", "")
            ).value,
        }
        extracted.append(
            _ExtractedRow(
                row_number=next_row_number,
                source_row=source_row,
                source_range=_row_range(row_cells),
                source_cells=source_cells,
                values=values,
                week_number=week_number,
                source_auxiliary=auxiliary,
                resolution_key=_normalized_match_key(exercise_name),
            )
        )
        next_row_number += 1

    if not extracted:
        raise ProgramImportError(
            "layout_not_supported",
            "Не удалось найти строки с упражнениями и назначением подходов/повторов",
        )
    warnings: list[tuple[str, str, str]] = [
        (
            "generic_layout_detected",
            "warning",
            "Распознан общий табличный формат; проверьте каждую строку перед сохранением",
        )
    ]
    if not saw_explicit_day:
        warnings.append(
            (
                "day_inferred",
                "warning",
                "День не указан явно, поэтому строки отнесены к дню 1",
            )
        )
    if not saw_explicit_week:
        warnings.append(
            (
                "week_inferred",
                "warning",
                "Неделя не указана явно, поэтому файл импортируется как одна неделя",
            )
        )
    if saw_auxiliary:
        warnings.append(
            (
                "auxiliary_values_ignored",
                "warning",
                "Вспомогательные значения вроде веса, даты или нагрузки не импортируются как плановая нагрузка",
            )
        )
    duration_weeks = max(row.week_number or 1 for row in extracted)
    if duration_weeks > 24:
        raise ProgramImportError("week_limit", "Файл содержит более 24 недель")
    return tuple(extracted), duration_weeks, tuple(warnings)


def _extract_weekly_matrix_rows(
    table: _Table,
) -> tuple[tuple[_ExtractedRow, ...], int, tuple[tuple[str, str, str], ...]] | None:
    cells_by_coordinate = {(cell.row, cell.column): cell for cell in table.grid if cell.value}
    cells_by_row: dict[int, list[_GridCell]] = defaultdict(list)
    for cell in table.grid:
        if cell.value:
            cells_by_row[cell.row].append(cell)
    week_labels: list[tuple[int, int, int]] = []
    for cell in table.grid:
        match = _WEEK_HEADER_PATTERN.fullmatch(cell.value)
        if match is not None:
            week_labels.append((cell.row, cell.column, int(match.group(1))))
    if not week_labels:
        return None
    by_label_row: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for row_number, column_number, week_number in week_labels:
        by_label_row[row_number].append((column_number, week_number))
    header_row, labels = max(by_label_row.items(), key=lambda item: (len(item[1]), -item[0]))
    if len(labels) < 2:
        return None
    labels = sorted(labels)
    labels_by_week = sorted(labels, key=lambda item: item[1])
    if [week for _, week in labels_by_week] != list(range(1, len(labels_by_week) + 1)):
        return None
    blocks: list[tuple[int, int]] = []
    for label_column, week_number in labels_by_week:
        candidate_start = label_column - 2
        if candidate_start >= 1 and _DAY_HEADER_PATTERN.fullmatch(
            cells_by_coordinate.get((header_row, candidate_start), _GridCell(0, 0, "", "")).value
        ):
            block_start = candidate_start
        else:
            block_start = label_column
        blocks.append((week_number, block_start))
    block_starts = [start for _, start in blocks]
    if any(right - left != 3 for left, right in pairwise(block_starts)):
        return None

    day_headers_by_week: dict[int, list[tuple[int, int]]] = {}
    for week_number, block_start in blocks:
        day_headers: list[tuple[int, int]] = []
        for row_number in sorted(cells_by_row):
            value = cells_by_coordinate.get((row_number, block_start))
            if value is None:
                continue
            match = _DAY_HEADER_PATTERN.fullmatch(value.value)
            if match is not None:
                day_headers.append((row_number, int(match.group(1))))
        if not day_headers or len(day_headers) > 8:
            return None
        day_headers_by_week[week_number] = day_headers
    first_day_rows = [row for row, _ in day_headers_by_week[1]]
    if any(
        [row for row, _ in day_headers_by_week[week]] != first_day_rows
        for week in day_headers_by_week
    ):
        return None
    canonical_day_numbers = [day for _, day in day_headers_by_week[1]]
    if sorted(canonical_day_numbers) != list(range(1, len(canonical_day_numbers) + 1)):
        return None
    first_block_start = blocks[0][1]
    canonical_day_titles = [
        cells_by_coordinate[(row, first_block_start)].value for row, _ in day_headers_by_week[1]
    ]

    extracted: list[_ExtractedRow] = []
    next_row_number = 3
    source_day_orders: dict[int, list[int]] = {}
    saw_auxiliary = False
    for week_number, block_start in blocks:
        day_headers = day_headers_by_week[week_number]
        source_day_orders[week_number] = [day for _, day in day_headers]
        week_label_column = next(column for column, value in labels if value == week_number)
        for day_index, (day_header_row, _day_number) in enumerate(day_headers):
            end_row = day_headers[day_index + 1][0] if day_index + 1 < len(day_headers) else None
            canonical_day_number = canonical_day_numbers[day_index]
            canonical_day_title = canonical_day_titles[day_index]
            block_rows = [
                row_number
                for row_number, cells in cells_by_row.items()
                if row_number > day_header_row
                and (end_row is None or row_number < end_row)
                and any(block_start <= cell.column <= block_start + 2 for cell in cells)
            ]
            if not block_rows:
                continue
            last_row = max(block_rows)
            for source_row in range(day_header_row + 1, last_row + 1):
                main = cells_by_coordinate.get((source_row, block_start))
                if main is None or not main.value:
                    continue
                exercise_name, sets, reps = _exercise_name_and_prescription(main.value)
                if exercise_name is None:
                    exercise_name = main.value
                auxiliary_cell = cells_by_coordinate.get((source_row, block_start + 2))
                auxiliary = _optional_text(auxiliary_cell.value if auxiliary_cell else None)
                saw_auxiliary = saw_auxiliary or auxiliary is not None
                source_cells = {
                    "week_number": f"{_xlsx_column_label(week_label_column)}{header_row}",
                    "day_number": f"{_xlsx_column_label(block_start)}{day_header_row}",
                    "exercise_name": main.address,
                    "prescribed_sets": main.address,
                    "prescribed_reps": main.address,
                }
                if auxiliary_cell is not None:
                    source_cells["source_auxiliary"] = auxiliary_cell.address
                values = {
                    "program_title": "",
                    "goal": "",
                    "level": "",
                    "day_number": str(canonical_day_number),
                    "day_title": canonical_day_title,
                    "week_number": str(week_number),
                    "exercise_name": exercise_name,
                    "prescribed_sets": "" if sets is None else str(sets),
                    "prescribed_reps": reps or "",
                    "rest_seconds": "90",
                    "notes": "",
                }
                extracted.append(
                    _ExtractedRow(
                        row_number=next_row_number,
                        source_row=source_row,
                        source_range=(
                            f"{_xlsx_column_label(block_start)}{source_row}:"
                            f"{_xlsx_column_label(block_start + 2)}{source_row}"
                        ),
                        source_cells=source_cells,
                        values=values,
                        week_number=week_number,
                        source_auxiliary=auxiliary,
                        resolution_key=_normalized_match_key(exercise_name),
                    )
                )
                next_row_number += 1
    if not extracted:
        return None
    warnings: list[tuple[str, str, str]] = []
    if any(
        order != sorted(order) or order != canonical_day_numbers
        for order in source_day_orders.values()
    ):
        warnings.append(
            (
                "day_order_normalized",
                "warning",
                "Порядок подписанных дней в исходном файле различается; при сборке сохраняются физические секции первой недели",
            )
        )
    if saw_auxiliary:
        warnings.append(
            (
                "auxiliary_values_ignored",
                "warning",
                "Вспомогательные значения вроде веса, даты или нагрузки не импортируются как плановая нагрузка",
            )
        )
    return tuple(extracted), len(blocks), tuple(warnings)


def _extract_layout_rows(
    table: _Table,
) -> tuple[tuple[_ExtractedRow, ...], int, tuple[tuple[str, str, str], ...], str]:
    if table.layout_version == PROGRAM_IMPORT_CANONICAL_LAYOUT:
        return (), 1, table.layout_warnings, PROGRAM_IMPORT_CANONICAL_LAYOUT
    matrix = _extract_weekly_matrix_rows(table)
    if matrix is not None:
        rows, duration_weeks, warnings = matrix
        expanded, expansion_warnings = _expand_extracted_rows(rows)
        return (
            expanded,
            duration_weeks,
            table.layout_warnings + warnings + expansion_warnings,
            PROGRAM_IMPORT_MATRIX_LAYOUT,
        )
    generic_rows, duration_weeks, warnings = _extract_generic_rows(table)
    expanded, expansion_warnings = _expand_extracted_rows(generic_rows)
    return (
        expanded,
        duration_weeks,
        table.layout_warnings + warnings + expansion_warnings,
        PROGRAM_IMPORT_GENERIC_LAYOUT,
    )


def _matchable_exercise_name(value: str) -> str:
    normalized = _text(value)
    normalized = re.sub(r"\s*\([^()]{1,256}\)\s*$", "", normalized)
    normalized = re.sub(r"\s*/\s*по одной(?:\s+ноге)?\s*$", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+по одной(?:\s+ноге)?\s*$", "", normalized, flags=re.IGNORECASE)
    return _optional_text(normalized) or _text(value)


def _expand_extracted_rows(
    rows: tuple[_ExtractedRow, ...],
) -> tuple[tuple[_ExtractedRow, ...], tuple[tuple[str, str, str], ...]]:
    expanded: list[_ExtractedRow] = []
    warnings: list[tuple[str, str, str]] = []
    next_row_number = 3
    group_numbers: dict[tuple[int, int], int] = defaultdict(int)
    saw_compound = False
    saw_qualifier = False
    for source in rows:
        source_name = _optional_text(source.values.get("exercise_name")) or ""
        components = [part.strip() for part in re.split(r"\s*\+\s*", source_name) if part.strip()]
        if len(components) > 2:
            components = [source_name]
        is_compound = len(components) == 2
        if is_compound:
            saw_compound = True
            key = (source.week_number or 1, int(source.values.get("day_number", "1")))
            group_numbers[key] += 1
            group = group_numbers[key]
        else:
            group = None
        for component_index, component in enumerate(components, start=1):
            match_name = _matchable_exercise_name(component)
            saw_qualifier = saw_qualifier or match_name != component
            values = dict(source.values)
            values["exercise_name"] = component
            existing_notes = _optional_text(values.get("notes"))
            qualifier = (
                component[len(match_name) :].strip() if component.startswith(match_name) else ""
            )
            if qualifier:
                values["notes"] = (
                    f"{existing_notes}; " if existing_notes else ""
                ) + f"Уточнение из файла: {qualifier}"
            if is_compound:
                values["notes"] = (
                    f"{values.get('notes')}; " if values.get("notes") else ""
                ) + "Связка из исходного файла"
            expanded.append(
                _ExtractedRow(
                    row_number=next_row_number,
                    source_row=source.source_row,
                    source_range=source.source_range,
                    source_cells=dict(source.source_cells),
                    values=values,
                    week_number=source.week_number,
                    source_auxiliary=source.source_auxiliary,
                    resolution_key=_normalized_match_key(match_name),
                    exercise_match_name=match_name,
                )
            )
            expanded[-1].values["superset_group"] = str(group) if group is not None else ""
            expanded[-1].values["superset_order"] = (
                str(component_index) if group is not None else ""
            )
            next_row_number += 1
    if saw_compound:
        warnings.append(
            (
                "compound_exercises_expanded",
                "warning",
                "Строки с символом + разобраны как пары суперсетов; проверьте сопоставление каждой позиции",
            )
        )
    if saw_qualifier:
        warnings.append(
            (
                "exercise_qualifiers_preserved_as_notes",
                "warning",
                "Уточнения в скобках и пометки «по одной» сохранены в заметках, а сопоставление выполнено по базовому названию",
            )
        )
    return tuple(expanded), tuple(warnings)


def _normalized_match_key(value: str, *, transliterated: bool = False) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().replace("ё", "е")
    if transliterated:
        normalized = normalized.translate(_TRANSLITERATION)
    return "".join(character for character in normalized if character.isalnum())


def _match_keys(value: str) -> tuple[tuple[str, bool], ...]:
    if not value:
        return ()
    base = _normalized_match_key(value)
    transliterated = _normalized_match_key(value, transliterated=True)
    result: list[tuple[str, bool]] = []
    if base:
        result.append((base, False))
    if transliterated and transliterated != base:
        result.append((transliterated, True))
    return tuple(result)


def _catalog_candidates(
    db: Session, current_user: User
) -> tuple[dict[int, _Candidate], dict[str, list[_Candidate]]]:
    visible = _load_visible_exercise_rows(db, current_user)
    by_id: dict[int, _Candidate] = {}
    by_key: dict[str, list[_Candidate]] = defaultdict(list)
    for exercise in visible:
        exercise_id = _effective_exercise_id(exercise)
        source_slug = _source_exercise_slug(exercise)
        canonical_slug = CANONICAL_EXERCISE_REDIRECTS.get(source_slug, source_slug)
        metadata = exercise_catalog_metadata(canonical_slug)
        candidate = _Candidate(
            exercise_id=exercise_id,
            title=exercise.title,
            slug=canonical_slug,
            metric_type=exercise_metric_type(exercise),
            match_type="title",
        )
        by_id[exercise_id] = candidate
        labels: list[tuple[str, str]] = [(exercise.title, "title"), (exercise.slug, "slug")]
        if source_slug != exercise.slug:
            labels.append((source_slug, "slug"))
        if canonical_slug not in {exercise.slug, source_slug}:
            labels.append((canonical_slug, "slug"))
        if metadata:
            labels.extend((alias, "alias") for alias in metadata["aliases"])
        for label, match_type in labels:
            for key, transliterated in _match_keys(label):
                typed_candidate = _Candidate(
                    exercise_id=candidate.exercise_id,
                    title=candidate.title,
                    slug=candidate.slug,
                    metric_type=candidate.metric_type,
                    match_type="transliteration" if transliterated else match_type,
                )
                if not any(existing.exercise_id == exercise_id for existing in by_key[key]):
                    by_key[key].append(typed_candidate)
                elif match_type == "title":
                    by_key[key] = [typed_candidate] + [
                        existing for existing in by_key[key] if existing.exercise_id != exercise_id
                    ]
    return by_id, by_key


def _public_candidate(candidate: _Candidate) -> _CandidateData:
    return {
        "exercise_id": candidate.exercise_id,
        "title": candidate.title,
        "slug": candidate.slug,
        "metric_type": candidate.metric_type,
        "match_type": candidate.match_type,
    }


def _identity_candidate_ids(
    value: str,
    *,
    by_key: dict[str, list[_Candidate]],
    transliteration: bool,
) -> set[int]:
    keys = _match_keys(value) if transliteration else ((_normalized_match_key(value), False),)
    return {candidate.exercise_id for key, _ in keys if key for candidate in by_key.get(key, [])}


def _parse_integer(
    value: object,
    *,
    row_number: int,
    field: str,
    issues: list[_Issue],
) -> int | None:
    normalized = _optional_text(value)
    if normalized is None:
        return None
    if re.fullmatch(r"\d+[.,]0+", normalized):
        normalized = re.split(r"[.,]", normalized, maxsplit=1)[0]
    if not _INTEGER_PATTERN.fullmatch(normalized):
        _append_issue(
            issues,
            "invalid_integer",
            "blocking",
            "Ожидалось целое неотрицательное число",
            row_number=row_number,
            field=field,
        )
        return None
    return int(normalized)


def _row_from_values(
    *,
    row_number: int,
    source_sheet: str | None,
    source_range: str,
    source_cells: dict[str, str],
    values: dict[str, str],
) -> tuple[_RowDraft, list[_Issue]]:
    issues: list[_Issue] = []
    raw_rest_seconds = _optional_text(values.get("rest_seconds"))
    row: _RowDraft = {
        "row_number": row_number,
        "source_sheet": source_sheet,
        "source_range": source_range,
        "source_cells": source_cells,
        "day_number": _parse_integer(
            values.get("day_number"), row_number=row_number, field="day_number", issues=issues
        ),
        "day_title": _optional_text(values.get("day_title")),
        "exercise_name": _optional_text(values.get("exercise_name")),
        "exercise_id": _parse_integer(
            values.get("exercise_id"), row_number=row_number, field="exercise_id", issues=issues
        ),
        "exercise_slug": _optional_text(values.get("exercise_slug")),
        "metric_type": _optional_text(values.get("metric_type")),
        "prescribed_sets": _parse_integer(
            values.get("prescribed_sets"),
            row_number=row_number,
            field="prescribed_sets",
            issues=issues,
        ),
        "prescribed_reps": _optional_text(values.get("prescribed_reps")),
        "prescribed_duration_minutes": _parse_integer(
            values.get("prescribed_duration_minutes"),
            row_number=row_number,
            field="prescribed_duration_minutes",
            issues=issues,
        ),
        "rest_seconds": _parse_integer(
            values.get("rest_seconds"), row_number=row_number, field="rest_seconds", issues=issues
        ),
        "notes": _optional_text(values.get("notes")),
        "superset_group": _parse_integer(
            values.get("superset_group"),
            row_number=row_number,
            field="superset_group",
            issues=issues,
        ),
        "superset_order": _parse_integer(
            values.get("superset_order"),
            row_number=row_number,
            field="superset_order",
            issues=issues,
        ),
        "manual_exercise_id": None,
        "resolved_exercise_id": None,
        "resolved_exercise_title": None,
        "match_status": "needs_resolution",
        "match_type": None,
        "candidates": [],
        "rest_defaulted": raw_rest_seconds is None,
    }
    if row["metric_type"] is not None:
        row["metric_type"] = str(row["metric_type"]).casefold()
    if row["rest_seconds"] is None:
        row["rest_seconds"] = 90
    return row, issues


def _add_domain_range_issues(row: _RowDraft, issues: list[_Issue]) -> None:
    row_number = row["row_number"]
    ranges = (
        ("week_number", 1, 24, "Номер недели должен быть от 1 до 24"),
        ("day_number", 1, 8, "Номер дня должен быть от 1 до 8"),
        ("exercise_id", 1, 2_147_483_647, "ID упражнения должен быть положительным"),
        ("prescribed_sets", 1, 10, "Количество подходов должно быть от 1 до 10"),
        ("prescribed_duration_minutes", 1, 600, "Длительность должна быть от 1 до 600 минут"),
        ("rest_seconds", 0, 600, "Отдых должен быть от 0 до 600 секунд"),
        ("superset_group", 1, 2_147_483_647, "Группа суперсета должна быть положительной"),
        ("superset_order", 1, 2, "Позиция суперсета должна быть 1 или 2"),
    )
    for field, minimum, maximum, message in ranges:
        value = row.get(field)
        if value is not None and (not isinstance(value, int) or not minimum <= value <= maximum):
            _append_issue(
                issues,
                "value_out_of_range",
                "blocking",
                message,
                row_number=row_number,
                field=field,
            )
    if (row.get("superset_group") is None) != (row.get("superset_order") is None):
        _append_issue(
            issues,
            "superset_pair",
            "blocking",
            "Группа и позиция суперсета должны задаваться вместе",
            row_number=row_number,
            field="superset_group",
        )
    if row.get("prescribed_reps") and len(str(row["prescribed_reps"])) > 32:
        _append_issue(
            issues,
            "value_too_long",
            "blocking",
            "Диапазон повторений слишком длинный",
            row_number=row_number,
            field="prescribed_reps",
        )
    if row.get("notes") and len(str(row["notes"])) > 2_000:
        _append_issue(
            issues,
            "value_too_long",
            "blocking",
            "Заметка слишком длинная",
            row_number=row_number,
            field="notes",
        )


def _source_name_values(row: _RowDraft) -> tuple[tuple[str, bool], ...]:
    raw_name = _optional_text(row.get("exercise_name"))
    match_name = _optional_text(row.get("exercise_match_name"))
    values: list[tuple[str, bool]] = []
    if match_name:
        values.append((match_name, match_name != raw_name))
    elif raw_name:
        values.append((raw_name, False))
    if match_name:
        for alias in _SOURCE_EXERCISE_ALIASES.get(_normalized_match_key(match_name), ()):
            values.append((alias, True))
    return tuple(values)


def _apply_ai_candidate_order(row: _RowDraft) -> None:
    if row.get("match_status") != "needs_resolution":
        row["ai_rerank_reason"] = None
        return
    requested_order = row.get("ai_candidate_order")
    candidates = row.get("candidates", [])
    if not isinstance(requested_order, list) or not candidates:
        row["ai_rerank_reason"] = None
        return
    candidates_by_id = {
        candidate["exercise_id"]: candidate
        for candidate in candidates
        if isinstance(candidate.get("exercise_id"), int)
    }
    ordered = [
        candidates_by_id[exercise_id]
        for exercise_id in requested_order
        if exercise_id in candidates_by_id
    ]
    ordered_ids = {candidate["exercise_id"] for candidate in ordered}
    row["candidates"] = ordered + [
        candidate for candidate in candidates if candidate["exercise_id"] not in ordered_ids
    ]


def _resolve_row(
    row: _RowDraft,
    row_issues: list[_Issue],
    *,
    by_id: dict[int, _Candidate],
    by_key: dict[str, list[_Candidate]],
) -> None:
    row_number = row["row_number"]
    row["resolved_exercise_id"] = None
    row["resolved_exercise_title"] = None
    row["match_type"] = None
    row["candidates"] = []
    row["name_normalized"] = False
    row["source_alias_used"] = False
    manual_id = row.get("manual_exercise_id")
    candidate: _Candidate | None = None
    if isinstance(manual_id, int):
        candidate = by_id.get(manual_id)
        if candidate is None:
            _append_issue(
                row_issues,
                "exercise_no_longer_available",
                "blocking",
                "Выбранное упражнение больше недоступно",
                row_number=row_number,
                field="exercise_id",
            )
        else:
            row["match_type"] = "manual"
    else:
        imported_id = row.get("exercise_id")
        if isinstance(imported_id, int):
            candidate = by_id.get(imported_id)
            if candidate is None:
                _append_issue(
                    row_issues,
                    "exercise_not_available",
                    "blocking",
                    "Упражнение с таким ID недоступно пользователю",
                    row_number=row_number,
                    field="exercise_id",
                )
            else:
                row["match_type"] = "id"
        elif row.get("exercise_slug"):
            matches = by_key.get(_normalized_match_key(str(row["exercise_slug"])), [])
            unique = {item.exercise_id: item for item in matches}
            if len(unique) == 1:
                candidate = next(iter(unique.values()))
                row["match_type"] = "slug"
            elif len(unique) > 1:
                row["candidates"] = [
                    _public_candidate(item)
                    for item in sorted(unique.values(), key=lambda item: item.title)[
                        :PROGRAM_IMPORT_MAX_CANDIDATES
                    ]
                ]
                _append_issue(
                    row_issues,
                    "exercise_ambiguous",
                    "blocking",
                    "Название упражнения совпало с несколькими упражнениями",
                    row_number=row_number,
                    field="exercise_slug",
                )
            else:
                _append_issue(
                    row_issues,
                    "exercise_not_found",
                    "blocking",
                    "Упражнение по slug не найдено",
                    row_number=row_number,
                    field="exercise_slug",
                )
        elif row.get("exercise_name"):
            matches_by_id: dict[int, _Candidate] = {}
            source_values = _source_name_values(row)
            for source_value, source_alias in source_values:
                match_keys = _match_keys(source_value)
                for key, _transliterated in match_keys:
                    for item in by_key.get(key, []):
                        current = matches_by_id.get(item.exercise_id)
                        if current is None or item.match_type == "title":
                            matches_by_id[item.exercise_id] = item
                if source_alias:
                    row["source_alias_used"] = True
            if len(matches_by_id) == 1:
                candidate = next(iter(matches_by_id.values()))
                row["match_type"] = (
                    "alias" if row.get("source_alias_used") else candidate.match_type
                )
                row["name_normalized"] = bool(
                    row.get("exercise_match_name")
                    and row.get("exercise_match_name") != row.get("exercise_name")
                )
            elif len(matches_by_id) > 1:
                candidates = sorted(matches_by_id.values(), key=lambda item: item.title)
                row["candidates"] = [
                    _public_candidate(item) for item in candidates[:PROGRAM_IMPORT_MAX_CANDIDATES]
                ]
                _append_issue(
                    row_issues,
                    "exercise_ambiguous",
                    "blocking",
                    "Название упражнения требует ручного выбора",
                    row_number=row_number,
                    field="exercise_name",
                )
            else:
                _append_issue(
                    row_issues,
                    "exercise_not_found",
                    "blocking",
                    "Упражнение не найдено в доступном каталоге",
                    row_number=row_number,
                    field="exercise_name",
                )
        else:
            _append_issue(
                row_issues,
                "exercise_missing",
                "blocking",
                "Укажите exercise_id, exercise_slug или exercise_name",
                row_number=row_number,
                field="exercise_name",
            )

    if candidate is not None:
        if not isinstance(manual_id, int):
            identity_values = [("exercise_slug", row.get("exercise_slug"), False)]
            identity_values.extend(
                ("exercise_name", value, True) for value, _is_alias in _source_name_values(row)
            )
            for field, value, allow_transliteration in identity_values:
                if not isinstance(value, str) or not value:
                    continue
                candidate_ids = _identity_candidate_ids(
                    value,
                    by_key=by_key,
                    transliteration=allow_transliteration,
                )
                if candidate.exercise_id not in candidate_ids:
                    if field == "exercise_name" and row.get("source_alias_used"):
                        continue
                    _append_issue(
                        row_issues,
                        "exercise_identity_conflict",
                        "blocking",
                        "Идентификаторы упражнения в строке указывают на разные упражнения",
                        row_number=row_number,
                        field=field,
                    )
        row["resolved_exercise_id"] = candidate.exercise_id
        row["resolved_exercise_title"] = candidate.title
        row["match_status"] = "matched"
        imported_metric = row.get("metric_type")
        if imported_metric is None:
            row["metric_type"] = candidate.metric_type
        if imported_metric is not None and imported_metric not in {"strength", "cardio"}:
            row["metric_type"] = None
            _append_issue(
                row_issues,
                "metric_type_invalid",
                "blocking",
                "metric_type должен быть strength или cardio",
                row_number=row_number,
                field="metric_type",
            )
        elif imported_metric is not None and imported_metric != candidate.metric_type:
            _append_issue(
                row_issues,
                "metric_type_mismatch",
                "blocking",
                "Тип нагрузки не совпадает с каталогом упражнения",
                row_number=row_number,
                field="metric_type",
            )
        try:
            prescribed_sets = row.get("prescribed_sets")
            prescribed_reps = row.get("prescribed_reps")
            prescribed_duration_minutes = row.get("prescribed_duration_minutes")
            rest_seconds = row.get("rest_seconds")
            normalize_exercise_prescription(
                Exercise(metric_type=candidate.metric_type),
                prescribed_sets=prescribed_sets,
                prescribed_reps=prescribed_reps,
                prescribed_duration_minutes=prescribed_duration_minutes,
                rest_seconds=90 if rest_seconds is None else rest_seconds,
            )
        except (ProgramError, TypeError, ValueError) as exc:
            _append_issue(
                row_issues,
                "prescription_invalid",
                "blocking",
                str(exc)[:500],
                row_number=row_number,
                field="prescribed_sets",
            )
    else:
        row["match_status"] = (
            "needs_resolution"
            if not any(
                item["code"] in {"value_out_of_range", "invalid_integer"} for item in row_issues
            )
            else "invalid"
        )
    _apply_ai_candidate_order(row)


def _metadata_value(
    rows: list[_RowDraft],
    field: str,
    issues: list[_Issue],
    *,
    allowed: frozenset[str] | None = None,
) -> str | None:
    values = [str(row.get(field)).strip() for row in rows if row.get(field) not in (None, "")]
    if not values:
        _append_issue(
            issues,
            f"missing_{field}",
            "blocking",
            f"Заполните поле {field} перед подтверждением импорта",
            field=field,
        )
        return None
    first = values[0].casefold() if allowed is not None else values[0]
    if any((value.casefold() if allowed is not None else value) != first for value in values[1:]):
        _append_issue(
            issues,
            f"conflicting_{field}",
            "blocking",
            f"Поле {field} должно быть одинаковым во всех строках",
            field=field,
        )
        return None
    if allowed is not None:
        if first not in allowed:
            _append_issue(
                issues,
                f"invalid_{field}",
                "blocking",
                f"Недопустимое значение поля {field}",
                field=field,
            )
            return None
        return first
    if len(first) > 128:
        _append_issue(
            issues, "value_too_long", "blocking", f"Поле {field} слишком длинное", field=field
        )
        return None
    return first


def _source_location(
    *,
    sheet_name: str | None,
    row_number: int | None,
    cell: str | None,
    row_range: str | None,
) -> str:
    prefix = f"Лист «{sheet_name}», " if sheet_name else ""
    if cell:
        return f"{prefix}ячейка {cell}"
    if row_range:
        return f"{prefix}диапазон {row_range}"
    if row_number is not None:
        return f"{prefix}строка {row_number}"
    if sheet_name:
        return f"Лист «{sheet_name}»"
    return "Файл"


def _attach_source_coordinates(issue: _Issue, rows: list[_RowDraft]) -> None:
    row_number = issue.get("row_number")
    row = next((item for item in rows if item.get("row_number") == row_number), None)
    if row is None and rows:
        row = rows[0]

    if row is None:
        issue["location"] = _source_location(
            sheet_name=None,
            row_number=None,
            cell=None,
            row_range=None,
        )
        return

    sheet_name = row.get("source_sheet")
    source_range = row.get("source_range")
    source_cells = row.get("source_cells", {})
    field = issue.get("field", "")
    cell = source_cells.get(field) if field else None
    source_row = row.get("source_row") if row_number is not None else None

    # File-level metadata errors point to the corresponding header cell. Row-level
    # errors retain the exact data cell that triggered the validation.
    if row_number is None and cell:
        column_match = re.match(r"([A-Z]+)\d+\Z", cell)
        cell = f"{column_match.group(1)}2" if column_match else None
        source_row = 2 if cell else None

    issue["source_sheet"] = sheet_name
    issue["source_row"] = source_row
    issue["source_cell"] = cell
    issue["location"] = _source_location(
        sheet_name=sheet_name,
        row_number=source_row,
        cell=cell,
        row_range=source_range,
    )


def _row_signature(row: _RowDraft) -> tuple[object, ...]:
    return tuple(
        row.get(field)
        for field in (
            "week_number",
            "day_number",
            "day_title",
            "exercise_id",
            "exercise_slug",
            "exercise_name",
            "prescribed_sets",
            "prescribed_reps",
            "prescribed_duration_minutes",
            "rest_seconds",
            "notes",
            "superset_group",
            "superset_order",
        )
    )


def _build_draft(
    db: Session,
    current_user: User,
    *,
    source_format: str,
    cell_count: int,
    raw_rows: list[_RowDraft],
    layout_version: str = PROGRAM_IMPORT_CANONICAL_LAYOUT,
    duration_weeks: int = 1,
    layout_warnings: tuple[tuple[str, str, str], ...] = (),
    ai_metadata: dict[str, object] | None = None,
) -> _Draft:
    global_issues: list[_Issue] = []
    for code, severity, message in layout_warnings:
        _append_issue(global_issues, code, severity, message)
    rows = [cast(_RowDraft, dict(row)) for row in raw_rows]
    for row in rows:
        if layout_version != PROGRAM_IMPORT_CANONICAL_LAYOUT:
            row["week_number"] = row.get("week_number") or 1
        else:
            row["week_number"] = None
    by_id, by_key = _catalog_candidates(db, current_user)

    for row in rows:
        row_issues: list[_Issue] = [
            cast(_Issue, dict(issue)) for issue in row.get("parse_issues", [])
        ]
        _add_domain_range_issues(row, row_issues)
        if row.get("day_number") is None:
            _append_issue(
                row_issues,
                "day_number_missing",
                "blocking",
                "Номер тренировочного дня обязателен",
                row_number=row["row_number"],
                field="day_number",
            )
        if not row.get("day_title"):
            _append_issue(
                row_issues,
                "day_title_missing",
                "blocking",
                "Название тренировочного дня обязательно",
                row_number=row["row_number"],
                field="day_title",
            )
        _resolve_row(row, row_issues, by_id=by_id, by_key=by_key)
        if row.get("metric_type") != "cardio" and (
            row.get("prescribed_sets") is None or not row.get("prescribed_reps")
        ):
            _append_issue(
                row_issues,
                "prescription_missing",
                "blocking",
                "Для силового упражнения нужны подходы и повторения",
                row_number=row["row_number"],
                field="prescribed_sets",
            )
        row["issues"] = row_issues

    if not rows:
        _append_issue(global_issues, "no_data_rows", "blocking", "В файле нет строк с упражнениями")

    title_rows = [cast(_RowDraft, {"program_title": row.get("program_title")}) for row in rows]
    # Metadata is added to every parsed row by the caller. Keeping this explicit
    # makes the stored draft independent from the source file representation.
    title = _metadata_value(title_rows, "program_title", global_issues)
    goal = _metadata_value(
        rows,
        "goal",
        global_issues,
        allowed=frozenset({"muscle_gain", "fat_loss", "maintenance", "recomposition"}),
    )
    level = _metadata_value(
        rows, "level", global_issues, allowed=frozenset({"beginner", "intermediate", "advanced"})
    )

    days: dict[tuple[int, int], list[_RowDraft]] = defaultdict(list)
    seen_signatures: set[tuple[object, ...]] = set()
    for row in rows:
        week_number = row.get("week_number") or 1
        day_number = row.get("day_number")
        if isinstance(day_number, int) and 1 <= day_number <= 8:
            days[(week_number, day_number)].append(row)
        signature = _row_signature(row)
        if signature in seen_signatures:
            _append_issue(
                global_issues,
                "duplicate_row",
                "blocking",
                "Одинаковая строка упражнения повторяется в импорте",
                row_number=row["row_number"],
            )
        seen_signatures.add(signature)

    weeks = sorted({week for week, _ in days})
    if duration_weeks < 1 or duration_weeks > 24:
        _append_issue(
            global_issues, "week_limit", "blocking", "Программа может содержать от 1 до 24 недель"
        )
        duration_weeks = max(1, min(duration_weeks, 24))
    if weeks and weeks != list(range(1, duration_weeks + 1)):
        _append_issue(
            global_issues,
            "week_sequence",
            "blocking",
            "Номера недель должны идти последовательно с 1",
        )
    days_by_week: dict[int, list[int]] = defaultdict(list)
    for week_number, day_number in days:
        days_by_week[week_number].append(day_number)
    expected_days: list[int] | None = None
    for week_number in sorted(days_by_week):
        week_days = sorted(days_by_week[week_number])
        if len(week_days) > 8:
            _append_issue(
                global_issues,
                "day_limit",
                "blocking",
                f"В неделе {week_number} больше 8 тренировочных дней",
            )
        if week_days != list(range(1, len(week_days) + 1)):
            _append_issue(
                global_issues,
                "day_sequence",
                "blocking",
                f"Номера тренировочных дней в неделе {week_number} должны идти последовательно с 1",
            )
        if expected_days is None:
            expected_days = week_days
        elif week_days != expected_days:
            _append_issue(
                global_issues,
                "weekly_structure_incomplete",
                "blocking",
                "Во всех неделях должен быть одинаковый набор тренировочных дней",
            )

    for (week_number, day_number), day_rows in days.items():
        if len(day_rows) > 20:
            _append_issue(
                global_issues,
                "exercise_limit",
                "blocking",
                f"В неделе {week_number}, дне {day_number} больше 20 упражнений",
            )
        day_titles = {str(row.get("day_title")) for row in day_rows if row.get("day_title")}
        if len(day_titles) > 1:
            _append_issue(
                global_issues,
                "conflicting_day_title",
                "blocking",
                f"Название дня {day_number} в неделе {week_number} должно быть одинаковым во всех его строках",
            )
        group_orders: dict[int, list[int]] = defaultdict(list)
        for row in day_rows:
            group = row.get("superset_group")
            order = row.get("superset_order")
            if isinstance(group, int) and isinstance(order, int):
                group_orders[group].append(order)
        if any(sorted(orders) != [1, 2] for orders in group_orders.values()):
            _append_issue(
                global_issues,
                "superset_complete",
                "blocking",
                f"Суперсет в неделе {week_number}, дне {day_number} должен содержать ровно две позиции",
            )

    if layout_version != PROGRAM_IMPORT_CANONICAL_LAYOUT and len(days) > 0:
        rows_by_week_day = {
            key: sorted(day_rows, key=lambda row: row["row_number"])
            for key, day_rows in days.items()
        }
        saw_weekly_exercise_variation = False
        for week_number in range(2, duration_weeks + 1):
            for day_number in expected_days or []:
                previous = rows_by_week_day.get((1, day_number), [])
                current = rows_by_week_day.get((week_number, day_number), [])
                if len(previous) != len(current):
                    _append_issue(
                        global_issues,
                        "weekly_structure_incomplete",
                        "blocking",
                        "Количество упражнений в одном из дней отличается между неделями",
                    )
                    break
                if any(
                    previous_row.get("resolved_exercise_id")
                    != current_row.get("resolved_exercise_id")
                    for previous_row, current_row in zip(previous, current, strict=True)
                    if isinstance(previous_row.get("resolved_exercise_id"), int)
                    and isinstance(current_row.get("resolved_exercise_id"), int)
                ):
                    saw_weekly_exercise_variation = True
        if saw_weekly_exercise_variation:
            _append_issue(
                global_issues,
                "weekly_exercise_variation",
                "warning",
                "В разных неделях меняется упражнение в одной из позиций; замена сохранится в недельном плане",
            )

    if any(row.get("name_normalized") for row in rows):
        _append_issue(
            global_issues,
            "exercise_name_normalized",
            "warning",
            "Часть названий нормализована для сопоставления; исходные уточнения сохранены в заметках",
        )
    if any(row.get("source_alias_used") for row in rows):
        _append_issue(
            global_issues,
            "exercise_source_alias",
            "warning",
            "Часть названий сопоставлена по детерминированным русским алиасам каталога",
        )

    all_issues = list(global_issues) + [issue for row in rows for issue in row.get("issues", [])]
    for issue in global_issues:
        _attach_source_coordinates(issue, rows)
    for row in rows:
        for issue in row.get("issues", []):
            _attach_source_coordinates(issue, rows)
    blocking_count = sum(issue["severity"] == "blocking" for issue in all_issues)
    warning_count = sum(issue["severity"] == "warning" for issue in all_issues)
    matched_count = sum(row.get("match_status") == "matched" for row in rows)
    draft: _Draft = {
        "source_format": source_format,
        "schema_version": PROGRAM_IMPORT_SCHEMA_VERSION,
        "parser_version": PROGRAM_IMPORT_PARSER_VERSION,
        "layout_version": layout_version,
        "duration_weeks": duration_weeks,
        "program_title": title,
        "goal": goal,
        "level": level,
        "rows": rows,
        "issues": global_issues,
        "summary": {
            "row_count": len(rows),
            "cell_count": cell_count,
            "matched_row_count": matched_count,
            "unresolved_row_count": len(rows) - matched_count,
            "blocking_issue_count": blocking_count,
            "warning_count": warning_count,
        },
    }
    if ai_metadata is not None:
        draft["ai"] = dict(ai_metadata)
    return draft


def _program_import_ai_port() -> ProgramImportAiPort:
    if not settings.program_import_ai_enabled:
        return DisabledProgramImportAiPort("disabled")
    if settings.program_import_ai_data_policy != "synthetic_only":
        return DisabledProgramImportAiPort("policy_blocked")
    # No provider adapter is wired by this task.  Enabling the flag cannot turn
    # a user document into an outbound request accidentally.
    return DisabledProgramImportAiPort("unavailable")


def _ai_metadata(
    status: str,
    *,
    attempts: int = 0,
    proposal_count: int = 0,
    candidate_rerank_count: int = 0,
    conflict_count: int = 0,
) -> dict[str, object]:
    return {
        "contract_version": PROGRAM_IMPORT_AI_CONTRACT_VERSION,
        "prompt_version": PROGRAM_IMPORT_AI_PROMPT_VERSION,
        "status": status,
        "attempts": attempts,
        "proposal_count": proposal_count,
        "candidate_rerank_count": candidate_rerank_count,
        "conflict_count": conflict_count,
        "fallback": "deterministic_manual",
    }


_AI_PROPOSABLE_FIELDS: Final = (
    "program_title",
    "goal",
    "level",
    "day_number",
    "day_title",
    "prescribed_sets",
    "prescribed_reps",
    "prescribed_duration_minutes",
    "rest_seconds",
    "notes",
)


def _ai_unresolved_fields(row: _RowDraft) -> tuple[str, ...]:
    fields: list[str] = []
    for field in (
        "program_title",
        "goal",
        "level",
        "day_number",
        "day_title",
        "prescribed_sets",
        "prescribed_reps",
        "prescribed_duration_minutes",
    ):
        if field in {"prescribed_sets", "prescribed_reps"} and row.get("metric_type") == "cardio":
            continue
        if field == "prescribed_duration_minutes" and row.get("metric_type") != "cardio":
            continue
        if row.get(field) in (None, ""):
            fields.append(field)
    if row.get("match_status") != "matched":
        fields.append("exercise_mapping")
    return tuple(dict.fromkeys(fields))


def _ai_source_evidence(
    row: _RowDraft,
    unresolved_fields: tuple[str, ...],
) -> str | None:
    """Build the minimum normalized evidence needed for the unresolved fields.

    The deterministic draft may carry richer evidence while parsing, but a
    future provider adapter must not receive optional notes, auxiliary load
    values or other unrelated cells just because they share a source row.
    """

    context_fields = tuple(dict.fromkeys(("exercise_name", *unresolved_fields)))
    values = [
        (field, value)
        for field in context_fields
        if (value := _optional_text(row.get(field))) is not None
    ]
    if len(values) == 1 and values[0][0] == "exercise_name":
        return values[0][1]
    return _optional_text(" | ".join(f"{field}: {value}" for field, value in values)[:512])


def _build_ai_request(
    draft: _Draft,
    *,
    source_format: str,
) -> tuple[ProgramImportAiRequest | None, dict[str, ProgramImportAiSourceSpan]]:
    contexts: list[ProgramImportAiRowContext] = []
    source_spans: list[ProgramImportAiSourceSpan] = []
    evidence_by_id: dict[str, ProgramImportAiSourceSpan] = {}
    for row in draft["rows"]:
        unresolved_fields = _ai_unresolved_fields(row)
        if not unresolved_fields:
            continue
        source_evidence = _ai_source_evidence(row, unresolved_fields)
        evidence_id = f"source:{source_format}:{row['row_number']}"
        if source_evidence is None or len(source_spans) >= 32:
            continue
        span = ProgramImportAiSourceSpan(
            evidence_id=evidence_id,
            location=str(row.get("source_range") or f"строка {row['row_number']}"),
            text=source_evidence,
        )
        source_spans.append(span)
        evidence_by_id[evidence_id] = span
        context_fields = {"exercise_name", *unresolved_fields}
        fields = {
            field: str(row[field])
            for field in (
                "program_title",
                "goal",
                "level",
                "day_number",
                "day_title",
                "exercise_name",
                "prescribed_sets",
                "prescribed_reps",
                "prescribed_duration_minutes",
                "rest_seconds",
                "notes",
            )
            if field in context_fields and row.get(field) not in (None, "")
        }
        candidate_ids = tuple(
            candidate["exercise_id"]
            for candidate in row.get("candidates", [])
            if isinstance(candidate.get("exercise_id"), int)
        )
        contexts.append(
            ProgramImportAiRowContext(
                row_number=row["row_number"],
                unresolved_fields=unresolved_fields,
                fields=cast(dict[str, str], fields),
                candidate_exercise_ids=candidate_ids[:5],
            )
        )
    if not contexts:
        return None, evidence_by_id
    locale = "ru"
    if any(
        any("a" <= character.casefold() <= "z" for character in span.text) for span in source_spans
    ):
        locale = "mixed"
    return (
        ProgramImportAiRequest(
            source_format=cast(Literal["csv", "xlsx", "txt", "docx"], source_format),
            locale=cast(Literal["ru", "en", "mixed"], locale),
            source_spans=tuple(source_spans),
            rows=tuple(contexts),
        ),
        evidence_by_id,
    )


def _ai_value(field: str, value: str) -> object | None:
    if field in {
        "day_number",
        "prescribed_sets",
        "prescribed_duration_minutes",
        "rest_seconds",
    }:
        parsed = _parse_integer_text(value)
        if parsed is None:
            return None
        numeric_limits: dict[str, tuple[int, int]] = {
            "day_number": (1, 8),
            "prescribed_sets": (1, 10),
            "prescribed_duration_minutes": (1, 600),
            "rest_seconds": (0, 600),
        }
        minimum, maximum = numeric_limits[field]
        return parsed if minimum <= parsed <= maximum else None
    if field == "goal":
        return (
            value if value in {"muscle_gain", "fat_loss", "maintenance", "recomposition"} else None
        )
    if field == "level":
        return value if value in {"beginner", "intermediate", "advanced"} else None
    text_limits: dict[str, int] = {
        "program_title": 128,
        "day_title": 128,
        "prescribed_reps": 32,
        "notes": 2_000,
    }
    text_maximum = text_limits.get(field)
    if text_maximum is None:
        return None
    normalized = _optional_text(value)
    return normalized if normalized is not None and len(normalized) <= text_maximum else None


def _ai_row_field_is_present(row: _RowDraft, field: str) -> bool:
    if field == "rest_seconds" and row.get("rest_defaulted"):
        return False
    return row.get(field) not in (None, "")


def _append_ai_proposal(
    row: _RowDraft,
    proposal: ProgramImportAiProposal,
    evidence: ProgramImportAiSourceSpan,
    *,
    applied: bool,
) -> None:
    row.setdefault("ai_proposals", []).append(
        {
            "field": proposal.field,
            "value": proposal.value,
            "evidence_id": evidence.evidence_id,
            "source_location": evidence.location,
            "source_text": evidence.text,
            "rationale": proposal.rationale,
            "applied": applied,
        }
    )


def _apply_ai_response(
    rows: list[_RowDraft],
    response: ProgramImportAiResponse,
    evidence_by_id: dict[str, ProgramImportAiSourceSpan],
) -> tuple[int, int, int, bool]:
    row_by_number = {row["row_number"]: row for row in rows}
    applied_count = 0
    rerank_count = 0
    conflict_count = 0
    invalid_output = False
    metadata_fields = {"program_title", "goal", "level"}
    for proposal in response.proposals:
        row = row_by_number.get(proposal.row_number)
        evidence = evidence_by_id.get(proposal.evidence_id)
        if row is None or evidence is None:
            conflict_count += 1
            invalid_output = True
            continue
        if len(row.get("ai_proposals", [])) >= 20:
            conflict_count += 1
            invalid_output = True
            continue
        if proposal.field == "exercise_mapping":
            # The proposal is intentionally visible but never changes the selected
            # exercise.  Ambiguity always remains a manual user decision.
            _append_ai_proposal(row, proposal, evidence, applied=False)
            continue
        if proposal.field not in _AI_PROPOSABLE_FIELDS:
            conflict_count += 1
            invalid_output = True
            continue
        value = _ai_value(proposal.field, proposal.value)
        if value is None:
            conflict_count += 1
            invalid_output = True
            continue
        target_rows = rows if proposal.field in metadata_fields else [row]
        if any(
            _ai_row_field_is_present(target, proposal.field) and target.get(proposal.field) != value
            for target in target_rows
        ):
            conflict_count += 1
            _append_ai_proposal(row, proposal, evidence, applied=False)
            continue
        if all(target.get(proposal.field) == value for target in target_rows):
            _append_ai_proposal(row, proposal, evidence, applied=False)
            continue
        for target in target_rows:
            cast(dict[str, object], target)[proposal.field] = value
            if proposal.field == "rest_seconds":
                target["rest_defaulted"] = False
        _append_ai_proposal(row, proposal, evidence, applied=True)
        applied_count += 1

    for rerank in response.candidate_reranks:
        row = row_by_number.get(rerank.row_number)
        if row is None:
            conflict_count += 1
            invalid_output = True
            continue
        candidates = row.get("candidates", [])
        candidate_by_id = {
            candidate["exercise_id"]: candidate
            for candidate in candidates
            if isinstance(candidate.get("exercise_id"), int)
        }
        requested = tuple(rerank.candidate_ids)
        if (
            not candidate_by_id
            or set(requested) != set(candidate_by_id)
            or len(requested) != len(candidate_by_id)
        ):
            conflict_count += 1
            invalid_output = True
            continue
        row["candidates"] = [candidate_by_id[candidate_id] for candidate_id in requested]
        row["ai_candidate_order"] = list(requested)
        row["ai_rerank_reason"] = rerank.rationale or None
        rerank_count += 1
    return applied_count, rerank_count, conflict_count, invalid_output


def _ai_warning(status: str) -> tuple[str, str, str] | None:
    messages = {
        "disabled": "AI-помощь отключена; используйте детерминированный предпросмотр и ручное разрешение",
        "policy_blocked": "AI-помощь недоступна по политике данных; исходный документ не отправлялся наружу",
        "unavailable": "AI-помощь временно недоступна; продолжайте с детерминированным предпросмотром и ручным разрешением",
        "invalid_output": "Предложение AI отклонено проверкой; исходные детерминированные значения сохранены",
    }
    message = messages.get(status)
    return ("ai_assistance_unavailable", "warning", message) if message else None


def _run_ai_assistance(
    db: Session,
    current_user: User,
    *,
    draft: _Draft,
    source_format: str,
    layout_warnings: tuple[tuple[str, str, str], ...],
    ai_port: ProgramImportAiPort | None,
) -> _Draft:
    request, evidence_by_id = _build_ai_request(draft, source_format=source_format)
    if request is None:
        draft["ai"] = _ai_metadata("not_needed")
        return draft
    port = ai_port or _program_import_ai_port()
    try:
        response = ProgramImportAiResponse.model_validate(port.propose(request))
    except Exception:
        logger.warning(
            "program_import_ai_unavailable",
            extra={"source_format": source_format, "reason": "port_error"},
        )
        response = ProgramImportAiResponse(status="unavailable", attempts=1)

    if response.status not in {"proposed", "no_change"}:
        response = ProgramImportAiResponse(status=response.status, attempts=response.attempts)

    working_rows = [cast(_RowDraft, dict(row)) for row in draft["rows"]]
    applied_count, rerank_count, conflict_count, invalid_output = _apply_ai_response(
        working_rows, response, evidence_by_id
    )
    status = response.status
    if invalid_output:
        status = "invalid_output"
    elif response.status == "proposed" and not (
        applied_count or rerank_count or response.proposals
    ):
        status = "no_change"
    warning = _ai_warning(status)
    warnings = layout_warnings + ((warning,) if warning is not None else ())
    ai_info = _ai_metadata(
        status,
        attempts=response.attempts,
        proposal_count=len(response.proposals),
        candidate_rerank_count=rerank_count,
        conflict_count=conflict_count,
    )
    return _build_draft(
        db,
        current_user,
        source_format=source_format,
        cell_count=draft["summary"]["cell_count"],
        raw_rows=working_rows,
        layout_version=draft["layout_version"],
        duration_weeks=draft["duration_weeks"],
        layout_warnings=warnings,
        ai_metadata=ai_info,
    )


def parse_program_import(
    db: Session,
    current_user: User,
    *,
    source: bytes,
    source_format: str,
    ai_port: ProgramImportAiPort | None = None,
) -> _Draft:
    started = time.perf_counter()
    if len(source) > settings.program_import_max_file_bytes:
        raise ProgramImportError("file_too_large", "Файл превышает допустимый размер", 413)
    table: _Table | None = None
    document_lines: tuple[_DocumentLine, ...] | None = None
    if source_format == "csv":
        table = _parse_csv(source)
    elif source_format == "xlsx":
        table = _parse_xlsx(source)
    elif source_format == "txt":
        document_lines = _parse_txt(source)
    elif source_format == "docx":
        document_lines = _parse_docx(source)
    else:
        raise ProgramImportError(
            "format_unsupported", "Поддерживаются файлы XLSX, CSV, TXT и DOCX", 415
        )

    raw_rows: list[_RowDraft] = []
    if document_lines is not None:
        extracted_rows, duration_weeks, layout_warnings, layout_version = _extract_document_rows(
            document_lines,
            source_format=source_format,
        )
        cell_count = sum(
            len(line.cells) if line.table_id is not None else 1 for line in document_lines
        )
    else:
        assert table is not None
        extracted_rows, duration_weeks, layout_warnings, layout_version = _extract_layout_rows(
            table
        )
        cell_count = table.cell_count
    if extracted_rows:
        for extracted in extracted_rows:
            row_number = extracted.row_number if extracted.row_number >= 3 else len(raw_rows) + 3
            source_sheet = extracted.source_sheet or (
                table.sheet_name if table is not None else None
            )
            parsed_row, row_issues = _row_from_values(
                row_number=row_number,
                source_sheet=source_sheet,
                source_range=extracted.source_range,
                source_cells=extracted.source_cells,
                values=extracted.values,
            )
            parsed_row["source_row"] = extracted.source_row
            parsed_row["week_number"] = extracted.week_number
            parsed_row["source_auxiliary"] = extracted.source_auxiliary
            parsed_row["resolution_key"] = extracted.resolution_key
            parsed_row["exercise_match_name"] = extracted.exercise_match_name
            parsed_row["program_title"] = _optional_text(extracted.values.get("program_title"))
            parsed_row["goal"] = _optional_text(extracted.values.get("goal"))
            parsed_row["level"] = _optional_text(extracted.values.get("level"))
            parsed_row["source_evidence"] = (
                extracted.source_evidence
                or _text(
                    " | ".join(
                        f"{field}: {value}"
                        for field, value in extracted.values.items()
                        if _optional_text(value) is not None
                    )
                )[:512]
            )
            parsed_row["parse_issues"] = row_issues
            raw_rows.append(parsed_row)
    elif table is not None:
        values_by_column = {field: index for index, field in enumerate(table.header)}
        for row_number, values in table.rows:
            if not any(_text(value) for value in values):
                continue
            row_values = {field: values[index] for field, index in values_by_column.items()}
            source_cells = {
                field: f"{_xlsx_column_label(index + 1)}{row_number}"
                for field, index in values_by_column.items()
            }
            parsed_row, row_issues = _row_from_values(
                row_number=row_number,
                source_sheet=table.sheet_name,
                source_range=f"A{row_number}:{_xlsx_column_label(len(table.header))}{row_number}",
                source_cells=source_cells,
                values=row_values,
            )
            parsed_row["source_row"] = row_number
            parsed_row["week_number"] = None
            parsed_row["resolution_key"] = f"canonical|{row_number}"
            parsed_row["program_title"] = _optional_text(row_values.get("program_title"))
            parsed_row["goal"] = _optional_text(row_values.get("goal"))
            parsed_row["level"] = _optional_text(row_values.get("level"))
            parsed_row["source_evidence"] = _text(
                " | ".join(
                    f"{field}: {value}"
                    for field, value in row_values.items()
                    if _optional_text(value) is not None
                )
            )[:512]
            parsed_row["parse_issues"] = row_issues
            raw_rows.append(parsed_row)
    # Empty lines are intentionally ignored. Their presence does not alter the
    # canonical order or create a false exercise row.
    for row in raw_rows:
        row.setdefault("parse_issues", [])
    draft = _build_draft(
        db,
        current_user,
        source_format=source_format,
        cell_count=cell_count,
        raw_rows=raw_rows,
        layout_version=layout_version,
        duration_weeks=duration_weeks,
        layout_warnings=layout_warnings,
    )
    draft = _run_ai_assistance(
        db,
        current_user,
        draft=draft,
        source_format=source_format,
        layout_warnings=layout_warnings,
        ai_port=ai_port,
    )
    for row in draft["rows"]:
        row.pop("source_evidence", None)
        row.pop("rest_defaulted", None)
    elapsed = time.perf_counter() - started
    if elapsed > settings.program_import_parse_timeout_seconds:
        raise ProgramImportError("parse_timeout", "Файл не удалось разобрать в установленный срок")
    return draft


def _public_row(row: _RowDraft) -> dict[str, object]:
    return {
        key: value
        for key, value in row.items()
        if key
        not in {
            "manual_exercise_id",
            "program_title",
            "goal",
            "level",
            "parse_issues",
            "source_row",
            "resolution_key",
            "exercise_match_name",
            "name_normalized",
            "source_alias_used",
            "source_evidence",
            "rest_defaulted",
            "ai_candidate_order",
        }
    }


def _public_issue(issue: _Issue) -> dict[str, object]:
    return {key: value for key, value in issue.items() if key != "row_number"}


def _document_format(import_row: ProgramImport) -> str:
    return import_row.document_format or import_row.source_format


def serialize_import(import_row: ProgramImport) -> dict[str, object]:
    draft: _Draft | None = (
        cast(_Draft, import_row.draft_json) if import_row.status == "pending" else None
    )
    rows = draft["rows"] if draft is not None else []
    global_issues = draft["issues"] if draft is not None else []
    row_list = [_public_row(row) for row in rows]
    row_issues = [issue for row in rows for issue in row.get("issues", [])]
    issues = [_public_issue(issue) for issue in global_issues] + [
        _public_issue(issue) for issue in row_issues
    ]
    summary = dict(draft["summary"]) if draft is not None else {}
    summary.update(
        {
            "row_count": import_row.row_count,
            "cell_count": import_row.cell_count,
            "blocking_issue_count": import_row.blocking_issue_count,
            "warning_count": import_row.warning_count,
            "matched_row_count": sum(row.get("match_status") == "matched" for row in row_list),
            "unresolved_row_count": sum(row.get("match_status") != "matched" for row in row_list),
        }
    )
    return {
        "id": import_row.id,
        "status": import_row.status,
        "source_format": _document_format(import_row),
        "schema_version": import_row.schema_version,
        "parser_version": import_row.parser_version,
        "layout_version": draft.get("layout_version") if draft is not None else None,
        "duration_weeks": draft.get("duration_weeks") if draft is not None else None,
        "expires_at": import_row.expires_at,
        "program_title": draft["program_title"] if draft is not None else None,
        "goal": draft["goal"] if draft is not None else None,
        "level": draft["level"] if draft is not None else None,
        "rows": row_list if import_row.status == "pending" else [],
        "issues": issues if import_row.status == "pending" else [],
        "summary": summary,
        "ai": draft.get("ai") if draft is not None else None,
    }


def expire_program_imports(
    db: Session,
    *,
    owner_user_id: int | None = None,
    now: datetime | None = None,
) -> int:
    current = now or now_msk_naive()
    query = db.query(ProgramImport).filter(
        ProgramImport.status == "pending",
        ProgramImport.expires_at <= current,
    )
    if owner_user_id is not None:
        query = query.filter(ProgramImport.owner_user_id == owner_user_id)
    rows = (
        query.order_by(ProgramImport.expires_at.asc(), ProgramImport.id.asc())
        .limit(settings.program_import_cleanup_batch_size)
        .all()
    )
    for row in rows:
        row.status = "expired"
        row.draft_json = {}
        row.updated_at = current
        record_audit_event(
            db,
            actor_user_id=row.owner_user_id,
            target_user_id=row.owner_user_id,
            action="program_import.expired",
            resource_type="program_import",
            resource_id=row.id,
            details={"source_format": _document_format(row), "row_count": row.row_count},
        )
    if rows:
        db.flush()
    return len(rows)


def create_program_import(
    db: Session,
    current_user: User,
    *,
    source: bytes,
    source_format: str,
) -> ProgramImport:
    source_format = _text(source_format).casefold()
    if source_format not in PROGRAM_IMPORT_SUPPORTED_FORMATS:
        raise ProgramImportError(
            "format_unsupported", "Поддерживаются файлы XLSX, CSV, TXT и DOCX", 415
        )
    expire_program_imports(db, owner_user_id=current_user.id)
    source_sha256 = hashlib.sha256(source).hexdigest()
    duplicate = (
        db.query(ProgramImport)
        .filter(
            ProgramImport.owner_user_id == current_user.id,
            ProgramImport.source_sha256 == source_sha256,
            ProgramImport.status == "pending",
            ProgramImport.expires_at > now_msk_naive(),
        )
        .first()
    )
    if duplicate is not None:
        raise ProgramImportError("duplicate_upload", "Такой файл уже ожидает подтверждения", 409)
    draft = parse_program_import(
        db,
        current_user,
        source=source,
        source_format=source_format,
    )
    current = now_msk_naive()
    stored_source_format = source_format if source_format in {"csv", "xlsx"} else "csv"
    import_row = ProgramImport(
        id=str(uuid4()),
        owner_user_id=current_user.id,
        source_format=stored_source_format,
        document_format=source_format if source_format not in {"csv", "xlsx"} else None,
        source_sha256=source_sha256,
        schema_version=PROGRAM_IMPORT_SCHEMA_VERSION,
        parser_version=PROGRAM_IMPORT_PARSER_VERSION,
        status="pending",
        draft_json=draft,
        row_count=draft["summary"]["row_count"],
        cell_count=draft["summary"]["cell_count"],
        blocking_issue_count=draft["summary"]["blocking_issue_count"],
        warning_count=draft["summary"]["warning_count"],
        expires_at=current + timedelta(minutes=settings.program_import_draft_ttl_minutes),
    )
    db.add(import_row)
    record_audit_event(
        db,
        actor_user_id=current_user.id,
        target_user_id=current_user.id,
        action="program_import.previewed",
        resource_type="program_import",
        resource_id=import_row.id,
        details={
            "source_format": source_format,
            "schema_version": PROGRAM_IMPORT_SCHEMA_VERSION,
            "parser_version": PROGRAM_IMPORT_PARSER_VERSION,
            "row_count": import_row.row_count,
            "cell_count": import_row.cell_count,
            "blocking_issue_count": import_row.blocking_issue_count,
            "warning_count": import_row.warning_count,
        },
    )
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", "")
        if (
            constraint_name == "uq_program_imports_pending_hash"
            or "uq_program_imports_pending_hash" in str(exc)
            or "program_imports.owner_user_id, program_imports.source_sha256" in str(exc)
        ):
            raise ProgramImportError(
                "duplicate_upload", "Такой файл уже ожидает подтверждения", 409
            ) from exc
        raise
    return import_row


def get_program_import(
    db: Session,
    current_user: User,
    import_id: str,
    *,
    for_update: bool = False,
) -> ProgramImport:
    query = db.query(ProgramImport).filter(
        ProgramImport.id == import_id,
        ProgramImport.owner_user_id == current_user.id,
    )
    if for_update:
        query = query.with_for_update()
    import_row = query.first()
    if import_row is None:
        raise ProgramImportError("import_not_found", "Импорт не найден", 404)
    if import_row.status == "pending" and import_row.expires_at <= now_msk_naive():
        import_row.status = "expired"
        import_row.draft_json = {}
        import_row.updated_at = now_msk_naive()
        record_audit_event(
            db,
            actor_user_id=current_user.id,
            target_user_id=current_user.id,
            action="program_import.expired",
            resource_type="program_import",
            resource_id=import_row.id,
            details={
                "source_format": _document_format(import_row),
                "row_count": import_row.row_count,
            },
        )
        db.commit()
        raise ProgramImportError("import_expired", "Срок действия предпросмотра истёк", 410)
    return import_row


def resolve_program_import(
    db: Session,
    current_user: User,
    import_id: str,
    *,
    title: str | None,
    goal: str | None,
    level: str | None,
    row_resolutions: list[tuple[int, int | None]],
) -> ProgramImport:
    import_row = get_program_import(db, current_user, import_id, for_update=True)
    if import_row.status != "pending":
        raise ProgramImportError("import_not_editable", "Этот импорт больше нельзя изменить", 409)
    draft = cast(_Draft, dict(import_row.draft_json))
    rows = [cast(_RowDraft, dict(row)) for row in draft["rows"]]
    row_by_number = {row["row_number"]: row for row in rows}
    for row_number, exercise_id in row_resolutions:
        row = row_by_number.get(row_number)
        if row is None:
            raise ProgramImportError("row_not_found", "Строка импорта не найдена")
        row["manual_exercise_id"] = exercise_id
        resolution_key = row.get("resolution_key")
        if resolution_key:
            for related_row in rows:
                if related_row.get("resolution_key") == resolution_key:
                    related_row["manual_exercise_id"] = exercise_id
    if title is not None:
        draft["program_title"] = title.strip()
        for row in rows:
            row["program_title"] = draft["program_title"]
    if goal is not None:
        draft["goal"] = goal
        for row in rows:
            row["goal"] = goal
    if level is not None:
        draft["level"] = level
        for row in rows:
            row["level"] = level
    rebuilt = _build_draft(
        db,
        current_user,
        source_format=_document_format(import_row),
        cell_count=import_row.cell_count,
        raw_rows=rows,
        layout_version=draft.get("layout_version", PROGRAM_IMPORT_CANONICAL_LAYOUT),
        duration_weeks=draft.get("duration_weeks", 1),
        layout_warnings=tuple(
            (
                str(issue.get("code", "layout_warning")),
                str(issue.get("severity", "warning")),
                str(issue.get("message", "")),
            )
            for issue in draft.get("issues", [])
            if issue.get("severity") == "warning"
        ),
        ai_metadata=draft.get("ai"),
    )
    import_row.draft_json = dict(rebuilt)
    import_row.blocking_issue_count = rebuilt["summary"]["blocking_issue_count"]
    import_row.warning_count = rebuilt["summary"]["warning_count"]
    import_row.updated_at = now_msk_naive()
    db.commit()
    return import_row


def _program_payload_from_draft(draft: _Draft) -> ProgramTemplateCreate:
    rows = draft["rows"]
    if draft.get("duration_weeks", 1) > 1:
        rows = [row for row in rows if (row.get("week_number") or 1) == 1]
    days: dict[int, list[_RowDraft]] = defaultdict(list)
    for row in rows:
        day_number = row.get("day_number")
        if not isinstance(day_number, int):
            raise ProgramImportError("domain_invalid", "Номер дня не заполнен")
        days[day_number].append(row)
    day_payloads: list[ProgramTemplateDayCreate] = []
    for day_number in sorted(days):
        day_rows = sorted(days[day_number], key=lambda row: row["row_number"])
        title = _optional_text(day_rows[0].get("day_title"))
        if title is None:
            raise ProgramImportError("domain_invalid", f"Название дня {day_number} не заполнено")
        exercises: list[ProgramTemplateExerciseCreate] = []
        for row in day_rows:
            resolved_id = row.get("resolved_exercise_id")
            if not isinstance(resolved_id, int):
                raise ProgramImportError(
                    "domain_invalid", "Все упражнения должны быть сопоставлены"
                )
            rest_seconds = row.get("rest_seconds")
            exercises.append(
                ProgramTemplateExerciseCreate(
                    exercise_id=resolved_id,
                    prescribed_sets=row.get("prescribed_sets"),
                    prescribed_reps=_optional_text(row.get("prescribed_reps")),
                    prescribed_duration_minutes=row.get("prescribed_duration_minutes"),
                    rest_seconds=90 if rest_seconds is None else rest_seconds,
                    notes=_optional_text(row.get("notes")),
                    superset_group=row.get("superset_group"),
                    superset_order=row.get("superset_order"),
                )
            )
        day_payloads.append(ProgramTemplateDayCreate(title=title, exercises=exercises))
    title = _optional_text(draft["program_title"])
    goal = _optional_text(draft["goal"])
    level = _optional_text(draft["level"])
    if title is None or goal is None or level is None:
        raise ProgramImportError("domain_invalid", "Заполните название, цель и уровень программы")
    return ProgramTemplateCreate.model_validate(
        {
            "title": title,
            "goal": goal,
            "level": level,
            "mode": "self",
            "days": day_payloads,
            "assign_after_create": False,
        }
    )


def _same_weekly_exercise(base_row: _RowDraft, source_row: _RowDraft) -> bool:
    base_key = base_row.get("resolution_key")
    source_key = source_row.get("resolution_key")
    if base_key and source_key and base_key == source_key:
        return True
    base_id = base_row.get("resolved_exercise_id")
    source_id = source_row.get("resolved_exercise_id")
    return isinstance(base_id, int) and base_id == source_id


def _align_weekly_rows(base_rows: list[_RowDraft], source_rows: list[_RowDraft]) -> list[_RowDraft]:
    """Align a week's rows to week one's physical exercise slots.

    Exercise substitutions remain positional when no stable identity is available.
    Matching known identities first also makes ordinary row reordering safe without
    allowing one substitution to steal a later exercise's prescription.
    """
    remaining = list(source_rows)
    aligned: list[_RowDraft] = []
    for position, base_row in enumerate(base_rows):
        matching_index = next(
            (
                index
                for index, source_row in enumerate(remaining)
                if _same_weekly_exercise(base_row, source_row)
            ),
            None,
        )
        if matching_index is None:
            future_base_rows = base_rows[position + 1 :]
            reserved_indices = {
                index
                for index, source_row in enumerate(remaining)
                if any(_same_weekly_exercise(future, source_row) for future in future_base_rows)
            }
            preferred_index = position if position < len(remaining) else None
            if preferred_index is not None and preferred_index not in reserved_indices:
                matching_index = preferred_index
            else:
                matching_index = next(
                    (index for index in range(len(remaining)) if index not in reserved_indices),
                    0,
                )
        aligned.append(remaining.pop(matching_index))
    return aligned


def _create_weekly_prescriptions(
    db: Session,
    template: ProgramTemplate,
    draft: _Draft,
    owner: User,
) -> None:
    duration_weeks = draft.get("duration_weeks", 1)
    if duration_weeks <= 1:
        return
    visible_by_effective_id = get_visible_exercise_display_map(db, owner)
    rows_by_day_week: dict[tuple[int, int], list[_RowDraft]] = defaultdict(list)
    for row in draft["rows"]:
        day_number = row.get("day_number")
        if not isinstance(day_number, int):
            raise ProgramError("Номер дня недельного назначения не заполнен")
        week_number = row.get("week_number") or 1
        rows_by_day_week[(week_number, day_number)].append(row)

    days_by_number = {day.day_number: day for day in template.days}
    for day_number, day in days_by_number.items():
        base_exercises = sorted(day.exercises, key=lambda row: row.sort_order)
        base_source_rows = sorted(
            rows_by_day_week.get((1, day_number), []),
            key=lambda row: row["row_number"],
        )
        for week_number in range(1, duration_weeks + 1):
            source_rows = sorted(
                rows_by_day_week.get((week_number, day_number), []),
                key=lambda row: row["row_number"],
            )
            if len(source_rows) != len(base_exercises):
                raise ProgramError(
                    f"Недельное назначение для дня {day_number} имеет неполный состав упражнений"
                )
            source_rows = _align_weekly_rows(base_source_rows, source_rows)
            for source_row, template_exercise in zip(source_rows, base_exercises, strict=True):
                resolved_id = source_row.get("resolved_exercise_id")
                if not isinstance(resolved_id, int):
                    raise ProgramError("Упражнение недельного назначения не сопоставлено")
                exercise = visible_by_effective_id.get(resolved_id)
                if exercise is None:
                    raise ProgramError("Exercise is not available for imported program")
                rest_seconds = source_row.get("rest_seconds")
                prescription = normalize_exercise_prescription(
                    exercise,
                    prescribed_sets=source_row.get("prescribed_sets"),
                    prescribed_reps=_optional_text(source_row.get("prescribed_reps")),
                    prescribed_duration_minutes=source_row.get("prescribed_duration_minutes"),
                    rest_seconds=90 if rest_seconds is None else rest_seconds,
                )
                db.add(
                    ProgramTemplateExerciseWeekPrescription(
                        template_exercise_id=template_exercise.id,
                        exercise_id=resolved_id,
                        week_number=week_number,
                        prescribed_sets=prescription.prescribed_sets,
                        prescribed_reps=prescription.prescribed_reps,
                        prescribed_duration_minutes=prescription.prescribed_duration_minutes,
                        rest_seconds=prescription.rest_seconds,
                    )
                )
    template.default_duration_weeks = duration_weeks
    db.flush()


def confirm_program_import(
    db: Session,
    current_user: User,
    import_id: str,
) -> tuple[ProgramImport, ProgramTemplate]:
    import_row = get_program_import(db, current_user, import_id, for_update=True)
    if import_row.status == "confirmed" and import_row.confirmed_template_id is not None:
        template = (
            db.query(ProgramTemplate)
            .filter(ProgramTemplate.id == import_row.confirmed_template_id)
            .first()
        )
        if template is None:
            raise ProgramImportError(
                "confirmed_template_missing", "Результат подтверждённого импорта недоступен", 409
            )
        return import_row, template
    if import_row.status != "pending":
        raise ProgramImportError(
            "import_not_confirmable", "Этот импорт больше нельзя подтвердить", 409
        )

    draft = cast(_Draft, dict(import_row.draft_json))
    rebuilt = _build_draft(
        db,
        current_user,
        source_format=_document_format(import_row),
        cell_count=import_row.cell_count,
        raw_rows=[cast(_RowDraft, dict(row)) for row in draft["rows"]],
        layout_version=draft.get("layout_version", PROGRAM_IMPORT_CANONICAL_LAYOUT),
        duration_weeks=draft.get("duration_weeks", 1),
        layout_warnings=tuple(
            (
                str(issue.get("code", "layout_warning")),
                str(issue.get("severity", "warning")),
                str(issue.get("message", "")),
            )
            for issue in draft.get("issues", [])
            if issue.get("severity") == "warning"
        ),
        ai_metadata=draft.get("ai"),
    )
    import_row.draft_json = dict(rebuilt)
    import_row.blocking_issue_count = rebuilt["summary"]["blocking_issue_count"]
    import_row.warning_count = rebuilt["summary"]["warning_count"]
    if import_row.blocking_issue_count:
        db.commit()
        raise ProgramImportError(
            "blocking_issues", "Исправьте блокирующие проблемы в предпросмотре", 409
        )

    try:
        payload = _program_payload_from_draft(rebuilt)
        template = create_template(
            db,
            current_user,
            payload,
            current_user,
            force_private=True,
        )
        _create_weekly_prescriptions(db, template, rebuilt, current_user)
        import_row.status = "confirmed"
        import_row.confirmed_template_id = template.id
        import_row.draft_json = {}
        import_row.updated_at = now_msk_naive()
        record_audit_event(
            db,
            actor_user_id=current_user.id,
            target_user_id=current_user.id,
            action="program_import.confirmed",
            resource_type="program_import",
            resource_id=import_row.id,
            details={
                "source_format": _document_format(import_row),
                "schema_version": import_row.schema_version,
                "parser_version": import_row.parser_version,
                "row_count": import_row.row_count,
                "template_id": template.id,
                "assigned": False,
            },
        )
        db.commit()
    except ProgramImportError:
        db.rollback()
        raise
    except (ProgramError, ValueError) as exc:
        db.rollback()
        raise ProgramImportError("domain_invalid", str(exc)[:500], 422) from exc
    except Exception as exc:
        db.rollback()
        logger.exception("program_import_confirm_failed", extra={"import_id": import_id})
        raise ProgramImportError("confirm_failed", "Не удалось подтвердить импорт", 500) from exc
    return import_row, template


def cancel_program_import(db: Session, current_user: User, import_id: str) -> None:
    import_row = get_program_import(db, current_user, import_id, for_update=True)
    if import_row.status == "confirmed":
        raise ProgramImportError(
            "import_not_cancellable", "Подтверждённый импорт нельзя отменить", 409
        )
    if import_row.status != "pending":
        db.commit()
        return
    import_row.status = "cancelled"
    import_row.draft_json = {}
    import_row.updated_at = now_msk_naive()
    record_audit_event(
        db,
        actor_user_id=current_user.id,
        target_user_id=current_user.id,
        action="program_import.cancelled",
        resource_type="program_import",
        resource_id=import_row.id,
        details={"source_format": _document_format(import_row), "row_count": import_row.row_count},
    )
    db.commit()


def _safe_export_value(value: object) -> str:
    text_value = _text(value)
    if text_value.startswith(("=", "+", "-", "@")):
        return "'" + text_value
    return text_value


def _template_matrix() -> list[list[str]]:
    return [
        [PROGRAM_IMPORT_MARKER, PROGRAM_IMPORT_MARKER_VALUE],
        list(PROGRAM_IMPORT_COLUMNS),
        [
            "Пример импортируемой программы",
            "maintenance",
            "beginner",
            "1",
            "Силовая 1",
            "Приседания без веса",
            "3",
            "8-12",
            "90",
            "",
            "bodyweight-squat",
            "strength",
            "",
            "Безопасный пример: проверьте план перед подтверждением",
            "",
            "",
        ],
    ]


def build_program_import_template(source_format: str) -> tuple[bytes, str, str]:
    if source_format not in PROGRAM_IMPORT_TEMPLATE_FORMATS:
        raise ProgramImportError(
            "format_unsupported", "Канонические шаблоны доступны только для XLSX и CSV", 415
        )
    matrix = _template_matrix()
    if source_format == "csv":
        csv_output = io.StringIO(newline="")
        writer = csv.writer(csv_output, delimiter=",", lineterminator="\n")
        writer.writerows([_safe_export_value(value) for value in row] for row in matrix)
        return (
            csv_output.getvalue().encode("utf-8-sig"),
            "text/csv; charset=utf-8",
            "yfc-program-template-v1.csv",
        )

    def cell_reference(row_number: int, column_number: int) -> str:
        value = column_number
        letters = ""
        while value:
            value, remainder = divmod(value - 1, 26)
            letters = chr(ord("A") + remainder) + letters
        return f"{letters}{row_number}"

    rows_xml: list[str] = []
    for row_number, row in enumerate(matrix, start=1):
        cells: list[str] = []
        for column_number, value in enumerate(row, start=1):
            if value == "":
                continue
            safe_value = html.escape(_safe_export_value(value), quote=False)
            cells.append(
                f'<c r="{cell_reference(row_number, column_number)}" t="inlineStr">'
                f'<is><t xml:space="preserve">{safe_value}</t></is></c>'
            )
        rows_xml.append(f'<row r="{row_number}">{"".join(cells)}</row>')
    worksheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheetData>{''.join(rows_xml)}</sheetData></worksheet>"
    ).encode()
    files = {
        "[Content_Types].xml": (
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            b'<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            b'<Default Extension="xml" ContentType="application/xml"/>'
            b'<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            b'<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            b"</Types>"
        ),
        "_rels/.rels": (
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            b"</Relationships>"
        ),
        "xl/workbook.xml": (
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            b'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            b'<sheets><sheet name="YFC Import" sheetId="1" r:id="rId1"/></sheets></workbook>'
        ),
        "xl/_rels/workbook.xml.rels": (
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            b"</Relationships>"
        ),
        "xl/worksheets/sheet1.xml": worksheet,
    }
    xlsx_output = io.BytesIO()
    with zipfile.ZipFile(xlsx_output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 0
            info.external_attr = 0o600 << 16
            archive.writestr(info, content)
    return (
        xlsx_output.getvalue(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "yfc-program-template-v1.xlsx",
    )
