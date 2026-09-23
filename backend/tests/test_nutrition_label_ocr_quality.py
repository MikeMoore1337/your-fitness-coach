from __future__ import annotations

import subprocess
import time
from decimal import Decimal
from pathlib import Path

import pytest
from PIL import Image

from fitminiapp_api.nutrition_label import ocr as ocr_module
from fitminiapp_api.nutrition_label.ocr import (
    LocalOcrError,
    OcrCandidate,
    OcrToken,
    TesseractOcr,
    parse_tesseract_tsv,
    structured_text_from_tokens,
)
from fitminiapp_api.nutrition_label.parser import build_draft_from_ocr, score_nutrition_candidate
from fitminiapp_api.services import nutrition_label as nutrition_label_service


def _complete_label(*, energy: str = "281,4 кДж / 66,8 ккал") -> str:
    return "\n".join(
        (
            "ПИЩЕВАЯ ЦЕННОСТЬ / NUTRITION FACTS",
            "100 г продукта serving information",
            f"Энергетическая ценность / Energy {energy}",
            "Белки / Protein 8,0 г",
            "Жиры / Fat 2,0 г",
            "Углеводы / Carbohydrate 4,2 г",
            "Соль / Salt 0,35 г",
            "Натрий / Sodium 140 мг",
        )
    )


def test_case_a_representative_pair_and_macros_are_explicit() -> None:
    draft = build_draft_from_ocr(_complete_label())

    assert draft.source_basis == "per_100_g"
    assert draft.normalized_facts.energy_kj is not None
    assert draft.normalized_facts.energy_kj.value == Decimal("281.4")
    assert draft.normalized_facts.energy_kcal is not None
    assert draft.normalized_facts.energy_kcal.value == Decimal("66.8")
    assert draft.normalized_facts.protein_g is not None
    assert draft.normalized_facts.protein_g.value == Decimal("8.0")
    assert draft.normalized_facts.fat_g is not None
    assert draft.normalized_facts.fat_g.value == Decimal("2.0")
    assert draft.normalized_facts.carbohydrate_g is not None
    assert draft.normalized_facts.carbohydrate_g.value == Decimal("4.2")


def test_cases_e_and_f_accept_decimal_comma_and_same_line_energy_pair() -> None:
    draft = build_draft_from_ocr(
        "\n".join(
            (
                "Nutrition Facts",
                "Per 100 g",
                "Energy 66,8 kcal / 281.4 kJ",
                "Protein 8,0 g",
                "Fat 2.0 g",
                "Carbohydrate 4,2 g",
            )
        )
    )

    assert draft.normalized_facts.energy_kcal is not None
    assert draft.normalized_facts.energy_kcal.value == Decimal("66.8")
    assert draft.normalized_facts.energy_kj is not None
    assert draft.normalized_facts.energy_kj.value == Decimal("281.4")


def test_case_g_net_weight_does_not_become_nutrition_basis() -> None:
    draft = build_draft_from_ocr(
        "\n".join(("Масса нетто 100 г", "Белки 8 г", "Жиры 2 г", "Углеводы 4 г"))
    )

    assert draft.source_basis == "ambiguous"
    assert draft.package_amount is not None
    assert draft.package_amount.amount == Decimal("100")
    assert all(
        getattr(draft.normalized_facts, field_name) is None
        for field_name in ("protein_g", "fat_g", "carbohydrate_g")
    )


def test_basis_context_handles_broken_line_no_space_and_ocr_r_shape() -> None:
    for basis_line in ("100 г", "100 гпродукта", "100 r"):
        draft = build_draft_from_ocr("\n".join(("Пищевая ценность", basis_line, "Белки 8 г")))
        assert draft.source_basis == "per_100_g"


