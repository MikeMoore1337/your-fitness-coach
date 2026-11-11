"""Bounded validation for nutrition import adapters; no source bytes are persisted here."""

from __future__ import annotations

import csv
import io
import json
import math
import unicodedata
from time import monotonic
from typing import Literal

from pydantic import ValidationError

from fitminiapp_api.schemas.nutrition_import import (
    NutritionImportV1,
    NutritionImportV2,
    NutritionImportV3,
)

MAX_UPLOAD_BYTES = 512 * 1024
MAX_PDF_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_CSV_ROWS = 2_000
MAX_CSV_FIELDS = 64
MAX_FIELD_CHARS = 1_024
MAX_ADAPTER_BYTES = 2 * 1024 * 1024
MAX_ADAPTER_NODES = 100_000
MAX_ADAPTER_DEPTH = 16
MAX_ADAPTER_LIST = 2_000
MAX_SCAN_SECONDS = 2.0


class NutritionImportValidationError(ValueError):
    """A non-sensitive error code; do not attach source or validation details."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _has_unsafe_controls(value: str) -> bool:
    return any(
        unicodedata.category(char) in {"Cc", "Cs"} and char not in "\r\n\t" for char in value
    )


def validate_pdf_upload(source: bytes, *, filename: str | None, content_type: str | None) -> None:
    """Validate the upload envelope; PDF structure is checked by the bounded parser."""
    if (
        not filename
        or len(filename) > 120
        or not filename.casefold().endswith(".pdf")
        or ".." in filename
        or any(char in filename for char in "/\\:?#")
        or any(unicodedata.category(char) in {"Cc", "Cs"} for char in filename)
    ):
        raise NutritionImportValidationError("invalid_filename")
    if content_type is None or content_type.split(";", 1)[0].strip().lower() != "application/pdf":
        raise NutritionImportValidationError("unsupported_type")
    if not source or len(source) > MAX_PDF_UPLOAD_BYTES:
        raise NutritionImportValidationError("upload_size")
    if not source.startswith(b"%PDF-"):
        raise NutritionImportValidationError("unsupported_bytes")


def validate_csv_upload(
    source: bytes,
    *,
    filename: str | None,
    content_type: str | None,
    delimiter: Literal[",", ";", "\t"],
) -> None:
    """Validate bytes and CSV shape without retaining or interpreting personal fields."""
    if (
        not filename
        or len(filename) > 120
        or not filename.casefold().endswith(".csv")
        or ".." in filename
        or any(char in filename for char in "/\\:?#")
        or any(unicodedata.category(char) in {"Cc", "Cs"} for char in filename)
    ):
        raise NutritionImportValidationError("invalid_filename")
    if content_type is None or content_type.split(";", 1)[0].strip().lower() not in {
        "text/csv",
        "application/csv",
        "text/plain",
    }:
        raise NutritionImportValidationError("unsupported_type")
    if not source or len(source) > MAX_UPLOAD_BYTES:
        raise NutritionImportValidationError("upload_size")
    if delimiter not in {",", ";", "\t"}:
        raise NutritionImportValidationError("unsupported_dialect")
    if source.startswith((b"%PDF-", b"PK\x03\x04")):
        raise NutritionImportValidationError("unsupported_bytes")
    try:
        content = source.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise NutritionImportValidationError("invalid_encoding") from None
    if _has_unsafe_controls(content):
        raise NutritionImportValidationError("unsafe_control")

    deadline = monotonic() + MAX_SCAN_SECONDS
    try:
        reader = csv.reader(io.StringIO(content, newline=""), delimiter=delimiter, strict=True)
        rows = 0
        has_content = False
        for rows, row in enumerate(reader, start=1):
            if monotonic() > deadline:
                raise NutritionImportValidationError("scan_timeout")
            if rows > MAX_CSV_ROWS or len(row) > MAX_CSV_FIELDS:
                raise NutritionImportValidationError("csv_shape")
            if any(len(field) > MAX_FIELD_CHARS for field in row):
                raise NutritionImportValidationError("field_too_long")
            has_content = has_content or any(field.strip() for field in row)
        if not rows or not has_content:
            raise NutritionImportValidationError("empty_csv")
    except csv.Error:
        raise NutritionImportValidationError("invalid_csv") from None


def _validate_tree(value: object) -> None:
    pending = [(value, 0)]
    nodes = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if nodes > MAX_ADAPTER_NODES or depth > MAX_ADAPTER_DEPTH:
            raise NutritionImportValidationError("adapter_shape")
        if isinstance(item, dict):
            if len(item) > MAX_CSV_FIELDS:
                raise NutritionImportValidationError("adapter_shape")
            for key, child in item.items():
                if not isinstance(key, str) or len(key) > 128 or _has_unsafe_controls(key):
                    raise NutritionImportValidationError("adapter_shape")
                pending.append((child, depth + 1))
        elif isinstance(item, list):
            if len(item) > MAX_ADAPTER_LIST:
                raise NutritionImportValidationError("adapter_shape")
            pending.extend((child, depth + 1) for child in item)
        elif isinstance(item, str):
            if len(item) > MAX_FIELD_CHARS or _has_unsafe_controls(item):
                raise NutritionImportValidationError("adapter_shape")
        elif (isinstance(item, float) and not math.isfinite(item)) or (
            item is not None and not isinstance(item, (bool, int, float))
        ):
            raise NutritionImportValidationError("adapter_shape")


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_json_constant(_value: str) -> None:
    raise ValueError("non-finite JSON number")


def validate_adapter_result(
    payload: bytes, *, provider: str, adapter_version: str, source_format: str
) -> NutritionImportV1 | NutritionImportV2 | NutritionImportV3:
    """Validate a bounded adapter result without converting between contract versions."""
    if not payload or len(payload) > MAX_ADAPTER_BYTES:
        raise NutritionImportValidationError("adapter_size")
    try:
        data = json.loads(
            payload, parse_constant=_reject_json_constant, object_pairs_hook=_unique_json_object
        )
        _validate_tree(data)
        if not isinstance(data, dict):
            raise NutritionImportValidationError("adapter_shape")
        version = data.get("schema_version")
        result: NutritionImportV1 | NutritionImportV2 | NutritionImportV3
        if version == "nutrition-import-v1":
            result = NutritionImportV1.model_validate(data)
        elif version == "nutrition-import-v2":
            result = NutritionImportV2.model_validate(data)
        elif version == "nutrition-import-v3":
            result = NutritionImportV3.model_validate(data)
        else:
            raise NutritionImportValidationError("unsupported_version")
    except NutritionImportValidationError:
        raise
    except UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValidationError, ValueError:
        raise NutritionImportValidationError("invalid_adapter_result") from None
    if (
        result.source.provider != provider
        or result.source.adapter_version != adapter_version
        or result.source.source_format != source_format
        or result.source.transport != "upload"
    ):
        raise NutritionImportValidationError("source_mismatch")
    return result
