from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
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
from fitminiapp_api.nutrition_label.ocr import OcrToken, structured_text_from_tokens

_NUMBER = r"(?P<number>\d{1,6}(?:[\.,]\d{1,4})?)"
_UNIT = r"(?P<unit>ккал|kcal|кдж|kj|мг|mg|мл|ml|г|g|%)?"
_VALUE_PATTERN = re.compile(rf"(?<![\w])[-+]?{_NUMBER}\s*{_UNIT}(?![\w])", re.IGNORECASE)
_EXPLICIT_ENERGY_PATTERN = re.compile(
    r"(?<![\w])(?P<number>\d{1,6}(?:[\.,]\d{1,4})?)\s*"
    r"(?P<unit>ккал|kcal|кдж|kj)\b",
    re.IGNORECASE,
)
_OCR_GRAM_GLYPH_PATTERN = re.compile(
    r"(?P<number>\d{1,6}(?:[\.,]\d{1,4})?)[ \t]*r(?=[ \t]*(?:$|[\s,;:]))",
    re.IGNORECASE,
)
_BASIS_CONTEXT = (
    r"(?:пищев\w*\s+ценност\w*|энергетическ\w*\s+ценност\w*|"
    r"nutrition(?:al)?(?:\s+(?:facts?|information|value))?|food\s+value)"
)
_BASIS_PATTERN = re.compile(
    rf"(?<!\w)(?:"
    rf"(?:на|в)\s*(?:100\s*(?P<ru_mass>г|g|мл|ml)|(?P<ru_serving>порц\w*))"
    rf"|100\s*(?P<product_mass>г|g|мл|ml)\s*(?:продукт\w*|product)"
    rf"|per\s*100\s*(?P<per_mass>g|ml)"
    rf"|per\s*(?P<per_serving>serving)"
    rf"|{_BASIS_CONTEXT}\s*[:\-]?\s*(?:на|в)?\s*100\s*"
    rf"(?P<context_mass>г|g|мл|ml)"
    rf")(?!\w)",
    re.IGNORECASE,
)
_BARE_RU_BASIS_LINE = re.compile(
    r"^\s*(?:на|в)\s*(?:100\s*(?:г|g|мл|ml)|порц\w*)"
    r"(?:\s+продукт\w*)?\s*[.:;,!?-]*\s*$",
    re.IGNORECASE,
)
_BARE_MASS_LINE = re.compile(
    r"^\s*100\s*(?:г|g|мл|ml)(?:\s*продукт\w*|\s*product)?"
    r"\s*[.:;,!?-]*\s*$",
    re.IGNORECASE,
)
_SERVING_SIZE_PATTERN = re.compile(
    rf"(?:размер\s+порци\w*|serving\s+size|порци\w*)\D{{0,12}}{_NUMBER}\s*"
    rf"(?P<unit>г|g|мл|ml)",
    re.IGNORECASE,
)
_SERVINGS_PATTERN = re.compile(
    rf"(?:порци\w*\s+в\s+упаковке|servings?\s+per\s+container)\D{{0,12}}{_NUMBER}",
    re.IGNORECASE,
)
_PACKAGE_PATTERN = re.compile(
    rf"(?:масса\s+нетто|net\s+weight|объ[её]м|volume)\D{{0,12}}{_NUMBER}\s*"
    rf"(?P<unit>г|g|мл|ml)",
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
)

_WARNING_ORDER = (
    "ambiguous_basis",
    "serving_size_required_for_normalization",
    "dv_as_mass",
    "missing_required_fact",
    "energy_unit_ambiguous",
    "ambiguous_column",
    "untrusted_numeric_token",
    "energy_outlier",
    "nutrient_outlier",
    "energy_unit_conflict",
    "energy_sanity_warning",
    "unreadable_field",
)
_REQUIRED_FIELDS = ("energy_kcal", "protein_g", "fat_g", "carbohydrate_g")
_CATASTROPHIC_WARNINGS = {"energy_outlier", "energy_unit_conflict", "energy_sanity_warning"}


