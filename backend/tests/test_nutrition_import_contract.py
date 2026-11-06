import csv
import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from fitminiapp_api.schemas.nutrition_import import NutritionImportV1

FIXTURES = Path(__file__).parent / "fixtures" / "nutrition_import"


@pytest.fixture
def payload():
    return json.loads((FIXTURES / "neutral-golden.json").read_text(encoding="utf-8"))


def test_golden_contract_preserves_precision_unknowns_and_original_totals(payload):
    report = NutritionImportV1.model_validate(payload)
    first = report.rows[0]
    assert first.nutrition.facts.energy_kcal.value == Decimal("12.30")
    assert first.nutrition.facts.energy_kcal.value.as_tuple().exponent == -2
    assert first.nutrition.facts.protein_g.value == Decimal("0.00")
    assert first.nutrition.facts.fat_g.value is None
    assert first.nutrition.facts.fat_g.evidence == "ambiguous"
    assert first.nutrition.facts.carbohydrate_g is None
    assert first.nutrition.facts.fiber_g is None
    assert report.original_totals[1].facts.energy_kcal.value == Decimal("9999.0")
    assert len(report.rows) == 5
    assert NutritionImportV1.model_validate_json(report.model_dump_json()) == report


def test_serving_and_identity_are_not_inferred_or_deduplicated(payload):
    report = NutritionImportV1.model_validate(payload)
    assert [row.amount_unit for row in report.rows] == ["g", "ml", "piece", "serving", "g"]
    assert report.rows[3].serving_measure is None
    assert report.rows[2].food.name == report.rows[3].food.name
    assert report.rows[2].food.identity_source != report.rows[3].food.identity_source
    assert report.rows[0].food.name == report.rows[4].food.name
    assert report.rows[0].coordinates.row != report.rows[4].coordinates.row


