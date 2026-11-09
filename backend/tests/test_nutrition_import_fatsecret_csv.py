import csv
import io
import json
import os
import sys
from copy import deepcopy
from decimal import Decimal

import pytest
from pydantic import ValidationError
from test_training_analytics import _auth

from fitminiapp_api.db.session import engine, get_session_context
from fitminiapp_api.models.food import Food
from fitminiapp_api.models.food_diary import FoodDiaryEntry
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.nutrition_import import NutritionImportV1, NutritionImportV2
from fitminiapp_api.schemas.nutrition_import_engine import ImportPreview
from fitminiapp_api.services.nutrition_catalog_import import catalog_import_preview
from fitminiapp_api.services.nutrition_import_drafts import (
    NutritionDraftError,
    create_nutrition_import_draft,
    get_nutrition_import_draft,
    nutrition_import_preview,
    set_resolutions,
)
from fitminiapp_api.services.nutrition_import_fatsecret_csv import parse
from fitminiapp_api.services.nutrition_import_validation import (
    MAX_CSV_ROWS,
    MAX_UPLOAD_BYTES,
    validate_adapter_result,
)

SUMMARY_HEADER = [
    "Суточная норма (пример)",
    "Калории (ккал)",
    "Жир (г)",
    "Углеводы (г)",
    "Белок (г)",
]
DETAIL_HEADER = [
    "Метка",
    "Калории (ккал)",
    "Жир (г)",
    "Н/жир (г)",
    "Углеводы (г)",
    "Клетчатка (г)",
    "Сахар (г)",
    "Белок (г)",
    "Натрий (мг)",
    "Холестерин (мг)",
    "Калий (мг)",
]
NUTRIENTS = ["12,30000001", "2,00", "0,50", "4,00", "", "0,00", "3,00", "1,00", "0,00", "5,00"]


@pytest.fixture
def rows():
    return [
        ["# Period Summary"],
        ["Период: 01.02.2024–31.03.2024"],
        SUMMARY_HEADER[:],
        ["Завтрак", "12,30", "2,00", "4,00", "3,00"],
        ["Итого", "12,30", "2,00", "4,00", "3,00"],
        ["# Report Details"],
        DETAIL_HEADER[:],
        ["Дата: 29.02.2024"],
        ["Завтрак", *NUTRIENTS],
        ["Тестовый продукт, альфа", *NUTRIENTS],
        ["100,00 г"],
        ["Тестовый напиток", *NUTRIENTS],
        ["250,5 мл"],
        ["Обед"],
        ["Тестовый товар", *NUTRIENTS],
        ["2 штуки"],
        ["Итого за день", *NUTRIENTS],
        [],
        ["Дата: 02.03.2024"],
        ["Перекус"],
        ["Тестовая порция", *NUTRIENTS],
        ["1,5 порции"],
        ["Тестовая чашка", *NUTRIENTS],
        ["1 чашка"],
        ["Тестовая порция", *NUTRIENTS],
        ["1,5 порции"],
    ]


def _csv(rows, *, bom=True):
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\r\n").writerows(rows)
    return (("\ufeff" if bom else "") + output.getvalue()).encode("utf-8")


def _validated(rows):
    source = _csv(rows)
    payload = parse(source)
    result = validate_adapter_result(
        json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        provider="fatsecret",
        adapter_version="fatsecret-csv-v1",
        source_format="csv",
    )
    return source, result


