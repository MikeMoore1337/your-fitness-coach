import csv
import io
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from decimal import Decimal
from threading import Barrier

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from test_training_analytics import _auth

from fitminiapp_api.db.session import engine, get_session_context
from fitminiapp_api.models.food import Food
from fitminiapp_api.models.food_diary import FoodDiaryEntry
from fitminiapp_api.models.nutrition_import import NutritionImportDraft
from fitminiapp_api.models.nutrition_label import NutritionCatalogContribution
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.nutrition_import import NutritionImportV1, NutritionImportV2
from fitminiapp_api.schemas.nutrition_import_engine import (
    CatalogConflictChoice,
    CatalogProductCorrection,
    ImportPreview,
)
from fitminiapp_api.services import nutrition_import_fatsecret_csv
from fitminiapp_api.services.nutrition_catalog_import import (
    catalog_import_preview,
    confirm_catalog_import,
)
from fitminiapp_api.services.nutrition_import_drafts import (
    NutritionDraftError,
    create_nutrition_import_draft,
    get_nutrition_import_draft,
    nutrition_import_preview,
    set_resolutions,
)
from fitminiapp_api.services.nutrition_import_fatsecret_csv import parse
from fitminiapp_api.services.nutrition_import_runner import ADAPTERS
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
SHORT_DETAIL_HEADER = [
    "Метка",
    "Кал ( ккал)",
    "Жир( г)",
    "Н/жир( г)",
    "Углев( г)",
    "Клетч( г)",
    "Сахар( г)",
    "Белк( г)",
    "Натри( мг)",
    "Холес( мг)",
    "Калий( мг)",
]
NUTRIENTS = ["12,30000001", "2,00", "0,50", "4,00", "", "0,00", "3,00", "1,00", "0,00", "5,00"]


@pytest.mark.parametrize("adapter_id", ["fatsecret-csv-v1", "fatsecret-pdf-v1"])
def test_owner_reported_permission_does_not_classify_products(adapter_id):
    adapter = ADAPTERS[adapter_id]
    assert adapter.catalog_publication_rights == frozenset({"owner_reported"})
    assert adapter.catalog_source == "diary_export"
    assert adapter.catalog_food_kinds == frozenset()


def test_review_and_confirm_corrected_fatsecret_row(rows):
    source, document = _validated(rows)
    with get_session_context() as db:
        owner = User(telegram_user_id=984_110, measurement_eligibility="test")
        other = User(telegram_user_id=984_111, measurement_eligibility="test")
        db.add_all([owner, other])
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
            upload_key="synthetic-review-885",
            adapter_id="fatsecret-csv-v1",
        )
        index = next(
            i
            for i, row in enumerate(document.rows)
            if not any(issue.severity == "error" for issue in row.diagnostics)
        )
        correction = CatalogProductCorrection.model_validate(
            {
                "index": index,
                "name": "Синтетический продукт",
                "kind": "standard_food",
                "nutrition": {
                    "source_basis": "per_100_g",
                    "energy_kcal": "65",
                    "protein_g": "4",
                    "fat_g": "3",
                    "carbohydrate_g": "5",
                },
                "confirmed": True,
            }
        )
        before = db.query(Food).count()
        preview = catalog_import_preview(db, owner, draft.id, revision=1, corrections=[correction])
        assert preview["rows"][index]["outcome"] == "publish"
        assert db.query(Food).count() == before
        with pytest.raises(NutritionDraftError, match="not_found"):
            catalog_import_preview(db, other, draft.id, revision=1, corrections=[correction])
        with pytest.raises(NutritionDraftError, match="stale_revision"):
            catalog_import_preview(db, owner, draft.id, revision=2, corrections=[correction])
        with pytest.raises(NutritionDraftError, match="invalid_rows"):
            catalog_import_preview(db, owner, draft.id, revision=1, corrections=[correction] * 2)
        kwargs = {
            "revision": 1,
            "preview_signature": preview["preview_signature"],
            "confirm_key": "confirm-correction-885",
            "row_indexes": [index],
            "confirmed": True,
            "corrections": [correction],
        }
        altered = correction.model_copy(deep=True)
        assert altered.nutrition is not None
        altered.nutrition.fat_g = Decimal("9")
        with pytest.raises(NutritionDraftError, match="preview_changed"):
            confirm_catalog_import(db, owner, draft.id, **{**kwargs, "corrections": [altered]})
        receipt = confirm_catalog_import(db, owner, draft.id, **kwargs)
        assert receipt["rows"][0]["outcome"] == "publish"
        assert len(receipt["excluded_rows"]) == len(document.rows) - 1
        assert confirm_catalog_import(db, owner, draft.id, **kwargs) == receipt
        assert db.query(Food).count() == before + 1
        second = create_nutrition_import_draft(
            db,
            other,
            document=document,
            source=source,
            filename="synthetic.csv",
            content_type="text/csv",
            delimiter=",",
            parser_version="fatsecret-csv-v1",
            upload_key="synthetic-review-886",
            adapter_id="fatsecret-csv-v1",
        )
        conflict = catalog_import_preview(db, other, second.id, revision=1, corrections=[altered])
        assert conflict["rows"][index]["outcome"] == "conflict"
        food_id = conflict["rows"][index]["food_id"]
        forged = CatalogConflictChoice(index=index, action="reuse", food_id=999999)
        with pytest.raises(NutritionDraftError, match="invalid_rows"):
            catalog_import_preview(
                db, other, second.id, revision=1, corrections=[altered], choices=[forged]
            )
        choice = CatalogConflictChoice(index=index, action="reuse", food_id=food_id)
        resolved = catalog_import_preview(
            db, other, second.id, revision=1, corrections=[altered], choices=[choice]
        )
        assert resolved["rows"][index]["reason"] == "user_selected_existing"
        contributions_before = db.query(NutritionCatalogContribution).count()
        reused = confirm_catalog_import(
            db,
            other,
            second.id,
            revision=1,
            preview_signature=resolved["preview_signature"],
            confirm_key="confirm-reuse-885",
            row_indexes=[index],
            confirmed=True,
            corrections=[altered],
            choices=[choice],
        )
        assert reused["rows"][0]["food_id"] == food_id
        assert db.query(NutritionCatalogContribution).count() == contributions_before
        assert db.query(Food).count() == before + 1
        third = create_nutrition_import_draft(
            db,
            owner,
            document=document,
            source=source,
            filename="synthetic.csv",
            content_type="text/csv",
            delimiter=",",
            parser_version="fatsecret-csv-v1",
            upload_key="synthetic-review-887",
            adapter_id="fatsecret-csv-v1",
        )
        skip = CatalogConflictChoice(index=index, action="skip")
        skipped_preview = catalog_import_preview(db, owner, third.id, revision=1, choices=[skip])
        skipped = confirm_catalog_import(
            db,
            owner,
            third.id,
            revision=1,
            preview_signature=skipped_preview["preview_signature"],
            confirm_key="confirm-skip-885",
            row_indexes=[],
            confirmed=True,
            choices=[skip],
        )
        assert skipped["rows"] == []
        assert skipped["excluded_rows"][index]["outcome"] == "skipped"
        assert db.query(Food).count() == before + 1
        db.rollback()


