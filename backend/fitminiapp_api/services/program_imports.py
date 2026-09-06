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
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, TypedDict, cast
from uuid import uuid4
from xml.etree import ElementTree

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fitminiapp_api.core.config import settings
from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.models.exercise import Exercise
from fitminiapp_api.models.program import ProgramTemplate
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
)
from fitminiapp_api.services.exercise_catalog_metadata import (
    CANONICAL_EXERCISE_REDIRECTS,
    exercise_catalog_metadata,
)
from fitminiapp_api.services.program_common import ProgramError
from fitminiapp_api.services.programs import create_template
from fitminiapp_api.services.workout_metrics import (
    exercise_metric_type,
    normalize_exercise_prescription,
)

logger = logging.getLogger(__name__)

PROGRAM_IMPORT_SCHEMA_VERSION: Final = 1
PROGRAM_IMPORT_PARSER_VERSION: Final = "program-import-v1"
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
PROGRAM_IMPORT_SUPPORTED_FORMATS: Final = frozenset({"csv", "xlsx"})
_CONTROL_CHARACTERS = frozenset(chr(value) for value in range(32)) - {"\t", "\r", "\n"}
_INTEGER_PATTERN = re.compile(r"\d+")
_COLUMN_PATTERN = re.compile(r"[A-Z]+")
_CELL_REFERENCE_PATTERN = re.compile(r"([A-Z]+)(\d+)\Z")
_REL_NAMESPACE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
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
class _Table:
    header: tuple[str, ...]
    rows: tuple[tuple[int, tuple[str, ...]], ...]
    cell_count: int
    sheet_name: str | None


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
    source_sheet: str | None
    source_range: str
    source_cells: dict[str, str]
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
    program_title: str | None
    goal: str | None
    level: str | None
    rows: list[_RowDraft]
    issues: list[_Issue]
    summary: _Summary


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
    )


def _parse_csv(source: bytes) -> _Table:
    if not source:
        raise ProgramImportError("empty_file", "Файл пуст")
    if source.startswith((b"\xff\xfe", b"\xfe\xff", b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        raise ProgramImportError("csv_encoding", "CSV должен быть сохранён в UTF-8")
    try:
        text = source.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ProgramImportError("csv_encoding", "CSV должен быть сохранён в UTF-8") from exc
    lines = text.splitlines()
    if lines and ";" in lines[0] and "," not in lines[0]:
        raise ProgramImportError("csv_delimiter", "Поддерживается только разделитель-запятая")
    csv.field_size_limit(settings.program_import_max_cell_chars)
    try:
        rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=",", strict=True))
    except (csv.Error, UnicodeError) as exc:
        raise ProgramImportError(
            "csv_malformed", "CSV содержит некорректные кавычки или строки"
        ) from exc
    if len(rows) < 2:
        raise ProgramImportError("header_missing", "В CSV нужны маркер версии и заголовки")
    raw_rows = [(index, tuple(row)) for index, row in enumerate(rows, start=1)]
    return _validate_table(
        marker=raw_rows[0][1],
        header=raw_rows[1][1],
        rows=raw_rows[2:],
        cell_count=sum(len(row) for _, row in raw_rows),
        sheet_name=None,
    )


def _safe_zip_path(name: str) -> str:
    normalized = name.replace("\\", "/")
    if not normalized or normalized.startswith("/") or ":" in normalized.split("/", 1)[0]:
        raise ProgramImportError("xlsx_path", "XLSX содержит небезопасный путь внутри архива")
    parts = normalized.split("/")
    path_parts = parts[:-1] if parts[-1] == "" else parts
    if any(part in {"", ".", ".."} for part in path_parts):
        raise ProgramImportError("xlsx_path", "XLSX содержит небезопасный путь внутри архива")
    return normalized


