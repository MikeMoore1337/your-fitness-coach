from __future__ import annotations

import csv
import io
import math
import shutil
import subprocess
import tempfile
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps

OCR_PIPELINE_VERSION = "tesseract-structured-adaptive-v3"
OCR_PSM_MODES: tuple[int, ...] = (6, 4, 11)
OCR_TESSERACT_DPI = 300
OCR_MAX_VARIANTS = 5
OCR_MAX_TOKENS = 4096
OCR_MAX_PREPROCESSED_PIXELS = 12_000_000
OCR_MAX_DIMENSION = 4096
# Production-like constrained containers can need a little over three seconds for the first
# high-resolution deskewed pass (Tesseract language/model startup plus the 2x ROI). Keep that
# cold-start allowance separate from the normal per-pass budget; the request deadline remains
# authoritative for the whole adaptive stream.
OCR_DEFAULT_PASS_TIMEOUT_SECONDS = 1.5
OCR_DEFAULT_INITIAL_PASS_TIMEOUT_SECONDS = 3.5

# 128E's production-like benchmark found the deskewed ROI to be the first variant that
# recovered all mandatory facts. Keep the fallback order explicit and bounded: each pair is
# scheduled at most once, and the service may stop consuming this stream after a strong draft.
OCR_VARIANT_PRIORITY: tuple[str, ...] = (
    "roi_deskew_minus_1_5_2x",
    "source_rgb_1x",
    "roi_gray_contrast_denoised_2x",
    "roi_inverted_2x",
    "roi_adaptive_threshold_2x",
)
OCR_PSM_PRIORITY: dict[str, tuple[int, ...]] = {
    "roi_deskew_minus_1_5_2x": (6, 4, 11),
    "source_rgb_1x": (4, 11, 6),
    "roi_gray_contrast_denoised_2x": (4, 6, 11),
    "roi_inverted_2x": (4, 6, 11),
    "roi_adaptive_threshold_2x": (4, 11, 6),
}


