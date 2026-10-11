from __future__ import annotations

import json
import logging
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from fitminiapp_api.core.config import Settings
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.main import app
from fitminiapp_api.models.food import Food
from fitminiapp_api.services import open_food_facts as off_module
from fitminiapp_api.services import usda_food_data_central as usda_module
from fitminiapp_api.services.food_catalog import (
    clear_food_provider_search_cache,
    deduplicate_provider_foods,
    rank_provider_foods,
)
from fitminiapp_api.services.food_provider import (
    BarcodeProviderRegistration,
    FoodProviderRegistry,
    FoodProviderUnavailable,
    ProviderFood,
    SearchProviderRegistration,
    get_food_provider_registry,
)
from fitminiapp_api.services.food_search_aliases import (
    FOOD_SEARCH_ALIAS_VERSION,
    USDA_RU_DISPLAY_NAMES_V2,
    USDA_RU_DISPLAY_VERSION,
    USDA_RU_RESULT_IDS_V2,
    generic_food_search_query,
)
from fitminiapp_api.services.open_food_facts import OpenFoodFactsProvider
from fitminiapp_api.services.usda_food_data_central import USDAFoodDataCentralProvider


def _auth(client, telegram_user_id: int) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "is_coach": False, "is_admin": False},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _provider_food(
    *,
    barcode: str | None = "3017620422003",
    name: str = "Тестовый продукт",
    provider: str = "fake_food_catalog",
) -> ProviderFood:
    external_id = barcode or f"generic-{name.casefold().replace(' ', '-')}"
    return ProviderFood(
        external_id=external_id,
        name=name,
        brand="Open brand",
        barcode=barcode,
        energy_kcal_per_100g=Decimal("120"),
        protein_g_per_100g=Decimal("5"),
        fat_g_per_100g=Decimal("3"),
        carbs_g_per_100g=Decimal("18"),
        fiber_g_per_100g=Decimal("2"),
        standard_serving_amount=Decimal("30"),
        standard_serving_unit="g",
        standard_serving_weight_g=Decimal("30"),
        provider=provider,
        attribution="Fake catalog contributors",
        source_url=f"https://catalog.example/products/{external_id}",
        license="Test-1.0",
        license_url="https://catalog.example/license",
        name_language="ru",
    )


class FakeFoodProvider:
    name = "fake_food_catalog"

    def __init__(
        self,
        *,
        search_results: list[ProviderFood] | None = None,
        barcode_result: ProviderFood | None = None,
        failure: FoodProviderUnavailable | None = None,
        name: str = "fake_food_catalog",
    ) -> None:
        self.name = name
        self.search_results = search_results or []
        self.barcode_result = barcode_result
        self.failure = failure
        self.search_calls = 0
        self.barcode_calls = 0

    def search(self, query: str, *, limit: int) -> list[ProviderFood]:
        del query, limit
        self.search_calls += 1
        if self.failure is not None:
            raise self.failure
        return self.search_results

    def get_by_barcode(self, barcode: str) -> ProviderFood | None:
        del barcode
        self.barcode_calls += 1
        if self.failure is not None:
            raise self.failure
        return self.barcode_result


def _registry(
    *providers: FakeFoodProvider,
    disabled_search: tuple[str, ...] = (),
) -> FoodProviderRegistry:
    return FoodProviderRegistry(
        search=(
            *(SearchProviderRegistration(provider.name, provider) for provider in providers),
            *(SearchProviderRegistration(name, None) for name in disabled_search),
        ),
        barcode=tuple(
            BarcodeProviderRegistration(provider.name, provider) for provider in providers
        ),
    )


def _override_provider(provider: FakeFoodProvider | None) -> None:
    registry = (
        _registry(provider)
        if provider is not None
        else _registry(disabled_search=("open_food_facts", "usda_fdc"))
    )
    app.dependency_overrides[get_food_provider_registry] = lambda: registry


def _clear_provider_override() -> None:
    app.dependency_overrides.pop(get_food_provider_registry, None)
    clear_food_provider_search_cache()


def test_food_search_skips_external_when_local_results_fill_budget(client) -> None:
    headers = _auth(client, 19_001)
    created = client.post(
        "/api/v1/nutrition/foods",
        headers=headers,
        json={
            "name": "Локальный кефир",
            "energy_kcal_per_100g": "52",
            "protein_g_per_100g": "3",
            "fat_g_per_100g": "2.5",
            "carbs_g_per_100g": "4",
        },
    )
    assert created.status_code == 201
    fake = FakeFoodProvider(search_results=[_provider_food()])
    _override_provider(fake)
    try:
        local = client.get(
            "/api/v1/nutrition/foods/search",
            headers=headers,
            params={"q": "кефир", "include_external": "true", "limit": 1},
        )
        not_requested = client.get(
            "/api/v1/nutrition/foods/search",
            headers=headers,
            params={"q": "редкий продукт"},
        )
        paginated = client.get(
            "/api/v1/nutrition/foods/search",
            headers=headers,
            params={"q": "редкий продукт", "include_external": "true", "offset": 1},
        )
    finally:
        _clear_provider_override()

    assert local.status_code == 200
    assert [item["id"] for item in local.json()["items"]] == [created.json()["id"]]
    assert local.json()["external_items"] == []
    assert local.json()["provider_status"] == "not_needed"
    assert not_requested.json()["provider_status"] == "not_requested"
    assert paginated.json()["provider_status"] == "not_requested"
    assert fake.search_calls == 0