def test_case_h_unitless_energy_is_ambiguous_and_never_kcal() -> None:
    draft = build_draft_from_ocr(
        "\n".join(
            (
                "Пищевая ценность 100 г продукта",
                "Energy 2814",
                "Protein 8 g",
                "Fat 2 g",
                "Carbohydrate 4 g",
            )
        )
    )

    assert draft.normalized_facts.energy_kcal is None
    assert draft.normalized_facts.energy_kj is None
    assert draft.field_evidence.energy_kcal == "ambiguous"
    assert draft.field_evidence.energy_kj == "ambiguous"
    assert "energy_unit_ambiguous" in draft.warnings
    assert "2814" not in {
        str(draft.normalized_facts.energy_kcal),
        str(draft.normalized_facts.energy_kj),
    }


def test_ocr_gram_glyph_shape_is_repaired_only_for_gram_nutrient_rows() -> None:
    draft = build_draft_from_ocr(
        "\n".join(
            (
                "Пищевая ценность 100 г продукта",
                "Белки 8,0r",
                "Жиры 2,0r",
                "Углеводы 4,2r",
            )
        )
    )

    assert draft.normalized_facts.protein_g is not None
    assert draft.normalized_facts.protein_g.value == Decimal("8.0")
    assert draft.normalized_facts.fat_g is not None
    assert draft.normalized_facts.fat_g.value == Decimal("2.0")
    assert draft.normalized_facts.carbohydrate_g is not None
    assert draft.normalized_facts.carbohydrate_g.value == Decimal("4.2")


def test_captured_kazakh_label_rows_and_reordered_energy_units_parse_safely() -> None:
    captured_geometry = (
        ("Пищевая", 221, 650, 104, 40, 93.238, 11),
        ("ценность", 314, 651, 119, 36, 98.323, 12),
        ("100 г продукта", 423, 641, 203, 58, 92.56, 13),
        ("(средние з", 614, 641, 134, 59, 92.005, 14),
        ("значения)", 731, 653, 122, 42, 95.503, 15),
        ("(орташа", 648, 686, 113, 58, 93.422, 16),
        ("мәндер):", 746, 687, 116, 58, 86.441, 17),
        ("6enkи", 218, 740, 80, 56, 64.137, 18),
        ("акуыздар", 302, 748, 131, 62, 89.391, 19),
        ("8,0r", 792, 751, 72, 62, 94.037, 20),
        ("*уры", 217, 807, 77, 55, 58.454, 21),
        ("майлар", 295, 809, 109, 63, 93.229, 22),
        ("2,0r", 796, 816, 67, 61, 95.057, 23),
        ("yгеводы", 216, 866, 121, 63, 66.505, 24),
        ("көмирсулар", 340, 875, 163, 71, 92.226, 25),
        ("4,2r", 796, 877, 64, 59, 89.695, 26),
        ("Энергeтичecкaя", 216, 925, 180, 73, 59.217, 27),
        ("ценность", 385, 949, 121, 54, 98.552, 28),
        ("(калорийность)/", 497, 947, 223, 66, 97.814, 29),
        ("281,4 KДж", 734, 941, 135, 66, 73.271, 30),
        ("Энеpreтикaлbк", 214, 969, 179, 79, 55.984, 31),
        ("КұНДЫЛЫғЫ", 379, 993, 151, 61, 69.959, 32),
        ("(Кунарлылыы)(66,8", 520, 986, 288, 80, 70.626, 33),
        ("ккал)", 786, 994, 75, 56, 82.857, 34),
    )
    captured_tokens = tuple(
        OcrToken(
            text=text,
            left=left,
            top=top,
            width=width,
            height=height,
            confidence=confidence,
            block_num=1,
            paragraph_num=1,
            line_num=line_num,
            word_num=1,
        )
        for text, left, top, width, height, confidence, line_num in captured_geometry
    )
    captured_photo_text = structured_text_from_tokens(captured_tokens)
    assert captured_photo_text == "\n".join(
        (
            "Пищевая ценность 100 г продукта (средние з (орташа значения) мәндер):",
            "6enkи акуыздар 8,0r",
            "*уры майлар 2,0r",
            "yгеводы көмирсулар 4,2r",
            "Энеpreтикaлbк Энергeтичecкaя КұНДЫЛЫғЫ ценность (калорийность)/ "
            "(Кунарлылыы)(66,8 281,4 KДж ккал)",
        )
    )

    draft = build_draft_from_ocr(captured_photo_text, structured_tokens=captured_tokens)

    assert draft.source_basis == "per_100_g"
    for field_name, expected in (
        ("protein_g", "8.0"),
        ("fat_g", "2.0"),
        ("carbohydrate_g", "4.2"),
        ("energy_kj", "281.4"),
        ("energy_kcal", "66.8"),
    ):
        fact = getattr(draft.normalized_facts, field_name)
        assert fact is not None
        assert fact.value == Decimal(expected)
    assert draft.warnings == []
    assert draft.normalized_facts.energy_kcal.value != Decimal("2814")


