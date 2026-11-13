import csv
import io
import os
import platform
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from threading import Barrier

import pytest
from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from fitminiapp_api.db.session import engine, get_session_context
from fitminiapp_api.models.food import Food
from fitminiapp_api.models.food_diary import FoodDiaryEntry
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.nutrition_import import NutritionImportV3
from fitminiapp_api.services import nutrition_import_fatsecret_pdf
from fitminiapp_api.services.nutrition_import_drafts import (
    NutritionDraftError,
    confirm_nutrition_import_draft,
    create_nutrition_import_draft,
    get_nutrition_import_draft,
    nutrition_import_preview,
    set_resolutions,
)
from fitminiapp_api.services.nutrition_import_fatsecret_csv import DETAIL_HEADERS, SUMMARY_HEADERS
from fitminiapp_api.services.nutrition_import_fatsecret_csv import parse as parse_csv
from fitminiapp_api.services.nutrition_import_fatsecret_pdf import parse
from fitminiapp_api.services.nutrition_import_pdf_text import PdfLine
from fitminiapp_api.services.nutrition_import_runner import run_nutrition_import_adapter
from fitminiapp_api.services.nutrition_import_validation import NutritionImportValidationError


def synthetic_pdf(
    *,
    russian=False,
    second_page=False,
    mismatch=False,
    amount=None,
    wrapped=False,
    hyphen=False,
    reordered=False,
    day_mismatch=False,
    repeat_header=True,
    large=False,
):
    stream = BytesIO()
    pdf = Canvas(stream, pagesize=(1800, 800), pageCompression=0)
    font = Path(__file__).parents[1] / "fitminiapp_api/assets/fonts/Inter-Regular.ttf"
    pdfmetrics.registerFont(TTFont("SyntheticInter", str(font)))
    pdf.setFont("SyntheticInter", 10)
    if large:
        pixels = random.Random(913).randbytes(620 * 620 * 3)
        pdf.drawImage(
            ImageReader(Image.frombytes("RGB", (620, 620), pixels)), 0, 0, width=10, height=10
        )
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
    order = [0, 6, 8, 3, 4, 5, 1, 7, 2, 9] if reordered else list(range(10))
    headers = [headers[index] for index in order]
    for i, text in enumerate(headers):
        pdf.drawString(400 + 130 * i, 740, text)
    pdf.drawString(20, 700, "Дата: 02.03.2024" if russian else "Date: 02.03.2024")
    pdf.drawString(20, 670, "Завтрак" if russian else "Breakfast")
    pdf.drawString(20, 640, amount or ("100 г" if russian else "100 g"))
    name = "Тестовый продукт" if russian else "Synthetic food"
    pdf.drawString(160, 640, name + (" -" if hyphen else ""))
    values = ["12.3", "1", "0", "2", "0", "0", "3", "4", "0", "5"]
    for i, index in enumerate(order):
        pdf.drawString(400 + 130 * i, 640, values[index])
    if wrapped:
        pdf.drawString(160, 625, "continued")
    if mismatch:
        pdf.drawString(20, 610, "Total Breakfast")
        pdf.drawString(400, 610, "99")
    if day_mismatch:
        pdf.drawString(20, 580, "Total")
        pdf.drawString(400, 580, "99")
    if second_page:
        pdf.drawString(20, 30, "Page 1")
        pdf.showPage()
        pdf.setFont("SyntheticInter", 10)
        if repeat_header:
            for i, text in enumerate(headers):
                pdf.drawString(400 + 130 * i, 740, text)
        pdf.drawString(20, 700, "100 g")
        pdf.drawString(160, 700, "Another food")
        pdf.drawString(400, 700, "10")
    pdf.save()
    return stream.getvalue()


