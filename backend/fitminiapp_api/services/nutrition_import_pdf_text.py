"""Bounded, local extraction of positioned PDF text for nutrition imports."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LAParams, LTContainer, LTTextLine
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser
from pdfminer.pdftypes import PDFObjRef, PDFStream

from fitminiapp_api.services.nutrition_import_validation import NutritionImportValidationError

MAX_PAGES = 100
MAX_OBJECTS = 10_000
MAX_TEXT = 1_000_000
_FORBIDDEN_KEYS = frozenset(
    {
        "AA",
        "OpenAction",
        "JS",
        "JavaScript",
        "Launch",
        "EmbeddedFiles",
        "EmbeddedFile",
        "EF",
        "AF",
        "RichMedia",
        "URI",
        "A",
    }
)


@dataclass(frozen=True)
class PdfLine:
    page: int
    bbox: tuple[float, float, float, float]
    text: str


def _check_object(value: object) -> None:
    pending = [value]
    visited = 0
    while pending:
        current = pending.pop()
        visited += 1
        if visited > MAX_OBJECTS:
            raise NutritionImportValidationError("pdf_objects_limit")
        if isinstance(current, PDFObjRef):
            continue
        if isinstance(current, PDFStream):
            current = current.attrs
        if isinstance(current, dict):
            if _FORBIDDEN_KEYS.intersection(current):
                raise NutritionImportValidationError("pdf_active_content")
            pending.extend(current.values())
        elif isinstance(current, (list, tuple)):
            pending.extend(current)


def extract_pdf_lines(source: bytes) -> list[PdfLine]:
    """Extract text with page coordinates; callers must enforce upload and OS limits."""
    try:
        document = PDFDocument(PDFParser(BytesIO(source)), fallback=False)
        if document.encryption is not None or not document.is_extractable:
            raise NutritionImportValidationError("pdf_encrypted")
        ids: set[int] = set()
        for xref in document.xrefs:
            for objid in xref.get_objids():
                ids.add(objid)
                if len(ids) > MAX_OBJECTS:
                    raise NutritionImportValidationError("pdf_objects_limit")
        for objid in ids:
            _check_object(document.getobj(objid))
        resource_manager = PDFResourceManager()
        device = PDFPageAggregator(resource_manager, laparams=LAParams())
        interpreter = PDFPageInterpreter(resource_manager, device)
        lines: list[PdfLine] = []
        text_size = 0
        for page_number, page in enumerate(PDFPage.create_pages(document), 1):
            if page_number > MAX_PAGES:
                raise NutritionImportValidationError("pdf_pages_limit")
            interpreter.process_page(page)
            pending: list[object] = [device.get_result()]
            while pending:
                item = pending.pop()
                if isinstance(item, LTTextLine):
                    text = item.get_text().strip()
                    text_size += len(text)
                    if text_size > MAX_TEXT:
                        raise NutritionImportValidationError("pdf_text_limit")
                    if text:
                        lines.append(
                            PdfLine(page_number, (item.x0, item.y0, item.x1, item.y1), text)
                        )
                elif isinstance(item, LTContainer):
                    pending.extend(reversed(list(item)))
        if not lines:
            raise NutritionImportValidationError("pdf_no_text")
        return lines
    except NutritionImportValidationError:
        raise
    except Exception:
        raise NutritionImportValidationError("invalid_pdf") from None