def test_catalog_review_api_enforces_owner_and_explicit_confirmation(client, rows):
    owner_headers = _auth(client, 984120)
    other_headers = _auth(client, 984121)
    source, document = _validated(rows)
    with get_session_context() as db:
        owner = db.query(User).filter_by(telegram_user_id=984120).one()
        draft = create_nutrition_import_draft(
            db,
            owner,
            document=document,
            source=source,
            filename="synthetic.csv",
            content_type="text/csv",
            delimiter=",",
            parser_version="fatsecret-csv-v1",
            upload_key="synthetic-api-885",
            adapter_id="fatsecret-csv-v1",
        )
        draft_id = draft.id
        db.commit()
    index = next(
        i
        for i, row in enumerate(document.rows)
        if not any(issue.severity == "error" for issue in row.diagnostics)
    )
    correction = {
        "index": index,
        "name": "Синтетический продукт",
        "kind": "standard_food",
        "nutrition": {
            "source_basis": "per_100_g",
            "energy_kcal": "65",
            "protein_g": "4",
            "fat_g": "3",
            "carbohydrate_g": "5",
        },
        "confirmed": True,
    }
    root = f"/api/v1/nutrition/imports/{draft_id}/catalog"
    body = {"revision": 1, "corrections": [correction], "choices": []}
    assert client.post(f"{root}/review", headers=other_headers, json=body).status_code == 404
    assert (
        client.post(
            f"{root}/review", headers=owner_headers, json={**body, "revision": 2}
        ).status_code
        == 409
    )
    invalid = {**correction, "confirmed": False}
    assert (
        client.post(
            f"{root}/review", headers=owner_headers, json={**body, "corrections": [invalid]}
        ).status_code
        == 422
    )
    preview = client.post(f"{root}/review", headers=owner_headers, json=body)
    assert preview.status_code == 200
    assert preview.headers["cache-control"] == "no-store, private"
    confirm = {
        **body,
        "preview_signature": preview.json()["preview_signature"],
        "confirm_key": "api-confirm-885",
        "row_indexes": [index],
        "confirmed": True,
    }
    assert client.post(f"{root}/confirm", headers=other_headers, json=confirm).status_code == 404
    assert (
        client.post(
            f"{root}/confirm", headers=owner_headers, json={**confirm, "confirmed": False}
        ).status_code
        == 422
    )
    result = client.post(f"{root}/confirm", headers=owner_headers, json=confirm)
    assert result.status_code == 200
    assert result.json()["rows"][0]["outcome"] == "publish"
    assert (
        client.post(f"{root}/confirm", headers=owner_headers, json=confirm).json() == result.json()
    )


def test_completed_catalog_imports_do_not_exhaust_active_draft_limit(rows):
    source, document = _validated(rows)
    with get_session_context() as db:
        owner = User(telegram_user_id=984139, measurement_eligibility="test")
        db.add(owner)
        db.flush()
        for index in range(4):
            draft = create_nutrition_import_draft(
                db,
                owner,
                document=document,
                source=source,
                filename="synthetic.csv",
                content_type="text/csv",
                delimiter=",",
                parser_version="fatsecret-csv-v1",
                upload_key=f"limit-upload-885-{index}",
                adapter_id="fatsecret-csv-v1",
            )
            preview = catalog_import_preview(db, owner, draft.id)
            receipt = confirm_catalog_import(
                db,
                owner,
                draft.id,
                revision=1,
                preview_signature=preview["preview_signature"],
                confirm_key=f"limit-confirm-885-{index}",
                row_indexes=[],
                confirmed=True,
            )
            assert receipt["rows"] == []
        other = User(telegram_user_id=984138, measurement_eligibility="test")
        db.add(other)
        db.flush()
        for index in range(3):
            create_nutrition_import_draft(
                db,
                other,
                document=document,
                source=source,
                filename="synthetic.csv",
                content_type="text/csv",
                delimiter=",",
                parser_version="fatsecret-csv-v1",
                upload_key=f"pending-upload-885-{index}",
                adapter_id="fatsecret-csv-v1",
            )
        with pytest.raises(NutritionDraftError, match="draft_limit"):
            create_nutrition_import_draft(
                db,
                other,
                document=document,
                source=source,
                filename="synthetic.csv",
                content_type="text/csv",
                delimiter=",",
                parser_version="fatsecret-csv-v1",
                upload_key="pending-upload-885-fourth",
                adapter_id="fatsecret-csv-v1",
            )
        db.rollback()


