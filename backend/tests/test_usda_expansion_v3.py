"""Проверки новой проверенной русскоязычной подборки USDA без сети."""

from __future__ import annotations

from datetime import date

import httpx
import pytest
from scripts.compare_usda_reviewed_catalogs import compare_catalogs
from scripts.export_usda_reviewed_catalog import CuratedCatalogError, build_catalog

from fitminiapp_api.services.food_search_aliases import (
    USDA_RU_DISPLAY_NAMES_V2,
    USDA_RU_DISPLAY_NAMES_V3,
    USDA_RU_DISPLAY_VERSION_V3,
    generic_food_search_query,
    has_generic_food_alias,
    usda_ru_result_ids,
)
from fitminiapp_api.services.usda_food_data_central import USDAFoodDataCentralProvider
from fitminiapp_api.services.usda_reviewed_expansion import (
    USDA_REVIEWED_FNDDS_EXPANSION_V3,
    USDA_REVIEWED_SEARCH_GROUPS_V3,
)


def _fdc_response(fdc_id: str, *, name_override: str | None = None) -> dict:
    reviewed_name = USDA_REVIEWED_FNDDS_EXPANSION_V3[fdc_id][1]
    return {
        "fdcId": int(fdc_id),
        "description": name_override if name_override is not None else reviewed_name,
        "dataType": "Survey (FNDDS)",
        "foodNutrients": [
            {"nutrient": {"id": nutrient, "unitName": unit}, "amount": amount}
            for nutrient, unit, amount in (
                (1008, "kcal", 123),
                (1003, "g", 7),
                (1004, "g", 2),
                (1005, "g", 19),
            )
        ],
    }


def _client(records: list[dict]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.nal.usda.gov"
        assert request.url.path == "/fdc/v1/foods"
        assert request.url.params["api_key"] == "synthetic-key"
        return httpx.Response(200, json=records, request=request)

    return httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)


def test_reviewed_v3_expands_exactly_without_modifying_previous_fdc_identities() -> None:
    assert len(USDA_RU_DISPLAY_NAMES_V2) == 118
    assert len(USDA_REVIEWED_FNDDS_EXPANSION_V3) >= 80
    assert set(USDA_REVIEWED_FNDDS_EXPANSION_V3).isdisjoint(USDA_RU_DISPLAY_NAMES_V2)
    assert len(USDA_RU_DISPLAY_NAMES_V3) == 118 + len(USDA_REVIEWED_FNDDS_EXPANSION_V3)
    assert all(
        value == USDA_RU_DISPLAY_NAMES_V3[key] for key, value in USDA_RU_DISPLAY_NAMES_V2.items()
    )
    assert all(
        source and russian and not any("а" <= x <= "я" for x in source.lower())
        for russian, source in USDA_REVIEWED_FNDDS_EXPANSION_V3.values()
    )
    for ids in USDA_REVIEWED_SEARCH_GROUPS_V3.values():
        assert ids and set(ids).issubset(USDA_REVIEWED_FNDDS_EXPANSION_V3)


@pytest.mark.parametrize(
    ("query", "english", "expected", "excluded"),
    [
        ("морковь сырая", "carrots raw", "2709660", "2709661"),
        ("макароны цельнозерновые", "pasta whole grain cooked", "2708358", "2708357"),
        ("лосось на пару", "fish salmon steamed", "2706290", "2706289"),
        ("бедро куриное без кожи", "chicken thigh skin not eaten", "2706036", "2706035"),
        ("клубника сырая", "strawberries raw", "2709283", "2709284"),
    ],
)
def test_precise_russian_alias_does_not_expand_to_wrong_preparation(
    query: str, english: str, expected: str, excluded: str
) -> None:
    assert has_generic_food_alias(query)
    assert generic_food_search_query(query) == english
    assert expected in usda_ru_result_ids(query)
    assert excluded not in usda_ru_result_ids(query)


def test_v3_catalog_has_curated_russian_names_and_CC0_provenance() -> None:
    selected = ("2709643", "2708358", "2706284")
    with _client([_fdc_response(id_) for id_ in selected]) as transport:
        catalog = build_catalog(
            transport,
            api_key="synthetic-key",
            reviewed_at=date(2026, 10, 11),
            ids=selected,
        )
    assert catalog.source.version == USDA_RU_DISPLAY_VERSION_V3
    assert catalog.source.license == "CC0-1.0"
    assert all(
        record.name == USDA_RU_DISPLAY_NAMES_V3[record.external_id] for record in catalog.foods
    )
    assert all(record.fiber_g_per_100g is None for record in catalog.foods)


def test_reviewed_v3_rejects_identity_reused_with_different_english_description() -> None:
    selected = ("2709643",)
    with (
        _client(
            [_fdc_response("2709643", name_override="Broccoli, steamed in butter")]
        ) as transport,
        pytest.raises(
            CuratedCatalogError, match="unknown, duplicated, or has incomplete nutrients"
        ),
    ):
        build_catalog(
            transport, api_key="synthetic-key", reviewed_at=date(2026, 10, 11), ids=selected
        )
    assert (
        USDAFoodDataCentralProvider._parse_food(
            _fdc_response("2709643", name_override="Broccoli, steamed in butter"),
            require_russian_name=True,
        )
        is None
    )


def test_v3_catalog_comparator_rejects_factual_changes_and_removals() -> None:
    def build(ids: tuple[str, ...], *, name_override: str | None = None):
        records = [
            _fdc_response(id_, name_override=name_override if id_ == "2709643" else None)
            for id_ in ids
        ]
        with _client(records) as transport:
            return build_catalog(
                transport, api_key="synthetic-key", reviewed_at=date(2026, 10, 11), ids=ids
            )

    previous = build(("2709643",))
    extended = build(("2709643", "2706284"))
    healthy = compare_catalogs(previous, extended)
    assert healthy.safe_for_reviewed_extension
    assert healthy.new_ids == ("2706284",)
    assert not healthy.changed_ids
    removed = compare_catalogs(extended, previous)
    assert not removed.safe_for_reviewed_extension
    assert removed.removed_ids == ("2706284",)

    updated = extended.model_copy(deep=True)
    next(item for item in updated.foods if item.external_id == "2709643").energy_kcal_per_100g += 1
    changed = compare_catalogs(previous, updated)
    assert not changed.safe_for_reviewed_extension
    assert changed.changed_ids == ("2709643",)
