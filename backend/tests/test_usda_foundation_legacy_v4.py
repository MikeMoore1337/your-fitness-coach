"""Проверки смешанного USDA набора и безопасной квартальной сверки без сети."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import httpx
import pytest
from scripts.export_usda_reviewed_catalog import CuratedCatalogError, build_catalog

from fitminiapp_api.services.food_search_aliases import (
    USDA_RU_DISPLAY_NAMES_V3,
    USDA_RU_DISPLAY_NAMES_V4,
    USDA_RU_DISPLAY_VERSION_V4,
    generic_food_search_query,
    usda_ru_result_ids,
)
from fitminiapp_api.services.usda_food_data_central import USDAFoodDataCentralProvider
from fitminiapp_api.services.usda_reviewed_foundation_legacy import (
    USDA_REVIEWED_FOUNDATION_LEGACY_V4,
    USDA_REVIEWED_SEARCH_GROUPS_V4,
)


def _food(
    fdc_id: str,
    *,
    data_type: str | None = None,
    description: str | None = None,
    energy_id: int = 2048,
    energy_unit: str = "kcal",
) -> dict:
    _name, english, kind = USDA_REVIEWED_FOUNDATION_LEGACY_V4[fdc_id]
    nutrients = [
        {"nutrient": {"id": energy_id, "unitName": energy_unit}, "amount": 123},
        {"nutrient": {"id": 1003, "unitName": "g"}, "amount": 5},
        {"nutrient": {"id": 1004, "unitName": "g"}, "amount": 3},
        {"nutrient": {"id": 1005, "unitName": "g"}, "amount": 23},
    ]
    return {
        "fdcId": int(fdc_id),
        "dataType": data_type or kind,
        "description": description or english,
        "foodNutrients": nutrients,
    }


def _client(raw: list[dict]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.nal.usda.gov"
        assert request.url.params["api_key"] == "fixture-key"
        return httpx.Response(200, json=raw, request=request)

    return httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)


def test_v4_ids_are_unambiguous_and_reviewed() -> None:
    assert len(USDA_RU_DISPLAY_NAMES_V3) == 215
    assert len(USDA_REVIEWED_FOUNDATION_LEGACY_V4) == 18
    assert set(USDA_REVIEWED_FOUNDATION_LEGACY_V4).isdisjoint(USDA_RU_DISPLAY_NAMES_V3)
    assert len(USDA_RU_DISPLAY_NAMES_V4) == 233
    assert {data[2] for data in USDA_REVIEWED_FOUNDATION_LEGACY_V4.values()} == {
        "Foundation",
        "SR Legacy",
    }
    for values in USDA_REVIEWED_SEARCH_GROUPS_V4.values():
        assert set(values).issubset(USDA_REVIEWED_FOUNDATION_LEGACY_V4)
    assert all(USDA_RU_DISPLAY_NAMES_V4[k] == v for k, v in USDA_RU_DISPLAY_NAMES_V3.items())


@pytest.mark.parametrize("fdc_id", ["1750340", "2646170", "2346393", "2258586"])
def test_foundation_uses_reported_atwater_specific_energy_when_1008_missing(fdc_id: str) -> None:
    parsed = USDAFoodDataCentralProvider._parse_food(_food(fdc_id), require_russian_name=True)
    assert parsed is not None and parsed.energy_kcal_per_100g == Decimal(123)
    assert parsed.name == USDA_RU_DISPLAY_NAMES_V4[fdc_id]


def test_energy_priority_and_refusal_to_invent_value() -> None:
    food = _food("1750340", energy_id=2047)
    food["foodNutrients"].append({"nutrient": {"id": 2048, "unitName": "kcal"}, "amount": 115})
    p = USDAFoodDataCentralProvider._parse_food(food, require_russian_name=True)
    assert p is not None and p.energy_kcal_per_100g == Decimal(115)
    food["foodNutrients"].append({"nutrient": {"id": 1008, "unitName": "kcal"}, "amount": 89})
    p = USDAFoodDataCentralProvider._parse_food(food, require_russian_name=True)
    assert p is not None and p.energy_kcal_per_100g == Decimal(89)
    bad = _food("1750340", energy_id=2048, energy_unit="kJ")
    assert USDAFoodDataCentralProvider._parse_food(bad, require_russian_name=True) is None
    assert (
        USDAFoodDataCentralProvider._parse_food(
            _food("170379", energy_id=2048), require_russian_name=True
        )
        is None
    )


@pytest.mark.parametrize("fdc_id", ["171077", "173944", "170567"])
def test_sr_legacy_old_energy_1008(fdc_id: str) -> None:
    p = USDAFoodDataCentralProvider._parse_food(
        _food(fdc_id, energy_id=1008),
        require_russian_name=True,
    )
    assert p is not None and p.provider == "usda_fdc"


@pytest.mark.parametrize(
    "name,kind",
    [
        ("Broccoli, cooked", "Foundation"),
        ("Broccoli, raw", "SR Legacy"),
    ],
)
def test_reviewed_identity_rejects_description_or_dataset_drift(name: str, kind: str) -> None:
    raw = _food("747447", data_type=kind, description=name)
    assert USDAFoodDataCentralProvider._parse_food(raw, require_russian_name=True) is None
    with _client([raw]) as client, pytest.raises(CuratedCatalogError):
        build_catalog(
            client,
            api_key="fixture-key",
            reviewed_at=date(2026, 10, 11),
            ids=("747447",),
        )


def test_v4_export_has_verified_version_source_and_no_synthetic_fiber() -> None:
    ids = ("1750340", "747447", "173944")
    items = [_food(fid, energy_id=2048 if fid != "173944" else 1008) for fid in ids]
    with _client(items) as client:
        catalog = build_catalog(
            client,
            api_key="fixture-key",
            reviewed_at=date(2026, 10, 11),
            ids=ids,
        )
    assert catalog.source.version == USDA_RU_DISPLAY_VERSION_V4
    assert catalog.source.license == "CC0-1.0"
    assert len(catalog.foods) == len(ids)
    assert all(food.fiber_g_per_100g is None for food in catalog.foods)


def test_precise_russian_queries_do_not_merge_preparation_states() -> None:
    assert generic_food_search_query("рис бурый сухой") == "rice brown raw"
    assert "2512380" in usda_ru_result_ids("рис бурый сухой")
    assert "2708409" not in usda_ru_result_ids("рис бурый сухой")
    assert "171689" in usda_ru_result_ids("яблоко без кожуры")
    assert "1750340" not in usda_ru_result_ids("яблоко без кожуры")