class CanonicalNormalizationError(ValueError):
    pass


@dataclass(frozen=True)
class NutritionCandidateScore:
    rank: tuple[int, ...]
    reasons: tuple[str, ...]


def parse_decimal_token(value: str) -> Decimal:
    normalized = value.strip().replace("\u00a0", "").replace(" ", "").replace(",", ".")
    try:
        result = Decimal(normalized)
    except InvalidOperation as exc:
        raise CanonicalNormalizationError("invalid_decimal") from exc
    if not result.is_finite() or result < 0:
        raise CanonicalNormalizationError("invalid_decimal")
    return result


def _normalize_basis_shape(text: str) -> str:
    """Repair only the bounded OCR `100 r` glyph shape in a nutrition context."""

    return re.sub(
        r"(?<!\w)100[ \t]*r(?=[ \t]*(?:продукт\w*|product|serving|information)?[ \t]*(?:$|\n))",
        "100 г",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )


def _basis_match_has_context(text: str, match: re.Match[str]) -> bool:
    if match.group("ru_mass") is None and match.group("ru_serving") is None:
        return True
    line_start = text.rfind("\n", 0, match.start()) + 1
    line_end = text.find("\n", match.end())
    line = text[line_start:] if line_end == -1 else text[line_start:line_end]
    return bool(_BARE_RU_BASIS_LINE.fullmatch(line) or re.search(_BASIS_CONTEXT, line, re.I))


def _basis_from_text(
    text: str,
) -> tuple[Literal["per_100_g", "per_100_ml", "per_serving", "ambiguous"], list[str]]:
    normalized = _normalize_basis_shape(text)
    matches = [
        match
        for match in _BASIS_PATTERN.finditer(normalized)
        if _basis_match_has_context(normalized, match)
    ]
    candidates: list[str] = []
    for match in matches:
        mass = next(
            (
                match.group(group_name)
                for group_name in ("ru_mass", "product_mass", "per_mass", "context_mass")
                if match.group(group_name) is not None
            ),
            None,
        )
        if mass is not None and mass.casefold() in {"г", "g"}:
            candidates.append("per_100_g")
        elif mass is not None and mass.casefold() in {"мл", "ml"}:
            candidates.append("per_100_ml")
        elif match.group("ru_serving") or match.group("per_serving"):
            candidates.append("per_serving")

    lines = [" ".join(line.split()) for line in normalized.splitlines() if line.strip()]
    has_context = any(re.search(_BASIS_CONTEXT, line, re.IGNORECASE) for line in lines)
    for line in lines:
        if has_context and _BARE_MASS_LINE.fullmatch(line):
            mass = re.search(r"100\s*(г|g|мл|ml)", line, re.IGNORECASE)
            if mass is not None:
                candidates.append(
                    "per_100_g" if mass.group(1).casefold() in {"г", "g"} else "per_100_ml"
                )

    unique = list(dict.fromkeys(candidates))
    if len(unique) == 1:
        return cast(Literal["per_100_g", "per_100_ml", "per_serving", "ambiguous"], unique[0]), []
    if len(unique) > 1:
        return "ambiguous", ["ambiguous_basis"]
    if _SERVING_SIZE_PATTERN.search(normalized) or _SERVINGS_PATTERN.search(normalized):
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


def _canonical_unit(raw: str | None) -> str | None:
    if raw is None or raw == "%":
        return raw
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
    return aliases.get(raw.casefold(), raw)


def _values_for_line(line: str, expected_unit: str) -> tuple[list[Decimal], bool, bool]:
    values: list[Decimal] = []
    had_percent = False
    had_unqualified = False
    for match in _VALUE_PATTERN.finditer(line):
        unit = _canonical_unit(match.group("unit"))
        if unit == "%":
            had_percent = True
            continue
        if unit is None:
            had_unqualified = True
            continue
        if unit != expected_unit:
            continue
        try:
            values.append(parse_decimal_token(match.group("number")))
        except CanonicalNormalizationError:
            continue
    return values, had_percent, had_unqualified