def _xml_root(source: bytes, code: str) -> ElementTree.Element:
    lowered = source.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise ProgramImportError("xlsx_xml", "XLSX содержит запрещённую XML-конструкцию")
    try:
        return ElementTree.fromstring(source)
    except ElementTree.ParseError as exc:
        raise ProgramImportError(code, "XLSX содержит некорректный XML") from exc


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
                "xlsx_sheet_count", "Канонический XLSX должен содержать ровно один лист"
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
        for element in sheet_root.iter():
            if _local_name(element.tag) == "mergeCells":
                raise ProgramImportError(
                    "xlsx_merged_cells", "Объединённые ячейки XLSX не поддерживаются"
                )
            if _local_name(element.tag) in {"row", "col"} and element.attrib.get("hidden", "0") in {
                "1",
                "true",
            }:
                raise ProgramImportError(
                    "xlsx_hidden_rows", "Скрытые строки и колонки XLSX не поддерживаются"
                )

        parsed_rows: dict[int, tuple[str, ...]] = {}
        cell_count = 0
        for fallback_row_number, row_element in enumerate(row_elements, start=1):
            raw_row_number = row_element.attrib.get("r", str(fallback_row_number))
            if not _INTEGER_PATTERN.fullmatch(raw_row_number):
                raise ProgramImportError(
                    "xlsx_row_reference", "XLSX содержит некорректный номер строки"
                )
            row_number = int(raw_row_number)
            if row_number > settings.program_import_max_rows + 2:
                raise ProgramImportError("row_limit", "XLSX превышает лимит строк")
            if row_number in parsed_rows:
                raise ProgramImportError("xlsx_duplicate_row", "XLSX содержит дублирующиеся строки")
            values: dict[int, str] = {}
            fallback_column = 1
            for cell in row_element:
                if _local_name(cell.tag) != "c":
                    continue
                cell_count += 1
                if cell_count > settings.program_import_max_cells:
                    raise ProgramImportError("cell_limit", "XLSX превышает лимит ячеек")
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
                if len(value) > settings.program_import_max_cell_chars:
                    raise ProgramImportError(
                        "cell_too_long", "XLSX содержит слишком длинное значение"
                    )
                values[column_number] = value
            width = max(values, default=0)
            parsed_rows[row_number] = tuple(values.get(index, "") for index in range(1, width + 1))

        marker = parsed_rows.get(1)
        header = parsed_rows.get(2)
        data_rows = [
            (row_number, values)
            for row_number, values in sorted(parsed_rows.items())
            if row_number > 2
        ]
        return _validate_table(
            marker=marker,
            header=header,
            rows=data_rows,
            cell_count=cell_count,
            sheet_name=sheet_name,
        )


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
    }
    if row["metric_type"] is not None:
        row["metric_type"] = str(row["metric_type"]).casefold()
    if row["rest_seconds"] is None:
        row["rest_seconds"] = 90
    return row, issues


