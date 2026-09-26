from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from datetime import timedelta
from decimal import Decimal
from functools import lru_cache
from typing import Literal, cast

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fitminiapp_api.core.config import settings
from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.models.food import Food
from fitminiapp_api.models.nutrition_label import (
    NutritionCatalogContribution,
    NutritionLabelDraft,
)
from fitminiapp_api.models.user import User
from fitminiapp_api.nutrition_label.contracts import (
    CANONICAL_DRAFT_SCHEMA_VERSION,
    NUTRIENT_FIELDS,
    NUTRIENT_UNITS,
    BasisKind,
    CanonicalDraft,
    CanonicalFact,
    FieldEvidence,
    NutrientFacts,
    ServingSize,
    SourceNutrientFacts,
    validate_canonical_draft,
)
from fitminiapp_api.nutrition_label.image import ImageIngressError, normalize_uploaded_image
from fitminiapp_api.nutrition_label.ocr import (
    OCR_PIPELINE_VERSION,
    LocalOcrError,
    OcrCandidate,
    OcrEngine,
    RapidOcr,
    TesseractOcr,
)
from fitminiapp_api.nutrition_label.parser import (
    CanonicalNormalizationError,
    build_draft_from_ocr,
    score_nutrition_candidate,
)
from fitminiapp_api.nutrition_label.recognition_assessment import (
    OCR_BUDGET_EXHAUSTED_WARNING,
    RecognitionOutcome,
    assess_recognition,
    has_reviewable_source_signal,
    usable_read_fact_count,
)
from fitminiapp_api.nutrition_label.vision import (
    VISION_MAX_RESPONSE_BYTES,
    VisionFallbackAdapter,
    VisionProposalError,
    validate_vision_proposal,
)
from fitminiapp_api.schemas.food import (
    FoodCatalogContributionOutcome,
    FoodResponse,
    validate_gtin,
)
from fitminiapp_api.schemas.nutrition_label import (
    LabelDraftStatus,
    NutritionLabelConfirmRequest,
    NutritionLabelConfirmResponse,
    NutritionLabelDraftResponse,
)
from fitminiapp_api.services.food_catalog_contributions import (
    canonical_facts_match,
    find_shared_food,
)
from fitminiapp_api.services.foods import get_food_response

NUTRITION_LABEL_SOURCE_VERSION = "nutrition-label-local-v3"
NUTRITION_LABEL_PROMPT_VERSION = "ocr-structured-adaptive-v3"
_STRONG_SUCCESS_BLOCKING_WARNINGS = frozenset(
    {
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
    }
)
logger = logging.getLogger("app")


class NutritionLabelError(ValueError):
    def __init__(self, code: str, *, status_code: int = 422) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class NutritionLabelNotFoundError(NutritionLabelError):
    def __init__(self) -> None:
        super().__init__("draft_not_found", status_code=404)


class NutritionLabelConflictError(NutritionLabelError):
    def __init__(self, code: str = "draft_conflict") -> None:
        super().__init__(code, status_code=409)


def _now():
    return now_msk_naive()


def _normalize_idempotency_key(value: str) -> str:
    normalized = value.strip()
    if len(normalized) < 8 or len(normalized) > 128:
        raise NutritionLabelError("invalid_idempotency_key")
    return normalized


def _json_digest(payload: object) -> str:
    serialized = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _draft_response(row: NutritionLabelDraft) -> NutritionLabelDraftResponse:
    try:
        canonical = validate_canonical_draft(row.canonical_payload)
    except ValueError as exc:
        raise NutritionLabelError("invalid_persisted_draft", status_code=500) from exc
    return NutritionLabelDraftResponse(
        draft_id=row.id,
        revision=row.revision,
        status=cast("LabelDraftStatus", row.status),
        expires_at=row.expires_at,
        product_name=row.product_name,
        product_brand=row.product_brand,
        product_barcode=row.product_barcode,
        nutrition=canonical,
        warnings=canonical.warnings,
        requires_user_review=True,
    )


def _mark_expired(row: NutritionLabelDraft) -> None:
    row.status = "expired"