def synthetic_ru_report(
    *,
    ambiguous=False,
    split_portion=False,
    duplicate=False,
    food_override=None,
    second_date=False,
    wrapped=False,
):
    output = BytesIO()
    pdf = Canvas(output, pagesize=(842, 595), pageCompression=0)
    font = Path(__file__).parents[1] / "fitminiapp_api/assets/fonts/Inter-Regular.ttf"
    pdfmetrics.registerFont(TTFont("SyntheticReportInter", str(font)))

    def header(page):
        pdf.setFont("SyntheticReportInter", 12)
        pdf.drawString(25, 575, "Synthetic report")
        pdf.drawString(330, 575, "Synthetic period")
        pdf.drawString(728, 575, "Synthetic account")
        pdf.setFont("SyntheticReportInter", 8)
        pdf.drawRightString(817, 18, f"Page {page}")

    def columns(labels, units, xs):
        pdf.setFont("SyntheticReportInter", 10)
        for label, unit, x in zip(labels, units, xs, strict=True):
            pdf.drawCentredString(x, 520, label)
            pdf.drawCentredString(x, 508, unit)

    header(1)
    pdf.setFont("SyntheticReportInter", 14)
    pdf.drawString(27, 544, "Period Summary")
    pdf.setFont("SyntheticReportInter", 10)
    pdf.drawString(27, 520, "Сводка")
    columns(("Кал", "Жир", "Углев", "Белк"), ("(ккал)", "(г)", "(г)", "(г)"), (211, 271, 331, 391))
    for y, label in ((490, "Завтрак"), (475, "Всего")):
        pdf.drawString(27, y, label)
        for x, value in zip((211, 271, 331, 391), ("42", "2", "4", "6"), strict=True):
            pdf.drawCentredString(x, y, value)
    pdf.showPage()
    labels = ("Кал", "Жир", "Н/жир", "Углев", "Клетч", "Сахар", "Белк", "Натри", "Холес", "Калий")
    units = ("(ккал)", "(г)", "(г)", "(г)", "(г)", "(г)", "(г)", "(мг)", "(мг)", "(мг)")
    xs = tuple(247 + 60 * i for i in range(10))
    long_name = "Синтетический продукт "
    while pdfmetrics.stringWidth(long_name + "образец ", "SyntheticReportInter", 10) < 208:
        long_name += "образец "
    long_name = long_name.strip()
    while pdfmetrics.stringWidth(long_name, "SyntheticReportInter", 10) < 210:
        long_name += "а"
    for page in (2, 3):
        header(page)
        pdf.setFont("SyntheticReportInter", 14)
        pdf.drawString(27, 544, "Суббота, марта 2, 2024")
        columns(labels, units, xs)
        if page == 2:
            pdf.drawString(25, 470, "Завтрак")
        elif split_portion:
            pdf.setFont("SyntheticReportInter", 8)
            pdf.drawString(25, 490, "100 г")
            pdf.setFont("SyntheticReportInter", 10)
        name = long_name if page == 2 or duplicate else "Синтетический продукт Б"
        if page == 3 and wrapped == "hyphen":
            name += " -"
        if page == 2 and food_override:
            name = food_override
        pdf.drawString(25, 455, name)
        for i, (x, value) in enumerate(
            zip(xs, ("21", "1", "0", "2", "0", "0", "3", "4", "0", "5"), strict=True)
        ):
            if not ambiguous or i == 0:
                pdf.drawCentredString(x, 453, value)
        if page == 3 or not split_portion:
            if page == 3 and wrapped:
                pdf.drawString(25, 443, "продолжение")
            pdf.setFont("SyntheticReportInter", 8)
            pdf.drawString(25, 431 if page == 3 and wrapped else 443, "100 г")
        if page == 3:
            pdf.setFont("SyntheticReportInter", 10)
            for y in (415, 385):
                pdf.drawString(27, y, "Всего")
                for x, value in zip(
                    xs, ("42", "2", "0", "4", "0", "0", "6", "8", "0", "10"), strict=True
                ):
                    pdf.drawCentredString(x, y, value)
            if second_date:
                pdf.setFont("SyntheticReportInter", 14)
                pdf.drawString(27, 350, "Воскресенье, марта 3, 2024")
                pdf.setFont("SyntheticReportInter", 10)
                pdf.drawString(25, 325, "Обед")
                pdf.drawString(25, 305, "Другой продукт")
                for x, value in zip(
                    xs, ("21", "1", "0", "2", "0", "0", "3", "4", "0", "5"), strict=True
                ):
                    pdf.drawCentredString(x, 303, value)
                pdf.setFont("SyntheticReportInter", 8)
                pdf.drawString(25, 293, "100 г")
        if page == 2:
            pdf.showPage()
    pdf.save()
    return output.getvalue(), long_name


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


def test_page_without_verified_header_fails_closed():
    result = NutritionImportV3.model_validate(
        parse(synthetic_pdf(second_page=True, repeat_header=False))
    )
    assert result.rows == []
    assert result.diagnostics[0].code == "unknown_detail_header"


