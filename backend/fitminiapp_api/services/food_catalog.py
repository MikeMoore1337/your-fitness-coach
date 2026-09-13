from __future__ import annotations

import logging
import time
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from decimal import Decimal
from threading import Lock

from sqlalchemy.orm import Session

from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.food import (
    ExternalFoodResponse,
    FoodBarcodeLookupResponse,
    FoodProviderStatus,
    FoodProviderStatusResponse,
    FoodResponse,
    FoodSearchResponse,
)
from fitminiapp_api.services.food_provider import (
    BarcodeProviderRegistration,
    FoodProviderRegistry,
    FoodProviderUnavailable,
    ProviderFood,
    SearchProviderRegistration,
    serialize_provider_food,
)
from fitminiapp_api.services.food_search_aliases import (
    external_food_search_terms,
    is_russian_food_query,
    normalize_food_search_query,
)
from fitminiapp_api.services.foods import (
    get_food_by_barcode_response,
    search_foods,
)

logger = logging.getLogger("app")
_SEARCH_CACHE_TTL_SECONDS = 60.0
_SEARCH_CACHE_MAX_ENTRIES = 256


@dataclass(frozen=True)
class _CachedSearch:
    expires_at: float
    items: tuple[ProviderFood, ...]


class _ProviderSearchCache:
    def __init__(self) -> None:
        self._entries: OrderedDict[tuple[int, str, str, int], _CachedSearch] = OrderedDict()
        self._lock = Lock()

    def get(
        self,
        provider: object,
        provider_name: str,
        query: str,
        limit: int,
    ) -> tuple[ProviderFood, ...] | None:
        key = (id(provider), provider_name, query, limit)
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._entries.pop(key, None)
                return None
            self._entries.move_to_end(key)
            return entry.items

    def put(
        self,
        provider: object,
        provider_name: str,
        query: str,
        limit: int,
        items: list[ProviderFood],
    ) -> None:
        key = (id(provider), provider_name, query, limit)
        entry = _CachedSearch(
            expires_at=time.monotonic() + _SEARCH_CACHE_TTL_SECONDS,
            items=tuple(items),
        )
        with self._lock:
            self._entries[key] = entry
            self._entries.move_to_end(key)
            while len(self._entries) > _SEARCH_CACHE_MAX_ENTRIES:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


_SEARCH_CACHE = _ProviderSearchCache()


def clear_food_provider_search_cache() -> None:
    _SEARCH_CACHE.clear()


def _provider_failure_status(exc: FoodProviderUnavailable) -> FoodProviderStatus:
    return "rate_limited" if exc.reason == "rate_limited" else "unavailable"


def _aggregate_provider_status(
    statuses: list[FoodProviderStatusResponse],
) -> FoodProviderStatus:
    attempted = [status.status for status in statuses if status.status != "disabled"]
    if not attempted:
        return "disabled"
    if "available" in attempted:
        return "available"
    if attempted and all(status == "rate_limited" for status in attempted):
        return "rate_limited"
    return "unavailable"


def _search_provider(
    registration: SearchProviderRegistration,
    query_text: str,
    *,
    limit: int,
) -> list[ProviderFood]:
    provider = registration.provider
    if provider is None:
        return []
    normalized_query = normalize_food_search_query(query_text)
    cached = _SEARCH_CACHE.get(provider, registration.name, normalized_query, limit)
    if cached is not None:
        logger.info(
            "food_provider_search_cache_hit",
            extra={"provider": registration.name, "result_count": len(cached)},
        )
        return list(cached)
    logger.info("food_provider_search_cache_miss", extra={"provider": registration.name})
    items = provider.search(query_text, limit=limit)
    _SEARCH_CACHE.put(provider, registration.name, normalized_query, limit, items)
    logger.info(
        "food_provider_searched",
        extra={"provider": registration.name, "result_count": len(items)},
    )
    return items


def _normalized_identity(value: str | None) -> str:
    return normalize_food_search_query(value or "")


def _macros_match(left: ProviderFood, right: ProviderFood) -> bool:
    return (
        abs(left.energy_kcal_per_100g - right.energy_kcal_per_100g) <= Decimal("0.5")
        and abs(left.protein_g_per_100g - right.protein_g_per_100g) <= Decimal("0.1")
        and abs(left.fat_g_per_100g - right.fat_g_per_100g) <= Decimal("0.1")
        and abs(left.carbs_g_per_100g - right.carbs_g_per_100g) <= Decimal("0.1")
    )


