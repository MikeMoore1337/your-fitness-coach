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

    assert captured["Global.max_side_len"] == 1750
    assert captured["EngineConfig.onnxruntime.intra_op_num_threads"] == 2
    assert captured["EngineConfig.onnxruntime.inter_op_num_threads"] == 1
    assert captured["EngineConfig.onnxruntime.enable_cpu_mem_arena"] is False
    assert captured["Det.limit_side_len"] == 1750
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


def test_rapidocr_cancels_pending_future_and_releases_slot_after_timeout() -> None:
    adapter = _adapter_without_runtime()

    class _PendingExecutor:
        def submit(self, fn):
            del fn
            return Future()

    adapter._executor = _PendingExecutor()

    with pytest.raises(LocalOcrError, match="local_ocr_timeout"):
        adapter.extract_candidates(b"normalized-png")
    assert adapter._inference_slots.acquire(timeout=0) is True
    adapter._inference_slots.release()


def test_rapidocr_slot_wait_timeout_is_controlled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _adapter_without_runtime()
    adapter._timeout_seconds = 1.0
    acquire_timeouts: list[float] = []

    class _UnavailableSemaphore:
        def acquire(self, *, timeout: float) -> bool:
            acquire_timeouts.append(timeout)
            return False

        def release(self) -> None:
            raise AssertionError("an unavailable semaphore cannot be released")

    class _UnusedExecutor:
        def submit(self, fn):
            del fn
            raise AssertionError("inference must not be submitted without a slot")

    adapter._inference_slots = _UnavailableSemaphore()
    adapter._executor = _UnusedExecutor()
    monkeypatch.setattr("fitminiapp_api.nutrition_label.ocr.time.monotonic", lambda: 10.0)

    with pytest.raises(LocalOcrError, match="local_ocr_timeout"):
        adapter.extract_candidates(b"normalized-png")

    assert acquire_timeouts == [pytest.approx(1.0)]


def test_rapidocr_running_timeout_keeps_slot_until_worker_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _adapter_without_runtime()
    adapter._timeout_seconds = 1.0
    active = 0
    max_active = 0
    inference_calls = 0
    captured_workers = []

    class _DeterministicSemaphore:
        available = True

        def acquire(self, *, timeout: float) -> bool:
            del timeout
            if not self.available:
                return False
            self.available = False
            return True

        def release(self) -> None:
            assert not self.available
            self.available = True

    class _TimedOutRunningFuture:
        def result(self, timeout: float | None = None):
            assert timeout == pytest.approx(1.0)
            raise TimeoutError

        def cancel(self) -> bool:
            return False

    class _CompletedFuture:
        def __init__(self, worker) -> None:
            self._worker = worker

        def result(self, timeout: float | None = None):
            assert timeout == pytest.approx(1.0)
            return self._worker()

    class _SerialExecutor:
        submissions = 0

        def submit(self, worker):
            self.submissions += 1
            if self.submissions == 1:
                captured_workers.append(worker)
                return _TimedOutRunningFuture()
            return _CompletedFuture(worker)

    def run_inference(payload: bytes):
        nonlocal active, max_active, inference_calls
        assert payload == b"normalized-png"
        active += 1
        inference_calls += 1
        max_active = max(max_active, active)
        try:
            return SimpleNamespace(
                boxes=[[[12, 30], [112, 30], [112, 58], [12, 58]]],
                txts=["Protein 8,0 g"],
                scores=[0.98],
            )
        finally:
            active -= 1

    adapter._inference_slots = _DeterministicSemaphore()
    adapter._executor = _SerialExecutor()
    adapter._run_inference = run_inference
    monkeypatch.setattr("fitminiapp_api.nutrition_label.ocr.time.monotonic", lambda: 10.0)

    with pytest.raises(LocalOcrError, match="local_ocr_timeout"):
        adapter.extract_candidates(b"normalized-png")

    assert adapter._inference_slots.available is False
    with pytest.raises(LocalOcrError, match="local_ocr_timeout"):
        adapter.extract_candidates(b"normalized-png")
    assert len(captured_workers) == 1
    assert inference_calls == 0

    captured_workers[0]()

    assert adapter._inference_slots.available is True
    candidates = adapter.extract_candidates(b"normalized-png")
    assert candidates[0].text == "Protein 8,0 g"
    assert inference_calls == 2
    assert max_active == 1


def test_rapidocr_uses_one_deadline_for_slot_wait_and_inference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _adapter_without_runtime()
    adapter._timeout_seconds = 1.0
    elapsed = 0.0
    result_timeouts: list[float | None] = []

    class _DelayedSemaphore:
        def acquire(self, *, timeout: float) -> bool:
            nonlocal elapsed
            assert timeout == pytest.approx(1.0)
            elapsed += 0.4
            return True

        def release(self) -> None:
            return None

    class _ObservedFuture(Future):
        def result(self, timeout: float | None = None):
            result_timeouts.append(timeout)
            return super().result(timeout=timeout)

    class _ImmediateExecutor:
        def submit(self, fn):
            future = _ObservedFuture()
            future.set_result(fn())
            return future

    adapter._inference_slots = _DelayedSemaphore()
    adapter._executor = _ImmediateExecutor()
    adapter._run_inference = lambda payload: SimpleNamespace(
        boxes=[[[12, 30], [112, 30], [112, 58], [12, 58]]],
        txts=["Protein 8,0 g"],
        scores=[0.98],
    )
    monkeypatch.setattr("fitminiapp_api.nutrition_label.ocr.time.monotonic", lambda: elapsed)

    candidates = adapter.extract_candidates(b"normalized-png")

    assert result_timeouts == [pytest.approx(0.6)]
    assert candidates[0].text == "Protein 8,0 g"


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
