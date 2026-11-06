import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from fitminiapp_api.schemas.nutrition_import import NutritionImportV1, NutritionImportV2

FIXTURES = Path(__file__).parent / "fixtures" / "nutrition_import"


@pytest.fixture
def payload():
    return json.loads((FIXTURES / "neutral-summary-v2-golden.json").read_text(encoding="utf-8"))


def test_unknown_summary_round_trip_preserves_source_and_numeric_meaning(payload):
    report = NutritionImportV2.model_validate(payload)
    summary = report.original_summaries[0]
    row = summary.rows[0]
    energy, missing, carbohydrates, protein, unknown = row.values

    assert report.source.provider == "fixture_provider"
    assert report.rows == [] and report.original_totals == []
    assert summary.aggregation.kind == "unknown"
    assert summary.aggregation.evidence == "unknown"
    assert summary.header_label == "  Синтетический заголовок  "
    assert summary.period_label == "  Пример периода  "
    assert summary.header_coordinates.row == 2
    assert row.source_label == "  Синтетическая группа A  "
    assert row.scope == "meal" and row.meal_type is None
    assert energy.source_header == "  Энергия (пример)  "
    assert energy.source_value == " 17,2300 "
    assert energy.nutrient_field == "energy_kcal"
    assert energy.fact.value == Decimal("17.2300")
    assert energy.fact.value.as_tuple().exponent == -4
    assert missing.source_value == "" and missing.fact.value is None
    assert missing.fact.evidence == "absent"
    assert carbohydrates.nutrient_field == "carbohydrate_g"
    assert carbohydrates.fact.value == Decimal("0.00")
    assert protein.nutrient_field == "protein_g" and protein.fact.value == Decimal("2.30")
    assert unknown.nutrient_field is None and unknown.mapping_evidence == "unknown"
    assert unknown.fact.value == Decimal("0.00") and unknown.fact.unit is None
    assert unknown.fact.source_unit == "пример единицы"
    assert "Синтетическая группа A" not in repr(report)
    assert "17,2300" not in repr(energy)

    restored = NutritionImportV2.model_validate_json(report.model_dump_json())
    assert restored == report
    assert restored.original_summaries[0].rows[0].values[0].source_value == " 17,2300 "


def test_repr_omits_sensitive_v2_summary_and_existing_entry_data(payload):
    legacy = json.loads((FIXTURES / "neutral-golden.json").read_text(encoding="utf-8"))
    payload["rows"] = [legacy["rows"][0]]
    payload["original_totals"] = [legacy["original_totals"][0]]
    payload["original_summaries"][0]["rows"][0]["meal_type"] = "breakfast"

    report = NutritionImportV2.model_validate(payload)
    summary = report.original_summaries[0]
    row = summary.rows[0]
    assert "Тестовый продукт Альфа" not in repr(report)
    assert "Синтетическая группа A" not in repr(report)
    assert "2031" not in repr(summary)
    assert "breakfast" not in repr(row)


def test_duplicate_summary_rows_are_preserved_in_source_order(payload):
    rows = payload["original_summaries"][0]["rows"]
    repeat = deepcopy(rows[0])
    repeat["coordinates"]["row"] = 5
    rows.append(repeat)

    report = NutritionImportV2.model_validate(payload)
    restored = NutritionImportV2.model_validate_json(report.model_dump_json())
    assert [row.coordinates.row for row in restored.original_summaries[0].rows] == [3, 4, 5]
    assert restored.original_summaries[0].rows[0].source_label == repeat["source_label"]


def test_absent_headers_and_column_positions_remain_unknown(payload):
    values = payload["original_summaries"][0]["rows"][0]["values"]
    values[0].update(
        source_column=None,
        source_header=None,
        nutrient_field=None,
        mapping_evidence="unknown",
    )
    values[1].update(
        source_column=None,
        source_header="",
        source_value=None,
        nutrient_field=None,
        mapping_evidence="unknown",
    )
    summary = payload["original_summaries"][0]
    summary["header_label"] = None
    summary["period_label"] = None
    summary["rows"][0]["source_label"] = None

    report = NutritionImportV2.model_validate(payload)
    restored = NutritionImportV2.model_validate_json(report.model_dump_json())
    row = restored.original_summaries[0].rows[0]
    assert row.source_label is None
    assert row.values[0].source_column is None and row.values[0].source_header is None
    assert row.values[1].source_column is None and row.values[1].source_header == ""
    assert row.values[1].source_value is None