def test_food_search_supplements_local_results_with_multiple_providers(client) -> None:
    headers = _auth(client, 19_011)
    created = client.post(
        "/api/v1/nutrition/foods",
        headers=headers,
        json={
            "name": "Рис домашний",
            "energy_kcal_per_100g": "130",
            "protein_g_per_100g": "2.7",
            "fat_g_per_100g": "0.3",
            "carbs_g_per_100g": "28",
        },
    )
    assert created.status_code == 201
    off = FakeFoodProvider(
        name="open_food_facts",
        search_results=[
            _provider_food(name="Рис длиннозёрный", provider="open_food_facts"),
            _provider_food(
                name="Рис круглозёрный",
                barcode="4006381333931",
                provider="open_food_facts",
            ),
        ],
    )
    usda = FakeFoodProvider(
        name="usda_fdc",
        search_results=[
            _provider_food(
                name="Рис белый приготовленный, без добавления масла",
                barcode=None,
                provider="usda_fdc",
            ),
            _provider_food(
                name="Рис бурый приготовленный, без добавления масла",
                barcode=None,
                provider="usda_fdc",
            ),
            _provider_food(
                name="Рис дикий приготовленный, без добавления масла",
                barcode=None,
                provider="usda_fdc",
            ),
        ],
    )
    registry = _registry(off, usda)
    app.dependency_overrides[get_food_provider_registry] = lambda: registry
    try:
        response = client.get(
            "/api/v1/nutrition/foods/search",
            headers=headers,
            params={"q": "рис", "include_external": "true", "limit": 6},
        )
    finally:
        _clear_provider_override()

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["items"]] == [created.json()["id"]]
    assert {item["source"]["provider"] for item in payload["external_items"]} == {
        "open_food_facts",
        "usda_fdc",
    }
    assert len(payload["external_items"]) == 5
    assert all("рис" in item["name"].casefold() for item in payload["external_items"])
    assert payload["provider_status"] == "available"
    assert [status["provider"] for status in payload["provider_statuses"]] == [
        "open_food_facts",
        "usda_fdc",
    ]
    assert off.search_calls == usda.search_calls == 1


def test_food_search_returns_separate_attributed_provider_results(client) -> None:
    headers = _auth(client, 19_002)
    fake = FakeFoodProvider(search_results=[_provider_food()])
    _override_provider(fake)
    try:
        response = client.get(
            "/api/v1/nutrition/foods/search",
            headers=headers,
            params={"q": "редкий продукт", "include_external": "true"},
        )
    finally:
        _clear_provider_override()

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == []
    assert payload["provider_status"] == "available"
    assert payload["external_items"][0]["external_id"] == "3017620422003"
    assert payload["external_items"][0]["source"] == {
        "provider": "fake_food_catalog",
        "attribution": "Fake catalog contributors",
        "source_url": "https://catalog.example/products/3017620422003",
        "license": "Test-1.0",
        "license_url": "https://catalog.example/license",
    }
    assert fake.search_calls == 1


def test_barcode_lookup_is_local_first_and_private_scope_is_preserved(client) -> None:
    owner_headers = _auth(client, 19_003)
    other_headers = _auth(client, 19_004)
    barcode = "4006381333931"
    created = client.post(
        "/api/v1/nutrition/foods",
        headers=owner_headers,
        json={
            "name": "Личный продукт",
            "barcode": barcode,
            "energy_kcal_per_100g": "80",
            "protein_g_per_100g": "4",
            "fat_g_per_100g": "2",
            "carbs_g_per_100g": "12",
        },
    )
    assert created.status_code == 201
    fake = FakeFoodProvider(barcode_result=_provider_food(barcode=barcode))
    _override_provider(fake)
    try:
        owner_result = client.get(
            f"/api/v1/nutrition/foods/barcode/{barcode}", headers=owner_headers
        )
        other_result = client.get(
            f"/api/v1/nutrition/foods/barcode/{barcode}", headers=other_headers
        )
    finally:
        _clear_provider_override()

    owner_payload = owner_result.json()
    other_payload = other_result.json()
    assert owner_payload["barcode"] == barcode
    assert owner_payload["status"] == "found"
    assert owner_payload["source"] == "local"
    assert owner_payload["local_item"]["id"] == created.json()["id"]
    assert owner_payload["external_item"] is None
    assert owner_payload["provider_status"] == "not_needed"
    assert other_payload["barcode"] == barcode
    assert other_payload["status"] == "found"
    assert other_payload["source"] == "external"
    assert other_payload["local_item"] is None
    assert other_payload["external_item"]["barcode"] == barcode
    assert other_payload["external_item"]["source"] == {
        "provider": "fake_food_catalog",
        "attribution": "Fake catalog contributors",
        "source_url": f"https://catalog.example/products/{barcode}",
        "license": "Test-1.0",
        "license_url": "https://catalog.example/license",
    }
    assert other_payload["provider_status"] == "available"
    assert fake.barcode_calls == 1


@pytest.mark.parametrize(
    ("failure", "expected_status"),
    [
        (FoodProviderUnavailable("timeout"), "unavailable"),
        (FoodProviderUnavailable("rate_limited"), "rate_limited"),
    ],
)
def test_provider_failure_falls_back_without_touching_local_foods(
    client,
    failure: FoodProviderUnavailable,
    expected_status: str,
    caplog,
) -> None:
    headers = _auth(client, 19_005)
    fake = FakeFoodProvider(failure=failure)
    _override_provider(fake)
    try:
        response = client.get(
            "/api/v1/nutrition/foods/search",
            headers=headers,
            params={"q": "не найдено", "include_external": "true"},
        )
    finally:
        _clear_provider_override()

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["external_items"] == []
    assert response.json()["provider_status"] == expected_status
    provider_record = next(
        record for record in caplog.records if record.message == "food_provider_search_unavailable"
    )
    assert provider_record.provider == "fake_food_catalog"
    assert provider_record.reason == failure.reason
    with get_session_context() as db:
        assert db.query(Food).count() == 0


