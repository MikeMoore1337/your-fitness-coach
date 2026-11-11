import csv
import io
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import pytest
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.food import Food
from fitminiapp_api.models.food_diary import FoodDiaryEntry
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.nutrition_import import NutritionImportV3
from fitminiapp_api.services.nutrition_import_drafts import (
    NutritionDraftError,
    create_nutrition_import_draft,
    get_nutrition_import_draft,
    nutrition_import_preview,
)
from fitminiapp_api.services.nutrition_import_fatsecret_csv import DETAIL_HEADERS, SUMMARY_HEADERS
from fitminiapp_api.services.nutrition_import_fatsecret_csv import parse as parse_csv
from fitminiapp_api.services.nutrition_import_fatsecret_pdf import parse
from fitminiapp_api.services.nutrition_import_runner import run_nutrition_import_adapter
from fitminiapp_api.services.nutrition_import_validation import NutritionImportValidationError


def synthetic_pdf(
    *, russian=False, second_page=False, mismatch=False, amount=None, wrapped=False, hyphen=False
):
    stream = BytesIO()
    pdf = Canvas(stream, pagesize=(1800, 800), pageCompression=0)
    font = Path(__file__).parents[1] / "fitminiapp_api/assets/fonts/Inter-Regular.ttf"
    pdfmetrics.registerFont(TTFont("SyntheticInter", str(font)))
    pdf.setFont("SyntheticInter", 10)
    pdf.drawString(20, 770, "Report Details")
    headers = [
        "Calories",
        "Fat",
        "Sat. Fat",
        "Carbs",
        "Fiber",
        "Sugar",
        "Protein",
        "Sodium",
        "Chol",
        "Potassium",
    ]
    if russian:
        headers = list(DETAIL_HEADERS)
    for i, text in enumerate(headers):
        pdf.drawString(400 + 130 * i, 740, text)
    pdf.drawString(20, 700, "Дата: 02.03.2024" if russian else "Date: 02.03.2024")
    pdf.drawString(20, 670, "Завтрак" if russian else "Breakfast")
    pdf.drawString(20, 640, amount or ("100 г" if russian else "100 g"))
    name = "Тестовый продукт" if russian else "Synthetic food"
    pdf.drawString(160, 640, name + (" -" if hyphen else ""))
    for i, text in enumerate(["12.3", "1", "0", "2", "0", "0", "3", "4", "0", "5"]):
        pdf.drawString(400 + 130 * i, 640, text)
    if wrapped:
        pdf.drawString(160, 625, "continued")
    if mismatch:
        pdf.drawString(20, 610, "Total Breakfast")
        pdf.drawString(400, 610, "99")
    if second_page:
        pdf.drawString(20, 30, "Page 1")
        pdf.showPage()
        pdf.setFont("SyntheticInter", 10)
        for i, text in enumerate(headers):
            pdf.drawString(400 + 130 * i, 740, text)
        pdf.drawString(20, 700, "100 g")
        pdf.drawString(160, 700, "Another food")
        pdf.drawString(400, 700, "10")
    pdf.save()
    return stream.getvalue()


@pytest.mark.parametrize(
    ("russian", "name"), [(False, "Synthetic food"), (True, "Тестовый продукт")]
)
def test_synthetic_detail_is_normalized_with_page_coordinates(russian, name):
    result = NutritionImportV3.model_validate(parse(synthetic_pdf(russian=russian)))
    assert len(result.rows) == 1
    row = result.rows[0]
    assert (row.food.name, str(row.diary_date), row.meal_type) == (
        name,
        "2024-03-02",
        "breakfast",
    )
    assert (str(row.quantity), row.amount_unit) == ("100", "g")
    assert row.coordinates.page == 1
    assert result.original_totals[0].facts.energy_kcal.value == Decimal("12.3")


