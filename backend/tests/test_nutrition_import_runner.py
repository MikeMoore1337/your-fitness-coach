import os
import sys
from pathlib import Path

import pytest

from fitminiapp_api.services.nutrition_import_runner import (
    ADAPTERS,
    NutritionImportAdapter,
    run_nutrition_import_adapter,
)
from fitminiapp_api.services.nutrition_import_validation import NutritionImportValidationError

SYNTHETIC = Path(__file__).parent / "fixtures" / "nutrition_import" / "synthetic_adapter.py"


def _run(content: bytes):
    return run_nutrition_import_adapter(
        "synthetic", content, filename="synthetic.csv", content_type="text/csv"
    )


def test_unknown_adapter_is_rejected_without_reading_content():
    with pytest.raises(NutritionImportValidationError, match="adapter_unavailable"):
        _run(b"private diet")


@pytest.mark.skipif(
    sys.platform != "linux"
    or not hasattr(os, "memfd_create")
    or getattr(os, "geteuid", lambda: 0)() == 0,
    reason="requires a non-root Linux process with memfd",
)
def test_synthetic_adapter_and_resource_limits(monkeypatch):
    monkeypatch.setitem(
        ADAPTERS,
        "synthetic",
        NutritionImportAdapter("fixture_provider", "synthetic-v2", "synthetic-v2", ",", SYNTHETIC),
    )
    result = _run(b"name,quantity\nSynthetic,1\n")
    assert result.schema_version == "nutrition-import-v2"
    assert str(result.rows[0].quantity) == "1.000"
    assert result.rows[0].nutrition.facts.energy_kcal is None
    for source in (
        b"__BUSY__\n",
        b"__TOO_LARGE__\n",
        b"__MEMORY__\n",
        b"__SLEEP__\n",
        b"unrecognised\n",
    ):
        with pytest.raises(NutritionImportValidationError, match=r"adapter_(failed|timeout)"):
            _run(source)