def test_document_preserves_sections_nutrients_quantities_and_duplicates(rows):
    source, result = _validated(rows)
    assert source.startswith(b"\xef\xbb\xbf") and source.count(b"\n") == source.count(b"\r\n")
    assert result.schema_version == "nutrition-import-v3"
    assert len(result.rows) == 6
    assert [row.diary_date.isoformat() for row in result.rows] == [
        "2024-02-29",
        "2024-02-29",
        "2024-02-29",
        "2024-03-02",
        "2024-03-02",
        "2024-03-02",
    ]
    assert [row.amount_unit for row in result.rows] == [
        "g",
        "ml",
        "piece",
        "serving",
        None,
        "serving",
    ]
    assert [str(row.quantity) for row in result.rows] == ["100.00", "250.5", "2", "1.5", "1", "1.5"]
    assert result.rows[4].source_unit == "чашка"
    assert result.rows[3].serving_measure is None
    assert result.rows[0].coordinates.row == 10
    assert result.rows[0].quantity_coordinates[0].row == 11
    assert all(row.food.kind == "unknown" and row.nutrition.basis is None for row in result.rows)
    assert any(issue.code == "unknown_unit" for issue in result.rows[4].diagnostics)
    assert any(issue.code == "possible_duplicate" for issue in result.rows[5].diagnostics)

    first = next(item for item in result.original_totals if item.coordinates.row == 10)
    assert first.scope == "unknown"
    assert first.facts.energy_kcal.value == Decimal("12.30000001")
    assert first.facts.fat_g.value == Decimal("2.00")
    assert first.facts.carbohydrate_g.value == Decimal("4.00")
    assert first.facts.fiber_g.evidence == "absent"
    assert first.facts.sugars_g.value == Decimal("0.00")
    assert first.facts.protein_g.value == Decimal("3.00")
    assert first.facts.sodium_mg.value == Decimal("1.00")
    assert first.facts.cholesterol_mg.value == Decimal("0.00")
    assert first.facts.potassium_mg.value == Decimal("5.00")
    assert first.facts.saturated_fat_g is None
    cell = next(item for item in result.original_detail_cells if item.coordinates.row == 10)
    assert cell.source_header == "Н/жир (г)" and cell.source_value == "0,50"
    assert cell.nutrient_field is None and cell.mapping_evidence == "unknown"
    assert cell.fact.value == Decimal("0.50") and cell.fact.evidence == "read"
    assert any(issue.code == "potassium_not_in_catalog" for issue in result.rows[0].diagnostics)

    summary = result.original_summaries[0]
    assert summary.aggregation.kind == "unknown"
    assert (summary.period_start.isoformat(), summary.period_end.isoformat()) == (
        "2024-02-01",
        "2024-03-31",
    )
    assert summary.rows[0].values[0].source_value == "12,30"
    assert any(item.scope == "meal" for item in result.original_totals)
    assert any(item.scope == "day" for item in result.original_totals)
    assert any(issue.code == "totals_not_comparable" for issue in result.diagnostics)


def test_unreadable_nutrient_is_preserved_and_marks_the_row_invalid(rows):
    rows[9][1] = "NaN"
    rows[11][2] = "1,123456789"
    _, result = _validated(rows)
    assert [
        issue.severity
        for issue in result.rows[0].diagnostics
        if issue.code == "nutrient_unreadable"
    ] == ["error"]
    assert [
        issue.severity
        for issue in result.rows[1].diagnostics
        if issue.code == "nutrient_unreadable"
    ] == ["error"]
    cells = {
        (cell.coordinates.row, cell.source_column): cell for cell in result.original_detail_cells
    }
    assert cells[(10, 2)].source_value == "NaN"
    assert cells[(10, 2)].fact.value is None and cells[(10, 2)].fact.evidence == "unreadable"
    assert cells[(12, 3)].source_value == "1,123456789"
    assert cells[(12, 3)].fact.value is None


@pytest.mark.parametrize("bad_amount", ["100", "0 г", "маленькая чашка", "1,123456789 г"])
def test_unusable_quantity_never_gets_invented(rows, bad_amount):
    rows[10] = [bad_amount]
    _, result = _validated(rows)
    row = result.rows[0]
    assert row.quantity is None and row.amount_unit is None
    assert row.serving_measure is None
    assert any(issue.severity == "error" for issue in row.diagnostics)


@pytest.mark.parametrize(
    ("amount", "code"),
    [("2024-03-01", "quantity_unrecognized"), ("1 мар 2024 г.", "unknown_unit")],
)
def test_unrecognized_amount_cannot_silently_assign_later_rows_to_an_old_date(rows, amount, code):
    rows[10] = [amount]
    _, result = _validated(rows)
    assert any(issue.code == code for issue in result.rows[0].diagnostics)
    assert any(issue.code == "source_context_ambiguous" for issue in result.rows[1].diagnostics)
    assert result.rows[1].diary_date is None
    assert (
        next(item for item in result.original_totals if item.coordinates.row == 12).diary_date
        is None
    )
    assert not any(issue.code == "source_context_ambiguous" for issue in result.rows[3].diagnostics)


def test_quoted_newline_uses_physical_source_rows(rows):
    rows[9][0] = "Тестовый\nпродукт"
    _, result = _validated(rows)
    assert result.rows[0].food.name == "Тестовый\nпродукт"
    assert result.rows[0].coordinates.row == 10
    assert result.rows[0].quantity_coordinates[0].row == 12
    assert result.rows[1].coordinates.row == 13


