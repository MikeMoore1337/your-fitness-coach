"""Extract text from the PDF subset produced by YFC's ReportLab/Chromium paths.

This intentionally stays small and dependency-free.  It understands Flate streams,
page font resources, ToUnicode CMaps, and the text operators used by the two PDF
producers under test.  It is a test/evidence helper, not a general PDF reader.
"""

from __future__ import annotations

import re
import sys
import zlib
from base64 import a85decode
from pathlib import Path
from typing import NamedTuple


class _PdfObject(NamedTuple):
    dictionary: bytes
    stream: bytes | None


class PdfTextExtractionError(ValueError):
    """Raised when a PDF stream cannot be decoded safely."""


_OBJECT_RE = re.compile(rb"(?ms)^(\d+)\s+\d+\s+obj\b(.*?)\bendobj\s*")
_REF_RE = re.compile(rb"(\d+)\s+0\s+R")
_TEXT_TOKEN_RE = re.compile(
    rb"/(F\d+(?:\+\d+)?)\s+[\d.]+\s+Tf|<([0-9A-Fa-f\s]+)>\s*Tj|"
    rb"\[(.*?)\]\s*TJ|\(((?:\\.|[^\\)])*)\)\s*Tj",
    re.DOTALL,
)


def _objects(pdf: bytes) -> dict[int, _PdfObject]:
    result: dict[int, _PdfObject] = {}
    for match in _OBJECT_RE.finditer(pdf):
        object_id = int(match.group(1))
        raw = match.group(2)
        marker = raw.find(b"stream")
        if marker < 0:
            result[object_id] = _PdfObject(raw, None)
            continue
        end = raw.rfind(b"endstream")
        if end < marker:
            result[object_id] = _PdfObject(raw, None)
            continue
        dictionary = raw[:marker]
        payload = raw[marker + len(b"stream") : end]
        payload = payload.lstrip(b" \t\r\n")
        if b"/ASCII85Decode" in dictionary:
            encoded = payload.rstrip(b" \t\r\n")
            if encoded.endswith(b"~>"):
                encoded = encoded[:-2]
            try:
                payload = a85decode(encoded, adobe=False)
            except ValueError as exc:
                raise PdfTextExtractionError(
                    f"Invalid ASCII85 stream in PDF object {object_id}"
                ) from exc
        if b"/FlateDecode" in dictionary:
            try:
                payload = zlib.decompress(payload)
            except zlib.error as exc:
                raise PdfTextExtractionError(
                    f"Invalid Flate stream in PDF object {object_id}"
                ) from exc
        result[object_id] = _PdfObject(dictionary, payload)
    return result


def _unicode_value(value: bytes) -> str:
    raw = bytes.fromhex(value.decode("ascii"))
    if not raw:
        return ""
    if len(raw) % 2 == 0:
        return "".join(
            chr(int.from_bytes(raw[offset : offset + 2], "big")) for offset in range(0, len(raw), 2)
        )
    return "".join(chr(item) for item in raw)