def _normalize_gram_glyph_shape(line: str) -> str:
    """Repair only the bounded OCR `8,0r` shape in gram-valued nutrient rows."""

    return _OCR_GRAM_GLYPH_PATTERN.sub(r"\g<number> г", line)


def _field_for_line(line: str) -> str | None:
    lowered = line.casefold()
    for field_name, patterns in _LABELS:
        if any(re.search(pattern, lowered, re.IGNORECASE) for pattern in patterns):
            return field_name
    return None


def _numeric_metadata(text: str):
    serving_size = None
    match = _SERVING_SIZE_PATTERN.search(text)
    if match:
        amount = parse_decimal_token(match.group("number"))
        if amount > 0:
            serving_size = {
                "amount": amount,
                "unit": "g" if match.group("unit") in {"г", "g"} else "ml",
            }
    servings = None
    match = _SERVINGS_PATTERN.search(text)
    if match:
        amount = parse_decimal_token(match.group("number"))
        if amount > 0:
            servings = amount
    package = None
    match = _PACKAGE_PATTERN.search(text)
    if match:
        amount = parse_decimal_token(match.group("number"))
        if amount > 0:
            package = {
                "amount": amount,
                "unit": "g" if match.group("unit") in {"г", "g"} else "ml",
            }
    return serving_size, servings, package


def _convert_value(value: Decimal, source_basis: str, serving_size: dict | None):
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


def _basis_ref(source_basis: str) -> Literal["per_100_g", "per_100_ml", "per_serving", "ambiguous"]:
    return cast(Literal["per_100_g", "per_100_ml", "per_serving", "ambiguous"], source_basis)


def _ambiguous_source_fact(field_name: str, source_basis: str, column_ref: str) -> SourceFact:
    return SourceFact(
        value=None,
        unit=_expected_unit(field_name),
        basis_ref=_basis_ref(source_basis),
        column_ref=column_ref,
        evidence="ambiguous",
    )


def _mark_ambiguous(
    field_name: str,
    *,
    source_basis: str,
    source_facts: dict[str, list[SourceFact] | None],
    normalized: dict[str, CanonicalFact | None],
    evidence: dict[str, str],
    column_ref: str,
    warnings: list[str],
    warning: str,
) -> None:
    source_facts[field_name] = [_ambiguous_source_fact(field_name, source_basis, column_ref)]
    normalized[field_name] = None
    evidence[field_name] = "ambiguous"
    if warning not in warnings:
        warnings.append(warning)


def _set_read_fact(
    field_name: str,
    value: Decimal,
    *,
    source_basis: str,
    serving_size: dict | None,
    source_facts: dict[str, list[SourceFact] | None],
    normalized: dict[str, CanonicalFact | None],
    evidence: dict[str, str],
    column_ref: str,
    warnings: list[str],
) -> None:
    source_facts[field_name] = [
        SourceFact(
            value=value,
            unit=_expected_unit(field_name),
            basis_ref=_basis_ref(source_basis),
            column_ref=column_ref,
            evidence="read",
        )
    ]
    evidence[field_name] = "read"
    if source_basis != "ambiguous":
        normalized_value, normalized_basis = _convert_value(value, source_basis, serving_size)
        if (
            source_basis == "per_serving"
            and serving_size is None
            and "serving_size_required_for_normalization" not in warnings
        ):
            warnings.append("serving_size_required_for_normalization")
        normalized[field_name] = CanonicalFact(
            value=normalized_value,
            unit=_expected_unit(field_name),
            basis_ref=cast(Literal["per_100_g", "per_100_ml", "per_serving"], normalized_basis),
        )
    else:
        normalized[field_name] = None