@pytest.mark.parametrize(
    ("change", "code"),
    [
        (lambda r: r[6].__setitem__(1, "Калории (кДж)"), "unknown_detail_header"),
        (lambda r: r[2].__setitem__(1, "Неизвестно"), "unknown_summary_structure"),
        (lambda r: r[7].__setitem__(0, "Дата: 31.02.2024"), "invalid_date"),
        (lambda r: r[10].__setitem__(0, "Дата: 01.03.2024"), "quantity_association_ambiguous"),
        (lambda r: r[10].__setitem__(0, "Дата 01.03.2024"), "quantity_association_ambiguous"),
        (lambda r: r[10].__setitem__(0, "01.03.2024"), "quantity_association_ambiguous"),
        (lambda r: r[10].__setitem__(0, "1 марта 2024 г."), "quantity_association_ambiguous"),
        (lambda r: r[9].__setitem__(0, "Итого за приём пищи"), "unknown_total_scope"),
        (lambda r: r[9].__setitem__(0, "Промежуточный итог"), "unknown_total_scope"),
        (lambda r: r[9].__setitem__(0, "Дневной итог"), "unknown_total_scope"),
        (lambda r: r[11].__setitem__(0, "Итого, приём пищи"), "unknown_total_scope"),
        (lambda r: r[9].__setitem__(0, "Дата: 01.03.2024"), "unknown_detail_structure"),
        (lambda r: r[9].pop(), "unknown_detail_structure"),
        (lambda r: r.append(["# Report Details"]), "unknown_sections"),
    ],
)
def test_unrecognized_structure_fails_closed_without_private_text(rows, change, code):
    change(rows)
    result = parse(_csv(rows))
    assert result["rows"] == [] and result["original_totals"] == []
    assert result["diagnostics"][0]["code"] == code
    assert "Тестовый" not in json.dumps(result["diagnostics"], ensure_ascii=False)


def test_invalid_csv_and_existing_limits_fail_closed(rows):
    assert parse(b'a,"unterminated')["diagnostics"][0]["code"] == "invalid_csv"
    assert parse(b"x" * (MAX_UPLOAD_BYTES + 1))["diagnostics"][0]["code"] == "upload_size"
    assert parse(_csv(rows + [["x"]] * MAX_CSV_ROWS))["diagnostics"][0]["code"] == "csv_shape"


def test_v3_rejects_duplicate_cells_and_does_not_change_v1_v2(rows):
    _, result = _validated(rows)
    payload = result.model_dump(mode="json")
    for old in (NutritionImportV1, NutritionImportV2):
        with pytest.raises(ValidationError):
            old.model_validate(payload)
    duplicate = deepcopy(payload)
    duplicate["original_detail_cells"].append(deepcopy(duplicate["original_detail_cells"][0]))
    with pytest.raises(ValidationError, match="unique coordinates"):
        type(result).model_validate(duplicate)
    wrong_section = deepcopy(payload)
    wrong_section["original_detail_cells"][0]["coordinates"]["section_kind"] = "summary"
    with pytest.raises(ValidationError):
        type(result).model_validate(wrong_section)
    orphan = deepcopy(payload)
    orphan["original_detail_cells"][0]["coordinates"]["row"] = 2000
    with pytest.raises(ValidationError, match="refer to a source row"):
        type(result).model_validate(orphan)
    assert type(result).model_validate_json(result.model_dump_json()) == result


def test_draft_and_preview_preserve_cells_without_canonical_writes(rows):
    source, document = _validated(rows)
    with get_session_context() as db:
        owner = User(telegram_user_id=984_100, measurement_eligibility="test")
        other = User(telegram_user_id=984_101, measurement_eligibility="test")
        db.add_all([owner, other])
        db.flush()
        owner_id = owner.id
        before = db.query(Food).count(), db.query(FoodDiaryEntry).count()
        draft = create_nutrition_import_draft(
            db,
            owner,
            document=document,
            source=source,
            filename="synthetic.csv",
            content_type="text/csv",
            delimiter=",",
            parser_version="fatsecret-csv-v1",
            upload_key="synthetic-upload-884",
            adapter_id="fatsecret-csv-v1",
        )
        draft_id = draft.id
        preview = ImportPreview.model_validate(nutrition_import_preview(db, owner, draft_id))
        assert preview.schema_version == "nutrition-import-v3"
        assert preview.original_detail_cells[1].source_value == "0,50"
        assert preview.original_detail_cells[1].mapping_evidence == "unknown"
        assert preview.rows[4].status == "invalid"
        assert all(
            row["outcome"] == "needs_review"
            for row in catalog_import_preview(db, owner, draft_id)["rows"]
        )
        assert (db.query(Food).count(), db.query(FoodDiaryEntry).count()) == before
        with pytest.raises(NutritionDraftError, match="not_found"):
            get_nutrition_import_draft(db, other, draft_id)
        db.commit()
    with get_session_context() as db:
        owner = db.get(User, owner_id)
        persisted = get_nutrition_import_draft(db, owner, draft_id)
        assert persisted.document["original_detail_cells"][1]["source_value"] == "0,50"


