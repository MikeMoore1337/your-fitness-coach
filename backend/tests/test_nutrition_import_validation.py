import json
from decimal import Decimal
from pathlib import Path

import pytest

from fitminiapp_api.schemas.nutrition_import import NutritionImportV1, NutritionImportV2
from fitminiapp_api.services.nutrition_import_validation import (
    MAX_CSV_FIELDS,
    MAX_CSV_ROWS,
    MAX_FIELD_CHARS,
    MAX_UPLOAD_BYTES,
    NutritionImportValidationError,
    validate_adapter_result,
    validate_csv_upload,
    validate_pdf_upload,
)

FIXTURES = Path(__file__).parent / "fixtures" / "nutrition_import"


@pytest.mark.parametrize(
    ("source", "filename", "content_type", "code"),
    [
        (b"", "report.pdf", "application/pdf", "upload_size"),
        (b"%PDF-" + b"x" * MAX_UPLOAD_BYTES, "report.pdf", "application/pdf", "upload_size"),
        (b"name,food", "report.pdf", "application/pdf", "unsupported_bytes"),
        (b"%PDF-1.7", "report.csv", "application/pdf", "invalid_filename"),
        (b"%PDF-1.7", "../report.pdf", "application/pdf", "invalid_filename"),
        (b"%PDF-1.7", "report.pdf?secret", "application/pdf", "invalid_filename"),
        (b"%PDF-1.7", "report.pdf", "text/csv", "unsupported_type"),
    ],
    ids=["empty", "oversized", "signature", "extension", "path", "query", "mime"],
)
def test_pdf_upload_envelope_rejects_invalid_inputs(source, filename, content_type, code):
    with pytest.raises(NutritionImportValidationError) as exc:
        validate_pdf_upload(source, filename=filename, content_type=content_type)
    assert exc.value.code == code
    assert "secret" not in str(exc.value)


def test_pdf_upload_envelope_accepts_signature_without_claiming_structure_is_valid():
    validate_pdf_upload(b"%PDF-1.7\n", filename="report.PDF", content_type="application/pdf")


def _upload(data: bytes, filename: str = "import.csv", content_type: str = "text/csv") -> None:
    validate_csv_upload(data, filename=filename, content_type=content_type, delimiter=",")


def test_valid_csv_preserves_source_and_accepts_quoted_newlines() -> None:
    source = 'name,quantity\n"=Синтетический\nпродукт",10\n'.encode()
    before = source[:]
    _upload(source)
    assert source == before


@pytest.mark.parametrize(
    ("source", "filename", "content_type", "code"),
    [
        (b"", "import.csv", "text/csv", "upload_size"),
        (b"a" * (MAX_UPLOAD_BYTES + 1), "import.csv", "text/csv", "upload_size"),
        (b"a\xff", "import.csv", "text/csv", "invalid_encoding"),
        (b"a\x00b", "import.csv", "text/csv", "unsafe_control"),
        (b'a,"unterminated', "import.csv", "text/csv", "invalid_csv"),
        (b"%PDF-1.4\n", "import.csv", "text/csv", "unsupported_bytes"),
        (b"PK\x03\x04fake", "import.csv", "text/csv", "unsupported_bytes"),
        (b"a,b", "private\n.csv", "text/csv", "invalid_filename"),
        (b"a,b", "../private.csv", "text/csv", "invalid_filename"),
        (b"a,b", "private.csv?token=secret", "text/csv", "invalid_filename"),
        (b"a,b", "import.pdf", "text/csv", "invalid_filename"),
        (b"a,b", "import.csv", "application/pdf", "unsupported_type"),
        (b"a" * (MAX_FIELD_CHARS + 1), "import.csv", "text/csv", "field_too_long"),
        (b",".join([b"x"] * (MAX_CSV_FIELDS + 1)), "import.csv", "text/csv", "csv_shape"),
        (b"x\n" * (MAX_CSV_ROWS + 1), "import.csv", "text/csv", "csv_shape"),
    ],
    ids=[
        "empty",
        "bytes",
        "encoding",
        "control",
        "malformed",
        "pdf",
        "zip",
        "filename_control",
        "path",
        "query",
        "extension",
        "mime",
        "field",
        "columns",
        "rows",
    ],
)
def test_invalid_csv_inputs_have_nonsensitive_errors(source, filename, content_type, code) -> None:
    with pytest.raises(NutritionImportValidationError) as exc:
        _upload(source, filename, content_type)
    assert exc.value.code == code
    assert "secret" not in str(exc.value)


@pytest.mark.parametrize(
    ("fixture", "provider", "version", "model"),
    [
        ("neutral-golden.json", "fatsecret", "synthetic-v1", NutritionImportV1),
        ("neutral-summary-v2-golden.json", "fixture_provider", "fixture-v2", NutritionImportV2),
    ],
)
def test_adapter_result_keeps_contract_version_and_decimal_precision(
    fixture, provider, version, model
) -> None:
    result = validate_adapter_result(
        (FIXTURES / fixture).read_bytes(),
        provider=provider,
        adapter_version=version,
        source_format="csv",
    )
    assert isinstance(result, model)
    if isinstance(result, NutritionImportV1):
        assert result.rows[0].nutrition.facts.energy_kcal.value == Decimal("12.30")
        assert str(result.rows[0].nutrition.facts.energy_kcal.value) == "12.30"
        assert result.rows[0].nutrition.facts.fat_g.value is None


def test_adapter_source_cannot_claim_another_provider_or_transport() -> None:
    source = (FIXTURES / "neutral-summary-v2-golden.json").read_bytes()
    with pytest.raises(NutritionImportValidationError, match="source_mismatch"):
        validate_adapter_result(
            source, provider="other", adapter_version="fixture-v2", source_format="csv"
        )
    payload = json.loads(source)
    payload["source"]["transport"] = "url"
    with pytest.raises(NutritionImportValidationError, match="source_mismatch"):
        validate_adapter_result(
            json.dumps(payload).encode(),
            provider="fixture_provider",
            adapter_version="fixture-v2",
            source_format="csv",
        )


def test_adapter_result_rejects_oversized_or_malformed_output_without_exposing_data() -> None:
    cases = [
        b'{"secret":"PRIVATE_DIET",',
        json.dumps(
            {"schema_version": "nutrition-import-v2", "rows": [0] * (MAX_CSV_ROWS + 1)}
        ).encode(),
        b'{"schema_version":NaN}',
        b'{"unsafe":"\\ud800"}',
        b'{"unsafe":1e999}',
        b'{"schema_version":"nutrition-import-v1","schema_version":"nutrition-import-v2"}',
    ]
    for payload in cases:
        with pytest.raises(NutritionImportValidationError) as exc:
            validate_adapter_result(
                payload,
                provider="fixture_provider",
                adapter_version="fixture-v2",
                source_format="csv",
            )
        assert "PRIVATE_DIET" not in str(exc.value)


def test_csv_export_escapes_imported_formula_like_names() -> None:
    from fitminiapp_api.services.account_exports import _csv_cell

    assert _csv_cell("  =1+1") == "'  =1+1"
    assert _csv_cell("\t@command") == "'\t@command"
    assert _csv_cell("ordinary name") == "ordinary name"
