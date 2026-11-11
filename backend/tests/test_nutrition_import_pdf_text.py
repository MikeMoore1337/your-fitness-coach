from io import BytesIO

import pytest
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.pdfgen.canvas import Canvas

from fitminiapp_api.services import nutrition_import_pdf_text
from fitminiapp_api.services.nutrition_import_pdf_text import extract_pdf_lines
from fitminiapp_api.services.nutrition_import_validation import NutritionImportValidationError


def test_extracts_positioned_text_on_each_page():
    stream = BytesIO()
    pdf = Canvas(stream, pageCompression=0)
    pdf.drawString(50, 700, "Breakfast")
    pdf.showPage()
    pdf.drawString(75, 600, "Synthetic food 100 g")
    pdf.save()

    lines = extract_pdf_lines(stream.getvalue())
    assert [(line.page, line.text) for line in lines] == [
        (1, "Breakfast"),
        (2, "Synthetic food 100 g"),
    ]
    assert lines[0].bbox[0] == pytest.approx(50)
    assert lines[1].bbox[0] == pytest.approx(75)


def test_rejects_corrupt_and_textless_pdf():
    with pytest.raises(NutritionImportValidationError, match="invalid_pdf"):
        extract_pdf_lines(b"%PDF-1.7\ninvalid")
    stream = BytesIO()
    pdf = Canvas(stream)
    pdf.rect(50, 50, 50, 50, fill=1)
    pdf.save()
    with pytest.raises(NutritionImportValidationError, match="pdf_no_text"):
        extract_pdf_lines(stream.getvalue())


def test_rejects_active_content_and_encrypted_pdf():
    stream = BytesIO()
    pdf = Canvas(stream)
    pdf.drawString(50, 700, "Synthetic")
    pdf.linkURL("https://example.invalid", (50, 700, 100, 720))
    pdf.save()
    with pytest.raises(NutritionImportValidationError, match="pdf_active_content"):
        extract_pdf_lines(stream.getvalue())

    stream = BytesIO()
    pdf = Canvas(stream, encrypt=StandardEncryption("secret"))
    pdf.drawString(50, 700, "Synthetic")
    pdf.save()
    with pytest.raises(NutritionImportValidationError, match=r"invalid_pdf|pdf_encrypted"):
        extract_pdf_lines(stream.getvalue())


def test_page_and_text_limits_fail_closed(monkeypatch):
    stream = BytesIO()
    pdf = Canvas(stream)
    pdf.drawString(50, 700, "Synthetic food")
    pdf.showPage()
    pdf.drawString(50, 700, "Second page")
    pdf.save()
    source = stream.getvalue()

    monkeypatch.setattr(nutrition_import_pdf_text, "MAX_PAGES", 1)
    with pytest.raises(NutritionImportValidationError, match="pdf_pages_limit"):
        extract_pdf_lines(source)
    monkeypatch.setattr(nutrition_import_pdf_text, "MAX_PAGES", 100)
    monkeypatch.setattr(nutrition_import_pdf_text, "MAX_TEXT", 5)
    with pytest.raises(NutritionImportValidationError, match="pdf_text_limit"):
        extract_pdf_lines(source)