def test_partial_provider_failure_preserves_other_provider_results(client) -> None:
    headers = _auth(client, 19_012)
    unavailable = FakeFoodProvider(
        name="open_food_facts",
        failure=FoodProviderUnavailable("timeout"),
    )
    available = FakeFoodProvider(
        name="usda_fdc",
        search_results=[
            _provider_food(
                name="Куриная грудка, способ приготовления не указан, без кожи",
                barcode=None,
                provider="usda_fdc",
            )
        ],
    )
    registry = _registry(unavailable, available)
    app.dependency_overrides[get_food_provider_registry] = lambda: registry
    try:
        response = client.get(
            "/api/v1/nutrition/foods/search",
            headers=headers,
            params={"q": "куриная грудка", "include_external": "true"},
        )
    finally:
        _clear_provider_override()

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_status"] == "available"
    assert [item["source"]["provider"] for item in payload["external_items"]] == ["usda_fdc"]
    assert [(item["provider"], item["status"]) for item in payload["provider_statuses"]] == [
        ("open_food_facts", "unavailable"),
        ("usda_fdc", "available"),
    ]


def test_provider_search_uses_short_process_local_cache(client, caplog) -> None:
    caplog.set_level(logging.INFO, logger="app")
    headers = _auth(client, 19_014)
    fake = FakeFoodProvider(search_results=[_provider_food(name="Cached result")])
    _override_provider(fake)
    try:
        for _ in range(2):
            response = client.get(
                "/api/v1/nutrition/foods/search",
                headers=headers,
                params={"q": "cached result", "include_external": "true"},
            )
            assert response.status_code == 200
    finally:
        _clear_provider_override()

    assert fake.search_calls == 1
    assert any(record.message == "food_provider_search_cache_hit" for record in caplog.records)


def test_russian_search_never_exposes_unlocalized_external_title(client) -> None:
    headers = _auth(client, 19_016)
    localized = _provider_food(name="Русское название", barcode=None)
    english_only = ProviderFood(
        **{
            **_provider_food(name="English only", barcode=None).__dict__,
            "external_id": "english-only",
            "name_language": "en",
        }
    )
    fake = FakeFoodProvider(search_results=[english_only, localized])
    _override_provider(fake)
    try:
        response = client.get(
            "/api/v1/nutrition/foods/search",
            headers=headers,
            params={"q": "любой продукт", "include_external": "true"},
        )
    finally:
        _clear_provider_override()

    assert response.status_code == 200
    assert [item["name"] for item in response.json()["external_items"]] == ["Русское название"]
    assert response.json()["provider_statuses"][0]["result_count"] == 1


def test_external_deduplication_uses_gtin_provider_identity_and_bounded_weak_identity() -> None:
    barcode = _provider_food(name="Same GTIN")
    same_barcode_other_provider = ProviderFood(
        **{
            **barcode.__dict__,
            "provider": "second_provider",
            "external_id": "second-1",
        }
    )
    generic = _provider_food(name="Rice, cooked", barcode=None)
    same_generic_other_provider = ProviderFood(
        **{
            **generic.__dict__,
            "provider": "second_provider",
            "external_id": "second-2",
        }
    )
    distinct_generic = ProviderFood(
        **{
            **generic.__dict__,
            "provider": "second_provider",
            "external_id": "second-3",
            "carbs_g_per_100g": Decimal("19"),
        }
    )

    kept, removed = deduplicate_provider_foods(
        [],
        [
            barcode,
            barcode,
            same_barcode_other_provider,
            generic,
            same_generic_other_provider,
            distinct_generic,
        ],
    )

    assert removed == 3
    assert [(item.provider, item.external_id) for item in kept] == [
        ("fake_food_catalog", "3017620422003"),
        ("fake_food_catalog", "generic-rice,-cooked"),
        ("second_provider", "second-3"),
    ]


def test_external_ranking_is_deterministic_and_not_provider_priority() -> None:
    exact_late_provider = _provider_food(name="Chicken breast", barcode=None)
    exact_late_provider = ProviderFood(
        **{**exact_late_provider.__dict__, "provider": "z_provider", "external_id": "z-1"}
    )
    weak_early_provider = _provider_food(name="Chicken breast salad", barcode=None)
    weak_early_provider = ProviderFood(
        **{**weak_early_provider.__dict__, "provider": "a_provider", "external_id": "a-1"}
    )

    ranked = rank_provider_foods([weak_early_provider, exact_late_provider], "куриная грудка")

    assert [item.external_id for item in ranked] == ["z-1", "a-1"]


def test_external_ranking_prefers_russian_market_for_equal_russian_matches() -> None:
    global_food = _provider_food(name="Рис басмати", barcode=None)
    russian_market_food = ProviderFood(
        **{
            **_provider_food(name="Рис жасмин", barcode=None).__dict__,
            "is_russian_market": True,
        }
    )

    ranked = rank_provider_foods([global_food, russian_market_food], "рис")

    assert ranked[0].name == "Рис жасмин"