def test_concurrent_corrected_imports_do_not_duplicate_catalog_food(rows):
    if engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL transaction and uniqueness behavior")
    source, document = _validated(rows)
    index = next(
        i
        for i, row in enumerate(document.rows)
        if not any(issue.severity == "error" for issue in row.diagnostics)
    )
    correction = CatalogProductCorrection.model_validate(
        {
            "index": index,
            "name": "Синтетический продукт гонка 885",
            "kind": "standard_food",
            "nutrition": {
                "source_basis": "per_100_g",
                "energy_kcal": "65",
                "protein_g": "4",
                "fat_g": "3",
                "carbohydrate_g": "5",
            },
            "confirmed": True,
        }
    )
    drafts = []
    with get_session_context() as db:
        for number in range(2):
            user = User(telegram_user_id=984140 + number, measurement_eligibility="test")
            db.add(user)
            db.flush()
            draft = create_nutrition_import_draft(
                db,
                user,
                document=document,
                source=source,
                filename="synthetic.csv",
                content_type="text/csv",
                delimiter=",",
                parser_version="fatsecret-csv-v1",
                upload_key=f"concurrent-upload-885-{number}",
                adapter_id="fatsecret-csv-v1",
            )
            preview = catalog_import_preview(
                db, user, draft.id, revision=1, corrections=[correction]
            )
            drafts.append((user.id, draft.id, preview["preview_signature"], number))
        db.commit()
    barrier = Barrier(2)

    def submit(item):
        user_id, draft_id, signature, number = item
        with get_session_context() as db:
            user = db.get(User, user_id)
            barrier.wait(timeout=10)
            try:
                result = confirm_catalog_import(
                    db,
                    user,
                    draft_id,
                    revision=1,
                    preview_signature=signature,
                    confirm_key=f"concurrent-confirm-885-{number}",
                    row_indexes=[index],
                    confirmed=True,
                    corrections=[correction],
                )
                db.commit()
                return result["rows"][0]["outcome"]
            except IntegrityError, NutritionDraftError:
                db.rollback()
                return "refresh"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, drafts))
    assert results.count("publish") == 1
    with get_session_context() as db:
        assert db.query(Food).filter_by(name="Синтетический продукт гонка 885").count() == 1
        for (user_id, draft_id, _, number), result in zip(drafts, results, strict=True):
            if result != "refresh":
                continue
            user = db.get(User, user_id)
            preview = catalog_import_preview(
                db, user, draft_id, revision=1, corrections=[correction]
            )
            assert preview["rows"][index]["outcome"] == "reuse"
            receipt = confirm_catalog_import(
                db,
                user,
                draft_id,
                revision=1,
                preview_signature=preview["preview_signature"],
                confirm_key=f"concurrent-confirm-885-retry-{number}",
                row_indexes=[index],
                confirmed=True,
                corrections=[correction],
            )
            assert receipt["rows"][0]["outcome"] == "reuse"
        assert db.query(Food).filter_by(name="Синтетический продукт гонка 885").count() == 1


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


@pytest.mark.parametrize("name", ["=2+2", "+2+2", "-2+2", "@SUM(1,2)", "  =2+2"])
def test_imported_formula_like_food_name_is_escaped_in_account_csv(rows, name):
    from fitminiapp_api.services.account_exports import _csv_bytes

    rows[9][0] = name
    _, result = _validated(rows)
    imported_name = result.rows[0].food.name
    assert imported_name.lstrip() == name.lstrip()
    output = _csv_bytes([{"food_name": imported_name}], ("food_name",))
    exported = list(csv.DictReader(io.StringIO(output.decode("utf-8-sig"))))
    assert exported == [{"food_name": "'" + imported_name}]


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


def test_hash_separators_are_ignored_but_other_hash_lines_fail_closed(rows):
    rows.insert(0, ["#-------------------------------------------"])
    details = rows.index(["# Report Details"])
    rows.insert(details, ["#-------------------------------------------"])
    _, result = _validated(rows)
    assert len(result.rows) == 6
    assert result.rows[0].food.name == "Тестовый продукт, альфа"

    rows.insert(details, ["# unknown section"])
    result = parse(_csv(rows))
    assert result["rows"] == []
    assert result["diagnostics"][0]["code"] == "unknown_summary_structure"