def test_native_kazakh_nutrient_names_are_bounded_aliases() -> None:
    draft = build_draft_from_ocr(
        "Пищевая ценность 100 г продукта\nақуыздар 8 г\nмайлар 2 г\nкөмірсулар 4 г"
    )

    assert draft.normalized_facts.protein_g is not None
    assert draft.normalized_facts.protein_g.value == Decimal("8")
    assert draft.normalized_facts.fat_g is not None
    assert draft.normalized_facts.fat_g.value == Decimal("2")
    assert draft.normalized_facts.carbohydrate_g is not None
    assert draft.normalized_facts.carbohydrate_g.value == Decimal("4")


def test_unordered_energy_units_stay_ambiguous_when_pairing_is_not_unique() -> None:
    draft = build_draft_from_ocr("Пищевая ценность 100 г продукта\nEnergy 1 1 KДж ккал")

    assert draft.normalized_facts.energy_kj is None
    assert draft.normalized_facts.energy_kcal is None
    assert draft.field_evidence.energy_kj == "ambiguous"
    assert draft.field_evidence.energy_kcal == "ambiguous"
    assert "energy_unit_ambiguous" in draft.warnings


@pytest.mark.parametrize(
    "energy_line",
    (
        "Energy 66,8 281,4 KДж",
        "Energy 66,8 281,4",
        "Energy 66,8 281,4 KДж ккал 100",
        "Energy 2814 66,8 KДж ккал",
        "Energy 1195 5000 KДж ккал",
    ),
)
def test_degraded_energy_pair_with_missing_extra_or_unsafe_evidence_stays_ambiguous(
    energy_line: str,
) -> None:
    draft = build_draft_from_ocr(f"Пищевая ценность 100 г продукта\n{energy_line}")

    assert draft.normalized_facts.energy_kj is None
    assert draft.normalized_facts.energy_kcal is None
    assert draft.field_evidence.energy_kj == "ambiguous"
    assert draft.field_evidence.energy_kcal == "ambiguous"
    assert "energy_unit_ambiguous" in draft.warnings
    assert "2814" not in {
        str(draft.normalized_facts.energy_kj),
        str(draft.normalized_facts.energy_kcal),
    }


def test_explicit_inverse_energy_pair_remains_rejected() -> None:
    draft = build_draft_from_ocr("Пищевая ценность 100 г продукта\nEnergy 66,8 кДж / 281,4 ккал")

    assert draft.normalized_facts.energy_kj is None
    assert draft.normalized_facts.energy_kcal is None
    assert "energy_unit_conflict" in draft.warnings


def test_energy_kj_only_does_not_fill_kcal() -> None:
    draft = build_draft_from_ocr("Пищевая ценность 100 г продукта\nEnergy 281,4 кДж\nProtein 8 г")

    assert draft.normalized_facts.energy_kj is not None
    assert draft.normalized_facts.energy_kj.value == Decimal("281.4")
    assert draft.normalized_facts.energy_kcal is None
    assert draft.field_evidence.energy_kcal == "absent"


