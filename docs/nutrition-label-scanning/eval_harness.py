"""Воспроизводимая локальная проверка structural/critical-инвариантов draft v1.

Скрипт не вызывает провайдеров и не является полным JSON Schema validator. Он
предназначен для bounded eval: проверяет сам документ схемы и несколько
детерминированных synthetic payloads, включая критические отрицательные случаи.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import re
from collections.abc import Sequence
from pathlib import Path
from typing import cast

SCRIPT_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = SCRIPT_DIR / "canonical_draft.schema.json"
SCHEMA_VERSION = "nutrition-label-draft-v1"

NUTRIENT_FIELDS = (
    "energy_kcal",
    "energy_kj",
    "protein_g",
    "fat_g",
    "saturated_fat_g",
    "trans_fat_g",
    "carbohydrate_g",
    "sugars_g",
    "added_sugars_g",
    "fiber_g",
    "salt_g",
    "sodium_mg",
    "cholesterol_mg",
)
FACT_UNITS = {"g", "mg", "kcal", "kJ"}
BASIS_VALUES = {"per_100_g", "per_100_ml", "per_serving", "ambiguous"}
EVIDENCE_VALUES = {"read", "ambiguous", "unreadable", "absent", "derived"}
WARNING_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


def _mapping(value: object, label: str, errors: list[str]) -> dict[str, object] | None:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        errors.append(f"{label} must be an object with string keys")
        return None
    return cast(dict[str, object], value)


def _exact_keys(
    value: dict[str, object], expected: set[str], label: str, errors: list[str]
) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        errors.append(f"{label} keys mismatch; missing={missing}, extra={extra}")


def _finite_number(
    value: object,
    label: str,
    errors: list[str],
    *,
    minimum: float | None = None,
    exclusive_minimum: bool = False,
) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"{label} must be a finite number")
        return
    numeric = float(value)
    if not math.isfinite(numeric):
        errors.append(f"{label} must be a finite number")
    if minimum is not None:
        below_minimum = numeric <= minimum if exclusive_minimum else numeric < minimum
        if below_minimum:
            operator = ">" if exclusive_minimum else ">="
            errors.append(f"{label} must be {operator} {minimum}")


def _fact(value: object, label: str, errors: list[str]) -> None:
    if value is None:
        return
    fact = _mapping(value, label, errors)
    if fact is None:
        return
    _exact_keys(fact, {"value", "unit", "basis_ref"}, label, errors)
    _finite_number(fact.get("value"), f"{label}.value", errors, minimum=0)
    unit = fact.get("unit")
    if not isinstance(unit, str) or unit not in FACT_UNITS:
        errors.append(f"{label}.unit is not a mass/energy unit")
    basis_ref = fact.get("basis_ref")
    if not isinstance(basis_ref, str) or basis_ref not in BASIS_VALUES - {"ambiguous"}:
        errors.append(f"{label}.basis_ref must identify a known basis")


def _derived_fact(value: object, label: str, errors: list[str]) -> None:
    if value is None:
        return
    fact = _mapping(value, label, errors)
    if fact is None:
        return
    _exact_keys(fact, {"value", "unit", "reason", "source_fields"}, label, errors)
    _finite_number(fact.get("value"), f"{label}.value", errors, minimum=0)
    unit = fact.get("unit")
    if not isinstance(unit, str) or unit not in FACT_UNITS:
        errors.append(f"{label}.unit is not a mass/energy unit")
    reason = fact.get("reason")
    if not isinstance(reason, str) or not reason:
        errors.append(f"{label}.reason must be non-empty")
    source_fields = fact.get("source_fields")
    if (
        not isinstance(source_fields, list)
        or not source_fields
        or not all(isinstance(field, str) and field for field in source_fields)
    ) or len(set(source_fields)) != len(source_fields):
        errors.append(f"{label}.source_fields must be a non-empty unique string list")


def _validate_field_map(
    draft: dict[str, object],
    name: str,
    validator: object,
    errors: list[str],
) -> dict[str, object] | None:
    value = _mapping(draft.get(name), name, errors)
    if value is None:
        return None
    _exact_keys(value, set(NUTRIENT_FIELDS), name, errors)
    if validator is _fact:
        for field in NUTRIENT_FIELDS:
            _fact(value.get(field), f"{name}.{field}", errors)
    else:
        for field in NUTRIENT_FIELDS:
            _derived_fact(value.get(field), f"{name}.{field}", errors)
    return value


def _validate_daily_values(draft: dict[str, object], errors: list[str]) -> dict[str, object] | None:
    value = _mapping(
        draft.get("displayed_daily_value_percent"), "displayed_daily_value_percent", errors
    )
    if value is None:
        return None
    _exact_keys(
        value, set(NUTRIENT_FIELDS) - {"energy_kj"}, "displayed_daily_value_percent", errors
    )
    for field, daily_value in value.items():
        if daily_value is not None:
            _finite_number(daily_value, f"displayed_daily_value_percent.{field}", errors, minimum=0)
            if (
                isinstance(daily_value, (int, float))
                and not isinstance(daily_value, bool)
                and daily_value > 1000
            ):
                errors.append(f"displayed_daily_value_percent.{field} must be <= 1000")
    return value


def _validate_evidence(draft: dict[str, object], errors: list[str]) -> dict[str, object] | None:
    value = _mapping(draft.get("field_evidence"), "field_evidence", errors)
    if value is None:
        return None
    _exact_keys(value, set(NUTRIENT_FIELDS), "field_evidence", errors)
    for field, evidence in value.items():
        if not isinstance(evidence, str) or evidence not in EVIDENCE_VALUES:
            errors.append(f"field_evidence.{field} has an unknown evidence state")
    return value


def _validate_confidence(draft: dict[str, object], errors: list[str]) -> dict[str, object] | None:
    value = _mapping(draft.get("confidence"), "confidence", errors)
    if value is None:
        return None
    _exact_keys(value, set(NUTRIENT_FIELDS), "confidence", errors)
    for field, confidence in value.items():
        if confidence is not None:
            _finite_number(confidence, f"confidence.{field}", errors, minimum=0)
            if (
                isinstance(confidence, (int, float))
                and not isinstance(confidence, bool)
                and confidence > 1
            ):
                errors.append(f"confidence.{field} must be <= 1")
    return value


def _validate_amount(value: object, label: str, errors: list[str]) -> None:
    if value is None:
        return
    amount = _mapping(value, label, errors)
    if amount is None:
        return
    _exact_keys(amount, {"amount", "unit"}, label, errors)
    _finite_number(
        amount.get("amount"), f"{label}.amount", errors, minimum=0, exclusive_minimum=True
    )
    unit = amount.get("unit")
    if not isinstance(unit, str) or unit not in {"g", "ml"}:
        errors.append(f"{label}.unit must be g or ml")


def _validate_schema_document(schema: dict[str, object]) -> list[str]:
    errors: list[str] = []
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        errors.append("schema top level must be a closed object")
    if schema.get("title") != "YFC nutrition label draft v1":
        errors.append("schema title is unexpected")
    required = schema.get("required")
    if not isinstance(required, list) or set(required) != {
        "schema_version",
        "source_language",
        "label_format",
        "source_basis",
        "serving_size",
        "servings_per_container",
        "package_amount",
        "source_facts",
        "normalized_facts",
        "derived_fields",
        "displayed_daily_value_percent",
        "field_evidence",
        "confidence_kind",
        "confidence",
        "warnings",
        "requires_user_review",
        "metadata",
    }:
        errors.append("schema required set is unexpected")
    definitions = _mapping(schema.get("$defs"), "$defs", errors)
    if definitions is None:
        return errors
    facts = _mapping(definitions.get("facts"), "$defs.facts", errors)
    if facts is None or facts.get("additionalProperties") is not False:
        errors.append("$defs.facts must be closed")
    fact_properties = _mapping(
        facts.get("properties") if facts else None, "$defs.facts.properties", errors
    )
    if fact_properties is None or set(fact_properties) != set(NUTRIENT_FIELDS):
        errors.append("$defs.facts properties must match the fixed nutrient vocabulary")
    fact_definition = _mapping(definitions.get("fact"), "$defs.fact", errors)
    if fact_definition is None:
        return errors
    fact_any_of = fact_definition.get("anyOf")
    if not isinstance(fact_any_of, list) or len(fact_any_of) != 2:
        errors.append("$defs.fact must allow null and one structured fact")
    return errors


def validate_draft(draft: object, schema: dict[str, object]) -> list[str]:
    errors = _validate_schema_document(schema)
    value = _mapping(draft, "draft", errors)
    if value is None:
        return errors

    expected_top_level = {
        "schema_version",
        "source_language",
        "label_format",
        "source_basis",
        "serving_size",
        "servings_per_container",
        "package_amount",
        "source_facts",
        "normalized_facts",
        "derived_fields",
        "displayed_daily_value_percent",
        "field_evidence",
        "confidence_kind",
        "confidence",
        "warnings",
        "requires_user_review",
        "metadata",
    }
    _exact_keys(value, expected_top_level, "draft", errors)
    if value.get("schema_version") != SCHEMA_VERSION:
        errors.append("draft.schema_version is unexpected")
    source_language = value.get("source_language")
    if not isinstance(source_language, str) or source_language not in {
        "ru",
        "en",
        "mixed",
        "unknown",
    }:
        errors.append("draft.source_language is unexpected")
    label_format = value.get("label_format")
    if not isinstance(label_format, str) or label_format not in {
        "ru_standard",
        "eu_uk",
        "us_nutrition_facts",
        "unknown",
    }:
        errors.append("draft.label_format is unexpected")
    source_basis = value.get("source_basis")
    if not isinstance(source_basis, str) or source_basis not in BASIS_VALUES:
        errors.append("draft.source_basis is unexpected")

    _validate_amount(value.get("serving_size"), "serving_size", errors)
    servings = value.get("servings_per_container")
    if servings is not None:
        _finite_number(
            servings, "servings_per_container", errors, minimum=0, exclusive_minimum=True
        )
    _validate_amount(value.get("package_amount"), "package_amount", errors)

    source_facts = _validate_field_map(value, "source_facts", _fact, errors)
    normalized_facts = _validate_field_map(value, "normalized_facts", _fact, errors)
    derived_fields = _validate_field_map(value, "derived_fields", _derived_fact, errors)
    daily_values = _validate_daily_values(value, errors)
    evidence = _validate_evidence(value, errors)
    confidence = _validate_confidence(value, errors)

    confidence_kind = value.get("confidence_kind")
    if not isinstance(confidence_kind, str) or confidence_kind not in {
        "provider_native",
        "calibrated_eval",
        "none",
    }:
        errors.append("draft.confidence_kind is unexpected")
    elif (
        confidence_kind == "none"
        and confidence is not None
        and any(item is not None for item in confidence.values())
    ):
        errors.append("confidence_kind=none cannot carry numeric confidence")

    warnings = value.get("warnings")
    if (
        not isinstance(warnings, list)
        or len(warnings) > 32
        or not all(isinstance(item, str) and WARNING_PATTERN.fullmatch(item) for item in warnings)
    ) or len(set(warnings)) != len(warnings):
        errors.append("warnings must be unique bounded snake_case strings")
    if value.get("requires_user_review") is not True:
        errors.append("requires_user_review must remain true")

    metadata = _mapping(value.get("metadata"), "metadata", errors)
    if metadata is not None:
        _exact_keys(
            metadata,
            {"provider", "model", "prompt_version", "schema_version", "policy_revision"},
            "metadata",
            errors,
        )
        for field in ("provider", "model", "prompt_version", "policy_revision"):
            if not isinstance(metadata.get(field), str) or not metadata.get(field):
                errors.append(f"metadata.{field} must be non-empty")
        if metadata.get("schema_version") != SCHEMA_VERSION:
            errors.append("metadata.schema_version is unexpected")

    if evidence is not None:
        for field in NUTRIENT_FIELDS:
            state = evidence.get(field)
            if isinstance(state, str) and state in {"absent", "ambiguous", "unreadable"}:
                if any(
                    facts is not None and facts.get(field) is not None
                    for facts in (source_facts, normalized_facts, derived_fields)
                ):
                    errors.append(f"{field} with evidence={state} must remain null")
                if confidence is not None and confidence.get(field) is not None:
                    errors.append(f"{field} with evidence={state} cannot have confidence")
            if state == "derived" and (derived_fields is None or derived_fields.get(field) is None):
                errors.append(f"{field} with evidence=derived needs a derived field")

    # Daily values are deliberately a separate map and never a fact with a mass unit.
    if daily_values is not None and "energy_kj" in daily_values:
        errors.append("displayed_daily_value_percent must not contain energy_kj")
    return errors


def _synthetic_valid_draft() -> dict[str, object]:
    source: dict[str, object] = dict.fromkeys(NUTRIENT_FIELDS)
    normalized: dict[str, object] = dict.fromkeys(NUTRIENT_FIELDS)
    derived: dict[str, object] = dict.fromkeys(NUTRIENT_FIELDS)
    evidence: dict[str, object] = dict.fromkeys(NUTRIENT_FIELDS, "absent")
    confidence: dict[str, object] = dict.fromkeys(NUTRIENT_FIELDS)
    daily_values: dict[str, object] = {
        field: None for field in NUTRIENT_FIELDS if field != "energy_kj"
    }
    values = {
        "energy_kcal": (450.0, "kcal"),
        "energy_kj": (1880.0, "kJ"),
        "protein_g": (10.0, "g"),
        "fat_g": (20.0, "g"),
        "saturated_fat_g": (8.0, "g"),
        "carbohydrate_g": (50.0, "g"),
        "sugars_g": (25.0, "g"),
        "fiber_g": (3.0, "g"),
        "salt_g": (1.5, "g"),
        "sodium_mg": (600.0, "mg"),
    }
    for field, (numeric_value, unit) in values.items():
        fact = {"value": numeric_value, "unit": unit, "basis_ref": "per_100_g"}
        source[field] = fact
        normalized[field] = copy.deepcopy(fact)
        evidence[field] = "read"
        confidence[field] = 0.99
    daily_values["energy_kcal"] = 5.0
    daily_values["sodium_mg"] = 4.0
    return {
        "schema_version": SCHEMA_VERSION,
        "source_language": "ru",
        "label_format": "ru_standard",
        "source_basis": "per_100_g",
        "serving_size": {"amount": 30.0, "unit": "g"},
        "servings_per_container": 10.0,
        "package_amount": {"amount": 300.0, "unit": "g"},
        "source_facts": source,
        "normalized_facts": normalized,
        "derived_fields": derived,
        "displayed_daily_value_percent": daily_values,
        "field_evidence": evidence,
        "confidence_kind": "calibrated_eval",
        "confidence": confidence,
        "warnings": ["user_review_required"],
        "requires_user_review": True,
        "metadata": {
            "provider": "synthetic",
            "model": "fixture",
            "prompt_version": "eval-v1",
            "schema_version": SCHEMA_VERSION,
            "policy_revision": "2026-09-12",
        },
    }


def _expect_valid(label: str, draft: object, schema: dict[str, object]) -> None:
    errors = validate_draft(draft, schema)
    if errors:
        raise AssertionError(f"{label} unexpectedly rejected: {errors}")


def _expect_rejected(label: str, draft: object, schema: dict[str, object]) -> None:
    errors = validate_draft(draft, schema)
    if not errors:
        raise AssertionError(f"{label} unexpectedly accepted")


def run_self_check(schema: dict[str, object]) -> None:
    valid = _synthetic_valid_draft()
    _expect_valid("synthetic valid RU per-100-g draft", valid, schema)

    extra_key = copy.deepcopy(valid)
    extra_key["unexpected"] = "reject"
    _expect_rejected("unknown top-level key", extra_key, schema)

    review_bypass = copy.deepcopy(valid)
    review_bypass["requires_user_review"] = False
    _expect_rejected("review bypass", review_bypass, schema)

    percent_as_mass = copy.deepcopy(valid)
    percent_facts = cast(dict[str, object], percent_as_mass["source_facts"])
    sodium = cast(dict[str, object], percent_facts["sodium_mg"])
    sodium["unit"] = "%DV"
    _expect_rejected("percent daily value presented as mass", percent_as_mass, schema)

    unreadable_with_value = copy.deepcopy(valid)
    unreadable_facts = cast(dict[str, object], unreadable_with_value["source_facts"])
    unreadable_facts["fiber_g"] = {"value": 3.0, "unit": "g", "basis_ref": "per_100_g"}
    unreadable_evidence = cast(dict[str, object], unreadable_with_value["field_evidence"])
    unreadable_evidence["fiber_g"] = "unreadable"
    _expect_rejected("unreadable field hallucinated as a value", unreadable_with_value, schema)

    ambiguous_basis = copy.deepcopy(valid)
    ambiguous_facts = cast(dict[str, object], ambiguous_basis["source_facts"])
    ambiguous_protein = cast(dict[str, object], ambiguous_facts["protein_g"])
    ambiguous_protein["basis_ref"] = "ambiguous"
    _expect_rejected("ambiguous fact basis", ambiguous_basis, schema)

    confidence_without_semantics = copy.deepcopy(valid)
    confidence_without_semantics["confidence_kind"] = "none"
    _expect_rejected("undocumented numeric confidence", confidence_without_semantics, schema)

    zero_serving = copy.deepcopy(valid)
    serving = cast(dict[str, object], zero_serving["serving_size"])
    serving["amount"] = 0
    _expect_rejected("zero serving amount", zero_serving, schema)

    unhashable_warning = copy.deepcopy(valid)
    unhashable_warning["warnings"] = [["nested"]]
    _expect_rejected("malformed warning payload", unhashable_warning, schema)


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-check", action="store_true", help="run deterministic synthetic checks"
    )
    parser.add_argument("--input", type=Path, help="validate one provider-neutral draft JSON")
    args = parser.parse_args(argv)
    if args.self_check == (args.input is not None):
        parser.error("specify exactly one of --self-check or --input")

    try:
        schema = _load_json(SCHEMA_PATH)
        draft = _load_json(args.input) if args.input is not None else None
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: cannot load JSON input: {exc}")
        return 1
    if not isinstance(schema, dict):
        print("FAIL: schema root must be an object")
        return 1
    typed_schema = cast(dict[str, object], schema)

    try:
        if args.self_check:
            run_self_check(typed_schema)
            print(
                "PASS: contract structural/critical invariants (stdlib self-check; synthetic only)"
            )
            return 0
        errors = validate_draft(draft, typed_schema)
    except AssertionError as exc:
        print(f"FAIL: {exc}")
        return 1
    if errors:
        print("FAIL: draft rejected")
        for error in errors:
            print(f"- {error}")
        return 1
    print("PASS: draft structural/critical invariants")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
