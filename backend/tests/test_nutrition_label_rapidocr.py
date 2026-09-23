from __future__ import annotations

import sys
from concurrent.futures import Future
from decimal import Decimal
from threading import BoundedSemaphore
from types import ModuleType, SimpleNamespace

import pytest

from fitminiapp_api.nutrition_label.ocr import (
    RAPIDOCR_MODEL_FILES,
    LocalOcrError,
    OcrToken,
    RapidOcr,
    structured_text_from_tokens,
)
from fitminiapp_api.nutrition_label.parser import build_draft_from_ocr


def _adapter_without_runtime() -> RapidOcr:
    adapter = object.__new__(RapidOcr)
    adapter._inference_slots = BoundedSemaphore(1)
    adapter._timeout_seconds = 0.001
    adapter._max_output_chars = 50_000
    return adapter


def test_rapidocr_maps_positioned_lines_to_bounded_tokens() -> None:
    adapter = object.__new__(RapidOcr)
    result = SimpleNamespace(
        boxes=[[[12, 30], [112, 30], [112, 58], [12, 58]]],
        txts=["Белки 8,0 г"],
        scores=[0.98],
    )

    tokens = adapter._tokens_from_result(result)

    assert tokens[0].text == "Белки 8,0 г"
    assert (tokens[0].left, tokens[0].top, tokens[0].width, tokens[0].height) == (12, 30, 100, 28)
    assert tokens[0].confidence == pytest.approx(98.0)
    assert structured_text_from_tokens(tokens) == "Белки 8,0 г"


def test_rapidocr_positioned_evidence_uses_existing_parser_safety() -> None:
    tokens = (
        OcrToken("Пищевая ценность 100 г продукта", 0, 0, 300, 30, 99, 1, 1, 1, 1),
        OcrToken("Energy 66,8 kcal / 281,4 kJ", 0, 40, 300, 30, 99, 1, 1, 2, 1),
        OcrToken("Protein 8,0 g", 0, 80, 200, 30, 99, 1, 1, 3, 1),
        OcrToken("Fat 2,0 g", 0, 120, 200, 30, 99, 1, 1, 4, 1),
        OcrToken("Carbohydrate 4,2 g", 0, 160, 250, 30, 99, 1, 1, 5, 1),
    )

    draft = build_draft_from_ocr(
        structured_text_from_tokens(tokens),
        structured_tokens=tokens,
        provider="local_rapidocr",
        model=RapidOcr.version,
    )

    assert draft.source_basis == "per_100_g"
    assert draft.normalized_facts.energy_kcal is not None
    assert draft.normalized_facts.energy_kcal.value == Decimal("66.8")
    assert draft.normalized_facts.energy_kj is not None
    assert draft.normalized_facts.energy_kj.value == Decimal("281.4")
    assert draft.normalized_facts.protein_g is not None
    assert draft.normalized_facts.fat_g is not None
    assert draft.normalized_facts.carbohydrate_g is not None

    unsafe = build_draft_from_ocr(
        "Пищевая ценность 100 г продукта\nEnergy 2814\nProtein 8 g\nFat 2 g\nCarbohydrate 4 g",
        provider="local_rapidocr",
        model=RapidOcr.version,
    )
    assert unsafe.normalized_facts.energy_kcal is None
    assert unsafe.normalized_facts.energy_kj is None
    assert "energy_unit_ambiguous" in unsafe.warnings


def test_rapidocr_requires_preinstalled_models(tmp_path) -> None:
    with pytest.raises(LocalOcrError, match="local_ocr_model_missing"):
        RapidOcr(model_dir=tmp_path, timeout_seconds=8, max_output_chars=50_000)

    assert RAPIDOCR_MODEL_FILES == (
        "ch_PP-OCRv5_det_mobile.onnx",
        "cyrillic_PP-OCRv5_rec_mobile.onnx",
        "ch_PP-LCNet_x0_25_textline_ori_cls_mobile.onnx",
    )


def test_rapidocr_passes_explicit_model_paths_and_bounded_runtime_params(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for file_name in RAPIDOCR_MODEL_FILES:
        (tmp_path / file_name).write_bytes(b"model")
    captured: dict[str, object] = {}

    class _FakeRapidOCR:
        def __init__(self, *, params: dict[str, object]) -> None:
            captured.update(params)

    fake_module = ModuleType("rapidocr")
    fake_module.EngineType = SimpleNamespace(ONNXRUNTIME="onnxruntime")
    fake_module.LangDet = SimpleNamespace(CH="ch")
    fake_module.LangRec = SimpleNamespace(CYRILLIC="cyrillic")
    fake_module.ModelType = SimpleNamespace(MOBILE="mobile")
    fake_module.OCRVersion = SimpleNamespace(PPOCRV5="PP-OCRv5")
    fake_module.RapidOCR = _FakeRapidOCR
    monkeypatch.setitem(sys.modules, "rapidocr", fake_module)

    engine = RapidOcr(model_dir=tmp_path, timeout_seconds=8, max_output_chars=50_000)
    engine._executor.shutdown(wait=True)

    assert captured["Global.max_side_len"] == 1800
    assert captured["EngineConfig.onnxruntime.intra_op_num_threads"] == 2
    assert captured["EngineConfig.onnxruntime.inter_op_num_threads"] == 1
    assert captured["EngineConfig.onnxruntime.enable_cpu_mem_arena"] is False
    assert captured["Det.limit_side_len"] == 1800
    assert captured["Det.model_path"] == str(tmp_path / RAPIDOCR_MODEL_FILES[0])
    assert captured["Cls.model_path"] == str(tmp_path / RAPIDOCR_MODEL_FILES[2])
    assert captured["Rec.model_path"] == str(tmp_path / RAPIDOCR_MODEL_FILES[1])


def test_rapidocr_rejects_mismatched_positioned_result_lengths() -> None:
    adapter = object.__new__(RapidOcr)

    with pytest.raises(LocalOcrError, match="local_ocr_failed"):
        adapter._tokens_from_result(
            SimpleNamespace(
                boxes=[[[0, 0], [10, 0], [10, 10], [0, 10]]],
                txts=[],
                scores=[0.9],
            )
        )


def test_rapidocr_timeout_is_controlled_without_unbounded_concurrency() -> None:
    adapter = _adapter_without_runtime()

    class _PendingExecutor:
        def submit(self, fn):
            del fn
            return Future()

    adapter._executor = _PendingExecutor()

    with pytest.raises(LocalOcrError, match="local_ocr_timeout"):
        adapter.extract_candidates(b"normalized-png")


def test_rapidocr_executor_failure_is_controlled_and_releases_slot() -> None:
    adapter = _adapter_without_runtime()

    class _BrokenExecutor:
        def submit(self, fn):
            del fn
            raise RuntimeError("executor stopped")

    adapter._executor = _BrokenExecutor()

    with pytest.raises(LocalOcrError, match="local_ocr_unavailable"):
        adapter.extract_candidates(b"normalized-png")
    assert adapter._inference_slots.acquire(timeout=0) is True
    adapter._inference_slots.release()