def test_percent_dv_never_coexists_with_mass_prefill() -> None:
    draft = build_draft_from_ocr("Пищевая ценность 100 г продукта\nProtein 8 г 16%")

    assert draft.normalized_facts.protein_g is None
    assert draft.field_evidence.protein_g == "ambiguous"
    assert "dv_as_mass" in draft.warnings


def test_explicit_2814_kcal_with_macros_is_rejected_as_an_outlier() -> None:
    draft = build_draft_from_ocr(_complete_label(energy="11754 кДж / 2814 ккал"))

    assert draft.normalized_facts.energy_kcal is None
    assert draft.normalized_facts.energy_kj is None
    assert draft.field_evidence.energy_kcal == "ambiguous"
    assert "energy_outlier" in draft.warnings


def test_decimal_separator_loss_in_macro_row_fails_closed() -> None:
    draft = build_draft_from_ocr(
        "\n".join(
            (
                "Пищевая ценность 100 г продукта",
                "Energy 66,8 kcal / 281,4 kJ",
                "Protein 8,0 g",
                "Fat 2,0 g",
                "Carbohydrate 42 g",
            )
        )
    )

    assert all(
        getattr(draft.normalized_facts, field_name) is None
        for field_name in ("energy_kcal", "protein_g", "fat_g", "carbohydrate_g")
    )
    assert all(
        getattr(draft.field_evidence, field_name) == "ambiguous"
        for field_name in ("energy_kcal", "protein_g", "fat_g", "carbohydrate_g")
    )
    assert "energy_sanity_warning" in draft.warnings


def test_mismatching_energy_pair_is_ambiguous_without_replacement() -> None:
    draft = build_draft_from_ocr(_complete_label(energy="281,4 кДж / 281,4 ккал"))

    assert draft.normalized_facts.energy_kcal is None
    assert draft.normalized_facts.energy_kj is None
    assert "energy_unit_conflict" in draft.warnings


def test_case_i_partial_draft_remains_editable() -> None:
    draft = build_draft_from_ocr("Per 100 g\nProtein 8 g")

    assert draft.normalized_facts.protein_g is not None
    assert draft.normalized_facts.protein_g.value == Decimal("8")
    assert "missing_required_fact" in draft.warnings
    assert draft.requires_user_review is True


def test_case_j_unreadable_text_has_no_numeric_prefill() -> None:
    draft = build_draft_from_ocr("ПИЩЕВАЯ ЦЕННОСТЬ\n???")

    assert draft.source_basis == "ambiguous"
    assert all(
        getattr(draft.normalized_facts, field_name) is None
        for field_name in ("energy_kcal", "protein_g")
    )


def _token(text: str, left: int, top: int, *, width: int = 40) -> OcrToken:
    return OcrToken(
        text=text,
        left=left,
        top=top,
        width=width,
        height=24,
        confidence=92.0,
        block_num=1,
        paragraph_num=1,
        line_num=top,
        word_num=left,
    )


