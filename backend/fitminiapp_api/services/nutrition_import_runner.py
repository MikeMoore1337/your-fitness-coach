"""Run registered import adapters in a bounded subprocess on Linux."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fitminiapp_api.schemas.nutrition_import import NutritionImportV1, NutritionImportV2
from fitminiapp_api.services.nutrition_import_validation import (
    MAX_ADAPTER_BYTES,
    NutritionImportValidationError,
    validate_adapter_result,
    validate_csv_upload,
)

MAX_ADAPTER_SECONDS = 5


@dataclass(frozen=True)
class NutritionImportAdapter:
    provider: str
    adapter_version: str
    parser_version: str
    delimiter: Literal[",", ";", "\t"]
    module_path: Path
    # Grant these policies only to reviewed classifiers and verified product identities, not CSV claims.
    catalog_source: str | None = None
    catalog_publication_rights: frozenset[str] = frozenset()
    catalog_food_kinds: frozenset[str] = frozenset()
    catalog_source_versions: frozenset[str | None] = frozenset()
    catalog_identity_sources: frozenset[str] = frozenset()
    catalog_attribution: str | None = None


ADAPTERS: dict[str, NutritionImportAdapter] = {}


def run_nutrition_import_adapter(
    adapter_id: str, source: bytes, *, filename: str | None, content_type: str | None
) -> NutritionImportV1 | NutritionImportV2:
    adapter = ADAPTERS.get(adapter_id)
    if adapter is None:
        raise NutritionImportValidationError("adapter_unavailable")
    validate_csv_upload(
        source, filename=filename, content_type=content_type, delimiter=adapter.delimiter
    )
    if sys.platform != "linux" or not hasattr(os, "memfd_create") or os.geteuid() == 0:
        raise NutritionImportValidationError("adapter_execution_unavailable")
    try:
        descriptor = os.memfd_create("nutrition-import", flags=0)
    except OSError:
        raise NutritionImportValidationError("adapter_execution_unavailable") from None
    process = None
    try:
        worker = Path(__file__).with_name("nutrition_import_adapter_worker.py")
        process = subprocess.Popen(
            [sys.executable, "-I", str(worker), str(adapter.module_path)],
            stdin=subprocess.PIPE,
            stdout=descriptor,
            stderr=subprocess.DEVNULL,
            env={},
            start_new_session=True,
        )
        try:
            process.communicate(input=source, timeout=MAX_ADAPTER_SECONDS)
        except subprocess.TimeoutExpired:
            raise NutritionImportValidationError("adapter_timeout") from None
        if process.returncode != 0:
            raise NutritionImportValidationError("adapter_failed")
        os.lseek(descriptor, 0, os.SEEK_SET)
        output = os.read(descriptor, MAX_ADAPTER_BYTES + 1)
        return validate_adapter_result(
            output,
            provider=adapter.provider,
            adapter_version=adapter.adapter_version,
            source_format="csv",
        )
    except OSError:
        raise NutritionImportValidationError("adapter_execution_unavailable") from None
    finally:
        if process is not None:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        os.close(descriptor)
