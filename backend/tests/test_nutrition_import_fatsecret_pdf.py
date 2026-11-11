import csv
import io
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import pytest
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from fitminiapp_api.schemas.nutrition_import import NutritionImportV3
from fitminiapp_api.services.nutrition_import_fatsecret_csv import DETAIL_HEADERS, SUMMARY_HEADERS
from fitminiapp_api.services.nutrition_import_fatsecret_csv import parse as parse_csv
from fitminiapp_api.services.nutrition_import_fatsecret_pdf import parse


def synthetic_pdf(*, russian=False, second_page=False):
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
    pdf.drawString(20, 640, "100 г" if russian else "100 g")
    pdf.drawString(160, 640, "Тестовый продукт" if russian else "Synthetic food")
    for i, text in enumerate(["12.3", "1", "0", "2", "0", "0", "3", "4", "0", "5"]):
        pdf.drawString(400 + 130 * i, 640, text)
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