def _add_domain_range_issues(row: _RowDraft, issues: list[_Issue]) -> None:
    row_number = row["row_number"]
    ranges = (
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
            match_keys = _match_keys(str(row["exercise_name"]))
            for key, _transliterated in match_keys:
                for item in by_key.get(key, []):
                    current = matches_by_id.get(item.exercise_id)
                    if current is None or item.match_type == "title":
                        matches_by_id[item.exercise_id] = item
            if len(matches_by_id) == 1:
                candidate = next(iter(matches_by_id.values()))
                row["match_type"] = candidate.match_type
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
            identity_values = (
                ("exercise_slug", row.get("exercise_slug"), False),
                ("exercise_name", row.get("exercise_name"), True),
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
        if imported_metric is not None and imported_metric not in {"strength", "cardio"}:
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
    source_row = row_number if row_number is not None else None

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
) -> _Draft:
    global_issues: list[_Issue] = []
    rows = [cast(_RowDraft, dict(row)) for row in raw_rows]
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

    days: dict[int, list[_RowDraft]] = defaultdict(list)
    seen_signatures: set[tuple[object, ...]] = set()
    for row in rows:
        day_number = row.get("day_number")
        if isinstance(day_number, int) and 1 <= day_number <= 8:
            days[day_number].append(row)
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

    if len(days) > 8:
        _append_issue(
            global_issues,
            "day_limit",
            "blocking",
            "Программа может содержать не более 8 тренировочных дней",
        )
    if days and sorted(days) != list(range(1, len(days) + 1)):
        _append_issue(
            global_issues,
            "day_sequence",
            "blocking",
            "Номера тренировочных дней должны идти последовательно с 1",
        )
    for day_number, day_rows in days.items():
        if len(day_rows) > 20:
            _append_issue(
                global_issues,
                "exercise_limit",
                "blocking",
                f"В дне {day_number} больше 20 упражнений",
            )
        day_titles = {str(row.get("day_title")) for row in day_rows if row.get("day_title")}
        if len(day_titles) > 1:
            _append_issue(
                global_issues,
                "conflicting_day_title",
                "blocking",
                f"Название дня {day_number} должно быть одинаковым во всех его строках",
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
                f"Суперсет в дне {day_number} должен содержать ровно две позиции",
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
    return {
        "source_format": source_format,
        "schema_version": PROGRAM_IMPORT_SCHEMA_VERSION,
        "parser_version": PROGRAM_IMPORT_PARSER_VERSION,
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


def parse_program_import(
    db: Session,
    current_user: User,
    *,
    source: bytes,
    source_format: str,
) -> _Draft:
    started = time.perf_counter()
    if len(source) > settings.program_import_max_file_bytes:
        raise ProgramImportError("file_too_large", "Файл превышает допустимый размер", 413)
    if source_format == "csv":
        table = _parse_csv(source)
    elif source_format == "xlsx":
        table = _parse_xlsx(source)
    else:
        raise ProgramImportError("format_unsupported", "Поддерживаются только XLSX и CSV", 415)

    values_by_column = {field: index for index, field in enumerate(table.header)}
    raw_rows: list[_RowDraft] = []
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
        parsed_row["program_title"] = _optional_text(row_values.get("program_title"))
        parsed_row["goal"] = _optional_text(row_values.get("goal"))
        parsed_row["level"] = _optional_text(row_values.get("level"))
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
        cell_count=table.cell_count,
        raw_rows=raw_rows,
    )
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
        }
    }


def _public_issue(issue: _Issue) -> dict[str, object]:
    return {key: value for key, value in issue.items() if key != "row_number"}


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
        "source_format": import_row.source_format,
        "schema_version": import_row.schema_version,
        "parser_version": import_row.parser_version,
        "expires_at": import_row.expires_at,
        "program_title": draft["program_title"] if draft is not None else None,
        "goal": draft["goal"] if draft is not None else None,
        "level": draft["level"] if draft is not None else None,
        "rows": row_list if import_row.status == "pending" else [],
        "issues": issues if import_row.status == "pending" else [],
        "summary": summary,
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
            details={"source_format": row.source_format, "row_count": row.row_count},
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
    import_row = ProgramImport(
        id=str(uuid4()),
        owner_user_id=current_user.id,
        source_format=source_format,
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
            details={"source_format": import_row.source_format, "row_count": import_row.row_count},
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
        source_format=import_row.source_format,
        cell_count=import_row.cell_count,
        raw_rows=rows,
    )
    import_row.draft_json = dict(rebuilt)
    import_row.blocking_issue_count = rebuilt["summary"]["blocking_issue_count"]
    import_row.warning_count = rebuilt["summary"]["warning_count"]
    import_row.updated_at = now_msk_naive()
    db.commit()
    return import_row


def _program_payload_from_draft(draft: _Draft) -> ProgramTemplateCreate:
    rows = draft["rows"]
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
        source_format=import_row.source_format,
        cell_count=import_row.cell_count,
        raw_rows=[cast(_RowDraft, dict(row)) for row in draft["rows"]],
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
                "source_format": import_row.source_format,
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
        details={"source_format": import_row.source_format, "row_count": import_row.row_count},
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
    if source_format not in PROGRAM_IMPORT_SUPPORTED_FORMATS:
        raise ProgramImportError("format_unsupported", "Поддерживаются только XLSX и CSV", 415)
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
