from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


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
class TesseractOcr:
    languages: str
    timeout_seconds: float
    max_output_chars: int
    executable: str | None = None
    name: str = "local_tesseract"
    version: str = "tesseract-text-v1"

    def extract_text(self, normalized_png: bytes) -> str:
        executable = self.executable or shutil.which("tesseract")
        if not executable:
            raise LocalOcrError("local_ocr_unavailable")
        try:
            with tempfile.TemporaryDirectory(prefix="yfc-label-") as directory:
                image_path = Path(directory) / "normalized.png"
                image_path.write_bytes(normalized_png)
                completed = subprocess.run(
                    [
                        executable,
                        str(image_path),
                        "stdout",
                        "--oem",
                        "1",
                        "--psm",
                        "6",
                        "-l",
                        self.languages,
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    timeout=self.timeout_seconds,
                    check=False,
                    shell=False,
                )
        except subprocess.TimeoutExpired as exc:
            raise LocalOcrError("local_ocr_timeout") from exc
        except (OSError, ValueError) as exc:
            raise LocalOcrError("local_ocr_unavailable") from exc
        if completed.returncode != 0:
            raise LocalOcrError("local_ocr_failed")
        try:
            text = completed.stdout.decode("utf-8", errors="replace")
        except (AttributeError, UnicodeError) as exc:
            raise LocalOcrError("local_ocr_failed") from exc
        if len(text) > self.max_output_chars:
            raise LocalOcrError("local_ocr_output_too_large")
        return text