def test_external_import_keeps_source_metadata_without_fuzzy_persistent_merge(client) -> None:
    headers = _auth(client, 19_013)
    common = {
        "name": "Rice, cooked",
        "energy_kcal_per_100g": "130",
        "protein_g_per_100g": "2.7",
        "fat_g_per_100g": "0.3",
        "carbs_g_per_100g": "28",
    }
    source = {
        "provider": "usda_fdc",
        "attribution": "USDA FoodData Central",
        "source_url": "https://fdc.nal.usda.gov/fdc-app.html#/food-details/1/nutrients",
        "license": "CC0-1.0",
        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
    }
    first = client.post(
        "/api/v1/nutrition/foods",
        headers=headers,
        json={**common, "external_source": {**source, "external_id": "1"}},
    )
    second = client.post(
        "/api/v1/nutrition/foods",
        headers=headers,
        json={**common, "external_source": {**source, "external_id": "2"}},
    )

    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    with get_session_context() as db:
        stored = db.query(Food).filter(Food.source_name == "usda_fdc").order_by(Food.id).all()
        assert [food.external_id for food in stored] == ["1", "2"]
        assert all(food.source_name == "usda_fdc" for food in stored)
        assert all(food.source_license == "CC0-1.0" for food in stored)


def test_disabled_provider_and_invalid_barcode_have_safe_contract(client) -> None:
    headers = _auth(client, 19_006)
    _override_provider(None)
    try:
        search = client.get(
            "/api/v1/nutrition/foods/search",
            headers=headers,
            params={"q": "не найдено", "include_external": "true"},
        )
        disabled_barcode = client.get(
            "/api/v1/nutrition/foods/barcode/3017620422003",
            headers=headers,
        )
        barcode = client.get("/api/v1/nutrition/foods/barcode/12345678", headers=headers)
    finally:
        _clear_provider_override()

    assert search.status_code == 200
    assert search.json()["provider_status"] == "disabled"
    assert disabled_barcode.status_code == 200
    assert disabled_barcode.json() == {
        "barcode": "3017620422003",
        "status": "not_found",
        "source": None,
        "local_item": None,
        "external_item": None,
        "provider_status": "disabled",
        "provider_statuses": [],
    }
    assert barcode.status_code == 422


@pytest.mark.parametrize(
    ("failure", "expected_provider_status"),
    [
        (FoodProviderUnavailable("timeout"), "unavailable"),
        (FoodProviderUnavailable("rate_limited"), "rate_limited"),
        (FoodProviderUnavailable("malformed_response"), "unavailable"),
    ],
)
def test_barcode_provider_failure_returns_safe_not_found_contract(
    client,
    failure: FoodProviderUnavailable,
    expected_provider_status: str,
) -> None:
    headers = _auth(client, 19_007)
    fake = FakeFoodProvider(failure=failure)
    _override_provider(fake)
    try:
        response = client.get(
            "/api/v1/nutrition/foods/barcode/3017620422003",
            headers=headers,
        )
    finally:
        _clear_provider_override()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "not_found"
    assert payload["source"] is None
    assert payload["local_item"] is None
    assert payload["external_item"] is None
    assert payload["provider_status"] == expected_provider_status
    assert "detail" not in payload
    assert fake.barcode_calls == 1


def test_barcode_not_found_can_flow_into_manual_user_food_creation(client) -> None:
    headers = _auth(client, 19_008)
    barcode = "3017620422003"
    fake = FakeFoodProvider()
    _override_provider(fake)
    try:
        not_found = client.get(
            f"/api/v1/nutrition/foods/barcode/{barcode}",
            headers=headers,
        )
        created = client.post(
            "/api/v1/nutrition/foods",
            headers=headers,
            json={
                "name": "Продукт, добавленный вручную",
                "barcode": not_found.json()["barcode"],
                "energy_kcal_per_100g": "100",
                "protein_g_per_100g": "5",
                "fat_g_per_100g": "3",
                "carbs_g_per_100g": "15",
            },
        )
        local = client.get(
            f"/api/v1/nutrition/foods/barcode/{barcode}",
            headers=headers,
        )
    finally:
        _clear_provider_override()

    assert not_found.status_code == 200
    assert not_found.json()["status"] == "not_found"
    assert not_found.json()["provider_status"] == "available"
    assert created.status_code == 201
    assert local.status_code == 200
    assert local.json()["status"] == "found"
    assert local.json()["source"] == "local"
    assert local.json()["local_item"]["id"] == created.json()["id"]
    assert fake.barcode_calls == 1


def test_generic_search_provider_is_not_called_for_barcode_lookup(client) -> None:
    headers = _auth(client, 19_015)
    generic = FakeFoodProvider(
        name="usda_fdc",
        barcode_result=_provider_food(provider="usda_fdc"),
    )
    registry = FoodProviderRegistry(
        search=(SearchProviderRegistration("usda_fdc", generic),),
        barcode=(BarcodeProviderRegistration("open_food_facts", None),),
    )
    app.dependency_overrides[get_food_provider_registry] = lambda: registry
    try:
        response = client.get(
            "/api/v1/nutrition/foods/barcode/3017620422003",
            headers=headers,
        )
    finally:
        _clear_provider_override()

    assert response.status_code == 200
    assert response.json()["status"] == "not_found"
    assert response.json()["provider_status"] == "disabled"
    assert generic.barcode_calls == 0


def test_barcode_lookup_rejects_mismatched_provider_result(client) -> None:
    headers = _auth(client, 19_009)
    requested_barcode = "3017620422003"
    fake = FakeFoodProvider(barcode_result=_provider_food(barcode="4006381333931"))
    _override_provider(fake)
    try:
        response = client.get(
            f"/api/v1/nutrition/foods/barcode/{requested_barcode}",
            headers=headers,
        )
    finally:
        _clear_provider_override()

    assert response.status_code == 200
    assert response.json()["status"] == "not_found"
    assert response.json()["provider_status"] == "unavailable"
    assert response.json()["external_item"] is None