def _get_owned_draft(
    db: Session,
    user: User,
    draft_id: str,
    *,
    lock_for_update: bool = False,
) -> NutritionLabelDraft:
    query = db.query(NutritionLabelDraft).filter(
        NutritionLabelDraft.id == draft_id,
        NutritionLabelDraft.user_id == user.id,
    )
    if lock_for_update:
        query = query.with_for_update()
    row = query.first()
    if row is None:
        raise NutritionLabelNotFoundError()
    if row.status == "draft" and row.expires_at <= _now():
        _mark_expired(row)
        db.commit()
        raise NutritionLabelConflictError("draft_expired")
    return row


@lru_cache(maxsize=2)
def _build_rapidocr_engine(
    model_dir: str,
    timeout_seconds: float,
    max_output_chars: int,
) -> RapidOcr:
    try:
        return RapidOcr(
            model_dir=model_dir,
            timeout_seconds=timeout_seconds,
            max_output_chars=max_output_chars,
        )
    except LocalOcrError as exc:
        raise NutritionLabelError(exc.code, status_code=503) from exc


def _build_ocr_engine() -> OcrEngine:
    if settings.nutrition_label_scan_ocr_engine == "rapidocr":
        return _build_rapidocr_engine(
            settings.nutrition_label_scan_ocr_model_dir,
            settings.nutrition_label_scan_ocr_timeout_seconds,
            settings.nutrition_label_scan_ocr_max_output_chars,
        )
    if settings.nutrition_label_scan_ocr_engine == "tesseract":
        return TesseractOcr(
            languages=settings.nutrition_label_scan_ocr_languages,
            timeout_seconds=settings.nutrition_label_scan_ocr_timeout_seconds,
            max_output_chars=settings.nutrition_label_scan_ocr_max_output_chars,
            version=OCR_PIPELINE_VERSION,
        )
    raise NutritionLabelError("local_ocr_unavailable", status_code=503)


def _parse_ocr_candidates(
    engine: OcrEngine,
    normalized_png: bytes,
) -> CanonicalDraft:
    def parse_candidate(candidate: object) -> CanonicalDraft | None:
        if not isinstance(candidate, OcrCandidate):
            return None
        try:
            return build_draft_from_ocr(
                candidate.text,
                structured_tokens=candidate.tokens or None,
                provider=engine.name,
                model=engine.version,
                prompt_version=NUTRITION_LABEL_PROMPT_VERSION,
            )
        except CanonicalNormalizationError:
            return None

    def is_strong_success(canonical: CanonicalDraft) -> bool:
        if canonical.source_basis == "ambiguous":
            return False
        if _STRONG_SUCCESS_BLOCKING_WARNINGS.intersection(canonical.warnings):
            return False
        for field_name in ("protein_g", "fat_g", "carbohydrate_g"):
            source_facts = getattr(canonical.source_facts, field_name) or []
            if (
                getattr(canonical.field_evidence, field_name) != "read"
                or getattr(canonical.normalized_facts, field_name) is None
                or len(source_facts) != 1
                or source_facts[0].evidence != "read"
                or source_facts[0].unit != NUTRIENT_UNITS[field_name]
            ):
                return False
        energy_read = False
        for field_name in ("energy_kcal", "energy_kj"):
            source_facts = getattr(canonical.source_facts, field_name) or []
            if (
                getattr(canonical.field_evidence, field_name) == "read"
                and getattr(canonical.normalized_facts, field_name) is not None
                and len(source_facts) == 1
                and source_facts[0].evidence == "read"
                and source_facts[0].unit == NUTRIENT_UNITS[field_name]
            ):
                energy_read = True
                break
        return energy_read

    def select_best(
        parsed_candidates: list[tuple[tuple[int, ...], int, CanonicalDraft]],
        *,
        budget_exhausted: bool = False,
    ) -> CanonicalDraft:
        if not parsed_candidates:
            raise CanonicalNormalizationError("ocr_candidates_unusable")
        _, _, selected = max(parsed_candidates, key=lambda item: (item[0], -item[1]))
        if budget_exhausted:
            if not has_reviewable_source_signal(selected):
                raise LocalOcrError("local_ocr_timeout")
            selected = selected.model_copy(
                update={
                    "warnings": list(
                        dict.fromkeys([*selected.warnings, OCR_BUDGET_EXHAUSTED_WARNING])
                    )
                }
            )
        return selected

    extract_candidates = getattr(engine, "extract_candidates", None)
    iter_candidates = getattr(engine, "iter_candidates", None)
    if callable(iter_candidates):
        stream_parsed_candidates: list[tuple[tuple[int, ...], int, CanonicalDraft]] = []
        candidate_index = 0
        iterator = iter_candidates(normalized_png)
        budget_exhausted = False
        try:
            while True:
                try:
                    candidate = next(iterator)
                except StopIteration:
                    break
                except LocalOcrError as exc:
                    if exc.code != "local_ocr_timeout" or not stream_parsed_candidates:
                        raise
                    budget_exhausted = True
                    break
                if not isinstance(candidate, OcrCandidate):
                    continue
                canonical = parse_candidate(candidate)
                if canonical is None:
                    continue
                score = score_nutrition_candidate(canonical, candidate.tokens)
                stream_parsed_candidates.append((score.rank, candidate_index, canonical))
                candidate_index += 1
                if is_strong_success(canonical):
                    return canonical
        finally:
            close = getattr(iterator, "close", None)
            if callable(close):
                close()
        return select_best(stream_parsed_candidates, budget_exhausted=budget_exhausted)

    if not callable(extract_candidates):
        return build_draft_from_ocr(
            engine.extract_text(normalized_png),
            provider=engine.name,
            model=engine.version,
            prompt_version=NUTRITION_LABEL_PROMPT_VERSION,
        )

    raw_candidates = tuple(extract_candidates(normalized_png))
    parsed_candidates: list[tuple[tuple[int, ...], int, CanonicalDraft]] = []
    for index, candidate in enumerate(raw_candidates):
        canonical = parse_candidate(candidate)
        if canonical is None or not isinstance(candidate, OcrCandidate):
            continue
        score = score_nutrition_candidate(canonical, candidate.tokens)
        parsed_candidates.append((score.rank, index, canonical))
    return select_best(parsed_candidates)


