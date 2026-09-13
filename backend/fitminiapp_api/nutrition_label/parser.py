from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Literal, cast

from pydantic import ValidationError

from fitminiapp_api.nutrition_label.contracts import (
    CANONICAL_DRAFT_SCHEMA_VERSION,
    CANONICAL_POLICY_REVISION,
    NUTRIENT_FIELDS,
    NUTRIENT_UNITS,
    CanonicalDraft,
    CanonicalFact,
    DailyValuePercent,
    DraftMetadata,
    FieldConfidence,
    FieldEvidence,
    NutrientFacts,
    SourceFact,
    SourceNutrientFacts,
    empty_derived_facts,
)

_NUMBER = r"(?P<number>\d{1,6}(?:[\.,]\d{1,4})?)"
_UNIT = r"(?P<unit>ккал|kcal|кдж|kj|мг|mg|мл|ml|г|g|%)?"
_VALUE_PATTERN = re.compile(rf"(?<![\w])[-+]?{_NUMBER}\s*{_UNIT}(?![\w])", re.IGNORECASE)
_BASIS_PATTERN = re.compile(
    r"(?<!\w)(?:на|per)\s*(?:100\s*(?P<mass>г|g|мл|ml)|(?P<serving>порц\w*|serving))(?!\w)",
    re.IGNORECASE,
)
_SERVING_SIZE_PATTERN = re.compile(
    rf"(?:размер\s+порци\w*|serving\s+size|порци\w*)\D{{0,12}}{_NUMBER}\s*(?P<unit>г|g|мл|ml)",
    re.IGNORECASE,
)
_SERVINGS_PATTERN = re.compile(
    rf"(?:порци\w*\s+в\s+упаковке|servings?\s+per\s+container)\D{{0,12}}{_NUMBER}",
    re.IGNORECASE,
)
_PACKAGE_PATTERN = re.compile(
    rf"(?:масса\s+нетто|net\s+weight|объ[её]м|volume)\D{{0,12}}{_NUMBER}\s*(?P<unit>г|g|мл|ml)",
    re.IGNORECASE,
)

_LABELS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("saturated_fat_g", ("насыщенн", "saturated fat")),
    ("trans_fat_g", ("трансжир", "trans fat")),
    ("added_sugars_g", ("добавленн.*сахар", "added sugars")),
    ("carbohydrate_g", ("углевод", "carbohydrate", "total carbs", "carbs")),
    ("protein_g", ("белк", "protein")),
    ("fat_g", ("жир", "fat")),
    ("sugars_g", ("сахар", "sugars", "sugar")),
    ("fiber_g", ("клетчат", "пищев.*волок", "fiber")),
    ("salt_g", ("соль", "salt")),
    ("sodium_mg", ("натри", "sodium")),
    ("cholesterol_mg", ("холестерин", "cholesterol")),
    ("energy_kcal", ("энергетическ.*ценност", "калори", "energy", "calories", "calorie")),
    ("energy_kj", ("энергетическ.*ценност", "energy")),
)

_WARNING_ORDER = (
    "ambiguous_basis",
    "serving_size_required_for_normalization",
    "dv_as_mass",
    "missing_required_fact",
    "energy_sanity_warning",
    "unreadable_field",
)


class CanonicalNormalizationError(ValueError):
    pass


def parse_decimal_token(value: str) -> Decimal:
    normalized = value.strip().replace("\u00a0", "").replace(" ", "").replace(",", ".")
    try:
        result = Decimal(normalized)
    except InvalidOperation as exc:
        raise CanonicalNormalizationError("invalid_decimal") from exc
    if not result.is_finite() or result < 0:
        raise CanonicalNormalizationError("invalid_decimal")
    return result


