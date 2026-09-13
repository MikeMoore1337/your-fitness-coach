from __future__ import annotations

import io
import warnings
from dataclasses import dataclass
from typing import Literal

from PIL import Image, ImageOps, UnidentifiedImageError

AllowedMime = Literal["image/jpeg", "image/png", "image/webp"]


class ImageIngressError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class NormalizedImage:
    data: bytes
    mime: AllowedMime
    width: int
    height: int
    pixel_count: int


def _signature_mime(data: bytes) -> AllowedMime | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def normalize_uploaded_image(
    data: bytes,
    content_type: str | None,
    *,
    max_bytes: int,
    max_pixels: int,
) -> NormalizedImage:
    if len(data) == 0:
        raise ImageIngressError("invalid_image")
    if len(data) > max_bytes:
        raise ImageIngressError("oversized_image")
    declared = content_type.strip().lower() if content_type else ""
    if declared not in {"image/jpeg", "image/png", "image/webp"}:
        raise ImageIngressError("unsupported_mime")
    actual = _signature_mime(data)
    if actual is None or actual != declared:
        raise ImageIngressError("invalid_image")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as probe:
                width, height = probe.size
                if width <= 0 or height <= 0 or width * height > max_pixels:
                    raise ImageIngressError("oversized_image")
                probe.verify()
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                oriented = ImageOps.exif_transpose(source)
                width, height = oriented.size
                if width <= 0 or height <= 0 or width * height > max_pixels:
                    raise ImageIngressError("oversized_image")
                if width < 64 or height < 64:
                    raise ImageIngressError("retake_required")
                converted = oriented.convert("RGB")
                output = io.BytesIO()
                # A new image object drops EXIF, ICC and user metadata. The
                # OCR subprocess receives only this normalized representation.
                converted.save(output, format="PNG", optimize=False)
    except ImageIngressError:
        raise
    except Image.DecompressionBombError, Image.DecompressionBombWarning:
        raise ImageIngressError("oversized_image") from None
    except UnidentifiedImageError, OSError, ValueError:
        raise ImageIngressError("decode_failed") from None
    return NormalizedImage(
        data=output.getvalue(),
        mime="image/png",
        width=width,
        height=height,
        pixel_count=width * height,
    )