@pytest.mark.parametrize(
    "barcode",
    [
        "1234567",
        "123456789012345",
        "3017620422004",
        "30176204220A3",
    ],
)
def test_barcode_lookup_rejects_invalid_manual_input(client, barcode: str) -> None:
    headers = _auth(client, 19_010)

    response = client.get(f"/api/v1/nutrition/foods/barcode/{barcode}", headers=headers)

    assert response.status_code == 422


def _usda_food(
    *,
    fdc_id: int = 2705954,
    description: str = "Chicken breast, NS as to cooking method, skin not eaten",
    include_carbs: bool = True,
    energy_kcal: int = 165,
) -> dict[str, object]:
    nutrients = [
        {"nutrientId": 1008, "unitName": "KCAL", "value": energy_kcal},
        {"nutrientId": 1003, "unitName": "G", "value": 31},
        {"nutrientId": 1004, "unitName": "G", "value": 3.6},
        {"nutrientId": 1079, "unitName": "G", "value": 0},
    ]
    if include_carbs:
        nutrients.append({"nutrientId": 1005, "unitName": "G", "value": 0})
    return {
        "fdcId": fdc_id,
        "description": description,
        "dataType": "Survey (FNDDS)",
        "foodNutrients": nutrients,
    }


def test_usda_search_translates_versioned_ru_alias_and_normalizes_per_100g() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, request=request, json={"foods": [_usda_food()]})

    provider = USDAFoodDataCentralProvider(
        api_key="test-usda-key",
        transport=httpx.MockTransport(handler),
    )
    results = provider.search("  КУРИНАЯ   ГРУДКА  ", limit=50)

    assert FOOD_SEARCH_ALIAS_VERSION == "ru-en-v4"
    assert USDA_RU_DISPLAY_VERSION == "fdc-fndds-2021-2023-ru-v2"
    assert generic_food_search_query("куриная грудка") == "chicken breast"
    assert len(results) == 1
    assert results[0].name == ("Куриная грудка, способ приготовления не указан, без кожи")
    assert results[0].name_language == "ru"
    assert results[0].barcode is None
    assert results[0].external_id == "2705954"
    assert results[0].energy_kcal_per_100g == Decimal("165")
    assert results[0].source_url.endswith("/2705954/nutrients")
    payload = json.loads(requests[0].content)
    assert payload == {
        "query": "chicken breast",
        "pageNumber": 1,
        "pageSize": 200,
        "dataType": ["Foundation", "SR Legacy", "Survey (FNDDS)"],
    }
    assert requests[0].url.params["api_key"] == "test-usda-key"


def test_usda_russian_search_skips_unreviewed_names_and_unknown_queries() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            request=request,
            json={"foods": [_usda_food(fdc_id=9999999, description="Unreviewed food")]},
        )

    provider = USDAFoodDataCentralProvider(
        api_key="test-usda-key",
        transport=httpx.MockTransport(handler),
    )

    assert provider.search("куриная грудка", limit=5) == []
    assert provider.search("неизвестный русский продукт", limit=5) == []
    assert calls == 1


def test_usda_russian_search_rejects_reviewed_but_irrelevant_fdc_identity() -> None:
    provider = USDAFoodDataCentralProvider(
        api_key="test-usda-key",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                request=request,
                json={
                    "foods": [
                        _usda_food(
                            fdc_id=2708408,
                            description="Rice, white, cooked, no added fat",
                        )
                    ]
                },
            )
        ),
    )

    assert provider.search("куриная грудка", limit=5) == []


def test_usda_russian_search_returns_reviewed_rice_variants() -> None:
    rice_foods = [
        _usda_food(
            fdc_id=2708403,
            description="Rice, white, cooked, NS as to fat",
        ),
        _usda_food(
            fdc_id=2708408,
            description="Rice, white, cooked, no added fat",
        ),
        _usda_food(
            fdc_id=2708414,
            description="Rice, brown, cooked, no added fat",
        ),
        _usda_food(
            fdc_id=2708424,
            description="Rice, wild, 100%, cooked, no added fat",
        ),
    ]
    provider = USDAFoodDataCentralProvider(
        api_key="test-usda-key",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, request=request, json={"foods": rice_foods})
        ),
    )

    results = provider.search("рис", limit=20)

    assert len(results) == 4
    assert all(item.name_language == "ru" for item in results)
    assert all("рис" in item.name.casefold() for item in results)
    assert {item.name for item in results} == {
        "Рис белый приготовленный, масло не указано",
        "Рис белый приготовленный, без добавления масла",
        "Рис бурый приготовленный, без добавления масла",
        "Рис дикий приготовленный, без добавления масла",
    }


def test_usda_russian_search_keeps_food_preparation_states_separate() -> None:
    potato_foods = [
        _usda_food(fdc_id=2709383, description="Potato, baked, NFS", energy_kcal=93),
        _usda_food(fdc_id=2709385, description="Potato, boiled, NFS", energy_kcal=87),
        _usda_food(
            fdc_id=2709458,
            description="Potato, french fries, from fresh, fried",
            energy_kcal=289,
        ),
        _usda_food(
            fdc_id=2709474,
            description="Potato, home fries, from fresh",
            energy_kcal=185,
        ),
        _usda_food(fdc_id=2709492, description="Potato, mashed, NFS", energy_kcal=113),
    ]
    provider = USDAFoodDataCentralProvider(
        api_key="test-usda-key",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, request=request, json={"foods": potato_foods})
        ),
    )

    all_states = provider.search("картофель", limit=20)
    fried = provider.search("картофель жареный", limit=20)

    assert {item.name for item in all_states} == {
        "Картофель запечённый, способ приготовления не указан",
        "Картофель отварной, способ приготовления не указан",
        "Картофель фри из свежего картофеля, жареный",
        "Картофель жареный по-домашнему из свежего картофеля",
        "Картофельное пюре, способ приготовления не указан",
    }
    assert [item.name for item in fried] == ["Картофель жареный по-домашнему из свежего картофеля"]
    assert {item.energy_kcal_per_100g for item in all_states} == {
        Decimal("87"),
        Decimal("93"),
        Decimal("113"),
        Decimal("185"),
        Decimal("289"),
    }