def _weak_provider_duplicate(left: ProviderFood, right: ProviderFood) -> bool:
    return (
        left.barcode is None
        and right.barcode is None
        and _normalized_identity(left.name) == _normalized_identity(right.name)
        and _normalized_identity(left.brand) == _normalized_identity(right.brand)
        and _macros_match(left, right)
    )


def _weak_local_duplicate(local: FoodResponse, external: ProviderFood) -> bool:
    local_energy = local.energy_kcal_per_100g
    local_protein = local.protein_g_per_100g
    local_fat = local.fat_g_per_100g
    local_carbs = local.carbs_g_per_100g
    if any(value is None for value in (local_energy, local_protein, local_fat, local_carbs)):
        return False
    return (
        local.barcode is None
        and external.barcode is None
        and _normalized_identity(local.name) == _normalized_identity(external.name)
        and _normalized_identity(local.brand) == _normalized_identity(external.brand)
        and local_energy is not None
        and local_protein is not None
        and local_fat is not None
        and local_carbs is not None
        and abs(local_energy - external.energy_kcal_per_100g) <= Decimal("0.5")
        and abs(local_protein - external.protein_g_per_100g) <= Decimal("0.1")
        and abs(local_fat - external.fat_g_per_100g) <= Decimal("0.1")
        and abs(local_carbs - external.carbs_g_per_100g) <= Decimal("0.1")
    )


def deduplicate_provider_foods(
    local_items: list[FoodResponse],
    external_items: list[ProviderFood],
) -> tuple[list[ProviderFood], int]:
    kept: list[ProviderFood] = []
    local_barcodes = {item.barcode for item in local_items if item.barcode is not None}
    seen_provider_ids: set[tuple[str, str]] = set()
    seen_barcodes: set[str] = set()
    removed = 0
    for candidate in external_items:
        provider_identity = (candidate.provider, candidate.external_id)
        if provider_identity in seen_provider_ids:
            removed += 1
            continue
        if candidate.barcode is not None and (
            candidate.barcode in local_barcodes or candidate.barcode in seen_barcodes
        ):
            removed += 1
            continue
        if any(_weak_local_duplicate(local, candidate) for local in local_items):
            removed += 1
            continue
        if any(_weak_provider_duplicate(existing, candidate) for existing in kept):
            removed += 1
            continue
        kept.append(candidate)
        seen_provider_ids.add(provider_identity)
        if candidate.barcode is not None:
            seen_barcodes.add(candidate.barcode)
    return kept, removed


def _match_rank(food: ProviderFood, query_text: str) -> tuple[int, int, str, str, str, str]:
    terms = external_food_search_terms(query_text)
    name = _normalized_identity(food.name)
    brand = _normalized_identity(food.brand)
    searchable = " ".join(part for part in (name, brand) if part)
    if any(term in (name, brand) for term in terms):
        level = 0
    elif any(name.startswith(term) or brand.startswith(term) for term in terms):
        level = 1
    elif any(all(token in searchable.split() for token in term.split()) for term in terms):
        level = 2
    elif any(term in searchable for term in terms):
        level = 3
    else:
        level = 4
    market_rank = 0 if is_russian_food_query(query_text) and food.is_russian_market else 1
    return level, market_rank, name, brand, food.provider, food.external_id


def rank_provider_foods(items: list[ProviderFood], query_text: str) -> list[ProviderFood]:
    return sorted(items, key=lambda food: _match_rank(food, query_text))