def test_structured_tokens_associate_separate_label_and_value_columns() -> None:
    tokens = (
        _token("ПИЩЕВАЯ", 10, 10, width=100),
        _token("ЦЕННОСТЬ", 115, 10, width=120),
        _token("100", 10, 45),
        _token("г", 55, 45),
        _token("Energy", 10, 90, width=75),
        _token("281,4", 400, 86, width=65),
        _token("кДж", 470, 86, width=48),
        _token("/", 525, 86, width=12),
        _token("66,8", 545, 86, width=65),
        _token("ккал", 615, 86, width=50),
        _token("Белки", 10, 135, width=65),
        _token("8,0", 400, 131, width=45),
        _token("г", 450, 131),
        _token("Жиры", 10, 180, width=55),
        _token("2,0", 400, 176, width=45),
        _token("г", 450, 176),
        _token("Углеводы", 10, 225, width=100),
        _token("427", 400, 221, width=45),
        _token("Соль", 10, 270, width=50),
        _token("0,35", 400, 266, width=55),
        _token("г", 460, 266),
        _token("Натрий", 10, 315, width=70),
        _token("140", 400, 311, width=45),
        _token("мг", 450, 311, width=45),
    )
    text = structured_text_from_tokens(tokens)
    draft = build_draft_from_ocr(text, structured_tokens=tokens)

    assert draft.normalized_facts.energy_kcal is not None
    assert draft.normalized_facts.energy_kj is not None
    assert draft.normalized_facts.protein_g is not None
    assert draft.normalized_facts.fat_g is not None
    assert draft.normalized_facts.carbohydrate_g is None
    assert draft.field_evidence.carbohydrate_g == "ambiguous"
    assert "untrusted_numeric_token" in draft.warnings


def test_tsv_parser_preserves_geometry_and_confidence() -> None:
    tsv = (
        b"level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        b"5\t1\t2\t3\t4\t5\t10\t20\t30\t12\t87.5\tProtein\n"
    )

    tokens = parse_tesseract_tsv(tsv)

    assert len(tokens) == 1
    assert tokens[0].text == "Protein"
    assert tokens[0].left == 10
    assert tokens[0].confidence == 87.5
    assert tokens[0].block_num == 2
    assert tokens[0].paragraph_num == 3
    assert tokens[0].line_num == 4
    assert tokens[0].word_num == 5


def test_tesseract_pass_is_explicit_structured_and_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeProcess:
        returncode = 0

        def communicate(self, *, timeout: float | None = None) -> tuple[bytes, bytes]:
            captured["timeout"] = timeout
            return b"level\ttext\n", b""

    def fake_popen(argv: list[str], **kwargs: object) -> FakeProcess:
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(ocr_module.subprocess, "Popen", fake_popen)
    engine = TesseractOcr(languages="rus+eng", timeout_seconds=8, max_output_chars=50_000)

    output = engine._run_pass("tesseract", Path("label.png"), 11, time.monotonic() + 2)

    assert output == b"level\ttext\n"
    assert captured["argv"] == [
        "tesseract",
        "label.png",
        "stdout",
        "--oem",
        "1",
        "--psm",
        "11",
        "--dpi",
        "300",
        "-l",
        "rus+eng",
        "tsv",
    ]
    assert captured["kwargs"] == {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.DEVNULL,
        "shell": False,
    }
    assert isinstance(captured["timeout"], float)


def test_tesseract_timeout_kills_child_and_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    class TimeoutProcess:
        returncode = -9

        def __init__(self) -> None:
            self.killed = False

        def communicate(self, *, timeout: float | None = None) -> tuple[bytes, bytes]:
            if timeout is not None and not self.killed:
                raise subprocess.TimeoutExpired("tesseract", timeout)
            return b"", b""

        def kill(self) -> None:
            self.killed = True

    process = TimeoutProcess()
    monkeypatch.setattr(ocr_module.subprocess, "Popen", lambda *args, **kwargs: process)
    engine = TesseractOcr(languages="rus+eng", timeout_seconds=8, max_output_chars=50_000)

    with pytest.raises(LocalOcrError, match="local_ocr_timeout"):
        engine._run_pass("tesseract", Path("label.png"), 6, time.monotonic() + 1)

    assert process.killed is True