def test_russian_detailed_report_layout_preserves_context_and_skips_totals():
    summary_header = ["Сводка", "Кал ( ккал)", "Жир( г)", "Углев( г)", "Белк( г)"]
    rows = [
        ["#-------------------------------------------"],
        [
            "# Food Diary Report - Detailed Report",
            "Суббота, марта 2, 2024",
            "Воскресенье, марта 3, 2024",
        ],
        ["#-------------------------------------------"],
        ["# Period Summary"],
        summary_header,
        ["Всего", "12,30", "2,00", "4,00", "3,00"],
        ["Перекус/Другое", "12,30", "2,00", "4,00", "3,00"],
        ["# Report Details"],
        SHORT_DETAIL_HEADER[:],
        ["Суббота, марта 2, 2024", *NUTRIENTS],
        ["Перекус/Другое", *NUTRIENTS],
        ["Синтетический продукт", *NUTRIENTS],
        ["2 порции (100 г)"],
        ["Всего", *NUTRIENTS],
    ]
    _, result = _validated(rows)
    assert len(result.rows) == 1
    assert result.rows[0].food.name == "Синтетический продукт"
    assert result.rows[0].diary_date.isoformat() == "2024-03-02"
    assert result.rows[0].meal_type == "snacks"
    assert result.rows[0].serving_label == "2 порции (100 г)"
    assert result.rows[0].quantity == Decimal("2")
    assert result.rows[0].amount_unit == "serving"
    assert result.rows[0].serving_measure is None
    assert [(x.scope, x.coordinates.row) for x in result.original_totals] == [
        ("day", 10),
        ("meal", 11),
        ("unknown", 12),
        ("unknown", 14),
    ]
    summary = result.original_summaries[0]
    assert (summary.period_start.isoformat(), summary.period_end.isoformat()) == (
        "2024-03-02",
        "2024-03-03",
    )
    assert summary.aggregation.kind == "unknown"

    for change, code in (
        (lambda r: r[1].__setitem__(0, "# Unknown Report"), "unknown_sections"),
        (lambda r: r[1].__setitem__(1, "Понедельник, марта 4, 2024"), "invalid_period"),
        (lambda r: r[9].__setitem__(0, "Вторник, марта 2, 2024"), "invalid_date"),
        (lambda r: r[9].__setitem__(0, "Суббота, марта 32, 2024"), "invalid_date"),
        (lambda r: r[8].__setitem__(2, "Жир(мг)"), "unknown_detail_header"),
    ):
        invalid = deepcopy(rows)
        change(invalid)
        rejected = parse(_csv(invalid))
        assert rejected["rows"] == []
        assert rejected["diagnostics"][0]["code"] == code


def test_single_day_report_has_no_fabricated_summary_and_checks_its_date():
    rows = [
        ["#-------------------------------------------"],
        ["# Food Diary Report - Detailed Report", "Суббота, марта 2, 2024"],
        ["#-------------------------------------------"],
        ["# Report Details"],
        SHORT_DETAIL_HEADER[:],
        ["Суббота, марта 2, 2024", *NUTRIENTS],
        ["Завтрак", *NUTRIENTS],
        ["Синтетический продукт", *NUTRIENTS],
        ["100 г"],
        ["Всего", *NUTRIENTS],
    ]
    _, result = _validated(rows)
    assert result.original_summaries == []
    assert len(result.rows) == 1
    assert result.rows[0].diary_date.isoformat() == "2024-03-02"
    assert result.rows[0].food.name == "Синтетический продукт"
    assert [(item.scope, item.coordinates.row) for item in result.original_totals] == [
        ("day", 6),
        ("meal", 7),
        ("unknown", 8),
        ("unknown", 10),
    ]
    assert not any(issue.code == "summary_aggregation_unknown" for issue in result.diagnostics)
    daily_facts = next(item.facts for item in result.original_totals if item.coordinates.row == 8)
    assert daily_facts.fiber_g.evidence == "absent"
    assert daily_facts.sugars_g.value == Decimal("0.00")
    assert (
        next(
            cell for cell in result.original_detail_cells if cell.coordinates.row == 8
        ).source_value
        == "0,50"
    )

    period_rows = [
        [
            "# Food Diary Report - Detailed Report",
            "Суббота, марта 2, 2024",
            "Воскресенье, марта 3, 2024",
        ],
        ["# Period Summary"],
        SUMMARY_HEADER[:],
        ["# Report Details"],
        *rows[4:],
    ]
    _, period = _validated(period_rows)
    period_item = period.rows[0]
    period_facts = next(
        item.facts
        for item in period.original_totals
        if item.coordinates.row == period_item.coordinates.row
    )
    assert period_item.food == result.rows[0].food
    assert period_item.diary_date == result.rows[0].diary_date
    assert period_item.serving_label == result.rows[0].serving_label
    assert period_facts == daily_facts

    for change, code in (
        (lambda r: r[1].__setitem__(0, "# Unknown Report"), "unknown_sections"),
        (lambda r: r[1].__setitem__(1, "Воскресенье, марта 3, 2024"), "date_outside_period"),
        (lambda r: r[4].__setitem__(2, "Жир(мг)"), "unknown_detail_header"),
        (lambda r: r.append(["# Report Details"]), "unknown_sections"),
        (lambda r: r.pop(1), "unknown_sections"),
    ):
        invalid = deepcopy(rows)
        change(invalid)
        rejected = parse(_csv(invalid))
        assert rejected["rows"] == []
        assert rejected["diagnostics"][0]["code"] == code