def _basis_from_text(
    text: str,
) -> tuple[Literal["per_100_g", "per_100_ml", "per_serving", "ambiguous"], list[str]]:
    matches = list(_BASIS_PATTERN.finditer(text))
    candidates: list[str] = []
    for match in matches:
        if match.group("mass") in {"г", "g"}:
            candidates.append("per_100_g")
        elif match.group("mass") in {"мл", "ml"}:
            candidates.append("per_100_ml")
        elif match.group("serving"):
            candidates.append("per_serving")
    unique = list(dict.fromkeys(candidates))
    if len(unique) == 1:
        return cast(Literal["per_100_g", "per_100_ml", "per_serving", "ambiguous"], unique[0]), []
    if len(unique) > 1:
        return "ambiguous", ["ambiguous_basis"]
    if _SERVING_SIZE_PATTERN.search(text) or _SERVINGS_PATTERN.search(text):
        return "per_serving", []
    return "ambiguous", ["ambiguous_basis"]


def _source_language(text: str) -> Literal["ru", "en", "mixed", "unknown"]:
    has_cyrillic = bool(re.search(r"[А-Яа-яЁё]", text))
    has_latin = bool(re.search(r"[A-Za-z]", text))
    if has_cyrillic and has_latin:
        return "mixed"
    if has_cyrillic:
        return "ru"
    if has_latin:
        return "en"
    return "unknown"


def _label_format(text: str) -> Literal["ru_standard", "eu_uk", "us_nutrition_facts", "unknown"]:
    lowered = text.casefold()
    if "nutrition facts" in lowered or "servings per container" in lowered:
        return "us_nutrition_facts"
    if re.search(r"\b(?:per|100\s*g|100\s*ml)\b", lowered) and _source_language(text) == "en":
        return "eu_uk"
    if _source_language(text) in {"ru", "mixed"}:
        return "ru_standard"
    return "unknown"


def _expected_unit(field_name: str) -> Literal["g", "mg", "kcal", "kJ"]:
    return NUTRIENT_UNITS[field_name]


def _canonical_unit(raw: str | None, expected: str) -> str | None:
    if raw is None or raw == "%":
        return raw
    normalized = raw.casefold()
    aliases = {
        "г": "g",
        "мг": "mg",
        "мл": "ml",
        "ккал": "kcal",
        "кдж": "kJ",
        "kj": "kJ",
        "kcal": "kcal",
        "mg": "mg",
        "g": "g",
        "ml": "ml",
    }
    return aliases.get(normalized, raw)


def _values_for_line(line: str, expected_unit: str) -> tuple[list[Decimal], bool]:
    values: list[Decimal] = []
    had_percent = False
    for match in _VALUE_PATTERN.finditer(line):
        unit = _canonical_unit(match.group("unit"), expected_unit)
        if unit == "%":
            had_percent = True
            continue
        if unit is not None and unit != expected_unit:
            continue
        try:
            values.append(parse_decimal_token(match.group("number")))
        except CanonicalNormalizationError:
            continue
    return values, had_percent


def _field_for_line(line: str) -> str | None:
    lowered = line.casefold()
    if (
        re.search(r"(?:энергетическ.*ценност|energy|калори|calorie)", lowered)
        and re.search(r"\d[\d\s\.,]*\s*(?:кдж|kj)\b", lowered)
        and not re.search(r"\d[\d\s\.,]*\s*(?:ккал|kcal)\b", lowered)
    ):
        return "energy_kj"
    for field_name, patterns in _LABELS:
        if any(re.search(pattern, lowered, re.IGNORECASE) for pattern in patterns):
            return field_name
    return None


def _numeric_metadata(text: str):
    serving_size = None
    match = _SERVING_SIZE_PATTERN.search(text)
    if match:
        serving_size = {
            "amount": parse_decimal_token(match.group("number")),
            "unit": "g" if match.group("unit") in {"г", "g"} else "ml",
        }
    servings = None
    match = _SERVINGS_PATTERN.search(text)
    if match:
        servings = parse_decimal_token(match.group("number"))
    package = None
    match = _PACKAGE_PATTERN.search(text)
    if match:
        package = {
            "amount": parse_decimal_token(match.group("number")),
            "unit": "g" if match.group("unit") in {"г", "g"} else "ml",
        }
    return serving_size, servings, package


def _convert_value(value: Decimal, field_name: str, source_basis: str, serving_size: dict | None):
    if source_basis != "per_serving" or serving_size is None:
        return value, source_basis
    serving_unit = serving_size["unit"]
    if serving_unit == "g":
        target_basis = "per_100_g"
    elif serving_unit == "ml":
        target_basis = "per_100_ml"
    else:
        return value, source_basis
    return value * Decimal(100) / serving_size["amount"], target_basis