def _cmap(stream: bytes) -> dict[bytes, str]:
    result: dict[bytes, str] = {}
    for block in re.findall(rb"beginbfchar(.*?)endbfchar", stream, re.DOTALL):
        for source, destination in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block):
            result[bytes.fromhex(source.decode("ascii"))] = _unicode_value(destination)
    for block in re.findall(rb"beginbfrange(.*?)endbfrange", stream, re.DOTALL):
        for source_start, source_end, destination in re.findall(
            rb"<([0-9A-Fa-f]+)>\s+<([0-9A-Fa-f]+)>\s+(<[^>]+>|\[.*?\])",
            block,
            re.DOTALL,
        ):
            start = int(source_start, 16)
            end = int(source_end, 16)
            if destination.startswith(b"["):
                values = re.findall(rb"<([0-9A-Fa-f]+)>", destination)
                for offset, value in enumerate(values[: end - start + 1]):
                    result[(start + offset).to_bytes(len(source_start) // 2, "big")] = (
                        _unicode_value(value)
                    )
                continue
            first = destination[1:-1]
            decoded = _unicode_value(first)
            if len(decoded) != 1:
                continue
            code_width = len(source_start) // 2
            codepoint = ord(decoded)
            for offset, source_code in enumerate(range(start, end + 1)):
                result[source_code.to_bytes(code_width, "big")] = chr(codepoint + offset)
    return result


def _font_maps(objects: dict[int, _PdfObject], page: bytes) -> dict[str, dict[bytes, str]]:
    resource = page
    resource_ref = re.search(rb"/Resources\s+(\d+)\s+0\s+R", page)
    if resource_ref and int(resource_ref.group(1)) in objects:
        resource = objects[int(resource_ref.group(1))].dictionary

    font_text = resource
    font_ref = re.search(rb"/Font\s+(\d+)\s+0\s+R", resource)
    if font_ref and int(font_ref.group(1)) in objects:
        font_text = objects[int(font_ref.group(1))].dictionary
    else:
        font_dict = re.search(rb"/Font\s*<<(.*?)>>", resource, re.DOTALL)
        if font_dict:
            font_text = font_dict.group(1)

    result: dict[str, dict[bytes, str]] = {}
    for name, object_id in re.findall(rb"/(F\d+(?:\+\d+)?)\s+(\d+)\s+0\s+R", font_text):
        font = objects.get(int(object_id))
        if font is None:
            continue
        cmap_ref = re.search(rb"/ToUnicode\s+(\d+)\s+0\s+R", font.dictionary)
        if cmap_ref is None:
            continue
        cmap_object = objects.get(int(cmap_ref.group(1)))
        if cmap_object is not None and cmap_object.stream is not None:
            result[name.decode("ascii")] = _cmap(cmap_object.stream)
    return result


def _content_refs(page: bytes) -> list[int]:
    match = re.search(rb"/Contents\s+(\[[^]]*\]|\d+\s+0\s+R)", page, re.DOTALL)
    if match is None:
        return []
    return [int(value) for value in _REF_RE.findall(match.group(1))]


def _decode_hex(value: bytes, mapping: dict[bytes, str]) -> str:
    raw = bytes.fromhex(re.sub(rb"\s+", b"", value).decode("ascii"))
    if not mapping:
        return raw.decode("latin1", errors="replace")
    widths = sorted({len(key) for key in mapping}, reverse=True)
    result: list[str] = []
    offset = 0
    while offset < len(raw):
        for width in widths:
            key = raw[offset : offset + width]
            if key in mapping:
                result.append(mapping[key])
                offset += width
                break
        else:
            offset += 1
    return "".join(result)


def _decode_literal(value: bytes) -> bytes:
    decoded = bytearray()
    offset = 0
    escapes = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12}
    while offset < len(value):
        current = value[offset]
        if current != ord("\\") or offset + 1 >= len(value):
            decoded.append(current)
            offset += 1
            continue
        offset += 1
        current = value[offset]
        if current in b"01234567":
            end = offset + 1
            while end < len(value) and end < offset + 3 and value[end] in b"01234567":
                end += 1
            decoded.append(int(value[offset:end], 8))
            offset = end
            continue
        decoded.append(escapes.get(current, current))
        offset += 1
    return bytes(decoded)


def _content_text(stream: bytes, fonts: dict[str, dict[bytes, str]]) -> str:
    current_font = ""
    parts: list[str] = []
    for match in _TEXT_TOKEN_RE.finditer(stream):
        if match.group(1):
            current_font = match.group(1).decode("ascii")
            continue
        mapping = fonts.get(current_font, {})
        if match.group(2):
            parts.append(_decode_hex(match.group(2), mapping))
            continue
        if match.group(3):
            for value in re.findall(rb"<([0-9A-Fa-f\s]+)>|((?:\\.|[^\\)])*)", match.group(3)):
                if value[0]:
                    parts.append(_decode_hex(value[0], mapping))
                elif value[1]:
                    parts.append(_decode_hex(value[1].hex().encode("ascii"), mapping))
            continue
        parts.append(_decode_hex(_decode_literal(match.group(4)).hex().encode("ascii"), mapping))
    return " ".join(part for part in parts if part)


def extract_pdf_text(pdf: bytes | bytearray | Path | str) -> str:
    """Return the text emitted by PDF page content streams."""

    if isinstance(pdf, (Path, str)):
        data = Path(pdf).read_bytes()
    else:
        data = bytes(pdf)
    if not data.startswith(b"%PDF-"):
        raise ValueError("Not a PDF")
    objects = _objects(data)
    pages = [
        (object_id, obj.dictionary)
        for object_id, obj in objects.items()
        if b"/Type /Page" in obj.dictionary and b"/Type /Pages" not in obj.dictionary
    ]
    output: list[str] = []
    for _object_id, page in sorted(pages):
        fonts = _font_maps(objects, page)
        page_text = []
        for content_ref in _content_refs(page):
            content = objects.get(content_ref)
            if content is not None and content.stream is not None:
                page_text.append(_content_text(content.stream, fonts))
        output.append("\n".join(page_text))
    return "\n".join(output)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: extract_pdf_text.py PDF")
    sys.stdout.reconfigure(encoding="utf-8")
    print(extract_pdf_text(Path(sys.argv[1])))