def test_single_day_report_with_no_foods_does_not_create_entries():
    rows = [
        ["# Food Diary Report - Detailed Report", "Суббота, марта 2, 2024"],
        ["# Report Details"],
        SHORT_DETAIL_HEADER[:],
        ["Суббота, марта 2, 2024", *([""] * 10)],
        ["Завтрак", *([""] * 10)],
        ["Обед", *([""] * 10)],
        ["Ужин", *([""] * 10)],
        ["Перекус/Другое", *([""] * 10)],
        ["Всего", *([""] * 10)],
    ]
    _, result = _validated(rows)
    assert result.rows == []
    assert result.original_summaries == []
    assert result.original_totals == []


def test_descriptive_quantity_does_not_taint_the_following_date(rows):
    rows[10] = ["1 чашка (100 г)"]
    _, result = _validated(rows)
    assert any(issue.code == "unknown_unit" for issue in result.rows[0].diagnostics)
    assert result.rows[0].serving_label == "1 чашка (100 г)"
    assert result.rows[1].diary_date.isoformat() == "2024-02-29"
    assert not any(issue.code == "source_context_ambiguous" for issue in result.rows[1].diagnostics)

    rows[10] = ["2 x 3 порции (100 г)"]
    _, result = _validated(rows)
    assert result.rows[0].quantity is None and result.rows[0].amount_unit is None
    assert any(issue.code == "quantity_unrecognized" for issue in result.rows[0].diagnostics)
    assert result.rows[1].diary_date.isoformat() == "2024-02-29"

    rows[10] = ["1 марта (2024 г)"]
    _, result = _validated(rows)
    assert result.rows[1].diary_date is None
    assert any(issue.code == "source_context_ambiguous" for issue in result.rows[1].diagnostics)


def test_serving_with_comma_keeps_quantity_without_guessing_mass(rows):
    rows[10] = ["1 порция, 100 г"]
    _, result = _validated(rows)
    assert result.rows[0].quantity == Decimal("1")
    assert result.rows[0].amount_unit == "serving"
    assert result.rows[0].serving_measure is None
    assert result.rows[0].serving_label == "1 порция, 100 г"


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Понедельник, января 1, 2024", "2024-01-01"),
        ("Четверг, февраля 29, 2024", "2024-02-29"),
        ("Среда, мая 1, 2024", "2024-05-01"),
        ("Вторник, октября 1, 2024", "2024-10-01"),
        ("Вторник, декабря 31, 2024", "2024-12-31"),
    ],
)
def test_russian_report_dates_across_months(rows, label, expected):
    rows[1] = ["Период: 01.01.2024–31.12.2024"]
    rows[7] = [label, *NUTRIENTS]
    _, result = _validated(rows)
    assert result.rows[0].diary_date.isoformat() == expected
    assert result.original_totals[0].scope == "day"


def test_daily_meal_totals_are_compared_only_with_complete_source_values():
    def values(energy):
        return [energy, *([""] * 9)]

    rows = [
        ["# Period Summary"],
        SUMMARY_HEADER[:],
        ["# Report Details"],
        DETAIL_HEADER[:],
        ["Суббота, марта 2, 2024", *values("10")],
    ]
    for meal, energy in (("Завтрак", "1"), ("Обед", "2"), ("Ужин", "3"), ("Перекус", "4")):
        rows.extend(
            [[meal, *values(energy)], ["Синтетический продукт", *values(energy)], ["100 г"]]
        )

    _, result = _validated(rows)
    assert not any(issue.code == "day_meal_totals_differ" for issue in result.diagnostics)

    rows[4][1] = "11"
    _, result = _validated(rows)
    issue = next(issue for issue in result.diagnostics if issue.code == "day_meal_totals_differ")
    assert issue.severity == "warning" and issue.coordinates.row == 5
    assert issue.field == "energy_kcal"

    rows[8][1] = ""
    _, result = _validated(rows)
    assert not any(issue.code == "day_meal_totals_differ" for issue in result.diagnostics)

    rows[8][1] = "2"
    rows[14][0] = "Ужин"
    _, result = _validated(rows)
    assert not any(issue.code == "day_meal_totals_differ" for issue in result.diagnostics)


def _source_comparison_rows():
    def values(energy, fat, unmapped):
        return [energy, fat, unmapped, *([""] * 7)]

    return [
        ["# Period Summary"],
        SUMMARY_HEADER[:],
        ["# Report Details"],
        DETAIL_HEADER[:],
        ["Суббота, марта 2, 2024", *values("11", "2", "0,30")],
        ["Завтрак", *values("10", "2,1", "0,20")],
        ["Синтетический продукт A", *values("4", "0,8", "0,08")],
        ["100 г"],
        ["Синтетический продукт B", *values("6", "1,2", "0,12")],
        ["100 г"],
        ["Обед", *values("0", "0", "0")],
        ["Ужин", *values("0", "0", "0")],
        ["Перекус", *values("0", "0", "0")],
    ]


def test_source_differences_preserve_opaque_column_and_do_not_guess_rounding():
    _, result = _validated(_source_comparison_rows())
    differences = {
        (issue.code, issue.field, issue.coordinates.row)
        for issue in result.diagnostics
        if issue.code
        in {
            "day_meal_totals_differ",
            "meal_source_values_differ",
            "day_source_values_differ",
        }
    }
    assert differences == {
        ("meal_source_values_differ", "fat_g", 6),
        ("day_meal_totals_differ", "energy_kcal", 5),
        ("day_meal_totals_differ", "fat_g", 5),
        ("day_meal_totals_differ", "source_column_4", 5),
        ("day_source_values_differ", "energy_kcal", 5),
        ("day_source_values_differ", "source_column_4", 5),
    }
    assert all(row.nutrition.basis is None for row in result.rows)
    cell = next(cell for cell in result.original_detail_cells if cell.coordinates.row == 7)
    assert cell.source_value == "0,08" and cell.nutrient_field is None
    assert (
        "округл"
        not in json.dumps(
            [issue.model_dump() for issue in result.diagnostics], ensure_ascii=False
        ).lower()
    )


