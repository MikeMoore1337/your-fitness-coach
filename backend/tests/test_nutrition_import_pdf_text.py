import zlib
from io import BytesIO

import pytest
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.pdfbase import pdfdoc
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


def test_rejects_pdf_with_embedded_file():
    output = BytesIO()
    pdf = Canvas(output)
    pdf.drawString(50, 700, "Synthetic")
    embedded = pdfdoc.PDFStream(
        pdfdoc.PDFDictionary({"Type": pdfdoc.PDFName("EmbeddedFile")}), b"synthetic attachment"
    )
    file_spec = pdfdoc.PDFDictionary(
        {
            "Type": pdfdoc.PDFName("Filespec"),
            "F": pdfdoc.PDFString("synthetic.txt"),
            "EF": pdfdoc.PDFDictionary({"F": pdf._doc.Reference(embedded)}),
        }
    )
    pdf._doc.Catalog.Names = pdfdoc.PDFDictionary(
        {
            "EmbeddedFiles": pdfdoc.PDFDictionary(
                {"Names": pdfdoc.PDFArray([pdfdoc.PDFString("synthetic.txt"), file_spec])}
            )
        }
    )
    pdf.save()
    with pytest.raises(NutritionImportValidationError, match="pdf_active_content"):
        extract_pdf_lines(output.getvalue())


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


def test_object_limit_fails_closed(monkeypatch):
    stream = BytesIO()
    pdf = Canvas(stream)
    pdf.drawString(50, 700, "Synthetic")
    pdf.save()
    monkeypatch.setattr(nutrition_import_pdf_text, "MAX_OBJECTS", 1)
    with pytest.raises(NutritionImportValidationError, match="pdf_objects_limit"):
        extract_pdf_lines(stream.getvalue())


def _truncated_pdf():
    payload = zlib.compress(b"BT /F1 12 Tf 50 700 Td (SYNTHETIC_PRIVATE_913) Tj ET")[:-4]
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length "
        + str(len(payload)).encode()
        + b" /Filter /FlateDecode >>\nstream\n"
        + payload
        + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    data = b"%PDF-1.4\n"
    offsets = []
    for number, item in enumerate(objects, 1):
        offsets.append(len(data))
        data += f"{number} 0 obj\n".encode() + item + b"\nendobj\n"
    start = len(data)
    data += b"xref\n0 6\n0000000000 65535 f \n"
    data += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    data += f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()
    return data


def test_truncated_flate_stream_fails_closed_without_source_in_error(caplog):
    data = _truncated_pdf()
    with pytest.raises(NutritionImportValidationError, match="invalid_pdf") as exc:
        extract_pdf_lines(data)
    assert "SYNTHETIC_PRIVATE_913" not in str(exc.value)
    assert "SYNTHETIC_PRIVATE_913" not in caplog.text
