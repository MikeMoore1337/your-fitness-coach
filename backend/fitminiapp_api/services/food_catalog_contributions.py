from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Literal

from sqlalchemy.orm import Session

from fitminiapp_api.models.food import Food, normalize_food_catalog_identity
from fitminiapp_api.models.nutrition_label import NutritionCatalogContribution
from fitminiapp_api.models.user import User
from fitminiapp_api.nutrition_label.contracts import (
    CANONICAL_DRAFT_SCHEMA_VERSION,
    CanonicalDraft,
    CanonicalFact,
    DailyValuePercent,
    DerivedNutrientFacts,
    DraftMetadata,
    FieldConfidence,
    FieldEvidence,
    NutrientFacts,
    ServingSize,
    SourceNutrientFacts,
    validate_canonical_draft,
)
from fitminiapp_api.schemas.food import UserFoodCreate

MANUAL_FOOD_SOURCE_VERSION = "nutrition-manual-v1"
CatalogContributionState = Literal["accepted", "duplicate", "conflict"]


def _remember_catalog_identity(food: Food, identity: str) -> Food:
    if (
        food.food_type == "branded"
        and food.source_name == "yfc_community"
        and food.catalog_identity is None
    ):
        food.catalog_identity = identity
    return food


def build_manual_canonical(payload: UserFoodCreate) -> CanonicalDraft:
    basis = payload.nutrition_basis_kind
    serving_size = None
    if basis == "per_serving":
        if payload.standard_serving_unit == "g" and payload.standard_serving_weight_g:
            serving_size = ServingSize(
                amount=payload.standard_serving_weight_g,
                unit="g",
            )
        elif payload.standard_serving_unit == "ml" and payload.standard_serving_amount:
            serving_size = ServingSize(
                amount=payload.standard_serving_amount,
                unit="ml",
            )

    normalized = NutrientFacts(
        energy_kcal=CanonicalFact(
            value=payload.energy_kcal_per_100g,
            unit="kcal",
            basis_ref=basis,
        ),
        protein_g=CanonicalFact(
            value=payload.protein_g_per_100g,
            unit="g",
            basis_ref=basis,
        ),
        fat_g=CanonicalFact(
            value=payload.fat_g_per_100g,
            unit="g",
            basis_ref=basis,
        ),
        carbohydrate_g=CanonicalFact(
            value=payload.carbs_g_per_100g,
            unit="g",
            basis_ref=basis,
        ),
        fiber_g=(
            CanonicalFact(value=payload.fiber_g_per_100g, unit="g", basis_ref=basis)
            if payload.fiber_g_per_100g is not None
            else None
        ),
    )
    return CanonicalDraft(
        schema_version=CANONICAL_DRAFT_SCHEMA_VERSION,
        source_language="unknown",
        label_format="unknown",
        source_basis=basis,
        serving_size=serving_size,
        source_facts=SourceNutrientFacts(),
        normalized_facts=normalized,
        derived_fields=DerivedNutrientFacts(),
        displayed_daily_value_percent=DailyValuePercent(),
        field_evidence=FieldEvidence(),
        confidence_kind="none",
        confidence=FieldConfidence(),
        warnings=[],
        requires_user_review=True,
        metadata=DraftMetadata(
            provider="manual",
            model="manual",
            prompt_version="manual",
            schema_version=CANONICAL_DRAFT_SCHEMA_VERSION,
            policy_revision="manual",
        ),
    )


def manual_food_values(payload: UserFoodCreate) -> tuple[dict[str, object], CanonicalDraft]:
    canonical = build_manual_canonical(payload)
    values = payload.model_dump(
        exclude={
            "external_source",
            "classification",
            "nutrition_basis_kind",
            "nutrition_basis_amount",
            "nutrition_basis_unit",
        }
    )
    values.update(
        {
            "nutrition_basis_kind": payload.nutrition_basis_kind,
            "nutrition_basis_amount": payload.nutrition_basis_amount,
            "nutrition_basis_unit": payload.nutrition_basis_unit,
            "canonical_facts": canonical.model_dump(mode="json"),
            "canonical_complete": True,
        }
    )
    if payload.nutrition_basis_kind != "per_100_g":
        for field_name in (
            "energy_kcal_per_100g",
            "protein_g_per_100g",
            "fat_g_per_100g",
            "carbs_g_per_100g",
            "fiber_g_per_100g",
        ):
            values[field_name] = None
    return values, canonical