def test_source_comparisons_skip_missing_values_and_ambiguous_context():
    rows = _source_comparison_rows()
    rows[8][2] = rows[8][3] = ""
    _, result = _validated(rows)
    assert not any(
        issue.code in {"meal_source_values_differ", "day_source_values_differ"}
        and issue.field in {"fat_g", "source_column_4"}
        for issue in result.diagnostics
    )
    assert any(
        issue.code == "day_meal_totals_differ" and issue.field == "source_column_4"
        for issue in result.diagnostics
    )

    rows = _source_comparison_rows()
    rows.insert(10, ["Завтрак"])
    _, result = _validated(rows)
    assert not any(
        issue.code
        in {"day_meal_totals_differ", "meal_source_values_differ", "day_source_values_differ"}
        for issue in result.diagnostics
    )

    rows = _source_comparison_rows()
    rows[7] = ["неизвестная порция"]
    _, result = _validated(rows)
    assert not any(
        issue.code
        in {"day_meal_totals_differ", "meal_source_values_differ", "day_source_values_differ"}
        for issue in result.diagnostics
    )


def test_source_difference_diagnostics_are_bounded(monkeypatch):
    monkeypatch.setattr(nutrition_import_fatsecret_csv, "_MAX_COMPARISON_DIAGNOSTICS", 2)
    _, result = _validated(_source_comparison_rows())
    assert sum(issue.code == "source_differences_truncated" for issue in result.diagnostics) == 1


def test_source_differences_respect_shared_adapter_diagnostics_limit(monkeypatch):
    monkeypatch.setattr(nutrition_import_fatsecret_csv, "MAX_ADAPTER_LIST", 4)
    _, result = _validated(_source_comparison_rows())
    assert len(result.diagnostics) == 4
    assert result.diagnostics[-1].code == "source_differences_truncated"

    monkeypatch.setattr(nutrition_import_fatsecret_csv, "MAX_ADAPTER_LIST", 2)
    result = parse(_csv(_source_comparison_rows()))
    assert result["rows"] == []
    assert result["diagnostics"][0]["code"] == "adapter_diagnostics_limit"