def _energy_values(line: str) -> tuple[dict[str, list[Decimal]], bool]:
    values: dict[str, list[Decimal]] = {"energy_kcal": [], "energy_kj": []}
    explicit_spans: list[tuple[int, int]] = []
    for match in _EXPLICIT_ENERGY_PATTERN.finditer(line):
        field_name = (
            "energy_kcal" if _canonical_unit(match.group("unit")) == "kcal" else "energy_kj"
        )
        try:
            values[field_name].append(parse_decimal_token(match.group("number")))
        except CanonicalNormalizationError:
            continue
        explicit_spans.append(match.span())
    had_unqualified = False
    for match in _VALUE_PATTERN.finditer(line):
        if match.group("unit") is not None:
            continue
        if any(start <= match.start() < end for start, end in explicit_spans):
            continue
        had_unqualified = True
    return values, had_unqualified


def _read_source_value(source_facts: dict[str, list[SourceFact] | None], field_name: str):
    cells = source_facts[field_name]
    if cells is None or len(cells) != 1 or cells[0].evidence != "read":
        return None
    return cells[0].value


def _apply_energy_safety(
    *,
    source_basis: str,
    source_facts: dict[str, list[SourceFact] | None],
    normalized: dict[str, CanonicalFact | None],
    evidence: dict[str, str],
    warnings: list[str],
) -> None:
    kj_value = _read_source_value(source_facts, "energy_kj")
    kcal_value = _read_source_value(source_facts, "energy_kcal")
    if kj_value is not None and kcal_value is not None:
        expected_kcal = kj_value / Decimal("4.184")
        tolerance = max(Decimal("5"), expected_kcal * Decimal("0.10"))
        if abs(expected_kcal - kcal_value) > tolerance:
            _mark_ambiguous(
                "energy_kj",
                source_basis=source_basis,
                source_facts=source_facts,
                normalized=normalized,
                evidence=evidence,
                column_ref="energy_pair_kj",
                warnings=warnings,
                warning="energy_unit_conflict",
            )
            _mark_ambiguous(
                "energy_kcal",
                source_basis=source_basis,
                source_facts=source_facts,
                normalized=normalized,
                evidence=evidence,
                column_ref="energy_pair_kcal",
                warnings=warnings,
                warning="energy_unit_conflict",
            )


def _apply_outlier_safety(
    *,
    source_basis: str,
    source_facts: dict[str, list[SourceFact] | None],
    normalized: dict[str, CanonicalFact | None],
    evidence: dict[str, str],
    warnings: list[str],
) -> None:
    if source_basis not in {"per_100_g", "per_100_ml"}:
        return
    for field_name in NUTRIENT_FIELDS:
        fact = normalized[field_name]
        if fact is None:
            continue
        limit = Decimal("100") if fact.unit == "g" else Decimal("100000")
        if field_name == "energy_kcal":
            limit = Decimal("1000")
        elif field_name == "energy_kj":
            limit = Decimal("10000")
        if fact.value > limit:
            _mark_ambiguous(
                field_name,
                source_basis=source_basis,
                source_facts=source_facts,
                normalized=normalized,
                evidence=evidence,
                column_ref=f"outlier_{field_name}",
                warnings=warnings,
                warning="energy_outlier"
                if field_name.startswith("energy_")
                else "nutrient_outlier",
            )


def _apply_macro_energy_consistency(
    *,
    source_basis: str,
    source_facts: dict[str, list[SourceFact] | None],
    normalized: dict[str, CanonicalFact | None],
    evidence: dict[str, str],
    warnings: list[str],
) -> None:
    if source_basis == "ambiguous":
        return
    energy = normalized["energy_kcal"]
    protein = normalized["protein_g"]
    fat = normalized["fat_g"]
    carbohydrate = normalized["carbohydrate_g"]
    if energy is None or protein is None or fat is None or carbohydrate is None:
        return
    implied = protein.value * Decimal(4) + fat.value * Decimal(9) + carbohydrate.value * Decimal(4)
    if abs(implied - energy.value) > max(Decimal("20"), energy.value * Decimal("0.2")):
        for field_name in _REQUIRED_FIELDS:
            _mark_ambiguous(
                field_name,
                source_basis=source_basis,
                source_facts=source_facts,
                normalized=normalized,
                evidence=evidence,
                column_ref=f"energy_macro_consistency_{field_name}",
                warnings=warnings,
                warning="energy_sanity_warning",
            )