def test_draft_preserves_a_large_valid_report_with_existing_output_limit():
    rows = [
        ["# Period Summary"],
        SUMMARY_HEADER[:],
        ["# Report Details"],
        DETAIL_HEADER[:],
        ["Дата: 01.03.2024"],
        ["Завтрак"],
    ]
    for index in range(950):
        rows.extend([[f"Тестовый продукт {index}", *NUTRIENTS], ["100 г"]])
    source, document = _validated(rows)
    with get_session_context() as db:
        owner = User(telegram_user_id=984_102, measurement_eligibility="test")
        db.add(owner)
        db.flush()
        draft = create_nutrition_import_draft(
            db,
            owner,
            document=document,
            source=source,
            filename="synthetic.csv",
            content_type="text/csv",
            delimiter=",",
            parser_version="fatsecret-csv-v1",
            upload_key="synthetic-large-884",
            adapter_id="fatsecret-csv-v1",
        )
        assert len(draft.document["rows"]) == 950
        assert len(draft.document["original_detail_cells"]) == 950
        assert draft.document["original_detail_cells"][0]["source_value"] == "0,50"
        assert len(nutrition_import_preview(db, owner, draft.id)["rows"]) == 950


def test_ambiguous_context_cannot_be_resolved_into_a_diary_entry(rows):
    rows[10] = ["2024-03-01"]
    source, document = _validated(rows)
    with get_session_context() as db:
        owner = User(telegram_user_id=984_103, measurement_eligibility="test")
        db.add(owner)
        db.flush()
        draft = create_nutrition_import_draft(
            db,
            owner,
            document=document,
            source=source,
            filename="synthetic.csv",
            content_type="text/csv",
            delimiter=",",
            parser_version="fatsecret-csv-v1",
            upload_key="synthetic-ambiguous-884",
            adapter_id="fatsecret-csv-v1",
        )
        preview = nutrition_import_preview(db, owner, draft.id)
        assert preview["rows"][1]["status"] == "invalid"
        assert "source_context_ambiguous" in preview["rows"][1]["issues"]
        assert preview["rows"][1]["source"]["diary_date"] is None
        with pytest.raises(NutritionDraftError, match="invalid_row"):
            set_resolutions(db, owner, draft.id, revision=1, matches={1: 1}, skipped_rows=[])


@pytest.mark.skipif(
    sys.platform != "linux"
    or not hasattr(os, "memfd_create")
    or getattr(os, "geteuid", lambda: 0)() == 0,
    reason="requires a non-root Linux process with memfd",
)
def test_api_upload_uses_worker_and_keeps_unconfirmed_data_private(client, rows):
    if engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL transaction locks")
    owner = _auth(client, 984_200)
    other = _auth(client, 984_201)
    with get_session_context() as db:
        before = db.query(Food).count(), db.query(FoodDiaryEntry).count()

    def upload(source_rows, key):
        return client.post(
            "/api/v1/nutrition/imports",
            headers={**owner, "Idempotency-Key": key},
            data={"adapter_id": "fatsecret-csv-v1"},
            files={"file": ("synthetic.csv", _csv(source_rows), "text/csv")},
        )

    response = upload(rows, "synthetic-api-884")
    assert response.status_code == 201
    preview = response.json()
    assert preview["schema_version"] == "nutrition-import-v3"
    cell = next(
        item for item in preview["original_detail_cells"] if item["coordinates"]["row"] == 10
    )
    assert cell["source_value"] == "0,50" and cell["nutrient_field"] is None
    draft_id = preview["id"]
    assert client.get(f"/api/v1/nutrition/imports/{draft_id}", headers=other).status_code == 404
    catalog = client.get(f"/api/v1/nutrition/imports/{draft_id}/catalog", headers=owner)
    assert catalog.status_code == 200
    assert all(item["outcome"] == "needs_review" for item in catalog.json()["rows"])
    confirm = client.post(
        f"/api/v1/nutrition/imports/{draft_id}/confirm",
        headers=owner,
        json={
            "revision": preview["revision"],
            "preview_signature": preview["preview_signature"],
            "confirm_key": "synthetic-confirm-884",
            "confirmed": True,
        },
    )
    assert confirm.status_code == 409 and confirm.json()["detail"]["code"] == "unresolved_rows"

    invalid = deepcopy(rows)
    invalid[6][1] = "Калории (кДж)"
    response = upload(invalid, "synthetic-invalid-884")
    assert response.status_code == 201
    failed = response.json()
    assert failed["rows"] == [] and failed["diagnostics"][0]["code"] == "unknown_detail_header"
    with get_session_context() as db:
        assert (db.query(Food).count(), db.query(FoodDiaryEntry).count()) == before
