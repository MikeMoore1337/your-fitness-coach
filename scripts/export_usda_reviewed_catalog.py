"""Create a reviewed, reproducible CC0 USDA catalog snapshot; never mutate the DB."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from fitminiapp_api.schemas.food import FoodCatalog  # noqa: E402
from fitminiapp_api.services.food_search_aliases import (  # noqa: E402
    USDA_RU_DISPLAY_NAMES_V4,
    USDA_RU_DISPLAY_VERSION_V4,
)
from fitminiapp_api.services.usda_food_data_central import (  # noqa: E402
    USDAFoodDataCentralProvider,
)
from fitminiapp_api.services.usda_reviewed_expansion import (  # noqa: E402
    USDA_REVIEWED_FNDDS_EXPANSION_V3,
)

_API_URL = "https://api.nal.usda.gov/fdc/v1/foods"
_BATCH_SIZE = 20


class CuratedCatalogError(ValueError):
    pass


def build_catalog(
    client: httpx.Client,
    *,
    api_key: str,
    reviewed_at: date,
    ids: tuple[str, ...] | None = None,
) -> FoodCatalog:
    """Only import verified FDC identities already bearing reviewed Russian labels."""

    selected = ids if ids is not None else tuple(sorted(USDA_RU_DISPLAY_NAMES_V4, key=int))
    if not selected or len(selected) != len(set(selected)):
        raise CuratedCatalogError("FDC IDs must be nonempty and unique")
    if any(item not in USDA_RU_DISPLAY_NAMES_V4 for item in selected):
        raise CuratedCatalogError("an FDC identity lacks an approved Russian label")
    if not api_key.strip():
        raise CuratedCatalogError("USDA_FDC_API_KEY is required")

    foods: list[dict[str, object]] = []
    for start in range(0, len(selected), _BATCH_SIZE):
        batch = selected[start : start + _BATCH_SIZE]
        try:
            response = client.post(
                _API_URL,
                params={"api_key": api_key},
                json={"fdcIds": [int(item) for item in batch], "format": "full"},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise CuratedCatalogError("USDA batch could not be retrieved or decoded") from exc
        if not isinstance(payload, list) or len(payload) != len(batch):
            raise CuratedCatalogError("USDA returned a missing or extra FDC identity")
        found: set[str] = set()
        for raw in payload:
            food = USDAFoodDataCentralProvider._parse_food(raw, require_russian_name=True)
            if (
                food is None
                or food.external_id not in batch
                or food.external_id in found
                or (
                    food.external_id in USDA_REVIEWED_FNDDS_EXPANSION_V3
                    and (
                        raw.get("dataType") != "Survey (FNDDS)"
                        or " ".join(str(raw.get("description", "")).split())
                        != USDA_REVIEWED_FNDDS_EXPANSION_V3[food.external_id][1]
                    )
                )
            ):
                raise CuratedCatalogError(
                    "USDA record is unknown, duplicated, or has incomplete nutrients"
                )
            found.add(food.external_id)
            foods.append(
                {
                    "external_id": food.external_id,
                    "food_type": "system",
                    "name": food.name,
                    "energy_kcal_per_100g": food.energy_kcal_per_100g,
                    "protein_g_per_100g": food.protein_g_per_100g,
                    "fat_g_per_100g": food.fat_g_per_100g,
                    "carbs_g_per_100g": food.carbs_g_per_100g,
                    "fiber_g_per_100g": food.fiber_g_per_100g,
                    "status": "active",
                }
            )
        if found != set(batch):
            raise CuratedCatalogError("USDA omitted an expected reviewed FDC identity")
    return FoodCatalog.model_validate(
        {
            "schema_version": 1,
            "source": {
                "name": "usda-fdc-reviewed-ru",
                "version": USDA_RU_DISPLAY_VERSION_V4,
                "source_url": "https://fdc.nal.usda.gov/",
                "license": "CC0-1.0",
                "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                "reviewed_by": "YFC reviewed Russian FDC alias mapping v4",
                "reviewed_at": reviewed_at.isoformat(),
                "license_verified": True,
            },
            "foods": sorted(foods, key=lambda item: int(str(item["external_id"]))),
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--limit", type=int, default=None, help="Restrict to the first N reviewed IDs"
    )
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    key = os.getenv("USDA_FDC_API_KEY", "")
    proxy = os.getenv("USDA_FDC_PROXY_URL", "").strip() or None
    selected = tuple(sorted(USDA_RU_DISPLAY_NAMES_V4, key=int))
    if args.limit is not None:
        selected = selected[: args.limit]
    if args.output.exists():
        parser.error("output exists: refusing to overwrite an unreviewed snapshot")
    with httpx.Client(proxy=proxy, trust_env=False, timeout=12, follow_redirects=False) as client:
        catalog = build_catalog(client, api_key=key, reviewed_at=date.today(), ids=selected)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(catalog.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Validated snapshot: {len(catalog.foods)} reviewed USDA records; no DB writes")


if __name__ == "__main__":
    main()