def test_reordered_columns_follow_header_labels():
    result = NutritionImportV3.model_validate(parse(synthetic_pdf(reordered=True)))
    facts = result.original_totals[0].facts
    assert facts.protein_g.value == Decimal("3")
    assert facts.fat_g.value == Decimal("1")
    assert result.original_detail_cells[0].source_header == "Sat. Fat"
    assert result.original_detail_cells[0].source_column == 10


def test_ru_report_two_line_headers_summary_and_page_continuation():
    source, long_name = synthetic_ru_report()
    document = NutritionImportV3.model_validate(parse(source))
    assert [item.food.name for item in document.rows] == [long_name, "Синтетический продукт Б"]
    assert [item.coordinates.page for item in document.rows] == [2, 3]
    assert all(item.meal_type == "breakfast" and item.amount_unit == "g" for item in document.rows)
    assert len(document.original_summaries) == 1
    assert len([item for item in document.original_totals if item.scope == "meal"]) == 1
    assert len([item for item in document.original_totals if item.scope == "day"]) == 1
    assert not any(item.code.endswith("_differ") for item in document.diagnostics)


def test_ru_report_accepts_new_date_without_repeated_header_on_same_page():
    source, _ = synthetic_ru_report(second_date=True)
    document = NutritionImportV3.model_validate(parse(source))
    assert [(str(row.diary_date), row.meal_type) for row in document.rows] == [
        ("2024-03-02", "breakfast"),
        ("2024-03-02", "breakfast"),
        ("2024-03-03", "lunch"),
    ]


def test_ru_report_preserves_hyphenated_food_continuation():
    source, _ = synthetic_ru_report(wrapped="hyphen")
    document = NutritionImportV3.model_validate(parse(source))
    assert document.rows[1].food.name == "Синтетический продукт Б - продолжение"
    assert document.rows[1].amount_unit == "g"


def test_ru_report_rejects_unverified_food_continuation():
    source, _ = synthetic_ru_report(wrapped="plain")
    document = NutritionImportV3.model_validate(parse(source))
    assert document.rows == []
    assert document.diagnostics[0].code == "pdf_row_ambiguous"


def test_repeated_numeric_content_at_page_top_is_not_discarded(monkeypatch):
    source, _ = synthetic_ru_report()
    lines = nutrition_import_fatsecret_pdf.extract_pdf_lines(source)
    lines.extend(
        PdfLine(page, (25, 583, 85, 590), "Product 99", page_height=595) for page in (2, 3)
    )
    monkeypatch.setattr(nutrition_import_fatsecret_pdf, "extract_pdf_lines", lambda _: lines)
    document = NutritionImportV3.model_validate(parse(source))
    assert document.rows == []
    assert document.diagnostics


def test_ru_report_does_not_guess_ambiguous_merged_column():
    source, _ = synthetic_ru_report(ambiguous=True)
    document = NutritionImportV3.model_validate(parse(source))
    assert document.rows == []
    assert document.diagnostics[0].code == "pdf_column_ambiguous"
    assert document.diagnostics[0].coordinates.page == 2
    assert document.diagnostics[0].coordinates.row > 0


def test_ru_report_preserves_duplicate_and_portion_split_between_pages():
    source, long_name = synthetic_ru_report(split_portion=True, duplicate=True)
    document = NutritionImportV3.model_validate(parse(source))
    assert [row.food.name for row in document.rows] == [long_name, long_name]
    assert document.rows[0].coordinates.page == 2
    assert document.rows[0].quantity_coordinates[0].page == 3
    assert any(item.code == "possible_duplicate" for item in document.rows[1].diagnostics)


def test_ru_report_does_not_treat_food_named_like_total_as_total():
    source, _ = synthetic_ru_report(food_override="Всего")
    document = NutritionImportV3.model_validate(parse(source))
    assert document.rows == []
    assert document.diagnostics[0].code == "pdf_total_ambiguous"