def test_pdf_and_csv_agree_on_synthetic_russian_entry():
    data = io.StringIO(newline="")
    writer = csv.writer(data)
    writer.writerows(
        [
            ["# Period Summary"],
            ["Метка", *SUMMARY_HEADERS],
            ["# Report Details"],
            ["Метка", *DETAIL_HEADERS],
            ["Дата: 02.03.2024"],
            ["Завтрак"],
            ["Тестовый продукт", "12.3", "1", "0", "2", "0", "0", "3", "4", "0", "5"],
            ["100 г"],
        ]
    )
    pdf = NutritionImportV3.model_validate(parse(synthetic_pdf(russian=True)))
    csv_result = NutritionImportV3.model_validate(parse_csv(data.getvalue().encode()))
    p, c = pdf.rows[0], csv_result.rows[0]
    assert (p.food, p.diary_date, p.meal_type, p.quantity, p.amount_unit, p.nutrition) == (
        c.food,
        c.diary_date,
        c.meal_type,
        c.quantity,
        c.amount_unit,
        c.nutrition,
    )
    assert pdf.original_totals[0].facts == csv_result.original_totals[0].facts


def test_page_break_and_repeated_header_preserve_both_entries():
    result = NutritionImportV3.model_validate(parse(synthetic_pdf(second_page=True)))
    assert [(row.food.name, row.coordinates.page) for row in result.rows] == [
        ("Synthetic food", 1),
        ("Another food", 2),
    ]


def test_mismatched_meal_total_is_reported_before_confirm():
    result = NutritionImportV3.model_validate(parse(synthetic_pdf(mismatch=True)))
    assert len(result.rows) == 1
    assert any(
        item.code == "meal_source_values_differ" and item.field == "energy_kcal"
        for item in result.diagnostics
    )


def test_unknown_serving_unit_remains_unresolved():
    result = NutritionImportV3.model_validate(parse(synthetic_pdf(amount="2 cups")))
    row = result.rows[0]
    assert row.source_unit == "cups" and row.amount_unit is None and row.serving_measure is None
    assert any(item.code == "unknown_unit" for item in row.diagnostics)


def test_summary_only_and_corrupt_pdf_never_create_rows():
    stream = BytesIO()
    pdf = Canvas(stream)
    pdf.drawString(20, 700, "Period Summary")
    pdf.drawString(20, 670, "Synthetic aggregate 100")
    pdf.save()
    for source, code in [
        (stream.getvalue(), "pdf_no_details"),
        (b"%PDF-1.7\ninvalid", "invalid_pdf"),
    ]:
        result = NutritionImportV3.model_validate(parse(source))
        assert result.rows == []
        assert result.diagnostics[0].code == code


def test_unrecognized_wrapped_row_cannot_be_silently_imported():
    result = NutritionImportV3.model_validate(parse(synthetic_pdf(wrapped=True)))
    assert result.rows == []
    assert result.diagnostics[0].code == "pdf_row_ambiguous"


def test_explicit_hyphenated_continuation_is_kept_with_its_food():
    result = NutritionImportV3.model_validate(parse(synthetic_pdf(wrapped=True, hyphen=True)))
    assert [row.food.name for row in result.rows] == ["Synthetic food - continued"]


def test_pdf_document_can_create_a_private_draft_without_canonical_writes():
    source = synthetic_pdf()
    document = NutritionImportV3.model_validate(parse(source))
    with get_session_context() as db:
        owner = User(telegram_user_id=984_910, measurement_eligibility="test")
        other = User(telegram_user_id=984_911, measurement_eligibility="test")
        db.add_all([owner, other])
        db.flush()
        before = (db.query(Food).count(), db.query(FoodDiaryEntry).count())
        draft = create_nutrition_import_draft(
            db,
            owner,
            document=document,
            source=source,
            filename="report.pdf",
            content_type="application/pdf",
            delimiter=",",
            parser_version="fatsecret-pdf-v1",
            upload_key="synthetic-pdf-913",
            adapter_id="fatsecret-pdf-v1",
        )
        preview = nutrition_import_preview(db, owner, draft.id)
        assert preview["rows"][0]["source"]["food"]["name"] == "Synthetic food"
        with pytest.raises(NutritionDraftError, match="not_found"):
            get_nutrition_import_draft(db, other, draft.id)
        assert (db.query(Food).count(), db.query(FoodDiaryEntry).count()) == before


def test_pdf_worker_stays_closed_until_isolation_is_available():
    with pytest.raises(NutritionImportValidationError, match="adapter_execution_unavailable"):
        run_nutrition_import_adapter(
            "fatsecret-pdf-v1",
            synthetic_pdf(),
            filename="report.pdf",
            content_type="application/pdf",
        )