def test_usda_russian_search_keeps_preparation_states_across_food_categories() -> None:
    foods = [
        _usda_food(fdc_id=2705956, description="Chicken breast, baked", energy_kcal=165),
        _usda_food(fdc_id=2705966, description="Chicken breast, stewed", energy_kcal=151),
        _usda_food(fdc_id=2705972, description="Chicken breast, sauteed", energy_kcal=187),
        _usda_food(fdc_id=2707152, description="Egg, whole, raw", energy_kcal=143),
        _usda_food(fdc_id=2707154, description="Egg, whole, boiled", energy_kcal=155),
        _usda_food(fdc_id=2707156, description="Egg, whole, fried, no added fat", energy_kcal=174),
        _usda_food(fdc_id=2707158, description="Egg, whole, fried with oil", energy_kcal=196),
        _usda_food(fdc_id=2707159, description="Egg, whole, fried with butter", energy_kcal=196),
        _usda_food(fdc_id=2708381, description="Oatmeal, made with water", energy_kcal=71),
        _usda_food(fdc_id=2708383, description="Oatmeal, made with milk", energy_kcal=102),
        _usda_food(fdc_id=2709215, description="Apple, raw", energy_kcal=52),
        _usda_food(fdc_id=2709220, description="Apple, baked", energy_kcal=95),
        _usda_food(fdc_id=2709719, description="Tomatoes, raw", energy_kcal=18),
        _usda_food(fdc_id=2709721, description="Tomatoes, fresh, cooked", energy_kcal=21),
        _usda_food(fdc_id=2709784, description="Cucumber, raw", energy_kcal=15),
        _usda_food(fdc_id=2709928, description="Cucumber, cooked", energy_kcal=20),
    ]
    provider = USDAFoodDataCentralProvider(
        api_key="test-usda-key",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, request=request, json={"foods": foods})
        ),
    )

    chicken = provider.search("куриная грудка", limit=20)
    fried_eggs = provider.search("яйцо жареное", limit=20)
    oatmeal = provider.search("овсянка", limit=20)
    apples = provider.search("яблоко", limit=20)
    tomatoes = provider.search("помидор", limit=20)
    cucumbers = provider.search("огурец", limit=20)

    assert {item.name for item in chicken} == {
        "Куриная грудка запечённая или приготовленная на гриле, без кожи",
        "Куриная грудка тушёная, без кожи",
        "Куриная грудка жареная без панировки, без кожи",
    }
    assert {item.name for item in fried_eggs} == {
        "Яйцо целое жареное без добавления масла",
        "Яйцо целое жареное с растительным маслом",
        "Яйцо целое жареное со сливочным маслом",
    }
    assert {item.energy_kcal_per_100g for item in fried_eggs} == {
        Decimal("174"),
        Decimal("196"),
    }
    assert {item.name for item in oatmeal} == {
        "Овсянка на воде, без добавления масла",
        "Овсянка на молоке, без добавления масла",
    }
    assert {item.name for item in apples} == {"Яблоко сырое", "Яблоко запечённое"}
    assert {item.name for item in tomatoes} == {
        "Помидоры сырые",
        "Помидоры свежие приготовленные",
    }
    assert {item.name for item in cucumbers} == {"Огурец сырой", "Огурец приготовленный"}


def test_usda_rejects_missing_or_wrong_unit_nutrients_and_malformed_payload() -> None:
    responses = iter(
        [
            {"foods": [_usda_food(include_carbs=False)]},
            {"foods": [{**_usda_food(), "dataType": "Branded"}]},
            {},
        ]
    )
    provider = USDAFoodDataCentralProvider(
        api_key="test-usda-key",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, request=request, json=next(responses))
        ),
    )

    assert provider.search("chicken", limit=5) == []
    assert provider.search("chicken", limit=5) == []
    with pytest.raises(FoodProviderUnavailable) as malformed:
        provider.search("chicken", limit=5)
    assert malformed.value.reason == "malformed_response"