def catalog_identity_for_payload(
    *,
    name: str,
    brand: str | None,
    canonical: CanonicalDraft,
) -> str:
    return normalize_food_catalog_identity(
        name,
        brand,
        canonical.source_basis,
        Decimal("100") if canonical.source_basis != "per_serving" else Decimal("1"),
        {"per_100_g": "g", "per_100_ml": "ml", "per_serving": "serving"}[canonical.source_basis],
    )


def catalog_payload(
    *,
    name: str,
    brand: str | None,
    barcode: str | None,
    canonical: CanonicalDraft,
) -> dict[str, object]:
    return {
        "product": {"name": name, "brand": brand, "barcode": barcode},
        "nutrition": canonical.model_dump(mode="json"),
    }


def payload_digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def find_shared_food(
    db: Session,
    *,
    name: str,
    brand: str | None,
    barcode: str | None,
    canonical: CanonicalDraft,
) -> Food | None:
    query = db.query(Food).filter(Food.status == "active", Food.food_type != "user")
    identity = catalog_identity_for_payload(name=name, brand=brand, canonical=canonical)
    if barcode is not None:
        existing_by_barcode = query.filter(Food.barcode == barcode).with_for_update().first()
        if existing_by_barcode is not None:
            return _remember_catalog_identity(existing_by_barcode, identity)

        # A product first confirmed without a barcode can be upgraded when the
        # author later supplies a valid GTIN, but a different existing GTIN is
        # never silently merged into it.
        existing_without_barcode = (
            query.filter(
                Food.barcode.is_(None),
                Food.catalog_identity == identity,
            )
            .with_for_update()
            .first()
        )
        if existing_without_barcode is not None:
            return _remember_catalog_identity(existing_without_barcode, identity)

    existing = query.filter(Food.catalog_identity == identity).with_for_update().first()
    if existing is not None:
        return _remember_catalog_identity(existing, identity)

    # Older community rows predate catalog_identity. Match only their exact
    # normalized name/brand/basis, never a fuzzy candidate.
    candidates = (
        query.filter(
            Food.barcode.is_(None),
            Food.food_type == "branded",
            Food.source_name == "yfc_community",
            Food.catalog_identity.is_(None),
        )
        .with_for_update()
        .all()
    )
    for candidate in candidates:
        candidate_identity = normalize_food_catalog_identity(
            candidate.name,
            candidate.brand,
            candidate.nutrition_basis_kind or "per_100_g",
            candidate.nutrition_basis_amount or Decimal("100"),
            candidate.nutrition_basis_unit or "g",
        )
        if candidate_identity == identity:
            return _remember_catalog_identity(candidate, identity)
    return None


def canonical_facts_match(food: Food, canonical: CanonicalDraft) -> bool:
    if food.canonical_facts:
        try:
            stored = validate_canonical_draft(food.canonical_facts)
        except ValueError:
            return False
        return stored.source_basis == canonical.source_basis and stored.normalized_facts.model_dump(
            mode="json"
        ) == canonical.normalized_facts.model_dump(mode="json")

    if (food.nutrition_basis_kind or "per_100_g") != canonical.source_basis:
        return False
    legacy_values = {
        "energy_kcal": food.energy_kcal_per_100g,
        "protein_g": food.protein_g_per_100g,
        "fat_g": food.fat_g_per_100g,
        "carbohydrate_g": food.carbs_g_per_100g,
        "fiber_g": food.fiber_g_per_100g,
    }
    for field_name, value in legacy_values.items():
        expected = getattr(canonical.normalized_facts, field_name)
        if expected is not None and value != expected.value:
            return False
    return True


def contribution_for_digest(
    db: Session,
    *,
    food_id: int,
    digest: str,
) -> NutritionCatalogContribution | None:
    return (
        db.query(NutritionCatalogContribution)
        .filter(
            NutritionCatalogContribution.food_id == food_id,
            NutritionCatalogContribution.payload_digest == digest,
        )
        .first()
    )


def add_catalog_contribution(
    db: Session,
    *,
    food: Food,
    user: User,
    canonical_payload: dict[str, object],
    digest: str,
    state: CatalogContributionState,
    source_version: str,
) -> NutritionCatalogContribution:
    contribution = NutritionCatalogContribution(
        food_id=food.id,
        contributor_user_id=user.id,
        visibility="share_to_yfc_catalog",
        state=state,
        payload_digest=digest,
        canonical_payload=canonical_payload,
        source_version=source_version,
    )
    db.add(contribution)
    return contribution