class LocalOcrError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class OcrEngine(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    def extract_text(self, normalized_png: bytes) -> str: ...


@dataclass(frozen=True)
class OcrToken:
    text: str
    left: int
    top: int
    width: int
    height: int
    confidence: float
    block_num: int
    paragraph_num: int
    line_num: int
    word_num: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def center_y(self) -> float:
        return self.top + self.height / 2


@dataclass(frozen=True)
class OcrCandidate:
    variant: str
    psm: int
    text: str
    tokens: tuple[OcrToken, ...]
    elapsed_ms: float


@dataclass(frozen=True)
class PreprocessedVariant:
    name: str
    image: Image.Image


def _safe_int(value: str) -> int | None:
    try:
        return int(value)
    except TypeError, ValueError:
        return None


def _safe_float(value: str) -> float | None:
    try:
        parsed = float(value)
    except TypeError, ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def parse_tesseract_tsv(data: bytes, *, max_output_chars: int = 50_000) -> tuple[OcrToken, ...]:
    """Parse bounded word-level TSV; raw TSV never leaves this process."""

    if len(data) > max_output_chars:
        raise LocalOcrError("local_ocr_output_too_large")
    try:
        text = data.decode("utf-8", errors="replace")
    except (AttributeError, UnicodeError) as exc:
        raise LocalOcrError("local_ocr_failed") from exc
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    tokens: list[OcrToken] = []
    for row in reader:
        if row.get("level") != "5":
            continue
        token_text = " ".join((row.get("text") or "").split())
        if not token_text:
            continue
        coordinates = {
            field: _safe_int(row.get(field, "")) for field in ("left", "top", "width", "height")
        }
        sequence = {
            field: _safe_int(row.get(field, ""))
            for field in ("block_num", "par_num", "line_num", "word_num")
        }
        confidence = _safe_float(row.get("conf", ""))
        if (
            any(value is None for value in coordinates.values())
            or any(value is None for value in sequence.values())
            or confidence is None
        ):
            continue
        left = coordinates["left"]
        top = coordinates["top"]
        width = coordinates["width"]
        height = coordinates["height"]
        if left is None or top is None or width is None or height is None:
            continue
        if width <= 0 or height <= 0 or left < 0 or top < 0:
            continue
        tokens.append(
            OcrToken(
                text=token_text,
                left=left,
                top=top,
                width=width,
                height=height,
                confidence=max(0.0, min(100.0, confidence)),
                block_num=sequence["block_num"] or 0,
                paragraph_num=sequence["par_num"] or 0,
                line_num=sequence["line_num"] or 0,
                word_num=sequence["word_num"] or 0,
            )
        )
        if len(tokens) > OCR_MAX_TOKENS:
            raise LocalOcrError("local_ocr_output_too_large")
    return tuple(tokens)


def _row_tolerance(row: Sequence[OcrToken], token: OcrToken) -> float:
    heights = [item.height for item in row]
    return max(12.0, min(48.0, max(max(heights, default=token.height), token.height) * 0.8))


def structured_text_from_tokens(tokens: Sequence[OcrToken]) -> str:
    """Create deterministic visual rows from word boxes for label/value association."""

    rows: list[list[OcrToken]] = []
    row_centers: list[float] = []
    for token in sorted(tokens, key=lambda item: (item.top, item.left, item.word_num)):
        matches = [
            index
            for index, row in enumerate(rows)
            if abs(row_centers[index] - token.center_y) <= _row_tolerance(row, token)
        ]
        if matches:
            index = min(matches, key=lambda candidate: abs(row_centers[candidate] - token.center_y))
            rows[index].append(token)
            row_centers[index] = sum(item.center_y for item in rows[index]) / len(rows[index])
        else:
            rows.append([token])
            row_centers.append(token.center_y)
    ordered_rows = sorted(zip(row_centers, rows, strict=True), key=lambda item: item[0])
    return "\n".join(
        " ".join(item.text for item in sorted(row, key=lambda value: (value.left, value.top)))
        for _, row in ordered_rows
    )


def _scale_image(image: Image.Image, factor: float) -> Image.Image:
    target_factor = min(
        factor,
        math.sqrt(OCR_MAX_PREPROCESSED_PIXELS / max(1, image.width * image.height)),
        OCR_MAX_DIMENSION / max(image.width, image.height),
    )
    target_factor = max(1.0 / max(image.width, image.height), target_factor)
    if target_factor >= 0.999:
        return image.copy()
    return image.resize(
        (max(1, round(image.width * target_factor)), max(1, round(image.height * target_factor))),
        resample=Image.Resampling.LANCZOS,
    )


def _safe_roi(image: Image.Image) -> Image.Image:
    """Use a conservative inner crop; never depend on an unreliable perspective guess."""

    margin_x = round(image.width * 0.045)
    margin_y = round(image.height * 0.045)
    if image.width - 2 * margin_x < 64 or image.height - 2 * margin_y < 64:
        return image.copy()
    return image.crop((margin_x, margin_y, image.width - margin_x, image.height - margin_y))


def _gray_contrast(image: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(image)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    gray = gray.filter(ImageFilter.MedianFilter(size=3))
    return ImageEnhance.Contrast(gray).enhance(1.6)


def _adaptive_threshold(gray: Image.Image) -> Image.Image:
    background = gray.filter(ImageFilter.GaussianBlur(radius=8))
    local_delta = ImageChops.subtract(gray, background, offset=128)
    return local_delta.point(lambda value: 255 if value >= 137 else 0)


def _iter_preprocessed_variants(normalized_png: bytes) -> Iterator[PreprocessedVariant]:
    try:
        with Image.open(io.BytesIO(normalized_png)) as source:
            rgb = _scale_image(source.convert("RGB"), 1.0)
            roi = _safe_roi(rgb)
            gray = _gray_contrast(roi)
            variant_builders = {
                "roi_deskew_minus_1_5_2x": lambda: _scale_image(
                    gray.rotate(
                        -1.5,
                        resample=Image.Resampling.BICUBIC,
                        expand=True,
                        fillcolor=255,
                    ),
                    2.0,
                ),
                "source_rgb_1x": lambda: rgb.copy(),
                "roi_gray_contrast_denoised_2x": lambda: _scale_image(gray, 2.0),
                "roi_inverted_2x": lambda: _scale_image(ImageOps.invert(gray), 2.0),
                "roi_adaptive_threshold_2x": lambda: _scale_image(_adaptive_threshold(gray), 2.0),
            }
            for variant_name in OCR_VARIANT_PRIORITY:
                yield PreprocessedVariant(variant_name, variant_builders[variant_name]())
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise LocalOcrError("local_ocr_failed") from exc


def preprocessing_variant_names(normalized_png: bytes) -> tuple[str, ...]:
    names: list[str] = []
    for variant in _iter_preprocessed_variants(normalized_png):
        names.append(variant.name)
        variant.image.close()
    return tuple(names)


@dataclass(frozen=True)
class TesseractOcr:
    languages: str
    timeout_seconds: float
    max_output_chars: int
    executable: str | None = None
    pass_timeout_seconds: float = OCR_DEFAULT_PASS_TIMEOUT_SECONDS
    initial_pass_timeout_seconds: float = OCR_DEFAULT_INITIAL_PASS_TIMEOUT_SECONDS
    name: str = "local_tesseract"
    version: str = OCR_PIPELINE_VERSION

    def _run_pass(self, executable: str, image_path: Path, psm: int, deadline: float) -> bytes:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise LocalOcrError("local_ocr_timeout")
        try:
            process = subprocess.Popen(
                [
                    executable,
                    str(image_path),
                    "stdout",
                    "--oem",
                    "1",
                    "--psm",
                    str(psm),
                    "--dpi",
                    str(OCR_TESSERACT_DPI),
                    "-l",
                    self.languages,
                    "tsv",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                shell=False,
            )
            stdout, _ = process.communicate(timeout=remaining)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.communicate()
            raise LocalOcrError("local_ocr_timeout") from exc
        except (OSError, ValueError) as exc:
            raise LocalOcrError("local_ocr_unavailable") from exc
        if process.returncode != 0:
            raise LocalOcrError("local_ocr_failed")
        if len(stdout) > self.max_output_chars:
            raise LocalOcrError("local_ocr_output_too_large")
        return stdout

    def _effective_pass_timeout(self, *, initial: bool = False) -> float:
        configured = self.initial_pass_timeout_seconds if initial else self.pass_timeout_seconds
        if self.timeout_seconds <= 0 or configured <= 0:
            raise LocalOcrError("local_ocr_timeout")
        return min(self.timeout_seconds, configured)

    def iter_candidates(self, normalized_png: bytes) -> Iterator[OcrCandidate]:
        """Yield bounded OCR candidates in priority order.

        The generator deliberately reports a timeout after already-yielded candidates instead
        of converting the prefix into a success itself. The service owns nutrition parsing and
        can therefore decide whether that prefix is safe enough to return as a review draft.
        ``extract_candidates`` below keeps the lower-level compatibility contract for callers
        that only need a tuple.
        """

        executable = self.executable or shutil.which("tesseract")
        if not executable:
            raise LocalOcrError("local_ocr_unavailable")
        deadline = time.monotonic() + self.timeout_seconds
        pass_index = 0
        candidate_count = 0
        try:
            with tempfile.TemporaryDirectory(prefix="yfc-label-") as directory:
                for variant in _iter_preprocessed_variants(normalized_png):
                    variant_path = Path(directory) / f"{variant.name}.png"
                    try:
                        if time.monotonic() >= deadline:
                            raise LocalOcrError("local_ocr_timeout")
                        variant.image.save(variant_path, format="PNG", optimize=False)
                        for psm in OCR_PSM_PRIORITY[variant.name]:
                            if time.monotonic() >= deadline:
                                raise LocalOcrError("local_ocr_timeout")
                            started = time.monotonic()
                            pass_timeout = self._effective_pass_timeout(initial=pass_index == 0)
                            pass_index += 1
                            pass_deadline = min(deadline, started + pass_timeout)
                            tsv = self._run_pass(executable, variant_path, psm, pass_deadline)
                            tokens = parse_tesseract_tsv(
                                tsv,
                                max_output_chars=self.max_output_chars,
                            )
                            yield OcrCandidate(
                                variant=variant.name,
                                psm=psm,
                                text=structured_text_from_tokens(tokens),
                                tokens=tokens,
                                elapsed_ms=(time.monotonic() - started) * 1000,
                            )
                            candidate_count += 1
                            if candidate_count >= OCR_MAX_VARIANTS * len(OCR_PSM_MODES):
                                return
                    finally:
                        variant.image.close()
        except (OSError, ValueError) as exc:
            raise LocalOcrError("local_ocr_failed") from exc

    def extract_candidates(self, normalized_png: bytes) -> tuple[OcrCandidate, ...]:
        candidates: list[OcrCandidate] = []
        try:
            candidates.extend(self.iter_candidates(normalized_png))
        except LocalOcrError as exc:
            if exc.code != "local_ocr_timeout" or not candidates:
                raise
        if not candidates:
            raise LocalOcrError("local_ocr_failed")
        return tuple(candidates)

    def extract_text(self, normalized_png: bytes) -> str:
        candidates = self.extract_candidates(normalized_png)
        return candidates[0].text
