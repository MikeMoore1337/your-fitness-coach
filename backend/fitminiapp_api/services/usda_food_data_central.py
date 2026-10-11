from __future__ import annotations

import time
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from fitminiapp_api.schemas.food import validate_gtin
from fitminiapp_api.services.food_provider import (
    FoodProviderUnavailable,
    ProviderFood,
    RequestBudget,
)
from fitminiapp_api.services.food_search_aliases import (
    USDA_RU_DISPLAY_NAMES_V2,
    generic_food_search_query,
    has_generic_food_alias,
    is_russian_food_query,
    usda_ru_result_ids,
)

_API_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"
_SOURCE_BASE_URL = "https://fdc.nal.usda.gov/fdc-app.html#/food-details"
_LICENSE_URL = "https://creativecommons.org/publicdomain/zero/1.0/"
_DATA_TYPES = ("Foundation", "SR Legacy", "Survey (FNDDS)")
_REQUEST_BUDGET = RequestBudget(15)
_RETRY_DELAY_SECONDS = 0.1
_RUSSIAN_SEARCH_PAGE_SIZE = 200
_REQUIRED_NUTRIENTS = {
    1008: ("energy_kcal_per_100g", "KCAL", Decimal(1000)),
    1003: ("protein_g_per_100g", "G", Decimal(100)),
    1004: ("fat_g_per_100g", "G", Decimal(100)),
    1005: ("carbs_g_per_100g", "G", Decimal(100)),
}
_FIBER_NUTRIENT_ID = 1079