def test_source_label_evidence_requires_an_observed_label(payload):
    summary = payload["original_summaries"][0]
    summary["aggregation"] = {"kind": "total", "evidence": "source_label"}
    summary["header_label"] = None
    with pytest.raises(ValidationError, match="requires a header label"):
        NutritionImportV2.model_validate(payload)

    summary["header_label"] = "пример"
    summary["rows"][0]["values"][0]["source_header"] = ""
    with pytest.raises(ValidationError, match="requires a source header"):
        NutritionImportV2.model_validate(payload)


def test_v1_and_v2_require_explicit_distinct_versions(payload):
    legacy = json.loads((FIXTURES / "neutral-golden.json").read_text(encoding="utf-8"))
    assert NutritionImportV1.model_validate(legacy).schema_version == "nutrition-import-v1"
    assert NutritionImportV2.model_validate(payload).schema_version == "nutrition-import-v2"

    with pytest.raises(ValidationError):
        NutritionImportV1.model_validate(payload)
    with pytest.raises(ValidationError):
        NutritionImportV2.model_validate(legacy)
    assert "original_summaries" not in NutritionImportV1.model_json_schema()["properties"]


@pytest.mark.parametrize(
    "aggregation",
    [
        {"kind": "unknown", "evidence": "unknown"},
        {"kind": "total", "evidence": "source_label"},
        {"kind": "target", "evidence": "source_profile"},
        {
            "kind": "daily_average",
            "evidence": "provider_documentation",
            "denominator": "logged_days",
            "denominator_days": 3,
        },
        {
            "kind": "daily_average",
            "evidence": "source_profile",
            "denominator": "unknown",
            "denominator_days": 0,
        },
    ],
)
def test_explicit_aggregation_and_denominator_round_trip(payload, aggregation):
    payload["original_summaries"][0]["aggregation"] = aggregation
    report = NutritionImportV2.model_validate(payload)
    restored = NutritionImportV2.model_validate_json(report.model_dump_json())
    assert restored.original_summaries[0].aggregation.kind == aggregation["kind"]
    assert restored.original_summaries[0].aggregation.evidence == aggregation["evidence"]
    assert restored.original_summaries[0].aggregation.denominator == aggregation.get("denominator")
    assert restored.original_summaries[0].aggregation.denominator_days == aggregation.get(
        "denominator_days"
    )


@pytest.mark.parametrize(
    ("aggregation", "message"),
    [
        ({"kind": "daily_average", "evidence": "unknown"}, "known aggregation requires evidence"),
        ({"kind": "unknown", "evidence": "source_label"}, "known aggregation requires evidence"),
        ({"kind": "daily_average", "evidence": "source_label"}, "requires a denominator"),
        (
            {"kind": "target", "evidence": "source_label", "denominator": "logged_days"},
            "only a daily average",
        ),
        ({"kind": "total", "evidence": "source_label", "denominator_days": 1}, "only a daily"),
        (
            {
                "kind": "daily_average",
                "evidence": "source_label",
                "denominator": "logged_days",
                "denominator_days": -1,
            },
            "greater than or equal",
        ),
        (
            {
                "kind": "daily_average",
                "evidence": "source_label",
                "denominator": "logged_days",
                "denominator_days": True,
            },
            "valid integer",
        ),
    ],
)
def test_aggregation_does_not_guess_or_accept_inconsistent_evidence(payload, aggregation, message):
    payload["original_summaries"][0]["aggregation"] = aggregation
    with pytest.raises(ValidationError, match=message):
        NutritionImportV2.model_validate(payload)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"nutrient_field": "invented_nutrient"}, "unsupported nutrient field"),
        (
            {"nutrient_field": None, "mapping_evidence": "source_label"},
            "known nutrient mapping requires evidence",
        ),
        ({"mapping_evidence": "unknown"}, "known nutrient mapping requires evidence"),
        ({"source_value": None}, "require a source value"),
        ({"source_value": "   "}, "require a source value"),
        ({"source_column": 0}, "greater than or equal"),
        ({"source_column": True}, "valid integer"),
        ({"source_header": "x" * 257}, "at most 256 characters"),
        ({"source_value": "1" * 129}, "at most 128 characters"),
    ],
)
def test_summary_values_reject_unsafe_or_unsupported_mapping(payload, changes, message):
    payload["original_summaries"][0]["rows"][0]["values"][0].update(changes)
    with pytest.raises(ValidationError, match=message):
        NutritionImportV2.model_validate(payload)