def create_label_draft(
    db: Session,
    user: User,
    *,
    image_bytes: bytes,
    content_type: str | None,
    idempotency_key: str,
    ocr_engine: OcrEngine | None = None,
    vision_adapter: VisionFallbackAdapter | None = None,
) -> NutritionLabelDraftResponse:
    started = time.monotonic()
    configured_provider = (
        "local_rapidocr"
        if settings.nutrition_label_scan_ocr_engine == "rapidocr"
        else "local_tesseract"
    )
    logger.info(
        "nutrition_scan_started",
        extra={"data_class": "package_image", "provider": configured_provider},
    )
    key = _normalize_idempotency_key(idempotency_key)
    existing = (
        db.query(NutritionLabelDraft)
        .filter(
            NutritionLabelDraft.user_id == user.id,
            NutritionLabelDraft.idempotency_key == key,
        )
        .first()
    )
    if existing is not None:
        if existing.status == "draft" and existing.expires_at > _now():
            return _draft_response(existing)
        if existing.status == "draft":
            _mark_expired(existing)
            db.commit()
        raise NutritionLabelConflictError("idempotency_key_already_used")

    try:
        normalized_image = normalize_uploaded_image(
            image_bytes,
            content_type,
            max_bytes=settings.nutrition_label_scan_max_image_bytes,
            max_pixels=settings.nutrition_label_scan_max_pixels,
        )
        engine = ocr_engine or _build_ocr_engine()
        canonical = _parse_ocr_candidates(engine, normalized_image.data)
    except ImageIngressError as exc:
        logger.info("nutrition_scan_failed", extra={"error_code": exc.code})
        raise NutritionLabelError(exc.code) from exc
    except LocalOcrError as exc:
        logger.info("nutrition_scan_failed", extra={"error_code": exc.code})
        raise NutritionLabelError(exc.code, status_code=503) from exc
    except CanonicalNormalizationError as exc:
        logger.info("nutrition_scan_failed", extra={"error_code": str(exc)})
        raise NutritionLabelError(str(exc)) from exc

    assessment = assess_recognition(canonical)
    provider_outcome = "not_invoked"
    provider_class = "none"

    vision_rescue_available = (
        settings.nutrition_label_vision_enabled
        and not settings.nutrition_label_vision_kill_switch
        and vision_adapter is not None
    )
    if assessment.outcome == RecognitionOutcome.RETAKE_REQUIRED and vision_rescue_available:
        assessment = assessment.with_outcome(
            RecognitionOutcome.VISION_CANDIDATE,
            "vision_rescue_no_local_signal",
        )

    route_class = assessment.outcome.value

    if assessment.outcome == RecognitionOutcome.RETAKE_REQUIRED:
        logger.info(
            "nutrition_scan_failed",
            extra={
                "error_code": "retake_required",
                "assessment_outcome": assessment.outcome.value,
                "assessment_reason_codes": assessment.reasons,
            },
        )
        raise NutritionLabelError("retake_required")

    if assessment.outcome == RecognitionOutcome.VISION_CANDIDATE:
        if (
            not settings.nutrition_label_vision_enabled
            or settings.nutrition_label_vision_kill_switch
        ):
            reason = (
                "vision_kill_switch"
                if settings.nutrition_label_vision_kill_switch
                else "vision_disabled"
            )
            assessment = assessment.with_outcome(RecognitionOutcome.MANUAL_REVIEW, reason)
            provider_outcome = "disabled"
        elif vision_adapter is None:
            assessment = assessment.with_outcome(
                RecognitionOutcome.MANUAL_REVIEW, "vision_adapter_unavailable"
            )
            provider_outcome = "unavailable"
        elif len(normalized_image.data) > settings.nutrition_label_scan_max_image_bytes:
            assessment = assessment.with_outcome(
                RecognitionOutcome.MANUAL_REVIEW, "vision_image_too_large"
            )
            provider_outcome = "image_too_large"
        else:
            provider_class = vision_adapter.provider_class
            try:
                proposal = vision_adapter.recognize(
                    normalized_image.data,
                    timeout_seconds=settings.nutrition_label_vision_timeout_seconds,
                    max_response_bytes=VISION_MAX_RESPONSE_BYTES,
                )
                canonical = validate_vision_proposal(
                    proposal,
                    provider_class=vision_adapter.provider_class,
                    model_class=vision_adapter.model_class,
                    prompt_version=vision_adapter.prompt_version,
                )
            except TimeoutError:
                assessment = assessment.with_outcome(
                    RecognitionOutcome.MANUAL_REVIEW, "vision_timeout"
                )
                provider_outcome = "timeout"
            except VisionProposalError:
                assessment = assessment.with_outcome(
                    RecognitionOutcome.MANUAL_REVIEW, "vision_invalid_response"
                )
                provider_outcome = "invalid_response"
            except OSError:
                assessment = assessment.with_outcome(
                    RecognitionOutcome.MANUAL_REVIEW, "vision_provider_unavailable"
                )
                provider_outcome = "unavailable"
            except Exception:
                assessment = assessment.with_outcome(
                    RecognitionOutcome.MANUAL_REVIEW, "vision_provider_failed"
                )
                provider_outcome = "failed"
            else:
                provider_outcome = "succeeded"
                route_class = "vision_fallback"

    if route_class != "vision_fallback":
        route_class = assessment.outcome.value

    row = NutritionLabelDraft(
        id=str(uuid.uuid4()),
        user_id=user.id,
        idempotency_key=key,
        revision=1,
        status="draft",
        canonical_payload=canonical.model_dump(mode="json"),
        ocr_engine=engine.name,
        ocr_engine_version=engine.version,
        source_mime=normalized_image.mime,
        expires_at=_now() + timedelta(minutes=settings.nutrition_label_scan_draft_ttl_minutes),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        replay = (
            db.query(NutritionLabelDraft)
            .filter(
                NutritionLabelDraft.user_id == user.id,
                NutritionLabelDraft.idempotency_key == key,
            )
            .first()
        )
        if replay is not None and replay.status == "draft" and replay.expires_at > _now():
            return _draft_response(replay)
        raise NutritionLabelConflictError("draft_could_not_be_created") from exc
    db.refresh(row)
    logger.info(
        "nutrition_scan_completed",
        extra={
            "outcome": "draft_created",
            "latency_ms": (time.monotonic() - started) * 1000,
            "items_count": usable_read_fact_count(canonical),
            "assessment_outcome": assessment.outcome.value,
            "assessment_reason_codes": assessment.reasons,
            "route_class": route_class,
            "provider_class": provider_class,
            "provider_outcome": provider_outcome,
        },
    )
    return _draft_response(row)


def get_label_draft(db: Session, user: User, draft_id: str) -> NutritionLabelDraftResponse:
    return _draft_response(_get_owned_draft(db, user, draft_id))


def cancel_label_draft(db: Session, user: User, draft_id: str, revision: int) -> None:
    row = _get_owned_draft(db, user, draft_id)
    if row.status != "draft":
        raise NutritionLabelConflictError("draft_not_active")
    if row.revision != revision:
        raise NutritionLabelConflictError("stale_draft_revision")
    row.status = "cancelled"
    db.commit()


def _fact_from_edit(
    field_name: str,
    value: Decimal | None,
    source_basis: str,
    serving_size: ServingSize | None,
) -> CanonicalFact | None:
    if value is None:
        return None
    basis_ref = source_basis
    normalized_value = value
    if source_basis == "per_serving" and serving_size is not None:
        unit = serving_size.unit
        if unit in {"g", "ml"}:
            basis_ref = "per_100_g" if unit == "g" else "per_100_ml"
            normalized_value = value * Decimal(100) / serving_size.amount
    return CanonicalFact(
        value=normalized_value,
        unit=NUTRIENT_UNITS[field_name],
        basis_ref=cast(BasisKind, basis_ref),
    )


def _canonical_from_confirmation(
    stored: CanonicalDraft,
    request: NutritionLabelConfirmRequest,
) -> CanonicalDraft:
    edit = request.nutrition
    values = edit.model_dump()
    normalized = {
        field_name: _fact_from_edit(
            field_name,
            values[field_name],
            edit.source_basis,
            edit.serving_size,
        )
        for field_name in NUTRIENT_FIELDS
    }
    evidence_values = stored.field_evidence.model_dump()
    for field_name in NUTRIENT_FIELDS:
        if values[field_name] is not None:
            evidence_values[field_name] = "read"
        elif evidence_values[field_name] == "read":
            evidence_values[field_name] = "absent"
    source_facts = stored.source_facts
    if stored.source_basis == "ambiguous":
        source_values = source_facts.model_dump()
        for field_name in NUTRIENT_FIELDS:
            cells = source_values[field_name]
            if cells is None:
                continue
            for cell in cells:
                if cell["basis_ref"] == "ambiguous":
                    cell["basis_ref"] = edit.source_basis
        source_facts = SourceNutrientFacts.model_validate(source_values)
    warnings = list(stored.warnings)
    if "user_corrected_fields" not in warnings:
        warnings.append("user_corrected_fields")
    return CanonicalDraft(
        schema_version=CANONICAL_DRAFT_SCHEMA_VERSION,
        source_language=stored.source_language,
        label_format=stored.label_format,
        source_basis=edit.source_basis,
        serving_size=edit.serving_size,
        servings_per_container=edit.servings_per_container,
        package_amount=edit.package_amount,
        source_facts=source_facts,
        normalized_facts=NutrientFacts.model_validate(normalized),
        derived_fields=stored.derived_fields,
        displayed_daily_value_percent=stored.displayed_daily_value_percent,
        field_evidence=FieldEvidence.model_validate(evidence_values),
        confidence_kind="none",
        confidence=stored.confidence.model_copy(update=dict.fromkeys(NUTRIENT_FIELDS)),
        warnings=warnings,
        requires_user_review=True,
        metadata=stored.metadata,
    )


def _require_confirmable_facts(canonical: CanonicalDraft) -> None:
    if canonical.source_basis == "ambiguous":
        raise NutritionLabelError("ambiguous_basis")
    required = ("energy_kcal", "protein_g", "fat_g", "carbohydrate_g")
    if any(getattr(canonical.normalized_facts, field_name) is None for field_name in required):
        raise NutritionLabelError("incomplete_required_facts")


def _legacy_projection(canonical: CanonicalDraft) -> dict[str, Decimal | None]:
    projection: dict[str, Decimal | None] = {
        "energy_kcal_per_100g": None,
        "protein_g_per_100g": None,
        "fat_g_per_100g": None,
        "carbs_g_per_100g": None,
        "fiber_g_per_100g": None,
    }
    mapping = {
        "energy_kcal": "energy_kcal_per_100g",
        "protein_g": "protein_g_per_100g",
        "fat_g": "fat_g_per_100g",
        "carbohydrate_g": "carbs_g_per_100g",
        "fiber_g": "fiber_g_per_100g",
    }
    for field_name, column_name in mapping.items():
        fact = getattr(canonical.normalized_facts, field_name)
        if fact is not None and fact.basis_ref == "per_100_g":
            projection[column_name] = fact.value
    return projection


def _food_serving_projection(canonical: CanonicalDraft) -> dict[str, Decimal | str | None]:
    serving = canonical.serving_size
    if serving is None:
        if canonical.source_basis == "per_serving":
            return {
                "standard_serving_amount": Decimal("1"),
                "standard_serving_unit": "serving",
                "standard_serving_weight_g": None,
            }
        return {
            "standard_serving_amount": None,
            "standard_serving_unit": None,
            "standard_serving_weight_g": None,
        }
    return {
        "standard_serving_amount": serving.amount,
        "standard_serving_unit": serving.unit,
        "standard_serving_weight_g": serving.amount if serving.unit == "g" else None,
    }


def _nutrition_provenance(
    canonical: CanonicalDraft,
    *,
    barcode: str | None,
    visibility: str,
) -> dict[str, object]:
    normalized_bases = {
        getattr(canonical.normalized_facts, field_name).basis_ref
        for field_name in NUTRIENT_FIELDS
        if getattr(canonical.normalized_facts, field_name) is not None
    }
    return {
        "nutrition_source": "package_scan",
        "source_language": canonical.source_language,
        "label_format": canonical.label_format,
        "barcode": barcode,
        "provider": canonical.metadata.provider,
        "model": canonical.metadata.model,
        "prompt_version": canonical.metadata.prompt_version,
        "schema_version": canonical.schema_version,
        "policy_revision": canonical.metadata.policy_revision,
        "original_basis": canonical.source_basis,
        "normalized_basis": sorted(normalized_bases),
        "user_verified": True,
        "confidence_kind": canonical.confidence_kind,
        "visibility": visibility,
        "raw_image_retained": False,
        "raw_ocr_retained": False,
    }


def _payload_for_digest(canonical: CanonicalDraft, request: NutritionLabelConfirmRequest) -> dict:
    return {
        "name": request.name,
        "brand": request.brand,
        "barcode": request.barcode,
        "nutrition": canonical.model_dump(mode="json"),
    }


def _make_food(
    user: User,
    request: NutritionLabelConfirmRequest,
    canonical: CanonicalDraft,
    *,
    shared: bool,
    visibility: str,
) -> Food:
    projection = _legacy_projection(canonical)
    serving = _food_serving_projection(canonical)
    basis_fact = canonical.normalized_facts.energy_kcal
    if basis_fact is None:
        for field_name in NUTRIENT_FIELDS:
            basis_fact = getattr(canonical.normalized_facts, field_name)
            if basis_fact is not None:
                break
    if basis_fact is None:
        raise NutritionLabelError("incomplete_required_facts")
    basis_kind = basis_fact.basis_ref
    basis_amount = Decimal("100") if basis_kind in {"per_100_g", "per_100_ml"} else Decimal("1")
    basis_unit = {"per_100_g": "g", "per_100_ml": "ml", "per_serving": "serving"}[basis_kind]
    return Food(
        name=request.name,
        brand=request.brand,
        barcode=request.barcode,
        **projection,
        **serving,
        nutrition_basis_kind=basis_kind,
        nutrition_basis_amount=basis_amount,
        nutrition_basis_unit=basis_unit,
        canonical_facts=canonical.model_dump(mode="json"),
        nutrition_provenance=_nutrition_provenance(
            canonical,
            barcode=request.barcode,
            visibility=visibility,
        ),
        canonical_complete=True,
        food_type="branded" if shared else "user",
        owner_user_id=None if shared else user.id,
        provenance="user_confirmed_package" if shared else "user",
        source_name="yfc_community" if shared else None,
        source_version=NUTRITION_LABEL_SOURCE_VERSION if shared else None,
        trust_level="unverified",
        catalog_quality="community_unverified" if shared else "private",
        status="active",
    )


def _same_canonical_facts(food: Food, canonical: CanonicalDraft) -> bool:
    return canonical_facts_match(food, canonical)


def _add_contribution(
    db: Session,
    *,
    food: Food,
    user: User,
    canonical: CanonicalDraft,
    request: NutritionLabelConfirmRequest,
    state: str,
    digest: str,
) -> NutritionCatalogContribution:
    contribution = NutritionCatalogContribution(
        food_id=food.id,
        contributor_user_id=user.id,
        visibility="share_to_yfc_catalog",
        state=state,
        payload_digest=digest,
        canonical_payload={
            "product": {
                "name": request.name,
                "brand": request.brand,
                "barcode": request.barcode,
            },
            "nutrition": canonical.model_dump(mode="json"),
        },
        source_version=NUTRITION_LABEL_SOURCE_VERSION,
    )
    db.add(contribution)
    return contribution


def confirm_label_draft(
    db: Session,
    user: User,
    draft_id: str,
    request: NutritionLabelConfirmRequest,
) -> NutritionLabelConfirmResponse:
    row = _get_owned_draft(db, user, draft_id, lock_for_update=True)
    if row.status != "draft":
        raise NutritionLabelConflictError("draft_not_active")
    if row.revision != request.revision:
        raise NutritionLabelConflictError("stale_draft_revision")
    try:
        stored = validate_canonical_draft(row.canonical_payload)
        canonical = _canonical_from_confirmation(stored, request)
        _require_confirmable_facts(canonical)
    except NutritionLabelError:
        raise
    except (ValueError, TypeError) as exc:
        raise NutritionLabelError("invalid_confirmation_payload") from exc

    visibility = request.resolved_visibility()
    request = request.model_copy(update={"visibility": visibility})
    existing_shared = None
    shared = visibility == "share_to_yfc_catalog"
    if shared:
        request.barcode = validate_gtin(request.barcode)
        existing_shared = find_shared_food(
            db,
            name=request.name,
            brand=request.brand,
            barcode=request.barcode,
            canonical=canonical,
        )
    digest = _json_digest(_payload_for_digest(canonical, request))
    contribution_state = "private"
    contribution_outcome: FoodCatalogContributionOutcome | None = None
    if shared and existing_shared is not None:
        existing_contribution = (
            db.query(NutritionCatalogContribution)
            .filter(
                NutritionCatalogContribution.food_id == existing_shared.id,
                NutritionCatalogContribution.payload_digest == digest,
            )
            .first()
        )
        if existing_contribution is not None:
            contribution_state = "duplicate"
            contribution_outcome = "duplicate"
            food = existing_shared
        elif _same_canonical_facts(existing_shared, canonical):
            contribution_state = "accepted"
            contribution_outcome = "reused"
            food = existing_shared
            if request.barcode is not None and food.barcode is None:
                food.barcode = request.barcode
            _add_contribution(
                db,
                food=food,
                user=user,
                canonical=canonical,
                request=request,
                state="accepted",
                digest=digest,
            )
        else:
            _add_contribution(
                db,
                food=existing_shared,
                user=user,
                canonical=canonical,
                request=request,
                state="conflict",
                digest=digest,
            )
            # Do not overwrite the existing shared facts.  Keep the author
            # productive with an owner-scoped fallback while preserving the
            # conflict contribution for later catalog moderation.
            food = _make_food(
                user,
                request,
                canonical,
                shared=False,
                visibility="private",
            )
            db.add(food)
            db.flush()
            contribution_state = "conflict"
            contribution_outcome = "conflict"
    else:
        food = _make_food(
            user,
            request,
            canonical,
            shared=shared,
            visibility=visibility,
        )
        db.add(food)
        db.flush()
        if shared:
            contribution_state = "accepted"
            contribution_outcome = "created"
            _add_contribution(
                db,
                food=food,
                user=user,
                canonical=canonical,
                request=request,
                state="accepted",
                digest=digest,
            )

    row.status = "confirmed"
    row.revision += 1
    row.canonical_payload = canonical.model_dump(mode="json")
    row.product_name = request.name
    row.product_brand = request.brand
    row.product_barcode = request.barcode
    row.confirmed_visibility = visibility
    row.confirmed_food_id = food.id
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if shared:
            raise NutritionLabelConflictError("duplicate_barcode") from exc
        raise NutritionLabelConflictError("private_food_conflict") from exc
    db.refresh(food)
    response_food: FoodResponse = get_food_response(db, user, food.id)
    logger.info(
        "nutrition_scan_confirmed",
        extra={
            "outcome": contribution_state,
            "catalog_quality": food.catalog_quality,
            "visibility": visibility,
        },
    )
    return NutritionLabelConfirmResponse(
        food=response_food,
        visibility=visibility,
        contribution_state=cast(
            Literal["private", "accepted", "duplicate", "conflict"], contribution_state
        ),
        contribution_outcome=contribution_outcome,
        catalog_quality=cast(
            Literal["private", "verified", "community_unverified"], food.catalog_quality
        ),
        provenance=food.provenance or "user",
    )


__all__ = [
    "NutritionLabelConflictError",
    "NutritionLabelError",
    "NutritionLabelNotFoundError",
    "cancel_label_draft",
    "confirm_label_draft",
    "create_label_draft",
    "get_label_draft",
]
