from __future__ import annotations

from datetime import date
from decimal import Decimal

import httpx
import pytest
from scripts.export_usda_reviewed_catalog import CuratedCatalogError, build_catalog

from fitminiapp_api.services.food_search_aliases import USDA_RU_DISPLAY_NAMES_V2


def _fdc_record(fdc_id: int, *, energy: float = 120) -> dict:
    values = ((1008, "kcal", energy), (1003, "g", 5), (1004, "g", 3), (1005, "g", 22))
    return {
        "fdcId": fdc_id,
        "description": "USDA test raw food description",
        "dataType": "Survey (FNDDS)",
        "foodNutrients": [
            {"nutrient": {"id": nutrient, "unitName": unit}, "amount": amount}
            for nutrient, unit, amount in values
        ],
    }


def _mock_client(ids: tuple[int, ...], *, response_override=None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.nal.usda.gov"
        assert request.url.path == "/fdc/v1/foods"
        assert request.url.params["api_key"] == "safe-test-key"
        payload = (
            response_override if response_override is not None else [_fdc_record(i) for i in ids]
        )
        return httpx.Response(200, json=payload, request=request)

    return httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)


def test_usda_reviewed_catalog_is_reproducible_and_has_official_provenance() -> None:
    ids = tuple(int(value) for value in sorted(USDA_RU_DISPLAY_NAMES_V2, key=int)[:2])
    with _mock_client(ids) as client:
        catalog = build_catalog(
            client,
            api_key="safe-test-key",
            reviewed_at=date(2026, 10, 11),
            ids=tuple(map(str, ids)),
        )
    assert [item.external_id for item in catalog.foods] == list(map(str, ids))
    assert all(item.name == USDA_RU_DISPLAY_NAMES_V2[item.external_id] for item in catalog.foods)
    assert catalog.source.name == "usda-fdc-reviewed-ru"
    assert catalog.source.license == "CC0-1.0"
    assert catalog.source.license_verified
    assert all(item.food_type == "system" and item.barcode is None for item in catalog.foods)
    assert all(item.energy_kcal_per_100g == Decimal("120") for item in catalog.foods)


@pytest.mark.parametrize(
    "bad_data",
    [
        [],
        [_fdc_record(999999)],
        [_fdc_record(2705385, energy=120), _fdc_record(2705385, energy=120)],
        [_fdc_record(2705385, energy=1200)],
    ],
)
def test_usda_reviewed_catalog_fails_closed_on_unknown_or_incomplete_source(bad_data) -> None:
    ids = ("2705385",)
    with (
        _mock_client((2705385,), response_override=bad_data) as client,
        pytest.raises(CuratedCatalogError),
    ):
        build_catalog(client, api_key="safe-test-key", reviewed_at=date(2026, 10, 11), ids=ids)


def test_usda_reviewed_catalog_rejects_ids_not_in_approved_ru_mapping() -> None:
    with (
        _mock_client((999999,)) as client,
        pytest.raises(CuratedCatalogError, match="approved Russian label"),
    ):
        build_catalog(
            client, api_key="safe-test-key", reviewed_at=date(2026, 10, 11), ids=("999999",)
        )


def test_curated_usda_catalog_upsert_is_idempotent_and_public(client) -> None:
    from fitminiapp_api.db.session import get_session_context
    from fitminiapp_api.models.food import Food
    from fitminiapp_api.services.food_import import import_food_catalog

    fdc_id = 2705385
    with _mock_client((fdc_id,)) as upstream:
        catalog = build_catalog(
            upstream,
            api_key="safe-test-key",
            reviewed_at=date(2026, 10, 11),
            ids=(str(fdc_id),),
        )
    with get_session_context() as db:
        first = import_food_catalog(db, catalog)
    with get_session_context() as db:
        second = import_food_catalog(db, catalog)
        entries = (
            db.query(Food)
            .filter(
                Food.source_name == "usda-fdc-reviewed-ru",
                Food.external_id == str(fdc_id),
            )
            .all()
        )
        assert len(entries) == 1
        food = entries[0]
        assert food.food_type == "system"
        assert food.owner_user_id is None
        assert food.trust_level == "verified"
        assert food.source_license == "CC0-1.0"
        assert food.name == USDA_RU_DISPLAY_NAMES_V2[str(fdc_id)]
    assert (first.created, first.updated) == (1, 0)
    assert (second.created, second.updated) == (0, 1)