def test_default_pass_budget_allows_constrained_first_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = TesseractOcr(
        languages="rus+eng",
        timeout_seconds=8,
        max_output_chars=50_000,
        executable="fake-tesseract",
    )
    monkeypatch.setattr(
        ocr_module,
        "_iter_preprocessed_variants",
        lambda _data: iter(
            (ocr_module.PreprocessedVariant("roi_deskew_minus_1_5_2x", Image.new("RGB", (1, 1))),)
        ),
    )

    calls = 0
    budgets: list[float] = []

    def fake_run(self, executable, image_path, psm, deadline):
        nonlocal calls
        del self, executable, image_path, psm
        budgets.append(deadline - time.monotonic())
        if calls == 0 and deadline - time.monotonic() < 3.0:
            raise LocalOcrError("local_ocr_timeout")
        calls += 1
        return b"level\ttext\n"

    monkeypatch.setattr(ocr_module.TesseractOcr, "_run_pass", fake_run)

    candidates = tuple(engine.iter_candidates(b"normalized"))

    assert len(candidates) == 3
    assert budgets[0] > 3.0
    assert all(budget <= 1.6 for budget in budgets[1:])


def test_candidate_extraction_preserves_completed_candidates_before_optional_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = TesseractOcr(
        languages="rus+eng",
        timeout_seconds=8,
        max_output_chars=50_000,
        executable="fake-tesseract",
    )
    calls = 0

    def fake_run(self, executable, image_path, psm, deadline):
        del self, executable, image_path, psm, deadline
        nonlocal calls
        calls += 1
        if calls == 1:
            return b"level\ttext\n"
        raise LocalOcrError("local_ocr_timeout")

    monkeypatch.setattr(
        ocr_module,
        "_iter_preprocessed_variants",
        lambda _data: iter(
            (ocr_module.PreprocessedVariant("source_rgb_1x", Image.new("RGB", (1, 1))),)
        ),
    )
    monkeypatch.setattr(ocr_module.TesseractOcr, "_run_pass", fake_run)

    candidates = engine.extract_candidates(b"normalized")

    assert len(candidates) == 1
    assert calls == 2


def _candidate(text: str, *, variant: str = "source_rgb_1x", psm: int = 6) -> OcrCandidate:
    return OcrCandidate(variant=variant, psm=psm, text=text, tokens=(), elapsed_ms=1)


class _StreamingCandidateEngine:
    name = "local_tesseract"
    version = "test-streaming-v1"

    def __init__(self, events: tuple[OcrCandidate | LocalOcrError, ...]) -> None:
        self.events = events
        self.calls = 0

    def iter_candidates(self, image_bytes: bytes):
        assert image_bytes == b"normalized"
        for event in self.events:
            if isinstance(event, LocalOcrError):
                raise event
            self.calls += 1
            yield event


def test_strong_first_candidate_stops_remaining_passes() -> None:
    engine = _StreamingCandidateEngine(
        (_candidate(_complete_label()), LocalOcrError("local_ocr_failed"))
    )

    selected = nutrition_label_service._parse_ocr_candidates(engine, b"normalized")

    assert selected.normalized_facts.protein_g is not None
    assert engine.calls == 1


def test_incomplete_primary_runs_fallback_and_stops_on_second_strong_candidate() -> None:
    partial = "Per 100 g\nProtein 8 g\nFat 2 g\nCarbohydrate 4 g"
    engine = _StreamingCandidateEngine(
        (
            _candidate(partial),
            _candidate(_complete_label(), variant="roi_deskew_minus_1_5_2x", psm=4),
            LocalOcrError("local_ocr_failed"),
        )
    )

    selected = nutrition_label_service._parse_ocr_candidates(engine, b"normalized")

    assert selected.normalized_facts.energy_kcal is not None
    assert engine.calls == 2


def test_optional_timeout_after_reviewable_candidate_returns_partial_draft() -> None:
    partial = "Per 100 g\nProtein 8 g\nFat 2 g\nCarbohydrate 4 g"
    engine = _StreamingCandidateEngine((_candidate(partial), LocalOcrError("local_ocr_timeout")))

    selected = nutrition_label_service._parse_ocr_candidates(engine, b"normalized")

    assert selected.normalized_facts.protein_g is not None
    assert selected.normalized_facts.energy_kcal is None
    assert "ocr_budget_exhausted" in selected.warnings