def test_overlapping_column_candidates_fail_closed(monkeypatch):
    def line(text, x, y):
        return PdfLine(1, (x, y - 8, x + 8, y), text)

    lines = [line("Report Details", 20, 770)]
    lines.extend(
        line(label, 400 + i * 30, 740)
        for i, label in enumerate(nutrition_import_fatsecret_pdf._EN_HEADERS)
    )
    lines.extend(
        [
            line("Date: 02.03.2024", 20, 700),
            line("Breakfast", 20, 670),
            line("100 g", 20, 640),
            line("Synthetic food", 160, 640),
            line("12.3", 415, 640),
        ]
    )
    monkeypatch.setattr(nutrition_import_fatsecret_pdf, "extract_pdf_lines", lambda _: lines)
    result = NutritionImportV3.model_validate(parse(b"synthetic"))
    assert result.rows == []
    assert result.diagnostics[0].code == "pdf_column_ambiguous"


def test_mismatched_meal_total_is_reported_before_confirm():
    result = NutritionImportV3.model_validate(parse(synthetic_pdf(mismatch=True)))
    assert len(result.rows) == 1
    assert any(
        item.code == "meal_source_values_differ" and item.field == "energy_kcal"
        for item in result.diagnostics
    )


def test_daily_total_is_compared_even_with_one_meal():
    result = NutritionImportV3.model_validate(parse(synthetic_pdf(day_mismatch=True)))
    assert len(result.rows) == 1
    assert any(
        item.code == "day_source_values_differ" and item.field == "energy_kcal"
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


def test_invalid_pdf_diagnostic_does_not_expose_source(caplog):
    marker = "SYNTHETIC_PRIVATE_MARKER_913"
    result = parse(b"%PDF-1.7\n" + marker.encode())
    assert marker not in repr(result)
    assert marker not in caplog.text


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


@pytest.mark.skipif(
    sys.platform == "linux"
    and platform.machine() == "x86_64"
    and hasattr(os, "memfd_create")
    and getattr(os, "geteuid", lambda: 0)() != 0,
    reason="tests unsupported worker environments",
)
def test_pdf_worker_is_unavailable_on_unsupported_platform():
    with pytest.raises(NutritionImportValidationError, match="adapter_execution_unavailable"):
        run_nutrition_import_adapter(
            "fatsecret-pdf-v1",
            synthetic_pdf(),
            filename="report.pdf",
            content_type="application/pdf",
        )


@pytest.mark.skipif(
    sys.platform != "linux" or getattr(os, "geteuid", lambda: 0)() == 0,
    reason="requires a non-root Linux parser worker",
)
def test_real_pdf_upload_review_and_catalog_confirm(client):
    if engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL transaction locks")
    from test_training_analytics import _auth

    owner = _auth(client, 984_940)
    other = _auth(client, 984_941)
    root = "/api/v1/nutrition/imports"
    upload = client.post(
        root,
        headers={**owner, "Idempotency-Key": "pdf-full-885"},
        data={"adapter_id": "fatsecret-pdf-v1"},
        files={"file": ("synthetic.pdf", synthetic_pdf(), "application/pdf")},
    )
    assert upload.status_code == 201, upload.text
    draft = upload.json()
    index = draft["rows"][0]["index"]
    correction = {
        "index": index,
        "name": "Синтетический продукт PDF 885",
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
        "confirm_key": "pdf-full-confirm-885",
        "row_indexes": [index],
        "confirmed": True,
    }
    result = client.post(f"{endpoint}/confirm", headers=owner, json=confirm)
    assert result.status_code == 200, result.text
    assert result.json()["rows"][0]["outcome"] == "publish"
    assert client.post(f"{endpoint}/confirm", headers=owner, json=confirm).json() == result.json()
    food_id = result.json()["rows"][0]["food_id"]
    assert client.get(f"/api/v1/nutrition/foods/{food_id}", headers=other).status_code == 200


@pytest.mark.skipif(
    sys.platform != "linux"
    or platform.machine() != "x86_64"
    or getattr(os, "geteuid", lambda: 0)() == 0,
    reason="requires non-root x86_64 Linux worker",
)
def test_real_pdf_upload_is_private_and_creates_no_canonical_rows(client):
    if engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL transaction locks")
    from test_nutrition_import_pdf_text import _truncated_pdf
    from test_training_analytics import _auth

    owner = _auth(client, 984_912)
    other = _auth(client, 984_913)
    source = synthetic_pdf()
    with get_session_context() as db:
        before = (db.query(Food).count(), db.query(FoodDiaryEntry).count())

    def upload():
        return client.post(
            "/api/v1/nutrition/imports",
            headers={**owner, "Idempotency-Key": "synthetic-pdf-api-913"},
            data={"adapter_id": "fatsecret-pdf-v1"},
            files={"file": ("synthetic.pdf", source, "application/pdf")},
        )

    response = upload()
    assert response.status_code == 201, response.text
    preview = response.json()
    assert preview["rows"][0]["source"]["food"]["name"] == "Synthetic food"
    assert preview["rows"][0]["source"]["coordinates"]["page"] == 1
    assert upload().json()["id"] == preview["id"]
    assert (
        client.get(f"/api/v1/nutrition/imports/{preview['id']}", headers=other).status_code == 404
    )
    large_source = synthetic_pdf(large=True)
    assert 1024 * 1024 < len(large_source) < 2 * 1024 * 1024
    large = client.post(
        "/api/v1/nutrition/imports",
        headers={**owner, "Idempotency-Key": "synthetic-pdf-large-913"},
        data={"adapter_id": "fatsecret-pdf-v1"},
        files={"file": ("synthetic.pdf", large_source, "application/pdf")},
    )
    assert large.status_code == 201, large.text
    assert len(large.json()["rows"]) == 1
    blank = BytesIO()
    image_only = Canvas(blank)
    image_only.rect(20, 20, 50, 50, fill=1)
    image_only.save()
    rejected = client.post(
        "/api/v1/nutrition/imports",
        headers={**owner, "Idempotency-Key": "synthetic-pdf-no-text-913"},
        data={"adapter_id": "fatsecret-pdf-v1"},
        files={"file": ("synthetic.pdf", blank.getvalue(), "application/pdf")},
    )
    assert rejected.status_code == 400
    assert rejected.json()["detail"] == {
        "code": "pdf_no_text",
        "message": "В PDF не найден текст. Загрузите файл CSV",
    }
    corrupt = client.post(
        "/api/v1/nutrition/imports",
        headers={**owner, "Idempotency-Key": "synthetic-pdf-corrupt-913"},
        data={"adapter_id": "fatsecret-pdf-v1"},
        files={"file": ("synthetic.pdf", _truncated_pdf(), "application/pdf")},
    )
    assert corrupt.status_code == 400
    assert corrupt.json()["detail"]["code"] == "invalid_pdf"
    assert "SYNTHETIC_PRIVATE_913" not in corrupt.text
    with get_session_context() as db:
        assert (db.query(Food).count(), db.query(FoodDiaryEntry).count()) == before


@pytest.mark.skipif(
    sys.platform != "linux"
    or platform.machine() != "x86_64"
    or getattr(os, "geteuid", lambda: 0)() == 0,
    reason="requires non-root x86_64 Linux worker",
)
def test_concurrent_pdf_confirm_is_idempotent_in_postgresql(client):
    if engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL transaction locks")
    from test_food_diary import _active_food
    from test_training_analytics import _auth, _user_id

    headers = _auth(client, 984_914)
    owner_id = _user_id(984_914)
    response = client.post(
        "/api/v1/nutrition/imports",
        headers={**headers, "Idempotency-Key": "synthetic-pdf-concurrent-913"},
        data={"adapter_id": "fatsecret-pdf-v1"},
        files={"file": ("synthetic.pdf", synthetic_pdf(), "application/pdf")},
    )
    assert response.status_code == 201, response.text
    draft_id = response.json()["id"]
    with get_session_context() as db:
        owner = db.get(User, owner_id)
        food = _active_food(protein_g_per_100g=None)
        db.add(food)
        db.flush()
        set_resolutions(db, owner, draft_id, revision=1, matches={0: food.id}, skipped_rows=[])
        preview = nutrition_import_preview(db, owner, draft_id)
        db.commit()
    barrier = Barrier(2)

    def confirm():
        with get_session_context() as db:
            owner = db.get(User, owner_id)
            barrier.wait(timeout=10)
            receipt = confirm_nutrition_import_draft(
                db,
                owner,
                draft_id,
                revision=preview["revision"],
                preview_signature=preview["preview_signature"],
                confirm_key="synthetic-pdf-confirm-913",
                confirmed=True,
            )
            db.commit()
            return receipt

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: confirm(), range(2)))
    assert results[0] == results[1]
    with get_session_context() as db:
        assert db.query(FoodDiaryEntry).filter_by(user_id=owner_id).count() == 1