class USDAFoodDataCentralProvider:
    name = "usda_fdc"

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float = 4.0,
        transport: httpx.BaseTransport | None = None,
        proxy_url: str | None = None,
    ) -> None:
        self._api_key = api_key.strip()
        self._timeout = httpx.Timeout(timeout_seconds)
        self._transport = transport
        self._proxy_url = proxy_url

    def search(self, query: str, *, limit: int) -> list[ProviderFood]:
        russian_query = is_russian_food_query(query)
        if russian_query and not has_generic_food_alias(query):
            return []
        normalized = generic_food_search_query(query)
        if len(normalized) < 2:
            return []
        payload = self._request_json(
            json={
                "query": normalized,
                "pageNumber": 1,
                "pageSize": _RUSSIAN_SEARCH_PAGE_SIZE if russian_query else min(limit, 20),
                "dataType": list(_DATA_TYPES),
            }
        )
        raw_foods = payload.get("foods")
        if not isinstance(raw_foods, list):
            raise FoodProviderUnavailable("malformed_response")
        results: list[ProviderFood] = []
        allowed_ru_ids = usda_ru_result_ids(query) if russian_query else frozenset()
        for raw_food in raw_foods:
            food = self._parse_food(raw_food, require_russian_name=russian_query)
            if food is not None and (not russian_query or food.external_id in allowed_ru_ids):
                results.append(food)
        return results[:limit]

    def _request_json(self, *, json: Mapping[str, Any]) -> dict[str, Any]:
        for attempt in range(2):
            if not _REQUEST_BUDGET.try_acquire():
                raise FoodProviderUnavailable("rate_limited")
            try:
                with httpx.Client(
                    headers={"Accept": "application/json"},
                    timeout=self._timeout,
                    transport=self._transport,
                    proxy=self._proxy_url,
                    follow_redirects=False,
                    trust_env=False,
                ) as client:
                    response = client.post(
                        _API_URL,
                        params={"api_key": self._api_key},
                        json=json,
                    )
            except httpx.TimeoutException as exc:
                if attempt == 0:
                    time.sleep(_RETRY_DELAY_SECONDS)
                    continue
                raise FoodProviderUnavailable("timeout") from exc
            except httpx.RequestError as exc:
                if attempt == 0:
                    time.sleep(_RETRY_DELAY_SECONDS)
                    continue
                raise FoodProviderUnavailable("network_error") from exc

            if response.status_code == 429:
                raise FoodProviderUnavailable("rate_limited")
            if response.status_code >= 500:
                if attempt == 0:
                    time.sleep(_RETRY_DELAY_SECONDS)
                    continue
                raise FoodProviderUnavailable("upstream_error")
            if response.status_code >= 400:
                raise FoodProviderUnavailable("upstream_error")
            try:
                payload = response.json()
            except ValueError as exc:
                raise FoodProviderUnavailable("malformed_response") from exc
            if not isinstance(payload, dict):
                raise FoodProviderUnavailable("malformed_response")
            return payload
        raise AssertionError("request retry loop must return or raise")

    @classmethod
    def _parse_food(
        cls,
        raw_food: object,
        *,
        require_russian_name: bool = False,
    ) -> ProviderFood | None:
        if not isinstance(raw_food, dict):
            return None
        external_id = cls._external_id(raw_food.get("fdcId"))
        source_name = cls._text(raw_food.get("description"))
        data_type = cls._text(raw_food.get("dataType"))
        if external_id is None or source_name is None or data_type not in _DATA_TYPES:
            return None
        russian_name = USDA_RU_DISPLAY_NAMES_V2.get(external_id)
        if require_russian_name and russian_name is None:
            return None
        name = russian_name or source_name
        nutrients = cls._nutrients(raw_food.get("foodNutrients"))
        required: dict[str, Decimal] = {}
        for nutrient_id, (field, expected_unit, maximum) in _REQUIRED_NUTRIENTS.items():
            value = cls._nutrient_value(
                nutrients.get(nutrient_id),
                expected_unit=expected_unit,
                maximum=maximum,
            )
            if value is None:
                return None
            required[field] = value
        fiber = cls._nutrient_value(
            nutrients.get(_FIBER_NUTRIENT_ID),
            expected_unit="G",
            maximum=Decimal(100),
        )
        barcode = cls._barcode(raw_food.get("gtinUpc"))
        return ProviderFood(
            external_id=external_id,
            name=name,
            brand=None,
            barcode=barcode,
            energy_kcal_per_100g=required["energy_kcal_per_100g"],
            protein_g_per_100g=required["protein_g_per_100g"],
            fat_g_per_100g=required["fat_g_per_100g"],
            carbs_g_per_100g=required["carbs_g_per_100g"],
            fiber_g_per_100g=fiber,
            standard_serving_amount=None,
            standard_serving_unit=None,
            standard_serving_weight_g=None,
            provider="usda_fdc",
            attribution=(
                "U.S. Department of Agriculture, Agricultural Research Service. FoodData Central"
            ),
            source_url=f"{_SOURCE_BASE_URL}/{external_id}/nutrients",
            license="CC0-1.0",
            license_url=_LICENSE_URL,
            name_language="ru" if russian_name is not None else "en",
        )

    @staticmethod
    def _nutrients(value: object) -> dict[int, Mapping[str, object]]:
        if not isinstance(value, list):
            return {}
        result: dict[int, Mapping[str, object]] = {}
        for item in value:
            if not isinstance(item, dict):
                continue
            raw_id = item.get("nutrientId")
            if not isinstance(raw_id, int):
                nutrient = item.get("nutrient")
                raw_id = nutrient.get("id") if isinstance(nutrient, dict) else None
            if isinstance(raw_id, int):
                result[raw_id] = item
        return result

    @staticmethod
    def _nutrient_value(
        nutrient: Mapping[str, object] | None,
        *,
        expected_unit: str,
        maximum: Decimal,
    ) -> Decimal | None:
        if nutrient is None:
            return None
        raw_unit = nutrient.get("unitName")
        nested_nutrient = nutrient.get("nutrient")
        if raw_unit is None and isinstance(nested_nutrient, dict):
            raw_unit = nested_nutrient.get("unitName")
        if not isinstance(raw_unit, str) or raw_unit.upper() != expected_unit:
            return None
        raw_value = nutrient.get("value", nutrient.get("amount"))
        parsed = USDAFoodDataCentralProvider._decimal(raw_value)
        if parsed is None or parsed < 0 or parsed > maximum:
            return None
        return parsed

    @staticmethod
    def _external_id(value: object) -> str | None:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            return None
        return str(value)

    @staticmethod
    def _text(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = " ".join(value.split())
        return normalized or None

    @staticmethod
    def _barcode(value: object) -> str | None:
        if value is None:
            return None
        try:
            return validate_gtin(str(value))
        except ValueError:
            return None

    @staticmethod
    def _decimal(value: object) -> Decimal | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            parsed = Decimal(str(value))
        except InvalidOperation, ValueError:
            return None
        return parsed if parsed.is_finite() else None