def search_food_catalog(
    db: Session,
    current_user: User,
    query_text: str,
    *,
    limit: int,
    offset: int,
    include_external: bool,
    registry: FoodProviderRegistry,
) -> FoodSearchResponse:
    local = search_foods(db, current_user, query_text, limit=limit, offset=offset)
    response_values = local.model_dump()
    if not include_external or offset > 0:
        return FoodSearchResponse(**response_values, provider_status="not_requested")
    remaining = max(0, limit - len(local.items))
    if remaining == 0:
        logger.info("food_provider_search_skipped", extra={"reason": "local_budget_filled"})
        return FoodSearchResponse(**response_values, provider_status="not_needed")

    statuses: list[FoodProviderStatusResponse] = []
    collected: list[ProviderFood] = []
    request_limit = min(max(remaining, 5), 20)
    enabled = [registration for registration in registry.search if registration.provider]
    futures: dict[str, Future[list[ProviderFood]]] = {}
    with ThreadPoolExecutor(max_workers=max(1, len(enabled))) as executor:
        for registration in enabled:
            futures[registration.name] = executor.submit(
                _search_provider,
                registration,
                query_text,
                limit=request_limit,
            )
        for registration in registry.search:
            if registration.provider is None:
                statuses.append(
                    FoodProviderStatusResponse(provider=registration.name, status="disabled")
                )
                logger.info(
                    "food_provider_search_skipped",
                    extra={"provider": registration.name, "reason": "disabled"},
                )
                continue
            try:
                items = futures[registration.name].result()
            except FoodProviderUnavailable as exc:
                status = _provider_failure_status(exc)
                statuses.append(
                    FoodProviderStatusResponse(provider=registration.name, status=status)
                )
                logger.warning(
                    "food_provider_search_unavailable",
                    extra={"provider": registration.name, "reason": exc.reason},
                )
                continue
            if is_russian_food_query(query_text):
                localized_items = [item for item in items if item.name_language == "ru"]
                rejected_count = len(items) - len(localized_items)
                if rejected_count:
                    logger.info(
                        "food_provider_results_skipped_without_ru_name",
                        extra={
                            "provider": registration.name,
                            "result_count": rejected_count,
                        },
                    )
                items = localized_items
            statuses.append(
                FoodProviderStatusResponse(
                    provider=registration.name,
                    status="available",
                    result_count=len(items),
                )
            )
            collected.extend(items)

    deduplicated, removed = deduplicate_provider_foods(local.items, collected)
    ranked = rank_provider_foods(deduplicated, query_text)[:remaining]
    logger.info(
        "food_provider_search_deduplicated",
        extra={"removed_count": removed, "result_count": len(ranked)},
    )
    external_items: list[ExternalFoodResponse] = []
    for item in ranked:
        try:
            external_items.append(serialize_provider_food(item))
        except FoodProviderUnavailable as exc:
            logger.warning(
                "food_provider_result_rejected",
                extra={"provider": item.provider, "reason": exc.reason},
            )
    return FoodSearchResponse(
        **response_values,
        external_items=external_items,
        provider_status=_aggregate_provider_status(statuses),
        provider_statuses=statuses,
    )


def _disabled_barcode_statuses(
    registrations: tuple[BarcodeProviderRegistration, ...],
) -> list[FoodProviderStatusResponse]:
    return [
        FoodProviderStatusResponse(provider=registration.name, status="disabled")
        for registration in registrations
        if registration.provider is None
    ]


def get_food_catalog_item_by_barcode(
    db: Session,
    current_user: User,
    barcode: str,
    *,
    registry: FoodProviderRegistry,
) -> FoodBarcodeLookupResponse:
    local = get_food_by_barcode_response(db, current_user, barcode)
    if local is not None:
        return FoodBarcodeLookupResponse(
            barcode=barcode,
            status="found",
            source="local",
            local_item=local,
            provider_status="not_needed",
        )

    statuses = _disabled_barcode_statuses(registry.barcode)
    for registration in registry.barcode:
        provider = registration.provider
        if provider is None:
            continue
        try:
            external = provider.get_by_barcode(barcode)
            if external is not None and external.barcode != barcode:
                raise FoodProviderUnavailable("malformed_response")
        except FoodProviderUnavailable as exc:
            statuses.append(
                FoodProviderStatusResponse(
                    provider=registration.name,
                    status=_provider_failure_status(exc),
                )
            )
            logger.warning(
                "food_provider_barcode_unavailable",
                extra={"provider": registration.name, "reason": exc.reason},
            )
            continue
        statuses.append(
            FoodProviderStatusResponse(
                provider=registration.name,
                status="available",
                result_count=int(external is not None),
            )
        )
        if external is None:
            continue
        try:
            external_item = serialize_provider_food(external)
        except FoodProviderUnavailable as exc:
            statuses[-1] = FoodProviderStatusResponse(
                provider=registration.name,
                status=_provider_failure_status(exc),
            )
            continue
        return FoodBarcodeLookupResponse(
            barcode=barcode,
            status="found",
            source="external",
            external_item=external_item,
            provider_status="available",
            provider_statuses=statuses,
        )

    return FoodBarcodeLookupResponse(
        barcode=barcode,
        status="not_found",
        provider_status=_aggregate_provider_status(statuses),
        provider_statuses=statuses,
    )
