"""Provider-neutral preparation of an imported product for the shared catalogue."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from fitminiapp_api.models.food import (
    Food,
    normalize_food_catalog_identity,
    normalize_food_search_text,
)
from fitminiapp_api.models.nutrition_import import NutritionImportDraft
from fitminiapp_api.models.nutrition_label import (
    NutritionCatalogContribution,
    NutritionCatalogIdentifier,
)
from fitminiapp_api.models.user import User
from fitminiapp_api.nutrition_label.contracts import (
    CANONICAL_DRAFT_SCHEMA_VERSION,
    NUTRIENT_FIELDS,
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
)
from fitminiapp_api.schemas.food import FoodValuesInput, UserFoodCreate
from fitminiapp_api.schemas.nutrition_import import ImportFoodRow, ImportSource
from fitminiapp_api.services.audit import record_audit_event
from fitminiapp_api.services.food_catalog_contributions import (
    add_catalog_contribution,
    payload_digest,
)
from fitminiapp_api.services.nutrition_import_drafts import (
    _KEY,
    NutritionDraftError,
    _lock_user,
    get_nutrition_import_draft,
)
from fitminiapp_api.services.nutrition_import_runner import ADAPTERS, NutritionImportAdapter
from fitminiapp_api.services.nutrition_label import _food_serving_projection, _legacy_projection


@dataclass(frozen=True)
class PreparedCatalogFood:
    name: str
    brand: str | None
    barcode: str | None
    kind: str
    identity: str
    canonical: CanonicalDraft
    adapter_version: str
    provenance: dict[str, object]


@dataclass(frozen=True)
class CatalogPreparation:
    outcome: str
    reason: str | None = None
    food: PreparedCatalogFood | None = None


_UNSAFE_TEXT = re.compile(
    r"(?:https?://|www\.|\S+@\S+|[\x00-\x1f\x7f]|\b\d{4}[-./]\d{1,2}[-./]\d{1,2}\b"
    r"|\b\d{1,2}[-./]\d{1,2}[-./]\d{4}\b|\b[a-z0-9-]+\.[a-z]{2,}(?:/|\b)"
    r"|[?&](?:token|key|secret)=|/(?:export|private)/)",
    re.IGNORECASE,
)
_SOURCE_UNITS = {
    "g": {"g", "г", "гр", "gram", "grams"},
    "mg": {"mg", "мг"},
    "kcal": {"kcal", "ккал"},
    "kJ": {"kj", "кдж"},
}


def prepare_catalog_food(
    row: ImportFoodRow,
    source: ImportSource,
    *,
    allowed_publication_rights: frozenset[str],
    allowed_food_kinds: frozenset[str] = frozenset(),
    attribution: str | None = None,
) -> CatalogPreparation:
    """Validate the product without writing or copying private diary fields."""
    if row.food.kind in {"personal_recipe", "arbitrary"}:
        return CatalogPreparation("private_only", "personal_or_arbitrary_food")
    if row.food.kind not in {"standard_food", "branded_food"}:
        return CatalogPreparation("needs_review", "unclassified_food")
    if source.publication_rights == "prohibited":
        return CatalogPreparation("private_only", "publication_prohibited")
    if source.publication_rights not in allowed_publication_rights:
        return CatalogPreparation("needs_review", "publication_rights_unconfirmed")
    if row.food.kind not in allowed_food_kinds:
        return CatalogPreparation("needs_review", "classification_unconfirmed")
    if attribution is not None and (len(attribution) > 256 or _UNSAFE_TEXT.search(attribution)):
        return CatalogPreparation("needs_review", "attribution_not_public")
    if any(diagnostic.severity == "error" for diagnostic in row.diagnostics):
        return CatalogPreparation("needs_review", "invalid_source_row")
    if row.food.kind == "branded_food" and not row.food.brand:
        return CatalogPreparation("needs_review", "brand_required")
    if row.food.kind == "standard_food" and row.food.brand:
        return CatalogPreparation("needs_review", "inconsistent_classification")
    if any(
        _UNSAFE_TEXT.search(value)
        for value in (row.food.name, row.food.brand, row.food.variant)
        if value
    ):
        return CatalogPreparation("needs_review", "unsafe_product_text")

    basis = row.nutrition.basis
    if basis is None:
        return CatalogPreparation("needs_review", "nutrition_basis_unknown")
    if basis == "per_serving" and row.serving_measure is None:
        return CatalogPreparation("needs_review", "serving_measure_unknown")
    required = ("energy_kcal", "protein_g", "fat_g", "carbohydrate_g")
    facts = row.nutrition.facts
    required_values: dict[str, Decimal] = {}
    for key in required:
        fact = getattr(facts, key)
        if fact is None or fact.value is None:
            return CatalogPreparation("needs_review", "incomplete_nutrition")
        required_values[key] = fact.value
    if any(
        fact is not None and fact.value is not None and fact.evidence != "read"
        for fact in facts.__dict__.values()
    ):
        return CatalogPreparation("needs_review", "derived_nutrition_requires_review")
    if any(
        fact is not None
        and fact.source_unit is not None
        and fact.source_unit.casefold() not in _SOURCE_UNITS.get(fact.unit, set())
        for fact in facts.__dict__.values()
    ):
        return CatalogPreparation("needs_review", "source_unit_unrecognized")

    name = " ".join(row.food.name.split())
    variant = " ".join(row.food.variant.split()) if row.food.variant else None
    display_name = f"{name} — {variant}" if variant else name
    amount, unit = (
        (Decimal("1"), "serving")
        if basis == "per_serving"
        else (Decimal("100"), "g" if basis == "per_100_g" else "ml")
    )
    try:
        validated = FoodValuesInput(name=display_name, brand=row.food.brand, barcode=row.food.gtin)
        if basis == "per_100_g":
            UserFoodCreate(
                name=display_name,
                brand=row.food.brand,
                barcode=row.food.gtin,
                energy_kcal_per_100g=required_values["energy_kcal"],
                protein_g_per_100g=required_values["protein_g"],
                fat_g_per_100g=required_values["fat_g"],
                carbs_g_per_100g=required_values["carbohydrate_g"],
                fiber_g_per_100g=facts.fiber_g.value if facts.fiber_g else None,
            )
    except ValidationError:
        return CatalogPreparation("needs_review", "nutrition_or_identity_invalid")
    mass = (
        Decimal("100")
        if basis == "per_100_g"
        else row.serving_measure.amount
        if basis == "per_serving" and row.serving_measure and row.serving_measure.unit == "g"
        else None
    )
    if mass is not None and (
        sum(required_values[key] for key in ("protein_g", "fat_g", "carbohydrate_g")) > mass
        or required_values["energy_kcal"] > mass * 10
    ):
        return CatalogPreparation("needs_review", "inconsistent_nutrition")
    if row.serving_measure and (
        row.serving_measure.amount != row.serving_measure.amount.quantize(Decimal("0.001"))
        or row.serving_measure.amount > Decimal("9999999.999")
    ):
        return CatalogPreparation("needs_review", "serving_precision_unsupported")

    normalized: dict[str, CanonicalFact] = {}
    evidence: dict[str, str] = {}
    fact_provenance: dict[str, object] = {}
    for key in NUTRIENT_FIELDS:
        fact = getattr(facts, key)
        if fact is not None:
            evidence[key] = fact.evidence
            if fact.value is not None:
                normalized[key] = CanonicalFact(value=fact.value, unit=fact.unit, basis_ref=basis)
            fact_provenance[key] = {
                "evidence": fact.evidence,
                "unit": fact.unit,
                "source_unit": fact.source_unit,
            }
    if facts.potassium_mg is not None:
        potassium = facts.potassium_mg
        fact_provenance["potassium_mg"] = {
            "value": format(potassium.value, "f") if potassium.value is not None else None,
            "unit": potassium.unit,
            "source_unit": potassium.source_unit,
            "evidence": potassium.evidence,
        }

    canonical = CanonicalDraft(
        schema_version=CANONICAL_DRAFT_SCHEMA_VERSION,
        source_language="unknown",
        label_format="unknown",
        source_basis=basis,
        serving_size=(
            ServingSize(amount=row.serving_measure.amount, unit=row.serving_measure.unit)
            if row.serving_measure
            else None
        ),
        source_facts=SourceNutrientFacts(),
        normalized_facts=NutrientFacts(**normalized),
        derived_fields=DerivedNutrientFacts(),
        displayed_daily_value_percent=DailyValuePercent(),
        field_evidence=FieldEvidence.model_validate(evidence),
        confidence_kind="none",
        confidence=FieldConfidence(),
        metadata=DraftMetadata(
            provider=source.provider,
            model="not_applicable",
            prompt_version="not_applicable",
            schema_version=CANONICAL_DRAFT_SCHEMA_VERSION,
            policy_revision="nutrition-import-catalog-v1",
        ),
    )
    identity = normalize_food_catalog_identity(name, validated.brand, basis, amount, unit)
    if variant:
        parts = json.loads(identity)
        parts.append(" ".join(variant.split()).casefold().replace("ё", "е"))
        identity = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    if len(identity) > 512:
        return CatalogPreparation("needs_review", "identity_too_long")
    provenance: dict[str, object] = {
        "provider": source.provider,
        "source": source.source,
        "source_version": source.source_version,
        "adapter_version": source.adapter_version,
        "publication_rights": source.publication_rights,
        "attribution": attribution,
        "classification": row.food.kind,
        "trust": "community_unverified",
        "basis": basis,
        "facts": fact_provenance,
    }
    return CatalogPreparation(
        "publish",
        food=PreparedCatalogFood(
            name=validated.name,
            brand=validated.brand,
            barcode=validated.barcode,
            kind=row.food.kind,
            identity=identity,
            canonical=canonical,
            adapter_version=source.adapter_version,
            provenance=provenance,
        ),
    )


def _key(parts: object) -> str:
    data = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _adapter(draft: NutritionImportDraft, source: ImportSource) -> NutritionImportAdapter | None:
    adapter = ADAPTERS.get(draft.adapter_id) if draft.adapter_id else None
    if (
        adapter is not None
        and adapter.provider == source.provider
        and adapter.adapter_version == source.adapter_version
        and adapter.parser_version == draft.parser_version
        and adapter.catalog_source == source.source
        and source.source_version in adapter.catalog_source_versions
    ):
        return adapter
    return None


def _source_key(
    row: ImportFoodRow, source: ImportSource, adapter: NutritionImportAdapter | None
) -> str | None:
    if (
        adapter is None
        or row.food.identity_source not in adapter.catalog_identity_sources
        or row.food.source_id is None
    ):
        return None
    return _key([source.provider, source.source, row.food.identity_source, row.food.source_id])


def _stored_identity(food: Food) -> str:
    return food.catalog_identity or normalize_food_catalog_identity(
        food.name,
        food.brand,
        food.nutrition_basis_kind or "per_100_g",
        food.nutrition_basis_amount or Decimal("100"),
        food.nutrition_basis_unit or "g",
    )


def _food_snapshot(food: Food) -> str:
    return _key(
        [
            food.id,
            food.status,
            food.name,
            food.brand,
            food.barcode,
            food.catalog_identity,
            food.nutrition_basis_kind,
            str(food.nutrition_basis_amount),
            food.nutrition_basis_unit,
            food.canonical_facts,
            str(food.energy_kcal_per_100g),
            str(food.protein_g_per_100g),
            str(food.fat_g_per_100g),
            str(food.carbs_g_per_100g),
            str(food.fiber_g_per_100g),
            str(food.standard_serving_amount),
            food.standard_serving_unit,
            str(food.standard_serving_weight_g),
            food.food_type,
            food.trust_level,
            food.catalog_quality,
            food.canonical_complete,
            food.nutrition_provenance,
        ]
    )


def _facts_match(food: Food, proposed: PreparedCatalogFood) -> bool:
    if food.canonical_facts:
        try:
            current = CanonicalDraft.model_validate(food.canonical_facts)
        except ValidationError:
            return False
        if current.source_basis != proposed.canonical.source_basis:
            return False
        if current.source_basis == "per_serving" and (
            current.serving_size is None or current.serving_size != proposed.canonical.serving_size
        ):
            return False
        required = {"energy_kcal", "protein_g", "fat_g", "carbohydrate_g"}
        for name in NUTRIENT_FIELDS:
            previous = getattr(current.normalized_facts, name)
            new = getattr(proposed.canonical.normalized_facts, name)
            if previous is None or previous.basis_ref != current.source_basis:
                source_facts = getattr(current.source_facts, name) or []
                previous = next(
                    (
                        fact
                        for fact in source_facts
                        if fact.evidence == "read" and fact.basis_ref == current.source_basis
                    ),
                    None,
                )
            if name in required and previous is None:
                return False
            if (
                previous is not None
                and new is not None
                and (previous.value != new.value or previous.unit != new.unit)
            ):
                return False
        return True
    if (food.nutrition_basis_kind or "per_100_g") != proposed.canonical.source_basis:
        return False
    if proposed.canonical.source_basis != "per_100_g":
        return False
    values = {
        "energy_kcal": food.energy_kcal_per_100g,
        "protein_g": food.protein_g_per_100g,
        "fat_g": food.fat_g_per_100g,
        "carbohydrate_g": food.carbs_g_per_100g,
        "fiber_g": food.fiber_g_per_100g,
    }
    for name, previous in values.items():
        new = getattr(proposed.canonical.normalized_facts, name)
        if name != "fiber_g" and previous is None:
            return False
        if previous is not None and new is not None and previous != new.value:
            return False
    return True


def catalog_plan(
    db: Session, draft: NutritionImportDraft, *, include_suggestions: bool = True
) -> tuple[list[dict], list[PreparedCatalogFood | None]]:
    source = ImportSource.model_validate(draft.document["source"])
    adapter = _adapter(draft, source)
    rights = (
        (adapter.catalog_publication_rights & {"owner_reported", "verified"})
        if adapter
        else frozenset()
    )
    rows = [ImportFoodRow.model_validate(item) for item in draft.document["rows"]]
    prepared = [
        prepare_catalog_food(
            row,
            source,
            allowed_publication_rights=rights,
            allowed_food_kinds=adapter.catalog_food_kinds if adapter else frozenset(),
            attribution=adapter.catalog_attribution if adapter else None,
        )
        for row in rows
    ]
    proposals = [item.food for item in prepared]
    source_keys = [_source_key(row, source, adapter) for row in rows]
    alias_keys = [_key(item.identity) if item else None for item in proposals]
    keys = {key for key in [*source_keys, *alias_keys] if key is not None}
    mappings = (
        db.query(NutritionCatalogIdentifier)
        .filter(NutritionCatalogIdentifier.key_hash.in_(keys))
        .all()
        if keys
        else []
    )
    by_mapping = {(item.kind, item.key_hash): item.food_id for item in mappings}
    mapped_ids = {item.food_id for item in mappings}
    barcodes = {item.barcode for item in proposals if item and item.barcode}
    identities = {item.identity for item in proposals if item}
    search_texts = {normalize_food_search_text(item.name, item.brand) for item in proposals if item}
    criteria = []
    if mapped_ids:
        criteria.append(Food.id.in_(mapped_ids))
    if barcodes:
        criteria.append(Food.barcode.in_(barcodes))
    if identities:
        criteria.append(Food.catalog_identity.in_(identities))
    if search_texts:
        criteria.append(Food.search_text.in_(search_texts))
    foods = (
        db.query(Food).filter(Food.food_type != "user", or_(*criteria)).all() if criteria else []
    )
    by_id = {food.id: food for food in foods}
    by_barcode = {food.barcode: food for food in foods if food.barcode}
    by_identity: dict[str, list[Food]] = {}
    by_search_text: dict[str, list[Food]] = {}
    for food in foods:
        by_identity.setdefault(_stored_identity(food), []).append(food)
        by_search_text.setdefault(food.search_text, []).append(food)

    plan: list[dict] = []
    for index, item in enumerate(prepared):
        proposal = item.food
        outcome, reason, match = item.outcome, item.reason, None
        if proposal is not None:
            source_key = source_keys[index]
            alias_key = alias_keys[index]
            mapped_id = by_mapping.get(("source", source_key)) if source_key else None
            alias_id = by_mapping.get(("alias", alias_key)) if alias_key else None
            source_match = by_id.get(mapped_id) if mapped_id else None
            barcode_match = by_barcode.get(proposal.barcode) if proposal.barcode else None
            exact = by_identity.get(proposal.identity, [])
            alias_match = by_id.get(alias_id) if alias_id else None
            matches = [
                x for x in (source_match, barcode_match, *(exact[:1]), alias_match) if x is not None
            ]
            if len(exact) > 1:
                outcome, reason = "needs_review", "multiple_exact_matches"
            elif len({x.id for x in matches}) > 1:
                match, outcome, reason = (
                    matches[0],
                    "conflict",
                    "identity_points_to_different_foods",
                )
            else:
                match = (
                    source_match or barcode_match or (exact[0] if exact else None) or alias_match
                )
                if match is None and by_search_text.get(
                    normalize_food_search_text(proposal.name, proposal.brand)
                ):
                    outcome, reason = "needs_review", "ambiguous_existing_identity"
                if match is not None:
                    if match.status != "active":
                        outcome, reason = "needs_review", "catalog_food_unavailable"
                    elif (
                        (_stored_identity(match) != proposal.identity and alias_id != match.id)
                        or (
                            match.barcode and proposal.barcode and match.barcode != proposal.barcode
                        )
                        or not _facts_match(match, proposal)
                    ):
                        outcome, reason = "conflict", "catalog_facts_or_identity_conflict"
                    else:
                        outcome, reason = "reuse", None
        snapshot = None
        if match is not None:
            snapshot = _food_snapshot(match)
        plan.append(
            {
                "index": index,
                "outcome": outcome,
                "reason": reason,
                "food_id": match.id if match is not None else None,
                "snapshot": snapshot,
                "source_key": source_keys[index],
                "proposal": (
                    _key(
                        [
                            proposal.name,
                            proposal.brand,
                            proposal.barcode,
                            proposal.kind,
                            proposal.identity,
                            proposal.canonical.model_dump(mode="json"),
                            proposal.provenance,
                        ]
                    )
                    if proposal is not None
                    else None
                ),
                "source_reference": (
                    {
                        "provider": source.provider,
                        "source": source.source,
                        "identity_source": rows[index].food.identity_source,
                        "source_id": rows[index].food.source_id,
                    }
                    if source_keys[index]
                    else None
                ),
            }
        )
    batches: dict[tuple[str, str], list[int]] = {}
    for entry in plan:
        if entry["outcome"] != "publish":
            continue
        proposal = proposals[entry["index"]]
        assert proposal is not None
        batches.setdefault(("identity", proposal.identity), []).append(entry["index"])
        batches.setdefault(
            ("search", normalize_food_search_text(proposal.name, proposal.brand)), []
        ).append(entry["index"])
        if proposal.barcode:
            batches.setdefault(("barcode", proposal.barcode), []).append(entry["index"])
        if entry["source_key"]:
            batches.setdefault(("source", entry["source_key"]), []).append(entry["index"])
    for indexes in batches.values():
        if len(indexes) < 2:
            continue
        group = [proposals[index] for index in indexes]
        assert all(proposal is not None for proposal in group)
        group_foods = [proposal for proposal in group if proposal is not None]
        first = group_foods[0]
        if len({proposal.barcode for proposal in group_foods if proposal.barcode}) > 1 or any(
            proposal.identity != first.identity
            or proposal.canonical.normalized_facts != first.canonical.normalized_facts
            or proposal.canonical.serving_size != first.canonical.serving_size
            for proposal in group_foods[1:]
        ):
            for index in indexes:
                plan[index]["outcome"] = "needs_review"
                plan[index]["reason"] = "conflicting_batch_rows"
    for entry in plan:
        entry["suggestions"] = []
        entry["suggestions_evaluated"] = False
    if include_suggestions and db.get_bind().dialect.name == "postgresql":
        # shortcut: fuzzy hints cover 200 rows; use Food Search for remaining rows.
        eligible = [
            (entry["index"], proposals[entry["index"]])
            for entry in plan
            if entry["outcome"] in {"publish", "needs_review"}
            and proposals[entry["index"]] is not None
        ][:200]
        if eligible:
            for index, _ in eligible:
                plan[index]["suggestions_evaluated"] = True
            suggestions = db.execute(
                text(
                    "SELECT input.row_index, candidate.id, candidate.name, candidate.brand "
                    "FROM unnest(CAST(:indexes AS integer[]), CAST(:queries AS text[])) "
                    "AS input(row_index, query) CROSS JOIN LATERAL ("
                    "SELECT f.id, f.name, f.brand, similarity(f.search_text, input.query) AS score FROM foods f "
                    "WHERE f.status = 'active' AND f.food_type <> 'user' "
                    "AND f.search_text % input.query "
                    "ORDER BY score DESC, f.id LIMIT 3"
                    ") candidate ORDER BY input.row_index, candidate.score DESC, candidate.id"
                ),
                {
                    "indexes": [index for index, _ in eligible],
                    "queries": [
                        normalize_food_search_text(proposal.name, proposal.brand)
                        for _, proposal in eligible
                    ],
                },
            ).all()
            for row_index, food_id, name, brand in suggestions:
                plan[row_index]["suggestions"].append(
                    {"food_id": food_id, "name": name, "brand": brand}
                )
    return plan, proposals


def catalog_signature(draft: NutritionImportDraft, plan: list[dict]) -> str:
    return _key([draft.id, draft.revision, draft.document_sha256, plan])


def write_catalog_plan(
    db: Session,
    user: User,
    plan: list[dict],
    proposals: list[PreparedCatalogFood | None],
    selected: set[int],
) -> list[dict]:
    chosen = [item for item in plan if item["index"] in selected]
    existing_ids = {item["food_id"] for item in chosen if item["food_id"] is not None}
    foods = (
        {item.id: item for item in db.query(Food).filter(Food.id.in_(existing_ids)).all()}
        if existing_ids
        else {}
    )
    pending_by_identity: dict[str, Food] = {}
    pending_barcodes: dict[str, str] = {}
    pending_sources: dict[str, str] = {}
    chosen_foods = []
    for item in chosen:
        proposal = proposals[item["index"]]
        if proposal is None or item["outcome"] not in {"publish", "reuse", "conflict"}:
            raise ValueError("catalog_row_unavailable")
        food = foods.get(item["food_id"]) if item["food_id"] is not None else None
        if food is None:
            food = pending_by_identity.get(proposal.identity)
            if food is None:
                food = Food(
                    name=proposal.name,
                    brand=proposal.brand,
                    barcode=proposal.barcode,
                    catalog_identity=proposal.identity,
                    **_legacy_projection(proposal.canonical),
                    **_food_serving_projection(proposal.canonical),
                    nutrition_basis_kind=proposal.canonical.source_basis,
                    nutrition_basis_amount=Decimal("1")
                    if proposal.canonical.source_basis == "per_serving"
                    else Decimal("100"),
                    nutrition_basis_unit={
                        "per_100_g": "g",
                        "per_100_ml": "ml",
                        "per_serving": "serving",
                    }[proposal.canonical.source_basis],
                    canonical_facts=proposal.canonical.model_dump(mode="json"),
                    nutrition_provenance=proposal.provenance,
                    canonical_complete=True,
                    food_type="branded" if proposal.kind == "branded_food" else "system",
                    owner_user_id=None,
                    provenance="user_confirmed_package",
                    source_name="yfc_community",
                    source_version=proposal.adapter_version,
                    trust_level="unverified",
                    catalog_quality="community_unverified",
                    status="active",
                )
                db.add(food)
                pending_by_identity[proposal.identity] = food
            elif not _facts_match(food, proposal) or (
                food.barcode and proposal.barcode and food.barcode != proposal.barcode
            ):
                raise ValueError("catalog_batch_conflict")
            elif food.barcode is None and proposal.barcode:
                food.barcode = proposal.barcode
            if proposal.barcode:
                previous = pending_barcodes.setdefault(proposal.barcode, proposal.identity)
                if previous != proposal.identity:
                    raise ValueError("catalog_batch_conflict")
            if item["source_key"]:
                previous = pending_sources.setdefault(item["source_key"], proposal.identity)
                if previous != proposal.identity:
                    raise ValueError("catalog_batch_conflict")
        chosen_foods.append((item, proposal, food))
    db.flush()

    payloads = []
    for item, proposal, food in chosen_foods:
        payload = {
            "product": {
                "name": proposal.name,
                "brand": proposal.brand,
                "barcode": proposal.barcode,
                "catalog_identity": proposal.identity,
            },
            "nutrition": proposal.canonical.model_dump(mode="json"),
            "provenance": proposal.provenance,
            "source_identity": item["source_reference"],
        }
        payloads.append((item, proposal, food, payload, payload_digest(payload)))
    food_ids = {food.id for _, _, food, _, _ in payloads}
    digests = {digest for _, _, _, _, digest in payloads}
    present = (
        {
            (food_id, digest)
            for food_id, digest in db.query(
                NutritionCatalogContribution.food_id, NutritionCatalogContribution.payload_digest
            )
            .filter(
                NutritionCatalogContribution.food_id.in_(food_ids),
                NutritionCatalogContribution.payload_digest.in_(digests),
            )
            .all()
        }
        if food_ids
        else set()
    )
    source_keys = {item["source_key"] for item, _, _, _, _ in payloads if item["source_key"]}
    mappings = (
        {
            row.key_hash: row.food_id
            for row in db.query(NutritionCatalogIdentifier)
            .filter(
                NutritionCatalogIdentifier.kind == "source",
                NutritionCatalogIdentifier.key_hash.in_(source_keys),
            )
            .all()
        }
        if source_keys
        else {}
    )
    results = []
    published_food_ids: set[int] = set()
    for item, proposal, food, payload, digest in payloads:
        if (food.id, digest) not in present:
            add_catalog_contribution(
                db,
                food=food,
                user=user,
                canonical_payload=payload,
                digest=digest,
                state="conflict" if item["outcome"] == "conflict" else "accepted",
                source_version=proposal.adapter_version,
            )
            present.add((food.id, digest))
        if item["source_key"] and item["outcome"] != "conflict":
            mapped = mappings.get(item["source_key"])
            if mapped is None:
                db.add(
                    NutritionCatalogIdentifier(
                        food_id=food.id,
                        kind="source",
                        key_hash=item["source_key"],
                        **item["source_reference"],
                    )
                )
                mappings[item["source_key"]] = food.id
            elif mapped != food.id:
                raise ValueError("catalog_source_conflict")
        outcome = item["outcome"]
        if outcome == "publish":
            if food.id in published_food_ids:
                outcome = "reuse"
            published_food_ids.add(food.id)
        results.append(
            {
                "index": item["index"],
                "outcome": outcome,
                "reason": item["reason"],
                "food_id": food.id,
            }
        )
    db.flush()
    return results


def catalog_import_preview(db: Session, user: User, draft_id: str) -> dict:
    draft = get_nutrition_import_draft(db, user, draft_id, allow_confirmed=True)
    plan, proposals = catalog_plan(db, draft)
    rows = []
    for row, proposal in zip(plan, proposals, strict=True):
        product = None
        if proposal is not None:
            product = {
                "name": proposal.name,
                "brand": proposal.brand,
                "barcode": proposal.barcode,
                "kind": proposal.kind,
                "nutrition": proposal.canonical.model_dump(mode="json"),
                "provenance": proposal.provenance,
            }
        rows.append(
            {
                **{
                    key: row[key]
                    for key in (
                        "index",
                        "outcome",
                        "reason",
                        "food_id",
                        "suggestions",
                        "suggestions_evaluated",
                    )
                },
                "product": product,
            }
        )
    return {
        "id": draft.id,
        "revision": draft.revision,
        "expires_at": draft.expires_at,
        "source": draft.document["source"],
        "rows": rows,
        "preview_signature": catalog_signature(draft, plan),
    }


def confirm_catalog_import(
    db: Session,
    user: User,
    draft_id: str,
    *,
    revision: int,
    preview_signature: str,
    confirm_key: str,
    row_indexes: list[int],
    confirmed: bool,
) -> dict:
    if confirmed is not True or not _KEY.fullmatch(confirm_key):
        raise NutritionDraftError("confirmation_required", 422)
    if not row_indexes or len(row_indexes) != len(set(row_indexes)):
        raise NutritionDraftError("invalid_rows", 422)
    selected = set(row_indexes)
    fingerprint = _key([draft_id, revision, preview_signature, sorted(selected)])
    key_hash = hashlib.sha256(confirm_key.encode("ascii")).hexdigest()
    _lock_user(db, user)
    draft = get_nutrition_import_draft(db, user, draft_id, lock=True, allow_confirmed=True)
    if draft.catalog_receipt is not None:
        if (
            draft.catalog_confirm_key_hash != key_hash
            or draft.catalog_confirm_fingerprint != fingerprint
        ):
            raise NutritionDraftError("confirmation_conflict", 409)
        return draft.catalog_receipt
    if draft.revision != revision:
        raise NutritionDraftError("stale_revision", 409)
    if (
        db.query(NutritionImportDraft.id)
        .filter(
            NutritionImportDraft.owner_user_id == user.id,
            NutritionImportDraft.catalog_confirm_key_hash == key_hash,
            NutritionImportDraft.id != draft.id,
        )
        .first()
    ):
        raise NutritionDraftError("confirmation_conflict", 409)
    plan, _ = catalog_plan(db, draft, include_suggestions=False)
    ids = sorted({item["food_id"] for item in plan if item["food_id"] is not None})
    if ids:
        db.query(Food).filter(Food.id.in_(ids)).order_by(
            Food.id
        ).with_for_update().populate_existing().all()
    plan, proposals = catalog_plan(db, draft)
    if catalog_signature(draft, plan) != preview_signature:
        raise NutritionDraftError("preview_changed", 409)
    if any(index < 0 or index >= len(plan) for index in selected):
        raise NutritionDraftError("invalid_rows", 422)
    try:
        rows = write_catalog_plan(db, user, plan, proposals, selected)
    except ValueError as exc:
        raise NutritionDraftError(str(exc), 409) from None
    receipt = {"rows": rows, "preview_signature": preview_signature}
    draft.catalog_confirm_key_hash = key_hash
    draft.catalog_confirm_fingerprint = fingerprint
    draft.catalog_receipt = receipt
    db.flush()
    return receipt


def list_catalog_conflicts(db: Session, *, after_id: int, limit: int) -> list[dict]:
    rows = (
        db.query(NutritionCatalogContribution, Food)
        .join(Food, Food.id == NutritionCatalogContribution.food_id)
        .filter(
            NutritionCatalogContribution.state == "conflict",
            NutritionCatalogContribution.id > after_id,
        )
        .order_by(NutritionCatalogContribution.id)
        .limit(limit)
        .all()
    )
    return [
        {
            "id": contribution.id,
            "food_id": food.id,
            "payload": contribution.canonical_payload,
            "preview_signature": _key(
                [contribution.id, contribution.canonical_payload, _food_snapshot(food)]
            ),
        }
        for contribution, food in rows
    ]


def confirm_catalog_alias(
    db: Session, actor: User, contribution_id: int, *, preview_signature: str
) -> dict:
    contribution = (
        db.query(NutritionCatalogContribution)
        .filter_by(id=contribution_id, state="conflict")
        .with_for_update()
        .first()
    )
    if contribution is None:
        raise NutritionDraftError("not_found", 404)
    food = db.query(Food).filter_by(id=contribution.food_id).with_for_update().first()
    if food is None or food.status != "active" or food.food_type == "user":
        raise NutritionDraftError("catalog_food_unavailable", 409)
    payload = contribution.canonical_payload
    if _key([contribution.id, payload, _food_snapshot(food)]) != preview_signature:
        raise NutritionDraftError("preview_changed", 409)
    try:
        product = payload["product"]
        identity = product["catalog_identity"]
        candidate_parts = json.loads(identity)
        current_parts = json.loads(_stored_identity(food))
        canonical = CanonicalDraft.model_validate(payload["nutrition"])
        proposed = PreparedCatalogFood(
            name=product["name"],
            brand=product["brand"],
            barcode=product["barcode"],
            kind="branded_food" if food.brand else "standard_food",
            identity=identity,
            canonical=canonical,
            adapter_version=payload["provenance"]["adapter_version"],
            provenance={},
        )
        if (
            not isinstance(candidate_parts, list)
            or len(candidate_parts) not in {5, 6}
            or candidate_parts[0] != current_parts[0]
            or candidate_parts[2:] != current_parts[2:]
            or (food.barcode and proposed.barcode and food.barcode != proposed.barcode)
            or not _facts_match(food, proposed)
        ):
            raise ValueError
    except KeyError, TypeError, ValueError, ValidationError:
        raise NutritionDraftError("alias_not_confirmable", 409) from None
    key = _key(identity)
    existing = db.query(NutritionCatalogIdentifier).filter_by(kind="alias", key_hash=key).first()
    if existing is not None:
        if existing.food_id != food.id:
            raise NutritionDraftError("alias_conflict", 409)
        return {"food_id": food.id, "contribution_id": contribution.id}
    candidates = (
        db.query(Food)
        .filter(
            Food.food_type != "user",
            or_(
                Food.catalog_identity == identity,
                Food.search_text == normalize_food_search_text(proposed.name, proposed.brand),
            ),
        )
        .all()
    )
    if any(other.id != food.id and _stored_identity(other) == identity for other in candidates):
        raise NutritionDraftError("alias_conflict", 409)
    db.add(NutritionCatalogIdentifier(food_id=food.id, kind="alias", key_hash=key))
    record_audit_event(
        db,
        action="nutrition_catalog_alias_confirmed",
        resource_type="food",
        resource_id=food.id,
        actor_user_id=actor.id,
    )
    db.flush()
    return {"food_id": food.id, "contribution_id": contribution.id}