@pytest.mark.parametrize(
    ("change", "code"),
    [
        (lambda r: r[6].__setitem__(1, "Калории (кДж)"), "unknown_detail_header"),
        (lambda r: r[2].__setitem__(1, "Неизвестно"), "unknown_summary_structure"),
        (lambda r: r[7].__setitem__(0, "Дата: 31.02.2024"), "invalid_date"),
        (lambda r: r[7].__setitem__(0, "Дата: 01.01.2024"), "date_outside_period"),
        (lambda r: r[10].__setitem__(0, "Дата: 01.03.2024"), "quantity_association_ambiguous"),
        (lambda r: r[10].__setitem__(0, "Дата 01.03.2024"), "quantity_association_ambiguous"),
        (lambda r: r[10].__setitem__(0, "01.03.2024"), "quantity_association_ambiguous"),
        (lambda r: r[10].__setitem__(0, "1 марта 2024 г."), "quantity_association_ambiguous"),
        (lambda r: r[9].__setitem__(0, "Итого за приём пищи"), "unknown_total_scope"),
        (lambda r: r[9].__setitem__(0, "Промежуточный итог"), "unknown_total_scope"),
        (lambda r: r[9].__setitem__(0, "Дневной итог"), "unknown_total_scope"),
        (lambda r: r[11].__setitem__(0, "Итого, приём пищи"), "unknown_total_scope"),
        (lambda r: r[9].__setitem__(0, "Всего"), "unknown_total_scope"),
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
        assert any(
            issue.code == "meal_source_values_differ" and issue.field == "energy_kcal"
            for issue in preview.diagnostics
        )
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

    daily_rows = [
        ["# Food Diary Report - Detailed Report", "Четверг, февраля 29, 2024"],
        ["# Report Details"],
        SHORT_DETAIL_HEADER[:],
        ["Четверг, февраля 29, 2024", *NUTRIENTS],
        ["Завтрак", *NUTRIENTS],
        ["Синтетический продукт", *NUTRIENTS],
        ["100 г"],
        ["Всего", *NUTRIENTS],
    ]
    daily = upload(daily_rows, "synthetic-day-api-884")
    assert daily.status_code == 201
    daily_preview = daily.json()
    assert daily_preview["original_summaries"] == []
    assert len(daily_preview["rows"]) == 1
    assert daily_preview["rows"][0]["source"]["diary_date"] == "2024-02-29"
    assert (
        client.get(f"/api/v1/nutrition/imports/{daily_preview['id']}", headers=other).status_code
        == 404
    )

    invalid = deepcopy(rows)
    invalid[6][1] = "Калории (кДж)"
    response = upload(invalid, "synthetic-invalid-884")
    assert response.status_code == 201
    failed = response.json()
    assert failed["rows"] == [] and failed["diagnostics"][0]["code"] == "unknown_detail_header"
    with get_session_context() as db:
        assert (db.query(Food).count(), db.query(FoodDiaryEntry).count()) == before


@pytest.mark.skipif(
    sys.platform != "linux"
    or not hasattr(os, "memfd_create")
    or getattr(os, "geteuid", lambda: 0)() == 0,
    reason="requires a non-root Linux process with memfd",
)
def test_real_csv_upload_review_and_catalog_confirm(client, rows):
    if engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL transaction locks")
    owner = _auth(client, 984_230)
    other = _auth(client, 984_231)
    root = "/api/v1/nutrition/imports"
    upload = client.post(
        root,
        headers={**owner, "Idempotency-Key": "csv-full-885"},
        data={"adapter_id": "fatsecret-csv-v1"},
        files={"file": ("synthetic.csv", _csv(rows), "text/csv")},
    )
    assert upload.status_code == 201, upload.text
    draft = upload.json()
    index = next(
        row["index"]
        for row in draft["rows"]
        if not any(item["severity"] == "error" for item in row["source"].get("diagnostics", []))
    )
    correction = {
        "index": index,
        "name": "Синтетический продукт тест 885",
        "kind": "standard_food",
        "nutrition": {
            "source_basis": "per_100_g",
            "energy_kcal": "65",
            "protein_g": "4",
            "fat_g": "3",
            "carbohydrate_g": "5",
        },
        "confirmed": True,
    }
    body = {"revision": draft["revision"], "corrections": [correction], "choices": []}
    endpoint = f"{root}/{draft['id']}/catalog"
    preview = client.post(f"{endpoint}/review", headers=owner, json=body)
    assert preview.status_code == 200, preview.text
    assert preview.json()["rows"][index]["outcome"] == "publish"
    confirm = {
        **body,
        "preview_signature": preview.json()["preview_signature"],
        "confirm_key": "csv-full-confirm-885",
        "row_indexes": [index],
        "confirmed": True,
    }
    first = client.post(f"{endpoint}/confirm", headers=owner, json=confirm)
    assert first.status_code == 200, first.text
    assert first.json()["rows"][0]["outcome"] == "publish"
    assert client.post(f"{endpoint}/confirm", headers=owner, json=confirm).json() == first.json()
    food_id = first.json()["rows"][0]["food_id"]
    assert client.get(f"/api/v1/nutrition/foods/{food_id}", headers=other).status_code == 200
    assert client.get(f"{root}/{draft['id']}", headers=other).status_code == 404
    search = client.get(
        "/api/v1/nutrition/foods/search", headers=other, params={"q": correction["name"]}
    )
    assert search.status_code == 200
    found = next(item for item in search.json()["items"] if item["id"] == food_id)
    assert found["catalog_quality"] == "community_unverified"
    entry = client.post(
        "/api/v1/nutrition/diary/entries",
        headers=other,
        json={
            "food_id": food_id,
            "diary_date": "2024-03-02",
            "meal_type": "breakfast",
            "amount": "100",
            "amount_unit": "g",
        },
    )
    assert entry.status_code == 201
    assert (
        client.delete(
            f"/api/v1/nutrition/diary/entries/{entry.json()['id']}", headers=owner
        ).status_code
        == 404
    )
    owner_day = client.get(
        "/api/v1/nutrition/diary", headers=owner, params={"diary_date": "2024-03-02"}
    )
    assert owner_day.status_code == 200
    assert all(not meal["entries"] for meal in owner_day.json()["meals"])
    owner_entry = client.post(
        "/api/v1/nutrition/diary/entries",
        headers=owner,
        json={
            "food_id": food_id,
            "diary_date": "2024-03-02",
            "meal_type": "breakfast",
            "amount": "50",
            "amount_unit": "g",
        },
    )
    assert owner_entry.status_code == 201
    assert (
        client.delete(
            f"/api/v1/nutrition/diary/entries/{owner_entry.json()['id']}", headers=other
        ).status_code
        == 404
    )
    other_day = client.get(
        "/api/v1/nutrition/diary", headers=other, params={"diary_date": "2024-03-02"}
    )
    assert other_day.status_code == 200
    assert [item["id"] for meal in other_day.json()["meals"] for item in meal["entries"]] == [
        entry.json()["id"]
    ]

    repeat = client.post(
        root,
        headers={**other, "Idempotency-Key": "csv-full-upload-b"},
        data={"adapter_id": "fatsecret-csv-v1"},
        files={"file": ("synthetic.csv", _csv(rows), "text/csv")},
    )
    assert repeat.status_code == 201, repeat.text
    repeat_draft = repeat.json()
    repeat_body = {**body, "revision": repeat_draft["revision"]}
    repeat_endpoint = f"{root}/{repeat_draft['id']}/catalog"
    repeat_preview = client.post(f"{repeat_endpoint}/review", headers=other, json=repeat_body)
    assert repeat_preview.status_code == 200, repeat_preview.text
    assert repeat_preview.json()["rows"][index]["outcome"] == "reuse"
    repeat_confirm = client.post(
        f"{repeat_endpoint}/confirm",
        headers=other,
        json={
            **repeat_body,
            "preview_signature": repeat_preview.json()["preview_signature"],
            "confirm_key": "csv-full-confirm-b",
            "row_indexes": [index],
            "confirmed": True,
        },
    )
    assert repeat_confirm.status_code == 200, repeat_confirm.text
    assert repeat_confirm.json()["rows"][0]["food_id"] == food_id
    owner_after = client.get(
        "/api/v1/nutrition/diary", headers=owner, params={"diary_date": "2024-03-02"}
    )
    assert owner_after.status_code == 200
    assert [entry["id"] for meal in owner_after.json()["meals"] for entry in meal["entries"]] == [
        owner_entry.json()["id"]
    ]
    with get_session_context() as db:
        assert db.query(Food).filter_by(name=correction["name"]).count() == 1


def test_stale_catalog_preview_requires_explicit_review_without_partial_writes(client, rows):
    if engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL transaction locks")
    owner = _auth(client, 984_240)
    other = _auth(client, 984_241)
    root = "/api/v1/nutrition/imports"

    def upload(headers, key):
        result = client.post(
            root,
            headers={**headers, "Idempotency-Key": key},
            data={"adapter_id": "fatsecret-csv-v1"},
            files={"file": ("synthetic.csv", _csv(rows), "text/csv")},
        )
        assert result.status_code == 201, result.text
        return result.json()

    first, second = upload(owner, "stale-upload-a-888"), upload(other, "stale-upload-b-888")
    indices = [
        row["index"]
        for row in first["rows"]
        if not any(item["severity"] == "error" for item in row["source"].get("diagnostics", []))
    ][:2]
    assert len(indices) == 2

    def correction(index, name):
        return {
            "index": index,
            "name": name,
            "kind": "standard_food",
            "nutrition": {
                "source_basis": "per_100_g",
                "energy_kcal": "65",
                "protein_g": "4",
                "fat_g": "3",
                "carbohydrate_g": "5",
            },
            "confirmed": True,
        }

    common = correction(indices[0], "Синтетический общий продукт 888")
    additional = correction(indices[1], "Синтетический второй продукт 888")
    first_endpoint = f"{root}/{first['id']}/catalog"
    second_endpoint = f"{root}/{second['id']}/catalog"
    first_body = {"revision": first["revision"], "corrections": [common], "choices": []}
    second_body = {
        "revision": second["revision"],
        "corrections": [common, additional],
        "choices": [],
    }
    first_preview = client.post(f"{first_endpoint}/review", headers=owner, json=first_body)
    stale = client.post(f"{second_endpoint}/review", headers=other, json=second_body)
    assert first_preview.status_code == stale.status_code == 200
    assert stale.json()["rows"][indices[0]]["outcome"] == "publish"
    assert stale.json()["rows"][indices[1]]["outcome"] == "publish"
    first_confirm = {
        **first_body,
        "preview_signature": first_preview.json()["preview_signature"],
        "confirm_key": "stale-confirm-a-888",
        "row_indexes": [indices[0]],
        "confirmed": True,
    }
    published = client.post(f"{first_endpoint}/confirm", headers=owner, json=first_confirm)
    assert published.status_code == 200, published.text
    food_id = published.json()["rows"][0]["food_id"]
    assert published.json()["rows"][0]["outcome"] == "publish"

    for headers in (owner, other):
        entry = client.post(
            "/api/v1/nutrition/diary/entries",
            headers=headers,
            json={
                "food_id": food_id,
                "diary_date": "2024-03-02",
                "meal_type": "breakfast",
                "amount": "50",
                "amount_unit": "g",
            },
        )
        assert entry.status_code == 201, entry.text

    def diary(headers):
        response = client.get(
            "/api/v1/nutrition/diary", headers=headers, params={"diary_date": "2024-03-02"}
        )
        assert response.status_code == 200
        return response.json()

    diaries_before = [diary(owner), diary(other)]
    with get_session_context() as db:
        contributions_before = db.query(NutritionCatalogContribution).count()
    second_confirm = {
        **second_body,
        "preview_signature": stale.json()["preview_signature"],
        "confirm_key": "stale-confirm-b-888",
        "row_indexes": indices,
        "confirmed": True,
    }
    rejected = client.post(f"{second_endpoint}/confirm", headers=other, json=second_confirm)
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "preview_changed"
    with get_session_context() as db:
        assert db.query(Food).filter_by(name=common["name"]).count() == 1
        assert db.query(Food).filter_by(name=additional["name"]).count() == 0
        assert db.query(NutritionCatalogContribution).count() == contributions_before
        assert db.get(NutritionImportDraft, second["id"]).catalog_receipt is None
    assert [diary(owner), diary(other)] == diaries_before

    refreshed = client.post(f"{second_endpoint}/review", headers=other, json=second_body)
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["preview_signature"] != stale.json()["preview_signature"]
    assert refreshed.json()["rows"][indices[0]]["outcome"] == "reuse"
    assert refreshed.json()["rows"][indices[0]]["food_id"] == food_id
    assert refreshed.json()["rows"][indices[1]]["outcome"] == "publish"
    second_confirm["preview_signature"] = refreshed.json()["preview_signature"]
    unconfirmed = client.post(
        f"{second_endpoint}/confirm", headers=other, json={**second_confirm, "confirmed": False}
    )
    assert unconfirmed.status_code == 422
    completed = client.post(f"{second_endpoint}/confirm", headers=other, json=second_confirm)
    assert completed.status_code == 200, completed.text
    assert [item["outcome"] for item in completed.json()["rows"]] == ["reuse", "publish"]
    repeated = client.post(f"{second_endpoint}/confirm", headers=other, json=second_confirm)
    assert repeated.status_code == 200 and repeated.json() == completed.json()
    with get_session_context() as db:
        assert db.query(Food).filter_by(name=common["name"]).count() == 1
        assert db.query(Food).filter_by(name=additional["name"]).count() == 1
    assert [diary(owner), diary(other)] == diaries_before