def _empty_field_evidence() -> dict[str, str]:
    return dict.fromkeys(NUTRIENT_FIELDS, "absent")


def build_draft_from_ocr(
    ocr_text: str,
    *,
    provider: str = "local_tesseract",
    model: str = "tesseract",
    prompt_version: str = "ocr-text-v1",
    policy_revision: str = CANONICAL_POLICY_REVISION,
) -> CanonicalDraft:
    """Parse only explicit label-like rows; no model or heuristic fills absent fields."""

    if not isinstance(ocr_text, str) or len(ocr_text) > 50_000:
        raise CanonicalNormalizationError("ocr_text_too_large")
    source_basis, warnings = _basis_from_text(ocr_text)
    serving_size, servings_per_container, package_amount = _numeric_metadata(ocr_text)
    source_facts: dict[str, list[SourceFact] | None] = dict.fromkeys(NUTRIENT_FIELDS)
    normalized: dict[str, CanonicalFact | None] = dict.fromkeys(NUTRIENT_FIELDS)
    evidence = _empty_field_evidence()
    daily_values: dict[str, Decimal | None] = {
        field_name: None for field_name in NUTRIENT_FIELDS if field_name != "energy_kj"
    }
    seen: set[str] = set()
    lines: list[tuple[int, str]] = []
    for line_number, raw_line in enumerate(ocr_text.splitlines(), start=1):
        line = " ".join(raw_line.split())
        if not line:
            continue
        lines.append((line_number, line))
        if (
            _field_for_line(line) == "energy_kcal"
            and re.search(r"\d[\d\s\.,]*\s*(?:ккал|kcal)\b", line, re.IGNORECASE)
            and re.search(r"\d[\d\s\.,]*\s*(?:кдж|kj)\b", line, re.IGNORECASE)
        ):
            kj_match = re.search(
                r"(?P<number>\d{1,6}(?:[\.,]\d{1,4})?)\s*(?:кдж|kj)\b",
                line,
                re.IGNORECASE,
            )
            if kj_match:
                lines.append((line_number, f"Energy {kj_match.group('number')} kJ"))

    for line_number, line in lines:
        field_name = _field_for_line(line)
        if field_name is None:
            continue
        expected_unit = _expected_unit(field_name)
        values, had_percent = _values_for_line(line, expected_unit)
        column_ref = f"line_{line_number}_{field_name}"
        if had_percent and not values:
            source_facts[field_name] = [
                SourceFact(
                    value=None,
                    unit=expected_unit,
                    basis_ref=source_basis if source_basis != "ambiguous" else "per_serving",
                    column_ref=column_ref,
                    evidence="ambiguous",
                )
            ]
            evidence[field_name] = "ambiguous"
            if "dv_as_mass" not in warnings:
                warnings.append("dv_as_mass")
            continue
        if not values:
            continue
        if len(values) > 1:
            source_facts[field_name] = [
                SourceFact(
                    value=None,
                    unit=expected_unit,
                    basis_ref=source_basis if source_basis != "ambiguous" else "per_serving",
                    column_ref=column_ref,
                    evidence="ambiguous",
                )
            ]
            evidence[field_name] = "ambiguous"
            if "ambiguous_column" not in warnings:
                warnings.append("ambiguous_column")
            continue
        value = values[0]
        if field_name in seen:
            if "ambiguous_column" not in warnings:
                warnings.append("ambiguous_column")
            evidence[field_name] = "ambiguous"
            source_facts[field_name] = None
            normalized[field_name] = None
            continue
        seen.add(field_name)
        source_basis_for_cell = source_basis if source_basis != "ambiguous" else "per_serving"
        source_facts[field_name] = [
            SourceFact(
                value=value,
                unit=expected_unit,
                basis_ref=source_basis_for_cell,
                column_ref=column_ref,
                evidence="read",
            )
        ]
        evidence[field_name] = "read"
        if source_basis != "ambiguous":
            normalized_value, normalized_basis = _convert_value(
                value, field_name, source_basis, serving_size
            )
            if (
                source_basis == "per_serving"
                and serving_size is None
                and "serving_size_required_for_normalization" not in warnings
            ):
                warnings.append("serving_size_required_for_normalization")
            normalized[field_name] = CanonicalFact(
                value=normalized_value,
                unit=expected_unit,
                basis_ref=normalized_basis,
            )
        else:
            normalized[field_name] = None

    if source_basis == "ambiguous":
        for field_name in NUTRIENT_FIELDS:
            cells = source_facts[field_name]
            if cells is not None:
                source_facts[field_name] = [
                    cell.model_copy(update={"value": None, "evidence": "ambiguous"})
                    for cell in cells
                ]
        evidence = {
            field_name: ("ambiguous" if source_facts[field_name] is not None else "absent")
            for field_name in NUTRIENT_FIELDS
        }
    required_fields = ("energy_kcal", "protein_g", "fat_g", "carbohydrate_g")
    if any(normalized[field_name] is None for field_name in required_fields):
        warnings.append("missing_required_fact")
    if (
        normalized["energy_kcal"] is not None
        and normalized["protein_g"] is not None
        and normalized["fat_g"] is not None
        and normalized["carbohydrate_g"] is not None
        and source_basis != "ambiguous"
    ):
        implied = (
            normalized["protein_g"].value * Decimal(4)
            + normalized["fat_g"].value * Decimal(9)
            + normalized["carbohydrate_g"].value * Decimal(4)
        )
        if abs(implied - normalized["energy_kcal"].value) > max(
            Decimal("20"), normalized["energy_kcal"].value * Decimal("0.2")
        ):
            warnings.append("energy_sanity_warning")
    warnings = list(dict.fromkeys(warnings))
    warnings.sort(
        key=lambda value: (_WARNING_ORDER.index(value) if value in _WARNING_ORDER else 99, value)
    )
    try:
        return CanonicalDraft(
            schema_version=CANONICAL_DRAFT_SCHEMA_VERSION,
            source_language=_source_language(ocr_text),
            label_format=_label_format(ocr_text),
            source_basis=source_basis,
            serving_size=serving_size,
            servings_per_container=servings_per_container,
            package_amount=package_amount,
            source_facts=SourceNutrientFacts.model_validate(source_facts),
            normalized_facts=NutrientFacts.model_validate(normalized),
            derived_fields=empty_derived_facts(),
            displayed_daily_value_percent=DailyValuePercent.model_validate(daily_values),
            field_evidence=FieldEvidence.model_validate(evidence),
            confidence_kind="none",
            confidence=FieldConfidence(),
            warnings=warnings,
            requires_user_review=True,
            metadata=DraftMetadata(
                provider=provider,
                model=model,
                prompt_version=prompt_version,
                schema_version=CANONICAL_DRAFT_SCHEMA_VERSION,
                policy_revision=policy_revision,
            ),
        )
    except ValidationError as exc:
        raise CanonicalNormalizationError("invalid_canonical_draft") from exc


def build_draft_from_facts(
    *,
    source_basis: Literal["per_100_g", "per_100_ml", "per_serving"],
    values: dict[str, Decimal | str | None],
    serving_size: dict | None = None,
    source_language: Literal["ru", "en", "mixed", "unknown"] = "unknown",
    label_format: Literal["ru_standard", "eu_uk", "us_nutrition_facts", "unknown"] = "unknown",
) -> CanonicalDraft:
    """Test/adapter seam for already structured local OCR output."""

    lines = [
        f"{field_name} {value} {_expected_unit(field_name)}"
        for field_name, value in values.items()
        if value is not None
    ]
    basis_label = {
        "per_100_g": "на 100 г",
        "per_100_ml": "на 100 мл",
        "per_serving": "на порцию",
    }[source_basis]
    serving_line = (
        [f"Serving size {serving_size['amount']} {serving_size['unit']}"]
        if serving_size is not None
        else []
    )
    text = "\n".join([basis_label, *serving_line, *lines])
    return build_draft_from_ocr(
        text,
        provider="local_test_adapter",
        model="structured-fixture",
        prompt_version="fixture-v1",
    )