@pytest.mark.parametrize("source_value", ["  ?  ", "123456789012345678901234567890,123456789"])
def test_unreadable_source_cell_is_preserved_without_a_numeric_guess(payload, source_value):
    value = payload["original_summaries"][0]["rows"][0]["values"][0]
    value.update(
        source_value=source_value,
        nutrient_field=None,
        mapping_evidence="unknown",
        fact={"value": None, "unit": None, "evidence": "unreadable"},
    )
    report = NutritionImportV2.model_validate(payload)
    restored = NutritionImportV2.model_validate_json(report.model_dump_json())
    result = restored.original_summaries[0].rows[0].values[0]
    assert result.source_value == source_value
    assert result.fact.value is None and result.fact.evidence == "unreadable"
    assert result.nutrient_field is None


@pytest.mark.parametrize("field", ["header_label", "period_label"])
def test_summary_labels_are_bounded_without_truncation(payload, field):
    payload["original_summaries"][0][field] = "x" * 257
    with pytest.raises(ValidationError, match="at most 256 characters"):
        NutritionImportV2.model_validate(payload)


def test_original_summary_rejects_derived_fact(payload):
    fact = payload["original_summaries"][0]["rows"][0]["values"][0]["fact"]
    fact.update(
        evidence="derived",
        derivation="scale_by_weight",
        derived_from=[
            {
                "coordinates": {"section": "period_summary", "section_kind": "summary", "row": 3},
                "field": "energy_kcal",
            }
        ],
    )
    with pytest.raises(ValidationError, match="original summary facts cannot be derived"):
        NutritionImportV2.model_validate(payload)


def test_duplicate_columns_and_overall_meal_are_rejected(payload):
    row = payload["original_summaries"][0]["rows"][0]
    row["values"].append(deepcopy(row["values"][0]))
    with pytest.raises(ValidationError, match="columns must be unique"):
        NutritionImportV2.model_validate(payload)

    row["values"].pop()
    row.update(scope="overall", meal_type="breakfast")
    with pytest.raises(ValidationError, match="overall summary cannot name a meal"):
        NutritionImportV2.model_validate(payload)


@pytest.mark.parametrize("where", ["header", "row", "period", "diagnostic"])
def test_csv_summary_provenance_requires_row_coordinates(payload, where):
    summary = payload["original_summaries"][0]
    coordinates = {
        "header": summary["header_coordinates"],
        "row": summary["rows"][0]["coordinates"],
        "period": summary["period_coordinates"],
        "diagnostic": payload["diagnostics"][0]["coordinates"],
    }[where]
    coordinates.update(row=None, page=1)
    with pytest.raises(ValidationError, match="CSV source coordinates require a row"):
        NutritionImportV2.model_validate(payload)


def test_pdf_summary_requires_page_coordinates_and_keeps_another_provider(payload):
    payload["source"]["source_format"] = "pdf"
    with pytest.raises(ValidationError, match="PDF source coordinates require a page"):
        NutritionImportV2.model_validate(payload)

    summary = payload["original_summaries"][0]
    summary["header_coordinates"]["page"] = 1
    summary["period_coordinates"]["page"] = 1
    for row in summary["rows"]:
        row["coordinates"]["page"] = 1
    payload["diagnostics"][0]["coordinates"]["page"] = 1
    assert NutritionImportV2.model_validate(payload).source.provider == "fixture_provider"


def test_partial_period_and_known_timezone_are_preserved(payload):
    summary = payload["original_summaries"][0]
    summary["period_end"] = None
    summary["timezone"] = "UTC"

    report = NutritionImportV2.model_validate(payload)
    restored = NutritionImportV2.model_validate_json(report.model_dump_json())
    result = restored.original_summaries[0]
    assert result.period_start.isoformat() == "2031-02-01"
    assert result.period_end is None and result.timezone == "UTC"


def test_invalid_summary_period_and_timezone_are_rejected(payload):
    summary = payload["original_summaries"][0]
    summary["period_start"] = "2031-03-01"
    with pytest.raises(ValidationError, match="period start must not be after end"):
        NutritionImportV2.model_validate(payload)

    summary["period_start"] = "2031-02-01"
    summary["timezone"] = "Not/A_Timezone"
    with pytest.raises(ValidationError, match="known IANA timezone"):
        NutritionImportV2.model_validate(payload)