def test_synthetic_csv_shapes_are_inputs_not_an_adapter_test():
    ru = (FIXTURES / "synthetic-ru.csv").read_bytes()
    en = (FIXTURES / "synthetic-en.csv").read_bytes()
    assert ru.startswith(b"\xef\xbb\xbf") and b"\r\n" in ru
    assert ru.count(b"\n") == ru.count(b"\r\n")
    assert not en.startswith(b"\xef\xbb\xbf") and b"\r\n" in en
    with (FIXTURES / "synthetic-ru.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle, strict=True))
    assert rows[0] == ["# Period Summary"]
    assert rows[3] == ["# Report Details"]
    assert len(rows[6]) == 11 and rows[6][1] == "12,30"
    assert rows[7] == ["100,00 г"]
    assert rows[6] == rows[14]
    assert rows[2][1] == "9999,0"
    with (FIXTURES / "synthetic-en.csv").open(encoding="utf-8", newline="") as handle:
        english = list(csv.reader(handle, strict=True))
    assert len(english[4]) == 11 and english[4][1] == "12.30"
    assert english[6][1] == "12.31"
    with (FIXTURES / "synthetic-invalid.csv").open(encoding="utf-8-sig", newline="") as handle:
        invalid = list(csv.reader(handle, strict=True))
    assert invalid[3] == ["Дата: 31.02.2024"]
    assert invalid[5][1] == "NaN" and len(invalid[-1]) == 2
    with (
        (FIXTURES / "synthetic-malformed.csv").open(encoding="utf-8-sig", newline="") as handle,
        pytest.raises(csv.Error),
    ):
        list(csv.reader(handle, strict=True))


def test_report_preserves_a_reported_total_mismatch_without_rewriting_it(payload):
    payload["rows"] = payload["rows"][:1]
    payload["original_totals"] = payload["original_totals"][:1]
    payload["original_totals"].append(
        {
            "scope": "day",
            "coordinates": {"section": "report_details", "section_kind": "detail", "row": 17},
            "diary_date": "2024-03-02",
            "facts": {"energy_kcal": {"value": "12.31", "unit": "kcal", "evidence": "read"}},
        }
    )
    payload["diagnostics"].append({"code": "totals_mismatch", "severity": "warning"})
    report = NutritionImportV1.model_validate(payload)
    assert report.original_totals[0].facts.energy_kcal.value == Decimal("12.30")
    assert report.original_totals[1].facts.energy_kcal.value == Decimal("12.31")
    assert report.diagnostics[-1].code == "totals_mismatch"


def test_serving_measure_is_explicit_and_never_inferred_from_volume(payload):
    payload["rows"][3]["serving_measure"] = {"amount": "250.00", "unit": "ml"}
    row = NutritionImportV1.model_validate(payload).rows[3]
    assert row.serving_measure.amount == Decimal("250.00")
    assert row.serving_measure.unit == "ml"
    assert "weight_g" not in row.model_dump()


def test_original_totals_preserve_reported_and_unknown_units_without_normalizing(payload):
    source_facts = payload["original_totals"][0]["facts"]
    source_facts["sodium_mg"] = {"value": "0.120", "unit": "g", "evidence": "read"}
    source_facts["potassium_mg"] = {
        "value": "2.00",
        "unit": None,
        "source_unit": "мера источника",
        "evidence": "read",
    }
    report = NutritionImportV1.model_validate(payload)
    sodium = report.original_totals[0].facts.sodium_mg
    assert sodium.value == Decimal("0.120") and sodium.unit == "g"
    assert report.original_totals[0].facts.potassium_mg.unit is None
    payload["rows"][0]["nutrition"]["facts"]["sodium_mg"] = source_facts["sodium_mg"]
    with pytest.raises(ValidationError, match="invalid unit"):
        NutritionImportV1.model_validate(payload)


@pytest.mark.parametrize(
    "bad",
    [
        "1,5",
        "-1",
        "NaN",
        "Infinity",
        "1e2",
        "1 000",
        "1.123456789",
        "1.000000000",
        "123456789012345678.0",
        Decimal("-0"),
        Decimal("1E+2"),
        1.5,
        True,
    ],
)
def test_invalid_or_imprecise_numeric_inputs_are_rejected(payload, bad):
    payload["rows"][0]["quantity"] = bad
    with pytest.raises(ValidationError):
        NutritionImportV1.model_validate(payload)


def test_small_decimals_and_explicit_zero_round_trip_without_scientific_notation(payload):
    payload["rows"][0]["quantity"] = "0.00000001"
    payload["rows"][0]["nutrition"]["facts"]["protein_g"]["value"] = "0.00000000"
    report = NutritionImportV1.model_validate(payload)
    encoded = report.model_dump_json()
    assert '"0.00000001"' in encoded and '"0.00000000"' in encoded
    assert NutritionImportV1.model_validate_json(encoded) == report


def test_eighteen_digit_integer_is_preserved(payload):
    payload["rows"][0]["quantity"] = "123456789012345678"
    assert NutritionImportV1.model_validate(payload).rows[0].quantity == Decimal(
        "123456789012345678"
    )


@pytest.mark.parametrize("bad", ["2024-02-30", "02.03.2024", 1709337600, "2024-03-02T00:00:00"])
def test_date_must_be_an_actual_iso_calendar_date(payload, bad):
    payload["rows"][0]["diary_date"] = bad
    with pytest.raises(ValidationError):
        NutritionImportV1.model_validate(payload)


def test_unknown_unit_and_timezone_stay_unknown(payload):
    row = payload["rows"][0]
    row.update(quantity="1.50", amount_unit=None, source_unit="условная мера", timezone=None)
    parsed = NutritionImportV1.model_validate(payload).rows[0]
    assert parsed.amount_unit is None and parsed.source_unit == "условная мера"
    assert parsed.timezone is None
    row["timezone"] = "Not/A_Timezone"
    with pytest.raises(ValidationError):
        NutritionImportV1.model_validate(payload)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda row: row["coordinates"].update(section_kind="summary"), "detail section"),
        (
            lambda row: row["quantity_coordinates"][0].update(section_kind="summary"),
            "detail section",
        ),
        (lambda row: row["coordinates"].update(row=None), "source page or row"),
        (lambda row: row["coordinates"].update(row=0), "greater than or equal"),
        (lambda row: row.update(quantity=None, amount_unit="g"), "requires a quantity"),
        (lambda row: row["nutrition"].update(basis=None), "explicit basis"),
        (lambda row: row["nutrition"]["facts"]["energy_kcal"].update(unit="g"), "invalid unit"),
        (
            lambda row: row["nutrition"]["facts"]["energy_kcal"].update(evidence="ambiguous"),
            "facts have a value",
        ),
        (
            lambda row: row["nutrition"]["facts"]["energy_kcal"].update(evidence="derived"),
            "derivation and inputs",
        ),
        (lambda row: row["food"].update(identity_source="source_a"), "provided together"),
        (lambda row: row["food"].update(gtin="12345678"), "check digit"),
    ],
)
def test_contract_rejects_unsafe_or_inconsistent_rows(payload, mutate, message):
    mutate(payload["rows"][0])
    with pytest.raises(ValidationError, match=message):
        NutritionImportV1.model_validate(payload)