@pytest.mark.parametrize(
    ("responses", "expected_reason", "expected_calls"),
    [
        ([429], "rate_limited", 1),
        ([503, 503], "upstream_error", 2),
    ],
)
def test_usda_handles_rate_limit_and_bounded_5xx_retry(
    monkeypatch,
    responses: list[int],
    expected_reason: str,
    expected_calls: int,
) -> None:
    monkeypatch.setattr(usda_module, "_REQUEST_BUDGET", usda_module.RequestBudget(15))
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        status_code = responses[min(calls, len(responses) - 1)]
        calls += 1
        return httpx.Response(status_code, request=request)

    provider = USDAFoodDataCentralProvider(
        api_key="test-usda-key",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(FoodProviderUnavailable) as exc_info:
        provider.search("chicken", limit=5)
    assert exc_info.value.reason == expected_reason
    assert calls == expected_calls


def test_versioned_coverage_corpus_matches_deterministic_aliases() -> None:
    fixture = Path(__file__).parent / "fixtures" / "food_search_coverage_v2.json"
    corpus = json.loads(fixture.read_text(encoding="utf-8"))

    assert corpus["version"] == "food-search-coverage-v2"
    generic = [item for item in corpus["queries"] if item["external_alias"] is not None]
    assert len(generic) >= 33
    assert all(generic_food_search_query(item["ru"]) == item["external_alias"] for item in generic)
    assert all(
        external_id in USDA_RU_DISPLAY_NAMES_V2
        for external_ids in USDA_RU_RESULT_IDS_V2.values()
        for external_id in external_ids
    )
    assert len(USDA_RU_RESULT_IDS_V2["картофель"]) == 24
    assert {
        "картофель запеченный",
        "картофель жареный",
        "картофель отварной",
        "картофель фри",
        "картофельное пюре",
    }.issubset(USDA_RU_RESULT_IDS_V2)
    assert len(USDA_RU_RESULT_IDS_V2["рис"]) == 23
    assert all(
        "рис" in USDA_RU_DISPLAY_NAMES_V2[external_id].casefold()
        for external_id in USDA_RU_RESULT_IDS_V2["рис"]
    )
    assert {
        "банан",
        "говядина",
        "индейка",
        "куриная грудка",
        "овсянка",
        "огурец",
        "помидор",
        "яблоко",
        "яйцо",
    }.issubset(USDA_RU_RESULT_IDS_V2)
    assert all(
        len(USDA_RU_RESULT_IDS_V2[query]) >= 2
        for query in {
            "банан",
            "говядина",
            "индейка",
            "куриная грудка",
            "овсянка",
            "огурец",
            "помидор",
            "яблоко",
            "яйцо",
        }
    )
    assert all("жир" not in name.casefold() for name in USDA_RU_DISPLAY_NAMES_V2.values())


def test_provider_registry_order_and_barcode_capability_are_explicit() -> None:
    registry = get_food_provider_registry()

    assert [registration.name for registration in registry.search] == [
        "open_food_facts",
        "usda_fdc",
    ]
    assert [registration.name for registration in registry.barcode] == ["open_food_facts"]


def _off_product() -> dict[str, object]:
    return {
        "code": "3017620422003",
        "product_name": "Open product",
        "product_name_en": "Open product",
        "product_name_ru": "Открытый продукт",
        "countries_tags": ["en:russia"],
        "brands": "Open brand",
        "serving_quantity": 25,
        "serving_quantity_unit": "g",
        "nutriments": {
            "energy-kcal_100g": 120,
            "proteins_100g": 5,
            "fat_100g": 3,
            "carbohydrates_100g": 18,
            "fiber_100g": 2,
        },
    }


def test_open_food_facts_contract_uses_user_agent_and_parses_search_and_barcode() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "search.openfoodfacts.org":
            return httpx.Response(200, request=request, json={"hits": [_off_product()]})
        return httpx.Response(
            200,
            request=request,
            json={"status": 1, "product": _off_product()},
        )

    provider = OpenFoodFactsProvider(
        user_agent="YourFitnessCoach/1.0 (ops@example.test)",
        transport=httpx.MockTransport(handler),
    )
    search_results = provider.search("open product", limit=50)
    barcode_result = provider.get_by_barcode("3017620422003")

    assert len(search_results) == 1
    assert search_results[0].name == "Открытый продукт"
    assert search_results[0].name_language == "ru"
    assert search_results[0].is_russian_market is True
    assert search_results[0].source_url.endswith("/product/3017620422003")
    assert barcode_result is not None
    assert barcode_result.standard_serving_weight_g == Decimal("25")
    assert all(
        request.headers["user-agent"] == "YourFitnessCoach/1.0 (ops@example.test)"
        for request in requests
    )
    assert requests[0].method == "POST"
    search_payload = json.loads(requests[0].content)
    assert search_payload["q"] == "open product"
    assert requests[1].url.path == "/api/v3.6/product/3017620422003.json"


def test_open_food_facts_russian_search_requires_provider_ru_name() -> None:
    product = _off_product()
    product.pop("product_name_ru")
    provider = OpenFoodFactsProvider(
        user_agent="YourFitnessCoach/1.0 (ops@example.test)",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, request=request, json={"hits": [product]})
        ),
    )

    assert provider.search("русский запрос", limit=10) == []


def test_open_food_facts_accepts_primary_name_declared_as_russian() -> None:
    product = _off_product()
    product.pop("product_name_ru")
    product["product_name"] = "Русское основное название"
    product["lang"] = "ru"
    provider = OpenFoodFactsProvider(
        user_agent="YourFitnessCoach/1.0 (ops@example.test)",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, request=request, json={"hits": [product]})
        ),
    )

    results = provider.search("русский запрос", limit=10)

    assert [item.name for item in results] == ["Русское основное название"]
    assert results[0].name_language == "ru"


