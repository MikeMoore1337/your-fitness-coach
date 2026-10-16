from __future__ import annotations

import zlib
from base64 import a85encode

import pytest
from scripts.extract_pdf_text import PdfTextExtractionError, extract_pdf_text


def _ascii85_pdf(encoded_stream: bytes) -> bytes:
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n"
        b"<< /Length "
        + str(len(encoded_stream)).encode("ascii")
        + b" /Filter [/ASCII85Decode /FlateDecode] >>\n"
        b"stream\n" + encoded_stream + b"endstream\n"
        b"endobj\n"
        b"2 0 obj\n"
        b"<< /Type /Page /Contents 1 0 R >>\n"
        b"endobj\n"
        b"trailer\n<<>>\n%%EOF\n"
    )


def _encoded_content() -> bytes:
    content = b"BT /F1 12 Tf (hello) Tj ET"
    for padding in range(1000):
        encoded = a85encode(zlib.compress(content + b" " * padding), adobe=False)
        if encoded.endswith(b">"):
            return encoded + b"~>"
    raise AssertionError("test fixture did not find an ASCII85 payload ending in '>'")


def test_extract_pdf_text_preserves_ascii85_data_before_eod_marker() -> None:
    assert extract_pdf_text(_ascii85_pdf(_encoded_content())) == "hello"


def test_extract_pdf_text_rejects_truncated_flate_stream() -> None:
    encoded = _encoded_content()
    truncated = encoded[:-3] + encoded[-2:]

    with pytest.raises(PdfTextExtractionError, match="Invalid Flate stream in PDF object 1"):
        extract_pdf_text(_ascii85_pdf(truncated))