def build_draft_from_ocr(
    ocr_text: str,
    *,
    structured_tokens: Sequence[OcrToken] | None = None,
    provider: str = "local_tesseract",
    model: str = "tesseract",
    prompt_version: str = "ocr-text-v1",
    policy_revision: str = CANONICAL_POLICY_REVISION,
) -> CanonicalDraft:
    """Parse explicit, unit-qualified label rows and fail closed on ambiguity."""

    if not isinstance(ocr_text, str) or len(ocr_text) > 50_000:
        raise CanonicalNormalizationError("ocr_text_too_large")
    if structured_tokens is not None and len(structured_tokens) > 4096:
        raise CanonicalNormalizationError("ocr_tokens_too_large")
    parsed_text = (
        structured_text_from_tokens(structured_tokens)
        if structured_tokens is not None
        else ocr_text
    )
    source_basis, warnings = _basis_from_text(parsed_text)
    serving_size, servings_per_container, package_amount = _numeric_metadata(parsed_text)
    source_facts: dict[str, list[SourceFact] | None] = dict.fromkeys(NUTRIENT_FIELDS)
    normalized: dict[str, CanonicalFact | None] = dict.fromkeys(NUTRIENT_FIELDS)
    evidence = _empty_field_evidence()
    daily_values: dict[str, Decimal | None] = {
        field_name: None for field_name in NUTRIENT_FIELDS if field_name != "energy_kj"
    }
    seen: set[str] = set()
    lines = [
        (line_number, " ".join(raw_line.split()))
        for line_number, raw_line in enumerate(parsed_text.splitlines(), start=1)
        if raw_line.strip()
    ]

    for line_number, line in lines:
        field_name = _field_for_line(line)
        if field_name in {"energy_kcal", "energy_kj"}:
            energy_values, had_unqualified = _energy_values(line)
            if had_unqualified:
                for energy_field in ("energy_kcal", "energy_kj"):
                    _mark_ambiguous(
                        energy_field,
                        source_basis=source_basis,
                        source_facts=source_facts,
                        normalized=normalized,
                        evidence=evidence,
                        column_ref=f"line_{line_number}_{energy_field}",
                        warnings=warnings,
                        warning="energy_unit_ambiguous",
                    )
                if "untrusted_numeric_token" not in warnings:
                    warnings.append("untrusted_numeric_token")
                continue
            for energy_field in ("energy_kcal", "energy_kj"):
                values = energy_values[energy_field]
                if not values:
                    continue
                if len(values) > 1 or energy_field in seen:
                    _mark_ambiguous(
                        energy_field,
                        source_basis=source_basis,
                        source_facts=source_facts,
                        normalized=normalized,
                        evidence=evidence,
                        column_ref=f"line_{line_number}_{energy_field}",
                        warnings=warnings,
                        warning="ambiguous_column",
                    )
                    continue
                seen.add(energy_field)
                _set_read_fact(
                    energy_field,
                    values[0],
                    source_basis=source_basis,
                    serving_size=serving_size,
                    source_facts=source_facts,
                    normalized=normalized,
                    evidence=evidence,
                    column_ref=f"line_{line_number}_{energy_field}",
                    warnings=warnings,
                )
            continue

        if field_name is None:
            continue
        if _expected_unit(field_name) == "g":
            line = _normalize_gram_glyph_shape(line)
        expected_unit = _expected_unit(field_name)
        values, had_percent, had_unqualified = _values_for_line(line, expected_unit)
        column_ref = f"line_{line_number}_{field_name}"
        if had_percent:
            _mark_ambiguous(
                field_name,
                source_basis=source_basis,
                source_facts=source_facts,
                normalized=normalized,
                evidence=evidence,
                column_ref=column_ref,
                warnings=warnings,
                warning="dv_as_mass",
            )
            continue
        if had_unqualified:
            _mark_ambiguous(
                field_name,
                source_basis=source_basis,
                source_facts=source_facts,
                normalized=normalized,
                evidence=evidence,
                column_ref=column_ref,
                warnings=warnings,
                warning="untrusted_numeric_token",
            )
            continue
        if not values:
            continue
        if len(values) > 1 or field_name in seen:
            _mark_ambiguous(
                field_name,
                source_basis=source_basis,
                source_facts=source_facts,
                normalized=normalized,
                evidence=evidence,
                column_ref=column_ref,
                warnings=warnings,
                warning="ambiguous_column",
            )
            continue
        seen.add(field_name)
        _set_read_fact(
            field_name,
            values[0],
            source_basis=source_basis,
            serving_size=serving_size,
            source_facts=source_facts,
            normalized=normalized,
            evidence=evidence,
            column_ref=column_ref,
            warnings=warnings,
        )

    _apply_outlier_safety(
        source_basis=source_basis,
        source_facts=source_facts,
        normalized=normalized,
        evidence=evidence,
        warnings=warnings,
    )
    _apply_energy_safety(
        source_basis=source_basis,
        source_facts=source_facts,
        normalized=normalized,
        evidence=evidence,
        warnings=warnings,
    )
    _apply_macro_energy_consistency(
        source_basis=source_basis,
        source_facts=source_facts,
        normalized=normalized,
        evidence=evidence,
        warnings=warnings,
    )
    if any(normalized[field_name] is None for field_name in _REQUIRED_FIELDS):
        warnings.append("missing_required_fact")
    warnings = list(dict.fromkeys(warnings))
    warnings.sort(
        key=lambda value: (_WARNING_ORDER.index(value) if value in _WARNING_ORDER else 99, value)
    )
    try:
        return CanonicalDraft(
            schema_version=CANONICAL_DRAFT_SCHEMA_VERSION,
            source_language=_source_language(parsed_text),
            label_format=_label_format(parsed_text),
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


def score_nutrition_candidate(
    canonical: CanonicalDraft,
    tokens: Sequence[OcrToken] = (),
) -> NutritionCandidateScore:
    """Rank fixed OCR candidates by nutrition evidence, never by text volume."""

    required_present = sum(
        getattr(canonical.normalized_facts, field_name) is not None
        for field_name in _REQUIRED_FIELDS
    )
    readable_count = sum(
        getattr(canonical.field_evidence, field_name) == "read" for field_name in NUTRIENT_FIELDS
    )
    explicit_units = sum(
        len(getattr(canonical.source_facts, field_name) or [])
        for field_name in NUTRIENT_FIELDS
        if getattr(canonical.field_evidence, field_name) == "read"
    )
    ambiguous_count = sum(
        getattr(canonical.field_evidence, field_name) == "ambiguous"
        for field_name in NUTRIENT_FIELDS
    )
    confidence = round(sum(token.confidence for token in tokens) / max(1, len(tokens)))
    catastrophic = sum(warning in _CATASTROPHIC_WARNINGS for warning in canonical.warnings)
    energy_pair = int(
        canonical.normalized_facts.energy_kcal is not None
        and canonical.normalized_facts.energy_kj is not None
    )
    reasons = (
        f"basis={'resolved' if canonical.source_basis != 'ambiguous' else 'ambiguous'}",
        f"required={required_present}/{len(_REQUIRED_FIELDS)}",
        f"read={readable_count}",
        f"energy_pair={energy_pair}",
        f"ambiguous={ambiguous_count}",
    )
    rank = (
        -catastrophic,
        int(canonical.source_basis != "ambiguous"),
        int(required_present == len(_REQUIRED_FIELDS)),
        required_present,
        energy_pair,
        readable_count,
        explicit_units,
        -ambiguous_count,
        confidence,
    )
    return NutritionCandidateScore(rank=rank, reasons=reasons)


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
        f"{field_name} {value} {NUTRIENT_UNITS[field_name]}"
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