@pytest.mark.parametrize(
    ("responses", "expected_reason", "expected_calls"),
    [
        ([429], "rate_limited", 1),
        ([503, 503], "upstream_error", 2),
    ],
)
def test_open_food_facts_handles_rate_limit_and_bounded_5xx_retry(
    responses: list[int], expected_reason: str, expected_calls: int
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        status_code = responses[min(calls, len(responses) - 1)]
        calls += 1
        return httpx.Response(status_code, request=request)

    provider = OpenFoodFactsProvider(
        user_agent="YourFitnessCoach/1.0 (ops@example.test)",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(FoodProviderUnavailable) as exc_info:
        provider.search("product", limit=10)
    assert exc_info.value.reason == expected_reason
    assert calls == expected_calls


def test_open_food_facts_enforces_documented_search_budget(monkeypatch) -> None:
    monkeypatch.setattr(off_module, "_SEARCH_REQUEST_BUDGET", off_module._RequestBudget(1))
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, request=request, json={"hits": []})

    provider = OpenFoodFactsProvider(
        user_agent="YourFitnessCoach/1.0 (ops@example.test)",
        transport=httpx.MockTransport(handler),
    )
    assert provider.search("first", limit=10) == []
    with pytest.raises(FoodProviderUnavailable) as exc_info:
        provider.search("second", limit=10)
    assert exc_info.value.reason == "rate_limited"
    assert calls == 1


def test_open_food_facts_retries_timeout_and_rejects_malformed_response() -> None:
    timeout_calls = 0

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        nonlocal timeout_calls
        timeout_calls += 1
        raise httpx.ReadTimeout("upstream timeout", request=request)

    timeout_provider = OpenFoodFactsProvider(
        user_agent="YourFitnessCoach/1.0 (ops@example.test)",
        transport=httpx.MockTransport(timeout_handler),
    )
    with pytest.raises(FoodProviderUnavailable) as timeout_error:
        timeout_provider.search("product", limit=10)
    assert timeout_error.value.reason == "timeout"
    assert timeout_calls == 2

    malformed_provider = OpenFoodFactsProvider(
        user_agent="YourFitnessCoach/1.0 (ops@example.test)",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, request=request, json={})
        ),
    )
    with pytest.raises(FoodProviderUnavailable) as malformed_error:
        malformed_provider.search("product", limit=10)
    assert malformed_error.value.reason == "malformed_response"


def test_open_food_facts_retries_network_error_with_safe_classification() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("upstream unavailable", request=request)

    provider = OpenFoodFactsProvider(
        user_agent="YourFitnessCoach/1.0 (ops@example.test)",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(FoodProviderUnavailable) as exc_info:
        provider.get_by_barcode("3017620422003")
    assert exc_info.value.reason == "network_error"
    assert calls == 2


def test_open_food_facts_requires_identifying_user_agent_when_enabled() -> None:
    common = {
        "app_env": "dev",
        "app_name": "Your Fitness Coach",
        "app_debug": False,
        "secret_key": "test-secret",
        "access_token_expire_minutes": 60,
        "refresh_token_expire_days": 30,
        "database_url": "sqlite://",
        "telegram_bot_token": "test-token",
    }
    with pytest.raises(ValidationError, match="OPEN_FOOD_FACTS_USER_AGENT"):
        Settings(**common, food_provider="open_food_facts")
    configured = Settings(
        **common,
        food_provider="open_food_facts",
        open_food_facts_user_agent="YourFitnessCoach/1.0 (ops@example.test)",
    )
    assert configured.food_provider == "open_food_facts"
    assert configured.food_provider_timeout_seconds == 4
    with pytest.raises(ValidationError):
        Settings(
            **common,
            food_provider="open_food_facts",
            open_food_facts_user_agent="YourFitnessCoach/1.0 (ops@example.test)",
            food_provider_timeout_seconds=0.9,
        )
    configured_timeout = Settings(
        **common,
        food_provider="open_food_facts",
        open_food_facts_user_agent="YourFitnessCoach/1.0 (ops@example.test)",
        food_provider_timeout_seconds=6,
    )
    assert configured_timeout.food_provider_timeout_seconds == 6
    with pytest.raises(ValidationError, match="USDA_FDC_API_KEY"):
        Settings(**common, food_usda_enabled=True)
    usda_configured = Settings(
        **common,
        food_usda_enabled=True,
        usda_fdc_api_key="server-side-key",
    )
    assert usda_configured.food_usda_enabled is True
    assert usda_configured.usda_fdc_api_key.get_secret_value() == "server-side-key"
    assert "server-side-key" not in repr(usda_configured)
    proxied = Settings(
        **common,
        food_usda_enabled=True,
        usda_fdc_api_key="server-side-key",
        usda_fdc_proxy_url=" socks5h://host.docker.internal:1082 ",
    )
    assert proxied.usda_fdc_proxy_url == "socks5h://host.docker.internal:1082"
    for invalid_proxy in (
        "https://example.com:443",
        "socks5://remote.example.org:1082",
        "socks5h://username:secret@localhost:1082",
        "socks5h://localhost:1082/other",
        "socks5h://localhost:1082?key=exposed",
        "socks5h://localhost",
        "socks5h://localhost:99999",
    ):
        with pytest.raises(ValidationError, match="USDA_FDC_PROXY_URL"):
            Settings(**common, usda_fdc_proxy_url=invalid_proxy)


def test_usda_provider_uses_proxy_only_when_explicitly_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured_proxy = "socks5h://host.docker.internal:1082"
    captured_proxies: list[str | None] = []
    actual_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.nal.usda.gov"
        return httpx.Response(200, request=request, json={"foods": []})

    def client_spy(**kwargs):
        captured_proxies.append(kwargs.pop("proxy"))
        kwargs["transport"] = httpx.MockTransport(handler)
        return actual_client(**kwargs)

    monkeypatch.setattr(usda_module, "_REQUEST_BUDGET", usda_module.RequestBudget(15))
    monkeypatch.setattr(usda_module.httpx, "Client", client_spy)
    proxied = USDAFoodDataCentralProvider(api_key="test-key", proxy_url=configured_proxy)
    direct = USDAFoodDataCentralProvider(api_key="test-key")
    assert proxied.search("rice", limit=2) == []
    assert direct.search("rice", limit=2) == []
    assert captured_proxies == [configured_proxy, None]