def test_timeout_before_any_usable_candidate_remains_controlled_error() -> None:
    engine = _StreamingCandidateEngine((LocalOcrError("local_ocr_timeout"),))

    with pytest.raises(LocalOcrError, match="local_ocr_timeout"):
        nutrition_label_service._parse_ocr_candidates(engine, b"normalized")


def test_unsafe_energy_candidate_is_not_early_success_and_safe_fallback_wins() -> None:
    engine = _StreamingCandidateEngine(
        (
            _candidate(_complete_label(energy="2814 kcal")),
            _candidate(_complete_label(), variant="roi_deskew_minus_1_5_2x", psm=4),
        )
    )

    selected = nutrition_label_service._parse_ocr_candidates(engine, b"normalized")

    assert selected.normalized_facts.energy_kcal is not None
    assert selected.normalized_facts.energy_kcal.value == Decimal("66.8")
    assert "energy_outlier" not in selected.warnings
    assert engine.calls == 2


def test_pass_budget_is_bounded_and_each_priority_pair_runs_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = TesseractOcr(
        languages="rus+eng",
        timeout_seconds=1,
        pass_timeout_seconds=0.2,
        initial_pass_timeout_seconds=0.2,
        max_output_chars=50_000,
        executable="fake-tesseract",
    )
    calls: list[tuple[str, int]] = []
    deadline_budgets: list[float] = []
    variants = (
        ocr_module.PreprocessedVariant("source_rgb_1x", Image.new("RGB", (1, 1))),
        ocr_module.PreprocessedVariant("roi_gray_contrast_denoised_2x", Image.new("RGB", (1, 1))),
    )

    def fake_run(self, executable, image_path, psm, deadline):
        del self, executable
        started = time.monotonic()
        calls.append((image_path.stem, psm))
        deadline_budgets.append(deadline - started)
        return b"level\ttext\n"

    monkeypatch.setattr(ocr_module, "_iter_preprocessed_variants", lambda _data: iter(variants))
    monkeypatch.setattr(ocr_module.TesseractOcr, "_run_pass", fake_run)

    candidates = tuple(engine.iter_candidates(b"normalized"))

    assert len(candidates) == 6
    assert len(calls) == len(set(calls))
    assert all(0 < budget <= 0.21 for budget in deadline_budgets)


def test_candidate_score_prefers_complete_safe_facts_over_longer_partial_text() -> None:
    partial = build_draft_from_ocr("Per 100 g\n" + "noise " * 100 + "Protein 8 g")
    complete = build_draft_from_ocr(_complete_label())

    partial_score = score_nutrition_candidate(partial)
    complete_score = score_nutrition_candidate(complete)

    assert complete_score.rank > partial_score.rank
    assert "required=4/4" in complete_score.reasons


def test_service_candidate_selection_is_stable_and_not_text_length_based() -> None:
    class CandidateEngine:
        name = "local_tesseract"
        version = "test-structured-v1"

        def extract_text(self, image_bytes: bytes) -> str:
            raise AssertionError("candidate extraction should be selected")

        def extract_candidates(self, image_bytes: bytes) -> tuple[OcrCandidate, ...]:
            assert image_bytes == b"normalized"
            return (
                OcrCandidate(
                    variant="long_partial",
                    psm=6,
                    text="Per 100 g\n" + "noise " * 100 + "Protein 8 g",
                    tokens=(),
                    elapsed_ms=1,
                ),
                OcrCandidate(
                    variant="short_complete",
                    psm=4,
                    text=_complete_label(),
                    tokens=(),
                    elapsed_ms=1,
                ),
            )

    selected = nutrition_label_service._parse_ocr_candidates(CandidateEngine(), b"normalized")

    assert selected.normalized_facts.carbohydrate_g is not None
    assert selected.metadata.model == "test-structured-v1"
