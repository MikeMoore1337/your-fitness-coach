from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from threading import Lock
from typing import Literal, Protocol

from pydantic import ValidationError

from fitminiapp_api.core.config import settings
from fitminiapp_api.schemas.food import ExternalFoodResponse, ExternalFoodSource, ServingUnit

FoodProviderFailureReason = Literal[
    "timeout",
    "network_error",
    "rate_limited",
    "upstream_error",
    "malformed_response",
]


class FoodProviderUnavailable(RuntimeError):
    def __init__(self, reason: FoodProviderFailureReason) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class ProviderFood:
    external_id: str
    name: str
    brand: str | None
    barcode: str | None
    energy_kcal_per_100g: Decimal
    protein_g_per_100g: Decimal
    fat_g_per_100g: Decimal
    carbs_g_per_100g: Decimal
    fiber_g_per_100g: Decimal | None
    standard_serving_amount: Decimal | None
    standard_serving_unit: ServingUnit | None
    standard_serving_weight_g: Decimal | None
    provider: str
    attribution: str
    source_url: str
    license: str
    license_url: str
    name_language: Literal["ru", "en", "und"] = "und"
    is_russian_market: bool = False


class FoodSearchProvider(Protocol):
    name: str

    def search(self, query: str, *, limit: int) -> list[ProviderFood]: ...


class BarcodeFoodProvider(Protocol):
    name: str

    def get_by_barcode(self, barcode: str) -> ProviderFood | None: ...


@dataclass(frozen=True)
class SearchProviderRegistration:
    name: str
    provider: FoodSearchProvider | None


@dataclass(frozen=True)
class BarcodeProviderRegistration:
    name: str
    provider: BarcodeFoodProvider | None


@dataclass(frozen=True)
class FoodProviderRegistry:
    search: tuple[SearchProviderRegistration, ...]
    barcode: tuple[BarcodeProviderRegistration, ...]


class RequestBudget:
    def __init__(self, limit: int, *, window_seconds: float = 60.0) -> None:
        self._limit = limit
        self._window_seconds = window_seconds
        self._timestamps: deque[float] = deque()
        self._lock = Lock()

    def try_acquire(self) -> bool:
        now = time.monotonic()
        cutoff = now - self._window_seconds
        with self._lock:
            while self._timestamps and self._timestamps[0] <= cutoff:
                self._timestamps.popleft()
            if len(self._timestamps) >= self._limit:
                return False
            self._timestamps.append(now)
            return True


def serialize_provider_food(food: ProviderFood) -> ExternalFoodResponse:
    try:
        return ExternalFoodResponse(
            external_id=food.external_id,
            name=food.name,
            brand=food.brand,
            barcode=food.barcode,
            energy_kcal_per_100g=food.energy_kcal_per_100g,
            protein_g_per_100g=food.protein_g_per_100g,
            fat_g_per_100g=food.fat_g_per_100g,
            carbs_g_per_100g=food.carbs_g_per_100g,
            fiber_g_per_100g=food.fiber_g_per_100g,
            standard_serving_amount=food.standard_serving_amount,
            standard_serving_unit=food.standard_serving_unit,
            standard_serving_weight_g=food.standard_serving_weight_g,
            source=ExternalFoodSource.model_validate(
                {
                    "provider": food.provider,
                    "attribution": food.attribution,
                    "source_url": food.source_url,
                    "license": food.license,
                    "license_url": food.license_url,
                }
            ),
        )
    except ValidationError as exc:
        raise FoodProviderUnavailable("malformed_response") from exc


@lru_cache(maxsize=1)
def get_food_provider_registry() -> FoodProviderRegistry:
    from fitminiapp_api.services.open_food_facts import OpenFoodFactsProvider
    from fitminiapp_api.services.usda_food_data_central import USDAFoodDataCentralProvider

    open_food_facts: OpenFoodFactsProvider | None = None
    if settings.food_provider == "open_food_facts":
        open_food_facts = OpenFoodFactsProvider(
            user_agent=settings.open_food_facts_user_agent,
            timeout_seconds=settings.food_provider_timeout_seconds,
        )

    usda: USDAFoodDataCentralProvider | None = None
    if settings.food_usda_enabled:
        usda = USDAFoodDataCentralProvider(
            api_key=settings.usda_fdc_api_key.get_secret_value(),
            timeout_seconds=settings.food_provider_timeout_seconds,
            proxy_url=settings.usda_fdc_proxy_url or None,
        )

    return FoodProviderRegistry(
        search=(
            SearchProviderRegistration("open_food_facts", open_food_facts),
            SearchProviderRegistration("usda_fdc", usda),
        ),
        barcode=(BarcodeProviderRegistration("open_food_facts", open_food_facts),),
    )