def test_derived_facts_need_provenance_and_cannot_replace_original_totals(payload):
    fact = payload["rows"][0]["nutrition"]["facts"]["energy_kcal"]
    fact.update(
        evidence="derived", derivation="scale_by_weight", derived_from=["entry_total", "quantity"]
    )
    assert (
        NutritionImportV1.model_validate(payload).rows[0].nutrition.facts.energy_kcal.evidence
        == "derived"
    )
    payload["original_totals"][0]["facts"]["energy_kcal"] = deepcopy(fact)
    with pytest.raises(ValidationError, match="original totals"):
        NutritionImportV1.model_validate(payload)


def test_pdf_coordinates_and_other_provider_are_independent(payload):
    payload["source"].update(provider="another_provider", source_format="pdf", transport="url")
    with pytest.raises(ValidationError, match="PDF source coordinates require a page"):
        NutritionImportV1.model_validate(payload)
    for row in payload["rows"]:
        row["coordinates"]["page"] = 1
        for coord in row["quantity_coordinates"]:
            coord["page"] = 1
    for total in payload["original_totals"]:
        total["coordinates"]["page"] = 1
    assert NutritionImportV1.model_validate(payload).source.provider == "another_provider"


def test_unsupported_fields_and_sensitive_diagnostic_text_are_rejected(payload):
    payload["diagnostics"][0]["code"] = "https://example.invalid/private-token"
    with pytest.raises(ValidationError):
        NutritionImportV1.model_validate(payload)
    payload["diagnostics"][0]["code"] = "partial_export"
    payload["rows"][0]["nutrition"]["facts"]["invented_nutrient"] = None
    with pytest.raises(ValidationError, match="Extra inputs"):
        NutritionImportV1.model_validate(payload)


def test_version_and_required_contract_fields(payload):
    schema = NutritionImportV1.model_json_schema()
    assert schema["properties"]["schema_version"]["const"] == "nutrition-import-v1"
    assert (
        schema["$defs"]["ImportFoodRow"]["properties"]["quantity"]["anyOf"][0]["type"] == "string"
    )
    assert schema["$defs"]["NutrientFact"]["properties"]["value"]["anyOf"][0]["type"] == "string"
    payload["schema_version"] = "nutrition-import-v2"
    with pytest.raises(ValidationError):
        NutritionImportV1.model_validate(payload)
    payload["schema_version"] = "nutrition-import-v1"
    del payload["rows"][0]["nutrition"]["basis"]
    with pytest.raises(ValidationError):
        NutritionImportV1.model_validate(payload)
